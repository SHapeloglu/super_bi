"""
SQLite bağlantı politikası (Faz 0.1 — dosya okuma açığı).

Kullanıcı tanımlı bir SQLite bağlantısı yalnızca şu koşullarda açılır:
  - DATALENS_SQLITE_ROOT tanımlı olmalı; tanımlı değilse SQLite bağlantıları kapalıdır.
  - İstenen yol (realpath ile çözülmüş, symlink dahil) bu kök dizin altında olmalı.
  - Uygulamanın kendi metadata DB'si (DATALENS_DB ya da superbi.db / datalens.db adları) olamaz.
  - Dosya var olmalı; oluşturulmaz.
  - Dosya salt okunur (mode=ro) açılır; yazma denemesi başarısız olur.

Bu modül bilinçli olarak yalnızca yol kararı verir; bağlantı kurmaz.
"""
from __future__ import annotations

import os
from urllib.parse import quote

_PROTECTED_NAMES = {"superbi.db", "datalens.db"}


class SQLitePolicyError(ValueError):
    """SQLite yolu politika tarafından reddedildi."""


def _sqlite_root() -> str | None:
    raw = os.environ.get("DATALENS_SQLITE_ROOT", "").strip()
    return os.path.realpath(raw) if raw else None


def _metadata_db() -> str | None:
    raw = os.environ.get("DATALENS_DB", "").strip()
    return os.path.realpath(raw) if raw else None


def resolve_sqlite_path(database: str | None) -> str:
    """Kullanıcının verdiği yolu politikaya göre doğrular ve gerçek (realpath) yolu döner."""
    root = _sqlite_root()
    if root is None:
        raise SQLitePolicyError("SQLite bağlantıları kapalı (DATALENS_SQLITE_ROOT tanımlı değil)")

    value = (database or "").strip()
    if not value or value == ":memory:":
        raise SQLitePolicyError("Geçersiz SQLite yolu")

    # join: value mutlak ise root'u yok sayar; sonra realpath symlink'leri de çözer.
    candidate = os.path.realpath(os.path.join(root, value))
    if candidate == root or not candidate.startswith(root + os.sep):
        raise SQLitePolicyError("SQLite yolu kök dizin dışında")

    if os.path.basename(candidate) in _PROTECTED_NAMES:
        raise SQLitePolicyError("Uygulama metadata veritabanı bağlantı olarak kullanılamaz")

    meta = _metadata_db()
    if meta is not None and candidate == meta:
        raise SQLitePolicyError("Uygulama metadata veritabanı bağlantı olarak kullanılamaz")

    if not os.path.isfile(candidate):
        raise SQLitePolicyError("SQLite dosyası bulunamadı")

    return candidate


def sqlite_url(database: str | None) -> str:
    """Politikadan geçen yol için salt okunur SQLAlchemy URL'si üretir."""
    path = resolve_sqlite_path(database)
    return "sqlite:///file:" + quote(path) + "?mode=ro&uri=true"
