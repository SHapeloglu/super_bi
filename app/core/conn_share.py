"""
Bağlantı paylaşımı (docs/VIEWER_BAGLANTI_PAYLASIMI.md, seçenek B sınırlı hali).

Bir bağlantı bir kullanıcıya 'use' izniyle paylaşılır; paylaşım kaydı shares tablosundadır
(resource_type='connection', permission='use'). Alıcının hangi tablolardan veri seti kurabileceği
connection_share_tables tablosunda tutulur (share_id'ye bağlı). Paylaşım kaldırılınca ya da
yeniden paylaşılınca tablo listesi shares kaydına göre yorumlanır; eski satırlar yok sayılır.

Bu modül şifre ya da host bilgisine dokunmaz.
"""
from __future__ import annotations

from typing import Optional

from app.core.sharing import ShareRepository

RESOURCE_TYPE = "connection"
PERMISSION = "use"


def _norm_schema(schema: Optional[str]) -> str:
    """Şemasız tablo için sabit anahtar ('')."""
    return schema or ""


class ConnectionShareRepository:
    """Bağlantı 'use' paylaşımları ve izinli tablo listeleri."""

    def __init__(self, store) -> None:
        self._s = store
        self._shares = ShareRepository(store)

    def grant(self, conn_id: str, user_id: str, tables: list[tuple[Optional[str], str]],
              created_by: str) -> str:
        """Kullanıcıya bağlantıyı 'use' izniyle paylaşır ve tablo listesini yazar. Varsa listeyi değiştirir."""
        share_id = self._shares.create(RESOURCE_TYPE, conn_id, "user", user_id, PERMISSION, created_by)
        self._s.execute("DELETE FROM connection_share_tables WHERE share_id=?", (share_id,))
        for schema, table in tables:
            self._s.execute(
                "INSERT OR IGNORE INTO connection_share_tables (share_id, schema_name, table_name) "
                "VALUES (?, ?, ?)",
                (share_id, _norm_schema(schema), table),
            )
        return share_id

    def _share_row(self, conn_id: str, user_id: str):
        return self._s.fetchone(
            "SELECT share_id FROM shares WHERE resource_type=? AND resource_id=? "
            "AND grantee_type='user' AND grantee_id=? AND permission=?",
            (RESOURCE_TYPE, conn_id, user_id, PERMISSION),
        )

    def has_use(self, conn_id: str, user_id: str) -> bool:
        return self._share_row(conn_id, user_id) is not None

    def allowed_tables(self, conn_id: str, user_id: str) -> Optional[set[tuple[str, str]]]:
        """Alıcının izinli (şema, tablo) kümesi; paylaşım yoksa None."""
        row = self._share_row(conn_id, user_id)
        if row is None:
            return None
        rows = self._s.fetchall(
            "SELECT schema_name, table_name FROM connection_share_tables WHERE share_id=?",
            (row["share_id"],),
        )
        return {(r["schema_name"], r["table_name"]) for r in rows}

    def allowed_tables_list(self, conn_id: str, user_id: str) -> list[tuple[str, str]]:
        """Alıcının izinli (şema, tablo) listesi, sıralı; paylaşım yoksa boş."""
        allowed = self.allowed_tables(conn_id, user_id) or set()
        return sorted(allowed)

    def tables_of(self, share_id: str) -> list[tuple[str, str]]:
        """Bir paylaşımın tablo listesi (şema, tablo), sıralı."""
        rows = self._s.fetchall(
            "SELECT schema_name, table_name FROM connection_share_tables WHERE share_id=? "
            "ORDER BY schema_name, table_name",
            (share_id,),
        )
        return [(r["schema_name"], r["table_name"]) for r in rows]

    def shared_conn_ids(self, user_id: str) -> list[str]:
        rows = self._s.fetchall(
            "SELECT resource_id FROM shares WHERE resource_type=? AND grantee_type='user' "
            "AND grantee_id=? AND permission=? ORDER BY created_at",
            (RESOURCE_TYPE, user_id, PERMISSION),
        )
        return [r["resource_id"] for r in rows]

    def revoke(self, share_id: str) -> bool:
        """Paylaşımı ve tablo listesini kaldırır."""
        self._s.execute("DELETE FROM connection_share_tables WHERE share_id=?", (share_id,))
        return self._shares.delete(share_id)

    def delete_for_connection(self, conn_id: str) -> None:
        """Bağlantı silinince tüm 'use' paylaşımları ve tablo listeleri temizlenir."""
        rows = self._s.fetchall(
            "SELECT share_id FROM shares WHERE resource_type=? AND resource_id=?",
            (RESOURCE_TYPE, conn_id),
        )
        for r in rows:
            self._s.execute("DELETE FROM connection_share_tables WHERE share_id=?", (r["share_id"],))
        self._shares.delete_for_resource(RESOURCE_TYPE, conn_id)
