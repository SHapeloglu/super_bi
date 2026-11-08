"""
Faz 1.3 — Satır bazlı güvenlik (RLS) testleri.

Kurallar:
  - Kural bir veri setine bağlanır: kolon, operatör ve değer (sabit) ya da kullanıcı özniteliği.
  - Kurallar sorgu oluşturucuya ek FILTRE olarak eklenir (bind parametre; yeni SQL metni üretilmez).
  - Yönetici (admin) kuralları atlar; diğer herkes (sahip dahil) kuralların altındadır.
  - Gerekli kullanıcı özniteliği yoksa erişim reddedilir (fail-closed, 403).
  - Kuralları yalnız admin yönetir.

Çalıştırma:
  cd <worktree> && venv/bin/python tests/access/test_rls.py
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
from app.core.repository import Dataset, DatasetRepository  # noqa: E402
from app.core.sharing import ShareRepository  # noqa: E402
from app.core.rls import RuleRepository, AttributeRepository, build_rls_filters, RLSError  # noqa: E402
from app.api import datasets as ds_api  # noqa: E402
from app.api import users as users_api  # noqa: E402


class _Exec:
    def __init__(self):
        self.calls = []

    def execute(self, **kw):
        self.calls.append(kw)
        return {"columns": ["id"], "rows": [], "row_count": 0}


def _env():
    store = SQLiteStore(":memory:")
    dr = DatasetRepository(store)
    sr = ShareRepository(store)
    rr = RuleRepository(store)
    ar = AttributeRepository(store)
    dr.save(Dataset(dataset_id="d1", name="Satış", conn_id="c1", base_table="sales",
                    owner_id="owner", fields={"id": "dim", "amount": "dim"}))
    sr.create("dataset", "d1", "user", "u1", "read", created_by="owner")
    sr.create("dataset", "d1", "user", "u2", "read", created_by="owner")
    return store, dr, sr, rr, ar


def _u(uid, role="viewer"):
    return SimpleNamespace(user_id=uid, role=role, username=uid)


def _patch_engine():
    def fake(conn_id, current, registry, repo):
        return object(), SimpleNamespace(conn_id=conn_id, db_type="postgresql")
    ds_api.resolve_connection_engine = fake


def _run(current, dr, sr, rr, ar, ex):
    _patch_engine()
    body = ds_api.DatasetRunIn(sample=10)
    return ds_api.run_dataset("d1", body, current=current, repo=dr, shares=sr, registry=None,
                              conn_repo=None, executor=ex, rls_repo=rr, attr_repo=ar)


def _status(fn):
    try:
        fn()
    except HTTPException as e:
        return e.status_code
    return 200


# ── Kural motoru ──────────────────────────────────────────────────

def test_sabit_deger_kurali_filtre_uretir():
    _, _, _, rr, ar = _env()
    rr.add("d1", "bolge", "=", "TR", None, created_by="admin")
    filtreler = build_rls_filters(rr.list_for("d1"), "u1", "sales", ar)
    assert filtreler == [{"table": "sales", "column": "bolge", "operator": "=", "value": "TR"}], filtreler


def test_liste_kurali_in_ile_calisir():
    _, _, _, rr, ar = _env()
    rr.add("d1", "bolge", "IN", ["TR", "DE"], None, created_by="admin")
    f = build_rls_filters(rr.list_for("d1"), "u1", "sales", ar)
    assert f[0]["operator"] == "IN" and f[0]["value"] == ["TR", "DE"]


def test_ozellik_kurali_kullanicinin_degerini_alir():
    _, _, _, rr, ar = _env()
    ar.set("u1", "department", "sales")
    ar.set("u2", "department", "hr")
    rr.add("d1", "dept", "=", None, "department", created_by="admin")
    f1 = build_rls_filters(rr.list_for("d1"), "u1", "sales", ar)
    f2 = build_rls_filters(rr.list_for("d1"), "u2", "sales", ar)
    assert f1[0]["value"] == "sales" and f2[0]["value"] == "hr"


def test_ozellik_eksikse_rls_hatasi():
    _, _, _, rr, ar = _env()
    rr.add("d1", "dept", "=", None, "department", created_by="admin")
    try:
        build_rls_filters(rr.list_for("d1"), "u1", "sales", ar)
    except RLSError:
        return
    raise AssertionError("öznitelik eksikken erişim verildi")


# ── Veri seti çalıştırma ──────────────────────────────────────────

def test_iki_kullanici_farkli_satir_kumesi_gorur():
    _, dr, sr, rr, ar = _env()
    ar.set("u1", "department", "sales")
    ar.set("u2", "department", "hr")
    rr.add("d1", "dept", "=", None, "department", created_by="admin")
    ex = _Exec()
    _run(_u("u1"), dr, sr, rr, ar, ex)
    _run(_u("u2"), dr, sr, rr, ar, ex)
    p1, p2 = ex.calls[0]["params"], ex.calls[1]["params"]
    assert "sales" in p1.values() and "hr" in p2.values(), (p1, p2)
    assert "WHERE" in ex.calls[0]["sql"] and "WHERE" in ex.calls[1]["sql"]
    assert p1 != p2


def test_yonetici_kurallari_atlar():
    _, dr, sr, rr, ar = _env()
    rr.add("d1", "bolge", "=", "TR", None, created_by="admin")
    ex = _Exec()
    _run(_u("adm", "admin"), dr, sr, rr, ar, ex)
    assert "WHERE" not in ex.calls[-1]["sql"], ex.calls[-1]["sql"]


def test_sahip_de_kurallara_tabidir():
    _, dr, sr, rr, ar = _env()
    rr.add("d1", "bolge", "=", "TR", None, created_by="admin")
    ex = _Exec()
    _run(_u("owner"), dr, sr, rr, ar, ex)
    assert "WHERE" in ex.calls[-1]["sql"]


def test_ozellik_eksik_calistirma_403():
    _, dr, sr, rr, ar = _env()
    rr.add("d1", "dept", "=", None, "department", created_by="admin")
    ex = _Exec()
    assert _status(lambda: _run(_u("u1"), dr, sr, rr, ar, ex)) == 403
    assert ex.calls == []


# ── Kural yönetimi ────────────────────────────────────────────────

def test_kural_yalniz_admin_ekler():
    _, dr, sr, rr, ar = _env()
    body = ds_api.RuleIn(column="bolge", operator="=", value="TR")
    assert _status(lambda: ds_api.create_rule("d1", body, current=_u("owner"), repo=dr,
                                              rls_repo=rr)) == 403


def test_gecersiz_kolon_adi_400():
    _, dr, _, rr, _ = _env()
    body = ds_api.RuleIn(column="bolge; DROP TABLE x", operator="=", value="TR")
    assert _status(lambda: ds_api.create_rule("d1", body, current=_u("adm", "admin"), repo=dr,
                                              rls_repo=rr)) == 400


def test_kural_hem_deger_hem_ozellik_olamaz():
    try:
        ds_api.RuleIn(column="bolge", operator="=", value="TR", attr="department")
    except Exception:
        return
    raise AssertionError("hem value hem attr kabul edildi")


def test_admin_kural_ekler_ve_listeler():
    _, dr, _, rr, _ = _env()
    body = ds_api.RuleIn(column="bolge", operator="=", value="TR")
    out = ds_api.create_rule("d1", body, current=_u("adm", "admin"), repo=dr, rls_repo=rr)
    ds_api.create_rule("d1", body, current=_u("adm", "admin"), repo=dr, rls_repo=rr)
    lst = ds_api.list_rules("d1", current=_u("adm", "admin"), repo=dr, rls_repo=rr)
    assert len(lst) == 2 and out["rule_id"], lst


def test_ozellik_yalniz_admin_ayarlar():
    from app.auth.user_repository import UserRepository
    store, _, _, _, ar = _env()
    users = UserRepository(store)
    uid = users.create("u1", "guclu-sifre-1", role="viewer").user_id
    body = users_api.AttributeIn(value="sales")
    assert _status(lambda: users_api.set_attribute(uid, "department", body, current=_u("u1"),
                                                   attr_repo=ar, user_repo=users)) == 403
    assert _status(lambda: users_api.set_attribute(uid, "department", body, current=_u("adm", "admin"),
                                                   attr_repo=ar, user_repo=users)) == 200


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
