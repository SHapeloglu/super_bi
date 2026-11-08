"""
/api/users — kullanıcı oluşturma (yalnız admin). Faz 0.3: açık kayıt kapalıyken
yeni kullanıcıyı admin ekler. Rol yalnız 'admin' ya da 'viewer' olabilir.
"""
from typing import Literal

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.user_repository import UserRepository
from app.deps import get_user_repo, require_role, get_current_user, get_attr_repo

router = APIRouter()


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    role: Literal["admin", "editor", "viewer"] = "viewer"


@router.post("", status_code=201)
def create_user(
    body: UserCreate,
    # Faz 0.3: kullanıcı oluşturmak yalnız admin işi.
    current = Depends(require_role("admin")),
    repo: UserRepository = Depends(get_user_repo),
):
    """Yeni kullanıcı oluşturur (201). Kullanıcı adı alınmışsa 409 döner. Yalnız admin."""
    try:
        user = repo.create(body.username, body.password, role=body.role)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"user_id": user.user_id, "username": user.username, "role": user.role}


class AttributeIn(BaseModel):
    """Kullanıcı özniteliği değeri (ör. department = 'sales')."""
    value: str = Field(min_length=1, max_length=256)


@router.put("/{user_id}/attributes/{key}")
def set_attribute(
    user_id: str,
    key: str,
    body: AttributeIn,
    current = Depends(get_current_user),
    attr_repo = Depends(get_attr_repo),
    user_repo = Depends(get_user_repo),
):
    """Kullanıcı özniteliğini ayarlar (yalnız admin). Satır kuralları bu değeri kullanır."""
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Öznitelikleri yalnız admin ayarlayabilir")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,63}", key):
        raise HTTPException(status_code=400, detail="Geçersiz öznitelik anahtarı")
    if user_repo.get_by_id(user_id) is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    attr_repo.set(user_id, key, body.value)
    return {"user_id": user_id, "key": key, "msg": "Öznitelik kaydedildi"}
