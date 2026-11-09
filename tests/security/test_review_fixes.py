"""
Güvenlik incelemesi bulguları için regresyon testleri.

  1. Gizli kolon sızıntısı: 'off' kolon istemci tarafından açılamaz; boş seçim '*' üretmez.
  2. Yetki iptali: rol her istekte veritabanından okunur (JWT'deki eski rol kullanılmaz).
  3. Yazma izni yapıyı değiştiremez: yalnız sahip/admin tablo, bağlantı, kolon, join, filtre değiştirir.
  4. Silinen veri setinin satır kuralları da silinir.
  5. Öznitelik yazımı: var olmayan kullanıcıya ve geçersiz anahtara izin verilmez.

Çalıştırma:
  cd <worktree> && venv/bin/python tests/security/test_review_fixes.py
"""
from __future__ import annotations

import os
import sys
import traceback
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("DATALENS_JWT_SECRET", "yalnizca-test-icin-sir-2")

from fastapi import HTTPException  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials  # noqa: E402

from app.db.sqlite_store import SQLiteStore  # noqa: E402
from app.core.repository import Dataset, DatasetRepository  # noqa: E402
from app.core.sharing import ShareRepository  # noqa: E402
from app.core.rls import RuleRepository, AttributeRepository  # noqa: E402
from app.auth.user_repository import UserRepository  # noqa: E402
from app.auth.jwt_core import create_token  # noqa: E402
from app.api import datasets as ds_api  # noqa: E402
from app.api import users as users_api  # noqa: E402
from app import deps  # noqa: E402


class _Exec:
    def __init__(self):
        self.calls = []

    def execute(self, **kw):
        self.calls.append(kw)
        return {"columns": [], "rows": [], "row_count": 0}


def _u(uid, role="viewer"):
    return SimpleNamespace(user_id=uid, role=role, username=uid)


def _status(fn):
    try:
        fn()
    except HTTPException as e:
        return e.status_code
    return 200


def _patch_engine():
    ds_api.resolve_connection_engine = lambda conn_id, current, registry, repo: (
        object(), SimpleNamespace(conn_id=conn_id, db_type="postgresql"))


def _env(fields):
    store = SQLiteStore(":memory:")
    dr = DatasetRepository(store)
    sr = ShareRepository(store)
    rr = RuleRepository(store)
    ar = AttributeRepository(store)
    dr.save(Dataset(dataset_id="d1", name="Çalışan", conn_id="c1", base_table="employees",
                    owner_id="owner", fields=fields))
    sr.create("dataset", "d1", "user", "viewer1", "read", created_by="owner")
    sr.create("dataset", "d1", "user", "writer1", "write", created_by="owner")
    return store, dr, sr, rr, ar


def _run(current, env, body, ex):
    _patch_engine()
    _, dr, sr, rr, ar = env
    return ds_api.run_dataset("d1", body, current=current, repo=dr, shares=sr, registry=None,
                              conn_repo=None, executor=ex, rls_repo=rr, attr_repo=ar)


# ── 1. Gizli kolon sızıntısı ──────────────────────────────────────

def test_off_kolon_istek_ile_acilamaz():
    env = _env({"name": "dim", "salary": "off"})
    ex = _Exec()
    body = ds_api.DatasetRunIn(sample=10, fields={"salary": "dim"})
    assert _status(lambda: _run(_u("viewer1"), env, body, ex)) == 400
    assert ex.calls == [], "gizli kolonla sorgu çalıştı"


def test_istek_rolu_sunucuda_yok_sayilir():
    """İstemci 'off' gönderse bile görünür kolon 'dim' olarak çalışır; sorgu kolon listesini sınırlar."""
    env = _env({"name": "dim", "salary": "off"})
    ex = _Exec()
    body = ds_api.DatasetRunIn(sample=10, fields={"name": "off"})
    assert _status(lambda: _run(_u("viewer1"), env, body, ex)) == 200
    sql = ex.calls[-1]["sql"]
    assert "salary" not in sql and "*" not in sql, sql


def test_istek_bos_iken_yalniz_gorunur_kolonlar():
    env = _env({"name": "dim", "salary": "off"})
    ex = _Exec()
    body = ds_api.DatasetRunIn(sample=10)
    assert _status(lambda: _run(_u("viewer1"), env, body, ex)) == 200
    sql = ex.calls[-1]["sql"]
    assert "salary" not in sql and "*" not in sql, sql


def test_tum_kolonlar_gizliyse_yildiz_yerine_400():
    env = _env({"name": "off", "salary": "off"})
    ex = _Exec()
    body = ds_api.DatasetRunIn(sample=10)
    assert _status(lambda: _run(_u("viewer1"), env, body, ex)) == 400
    assert ex.calls == []


# ── 2. Yetki iptali (rol veritabanından okunur) ──────────────────

def test_rol_veritabanindan_okunur():
    store = SQLiteStore(":memory:")
    users = UserRepository(store)
    u = users.create("ali", "guclu-sifre-1", role="admin")
    token = create_token(u.user_id, "ali", "admin")
    store.execute("UPDATE users SET role='viewer' WHERE user_id=?", (u.user_id,))
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_repo=users)))
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    cur = deps.get_current_user(req=req, creds=creds)
    assert cur.role == "viewer", f"JWT'deki eski rol kullanıldı: {cur.role}"


def test_silinmis_kullanici_reddedilir():
    store = SQLiteStore(":memory:")
    users = UserRepository(store)
    u = users.create("ali", "guclu-sifre-1", role="admin")
    token = create_token(u.user_id, "ali", "admin")
    store.execute("DELETE FROM users WHERE user_id=?", (u.user_id,))
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(user_repo=users)))
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    try:
        deps.get_current_user(req=req, creds=creds)
    except HTTPException as e:
        assert e.status_code == 401
        return
    raise AssertionError("silinmiş kullanıcı token ile geçti")


# ── 3. Yazma izni yapıyı değiştiremez ────────────────────────────

def test_yazma_izni_tablo_degistiremez():
    env = _env({"name": "dim"})
    _, dr, sr, rr, ar = env
    body = ds_api.DatasetIn(name="Yeni", conn_id="c1", base_table="salaries")
    assert _status(lambda: ds_api.update_dataset("d1", body, current=_u("writer1"), repo=dr,
                                                 conn_repo=None, shares=sr)) == 403
    assert dr.get("d1").base_table == "employees"


def test_yazma_izni_yalniz_ad_degistirebilir():
    env = _env({"name": "dim"})
    _, dr, sr, rr, ar = env
    body = ds_api.DatasetIn(name="Yeni Ad", conn_id="c1", base_table="employees", fields={"name": "dim"})
    assert _status(lambda: ds_api.update_dataset("d1", body, current=_u("writer1"), repo=dr,
                                                 conn_repo=None, shares=sr)) == 200
    assert dr.get("d1").name == "Yeni Ad"


# ── 4. Silinen veri setinin kuralları da silinir ─────────────────

def test_veri_seti_silinince_kurallar_silinir():
    env = _env({"name": "dim"})
    _, dr, sr, rr, ar = env
    rr.add("d1", "name", "=", "x", None, created_by="admin")
    ds_api.delete_dataset("d1", current=_u("owner"), repo=dr, shares=sr, rls_repo=rr)
    assert rr.list_for("d1") == [], "yetim kurallar kaldı"


# ── 5. Öznitelik doğrulaması ─────────────────────────────────────

def test_var_olmayan_kullaniciya_oznitelik_yazilamaz():
    store = SQLiteStore(":memory:")
    ar = AttributeRepository(store)
    users = UserRepository(store)
    body = users_api.AttributeIn(value="sales")
    assert _status(lambda: users_api.set_attribute("yok", "department", body, current=_u("adm", "admin"),
                                                   attr_repo=ar, user_repo=users)) == 404


def test_gecersiz_oznitelik_anahtari_reddedilir():
    store = SQLiteStore(":memory:")
    ar = AttributeRepository(store)
    users = UserRepository(store)
    u = users.create("ali", "guclu-sifre-1", role="viewer")
    body = users_api.AttributeIn(value="sales")
    assert _status(lambda: users_api.set_attribute(u.user_id, "x y; drop", body,
                                                   current=_u("adm", "admin"), attr_repo=ar,
                                                   user_repo=users)) == 400


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
