# -*- coding: utf-8 -*-
"""
NLQ Kademe 1 - JSON Plan Insaasi

TopNIntent + FilledSlots -> QueryRunRequest ile BIREBIR eslesen sozluk.
app/models/schemas.py (formula_only_columns alani dahil, patch ile eklendi)
ve app/services/sql_builder.py (formula_only_columns destegi, patch ile
eklendi) ile 2026-09-18'de sandbox'ta dogrulandi: postgresql + mssql icin
tam calisir SQL uretimi, 3 farkli test sorusu (tek-tablo, tek-hop join,
iki-hop join) icin.

BILINEN SINIR: Oracle dialect'inde group_by/order_by/joins/calculated_fields
buyuk harfe cevrilmiyor (sql_builder.py'nin mevcut, NLQ'dan bagimsiz bir
bug'u) - bu plan Oracle baglantilarinda su an GUVENLE calismaz, ayrica
duzeltilmesi gerekir (bkz. BACKLOG.md).
"""


def build_top_n_plan(intent, slots, conn_id):
    """
    intent : TopNIntent
    slots  : FilledSlots
    conn_id: hedef baglanti id'si (API endpoint'inden gelir)
    -> dict (QueryRunRequest ile uyumlu JSON plan) veya None
    """
    if intent is None or slots is None:
        return None

    metric_alias = f"{slots.metric_col.lower()}_toplam"

    joins = []
    if slots.join_path:
        current_t1 = slots.dimension_table
        for hop in slots.join_path:
            to_table_full = hop["table"]  # "Schema.Table"
            joins.append({
                "type": "INNER JOIN",
                "t1": current_t1,
                "f1": hop["on_a"],
                "t2": to_table_full,
                "f2": hop["on_b"],
            })
            current_t1 = to_table_full.split(".", 1)[-1]

    plan = {
        "conn_id": conn_id,
        "base_table": slots.dimension_table,
        "schema_name": slots.dimension_schema,
        "fields": {slots.dimension_display_col: "group"},
        "joins": joins,
        "filters": [],
        "group_by": [slots.dimension_display_col],
        "order_by": [
            ("-" if intent.direction == "DESC" else "") + metric_alias
        ],
        "calculated_fields": [
            {"name": metric_alias, "formula": f"SUM({slots.metric_col})"}
        ],
        "formula_only_columns": [slots.metric_col],
        "limit": intent.n,
    }

    plan["_meta"] = {
        "nlq_raw_text": intent.raw_text,
        "nlq_confidence": round(slots.confidence, 1),
        "nlq_intent": "top_n",
    }

    return plan
