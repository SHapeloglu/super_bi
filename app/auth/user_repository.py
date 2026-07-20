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

_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_LEN = 16


@dataclass
class User:
    user_id:       str
    username:      str
    password_hash: str
    role:          str
    created_at:    Optional[str] = None
    last_login:    Optional[str] = None


def _hash_password(password: str) -> str:
    salt = os.urandom(_SALT_LEN)
    derived = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32,
    )
    return f"{salt.hex()}${derived.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, derived_hex = stored_hash.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(derived_hex)
    derived = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32,
    )
    return hmac.compare_digest(derived, expected)


class UserRepository:
    def __init__(self, store: "SQLiteStore") -> None:
        self._s = store

    def create(self, username: str, password: str, role: str = "viewer") -> User:
        if self.get_by_username(username) is not None:
            raise ValueError(f"Kullanıcı adı zaten alınmış: {username}")

        user_id = str(uuid.uuid4())[:12]
        password_hash = _hash_password(password)
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        self._s.execute(
            "INSERT INTO users (user_id, username, password_hash, role, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, username, password_hash, role, now),
        )
        return User(user_id=user_id, username=username, password_hash=password_hash,
                    role=role, created_at=now)

    def get_by_username(self, username: str) -> Optional[User]:
        row = self._s.fetchone("SELECT * FROM users WHERE username=?", (username,))
        return self._row_to_user(row) if row else None

    def get_by_id(self, user_id: str) -> Optional[User]:
        row = self._s.fetchone("SELECT * FROM users WHERE user_id=?", (user_id,))
        return self._row_to_user(row) if row else None

    def authenticate(self, username: str, password: str) -> Optional[User]:
        user = self.get_by_username(username)
        if user is None or not _verify_password(password, user.password_hash):
            return None
        self._s.execute(
            "UPDATE users SET last_login=? WHERE user_id=?",
            (datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"), user.user_id),
        )
        return user

    def count(self) -> int:
        return self._s.table_row_count("users")

    @staticmethod
    def _row_to_user(row) -> User:
        return User(
            user_id=row["user_id"], username=row["username"],
            password_hash=row["password_hash"], role=row["role"],
            created_at=row["created_at"], last_login=row["last_login"],
        )
