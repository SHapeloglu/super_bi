"""
NLQ sözleşme testi — slot_filler / plan_builder ile /api/analyze ve /api/query/run arasındaki biçim.

Doğrulanan uyuşmazlıklar:
  1. /api/analyze/{conn_id}/results tablo profili 'table_name' ve kolon LİSTESİ döner;
     slot_filler 'table' ve kolon->sınıf SÖZLÜĞÜ bekliyordu.
  2. plan_builder 'limit' anahtarı üretiyordu; QueryRunRequest bunu tanımaz (sessizce yok sayılır),
     satır sayısı 'sample' ile verilmeli.

Çalıştırma:
  cd <worktree> && venv/bin/python tests/unit/test_nlq_contract.py
"""
from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.models.schemas import QueryRunRequest  # noqa: E402
from app.services.nlq import plan_builder, slot_filler  # noqa: E402
from app.services.nlq.intent_patterns import detect_top_n  # noqa: E402
from app.services.nlq.nlq_engine import process_question  # noqa: E402


def _analyze_profiles() -> list[dict]:
    """/api/analyze/{conn_id}/results biçiminde (table_name + kolon listesi) örnek profiller."""
    return [
        {
            "table_name": "Production.Product",
            "row_count": 504,
            "grain_columns": ["ProductID"],
            "columns": [
                {"name": "ProductID", "dtype": "int", "distinct_count": 504,
                 "cardinality_ratio": 1.0, "classification": "identifier"},
                {"name": "Name", "dtype": "nvarchar", "distinct_count": 504,
                 "cardinality_ratio": 1.0, "classification": "categorical"},
            ],
            "analyzed_at": "2026-11-01T10:00:00",
        },
        {
            "table_name": "Sales.SalesOrderDetail",
            "row_count": 121317,
            "grain_columns": ["SalesOrderDetailID"],
            "columns": [
                {"name": "ProductID", "dtype": "int", "distinct_count": 266,
                 "cardinality_ratio": 0.002, "classification": "categorical"},
                {"name": "LineTotal", "dtype": "numeric", "distinct_count": 100000,
                 "cardinality_ratio": 0.8, "classification": "metric"},
            ],
            "analyzed_at": "2026-11-01T10:00:00",
        },
    ]


def _relationships() -> list[dict]:
    """/api/analyze/{conn_id}/results 'relationships' biçiminde tek bir FK ilişkisi."""
    return [
        {"table_a": "Sales.SalesOrderDetail", "column_a": "ProductID",
         "table_b": "Production.Product", "column_b": "ProductID",
         "cardinality": "N:1", "source": "fk_constraint", "confidence": 1.0,
         "verified": True, "analyzed_at": "2026-11-01T10:00:00"},
    ]


def _run_plan() -> dict:
    """Örnek soru için üretilen planı döner; başarısızsa test hatası verir."""
    sonuc = process_question("en çok satan 5 ürün", _analyze_profiles(), _relationships(), "c1")
    assert sonuc.success, f"Plan üretilmedi: {sonuc.message}"
    return sonuc.plan


def test_analyze_ciktisi_slot_filler_tarafindan_eslesir():
    """Analyze biçimindeki profiller ile 'ürün' boyutu Product tablosuna eşleşmeli."""
    intent = detect_top_n("en çok satan 5 ürün")
    assert intent is not None, "Top-N niyeti tanınmadı"
    slots = slot_filler.fill_slots(intent, _analyze_profiles(), _relationships())
    assert slots is not None, "Analyze biçimi slot_filler'a uymuyor (eşleşme yok)"
    assert slots.dimension_table == "Product", slots.dimension_table
    assert slots.metric_col == "LineTotal", slots.metric_col


def test_plan_query_run_istek_semasina_uyar():
    """Planın üst düzey anahtarları (_meta hariç) QueryRunRequest alanlarının içinde olmalı."""
    plan = _run_plan()
    bilinmeyen = set(plan) - {"_meta"} - set(QueryRunRequest.model_fields)
    assert not bilinmeyen, f"QueryRunRequest tanımayan anahtarlar: {sorted(bilinmeyen)}"
    QueryRunRequest(**{k: v for k, v in plan.items() if k != "_meta"})


def test_plan_satir_sayisi_sample_ile_verilir():
    """'en çok ... 5' sorusunda satır sayısı 'sample'=5 olarak gitmeli; 'limit' yalnız yanıltır."""
    plan = _run_plan()
    assert plan.get("sample") == 5, f"sample=5 bekleniyordu: {plan.get('sample')!r}"
    assert "limit" not in plan, "'limit' anahtarı /run tarafından yok sayılır"


def test_plan_siralama_yonu_dogru():
    """'en çok' DESC: order_by ölçü aliasının '-' önekiyle gelmeli."""
    plan = _run_plan()
    assert plan["order_by"] == ["-linetotal_toplam"], plan["order_by"]


TESTS = [
    test_analyze_ciktisi_slot_filler_tarafindan_eslesir,
    test_plan_query_run_istek_semasina_uyar,
    test_plan_satir_sayisi_sample_ile_verilir,
    test_plan_siralama_yonu_dogru,
]


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
