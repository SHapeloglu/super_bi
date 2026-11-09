"""
Güvenlik regresyon testleri — Faz 0.1 (SQLite dosya okuma) ve Faz 0.2 (bağlantı oluşturma yetkisi).

Çalıştırma (pytest kurulu değilse düz Python yeterli):
  cd /opt/superbi && venv/bin/python tests/security/test_sqlite_and_roles.py

Canlı data/superbi.db bu testlerde ASLA açılmaz; geçici dizinler kullanılır.
"""
from __future__ import annotations

import inspect
import os
import sqlite3
import sys
import tempfile
import traceback
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core.connector_registry import ConnectorRegistry  # noqa: E402
from app.api import connections  # noqa: E402


def _env(**kv):
    """Ortam değişkenlerini geçici olarak ayarlar; None değer = değişkeni kaldır."""
    class _Ctx:
        def __enter__(self):
            self._old = {k: os.environ.get(k) for k in kv}
            for k, v in kv.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        def __exit__(self, *a):
            for k, v in self._old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return _Ctx()


def _make_sqlite(path: str) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE users (id INTEGER, password_hash TEXT)")
    con.execute("INSERT INTO users VALUES (1, 'hash')")
    con.commit()
    con.close()


# ── 0.1 SQLite yol kısıtı ─────────────────────────────────────────

def test_sqlite_devre_disi_root_tanimsizken():
    """DATALENS_SQLITE_ROOT tanımlı değilse SQLite bağlantısı hiç kurulmamalı."""
    with _env(DATALENS_SQLITE_ROOT=None):
        reg = ConnectorRegistry()
        try:
            reg._build_url("sqlite", {"database": "/etc/hostname"})
        except ValueError:
            return
        raise AssertionError("root tanımsızken SQLite URL'si üretildi")


def test_sqlite_kok_disi_mutlak_yol_reddedilir():
    with tempfile.TemporaryDirectory() as root:
        with _env(DATALENS_SQLITE_ROOT=root):
            reg = ConnectorRegistry()
            for bad in ["/etc/hostname", "/opt/superbi/data/superbi.db"]:
                try:
                    reg._build_url("sqlite", {"database": bad})
                except ValueError:
                    continue
                raise AssertionError(f"kök dışı yol kabul edildi: {bad}")


def test_sqlite_dizin_gecisi_reddedilir():
    """'../' ile kök dizinden çıkma (path traversal) reddedilmeli."""
    with tempfile.TemporaryDirectory() as root:
        outside = os.path.join(os.path.dirname(root), "dis_" + os.path.basename(root) + ".db")
        _make_sqlite(outside)
        try:
            with _env(DATALENS_SQLITE_ROOT=root):
                reg = ConnectorRegistry()
                try:
                    reg._build_url("sqlite", {"database": "../" + os.path.basename(outside)})
                except ValueError:
                    return
                raise AssertionError("../ ile kök dışına çıkıldı")
        finally:
            os.remove(outside)


def test_sqlite_symlink_ile_kacis_reddedilir():
    """Kök içinde kök dışını gösteren symlink reddedilmeli (realpath ile çözülür)."""
    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
        target = os.path.join(other, "x.db")
        _make_sqlite(target)
        link = os.path.join(root, "link.db")
        os.symlink(target, link)
        with _env(DATALENS_SQLITE_ROOT=root):
            reg = ConnectorRegistry()
            try:
                reg._build_url("sqlite", {"database": "link.db"})
            except ValueError:
                return
            raise AssertionError("symlink ile kök dışı dosyaya erişildi")


def test_metadata_db_reddedilir():
    """Uygulamanın kendi metadata DB'si (DATALENS_DB) kullanıcı bağlantısı olamaz."""
    with tempfile.TemporaryDirectory() as root:
        meta = os.path.join(root, "superbi.db")
        _make_sqlite(meta)
        with _env(DATALENS_SQLITE_ROOT=root, DATALENS_DB=meta):
            reg = ConnectorRegistry()
            try:
                reg._build_url("sqlite", {"database": "superbi.db"})
            except ValueError:
                return
            raise AssertionError("metadata DB kullanıcı bağlantısı olarak açıldı")


def test_olmayan_dosya_olusturulmaz():
    """Var olmayan yol için boş dosya oluşturulmamalı (sqlite varsayılan davranışı engellenmeli)."""
    with tempfile.TemporaryDirectory() as root:
        yol = os.path.join(root, "yok.db")
        with _env(DATALENS_SQLITE_ROOT=root):
            reg = ConnectorRegistry()
            try:
                # Mutlak yol: göreli yol sqlite:/// ile CWD'ye gider, kök dizini sınamaz.
                url = reg._build_url("sqlite", {"database": yol})
            except ValueError:
                url = None  # reddedildi: dosya zaten oluşturulmadı
            if url is not None:
                try:
                    eng = create_engine(url)
                    with eng.connect() as c:
                        c.execute(text("SELECT 1"))
                except Exception:
                    pass  # bağlantı hatası beklenen davranış
        assert not os.path.exists(yol), "olmayan dosya oluşturuldu"


def test_salt_okunur_yazma_basarisiz():
    """Kök içindeki geçerli dosya salt okunur açılmalı; INSERT başarısız olmalı."""
    with tempfile.TemporaryDirectory() as root:
        dosya = os.path.join(root, "veri.db")
        _make_sqlite(dosya)
        with _env(DATALENS_SQLITE_ROOT=root):
            reg = ConnectorRegistry()
            url = reg._build_url("sqlite", {"database": dosya})
            eng = create_engine(url)
            # okuma çalışmalı
            with eng.connect() as c:
                assert c.execute(text("SELECT COUNT(*) FROM users")).scalar() == 1
            # yazma reddedilmeli
            failed = False
            try:
                with eng.begin() as c:
                    c.execute(text("INSERT INTO users VALUES (2, 'x')"))
            except Exception:
                failed = True
            eng.dispose()
            assert failed, "salt okunur bağlantıya yazma yapılabildi"


def test_bagli_sqlite_kayit_yeniden_baglanmada_reddedilir():
    """Restart sonrası reconnect de aynı politikadan geçmeli (root kaldırılırsa kayıt kullanılamaz)."""
    with tempfile.TemporaryDirectory() as root:
        dosya = os.path.join(root, "veri.db")
        _make_sqlite(dosya)
        with _env(DATALENS_SQLITE_ROOT=None):
            reg = ConnectorRegistry()
            try:
                reg._build_url("sqlite", {"database": dosya})
            except ValueError:
                return
            raise AssertionError("politika dışı SQLite kaydı yeniden bağlandı")


# ── 0.2 Bağlantı oluşturma / silme yetkisi ───────────────────────

def _dep_of(fn, name):
    """Endpoint'in ilgili parametresindeki Depends nesnesinin dependency fonksiyonunu döner."""
    return inspect.signature(fn).parameters[name].default.dependency


def test_viewer_baglanti_olusturamaz():
    dep = _dep_of(connections.create_connection, "current")
    viewer = SimpleNamespace(role="viewer", user_id="u1")
    try:
        dep(current=viewer)
    except HTTPException as e:
        assert e.status_code == 403
        return
    raise AssertionError("viewer bağlantı oluşturabildi")


def test_admin_baglanti_olusturabilir():
    dep = _dep_of(connections.create_connection, "current")
    admin = SimpleNamespace(role="admin", user_id="a1")
    assert dep(current=admin) is admin


def test_viewer_baglanti_silemez():
    dep = _dep_of(connections.delete_connection, "current")
    viewer = SimpleNamespace(role="viewer", user_id="u1")
    try:
        dep(current=viewer)
    except HTTPException as e:
        assert e.status_code == 403
        return
    raise AssertionError("viewer bağlantı silebildi")


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
