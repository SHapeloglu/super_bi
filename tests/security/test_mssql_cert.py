"""
Güvenlik regresyon testi — MSSQL sertifika doğrulaması (MITM riski).

Önceden MSSQL URL'lerinde TrustServerCertificate=yes sabitti; sunucu sertifikası
doğrulanmıyordu. Artık varsayılan doğrulamadır (TrustServerCertificate=no).
Kendinden imzalı sertifika kullanan kurumlar bilinçli olarak
DATALENS_MSSQL_TRUST_CERT=yes ayarlayabilir; yalnızca tam "yes" değeri kabul edilir.

Çalıştırma:
  cd <proje> && <python> tests/security/test_mssql_cert.py
"""
from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.core.connector_registry import ConnectorRegistry  # noqa: E402

HOST = "mssql-ortak"
ENV_KEY = "DATALENS_MSSQL_TRUST_CERT"

os.environ["DATALENS_ALLOWED_DB_HOSTS"] = "mssql-ortak"


def _trust_value():
    """URL nesnesinin sorgu parametresindeki TrustServerCertificate değeri."""
    params = {"host": HOST, "port": 1433, "database": "db", "user": "u", "password": "p"}
    url = ConnectorRegistry()._build_url("mssql", params)
    return url.query.get("TrustServerCertificate")


def _with_env(value):
    """ENV_KEY'i geçici olarak ayarlar (None → tanımsız)."""
    def deco(fn):
        def wrapper():
            old = os.environ.pop(ENV_KEY, None)
            try:
                if value is not None:
                    os.environ[ENV_KEY] = value
                fn()
            finally:
                os.environ.pop(ENV_KEY, None)
                if old is not None:
                    os.environ[ENV_KEY] = old
        wrapper.__name__ = fn.__name__
        return wrapper
    return deco


@_with_env(None)
def test_varsayilan_sertifika_dogrulanir():
    assert _trust_value() == "no", f"varsayılan doğrulama kapalı: {_trust_value()!r}"


@_with_env("yes")
def test_acik_istek_ile_guvensiz_mod_calisir():
    assert _trust_value() == "yes", f"DATALENS_MSSQL_TRUST_CERT=yes etkisiz: {_trust_value()!r}"


@_with_env("YES ")
def test_tam_yes_disinda_deger_kabul_edilmez():
    assert _trust_value() == "no", f"geçersiz değer kabul edildi: {_trust_value()!r}"


TESTS = [
    test_varsayilan_sertifika_dogrulanir,
    test_acik_istek_ile_guvensiz_mod_calisir,
    test_tam_yes_disinda_deger_kabul_edilmez,
]


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
