"""
Apache Doris bağlantı testleri (Faz 1.1).

(a) _build_url("doris", ...) URL.create ile doğru URL üretir; port varsayılanı 9030.
(b) database / user / password içindeki özel karakterler URL'de bozulmadan geri gelir.
(c) DRIVER_MAP["doris"] doğru sürücü modülünü ve paketi gösterir.
(d) SQL üretimi: sql_builder doris için LIMIT kullanır; formül derleyici doris lehçesini kabul eder.
(e) Canlı Doris entegrasyonu: yalnız DATALENS_IT_DORIS_URL tanımlıysa çalışır, yoksa SKIP.
    Değer SQLAlchemy URL'sidir, örn. mysql+pymysql://kullanici:parola@host:9030/veritabani
    (bu değer hiçbir yere yazdırılmaz).

Çalıştırma:
  cd /opt/superbi-wt/doris && /opt/superbi/venv/bin/python tests/doris/test_doris_driver.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy.engine import make_url  # noqa: E402

from app.core.connector_registry import DRIVER_MAP, ConnectorRegistry  # noqa: E402

HOST = "doris-fe-ortak"
ZOR_DB = "veri?tabani/x@y"
ZOR_USER = "kul@ad:1"
ZOR_PASS = "p/ss?w@rd:#%"

os.environ["DATALENS_ALLOWED_DB_HOSTS"] = HOST


class Skip(Exception):
    """Ön koşul yok (ör. canlı Doris tanımlı değil)."""


def _params(**kw) -> dict:
    p = {"host": HOST, "port": None, "database": "sales", "user": "root", "password": "x"}
    p.update(kw)
    return p


def test_a_url_varsayilan_port_9030():
    u = make_url(ConnectorRegistry()._build_url("doris", _params()))
    assert u.drivername == "mysql+pymysql", u.drivername
    assert u.port == 9030, f"port varsayılanı 9030 olmalı, gelen: {u.port}"
    assert u.host == HOST
    assert u.database == "sales"


def test_a_acik_port_korunur():
    u = make_url(ConnectorRegistry()._build_url("doris", _params(port=9031)))
    assert u.port == 9031, f"açık port korunmalı, gelen: {u.port}"


def test_b_ozel_karakterler_korunur():
    u = make_url(ConnectorRegistry()._build_url(
        "doris", _params(database=ZOR_DB, user=ZOR_USER, password=ZOR_PASS)))
    assert u.database == ZOR_DB, f"database bozuldu: {u.database!r}"
    assert u.username == ZOR_USER, f"user bozuldu: {u.username!r}"
    assert u.password == ZOR_PASS, "password bozuldu"
    assert u.host == HOST


def test_b_database_sorgu_parametresi_enjeksiyonu_olmaz():
    u = make_url(ConnectorRegistry()._build_url("doris", _params(database="db?charset=latin1")))
    assert u.database == "db?charset=latin1"
    assert "charset" not in u.query, "database değeri URL sorgusu olarak yorumlandı"


def test_c_driver_map_pymysql():
    meta = DRIVER_MAP["doris"]
    assert meta["module"] == "pymysql", meta
    assert meta["package"] == "PyMySQL", meta
    assert meta["dialect"] == "mysql+pymysql", meta
    installed = ConnectorRegistry().driver_installed("doris")
    assert installed == (importlib.util.find_spec("pymysql") is not None)


def test_d_limit_uretimi_doris():
    from app.services.sql_builder import SQLBuilder
    sql, _ = SQLBuilder().build(
        base_table="t", fields={"a": "a"}, joins=[], filters=[], group_by=[],
        order_by=[], limit=10, offset=5, db_type="doris")
    assert "LIMIT 10 OFFSET 5" in sql, sql
    assert "TOP" not in sql and "FETCH" not in sql, sql


def test_d_formul_doris_lehcesi_kabul_edilir():
    from app.services.expression_builder import validate_and_compile
    out = validate_and_compile("a > 0", "doris", {"a"})
    assert "a" in out and "0" in out, out


def test_e_canli_doris_entegrasyonu():
    url = os.environ.get("DATALENS_IT_DORIS_URL")
    if not url:
        raise Skip("DATALENS_IT_DORIS_URL tanımlı değil")
    from sqlalchemy import create_engine, inspect, text
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1
        names = inspect(engine).get_schema_names()
        assert isinstance(names, list) and names, "şema listesi boş"
    finally:
        engine.dispose()


TESTS = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]


if __name__ == "__main__":
    ok, fail, skip = 0, 0, 0
    for t in TESTS:
        try:
            t()
            print("PASS", t.__name__)
            ok += 1
        except Skip as e:
            print("SKIP", t.__name__, "-", e)
            skip += 1
        except Exception:
            print("FAIL", t.__name__)
            traceback.print_exc()
            fail += 1
    print(f"\n{ok} geçti, {fail} başarısız, {skip} atlandı")
    sys.exit(1 if fail else 0)
