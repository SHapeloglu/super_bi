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
from typing import Optional

from app.core.repository import Dataset, DatasetRepository, ConnectionRepository
from app.deps import get_dataset_repo, get_repo, get_current_user

router = APIRouter()


class DatasetIn(BaseModel):
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
    _check_conn_ownership(body.conn_id, current, conn_repo)

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
):
    try:
        if current.role == "admin":
            existing = repo.get(dataset_id)
            if not existing: raise KeyError
            owner_id = existing.owner_id
        else:
            existing = repo.get_owned_or_raise(dataset_id, current.user_id)
            owner_id = current.user_id
    except KeyError:
        raise HTTPException(status_code=404, detail="Dataset bulunamadı")

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
):
    owner = None if current.role == "admin" else current.user_id
    return [
        {"dataset_id": d.dataset_id, "owner_id": d.owner_id, "name": d.name,
         "conn_id": d.conn_id, "base_table": d.base_table, "updated_at": d.updated_at}
        for d in repo.list_all(owner_id=owner)
    ]


@router.get("/{dataset_id}")
def get_dataset(
    dataset_id: str,
    current = Depends(get_current_user),
    repo: DatasetRepository = Depends(get_dataset_repo),
):
    try:
        if current.role == "admin":
            ds = repo.get(dataset_id)
            if not ds: raise KeyError
        else:
            ds = repo.get_owned_or_raise(dataset_id, current.user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Dataset bulunamadı")

    from dataclasses import asdict
    return asdict(ds)


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: str,
    current = Depends(get_current_user),
    repo: DatasetRepository = Depends(get_dataset_repo),
):
    if current.role == "admin":
        deleted = repo.delete(dataset_id)
    else:
        deleted = repo.delete_owned(dataset_id, current.user_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset bulunamadı")
    return {"msg": f"{dataset_id} silindi"}
