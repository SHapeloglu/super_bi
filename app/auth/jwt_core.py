"""
jwt_core.py
-----------
YENİDEN OLUŞTURULDU: deps.py içinde `from app.auth.jwt_core import parse_token`
referansı var ama dosya bulunamadığı için buradan yeniden yazıldı.

DİKKAT: DATALENS_JWT_SECRET ortam değişkenini prod'da MUTLAKA ayarlayın.
Ayarlanmazsa süreç her başlatıldığında rastgele bir secret üretilir —
bu, restart sonrası TÜM eski token'ların geçersiz olacağı (kullanıcıların
tekrar login olması gerekeceği) anlamına gelir. Geliştirme için sorun değil,
prod'da mutlaka sabit ve gizli bir değer olmalı.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

# Token imzalama anahtarı. Ortam değişkeni yoksa her süreçte rastgele üretilir (üstteki DİKKAT notuna bakın).
_SECRET = os.environ.get("DATALENS_JWT_SECRET") or secrets.token_hex(32)
_ALGORITHM = "HS256"
_EXPIRE_MINUTES = int(os.environ.get("DATALENS_JWT_EXPIRE_MINUTES", "480"))  # 8 saat


@dataclass
class TokenData:
    """Token'dan çözülen kullanıcı bilgisi: kimlik (user_id), kullanıcı adı ve rol. Yetki kontrollerinde bu nesne kullanılır."""
    user_id:  str
    username: str
    role:     str


def create_token(user_id: str, username: str, role: str) -> str:
    """Kullanıcı bilgileriyle imzalı bir JWT token üretir. Süresi DATALENS_JWT_EXPIRE_MINUTES ile belirlenir (varsayılan 480 dk = 8 saat)."""
    # Token zamanları UTC olarak yazılır. iat: oluşturulma, exp: bitiş zamanı.
    now = datetime.now(timezone.utc)
    payload = {
        "sub":      user_id,
        "username": username,
        "role":     role,
        "iat":      now,
        "exp":      now + timedelta(minutes=_EXPIRE_MINUTES),
    }
    # HS256 simetrik imza: aynı anahtar hem imzalamak hem doğrulamak için kullanılır.
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def parse_token(token: str) -> TokenData:
    """
    Token'ı doğrular ve içindeki kullanıcı bilgisini TokenData olarak döner.
    Süresi dolmuşsa, bozuksa ya da gerekli alanları yoksa ValueError fırlatır.
    """
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    # Süresi dolmuş ve bozuk token'lar ValueError'a çevrilir; deps.py bunu 401 cevabına dönüştürür.
    except jwt.ExpiredSignatureError:
        raise ValueError("Token süresi doldu, yeniden giriş yapın")
    except jwt.InvalidTokenError:
        raise ValueError("Geçersiz token")

    user_id  = payload.get("sub")
    username = payload.get("username")
    role     = payload.get("role")
    # Kullanıcı kimliği (sub) veya rol yoksa token kabul edilmez.
    if not user_id or not role:
        raise ValueError("Token içeriği eksik")

    return TokenData(user_id=user_id, username=username or "", role=role)
