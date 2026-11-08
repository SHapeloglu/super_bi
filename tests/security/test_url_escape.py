"""
Güvenlik regresyon testi — Faz 0.5 (bağlantı URL'lerinde escape eksikliği).

database / user / password alanlarında '?', '/', '@', ':' gibi karakterler bulunduğunda
üretilen URL ayrıştırıldığında değerler aynen geri gelmeli (URL bozulmamalı, enjeksiyon olmamalı).

Çalıştırma:
  cd /opt/superbi && venv/bin/python tests/security/test_url_escape.py
"""
from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy.engine import make_url  # noqa: E402

from app.core.connector_registry import ConnectorRegistry  # noqa: E402

ZOR_DB = "veri?tabani/x@y"
ZOR_USER = "kul@ad:1"
ZOR_PASS = "p/ss?w@rd:#%"
HOST = "postgres-ortak"

os.environ["DATALENS_ALLOWED_DB_HOSTS"] = "postgres-ortak,mysql-ortak,mssql-ortak,oracle-ortak"


def _url(db_type: str, **kw) -> str:
    params = {"host": HOST, "port": 5432, "database": ZOR_DB, "user": ZOR_USER, "password": ZOR_PASS}
    params.update(kw)
    return ConnectorRegistry()._build_url(db_type, params)


def test_postgres_ozel_karakterler_korunur():
    u = make_url(_url("postgresql"))
    assert u.database == ZOR_DB, f"database bozuldu: {u.database!r}"
    assert u.username == ZOR_USER, f"user bozuldu: {u.username!r}"
    assert u.password == ZOR_PASS, "password bozuldu"
    assert u.host == HOST


def test_mysql_ozel_karakterler_korunur():
    u = make_url(_url("mysql", port=3306))
    assert u.database == ZOR_DB
    assert u.password == ZOR_PASS


def test_mssql_ozel_karakterler_korunur():
    u = make_url(_url("mssql", port=1433))
    assert u.database == ZOR_DB, f"mssql database bozuldu: {u.database!r}"
    assert u.password == ZOR_PASS


def test_oracle_service_name_korunur():
    u = make_url(_url("oracle", port=1521, host="oracle-ortak"))
    assert u.query.get("service_name") == ZOR_DB, f"service_name bozuldu: {u.query!r}"
    assert u.password == ZOR_PASS


def test_enjeksiyon_ek_sorgu_parametresi_uretmez():
    """database içine '?x=1' eklenmiş değer, URL'ye ek sorgu parametresi olarak girmemeli."""
    u = make_url(_url("postgresql", database="db?sslmode=disable"))
    assert u.database == "db?sslmode=disable"
    assert "sslmode" not in u.query, "database değeri URL sorgusu olarak yorumlandı"


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
