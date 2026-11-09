#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sorgu Oluşturucu'nun ürettiği SQL'i MSSQL için düzeltir (T-SQL'de LIMIT yok,
TOP/OFFSET-FETCH kullanılır) ve base_table'a şema desteği ekler (Query
Builder'daki Şema seçicisinden gelen değer artık FROM/preview/run/stream'e
gerçekten ulaşıyor).

Kullanım: /opt/superbi/venv/bin/python3 apply_mssql_limit_fix.py
Çalıştırılacağı dizin: /opt/superbi
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMAS = ROOT / "app" / "models" / "schemas.py"
BUILDER = ROOT / "app" / "services" / "sql_builder.py"
QUERYPY = ROOT / "app" / "api" / "query.py"
APPJS = ROOT / "frontend" / "app.js"


def replace_once(text, old, new, label):
    """
    Metinde 'old' metnini tam 1 kez arar ve 'new' ile değiştirir. Eşleşme sayısı 1 değilse ekrana hata yazıp betiği durdurur.
    Bu sayede yanlış yere ya da iki kez yama yapılması engellenir. label: hata mesajında gösterilen ad.
    """
    count = text.count(old)
    if count != 1:
        print(f"[HATA] '{label}' — beklenen 1 eşleşme, bulunan: {count}")
        print("---- ARANAN METİN (ilk 200 karakter) ----")
        print(old[:200])
        sys.exit(1)
    return text.replace(old, new, 1)


def main():
    """
    Yama betiğinin ana akışı: hedef dosyayı okur, değişiklikleri sırayla uygular ve sonucu yazar.
    Betik tek seferlik yazılmıştır; çalıştırmadan önce hedef dosyanın zaten yamalanıp yamalanmadığına bakın.
    """
    for p in (SCHEMAS, BUILDER, QUERYPY, APPJS):
        if not p.exists():
            print(f"[HATA] Bulunamadı: {p}")
            sys.exit(1)

    schemas = SCHEMAS.read_text(encoding="utf-8")
    builder = BUILDER.read_text(encoding="utf-8")
    querypy = QUERYPY.read_text(encoding="utf-8")
    appjs = APPJS.read_text(encoding="utf-8")

    # ---- 1) schemas.py: schema_name + db_type alanları ----
    OLD1 = '''class _QueryShapeBase(BaseModel):
    """QueryRequest ve QueryRunRequest'in ortak SELECT/JOIN/WHERE gövdesi."""
    conn_id:    str
    base_table: str
    fields:     dict[str, str]        = Field(default_factory=dict)  # {kolon: rol} rol="off" hariç seçilir'''
    NEW1 = '''class _QueryShapeBase(BaseModel):
    """QueryRequest ve QueryRunRequest'in ortak SELECT/JOIN/WHERE gövdesi."""
    conn_id:    str
    base_table: str
    schema_name: str | None = None  # çok şemalı DB'lerde (MSSQL/Postgres) hedef şema
    fields:     dict[str, str]        = Field(default_factory=dict)  # {kolon: rol} rol="off" hariç seçilir'''
    schemas = replace_once(schemas, OLD1, NEW1, "schemas.py _QueryShapeBase.schema_name")

    OLD2 = '''class SQLPreviewRequest(_QueryShapeBase):
    limit: int = Field(default=100, ge=1, le=100_000)'''
    NEW2 = '''class SQLPreviewRequest(_QueryShapeBase):
    limit: int = Field(default=100, ge=1, le=100_000)
    db_type: str | None = None  # sadece önizleme SQL metnini doğru dialect'te göstermek için (auth/veri erişimi yok)'''
    schemas = replace_once(schemas, OLD2, NEW2, "schemas.py SQLPreviewRequest.db_type")

    # ---- 2) sql_builder.py: build() — schema param + MSSQL TOP/OFFSET-FETCH ----
    OLD3 = '''    def build(
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

        if db_type == "oracle":
            base_table = base_table.upper()
            fields = {k.upper(): v for k, v in fields.items()}
        select_cols = self._select_columns(base_table, fields)
        select_cols += self._calculated_columns(fields, calculated_fields or [], db_type)

        select_sql = "SELECT\\n  " + ",\\n  ".join(select_cols)
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
        if db_type == "oracle":
            if int(offset) > 0:
                limit_clause = f"OFFSET {int(offset)} ROWS FETCH NEXT {int(limit)} ROWS ONLY"
            else:
                limit_clause = f"FETCH FIRST {int(limit)} ROWS ONLY"
        else:
            limit_clause = f"LIMIT {int(limit)}"
            if int(offset) > 0:
                limit_clause += f" OFFSET {int(offset)}"
        parts.append(limit_clause)

        return "\\n".join(parts), params'''
    NEW3 = '''    def build(
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
    ) -> tuple[str, dict[str, Any]]:

        if db_type == "oracle":
            base_table = base_table.upper()
            fields = {k.upper(): v for k, v in fields.items()}
            if schema:
                schema = schema.upper()
        select_cols = self._select_columns(base_table, fields)
        select_cols += self._calculated_columns(fields, calculated_fields or [], db_type)

        # T-SQL'de LIMIT yok; offset=0 ise "SELECT TOP n" ile en başta uygulanır
        select_prefix = "SELECT"
        if db_type == "mssql" and int(offset) == 0:
            select_prefix = f"SELECT TOP {int(limit)}"

        select_sql = select_prefix + "\\n  " + ",\\n  ".join(select_cols)
        qualified_table = f"{schema}.{base_table}" if schema else base_table
        from_sql   = f"FROM {quote_identifier(qualified_table)}"
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
            limit_clause = f"LIMIT {int(limit)}"
            if int(offset) > 0:
                limit_clause += f" OFFSET {int(offset)}"
            parts.append(limit_clause)

        return "\\n".join(parts), params'''
    builder = replace_once(builder, OLD3, NEW3, "sql_builder.py build() MSSQL desteği")

    # ---- 3) query.py: 3 çağrı noktasına schema= ekle, preview'a db_type= ekle ----
    OLD4 = '''        sql, _ = sql_builder.build(
            base_table=body.base_table,
            fields=body.fields,
            joins=body.joins,
            filters=body.filters,
            group_by=body.group_by,
            order_by=body.order_by,
            limit=body.limit,
            calculated_fields=body.calculated_fields,
            db_type="sqlite",
        )'''
    NEW4 = '''        sql, _ = sql_builder.build(
            base_table=body.base_table,
            fields=body.fields,
            joins=body.joins,
            filters=body.filters,
            group_by=body.group_by,
            order_by=body.order_by,
            limit=body.limit,
            calculated_fields=body.calculated_fields,
            db_type=body.db_type or "sqlite",
            schema=body.schema_name,
        )'''
    querypy = replace_once(querypy, OLD4, NEW4, "query.py preview_sql schema/db_type")

    OLD5 = '''        sql, params = sql_builder.build(
            base_table=body.base_table,
            fields=body.fields,
            joins=body.joins,
            filters=body.filters,
            group_by=body.group_by,
            order_by=body.order_by,
            limit=body.sample,
            offset=0,
            calculated_fields=body.calculated_fields,
            db_type=meta.db_type,
        )'''
    NEW5 = '''        sql, params = sql_builder.build(
            base_table=body.base_table,
            fields=body.fields,
            joins=body.joins,
            filters=body.filters,
            group_by=body.group_by,
            order_by=body.order_by,
            limit=body.sample,
            offset=0,
            calculated_fields=body.calculated_fields,
            db_type=meta.db_type,
            schema=body.schema_name,
        )'''
    querypy = replace_once(querypy, OLD5, NEW5, "query.py run_query schema")

    OLD6 = '''        sql, params = sql_builder.build(
            base_table=body.base_table,
            fields=body.fields,
            joins=body.joins,
            filters=body.filters,
            group_by=body.group_by,
            order_by=body.order_by,
            limit=body.limit,
            offset=body.offset,
            calculated_fields=body.calculated_fields,
            db_type=meta.db_type,
        )'''
    NEW6 = '''        sql, params = sql_builder.build(
            base_table=body.base_table,
            fields=body.fields,
            joins=body.joins,
            filters=body.filters,
            group_by=body.group_by,
            order_by=body.order_by,
            limit=body.limit,
            offset=body.offset,
            calculated_fields=body.calculated_fields,
            db_type=meta.db_type,
            schema=body.schema_name,
        )'''
    querypy = replace_once(querypy, OLD6, NEW6, "query.py stream_query schema")

    # ---- 4) app.js: buildQueryShape() + doPreview() ----
    OLD7 = '''function buildQueryShape() {
  return {
    conn_id: state.selectedConnId,
    base_table: state.selectedTable,
    fields: state.fields,
    joins: state.joins,
    filters: state.filters,
    group_by: state.groupBy,
    order_by: state.orderBy,
    calculated_fields: state.calculatedFields || [],
  };
}'''
    NEW7 = '''function buildQueryShape() {
  return {
    conn_id: state.selectedConnId,
    base_table: state.selectedTable,
    schema_name: state.selectedSchema || null,
    fields: state.fields,
    joins: state.joins,
    filters: state.filters,
    group_by: state.groupBy,
    order_by: state.orderBy,
    calculated_fields: state.calculatedFields || [],
  };
}'''
    appjs = replace_once(appjs, OLD7, NEW7, "app.js buildQueryShape schema_name")

    OLD8 = '''async function doPreview(resultCard) {
  try {
    const body = { ...buildQueryShape(), limit: state.sample };
    const res = await api.previewSql(body);'''
    NEW8 = '''async function doPreview(resultCard) {
  try {
    const conn = state.connections.find((c) => c.conn_id === state.selectedConnId);
    const body = { ...buildQueryShape(), limit: state.sample, db_type: conn ? conn.db_type : "sqlite" };
    const res = await api.previewSql(body);'''
    appjs = replace_once(appjs, OLD8, NEW8, "app.js doPreview db_type")

    # ---- Yedek al ve yaz ----
    shutil.copy2(SCHEMAS, str(SCHEMAS) + ".bak5")
    shutil.copy2(BUILDER, str(BUILDER) + ".bak5")
    shutil.copy2(QUERYPY, str(QUERYPY) + ".bak5")
    shutil.copy2(APPJS, str(APPJS) + ".bak5")
    SCHEMAS.write_text(schemas, encoding="utf-8")
    BUILDER.write_text(builder, encoding="utf-8")
    QUERYPY.write_text(querypy, encoding="utf-8")
    APPJS.write_text(appjs, encoding="utf-8")

    print("[OK] schemas.py, sql_builder.py, query.py, app.js güncellendi.")
    print("Yedekler: *.bak5")
    print("Not: Kaydedilmiş dataset'ler ve dashboard widget'ları bu patch'e dahil DEĞİL —")
    print("     schema-qualified MSSQL tablosunu bir dataset olarak kaydedip widget'a")
    print("     bağlarsanız ayrıca test edilmesi gerekir.")
    print("Sonra: systemctl restart superbi, tarayıcıda hard-refresh.")


if __name__ == "__main__":
    main()
