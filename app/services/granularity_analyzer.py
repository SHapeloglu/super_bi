"""
granularity_analyzer.py
------------------------
Tablo granularity (grain) tespiti, sütun sınıflandırma ve tablolar arası
ilişki keşfi. NLQ katmanının güvenlik temeli: yanlış grain'de JOIN
sessiz çift sayıma yol açar, bu modül olmadan NLQ'ya başlanmaz.

İki kaynaktan ilişki toplar:
  1. DB'nin kendi PK/FK metadata'sı (sqlalchemy.inspect) — ücretsiz,
     %100 güvenilir, source='fk_constraint', verified=1, confidence=1.0
  2. İstatistiksel çıkarım (grain + orphan testi) — FK tanımlanmamışsa
     veya cross-database ilişkiler için (fiziksel FK olamaz),
     source='inferred', verified=0, confidence=orphan oranına göre

MSSQL extended properties (sp_addextendedproperty / MS_Description)
BİLİNÇLİ OLARAK kullanılmıyor: serbest metin, format garantisi yok,
kural tabanlı/deterministik yaklaşımla çelişir.

Tüm sorgular SQLAlchemy Core (text()) ile dialect-agnostic yazılır;
identifier'lar connector_registry.quote_identifier ile güvenli hale
getirilir (SQL injection whitelist).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.core.connector_registry import quote_identifier

logger = logging.getLogger(__name__)

# Kategorik sınıflandırma eşikleri (ARCHITECTURE.md'deki tanıma göre)
_CATEGORICAL_RATIO_MIN = 0.001
_CATEGORICAL_RATIO_MAX = 0.10
_IDENTIFIER_RATIO_MIN = 0.98  # neredeyse tam tekillik = identifier

_DATE_TYPE_HINTS = ("date", "time", "timestamp")
_NUMERIC_TYPE_HINTS = (
    "int", "float", "double", "decimal", "numeric", "real", "money",
)


@dataclass
class ColumnProfile:
    name: str
    dtype: str
    distinct_count: int
    cardinality_ratio: float
    classification: str  # identifier | categorical | metric | date_axis | unknown

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "distinct_count": self.distinct_count,
            "cardinality_ratio": round(self.cardinality_ratio, 6),
            "classification": self.classification,
        }


@dataclass
class TableProfile:
    table_name: str
    row_count: int
    grain_columns: list[str]
    columns: list[ColumnProfile] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "table_name": self.table_name,
            "row_count": self.row_count,
            "grain_columns": self.grain_columns,
            "columns": [c.to_dict() for c in self.columns],
        }


@dataclass
class RelationshipCandidate:
    table_a: str
    column_a: str
    table_b: str
    column_b: str
    cardinality: str  # one-to-one | one-to-many | many-to-one | many-to-many | unknown
    source: str        # fk_constraint | inferred
    orphan_count: int | None
    orphan_ratio: float | None
    confidence: float
    verified: bool

    def to_dict(self) -> dict:
        return {
            "table_a": self.table_a,
            "column_a": self.column_a,
            "table_b": self.table_b,
            "column_b": self.column_b,
            "cardinality": self.cardinality,
            "source": self.source,
            "orphan_count": self.orphan_count,
            "orphan_ratio": (
                round(self.orphan_ratio, 6) if self.orphan_ratio is not None else None
            ),
            "confidence": round(self.confidence, 4),
            "verified": self.verified,
        }


def _q(identifier: str) -> str:
    return quote_identifier(identifier)


def _split_schema_table(table_name: str) -> tuple[str | None, str]:
    """
    "Schema.Table" -> ("Schema", "Table"); "Table" -> (None, "Table").
    sqlalchemy.inspect() metodları (get_columns, get_pk_constraint,
    get_foreign_keys) tam nitelikli adı tek parametre olarak kabul etmez,
    schema'yı ayrı bir keyword argüman ister — bu yüzden SQL sorgularında
    kullandığımız "Schema.Table" formatını burada ayrıştırıyoruz.
    """
    if "." in table_name:
        schema, table = table_name.split(".", 1)
        return schema, table
    return None, table_name


def _dtype_bucket(dtype_str: str) -> str:
    """SQLAlchemy tip adını kaba bir kovaya indirger (date/numeric/other)."""
    s = dtype_str.lower()
    if any(h in s for h in _DATE_TYPE_HINTS):
        return "date"
    if any(h in s for h in _NUMERIC_TYPE_HINTS):
        return "numeric"
    return "other"


# ---------------------------------------------------------------------------
# 1) PK/FK metadata keşfi — DB zaten biliyorsa tahmin yapma
# ---------------------------------------------------------------------------

def discover_fk_relationships(
    engine: Engine, schema: str | None = None
) -> list[RelationshipCandidate]:
    """
    sqlalchemy.inspect() ile tüm tablolardaki foreign key constraint'lerini
    okur. Bulunanlar source='fk_constraint', verified=1, confidence=1.0
    olarak döner — istatistiksel testten geçmelerine gerek yok.
    """
    insp = inspect(engine)
    results: list[RelationshipCandidate] = []
    try:
        table_names = insp.get_table_names(schema=schema)
    except Exception as e:
        logger.warning("Tablo listesi alınamadı: %s", e)
        return results

    for table_name in table_names:
        try:
            fks = insp.get_foreign_keys(table_name, schema=schema)
        except Exception as e:
            logger.warning("FK okunamadı (%s): %s", table_name, e)
            continue
        for fk in fks:
            ref_table = fk.get("referred_table")
            local_cols = fk.get("constrained_columns") or []
            ref_cols = fk.get("referred_columns") or []
            if not ref_table or not local_cols or not ref_cols:
                continue
            # Kompozit FK'lerde sıralı eşleşme varsayılır
            for local_col, ref_col in zip(local_cols, ref_cols):
                results.append(
                    RelationshipCandidate(
                        table_a=table_name,
                        column_a=local_col,
                        table_b=ref_table,
                        column_b=ref_col,
                        cardinality="many-to-one",
                        source="fk_constraint",
                        orphan_count=None,
                        orphan_ratio=None,
                        confidence=1.0,
                        verified=True,
                    )
                )
    return results


# ---------------------------------------------------------------------------
# 2) Grain tespiti — COUNT(*) vs COUNT(DISTINCT col)
# ---------------------------------------------------------------------------

def _row_count(engine: Engine, table_name: str) -> int:
    with engine.connect() as conn:
        row = conn.execute(text(f"SELECT COUNT(*) AS n FROM {_q(table_name)}")).fetchone()
    return int(row[0]) if row else 0


def _distinct_count(engine: Engine, table_name: str, column: str) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                f"SELECT COUNT(DISTINCT {_q(column)}) AS n FROM {_q(table_name)}"
            )
        ).fetchone()
    return int(row[0]) if row else 0


def detect_grain(
    engine: Engine, table_name: str, columns: list[str], row_count: int
) -> list[str]:
    """
    Grain tespiti: önce her sütunu tek başına dener (COUNT(*) == COUNT(DISTINCT)
    ise o sütun tablonun grain'i). Hiçbir tek sütun tekillik sağlamıyorsa,
    tüm sütunların birleşimini kompozit grain adayı olarak test eder.
    Not: tam kombinasyon taraması (powerset) büyük tablolarda maliyetli
    olduğundan MVP c~apsamında tek sütun + tam-küme fallback yeterli kabul
    edilir; ARCHITECTURE.md'deki "kombinasyonlar test edilir" ifadesi bu
    iki adımı kapsar.
    """
    if row_count == 0:
        return []

    safe_columns = []
    for col in columns:
        try:
            _q(col)
        except ValueError:
            continue  # desteklenmeyen (örn. boşluklu) kolon adı — atla
        safe_columns.append(col)
        distinct = _distinct_count(engine, table_name, col)
        if distinct == row_count:
            return [col]

    # Kompozit fallback: tüm (desteklenen) sütunları birlikte test et
    columns = safe_columns
    if len(columns) > 1:
        col_list = ", ".join(_q(c) for c in columns)
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    f"SELECT COUNT(*) AS n FROM (SELECT DISTINCT {col_list} "
                    f"FROM {_q(table_name)}) AS sub"
                )
            ).fetchone()
        composite_distinct = int(row[0]) if row else 0
        if composite_distinct == row_count:
            return list(columns)

    return []  # grain bulunamadı — tekrarlı satırlar olabilir


# ---------------------------------------------------------------------------
# 3) Sütun sınıflandırma
# --------------------------------------------------------------------------

def classify_columns(
    engine: Engine, table_name: str, row_count: int, pk_columns: set[str]
) -> list[ColumnProfile]:
    schema, bare_table = _split_schema_table(table_name)
    insp = inspect(engine)
    columns_meta = insp.get_columns(bare_table, schema=schema)
    profiles: list[ColumnProfile] = []

    for col_meta in columns_meta:
        name = col_meta["name"]
        dtype_str = str(col_meta.get("type", ""))
        bucket = _dtype_bucket(dtype_str)

        # Boşluk/özel karakter içeren kolon adları (örn. "Database Version")
        # quote_identifier whitelist'inden geçmez — SQL injection güvenliği
        # için bilinçli bir kısıtlama. Bu kolonlar "unsupported" olarak
        # işaretlenip atlanır, tüm tablo profillemesi çökertilmez.
        try:
            _q(name)
        except ValueError:
            profiles.append(ColumnProfile(name, dtype_str, 0, 0.0, "unsupported"))
            continue

        if row_count == 0:
            profiles.append(ColumnProfile(name, dtype_str, 0, 0.0, "unknown"))
            continue

        distinct = _distinct_count(engine, table_name, name)
        ratio = distinct / row_count

        if name in pk_columns or ratio >= _IDENTIFIER_RATIO_MIN:
            classification = "identifier"
        elif bucket == "date":
            classification = "date_axis"
        elif _CATEGORICAL_RATIO_MIN <= ratio <= _CATEGORICAL_RATIO_MAX:
            classification = "categorical"
        elif bucket == "numeric":
            classification = "metric"
        else:
            classification = "categorical" if ratio < _CATEGORICAL_RATIO_MIN else "unknown"

        profiles.append(ColumnProfile(name, dtype_str, distinct, ratio, classification))

    return profiles


def profile_table(engine: Engine, table_name: str) -> TableProfile:
    """
    Tek bir eyybo için tam profil: row_count + grain + sütun sınıflandırma.
    table_name "Schema.Table" (örn. "Sales.Customer") ya da şemasız
    "Table" formatında olabilir; inspect() çağrıları için ayrıştırılır,
    SQL sorguları için (quote_identifier) tam nitelikli haliyle kullanılır.
    """
    schema, bare_table = _split_schema_table(table_name)
    insp = inspect(engine)
    columns_meta = insp.get_columns(bare_table, schema=schema)
    column_names = [c["name"] for c in columns_meta]

    try:
        pk_constraint = insp.get_pk_constraint(bare_table, schema=schema)
        pk_columns = set(pk_constraint.get("constrained_columns") or [])
    except Exception:
        pk_columns = set()

    row_count = _row_count(engine, table_name)
    grain = list(pk_columns) if pk_columns else detect_grain(
        engine, table_name, column_names, row_count
    )
    columns = classify_columns(engine, table_name, row_count, pk_columns)

    return TableProfile(
        table_name=table_name, row_count=row_count, grain_columns=grain, columns=columns
    )


# ---------------------------------------------------------------------------
# 4) Referans bütünlüğü / orphan testi (FK metadata'da yoksa)
# ---------------------------------------------------------------------------

def test_relationship(
    engine: Engine, table_a: str, column_a: str, table_b: str, column_b: str
) -> RelationshipCandidate:
    """
    table_a.column_a -> table_b.column_b ilişkisini orphan testiyle doğrular:
      SELECT COUNT(*) FROM table_a LEFT JOIN table_b
        ON table_a.column_a = table_b.column_b
      WHERE table_b.column_b IS NULL AND table_a.column_a IS NOT NULL
    orphan_ratio düşükse ilişki adayı güçlü demektir (confidence yüksek).
    Kardinalite: table_b.column_b tarafında tekillik varsa many-to-one
    (A çok, B bir), yoksa many-to-many olarak işaretlenir.
    """
    qa_t, qa_c = _q(table_a), _q(column_a)
    qb_t, qb_c = _q(table_b), _q(column_b)

    with engine.connect() as conn:
        total_non_null = conn.execute(
            text(f"SELECT COUNT(*) FROM {qa_t} WHERE {qa_c} IS NOT NULL")
        ).scalar() or 0

        orphan_count = conn.execute(
            text(
                f"SELECT COUNT(*) FROM {qa_t} LEFT JOIN {qb_t} "
                f"ON {qa_t}.{qa_c} = {qb_t}.{qb_c} "
                f"WHERE {qb_t}.{qb_c} IS NULL AND {qa_t}.{qa_c} IS NOT NULL"
            )
        ).scalar() or 0

    orphan_ratio = (orphan_count / total_non_null) if total_non_null else 1.0
    confidence = max(0.0, 1.0 - orphan_ratio)

    b_distinct = _distinct_count(engine, table_b, column_b)
    b_row_count = _row_count(engine, table_b)
    cardinality = "many-to-one" if b_distinct == b_row_count and b_row_count > 0 else "many-to-many"

    return RelationshipCandidate(
        table_a=table_a,
        column_a=column_a,
        table_b=table_b,
        column_b=column_b,
        cardinality=cardinality,
        source="inferred",
        orphan_count=int(orphan_count),
        orphan_ratio=orphan_ratio,
        confidence=confidence,
        verified=False,
    )
