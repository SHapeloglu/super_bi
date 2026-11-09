"""/api/dashboards — dashboard (rapor sayfası) uç noktaları.
Admin tüm dashboard'ları görebilir; diğer kullanıcılar sadece kendininkileri.
Veri katmanı: app.core.repository.DashboardRepository. Kimlik: app.deps.get_current_user.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.core.repository import Dashboard, DashboardObj, DashboardRepository
from app.deps import get_dash_repo, get_current_user, get_share_repo
from app.core.sharing import ShareRepository, effective_permission, allows

router = APIRouter()


def perm_of(resource_id: str, owner_id, current, shares: ShareRepository):
    """Kullanıcının bu dashboard üzerindeki etkin izni (None = erişim yok)."""
    if owner_id is None:
        return None
    return effective_permission(
        owner_id=owner_id, user_id=current.user_id, role=current.role,
        shared=shares.permission_for("dashboard", resource_id, current.user_id, current.role),
    )


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
    shares: ShareRepository = Depends(get_share_repo),
):
    """
    Var olan dashboard'u günceller. Sahip, admin ya da 'write' paylaşımı olan kullanıcı güncelleyebilir.
    Erişimi yoksa 404; yalnız okuma izni varsa 403. Sahiplik değişmez.
    """
    existing = repo.get(dashboard_id)
    perm = perm_of(dashboard_id, existing.owner_id if existing else None, current, shares)
    if existing is None or perm is None:
        raise HTTPException(status_code=404, detail="Dashboard bulunamadı")
    if not allows(perm, "write"):
        raise HTTPException(status_code=403, detail="Bu dashboard'u değiştirme yetkiniz yok")

    dash = Dashboard(
        dashboard_id=dashboard_id, owner_id=existing.owner_id, name=body.name,
        scale=body.scale, page_w_mm=body.page_w_mm, page_h_mm=body.page_h_mm,
        objects=[DashboardObj(**o.model_dump()) for o in body.objects],
    )
    repo.save(dash)
    return {"dashboard_id": dashboard_id, "msg": "Güncellendi"}


@router.get("")
def list_dashboards(
    current = Depends(get_current_user),
    repo: DashboardRepository = Depends(get_dash_repo),
    shares: ShareRepository = Depends(get_share_repo),
):
    """Sahip olunan ve paylaşılan dashboard'ları döner (admin hepsini). Objeler listede yer almaz; 'permission' alanı var."""
    if current.role == "admin":
        items = repo.list_all(owner_id=None)
        shared = {}
    else:
        items = repo.list_all(owner_id=current.user_id)
        shared = shares.shared_map("dashboard", current.user_id, current.role)
        seen = {d.dashboard_id for d in items}
        for d_id in shared:
            if d_id not in seen:
                d = repo.get(d_id)
                if d:
                    items.append(d)
    out = []
    for d in items:
        perm = effective_permission(owner_id=d.owner_id, user_id=current.user_id,
                                    role=current.role, shared=shared.get(d.dashboard_id))
        if perm is None:
            continue
        out.append({"dashboard_id": d.dashboard_id, "owner_id": d.owner_id, "name": d.name,
                    "scale": d.scale, "updated_at": d.updated_at, "permission": perm})
    return out


@router.get("/{dashboard_id}")
def get_dashboard(
    dashboard_id: str,
    current = Depends(get_current_user),
    repo: DashboardRepository = Depends(get_dash_repo),
    shares: ShareRepository = Depends(get_share_repo),
):
    """Tek bir dashboard'u grafik objeleriyle ve etkin iznimle birlikte döner. Erişim yoksa ya da kayıt yoksa 404."""
    dash = repo.get(dashboard_id)
    perm = perm_of(dashboard_id, dash.owner_id if dash else None, current, shares)
    if dash is None or perm is None:
        raise HTTPException(status_code=404, detail="Dashboard bulunamadı")

    from dataclasses import asdict
    return {**asdict(dash), "permission": perm}


@router.delete("/{dashboard_id}")
def delete_dashboard(
    dashboard_id: str,
    current = Depends(get_current_user),
    repo: DashboardRepository = Depends(get_dash_repo),
    shares: ShareRepository = Depends(get_share_repo),
):
    """Dashboard'u siler. Yalnız sahip ya da admin silebilir (paylaşım izni silme yetkisi vermez)."""
    dash = repo.get(dashboard_id)
    perm = perm_of(dashboard_id, dash.owner_id if dash else None, current, shares)
    if dash is None or perm is None:
        raise HTTPException(status_code=404, detail="Dashboard bulunamadı")
    if not (current.role == "admin" or dash.owner_id == current.user_id):
        raise HTTPException(status_code=403, detail="Dashboard yalnız sahibi tarafından silinebilir")

    repo.delete(dashboard_id)
    shares.delete_for_resource("dashboard", dashboard_id)
    return {"msg": f"{dashboard_id} silindi"}
