"""
SQLiteStore
-----------
Tüm repository'lerin paylaştığı tek SQLite bağlantısı.

Tasarım kararları:
  - WAL modu: okuma/yazma çakışmasını önler
  - check_same_thread=False: FastAPI async worker'lar için
  - Şema migration: tablo yoksa oluştur, varsa dokunma
  - Şifreler asla burada saklanmaz — sadece metadata

Kullanım:
  store = SQLiteStore("/data/datalens.db")
  store.execute("INSERT INTO ...", {...})
  rows = store.fetchall("SELECT ...", {...})
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Tüm tablolar için DDL — migration basit: IF NOT EXISTS
SCHEMA_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Bağlantı metadata (şifresiz)
CREATE TABLE IF NOT EXISTS connections (
    conn_id      TEXT PRIMARY KEY,
    owner_id     TEXT NOT NULL DEFAULT 'anonymous',
    db_type      TEXT NOT NULL,
    host         TEXT NOT NULL DEFAULT '',
    database_    TEXT NOT NULL,
    user_        TEXT,
    schema_name  TEXT,
    name         TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at TEXT
);

-- Dashboard layout
CREATE TABLE IF NOT EXISTS dashboards (
    dashboard_id TEXT PRIMARY KEY,
    owner_id     TEXT NOT NULL DEFAULT 'anonymous',
    name         TEXT NOT NULL,
    scale        TEXT NOT NULL DEFAULT 'a4l',
    page_w_mm    REAL NOT NULL DEFAULT 297,
    page_h_mm    REAL NOT NULL DEFAULT 210,
    layout_json  TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Sorgu geçmişi + versiyonlama
CREATE TABLE IF NOT EXISTS query_history (
    id           TEXT PRIMARY KEY,
    fingerprint  TEXT NOT NULL,
    conn_id      TEXT NOT NULL,
    conn_name    TEXT NOT NULL DEFAULT '',
    base_table   TEXT NOT NULL,
    sql_text     TEXT NOT NULL,
    fields_json  TEXT NOT NULL DEFAULT '{}',
    joins_json   TEXT NOT NULL DEFAULT '[]',
    filters_json TEXT NOT NULL DEFAULT '[]',
    group_by_json TEXT NOT NULL DEFAULT '[]',
    sample       INTEGER NOT NULL DEFAULT 10,
    mode         TEXT NOT NULL DEFAULT 'memory',
    row_count    INTEGER,
    exec_ms      REAL,
    note         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Kullanıcılar (auth için hazırlandı)
CREATE TABLE IF NOT EXISTS users (
    user_id      TEXT PRIMARY KEY,
    username     TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT 'viewer',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_login   TEXT
);

-- Kayıtlı sorgular ("dataset") — widget'lar buna referansla bağlanır,
-- sorgu güncellenince ona bağlı TÜM widget'lar otomatik güncel veriyi görür.
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id   TEXT PRIMARY KEY,
    owner_id     TEXT NOT NULL DEFAULT 'anonymous',
    name         TEXT NOT NULL,
    conn_id      TEXT NOT NULL,
    base_table   TEXT NOT NULL,
    fields_json  TEXT NOT NULL DEFAULT '{}',
    joins_json   TEXT NOT NULL DEFAULT '[]',
    filters_json TEXT NOT NULL DEFAULT '[]',
    group_by_json TEXT NOT NULL DEFAULT '[]',
    order_by_json TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Sorgu geçmişinde hızlı gruplama için index
CREATE INDEX IF NOT EXISTS idx_qh_fingerprint ON query_history(fingerprint);
CREATE INDEX IF NOT EXISTS idx_qh_conn_id     ON query_history(conn_id);
CREATE INDEX IF NOT EXISTS idx_qh_created     ON query_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ds_owner       ON datasets(owner_id);
"""


class SQLiteStore:
    """
    Thread-safe SQLite wrapper.
    Tüm repository'ler bu store'u paylaşır.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock   = threading.Lock()
        self._conn   = self._connect()
        self._apply_schema()
        logger.info("SQLiteStore başlatıldı: %s", db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _apply_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA_DDL)
            self._conn.commit()
        logger.info("Şema uygulandı")
        # Mevcut DB'lerde owner_id kolonu yoksa ekle (migration)
        self.add_column_if_missing("connections", "owner_id", "TEXT NOT NULL DEFAULT 'anonymous'")
        self.add_column_if_missing("dashboards",  "owner_id", "TEXT NOT NULL DEFAULT 'anonymous'")
        self.add_column_if_missing("connections", "port_", "INTEGER")
        self.add_column_if_missing("connections", "password_enc", "TEXT")

    # ------------------------------------------------------------------
    # Temel operasyonlar
    # ------------------------------------------------------------------

    def execute(self, sql: str, params: dict | tuple = ()) -> sqlite3.Cursor:
        """INSERT / UPDATE / DELETE — lock altında çalışır."""
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def executemany(self, sql: str, params_list: list) -> None:
        with self._lock:
            self._conn.executemany(sql, params_list)
            self._conn.commit()

    def fetchone(self, sql: str, params: dict | tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: dict | tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Migration yardımcısı — ileride kolon eklemek için
    # ------------------------------------------------------------------

    def add_column_if_missing(self, table: str, column: str, definition: str) -> None:
        existing = [r[1] for r in self.fetchall(f"PRAGMA table_info({table})")]
        if column not in existing:
            self.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            logger.info("Kolon eklendi: %s.%s", table, column)

    def table_row_count(self, table: str) -> int:
        row = self.fetchone(f"SELECT COUNT(*) as n FROM {table}")
        return row["n"] if row else 0
