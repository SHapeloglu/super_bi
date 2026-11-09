"""
Repository katmanı
------------------
Her repository aynı SQLiteStore'u kullanır.
Endpoint'ler storage detayını görmez — sadece CRUD metodlarını çağırır.

ConnectionRepository  : bağlantı metadata (şifresiz)
DashboardRepository   : dashboard layout + obje listesi
QueryHistoryRepository: sorgu geçmişi + versiyonlama
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Veri modelleri (dataclass — Pydantic bağımlılığı yok)
# ---------------------------------------------------------------------------

@dataclass
class ConnectionMeta:
    """
    Bir veritabanı bağlantısının bilgileri (sunucu, veritabanı adı, kullanıcı vb.).
    Şifre düz metin olarak tutulmaz; password_enc alanı şifrelenmiş halini taşır.
    owner_id bağlantının sahibidir; varsayılan 'anonymous'.
    """
    conn_id:     str
    db_type:     str
    host:        str
    database:    str
    owner_id:    str = "anonymous"
    port:        Optional[int] = None
    user:        Optional[str] = None
    # Şifre burada düz metin değil, şifrelenmiş hali olarak tutulur.
    password_enc: Optional[str] = None
    schema_name: Optional[str] = None
    name:        Optional[str] = None
    created_at:  Optional[str] = None
    last_used_at:Optional[str] = None


@dataclass
class DashboardObj:
    """Tek bir grafik objesi — canvas üzerindeki konum ve boyut."""
    id:       str
    type:     str        # kpi | line | column | pie | donut | table | matrix | map | text
    x:        float      # mm
    y:        float      # mm
    w:        float      # mm
    h:        float      # mm
    title:    str        = ""
    query_id: Optional[str] = None
    # Varsayılan grafik rengi (mavi, hex kodu).
    color:    str        = "#378ADD"


@dataclass
class Dashboard:
    """
    Bir dashboard (rapor sayfası).
    objects listesi sayfadaki grafik objelerini (DashboardObj) tutar.
    scale ve page_w_mm / page_h_mm sayfa boyutunu belirler.
    """
    dashboard_id: str
    name:         str
    owner_id:     str             = "anonymous"
    # Sayfa boyutu adı; a4l = A4 yatay (297 x 210 mm).
    scale:        str             = "a4l"
    page_w_mm:    float           = 297.0
    page_h_mm:    float           = 210.0
    objects:      list[DashboardObj] = field(default_factory=list)
    created_at:   Optional[str]   = None
    updated_at:   Optional[str]   = None


@dataclass
class Dataset:
    """
    Kayıtlı sorgu ("dataset") — widget'lar buna dataset_id ile referans verir.
    Widget render'da HER SEFERİNDE bu tanımın GÜNCEL halini çekip çalıştırır,
    yani sorguyu burada güncellemek ona bağlı TÜM widget'ları otomatik günceller.
    """
    dataset_id: str
    name:       str
    conn_id:    str
    base_table: str
    owner_id:   str        = "anonymous"
    fields:     dict       = field(default_factory=dict)
    joins:      list       = field(default_factory=list)
    filters:    list       = field(default_factory=list)
    group_by:   list       = field(default_factory=list)
    order_by:   list       = field(default_factory=list)
    # Hedef şema adı (ör. "hr"); None ise base_table şemasız kullanılır.
    schema_name: Optional[str] = None
    # Hesaplanmış alanlar: [{"name": ..., "formula": ...}, ...]. Formüller çalıştırmada doğrulanır.
    calculated_fields: list = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class QueryVersion:
    """Bir sorgunun tek bir versiyonu."""
    id:           str
    fingerprint:  str
    conn_id:      str
    conn_name:    str
    base_table:   str
    sql_text:     str
    fields:       dict            = field(default_factory=dict)
    joins:        list            = field(default_factory=list)
    filters:      list            = field(default_factory=list)
    group_by:     list            = field(default_factory=list)
    # Önizlemede kaç satır gösterildiği; 10 varsayılan değer.
    sample:       int             = 10
    mode:         str             = "memory"
    row_count:    Optional[int]   = None
    exec_ms:      Optional[float] = None
    note:         str             = ""
    created_at:   Optional[str]   = None


# ---------------------------------------------------------------------------
# ConnectionRepository
# ---------------------------------------------------------------------------

class ConnectionRepository:
    """
    Bağlantı metadata — şifre asla burada.
    Şimdi: SQLiteStore | Sonra: PostgreSQL — endpoint değişmez.

    owner_id ile sahiplik kontrolü:
      - list_all(owner_id=...) → sadece o kullanıcının bağlantıları
      - get_owned(conn_id, owner_id) → başkasının bağlantısına erişim 404
      - admin rolü tüm bağlantıları görebilir (router seviyesinde kontrol)
    """

    def __init__(self, store: "SQLiteStore") -> None:
        """Repository'yi bir SQLiteStore ile oluşturur. store, SQL çalıştırmayı sağlayan veritabanı yardımcısıdır."""
        self._s = store

    def save(self, meta: ConnectionMeta) -> None:
        """
        Bağlantıyı kaydeder. Aynı conn_id zaten varsa günceller (UPSERT), yoksa yeni satır ekler.
        şifre yalnız şifreli hali (password_enc) olarak yazılır.
        """
        # DİKKAT: Bu UPSERT'te owner_id güncellenmez; bağlantının sahibi ilk kayıtta belirlenir.
        self._s.execute("""
            INSERT INTO connections
              (conn_id, owner_id, db_type, host, database_, port_, user_, password_enc, schema_name, name, created_at)
            VALUES (:conn_id,:owner,:db_type,:host,:db,:port,:user,:pwd,:schema,:name,:now)
            ON CONFLICT(conn_id) DO UPDATE SET
              db_type=excluded.db_type, host=excluded.host,
              database_=excluded.database_, port_=excluded.port_,
              user_=excluded.user_, password_enc=excluded.password_enc,
              schema_name=excluded.schema_name, name=excluded.name
        """, {
            "conn_id": meta.conn_id, "owner": meta.owner_id,
            "db_type": meta.db_type, "host": meta.host or "",
            "db": meta.database, "port": meta.port,
            "user": meta.user, "pwd": meta.password_enc, "schema": meta.schema_name,
            "name": meta.name or meta.conn_id, "now": _now(),
        })

    def touch(self, conn_id: str) -> None:
        """Son kullanım zamanını güncelle."""
        self._s.execute(
            "UPDATE connections SET last_used_at=? WHERE conn_id=?",
            (_now(), conn_id)
        )

    def get(self, conn_id: str) -> Optional[ConnectionMeta]:
        """conn_id ile bağlantıyı getirir. Bulunamazsa None döner."""
        row = self._s.fetchone(
            "SELECT * FROM connections WHERE conn_id=?", (conn_id,)
        )
        return _row_to_conn(row) if row else None

    def get_or_raise(self, conn_id: str) -> ConnectionMeta:
        """
        conn_id ile bağlantıyı getirir; yoksa KeyError fırlatır.
        Sahiplik kontrolü yapmaz; kullanıcıya bağlı kontrol için get_owned_or_raise kullanılır.
        """
        meta = self.get(conn_id)
        if meta is None:
            raise KeyError(conn_id)
        return meta

    def get_owned_or_raise(self, conn_id: str, owner_id: str) -> ConnectionMeta:
        """
        Bağlantı var mı VE bu kullanıcıya mı ait kontrolü.
        Başkasının bağlantısı için de KeyError fırlatır (var olduğunu sızdırmaz).
        """
        meta = self.get(conn_id)
        if meta is None or meta.owner_id != owner_id:
            raise KeyError(conn_id)
        return meta

    def list_all(self, owner_id: Optional[str] = None) -> list[ConnectionMeta]:
        """owner_id verilirse sadece o kullanıcının bağlantıları döner."""
        # DİKKAT: owner_id boş metin ('') ise filtre uygulanmaz ve TÜM kayıtlar gelir. Çağıran tarafta boş değer kontrol edilmeli.
        if owner_id:
            rows = self._s.fetchall(
                "SELECT * FROM connections WHERE owner_id=? "
                "ORDER BY last_used_at DESC, created_at DESC",
                (owner_id,)
            )
        else:
            rows = self._s.fetchall(
                "SELECT * FROM connections ORDER BY last_used_at DESC, created_at DESC"
            )
        return [_row_to_conn(r) for r in rows]

    def delete(self, conn_id: str) -> bool:
        """
        Bağlantıyı conn_id ile siler. Satır gerçekten silindiyse True, kayıt yoksa False döner.
        Sahiplik kontrolü yapmaz; kullanıcı sınırı için delete_owned kullanılır.
        """
        cur = self._s.execute(
            "DELETE FROM connections WHERE conn_id=?", (conn_id,)
        )
        return cur.rowcount > 0

    def delete_owned(self, conn_id: str, owner_id: str) -> bool:
        """Bağlantıyı yalnız sahibi (owner_id) silebilir. Kayıt yoksa ya da başkasınınsa False döner."""
        cur = self._s.execute(
            "DELETE FROM connections WHERE conn_id=? AND owner_id=?",
            (conn_id, owner_id)
        )
        return cur.rowcount > 0

    def exists(self, conn_id: str) -> bool:
        """Bu conn_id ile bir bağlantı var mı diye bakar (True/False). Tüm kolonları çekmez."""
        row = self._s.fetchone(
            "SELECT 1 FROM connections WHERE conn_id=?", (conn_id,)
        )
        return row is not None


def _row_to_conn(row: "sqlite3.Row") -> ConnectionMeta:
    """
    Veritabanı satırını (sqlite3.Row) ConnectionMeta nesnesine çevirir.
    Eski tablolarda bulunmayabilecek kolonlar için varsayılan değer kullanır.
    """
    keys = row.keys()
    return ConnectionMeta(
        conn_id=row["conn_id"], db_type=row["db_type"],
        host=row["host"],       database=row["database_"],
        # Eski veritabanlarında owner_id kolonu olmayabilir; bu yüzden kolon var mı diye bakılır.
        owner_id=row["owner_id"] if "owner_id" in keys else "anonymous",
        port=row["port_"] if "port_" in keys else None,
        user=row["user_"],
        password_enc=row["password_enc"] if "password_enc" in keys else None,
        schema_name=row["schema_name"],
        name=row["name"],       created_at=row["created_at"],
        last_used_at=row["last_used_at"],
    )


# ---------------------------------------------------------------------------
# DashboardRepository
# ---------------------------------------------------------------------------

class DashboardRepository:
    """owner_id ile sahiplik kontrolü — aynı ConnectionRepository mantığı."""

    def __init__(self, store: "SQLiteStore") -> None:
        """Repository'yi bir SQLiteStore ile oluşturur. store, SQL çalıştırmayı sağlayan veritabanı yardımcısıdır."""
        self._s = store

    def save(self, dash: Dashboard) -> None:
        """
        Dashboard'u kaydeder. Grafik objeleri JSON metnine çevrilip layout_json kolonuna yazılır.
        Aynı dashboard_id varsa günceller (UPSERT).
        """
        self._s.execute("""
            INSERT INTO dashboards
              (dashboard_id, owner_id, name, scale, page_w_mm, page_h_mm, layout_json, created_at, updated_at)
            VALUES (:id,:owner,:name,:scale,:pw,:ph,:layout,:now,:now)
            ON CONFLICT(dashboard_id) DO UPDATE SET
              name=excluded.name, scale=excluded.scale,
              page_w_mm=excluded.page_w_mm, page_h_mm=excluded.page_h_mm,
              layout_json=excluded.layout_json, updated_at=excluded.updated_at
        """, {
            "id": dash.dashboard_id, "owner": dash.owner_id, "name": dash.name,
            "scale": dash.scale, "pw": dash.page_w_mm, "ph": dash.page_h_mm,
            # Grafik objeleri JSON metnine çevrilir. ensure_ascii=False Türkçe karakterlerin bozulmasını önler.
            "layout": json.dumps([asdict(o) for o in dash.objects], ensure_ascii=False),
            "now": _now(),
        })

    def get(self, dashboard_id: str) -> Optional[Dashboard]:
        """dashboard_id ile dashboard'u objeleriyle birlikte getirir. Yoksa None döner."""
        row = self._s.fetchone(
            "SELECT * FROM dashboards WHERE dashboard_id=?", (dashboard_id,)
        )
        return _row_to_dash(row) if row else None

    def get_owned_or_raise(self, dashboard_id: str, owner_id: str) -> Dashboard:
        """
        dashboard var mı ve owner_id bu kullanıcıya mı ait diye bakar.
        Değilse KeyError fırlatır; başkasınınki ile olmayan aynı hatayı verir (varlık sızmaz).
        """
        dash = self.get(dashboard_id)
        if dash is None or dash.owner_id != owner_id:
            raise KeyError(dashboard_id)
        return dash

    def list_all(self, owner_id: Optional[str] = None) -> list[Dashboard]:
        """
        Dashboard listesini döner. Objeler (layout) çekilmez, liste hafiftir.
        owner_id verilirse sadece o kullanıcının dashboard'ları gelir.
        """
        if owner_id:
            rows = self._s.fetchall(
                "SELECT dashboard_id, owner_id, name, scale, page_w_mm, page_h_mm, created_at, updated_at "
                "FROM dashboards WHERE owner_id=? ORDER BY updated_at DESC",
                (owner_id,)
            )
        else:
            rows = self._s.fetchall(
                "SELECT dashboard_id, owner_id, name, scale, page_w_mm, page_h_mm, created_at, updated_at "
                "FROM dashboards ORDER BY updated_at DESC"
            )
        return [Dashboard(
            dashboard_id=r["dashboard_id"], owner_id=r["owner_id"], name=r["name"],
            scale=r["scale"], page_w_mm=r["page_w_mm"], page_h_mm=r["page_h_mm"],
            created_at=r["created_at"], updated_at=r["updated_at"],
            objects=[],
        ) for r in rows]

    def delete(self, dashboard_id: str) -> bool:
        """Dashboard'u id ile siler. Silinirse True, yoksa False döner."""
        cur = self._s.execute(
            "DELETE FROM dashboards WHERE dashboard_id=?", (dashboard_id,)
        )
        return cur.rowcount > 0

    def delete_owned(self, dashboard_id: str, owner_id: str) -> bool:
        """Dashboard'u yalnız sahibi silebilir. Kayıt yoksa ya da başkasınınsa False döner."""
        cur = self._s.execute(
            "DELETE FROM dashboards WHERE dashboard_id=? AND owner_id=?",
            (dashboard_id, owner_id)
        )
        return cur.rowcount > 0

    def exists(self, dashboard_id: str) -> bool:
        """Bu id ile dashboard var mı diye bakar (True/False)."""
        return self._s.fetchone(
            "SELECT 1 FROM dashboards WHERE dashboard_id=?", (dashboard_id,)
        ) is not None


def _row_to_dash(row: "sqlite3.Row") -> Dashboard:
    """
    Veritabanı satırını Dashboard nesnesine çevirir.
    layout_json metnini JSON'dan okuyup DashboardObj listesine dönüştürür.
    """
    # Her JSON sözlüğü DashboardObj nesnesine çevrilir.
    objs = [DashboardObj(**o) for o in json.loads(row["layout_json"])]
    return Dashboard(
        dashboard_id=row["dashboard_id"],
        owner_id=row["owner_id"] if "owner_id" in row.keys() else "anonymous",
        name=row["name"], scale=row["scale"],
        page_w_mm=row["page_w_mm"], page_h_mm=row["page_h_mm"],
        objects=objs, created_at=row["created_at"], updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# DatasetRepository
# ---------------------------------------------------------------------------

class DatasetRepository:
    """owner_id ile sahiplik kontrolü — aynı ConnectionRepository/DashboardRepository mantığı."""

    def __init__(self, store: "SQLiteStore") -> None:
        """Repository'yi bir SQLiteStore ile oluşturur. store, SQL çalıştırmayı sağlayan veritabanı yardımcısıdır."""
        self._s = store

    def save(self, ds: Dataset) -> None:
        """
        Kayıtlı sorguyu (dataset) kaydeder. Alan, join, filtre gibi listeler JSON metni olarak saklanır.
        Aynı dataset_id varsa günceller (UPSERT).
        """
        self._s.execute("""
            INSERT INTO datasets
              (dataset_id, owner_id, name, conn_id, base_table,
               fields_json, joins_json, filters_json, group_by_json, order_by_json,
               schema_name, calculated_fields_json,
               created_at, updated_at)
            VALUES (:id,:owner,:name,:conn_id,:base_table,
                    :fields,:joins,:filters,:group_by,:order_by,
                    :schema_name,:calc,
                    :now,:now)
            ON CONFLICT(dataset_id) DO UPDATE SET
              name=excluded.name, conn_id=excluded.conn_id, base_table=excluded.base_table,
              fields_json=excluded.fields_json, joins_json=excluded.joins_json,
              filters_json=excluded.filters_json, group_by_json=excluded.group_by_json,
              order_by_json=excluded.order_by_json,
              schema_name=excluded.schema_name, calculated_fields_json=excluded.calculated_fields_json,
              updated_at=excluded.updated_at
        """, {
            "id": ds.dataset_id, "owner": ds.owner_id, "name": ds.name,
            "conn_id": ds.conn_id, "base_table": ds.base_table,
            "fields": json.dumps(ds.fields, ensure_ascii=False),
            "joins": json.dumps(ds.joins, ensure_ascii=False),
            "filters": json.dumps(ds.filters, ensure_ascii=False),
            "group_by": json.dumps(ds.group_by, ensure_ascii=False),
            "order_by": json.dumps(ds.order_by, ensure_ascii=False),
            "schema_name": ds.schema_name,
            "calc": json.dumps(ds.calculated_fields, ensure_ascii=False),
            "now": _now(),
        })

    def get(self, dataset_id: str) -> Optional[Dataset]:
        """dataset_id ile dataset'i getirir. Yoksa None döner."""
        row = self._s.fetchone("SELECT * FROM datasets WHERE dataset_id=?", (dataset_id,))
        return _row_to_dataset(row) if row else None

    def get_or_raise(self, dataset_id: str) -> Dataset:
        """dataset_id ile dataset'i getirir; yoksa KeyError fırlatır. Sahiplik kontrolü yapmaz."""
        ds = self.get(dataset_id)
        if ds is None:
            raise KeyError(dataset_id)
        return ds

    def get_owned_or_raise(self, dataset_id: str, owner_id: str) -> Dataset:
        """dataset var mı ve sahibi bu kullanıcı mı diye bakar. Değilse KeyError fırlatır."""
        ds = self.get(dataset_id)
        if ds is None or ds.owner_id != owner_id:
            raise KeyError(dataset_id)
        return ds

    def list_all(self, owner_id: Optional[str] = None) -> list[Dataset]:
        """Dataset listesini döner. owner_id verilirse sadece o kullanıcının dataset'leri gelir."""
        if owner_id:
            rows = self._s.fetchall(
                "SELECT * FROM datasets WHERE owner_id=? ORDER BY updated_at DESC", (owner_id,)
            )
        else:
            rows = self._s.fetchall("SELECT * FROM datasets ORDER BY updated_at DESC")
        return [_row_to_dataset(r) for r in rows]

    def delete(self, dataset_id: str) -> bool:
        """Dataset'i id ile siler. Silinirse True, yoksa False döner."""
        cur = self._s.execute("DELETE FROM datasets WHERE dataset_id=?", (dataset_id,))
        return cur.rowcount > 0

    def delete_owned(self, dataset_id: str, owner_id: str) -> bool:
        """Dataset'i yalnız sahibi silebilir. Kayıt yoksa ya da başkasınınsa False döner."""
        cur = self._s.execute(
            "DELETE FROM datasets WHERE dataset_id=? AND owner_id=?", (dataset_id, owner_id)
        )
        return cur.rowcount > 0

    def exists(self, dataset_id: str) -> bool:
        """Bu id ile dataset var mı diye bakar (True/False)."""
        return self._s.fetchone("SELECT 1 FROM datasets WHERE dataset_id=?", (dataset_id,)) is not None


def _row_to_dataset(row: "sqlite3.Row") -> Dataset:
    """Veritabanı satırını Dataset nesnesine çevirir; JSON kolonlarını Python listesi/sözlüğüne çevirir."""
    return Dataset(
        dataset_id=row["dataset_id"], owner_id=row["owner_id"],
        name=row["name"], conn_id=row["conn_id"], base_table=row["base_table"],
        fields=json.loads(row["fields_json"]), joins=json.loads(row["joins_json"]),
        filters=json.loads(row["filters_json"]), group_by=json.loads(row["group_by_json"]),
        order_by=json.loads(row["order_by_json"]),
        schema_name=row["schema_name"],
        # Migration öncesi satırlarda kolon NULL kalır; boş liste sayılır.
        calculated_fields=json.loads(row["calculated_fields_json"] or "[]"),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# QueryHistoryRepository
# ---------------------------------------------------------------------------

class QueryHistoryRepository:
    """
    Sorgu geçmişi + versiyonlama.
    fingerprint = base_table + join'ler → aynı sorgu grubu
    """

    def __init__(self, store: "SQLiteStore") -> None:
        """Repository'yi bir SQLiteStore ile oluşturur. store, SQL çalıştırmayı sağlayan veritabanı yardımcısıdır."""
        self._s = store

    def add(self, version: QueryVersion) -> None:
        """
        Sorgu çalıştırma kaydını (versiyonu) geçmişe ekler.
        Aynı id zaten varsa hiçbir şey yapmaz (ON CONFLICT DO NOTHING); kayıt iki kez eklenmez.
        """
        self._s.execute("""
            INSERT INTO query_history
              (id, fingerprint, conn_id, conn_name, base_table, sql_text,
               fields_json, joins_json, filters_json, group_by_json,
               sample, mode, row_count, exec_ms, note, created_at)
            VALUES
              (:id,:fp,:conn,:cname,:bt,:sql,
               :fields,:joins,:filters,:group,
               :sample,:mode,:rows,:ms,:note,:now)
            ON CONFLICT(id) DO NOTHING
        """, {
            "id": version.id, "fp": version.fingerprint,
            "conn": version.conn_id, "cname": version.conn_name,
            "bt": version.base_table, "sql": version.sql_text,
            "fields":  json.dumps(version.fields,   ensure_ascii=False),
            "joins":   json.dumps(version.joins,    ensure_ascii=False),
            "filters": json.dumps(version.filters,  ensure_ascii=False),
            "group":   json.dumps(version.group_by, ensure_ascii=False),
            "sample":  version.sample, "mode": version.mode,
            "rows":    version.row_count, "ms": version.exec_ms,
            "note":    version.note, "now": version.created_at or _now(),
        })

    def get_groups(self, conn_id: Optional[str] = None) -> list[dict]:
        """
        fingerprint bazında grupla → her grup = 1 sorgu, N versiyon.
        """
        sql = """
            SELECT
              fingerprint,
              conn_id, conn_name,
              base_table,
              COUNT(*)           AS version_count,
              MAX(created_at)    AS last_at,
              SUM(row_count)     AS total_rows,
              AVG(exec_ms)       AS avg_ms
            FROM query_history
            {where}
            GROUP BY fingerprint
            ORDER BY last_at DESC
            LIMIT 50
        """
        # where metni sabit SQL parçasıdır; conn_id değeri :conn parametresiyle gönderilir (SQL enjeksiyonu olmaz).
        where = "WHERE conn_id=:conn" if conn_id else ""
        rows  = self._s.fetchall(
            sql.format(where=where),
            {"conn": conn_id} if conn_id else ()
        )
        return [dict(r) for r in rows]

    def get_versions(self, fingerprint: str) -> list[QueryVersion]:
        """Bir fingerprint'in tüm versiyonları — kronolojik sıra."""
        rows = self._s.fetchall(
            "SELECT * FROM query_history WHERE fingerprint=? ORDER BY created_at",
            (fingerprint,)
        )
        return [_row_to_version(r) for r in rows]

    def get_recent(self, limit: int = 20) -> list[QueryVersion]:
        """En son çalıştırılan sorguları (yeniden eskiye) döner. limit en fazla kaç kayıt geleceğini belirler; varsayılan 20."""
        rows = self._s.fetchall(
            "SELECT * FROM query_history ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        return [_row_to_version(r) for r in rows]

    def delete_group(self, fingerprint: str) -> int:
        """Bir fingerprint'in (sorgu grubunun) tüm versiyonlarını siler. Silinen satır sayısını döner."""
        cur = self._s.execute(
            "DELETE FROM query_history WHERE fingerprint=?", (fingerprint,)
        )
        return cur.rowcount

    def stats(self) -> dict:
        """
        Geçmiş için özet istatistik döner: benzersiz sorgu sayısı, toplam versiyon, ortalama süre ve toplam satır.
        Hiç kayıt yoksa boş sözlük döner.
        """
        row = self._s.fetchone("""
            SELECT
              COUNT(DISTINCT fingerprint) AS unique_queries,
              COUNT(*)                    AS total_versions,
              AVG(exec_ms)                AS avg_ms,
              SUM(row_count)              AS total_rows
            FROM query_history
        """)
        return dict(row) if row else {}


def _row_to_version(row: "sqlite3.Row") -> QueryVersion:
    """Veritabanı satırını QueryVersion nesnesine çevirir; JSON kolonlarını Python yapısına çevirir."""
    return QueryVersion(
        id=row["id"], fingerprint=row["fingerprint"],
        conn_id=row["conn_id"], conn_name=row["conn_name"],
        base_table=row["base_table"], sql_text=row["sql_text"],
        fields=json.loads(row["fields_json"]),
        joins=json.loads(row["joins_json"]),
        filters=json.loads(row["filters_json"]),
        group_by=json.loads(row["group_by_json"]),
        sample=row["sample"], mode=row["mode"],
        row_count=row["row_count"], exec_ms=row["exec_ms"],
        note=row["note"], created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Yardımcı
# ---------------------------------------------------------------------------

def _now() -> str:
    """
    Şu anki UTC zamanını 2026-10-24T09:00:00 biçiminde metin olarak döner.
    Tüm kayıt zamanları bu fonksiyonla yazılır.
    """
    # TODO(kontrol): datetime.utcnow yeni Python sürümlerinde kullanımdan kaldırıldı (uyarı verir). Davranış korunuyor; ileride timezone.utc'li yapıya geçilebilir.
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
