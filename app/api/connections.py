"""
/api/connections — auth bağlı, owner_id kontrollü
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.core.connector_registry import ConnectorRegistry
from app.core.repository import ConnectionMeta, ConnectionRepository
from app.core.crypto import encrypt_password
from app.deps import get_registry, get_repo, get_current_user, resolve_connection_engine
from app.models.schemas import ConnectionParams, ConnectionResponse, ConnectionTest

router = APIRouter()


@router.post("", response_model=ConnectionResponse)
def create_connection(
    params:   ConnectionParams,
    current                       = Depends(get_current_user),
    registry: ConnectorRegistry    = Depends(get_registry),
    repo:     ConnectionRepository = Depends(get_repo),
):
    if not registry.driver_installed(params.db_type):
        raise HTTPException(status_code=409, detail={
            "msg":    f"{params.db_type} driver kurulu değil",
            "action": f"POST /api/drivers/{params.db_type}/install",
        })

    conn_id = str(uuid.uuid4())[:8]
    raw_params = {
        "host":        params.host,
        "port":        params.port,
        "database":    params.database,
        "user":        params.user,
        "password":    params.get_password(),
        "schema_name": params.schema_name,
    }

    try:
        engine = registry.get_engine(conn_id, params.db_type, raw_params)
        ok, msg = registry.test_connection(engine)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not ok:
        registry.remove_engine(conn_id)
        raise HTTPException(status_code=400, detail=msg)

    repo.save(ConnectionMeta(
        conn_id=conn_id, owner_id=current.user_id,
        db_type=params.db_type, host=params.host, database=params.database,
        port=params.port, user=params.user,
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
    engine, meta = resolve_connection_engine(conn_id, current, registry, repo)

    import time
    t0 = time.perf_counter()
    ok, msg = registry.test_connection(engine)
    ms = (time.perf_counter() - t0) * 1000
    if ok:
        repo.touch(conn_id)
    return ConnectionTest(success=ok, message=msg, latency_ms=round(ms, 2))


@router.get("")
def list_connections(
    current = Depends(get_current_user),
    repo: ConnectionRepository = Depends(get_repo),
):
    """admin → herkesinkini görür, diğerleri → sadece kendisininkini."""
    owner = None if current.role == "admin" else current.user_id
    return [
        {"conn_id": m.conn_id, "owner_id": m.owner_id, "db_type": m.db_type,
         "host": m.host, "database": m.database, "user": m.user,
         "name": m.name, "created_at": m.created_at, "last_used_at": m.last_used_at}
        for m in repo.list_all(owner_id=owner)
    ]


@router.delete("/{conn_id}")
def delete_connection(
    conn_id:  str,
    current                    = Depends(get_current_user),
    registry: ConnectorRegistry    = Depends(get_registry),
    repo:     ConnectionRepository = Depends(get_repo),
):
    if current.role == "admin":
        deleted = repo.delete(conn_id)
    else:
        deleted = repo.delete_owned(conn_id, current.user_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")

    registry.remove_engine(conn_id)
    return {"msg": f"{conn_id} silindi"}
