#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1) "Analiz Et"i DB-geneli hale getirir: artık tek tıkla veritabanındaki TÜM
   kullanıcı şemalarını (sistem şemaları hariç) tarar — MSSQL'de Sales/
   Production/Person/... için ayrı ayrı tıklamaya gerek kalmaz.
2) Sorgu Oluşturucu'ya "Önerilen İlişkiler" butonu ekler — seçili tabloyla
   ilgili, daha önce analiz edilmiş (herhangi bir şemadaki) ilişkileri
   listeler ve tek tıkla join olarak ekletir.

Kullanım: /opt/superbi/venv/bin/python3 apply_relationship_suggestions.py
Çalıştırılacağı dizin: /opt/superbi
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ANALYZEPY = ROOT / "app" / "api" / "analyze.py"
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
    for p in (ANALYZEPY, APPJS):
        if not p.exists():
            print(f"[HATA] Bulunamadı: {p}")
            sys.exit(1)

    analyzepy = ANALYZEPY.read_text(encoding="utf-8")
    appjs = APPJS.read_text(encoding="utf-8")

    # ---- 1) analyze.py: _SYSTEM_SCHEMAS sabiti + all_schemas alanı ----
    OLD1 = '''logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic modelleri
# ---------------------------------------------------------------------------

class AnalyzeTablesRequest(BaseModel):
    schema_name: Optional[str] = None
    tables: Optional[list[str]] = None  # None = tüm tablolar'''
    NEW1 = '''logger = logging.getLogger(__name__)
router = APIRouter()

# all_schemas=True iken taranmayacak sistem şemaları (MSSQL fixed database
# role'ları + information_schema, Postgres pg_catalog/pg_toast, vb.)
_SYSTEM_SCHEMAS = {
    "sys", "information_schema", "guest",
    "db_accessadmin", "db_backupoperator", "db_datareader", "db_datawriter",
    "db_ddladmin", "db_denydatareader", "db_denydatawriter", "db_owner",
    "db_securityadmin", "pg_catalog", "pg_toast",
}


# ---------------------------------------------------------------------------
# Pydantic modelleri
# ---------------------------------------------------------------------------

class AnalyzeTablesRequest(BaseModel):
    schema_name: Optional[str] = None
    tables: Optional[list[str]] = None  # None = tüm tablolar
    all_schemas: bool = False  # True ise sistem şemaları hariç TÜM şemalar taranır'''
    analyzepy = replace_once(analyzepy, OLD1, NEW1, "analyze.py sabitler + all_schemas alanı")

    # ---- 2) analyze.py: analyze_tables() — çoklu şema desteği ----
    OLD2 = '''@router.post("/{conn_id}/tables")
def analyze_tables(
    conn_id: str,
    body: AnalyzeTablesRequest,
    current                       = Depends(get_current_user),
    registry: ConnectorRegistry    = Depends(get_registry),
    repo:     ConnectionRepository = Depends(get_repo),
    store:    SQLiteStore          = Depends(get_store),
):
    """
    Bağlantıdaki tabloları analiz eder; grain, sütun sınıflandırma ve
    FK ilişkilerini bulur, sonuçları SQLite metadata DB'ye kaydeder.
    """
    engine, _ = resolve_connection_engine(conn_id, current, registry, repo)

    from sqlalchemy import inspect as sa_inspect
    insp = sa_inspect(engine)

    schema = body.schema_name
    try:
        all_tables = insp.get_table_names(schema=schema)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tablo listesi alınamadı: {e}")

    # İstenen tablo listesi verilmişse filtrele
    target_tables = body.tables if body.tables else all_tables
    target_tables = [t for t in target_tables if t in all_tables]

    # Tam nitelikli tablo adı (sorgu için)
    def full_name(table: str) -> str:
        return f"{schema}.{table}" if schema else table

    profiled = []
    errors = []

    # 1) Tablo profilleri
    for table in target_tables:
        try:
            profile = ga.profile_table(engine, full_name(table))
            _save_profile(store, conn_id, profile)
            profiled.append(profile.to_dict())
            logger.info("Profil kaydedildi: %s.%s", conn_id, table)
        except Exception as e:
            logger.warning("Profil hatası (%s): %s", table, e)
            errors.append({"table": table, "error": str(e)})

    # 2) FK ilişkileri (tüm şema için tek seferde)
    fk_rels = []
    try:
        fk_rels = ga.discover_fk_relationships(engine, schema=schema)
        for rel in fk_rels:
            try:
                _save_relationship(store, conn_id, rel)
            except Exception as e:
                logger.warning("İlişki kayıt hatası: %s", e)
    except Exception as e:
        logger.warning("FK keşfi hatası: %s", e)
        errors.append({"fk_discovery": str(e)})

    return {
        "conn_id":       conn_id,
        "schema":        schema,
        "tables_found":  len(all_tables),
        "tables_profiled": len(profiled),
        "fk_relationships": len(fk_rels),
        "errors":        errors,
        "profiles":      profiled,
        "relationships": [r.to_dict() for r in fk_rels],
    }'''
    NEW2 = '''@router.post("/{conn_id}/tables")
def analyze_tables(
    conn_id: str,
    body: AnalyzeTablesRequest,
    current                       = Depends(get_current_user),
    registry: ConnectorRegistry    = Depends(get_registry),
    repo:     ConnectionRepository = Depends(get_repo),
    store:    SQLiteStore          = Depends(get_store),
):
    """
    Bağlantıdaki tabloları analiz eder; grain, sütun sınıflandırma ve
    FK ilişkilerini bulur, sonuçları SQLite metadata DB'ye kaydeder.

    all_schemas=True ise veritabanındaki TÜM kullanıcı şemaları taranır
    (sistem şemaları _SYSTEM_SCHEMAS ile hariç tutulur) — çok şemalı
    DB'lerde (MSSQL vb.) her şema için ayrı istek atmak gerekmez.
    """
    engine, _ = resolve_connection_engine(conn_id, current, registry, repo)

    from sqlalchemy import inspect as sa_inspect
    insp = sa_inspect(engine)

    def run_for_schema(schema: Optional[str]) -> dict:
        try:
            all_tables = insp.get_table_names(schema=schema)
        except Exception as e:
            return {
                "schema": schema, "tables_found": 0,
                "profiled": [], "fk_rels": [],
                "errors": [{"schema": schema, "error": f"Tablo listesi alınamadı: {e}"}],
            }

        target_tables = body.tables if body.tables else all_tables
        target_tables = [t for t in target_tables if t in all_tables]

        def full_name(table: str) -> str:
            return f"{schema}.{table}" if schema else table

        profiled = []
        errors = []

        # 1) Tablo profilleri
        for table in target_tables:
            try:
                profile = ga.profile_table(engine, full_name(table))
                _save_profile(store, conn_id, profile)
                profiled.append(profile.to_dict())
                logger.info("Profil kaydedildi: %s.%s", conn_id, full_name(table))
            except Exception as e:
                logger.warning("Profil hatası (%s): %s", full_name(table), e)
                errors.append({"table": full_name(table), "error": str(e)})

        # 2) FK ilişkileri (bu şema için)
        fk_rels = []
        try:
            fk_rels = ga.discover_fk_relationships(engine, schema=schema)
            for rel in fk_rels:
                try:
                    _save_relationship(store, conn_id, rel)
                except Exception as e:
                    logger.warning("İlişki kayıt hatası: %s", e)
        except Exception as e:
            logger.warning("FK keşfi hatası (%s): %s", schema, e)
            errors.append({"fk_discovery": str(e), "schema": schema})

        return {
            "schema": schema, "tables_found": len(all_tables),
            "profiled": profiled, "fk_rels": fk_rels, "errors": errors,
        }

    if body.all_schemas:
        try:
            schema_names = insp.get_schema_names()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Şema listesi alınamadı: {e}")
        target_schemas = [
            s for s in schema_names if s and s.lower() not in _SYSTEM_SCHEMAS
        ]
        results = [run_for_schema(s) for s in target_schemas]
    else:
        results = [run_for_schema(body.schema_name)]

    all_profiled = [p for r in results for p in r["profiled"]]
    all_fk_rels  = [rel for r in results for rel in r["fk_rels"]]
    all_errors   = [e for r in results for e in r["errors"]]
    tables_found_total = sum(r["tables_found"] for r in results)

    return {
        "conn_id":          conn_id,
        "schemas_scanned":  [r["schema"] for r in results],
        "tables_found":     tables_found_total,
        "tables_profiled":  len(all_profiled),
        "fk_relationships": len(all_fk_rels),
        "errors":           all_errors,
        "profiles":         all_profiled,
        "relationships":    [r.to_dict() for r in all_fk_rels],
    }'''
    analyzepy = replace_once(analyzepy, OLD2, NEW2, "analyze.py analyze_tables() çoklu şema")

    # ---- 3) app.js: analyzeBtn — prompt kaldırıldı, all_schemas:true ----
    OLD3 = '''    analyzeBtn.addEventListener("click", () =>
      withBusy(analyzeBtn, async () => {
        const schemaName = prompt(
          "Şema adı (opsiyonel). Boş bırakırsanız veritabanının varsayılan şeması taranır.\\n" +
          "Çok şemalı veritabanlarında (örn. MSSQL: Sales, Production, Person, HumanResources, " +
          "Purchasing) her şemayı ayrı ayrı analiz etmeniz gerekir.",
          ""
        );
        if (schemaName === null) return; // iptal edildi
        try {
          const res = await api.analyzeTables(c.conn_id, { schema_name: schemaName || null });
          toast(
            `Analiz tamam${schemaName ? ` (${schemaName})` : ""}: ${res.tables_profiled}/${res.tables_found} tablo, ${res.fk_relationships} FK ilişkisi bulundu`,
            "success"
          );
          if (res.errors && res.errors.length) {
            console.warn("Analiz hataları:", res.errors);
            toast(`${res.errors.length} tabloda hata oluştu — konsolu kontrol edin`, "error");
          }
          await showAnalysisResults(c.conn_id);
        } catch (e) { handleApiError(e, "Analiz başarısız"); }
      })
    );'''
    NEW3 = '''    analyzeBtn.addEventListener("click", () =>
      withBusy(analyzeBtn, async () => {
        try {
          const res = await api.analyzeTables(c.conn_id, { all_schemas: true });
          const schemaCount = (res.schemas_scanned || []).length;
          toast(
            `Analiz tamam (${schemaCount} şema): ${res.tables_profiled}/${res.tables_found} tablo, ${res.fk_relationships} FK ilişkisi bulundu`,
            "success"
          );
          if (res.errors && res.errors.length) {
            console.warn("Analiz hataları:", res.errors);
            toast(`${res.errors.length} tabloda hata oluştu — konsolu kontrol edin`, "error");
          }
          await showAnalysisResults(c.conn_id);
        } catch (e) { handleApiError(e, "Analiz başarısız"); }
      })
    );'''
    appjs = replace_once(appjs, OLD3, NEW3, "app.js analyzeBtn all_schemas")

    # ---- 4) app.js: Query Builder'a "Önerilen İlişkiler" ----
    OLD4 = '''  builderCard.appendChild(addJoinBtn);

  builderCard.appendChild(el("label", { style: "margin-top:16px" }, "Filtreler"));'''
    NEW4 = '''  builderCard.appendChild(addJoinBtn);

  const suggestBtn = el("button", { class: "btn btn-sm", style: "margin-left:8px" }, "Önerilen İlişkiler");
  const suggestBox = el("div", { id: "qb-suggest-box", style: "margin-top:8px" });
  suggestBtn.addEventListener("click", () => withBusy(suggestBtn, () => loadRelationshipSuggestions(suggestBox)));
  builderCard.appendChild(suggestBtn);
  builderCard.appendChild(suggestBox);

  builderCard.appendChild(el("label", { style: "margin-top:16px" }, "Filtreler"));'''
    appjs = replace_once(appjs, OLD4, NEW4, "app.js Önerilen İlişkiler butonu")

    OLD5 = '''function renderJoinsBox(box) {
  box.innerHTML = "";'''
    NEW5 = '''// Seçili tabloyla ilgili, daha önce analiz edilmiş (herhangi bir şemadaki)
// ilişkileri getirir ve tek tıkla join olarak eklemeyi sağlar. DB-geneli
// çalışır — getAnalysisResults() tüm şemalardan biriken veriyi döner,
// burada şema filtrelemesi YAPILMAZ.
async function loadRelationshipSuggestions(container) {
  container.innerHTML = "";
  container.appendChild(el("p", { class: "muted small" }, "Yükleniyor…"));

  let data;
  try {
    data = await api.getAnalysisResults(state.selectedConnId);
  } catch (e) {
    container.innerHTML = "";
    handleApiError(e, "İlişki önerileri alınamadı");
    return;
  }
  container.innerHTML = "";

  const table = state.selectedTable;
  const matches = (data.relationships || []).filter(
    (r) => r.table_a === table || r.table_b === table
  );

  if (!matches.length) {
    container.appendChild(el("p", { class: "muted small" },
      `"${table}" için kayıtlı ilişki bulunamadı. Bağlantılar sayfasından "Analiz Et" ile veritabanını taratın.`));
    return;
  }

  const suggestions = matches
    .map((r) => {
      const flipped = r.table_a === table;
      return {
        t1: table,
        f1: flipped ? r.column_a : r.column_b,
        t2: flipped ? r.table_b : r.table_a,
        f2: flipped ? r.column_b : r.column_a,
        source: r.source,
        confidence: r.confidence,
      };
    })
    .filter((s) => !state.joins.some((j) => j.t2 === s.t2 && j.f1 === s.f1 && j.f2 === s.f2));

  if (!suggestions.length) {
    container.appendChild(el("p", { class: "muted small" }, "Tüm önerilen ilişkiler zaten eklenmiş."));
    return;
  }

  const addAllBtn = el("button", { class: "btn btn-sm btn-primary" }, "Tümünü Ekle");
  addAllBtn.addEventListener("click", () => {
    for (const s of suggestions) {
      state.joins.push({ type: "LEFT JOIN", t1: s.t1, f1: s.f1, t2: s.t2, f2: s.f2 });
    }
    renderJoinsBox(qs("#qb-joins-box"));
    loadRelationshipSuggestions(container);
  });
  container.appendChild(addAllBtn);

  const list = el("div", { style: "margin-top:8px" });
  for (const s of suggestions) {
    const label = `${s.t1}.${s.f1} → ${s.t2}.${s.f2}` +
      (s.source === "fk_constraint" ? " (FK)" : ` (istatistiksel, güven ${s.confidence != null ? s.confidence.toFixed(2) : "-"})`);
    const addBtn = el("button", { class: "btn btn-sm" }, `+ ${label}`);
    addBtn.addEventListener("click", () => {
      state.joins.push({ type: "LEFT JOIN", t1: s.t1, f1: s.f1, t2: s.t2, f2: s.f2 });
      renderJoinsBox(qs("#qb-joins-box"));
      loadRelationshipSuggestions(container);
    });
    list.appendChild(el("div", { style: "margin:4px 0" }, addBtn));
  }
  container.appendChild(list);
}

function renderJoinsBox(box) {
  box.innerHTML = "";'''
    appjs = replace_once(appjs, OLD5, NEW5, "app.js loadRelationshipSuggestions()")

    # ---- Yedek al ve yaz ----
    shutil.copy2(ANALYZEPY, str(ANALYZEPY) + ".bak6")
    shutil.copy2(APPJS, str(APPJS) + ".bak6")
    ANALYZEPY.write_text(analyzepy, encoding="utf-8")
    APPJS.write_text(appjs, encoding="utf-8")

    print("[OK] analyze.py ve app.js güncellendi. Yedekler: *.bak6")
    print("Sonra: systemctl restart superbi, tarayıcıda hard-refresh.")


if __name__ == "__main__":
    main()
