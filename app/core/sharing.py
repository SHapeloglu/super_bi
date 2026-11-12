"""
Paylaşım modeli (Faz 1.2): dataset ve dashboard, bir kullanıcıya ya da bir role
'read' / 'write' izniyle paylaşılabilir.

Erişim kuralları:
  - admin ve sahip: her şeyi yapar (write).
  - paylaşım alıcısı: verilen izin kadar. Birden çok eşleşme varsa en yüksek izin geçerlidir.
  - izin yoksa kaynak görünmez (API 404 döner; varlık sızdırılmaz).
  - silme her zaman yalnız sahip ya da admin içindir (write paylaşımı silme yetkisi vermez).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

RESOURCE_TYPES = ("dataset", "dashboard")
GRANTEE_TYPES = ("user", "role")
ROLES = ("admin", "viewer")  # editor rolü kaldırıldı: anlamlı yetki farkı yoktu
PERMISSIONS = ("read", "write")

_RANK = {None: 0, "read": 1, "write": 2}


def max_permission(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """İki izinden yüksek olanı döner (None < read < write)."""
    return a if _RANK[a] >= _RANK[b] else b


def effective_permission(*, owner_id: str, user_id: str, role: str,
                         shared: Optional[str]) -> Optional[str]:
    """Kullanıcının kaynak üzerindeki etkin izni: admin/sahip → write; değilse paylaşım izni."""
    if role == "admin" or owner_id == user_id:
        return "write"
    return shared


def allows(permission: Optional[str], need: str) -> bool:
    """Etkin izin, istenen seviyeyi karşılıyor mu? need: 'read' veya 'write'."""
    return _RANK[permission] >= _RANK[need]


class ShareRepository:
    """shares tablosu üzerinde paylaşım kayıtları."""

    def __init__(self, store) -> None:
        self._s = store

    def create(self, resource_type: str, resource_id: str, grantee_type: str,
               grantee_id: str, permission: str, created_by: str) -> str:
        """Paylaşım ekler; aynı alıcı için varsa izni günceller. Kayıt kimliğini döner."""
        share_id = str(uuid.uuid4())[:12]
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        self._s.execute(
            "INSERT INTO shares (share_id, resource_type, resource_id, grantee_type, grantee_id, "
            "permission, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(resource_type, resource_id, grantee_type, grantee_id) "
            "DO UPDATE SET permission = excluded.permission, created_by = excluded.created_by",
            (share_id, resource_type, resource_id, grantee_type, grantee_id,
             permission, created_by, now),
        )
        row = self._s.fetchone(
            "SELECT share_id FROM shares WHERE resource_type=? AND resource_id=? "
            "AND grantee_type=? AND grantee_id=?",
            (resource_type, resource_id, grantee_type, grantee_id),
        )
        return row["share_id"]

    def get(self, share_id: str) -> Optional[dict]:
        row = self._s.fetchone("SELECT * FROM shares WHERE share_id=?", (share_id,))
        return dict(row) if row else None

    def list_for(self, resource_type: str, resource_id: str) -> list[dict]:
        rows = self._s.fetchall(
            "SELECT * FROM shares WHERE resource_type=? AND resource_id=? ORDER BY created_at",
            (resource_type, resource_id),
        )
        return [dict(r) for r in rows]

    def delete(self, share_id: str) -> bool:
        cur = self._s.execute("DELETE FROM shares WHERE share_id=?", (share_id,))
        return cur.rowcount > 0

    def delete_for_resource(self, resource_type: str, resource_id: str) -> None:
        """Kaynak silinince ona ait paylaşımlar da silinir."""
        self._s.execute("DELETE FROM shares WHERE resource_type=? AND resource_id=?",
                        (resource_type, resource_id))

    def permission_for(self, resource_type: str, resource_id: str,
                       user_id: str, role: str) -> Optional[str]:
        """Kullanıcının (ve rolünün) bu kaynak üzerindeki en yüksek paylaşım izni."""
        rows = self._s.fetchall(
            "SELECT permission FROM shares WHERE resource_type=? AND resource_id=? "
            "AND ((grantee_type='user' AND grantee_id=?) OR (grantee_type='role' AND grantee_id=?))",
            (resource_type, resource_id, user_id, role),
        )
        perm: Optional[str] = None
        for r in rows:
            perm = max_permission(perm, r["permission"])
        return perm

    def shared_map(self, resource_type: str, user_id: str, role: str) -> dict[str, str]:
        """Kullanıcıya (ya da rolüne) paylaşılmış kaynakların {resource_id: en yüksek izin} haritası."""
        rows = self._s.fetchall(
            "SELECT resource_id, permission FROM shares WHERE resource_type=? "
            "AND ((grantee_type='user' AND grantee_id=?) OR (grantee_type='role' AND grantee_id=?))",
            (resource_type, user_id, role),
        )
        out: dict[str, str] = {}
        for r in rows:
            out[r["resource_id"]] = max_permission(out.get(r["resource_id"]), r["permission"])
        return out
