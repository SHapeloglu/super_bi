"""
user_repository.py
-------------------
YENİDEN OLUŞTURULDU: deps.py içinde `from app.auth.user_repository import
UserRepository` referansı var ama dosya bulunamadığı için buradan yeniden
yazıldı. users tablosu zaten sqlite_store.py'nin SCHEMA_DDL'inde tanımlı.

Şifre hash'leme: stdlib hashlib.scrypt kullanılır (ek bağımlılık gerekmez,
bcrypt kadar yaygın kabul görmüş, CPU+RAM maliyetli, brute-force'a dayanıklı).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)

# scrypt ayarları: N (2^14) CPU ve bellek maliyetini belirler. Daha büyük değer daha güvenli ama daha yavaştır.
# DİKKAT: Bu değerler hash içinde saklanmaz; değiştirilirse mevcut hash'ler doğrulanamaz hale gelir.
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
# Tuz (salt): 16 bayt rastgele veri. Her kullanıcının şifresi farklı tuzla hash'lenir.
_SALT_LEN = 16


@dataclass
class User:
    """
    Kullanıcı kaydı (users tablosundaki bir satır). password_hash düz şifre değil, hash'lenmiş metindir.
    role: 'admin' ya da 'viewer' gibi yetki seviyesi.
    """
    user_id:       str
    username:      str
    password_hash: str
    role:          str
    created_at:    Optional[str] = None
    last_login:    Optional[str] = None


def _hash_password(password: str) -> str:
    """
    Şifreyi scrypt algoritmasıyla hash'ler. Sonuç 'tuz$hash' biçiminde bir metindir.
    Her çağrıda yeni rastgele tuz üretilir; aynı şifre farklı hash verir.
    """
    # İşletim sisteminin kriptografik rastgele kaynağından tuz üretilir.
    salt = os.urandom(_SALT_LEN)
    derived = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32,
    )
    # Tuz ve hash '$' işaretiyle ayrılıp tek metin olarak saklanır; doğrulamada tuz buradan okunur.
    return f"{salt.hex()}${derived.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    """Düz şifreyi kayıtlı hash ile karşılaştırır. Eşleşirse True, değilse False döner. Hash biçimi bozuksa False döner."""
    try:
        salt_hex, derived_hex = stored_hash.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(derived_hex)
    derived = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32,
    )
    # Sabit zamanlı karşılaştırma: sonucun ne kadar sürdüğünden şifre hakkında ipucu çıkarılamaz (zamanlama saldırısına karşı).
    return hmac.compare_digest(derived, expected)


class UserRepository:
    """Kullanıcı işlemleri (oluşturma, arama, giriş doğrulama) için repository sınıfı."""
    def __init__(self, store: "SQLiteStore") -> None:
        """store: SQL çalıştırmayı sağlayan SQLiteStore nesnesi."""
        self._s = store

    def create(self, username: str, password: str, role: str | None = None) -> User:
        """
        Yeni kullanıcı oluşturur. Kullanıcı adı zaten varsa ValueError fırlatır.
        role None ise rol, kaydın eklendiği SQL içinde belirlenir: users tablosu boşsa 'admin', değilse 'viewer'.
        role verilmişse o rol aynen kullanılır. Dönüş değeri veritabanından tekrar okunan User nesnesidir.
        """
        # DİKKAT: Kullanıcı adı büyük/küçük harfe duyarlıdır ('Ali' ve 'ali' ayrı kullanıcı olur); tablodaki UNIQUE kısıtı da böyle çalışır.
        if self.get_by_username(username) is not None:
            raise ValueError(f"Kullanıcı adı zaten alınmış: {username}")

        # DİKKAT: UUID'nin yalnız ilk 12 karakteri alınır. Çakışma olasılığı çok düşüktür ama sıfır değildir.
        user_id = str(uuid.uuid4())[:12]
        password_hash = _hash_password(password)
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        if role is None:
            # Rol için ayrı bir "sayım" adımı yok; sayım ile kayıt aynı INSERT içinde olduğu için
            # iki eşzamanlı ilk kayıt da admin olamaz. Tablo boşsa ilk kullanıcı admin olur.
            self._s.execute(
                "INSERT INTO users (user_id, username, password_hash, role, created_at) "
                "VALUES (?, ?, ?, CASE WHEN (SELECT COUNT(*) FROM users) = 0 THEN 'admin' ELSE 'viewer' END, ?)",
                (user_id, username, password_hash, now),
            )
        else:
            # Rol açıkça verildiyse eski davranış: verilen rol doğrudan yazılır.
            self._s.execute(
                "INSERT INTO users (user_id, username, password_hash, role, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, username, password_hash, role, now),
            )

        # Rolü veritabanından geri okuyoruz; böylece dönen nesne kayıttaki gerçek rolü gösterir.
        created = self.get_by_id(user_id)
        if created is None:
            # Az önce eklenen satır okunamadıysa bir şey çok yanlış demektir; sessizce None dönmek yerine hata veriyoruz.
            raise RuntimeError(f"Kullanıcı eklendi ama okunamadı: {user_id}")
        return created

    def get_by_username(self, username: str) -> Optional[User]:
        """Kullanıcı adına göre kullanıcıyı getirir. Bulunamazsa None döner."""
        row = self._s.fetchone("SELECT * FROM users WHERE username=?", (username,))
        return self._row_to_user(row) if row else None

    def get_by_id(self, user_id: str) -> Optional[User]:
        """Kullanıcı kimliğine (user_id) göre kullanıcıyı getirir. Bulunamazsa None döner."""
        row = self._s.fetchone("SELECT * FROM users WHERE user_id=?", (user_id,))
        return self._row_to_user(row) if row else None

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """
        Kullanıcı adı ve şifreyi doğrular. Doğruysa kullanıcıyı döner ve son giriş zamanını günceller; değilse None döner.
        Kullanıcı yok ile şifre yanlış aynı cevabı verir (kullanıcı adı taraması zorlaşır).
        """
        user = self.get_by_username(username)
        # Kullanıcı yoksa ya da şifre yanlışsa None döner; hata nedeni dışarı sızdırılmaz.
        if user is None or not _verify_password(password, user.password_hash):
            return None
        self._s.execute(
            "UPDATE users SET last_login=? WHERE user_id=?",
            (datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"), user.user_id),
        )
        return user

    def count(self) -> int:
        """Sistemdeki toplam kullanıcı sayısını döner."""
        return self._s.table_row_count("users")

    @staticmethod
    def _row_to_user(row) -> User:
        """Veritabanı satırını User nesnesine çevirir."""
        return User(
            user_id=row["user_id"], username=row["username"],
            password_hash=row["password_hash"], role=row["role"],
            created_at=row["created_at"], last_login=row["last_login"],
        )
