"""
/api/shares — dataset, dashboard ve bağlantı paylaşımları (Faz 1.2; bağlantı: viewer bağlantı paylaşımı).

Yalnız kaynağın sahibi ya da admin paylaşım ekleyebilir, listeleyebilir ve kaldırabilir.
Alıcı bir kullanıcı (grantee_type=user) ya da bir rol (grantee_type=role) olabilir.

Bağlantı paylaşımı özeldir: yalnız kullanıcıya, yalnız 'use' izniyle, en az bir tablo listesiyle yapılır.
Alıcı bu tablolardan veri seti kurabilir; şema listesi, serbest SQL ve bağlantı bilgisi görmez.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.core.sharing import ShareRepository, ROLES
from app.deps import get_current_user, get_share_repo, get_dataset_repo, get_dash_repo, get_user_repo, get_repo, get_conn_grant_repo

router = APIRouter()


class TableRef(BaseModel):
    """Bağlantı paylaşımında izin verilen bir tablo (şemasız tablo için schema_name boş bırakılır)."""
    schema_name: Optional[str] = Field(default=None, max_length=128)
    table_name:  str = Field(min_length=1, max_length=128)


class ShareIn(BaseModel):
    resource_type: Literal["dataset", "dashboard", "connection"]
    resource_id:   str = Field(min_length=1, max_length=64)
    grantee_type:  Literal["user", "role"]
    grantee_id:    str = Field(min_length=1, max_length=64)
    permission:    Literal["read", "write", "use"]
    # Yalnız bağlantı paylaşımında kullanılır: alıcının kullanabileceği tablolar.
    tables:        list[TableRef] = []

    @model_validator(mode="after")
    def _rol_kurallari(self):
        """Rol alıcısıysa grantee_id tanımlı rollerden biri olmalı ve izin yalnız okuma olabilir."""
        if self.grantee_type == "role":
            if self.grantee_id not in ROLES:
                raise ValueError("Geçersiz rol")
            if self.permission == "write":
                raise ValueError("Rol paylaşımı yalnız okuma olabilir; yazma tek tek kullanıcıya verilir")
        return self

    @model_validator(mode="after")
    def _baglanti_kurallari(self):
        """'use' yalnız bağlantı paylaşımında; bağlantı paylaşımı yalnız kullanıcıya ve tablo listesiyle."""
        if self.resource_type == "connection":
            if self.permission != "use":
                raise ValueError("Bağlantı paylaşımının izni yalnız 'use' olabilir")
            if self.grantee_type != "user":
                raise ValueError("Bağlantı yalnız tek tek kullanıcıya paylaşılabilir")
            if not self.tables:
                raise ValueError("Bağlantı paylaşımı en az bir tablo içermeli")
        else:
            if self.permission == "use":
                raise ValueError("'use' izni yalnız bağlantı paylaşımında geçerlidir")
            if self.tables:
                raise ValueError("Tablo listesi yalnız bağlantı paylaşımında kullanılır")
        return self


def _resource_owner(resource_type: str, resource_id: str, ds_repo, dash_repo, conn_repo=None) -> Optional[str]:
    """Kaynağın sahibi; kaynak yoksa None."""
    if resource_type == "dataset":
        ds = ds_repo.get(resource_id)
        return ds.owner_id if ds else None
    if resource_type == "connection":
        meta = conn_repo.get(resource_id) if conn_repo is not None else None
        return meta.owner_id if meta else None
    dash = dash_repo.get(resource_id)
    return dash.owner_id if dash else None


def _ensure_owner(current, owner_id: Optional[str]) -> None:
    """Sahip ya da admin değilse kaynak yokmuş gibi 404 döner (varlık sızdırılmaz)."""
    if owner_id is None or (current.role != "admin" and owner_id != current.user_id):
        raise HTTPException(status_code=404, detail="Kaynak bulunamadı")


@router.post("", status_code=201)
def create_share(
    body: ShareIn,
    current = Depends(get_current_user),
    share_repo: ShareRepository = Depends(get_share_repo),
    ds_repo = Depends(get_dataset_repo),
    dash_repo = Depends(get_dash_repo),
    user_repo = Depends(get_user_repo),
    conn_repo = Depends(get_repo),
    conn_grants = Depends(get_conn_grant_repo),
):
    """Kaynağı bir kullanıcıya ya da role paylaşır. Bağlantıda 'use' + tablo listesi; diğerlerinde 'read' / 'write'. Aynı alıcı için günceller."""
    _ensure_owner(current, _resource_owner(body.resource_type, body.resource_id, ds_repo, dash_repo, conn_repo))

    if body.grantee_type == "user" and user_repo.get_by_id(body.grantee_id) is None:
        raise HTTPException(status_code=404, detail="Alıcı kullanıcı bulunamadı")

    if body.resource_type == "connection":
        if body.grantee_id == conn_repo.get(body.resource_id).owner_id:
            raise HTTPException(status_code=400, detail="Bağlantının sahibine paylaşım gerekmez")
        share_id = conn_grants.grant(
            body.resource_id, body.grantee_id,
            [(t.schema_name, t.table_name) for t in body.tables],
            created_by=current.user_id,
        )
        return {"share_id": share_id, "msg": "Bağlantı paylaşıldı"}

    share_id = share_repo.create(body.resource_type, body.resource_id, body.grantee_type,
                                 body.grantee_id, body.permission, created_by=current.user_id)
    return {"share_id": share_id, "msg": "Paylaşıldı"}


@router.get("")
def list_shares(
    resource_type: Literal["dataset", "dashboard", "connection"],
    resource_id: str,
    current = Depends(get_current_user),
    share_repo: ShareRepository = Depends(get_share_repo),
    ds_repo = Depends(get_dataset_repo),
    dash_repo = Depends(get_dash_repo),
    conn_repo = Depends(get_repo),
    conn_grants = Depends(get_conn_grant_repo),
):
    """Bir kaynağın paylaşımlarını listeler. Yalnız sahip ya da admin. Bağlantıda izinli tablolar da eklenir."""
    _ensure_owner(current, _resource_owner(resource_type, resource_id, ds_repo, dash_repo, conn_repo))
    rows = share_repo.list_for(resource_type, resource_id)
    if resource_type == "connection":
        for r in rows:
            r["tables"] = [{"schema_name": s or None, "table_name": t}
                           for s, t in conn_grants.tables_of(r["share_id"])]
    return rows


@router.delete("/{share_id}")
def delete_share(
    share_id: str,
    current = Depends(get_current_user),
    share_repo: ShareRepository = Depends(get_share_repo),
    ds_repo = Depends(get_dataset_repo),
    dash_repo = Depends(get_dash_repo),
    conn_repo = Depends(get_repo),
    conn_grants = Depends(get_conn_grant_repo),
):
    """Paylaşımı kaldırır. Yalnız sahip ya da admin."""
    share = share_repo.get(share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Paylaşım bulunamadı")
    _ensure_owner(current, _resource_owner(share["resource_type"], share["resource_id"], ds_repo, dash_repo, conn_repo))
    if share["resource_type"] == "connection":
        conn_grants.revoke(share_id)
    else:
        share_repo.delete(share_id)
    return {"msg": "Paylaşım kaldırıldı"}
