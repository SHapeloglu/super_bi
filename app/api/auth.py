"""
/api/auth — kayıt + giriş
YENİDEN OLUŞTURULDU: main.py'nin eski (auth öncesi) versiyonunda bu router
hiç include edilmemişti — ama get_current_user JWT bekliyor, dolayısıyla
token üretecek bir login endpoint'i olmak zorunda. Bu dosya o eksikliği
kapatmak için eklendi.

İlk kullanıcı otomatik admin olur (bootstrap) — sıfırdan kurulan bir
sistemde giriş yapacak hiç kimse olmaması sorununu çözer. Sonraki kayıtlar
'viewer' rolüyle açılır, admin gerekirse sonradan DB'de rolünü değiştirir.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.auth.jwt_core import create_token
from app.auth.user_repository import UserRepository
from app.deps import get_user_repo
from app.models.schemas import TokenResponse, UserLogin, UserRegister

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(
    body: UserRegister,
    repo: UserRepository = Depends(get_user_repo),
):
    role = "admin" if repo.count() == 0 else "viewer"
    try:
        user = repo.create(body.username, body.password, role=role)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    token = create_token(user.user_id, user.username, user.role)
    return TokenResponse(access_token=token, role=user.role, user_id=user.user_id)


@router.post("/login", response_model=TokenResponse)
def login(
    body: UserLogin,
    repo: UserRepository = Depends(get_user_repo),
):
    user = repo.authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı")

    token = create_token(user.user_id, user.username, user.role)
    return TokenResponse(access_token=token, role=user.role, user_id=user.user_id)
