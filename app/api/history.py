"""
/api/history — sorgu geçmişi + versiyonlama (auth bağlı)

Not: query_history tablosunda owner_id kolonu yok — conn_id üzerinden
dolaylı izolasyon sağlanır (kullanıcı sadece kendi conn_id'lerini görebilir,
get_connection_engine zaten bunu kontrol ediyor). add_history conn_id
sahiplik kontrolü yapmaz çünkü /api/query/run zaten kontrol etmiş olur.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.core.repository import QueryVersion, QueryHistoryRepository, ConnectionRepository
from app.deps import get_hist_repo, get_repo, get_current_user

router = APIRouter()


class HistoryAddRequest(BaseModel):
    fingerprint:  str
    conn_id:      str
    conn_name:    str     = ""
    base_table:   str
    sql_text:     str
    fields:       dict    = {}
    joins:        list    = []
    filters:      list    = []
    group_by:     list    = []
    sample:       int     = 10
    mode:         str     = "memory"
    row_count:    Optional[int]   = None
    exec_ms:      Optional[float] = None
    note:         str     = ""


def _check_conn_access(conn_id: str, current, repo: ConnectionRepository):
    """Kullanıcı bu conn_id'ye erişebiliyor mu — admin hepsine erişir."""
    try:
        if current.role == "admin":
            repo.get_or_raise(conn_id)
        else:
            repo.get_owned_or_raise(conn_id, current.user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")


@router.post("", status_code=201)
def add_history(
    body: HistoryAddRequest,
    current = Depends(get_current_user),
    repo:    QueryHistoryRepository = Depends(get_hist_repo),
    cn_repo: ConnectionRepository   = Depends(get_repo),
):
    _check_conn_access(body.conn_id, current, cn_repo)
    version = QueryVersion(id=str(uuid.uuid4())[:12], **body.model_dump())
    repo.add(version)
    return {"id": version.id, "fingerprint": version.fingerprint}


@router.get("/groups")
def get_groups(
    conn_id: Optional[str] = None,
    current = Depends(get_current_user),
    repo:    QueryHistoryRepository = Depends(get_hist_repo),
    cn_repo: ConnectionRepository   = Depends(get_repo),
):
    """
    conn_id verilirse o bağlantının grupları (sahiplik kontrolü yapılır).
    conn_id verilmezse: admin tümünü, diğerleri sadece kendi bağlantılarının
    sorgu geçmişini görür (conn_id listesi üzerinden filtrelenir).
    """
    if conn_id:
        _check_conn_access(conn_id, current, cn_repo)
        return repo.get_groups(conn_id=conn_id)

    if current.role == "admin":
        return repo.get_groups()

    # Kullanıcının kendi bağlantı id'lerini al, sadece onları göster
    own_conn_ids = {c.conn_id for c in cn_repo.list_all(owner_id=current.user_id)}
    all_groups = repo.get_groups()
    return [g for g in all_groups if g["conn_id"] in own_conn_ids]


@router.get("/groups/{fingerprint}")
def get_versions(
    fingerprint: str,
    current = Depends(get_current_user),
    repo:    QueryHistoryRepository = Depends(get_hist_repo),
    cn_repo: ConnectionRepository   = Depends(get_repo),
):
    from dataclasses import asdict
    versions = repo.get_versions(fingerprint)
    if not versions:
        return []
    # İlk versiyonun conn_id'sine bakarak erişim kontrolü
    _check_conn_access(versions[0].conn_id, current, cn_repo)
    return [asdict(v) for v in versions]


@router.get("/recent")
def get_recent(
    limit: int = 20,
    current = Depends(get_current_user),
    repo:    QueryHistoryRepository = Depends(get_hist_repo),
    cn_repo: ConnectionRepository   = Depends(get_repo),
):
    from dataclasses import asdict
    recent = repo.get_recent(limit=limit * 2)   # filtre sonrası limit'e ulaşmak için fazladan çek

    if current.role == "admin":
        return [asdict(v) for v in recent[:limit]]

    own_conn_ids = {c.conn_id for c in cn_repo.list_all(owner_id=current.user_id)}
    filtered = [v for v in recent if v.conn_id in own_conn_ids]
    return [asdict(v) for v in filtered[:limit]]


@router.delete("/groups/{fingerprint}")
def delete_group(
    fingerprint: str,
    current = Depends(get_current_user),
    repo:    QueryHistoryRepository = Depends(get_hist_repo),
    cn_repo: ConnectionRepository   = Depends(get_repo),
):
    versions = repo.get_versions(fingerprint)
    if versions:
        _check_conn_access(versions[0].conn_id, current, cn_repo)
    count = repo.delete_group(fingerprint)
    return {"deleted": count, "fingerprint": fingerprint}


@router.get("/stats")
def stats(
    current = Depends(get_current_user),
    repo:    QueryHistoryRepository = Depends(get_hist_repo),
):
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    return repo.stats()
