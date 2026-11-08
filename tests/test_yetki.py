"""
test_yetki.py
--------------
Yetki ve kalıcılık testleri: ilk kullanıcının admin olması, commit sahipliği,
cache'ten dönüşte commit ve get_analysis_results sahiplik kontrolü.

Çalıştırma (pytest kurulu değilse düz Python yeterli):
  cd /opt/superbi && venv/bin/python tests/test_yetki.py

Veritabanı: yalnız bellekteki SQLiteStore(":memory:") ve sqlite:// motoru kullanılır.
Canlı data/superbi.db bu testlerde ASLA açılmaz.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback

# Proje kökü import yoluna eklenir; böylece "app" paketi bulunur.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import create_engine  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.auth.jwt_core import TokenData  # noqa: E402
from app.auth.user_repository import UserRepository  # noqa: E402
from app.api.analyze import get_analysis_results  # noqa: E402
from app.core.repository import ConnectionMeta, ConnectionRepository  # noqa: E402
from app.db.sqlite_store import SQLiteStore  # noqa: E402
from app.services.query_executor import QueryExecutor, _COMMITTED_TTL_SECONDS  # noqa: E402


# ---------------------------------------------------------------------------
# (a) İlk kullanıcı admin, sonrakiler viewer; eşzamanlı kayıtta tek admin
# ---------------------------------------------------------------------------

def test_ilk_kullanici_admin_digeri_viewer():
    repo = UserRepository(SQLiteStore(":memory:"))
    ilk = repo.create("ilk", "sifre-1")
    ikinci = repo.create("ikinci", "sifre-2")
    assert ilk.role == "admin", ilk.role
    assert ikinci.role == "viewer", ikinci.role


def test_acik_rol_verilirse_aynen_kullanilir():
    repo = UserRepository(SQLiteStore(":memory:"))
    # Tablo boşken bile açıkça verilen rol yazılır (eski davranış).
    yazar = repo.create("yazar", "sifre", role="viewer")
    assert yazar.role == "viewer", yazar.role
    # Tablo doluyken açıkça admin istenirse admin yazılır.
    ek_admin = repo.create("ek", "sifre", role="admin")
    assert ek_admin.role == "admin", ek_admin.role


def test_eszamanli_ilk_kayitlarda_tek_admin():
    store = SQLiteStore(":memory:")
    repo = UserRepository(store)
    n = 8
    # Barrier: tüm thread'ler aynı anda create çağrısına girsin diye bekletilir.
    baslangic = threading.Barrier(n)
    roller: list[str] = []
    hatalar: list[BaseException] = []
    kilit = threading.Lock()

    def kayit(i: int) -> None:
        try:
            baslangic.wait()
            user = repo.create(f"kullanici{i}", "sifre")
            with kilit:
                roller.append(user.role)
        except BaseException as e:  # thread içinde yakalanmazsa test sessizce geçer
            with kilit:
                hatalar.append(e)

    threads = [threading.Thread(target=kayit, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not hatalar, f"thread hatası: {hatalar[0]!r}"
    assert len(roller) == n, f"beklenen {n} kayıt, gelen {len(roller)}"
    assert roller.count("admin") == 1, f"admin sayısı: {roller.count('admin')} ({roller})"
    assert roller.count("viewer") == n - 1, roller
    assert store.table_row_count("users") == n


# ---------------------------------------------------------------------------
# (b) QueryExecutor.commit sahiplik kontrolü
# ---------------------------------------------------------------------------

def test_commit_sahiplik_kontrolu():
    ex = QueryExecutor()
    engine = create_engine("sqlite://")
    sonuc = ex.execute(
        engine, "SELECT 1 AS a", {}, sample=10, commit=False, mode="live",
        user_id="sahip", conn_id="c1",
    )
    anahtar = sonuc["cache_key"]

    # Başka kullanıcı commit edemez; kayıt geçici kalır.
    assert ex.commit(anahtar, user_id="baska") is False
    assert ex.cache_stats()["committed_entries"] == 0

    # Sahibi commit edebilir.
    assert ex.commit(anahtar, user_id="sahip") is True
    assert ex.cache_stats()["committed_entries"] == 1


# ---------------------------------------------------------------------------
# (c) Cache isabetinde commit=True kaydı kalıcılaştırır
# ---------------------------------------------------------------------------

def test_memory_isabetinde_commit_kaliciligi():
    ex = QueryExecutor()
    engine = create_engine("sqlite://")
    args = dict(sql="SELECT 1 AS a", params={}, sample=10, mode="memory",
                user_id="u1", conn_id="c1")

    # Önce geçici (commit=False) bir kayıt oluşturulur.
    ilk = ex.execute(engine, args["sql"], args["params"], args["sample"],
                     commit=False, mode="live", user_id="u1", conn_id="c1")
    anahtar = ilk["cache_key"]
    assert ex.cache_stats()["committed_entries"] == 0

    # Cache isabeti, commit=False: kayıt geçici kalır.
    isabet = ex.execute(engine, args["sql"], args["params"], args["sample"],
                        commit=False, mode="memory", user_id="u1", conn_id="c1")
    assert isabet["from_cache"] is True
    assert isabet["committed"] is False

    # Cache isabeti, commit=True: kayıt kalıcılaşır ve süresi 5 dakikaya çıkar.
    kalici = ex.execute(engine, args["sql"], args["params"], args["sample"],
                        commit=True, mode="memory", user_id="u1", conn_id="c1")
    assert kalici["from_cache"] is True
    assert kalici["committed"] is True
    assert kalici["cache_key"] == anahtar
    assert ex.cache_stats()["committed_entries"] == 1
    kalan = ex._cache[anahtar].expires_at - time.time()
    assert kalan > _COMMITTED_TTL_SECONDS - 5, f"TTL beklenenden kısa: {kalan:.1f} sn"

    # Zaten kalıcı kayıtta yeniden commit=True TTL'yi kısaltmamalı.
    sure_once = ex._cache[anahtar].expires_at
    ex.execute(engine, args["sql"], args["params"], args["sample"],
               commit=True, mode="memory", user_id="u1", conn_id="c1")
    assert ex._cache[anahtar].expires_at >= sure_once, "kalıcı kaydın TTL'si kısaldı"


# ---------------------------------------------------------------------------
# (d) get_analysis_results: başkasının bağlantısı 404, sahibine 200
#     TestClient yerine endpoint fonksiyonu doğrudan çağrılır (httpx kurulu değil).
# ---------------------------------------------------------------------------

def test_analiz_sonuclari_sahiplik():
    store = SQLiteStore(":memory:")
    repo = ConnectionRepository(store)
    conn_id = "baglanti-test-1"
    repo.save(ConnectionMeta(conn_id=conn_id, db_type="sqlite", host="",
                             database=":memory:", owner_id="sahip"))

    sahip = TokenData(user_id="sahip", username="sahip", role="viewer")
    baska = TokenData(user_id="baska", username="baska", role="viewer")

    # Sahibi sonucu alır.
    sonuc = get_analysis_results(conn_id, current=sahip, repo=repo, store=store)
    assert sonuc["conn_id"] == conn_id

    # Başkası 404 alır; bağlantının varlığı sızmaz.
    try:
        get_analysis_results(conn_id, current=baska, repo=repo, store=store)
    except HTTPException as e:
        assert e.status_code == 404, e.status_code
    else:
        raise AssertionError("başkasının bağlantısına 404 yerine cevap döndü")


# ---------------------------------------------------------------------------
# Düz Python çalıştırıcı (pytest yoksa)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    testler = [(ad, f) for ad, f in sorted(globals().items())
               if ad.startswith("test_") and callable(f)]
    basarili = 0
    for ad, f in testler:
        try:
            f()
            basarili += 1
            print(f"PASS {ad}")
        except Exception:
            print(f"FAIL {ad}")
            traceback.print_exc()
    print(f"\n{basarili}/{len(testler)} test geçti")
    sys.exit(0 if basarili == len(testler) else 1)
