"""
/api/datasets — auth bağlı, owner_id kontrollü

Bir "dataset", kayıtlı bir sorgu tanımıdır (conn_id + base_table + fields +
joins + filters + group_by + order_by). Widget'lar bu tanıma dataset_id ile
referans verir (query_id alanında JSON olarak {"datasetId": "..."} şeklinde
saklanır — bkz. frontend). Widget her render'da bu tanımın GÜNCEL halini
çekip çalıştırır; yani burada bir dataset'i güncellemek, ona bağlı TÜM
widget'ları otomatik günceller — ayrıca hiçbir widget'ı elle güncellemeye
gerek kalmaz.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
from types import SimpleNamespace

from pydantic import Field

from app.core.repository import Dataset, DatasetRepository, ConnectionRepository
from app.deps import get_dataset_repo, get_repo, get_current_user, get_share_repo, get_registry, get_executor, resolve_connection_engine, get_rls_repo, get_attr_repo
from app.core.rls import RuleRepository, AttributeRepository, build_rls_filters, RLSError
from app.core.connector_registry import quote_identifier
from pydantic import model_validator
from typing import Any
from app.core.sharing import ShareRepository, effective_permission, allows
from app.core.connector_registry import ConnectorRegistry
from app.models.schemas import JoinDef, FilterDef
from app.services.sql_builder import sql_builder
from app.services.query_executor import QueryExecutor

router = APIRouter()


def perm_of(resource_id: str, owner_id, current, shares: ShareRepository):
    """Kullanıcının bu dataset üzerindeki etkin izni (None = erişim yok)."""
    if owner_id is None:
        return None
    return effective_permission(
        owner_id=owner_id, user_id=current.user_id, role=current.role,
        shared=shares.permission_for("dataset", resource_id, current.user_id, current.role),
    )


class DatasetIn(BaseModel):
    """Dataset oluşturma / güncelleme isteği. Bağlantı, tablo, alanlar, join, filtre, gruplama ve sıralama bilgisini taşır."""
    name:       str
    conn_id:    str
    base_table: str
    fields:     dict           = {}
    joins:      list           = []
    filters:    list           = []
    group_by:   list           = []
    order_by:   list           = []


def _check_conn_ownership(conn_id: str, current, conn_repo: ConnectionRepository) -> None:
    """Dataset'in işaret ettiği bağlantı gerçekten bu kullanıcıya mı ait —
    burada erken uyarmak, widget render sırasında sessizce başarısız
    olmaktansa kullanıcıya net bir hata mesajı vermeyi sağlar."""
    try:
        if current.role == "admin":
            conn_repo.get_or_raise(conn_id)
        else:
            conn_repo.get_owned_or_raise(conn_id, current.user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Bağlantı bulunamadı: {conn_id}")


@router.post("", status_code=201)
def create_dataset(
    body: DatasetIn,
    current    = Depends(get_current_user),
    repo:      DatasetRepository   = Depends(get_dataset_repo),
    conn_repo: ConnectionRepository = Depends(get_repo),
):
    """
    Yeni dataset (kayıtlı sorgu) oluşturur (201). Önce bağlantının kullanıcıya ait olduğu kontrol edilir.
    Dönüş: dataset_id, ad ve mesaj.
    """
    _check_conn_ownership(body.conn_id, current, conn_repo)

    # Kısa kimlik: UUID'nin ilk 8 karakteri.
    dataset_id = str(uuid.uuid4())[:8]
    ds = Dataset(
        dataset_id=dataset_id, owner_id=current.user_id, name=body.name,
        conn_id=body.conn_id, base_table=body.base_table,
        fields=body.fields, joins=body.joins, filters=body.filters,
        group_by=body.group_by, order_by=body.order_by,
    )
    repo.save(ds)
    return {"dataset_id": dataset_id, "name": ds.name, "msg": "Kaydedildi"}


@router.put("/{dataset_id}")
def update_dataset(
    dataset_id: str,
    body: DatasetIn,
    current    = Depends(get_current_user),
    repo:      DatasetRepository   = Depends(get_dataset_repo),
    conn_repo: ConnectionRepository = Depends(get_repo),
    shares:    ShareRepository     = Depends(get_share_repo),
):
    """
    Var olan dataset'i günceller. Sahip, admin ya da 'write' paylaşımı olan kullanıcı güncelleyebilir.
    Erişimi yoksa 404; yalnız okuma izni varsa 403. Sahiplik değişmez.
    """
    existing = repo.get(dataset_id)
    perm = perm_of(dataset_id, existing.owner_id if existing else None, current, shares)
    if existing is None or perm is None:
        raise HTTPException(status_code=404, detail="Dataset bulunamadı")
    if not allows(perm, "write"):
        raise HTTPException(status_code=403, detail="Bu dataset'i değiştirme yetkiniz yok")
    # Güncellemede sahip korunur: paylaşılan kaydı düzenlemek sahipliği değiştirmez.
    owner_id = existing.owner_id

    # Bağlantı değişiyorsa yeni bağlantının kullanıcıya ait olduğu kontrol edilir.
    # Aynı bağlantı korunuyorsa kontrol yapılmaz: yazma paylaşımı alan kullanıcı sahibin bağlantısını
    # değiştirmeden veri setini düzenleyebilmeli.
    if body.conn_id != existing.conn_id:
        _check_conn_ownership(body.conn_id, current, conn_repo)

    ds = Dataset(
        dataset_id=dataset_id, owner_id=owner_id, name=body.name,
        conn_id=body.conn_id, base_table=body.base_table,
        fields=body.fields, joins=body.joins, filters=body.filters,
        group_by=body.group_by, order_by=body.order_by,
    )
    repo.save(ds)
    return {"dataset_id": dataset_id, "msg": "Güncellendi — buna bağlı tüm widget'lar bir sonraki görüntülemede güncel veriyi gösterecek"}


@router.get("")
def list_datasets(
    current = Depends(get_current_user),
    repo: DatasetRepository = Depends(get_dataset_repo),
    shares: ShareRepository = Depends(get_share_repo),
):
    """Sahip olunan ve kendisine paylaşılan dataset'leri döner (admin hepsini). Her kayıtta 'permission' alanı var."""
    if current.role == "admin":
        items = repo.list_all(owner_id=None)
        shared = {}
    else:
        items = repo.list_all(owner_id=current.user_id)
        shared = shares.shared_map("dataset", current.user_id, current.role)
        seen = {d.dataset_id for d in items}
        for ds_id in shared:
            if ds_id not in seen:
                ds = repo.get(ds_id)
                if ds:
                    items.append(ds)
    out = []
    for d in items:
        perm = effective_permission(owner_id=d.owner_id, user_id=current.user_id,
                                    role=current.role, shared=shared.get(d.dataset_id))
        if perm is None:
            continue
        out.append({"dataset_id": d.dataset_id, "owner_id": d.owner_id, "name": d.name,
                    "conn_id": d.conn_id, "base_table": d.base_table, "updated_at": d.updated_at,
                    "permission": perm})
    return out


@router.get("/{dataset_id}")
def get_dataset(
    dataset_id: str,
    current = Depends(get_current_user),
    repo: DatasetRepository = Depends(get_dataset_repo),
    shares: ShareRepository = Depends(get_share_repo),
):
    """Tek bir dataset'i tanımıyla ve etkin iznimle birlikte döner. Erişim yoksa ya da kayıt yoksa 404."""
    ds = repo.get(dataset_id)
    perm = perm_of(dataset_id, ds.owner_id if ds else None, current, shares)
    if ds is None or perm is None:
        raise HTTPException(status_code=404, detail="Dataset bulunamadı")

    from dataclasses import asdict
    return {**asdict(ds), "permission": perm}


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: str,
    current = Depends(get_current_user),
    repo: DatasetRepository = Depends(get_dataset_repo),
    shares: ShareRepository = Depends(get_share_repo),
):
    """Dataset'i siler. Yalnız sahip ya da admin silebilir (paylaşım izni silme yetkisi vermez)."""
    ds = repo.get(dataset_id)
    perm = perm_of(dataset_id, ds.owner_id if ds else None, current, shares)
    if ds is None or perm is None:
        raise HTTPException(status_code=404, detail="Dataset bulunamadı")
    if not (current.role == "admin" or ds.owner_id == current.user_id):
        raise HTTPException(status_code=403, detail="Dataset yalnız sahibi tarafından silinebilir")

    repo.delete(dataset_id)
    shares.delete_for_resource("dataset", dataset_id)
    return {"msg": f"{dataset_id} silindi"}


class RuleIn(BaseModel):
    """
    Satır kuralı: column operator (value | attr). value sabit değer ya da liste (IN için);
    attr kullanıcı özniteliğinin adıdır (değeri kullanıcıdan alınır; yalnız = ve != ile).
    """
    column:   str = Field(min_length=1, max_length=128)
    operator: Literal["=", "!=", "IN", "NOT IN"]
    value:    Any = None
    attr:     Optional[str] = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _kural_tutarli(self):
        if (self.attr is None) == (self.value is None):
            raise ValueError("value ya da attr alanlarından tam biri verilmeli")
        if self.attr is not None and self.operator not in ("=", "!="):
            raise ValueError("Öznitelik kuralları yalnız = ve != ile kullanılabilir")
        if self.operator in ("IN", "NOT IN") and not isinstance(self.value, list):
            raise ValueError("IN / NOT IN için liste gerekir")
        return self


def _yalniz_admin(current) -> None:
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Satır kurallarını yalnız admin yönetebilir")


@router.post("/{dataset_id}/rules", status_code=201)
def create_rule(
    dataset_id: str,
    body: RuleIn,
    current = Depends(get_current_user),
    repo: DatasetRepository = Depends(get_dataset_repo),
    rls_repo: RuleRepository = Depends(get_rls_repo),
):
    """Veri setine satır kuralı ekler (yalnız admin). Kolon adı tanımlanabilir bir identifier olmalı."""
    _yalniz_admin(current)
    if repo.get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset bulunamadı")
    try:
        quote_identifier(body.column)
    except ValueError:
        raise HTTPException(status_code=400, detail="Geçersiz kolon adı")
    rule_id = rls_repo.add(dataset_id, body.column, body.operator, body.value, body.attr,
                           created_by=current.user_id)
    return {"rule_id": rule_id, "msg": "Kural eklendi"}


@router.get("/{dataset_id}/rules")
def list_rules(
    dataset_id: str,
    current = Depends(get_current_user),
    repo: DatasetRepository = Depends(get_dataset_repo),
    rls_repo: RuleRepository = Depends(get_rls_repo),
):
    """Veri setinin satır kuralları (yalnız admin)."""
    _yalniz_admin(current)
    return rls_repo.list_for(dataset_id)


@router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: str,
    current = Depends(get_current_user),
    rls_repo: RuleRepository = Depends(get_rls_repo),
):
    """Satır kuralını siler (yalnız admin)."""
    _yalniz_admin(current)
    if not rls_repo.delete(rule_id):
        raise HTTPException(status_code=404, detail="Kural bulunamadı")
    return {"msg": "Kural silindi"}


class DatasetRunIn(BaseModel):
    """
    Veri seti çalıştırma isteği. Örnek boyutu, önbellek modu ve (isteğe bağlı) kolon alt kümesi.
    fields yalnız veri setinin kendi kolonlarından seçilebilir; SQL, tablo ya da bağlantı alınmaz.
    """
    sample: int = Field(default=100, ge=1, le=100_000)
    mode:   Literal["live", "memory"] = "memory"
    fields: Optional[dict[str, str]] = None


def _resolve_fields(requested: dict, allowed: dict) -> dict:
    """
    İstenen kolonları veri setinin kendi kolonlarına eşler. Anahtar tam eşleşirse olduğu gibi,
    değilse noktalı anahtarın son parçasıyla (tablo.kolon -> kolon) tek eşleşme aranır.
    Tanımsız ya da belirsiz kolon 400 döner.
    """
    out: dict = {}
    for rk, role in requested.items():
        if rk in allowed:
            key = rk
        else:
            adaylar = [k for k in allowed if k.split(".")[-1] == rk]
            if not allowed or len(adaylar) != 1:
                raise HTTPException(status_code=400, detail="İstenen kolonlar veri setinde tanımlı değil")
            key = adaylar[0]
        out[key] = role
    return out


@router.post("/{dataset_id}/run")
def run_dataset(
    dataset_id: str,
    body: DatasetRunIn,
    current = Depends(get_current_user),
    repo: DatasetRepository = Depends(get_dataset_repo),
    shares: ShareRepository = Depends(get_share_repo),
    registry: ConnectorRegistry = Depends(get_registry),
    conn_repo: ConnectionRepository = Depends(get_repo),
    executor: QueryExecutor = Depends(get_executor),
    rls_repo: RuleRepository = Depends(get_rls_repo),
    attr_repo: AttributeRepository = Depends(get_attr_repo),
):
    """
    Kayıtlı veri setini çalıştırır. Okuma izni olan herkes çalıştırabilir; bağlantı VERİ SETİNİN SAHİBİ
    kimliğiyle açılır (bağlantı sahibine aittir). Sorguyu yalnız kayıtlı tanım üretir.
    Erişim yoksa 404. Önbellek kullanıcıya özeldir (çalıştıran kullanıcının kimliğiyle).
    """
    ds = repo.get(dataset_id)
    perm = perm_of(dataset_id, ds.owner_id if ds else None, current, shares)
    if ds is None or perm is None:
        raise HTTPException(status_code=404, detail="Dataset bulunamadı")

    # Kolon alt kümesi: yalnız veri setinin kendi kolonları istenebilir (kayıtlı olmayan kolon 400).
    fields = ds.fields
    if body.fields is not None:
        fields = _resolve_fields(body.fields, ds.fields)

    # Bağlantı sahibinin kendi kimliği ile açılır; alıcının bağlantı erişimi yoktur.
    owner = SimpleNamespace(user_id=ds.owner_id, role="viewer")
    engine, meta = resolve_connection_engine(ds.conn_id, owner, registry, conn_repo)

    # Satır bazlı güvenlik: admin dışındaki herkes (sahip dahil) kuralların altındadır.
    rls_filters = []
    if current.role != "admin":
        try:
            rls_filters = build_rls_filters(rls_repo.list_for(dataset_id), current.user_id,
                                            ds.base_table, attr_repo)
        except RLSError:
            raise HTTPException(status_code=403,
                                detail="Bu veri seti için gerekli kullanıcı özniteliği tanımlı değil")

    try:
        sql, params = sql_builder.build(
            base_table=ds.base_table,
            fields=fields,
            joins=[JoinDef(**j) for j in ds.joins],
            filters=[FilterDef(**f) for f in ds.filters] + [FilterDef(**f) for f in rls_filters],
            group_by=ds.group_by,
            order_by=ds.order_by,
            limit=body.sample,
            offset=0,
            db_type=meta.db_type,
        )
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    return executor.execute(
        engine=engine, sql=sql, params=params, sample=body.sample,
        commit=False, mode=body.mode,
        user_id=current.user_id,   # önbellek ve kayıt çalıştıran kullanıcıya ait
        conn_id=meta.conn_id,
    )
