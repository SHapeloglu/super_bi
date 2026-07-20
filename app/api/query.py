"""
/api/query — "Önce gör, onay verince al" prensibi + auth

Endpoint'ler:
  POST /api/query/preview  → SQL üret, çalıştırma (auth gerektirmez)
  POST /api/query/run      → sample=10|100|1000, commit=false|true (auth gerekli)
  POST /api/query/commit   → geçici cache → kalıcı (auth gerekli)
  POST /api/query/stream   → ndjson stream (auth gerekli)
  DELETE /api/query/cache/{conn_id}  (auth gerekli — kendi cache'ini siler)
  GET  /api/query/cache/stats        (admin only)
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.deps import (
    get_executor, get_current_user,
    get_registry, get_repo, resolve_connection_engine,
)
from app.core.connector_registry import ConnectorRegistry
from app.core.repository import ConnectionRepository
from app.models.schemas import (
    SQLPreviewRequest, SQLPreviewResponse,
    QueryRequest, QueryResult,
    QueryRunRequest,
    CacheCommitRequest, CacheCommitResponse,
)
from app.services.query_executor import QueryExecutor
from app.services.sql_builder import sql_builder

router = APIRouter()


# ---------------------------------------------------------------------------
# 1. SQL Önizleme — auth gerektirmez, sadece SQL string üretir, DB'ye gitmez
#
#    Not: preview auth gerektirmediği için gerçek bağlantının db_type'ını
#    (dialect) bilmiyoruz — hesaplanmış alan formülleri burada "sqlite"
#    dialect'i varsayılarak önizlenir. Gerçek çalıştırma (/run, /stream)
#    doğrulanmış meta.db_type'ı kullanır, dialect farkı SADECE önizleme
#    metninde (örn. IFNULL vs COALESCE) görülebilir, gerçek sorguyu etkilemez.
# ---------------------------------------------------------------------------

@router.post("/preview", response_model=SQLPreviewResponse)
def preview_sql(body: SQLPreviewRequest):
    try:
        sql, _ = sql_builder.build(
            base_table=body.base_table,
            fields=body.fields,
            joins=body.joins,
            filters=body.filters,
            group_by=body.group_by,
            order_by=body.order_by,
            limit=body.limit,
            calculated_fields=body.calculated_fields,
            db_type="sqlite",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return SQLPreviewResponse(
        sql=sql,
        estimated_complexity=sql_builder.estimate_complexity(
            body.joins, body.filters, body.group_by
        ),
    )


# ---------------------------------------------------------------------------
# 2. Sorgu çalıştır — sample + commit prensibi + tenant izolasyon
#
#  conn_id TEK kaynaktan gelir: body.conn_id. resolve_connection_engine bu
#  değeri sahiplik kontrolünden geçirip engine döner; ayrı bir query-param
#  conn_id YOKTUR — böylece "path conn_id ≠ body conn_id" ile auth bypass
#  edip cache/history'yi başka bir conn_id'ye yazma açığı kapanmış olur.
#  current.user_id artık gerçek — cache_key buna göre üretilir.
# ---------------------------------------------------------------------------

@router.post("/run")
def run_query(
    body:        QueryRunRequest,
    current                     = Depends(get_current_user),
    registry:    ConnectorRegistry    = Depends(get_registry),
    repo:        ConnectionRepository = Depends(get_repo),
    executor:    QueryExecutor        = Depends(get_executor),
):
    engine, meta = resolve_connection_engine(body.conn_id, current, registry, repo)

    try:
        sql, params = sql_builder.build(
            base_table=body.base_table,
            fields=body.fields,
            joins=body.joins,
            filters=body.filters,
            group_by=body.group_by,
            order_by=body.order_by,
            limit=body.sample,
            offset=0,
            calculated_fields=body.calculated_fields,
            db_type=meta.db_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = executor.execute(
        engine=engine,
        sql=sql,
        params=params,
        sample=body.sample,
        commit=body.commit,
        mode=body.mode,
        user_id=current.user_id,   # ← artık gerçek kullanıcı, tenant izolasyon aktif
        conn_id=meta.conn_id,      # ← doğrulanmış conn_id (meta üzerinden) — body'ye güvenilmez
    )
    return result


# ---------------------------------------------------------------------------
# 3. Commit — geçici cache → kalıcı
#    cache_key zaten user_id içeriyor — başkasının cache'ini commit edemez
# ---------------------------------------------------------------------------

@router.post("/commit", response_model=CacheCommitResponse)
def commit_cache(
    body:     CacheCommitRequest,
    current                    = Depends(get_current_user),
    executor: QueryExecutor    = Depends(get_executor),
):
    success = executor.commit(body.cache_key)
    return CacheCommitResponse(
        success=success,
        cache_key=body.cache_key,
        message="Cache'e alındı" if success else "Cache bulunamadı veya süresi doldu",
    )


# ---------------------------------------------------------------------------
# 4. Stream — büyük sonuçlar için ndjson
# ---------------------------------------------------------------------------

@router.post("/stream")
async def stream_query(
    body:        QueryRequest,
    current                     = Depends(get_current_user),
    registry:    ConnectorRegistry    = Depends(get_registry),
    repo:        ConnectionRepository = Depends(get_repo),
    executor:    QueryExecutor        = Depends(get_executor),
):
    engine, meta = resolve_connection_engine(body.conn_id, current, registry, repo)
    try:
        sql, params = sql_builder.build(
            base_table=body.base_table,
            fields=body.fields,
            joins=body.joins,
            filters=body.filters,
            group_by=body.group_by,
            order_by=body.order_by,
            limit=body.limit,
            offset=body.offset,
            calculated_fields=body.calculated_fields,
            db_type=meta.db_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StreamingResponse(
        executor.stream_execute(engine, sql, params, sample=body.limit),
        media_type="application/x-ndjson",
    )


# ---------------------------------------------------------------------------
# 5. Cache yönetimi
# ---------------------------------------------------------------------------

@router.delete("/cache/{conn_id}")
def invalidate_cache(
    conn_id:  str,
    current                     = Depends(get_current_user),
    registry: ConnectorRegistry    = Depends(get_registry),
    repo:     ConnectionRepository = Depends(get_repo),
    executor: QueryExecutor        = Depends(get_executor),
):
    """
    Not: invalidate(conn_id) tüm kullanıcıların o conn_id'deki cache'ini siler.
    Bu kasıtlı — bağlantı silindiğinde admin/owner tüm cache'i temizleyebilmeli.

    Önceden burada sahiplik kontrolü YOKTU — sadece login olmak yetiyordu,
    yani herhangi bir kullanıcı başkasının conn_id'sini bilirse (tahmin/
    brute-force) onun cache'ini silebiliyordu. resolve_connection_engine
    ile conn_id + owner/admin kontrolü zorunlu hale getirildi; bağlantı
    kaydı yoksa veya kullanıcıya ait değilse 404 döner.
    """
    resolve_connection_engine(conn_id, current, registry, repo)
    count = executor.invalidate(conn_id)
    return {"invalidated": count, "conn_id": conn_id}


@router.post("/cache/purge")
def purge_expired(
    current   = Depends(get_current_user),
    executor: QueryExecutor = Depends(get_executor),
):
    count = executor.purge_expired()
    return {"purged": count}


@router.get("/cache/stats")
def cache_stats(
    current   = Depends(get_current_user),
    executor: QueryExecutor = Depends(get_executor),
):
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    return executor.cache_stats()
