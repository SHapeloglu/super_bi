"""
Güvenlik regresyon testleri — Faz 0.6 (varsayılan sırların kabul edilmesi).

  - DATALENS_JWT_SECRET, DATALENS_DB_ENCRYPTION_KEY, DATALENS_DB tanımlı değilse uygulama açılmaz.
  - Şifreleme anahtarı ve JWT secret için rastgele geçici değer üretilmez (restart'ta veri kaybolur).
  - DATALENS_DB için /tmp varsayılanı yoktur.
  - Hata mesajı değişken ADLARINI söyler, değerlerini asla yazdırmaz.

Çalıştırma:
  cd /opt/superbi && venv/bin/python tests/security/test_startup_secrets.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.core.startup_check import check_required_env  # noqa: E402

ZORUNLU = ["DATALENS_JWT_SECRET", "DATALENS_DB_ENCRYPTION_KEY", "DATALENS_DB"]
DEGER = "gizli-deger-123"


def _env(**kv):
    class _Ctx:
        def __enter__(self):
            self.old = {k: os.environ.get(k) for k in ZORUNLU}
            for k in ZORUNLU:
                os.environ.pop(k, None)
            for k, v in kv.items():
                os.environ[k] = v

        def __exit__(self, *a):
            for k, v in self.old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    return _Ctx()


def test_tum_degiskenler_varsa_gecer():
    with _env(DATALENS_JWT_SECRET=DEGER, DATALENS_DB_ENCRYPTION_KEY=DEGER, DATALENS_DB="/data/superbi.db"):
        check_required_env()


def test_jwt_secret_eksikse_durur():
    with _env(DATALENS_DB_ENCRYPTION_KEY=DEGER, DATALENS_DB="/data/x.db"):
        try:
            check_required_env()
        except RuntimeError as e:
            assert "DATALENS_JWT_SECRET" in str(e)
            assert DEGER not in str(e), "değer hata mesajında sızdı"
            return
    raise AssertionError("JWT secret eksikken açılışa izin verildi")


def test_sifreleme_anahtari_eksikse_durur():
    with _env(DATALENS_JWT_SECRET=DEGER, DATALENS_DB="/data/x.db"):
        try:
            check_required_env()
        except RuntimeError as e:
            assert "DATALENS_DB_ENCRYPTION_KEY" in str(e)
            return
    raise AssertionError("şifreleme anahtarı eksikken açılışa izin verildi")


def test_db_yolu_eksikse_durur():
    """DATALENS_DB yoksa /tmp varsayılanına düşülmez; açılış durur."""
    with _env(DATALENS_JWT_SECRET=DEGER, DATALENS_DB_ENCRYPTION_KEY=DEGER):
        try:
            check_required_env()
        except RuntimeError as e:
            assert "DATALENS_DB" in str(e)
            return
    raise AssertionError("DATALENS_DB eksikken açılışa izin verildi")


def test_bos_deger_eksik_sayilir():
    with _env(DATALENS_JWT_SECRET="   ", DATALENS_DB_ENCRYPTION_KEY=DEGER, DATALENS_DB="/data/x.db"):
        try:
            check_required_env()
        except RuntimeError:
            return
    raise AssertionError("boş JWT secret kabul edildi")


def test_crypto_rastgele_anahtar_uretmez():
    from app.core import crypto
    with _env(DATALENS_JWT_SECRET=DEGER, DATALENS_DB="/data/x.db"):
        try:
            crypto._get_fernet()
        except RuntimeError:
            return
    raise AssertionError("şifreleme anahtarı yokken rastgele anahtar üretildi")


def test_jwt_rastgele_secret_uretmez():
    from app.auth import jwt_core
    with _env(DATALENS_DB_ENCRYPTION_KEY=DEGER, DATALENS_DB="/data/x.db"):
        try:
            jwt_core.create_token("u1", "ali", "viewer")
        except RuntimeError:
            return
    raise AssertionError("JWT secret yokken rastgele secret ile token üretildi")


def test_lifespan_eksik_sirda_veritabani_acmadan_durur():
    """Uygulama lifespan'i eksik sırla başlatılamaz (DB açılmadan önce durmalı)."""
    from app.main import app, lifespan
    with _env():
        async def _run():
            async with lifespan(app):
                pass
        try:
            asyncio.run(_run())
        except RuntimeError:
            return
    raise AssertionError("eksik sırla uygulama açıldı")


def test_main_tmp_varsayilani_yok():
    path = os.path.join(ROOT, "app", "main.py")
    with open(path, encoding="utf-8") as f:
        kaynak = f.read()
    assert "/tmp/datalens.db" not in kaynak, "main.py hâlâ /tmp varsayılanı içeriyor"


TESTS = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]


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
