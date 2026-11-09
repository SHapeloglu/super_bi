"""
Regresyon testi — identifier tırnaklama dialect'e göre (MySQL / Doris backtick).

Sorun: quote_identifier her dialect'te çift tırnak üretiyordu. MySQL ailesinde çift tırnak
string literal'dir, dolayısıyla "FROM \"orders\"" geçersiz sorgu olur.

Çalıştırma:
  cd <worktree> && venv/bin/python tests/unit/test_quoting.py
"""
from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import sqlglot  # noqa: E402

from app.core.connector_registry import quote_identifier  # noqa: E402
from app.services.sql_builder import sql_builder  # noqa: E402
from app.services import granularity_analyzer as ga  # noqa: E402


def _sql(db_type: str) -> str:
    sql, _ = sql_builder.build(
        base_table="orders", fields={"id": "id", "tutar": "tutar"},
        joins=[], filters=[], group_by=[], order_by=[], limit=10, db_type=db_type,
    )
    return sql


def test_mysql_backtick():
    assert quote_identifier("orders", "mysql") == "`orders`"
    assert quote_identifier("a.b", "mysql") == "`a`.`b`"


def test_doris_backtick():
    assert quote_identifier("orders", "doris") == "`orders`"


def test_postgres_cift_tirnak_korunur():
    assert quote_identifier("orders", "postgresql") == '"orders"'
    assert quote_identifier("orders") == '"orders"'  # varsayılan davranış aynı


def test_mysql_uretilen_sql_cift_tirnak_icermez():
    sql = _sql("mysql")
    assert "`orders`" in sql and "`tutar`" in sql, sql
    assert '"' not in sql, f"MySQL SQL'inde çift tırnak var:\n{sql}"


def test_mysql_sql_sqlglot_ile_ayristirilir():
    """MySQL'de yeniden yazım (transpile) identifier'ları backtick ile vermeli; çift tırnak string olarak kalırsa başarısız."""
    cikti = sqlglot.transpile(_sql("mysql"), read="mysql", write="mysql")[0]
    assert "`orders`" in cikti, f"MySQL çıktısında tablo identifier değil:\n{cikti}"
    assert "'orders'" not in cikti, f"tablo adı string literal olarak yazıldı:\n{cikti}"


def test_mysql_join_where_order_group_backtick():
    from app.models.schemas import JoinDef, FilterDef
    sql, params = sql_builder.build(
        base_table="orders", fields={"id": "id"},
        joins=[JoinDef(t1="orders", f1="mid", t2="musteri", f2="id", type="LEFT JOIN")],
        filters=[FilterDef(table="orders", column="tutar", operator=">", value=5)],
        group_by=["id"], order_by=["-id"], limit=10, db_type="mysql",
    )
    assert '"' not in sql, sql
    assert "`musteri`" in sql and "`mid`" in sql and "`tutar`" in sql, sql
    assert "GROUP BY `id`" in sql and "ORDER BY `id` DESC" in sql, sql


def test_enjeksiyon_mysql_de_reddedilir():
    try:
        quote_identifier("x`; DROP TABLE y; --", "mysql")
    except ValueError:
        return
    raise AssertionError("MySQL'de zararlı identifier kabul edildi")


def test_granularity_q_dialect():
    assert ga._q("t", "mysql") == "`t`"
    assert ga._q("t", "postgresql") == '"t"'


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
