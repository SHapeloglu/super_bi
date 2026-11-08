# -*- coding: utf-8 -*-
"""
NLQ Kademe 1 - Niyet Tespiti: Top-N Siralama Kalibi

Ornekler:
  "En cok satan 5 urun"
  "En dusuk stoklu 10 urun hangileri"
  "En yuksek cirolu 5 musteri"
  "Kategoriye gore en cok satan 3 urun"
"""
import re

# Yön kelimeleri: çok / yüksek / fazla / büyük -> DESC (büyükten küçüğe); az / düşük / küçük -> ASC. Aksanlı ve aksansız yazımlar ikisi de kabul edilir.
DIRECTION_MAP = {
    "çok": "DESC", "cok": "DESC",
    "yüksek": "DESC", "yuksek": "DESC",
    "fazla": "DESC",
    "büyük": "DESC", "buyuk": "DESC",
    "az": "ASC",
    "düşük": "ASC", "dusuk": "ASC",
    "küçük": "ASC", "kucuk": "ASC",
}

# Yön kelimeleri regex'te alternatif olarak kullanılır. Uzunlar önce gelir ki kısa bir kelime uzun kelimenin başını yakalamasın.
_DIRECTION_ALT = "|".join(sorted(DIRECTION_MAP.keys(), key=len, reverse=True))

# Top-N soru kalıbı. Örnek: 'Kategoriye göre en çok satan 3 ürün'. Büyük/küçük harf duyarsızdır.
# Gruplar: group_hint (isteğe bağlı 'göre' kısmı), direction, metric_hint, n (sayı), dimension_hint.
TOP_N_PATTERN = re.compile(
    # Opsiyonel gruplama ifadesi, ör. 'kategoriye göre'.
    r"(?:(?P<group_hint>[\wçğıöşüÇĞİÖŞÜ]+)['’]?(?:e|a|ye|ya|nin|nın|nun|nün)\s+g[öo]re\s+)?"
    r"en\s+(?P<direction>" + _DIRECTION_ALT + r")\s+"
    # metric_hint en fazla 3 kelimelik ölçü adıdır (ör. 'toplam satış'). '?' işareti en kısa eşleşmeyi seçtirir.
    r"(?P<metric_hint>[\wçğıöşüÇĞİÖŞÜ]+(?:\s+[\wçğıöşüÇĞİÖŞÜ]+){0,2}?)\s*"
    r"(?P<n>\d+)\s+"
    r"(?P<dimension_hint>[\wçğıöşüÇĞİÖŞÜ]+)"
    # Sonda opsiyonel 'hangileri' / 'hangisi' ifadesi kabul edilir; yoksa da eşleşir.
    r"(?:\s+hangi(?:leri|si)?)?",
    re.IGNORECASE | re.UNICODE,
)


class TopNIntent:
    """Top-N soru niyetinin sonucu: yön (DESC/ASC), ölçü ipucu, sayı N, boyut ipucu, varsa gruplama ipucu ve ham metin."""
    __slots__ = ("direction", "metric_hint", "n", "dimension_hint", "group_hint", "raw_text")

    def __init__(self, direction, metric_hint, n, dimension_hint, group_hint, raw_text):
        """Niyet alanlarını verilen değerlerle atar."""
        self.direction = direction
        self.metric_hint = metric_hint
        self.n = n
        self.dimension_hint = dimension_hint
        self.group_hint = group_hint
        self.raw_text = raw_text

    def __repr__(self):
        """Hata ayıklama için okunabilir özet döner."""
        return (f"TopNIntent(direction={self.direction!r}, metric_hint={self.metric_hint!r}, "
                f"n={self.n}, dimension_hint={self.dimension_hint!r}, group_hint={self.group_hint!r})")


def detect_top_n(text: str):
    """Metni Top-N kalibina karsi test eder. Eslesme yoksa None doner."""
    if not text or not text.strip():
        return None

    # Kalıp metnin herhangi bir yerinde aranır (başta olmak zorunda değil).
    m = TOP_N_PATTERN.search(text.strip())
    if not m:
        return None

    # Yön kelimesi küçük harfe çevrilip sözlükte aranır.
    direction_word = m.group("direction").lower()
    direction = DIRECTION_MAP.get(direction_word)
    if direction is None:
        return None

    try:
        n = int(m.group("n"))
    except (TypeError, ValueError):
        return None

    # Sayı 1 ile 1000 arasında olmalı; üst sınır çok büyük sonuçları engeller.
    if n <= 0 or n > 1000:
        return None

    return TopNIntent(
        direction=direction,
        metric_hint=m.group("metric_hint").strip(),
        n=n,
        dimension_hint=m.group("dimension_hint").strip(),
        # Gruplama ifadesi yoksa group_hint None olur.
        group_hint=(m.group("group_hint").strip() if m.group("group_hint") else None),
        raw_text=text.strip(),
    )
