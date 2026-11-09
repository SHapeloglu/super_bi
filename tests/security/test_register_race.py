"""
Regresyon testi — register kullanıcı adı yarışı.

Sorun: register kullanıcı adını önce sorgular, sonra ekler. İki istek aynı adı
aynı anda gönderirse ikincisi INSERT'te UNIQUE ihlali alır. Bu sqlite3.IntegrityError
olarak yukarı taşınır ve 500 döner. Beklenen: 409.

Çalıştırma:
  cd <worktree> && venv/bin/python tests/security/test_register_race.py
"""
from __future__ import annotations

import os
import sys
import threading
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# JWT secret zorunlu (token üretilecek); kayıt, ilk kullanıcı dışında açık olmalı.
os.environ.setdefault("DATALENS_JWT_SECRET", "yalnizca-test-icin-sir")
os.environ["DATALENS_ALLOW_REGISTER"] = "true"

from fastapi import HTTPException  # noqa: E402

from app.api import auth  # noqa: E402
from app.auth.user_repository import UserRepository  # noqa: E402
from app.db.sqlite_store import SQLiteStore  # noqa: E402
from app.models.schemas import UserRegister  # noqa: E402


def _repo() -> UserRepository:
    """Bellek içi SQLite üzerinde taze bir UserRepository döner."""
    return UserRepository(SQLiteStore(":memory:"))


def _body(username: str) -> UserRegister:
    """Geçerli bir kayıt isteği gövdesi üretir."""
    return UserRegister(username=username, password="sifre-12345")


def test_yaris_penceresinde_ayni_ad_409_doner():
    """Kontrol 'yok' derken kullanıcı araya girip eklenmişse register 409 vermeli (500 değil)."""
    repo = _repo()
    repo.create("ali_veli", "sifre-12345")
    # Yarış penceresini taklit et: sorgu adı boş görür, ama kayıt zaten vardır.
    repo.get_by_username = lambda username: None
    try:
        auth.register(_body("ali_veli"), repo)
    except HTTPException as e:
        assert e.status_code == 409, f"409 bekleniyordu, {e.status_code} geldi"
        return
    raise AssertionError("409 bekleniyordu ama kayıt kabul edildi")


def test_es_zamanli_ayni_ad_500_donmez():
    """Aynı adla eşzamanlı kayıtlarda tam bir başarı, geri kalanı 409 olmalı; hiçbiri 500 olmamalı."""
    repo = _repo()
    repo.create("baska_kullanici", "sifre-12345")  # tablo dolu: kayıt açık kalmalı
    sonuclar: list = []
    kilit = threading.Lock()
    bariyer = threading.Barrier(8)

    def istek():
        bariyer.wait()
        try:
            auth.register(_body("yaris_kullanici"), repo)
            durum = "ok"
        except HTTPException as e:
            durum = e.status_code
        except Exception as e:  # 500'e dönecek beklenmeyen hata
            durum = f"HATA:{type(e).__name__}"
        with kilit:
            sonuclar.append(durum)

    threads = [threading.Thread(target=istek) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(s in ("ok", 409) for s in sonuclar), f"Beklenmeyen sonuçlar: {sonuclar}"
    assert sonuclar.count("ok") == 1, f"Tam bir başarı bekleniyordu: {sonuclar}"


TESTS = [test_yaris_penceresinde_ayni_ad_409_doner, test_es_zamanli_ayni_ad_500_donmez]


if __name__ == "__main__":
    basarili, basarisiz = 0, 0
    for t in TESTS:
        try:
            t()
            print("PASS", t.__name__)
            basarili += 1
        except Exception:
            print("FAIL", t.__name__)
            traceback.print_exc()
            basarisiz += 1
    print(f"\n{basarili} geçti, {basarisiz} başarısız")
    sys.exit(1 if basarisiz else 0)
