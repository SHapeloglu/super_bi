"""/api/dashboards — dashboard (rapor sayfası) uç noktaları.
Admin tüm dashboard'ları görebilir; diğer kullanıcılar sadece kendininkileri.
Veri katmanı: app.core.repository.DashboardRepository. Kimlik: app.deps.get_current_user.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.core.repository import Dashboard, DashboardObj, DashboardRepository
from app.deps import get_dash_repo, get_current_user

router = APIRouter()


class DashboardObjIn(BaseModel):
    """Frontend'den gelen tek bir grafik objesi. x, y, w, h değerleri mm cinsinden konum ve boyuttur."""
    id:       str
    type:     str
    x:        float
    y:        float
    w:        float
    h:        float
    title:    str             = ""
    # Bu grafiğin bağlı olduğu sorgunun (dataset) kimliği. Bağlı değilse boş kalır.
    query_id: Optional[str]  = None
    # Varsayılan grafik rengi: mavi (hex kodu).
    color:    str             = "#378ADD"


class DashboardIn(BaseModel):
    """Dashboard oluşturma / güncelleme isteği: ad, sayfa boyutu ve grafik objeleri listesi."""
    name:      str
    # Sayfa boyutu adı; a4l = A4 yatay (297 x 210 mm).
    scale:     str   = "a4l"
    page_w_mm: float = 297.0
    page_h_mm: float = 210.0
    objects:   list[DashboardObjIn] = []


@router.post("", status_code=201)
def create_dashboard(
    body: DashboardIn,
    current = Depends(get_current_user),
    repo: DashboardRepository = Depends(get_dash_repo),
):
    """
    Yeni dashboard oluşturur (201). Kimlik olarak UUID'nin ilk 8 karakteri kullanılır.
    Dönüş: dashboard_id, ad ve mesaj.
    """
    # Kısa, URL'de rahat kullanılan kimlik (8 karakter). Çakışma olasılığı düşüktür ama sıfır değildir.
    dash_id = str(uuid.uuid4())[:8]
    dash = Dashboard(
        dashboard_id=dash_id, owner_id=current.user_id, name=body.name,
        scale=body.scale, page_w_mm=body.page_w_mm, page_h_mm=body.page_h_mm,
        # Gelen istek modelleri (DashboardObjIn) iç veri modeline (DashboardObj) çevrilir.
        objects=[DashboardObj(**o.model_dump()) for o in body.objects],
    )
    repo.save(dash)
    return {"dashboard_id": dash_id, "name": dash.name, "msg": "Kaydedildi"}


@router.put("/{dashboard_id}")
def update_dashboard(
    dashboard_id: str,
    body: DashboardIn,
    current = Depends(get_current_user),
    repo: DashboardRepository = Depends(get_dash_repo),
):
    # Sahiplik kontrolü
    """
    Var olan dashboard'u günceller. Admin herkesinkini, diğer kullanıcılar sadece kendininkini güncelleyebilir.
    Yetki yoksa ya da kayıt yoksa 404 döner.
    """
    try:
        if current.role == "admin":
            existing = repo.get(dashboard_id)
            # Kayıt yoksa KeyError fırlatılır; aşağıdaki except bloğu bunu 404'e çevirir.
            if not existing: raise KeyError
        else:
            repo.get_owned_or_raise(dashboard_id, current.user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Dashboard bulunamadı")

    dash = Dashboard(
        dashboard_id=dashboard_id, owner_id=current.user_id, name=body.name,
        scale=body.scale, page_w_mm=body.page_w_mm, page_h_mm=body.page_h_mm,
        objects=[DashboardObj(**o.model_dump()) for o in body.objects],
    )
    repo.save(dash)
    return {"dashboard_id": dashboard_id, "msg": "Güncellendi"}


@router.get("")
def list_dashboards(
    current = Depends(get_current_user),
    repo: DashboardRepository = Depends(get_dash_repo),
):
    """Dashboard listesini döner. Admin tümünü, diğer kullanıcılar sadece kendininkileri görür. Objeler listede yer almaz."""
    # Admin için owner None verilir: filtre uygulanmaz, tüm dashboard'lar gelir.
    owner = None if current.role == "admin" else current.user_id
    return [
        {"dashboard_id": d.dashboard_id, "owner_id": d.owner_id, "name": d.name,
         "scale": d.scale, "updated_at": d.updated_at}
        for d in repo.list_all(owner_id=owner)
    ]


@router.get("/{dashboard_id}")
def get_dashboard(
    dashboard_id: str,
    current = Depends(get_current_user),
    repo: DashboardRepository = Depends(get_dash_repo),
):
    """Tek bir dashboard'u grafik objeleriyle birlikte döner. Yetki yoksa ya da kayıt yoksa 404 döner."""
    try:
        if current.role == "admin":
            dash = repo.get(dashboard_id)
            if not dash: raise KeyError
        else:
            dash = repo.get_owned_or_raise(dashboard_id, current.user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Dashboard bulunamadı")

    from dataclasses import asdict
    return asdict(dash)


@router.delete("/{dashboard_id}")
def delete_dashboard(
    dashboard_id: str,
    current = Depends(get_current_user),
    repo: DashboardRepository = Depends(get_dash_repo),
):
    """Dashboard'u siler. Admin herkesinkini, diğer kullanıcılar sadece kendininkini silebilir. Silinemezse 404 döner."""
    # Admin tüm dashboard'ları silebilir; diğerleri için sahiplik kontrollü silme yapılır.
    if current.role == "admin":
        deleted = repo.delete(dashboard_id)
    else:
        deleted = repo.delete_owned(dashboard_id, current.user_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Dashboard bulunamadı")
    return {"msg": f"{dashboard_id} silindi"}
