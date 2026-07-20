"""
/api/drivers — lazy driver installation
YENİDEN OLUŞTURULDU: main.py'de include_router(drivers.router, ...) referansı
var ama dosya bulunamadığı için kullanım şekli oradan çıkarıldı.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.core.connector_registry import ConnectorRegistry
from app.deps import get_registry, get_current_user

router = APIRouter()


@router.get("")
def list_drivers(
    current  = Depends(get_current_user),
    registry: ConnectorRegistry = Depends(get_registry),
):
    return registry.list_drivers()


@router.post("/{db_type}/install")
def install_driver(
    db_type: str,
    current  = Depends(get_current_user),
    registry: ConnectorRegistry = Depends(get_registry),
):
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Driver kurulumu için admin yetkisi gerekli")

    ok, msg = registry.install_driver(db_type)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"db_type": db_type, "installed": True, "message": msg}
