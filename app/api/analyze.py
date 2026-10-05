"""
/api/analyze — Tablo granularity + ilişki keşfi
------------------------------------------------
POST /api/analyze/{conn_id}/tables
    Bağlantıdaki tüm tabloları (veya istenen şemayı) analiz eder:
    - Grain tespiti
    - Sütun sınıflandırma
    - PK/FK ilişkileri (verified=1, confidence=1.0)
    Sonuçlar table_profiles + datasets_relationships tablolarına yazılır.

POST /api/analyze/{conn_id}/relationship
    İki tablo arası belirli bir sütun çifti için orphan testi çalıştırır
    (inferred ilişki, verified=0, confidence skoru ile).

GET /api/analyze/{conn_id}/results
    Bu bağlantıya ait kayıtlı profil ve ilişkileri döner.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.connector_registry import ConnectorRegistry
from app.core.repository import ConnectionRepository
from app.db.sqlite_store import SQLiteStore
from app.deps import (
    get_registry,
    get_repo,
    get_store,
    get_current_user,
    resolve_connection_engine,
)
from app.services import granularity_analyzer as ga

logger = logging.getLogger(__name__)
router = APIRouter()

# all_schemas=True iken taranmayacak sistem şemaları (MSSQL fixed database
# role'ları + information_schema, Postgres pg_catalog/pg_toast, vb.)
_SYSTEM_SCHEMAS = {
    "sys", "information_schema", "guest",
    "db_accessadmin", "db_backupoperator", "db_datareader", "db_datawriter",
    "db_ddladmin", "db_denydatareader", "db_denydatawriter", "db_owner",
    "db_securityadmin", "pg_catalog", "pg_toast",
}


# ---------------------------------------------------------------------------
# Pydantic modelleri
# ---------------------------------------------------------------------------

class AnalyzeTablesRequest(BaseModel):
    schema_name: Optional[str] = None
    tables: Optional[list[str]] = None  # None = tüm tablolar
    all_schemas: bool = False  # True ise sistem şemaları hariç TÜM şemalar taranır


class RelationshipTestRequest(BaseModel):
    table_a: str
    column_a: str
    table_b: str
    column_b: str


# ---------------------------------------------------------------------------
# Yardımcı: sonuçları SQLite'a kaydet
# ---------------------------------------------------------------------------

def _save_profile(store: SQLiteStore, conn_id: str, profile: ga.TableProfile) -> None:
    profile_id = str(uuid.uuid4())
    store.execute(
        """
        INSERT INTO table_profiles
            (profile_id, conn_id, table_name, row_count, grain_columns, columns_json)
        VALUES (:pid, :cid, :tname, :rc, :gc, :cj)
        ON CONFLICT(conn_id, table_name) DO UPDATE SET
            row_count     = excluded.row_count,
            grain_columns = excluded.grain_columns,
            columns_json  = excluded.columns_json,
            analyzed_at   = datetime('now')
        """,
        {
            "pid":   profile_id,
            "cid":   conn_id,
            "tname": profile.table_name,
            "rc":    profile.row_count,
            "gc":    json.dumps(profile.grain_columns),
            "cj":    json.dumps([c.to_dict() for c in profile.columns]),
        },
    )


def _save_relationship(
    store: SQLiteStore, conn_id: str, rel: ga.RelationshipCandidate
) -> None:
    rel_id = str(uuid.uuid4())
    store.execute(
        """
        INSERT INTO datasets_relationships
            (rel_id, conn_id, table_a, column_a, table_b, column_b,
             cardinality, source, orphan_count, orphan_ratio,
             confidence, verified)
        VALUES
            (:rid, :cid, :ta, :ca, :tb, :cb,
             :card, :src, :oc, :or_, :conf, :ver)
        ON CONFLICT(conn_id, table_a, column_a, table_b, column_b) DO UPDATE SET
            cardinality  = excluded.cardinality,
            source       = excluded.source,
            orphan_count = excluded.orphan_count,
            orphan_ratio = excluded.orphan_ratio,
            confidence   = excluded.confidence,
            verified     = excluded.verified,
            analyzed_at  = datetime('now')
        """,
        {
            "rid":  rel_id,
            "cid":  conn_id,
            "ta":   rel.table_a,
            "ca":   rel.column_a,
            "tb":   rel.table_b,
            "cb":   rel.column_b,
            "card": rel.cardinality,
            "src":  rel.source,
            "oc":   rel.orphan_count,
            "or_":  rel.orphan_ratio,
            "conf": rel.confidence,
            "ver":  1 if rel.verified else 0,
        },
    )


# ---------------------------------------------------------------------------
# Endpoint'ler
# ---------------------------------------------------------------------------

@router.post("/{conn_id}/tables")
def analyze_tables(
    conn_id: str,
    body: AnalyzeTablesRequest,
    current                       = Depends(get_current_user),
    registry: ConnectorRegistry    = Depends(get_registry),
    repo:     ConnectionRepository = Depends(get_repo),
    store:    SQLiteStore          = Depends(get_store),
):
    """
    Bağlantıdaki tabloları analiz eder; grain, sütun sınıflandırma ve
    FK ilişkilerini bulur, sonuçları SQLite metadata DB'ye kaydeder.

    all_schemas=True ise veritabanındaki TÜM kullanıcı şemaları taranır
    (sistem şemaları _SYSTEM_SCHEMAS ile hariç tutulur) — çok şemalı
    DB'lerde (MSSQL vb.) her şema için ayrı istek atmak gerekmez.
    """
    engine, _ = resolve_connection_engine(conn_id, current, registry, repo)

    from sqlalchemy import inspect as sa_inspect
    insp = sa_inspect(engine)

    def run_for_schema(schema: Optional[str]) -> dict:
        try:
            all_tables = insp.get_table_names(schema=schema)
        except Exception as e:
            return {
                "schema": schema, "tables_found": 0,
                "profiled": [], "fk_rels": [],
                "errors": [{"schema": schema, "error": f"Tablo listesi alınamadı: {e}"}],
            }

        target_tables = body.tables if body.tables else all_tables
        target_tables = [t for t in target_tables if t in all_tables]

        def full_name(table: str) -> str:
            return f"{schema}.{table}" if schema else table

        profiled = []
        errors = []

        # 1) Tablo profilleri
        for table in target_tables:
            try:
                profile = ga.profile_table(engine, full_name(table))
                _save_profile(store, conn_id, profile)
                profiled.append(profile.to_dict())
                logger.info("Profil kaydedildi: %s.%s", conn_id, full_name(table))
            except Exception as e:
                logger.warning("Profil hatası (%s): %s", full_name(table), e)
                errors.append({"table": full_name(table), "error": str(e)})

        # 2) FK ilişkileri (bu şema için)
        fk_rels = []
        try:
            fk_rels = ga.discover_fk_relationships(engine, schema=schema)
            for rel in fk_rels:
                try:
                    _save_relationship(store, conn_id, rel)
                except Exception as e:
                    logger.warning("İlişki kayıt hatası: %s", e)
        except Exception as e:
            logger.warning("FK keşfi hatası (%s): %s", schema, e)
            errors.append({"fk_discovery": str(e), "schema": schema})

        return {
            "schema": schema, "tables_found": len(all_tables),
            "profiled": profiled, "fk_rels": fk_rels, "errors": errors,
        }

    if body.all_schemas:
        try:
            schema_names = insp.get_schema_names()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Şema listesi alınamadı: {e}")
        target_schemas = [
            s for s in schema_names if s and s.lower() not in _SYSTEM_SCHEMAS
        ]
        results = [run_for_schema(s) for s in target_schemas]
    else:
        results = [run_for_schema(body.schema_name)]

    all_profiled = [p for r in results for p in r["profiled"]]
    all_fk_rels  = [rel for r in results for rel in r["fk_rels"]]
    all_errors   = [e for r in results for e in r["errors"]]
    tables_found_total = sum(r["tables_found"] for r in results)

    return {
        "conn_id":          conn_id,
        "schemas_scanned":  [r["schema"] for r in results],
        "tables_found":     tables_found_total,
        "tables_profiled":  len(all_profiled),
        "fk_relationships": len(all_fk_rels),
        "errors":           all_errors,
        "profiles":         all_profiled,
        "relationships":    [r.to_dict() for r in all_fk_rels],
    }


@router.post("/{conn_id}/relationship")
def test_relationship(
    conn_id: str,
    body: RelationshipTestRequest,
    current                       = Depends(get_current_user),
    registry: ConnectorRegistry    = Depends(get_registry),
    repo:     ConnectionRepository = Depends(get_repo),
    store:    SQLiteStore          = Depends(get_store),
):
    """
    İki sütun arası orphan testi çalıştırır. Sonuç kaydedilir ve döner.
    Kullanıcı daha sonra UI'dan verified=True yapabilir.
    """
    engine, _ = resolve_connection_engine(conn_id, current, registry, repo)

    try:
        rel = ga.test_relationship(
            engine,
            body.table_a, body.column_a,
            body.table_b, body.column_b,
        )
        _save_relationship(store, conn_id, rel)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return rel.to_dict()


@router.get("/{conn_id}/results")
def get_analysis_results(
    conn_id: str,
    current                       = Depends(get_current_user),
    repo:     ConnectionRepository = Depends(get_repo),
    store:    SQLiteStore          = Depends(get_store),
):
    """
    Bu bağlantıya ait tüm kayıtlı profil ve ilişkileri döner.
    """
    # Sahiplik kontrolü — bağlantı bu kullanıcıya ait mi?
    from app.deps import get_user_repo
    conn = repo.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")

    profiles = store.fetchall(
        "SELECT * FROM table_profiles WHERE conn_id = :cid ORDER BY analyzed_at DESC",
        {"cid": conn_id},
    )
    relationships = store.fetchall(
        "SELECT * FROM datasets_relationships WHERE conn_id = :cid ORDER BY confidence DESC",
        {"cid": conn_id},
    )

    return {
        "conn_id": conn_id,
        "profiles": [
            {
                "table_name":    r["table_name"],
                "row_count":     r["row_count"],
                "grain_columns": json.loads(r["grain_columns"]),
                "columns":       json.loads(r["columns_json"]),
                "analyzed_at":   r["analyzed_at"],
            }
            for r in profiles
        ],
        "relationships": [
            {
                "table_a":     r["table_a"],
                "column_a":    r["column_a"],
                "table_b":     r["table_b"],
                "column_b":    r["column_b"],
                "cardinality": r["cardinality"],
                "source":      r["source"],
                "confidence":  r["confidence"],
                "verified":    bool(r["verified"]),
                "analyzed_at": r["analyzed_at"],
            }
            for r in relationships
        ],
    }
