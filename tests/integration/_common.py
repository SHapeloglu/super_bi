"""
Entegrasyon testlerinin ortak yardımcıları.

Her DB için test dosyası kendi ortam değişkenini okur (DATALENS_IT_<DB>_URL, SQLAlchemy URL).
Değişken tanımlı değilse test "ATLANDI" yazar ve 0 ile çıkar.

Kurallar:
  - Test verisi (dl_it_musteri, dl_it_siparis) SQLAlchemy Core ile kurulur; DDL dialect'e göre elle yazılmaz.
  - Tablolar her çalıştırmada yeniden oluşturulur. URL'deki veritabanı TEST veritabanı olmalıdır;
    üretim veritabanı ASLA verilmez.
  - Satır sınırlama, JOIN ve WHERE SQL'i app/services/sql_builder.py ile üretilir (elle SQL yok).
  - Oracle'da tablo/kolon adları büyük harfle verilir (sql_builder yalnız temel tabloyu büyütür).
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import (  # noqa: E402
    Column, Integer, MetaData, Numeric, String, Table, create_engine, event,
    inspect, insert, text,
)

from app.models.schemas import FilterDef, JoinDef  # noqa: E402
from app.services.sql_builder import sql_builder  # noqa: E402

CUSTOMER = "dl_it_musteri"
ORDER = "dl_it_siparis"

# Türkçe karakter yok: MSSQL VARCHAR (N'' olmadan) kod sayfası sorunlarından kaçınmak için.
CUSTOMERS = [
    (1, "Ayse", "Ankara"),
    (2, "Mehmet", "Istanbul"),
    (3, "Zeynep", "Ankara"),
    (4, "Can", "Izmir"),
    (5, "Elif", "Bursa"),
]
ORDERS = [
    (1, 1, Decimal("100.00"), "tamam"),
    (2, 1, Decimal("250.50"), "tamam"),
    (3, 2, Decimal("80.00"), "iptal"),
    (4, 3, Decimal("500.00"), "tamam"),
    (5, 3, Decimal("20.00"), "beklemede"),
    (6, 4, Decimal("75.25"), "tamam"),
    (7, 4, Decimal("10.00"), "tamam"),
    (8, 5, Decimal("900.00"), "iptal"),
]


def _n(db_type: str, name: str) -> str:
    """Oracle'da ad büyük harf olmalı (metadata ve tırnaklı identifier eşleşmesi)."""
    return name.upper() if db_type == "oracle" else name


def _metadata() -> MetaData:
    md = MetaData()
    # autoincrement=False: MSSQL IDENTITY ve Oracle identity kolonu açık id yazımını engellemesin.
    Table(
        CUSTOMER, md,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("ad", String(50), nullable=False),
        Column("sehir", String(30), nullable=False),
    )
    Table(
        ORDER, md,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("musteri_id", Integer, nullable=False),
        Column("tutar", Numeric(10, 2), nullable=False),
        Column("durum", String(20), nullable=False),
    )
    return md


def setup_fixtures(engine) -> None:
    """Test tablolarını yeniden kurar ve verisini yazar."""
    md = _metadata()
    md.drop_all(engine, checkfirst=True)
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(md.tables[CUSTOMER]),
                     [{"id": i, "ad": a, "sehir": s} for i, a, s in CUSTOMERS])
        conn.execute(insert(md.tables[ORDER]),
                     [{"id": i, "musteri_id": m, "tutar": t, "durum": d} for i, m, t, d in ORDERS])


def build_sql(db_type: str, base: str, fields: dict[str, str], *, joins=(), filters=(),
              order_by=(), limit: int = 100, offset: int = 0):
    """
    sql_builder.build çağrısını sarar.
      joins:   (tip, t1, f1, t2, f2) demetleri
      filters: (tablo, kolon, operatör, değer) demetleri
    Dönüş: (sql, params)
    """
    join_defs = [
        JoinDef(type=jt, t1=_n(db_type, t1), f1=_n(db_type, f1),
                t2=_n(db_type, t2), f2=_n(db_type, f2))
        for jt, t1, f1, t2, f2 in joins
    ]
    filter_defs = [
        FilterDef(table=_n(db_type, t), column=_n(db_type, c), operator=op, value=v)
        for t, c, op, v in filters
    ]
    return sql_builder.build(
        base_table=_n(db_type, base),
        fields=fields,
        joins=join_defs,
        filters=filter_defs,
        group_by=[],
        order_by=[_n(db_type, o) for o in order_by],
        limit=limit,
        offset=offset,
        db_type=db_type,
    )


def fetch_rows(engine, sql_and_params) -> list[tuple]:
    sql, params = sql_and_params
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql), params).fetchall()]


def make_checks(db_type: str) -> list:
    """Tüm DB'lerde ortak kontrol listesi. Her kontrol başarısızsa AssertionError fırlatır."""

    def tablo_listesi(engine):
        names = {n.lower() for n in inspect(engine).get_table_names()}
        assert CUSTOMER in names and ORDER in names, f"test tabloları yok: {sorted(names)[:15]}"

    def basit_select(engine):
        rows = fetch_rows(engine, build_sql(db_type, CUSTOMER, {"id": "on", "ad": "on"},
                                            order_by=["id"]))
        assert len(rows) == len(CUSTOMERS), f"{len(CUSTOMERS)} bekleniyordu, {len(rows)} geldi"

    def where_filtresi(engine):
        rows = fetch_rows(engine, build_sql(
            db_type, CUSTOMER, {"id": "on"},
            filters=[(CUSTOMER, "sehir", "=", "Ankara")], order_by=["id"]))
        assert [int(r[0]) for r in rows] == [1, 3], f"[1, 3] bekleniyordu, {rows}"

    def join_select(engine):
        rows = fetch_rows(engine, build_sql(
            db_type, ORDER, {f"{CUSTOMER}.ad": "on", f"{ORDER}.tutar": "on"},
            joins=[("INNER JOIN", ORDER, "musteri_id", CUSTOMER, "id")],
            order_by=[f"{ORDER}.id"]))
        assert len(rows) == len(ORDERS), f"{len(ORDERS)} bekleniyordu, {len(rows)} geldi"

    def join_where(engine):
        rows = fetch_rows(engine, build_sql(
            db_type, ORDER, {f"{CUSTOMER}.ad": "on", f"{ORDER}.tutar": "on"},
            joins=[("INNER JOIN", ORDER, "musteri_id", CUSTOMER, "id")],
            filters=[(CUSTOMER, "sehir", "=", "Ankara")],
            order_by=[f"{ORDER}.id"]))
        # Ankara'daki müşteriler (1, 3) için siparişler: 1, 2, 4, 5
        assert len(rows) == 4, f"4 bekleniyordu, {len(rows)} geldi"

    def satir_siniri(engine):
        rows = fetch_rows(engine, build_sql(db_type, CUSTOMER, {"id": "on"},
                                            order_by=["id"], limit=3))
        assert [int(r[0]) for r in rows] == [1, 2, 3], f"[1, 2, 3] bekleniyordu, {rows}"

    def satir_siniri_offset(engine):
        rows = fetch_rows(engine, build_sql(db_type, CUSTOMER, {"id": "on"},
                                            order_by=["id"], limit=2, offset=2))
        assert [int(r[0]) for r in rows] == [3, 4], f"[3, 4] bekleniyordu, {rows}"

    return [
        ("tablo_listesi", tablo_listesi),
        ("basit_select", basit_select),
        ("where_filtresi", where_filtresi),
        ("join", join_select),
        ("join_where", join_where),
        ("satir_siniri_limit", satir_siniri),
        ("satir_siniri_offset", satir_siniri_offset),
    ]


def run_suite(label: str, env_var: str, db_type: str, checks: list, on_connect=None) -> int:
    """Ortam değişkenini okur, kurulumu yapar, kontrolleri çalıştırır. Çıkış kodu döner."""
    url = os.environ.get(env_var, "").strip()
    if not url:
        print(f"[ATLANDI] {label}: {env_var} tanımlı değil")
        return 0


    engine = create_engine(url, pool_pre_ping=True)
    if on_connect is not None:
        event.listen(engine, "connect", on_connect)
    try:
        setup_fixtures(engine)
    except Exception as e:  # URL'de parola olabilir; yalnız hata türü ve kısa mesaj yazılır
        print(f"[HATA] {label}: kurulum başarısız -> {type(e).__name__}: {str(e)[:300]}")
        engine.dispose()
        return 1

    failed = 0
    for name, fn in checks:
        try:
            fn(engine)
            print(f"[PASS] {label}: {name}")
        except Exception as e:
            failed += 1
            print(f"[FAIL] {label}: {name} -> {type(e).__name__}: {str(e)[:300]}")
    engine.dispose()
    print(f"{label}: {len(checks) - failed}/{len(checks)} kontrol geçti")
    return 1 if failed else 0
