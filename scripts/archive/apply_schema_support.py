#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Çok şemalı veritabanları (MSSQL: Sales/Production/Person/HumanResources/
Purchasing, Postgres: public dışı şemalar) için /api/schema katmanına
opsiyonel ?schema= desteği ve Sorgu Oluşturucu'ya "Şema" seçici ekler.

Kullanım: /opt/superbi/venv/bin/python3 apply_schema_support.py
Çalıştırılacağı dizin: /opt/superbi
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMAPY = ROOT / "app" / "api" / "schema.py"
APIJS = ROOT / "frontend" / "api.js"
APPJS = ROOT / "frontend" / "app.js"

EXPECTED_OLD_SCHEMAPY = '''"""
/api/schema — bağlı DB'nin tablo/kolon şeması (join builder için)
YENİDEN OLUŞTURULDU: main.py'de include_router(schema.router, ...) referansı
var ama dosya bulunamadığı için kullanım şekli oradan çıkarıldı.

conn_id path parametresi -> get_connection_engine ile sahiplik kontrolü.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect

from app.core.repository import ConnectionRepository
from app.deps import get_connection_engine, get_current_user, get_repo

router = APIRouter()


@router.get("/{conn_id}/tables")
def list_tables(
    conn_id:  str,
    engine_meta = Depends(get_connection_engine),
):
    engine, _meta = engine_meta
    try:
        insp = inspect(engine)
        return {"tables": insp.get_table_names()}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Şema okunamadı: {e}")


@router.get("/{conn_id}/tables/{table_name}/columns")
def list_columns(
    conn_id:    str,
    table_name: str,
    engine_meta = Depends(get_connection_engine),
):
    engine, _meta = engine_meta
    try:
        insp = inspect(engine)
        if table_name not in insp.get_table_names():
            raise HTTPException(status_code=404, detail=f"Tablo bulunamadı: {table_name}")
        cols = insp.get_columns(table_name)
        return {
            "table": table_name,
            "columns": [
                {"name": c["name"], "type": str(c["type"]), "nullable": c.get("nullable", True)}
                for c in cols
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Şema okunamadı: {e}")


@router.get("/{conn_id}/tables/{table_name}/foreign-keys")
def list_foreign_keys(
    conn_id:    str,
    table_name: str,
    engine_meta = Depends(get_connection_engine),
):
    """Join builder'da otomatik join önerisi için."""
    engine, _meta = engine_meta
    try:
        insp = inspect(engine)
        fks = insp.get_foreign_keys(table_name)
        return {
            "table": table_name,
            "foreign_keys": [
                {
                    "constrained_columns": fk["constrained_columns"],
                    "referred_table":      fk["referred_table"],
                    "referred_columns":    fk["referred_columns"],
                }
                for fk in fks
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FK bilgisi okunamadı: {e}")
'''

NEW_SCHEMAPY = '''"""
/api/schema — bağlı DB'nin tablo/kolon şeması (join builder için)

conn_id path parametresi -> get_connection_engine ile sahiplik kontrolü.
Opsiyonel ?schema=... parametresi çok şemalı veritabanları (MSSQL, Postgres
non-public şemalar) için doğru şemayı hedeflemeyi sağlar; verilmezse
SQLAlchemy'nin varsayılan şeması (MSSQL'de dbo, Postgres'te public) kullanılır.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect

from app.core.repository import ConnectionRepository
from app.deps import get_connection_engine, get_current_user, get_repo

router = APIRouter()


@router.get("/{conn_id}/schemas")
def list_schemas(
    conn_id: str,
    engine_meta = Depends(get_connection_engine),
):
    """Veritabanındaki tüm şemaları döner (SQLite/tek-şemalı DB'lerde boş/tek eleman dönebilir)."""
    engine, _meta = engine_meta
    try:
        insp = inspect(engine)
        return {"schemas": insp.get_schema_names()}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Şema listesi okunamadı: {e}")


@router.get("/{conn_id}/tables")
def list_tables(
    conn_id:  str,
    schema: Optional[str] = None,
    engine_meta = Depends(get_connection_engine),
):
    engine, _meta = engine_meta
    try:
        insp = inspect(engine)
        return {"tables": insp.get_table_names(schema=schema)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Şema okunamadı: {e}")


@router.get("/{conn_id}/tables/{table_name}/columns")
def list_columns(
    conn_id:    str,
    table_name: str,
    schema: Optional[str] = None,
    engine_meta = Depends(get_connection_engine),
):
    engine, _meta = engine_meta
    try:
        insp = inspect(engine)
        if table_name not in insp.get_table_names(schema=schema):
            raise HTTPException(status_code=404, detail=f"Tablo bulunamadı: {table_name}")
        cols = insp.get_columns(table_name, schema=schema)
        return {
            "table": table_name,
            "columns": [
                {"name": c["name"], "type": str(c["type"]), "nullable": c.get("nullable", True)}
                for c in cols
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Şema okunamadı: {e}")


@router.get("/{conn_id}/tables/{table_name}/foreign-keys")
def list_foreign_keys(
    conn_id:    str,
    table_name: str,
    schema: Optional[str] = None,
    engine_meta = Depends(get_connection_engine),
):
    """Join builder'da otomatik join önerisi için."""
    engine, _meta = engine_meta
    try:
        insp = inspect(engine)
        fks = insp.get_foreign_keys(table_name, schema=schema)
        return {
            "table": table_name,
            "foreign_keys": [
                {
                    "constrained_columns": fk["constrained_columns"],
                    "referred_table":      fk["referred_table"],
                    "referred_columns":    fk["referred_columns"],
                }
                for fk in fks
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FK bilgisi okunamadı: {e}")
'''


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
    for p in (SCHEMAPY, APIJS, APPJS):
        if not p.exists():
            print(f"[HATA] Bulunamadı: {p}")
            sys.exit(1)

    schemapy = SCHEMAPY.read_text(encoding="utf-8")
    apijs = APIJS.read_text(encoding="utf-8")
    appjs = APPJS.read_text(encoding="utf-8")

    # ---- 1) schema.py tam değişimi (içerik beklenenle birebir eşleşmeli) ----
    if schemapy != EXPECTED_OLD_SCHEMAPY:
        print("[HATA] app/api/schema.py beklenenden farklı — muhtemelen daha önce elle "
              "değiştirilmiş. Güvenlik için dokunmadım, dosyayı elle kontrol edin.")
        sys.exit(1)
    schemapy = NEW_SCHEMAPY

    # ---- 2) api.js: schema metodlarını şema-farkında hale getir ----
    OLD_API = '''    // ---- schema ----
    listTables: (connId) => request("GET", `/api/schema/${connId}/tables`),
    listColumns: (connId, table) =>
      request("GET", `/api/schema/${connId}/tables/${encodeURIComponent(table)}/columns`),
    listForeignKeys: (connId, table) =>
      request("GET", `/api/schema/${connId}/tables/${encodeURIComponent(table)}/foreign-keys`),'''
    NEW_API = '''    // ---- schema ----
    listSchemas: (connId) => request("GET", `/api/schema/${connId}/schemas`),
    listTables: (connId, schema) =>
      request("GET", `/api/schema/${connId}/tables${schema ? `?schema=${encodeURIComponent(schema)}` : ""}`),
    listColumns: (connId, table, schema) =>
      request("GET", `/api/schema/${connId}/tables/${encodeURIComponent(table)}/columns${schema ? `?schema=${encodeURIComponent(schema)}` : ""}`),
    listForeignKeys: (connId, table, schema) =>
      request("GET", `/api/schema/${connId}/tables/${encodeURIComponent(table)}/foreign-keys${schema ? `?schema=${encodeURIComponent(schema)}` : ""}`),'''
    apijs = replace_once(apijs, OLD_API, NEW_API, "api.js schema metodları")

    # ---- 3) app.js: Query Builder'a Şema seçici ekle ----
    OLD_APP = '''  const topCard = el("div", { class: "card" });
  const connSel = el("select", { id: "qb-conn-select" },
    state.connections.map((c) => el("option", { value: c.conn_id }, `${c.conn_id} (${c.database})`))
  );
  if (state.selectedConnId) connSel.value = state.selectedConnId;

  const tableSel = el("select", { id: "qb-table-select" }, [el("option", { value: "" }, "Tablo seçin…")]);

  topCard.appendChild(el("div", { class: "grid-2" }, [
    el("div", {}, [el("label", {}, "Bağlantı"), connSel]),
    el("div", {}, [el("label", {}, "Tablo"), tableSel]),
  ]));
  root.appendChild(topCard);

  const builderCard = el("div", { class: "card", id: "qb-builder-card" });
  builderCard.style.display = "none";
  root.appendChild(builderCard);

  const resultCard = el("div", { class: "card", id: "qb-result-card" });
  resultCard.style.display = "none";
  root.appendChild(resultCard);

  async function loadTablesFor(connId) {
    state.selectedConnId = connId;
    tableSel.innerHTML = "";
    tableSel.appendChild(el("option", { value: "" }, "Yükleniyor…"));
    try {
      const res = await api.listTables(connId);
      state.tables = res.tables || [];
      tableSel.innerHTML = "";
      tableSel.appendChild(el("option", { value: "" }, "Tablo seçin…"));
      for (const t of state.tables) tableSel.appendChild(el("option", { value: t }, t));
      if (state.selectedTable && state.tables.includes(state.selectedTable)) {
        tableSel.value = state.selectedTable;
        await loadColumnsFor(connId, state.selectedTable);
      }
    } catch (e) {
      handleApiError(e, "Tablolar alınamadı");
      tableSel.innerHTML = "";
      tableSel.appendChild(el("option", { value: "" }, "Hata"));
    }
  }

  async function loadColumnsFor(connId, table) {
    state.selectedTable = table;
    state.fields = {};
    state.joins = [];
    state.filters = [];
    state.groupBy = [];
    state.orderBy = [];
    state.calculatedFields = [];
    try {
      const res = await api.listColumns(connId, table);
      state.columns = res.columns || [];
      for (const c of state.columns) state.fields[c.name] = "dim";
      builderCard.style.display = "block";
      renderBuilderCard(builderCard, resultCard);
    } catch (e) { handleApiError(e, "Kolonlar alınamadı"); }
  }

  connSel.addEventListener("change", () => {
    resetQueryBuilderState();
    builderCard.style.display = "none";
    resultCard.style.display = "none";
    loadTablesFor(connSel.value);
  });

  tableSel.addEventListener("change", () => {
    if (!tableSel.value) { builderCard.style.display = "none"; return; }
    loadColumnsFor(connSel.value, tableSel.value);
  });

  await loadTablesFor(connSel.value);'''
    NEW_APP = '''  const topCard = el("div", { class: "card" });
  const connSel = el("select", { id: "qb-conn-select" },
    state.connections.map((c) => el("option", { value: c.conn_id }, `${c.conn_id} (${c.database})`))
  );
  if (state.selectedConnId) connSel.value = state.selectedConnId;

  const schemaSel = el("select", { id: "qb-schema-select" }, [el("option", { value: "" }, "(varsayılan)")]);
  const tableSel = el("select", { id: "qb-table-select" }, [el("option", { value: "" }, "Tablo seçin…")]);

  topCard.appendChild(el("div", { class: "grid-3" }, [
    el("div", {}, [el("label", {}, "Bağlantı"), connSel]),
    el("div", {}, [el("label", {}, "Şema"), schemaSel]),
    el("div", {}, [el("label", {}, "Tablo"), tableSel]),
  ]));
  root.appendChild(topCard);

  const builderCard = el("div", { class: "card", id: "qb-builder-card" });
  builderCard.style.display = "none";
  root.appendChild(builderCard);

  const resultCard = el("div", { class: "card", id: "qb-result-card" });
  resultCard.style.display = "none";
  root.appendChild(resultCard);

  async function loadSchemasFor(connId) {
    schemaSel.innerHTML = "";
    schemaSel.appendChild(el("option", { value: "" }, "(varsayılan)"));
    try {
      const res = await api.listSchemas(connId);
      for (const s of res.schemas || []) schemaSel.appendChild(el("option", { value: s }, s));
      if (state.selectedSchema && (res.schemas || []).includes(state.selectedSchema)) {
        schemaSel.value = state.selectedSchema;
      }
    } catch (e) {
      // Bazı DB tipleri (örn. SQLite) şema listesini desteklemeyebilir — sessizce (varsayılan) ile devam et
    }
  }

  async function loadTablesFor(connId, schema) {
    state.selectedConnId = connId;
    state.selectedSchema = schema || null;
    tableSel.innerHTML = "";
    tableSel.appendChild(el("option", { value: "" }, "Yükleniyor…"));
    try {
      const res = await api.listTables(connId, schema);
      state.tables = res.tables || [];
      tableSel.innerHTML = "";
      tableSel.appendChild(el("option", { value: "" }, "Tablo seçin…"));
      for (const t of state.tables) tableSel.appendChild(el("option", { value: t }, t));
      if (state.selectedTable && state.tables.includes(state.selectedTable)) {
        tableSel.value = state.selectedTable;
        await loadColumnsFor(connId, state.selectedTable, schema);
      }
    } catch (e) {
      handleApiError(e, "Tablolar alınamadı");
      tableSel.innerHTML = "";
      tableSel.appendChild(el("option", { value: "" }, "Hata"));
    }
  }

  async function loadColumnsFor(connId, table, schema) {
    state.selectedTable = table;
    state.fields = {};
    state.joins = [];
    state.filters = [];
    state.groupBy = [];
    state.orderBy = [];
    state.calculatedFields = [];
    try {
      const res = await api.listColumns(connId, table, schema);
      state.columns = res.columns || [];
      for (const c of state.columns) state.fields[c.name] = "dim";
      builderCard.style.display = "block";
      renderBuilderCard(builderCard, resultCard);
    } catch (e) { handleApiError(e, "Kolonlar alınamadı"); }
  }

  connSel.addEventListener("change", () => {
    resetQueryBuilderState();
    builderCard.style.display = "none";
    resultCard.style.display = "none";
    loadSchemasFor(connSel.value).then(() => loadTablesFor(connSel.value, schemaSel.value));
  });

  schemaSel.addEventListener("change", () => {
    resetQueryBuilderState();
    builderCard.style.display = "none";
    resultCard.style.display = "none";
    loadTablesFor(connSel.value, schemaSel.value);
  });

  tableSel.addEventListener("change", () => {
    if (!tableSel.value) { builderCard.style.display = "none"; return; }
    loadColumnsFor(connSel.value, tableSel.value, schemaSel.value);
  });

  await loadSchemasFor(connSel.value);
  await loadTablesFor(connSel.value, schemaSel.value);'''
    appjs = replace_once(appjs, OLD_APP, NEW_APP, "Query Builder şema seçici")

    # ---- Yedek al ve yaz ----
    shutil.copy2(SCHEMAPY, str(SCHEMAPY) + ".bak")
    shutil.copy2(APIJS, str(APIJS) + ".bak4")
    shutil.copy2(APPJS, str(APPJS) + ".bak4")
    SCHEMAPY.write_text(schemapy, encoding="utf-8")
    APIJS.write_text(apijs, encoding="utf-8")
    APPJS.write_text(appjs, encoding="utf-8")

    print("[OK] schema.py, api.js, app.js güncellendi.")
    print("Yedekler: app/api/schema.py.bak, frontend/api.js.bak4, frontend/app.js.bak4")
    print("Sonra: systemctl restart superbi, tarayıcıda hard-refresh.")


if __name__ == "__main__":
    main()
