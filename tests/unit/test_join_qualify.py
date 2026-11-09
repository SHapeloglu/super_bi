"""
Regresyon testi — join içeren sorgularda GROUP BY / ORDER BY kolonları base_table ile nitelenir.

Sorun: "id" gibi iki tabloda ortak kolon adı, nitelenmeden yazıldığında veritabanı
"ambiguous column" hatası verir (Oracle ve diğerleri).
Kural: join varsa ve ad nokta içermiyorsa VE calculated field alias'ı değilse, "tablo"."kolon" yazılır.

Çalıştırma:
  cd <worktree> && /opt/superbi/venv/bin/python tests/unit/test_join_qualify.py
"""
from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.models.schemas import JoinDef, CalculatedFieldDef  # noqa: E402
from app.services.sql_builder import sql_builder  # noqa: E402

JOIN = [JoinDef(t1="orders", f1="mid", t2="musteri", f2="id", type="LEFT JOIN")]


def _build(db_type="sqlite", joins=None, group_by=None, order_by=None, fields=None, calc=None):
    sql, _ = sql_builder.build(
        base_table="orders",
        fields=fields if fields is not None else {"id": "dim"},
        joins=JOIN if joins is None else joins,
        filters=[],
        group_by=group_by if group_by is not None else ["id"],
        order_by=order_by if order_by is not None else ["-id"],
        limit=10,
        db_type=db_type,
        calculated_fields=calc,
    )
    return sql


def _tail(sql: str) -> str:
    return sql[sql.index("GROUP BY"):]


def test_join_group_order_qualified_sqlite():
    tail = _tail(_build())
    assert 'GROUP BY "orders"."id"' in tail, tail
    assert 'ORDER BY "orders"."id" DESC' in tail, tail


def test_join_group_order_qualified_oracle_uppercase():
    tail = _tail(_build(db_type="oracle"))
    assert 'GROUP BY "ORDERS"."ID"' in tail, tail
    assert 'ORDER BY "ORDERS"."ID" DESC' in tail, tail


def test_join_group_order_qualified_mysql_backtick():
    tail = _tail(_build(db_type="mysql"))
    assert "GROUP BY `orders`.`id`" in tail, tail
    assert "ORDER BY `orders`.`id` DESC" in tail, tail


def test_no_join_unchanged():
    sql = _build(joins=[])
    assert 'GROUP BY "id"' in sql and 'ORDER BY "id" DESC' in sql, sql


def test_dotted_name_untouched():
    sql = _build(group_by=["musteri.ad"], order_by=["-musteri.ad"])
    assert 'GROUP BY "musteri"."ad"' in sql and 'ORDER BY "musteri"."ad" DESC' in sql, sql


def test_calculated_alias_not_qualified():
    calc = [CalculatedFieldDef(name="toplam", formula="ROUND(id * 1.18, 2)")]
    sql = _build(group_by=["toplam"], order_by=["-toplam"], calc=calc)
    assert 'ORDER BY "toplam" DESC' in sql, sql
    assert 'GROUP BY "toplam"' in sql, sql
    assert '"orders"."toplam"' not in sql, sql


def main() -> int:
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
