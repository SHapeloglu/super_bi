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
# Uygulama açılışında çalışan tüm tablo tanımları. IF NOT EXISTS sayesinde tekrar çalışması güvenlidir; var olan tabloyu silmez.
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

-- Tablo profilleri: grain tespiti + sütun sınıflandırma sonuçları
CREATE TABLE IF NOT EXISTS table_profiles (
    profile_id    TEXT PRIMARY KEY,
    conn_id       TEXT NOT NULL,
    table_name    TEXT NOT NULL,
    row_count     INTEGER,
    grain_columns TEXT NOT NULL DEFAULT '[]',
    columns_json  TEXT NOT NULL DEFAULT '[]',
    analyzed_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(conn_id, table_name)
);
-- Tablolar arası ilişki adayları: PK/FK metadata (verified=1) veya
-- istatistiksel orphan testi (verified=0, confidence skoru ile) sonucu
CREATE TABLE IF NOT EXISTS datasets_relationships (
    rel_id        TEXT PRIMARY KEY,
    conn_id       TEXT NOT NULL,
    table_a       TEXT NOT NULL,
    column_a      TEXT NOT NULL,
    table_b       TEXT NOT NULL,
    column_b      TEXT NOT NULL,
    cardinality   TEXT NOT NULL DEFAULT 'unknown',
    source        TEXT NOT NULL DEFAULT 'inferred',
    orphan_count  INTEGER,
    orphan_ratio  REAL,
    confidence    REAL NOT NULL DEFAULT 0,
    verified      INTEGER NOT NULL DEFAULT 0,
    analyzed_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(conn_id, table_a, column_a, table_b, column_b)
);
-- Sorgu geçmişinde hızlı gruplama için index
CREATE INDEX IF NOT EXISTS idx_qh_fingerprint ON query_history(fingerprint);
CREATE INDEX IF NOT EXISTS idx_qh_conn_id     ON query_history(conn_id);
CREATE INDEX IF NOT EXISTS idx_qh_created     ON query_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ds_owner       ON datasets(owner_id);
-- Faz 1.2: dataset / dashboard paylaşımları (alıcı kullanıcı ya da rol; izin read / write)
CREATE TABLE IF NOT EXISTS shares (
    share_id      TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,
    resource_id   TEXT NOT NULL,
    grantee_type  TEXT NOT NULL,
    grantee_id    TEXT NOT NULL,
    permission    TEXT NOT NULL,
    created_by    TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    UNIQUE(resource_type, resource_id, grantee_type, grantee_id)
);
CREATE INDEX IF NOT EXISTS idx_shares_grantee ON shares(grantee_type, grantee_id);
"""


class SQLiteStore:
    """
    Thread-safe SQLite wrapper.
    Tüm repository'ler bu store'u paylaşır.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        """
        Veritabanı dosyasını açar, bağlantıyı kurar ve tabloları oluşturur.
        db_path: dosya yolu. Varsayılan ':memory:' geçici bellek veritabanıdır; program kapanınca silinir.
        """
        self.db_path = db_path
        # Kilit: tek SQLite bağlantısı birden çok thread tarafından aynı anda kullanılmasın diye.
        self._lock   = threading.Lock()
        self._conn   = self._connect()
        self._apply_schema()
        logger.info("SQLiteStore başlatıldı: %s", db_path)

    def _connect(self) -> sqlite3.Connection:
        """SQLite bağlantısı açar. Satırlar sözlük gibi (row['kolon']) okunabilsin diye row_factory ayarlanır."""
        # check_same_thread=False: bağlantı başka bir thread'den de kullanılabilir. Güvenliği yukarıdaki kilit sağlar.
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            # Kolon tipi bildirimine göre değerlerin Python tipine çevrilmesini açar.
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _apply_schema(self) -> None:
        """SCHEMA_DDL içindeki tabloları oluşturur, sonra eski kurulumlarda eksik kalmış kolonları ekler (migration)."""
        with self._lock:
            # executescript birden çok komutu birlikte çalıştırır; kendi commit'ini yapar.
            self._conn.executescript(SCHEMA_DDL)
            self._conn.commit()
        logger.info("Şema uygulandı")
        # Mevcut DB'lerde owner_id kolonu yoksa ekle (migration)
        self.add_column_if_missing("connections", "owner_id", "TEXT NOT NULL DEFAULT 'anonymous'")
        self.add_column_if_missing("dashboards",  "owner_id", "TEXT NOT NULL DEFAULT 'anonymous'")
        # Eski kurulumlarda bu kolonlar yoktur; yoksa eklenir (migration).
        self.add_column_if_missing("connections", "port_", "INTEGER")
        self.add_column_if_missing("connections", "password_enc", "TEXT")

    # ------------------------------------------------------------------
    # Temel operasyonlar
    # ------------------------------------------------------------------

    def execute(self, sql: str, params: dict | tuple = ()) -> sqlite3.Cursor:
        """INSERT / UPDATE / DELETE — lock altında çalışır."""
        with self._lock:
            # Dönen cursor (ör. etkilenen satır sayısı için) kilit kaldırıldıktan sonra da kullanılabilir.
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def executemany(self, sql: str, params_list: list) -> None:
        """Aynı SQL'i birden çok parametre satırı ile çalıştırır (toplu ekleme). Kilit altında çalışır ve commit eder."""
        with self._lock:
            self._conn.executemany(sql, params_list)
            self._conn.commit()

    def fetchone(self, sql: str, params: dict | tuple = ()) -> sqlite3.Row | None:
        """SELECT sorgusunun ilk satırını döner. Sonuç yoksa None döner. Kilit altında çalışır."""
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: dict | tuple = ()) -> list[sqlite3.Row]:
        """SELECT sorgusunun tüm satırlarını liste olarak döner. Kilit altında çalışır."""
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        """Veritabanı bağlantısını kapatır. Kapatıldıktan sonra bu store ile sorgu yapılamaz."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Migration yardımcısı — ileride kolon eklemek için
    # ------------------------------------------------------------------

    def add_column_if_missing(self, table: str, column: str, definition: str) -> None:
        """
        Tabloda kolon yoksa ALTER TABLE ile ekler; varsa hiçbir şey yapmaz.
        Eski veritabanı dosyaları bozulmadan yeni kolon eklemek için kullanılır.
        """
        # PRAGMA table_info her kolon için satır döner; r[1] kolon adıdır.
        existing = [r[1] for r in self.fetchall(f"PRAGMA table_info({table})")]
        if column not in existing:
            self.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            logger.info("Kolon eklendi: %s.%s", table, column)

    def table_row_count(self, table: str) -> int:
        """
        Tablodaki toplam satır sayısını döner.
        DİKKAT: Tablo adı SQL'e doğrudan yazılır; sadece kodda sabit verilen tablo adlarıyla çağrılmalı.
        """
        # DİKKAT: Tablo adı f-string ile yazılıyor (parametre olarak geçilemez). Dış girdi ile çağrılmamalı.
        row = self.fetchone(f"SELECT COUNT(*) as n FROM {table}")
        return row["n"] if row else 0
