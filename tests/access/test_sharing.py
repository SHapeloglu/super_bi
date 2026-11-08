"""
Faz 1.2 — Paylaşım ve yetki testleri (dataset / dashboard).

Kurallar:
  - Sahip ve admin her şeyi yapar.
  - Paylaşım alıcısı (kullanıcı ya da rol) yalnız verilen izni kullanır:
      read  → görür, değiştiremez, silemez
      write → görür, değiştirebilir, silemez (silme yalnız sahip/admin)
  - Erişimi olmayan kaynak 404 (varlık sızdırmaz); erişimi var ama izni yetmiyorsa 403.
  - Paylaşılan kaydı düzenlemek sahipliği değiştirmez.

Çalıştırma:
  cd <worktree> && venv/bin/python tests/access/test_sharing.py
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
from app.core.repository import Dataset, DatasetRepository, Dashboard, DashboardRepository  # noqa: E402
from app.core.sharing import ShareRepository  # noqa: E402
from app.api import datasets as ds_api  # noqa: E402
from app.api import dashboard as dash_api  # noqa: E402
from app.api import shares as shares_api  # noqa: E402


def _setup():
    store = SQLiteStore(":memory:")
    return store, DatasetRepository(store), DashboardRepository(store), ShareRepository(store)


def _u(uid, role="viewer"):
    return SimpleNamespace(user_id=uid, role=role, username=uid)


def _mk_dataset(repo, ds_id="d1", owner="owner"):
    repo.save(Dataset(dataset_id=ds_id, name="Satış", conn_id="c1", base_table="sales", owner_id=owner))


def _mk_dashboard(repo, d_id="p1", owner="owner"):
    repo.save(Dashboard(dashboard_id=d_id, name="Pano", owner_id=owner))


def _status(fn):
    try:
        fn()
    except HTTPException as e:
        return e.status_code
    return 200


# ── Dataset ───────────────────────────────────────────────────────

def test_dataset_sahip_gorur():
    _, dr, _, sr = _setup()
    _mk_dataset(dr)
    assert _status(lambda: ds_api.get_dataset("d1", current=_u("owner"), repo=dr, shares=sr)) == 200


def test_dataset_yabanci_viewer_404():
    _, dr, _, sr = _setup()
    _mk_dataset(dr)
    assert _status(lambda: ds_api.get_dataset("d1", current=_u("other"), repo=dr, shares=sr)) == 404


def test_dataset_read_paylasim_gorur_degistiremez():
    _, dr, _, sr = _setup()
    _mk_dataset(dr)
    sr.create("dataset", "d1", "user", "other", "read", created_by="owner")
    assert _status(lambda: ds_api.get_dataset("d1", current=_u("other"), repo=dr, shares=sr)) == 200
    body = ds_api.DatasetIn(name="Yeni", conn_id="c1", base_table="sales")
    assert _status(lambda: ds_api.update_dataset("d1", body, current=_u("other"), repo=dr,
                                                 conn_repo=None, shares=sr)) == 403


def test_dataset_read_paylasim_silemez():
    _, dr, _, sr = _setup()
    _mk_dataset(dr)
    sr.create("dataset", "d1", "user", "other", "write", created_by="owner")
    assert _status(lambda: ds_api.delete_dataset("d1", current=_u("other"), repo=dr, shares=sr)) == 403


def test_dataset_rol_paylasimi():
    _, dr, _, sr = _setup()
    _mk_dataset(dr)
    sr.create("dataset", "d1", "role", "viewer", "read", created_by="owner")
    assert _status(lambda: ds_api.get_dataset("d1", current=_u("v2", "viewer"), repo=dr, shares=sr)) == 200
    assert _status(lambda: ds_api.get_dataset("d1", current=_u("e1", "editor"), repo=dr, shares=sr)) == 404


def test_dataset_paylasim_iptal_erisimi_kaldirir():
    _, dr, _, sr = _setup()
    _mk_dataset(dr)
    share_id = sr.create("dataset", "d1", "user", "other", "read", created_by="owner")
    assert _status(lambda: ds_api.get_dataset("d1", current=_u("other"), repo=dr, shares=sr)) == 200
    sr.delete(share_id)
    assert _status(lambda: ds_api.get_dataset("d1", current=_u("other"), repo=dr, shares=sr)) == 404


def test_dataset_liste_sahip_ve_paylasilan():
    _, dr, _, sr = _setup()
    _mk_dataset(dr, "d1", owner="owner")
    _mk_dataset(dr, "d2", owner="other")
    _mk_dataset(dr, "d3", owner="owner")
    sr.create("dataset", "d3", "user", "other", "write", created_by="owner")
    out = ds_api.list_datasets(current=_u("other"), repo=dr, shares=sr)
    ids = {d["dataset_id"]: d["permission"] for d in out}
    assert ids == {"d2": "write", "d3": "write"}, ids


def test_admin_hepsini_gorur():
    _, dr, _, sr = _setup()
    _mk_dataset(dr, "d1", owner="owner")
    assert _status(lambda: ds_api.get_dataset("d1", current=_u("adm", "admin"), repo=dr, shares=sr)) == 200


# ── Dashboard ─────────────────────────────────────────────────────

def test_dashboard_yazma_paylasimi_sahipligi_korur():
    _, _, pr, sr = _setup()
    _mk_dashboard(pr)
    sr.create("dashboard", "p1", "user", "other", "write", created_by="owner")
    body = dash_api.DashboardIn(name="Güncel")
    assert _status(lambda: dash_api.update_dashboard("p1", body, current=_u("other"), repo=pr, shares=sr)) == 200
    assert pr.get("p1").owner_id == "owner", "paylaşılan pano sahibi değişti"


def test_dashboard_read_paylasimi_guncelleyemez():
    _, _, pr, sr = _setup()
    _mk_dashboard(pr)
    sr.create("dashboard", "p1", "user", "other", "read", created_by="owner")
    body = dash_api.DashboardIn(name="Güncel")
    assert _status(lambda: dash_api.update_dashboard("p1", body, current=_u("other"), repo=pr, shares=sr)) == 403


def test_dashboard_admin_guncellemesi_sahibi_degistirmez():
    _, _, pr, sr = _setup()
    _mk_dashboard(pr)
    body = dash_api.DashboardIn(name="Admin")
    dash_api.update_dashboard("p1", body, current=_u("adm", "admin"), repo=pr, shares=sr)
    assert pr.get("p1").owner_id == "owner", "admin güncellemesi sahibi değiştirdi"


def test_dashboard_yabanci_404():
    _, _, pr, sr = _setup()
    _mk_dashboard(pr)
    assert _status(lambda: dash_api.get_dashboard("p1", current=_u("other"), repo=pr, shares=sr)) == 404


# ── Paylaşım API ──────────────────────────────────────────────────

class _Users:
    """UserRepository taklidi: yalnız tanıdığı kullanıcılar için nesne döner."""
    known = {"other", "owner"}

    def get_by_id(self, uid):
        return SimpleNamespace(user_id=uid) if uid in self.known else None


def test_paylasim_yalniz_sahip_ya_da_admin():
    _, dr, _, sr = _setup()
    _mk_dataset(dr)
    body = shares_api.ShareIn(resource_type="dataset", resource_id="d1", grantee_type="user",
                              grantee_id="other", permission="read")
    assert _status(lambda: shares_api.create_share(body, current=_u("other"), share_repo=sr,
                                                   ds_repo=dr, dash_repo=None, user_repo=_Users())) == 403
    assert _status(lambda: shares_api.create_share(body, current=_u("owner"), share_repo=sr,
                                                   ds_repo=dr, dash_repo=None, user_repo=_Users())) in (200, 201)


def test_paylasim_bilinmeyen_alici_404():
    _, dr, _, sr = _setup()
    _mk_dataset(dr)
    body = shares_api.ShareIn(resource_type="dataset", resource_id="d1", grantee_type="user",
                              grantee_id="hayalet", permission="read")
    assert _status(lambda: shares_api.create_share(body, current=_u("owner"), share_repo=sr,
                                                   ds_repo=dr, dash_repo=None, user_repo=_Users())) == 404


def test_gecersiz_izin_ve_rol_reddedilir():
    try:
        shares_api.ShareIn(resource_type="dataset", resource_id="d1", grantee_type="role",
                           grantee_id="superuser", permission="read")
    except Exception:
        pass
    else:
        raise AssertionError("geçersiz rol kabul edildi")
    try:
        shares_api.ShareIn(resource_type="dataset", resource_id="d1", grantee_type="user",
                           grantee_id="x", permission="delete")
    except Exception:
        return
    raise AssertionError("geçersiz izin kabul edildi")


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
