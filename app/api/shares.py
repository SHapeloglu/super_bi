"""
/api/shares — dataset ve dashboard paylaşımları (Faz 1.2).

Yalnız kaynağın sahibi ya da admin paylaşım ekleyebilir, listeleyebilir ve kaldırabilir.
Alıcı bir kullanıcı (grantee_type=user) ya da bir rol (grantee_type=role) olabilir.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.core.sharing import ShareRepository, ROLES
from app.deps import get_current_user, get_share_repo, get_dataset_repo, get_dash_repo, get_user_repo

router = APIRouter()


class ShareIn(BaseModel):
    resource_type: Literal["dataset", "dashboard"]
    resource_id:   str = Field(min_length=1, max_length=64)
    grantee_type:  Literal["user", "role"]
    grantee_id:    str = Field(min_length=1, max_length=64)
    permission:    Literal["read", "write"]

    @model_validator(mode="after")
    def _rol_gecerli_mi(self):
        """Rol alıcısıysa grantee_id tanımlı rollerden biri olmalı."""
        if self.grantee_type == "role" and self.grantee_id not in ROLES:
            raise ValueError("Geçersiz rol")
        return self


def _resource_owner(resource_type: str, resource_id: str, ds_repo, dash_repo) -> Optional[str]:
    """Kaynağın sahibi; kaynak yoksa None."""
    if resource_type == "dataset":
        ds = ds_repo.get(resource_id)
        return ds.owner_id if ds else None
    dash = dash_repo.get(resource_id)
    return dash.owner_id if dash else None


def _ensure_owner(current, owner_id: Optional[str]) -> None:
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Kaynak bulunamadı")
    if current.role != "admin" and owner_id != current.user_id:
        raise HTTPException(status_code=403, detail="Paylaşımı yalnız sahip ya da admin yönetebilir")


@router.post("", status_code=201)
def create_share(
    body: ShareIn,
    current = Depends(get_current_user),
    share_repo: ShareRepository = Depends(get_share_repo),
    ds_repo = Depends(get_dataset_repo),
    dash_repo = Depends(get_dash_repo),
    user_repo = Depends(get_user_repo),
):
    """Kaynağı bir kullanıcıya ya da role 'read' / 'write' izniyle paylaşır. Aynı alıcı için izni günceller."""
    _ensure_owner(current, _resource_owner(body.resource_type, body.resource_id, ds_repo, dash_repo))

    if body.grantee_type == "user" and user_repo.get_by_id(body.grantee_id) is None:
        raise HTTPException(status_code=404, detail="Alıcı kullanıcı bulunamadı")

    share_id = share_repo.create(body.resource_type, body.resource_id, body.grantee_type,
                                 body.grantee_id, body.permission, created_by=current.user_id)
    return {"share_id": share_id, "msg": "Paylaşıldı"}


@router.get("")
def list_shares(
    resource_type: Literal["dataset", "dashboard"],
    resource_id: str,
    current = Depends(get_current_user),
    share_repo: ShareRepository = Depends(get_share_repo),
    ds_repo = Depends(get_dataset_repo),
    dash_repo = Depends(get_dash_repo),
):
    """Bir kaynağın paylaşımlarını listeler. Yalnız sahip ya da admin."""
    _ensure_owner(current, _resource_owner(resource_type, resource_id, ds_repo, dash_repo))
    return share_repo.list_for(resource_type, resource_id)


@router.delete("/{share_id}")
def delete_share(
    share_id: str,
    current = Depends(get_current_user),
    share_repo: ShareRepository = Depends(get_share_repo),
    ds_repo = Depends(get_dataset_repo),
    dash_repo = Depends(get_dash_repo),
):
    """Paylaşımı kaldırır. Yalnız sahip ya da admin."""
    share = share_repo.get(share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Paylaşım bulunamadı")
    _ensure_owner(current, _resource_owner(share["resource_type"], share["resource_id"], ds_repo, dash_repo))
    share_repo.delete(share_id)
    return {"msg": "Paylaşım kaldırıldı"}
