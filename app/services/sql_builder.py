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

    """
    SQL metnini parça parça kuran sınıf.
    Tablo ve kolon adları quote_identifier ile güvenli hale getirilir; değerler ise parametre olarak (:p_0 gibi) gönderilir.
    """
    def _select_columns(self, base_table: str, fields: dict[str, str], dialect: str = "sqlite") -> list[str]:
        """
        SELECT listesindeki kolonları üretir. role 'off' olan kolonlar atlanır; hiç kolon kalmazsa tüm kolonlar (*) döner.
        Dönüş: tırnaklı kolon metinlerinin listesi.
        """
        cols = []
        for key, role in fields.items():
            # Rolü 'off' olan kolon SELECT'e eklenmez.
            if role == "off":
                continue
            # Noktalı ad (tablo.kolon) zaten tam nitelikli; nokta yoksa temel tablo adıyla birlikte yazılır.
            cols.append(quote_identifier(key, dialect) if "." in key
                        else f"{quote_identifier(base_table, dialect)}.{quote_identifier(key, dialect)}")
        # Hiç kolon seçilmediyse tüm kolonlar (*) alınır.
        return cols or [f"{quote_identifier(base_table, dialect)}.*"]

    def _calculated_columns(
        self,
        fields: dict[str, str],
        calculated_fields: list[CalculatedFieldDef],
        db_type: str,
        formula_only_columns: list[str] | None = None,
    ) -> list[str]:
        """
        Her hesaplanmış alan için formülü doğrulayıp (whitelist) hedef
        dialect'e derler, sonra "AS alias" ekleyerek SELECT listesine
        eklenecek parçayı üretir.

        allowed_columns iki kaynaktan gelir:
          1) Seçili (role != "off") fields'daki bare kolon adları — yani
             kullanıcı önce query builder'da bir kolonu "dahil" etmeden,
             o kolonu bir formülde kullanamaz (mevcut davranış, değişmedi).
          2) formula_only_columns — SADECE agregasyon/formül içinde
             kullanılacak, ham SELECT kolonu olarak EKLENMEYECEK kolonlar.
             Örn. "5 en çok satan ürün" sorgusunda LineTotal, SUM() içinde
             gerekli ama tek başına bir SELECT kolonu olarak (GROUP BY'a
             sokulmadığı için) sorguyu bozar — formula_only_columns bu
             kolonu whitelist'e ekler ama _select_columns hiç görmez.
        """
        if not calculated_fields:
            return []

        # Formüllerde kullanılabilecek kolon adları. Noktalı adlarda sadece son parça alınır.
        allowed_columns = {
            (key.split(".")[-1]) for key, role in fields.items() if role != "off"
        }
        if formula_only_columns:
            allowed_columns |= set(formula_only_columns)

        parts = []
        for cf in calculated_fields:
            try:
                compiled = validate_and_compile(cf.formula, db_type, allowed_columns)
            except ExpressionError as e:
                raise ValueError(f"Hesaplanmış alan {cf.name!r}: {e}")
            parts.append(f"{compiled} AS {quote_identifier(cf.name, db_type)}")
        return parts

    def _join_clauses(self, joins: list[JoinDef], dialect: str = "sqlite") -> str:
        """JOIN satırlarını üretir (ör. 'LEFT JOIN t2 ON t1.f1 = t2.f2'). Birden çok join satır satır birleştirilir."""
        parts = []
        for j in joins:
            # Her join parçası önce quote_identifier'dan geçer; güvenli olmayan bir ad ValueError verir.
            t1 = quote_identifier(j.t1, dialect); f1 = quote_identifier(j.f1, dialect)
            t2 = quote_identifier(j.t2, dialect); f2 = quote_identifier(j.f2, dialect)
            # JOIN tipi (JOIN, LEFT JOIN vb.) şema seviyesinde whitelist'ten geçtiği için tırnaksız yazılabilir.
            parts.append(f"{j.type} {t2} ON {t1}.{f1} = {t2}.{f2}")
        return "\n".join(parts)

    def _where_clauses(self, filters: list[FilterDef], dialect: str = "sqlite") -> tuple[str, dict[str, Any]]:
        """
        WHERE koşullarını üretir. Dönüş: (where metni, parametre sözlüğü).
        Koşullar AND ile bağlanır. IN için her değer ayrı parametre olur. Filtre yoksa boş metin döner.
        """
        parts: list[str] = []
        params: dict[str, Any] = {}

        for i, f in enumerate(filters):
            op  = f.operator   # zaten whitelist'ten geçti (FilterDef validator)
            col = f"{quote_identifier(f.table, dialect)}.{quote_identifier(f.column, dialect)}"
            # Parametre adı filtre sırasına göre üretilir (p_0, p_1...). Değer SQL metnine değil, parametre olarak gider.
            p   = f"p_{i}"

            # Whitelist double-check (DES-4)
            if op not in ALLOWED_OPERATORS:
                raise ValueError(f"İzin verilmeyen operatör: {op!r}")

            if op in ("IS NULL", "IS NOT NULL"):
                parts.append(f"{col} {op}")
                continue

            if op in ("IN", "NOT IN"):
                vals = f.value if isinstance(f.value, list) else [f.value]
                # Her IN değeri için ayrı bir yer tutucu (:p_0_0, :p_0_1 ...) üretilir.
                placeholders = ", ".join(f":{p}_{j}" for j in range(len(vals)))
                parts.append(f"{col} {op} ({placeholders})")
                for j, v in enumerate(vals):
                    params[f"{p}_{j}"] = v
                continue

            # BETWEEN iki parametre ister: alt sınır ve üst sınır.
            if op == "BETWEEN":
                parts.append(f"{col} BETWEEN :{p}_a AND :{p}_b")
                params[f"{p}_a"] = f.value
                params[f"{p}_b"] = f.value2
                continue

            # Diğer operatörler (=, >, LIKE vb.) tek parametre alır.
            parts.append(f"{col} {op} :{p}")
            params[p] = f.value

        # Tüm koşullar AND ile birleştirilir; hiç koşul yoksa WHERE yazılmaz.
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
        schema:     str | None = None,
        formula_only_columns: list[str] | None = None,
    ) -> tuple[str, dict[str, Any]]:

        """
        Tüm parçaları birleştirip SQL metni ve parametre sözlüğü döner.
        Sayfalama db_type'a göre yazılır (LIMIT, TOP veya FETCH). limit en fazla satır sayısı, offset atlanacak satır sayısıdır.
        Geçersiz kolon adı ya da ifade ValueError fırlatır.
        """
        # Oracle büyütmesi quote_identifier'da tek merkezden yapılır (burada tekrar yok).
        select_cols = self._select_columns(base_table, fields, db_type)
        select_cols += self._calculated_columns(
            fields, calculated_fields or [], db_type, formula_only_columns
        )

        # T-SQL'de LIMIT yok; offset=0 ise "SELECT TOP n" ile en başta uygulanır
        select_prefix = "SELECT"
        if db_type == "mssql" and int(offset) == 0:
            select_prefix = f"SELECT TOP {int(limit)}"

        select_sql = select_prefix + "\n  " + ",\n  ".join(select_cols)
        # Şema verilmişse tablo adı 'şema.tablo' biçiminde yazılır.
        qualified_table = f"{schema}.{base_table}" if schema else base_table
        from_sql   = f"FROM {quote_identifier(qualified_table, db_type)}"
        join_sql   = self._join_clauses(joins, db_type)
        where_sql, params = self._where_clauses(filters, db_type)

        # GROUP BY ve ORDER BY kolonları da quote_identifier'dan geçer. Sıralamada başta '-' varsa DESC olur.
        # Join varsa, nokta içermeyen ve calculated field alias'ı olmayan kolonlar base_table ile nitelenir;
        # aksi halde iki tabloda ortak kolon adı "ambiguous column" hatası verir. Alias'ı nitelemek SQL'de
        # alias'ı bozacağı için calculated field adları olduğu gibi kalır.
        alias_names = {cf.name for cf in (calculated_fields or [])}

        def _col(name: str) -> str:
            if joins and "." not in name and name not in alias_names:
                return f"{quote_identifier(base_table, db_type)}.{quote_identifier(name, db_type)}"
            return quote_identifier(name, db_type)

        group_sql = ("GROUP BY " + ", ".join(_col(g) for g in group_by)
                     if group_by else "")
        order_sql = ("ORDER BY " + ", ".join(
                         _col(o.lstrip("-")) + (" DESC" if o.startswith("-") else "")
                         for o in order_by)
                     if order_by else "")

        parts = [select_sql, from_sql]
        for clause in (join_sql, where_sql, group_sql, order_sql):
            if clause:
                parts.append(clause)

        # Sayfalama veritabanına göre farklı yazılır: Oracle FETCH, MSSQL OFFSET/FETCH veya TOP, diğerleri LIMIT.
        if db_type == "oracle":
            if int(offset) > 0:
                limit_clause = f"OFFSET {int(offset)} ROWS FETCH NEXT {int(limit)} ROWS ONLY"
            else:
                limit_clause = f"FETCH FIRST {int(limit)} ROWS ONLY"
            parts.append(limit_clause)
        elif db_type == "mssql":
            if int(offset) > 0:
                # T-SQL'de OFFSET/FETCH mutlaka bir ORDER BY gerektirir
                if not order_sql:
                    parts.append("ORDER BY (SELECT NULL)")
                parts.append(f"OFFSET {int(offset)} ROWS FETCH NEXT {int(limit)} ROWS ONLY")
            # offset == 0 durumunda TOP zaten SELECT'e eklendi, ayrı limit_clause gerekmiyor
        else:
            # limit ve offset int() ile sayıya çevrilir; metin olarak SQL'e girmez (enjeksiyona karşı).
            limit_clause = f"LIMIT {int(limit)}"
            if int(offset) > 0:
                limit_clause += f" OFFSET {int(offset)}"
            parts.append(limit_clause)

        return "\n".join(parts), params

    def estimate_complexity(self, joins: list, filters: list, group_by: list) -> str:
        """Sorgunun karmaşıklığını low / medium / high olarak tahmin eder (join, filtre ve gruplama sayısına göre). Sadece önizleme için kullanılır."""
        score = len(joins) * 2 + len(filters) + len(group_by)
        if score <= 2:  return "low"
        if score <= 6:  return "medium"
        return "high"


# Modül yüklenince tek bir SQLBuilder nesnesi oluşturulur ve tüm çağıranlar bunu paylaşır.
sql_builder = SQLBuilder()
