"""
connector_registry.py
----------------------
YENİDEN OLUŞTURULDU: Bu dosya orijinal projede vardı ama diskten silindi.
deps.py / connections.py / query.py / sql_builder.py içindeki kullanım
şekillerine (registry.get_engine(...), registry._engines, registry.
driver_installed(...), registry.test_connection(...), registry.
remove_engine(...), quote_identifier(...)) bakılarak yeniden yazıldı.

Düzeltilen bug (docstring'de referans verilen):
  BUG-3  quote_identifier: nokta ayrıştırma, regex whitelist
"""
from __future__ import annotations

import importlib
import logging
import re
import subprocess
import sys
import threading
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BUG-3: quote_identifier — nokta ayrıştırma + regex whitelist
# ---------------------------------------------------------------------------

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_identifier(identifier: str) -> str:
    """
    Tablo/kolon adını güvenli şekilde çift tırnaklar.
    'tablo.kolon' gibi noktalı girişleri parçalara ayırıp HER PARÇAYI
    ayrı ayrı whitelist'ten geçirir, sonra ayrı ayrı tırnaklayıp birleştirir.
    Böylece 'tablo"."zararlı; DROP TABLE x --' gibi girişler tek parça
    olarak regex'e takılır ve reddedilir.
    """
    if not identifier or not isinstance(identifier, str):
        raise ValueError(f"Geçersiz identifier: {identifier!r}")

    parts = identifier.split(".")
    if len(parts) > 2:
        raise ValueError(f"Identifier en fazla 1 nokta içerebilir: {identifier!r}")

    for part in parts:
        if not _IDENT_RE.match(part):
            raise ValueError(f"İzin verilmeyen identifier: {identifier!r}")

    return ".".join(f'"{p}"' for p in parts)


# ---------------------------------------------------------------------------
# Lazy driver kurulumu — DB tipine göre pip paketi
# ---------------------------------------------------------------------------

# db_type -> (import edilecek modül adı, pip paket adı, SQLAlchemy dialect prefix'i)
DRIVER_MAP: dict[str, dict[str, str]] = {
    "sqlite":     {"module": "sqlite3",   "package": "",                "dialect": "sqlite"},
    "postgresql": {"module": "psycopg2",  "package": "psycopg2-binary", "dialect": "postgresql+psycopg2"},
    "mysql":      {"module": "pymysql",   "package": "PyMySQL",         "dialect": "mysql+pymysql"},
    "mssql":      {"module": "pyodbc",    "package": "pyodbc",          "dialect": "mssql+pyodbc"},
}


class ConnectorRegistry:
    """
    Canlı SQLAlchemy engine'lerini tutar (conn_id -> Engine).
    Şifreler burada sadece RAM'de, engine connection string'i içinde durur —
    hiçbir zaman diske/DB'ye yazılmaz (ConnectionRepository sadece metadata tutar).
    """

    def __init__(self) -> None:
        self._engines: dict[str, Engine] = {}
        self._lock = threading.Lock()
        # sqlite her zaman stdlib ile gelir, kurulum gerektirmez
        self._installed: set[str] = {"sqlite"}

    # ------------------------------------------------------------------
    # Lazy driver installation
    # ------------------------------------------------------------------

    def driver_installed(self, db_type: str) -> bool:
        if db_type not in DRIVER_MAP:
            return False
        if db_type in self._installed:
            return True
        module_name = DRIVER_MAP[db_type]["module"]
        try:
            importlib.import_module(module_name)
            self._installed.add(db_type)
            return True
        except ImportError:
            return False

    def install_driver(self, db_type: str) -> tuple[bool, str]:
        """pip ile eksik sürücüyü kurmayı dener. (başarı, mesaj) döner."""
        if db_type not in DRIVER_MAP:
            return False, f"Bilinmeyen db_type: {db_type!r}"
        if self.driver_installed(db_type):
            return True, f"{db_type} zaten kurulu"

        package = DRIVER_MAP[db_type]["package"]
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--break-system-packages", package],
                capture_output=True, text=True, timeout=120,
            )
        except Exception as e:  # subprocess başlatılamadı
            return False, f"Kurulum başlatılamadı: {e}"

        if result.returncode != 0:
            logger.error("Driver kurulumu başarısız (%s): %s", db_type, result.stderr[-500:])
            return False, f"Kurulum başarısız: {result.stderr[-300:]}"

        importlib.invalidate_caches()
        if self.driver_installed(db_type):
            return True, f"{db_type} sürücüsü kuruldu"
        return False, "Kurulum tamamlandı ama modül hâlâ import edilemiyor"

    def list_drivers(self) -> list[dict]:
        return [
            {"db_type": dt, "installed": self.driver_installed(dt)}
            for dt in DRIVER_MAP
        ]

    # ------------------------------------------------------------------
    # Engine yaşam döngüsü
    # ------------------------------------------------------------------

    def get_engine(self, conn_id: str, db_type: str, params: dict) -> Engine:
        """Yeni bir SQLAlchemy engine oluşturur, kaydeder ve döner."""
        if db_type not in DRIVER_MAP:
            raise ValueError(f"Desteklenmeyen db_type: {db_type!r}")

        url = self._build_url(db_type, params)
        engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800)

        with self._lock:
            old = self._engines.pop(conn_id, None)
            if old is not None:
                old.dispose()
            self._engines[conn_id] = engine
        return engine

    def _build_url(self, db_type: str, params: dict) -> str:
        dialect = DRIVER_MAP[db_type]["dialect"]

        if db_type == "sqlite":
            # database alanı dosya yolu olarak kullanılır (":memory:" da geçerli)
            return f"sqlite:///{params.get('database', ':memory:')}"

        user     = params.get("user") or ""
        password = params.get("password") or ""
        host     = params.get("host") or "localhost"
        port     = params.get("port")
        database = params.get("database") or ""

        from urllib.parse import quote_plus
        auth = f"{quote_plus(user)}:{quote_plus(password)}@" if user else ""
        port_part = f":{port}" if port else ""
        return f"{dialect}://{auth}{host}{port_part}/{database}"

    def remove_engine(self, conn_id: str) -> None:
        with self._lock:
            engine = self._engines.pop(conn_id, None)
        if engine is not None:
            engine.dispose()

    def dispose_all(self) -> None:
        with self._lock:
            engines = list(self._engines.values())
            self._engines.clear()
        for e in engines:
            e.dispose()

    def get_active_engine(self, conn_id: str) -> Optional[Engine]:
        """Zaten oluşturulmuş bir engine'i döner — yenisini oluşturmaz."""
        return self._engines.get(conn_id)

    # ------------------------------------------------------------------
    # Test
    # ------------------------------------------------------------------

    def test_connection(self, engine: Engine) -> tuple[bool, str]:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True, "Bağlantı başarılı"
        except Exception as e:
            return False, str(e)
