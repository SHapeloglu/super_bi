"""
query_executor.py
------------------
YENİDEN OLUŞTURULDU: Bu dosya orijinal projede vardı ama diskten silindi.
query.py'deki kullanım şekline (execute, stream_execute, commit, invalidate,
purge_expired, cache_stats) ve proje memory notlarındaki "üç durumlu cache
(none → temp 30sn → committed 5dk)" prensibine göre yeniden yazıldı.

Önemli mimari kural: "Önce gör, onay verince al" —
  1) /run  çağrısı sonucu HER ZAMAN geçici cache'e (30sn) yazılır (commit=False ise)
  2) /commit çağrısı bu cache_key'i kalıcı cache'e (5dk) taşır (commit=True verilerek
     de doğrudan /run'da yapılabilir)
  3) mode='memory' aynı sorgu tekrar çalıştırıldığında DB'ye gitmeden cache'ten döner
     mode='live' her zaman DB'ye gider (ama sonucu yine cache'e yazar)
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Süreler saniye cinsindendir. Onaysız (geçici) sonuç 30 sn, commit edilmiş (kalıcı) sonuç 5 dk saklanır.
_TEMP_TTL_SECONDS      = 30
_COMMITTED_TTL_SECONDS = 5 * 60


@dataclass
class _CacheEntry:
    """
    Cache'te tutulan tek bir sorgu sonucu.
    expires_at (Unix zamanı, saniye) geçtiyse kayıt geçersizdir. committed=True ise kalıcı kayıttır, değilse geçici.
    """
    conn_id:    str
    user_id:    str
    columns:    list[str]
    rows:       list[list[Any]]
    row_count:  int
    exec_ms:    float
    created_at: float
    expires_at: float
    committed:  bool = False


class QueryExecutor:
    """
    Tüm cache state'i process belleğinde tutulur (tek worker/process varsayımı —
    çoklu worker'da harici bir cache (Redis vb.) gerekir, bu bilinçli bir
    sınırlamadır).
    """

    def __init__(self) -> None:
        """Boş cache sözlüğü ve bir kilit (Lock) oluşturur. Kilit, aynı anda birden çok isteğin cache'i bozmasını önler."""
        self._cache: dict[str, _CacheEntry] = {}
        # Thread kilidi: sunucu birden çok isteği paralel işleyebilir; cache sözlüğünü aynı anda değiştirmeyi engeller.
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Cache key üretimi — fingerprint mantığıyla tutarlı: aynı user+conn+sql+params
    # ------------------------------------------------------------------

    @staticmethod
    def _make_cache_key(user_id: str, conn_id: str, sql: str, params: dict, sample: int) -> str:
        """
        Kullanıcı, bağlantı, SQL, parametre ve satır sınırından kısa bir cache anahtarı üretir (SHA-256 özetinin ilk 24 karakteri).
        Aynı girdi her zaman aynı anahtarı verir. DİKKAT: mode anahtara dahil değildir (memory modu live ile yazılmış kaydı okuyabilsin diye).
        """
        payload = json.dumps(
            {"u": user_id, "c": conn_id, "sql": sql, "p": params, "s": sample},
            sort_keys=True, default=str,
        )
        # SHA-256 özetinin ilk 24 karakteri (96 bit) anahtar olarak yeterlidir; kısa tutulur.
        return hashlib.sha256(payload.encode()).hexdigest()[:24]

    # ------------------------------------------------------------------
    # Ana sorgu çalıştırma — sample + commit + mode
    # ------------------------------------------------------------------

    def execute(
        self,
        engine:   Engine,
        sql:      str,
        params:   dict,
        sample:   int,
        commit:   bool,
        mode:     str,
        user_id:  str,
        conn_id:  str,
    ) -> dict:
        """
        Sorguyu çalıştırır ve sonucu döner.
        mode='memory' ve geçerli bir cache kaydı varsa DB'ye gitmeden cache'ten döner.
        Aksi halde DB'de çalışır, en fazla sample satır alır ve sonucu cache'e yazar (commit=True ise 5 dk, değilse 30 sn).
        SQL hatası SQLAlchemy istisnası olarak yukarı taşınır.
        """
        cache_key = self._make_cache_key(user_id, conn_id, sql, params, sample)

        if mode == "memory":
            # DİKKAT: Cache'ten dönüşte commit=True ise kayıt kalıcılaştırılır (committed=True, 5 dk); commit=False ise kayıt olduğu gibi kalır.
            # Sample kontrol edilmez: önceki çağrıdan daha az satır dönebilir.
            cached = self._get_valid(cache_key)
            if cached is not None:
                if commit:
                    # Kilit altında yazıyoruz; başka bir thread aynı kaydı aynı anda değiştirebilir.
                    # Zaten kalıcıysa süreyi uzatmayız (kısaltmayız); geçiciyse 5 dakikalık kalıcı süreye geçer.
                    with self._lock:
                        if not cached.committed:
                            cached.committed = True
                            cached.expires_at = time.time() + _COMMITTED_TTL_SECONDS
                return self._entry_to_result(cache_key, cached, from_cache=True)

        t0 = time.perf_counter()
        with engine.connect() as conn:
            result = conn.execute(text(sql), params)
            columns = list(result.keys())
            # Sadece ilk sample satır alınır; geri kalan satırlar veritabanından okunmaz.
            fetched = result.fetchmany(sample)
            rows = [list(r) for r in fetched]
        exec_ms = (time.perf_counter() - t0) * 1000

        ttl = _COMMITTED_TTL_SECONDS if commit else _TEMP_TTL_SECONDS
        now = time.time()
        entry = _CacheEntry(
            conn_id=conn_id, user_id=user_id,
            columns=columns, rows=rows, row_count=len(rows),
            exec_ms=exec_ms, created_at=now, expires_at=now + ttl,
            committed=commit,
        )
        with self._lock:
            self._cache[cache_key] = entry

        return self._entry_to_result(cache_key, entry, from_cache=False)

    def _entry_to_result(self, cache_key: str, entry: _CacheEntry, from_cache: bool) -> dict:
        """Cache kaydını API'nin beklediği sözlük biçimine çevirir. from_cache alanı sonucun cache'ten gelip gelmediğini gösterir."""
        return {
            "columns":    entry.columns,
            "rows":       entry.rows,
            "row_count":  entry.row_count,
            "exec_ms":    round(entry.exec_ms, 2),
            "cache_key":  cache_key,
            "mode":       "memory" if from_cache else "live",
            "conn_id":    entry.conn_id,
            "committed":  entry.committed,
            "from_cache": from_cache,
        }

    def _get_valid(self, cache_key: str) -> _CacheEntry | None:
        """Geçerli (süresi dolmamış) cache kaydını döner. Süresi dolmuşsa kaydı siler ve None döner."""
        with self._lock:
            entry = self._cache.get(cache_key)
            if entry is None:
                return None
            if entry.expires_at < time.time():
                del self._cache[cache_key]
                return None
            return entry

    # ------------------------------------------------------------------
    # Commit — geçici cache'i kalıcıya taşı
    # ------------------------------------------------------------------

    def commit(self, cache_key: str, user_id: str | None = None) -> bool:
        """
        Geçici cache kaydını kalıcıya çevirir: committed=True yapar ve süresini 5 dakikaya uzatır.
        Kayıt yoksa, süresi dolmuşsa ya da kayıt başka bir kullanıcıya aitse False döner.
        """
        with self._lock:
            entry = self._cache.get(cache_key)
            if entry is not None and entry.user_id != user_id:
                return False
            if entry is None or entry.expires_at < time.time():
                self._cache.pop(cache_key, None)
                return False
            entry.committed = True
            entry.expires_at = time.time() + _COMMITTED_TTL_SECONDS
            return True

    # ------------------------------------------------------------------
    # Cache yönetimi
    # ------------------------------------------------------------------

    def invalidate(self, conn_id: str) -> int:
        """Bir bağlantıya ait tüm cache kayıtlarını siler (ör. bağlantı değiştiğinde). Silinen kayıt sayısını döner."""
        with self._lock:
            keys = [k for k, v in self._cache.items() if v.conn_id == conn_id]
            for k in keys:
                del self._cache[k]
            return len(keys)

    def purge_expired(self) -> int:
        """Süresi dolmuş kayıtları temizler ve sayısını döner. Bellek şişmesin diye periyodik çağrılabilir."""
        now = time.time()
        with self._lock:
            keys = [k for k, v in self._cache.items() if v.expires_at < now]
            for k in keys:
                del self._cache[k]
            return len(keys)

    def cache_stats(self) -> dict:
        """Cache'in özet sayılarını döner: toplam, aktif, kalıcı ve geçici kayıt sayıları."""
        with self._lock:
            entries = list(self._cache.values())
        now = time.time()
        active = [e for e in entries if e.expires_at >= now]
        return {
            "total_entries":     len(entries),
            "active_entries":    len(active),
            "committed_entries": sum(1 for e in active if e.committed),
            "temp_entries":      sum(1 for e in active if not e.committed),
        }

    # ------------------------------------------------------------------
    # Stream — büyük sonuçlar için, cache'e yazmaz
    # ------------------------------------------------------------------

    async def stream_execute(
        self, engine: Engine, sql: str, params: dict, sample: int,
    ) -> AsyncIterator[bytes]:
        """
        Büyük sonuçlar için satır satır JSON akışı üretir; cache'e yazmaz ve cache'ten okumaz.
        Her satır ayrı bir JSON nesnesidir: önce 'columns', sonra her satır için 'row', en sonda 'done'. sample en fazla kaç satır gideceğini belirler.
        """
        with engine.connect() as conn:
            result = conn.execute(text(sql), params)
            columns = list(result.keys())
            # Her satır ayrı bir JSON nesnesi (satır satır JSON). İstemci satırları tek tek okuyabilir.
            yield (json.dumps({"type": "columns", "columns": columns}) + "\n").encode()

            sent = 0
            while sent < sample:
                # Bir seferde en fazla 500 satır çekilir; hem bellek şişmez hem akış düzenli ilerler.
                batch = result.fetchmany(min(500, sample - sent))
                if not batch:
                    break
                for row in batch:
                    # default=str: tarih, ondalık sayı gibi JSON'a doğrudan çevrilemeyen değerleri metne çevirir.
                    yield (json.dumps({"type": "row", "row": list(row)}, default=str) + "\n").encode()
                sent += len(batch)

            yield (json.dumps({"type": "done", "row_count": sent}) + "\n").encode()
