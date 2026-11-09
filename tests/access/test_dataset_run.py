"""
Faz 1.2 devamı — paylaşılan veri setinin sunucu tarafında çalıştırılması.

Kural: okuma izni olan kullanıcı, kayıtlı veri seti tanımını çalıştırabilir. Bağlantı,
veri setinin SAHİBİNİN bağlantısı olarak açılır; kullanıcı SQL'i, tabloyu ya da bağlantıyı
değiştiremez. Erişimi olmayan kullanıcı 404 alır.

Çalıştırma:
  cd <worktree> && venv/bin/python tests/access/test_dataset_run.py
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
from app.api import datasets as ds_api  # noqa: E402
from app.core.rls import RuleRepository, AttributeRepository  # noqa: E402


class _Exec:
    """QueryExecutor taklidi: son çağrının argümanlarını saklar."""
    def __init__(self):
        self.calls = []

    def execute(self, **kw):
        self.calls.append(kw)
        return {"columns": ["id"], "rows": [[1]], "row_count": 1}


def _setup(monkey_owner_calls):
    store = SQLiteStore(":memory:")
    dr = DatasetRepository(store)
    sr = ShareRepository(store)
    dr.save(Dataset(dataset_id="d1", name="Satış", conn_id="c1", base_table="sales",
                    owner_id="owner", fields={"id": "id"}))
    return dr, sr


def _u(uid, role="viewer"):
    return SimpleNamespace(user_id=uid, role=role)


def _patch_engine(calls):
    """resolve_connection_engine yerine: hangi kimlikle çağrıldığını kaydeder."""
    def fake(conn_id, current, registry, repo):
        calls.append({"conn_id": conn_id, "as_user": current.user_id})
        return object(), SimpleNamespace(conn_id=conn_id, db_type="postgresql")
    ds_api.resolve_connection_engine = fake


def _run(current, dr, sr, ex, calls):
    _patch_engine(calls)
    body = ds_api.DatasetRunIn(sample=10)
    return ds_api.run_dataset("d1", body, current=current, repo=dr, shares=sr,
                              registry=None, conn_repo=None, executor=ex, rls_repo=RuleRepository(dr._s), attr_repo=AttributeRepository(dr._s))


def _status(fn):
    try:
        fn()
    except HTTPException as e:
        return e.status_code
    return 200


def test_sahip_calistirir():
    dr, sr = _setup([])
    ex, calls = _Exec(), []
    _run(_u("owner"), dr, sr, ex, calls)
    assert calls[-1]["as_user"] == "owner"
    assert "sales" in ex.calls[-1]["sql"]


def test_paylasim_okuma_calistirir_sahip_kimligiyle_baglanir():
    dr, sr = _setup([])
    sr.create("dataset", "d1", "user", "other", "read", created_by="owner")
    ex, calls = _Exec(), []
    _run(_u("other"), dr, sr, ex, calls)
    assert calls[-1]["as_user"] == "owner", "bağlantı alıcı kimliğiyle açıldı"
    assert ex.calls[-1]["user_id"] == "other", "önbellek/kayıt alıcıya ait olmalı"


def test_paylasimsiz_kullanici_404():
    dr, sr = _setup([])
    ex, calls = _Exec(), []
    assert _status(lambda: _run(_u("other"), dr, sr, ex, calls)) == 404
    assert ex.calls == [], "yetkisiz kullanıcı için sorgu çalıştı"


def test_kullanici_sql_ve_tablo_veremez():
    """İstek gövdesi yalnız örnek boyutunu taşır; tablo/bağlantı alanı kabul edilmez."""
    try:
        ds_api.DatasetRunIn(sample=10, base_table="users", conn_id="c9")
    except Exception:
        pass
    body = ds_api.DatasetRunIn(sample=10, base_table="users", conn_id="c9")
    assert not hasattr(body, "base_table") and not hasattr(body, "conn_id")


def test_sample_siniri():
    try:
        ds_api.DatasetRunIn(sample=0)
    except Exception:
        return
    raise AssertionError("sample=0 kabul edildi")


def _setup_iki_kolon():
    store = SQLiteStore(":memory:")
    dr = DatasetRepository(store)
    sr = ShareRepository(store)
    dr.save(Dataset(dataset_id="d2", name="İki kolon", conn_id="c1", base_table="sales",
                    owner_id="owner", fields={"id": "id", "tutar": "tutar"}))
    sr.create("dataset", "d2", "user", "other", "read", created_by="owner")
    return dr, sr


def test_alt_kume_kolon_secimi_sorguya_yansir():
    """Widget yalnız seçtiği kolonları ister; sunucu SQL'e yalnız onları yazar."""
    dr, sr = _setup_iki_kolon()
    ex, calls = _Exec(), []
    _patch_engine(calls)
    body = ds_api.DatasetRunIn(sample=10, fields={"id": "dim"})
    ds_api.run_dataset("d2", body, current=_u("other"), repo=dr, shares=sr,
                       registry=None, conn_repo=None, executor=ex, rls_repo=RuleRepository(dr._s), attr_repo=AttributeRepository(dr._s))
    sql = ex.calls[-1]["sql"]
    assert "id" in sql and "tutar" not in sql, sql


def test_veri_setinde_olmayan_kolon_400():
    dr, sr = _setup_iki_kolon()
    ex, calls = _Exec(), []
    _patch_engine(calls)
    body = ds_api.DatasetRunIn(sample=10, fields={"gizli_kolon": "dim"})
    assert _status(lambda: ds_api.run_dataset("d2", body, current=_u("other"), repo=dr, shares=sr,
                                              registry=None, conn_repo=None, executor=ex, rls_repo=RuleRepository(dr._s), attr_repo=AttributeRepository(dr._s))) == 400
    assert ex.calls == [], "geçersiz kolonla sorgu çalıştı"


def test_noktali_anahtar_cıplak_kolon_adiyla_eslesir():
    """Veri seti 'orders.id' gibi noktalı anahtar tutar; sonuç kolonu 'id' olarak gelir. Eşleşmeli."""
    store = SQLiteStore(":memory:")
    dr = DatasetRepository(store); sr = ShareRepository(store)
    dr.save(Dataset(dataset_id="d3", name="Noktalı", conn_id="c1", base_table="orders",
                    owner_id="owner", fields={"orders.id": "dim", "orders.tutar": "dim"}))
    sr.create("dataset", "d3", "user", "other", "read", created_by="owner")
    ex, calls = _Exec(), []
    _patch_engine(calls)
    body = ds_api.DatasetRunIn(sample=10, fields={"id": "dim"})
    ds_api.run_dataset("d3", body, current=_u("other"), repo=dr, shares=sr,
                       registry=None, conn_repo=None, executor=ex, rls_repo=RuleRepository(dr._s), attr_repo=AttributeRepository(dr._s))
    sql = ex.calls[-1]["sql"]
    assert "orders" in sql and "id" in sql and "tutar" not in sql, sql


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
