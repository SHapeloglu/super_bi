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

_TEMP_TTL_SECONDS      = 30
_COMMITTED_TTL_SECONDS = 5 * 60


@dataclass
class _CacheEntry:
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
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Cache key üretimi — fingerprint mantığıyla tutarlı: aynı user+conn+sql+params
    # ------------------------------------------------------------------

    @staticmethod
    def _make_cache_key(user_id: str, conn_id: str, sql: str, params: dict) -> str:
        payload = json.dumps(
            {"u": user_id, "c": conn_id, "sql": sql, "p": params},
            sort_keys=True, default=str,
        )
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
        cache_key = self._make_cache_key(user_id, conn_id, sql, params)

        if mode == "memory":
            cached = self._get_valid(cache_key)
            if cached is not None:
                return self._entry_to_result(cache_key, cached, from_cache=True)

        t0 = time.perf_counter()
        with engine.connect() as conn:
            result = conn.execute(text(sql), params)
            columns = list(result.keys())
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

    def commit(self, cache_key: str) -> bool:
        with self._lock:
            entry = self._cache.get(cache_key)
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
        with self._lock:
            keys = [k for k, v in self._cache.items() if v.conn_id == conn_id]
            for k in keys:
                del self._cache[k]
            return len(keys)

    def purge_expired(self) -> int:
        now = time.time()
        with self._lock:
            keys = [k for k, v in self._cache.items() if v.expires_at < now]
            for k in keys:
                del self._cache[k]
            return len(keys)

    def cache_stats(self) -> dict:
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
        with engine.connect() as conn:
            result = conn.execute(text(sql), params)
            columns = list(result.keys())
            yield (json.dumps({"type": "columns", "columns": columns}) + "\n").encode()

            sent = 0
            while sent < sample:
                batch = result.fetchmany(min(500, sample - sent))
                if not batch:
                    break
                for row in batch:
                    yield (json.dumps({"type": "row", "row": list(row)}, default=str) + "\n").encode()
                sent += len(batch)

            yield (json.dumps({"type": "done", "row_count": sent}) + "\n").encode()
