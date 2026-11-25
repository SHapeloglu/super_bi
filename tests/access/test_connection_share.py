"""
Viewer bağlantı paylaşımı (docs/VIEWER_BAGLANTI_PAYLASIMI.md, seçenek B sınırlı hali).

Kurallar:
  - Yalnız bağlantının sahibi ya da admin paylaşır. Paylaşım alıcısı bir kullanıcıdır (rol olamaz)
    ve izni 'use'tur (yazma yok). 'use' yalnız bağlantı paylaşımında geçerlidir.
  - Bağlantı paylaşımı en az bir tablo içermelidir; alıcı yalnız o tablolardan veri seti kurabilir.
  - Alıcı bağlantı listesinde yalnız kimlik/tür/ad görür (host, kullanıcı, veritabanı, parola yok).
  - Alıcı şema/tablo listesi, serbest SQL ya da bağlantı testi için bağlantıyı kullanamaz (404).
  - Veri seti çalıştırma bağlantıyı VERİ SETİNİN SAHİBİ adına açar; izin kaldırılınca ya da tablo
    beyaz listeden çıkınca çalıştırma reddedilir.

Çalıştırma:
  cd <worktree> && venv/bin/python tests/access/test_connection_share.py
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
from pydantic import ValidationError  # noqa: E402

from app.db.sqlite_store import SQLiteStore  # noqa: E402
from app.core.repository import ConnectionMeta, ConnectionRepository, Dataset, DatasetRepository  # noqa: E402
from app.core.sharing import ShareRepository  # noqa: E402
from app.core.conn_share import ConnectionShareRepository  # noqa: E402
from app.core.rls import RuleRepository, AttributeRepository  # noqa: E402
from app.api import datasets as ds_api  # noqa: E402
from app.api import shares as shares_api  # noqa: E402
from app.api import connections as conn_api  # noqa: E402
from app.deps import resolve_connection_engine  # noqa: E402


class _Users:
    """UserRepository taklidi: yalnız tanıdığı kullanıcılar."""
    KNOWN = {"v1", "v2", "admin1"}

    def get_by_id(self, uid):
        return SimpleNamespace(user_id=uid) if uid in self.KNOWN else None


class _Reg:
    """ConnectorRegistry taklidi: bellekte hazır engine'ler."""
    def __init__(self):
        self._engines = {"c1": object(), "c2": object()}

    def get_engine(self, *a, **k):
        raise RuntimeError("bu testte yeniden bağlanma olmamalı")


class _Exec:
    def __init__(self):
        self.calls = []

    def execute(self, **kw):
        self.calls.append(kw)
        return {"columns": ["id"], "rows": [[1]], "row_count": 1}


def _setup():
    store = SQLiteStore(":memory:")
    conns = ConnectionRepository(store)
    for cid in ("c1", "c2"):
        conns.save(ConnectionMeta(conn_id=cid, db_type="postgresql", host=f"{cid}.internal",
                                  database=f"db_{cid}", owner_id="admin1", port=5432,
                                  user=f"u_{cid}", password_enc="ENC"))
    return SimpleNamespace(
        store=store,
        conns=conns,
        grants=ConnectionShareRepository(store),
        shares=ShareRepository(store),
        ds=DatasetRepository(store),
        rls=RuleRepository(store),
        attr=AttributeRepository(store),
        reg=_Reg(),
    )


def _admin():
    return SimpleNamespace(user_id="admin1", role="admin", username="admin1")


def _viewer(uid):
    return SimpleNamespace(user_id=uid, role="viewer", username=uid)


def _share_body(**kw):
    base = {"resource_type": "connection", "resource_id": "c1", "grantee_type": "user",
            "grantee_id": "v1", "permission": "use",
            "tables": [{"schema_name": None, "table_name": "sales"},
                       {"schema_name": None, "table_name": "customers"}]}
    base.update(kw)
    return shares_api.ShareIn(**base)


def _grant(env, uid="v1", tables=("sales", "customers"), conn="c1"):
    body = _share_body(resource_id=conn, grantee_id=uid,
                       tables=[{"schema_name": None, "table_name": t} for t in tables])
    return shares_api.create_share(body, current=_admin(), share_repo=env.shares,
                                   ds_repo=env.ds, dash_repo=None, user_repo=_Users(),
                                   conn_repo=env.conns, conn_grants=env.grants)


def _status(fn):
    try:
        fn()
    except HTTPException as e:
        return e.status_code
    return 200


def _dataset_body(**kw):
    base = dict(name="Satış", conn_id="c1", base_table="sales", fields={"id": "id"})
    base.update(kw)
    return ds_api.DatasetIn(**base)


def _create(env, uid, **kw):
    return ds_api.create_dataset(_dataset_body(**kw), current=_viewer(uid), repo=env.ds,
                                 conn_repo=env.conns, conn_grants=env.grants)


def _run(env, uid, ds_id, ex):
    return ds_api.run_dataset(ds_id, ds_api.DatasetRunIn(sample=10), current=_viewer(uid),
                              repo=env.ds, shares=env.shares, registry=env.reg,
                              conn_repo=env.conns, executor=ex, rls_repo=env.rls,
                              attr_repo=env.attr, conn_grants=env.grants)


# ---------------------------------------------------------------- paylaşım kuralları

def test_sahip_bağlantıyı_use_ve_tablo_listesiyle_paylasir():
    env = _setup()
    _grant(env)
    assert env.grants.has_use("c1", "v1")
    assert env.grants.allowed_tables("c1", "v1") == {("", "sales"), ("", "customers")}


def test_yazma_izni_bağlantı_paylaşımında_reddedilir():
    try:
        _share_body(permission="write")
    except ValidationError:
        return
    raise AssertionError("connection + write kabul edildi")


def test_rol_alıcısı_bağlantı_paylaşımında_reddedilir():
    try:
        _share_body(grantee_type="role", grantee_id="viewer")
    except ValidationError:
        return
    raise AssertionError("connection + role kabul edildi")


def test_tablosuz_bağlantı_paylaşımı_reddedilir():
    try:
        _share_body(tables=[])
    except ValidationError:
        return
    raise AssertionError("tablosuz bağlantı paylaşımı kabul edildi")


def test_use_izni_veri_seti_paylaşımında_reddedilir():
    try:
        shares_api.ShareIn(resource_type="dataset", resource_id="d1", grantee_type="user",
                           grantee_id="v1", permission="use")
    except ValidationError:
        return
    raise AssertionError("dataset + use kabul edildi")


def test_sahip_olmayan_bağlantıyı_paylaşamaz():
    env = _setup()
    body = _share_body(grantee_id="v2")
    assert _status(lambda: shares_api.create_share(
        body, current=_viewer("v1"), share_repo=env.shares, ds_repo=env.ds, dash_repo=None,
        user_repo=_Users(), conn_repo=env.conns, conn_grants=env.grants)) == 404
    assert not env.grants.has_use("c1", "v2")


# ---------------------------------------------------------------- görünürlük

def test_alıcı_bağlantı_listesinde_paylaşılan_bağlantı_yok():
    # Paylaşılanlar yalnız GET /api/connections/shared ile gelir; ana liste yalnız kendi bağlantılarıdır.
    env = _setup()
    _grant(env)
    rows = conn_api.list_connections(current=_viewer("v1"), repo=env.conns, conn_grants=env.grants)
    assert rows == [], rows


def test_paylaşılmamış_bağlantı_listede_yok():
    env = _setup()
    _grant(env)
    rows = conn_api.list_connections(current=_viewer("v2"), repo=env.conns, conn_grants=env.grants)
    assert rows == []


def test_alıcı_paylaşılan_bağlantıyla_şema_ve_sorgu_yapamaz():
    env = _setup()
    _grant(env)
    # Şema listesi, bağlantı testi ve sorgu yolları aynı çözümleyiciyi kullanır: alıcı için 404.
    assert _status(lambda: resolve_connection_engine("c1", _viewer("v1"), env.reg, env.conns)) == 404


def test_alıcı_kendisine_paylaşılan_bağlantı_ve_izinli_tablolarını_görür():
    env = _setup()
    _grant(env)
    rows = conn_api.list_shared_connections(current=_viewer("v1"), repo=env.conns, conn_grants=env.grants)
    assert len(rows) == 1 and rows[0]["conn_id"] == "c1", rows
    assert rows[0]["tables"] == [{"schema_name": None, "table_name": "customers"},
                                 {"schema_name": None, "table_name": "sales"}], rows[0]["tables"]
    for yasak in ("host", "user", "database", "password", "password_enc", "owner_id"):
        assert yasak not in rows[0], f"{yasak} alıcıya sızdı"


def test_paylaşılmamış_alıcı_paylaşılan_liste_boş_görür():
    env = _setup()
    _grant(env)
    assert conn_api.list_shared_connections(current=_viewer("v2"), repo=env.conns, conn_grants=env.grants) == []


def _sqlite_env():
    """Gerçek bir SQLite engine: 'sales' izinli, 'payroll' izinsiz."""
    from sqlalchemy import create_engine, text
    eng = create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE sales (id INTEGER, amount REAL)"))
        c.execute(text("CREATE TABLE payroll (id INTEGER, salary REAL)"))
    env = _setup()
    env.reg._engines["c1"] = eng
    return env


def test_alıcı_izinli_tablonun_kolonlarını_görür():
    env = _sqlite_env()
    _grant(env, tables=("sales",))
    out = conn_api.list_shared_columns("c1", "sales", current=_viewer("v1"), repo=env.conns,
                                       registry=env.reg, conn_grants=env.grants)
    assert out["table"] == "sales"
    assert [c["name"] for c in out["columns"]] == ["id", "amount"], out


def test_alıcı_izinsiz_tablonun_kolonlarını_göremez():
    env = _sqlite_env()
    _grant(env, tables=("sales",))
    assert _status(lambda: conn_api.list_shared_columns("c1", "payroll", current=_viewer("v1"), repo=env.conns,
                                                        registry=env.reg, conn_grants=env.grants)) == 404


def test_paylaşılmamış_bağlantının_kolonları_alıcıya_kapalı():
    env = _sqlite_env()
    _grant(env, tables=("sales",))
    assert _status(lambda: conn_api.list_shared_columns("c2", "sales", current=_viewer("v1"), repo=env.conns,
                                                        registry=env.reg, conn_grants=env.grants)) == 404


def test_sahibi_bağlantıyı_hâlâ_kullanır():
    env = _setup()
    engine, meta = resolve_connection_engine("c1", _viewer("admin1"), env.reg, env.conns)
    assert meta.conn_id == "c1"


# ---------------------------------------------------------------- veri seti kurma

def test_alıcı_izinli_tablolarla_veri_seti_kurar():
    env = _setup()
    _grant(env)
    out = _create(env, "v1", base_table="sales")
    assert env.ds.get(out["dataset_id"]).owner_id == "v1"


def test_alıcı_izinsiz_tabloyla_veri_seti_kuramaz():
    env = _setup()
    _grant(env)
    assert _status(lambda: _create(env, "v1", base_table="payroll")) == 403


def test_alıcı_izinsiz_join_tablosuyla_veri_seti_kuramaz():
    env = _setup()
    _grant(env)
    join = [{"type": "LEFT JOIN", "t1": "sales", "f1": "id", "t2": "payroll", "f2": "id"}]
    assert _status(lambda: _create(env, "v1", base_table="sales", joins=join)) == 403


def test_paylaşılmamış_bağlantıyla_veri_seti_kurulamaz():
    env = _setup()
    _grant(env)
    assert _status(lambda: _create(env, "v1", conn_id="c2", base_table="sales")) == 404


# ---------------------------------------------------------------- çalıştırma ve geri alma

def test_veri_seti_sahibin_bağlantısıyla_çalışır():
    env = _setup()
    _grant(env)
    ds_id = _create(env, "v1", base_table="sales")["dataset_id"]
    ex = _Exec()
    _run(env, "v1", ds_id, ex)
    assert len(ex.calls) == 1 and ex.calls[0]["conn_id"] == "c1"


def test_izin_kaldırılınca_çalıştırma_reddedilir():
    env = _setup()
    share_id = _grant(env)["share_id"]
    ds_id = _create(env, "v1", base_table="sales")["dataset_id"]
    assert env.shares is not None
    env.grants.revoke(share_id)
    ex = _Exec()
    assert _status(lambda: _run(env, "v1", ds_id, ex)) == 404
    assert ex.calls == []


def test_tablo_listeden_çıkarılınca_çalıştırma_reddedilir():
    env = _setup()
    _grant(env)
    ds_id = _create(env, "v1", base_table="sales")["dataset_id"]
    _grant(env, tables=("customers",))  # aynı alıcıya yeniden paylaşım: yalnız customers kalır
    ex = _Exec()
    assert _status(lambda: _run(env, "v1", ds_id, ex)) == 403
    assert ex.calls == []


def test_admin_kendi_bağlantısıyla_veri_seti_çalıştırır():
    env = _setup()
    ds_id = _create(env, "admin1", conn_id="c1", base_table="sales")["dataset_id"]
    ex = _Exec()
    _run(env, "admin1", ds_id, ex)
    assert ex.calls and ex.calls[0]["conn_id"] == "c1"


def test_bağlantı_silinince_paylaşımlar_temizlenir():
    env = _setup()
    _grant(env)
    env.conns.delete("c1")
    env.grants.delete_for_connection("c1")
    assert env.grants.has_use("c1", "v1") is False
    assert env.grants.allowed_tables("c1", "v1") is None


TESTS = [v for k, v in dict(globals()).items() if k.startswith("test_")]


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
