# -*- coding: utf-8 -*-
"""
NLQ Kademe 1 - Turkce is terimi es anlamlilar sozlugu.

Sema-bagimsiz: hangi veritabanina baglanilirsa baglanilsin gecerli genel
is terimleri. Bu sozluk DETERMINISTIK tespite (granularity_analyzer.py)
GIRDI DEGILDIR, sadece NLQ katmaninin slot doldurma asamasinda kullanilir.
"""

METRIC_SYNONYMS = {
    "satan": ["sales", "salesamount", "totaldue", "orderqty", "quantity", "linetotal"],
    "satış": ["sales", "salesamount", "totaldue", "linetotal"],
    "satis": ["sales", "salesamount", "totaldue", "linetotal"],
    "ciro": ["revenue", "totaldue", "salesamount", "linetotal"],
    "cirolu": ["revenue", "totaldue", "salesamount", "linetotal"],
    "stok": ["stock", "quantity", "inventory", "safetystocklevel"],
    "stoklu": ["stock", "quantity", "inventory", "safetystocklevel"],
    "adet": ["quantity", "qty", "count"],
    "miktar": ["quantity", "amount", "qty"],
    "fiyat": ["price", "unitprice", "listprice"],
    "fiyatlı": ["price", "unitprice", "listprice"],
    "maliyet": ["cost", "standardcost"],
    "maliyetli": ["cost", "standardcost"],
    "kar": ["profit", "margin"],
    "karlı": ["profit", "margin"],
    "sipariş": ["order", "salesorder", "orderqty"],
    "siparis": ["order", "salesorder", "orderqty"],
    "kâr": ["profit", "margin"],
    "indirim": ["discount"],
    "indirimli": ["discount"],
    "ağırlık": ["weight"],
    "agirlik": ["weight"],
}

DIMENSION_SYNONYMS = {
    "ürün": ["product"],
    "urun": ["product"],
    "müşteri": ["customer"],
    "musteri": ["customer"],
    "kategori": ["category", "productcategory", "productsubcategory"],
    "tedarikçi": ["vendor", "supplier"],
    "tedarikci": ["vendor", "supplier"],
    "çalışan": ["employee"],
    "calisan": ["employee"],
    "şehir": ["city"],
    "sehir": ["city"],
    "bölge": ["territory", "region"],
    "bolge": ["territory", "region"],
    "mağaza": ["store"],
    "magaza": ["store"],
    "sipariş": ["salesorder", "order"],
    "siparis": ["salesorder", "order"],
}


def expand_metric_hint(hint: str):
    hint_lower = (hint or "").lower().strip()
    candidates = set()
    for word in hint_lower.split():
        for key, syns in METRIC_SYNONYMS.items():
            if word.startswith(key) or key.startswith(word):
                candidates.update(syns)
    candidates.update(hint_lower.split())
    return list(candidates)


def expand_dimension_hint(hint: str):
    hint_lower = (hint or "").lower().strip()
    candidates = set()
    for key, syns in DIMENSION_SYNONYMS.items():
        if hint_lower.startswith(key) or key.startswith(hint_lower):
            candidates.update(syns)
    candidates.add(hint_lower)
    return list(candidates)
