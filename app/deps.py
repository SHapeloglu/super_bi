"""deps.py — Dependency Injection (bağımlılık enjeksiyonu)
Tüm servisler buradan Depends() ile alınır.
Endpoint'ler ihtiyaç duyduğu nesneleri (repository, engine, kullanıcı) bu fonksiyonlarla ister.
JWT ile kullanıcı kimliği ve bağlantı sahipliği kontrolleri de burada yapılır.
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

# Aşağıdaki tek satırlık fonksiyonlar app.state'e konmuş nesneyi (store, repo vb.) FastAPI Depends() ile endpoint'e verir.
# get_store: Ana SQLite deposunu döner.
def get_store(req: Request)     -> SQLiteStore:            return req.app.state.store
# get_registry: Dış veritabanı bağlantı motorlarını (engine) yöneten kayıt defterini döner.
def get_registry(req: Request)  -> ConnectorRegistry:      return req.app.state.registry
# get_repo: Bağlantı bilgisi (metadata) repository'sini döner.
def get_repo(req: Request)      -> ConnectionRepository:   return req.app.state.repo
# get_dash_repo: Dashboard repository'sini döner.
def get_dash_repo(req: Request) -> DashboardRepository:    return req.app.state.dash_repo
# get_hist_repo: Sorgu geçmişi repository'sini döner.
def get_hist_repo(req: Request) -> QueryHistoryRepository: return req.app.state.hist_repo
# get_dataset_repo: Dataset (kayıtlı sorgu) repository'sini döner.
def get_dataset_repo(req: Request) -> DatasetRepository:   return req.app.state.dataset_repo
# get_share_repo: Paylaşım (shares) repository'sini döner (Faz 1.2).
def get_share_repo(req: Request):
    return req.app.state.share_repo
# get_rls_repo / get_attr_repo: satır kuralları ve kullanıcı öznitelikleri (Faz 1.3).
def get_rls_repo(req: Request):
    return req.app.state.rls_repo
def get_attr_repo(req: Request):
    return req.app.state.attr_repo
# get_executor: Sorgu çalıştırıcı ve cache nesnesini döner.
def get_executor(req: Request)  -> QueryExecutor:          return req.app.state.executor

def get_user_repo(req: Request):
    """
    Kullanıcı tablosu işlemleri için UserRepository nesnesi üretir.
    Import fonksiyon içinde yapılmış; döngüsel import'u önlemek için olabilir.
    """
    from app.auth.user_repository import UserRepository
    return UserRepository(req.app.state.store)

# ── Auth ───────────────────────────────────────────────────────────

# auto_error=False: Token yoksa FastAPI kendi 403 hatasını üretmesin; biz 401 mesajını kendimiz veriyoruz.
_bearer = HTTPBearer(auto_error=False)

def get_current_user(
    req: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
):
    """
    Bearer token'ı çözer → TokenData döner. Rol HER İSTEKTE veritabanından okunur: token süresi
    dolmadan düşürülen ya da silinen kullanıcı hemen etkisiz olur. Token yoksa, geçersizse
    ya da kullanıcı yoksa 401.

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
        data = parse_token(creds.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    users = req.app.state.user_repo
    kayit = users.get_by_id(data.user_id)
    if kayit is None:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı",
                            headers={"WWW-Authenticate": "Bearer"})
    data.role = kayit.role
    return data

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
        """
        require_role'ün iç fonksiyonu. Giriş yapmış kullanıcının rolünü kontrol eder.
        Rol izin verilenler arasında değilse 403, değilse kullanıcı bilgisini döner.
        """
        if current.role not in roles:
            # 403 Forbidden: kullanıcı giriş yapmış ama bu işlem için yetkisi yok.
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
        # Admin tüm bağlantılara erişebilir; sahiplik kontrolü atlanır.
        if current.role == "admin":
            meta = repo.get_or_raise(conn_id)
        else:
            meta = repo.get_owned_or_raise(conn_id, current.user_id)
    except KeyError:
        # Bağlantı yok ya da başkasına ait ise aynı 404 döner; varlığı sızdırılmaz.
        raise HTTPException(status_code=404, detail={
            "msg":    "Bağlantı bulunamadı.",
            "action": "POST /api/connections ile yeniden bağlanın.",
        })

    # Önce bellekteki (registry) engine'e bakılır. _engines özel bir alandır ama burada doğrudan okunur.
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
                # Şifre diskte şifreli tutulur; burada çözülüp engine kurulumuna verilir. Çözülen değer loglanmaz.
                "user": meta.user, "password": decrypt_password(meta.password_enc),
            })
        # DİKKAT: Yeniden bağlanma sırasındaki tüm hatalar sessizce yutulur (engine None olur). Nedenini görmek için log eklenebilir.
        except Exception:
            engine = None

    if engine is None:
        # 410 Gone: bağlantı kaydı DB'de var ama bellekteki engine yok (sunucu yeniden başlamış olabilir). Kullanıcı yeniden bağlanmalı.
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
