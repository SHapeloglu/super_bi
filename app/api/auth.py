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
import os

from fastapi import APIRouter, Depends, HTTPException

from app.auth.jwt_core import create_token
from app.auth.user_repository import UserRepository
from app.deps import get_user_repo
from app.models.schemas import TokenResponse, UserLogin, UserRegister

router = APIRouter()


def _registration_open(repo: UserRepository) -> bool:
    """Kayıt açık mı? Boş sistemde (bootstrap) her zaman; aksi halde yalnız DATALENS_ALLOW_REGISTER=true ise."""
    if repo.count() == 0:
        return True
    return os.environ.get("DATALENS_ALLOW_REGISTER", "false").strip().lower() == "true"


@router.get("/registration")
def registration_status(repo: UserRepository = Depends(get_user_repo)):
    """Arayüz için: kayıt formu gösterilsin mi? Kimlik gerektirmez; yalnız açık/kapalı bilgisi döner."""
    return {"open": _registration_open(repo)}


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(
    body: UserRegister,
    repo: UserRepository = Depends(get_user_repo),
):
    # İlk kayıt admin olur (ilk kurulumda giriş yapacak kimse kalmasın diye). Rol, kaydın eklendiği
    # tek SQL içinde belirlenir (repo.create); bu sayede aynı anda gelen iki ilk kayıt da admin olamaz.
    """
    Yeni kullanıcı kaydı (201). İlk kullanıcı admin, sonrakiler viewer rolüyle açılır. Kullanıcı adı alınmışsa 409 döner.
    Başarılıysa hemen token döner; ayrıca giriş yapılması gerekmez.
    """
    # Faz 0.3: açık kayıt varsayılan olarak kapalı. Sistemde kullanıcı varken yeni kayıt yalnız
    # DATALENS_ALLOW_REGISTER=true ise kabul edilir; yeni kullanıcıyı admin POST /api/users ile ekler.
    # Boş sistemde (bootstrap) ilk kayıt her zaman açıktır.
    if not _registration_open(repo):
        raise HTTPException(status_code=403, detail="Kayıt kapalı; kullanıcıyı yönetici oluşturmalı")

    try:
        user = repo.create(body.username, body.password)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # JWT token: kullanıcı kimliği, adı ve rolünü taşır; sonraki isteklerde Authorization başlığıyla gönderilir.
    token = create_token(user.user_id, user.username, user.role)
    return TokenResponse(access_token=token, role=user.role, user_id=user.user_id)


@router.post("/login", response_model=TokenResponse)
def login(
    body: UserLogin,
    repo: UserRepository = Depends(get_user_repo),
):
    """Kullanıcı adı ve şifreyle giriş yapar. Başarılıysa JWT token döner; hatalıysa 401 döner."""
    user = repo.authenticate(body.username, body.password)
    # Kullanıcı adı yanlış ya da şifre yanlışsa aynı mesaj döner; böylece hangi kullanıcı adlarının var olduğu anlaşılmaz.
    if user is None:
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı")

    token = create_token(user.user_id, user.username, user.role)
    return TokenResponse(access_token=token, role=user.role, user_id=user.user_id)
