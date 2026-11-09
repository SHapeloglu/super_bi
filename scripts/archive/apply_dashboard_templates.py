#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dashboard yerleşim şablonları — /opt/superbi/frontend/app.js ve style.css'e
saf frontend (backend değişikliği yok) patch uygular.

Kullanım: /opt/superbi/venv/bin/python3 apply_dashboard_templates.py
Çalıştırılacağı dizin: /opt/superbi
Her adımda OLD string tam olarak 1 kez bulunmazsa script DURUR ve hiçbir
dosyayı değiştirmez (kısmi patch riski yok). Önce .bak yedeği alınır.
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPJS = ROOT / "frontend" / "app.js"
CSS = ROOT / "frontend" / "style.css"


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
    if not APPJS.exists():
        print(f"[HATA] Bulunamadı: {APPJS}")
        sys.exit(1)
    if not CSS.exists():
        print(f"[HATA] Bulunamadı: {CSS}")
        sys.exit(1)

    appjs = APPJS.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")

    # ---- 1) state.showTemplatePicker flag ekle ----
    OLD1 = "  dashZoom: 1,"
    NEW1 = "  dashZoom: 1,\n  showTemplatePicker: false,"
    appjs = replace_once(appjs, OLD1, NEW1, "state.showTemplatePicker ekle")

    # ---- 2) DASHBOARD_TEMPLATES + yardımcı fonksiyonlar (blankDashboard sonrası) ----
    OLD2 = '''function blankDashboard() {
  return { dashboard_id: null, name: "Yeni Dashboard", scale: "a4l", page_w_mm: 297, page_h_mm: 210, objects: [] };
}'''
    NEW2 = OLD2 + '''

/* ---- Dashboard Yerleşim Şablonları ---- */
// Koordinatlar referans 297x210mm (a4l) üzerinden tasarlandı; applyDashboardTemplate
// farklı page_w_mm/page_h_mm için oranlı ölçekler. Saf frontend — backend/API değişmedi.
const DASHBOARD_TEMPLATES = {
  classic: {
    label: "Klasik",
    desc: "3 KPI + 2 grafik + tablo",
    refW: 297, refH: 210,
    widgets: [
      { type: "kpi",    title: "Toplam Ciro",        x: 5,   y: 5,   w: 90,  h: 35 },
      { type: "kpi",    title: "Sipariş Sayısı",      x: 100, y: 5,   w: 90,  h: 35 },
      { type: "kpi",    title: "Ortalama Sepet",      x: 195, y: 5,   w: 92,  h: 35 },
      { type: "column", title: "Aylık Satış",         x: 5,   y: 45,  w: 140, h: 80 },
      { type: "pie",    title: "Kategori Dağılımı",   x: 152, y: 45,  w: 135, h: 80 },
      { type: "table",  title: "Detay Tablo",         x: 5,   y: 130, w: 282, h: 75 },
    ],
  },
  focus: {
    label: "Odak Grafik",
    desc: "1 büyük grafik + yan metrikler",
    refW: 297, refH: 210,
    widgets: [
      { type: "line", title: "Ana Trend", x: 5,   y: 5,   w: 190, h: 200 },
      { type: "kpi",  title: "Metrik 1",  x: 200, y: 5,   w: 92,  h: 60 },
      { type: "kpi",  title: "Metrik 2",  x: 200, y: 70,  w: 92,  h: 60 },
      { type: "kpi",  title: "Metrik 3",  x: 200, y: 135, w: 92,  h: 60 },
    ],
  },
  metrics: {
    label: "Metrik Yoğun",
    desc: "8 KPI kartı + trend çizgisi",
    refW: 297, refH: 210,
    widgets: [
      { type: "kpi",  title: "KPI 1", x: 5,   y: 5,   w: 65,  h: 45 },
      { type: "kpi",  title: "KPI 2", x: 77,  y: 5,   w: 65,  h: 45 },
      { type: "kpi",  title: "KPI 3", x: 149, y: 5,   w: 65,  h: 45 },
      { type: "kpi",  title: "KPI 4", x: 221, y: 5,   w: 65,  h: 45 },
      { type: "kpi",  title: "KPI 5", x: 5,   y: 55,  w: 65,  h: 45 },
      { type: "kpi",  title: "KPI 6", x: 77,  y: 55,  w: 65,  h: 45 },
      { type: "kpi",  title: "KPI 7", x: 149, y: 55,  w: 65,  h: 45 },
      { type: "kpi",  title: "KPI 8", x: 221, y: 55,  w: 65,  h: 45 },
      { type: "line", title: "Trend", x: 5,   y: 105, w: 281, h: 100 },
    ],
  },
  grid: {
    label: "Izgara",
    desc: "6 eşit panel, serbest düzenlemeye hazır zemin",
    refW: 297, refH: 210,
    widgets: [
      { type: "column", title: "Panel 1", x: 5,   y: 5,   w: 90, h: 95 },
      { type: "line",   title: "Panel 2", x: 102, y: 5,   w: 90, h: 95 },
      { type: "pie",    title: "Panel 3", x: 199, y: 5,   w: 90, h: 95 },
      { type: "bar",    title: "Panel 4", x: 5,   y: 105, w: 90, h: 95 },
      { type: "table",  title: "Panel 5", x: 102, y: 105, w: 90, h: 95 },
      { type: "donut",  title: "Panel 6", x: 199, y: 105, w: 90, h: 95 },
    ],
  },
  mixed: {
    label: "Karma",
    desc: "KPI şeridi + büyük grafik + tablo + metin",
    refW: 297, refH: 210,
    widgets: [
      { type: "kpi",    title: "Metrik 1",   x: 5,   y: 5,   w: 90,  h: 30 },
      { type: "kpi",    title: "Metrik 2",   x: 100, y: 5,   w: 90,  h: 30 },
      { type: "kpi",    title: "Metrik 3",   x: 195, y: 5,   w: 92,  h: 30 },
      { type: "column", title: "Ana Grafik", x: 5,   y: 40,  w: 180, h: 100 },
      { type: "table",  title: "Özet Tablo", x: 190, y: 40,  w: 102, h: 100 },
      { type: "text",   title: "Not",        x: 5,   y: 145, w: 140, h: 55 },
      { type: "pie",    title: "Dağılım",    x: 150, y: 145, w: 142, h: 55 },
    ],
  },
};

// Şablonu dash.objects'e uygular (mevcut objeleri DEĞİŞTİRİR). page_w_mm/page_h_mm
// referanstan farklıysa koordinatları oranlı ölçekler.
function applyDashboardTemplate(dash, key) {
  const tmpl = DASHBOARD_TEMPLATES[key];
  if (!tmpl) return;
  const sx = dash.page_w_mm / tmpl.refW;
  const sy = dash.page_h_mm / tmpl.refH;
  dash.objects = tmpl.widgets.map((w) => ({
    id: "w_" + Math.random().toString(36).slice(2, 9),
    type: w.type,
    x: Math.round(w.x * sx),
    y: Math.round(w.y * sy),
    w: Math.round(w.w * sx),
    h: Math.round(w.h * sy),
    title: w.title,
    query_id: null,
    color: "#378ADD",
  }));
}

// Şablon seçim kartlarını içeren DOM elemanı döner. onPick(key) çağrılır;
// key === "blank" boş dashboard, key === null iptal anlamına gelir.
function renderTemplatePicker(onPick) {
  const wrap = el("div", { class: "template-picker" });
  wrap.appendChild(el("p", { class: "muted small" }, "Bir şablonla başlayın (sonra serbestçe düzenleyebilirsiniz):"));
  const grid = el("div", { class: "template-grid" });
  const options = [
    { key: "blank", label: "Boş Dashboard", desc: "Sıfırdan başla" },
    ...Object.entries(DASHBOARD_TEMPLATES).map(([key, t]) => ({ key, label: t.label, desc: t.desc })),
  ];
  for (const opt of options) {
    const card = el("div", { class: "template-card" }, [
      el("div", { class: "template-card-title" }, opt.label),
      el("div", { class: "template-card-desc muted small" }, opt.desc),
    ]);
    card.addEventListener("click", () => onPick(opt.key));
    grid.appendChild(card);
  }
  wrap.appendChild(grid);
  const cancelBtn = el("button", { class: "btn btn-sm", style: "margin-top:8px" }, "İptal");
  cancelBtn.addEventListener("click", () => onPick(null));
  wrap.appendChild(cancelBtn);
  return wrap;
}'''
    appjs = replace_once(appjs, OLD2, NEW2, "DASHBOARD_TEMPLATES + yardımcı fonksiyonlar ekle")

    # ---- 3) renderDashboardsView fonksiyonunu şablon seçici destekleyecek şekilde değiştir ----
    OLD3 = '''async function renderDashboardsView(root) {
  root.appendChild(el("h2", {}, "Dashboard'lar"));

  if (!state.connections.length) {
    try { await refreshConnections(); } catch (e) { handleApiError(e, "Bağlantılar alınamadı"); }
  }

  const listCard = el("div", { class: "card" });
  listCard.appendChild(el("h3", {}, "Kayıtlı Dashboard'lar"));
  const newBtn = el("button", { class: "btn btn-primary btn-sm" }, "+ Yeni Dashboard");
  newBtn.addEventListener("click", () => {
    state.currentDashboard = blankDashboard();
    state.selectedWidgetId = null;
    state.dashHistory = [];
    state.dashHistoryIndex = -1;
    renderView("dashboards");
  });
  listCard.appendChild(newBtn);

  const listBody = el("div", { style: "margin-top:12px" }, el("p", { class: "muted" }, "Yükleniyor…"));
  listCard.appendChild(listBody);
  root.appendChild(listCard);

  try {
    state.dashboards = await api.listDashboards();
    renderDashList(listBody);
  } catch (e) {
    handleApiError(e, "Dashboard listesi alınamadı");
  }

  if (state.currentDashboard) {
    renderDashboardEditor(root);
  }
}'''
    NEW3 = '''async function renderDashboardsView(root) {
  root.appendChild(el("h2", {}, "Dashboard'lar"));

  if (!state.connections.length) {
    try { await refreshConnections(); } catch (e) { handleApiError(e, "Bağlantılar alınamadı"); }
  }

  const listCard = el("div", { class: "card" });
  listCard.appendChild(el("h3", {}, "Kayıtlı Dashboard'lar"));
  const newBtn = el("button", { class: "btn btn-primary btn-sm" }, "+ Yeni Dashboard");
  newBtn.addEventListener("click", () => {
    state.showTemplatePicker = true;
    renderView("dashboards");
  });
  listCard.appendChild(newBtn);

  if (state.showTemplatePicker) {
    listCard.appendChild(renderTemplatePicker((key) => {
      state.showTemplatePicker = false;
      if (key !== null) {
        const dash = blankDashboard();
        if (key !== "blank") applyDashboardTemplate(dash, key);
        state.currentDashboard = dash;
        state.selectedWidgetId = null;
        state.dashHistory = [];
        state.dashHistoryIndex = -1;
      }
      renderView("dashboards");
    }));
    root.appendChild(listCard);
    return;
  }

  const listBody = el("div", { style: "margin-top:12px" }, el("p", { class: "muted" }, "Yükleniyor…"));
  listCard.appendChild(listBody);
  root.appendChild(listCard);

  try {
    state.dashboards = await api.listDashboards();
    renderDashList(listBody);
  } catch (e) {
    handleApiError(e, "Dashboard listesi alınamadı");
  }

  if (state.currentDashboard) {
    renderDashboardEditor(root);
  }
}'''
    appjs = replace_once(appjs, OLD3, NEW3, "renderDashboardsView şablon seçici entegrasyonu")

    # ---- 4) Editör toolbar'ına "Şablon Uygula" seçici ekle ----
    OLD4 = '''  undoBtn.addEventListener("click", () => undoDashboard());
  redoBtn.addEventListener("click", () => redoDashboard());

  const saveBtn = el("button", { class: "btn btn-primary" }, dash.dashboard_id ? "Güncelle" : "Kaydet");'''
    NEW4 = '''  undoBtn.addEventListener("click", () => undoDashboard());
  redoBtn.addEventListener("click", () => redoDashboard());

  const templateSelect = el("select", { id: "dash-template-select" }, [
    el("option", { value: "" }, "Şablon uygula…"),
    ...Object.entries(DASHBOARD_TEMPLATES).map(([key, t]) => el("option", { value: key }, t.label)),
  ]);
  templateSelect.addEventListener("change", () => {
    const key = templateSelect.value;
    if (!key) return;
    if (dash.objects.length && !confirm("Mevcut widget'lar silinip şablon yerleştirilecek. Emin misiniz?")) {
      templateSelect.value = "";
      return;
    }
    applyDashboardTemplate(dash, key);
    renderCanvasPage(canvasPage);
    pushHistory();
    templateSelect.value = "";
  });

  const saveBtn = el("button", { class: "btn btn-primary" }, dash.dashboard_id ? "Güncelle" : "Kaydet");'''
    appjs = replace_once(appjs, OLD4, NEW4, "templateSelect tanımı ekle")

    OLD5 = '''  card.appendChild(el("div", { class: "dash-toolbar" }, [
    el("div", {}, [el("label", {}, "Ad"), nameInput]),
    el("div", {}, [el("label", {}, "Zoom"), el("div", { class: "row" }, [zoomInput, zoomLabel])]),
    undoBtn, redoBtn,
    saveBtn, closeBtn,
  ]));'''
    NEW5 = '''  card.appendChild(el("div", { class: "dash-toolbar" }, [
    el("div", {}, [el("label", {}, "Ad"), nameInput]),
    el("div", {}, [el("label", {}, "Zoom"), el("div", { class: "row" }, [zoomInput, zoomLabel])]),
    el("div", {}, [el("label", {}, "Şablon"), templateSelect]),
    undoBtn, redoBtn,
    saveBtn, closeBtn,
  ]));'''
    appjs = replace_once(appjs, OLD5, NEW5, "templateSelect'i toolbar'a ekle")

    # ---- 5) CSS ----
    OLD_CSS = ".widget-palette { width: 160px; flex-shrink: 0; }"
    NEW_CSS = OLD_CSS + '''

.template-picker { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border, #e2e2e2); }
.template-grid { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 6px; }
.template-card {
  width: 160px;
  padding: 10px;
  border: 1px solid var(--border, #d8d8d8);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.template-card:hover { border-color: var(--accent); }
.template-card-title { font-weight: 600; margin-bottom: 4px; }
.template-card-desc { line-height: 1.3; }'''
    css = replace_once(css, OLD_CSS, NEW_CSS, "template CSS ekle")

    # ---- Yedek al ve yaz ----
    shutil.copy2(APPJS, APPJS.with_suffix(".js.bak"))
    shutil.copy2(CSS, CSS.with_suffix(".css.bak"))
    APPJS.write_text(appjs, encoding="utf-8")
    CSS.write_text(css, encoding="utf-8")

    print("[OK] app.js ve style.css güncellendi. Yedekler: app.js.bak, style.css.bak")
    print("Şimdi: systemctl restart superbi (statik dosyalar için genelde gerekmez ama")
    print("garanti olsun diye restart edip tarayıcıda hard-refresh (Ctrl+Shift+R) yapın.")


if __name__ == "__main__":
    main()
