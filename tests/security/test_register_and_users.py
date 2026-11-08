"""
Güvenlik regresyon testleri — Faz 0.3 (açık kayıt kapatma).

  - Kayıt varsayılan olarak kapalı (DATALENS_ALLOW_REGISTER != "true"); kullanıcı varken 403.
  - İlk kullanıcı (bootstrap) her zaman açık: boş sistem kilitli kalmasın.
  - Yeni kullanıcıyı yalnız admin oluşturabilir: POST /api/users.

Çalıştırma:
  cd /opt/superbi && venv/bin/python tests/security/test_register_and_users.py
"""
from __future__ import annotations

import inspect
import os
import sys
import traceback
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.api import auth  # noqa: E402
from app.api import users  # noqa: E402

# Faz 0.6: JWT secret zorunlu; kayıt testleri gerçek token ürettiği için yalnız test süreci için tanımlanır.
os.environ.setdefault("DATALENS_JWT_SECRET", "yalnizca-test-icin-sir")


class _Repo:
    """UserRepository taklidi: count ve create."""

    def __init__(self, n: int, duplicate: bool = False):
        self.n = n
        self.duplicate = duplicate
        self.created: list[tuple] = []

    def count(self) -> int:
        return self.n

    def create(self, username, password, role=None):
        if self.duplicate:
            raise ValueError(f"Kullanıcı adı zaten alınmış: {username}")
        self.created.append((username, role))
        return SimpleNamespace(user_id="u-1", username=username, role=role or "viewer")


def _env(value):
    class _Ctx:
        def __enter__(self):
            self._old = os.environ.get("DATALENS_ALLOW_REGISTER")
            if value is None:
                os.environ.pop("DATALENS_ALLOW_REGISTER", None)
            else:
                os.environ["DATALENS_ALLOW_REGISTER"] = value

        def __exit__(self, *a):
            if self._old is None:
                os.environ.pop("DATALENS_ALLOW_REGISTER", None)
            else:
                os.environ["DATALENS_ALLOW_REGISTER"] = self._old

    return _Ctx()


BODY = auth.UserRegister(username="yeniuser", password="guclu-sifre-1")


# ── 0.3 kayıt kapatma ─────────────────────────────────────────────

def test_kayit_varsayilan_kapali_kullanici_varken_403():
    with _env(None):
        try:
            auth.register(BODY, repo=_Repo(n=1))
        except HTTPException as e:
            assert e.status_code == 403
            return
    raise AssertionError("kayıt kapalıyken kullanıcı oluşturuldu")


def test_kayit_false_iken_403():
    with _env("false"):
        try:
            auth.register(BODY, repo=_Repo(n=1))
        except HTTPException as e:
            assert e.status_code == 403
            return
    raise AssertionError("DATALENS_ALLOW_REGISTER=false iken kayıt açıldı")


def test_ilk_kullanici_bootstrap_her_zaman_acik():
    with _env(None):
        repo = _Repo(n=0)
        resp = auth.register(BODY, repo=repo)
        assert resp.access_token
        assert len(repo.created) == 1


def test_env_true_iken_kayit_acik():
    with _env("true"):
        repo = _Repo(n=3)
        resp = auth.register(BODY, repo=repo)
        assert resp.access_token
        assert len(repo.created) == 1


# ── 0.3 admin kullanıcı oluşturma ─────────────────────────────────

def _create_user_dep():
    """POST /api/users endpoint'inin rol bağımlılığı (current parametresi)."""
    return inspect.signature(users.create_user).parameters["current"].default.dependency


def test_viewer_kullanici_olusturamaz():
    dep = _create_user_dep()
    try:
        dep(current=SimpleNamespace(role="viewer", user_id="v"))
    except HTTPException as e:
        assert e.status_code == 403
        return
    raise AssertionError("viewer kullanıcı oluşturma yetkisi aldı")


def test_admin_kullanici_olusturabilir():
    dep = _create_user_dep()
    admin = SimpleNamespace(role="admin", user_id="a")
    assert dep(current=admin) is admin


def test_admin_olusturma_rol_ve_sonuc():
    repo = _Repo(n=2)
    body = users.UserCreate(username="ali_viewer", password="guclu-sifre-1", role="viewer")
    out = users.create_user(body=body, current=SimpleNamespace(role="admin", user_id="a"), repo=repo)
    assert out["role"] == "viewer" and out["username"] == "ali_viewer"
    assert repo.created == [("ali_viewer", "viewer")]


def test_gecersiz_rol_reddedilir():
    try:
        users.UserCreate(username="x_kullanici", password="guclu-sifre-1", role="superuser")
    except ValidationError:
        return
    raise AssertionError("geçersiz rol kabul edildi")


def test_admin_olusturma_mukerrer_409():
    repo = _Repo(n=2, duplicate=True)
    body = users.UserCreate(username="ali_viewer", password="guclu-sifre-1", role="viewer")
    try:
        users.create_user(body=body, current=SimpleNamespace(role="admin", user_id="a"), repo=repo)
    except HTTPException as e:
        assert e.status_code == 409
        return
    raise AssertionError("mükerrer kullanıcı adı 409 dönmedi")


def test_users_route_uygulamaya_bagli():
    """OpenAPI şeması, /api/users yolunu ve POST metodunu içermeli (router main.py'ye bağlı)."""
    os.environ.setdefault("DATALENS_DB", ":memory:")
    from app.main import app  # noqa: WPS433
    paths = app.openapi()["paths"]
    assert "/api/users" in paths, "/api/users main.py'ye bağlı değil"
    assert "post" in paths["/api/users"], "/api/users altında POST yok"


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
