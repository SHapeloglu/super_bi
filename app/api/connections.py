"""/api/connections — veritabanı bağlantısı oluşturma, test etme, listeleme ve silme.
Şifre yalnız şifreli hali ile saklanır (app.core.crypto). Canlı engine app.core.connector_registry'de tutulur.
Kimlik ve sahiplik kontrolleri app.deps'te yapılır.
"""
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from sqlalchemy import inspect, text

from app.core.connector_registry import ConnectorRegistry
from app.core.host_policy import HostPolicyError
from app.core.sqlite_policy import SQLitePolicyError
from app.core.repository import ConnectionMeta, ConnectionRepository
from app.core.crypto import encrypt_password
from app.deps import get_registry, get_repo, get_current_user, require_role, resolve_connection_engine, resolve_dataset_connection, get_conn_grant_repo
from app.models.schemas import ConnectionParams, ConnectionResponse, ConnectionTest

router = APIRouter()


@router.post("", response_model=ConnectionResponse)
def create_connection(
    params:   ConnectionParams,
    # Faz 0.2: bağlantı oluşturmak yalnız admin işi (viewer SQLite/ağ erişimi açamaz).
    current                       = Depends(require_role("admin")),
    registry: ConnectorRegistry    = Depends(get_registry),
    repo:     ConnectionRepository = Depends(get_repo),
):
    # Sürücü kurulu değilse 409 döner; istemci /api/drivers/.../install ile kurulum isteyebilir.
    """
    Yeni veritabanı bağlantısı oluşturur (201 değil, varsayılan 200). Sürücü kurulu değilse 409, bağlantı testi başarısızsa 400 döner.
    Başarılıysa bağlantı bilgileri kaydedilir; şifre yalnız şifreli hali ile yazılır. Dönüş: conn_id ve durum.
    """
    if not registry.driver_installed(params.db_type):
        raise HTTPException(status_code=409, detail={
            "msg":    f"{params.db_type} driver kurulu değil",
            "action": f"POST /api/drivers/{params.db_type}/install",
        })

    # Bağlantı kimliği: UUID'nin ilk 8 karakteri.
    conn_id = str(uuid.uuid4())[:8]
    raw_params = {
        "host":        params.host,
        "port":        params.port,
        "database":    params.database,
        "user":        params.user,
        # Şifre bu aşamada yalnız test ve bağlantı kurmak için düz metin kullanılır; kalıcı kayda düz metin yazılmaz.
        "password":    params.get_password(),
        "schema_name": params.schema_name,
    }

    # Engine kurulur ve test edilir. Kurulum sırasındaki hatalar 400 olarak döner.
    try:
        engine = registry.get_engine(conn_id, params.db_type, raw_params)
        ok, msg = registry.test_connection(engine)
    except (HostPolicyError, SQLitePolicyError) as e:
        # Politika mesajları sabit ve güvenli metinlerdir; kullanıcıya gösterilebilir.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Faz 0.4: ham hata metni kullanıcıya gitmez; sunucu logunda kalır.
        logging.getLogger(__name__).warning("Bağlantı oluşturma hatası: %s", e)
        raise HTTPException(status_code=400, detail="Bağlantı kurulamadı")

    # Test başarısızsa geçici engine kapatılır ve hiçbir kayıt yapılmaz.
    if not ok:
        registry.remove_engine(conn_id)
        raise HTTPException(status_code=400, detail=msg)

    # Bağlantı başarılıysa yalnız metadata kaydedilir.
    repo.save(ConnectionMeta(
        conn_id=conn_id, owner_id=current.user_id,
        db_type=params.db_type, host=params.host, database=params.database,
        port=params.port, user=params.user,
        # Şifre şifrelenerek saklanır (bkz. app/core/crypto.py).
        password_enc=encrypt_password(params.get_password()),
        schema_name=params.schema_name,
    ))

    return ConnectionResponse(
        conn_id=conn_id, db_type=params.db_type,
        host=params.host, database=params.database,
        status="connected", message=msg,
    )


@router.get("/{conn_id}/test", response_model=ConnectionTest)
def test_connection(
    conn_id: str,
    current                    = Depends(get_current_user),
    registry: ConnectorRegistry = Depends(get_registry),
    repo:     ConnectionRepository = Depends(get_repo),
):
    # resolve_connection_engine artık şifrelenmiş şifreyle otomatik yeniden
    # bağlanmayı deniyor (bkz. deps.py) — bu yüzden burada artık "engine
    # yoksa 410" demek yerine, önce yeniden bağlanmayı deniyoruz.
    """
    Kayıtlı bir bağlantının canlı testini yapar ve gecikme süresini milisaniye olarak döner.
    Test başarılıysa son kullanım zamanı güncellenir.
    """
    engine, meta = resolve_connection_engine(conn_id, current, registry, repo)

    import time
    t0 = time.perf_counter()
    ok, msg = registry.test_connection(engine)
    ms = (time.perf_counter() - t0) * 1000
    if ok:
        # Başarılı testte son kullanım zamanı güncellenir.
        repo.touch(conn_id)
    return ConnectionTest(success=ok, message=msg, latency_ms=round(ms, 2))


@router.get("")
def list_connections(
    current = Depends(get_current_user),
    repo: ConnectionRepository = Depends(get_repo),
    conn_grants = Depends(get_conn_grant_repo),
):
    """
    admin → herkesinkini görür; diğerleri → yalnız kendi bağlantıları.
    Kendisine 'use' ile paylaşılan bağlantılar için GET /api/connections/shared kullanılır.
    """
    owner = None if current.role == "admin" else current.user_id
    rows = [
        {"conn_id": m.conn_id, "owner_id": m.owner_id, "db_type": m.db_type,
         "host": m.host, "database": m.database, "user": m.user,
         "name": m.name, "created_at": m.created_at, "last_used_at": m.last_used_at}
        for m in repo.list_all(owner_id=owner)
    ]
    return rows


@router.get("/shared")
def list_shared_connections(
    current = Depends(get_current_user),
    repo: ConnectionRepository = Depends(get_repo),
    conn_grants = Depends(get_conn_grant_repo),
):
    """
    Kullanıcıya 'use' ile paylaşılan bağlantılar ve bu bağlantıda veri seti kurabileceği tablolar.
    Host, kullanıcı, veritabanı ve parola dönmez; admin için de bu uç yalnız paylaşılanları listeler.
    """
    out = []
    for cid in conn_grants.shared_conn_ids(current.user_id):
        m = repo.get(cid)
        if m is None:
            continue
        out.append({
            "conn_id": m.conn_id, "db_type": m.db_type, "name": m.name,
            "tables": [{"schema_name": s or None, "table_name": t}
                       for s, t in sorted(conn_grants.allowed_tables_list(cid, current.user_id))],
        })
    return out


@router.get("/shared/{conn_id}/tables/{table_name}/columns")
def list_shared_columns(
    conn_id:    str,
    table_name: str,
    schema: Optional[str] = None,
    current = Depends(get_current_user),
    registry: ConnectorRegistry = Depends(get_registry),
    repo:     ConnectionRepository = Depends(get_repo),
    conn_grants = Depends(get_conn_grant_repo),
):
    """
    Alıcının paylaşılan bağlantısındaki İZİNLİ bir tablonun kolonları. İzinsiz tablo ya da paylaşılmamış bağlantı 404.
    Bağlantı, alıcının kendi kimliğiyle değil, paylaşımın yetkisiyle açılır (yalnız kolon adı/tipi döner).
    """
    allowed = conn_grants.allowed_tables(conn_id, current.user_id)
    if allowed is None or (schema or "", table_name) not in allowed:
        raise HTTPException(status_code=404, detail="Tablo bulunamadı")
    engine, _meta = resolve_dataset_connection(conn_id, current.user_id, registry, repo, conn_grants)
    try:
        insp = inspect(engine)
        if table_name not in insp.get_table_names(schema=schema):
            raise HTTPException(status_code=404, detail="Tablo bulunamadı")
        cols = insp.get_columns(table_name, schema=schema)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Şema okunamadı")
    return {
        "table": table_name,
        "columns": [{"name": c["name"], "type": str(c["type"]), "nullable": c.get("nullable", True)} for c in cols],
    }


@router.delete("/{conn_id}")
def delete_connection(
    conn_id:  str,
    # Faz 0.2: silme de yalnız admin (sahip olsa bile viewer silemez).
    current                    = Depends(require_role("admin")),
    registry: ConnectorRegistry    = Depends(get_registry),
    repo:     ConnectionRepository = Depends(get_repo),
    conn_grants = Depends(get_conn_grant_repo),
):
    """
    Bağlantıyı siler. Yalnız admin yapabilir. Bulunamazsa 404 döner.
    Silinince bellekteki engine de kapatılır.
    """
    deleted = repo.delete(conn_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")

    # Kayıt silindikten sonra bellekteki bağlantı havuzu da kapatılır.
    # Bağlantının paylaşımları ve izinli tablo listeleri de kaldırılır.
    conn_grants.delete_for_connection(conn_id)
    registry.remove_engine(conn_id)
    return {"msg": f"{conn_id} silindi"}
