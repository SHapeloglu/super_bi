"""
SQLBuilder
----------
QueryRequest → güvenli, parametreli SQL.

Düzeltilen bug'lar:
  BUG-3  quote_identifier: nokta ayrıştırma, regex whitelist
  DES-4  OPERATOR_MAP artık gerçekten kullanılıyor (whitelist kontrolü)

YENİ: hesaplanmış alan (calculated field) desteği — app.services.
expression_builder ile SQLGlot tabanlı, whitelist edilmiş formül derleme.
"""
from __future__ import annotations

from typing import Any

from app.core.connector_registry import quote_identifier
from app.models.schemas import FilterDef, JoinDef, CalculatedFieldDef, ALLOWED_OPERATORS
from app.services.expression_builder import validate_and_compile, ExpressionError


class SQLBuilder:

    def _select_columns(self, base_table: str, fields: dict[str, str]) -> list[str]:
        cols = []
        for key, role in fields.items():
            if role == "off":
                continue
            cols.append(quote_identifier(key) if "." in key
                        else f"{quote_identifier(base_table)}.{quote_identifier(key)}")
        return cols or [f"{quote_identifier(base_table)}.*"]

    def _calculated_columns(
        self,
        fields: dict[str, str],
        calculated_fields: list[CalculatedFieldDef],
        db_type: str,
    ) -> list[str]:
        """
        Her hesaplanmış alan için formülü doğrulayıp (whitelist) hedef
        dialect'e derler, sonra "AS alias" ekleyerek SELECT listesine
        eklenecek parçayı üretir.

        allowed_columns SADECE seçili (role != "off") fields'daki bare kolon
        adlarıdır — yani kullanıcı önce query builder'da bir kolonu "dahil"
        etmeden, o kolonu bir formülde kullanamaz. Bu bilinçli bir kısıtlama:
        SQLBuilder'ın tam şema bilgisi yok, sadece frontend'den gelen
        fields dict'ini biliyor; formülleri buna göre sınırlamak, şema
        dışı/rastgele kolon adı denemelerini baştan eler.
        """
        if not calculated_fields:
            return []

        allowed_columns = {
            (key.split(".")[-1]) for key, role in fields.items() if role != "off"
        }

        parts = []
        for cf in calculated_fields:
            try:
                compiled = validate_and_compile(cf.formula, db_type, allowed_columns)
            except ExpressionError as e:
                raise ValueError(f"Hesaplanmış alan {cf.name!r}: {e}")
            parts.append(f"{compiled} AS {quote_identifier(cf.name)}")
        return parts

    def _join_clauses(self, joins: list[JoinDef]) -> str:
        parts = []
        for j in joins:
            t1 = quote_identifier(j.t1); f1 = quote_identifier(j.f1)
            t2 = quote_identifier(j.t2); f2 = quote_identifier(j.f2)
            parts.append(f"{j.type} {t2} ON {t1}.{f1} = {t2}.{f2}")
        return "\n".join(parts)

    def _where_clauses(self, filters: list[FilterDef]) -> tuple[str, dict[str, Any]]:
        parts: list[str] = []
        params: dict[str, Any] = {}

        for i, f in enumerate(filters):
            op  = f.operator   # zaten whitelist'ten geçti (FilterDef validator)
            col = f"{quote_identifier(f.table)}.{quote_identifier(f.column)}"
            p   = f"p_{i}"

            # Whitelist double-check (DES-4)
            if op not in ALLOWED_OPERATORS:
                raise ValueError(f"İzin verilmeyen operatör: {op!r}")

            if op in ("IS NULL", "IS NOT NULL"):
                parts.append(f"{col} {op}")
                continue

            if op in ("IN", "NOT IN"):
                vals = f.value if isinstance(f.value, list) else [f.value]
                placeholders = ", ".join(f":{p}_{j}" for j in range(len(vals)))
                parts.append(f"{col} {op} ({placeholders})")
                for j, v in enumerate(vals):
                    params[f"{p}_{j}"] = v
                continue

            if op == "BETWEEN":
                parts.append(f"{col} BETWEEN :{p}_a AND :{p}_b")
                params[f"{p}_a"] = f.value
                params[f"{p}_b"] = f.value2
                continue

            parts.append(f"{col} {op} :{p}")
            params[p] = f.value

        where = "WHERE " + "\nAND ".join(parts) if parts else ""
        return where, params

    def build(
        self,
        base_table: str,
        fields:     dict[str, str],
        joins:      list[JoinDef],
        filters:    list[FilterDef],
        group_by:   list[str],
        order_by:   list[str],
        limit:      int,
        offset:     int = 0,
        calculated_fields: list[CalculatedFieldDef] | None = None,
        db_type:    str = "sqlite",
    ) -> tuple[str, dict[str, Any]]:

        select_cols = self._select_columns(base_table, fields)
        select_cols += self._calculated_columns(fields, calculated_fields or [], db_type)

        select_sql = "SELECT\n  " + ",\n  ".join(select_cols)
        from_sql   = f"FROM {quote_identifier(base_table)}"
        join_sql   = self._join_clauses(joins)
        where_sql, params = self._where_clauses(filters)

        group_sql = ("GROUP BY " + ", ".join(quote_identifier(g) for g in group_by)
                     if group_by else "")
        order_sql = ("ORDER BY " + ", ".join(
                         quote_identifier(o.lstrip("-")) + (" DESC" if o.startswith("-") else "")
                         for o in order_by)
                     if order_by else "")

        parts = [select_sql, from_sql]
        for clause in (join_sql, where_sql, group_sql, order_sql):
            if clause:
                parts.append(clause)
        limit_clause = f"LIMIT {int(limit)}"
        if int(offset) > 0:
            limit_clause += f" OFFSET {int(offset)}"
        parts.append(limit_clause)

        return "\n".join(parts), params

    def estimate_complexity(self, joins: list, filters: list, group_by: list) -> str:
        score = len(joins) * 2 + len(filters) + len(group_by)
        if score <= 2:  return "low"
        if score <= 6:  return "medium"
        return "high"


sql_builder = SQLBuilder()
