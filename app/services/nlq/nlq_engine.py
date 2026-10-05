# -*- coding: utf-8 -*-
"""
NLQ Kademe 1 - Ana Motor (Top-N kalibi)

Turkce soru -> (basarili ise) JSON plan, (basarisiz ise) fallback mesaji.

table_profiles/relationships parametreleri cagiran tarafca
/api/analyze/{conn_id}/results endpoint'inden getirilip buraya
GECIRILMELIDIR (bu modul kendi basina DB'ye gitmez).
"""
from .intent_patterns import detect_top_n
from .slot_filler import fill_slots
from .plan_builder import build_top_n_plan

FALLBACK_MESSAGE = (
    "Bu soruyu anlayamadım. Şu kalıplardan birini deneyebilirsiniz:\n"
    "  • \"En çok satan 5 ürün\"\n"
    "  • \"En düşük stoklu 10 ürün\"\n"
    "  • \"En yüksek cirolu 5 müşteri\""
)


class NLQResult:
    __slots__ = ("success", "plan", "message", "intent", "slots")

    def __init__(self, success, plan=None, message=None, intent=None, slots=None):
        self.success = success
        self.plan = plan
        self.message = message
        self.intent = intent
        self.slots = slots


def process_question(text, table_profiles, relationships, conn_id):
    """
    Ana giris noktasi. Tek soru -> NLQResult.
    conn_id: hedef baglanti id'si (API endpoint'inden gelir)
    """
    intent = detect_top_n(text)
    if intent is None:
        return NLQResult(success=False, message=FALLBACK_MESSAGE)

    slots = fill_slots(intent, table_profiles, relationships)
    if slots is None:
        return NLQResult(
            success=False,
            message=FALLBACK_MESSAGE + f"\n\n(Niyet \"Top-N\" olarak anlaşıldı ama "
                                        f"\"{intent.metric_hint}\" / \"{intent.dimension_hint}\" "
                                        f"şema ile eşleştirilemedi.)",
            intent=intent,
        )

    plan = build_top_n_plan(intent, slots, conn_id)
    return NLQResult(success=True, plan=plan, intent=intent, slots=slots)
