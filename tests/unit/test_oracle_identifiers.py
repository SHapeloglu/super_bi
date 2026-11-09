"""
Regresyon testi — Oracle identifier tutarlılığı (tek merkezden büyük harf).

quote_identifier(dialect="oracle") her parçayı büyük harfe çevirip tırnaklar.
Böylece tablo, join, filtre, group/order ve formül kolonları aynı biçimde çıkar;
Oracle'da tırnaklı identifier büyük/küçük harfe duyarlı olduğu için karışmaz.

Bilinen sınır: Oracle'da bilinçli olarak küçük/karma harfli tırnaklı tablo/kolon
adı kullanılan kurulumlar desteklenmez.

Çalıştırma:
  cd <worktree> && venv/bin/python tests/unit/test_oracle_identifiers.py
"""
from __future__ import annotations

import os
import re
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.core.connector_registry import quote_identifier  # noqa: E402
from app.services.sql_builder import sql_builder  # noqa: E402
from app.models.schemas import JoinDef, FilterDef, CalculatedFieldDef  # noqa: E402

LOWER_QUOTED = re.compile(r'"[a-z]')


def _build(db_type: str = "oracle", **kw):
    args = dict(
        base_table="orders", fields={"id": "id", "tutar": "tutar"},
        joins=[], filters=[], group_by=[], order_by=[], limit=10,
        db_type=db_type,
    )
    args.update(kw)
    return sql_builder.build(**args)


def _full_oracle_sql() -> str:
    sql, _ = _build(
        fields={"id": "id", "tutar": "tutar", "musteri.ad": "role"},
        joins=[JoinDef(t1="orders", f1="mid", t2="musteri", f2="id", type="LEFT JOIN")],
        filters=[FilterDef(table="orders", column="tutar", operator=">", value=5)],
        group_by=["id"], order_by=["-id"],
    )
    return sql


# --- quote_identifier -------------------------------------------------------

def test_quote_oracle_tek_parca_buyuk_harf():
    assert quote_identifier("orders", "oracle") == '"ORDERS"'


def test_quote_oracle_noktali_buyuk_harf():
    assert quote_identifier("a.b", "oracle") == '"A"."B"'


def test_quote_oracle_enjeksiyon_reddedilir():
    try:
        quote_identifier('x"; DROP TABLE y; --', "oracle")
    except ValueError:
        return
    raise AssertionError("Oracle'da zararlı identifier kabul edildi")


# --- sql_builder.build (oracle) --------------------------------------------

def test_build_oracle_base_table_ve_kolon_buyuk():
    sql, _ = _build()
    assert 'FROM "ORDERS"' in sql, sql
    assert '"ORDERS"."ID"' in sql and '"ORDERS"."TUTAR"' in sql, sql


def test_build_oracle_hic_kucuk_harfli_tirnak_kalmaz():
    sql = _full_oracle_sql()
    assert not LOWER_QUOTED.search(sql), f"küçük harfli tırnaklı identifier var:\n{sql}"
    assert '"MUSTERI"."ID"' in sql and '"ORDERS"."MID"' in sql, sql
    assert 'GROUP BY "ORDERS"."ID"' in sql and 'ORDER BY "ORDERS"."ID" DESC' in sql, sql


def test_build_oracle_schema_ile():
    sql, _ = _build(schema="hr")
    assert 'FROM "HR"."ORDERS"' in sql, sql
    assert not LOWER_QUOTED.search(sql), sql


def test_build_oracle_formul_kucuk_kolon_derlenir():
    """Küçük harfli kolon adı içeren hesaplanmış alan Oracle'da whitelist'ten geçmeli."""
    sql, _ = _build(calculated_fields=[CalculatedFieldDef(name="net", formula="tutar * 2")])
    assert 'AS "NET"' in sql, sql
    assert not LOWER_QUOTED.search(sql), sql


def test_build_oracle_formul_sbx_kucuk_kolon():
    sql, _ = _build(calculated_fields=[CalculatedFieldDef(name="net", formula="[tutar] * 2")])
    assert 'AS "NET"' in sql, sql
    assert not LOWER_QUOTED.search(sql), sql


def test_build_oracle_formula_only_kolon():
    sql, _ = _build(
        fields={"id": "id"},
        calculated_fields=[CalculatedFieldDef(name="cift", formula="fiyat * 2")],
        formula_only_columns=["fiyat"],
    )
    assert 'AS "CIFT"' in sql, sql
    assert not LOWER_QUOTED.search(sql), sql


def test_diger_dialectler_degismez():
    assert '"orders"."id"' in _build("postgresql")[0]
    assert '"orders"."id"' in _build("mssql")[0]
    assert "SELECT TOP 10" in _build("mssql")[0]
    assert '`orders`.`id`' in _build("mysql")[0]


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
