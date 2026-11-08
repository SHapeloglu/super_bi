"""
/api/users — kullanıcı oluşturma (yalnız admin). Faz 0.3: açık kayıt kapalıyken
yeni kullanıcıyı admin ekler. Rol yalnız 'admin' ya da 'viewer' olabilir.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.user_repository import UserRepository
from app.deps import get_user_repo, require_role

router = APIRouter()


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    role: Literal["admin", "viewer"] = "viewer"


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
