# -*- coding: utf-8 -*-
"""
NLQ Kademe 1 - Turkce is terimi es anlamlilar sozlugu.

Sema-bagimsiz: hangi veritabanina baglanilirsa baglanilsin gecerli genel
is terimleri. Bu sozluk DETERMINISTIK tespite (granularity_analyzer.py)
GIRDI DEGILDIR, sadece NLQ katmaninin slot doldurma asamasinda kullanilir.
"""

# Ölçü (metric) ipuçları: Türkçe kelime -> şemada olabilecek İngilizce kolon adları. Kesin eşleşme değil, aday üretmek içindir.
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

# Boyut ipuçları: Türkçe varlık adı -> olası tablo adları.
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
    """
    Türkçe ölçü ipucunu (ör. 'en çok satan') şemada aranacak İngilizce kolon adı adaylarına çevirir.
    Sözlükteki anahtarla başlayan ya da onunla başlayan kelimeler eşleşir. Sonuç bir liste döner.
    """
    # Küçük harfe çevrilip boşluklarla kelimelere ayrılır; her kelime için sözlük taranır.
    hint_lower = (hint or "").lower().strip()
    candidates = set()
    for word in hint_lower.split():
        for key, syns in METRIC_SYNONYMS.items():
            if word.startswith(key) or key.startswith(word):
                candidates.update(syns)
    # Kelimelerin kendisi de aday olur; sözlükte olmasa da kolon adı olabilirler.
    candidates.update(hint_lower.split())
    return list(candidates)


def expand_dimension_hint(hint: str):
    """Türkçe boyut ipucunu (ör. 'ürün') olası tablo adı adaylarına çevirir. İpucunun kendisi de aday listesine eklenir."""
    hint_lower = (hint or "").lower().strip()
    candidates = set()
    for key, syns in DIMENSION_SYNONYMS.items():
        # DİKKAT: Boş ipucu ('') her anahtarla eşleşir ve tüm boyutları aday yapar. Çağıran taraf boş ipucunu engellemelidir.
        if hint_lower.startswith(key) or key.startswith(hint_lower):
            candidates.update(syns)
    # İpucunun kendisi de aday listesine eklenir.
    candidates.add(hint_lower)
    return list(candidates)
