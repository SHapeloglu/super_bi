"""
deps.py — Dependency Injection
Tüm servisler buradan Depends() ile alınır.
"""
from __future__ import annotations

from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.connector_registry import ConnectorRegistry
from app.core.crypto import decrypt_password
from app.core.repository import (
    ConnectionRepository, DashboardRepository, QueryHistoryRepository, DatasetRepository,
)
from app.db.sqlite_store import SQLiteStore
from app.services.query_executor import QueryExecutor

# ── App state bağımlılıkları ───────────────────────────────────────

def get_store(req: Request)     -> SQLiteStore:            return req.app.state.store
def get_registry(req: Request)  -> ConnectorRegistry:      return req.app.state.registry
def get_repo(req: Request)      -> ConnectionRepository:   return req.app.state.repo
def get_dash_repo(req: Request) -> DashboardRepository:    return req.app.state.dash_repo
def get_hist_repo(req: Request) -> QueryHistoryRepository: return req.app.state.hist_repo
def get_dataset_repo(req: Request) -> DatasetRepository:   return req.app.state.dataset_repo
def get_executor(req: Request)  -> QueryExecutor:          return req.app.state.executor

def get_user_repo(req: Request):
    from app.auth.user_repository import UserRepository
    return UserRepository(req.app.state.store)

# ── Auth ───────────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)

def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
):
    """
    Bearer token'ı çözer → TokenData döner.
    Token yoksa veya geçersizse 401.

    Optional kullanım için: Depends(get_current_user_optional)
    """
    if not creds:
        raise HTTPException(
            status_code=401,
            detail="Kimlik doğrulama gerekli",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        from app.auth.jwt_core import parse_token
        return parse_token(creds.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_user_optional(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
):
    """Token varsa çöz, yoksa None döner — public endpoint'ler için."""
    if not creds:
        return None
    try:
        from app.auth.jwt_core import parse_token
        return parse_token(creds.credentials)
    except ValueError:
        return None

def require_role(*roles: str):
    """Belirli rol gerektiren endpoint'ler için factory."""
    def _check(current=Depends(get_current_user)):
        if current.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Bu işlem için {' veya '.join(roles)} yetkisi gerekli",
            )
        return current
    return _check

# ── Bağlantı guard ────────────────────────────────────────────────
#
# İki farklı kullanım şekli var, kasıtlı olarak ayrılmıştır:
#
#  1) get_connection_engine  → conn_id URL/path'ten gelir (örn. GET
#     /api/connections/{conn_id}/test gibi conn_id zaten path param'ı
#     olan endpoint'ler için FastAPI Depends() ile kullanılır).
#
#  2) resolve_connection_engine → conn_id request BODY'sinden gelir
#     (örn. QueryRunRequest.conn_id). Bunu Depends() olarak DEĞİL,
#     endpoint içinde body doğrulandıktan sonra elle çağırın:
#         engine, meta = resolve_connection_engine(body.conn_id, current, registry, repo)
#
#     ÖNEMLİ: /api/query/run ve /api/query/stream gibi endpoint'lerde
#     eskiden get_connection_engine hem Depends() ile ayrı bir
#     conn_id sorgu parametresi bekliyor hem de body.conn_id ayrıca
#     executor'a geçiriliyordu. Bu iki değer birbirinden BAĞIMSIZDI:
#     kullanıcı kendi sahip olduğu bir conn_id'yi query param'da geçip
#     auth'u geçiyor, ama body.conn_id'yi doğrulanmamış başka bir
#     değere set edebiliyordu — cache/history kayıtları o doğrulanmamış
#     conn_id'ye yazılıyordu. resolve_connection_engine bu sınıfın
#     tekrarını önler: TEK conn_id kaynağı (body) üzerinden hem auth
#     kontrolü yapılır hem de engine döner, ayrı bir query param'a
#     gerek kalmaz.

def _load_engine_for_owner(
    conn_id:  str,
    current,
    registry: ConnectorRegistry,
    repo:     ConnectionRepository,
):
    """Ortak mantık: conn_id + sahiplik kontrolü + engine lookup."""
    try:
        if current.role == "admin":
            meta = repo.get_or_raise(conn_id)
        else:
            meta = repo.get_owned_or_raise(conn_id, current.user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={
            "msg":    "Bağlantı bulunamadı.",
            "action": "POST /api/connections ile yeniden bağlanın.",
        })

    engine = registry._engines.get(conn_id)

    if engine is None:
        # Servis restart sonrası engine bellekten silinmiş olabilir — şifre
        # (varsa) diskte ŞİFRELİ olarak duruyor (bkz. app.core.crypto),
        # burada çözülüp otomatik yeniden bağlanmayı deniyoruz. SQLite gibi
        # şifresiz bağlantılarda decrypt_password zaten None döner, sorun
        # olmaz. Şifre çözülemezse (anahtar değişmiş vb.) engine None kalır
        # ve normal 410 hatasına düşer — kullanıcı elle yeniden bağlanır.
        try:
            engine = registry.get_engine(conn_id, meta.db_type, {
                "host": meta.host, "port": meta.port, "database": meta.database,
                "user": meta.user, "password": decrypt_password(meta.password_enc),
            })
        except Exception:
            engine = None

    if engine is None:
        raise HTTPException(status_code=410, detail={
            "msg":    "Engine yok — sunucu yeniden başlamış olabilir.",
            "action": "POST /api/connections ile yeniden bağlanın.",
        })
    return engine, meta


def get_connection_engine(
    conn_id:  str,
    current  = Depends(get_current_user),
    registry: ConnectorRegistry    = Depends(get_registry),
    repo:     ConnectionRepository = Depends(get_repo),
):
    """
    conn_id PATH/QUERY parametresinden gelir (Depends() ile kullanılır).
    conn_id geçerli VE bu kullanıcıya ait mi kontrolü.
    admin rolü herkesin bağlantısını kullanabilir.
    Başkasının bağlantısı için 404 döner (var olduğunu sızdırmaz).
    """
    return _load_engine_for_owner(conn_id, current, registry, repo)


def resolve_connection_engine(
    conn_id:  str,
    current,
    registry: ConnectorRegistry,
    repo:     ConnectionRepository,
):
    """
    conn_id'yi BODY'den (ör. body.conn_id) elle iletmek için — Depends()
    olarak kullanmayın. Aynı sahiplik kontrolünü tek bir conn_id kaynağı
    üzerinden yapar, böylece "path conn_id ile body conn_id farklı olabilir"
    sınıfı hatalara kapatır.
    """
    return _load_engine_for_owner(conn_id, current, registry, repo)
