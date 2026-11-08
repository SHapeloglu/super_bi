#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Granularity + ilişki analizi (Faz 4) için frontend UI ekler.
Backend (/api/analyze/*) zaten mevcut ve main.py'de kayıtlı — bu script
sadece Bağlantılar sayfasına "Analiz Et" / "Sonuçlar" butonlarını ve
sonuç görünümünü ekler. Saf frontend, backend/API değişmiyor.

Kullanım: /opt/superbi/venv/bin/python3 apply_analyze_ui.py
Çalıştırılacağı dizin: /opt/superbi
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPJS = ROOT / "frontend" / "app.js"
APIJS = ROOT / "frontend" / "api.js"


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
    if not APPJS.exists() or not APIJS.exists():
        print(f"[HATA] Dosyalar bulunamadı: {APPJS} / {APIJS}")
        sys.exit(1)

    appjs = APPJS.read_text(encoding="utf-8")
    apijs = APIJS.read_text(encoding="utf-8")

    # ---- 1) api.js: analyze metodları ----
    OLD1 = '''    listForeignKeys: (connId, table) =>
      request("GET", `/api/schema/${connId}/tables/${encodeURIComponent(table)}/foreign-keys`),

    // ---- drivers ----'''
    NEW1 = '''    listForeignKeys: (connId, table) =>
      request("GET", `/api/schema/${connId}/tables/${encodeURIComponent(table)}/foreign-keys`),

    // ---- analyze (granularity + ilişki keşfi) ----
    analyzeTables: (connId, body) => request("POST", `/api/analyze/${connId}/tables`, body || {}),
    testRelationship: (connId, body) => request("POST", `/api/analyze/${connId}/relationship`, body),
    getAnalysisResults: (connId) => request("GET", `/api/analyze/${connId}/results`),

    // ---- drivers ----'''
    apijs = replace_once(apijs, OLD1, NEW1, "api.js analyze metodları")

    # ---- 2) app.js: renderConnectionsList'i genişlet + showAnalysisResults ekle ----
    OLD2 = '''function renderConnectionsList(container) {
  container.innerHTML = "";
  if (!state.connections.length) {
    container.appendChild(el("div", { class: "empty-state" }, "Henüz bağlantı yok."));
    return;
  }

  const table = el("table");
  const thead = el("tr", {}, ["conn_id", "Tip", "Host", "Veritabanı", "Oluşturulma", ""].map(
    (h) => el("th", {}, h)
  ));
  table.appendChild(el("thead", {}, thead));

  const tbody = el("tbody");
  for (const c of state.connections) {
    const testBtn = el("button", { class: "btn btn-sm" }, "Test Et");
    const delBtn = el("button", { class: "btn btn-sm btn-danger" }, "Sil");
    const statusSpan = el("span", { class: "badge" }, "");

    testBtn.addEventListener("click", () =>
      withBusy(testBtn, async () => {
        try {
          const res = await api.testConnection(c.conn_id);
          statusSpan.textContent = res.success ? `OK (${res.latency_ms}ms)` : "HATA";
          statusSpan.className = `badge ${res.success ? "ok" : "warn"}`;
          if (!res.success) toast(res.message, "error");
        } catch (e) { handleApiError(e, "Test başarısız"); }
      })
    );

    delBtn.addEventListener("click", async () => {
      if (!confirm(`${c.conn_id} bağlantısını silmek istediğinize emin misiniz?`)) return;
      try {
        await api.deleteConnection(c.conn_id);
        toast("Bağlantı silindi", "success");
        await refreshConnections();
        renderConnectionsList(container);
      } catch (e) { handleApiError(e, "Silinemedi"); }
    });

    tbody.appendChild(el("tr", {}, [
      el("td", {}, c.conn_id),
      el("td", {}, c.db_type),
      el("td", {}, c.host || "-"),
      el("td", {}, c.database),
      el("td", {}, fmtDate(c.created_at)),
      el("td", { class: "row" }, [testBtn, statusSpan, delBtn]),
    ]));
  }
  table.appendChild(tbody);
  container.appendChild(table);
}'''
    NEW2 = '''function renderConnectionsList(container) {
  container.innerHTML = "";
  if (!state.connections.length) {
    container.appendChild(el("div", { class: "empty-state" }, "Henüz bağlantı yok."));
    return;
  }

  const table = el("table");
  const thead = el("tr", {}, ["conn_id", "Tip", "Host", "Veritabanı", "Oluşturulma", ""].map(
    (h) => el("th", {}, h)
  ));
  table.appendChild(el("thead", {}, thead));

  const tbody = el("tbody");
  for (const c of state.connections) {
    const testBtn = el("button", { class: "btn btn-sm" }, "Test Et");
    const analyzeBtn = el("button", { class: "btn btn-sm" }, "Analiz Et");
    const resultsBtn = el("button", { class: "btn btn-sm" }, "Sonuçlar");
    const delBtn = el("button", { class: "btn btn-sm btn-danger" }, "Sil");
    const statusSpan = el("span", { class: "badge" }, "");

    testBtn.addEventListener("click", () =>
      withBusy(testBtn, async () => {
        try {
          const res = await api.testConnection(c.conn_id);
          statusSpan.textContent = res.success ? `OK (${res.latency_ms}ms)` : "HATA";
          statusSpan.className = `badge ${res.success ? "ok" : "warn"}`;
          if (!res.success) toast(res.message, "error");
        } catch (e) { handleApiError(e, "Test başarısız"); }
      })
    );

    analyzeBtn.addEventListener("click", () =>
      withBusy(analyzeBtn, async () => {
        try {
          const res = await api.analyzeTables(c.conn_id, {});
          toast(
            `Analiz tamam: ${res.tables_profiled}/${res.tables_found} tablo, ${res.fk_relationships} FK ilişkisi bulundu`,
            "success"
          );
          if (res.errors && res.errors.length) {
            console.warn("Analiz hataları:", res.errors);
            toast(`${res.errors.length} tabloda hata oluştu — konsolu kontrol edin`, "error");
          }
          await showAnalysisResults(c.conn_id);
        } catch (e) { handleApiError(e, "Analiz başarısız"); }
      })
    );

    resultsBtn.addEventListener("click", () =>
      withBusy(resultsBtn, async () => {
        try { await showAnalysisResults(c.conn_id); }
        catch (e) { handleApiError(e, "Sonuçlar alınamadı"); }
      })
    );

    delBtn.addEventListener("click", async () => {
      if (!confirm(`${c.conn_id} bağlantısını silmek istediğinize emin misiniz?`)) return;
      try {
        await api.deleteConnection(c.conn_id);
        toast("Bağlantı silindi", "success");
        await refreshConnections();
        renderConnectionsList(container);
      } catch (e) { handleApiError(e, "Silinemedi"); }
    });

    tbody.appendChild(el("tr", {}, [
      el("td", {}, c.conn_id),
      el("td", {}, c.db_type),
      el("td", {}, c.host || "-"),
      el("td", {}, c.database),
      el("td", {}, fmtDate(c.created_at)),
      el("td", { class: "row" }, [testBtn, statusSpan, analyzeBtn, resultsBtn, delBtn]),
    ]));
  }
  table.appendChild(tbody);
  container.appendChild(table);

  const resultsPanel = el("div", { id: "analysis-results-panel", style: "margin-top:16px" });
  container.appendChild(resultsPanel);
}

// Bir bağlantı için kayıtlı granularity/ilişki analiz sonuçlarını
// #analysis-results-panel içine render eder. /api/analyze GET endpoint'i
// zaten mevcuttu (backend Faz 4 tamamdı) — burada sadece tüketiliyor.
async function showAnalysisResults(connId) {
  const panel = qs("#analysis-results-panel");
  if (!panel) return;
  panel.innerHTML = "";
  panel.appendChild(el("p", { class: "muted small" }, "Yükleniyor…"));

  let data;
  try {
    data = await api.getAnalysisResults(connId);
  } catch (e) {
    panel.innerHTML = "";
    handleApiError(e, "Analiz sonuçları alınamadı");
    return;
  }

  panel.innerHTML = "";

  if (!data.profiles.length && !data.relationships.length) {
    panel.appendChild(el("div", { class: "empty-state" },
      `"${connId}" için henüz analiz sonucu yok — "Analiz Et" ile başlatın.`));
    return;
  }

  panel.appendChild(el("h4", {}, `Analiz Sonuçları — ${connId}`));

  if (data.profiles.length) {
    panel.appendChild(el("h5", {}, "Tablo Profilleri"));
    const pTable = el("table");
    pTable.appendChild(el("thead", {}, el("tr", {},
      ["Tablo", "Satır Sayısı", "Grain", "Sütun Sınıflandırma"].map((h) => el("th", {}, h))
    )));
    const pBody = el("tbody");
    for (const p of data.profiles) {
      const colSummary = p.columns
        .map((col) => `${col.name}: ${col.classification}`)
        .join(", ");
      pBody.appendChild(el("tr", {}, [
        el("td", {}, p.table_name),
        el("td", {}, String(p.row_count ?? "-")),
        el("td", {}, p.grain_columns.length ? p.grain_columns.join(", ") : "-"),
        el("td", { class: "muted small" }, colSummary || "-"),
      ]));
    }
    pTable.appendChild(pBody);
    panel.appendChild(pTable);
  }

  if (data.relationships.length) {
    panel.appendChild(el("h5", { style: "margin-top:12px" }, "İlişkiler"));
    const rTable = el("table");
    rTable.appendChild(el("thead", {}, el("tr", {},
      ["A", "B", "Kardinalite", "Kaynak", "Güven", "Doğrulanmış"].map((h) => el("th", {}, h))
    )));
    const rBody = el("tbody");
    for (const r of data.relationships) {
      rBody.appendChild(el("tr", {}, [
        el("td", {}, `${r.table_a}.${r.column_a}`),
        el("td", {}, `${r.table_b}.${r.column_b}`),
        el("td", {}, r.cardinality),
        el("td", {}, r.source === "fk_constraint" ? "FK (kesin)" : "İstatistiksel"),
        el("td", {}, r.confidence != null ? r.confidence.toFixed(2) : "-"),
        el("td", {}, r.verified ? "✓" : "-"),
      ]));
    }
    rTable.appendChild(rBody);
    panel.appendChild(rTable);
  }
}'''
    appjs = replace_once(appjs, OLD2, NEW2, "renderConnectionsList + showAnalysisResults")

    # ---- Yedek al ve yaz ----
    shutil.copy2(APPJS, str(APPJS) + ".bak2")
    shutil.copy2(APIJS, str(APIJS) + ".bak2")
    APPJS.write_text(appjs, encoding="utf-8")
    APIJS.write_text(apijs, encoding="utf-8")

    print("[OK] app.js ve api.js güncellendi. Yedekler: app.js.bak2, api.js.bak2")
    print("Sonra: systemctl restart superbi, tarayıcıda hard-refresh.")


if __name__ == "__main__":
    main()
