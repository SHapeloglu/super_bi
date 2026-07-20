"""
/api/schema — bağlı DB'nin tablo/kolon şeması (join builder için)
YENİDEN OLUŞTURULDU: main.py'de include_router(schema.router, ...) referansı
var ama dosya bulunamadığı için kullanım şekli oradan çıkarıldı.

conn_id path parametresi -> get_connection_engine ile sahiplik kontrolü.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect

from app.core.repository import ConnectionRepository
from app.deps import get_connection_engine, get_current_user, get_repo

router = APIRouter()


@router.get("/{conn_id}/tables")
def list_tables(
    conn_id:  str,
    engine_meta = Depends(get_connection_engine),
):
    engine, _meta = engine_meta
    try:
        insp = inspect(engine)
        return {"tables": insp.get_table_names()}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Şema okunamadı: {e}")


@router.get("/{conn_id}/tables/{table_name}/columns")
def list_columns(
    conn_id:    str,
    table_name: str,
    engine_meta = Depends(get_connection_engine),
):
    engine, _meta = engine_meta
    try:
        insp = inspect(engine)
        if table_name not in insp.get_table_names():
            raise HTTPException(status_code=404, detail=f"Tablo bulunamadı: {table_name}")
        cols = insp.get_columns(table_name)
        return {
            "table": table_name,
            "columns": [
                {"name": c["name"], "type": str(c["type"]), "nullable": c.get("nullable", True)}
                for c in cols
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Şema okunamadı: {e}")


@router.get("/{conn_id}/tables/{table_name}/foreign-keys")
def list_foreign_keys(
    conn_id:    str,
    table_name: str,
    engine_meta = Depends(get_connection_engine),
):
    """Join builder'da otomatik join önerisi için."""
    engine, _meta = engine_meta
    try:
        insp = inspect(engine)
        fks = insp.get_foreign_keys(table_name)
        return {
            "table": table_name,
            "foreign_keys": [
                {
                    "constrained_columns": fk["constrained_columns"],
                    "referred_table":      fk["referred_table"],
                    "referred_columns":    fk["referred_columns"],
                }
                for fk in fks
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FK bilgisi okunamadı: {e}")
