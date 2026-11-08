"""
Güvenlik regresyon testleri — Faz 0.4 (sunucu üzerinden ağ erişimi / hata sızıntısı).

  - Host politikası: loopback, link-local (169.254.169.254 dahil), unspecified engellenir.
  - DATALENS_ALLOWED_DB_HOSTS tanımlıysa yalnız o hostlara izin verilir.
  - Bağlantı hatalarında ham exception metni kullanıcıya dönmez (IP / iç ayrıntı sızmaz).

Çalıştırma:
  cd /opt/superbi && venv/bin/python tests/security/test_host_and_errors.py
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

from app.api import connections  # noqa: E402
from app.core.connector_registry import ConnectorRegistry  # noqa: E402
from app.core.host_policy import check_db_host  # noqa: E402
from app.models.schemas import ConnectionParams  # noqa: E402


class _Env:
    def __init__(self, **kv):
        self.kv = kv

    def __enter__(self):
        self.old = {k: os.environ.get(k) for k in self.kv}
        for k, v in self.kv.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    return False


# ── 0.4 host politikası ───────────────────────────────────────────

def test_loopback_reddedilir():
    with _Env(DATALENS_ALLOWED_DB_HOSTS=None):
        assert _raises(lambda: check_db_host("127.0.0.1")), "127.0.0.1 kabul edildi"
        assert _raises(lambda: check_db_host("localhost")), "localhost kabul edildi"


def test_metadata_ip_reddedilir():
    with _Env(DATALENS_ALLOWED_DB_HOSTS=None):
        assert _raises(lambda: check_db_host("169.254.169.254")), "metadata IP kabul edildi"


def test_bos_host_localhost_sayilir_ve_reddedilir():
    with _Env(DATALENS_ALLOWED_DB_HOSTS=None):
        assert _raises(lambda: check_db_host("")), "boş host (localhost) kabul edildi"


def test_allowlist_disi_host_reddedilir():
    with _Env(DATALENS_ALLOWED_DB_HOSTS="postgres-ortak,mysql-ortak"):
        assert _raises(lambda: check_db_host("127.0.0.1")), "allowlist dışı IP kabul edildi"
        assert _raises(lambda: check_db_host("169.254.169.254")), "allowlist dışı metadata kabul edildi"
        assert _raises(lambda: check_db_host("baska-host")), "allowlist dışı ad kabul edildi"


def test_allowlist_ici_host_kabul_edilir():
    with _Env(DATALENS_ALLOWED_DB_HOSTS="postgres-ortak, Mysql-Ortak"):
        check_db_host("postgres-ortak")  # istisna fırlatmamalı
        check_db_host("mysql-ortak")


def test_registry_build_url_host_kontrolu():
    """Politika bağlantı URL'si üretimine bağlı olmalı (create ve yeniden bağlanma ikisini de kapsar)."""
    with _Env(DATALENS_ALLOWED_DB_HOSTS=None):
        reg = ConnectorRegistry()
        assert _raises(lambda: reg._build_url("postgresql", {"host": "127.0.0.1", "database": "x"})), \
            "_build_url loopback'e URL üretti"


# ── 0.4 hata mesajı sızıntısı ─────────────────────────────────────

class _FakeRegistry:
    def __init__(self, exc: Exception):
        self.exc = exc

    def driver_installed(self, db_type):
        return True

    def get_engine(self, *a, **k):
        raise self.exc

    def remove_engine(self, conn_id):
        pass


def test_create_hata_mesaji_ic_bilgi_sizdirmaz():
    params = ConnectionParams(db_type="postgresql", host="postgres-ortak", database="x")
    reg = _FakeRegistry(RuntimeError("could not connect to 10.20.30.40:5432 secret=abc"))
    try:
        connections.create_connection(
            params=params,
            current=SimpleNamespace(user_id="a", role="admin"),
            registry=reg,
            repo=None,
        )
    except HTTPException as e:
        assert e.status_code == 400
        assert "10.20.30.40" not in str(e.detail), "iç IP kullanıcıya sızdı"
        assert "secret" not in str(e.detail), "ham hata metni sızdı"
        return
    raise AssertionError("hata 400 olarak dönmedi")


class _FailingEngine:
    def connect(self):
        raise RuntimeError("auth failed for user at 10.9.9.9")


def test_test_connection_hata_mesaji_sizdirmaz():
    ok, msg = ConnectorRegistry().test_connection(_FailingEngine())
    assert ok is False
    assert "10.9.9.9" not in msg, "test_connection ham IP döndü"
    assert "auth failed" not in msg.lower(), "test_connection ham hata döndü"


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
