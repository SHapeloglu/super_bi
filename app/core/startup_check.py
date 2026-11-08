"""
Açılış ön kontrolü (Faz 0.6 — varsayılan sırların kabul edilmesi).

Zorunlu ortam değişkenleri tanımlı ve boş olmayan değerli değilse uygulama açılmaz.
Rastgele geçici sır üretilmez: restart'ta oturumlar ve kayıtlı bağlantı parolaları kaybolur.

Hata mesajı yalnızca değişken ADLARINI içerir; değerleri asla yazdırmaz.
"""
from __future__ import annotations

import os

ZORUNLU_DEGISKENLER = (
    "DATALENS_JWT_SECRET",
    "DATALENS_DB_ENCRYPTION_KEY",
    "DATALENS_DB",
)


def check_required_env() -> None:
    """Eksik ya da boş zorunlu değişken varsa RuntimeError fırlatır."""
    eksikler = [ad for ad in ZORUNLU_DEGISKENLER if not os.environ.get(ad, "").strip()]
    if eksikler:
        raise RuntimeError(
            "Zorunlu ortam değişkenleri tanımlı değil: " + ", ".join(eksikler)
        )
