"""
DataLens Backend — FastAPI

GÜNCELLENDİ: auth router + user_repo eklendi. Eski main.py'de bu router
hiç include edilmemişti — get_current_user JWT bekliyor ama token üretecek
bir login endpoint'i yoktu, bu güncellemeyle o eksiklik kapatıldı.
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.auth.user_repository import UserRepository
from app.core.connector_registry import ConnectorRegistry
from app.core.repository import (
    ConnectionRepository,
    DashboardRepository,
    QueryHistoryRepository,
    DatasetRepository,
)
from app.db.sqlite_store import SQLiteStore
from app.services.query_executor import QueryExecutor

logger = logging.getLogger(__name__)

DATALENS_DB = os.environ.get("DATALENS_DB", "/tmp/datalens.db")

# CORS origin'leri env'den okunur; verilmezse geliştirme varsayılanları kullanılır.
_default_origins = "http://localhost:3000,http://localhost:5173"
CORS_ORIGINS = [
    o.strip() for o in os.environ.get("DATALENS_CORS_ORIGINS", _default_origins).split(",")
    if o.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Başlangıç ──────────────────────────────────────────────────
    store = SQLiteStore(DATALENS_DB)           # tek SQLite bağlantısı

    app.state.store     = store
    app.state.registry  = ConnectorRegistry()
    app.state.repo      = ConnectionRepository(store)
    app.state.dash_repo = DashboardRepository(store)
    app.state.hist_repo = QueryHistoryRepository(store)
    app.state.dataset_repo = DatasetRepository(store)
    app.state.user_repo = UserRepository(store)
    app.state.executor  = QueryExecutor()

    logger.info("DataLens başlatıldı — DB: %s", DATALENS_DB)
    yield

    # ── Kapanış ────────────────────────────────────────────────────
    app.state.registry.dispose_all()
    app.state.store.close()
    logger.info("DataLens kapatıldı")


app = FastAPI(
    title="DataLens API",
    description="Dynamic BI backend — lazy driver, live/memory, commit pattern",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handler — stack trace kullanıcıya dönmez ──────

@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_handler(request: Request, exc: SQLAlchemyError):
    logger.error("SQLAlchemyError %s: %s", request.url, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Veritabanı hatası — bağlantı ayarlarını kontrol edin."},
    )


@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception):
    logger.error("Unhandled %s: %s", request.url, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Beklenmeyen hata."},
    )


# ── Router'lar ──────────────────────────────────────────────────────

from app.api import auth, connections, drivers, schema, query, dashboard, history, datasets  # noqa: E402

app.include_router(auth.router,        prefix="/api/auth",       tags=["auth"])
app.include_router(drivers.router,     prefix="/api/drivers",    tags=["drivers"])
app.include_router(connections.router, prefix="/api/connections",tags=["connections"])
app.include_router(schema.router,      prefix="/api/schema",     tags=["schema"])
app.include_router(query.router,       prefix="/api/query",      tags=["query"])
app.include_router(dashboard.router,   prefix="/api/dashboards", tags=["dashboards"])
app.include_router(history.router,     prefix="/api/history",    tags=["history"])
app.include_router(datasets.router,    prefix="/api/datasets",   tags=["datasets"])


@app.get("/api/health", tags=["health"])
def health():
    return {
        "status":  "ok",
        "version": "0.2.0",
        "db":      DATALENS_DB,
    }
