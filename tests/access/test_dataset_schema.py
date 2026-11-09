"""
Kayıtlı veri setinde şema adı (schema_name) ve hesaplanmış alanlar (calculated_fields).

Kapsam:
  (a) create -> repo / get / list round-trip
  (b) run_dataset schema ve calculated_fields'ı sql_builder'a geçirir
  (c) eski veritabanında migration mevcut veriyi bozmaz
  (d) update (PUT) yeni alanları kaydeder; yazma paylaşımı yapıyı değiştiremez

Çalıştırma:
  cd <worktree> && venv/bin/python tests/access/test_dataset_schema.py
"""
from __future__ import annotations

import os
import sys
import traceback
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import HTTPException  # noqa: E402

from app.db.sqlite_store import SQLiteStore  # noqa: E402
from app.core.repository import (  # noqa: E402
    Dataset, DatasetRepository, ConnectionRepository, ConnectionMeta,
)
from app.core.sharing import ShareRepository  # noqa: E402
from app.api import datasets as ds_api  # noqa: E402
from app.core.rls import RuleRepository, AttributeRepository  # noqa: E402


CALC = [{"name": "toplam", "formula": "amount * 2"}]


class _Exec:
    """QueryExecutor taklidi: çağrı argümanlarını saklar."""
    def __init__(self):
        self.calls = []

    def execute(self, **kw):
        self.calls.append(kw)
        return {"columns": ["id"], "rows": [[1]], "row_count": 1}


def _u(uid, role="viewer"):
    return SimpleNamespace(user_id=uid, role=role)


def _patch_engine(calls):
    """resolve_connection_engine yerine sahte motor; hangi kimlikle açıldığını kaydeder."""
    def fake(conn_id, current, registry, repo):
        calls.append({"conn_id": conn_id, "as_user": current.user_id})
        return object(), SimpleNamespace(conn_id=conn_id, db_type="postgresql")
    ds_api.resolve_connection_engine = fake


def _store_with_ds(schema_name=None, calc=None, fields=None):
    store = SQLiteStore(":memory:")
    ConnectionRepository(store).save(ConnectionMeta(
        conn_id="c1", db_type="postgresql", host="h", database="db", owner_id="owner"))
    DatasetRepository(store).save(Dataset(
        dataset_id="d1", name="Satış", conn_id="c1", base_table="sales", owner_id="owner",
        fields=fields if fields is not None else {"id": "dim", "amount": "dim"},
        schema_name=schema_name, calculated_fields=list(calc or [])))
    return store


def _run(store, current, ex=None, calls=None):
    _patch_engine(calls if calls is not None else [])
    dr = DatasetRepository(store)
    return ds_api.run_dataset(
        "d1", ds_api.DatasetRunIn(sample=10), current=current, repo=dr,
        shares=ShareRepository(store), registry=None, conn_repo=None,
        executor=ex or _Exec(), rls_repo=RuleRepository(store),
        attr_repo=AttributeRepository(store))


def _status(fn):
    try:
        fn()
    except HTTPException as e:
        return e.status_code
    return 200


# ---------------------------------------------------------------------------
# (a) round-trip
# ---------------------------------------------------------------------------

def test_create_round_trip():
    store = SQLiteStore(":memory:")
    ConnectionRepository(store).save(ConnectionMeta(
        conn_id="c1", db_type="postgresql", host="h", database="db", owner_id="owner"))
    dr, sr = DatasetRepository(store), ShareRepository(store)
    body = ds_api.DatasetIn(name="Satış", conn_id="c1", base_table="sales",
                            fields={"id": "dim", "amount": "dim"},
                            schema_name="hr", calculated_fields=CALC)
    res = ds_api.create_dataset(body, current=_u("owner"), repo=dr,
                                conn_repo=ConnectionRepository(store))
    ds = dr.get(res["dataset_id"])
    assert ds.schema_name == "hr", ds.schema_name
    assert ds.calculated_fields == CALC, ds.calculated_fields

    detay = ds_api.get_dataset(res["dataset_id"], current=_u("owner"), repo=dr, shares=sr)
    assert detay["schema_name"] == "hr" and detay["calculated_fields"] == CALC, detay

    liste = ds_api.list_datasets(current=_u("owner"), repo=dr, shares=sr)
    satir = [x for x in liste if x["dataset_id"] == res["dataset_id"]][0]
    assert satir["schema_name"] == "hr" and satir["calculated_fields"] == CALC, satir


def test_create_without_new_fields_defaults():
    store = SQLiteStore(":memory:")
    ConnectionRepository(store).save(ConnectionMeta(
        conn_id="c1", db_type="postgresql", host="h", database="db", owner_id="owner"))
    dr = DatasetRepository(store)
    body = ds_api.DatasetIn(name="Eski", conn_id="c1", base_table="sales")
    res = ds_api.create_dataset(body, current=_u("owner"), repo=dr,
                                conn_repo=ConnectionRepository(store))
    ds = dr.get(res["dataset_id"])
    assert ds.schema_name is None and ds.calculated_fields == [], (ds.schema_name, ds.calculated_fields)


# ---------------------------------------------------------------------------
# (b) run
# ---------------------------------------------------------------------------

def test_run_uses_schema_name():
    store = _store_with_ds(schema_name="hr", calc=CALC)
    ex, calls = _Exec(), []
    _run(store, _u("owner"), ex, calls)
    sql = ex.calls[-1]["sql"]
    assert '"hr"."sales"' in sql, sql


def test_run_uses_calculated_field():
    store = _store_with_ds(schema_name="hr", calc=CALC)
    ex, calls = _Exec(), []
    _run(store, _u("owner"), ex, calls)
    sql = ex.calls[-1]["sql"]
    assert 'AS "toplam"' in sql, sql


def test_run_without_schema_keeps_plain_table():
    store = _store_with_ds(schema_name=None)
    ex, calls = _Exec(), []
    _run(store, _u("owner"), ex, calls)
    sql = ex.calls[-1]["sql"]
    assert '"sales"' in sql and '"hr"' not in sql, sql


def test_run_invalid_formula_returns_400():
    store = _store_with_ds(calc=[{"name": "x", "formula": "amount; DROP TABLE sales"}])
    assert _status(lambda: _run(store, _u("owner"))) == 400


# ---------------------------------------------------------------------------
# (c) migration
# ---------------------------------------------------------------------------

_ESKI_DDL = """
CREATE TABLE datasets (
    dataset_id   TEXT PRIMARY KEY,
    owner_id     TEXT NOT NULL DEFAULT 'anonymous',
    name         TEXT NOT NULL,
    conn_id      TEXT NOT NULL,
    base_table   TEXT NOT NULL,
    fields_json  TEXT NOT NULL DEFAULT '{}',
    joins_json   TEXT NOT NULL DEFAULT '[]',
    filters_json TEXT NOT NULL DEFAULT '[]',
    group_by_json TEXT NOT NULL DEFAULT '[]',
    order_by_json TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


def test_migration_keeps_old_rows():
    store = SQLiteStore(":memory:")
    store._conn.execute("DROP TABLE datasets")
    store._conn.execute(_ESKI_DDL)
    store._conn.execute(
        "INSERT INTO datasets (dataset_id, owner_id, name, conn_id, base_table, fields_json) "
        "VALUES ('old1', 'owner', 'Eski', 'c1', 'sales', '{\"id\": \"dim\"}')")
    store._conn.commit()

    store._apply_schema()
    store._apply_schema()  # ikinci çalıştırma idempotent olmalı

    ds = DatasetRepository(store).get("old1")
    assert ds is not None
    assert ds.name == "Eski" and ds.conn_id == "c1" and ds.base_table == "sales", ds
    assert ds.fields == {"id": "dim"}, ds.fields
    assert ds.schema_name is None and ds.calculated_fields == [], (ds.schema_name, ds.calculated_fields)


# ---------------------------------------------------------------------------
# (d) update
# ---------------------------------------------------------------------------

def test_update_persists_new_fields():
    store = _store_with_ds(schema_name=None, calc=[])
    dr, sr = DatasetRepository(store), ShareRepository(store)
    body = ds_api.DatasetIn(name="Satış v2", conn_id="c1", base_table="sales",
                            fields={"id": "dim", "amount": "dim"},
                            schema_name="hr", calculated_fields=CALC)
    ds_api.update_dataset("d1", body, current=_u("owner"), repo=dr, conn_repo=None, shares=sr)
    ds = dr.get("d1")
    assert ds.schema_name == "hr" and ds.calculated_fields == CALC, (ds.schema_name, ds.calculated_fields)


def test_write_share_cannot_change_structure():
    store = _store_with_ds(schema_name="hr", calc=CALC)
    dr, sr = DatasetRepository(store), ShareRepository(store)
    sr.create("dataset", "d1", "user", "other", "write", created_by="owner")
    body = ds_api.DatasetIn(name="Satış", conn_id="c1", base_table="sales",
                            fields={"id": "dim", "amount": "dim"},
                            schema_name="dbo", calculated_fields=CALC)
    assert _status(lambda: ds_api.update_dataset(
        "d1", body, current=_u("other"), repo=dr, conn_repo=None, shares=sr)) == 403
    ds = dr.get("d1")
    assert ds.schema_name == "hr", ds.schema_name


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
