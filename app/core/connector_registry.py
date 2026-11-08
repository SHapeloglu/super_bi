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

# DİKKAT: Python'da $ sondaki yeni satırı da kabul eder; 'ad\n' gibi bir değer geçebilir. fullmatch daha sıkı olurdu.
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
# Her satır: DB tipi -> import edilecek modül, pip paket adı ve SQLAlchemy URL öneki. Yeni bir DB eklemek için buraya satır eklenir.
DRIVER_MAP: dict[str, dict[str, str]] = {
    "sqlite":     {"module": "sqlite3",   "package": "",                "dialect": "sqlite"},
    "postgresql": {"module": "psycopg2",  "package": "psycopg2-binary", "dialect": "postgresql+psycopg2"},
    "mysql":      {"module": "pymysql",   "package": "PyMySQL",         "dialect": "mysql+pymysql"},
    "mssql":      {"module": "pyodbc",    "package": "pyodbc",          "dialect": "mssql+pyodbc"},
    "oracle":     {"module": "oracledb",  "package": "oracledb",        "dialect": "oracle+oracledb"},
}


class ConnectorRegistry:
    """
    Canlı SQLAlchemy engine'lerini tutar (conn_id -> Engine).
    Şifreler burada sadece RAM'de, engine connection string'i içinde durur —
    hiçbir zaman diske/DB'ye yazılmaz (ConnectionRepository sadece metadata tutar).
    """

    def __init__(self) -> None:
        """Boş engine sözlüğü ve bir kilit oluşturur. sqlite her zaman kurulu kabul edilir (Python ile birlikte gelir)."""
        self._engines: dict[str, Engine] = {}
        self._lock = threading.Lock()
        # sqlite her zaman stdlib ile gelir, kurulum gerektirmez
        self._installed: set[str] = {"sqlite"}

    # ------------------------------------------------------------------
    # Lazy driver installation
    # ------------------------------------------------------------------

    def driver_installed(self, db_type: str) -> bool:
        """Veritabanı sürücüsü (ör. psycopg2) import edilebiliyor mu diye bakar. Bulunursa önbelleğe alınır. Bilinmeyen db_type için False döner."""
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
            # Paket adı ayrı argüman olarak verilir ve kabuk (shell) kullanılmaz. DİKKAT: --break-system-packages sistem Python'una doğrudan kurar; diğer paketleri etkileyebilir.
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--break-system-packages", package],
                capture_output=True, text=True, timeout=120,
            )
        except Exception as e:  # subprocess başlatılamadı
            return False, f"Kurulum başlatılamadı: {e}"

        if result.returncode != 0:
            # Hata çıktısının son 500 karakteri loga yazılır (uzun çıktıyı kırpmak için).
            logger.error("Driver kurulumu başarısız (%s): %s", db_type, result.stderr[-500:])
            # Kullanıcıya gösterilen mesajda daha kısa, son 300 karakter kullanılır.
            return False, f"Kurulum başarısız: {result.stderr[-300:]}"

        # Yeni kurulan paketin bulunabilmesi için import önbelleği temizlenir.
        importlib.invalidate_caches()
        if self.driver_installed(db_type):
            return True, f"{db_type} sürücüsü kuruldu"
        return False, "Kurulum tamamlandı ama modül hâlâ import edilemiyor"

    def list_drivers(self) -> list[dict]:
        """Desteklenen tüm veritabanı tiplerini ve her birinin kurulu olup olmadığını listeler."""
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
        # pool_pre_ping: her kullanımdan önce kısa bir test yapar (kopmuş bağlantıyı yakalar). pool_recycle=1800: bağlantılar 30 dk (1800 sn) sonra yenilenir; sunucunun zaman aşımına takılmayı önler.
        engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800)

        with self._lock:
            # Aynı conn_id için eski bir engine varsa kapatılır; bağlantı bilgileri değişmiş olabilir.
            old = self._engines.pop(conn_id, None)
            if old is not None:
                old.dispose()
            self._engines[conn_id] = engine
        return engine

    def _build_url(self, db_type: str, params: dict) -> str:
        """
        db_type ve bağlantı bilgilerinden SQLAlchemy bağlantı adresi (URL) üretir.
        Şifre bu adresin içine girer; bu yüzden adres loglanmamalıdır.
        """
        dialect = DRIVER_MAP[db_type]["dialect"]

        if db_type == "sqlite":
            # Faz 0.1: yol keyfi değil. Kök dizin (DATALENS_SQLITE_ROOT) altında, var olan,
            # metadata DB olmayan ve salt okunur açılan dosyalar kabul edilir (bkz. sqlite_policy).
            from app.core.sqlite_policy import sqlite_url
            return sqlite_url(params.get("database"))

        # Eksik değerler için varsayılanlar: kullanıcı ve şifre boş, host localhost.
        user     = params.get("user") or ""
        password = params.get("password") or ""
        host     = params.get("host") or "localhost"
        port     = params.get("port")
        database = params.get("database") or ""

        from urllib.parse import quote_plus
        # Kullanıcı adı ve şifre URL'de sorun çıkarmasın diye kodlanır (ör. '@' veya '/' karakterleri).
        auth = f"{quote_plus(user)}:{quote_plus(password)}@" if user else ""
        port_part = f":{port}" if port else ""
        # Oracle için bağlantı 'service_name' ile kurulur (SID değil).
        if db_type == "oracle":
            import oracledb
            from urllib.parse import quote_plus as qp
            return f"oracle+oracledb://{auth}{host}{port_part}/?service_name={database}"
        if db_type == "mssql":
            from urllib.parse import quote_plus as qp
            # ODBC sürücü adı URL'ye kodlanır. TrustServerCertificate=yes sunucu sertifika kontrolünü kapatır; test ortamında kolaylık sağlar, üretimde risklidir.
            driver = qp("ODBC Driver 18 for SQL Server")
            return f"{dialect}://{auth}{host}{port_part}/{database}?driver={driver}&TrustServerCertificate=yes"
        # DİKKAT: host ve database adı URL'ye kodlanmadan eklenir; bu değerlerde '/', '?' veya '@' varsa adres bozulabilir.
        return f"{dialect}://{auth}{host}{port_part}/{database}"

    def remove_engine(self, conn_id: str) -> None:
        """conn_id'nin engine'ini kayıt defterinden çıkarır ve bağlantı havuzunu kapatır (dispose)."""
        with self._lock:
            engine = self._engines.pop(conn_id, None)
        if engine is not None:
            engine.dispose()

    def dispose_all(self) -> None:
        """Tüm engine'leri kapatır ve kayıt defterini boşaltır. Uygulama kapanırken çağrılır."""
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
        """
        Verilen engine ile basit bir sorgu (SELECT 1) çalıştırır.
        Başarılıysa (True, 'Bağlantı başarılı'), hata varsa (False, hata metni) döner.
        """
        try:
            with engine.connect() as conn:
                # Önce SELECT 1 denenir; desteklenmezse (ör. Oracle) SELECT 1 FROM DUAL denenir.
                try:
                    conn.execute(text("SELECT 1"))
                except Exception:
                    conn.execute(text("SELECT 1 FROM DUAL"))
            return True, "Bağlantı başarılı"
        except Exception as e:
            return False, str(e)
