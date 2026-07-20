"""
crypto.py — bağlantı şifrelerini diskte şifreli tutmak için

NEDEN GEREKLİ: Servis her yeniden başladığında (systemctl restart), RAM'de
tutulan SQLAlchemy engine'leri (ve onların içindeki düz metin şifreleri)
kaybolur. SQLite için sorun değil (şifre gerekmiyor), ama PostgreSQL/MySQL/
MSSQL bağlantıları restart sonrası "yeniden bağlanın" hatası veriyordu —
kullanıcı şifreyi HER restart'ta elle tekrar girmek zorunda kalıyordu.

ÇÖZÜM: Şifre, Fernet (AES128-CBC + HMAC, simetrik şifreleme) ile şifrelenip
`connections.password_enc` kolonunda saklanır. Şifreleme anahtarı VERİTABANINDA
DEĞİL, ayrı bir ortam değişkeninde (DATALENS_DB_ENCRYPTION_KEY) tutulur — yani
biri sadece veritabanı dosyasını çalarsa şifreleri çözemez, sistemd servis
dosyasına (ya da .env'e) da erişmesi gerekir. Bu "encryption at rest" için
standart, makul bir yaklaşımdır (tam bir secrets vault kadar güçlü değildir,
ama tek-VPS'lik bir kurulum için doğru denge).

DİKKAT: DATALENS_DB_ENCRYPTION_KEY ortam değişkenini MUTLAKA sabit bir
değere ayarlayın (aşağıdaki gibi üretip .service dosyasına ekleyin).
Ayarlanmazsa süreç her başlatıldığında rastgele bir anahtar üretilir —
bu, restart sonrası önceden şifrelenmiş TÜM şifrelerin çözülemez hale
geleceği (yani JWT secret ile aynı sınıfta bir sorun) anlamına gelir.
Anahtar üretmek için: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    key = os.environ.get("DATALENS_DB_ENCRYPTION_KEY")
    if not key:
        # Sabit bir anahtar verilmemişse süreç ömrü boyunca geçerli rastgele
        # bir anahtar üretilir — restart'ta önceki şifreler çözülemez olur.
        # Bu, prod için MUTLAKA env değişkeniyle sabitlenmesi gereken bir
        # durumdur; burada çökme yerine geçici bir anahtarla devam ediyoruz
        # ki geliştirme ortamında sürtünme yaratmasın.
        key = Fernet.generate_key().decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_password(plaintext: str | None) -> str | None:
    """None güvenle None döner (sqlite gibi şifresiz bağlantılar için)."""
    if not plaintext:
        return None
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_password(ciphertext: str | None) -> str | None:
    """
    Çözülemezse (anahtar değişmiş, veri bozuk vb.) None döner — exception
    fırlatmaz, çünkü çağıran taraf zaten "engine kurulamadı" yoluna düşecek
    ve kullanıcıya net bir "yeniden bağlanın" mesajı gösterecek.
    """
    if not ciphertext:
        return None
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError, Exception):
        return None
