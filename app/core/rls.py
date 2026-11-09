"""Satır bazlı güvenlik (Faz 1.3): kural ve kullanıcı özniteliği deposu, kural → filtre dönüşümü."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Optional

RLS_OPERATORS = ("=", "!=", "IN", "NOT IN")


class RLSError(Exception):
    """Kullanıcı için gerekli kullanıcı özniteliği tanımlı değil: erişim reddedilir (fail-closed)."""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")


class RuleRepository:
    """row_rules tablosu: bir veri setine bağlı satır kuralları."""

    def __init__(self, store) -> None:
        self._s = store

    def add(self, dataset_id: str, column: str, operator: str, value: Any,
            attr: Optional[str], created_by: str) -> str:
        rule_id = str(uuid.uuid4())[:12]
        self._s.execute(
            "INSERT INTO row_rules (rule_id, dataset_id, column_name, operator, value_json, attr_name, "
            "created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (rule_id, dataset_id, column, operator, json.dumps(value), attr, created_by, _now()),
        )
        return rule_id

    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        d["value"] = json.loads(d.pop("value_json")) if d.get("value_json") is not None else None
        return d

    def list_for(self, dataset_id: str) -> list[dict]:
        rows = self._s.fetchall(
            "SELECT * FROM row_rules WHERE dataset_id=? ORDER BY created_at, rule_id", (dataset_id,))
        return [self._row(r) for r in rows]

    def get(self, rule_id: str) -> Optional[dict]:
        r = self._s.fetchone("SELECT * FROM row_rules WHERE rule_id=?", (rule_id,))
        return self._row(r) if r else None

    def delete(self, rule_id: str) -> bool:
        return self._s.execute("DELETE FROM row_rules WHERE rule_id=?", (rule_id,)).rowcount > 0

    def delete_for_dataset(self, dataset_id: str) -> None:
        self._s.execute("DELETE FROM row_rules WHERE dataset_id=?", (dataset_id,))


class AttributeRepository:
    """user_attributes tablosu: kullanıcı başına anahtar/değer öznitelikleri (ör. department)."""

    def __init__(self, store) -> None:
        self._s = store

    def set(self, user_id: str, key: str, value: str) -> None:
        self._s.execute(
            "INSERT INTO user_attributes (user_id, attr_key, attr_value) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, attr_key) DO UPDATE SET attr_value = excluded.attr_value",
            (user_id, key, value),
        )

    def get(self, user_id: str, key: str) -> Optional[str]:
        r = self._s.fetchone("SELECT attr_value FROM user_attributes WHERE user_id=? AND attr_key=?",
                             (user_id, key))
        return r["attr_value"] if r else None


def build_rls_filters(rules: list[dict], user_id: str, base_table: str, attrs: AttributeRepository) -> list[dict]:
    """
    Kuralları sorgu filtrelerine (FilterDef sözlüğü) çevirir. Özniteliğe bağlı kurallarda değer
    kullanıcının özniteliğinden alınır; öznitelik yoksa RLSError fırlatılır.
    """
    filtreler = []
    for r in rules:
        if r.get("attr_name"):
            deger = attrs.get(user_id, r["attr_name"])
            if deger is None:
                raise RLSError(r["attr_name"])
        else:
            deger = r["value"]
        filtreler.append({"table": base_table, "column": r["column_name"],
                          "operator": r["operator"], "value": deger})
    return filtreler
