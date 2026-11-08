/**
 * SuperBI ön yüzünün ana dosyası (vanilla JS, framework yok).
 * Tarayıcıda index.html tarafından module olarak yüklenir ve tüm ekranları (bağlantılar, sorgu, geçmiş, dashboard, sürücüler) bu dosyadan yönetir.
 * Veriyi api.js içindeki createApiClient üzerinden backend'den alır. Oturum token'ı localStorage'da tutulur; tema tercihi de yine localStorage'da saklanır.
 * Bu dosyayı index.html ve api.js ile birlikte düşünün: HTML'deki id'lere (qs("#...")) göre DOM'a bağlanır.
 */
import { createApiClient } from "./api.js";

/* ============================================================
 * Ayarlar + global state
 * ==========================================================*/

// API adresi. Sunucu başka bir adreste çalışıyorsa window.__SUPERBI_API_BASE__ ile verilebilir; yoksa boş kalır ve istekler aynı sunucuya gider.
const API_BASE = window.__SUPERBI_API_BASE__ || "";

/**
 * Uygulamanın tüm durumunu (state) tuttuğu tek nesne.
 * Neden: Ekranlar arasında veri paylaşmak ve yenilemeden sonra neyin seçili olduğunu hatırlamak için. Değer değişince ilgili render fonksiyonu çağrılarak ekran güncellenir.
 * Oturum alanları (token, role, userId, username) tarayıcı yenilenince kaybolmasın diye localStorage'dan okunarak başlatılır.
 */
const state = {
  token: localStorage.getItem("sb_token") || null,
  role: localStorage.getItem("sb_role") || null,
  userId: localStorage.getItem("sb_user_id") || null,
  username: localStorage.getItem("sb_username") || null,

  view: "connections",

  connections: [],
  selectedConnId: null,

  tables: [],
  selectedTable: null,
  columns: [],
  fields: {},
  joins: [],
  filters: [],
  groupBy: [],
  orderBy: [],
  calculatedFields: [],
  sample: 100,

  lastPreview: null,
  lastRun: null,

  historyRecent: [],
  historyGroups: [],

  dashboards: [],
  currentDashboard: null,
  dashZoom: 1,
  showTemplatePicker: false,
  selectedWidgetId: null,

  // Dashboard geri-al/yinele (undo/redo) geçmişi. dashHistory anlık görüntülerin listesi, dashHistoryIndex ise şu an hangi görüntüde olduğumuzu gösterir (-1 = hiç kayıt yok).
  // Undo/Redo
  dashHistory: [],
  dashHistoryIndex: -1,

  drivers: [],
  _widgetColumnsCache: [],
};

// API istemcisi. Token her istekte state.token'dan okunsun diye bir fonksiyon olarak verilir; böylece giriş/çıkış sonrası istemciyi yeniden kurmaya gerek kalmaz.
const api = createApiClient(API_BASE, () => state.token);

/* ============================================================
 * Küçük yardımcılar
 * ==========================================================*/

/**
 * document.querySelector kısaltması. Tek bir öğe döndürür; bulunamazsa null döner, bu yüzden kullanmadan önce varlığından emin olun.
 * Parametreler: sel = CSS seçici (örn. "#auth-form"), root = arama yapılacak üst öğe (varsayılan tüm sayfa).
 */
function qs(sel, root = document) { return root.querySelector(sel); }
/**
 * querySelectorAll kısaltması. Eşleşen tüm öğeleri GERÇEK bir diziye çevirip döndürür (forEach, filter gibi dizi metodları kullanılabilsin diye). Eşleşme yoksa boş dizi döner.
 */
function qsa(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

/**
 * DOM öğesi üretmek için kısa yardımcı. Ham document.createElement yazmayı azaltır.
 * Parametreler:
 * - tag: oluşturulacak etiket ("div", "button" gibi).
 * - attrs: özellikler. "class" className'e, "html" innerHTML'e yazılır (DİKKAT: html ile gelen metin HTML olarak çalışır; kullanıcı verisi buraya konmamalı). "onclick" gibi on ile başlayan ve fonksiyon olan değerler olay dinleyicisine dönüşür. Diğerleri setAttribute ile eklenir; null/undefined olanlar atlanır.
 * - children: alt öğe, metin (string) veya bunların dizisi. Metinler güvenli şekilde text node olarak eklenir.
 * Dönüş: oluşturulan öğe. Henüz sayfaya eklenmez; çağıran appendChild ile ekler.
 */
function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c === null || c === undefined) continue;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
}

/**
 * Ekranın sağ üstünde kısa süreli bildirim (toast) gösterir. 4 saniye sonra kendiliğinden kaybolur.
 * Parametreler: message = gösterilecek metin; type = "info", "error" veya "success" (CSS sınıfı olarak kullanılır, renk belirler).
 * Not: #toast-root öğesi index.html içinde olmalıdır; yoksa hata verir.
 */
function toast(message, type = "info") {
  const root = qs("#toast-root");
  const node = el("div", { class: `toast ${type}` }, message);
  root.appendChild(node);
  setTimeout(() => node.remove(), 4000);
}

/**
 * ISO tarih metnini (örn. "2026-10-24T10:00:00Z") Türkçe yerel formatta gösterir.
 * Tarih boşsa "-" döner. Geçersiz tarih gelirse hata fırlatmak yerine metni olduğu gibi döndürür.
 */
function fmtDate(iso) {
  if (!iso) return "-";
  try { return new Date(iso).toLocaleString("tr-TR"); } catch { return iso; }
}

/**
 * Bir düğmeyi işlem sürerken meşgul gösterir (çift tıklamayı engeller).
 * Akış: düğme kapatılır, metni "…" olur, fn çalışır (ve bittiğinde sonucu döner). Hata olsa bile finally bloğu düğmeyi eski haline getirir.
 * Parametreler: btn = düğme öğesi; fn = async işlem.
 * Dönüş: fn'in döndürdüğü değer. fn hata fırlatırsa aynen yukarı iletilir.
 */
async function withBusy(btn, fn) {
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = "…";
  try {
    return await fn();
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

/**
 * API hatalarını tek yerden işler: konsola yazar ve kullanıcıya bildirim gösterir.
 * HTTP 401 gelirse oturum süresi dolmuştur; kullanıcı çıkış yapılıp giriş ekranına döner.
 * Parametreler: e = yakalanan hata; fallback = hata mesajı yoksa gösterilecek metin.
 */
function handleApiError(e, fallback = "Bir hata oluştu") {
  console.error(e);
  if (e.status === 401) {
    toast("Oturumunuz sona erdi, tekrar giriş yapın.", "error");
    logout();
    return;
  }
  toast(e.message || fallback, "error");
}

/* ============================================================
 * Auth
 * ==========================================================*/

/**
 * Kullanıcının giriş yapıp yapmadığını söyler (token var mı). Token yalnız varlığına bakılarak kontrol edilir; süresi dolmuş olabilir, bu durum API'de 401 ile yakalanır.
 */
function isLoggedIn() { return !!state.token; }

/**
 * Giriş/kayıt sonrası dönen oturum bilgisini hem state'e hem localStorage'a yazar; sayfa yenilenince oturum korunsun diye.
 * Parametreler: {access_token, role, user_id} sunucu cevabından gelen alanlar; username = giriş formundaki kullanıcı adı.
 * Güvenlik notu: token localStorage'da tutulduğu için sayfada çalışan herhangi bir XSS açığı bu token'ı okuyabilir.
 */
function saveAuth({ access_token, role, user_id }, username) {
  state.token = access_token;
  state.role = role;
  state.userId = user_id;
  state.username = username;
  localStorage.setItem("sb_token", access_token);
  localStorage.setItem("sb_role", role);
  localStorage.setItem("sb_user_id", user_id);
  localStorage.setItem("sb_username", username);
}

/**
 * Oturumu kapatır: state ve localStorage'daki tüm oturum bilgilerini siler, giriş ekranını gösterir.
 */
function logout() {
  state.token = null;
  state.role = null;
  state.userId = null;
  state.username = null;
  localStorage.removeItem("sb_token");
  localStorage.removeItem("sb_role");
  localStorage.removeItem("sb_user_id");
  localStorage.removeItem("sb_username");
  showAuthScreen();
}

/**
 * Giriş ekranını gösterir, ana uygulama iskeletini (app-shell) gizler. Display değerleri index.html/CSS ile uyumlu olmalıdır.
 */
function showAuthScreen() {
  qs("#auth-screen").style.display = "flex";
  qs("#app-shell").style.display = "none";
}

/**
 * Giriş ekranını gizler, ana uygulama iskeletini gösterir, kullanıcı etiketini (ad ve rol) yazar ve mevcut ekranı yeniden çizer.
 */
function showAppShell() {
  qs("#auth-screen").style.display = "none";
  qs("#app-shell").style.display = "flex";
  qs("#user-label").textContent = `${state.username || "?"} (${state.role || "?"})`;
  renderView(state.view);
}

// Giriş formunun modu: "login" (giriş) veya "register" (kayıt). Sekmeler ve form gönderimi bu değere bakar.
let authMode = "login";

/**
 * Giriş/kayıt ekranının olaylarını (sekme tıklamaları, form gönderimi, çıkış düğmesi) bağlar. Uygulama açılışında bir kez çağrılır.
 * Form gönderildiğinde authMode'a göre api.login ya da api.register çağrılır; başarılıysa oturum kaydedilip uygulama açılır, hatada mesaj kutusunda gösterilir.
 */
function initAuthScreen() {
  qs("#tab-login").addEventListener("click", () => {
    authMode = "login";
    qs("#tab-login").classList.add("active");
    qs("#tab-register").classList.remove("active");
    qs("#auth-form button[type=submit]").textContent = "Giriş Yap";
    qs("#register-hint").style.display = "none";
    qs("#auth-error").textContent = "";
  });

  qs("#tab-register").addEventListener("click", () => {
    authMode = "register";
    qs("#tab-register").classList.add("active");
    qs("#tab-login").classList.remove("active");
    qs("#auth-form button[type=submit]").textContent = "Kayıt Ol";
    qs("#register-hint").style.display = "block";
    qs("#auth-error").textContent = "";
  });

  qs("#auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = qs("#auth-username").value.trim();
    const password = qs("#auth-password").value;
    const errBox = qs("#auth-error");
    errBox.textContent = "";
    try {
      const result = authMode === "login"
        ? await api.login(username, password)
        : await api.register(username, password);
      saveAuth(result, username);
      showAppShell();
    } catch (err) {
      errBox.textContent = err.message || "Giriş başarısız";
    }
  });

  qs("#logout-btn").addEventListener("click", logout);

  // Faz 0.3: kayıt kapalıysa kayıt sekmesi gizlenir. Durum alınamazsa sekme görünür kalır; sunucu yine de kontrol eder.
  api.registrationStatus()
    .then((r) => { if (!r.open) qs("#tab-register").style.display = "none"; })
    .catch(() => {});
}

/* ============================================================
 * Görünüm (view) yönlendirici
 * ==========================================================*/

const VIEW_RENDERERS = {
  connections: renderConnectionsView,
  query: renderQueryView,
  history: renderHistoryView,
  dashboards: renderDashboardsView,
  drivers: renderDriversView,
};

/**
 * Verilen görünümü (sayfayı) ekrana çizer.
 * Önce önceki ekrandaki grafik ve önbellek temizlenir (bellek sızıntısı ve eski verinin görünmemesi için). Sonra state.view güncellenir, menü düğmesi işaretlenir ve VIEW_RENDERERS'tan ilgili fonksiyon çağrılır.
 * Bilinmeyen bir ad gelirse içerik boş kalır.
 */
function renderView(name) {
  for (const chart of chartInstances.values()) chart.dispose();
  chartInstances.clear();
  widgetDataCache.clear();

  state.view = name;
  qsa(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  const root = qs("#view-root");
  root.innerHTML = "";
  const renderer = VIEW_RENDERERS[name];
  if (renderer) renderer(root);
}

/**
 * Sol menüdeki her düğmeye tıklanınca renderView'i çağıran olayı bağlar. Düğmenin data-view özelliği hangi ekranın açılacağını belirler.
 */
function initNav() {
  qsa(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => renderView(btn.dataset.view));
  });
}

/* ============================================================
 * Tema (koyu / açık)
 * ==========================================================*/

/**
 * Seçilen temayı uygular: body'ye "light-theme" sınıfını ekler/kaldırır ve tema düğmesinin simgesini (güneş/ay) değiştirir. Tema renkleri CSS tarafında tanımlıdır.
 */
function applyTheme(theme) {
  document.body.classList.toggle("light-theme", theme === "light");
  const btn = qs("#theme-toggle-btn");
  if (btn) btn.textContent = theme === "light" ? "☀️" : "🌙";
}

/**
 * Açılışta kayıtlı temayı uygular (kayıt yoksa koyu tema) ve tema düğmesine tıklanınca koyu/açık arasında geçişi yapar; tercih localStorage'a yazılır ki sonraki açılışta da hatırlansın.
 */
function initTheme() {
  const saved = localStorage.getItem("sb_theme") || "dark";
  applyTheme(saved);
  qs("#theme-toggle-btn").addEventListener("click", () => {
    const current = localStorage.getItem("sb_theme") || "dark";
    const next = current === "light" ? "dark" : "light";
    localStorage.setItem("sb_theme", next);
    applyTheme(next);
  });
}

/* ============================================================
 * 1) Bağlantılar (Connections)
 * ==========================================================*/

/**
 * 'Bağlantılar' ekranını kurar: yeni bağlantı formunu ve mevcut bağlantıların listesini çizer.
 * Async çünkü bağlantı listesi sunucudan çekilir; hata olursa handleApiError ile bildirilir ve liste alanında 'yüklenemedi' yazar.
 * Parametre: root = ekranın ekleneceği kapsayıcı öğe.
 */
async function renderConnectionsView(root) {
  root.appendChild(el("h2", {}, "Veritabanı Bağlantıları"));

  const formCard = el("div", { class: "card" });
  formCard.appendChild(el("h3", {}, "Yeni Bağlantı Ekle"));

  const dbTypeSel = el("select", { id: "conn-db-type" }, [
    el("option", { value: "sqlite" }, "SQLite"),
    el("option", { value: "postgresql" }, "PostgreSQL"),
    el("option", { value: "mysql" }, "MySQL"),
    el("option", { value: "mssql" }, "SQL Server"),
    el("option", { value: "oracle" }, "Oracle"),
  ]);

  const hostInput = el("input", { id: "conn-host", placeholder: "localhost" });
  const portInput = el("input", { id: "conn-port", placeholder: "5432", type: "number" });
  const dbInput = el("input", { id: "conn-database", placeholder: "/path/to/file.db  ya da  veritabani_adi" });
  const userInput = el("input", { id: "conn-user", placeholder: "kullanıcı adı (sqlite'ta boş bırakın)" });
  const passInput = el("input", { id: "conn-password", type: "password", placeholder: "şifre (sqlite'ta boş bırakın)" });

  const grid = el("div", { class: "grid-3" }, [
    el("div", {}, [el("label", {}, "Veritabanı Tipi"), dbTypeSel]),
    el("div", {}, [el("label", {}, "Host"), hostInput]),
    el("div", {}, [el("label", {}, "Port"), portInput]),
    el("div", {}, [el("label", {}, "Veritabanı / Dosya Yolu"), dbInput]),
    el("div", {}, [el("label", {}, "Kullanıcı"), userInput]),
    el("div", {}, [el("label", {}, "Şifre"), passInput]),
  ]);
  formCard.appendChild(grid);

  const createBtn = el("button", { class: "btn btn-primary" }, "Bağlantı Oluştur");
  createBtn.style.marginTop = "12px";
  formCard.appendChild(createBtn);

  createBtn.addEventListener("click", () =>
    withBusy(createBtn, async () => {
      try {
        const payload = {
          db_type: dbTypeSel.value,
          host: hostInput.value || "",
          port: portInput.value ? parseInt(portInput.value, 10) : null,
          database: dbInput.value,
          user: userInput.value || null,
          password: passInput.value || null,
        };
        if (!payload.database) { toast("Veritabanı / dosya yolu zorunlu", "error"); return; }
        const res = await api.createConnection(payload);
        toast(`Bağlantı oluşturuldu: ${res.conn_id}`, "success");
        await refreshConnections();
        renderView("connections");
      } catch (e) { handleApiError(e, "Bağlantı oluşturulamadı"); }
    })
  );

  root.appendChild(formCard);

  const listCard = el("div", { class: "card" });
  listCard.appendChild(el("h3", {}, "Mevcut Bağlantılar"));
  const listBody = el("div", { id: "conn-list-body" }, el("p", { class: "muted" }, "Yükleniyor…"));
  listCard.appendChild(listBody);
  root.appendChild(listCard);

  try {
    await refreshConnections();
    renderConnectionsList(listBody);
  } catch (e) {
    handleApiError(e, "Bağlantılar alınamadı");
    listBody.innerHTML = "";
    listBody.appendChild(el("p", { class: "error-text" }, "Bağlantılar yüklenemedi."));
  }
}

/**
 * Bağlantı listesini sunucudan yeniden çeker ve state.connections'a yazar, sonra listeyi yeniden çizer.
 */
async function refreshConnections() {
  state.connections = await api.listConnections();
}

/**
 * state.connections listesini tablo olarak çizer: her satır için 'Test Et' (bağlantıyı dener), 'Analiz Et' (şemayı tarar), 'Sonuçlar' (son analizi gösterir) ve 'Sil' düğmeleri olur.
 * Tablo boşsa 'Henüz bağlantı yok' mesajı gösterilir. Liste altında analiz sonuçları için boş bir panel (#analysis-results-panel) eklenir.
 */
function renderConnectionsList(container) {
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
}

/* ============================================================
 * 2) Sorgu Oluşturucu (Query Builder)
 * ==========================================================*/

// Sorgu oluşturucunun izin verdiği karşılaştırma operatörleri (WHERE koşulları için).
// Neden liste: Kullanıcının yazdığı metin doğrudan SQL'e girmesin diye yalnız bu değerlere izin verilir. Yeni operatör eklerken sunucu tarafındaki listeyle de uyumlu olmalıdır.
const ALLOWED_OPERATORS = [
  "=", "!=", "<>", ">", "<", ">=", "<=",
  "LIKE", "NOT LIKE", "ILIKE",
  "IN", "NOT IN",
  "IS NULL", "IS NOT NULL",
  "BETWEEN",
];

// Join tipleri için izin verilen liste. Yukarıdaki operatör listesi gibi, SQL'e yalnız bu sabit metinler yazılır.
const ALLOWED_JOIN_TYPES = [
  "JOIN", "INNER JOIN", "LEFT JOIN", "LEFT OUTER JOIN",
  "RIGHT JOIN", "RIGHT OUTER JOIN", "FULL JOIN", "FULL OUTER JOIN",
];

/**
 * Sorgu oluşturucunun durumunu sıfırlar: seçili tablo, kolonlar, join/filtre/gruplama ve son önizleme/çalıştırma sonuçları silinir.
 * Neden: Bağlantı veya tablo değişince eski tablonun alanları yeni tabloya karışmasın diye.
 */
function resetQueryBuilderState() {
  state.selectedTable = null;
  state.columns = [];
  state.fields = {};
  state.joins = [];
  state.filters = [];
  state.groupBy = [];
  state.orderBy = [];
  state.calculatedFields = [];
  state.lastPreview = null;
  state.lastRun = null;
}

/**
 * 'Sorgu Oluşturucu' ekranını kurar: bağlantı, şema ve tablo seçimi üstte; seçilen tablonun sorgu kartı (alanlar, join, filtre) ve sonuç kartı altta gelir.
 * Bağlantı yoksa uyarı gösterilip çıkılır. Seçim değişince önceki sorgu durumu sıfırlanır ve ilgili listeler sunucudan yeniden çekilir.
 * Parametre: root = ekranın ekleneceği kapsayıcı.
 */
async function renderQueryView(root) {
  root.appendChild(el("h2", {}, "Sorgu Oluşturucu"));

  if (!state.connections.length) {
    try { await refreshConnections(); } catch (e) { handleApiError(e); }
  }

  if (!state.connections.length) {
    root.appendChild(el("div", { class: "card" }, el("div", { class: "empty-state" },
      "Önce 'Bağlantılar' sekmesinden bir bağlantı oluşturun."
    )));
    return;
  }

  const topCard = el("div", { class: "card" });
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

  /**
   * Verilen bağlantının şema (schema) listesini açılır kutuya doldurur. Şema desteklemeyen veritabanlarında (örn. SQLite) hata sessizce yutulur ve kutuda sadece '(varsayılan)' kalır.
   * Parametre: connId = bağlantı kimliği.
   */
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

  /**
   * Seçili şemadaki tabloları tablo kutusuna doldurur. Seçili tablo hâlâ listedeyse onu otomatik seçer ve kolonlarını yükler.
   * Parametreler: connId = bağlantı kimliği; schema = şema adı (boş olabilir).
   */
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

  /**
   * Seçilen tablonun kolonlarını yükler ve sorgu kartını gösterir.
   * Önemli: Tablo değişince önceki alan, join, filtre ve gruplama seçimleri bilerek silinir (eski tablonun alanları yeni tabloda geçersizdir).
   * Varsayılan olarak her kolon 'dim' (boyut) alanı olarak işaretlenir; sonra kullanıcı kolonları dahil/hariç yapar.
   */
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
  await loadTablesFor(connSel.value, schemaSel.value);
}

/**
 * Sorgu oluşturucudaki seçimleri sunucuya gönderilecek tek bir nesneye çevirir (buildQueryShape).
 * Alanlar: bağlantı, tablo, şema, alanlar (fields), join, filtre, gruplama, sıralama ve hesaplanmış alanlar.
 * Önizleme, çalıştırma, geçmişe kayıt ve veri seti kaydı hepsi bu şekli kullanır, böylece aynı sorgu her yerde aynı görünür.
 */
function buildQueryShape() {
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
}

/**
 * Sorgu kartının içeriğini (alan çipleri, join, filtre, hesaplanmış alan, gruplama/sıralama, örnek boyutu ve düğmeler) baştan çizer.
 * Parametreler: builderCard = çizilecek kart; resultCard = sonuçların yazılacağı kart (önizleme/çalıştırma bunu kullanır).
 * Her değişiklikte yalnız bu kart silinip yeniden kurulur; state güncellemesi çağıranın sorumluluğundadır.
 */
function renderBuilderCard(builderCard, resultCard) {
  builderCard.innerHTML = "";
  builderCard.appendChild(el("h3", {}, `Tablo: ${state.selectedTable}`));

  builderCard.appendChild(el("label", {}, "Alanlar (tıklayarak dahil et / hariç tut)"));
  const fieldsBox = el("div", { class: "pill-list" });
  for (const col of state.columns) {
    const included = state.fields[col.name] !== "off";
    const chip = el("span", { class: `field-chip ${included ? "included" : ""}` }, [
      col.name,
      el("span", { class: "x" }, ` (${col.type})`),
    ]);
    chip.addEventListener("click", () => {
      state.fields[col.name] = included ? "off" : "dim";
      renderBuilderCard(builderCard, resultCard);
    });
    fieldsBox.appendChild(chip);
  }
  builderCard.appendChild(fieldsBox);

  builderCard.appendChild(el("label", { style: "margin-top:16px" }, "Join'ler"));
  const joinsBox = el("div", { id: "qb-joins-box" });
  renderJoinsBox(joinsBox);
  builderCard.appendChild(joinsBox);
  const addJoinBtn = el("button", { class: "btn btn-sm" }, "+ Join Ekle");
  addJoinBtn.addEventListener("click", () => {
    state.joins.push({ type: "LEFT JOIN", t1: state.selectedTable, f1: "", t2: "", f2: "" });
    renderJoinsBox(joinsBox);
  });
  builderCard.appendChild(addJoinBtn);

  const suggestBtn = el("button", { class: "btn btn-sm", style: "margin-left:8px" }, "Önerilen İlişkiler");
  const suggestBox = el("div", { id: "qb-suggest-box", style: "margin-top:8px" });
  suggestBtn.addEventListener("click", () => withBusy(suggestBtn, () => loadRelationshipSuggestions(suggestBox)));
  builderCard.appendChild(suggestBtn);
  builderCard.appendChild(suggestBox);

  builderCard.appendChild(el("label", { style: "margin-top:16px" }, "Filtreler"));
  const filtersBox = el("div", { id: "qb-filters-box" });
  renderFiltersBox(filtersBox);
  builderCard.appendChild(filtersBox);
  const addFilterBtn = el("button", { class: "btn btn-sm" }, "+ Filtre Ekle");
  addFilterBtn.addEventListener("click", () => {
    state.filters.push({ table: state.selectedTable, column: state.columns[0]?.name || "", operator: "=", value: "", value2: null });
    renderFiltersBox(filtersBox);
  });
  builderCard.appendChild(addFilterBtn);

  builderCard.appendChild(el("label", { style: "margin-top:16px" }, [
    "Hesaplanmış Alanlar (formül)",
    el("span", { class: "muted small" }, " — sadece yukarıda dahil ettiğiniz kolonları kullanabilirsiniz"),
  ]));
  const calcFieldsBox = el("div", { id: "qb-calc-fields-box" });
  renderCalcFieldsBox(calcFieldsBox);
  builderCard.appendChild(calcFieldsBox);
  const addCalcFieldBtn = el("button", { class: "btn btn-sm" }, "+ Hesaplanmış Alan Ekle");
  addCalcFieldBtn.addEventListener("click", () => {
    state.calculatedFields.push({ name: "", formula: "" });
    renderCalcFieldsBox(calcFieldsBox);
  });
  builderCard.appendChild(addCalcFieldBtn);

  const gbInput = el("input", { placeholder: "kolon1, kolon2", value: state.groupBy.join(", ") });
  const obInput = el("input", { placeholder: "kolon1, -kolon2 (- = azalan)", value: state.orderBy.join(", ") });
  gbInput.addEventListener("change", () => {
    state.groupBy = gbInput.value.split(",").map((s) => s.trim()).filter(Boolean);
  });
  obInput.addEventListener("change", () => {
    state.orderBy = obInput.value.split(",").map((s) => s.trim()).filter(Boolean);
  });
  builderCard.appendChild(el("div", { class: "grid-2", style: "margin-top:16px" }, [
    el("div", {}, [el("label", {}, "Group By"), gbInput]),
    el("div", {}, [el("label", {}, "Order By"), obInput]),
  ]));

  const sampleSel = el("select", { id: "qb-sample" }, [10, 100, 1000, 10000].map(
    (n) => el("option", { value: n, selected: n === state.sample ? "selected" : null }, String(n))
  ));
  sampleSel.addEventListener("change", () => { state.sample = parseInt(sampleSel.value, 10); });

  const previewBtn = el("button", { class: "btn" }, "SQL Önizle");
  const runBtn = el("button", { class: "btn btn-primary" }, "Sorguyu Çalıştır");

  previewBtn.addEventListener("click", () => withBusy(previewBtn, () => doPreview(resultCard)));
  runBtn.addEventListener("click", () => withBusy(runBtn, () => doRun(resultCard)));

  builderCard.appendChild(el("div", { class: "row", style: "margin-top:18px" }, [
    el("div", {}, [el("label", {}, "Örnek boyutu"), sampleSel]),
    previewBtn,
    runBtn,
  ]));
}

/**
 * Bir tablonun kolonlarını önbellekten (state._joinColumnsCache) ya da sunucudan alır. Aynı tablo için tekrar istek atılmaz.
 * Hata olursa kullanıcıya bildirilir ve boş dizi döner (join kutusu boş kalır).
 */
async function getColumnsForTable(connId, table) {
  state._joinColumnsCache = state._joinColumnsCache || {};
  const key = `${connId}::${table}`;
  if (state._joinColumnsCache[key]) return state._joinColumnsCache[key];
  try {
    const res = await api.listColumns(connId, table);
    state._joinColumnsCache[key] = res.columns || [];
    return state._joinColumnsCache[key];
  } catch (e) {
    handleApiError(e, "Kolonlar alınamadı");
    return [];
  }
}

// Seçili tablonun 'Önerilen İlişkiler' listesini getirir. Veriler analiz sonucundan gelir; bu yüzden önce Bağlantılar ekranında 'Analiz Et' çalıştırılmış olmalıdır. Analiz tüm şemalardan birikmiş veriyi döndürdüğü için burada şema filtresi uygulanmaz.
// Seçili tabloyla ilgili, daha önce analiz edilmiş (herhangi bir şemadaki)
// ilişkileri getirir ve tek tıkla join olarak eklemeyi sağlar. DB-geneli
// çalışır — getAnalysisResults() tüm şemalardan biriken veriyi döner,
// burada şema filtrelemesi YAPILMAZ.
/**
 * Seçili tablo ile ilgili kayıtlı ilişkileri öneri olarak listeler; tek tıkla join eklenmesini sağlar.
 * Akış: analiz sonuçlarını çek, seçili tabloyu içeren ilişkileri bul, zaten eklenmiş olanları çıkar, her öneri için bir düğme çiz.
 * Parametre: container = önerilerin yazılacağı kutu. Her ekleme sonrası kendini yeniden çizer.
 */
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

/**
 * Join satırlarını kutuya çizer. Her join için: join tipi, sol tablo/kolon, sağ tablo/kolon seçim kutuları ve Sil düğmesi bulunur.
 * Kolon listeleri tablo seçilince getirilir (getColumnsForTable). Parametre box = join kutusu öğesi.
 */
function renderJoinsBox(box) {
  box.innerHTML = "";
  state.joins.forEach((j, idx) => {
    const typeSel = el("select", {}, ALLOWED_JOIN_TYPES.map(
      (t) => el("option", { value: t, selected: t === j.type ? "selected" : null }, t)
    ));

    // Tablo seçim kutusunun seçenekleri: başta boş bir 'tablo seçin' satırı, sonra bağlantıdaki tüm tablolar. Seçili olan tablo 'selected' ile işaretlenir.
    const tableOptions = (selected) => [el("option", { value: "" }, "tablo seçin")].concat(
      state.tables.map((t) => el("option", { value: t, selected: t === selected ? "selected" : null }, t))
    );

    const t1Sel = el("select", {}, tableOptions(j.t1));
    const t2Sel = el("select", {}, tableOptions(j.t2));
    const f1Sel = el("select", {}, [el("option", { value: j.f1 || "" }, j.f1 || "kolon seçin")]);
    const f2Sel = el("select", {}, [el("option", { value: j.f2 || "" }, j.f2 || "kolon seçin")]);
    const delBtn = el("button", { class: "btn btn-sm btn-danger" }, "Sil");

    /**
     * Bir tablo kutusu değişince kolon kutusunu o tablonun kolonlarıyla doldurur. Tablo boşsa 'önce tablo seçin' yazar.
     * Parametreler: tableSel = tablo kutusu; colSel = kolon kutusu; currentVal = önceden seçili kolon (varsa tekrar seçili gelsin diye).
     */
    async function refreshColumnSelect(tableSel, colSel, currentVal) {
      const table = tableSel.value;
      colSel.innerHTML = "";
      if (!table) {
        colSel.appendChild(el("option", { value: "" }, "önce tablo seçin"));
        return;
      }
      colSel.appendChild(el("option", { value: "" }, "yükleniyor…"));
      const cols = await getColumnsForTable(state.selectedConnId, table);
      colSel.innerHTML = "";
      colSel.appendChild(el("option", { value: "" }, "kolon seçin"));
      for (const c of cols) {
        colSel.appendChild(el("option", { value: c.name, selected: c.name === currentVal ? "selected" : null }, c.name));
      }
    }

    typeSel.addEventListener("change", () => { j.type = typeSel.value; });
    t1Sel.addEventListener("change", () => { j.t1 = t1Sel.value; j.f1 = ""; refreshColumnSelect(t1Sel, f1Sel, ""); });
    t2Sel.addEventListener("change", () => { j.t2 = t2Sel.value; j.f2 = ""; refreshColumnSelect(t2Sel, f2Sel, ""); });
    f1Sel.addEventListener("change", () => { j.f1 = f1Sel.value; });
    f2Sel.addEventListener("change", () => { j.f2 = f2Sel.value; });
    delBtn.addEventListener("click", () => { state.joins.splice(idx, 1); renderJoinsBox(box); });

    if (j.t1) refreshColumnSelect(t1Sel, f1Sel, j.f1);
    if (j.t2) refreshColumnSelect(t2Sel, f2Sel, j.f2);

    box.appendChild(el("div", { class: "join-row" }, [typeSel, t1Sel, f1Sel, t2Sel, f2Sel, delBtn]));
  });
}

/**
 * Filtre satırlarını kutuya çizer: kolon adı, operatör, değer ve (BETWEEN için) ikinci değer alanları ile Sil düğmesi.
 * IN / NOT IN için değer virgülle ayrılmış bir listeye çevrilir. Parametre box = filtre kutusu.
 */
function renderFiltersBox(box) {
  box.innerHTML = "";
  state.filters.forEach((f, idx) => {
    const colInput = el("input", { value: f.column, placeholder: "kolon" });
    const opSel = el("select", {}, ALLOWED_OPERATORS.map(
      (o) => el("option", { value: o, selected: o === f.operator ? "selected" : null }, o)
    ));
    const valInput = el("input", { value: f.value ?? "", placeholder: "değer" });
    const val2Input = el("input", { value: f.value2 ?? "", placeholder: "değer 2 (BETWEEN)" });
    const delBtn = el("button", { class: "btn btn-sm btn-danger" }, "Sil");

    /**
     * Operatöre göre değer kutularını gösterir/gizler: IS NULL ve IS NOT NULL'da değer gerekmez; BETWEEN'de ikinci değer kutusu açılır.
     */
    function syncVisibility() {
      const noValue = f.operator === "IS NULL" || f.operator === "IS NOT NULL";
      valInput.style.display = noValue ? "none" : "block";
      val2Input.style.display = f.operator === "BETWEEN" ? "block" : "none";
    }
    syncVisibility();

    colInput.addEventListener("change", () => { f.column = colInput.value; });
    opSel.addEventListener("change", () => { f.operator = opSel.value; syncVisibility(); });
    valInput.addEventListener("change", () => {
      f.value = (f.operator === "IN" || f.operator === "NOT IN")
        ? valInput.value.split(",").map((s) => s.trim()).filter(Boolean)
        : valInput.value;
    });
    val2Input.addEventListener("change", () => { f.value2 = val2Input.value; });
    delBtn.addEventListener("click", () => { state.filters.splice(idx, 1); renderFiltersBox(box); });

    box.appendChild(el("div", { class: "filter-row" }, [colInput, opSel, valInput, val2Input, el("span"), delBtn]));
  });
  if (state.filters.some((f) => f.operator === "IN" || f.operator === "NOT IN")) {
    box.appendChild(el("p", { class: "muted small" }, "IN / NOT IN için değerleri virgülle ayırın."));
  }
}

/**
 * Hesaplanmış alan (formül) satırlarını kutuya çizer: alan adı, formül metni ve Sil düğmesi.
 * Formül alanı altında desteklenen ifadeler hakkında kısa uyarı gösterilir. Alt sorgu gibi desteklenmeyen ifadeler sunucuda reddedilir.
 */
function renderCalcFieldsBox(box) {
  box.innerHTML = "";
  state.calculatedFields.forEach((cf, idx) => {
    const nameInput = el("input", { value: cf.name, placeholder: "alan_adi (örn: kdv_dahil)" });
    const formulaInput = el("input", {
      value: cf.formula,
      placeholder: "formül (örn: ROUND(price * 1.18, 2))",
      style: "flex:2",
    });
    const delBtn = el("button", { class: "btn btn-sm btn-danger" }, "Sil");

    nameInput.addEventListener("change", () => { cf.name = nameInput.value.trim(); });
    formulaInput.addEventListener("change", () => { cf.formula = formulaInput.value; });
    delBtn.addEventListener("click", () => { state.calculatedFields.splice(idx, 1); renderCalcFieldsBox(box); });

    box.appendChild(el("div", { class: "row", style: "margin-bottom:8px" }, [nameInput, formulaInput, delBtn]));
  });
  if (state.calculatedFields.length) {
    box.appendChild(el("p", { class: "muted small" },
      "Sadece +, -, *, /, CASE WHEN, ROUND, ABS, COALESCE, UPPER, LOWER gibi temel " +
      "SQL ifadeleri desteklenir. Alt sorgu veya bilinmeyen fonksiyonlar reddedilir."
    ));
  }
}

/**
 * 'SQL Önizle' düğmesi: sorguyu çalıştırmadan, sunucunun üreteceği SQL metnini ister ve sonuç kartında gösterir. Hata olursa mesaj gösterilir.
 * Parametre resultCard = sonucun yazılacağı kart.
 */
async function doPreview(resultCard) {
  try {
    const conn = state.connections.find((c) => c.conn_id === state.selectedConnId);
    const body = { ...buildQueryShape(), limit: state.sample, db_type: conn ? conn.db_type : "sqlite" };
    const res = await api.previewSql(body);
    state.lastPreview = res;
    renderResultCard(resultCard);
  } catch (e) { handleApiError(e, "SQL önizleme başarısız — filtre/join alanlarını kontrol edin"); }
}

/**
 * 'Sorguyu Çalıştır' düğmesi: sorguyu sunucuda çalıştırır (örnek boyut kadar satır, commit: false ile henüz kalıcı değil) ve sonucu gösterir. Başarılıysa satır sayısı ve süre bildirimi çıkar.
 * Parametre resultCard = sonucun yazılacağı kart.
 */
async function doRun(resultCard) {
  try {
    const body = { ...buildQueryShape(), sample: state.sample, commit: false, mode: "memory" };
    const res = await api.runQuery(body);
    state.lastRun = res;
    renderResultCard(resultCard);
    toast(`${res.row_count} satır, ${res.exec_ms}ms (${res.mode})`, "success");
  } catch (e) { handleApiError(e, "Sorgu çalıştırılamadı"); }
}

/**
 * 'Sorguyu Çalıştır' sonucunu gösterir: önizleme SQL'i (varsa), çalıştırma rozetleri (satır sayısı, süre, önbellek durumu), onay düğmesi, geçmişe ve veri setine kaydet düğmeleri ve tablo.
 * Commit: sonuç önce geçici (30 sn) olarak durur; 'Bu sonucu onayla' ile 5 dakikalık önbelleğe alınır.
 * Not: Sonuç hücreleri text node olarak eklenir (HTML yorumlanmaz).
 */
function renderResultCard(resultCard) {
  resultCard.style.display = "block";
  resultCard.innerHTML = "";
  resultCard.appendChild(el("h3", {}, "Sonuç"));

  if (state.lastPreview) {
    resultCard.appendChild(el("p", { class: "muted small" }, `Tahmini karmaşıklık: ${state.lastPreview.estimated_complexity}`));
    resultCard.appendChild(el("pre", { class: "sql-preview" }, state.lastPreview.sql));
  }

  if (state.lastRun) {
    const r = state.lastRun;
    resultCard.appendChild(el("div", { class: "row" }, [
      el("span", { class: "badge" }, `${r.row_count} satır`),
      el("span", { class: "badge" }, `${r.exec_ms} ms`),
      el("span", { class: `badge ${r.from_cache ? "ok" : ""}` }, r.from_cache ? "cache'ten" : "canlı"),
      el("span", { class: `badge ${r.committed ? "ok" : "warn"}` }, r.committed ? "commit edildi" : "geçici (30sn)"),
    ]));

    if (!r.committed) {
      const commitBtn = el("button", { class: "btn btn-primary btn-sm", style: "margin:10px 0" }, "Bu sonucu onayla (5dk'ya al)");
      commitBtn.addEventListener("click", () => withBusy(commitBtn, async () => {
        try {
          await api.commitQuery(r.cache_key);
          r.committed = true;
          toast("Onaylandı, 5 dakika cache'te kalacak", "success");
          renderResultCard(resultCard);
        } catch (e) { handleApiError(e, "Onaylanamadı"); }
      }));
      resultCard.appendChild(commitBtn);
    }

    const saveHistBtn = el("button", { class: "btn btn-sm", style: "margin:10px 0 10px 8px" }, "Geçmişe Kaydet");
    saveHistBtn.addEventListener("click", () => withBusy(saveHistBtn, async () => {
      try {
        const shape = buildQueryShape();
        const fingerprint = await computeFingerprint(shape);
        await api.addHistory({
          fingerprint,
          conn_id: shape.conn_id,
          base_table: shape.base_table,
          sql_text: state.lastPreview ? state.lastPreview.sql : "",
          fields: shape.fields, joins: shape.joins, filters: shape.filters, group_by: shape.group_by,
          sample: state.sample, mode: r.mode,
          row_count: r.row_count, exec_ms: r.exec_ms,
        });
        toast("Geçmişe kaydedildi", "success");
      } catch (e) { handleApiError(e, "Geçmişe kaydedilemedi"); }
    }));
    resultCard.appendChild(saveHistBtn);

    const saveDatasetBtn = el("button", { class: "btn btn-sm", style: "margin:10px 0 10px 8px" }, "Dataset Olarak Kaydet");
    saveDatasetBtn.addEventListener("click", () => withBusy(saveDatasetBtn, async () => {
      const name = prompt("Bu sorguyu hangi isimle kaydedelim? (Aynı isim varsa GÜNCELLENİR — ona bağlı tüm widget'lar otomatik yeni veriyi gösterir)");
      if (!name) return;
      try {
        const shape = buildQueryShape();
        const payload = {
          name, conn_id: shape.conn_id, base_table: shape.base_table,
          fields: shape.fields, joins: shape.joins, filters: shape.filters,
          group_by: shape.group_by, order_by: shape.order_by,
        };

        const existing = await api.listDatasets();
        const match = existing.find((d) => d.name.trim().toLowerCase() === name.trim().toLowerCase());

        if (match) {
          await api.updateDataset(match.dataset_id, payload);
          toast(`"${name}" güncellendi — ona bağlı tüm widget'lar bir sonraki görüntülemede yeni veriyi gösterecek`, "success");
        } else {
          await api.createDataset(payload);
          toast(`Dataset kaydedildi: "${name}" — artık widget'larda "Kayıtlı Sorgu Kullan" ile seçilebilir`, "success");
        }
      } catch (e) { handleApiError(e, "Dataset kaydedilemedi"); }
    }));
    resultCard.appendChild(saveDatasetBtn);

    const table = el("table");
    table.appendChild(el("thead", {}, el("tr", {}, r.columns.map((c) => el("th", {}, c)))));
    const tbody = el("tbody");
    for (const row of r.rows) {
      tbody.appendChild(el("tr", {}, row.map((v) => el("td", {}, v === null ? "NULL" : String(v)))));
    }
    table.appendChild(tbody);
    resultCard.appendChild(table);
  }
}

/**
 * Sorgunun 'parmak izini' (fingerprint) üretir: base_table + join + group_by içeriğinin SHA-256 özeti, ilk 24 hex karakter.
 * Neden: Aynı yapıdaki sorgular geçmişte tek grupta toplansın diye. Bu bir güvenlik özeti değildir, yalnız gruplama anahtarıdır.
 * Tarayıcının crypto.subtle API'si kullanılır (asenkron).
 */
async function computeFingerprint(shape) {
  const payload = JSON.stringify({
    base_table: shape.base_table,
    joins: shape.joins,
    group_by: shape.group_by,
  });
  const enc = new TextEncoder().encode(payload);
  const hashBuf = await crypto.subtle.digest("SHA-256", enc);
  return Array.from(new Uint8Array(hashBuf)).map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 24);
}

/* ============================================================
 * 3) Geçmiş (History)
 * ==========================================================*/

/**
 * 'Sorgu Geçmişi' ekranını kurar: son çalıştırılanlar ve fingerprint'e göre gruplanmış sürümler iki ayrı kartta gösterilir. Her biri ayrı try/catch ile yüklenir; biri hata verse diğeri yine çalışır.
 * Parametre: root = ekranın ekleneceği kapsayıcı.
 */
async function renderHistoryView(root) {
  root.appendChild(el("h2", {}, "Sorgu Geçmişi"));

  const recentCard = el("div", { class: "card" });
  recentCard.appendChild(el("h3", {}, "Son Çalıştırılanlar"));
  const recentBody = el("div", {}, el("p", { class: "muted" }, "Yükleniyor…"));
  recentCard.appendChild(recentBody);
  root.appendChild(recentCard);

  const groupsCard = el("div", { class: "card" });
  groupsCard.appendChild(el("h3", {}, "Sorgu Grupları (fingerprint bazlı sürümler)"));
  const groupsBody = el("div", {}, el("p", { class: "muted" }, "Yükleniyor…"));
  groupsCard.appendChild(groupsBody);
  root.appendChild(groupsCard);

  try {
    state.historyRecent = await api.getRecent(30);
    renderRecentTable(recentBody);
  } catch (e) {
    handleApiError(e, "Geçmiş alınamadı");
    recentBody.innerHTML = "";
    recentBody.appendChild(el("p", { class: "error-text" }, "Yüklenemedi."));
  }

  try {
    state.historyGroups = await api.getGroups();
    renderGroupsTable(groupsBody);
  } catch (e) {
    handleApiError(e, "Gruplar alınamadı");
    groupsBody.innerHTML = "";
    groupsBody.appendChild(el("p", { class: "error-text" }, "Yüklenemedi."));
  }
}

/**
 * state.historyRecent (son çalıştırmalar) listesini tabloya çevirir. Tarih için fmtDate kullanılır; eksik alanlar '-' ile gösterilir.
 * Parametre container = tablonun yazılacağı kutu.
 */
function renderRecentTable(container) {
  container.innerHTML = "";
  if (!state.historyRecent.length) {
    container.appendChild(el("div", { class: "empty-state" }, "Henüz kayıtlı sorgu geçmişi yok."));
    return;
  }
  const table = el("table");
  table.appendChild(el("thead", {}, el("tr", {}, ["Tablo", "Bağlantı", "Satır", "Süre (ms)", "Mod", "Tarih"].map((h) => el("th", {}, h)))));
  const tbody = el("tbody");
  for (const v of state.historyRecent) {
    tbody.appendChild(el("tr", {}, [
      el("td", {}, v.base_table || "-"),
      el("td", {}, v.conn_id || "-"),
      el("td", {}, String(v.row_count ?? "-")),
      el("td", {}, String(v.exec_ms ?? "-")),
      el("td", {}, v.mode || "-"),
      el("td", {}, fmtDate(v.created_at || v.at)),
    ]));
  }
  table.appendChild(tbody);
  container.appendChild(table);
}

/**
 * state.historyGroups listesini tabloya çevirir; her satırda 'Grubu Sil' düğmesi vardır. Silme onaydan sonra yapılır ve liste sunucudan yeniden çekilir.
 * Parametre container = tablonun yazılacağı kutu.
 */
function renderGroupsTable(container) {
  container.innerHTML = "";
  if (!state.historyGroups.length) {
    container.appendChild(el("div", { class: "empty-state" }, "Henüz sorgu grubu yok."));
    return;
  }
  const table = el("table");
  table.appendChild(el("thead", {}, el("tr", {}, ["Tablo", "Bağlantı", "Sürüm Sayısı", "Son Çalışma", "Ortalama Süre", ""].map((h) => el("th", {}, h)))));
  const tbody = el("tbody");
  for (const g of state.historyGroups) {
    const delBtn = el("button", { class: "btn btn-sm btn-danger" }, "Grubu Sil");
    delBtn.addEventListener("click", async () => {
      if (!confirm("Bu sorgu grubunun tüm sürümlerini silmek istediğinize emin misiniz?")) return;
      try {
        await api.deleteGroup(g.fingerprint);
        toast("Grup silindi", "success");
        state.historyGroups = await api.getGroups();
        renderGroupsTable(container);
      } catch (e) { handleApiError(e, "Silinemedi"); }
    });
    tbody.appendChild(el("tr", {}, [
      el("td", {}, g.base_table || "-"),
      el("td", {}, g.conn_name || g.conn_id || "-"),
      el("td", {}, String(g.version_count ?? "-")),
      el("td", {}, fmtDate(g.last_at)),
      el("td", {}, g.avg_ms != null ? `${Math.round(g.avg_ms)} ms` : "-"),
      el("td", {}, delBtn),
    ]));
  }
  table.appendChild(tbody);
  container.appendChild(table);
}

/* ============================================================
 * 4) Dashboard'lar — Undo/Redo dahil
 * ==========================================================*/

// Dashboard tuvalinde 1 mm'nin kaç piksel olduğu (ekranda ölçek). mmToPx/pxToMm bu sabit ve yakınlık (zoom) ile çalışır. Tüm yerleşim değerleri (x, y, w, h) milimetre cinsinden saklanır, ekranda piksele çevrilir.
const PX_PER_MM = 3;

// Palete eklenebilecek widget türleri. w/h: yeni eklenen widget'ın varsayılan boyutu (mm). 'type' değeri CHART_TYPES ve renderWidgetChart kararlarında kullanılır.
const WIDGET_TYPES = [
  { type: "kpi",     label: "KPI Kartı",        w: 60,  h: 40 },
  { type: "line",    label: "Çizgi Grafik",      w: 100, h: 70 },
  { type: "area",    label: "Alan Grafik",        w: 100, h: 70 },
  { type: "column",  label: "Sütun Grafik",       w: 100, h: 70 },
  { type: "bar",     label: "Yatay Sütun",        w: 100, h: 70 },
  { type: "scatter", label: "Dağılım Grafiği",    w: 90,  h: 70 },
  { type: "pie",     label: "Pasta Grafik",        w: 70,  h: 70 },
  { type: "donut",   label: "Halka Grafik",        w: 70,  h: 70 },
  { type: "table",   label: "Tablo",              w: 120, h: 80 },
  { type: "matrix",  label: "Matris",             w: 120, h: 80 },
  { type: "map",     label: "Harita",             w: 100, h: 90 },
  { type: "text",    label: "Metin Kutusu",        w: 80,  h: 30 },
];

/**
 * Milimetreyi ekrandaki piksele çevirir (yakınlık dahil). Parametre mm: milimetre. Dönüş: piksel sayısı (metin olarak style'a yazılır).
 */
function mmToPx(mm) { return mm * PX_PER_MM * state.dashZoom; }
/**
 * Ekrandaki pikseli milimetreye çevirir; mmToPx'in tersidir. Sürükleme ve boyutlandırmada fare hareketi mm'ye çevrilirken kullanılır.
 */
function pxToMm(px) { return px / (PX_PER_MM * state.dashZoom); }

/**
 * Boş yeni bir dashboard nesnesi döner. Varsayılan sayfa yatay A4 (297 x 210 mm), henüz kaydedilmemiş olduğu için dashboard_id null'dır.
 */
function blankDashboard() {
  return { dashboard_id: null, name: "Yeni Dashboard", scale: "a4l", page_w_mm: 297, page_h_mm: 210, objects: [] };
}

/* ---- Dashboard Yerleşim Şablonları ---- */
// Koordinatlar referans 297x210mm (a4l) üzerinden tasarlandı; applyDashboardTemplate
// farklı page_w_mm/page_h_mm için oranlı ölçekler. Saf frontend — backend/API değişmedi.
// Hazır yerleşim şablonları. Koordinatlar 297 x 210 mm referansa göre yazılmıştır; applyDashboardTemplate diğer sayfa boyutlarına oranlı ölçekler. Şablon eklemek için buraya yeni bir giriş eklemek yeterlidir.
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
}

/* ---- Undo/Redo ---- */

// Dashboard'un mevcut objects dizisini derin kopyalayıp geçmişe ekler.
// Her rerenderWidget() çağrısının sonunda ve widget ekle/sil/sürükle/boyutlandır
// işlemlerinin sonunda çağrılmalı.
function pushHistory() {
  const dash = state.currentDashboard;
  if (!dash) return;
  const snapshot = JSON.stringify(dash.objects);
  // İndeksin ötesindeki geçmişi sil (redo branch temizleme)
  state.dashHistory = state.dashHistory.slice(0, state.dashHistoryIndex + 1);
  state.dashHistory.push(snapshot);
  // Bellek tasarrufu: en fazla 50 adım sakla
  if (state.dashHistory.length > 50) state.dashHistory.shift();
  state.dashHistoryIndex = state.dashHistory.length - 1;
  updateUndoRedoButtons();
}

/**
 * Bir adım geri alır (Ctrl+Z). Geçmişte önceki bir görüntü varsa imleci bir geri alır ve onu uygular. En eski kayıtta hiçbir şey yapmaz.
 */
function undoDashboard() {
  if (state.dashHistoryIndex <= 0) return;
  state.dashHistoryIndex--;
  _applyHistorySnapshot();
}

/**
 * Bir adım ileri alır (Ctrl+Y). Geri alınmış bir adım varsa onu yeniden uygular. En son kayıtta hiçbir şey yapmaz.
 */
function redoDashboard() {
  if (state.dashHistoryIndex >= state.dashHistory.length - 1) return;
  state.dashHistoryIndex++;
  _applyHistorySnapshot();
}

/**
 * dashHistoryIndex'teki anlık görüntüyü (JSON metni) geri yükler: dash.objects bu kopyadan yeniden üretilir ve tuval yeniden çizilir. Parse ettiği için her seferinde bağımsız bir kopya olur; geçmişteki kayıt değişmez.
 */
function _applyHistorySnapshot() {
  const dash = state.currentDashboard;
  if (!dash) return;
  const snapshot = state.dashHistory[state.dashHistoryIndex];
  if (snapshot === undefined) return;
  dash.objects = JSON.parse(snapshot);
  const canvasPage = qs("#dash-canvas-page");
  if (canvasPage) renderCanvasPage(canvasPage);
  updateUndoRedoButtons();
}

/**
 * Geri Al / İleri Al düğmelerini geçmiş durumuna göre açar veya kapatır. Düğmeler yoksa (editör açık değilse) hiçbir şey yapmaz.
 */
function updateUndoRedoButtons() {
  const undoBtn = qs("#dash-undo-btn");
  const redoBtn = qs("#dash-redo-btn");
  if (undoBtn) undoBtn.disabled = state.dashHistoryIndex <= 0;
  if (redoBtn) redoBtn.disabled = state.dashHistoryIndex >= state.dashHistory.length - 1;
}

/* ---- Dashboard listesi ve editör ---- */

/**
 * 'Dashboard'lar' ekranını kurar. Üstte yeni dashboard düğmesi; şablon seçici açıksa şablon kartları, değilse kayıtlı dashboard listesi gösterilir. Açık bir dashboard varsa altına editör çizilir.
 * Parametre: root = ekranın ekleneceği kapsayıcı.
 */
async function renderDashboardsView(root) {
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
}

/**
 * Kayıtlı dashboard'ların tablosunu çizer. Her satırda 'Aç' (sunucudan çekip editörde açar) ve 'Sil' (onaydan sonra siler) düğmeleri vardır.
 * Parametre container = tablonun yazılacağı kutu.
 */
function renderDashList(container) {
  container.innerHTML = "";
  if (!state.dashboards.length) {
    container.appendChild(el("div", { class: "empty-state" }, "Henüz dashboard yok. Yukarıdan yeni bir tane oluşturun."));
    return;
  }
  const table = el("table");
  table.appendChild(el("thead", {}, el("tr", {}, ["Ad", "Güncellenme", ""].map((h) => el("th", {}, h)))));
  const tbody = el("tbody");
  for (const d of state.dashboards) {
    const openBtn = el("button", { class: "btn btn-sm" }, "Aç");
    const delBtn = el("button", { class: "btn btn-sm btn-danger" }, "Sil");
    openBtn.addEventListener("click", () => withBusy(openBtn, async () => {
      try {
        state.currentDashboard = await api.getDashboard(d.dashboard_id);
        state.selectedWidgetId = null;
        state.dashHistory = [];
        state.dashHistoryIndex = -1;
        renderView("dashboards");
      } catch (e) { handleApiError(e, "Açılamadı"); }
    }));
    delBtn.addEventListener("click", async () => {
      if (!confirm(`"${d.name}" silinsin mi?`)) return;
      try {
        await api.deleteDashboard(d.dashboard_id);
        toast("Silindi", "success");
        if (state.currentDashboard?.dashboard_id === d.dashboard_id) state.currentDashboard = null;
        renderView("dashboards");
      } catch (e) { handleApiError(e, "Silinemedi"); }
    });
    tbody.appendChild(el("tr", {}, [
      el("td", {}, d.name),
      el("td", {}, fmtDate(d.updated_at)),
      el("td", { class: "row" }, [openBtn, delBtn]),
    ]));
  }
  table.appendChild(tbody);
  container.appendChild(table);
}

/**
 * Dashboard düzenleyicisini çizer: araç çubuğu (ad, zoom, undo/redo, şablon, kaydet, kapat), sol widget paleti, orta tuval (sayfa) ve sağ özellik paneli.
 * Kaydetme: dashboard_id yoksa yeni oluşturulur (POST), varsa güncellenir (PUT). Her ekleme/silme/taşıma pushHistory ile geçmişe yazılır.
 * Klavye: Ctrl+Z / Ctrl+Y, yalnız bir metin kutusu odakta değilken çalışır.
 * Parametre root = editörün ekleneceği kapsayıcı.
 */
function renderDashboardEditor(root) {
  const dash = state.currentDashboard;
  const card = el("div", { class: "card" });

  // --- Araç çubuğu ---
  const nameInput = el("input", { value: dash.name, style: "width:220px" });
  nameInput.addEventListener("change", () => { dash.name = nameInput.value; });

  const zoomInput = el("input", { type: "range", min: "0.5", max: "2", step: "0.1", value: String(state.dashZoom) });
  const zoomLabel = el("span", { class: "muted small" }, `${Math.round(state.dashZoom * 100)}%`);
  zoomInput.addEventListener("input", () => {
    state.dashZoom = parseFloat(zoomInput.value);
    zoomLabel.textContent = `${Math.round(state.dashZoom * 100)}%`;
    renderCanvasPage(canvasPage);
  });

  // Undo / Redo butonları
  const undoBtn = el("button", {
    class: "btn btn-sm",
    id: "dash-undo-btn",
    title: "Geri Al (Ctrl+Z)",
    disabled: state.dashHistoryIndex <= 0 ? "disabled" : null,
  }, "↩ Geri Al");
  const redoBtn = el("button", {
    class: "btn btn-sm",
    id: "dash-redo-btn",
    title: "İleri Al (Ctrl+Y)",
    disabled: state.dashHistoryIndex >= state.dashHistory.length - 1 ? "disabled" : null,
  }, "↪ İleri Al");
  undoBtn.addEventListener("click", () => undoDashboard());
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

  const saveBtn = el("button", { class: "btn btn-primary" }, dash.dashboard_id ? "Güncelle" : "Kaydet");
  saveBtn.addEventListener("click", () => withBusy(saveBtn, async () => {
    try {
      const body = {
        name: dash.name, scale: dash.scale, page_w_mm: dash.page_w_mm, page_h_mm: dash.page_h_mm,
        objects: dash.objects,
      };
      if (dash.dashboard_id) {
        await api.updateDashboard(dash.dashboard_id, body);
        toast("Dashboard güncellendi", "success");
      } else {
        const res = await api.createDashboard(body);
        dash.dashboard_id = res.dashboard_id;
        toast("Dashboard kaydedildi", "success");
      }
      state.dashboards = await api.listDashboards();
    } catch (e) { handleApiError(e, "Kaydedilemedi"); }
  }));

  const closeBtn = el("button", { class: "btn" }, "Kapat");
  closeBtn.addEventListener("click", () => { state.currentDashboard = null; renderView("dashboards"); });

  card.appendChild(el("div", { class: "dash-toolbar" }, [
    el("div", {}, [el("label", {}, "Ad"), nameInput]),
    el("div", {}, [el("label", {}, "Zoom"), el("div", { class: "row" }, [zoomInput, zoomLabel])]),
    el("div", {}, [el("label", {}, "Şablon"), templateSelect]),
    undoBtn, redoBtn,
    saveBtn, closeBtn,
  ]));

  // --- Gövde: palet + canvas ---
  const body = el("div", { class: "dash-body" });

  const palette = el("div", { class: "widget-palette" });
  palette.appendChild(el("label", {}, "Widget Ekle"));
  for (const w of WIDGET_TYPES) {
    const item = el("div", { class: "palette-item" }, w.label);
    item.addEventListener("click", () => {
      dash.objects.push({
        id: "w_" + Math.random().toString(36).slice(2, 9),
        type: w.type, x: 10, y: 10, w: w.w, h: w.h,
        title: w.label, query_id: null, color: "#378ADD",
      });
      renderCanvasPage(canvasPage);
      pushHistory();
    });
    palette.appendChild(item);
  }
  body.appendChild(palette);

  const canvasWrap = el("div", { class: "canvas-wrap" });
  const canvasPage = el("div", { class: "canvas-page", id: "dash-canvas-page" });
  canvasWrap.appendChild(canvasPage);
  body.appendChild(canvasWrap);

  const propsPanel = el("div", { class: "widget-palette", id: "dash-props-panel" });
  body.appendChild(propsPanel);

  card.appendChild(body);
  root.appendChild(card);

  // Klavye kısayolları — sadece dashboard editörü açıkken aktif
  // DİKKAT: Bu dinleyici yalnız 'Kapat' düğmesine basılınca kaldırılır. Ekran başka bir görünüme geçerse kaldırılmaz; her yeniden çizimde yeni bir dinleyici eklenir. Sonuçta Ctrl+Z tek basışta birden fazla kez çalışabilir.
  function onKeyDown(e) {
    // Input/textarea odakta ise kısayolları devreye alma
    const tag = document.activeElement?.tagName?.toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    if (e.ctrlKey && e.key === "z") { e.preventDefault(); undoDashboard(); }
    if (e.ctrlKey && e.key === "y") { e.preventDefault(); redoDashboard(); }
  }
  // Önceki editör çiziminden kalan dinleyiciyi kaldır (Ctrl+Z birikip çoklu geri almayı önler)
  if (window.__dashKeyHandler) document.removeEventListener("keydown", window.__dashKeyHandler);
  window.__dashKeyHandler = onKeyDown;
  document.addEventListener("keydown", onKeyDown);
  // Editör kapandığında dinleyiciyi temizle
  // TODO(kontrol): origClose hiçbir yerde kullanılmıyor (ölü kod). Silinebilir, ama davranışı değiştirmemek için bu sürümde bırakıldı.
  const origClose = closeBtn.onclick;
  closeBtn.addEventListener("click", () => document.removeEventListener("keydown", onKeyDown), { once: true });

  // İlk geçmiş snapshot'ı al (editör açıldığında başlangıç durumu)
  if (state.dashHistory.length === 0) pushHistory();

  renderCanvasPage(canvasPage);
  renderPropsPanel(propsPanel);
}

/* ---- Widget config helpers ---- */

/**
 * Widget'ın veri ayarlarını (query_id alanında JSON metni olarak saklanır) nesneye çevirir. Ayar yoksa veya bozuksa null döner.
 */
function getWidgetConfig(obj) {
  if (!obj.query_id) return null;
  try { return JSON.parse(obj.query_id); } catch { return null; }
}
/**
 * Widget'ın veri ayarlarını JSON metni olarak query_id alanına yazar (getWidgetConfig'in tersi).
 * Ayar alanı bu sürümde query_id içinde saklanır; kaydetme sırasında bu alan olduğu gibi gönderilir.
 */
function setWidgetConfig(obj, config) {
  obj.query_id = JSON.stringify(config);
}

// Grafik olarak çizilebilen widget türleri (tablo ve metin bunun dışında, ayrı çizilir).
const CHART_TYPES = new Set(["line", "area", "column", "bar", "scatter", "pie", "donut", "kpi", "map"]);
// Birden fazla seri (değer kolonu) destekleyen türler. Bunlarda 'valueCols' dizisi kullanılır; pie, donut, kpi ve map tek seri çizer.
const MULTI_SERIES_TYPES = new Set(["line", "area", "column", "bar", "scatter"]);

// Açık ECharts grafik nesneleri (widget id'ye göre). Yeniden çizimde ve kaldırmada bunlar dispose edilmezse bellek sızar.
const chartInstances = new Map();
// Tablo ve CSV dışa aktarma için son çekilen veriler (widget id'ye göre). exportWidget bu önbellekten okur.
const widgetDataCache = new Map();

// Dünya haritası verisinin tek seferde yüklenmesi için saklanan söz (Promise). Aynı anda birden çok harita olsa bile indirme bir kez yapılır.
let worldMapPromise = null;
/**
 * Dünya haritası (world.json) verisini harici CDN'den bir kez indirir ve ECharts'a 'world' adıyla kaydeder. Sonraki çağrılar aynı Promise'i döner.
 * DİKKAT: Bu, tarayıcının dış CDN'ye (cdn.jsdelivr.net) erişmesini gerektirir; bağlantı yoksa harita çizilmez (hata mesajı gösterilir). Bütünlük (SRI) kontrolü yoktur.
 */
function ensureWorldMapRegistered() {
  if (!worldMapPromise) {
    worldMapPromise = fetch("https://cdn.jsdelivr.net/npm/echarts@5.5.1/map/json/world.json")
      .then((r) => { if (!r.ok) throw new Error("world.json indirilemedi"); return r.json(); })
      .then((geoJson) => { window.echarts.registerMap("world", geoJson); return true; });
  }
  return worldMapPromise;
}

/**
 * Widget ayarından sorgunun 'temel' bilgilerini çıkarır. Eğer veri seti (datasetId) bağlıysa veri setinin tanımını sunucudan çeker; değilse doğrudan bağlantı ve tablo bilgisini kullanır.
 * Dönüş: conn_id, base_table, joins, filters, group_by, order_by alanlarını içeren nesne.
 */
async function resolveQueryBase(config) {
  if (config.datasetId) {
    const ds = await api.getDataset(config.datasetId);
    return {
      conn_id: ds.conn_id, base_table: ds.base_table,
      joins: ds.joins || [], filters: ds.filters || [],
      group_by: ds.group_by || [], order_by: ds.order_by || [],
    };
  }
  return { conn_id: config.conn_id, base_table: config.table, joins: [], filters: [], group_by: [], order_by: [] };
}

/**
 * Veri setinin kolon adlarını bulur. Veri seti tanımını alıp 1 satırlık örnek sorgu çalıştırır; yalnız 'columns' listesi kullanılır.
 * Neden 1 satır: Kolon adları için tüm veriyi çekmeye gerek yoktur.
 */
async function fetchDatasetColumns(datasetId) {
  const ds = await api.getDataset(datasetId);
  const res = await api.runQuery({
    conn_id: ds.conn_id, base_table: ds.base_table,
    fields: ds.fields || {}, joins: ds.joins || [], filters: ds.filters || [],
    group_by: ds.group_by || [], order_by: ds.order_by || [],
    sample: 1, commit: false, mode: "memory",
  });
  return res.columns;
}

/**
 * Tek seriye ait veriyi (etiket ve değer kolonu) sunucudan çeker ve grafik için hazırlar. Eğer agg (toplama) seçiliyse aynı etiketli satırları toplar (sum, avg, count, min, max).
 * DİKKAT: Sunucu en fazla 500 satır döndürür (sample: 500). Toplamlar bu örnek üzerinden hesaplanır, tüm tablo üzerinden değildir.
 * Dönüş: { labels, values, rawRows, rawCols }.
 */
async function fetchWidgetData(config) {
  const base = await resolveQueryBase(config);
  const fields = {};
  fields[config.labelCol] = "dim";
  fields[config.valueCol] = "dim";
  const body = { ...base, fields, sample: 500, commit: false, mode: "memory" };
  const res = await api.runQuery(body);
  const labelIdx = res.columns.indexOf(config.labelCol);
  const valueIdx = res.columns.indexOf(config.valueCol);
  // Etiketler metne, değerler sayıya çevrilir. Sayıya çevrilemeyen değerler (metin, boş) 0 olur; bu yüzden değer kolonu beklenen sayısal tipte olmalıdır.
  let labels = res.rows.map((r) => String(r[labelIdx]));
  let values = res.rows.map((r) => Number(r[valueIdx]) || 0);

  // Toplama adımı: önce aynı etiketteki değerler gruplanır (Map), sonra her grup için seçilen fonksiyon uygulanır. agg 'none' ise gruplama yapılmaz ve satırlar olduğu gibi kullanılır.
  if (config.agg && config.agg !== "none") {
    const grouped = new Map();
    labels.forEach((l, i) => {
      const cur = grouped.get(l) || [];
      cur.push(values[i]);
      grouped.set(l, cur);
    });
    labels = Array.from(grouped.keys());
    values = labels.map((l) => {
      const vals = grouped.get(l);
      if (config.agg === "sum") return vals.reduce((a, b) => a + b, 0);
      if (config.agg === "avg") return vals.reduce((a, b) => a + b, 0) / vals.length;
      if (config.agg === "count") return vals.length;
      if (config.agg === "max") return Math.max(...vals);
      if (config.agg === "min") return Math.min(...vals);
      return vals.reduce((a, b) => a + b, 0);
    });
  }
  return { labels, values, rawRows: res.rows, rawCols: res.columns };
}

/**
 * Çok serili widget için değer kolonlarının listesini döndürür. Önce valueCols (birden çok), yoksa tek valueCol kullanılır; ikisi de yoksa boş dizi döner.
 */
function getValueCols(config) {
  if (config.valueCols && config.valueCols.length) return config.valueCols;
  if (config.valueCol) return [config.valueCol];
  return [];
}

/**
 * Çok seriye sahip grafik (çizgi, alan, sütun, bar, dağılım) verisini çeker. Her değer kolonu ayrı bir seri olur; agg seçiliyse her seri, etiket başına toplanır.
 * Dönüş: { labels, seriesValues (her seri için bir dizi), seriesNames, rawRows, rawCols }.
 * DİKKAT: Burada da sunucu en fazla 500 satır döner.
 */
async function fetchMultiSeriesData(config) {
  const base = await resolveQueryBase(config);
  const valueCols = getValueCols(config);
  const fields = {};
  fields[config.labelCol] = "dim";
  for (const vc of valueCols) fields[vc] = "dim";
  const body = { ...base, fields, sample: 500, commit: false, mode: "memory" };
  const res = await api.runQuery(body);

  const labelIdx = res.columns.indexOf(config.labelCol);
  const valueIdxs = valueCols.map((vc) => res.columns.indexOf(vc));
  let labels = res.rows.map((r) => String(r[labelIdx]));
  let seriesValues = valueIdxs.map((idx) => res.rows.map((r) => Number(r[idx]) || 0));

  if (config.agg && config.agg !== "none") {
    const uniqueLabels = Array.from(new Set(labels));
    // Bir etiketin tüm değerlerini seçilen toplama fonksiyonuyla birleştiren yardımcı. Aynı kurallar fetchWidgetData içindeki toplamayla aynıdır.
    const aggregate = (vals) => {
      if (config.agg === "sum") return vals.reduce((a, b) => a + b, 0);
      if (config.agg === "avg") return vals.reduce((a, b) => a + b, 0) / vals.length;
      if (config.agg === "count") return vals.length;
      if (config.agg === "max") return Math.max(...vals);
      if (config.agg === "min") return Math.min(...vals);
      return vals.reduce((a, b) => a + b, 0);
    };
    const newSeriesValues = seriesValues.map((vals) => {
      return uniqueLabels.map((ul) => {
        const matching = labels.map((l, i) => (l === ul ? vals[i] : null)).filter((v) => v !== null);
        return aggregate(matching);
      });
    });
    labels = uniqueLabels;
    seriesValues = newSeriesValues;
  }

  return { labels, seriesValues, seriesNames: valueCols, rawRows: res.rows, rawCols: res.columns };
}

/**
 * Tablo ve matris widget'ları için ham satırları çeker (en fazla 200 satır). Dönüş: { rawRows, rawCols }. Toplama yapılmaz; kolon listesi config.columns ile belirlenir.
 */
async function fetchTableData(config) {
  const base = await resolveQueryBase(config);
  const columns = config.columns && config.columns.length ? config.columns : null;
  const fields = {};
  if (columns) {
    for (const c of columns) fields[c] = "dim";
  }
  const body = { ...base, fields, sample: 200, commit: false, mode: "memory" };
  const res = await api.runQuery(body);
  return { rawRows: res.rows, rawCols: res.columns };
}

/**
 * Bir widget'a ait ECharts grafiğini varsa kapatır (dispose) ve kayıt listesinden siler. Bellek sızıntısını önlemek için her widget yeniden çizilmeden ve silinmeden önce çağrılır.
 */
function disposeWidgetChart(widgetId) {
  const existing = chartInstances.get(widgetId);
  if (existing) { existing.dispose(); chartInstances.delete(widgetId); }
}

/**
 * Bir widget'ı gövde kutusuna (bodyEl) çizer. Türüne göre farklı yollar izler:
 * - text: düzenlenebilir metin kutusu (sunucu sorgusu yok).
 * - veri bağlı değilse 'bağlayın' uyarısı.
 * - table/matrix: ham veri tablosu (ilk 30 satır).
 * - kpi: tek bir toplam değer (sayı).
 * - grafikler: ECharts ile çizim (ECharts yüklenemezse uyarı).
 * Veri hatası olursa kutuya hata mesajı yazılır; widget sayfayı bozmaz.
 * Parametreler: obj = widget nesnesi; bodyEl = çizim kutusu öğesi.
 */
async function renderWidgetChart(obj, bodyEl) {
  const config = getWidgetConfig(obj);

  // Metin widget'ı sorgu yapmaz: içeriği ve stilini (punto, renk, hizalama, kalınlık) doğrudan ayardan okur. İçerik text node olarak eklenir (HTML yorumlanmaz).
  if (obj.type === "text") {
    disposeWidgetChart(obj.id);
    bodyEl.innerHTML = "";
    const content = config?.text || "";
    const fontSize = config?.textFontSize || 13;
    const textColor = config?.textColor || "var(--text)";
    const align = config?.textAlign || "left";
    const bold = config?.textBold ? "700" : "400";
    const textEl = el("div", {
      style: `width:100%;height:100%;overflow:auto;text-align:${align};color:${textColor};` +
             `font-size:${fontSize}px;font-weight:${bold};white-space:pre-wrap`,
    }, content || "(metin ekleyin — sağdaki panelden)");
    bodyEl.appendChild(textEl);
    return;
  }

  if (!config || (!config.conn_id && !config.datasetId)) {
    disposeWidgetChart(obj.id);
    bodyEl.innerHTML = "";
    bodyEl.appendChild(el("span", { class: "muted small" }, "Veri bağlı değil — sağdaki panelden bağlayın"));
    return;
  }

  if (obj.type === "table" || obj.type === "matrix") {
    try {
      const data = await fetchTableData(config);
      widgetDataCache.set(obj.id, { kind: "table", rawRows: data.rawRows, rawCols: data.rawCols });
      disposeWidgetChart(obj.id);
      bodyEl.innerHTML = "";
      const table = el("table", { style: "font-size:10px" });
      table.appendChild(el("thead", {}, el("tr", {}, data.rawCols.map((c) => el("th", {}, c)))));
      const tbody = el("tbody");
      for (const row of data.rawRows.slice(0, 30)) {
        tbody.appendChild(el("tr", {}, row.map((v) => el("td", {}, v === null ? "" : String(v)))));
      }
      table.appendChild(tbody);
      bodyEl.style.overflow = "auto";
      bodyEl.style.display = "block";
      bodyEl.appendChild(table);
    } catch (e) {
      disposeWidgetChart(obj.id);
      bodyEl.innerHTML = "";
      bodyEl.appendChild(el("span", { class: "muted small", style: "color:var(--danger)" }, "Veri çekilemedi: " + (e.message || "")));
    }
    return;
  }

  try {
    // KPI: tüm değerlerin toplamı büyük bir sayı olarak gösterilir (agg 'count' ise etiket sayısı). Yazı boyutu widget yüksekliğine göre büyür (en fazla 28 px).
    if (obj.type === "kpi") {
      const data = await fetchWidgetData(config);
      disposeWidgetChart(obj.id);
      const total = config.agg === "count" ? data.values.length : data.values.reduce((a, b) => a + b, 0);
      widgetDataCache.set(obj.id, { kind: "kpi", value: total, label: config.valueCol });
      bodyEl.innerHTML = "";
      bodyEl.appendChild(el("div", { style: "text-align:center" }, [
        el("div", { style: `font-size:${Math.min(28, 14 + obj.h / 6)}px;font-weight:700;color:${obj.color || "#378ADD"}` }, formatNumber(total)),
        el("div", { class: "muted small" }, config.valueCol),
      ]));
      return;
    }

    // Çok seri destekleyen türlerde (line/area/column/bar/scatter) çoklu veri çekilir; diğer türler tek seri olarak çekilir.
    const isMultiSeries = MULTI_SERIES_TYPES.has(obj.type);
    const data = isMultiSeries ? await fetchMultiSeriesData(config) : await fetchWidgetData(config);

    if (CHART_TYPES.has(obj.type)) {
      if (isMultiSeries) {
        const valueCols = data.seriesNames;
        widgetDataCache.set(obj.id, {
          kind: "chart", rawCols: [config.labelCol, ...valueCols],
          rawRows: data.labels.map((l, i) => [l, ...data.seriesValues.map((sv) => sv[i])]),
        });
      } else {
        widgetDataCache.set(obj.id, {
          kind: "chart", rawCols: [config.labelCol, config.valueCol],
          rawRows: data.labels.map((l, i) => [l, data.values[i]]),
        });
      }

      if (typeof window.echarts === "undefined") {
        disposeWidgetChart(obj.id);
        bodyEl.innerHTML = "";
        bodyEl.appendChild(el("span", { class: "muted small" }, "ECharts yüklenemedi (CDN engellenmiş olabilir)"));
        return;
      }

      // Harita için önce dünya haritası verisinin yüklenmesi beklenir. Yüklenemezse grafik çizilmez, hata mesajı gösterilir.
      if (obj.type === "map") {
        try { await ensureWorldMapRegistered(); }
        catch (e) {
          disposeWidgetChart(obj.id);
          bodyEl.innerHTML = "";
          bodyEl.appendChild(el("span", { class: "muted small", style: "color:var(--danger)" }, "Dünya haritası verisi indirilemedi"));
          return;
        }
      }

      let chart = chartInstances.get(obj.id);
      bodyEl.innerHTML = "";
      bodyEl.style.display = "block";
      bodyEl.style.padding = "0";
      const chartDiv = el("div", { style: "width:100%;height:100%" });
      bodyEl.appendChild(chartDiv);

      if (chart) chart.dispose();
      // ECharts örneği 'dark' temasıyla ve canvas renderer ile açılır (SVG yerine canvas: çok veri için daha hızlı). Grafik kutusunun içine tam boyutlu bir div yerleştirilir.
      chart = window.echarts.init(chartDiv, "dark", { renderer: "canvas" });
      chartInstances.set(obj.id, chart);

      // Seri renkleri bu sabit paletten sırayla alınır. Widget'ın kendi rengi (obj.color) bu grafiklerde seri renginde kullanılmaz; yalnız haritanın renk skalasında kullanılır.
      const palette = ["#378ADD", "#58c9a0", "#e5b93d", "#e5484d", "#9b6bd1", "#38b6d9"];
      const baseColor = obj.color || "#378ADD";
      const hasMultipleSeries = isMultiSeries && data.seriesValues.length > 1;

      let option;
      // Çizgi, alan ve sütun grafikleri aynı eksen yapısını kullanır. 'column' ECharts'ta 'bar' seri tipine, çizgi ve alan 'line' tipine çevrilir (alan için opaklık ayarlanır).
      if (obj.type === "line" || obj.type === "area" || obj.type === "column") {
        option = {
          backgroundColor: "transparent",
          grid: { left: 36, right: 12, top: hasMultipleSeries ? 28 : 16, bottom: 28 },
          tooltip: { trigger: "axis" },
          legend: hasMultipleSeries ? { show: true, top: 0, textStyle: { color: "#8b93a3", fontSize: 9 } } : undefined,
          xAxis: { type: "category", data: data.labels, axisLabel: { color: "#8b93a3", fontSize: 9 }, axisLine: { lineStyle: { color: "#2a2f3a" } } },
          yAxis: { type: "value", axisLabel: { color: "#8b93a3", fontSize: 9 }, splitLine: { lineStyle: { color: "#2a2f3a" } } },
          series: data.seriesValues.map((vals, i) => ({
            type: obj.type === "column" ? "bar" : "line",
            name: data.seriesNames[i],
            data: vals,
            itemStyle: { color: palette[i % palette.length] },
            smooth: obj.type !== "column",
            areaStyle: obj.type === "area" ? { opacity: 0.25 } : (obj.type === "line" ? { opacity: 0.08 } : undefined),
          })),
        };
      } else if (obj.type === "bar") {
        option = {
          backgroundColor: "transparent",
          grid: { left: 70, right: 20, top: hasMultipleSeries ? 28 : 16, bottom: 20 },
          tooltip: { trigger: "axis" },
          legend: hasMultipleSeries ? { show: true, top: 0, textStyle: { color: "#8b93a3", fontSize: 9 } } : undefined,
          xAxis: { type: "value", axisLabel: { color: "#8b93a3", fontSize: 9 }, splitLine: { lineStyle: { color: "#2a2f3a" } } },
          yAxis: { type: "category", data: data.labels, axisLabel: { color: "#8b93a3", fontSize: 9 }, axisLine: { lineStyle: { color: "#2a2f3a" } } },
          series: data.seriesValues.map((vals, i) => ({
            type: "bar", name: data.seriesNames[i], data: vals, itemStyle: { color: palette[i % palette.length] },
          })),
        };
      } else if (obj.type === "scatter") {
        option = {
          backgroundColor: "transparent",
          grid: { left: 40, right: 16, top: hasMultipleSeries ? 28 : 16, bottom: 28 },
          tooltip: { trigger: "item" },
          legend: hasMultipleSeries ? { show: true, top: 0, textStyle: { color: "#8b93a3", fontSize: 9 } } : undefined,
          xAxis: { type: "category", data: data.labels, axisLabel: { color: "#8b93a3", fontSize: 9 }, axisLine: { lineStyle: { color: "#2a2f3a" } } },
          yAxis: { type: "value", axisLabel: { color: "#8b93a3", fontSize: 9 }, splitLine: { lineStyle: { color: "#2a2f3a" } } },
          series: data.seriesValues.map((vals, i) => ({
            type: "scatter", name: data.seriesNames[i], symbolSize: 10, data: vals, itemStyle: { color: palette[i % palette.length] },
          })),
        };
      } else if (obj.type === "pie" || obj.type === "donut") {
        option = {
          backgroundColor: "transparent",
          tooltip: { trigger: "item" },
          legend: { show: true, textStyle: { color: "#8b93a3", fontSize: 9 }, bottom: 0 },
          series: [{
            type: "pie",
            radius: obj.type === "donut" ? ["40%", "70%"] : "70%",
            data: data.labels.map((l, i) => ({ name: l, value: data.values[i], itemStyle: { color: palette[i % palette.length] } })),
            label: { color: "#e6e8ec", fontSize: 9 },
          }],
        };
      } else if (obj.type === "map") {
        // Harita renk skalası 0 ile en büyük değer arasında çalışır. Math.max(1, ...) ile en az 1 alınır; tüm değerler 0 olsa bile skala bozulmaz.
        const maxVal = Math.max(1, ...data.values);
        option = {
          backgroundColor: "transparent",
          tooltip: { trigger: "item" },
          visualMap: {
            min: 0, max: maxVal, calculable: true, orient: "horizontal", left: "center", bottom: 0,
            textStyle: { color: "#8b93a3", fontSize: 9 },
            inRange: { color: ["#1e222b", baseColor] },
          },
          series: [{
            type: "map", map: "world",
            data: data.labels.map((l, i) => ({ name: l, value: data.values[i] })),
            emphasis: { label: { show: true } },
            itemStyle: { areaColor: "#1e222b", borderColor: "#2a2f3a" },
          }],
        };
      }

      chart.setOption(option);
      return;
    }
  } catch (e) {
    disposeWidgetChart(obj.id);
    bodyEl.innerHTML = "";
    bodyEl.appendChild(el("span", { class: "muted small", style: "color:var(--danger)" }, "Veri çekilemedi: " + (e.message || "")));
  }
}

/**
 * Sayıyı Türkçe biçimde yazar (binlik ayırıcı nokta, ondalık virgül). Tam sayıysa ondalık yazmaz; değilse en fazla 2 ondalık basamak gösterir.
 * Parametre n: sayı. Dönüş: metin.
 */
function formatNumber(n) {
  if (Number.isInteger(n)) return n.toLocaleString("tr-TR");
  return n.toLocaleString("tr-TR", { maximumFractionDigits: 2 });
}

/* ---- Export ---- */

/**
 * CSV hücresini güvenli hale getirir. Değer ; " veya satır sonu içeriyorsa tırnak içine alınır ve içindeki tırnaklar çift tırnak yapılır. null/undefined boş metin olur.
 * = + - @ (ve TAB/CR) ile başlayan metin değerler Excel'de formül olarak çalışabilir (CSV formül enjeksiyonu); bu yüzden metin değerlerin başına ' eklenir.
 */
function csvEscape(val) {
  if (val === null || val === undefined) return "";
  let s = String(val);
  // Metin değer formül olarak yorumlanmasın diye başına ' eklenir (sayılar olduğu gibi kalır)
  if (typeof val === "string" && /^[=+\-@\t\r]/.test(s)) s = "'" + s;
  if (/[",\n;]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
  return s;
}

/**
 * Kolon adları ve satırları noktalı virgüllü (;) CSV metnine çevirir. Türkçe ayarlı Excel genellikle virgül yerine noktalı virgül ayırıcısı bekler; bu yüzden ; seçildi.
 * Başta BOM (\uFEFF) eklenir ki Excel Türkçe karakterleri (ğ, ş, ı) doğru okusun. Satırlar \r\n ile ayrılır.
 * Parametreler: cols = başlık dizisi; rows = satır dizileri.
 */
function rowsToCsv(cols, rows) {
  const BOM = "\uFEFF";
  const lines = [cols.map(csvEscape).join(";")];
  for (const row of rows) lines.push(row.map(csvEscape).join(";"));
  return BOM + lines.join("\r\n");
}

/**
 * Verilen içeriği dosya olarak indirtir. Tarayıcıda geçici bir bağlantı (Blob URL) oluşturup gizli bir <a> öğesine tıklatır.
 * Parametreler: content = metin veya Blob; filename = dosya adı; mime = içerik türü (örn. text/csv).
 * Blob URL'i 1 saniye sonra iptal edilir; hemen iptal edilirse indirme bozulabilir.
 */
function triggerDownload(content, filename, mime) {
  const blob = content instanceof Blob ? content : new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * Dosya adında kullanılamayan karakterleri (boşluk, /, : gibi) alt çizgi yapar; Türkçe harfleri korur. En fazla 60 karakter. Boşsa 'widget' adı kullanılır.
 */
function safeFilename(s) {
  return (s || "widget").replace(/[^\w\-ğüşıöçĞÜŞİÖÇ]+/g, "_").slice(0, 60);
}

/**
 * Bir widget'ı dışa aktarır. Grafikse PNG resmi (ECharts'tan) indirilir. Grafik yoksa veya tablo/KPI ise önbellekteki veri CSV olarak indirilir.
 * Önce veri hiç çekilmemişse kullanıcıya 'önce veri bağlayın' uyarısı gösterilir.
 */
function exportWidget(obj) {
  const cached = widgetDataCache.get(obj.id);
  const nameBase = safeFilename(obj.title || obj.type);

  if (CHART_TYPES.has(obj.type) && obj.type !== "kpi") {
    const chart = chartInstances.get(obj.id);
    if (chart && typeof chart.getDataURL === "function") {
      const url = chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#171a21" });
      const a = document.createElement("a");
      a.href = url;
      a.download = `${nameBase}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      return;
    }
  }

  if (!cached) {
    toast("Dışa aktarılacak veri yok — önce widget'a veri bağlayın", "error");
    return;
  }

  if (cached.kind === "kpi") {
    triggerDownload(rowsToCsv([cached.label || "değer"], [[cached.value]]), `${nameBase}.csv`, "text/csv;charset=utf-8");
    return;
  }

  triggerDownload(rowsToCsv(cached.rawCols, cached.rawRows), `${nameBase}.csv`, "text/csv;charset=utf-8");
}

/* ---- Canvas render ---- */

/**
 * Dashboard tuvalini (sayfa) baştan çizer: boyutunu mm'den pikseli çevirerek ayarlar, arka plandaki kılavuz ızgarayı kurar ve her widget için bir düğüm üretir.
 * Parametre canvasPage: tuval öğesi (#dash-canvas-page).
 */
function renderCanvasPage(canvasPage) {
  const dash = state.currentDashboard;
  canvasPage.innerHTML = "";
  canvasPage.style.width = mmToPx(dash.page_w_mm) + "px";
  canvasPage.style.height = mmToPx(dash.page_h_mm) + "px";
  canvasPage.style.backgroundSize = `${mmToPx(10)}px ${mmToPx(10)}px`;

  for (const obj of dash.objects) {
    canvasPage.appendChild(renderWidgetNode(obj, canvasPage));
  }
}

// Tek widget'ı yeniden çizer; pushHistory() burada çağrılır.
function rerenderWidget(objId) {
  const canvasPage = qs("#dash-canvas-page");
  const dash = state.currentDashboard;
  const obj = dash && dash.objects.find((o) => o.id === objId);
  const oldNode = canvasPage && canvasPage.querySelector(`[data-widget-id="${objId}"]`);
  if (!canvasPage || !obj || !oldNode) {
    if (canvasPage) renderCanvasPage(canvasPage);
    return;
  }
  const newNode = renderWidgetNode(obj, canvasPage);
  oldNode.replaceWith(newNode);
  pushHistory();
}

/**
 * Tek bir widget'ın ekrandaki kutusunu (başlık, gövde, boyutlandırma tutamağı) üretir ve olayları bağlar:
 * - Sil (✕): widget'ı listeden çıkarır.
 * - Dışa aktar (⬇): exportWidget çağırır.
 * - Tıklama + sürükleme: konumu değiştirir.
 * - Köşe tutamağı: boyutu değiştirir.
 * Sürükleme için mousemove/mouseup dinleyicileri geçici olarak document'e eklenir ve bırakılınca kaldırılır.
 * Parametreler: obj = widget nesnesi; canvasPage = tuval öğesi. Dönüş: düğüm (henüz sayfaya eklenmemiş).
 */
function renderWidgetNode(obj, canvasPage) {
  const node = el("div", {
    class: `dash-widget ${state.selectedWidgetId === obj.id ? "selected" : ""}`,
    "data-widget-id": obj.id,
  });
  node.style.left = mmToPx(obj.x) + "px";
  node.style.top = mmToPx(obj.y) + "px";
  node.style.width = mmToPx(obj.w) + "px";
  node.style.height = mmToPx(obj.h) + "px";
  node.style.borderTopColor = obj.color || "#378ADD";
  node.style.borderTopWidth = "3px";

  const delBtn = el("span", { class: "del-btn" }, "✕");
  delBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    disposeWidgetChart(obj.id);
    widgetDataCache.delete(obj.id);
    const dash = state.currentDashboard;
    dash.objects = dash.objects.filter((o) => o.id !== obj.id);
    if (state.selectedWidgetId === obj.id) state.selectedWidgetId = null;
    renderCanvasPage(canvasPage);
    renderPropsPanel(qs("#dash-props-panel"));
    pushHistory();
  });

  const titleCfg = getWidgetConfig(obj) || {};
  const titleSpan = el("span", {
    style: `font-size:${titleCfg.titleFontSize || 11}px;color:${titleCfg.titleColor || "var(--text)"}`,
  }, `${obj.title || obj.type}`);

  const headChildren = [titleSpan];
  if (obj.type !== "text") {
    const exportBtn = el("span", { class: "export-btn", title: "Dışa aktar" }, "⬇");
    exportBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      exportWidget(obj);
    });
    headChildren.push(exportBtn);
  }
  headChildren.push(delBtn);

  const head = el("div", { class: "dash-widget-head" }, headChildren);
  const bodyEl = el("div", { class: "dash-widget-body" });
  renderWidgetChart(obj, bodyEl);
  const resizeHandle = el("div", { class: "dash-widget-resize" });

  node.appendChild(head);
  node.appendChild(bodyEl);
  node.appendChild(resizeHandle);

  node.addEventListener("mousedown", (e) => {
    if (e.target === resizeHandle) return;
    state.selectedWidgetId = obj.id;
    renderPropsPanel(qs("#dash-props-panel"));
    qsa(".dash-widget", canvasPage).forEach((n) => n.classList.remove("selected"));
    node.classList.add("selected");

    const startX = e.clientX, startY = e.clientY;
    const origX = obj.x, origY = obj.y;
    let moved = false;

    // Sürükleme sırasında fare hareketini milimetreye çevirip widget konumunu günceller; negatif konuma gitmez (0'da durur). Yalnız düğümün stili değişir, tam yeniden çizim yapılmaz (akıcılık için).
    function onMove(ev) {
      moved = true;
      const dxMm = pxToMm(ev.clientX - startX);
      const dyMm = pxToMm(ev.clientY - startY);
      obj.x = Math.max(0, origX + dxMm);
      obj.y = Math.max(0, origY + dyMm);
      node.style.left = mmToPx(obj.x) + "px";
      node.style.top = mmToPx(obj.y) + "px";
    }
    // Fare bırakılınca dinleyicileri kaldırır. Gerçekten taşındıysa (moved) geçmişe bir kayıt ekler; sadece tıklama olduysa geçmişe yazılmaz.
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      if (moved) pushHistory();
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    e.preventDefault();
  });

  resizeHandle.addEventListener("mousedown", (e) => {
    e.stopPropagation();
    const startX = e.clientX, startY = e.clientY;
    const origW = obj.w, origH = obj.h;
    let resized = false;

    // Boyutlandırma sırasında genişlik ve yüksekliği milimetre olarak günceller; en az 15 mm olur. Grafik varsa yeni boyuta uyması için resize çağrılır.
    function onMove(ev) {
      resized = true;
      const dwMm = pxToMm(ev.clientX - startX);
      const dhMm = pxToMm(ev.clientY - startY);
      obj.w = Math.max(15, origW + dwMm);
      obj.h = Math.max(15, origH + dhMm);
      node.style.width = mmToPx(obj.w) + "px";
      node.style.height = mmToPx(obj.h) + "px";
      const chart = chartInstances.get(obj.id);
      if (chart) chart.resize();
    }
    // Boyutlandırma bitince dinleyicileri kaldırır; KPI kartı yeni boyuta göre yeniden çizilir (yazı boyutu yüksekliğe bağlı). Değişiklik varsa geçmişe kaydedilir.
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      if (obj.type === "kpi") renderWidgetChart(obj, bodyEl);
      if (resized) pushHistory();
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    e.preventDefault();
  });

  return node;
}

/* ---- Props panel + data binding ---- */

/**
 * Sağ taraftaki özellik panelini seçili widget'a göre çizer: başlık, renk, başlık yazı boyutu/rengi, konum ve boyut (mm) alanları ve veri bağlama bölümü.
 * Hiçbir widget seçili değilse 'Bir widget seçin' yazar. Her alan değiştiğinde ilgili widget rerenderWidget ile yenilenir.
 * Parametre panel: panel öğesi (#dash-props-panel).
 */
function renderPropsPanel(panel) {
  if (!panel) return;
  panel.innerHTML = "";
  panel.appendChild(el("label", {}, "Özellikler"));

  const dash = state.currentDashboard;
  const obj = dash.objects.find((o) => o.id === state.selectedWidgetId);
  if (!obj) {
    panel.appendChild(el("p", { class: "muted small" }, "Bir widget seçin."));
    return;
  }

  const titleInput = el("input", { value: obj.title || "" });
  titleInput.addEventListener("change", () => {
    obj.title = titleInput.value;
    rerenderWidget(obj.id);
  });

  const colorInput = el("input", { type: "color", value: obj.color || "#378ADD" });
  colorInput.addEventListener("change", () => {
    obj.color = colorInput.value;
    rerenderWidget(obj.id);
  });

  const xInput = el("input", { type: "number", value: Math.round(obj.x) });
  const yInput = el("input", { type: "number", value: Math.round(obj.y) });
  const wInput = el("input", { type: "number", value: Math.round(obj.w) });
  const hInput = el("input", { type: "number", value: Math.round(obj.h) });
  [[xInput, "x"], [yInput, "y"], [wInput, "w"], [hInput, "h"]].forEach(([input, key]) => {
    input.addEventListener("change", () => {
      obj[key] = parseFloat(input.value) || 0;
      rerenderWidget(obj.id);
    });
  });

  panel.appendChild(el("div", {}, [el("label", { class: "small" }, "Başlık"), titleInput]));
  panel.appendChild(el("div", {}, [el("label", { class: "small" }, "Renk (grafik/vurgu rengi)"), colorInput]));

  const styleCfg = getWidgetConfig(obj) || {};
  const titleFontSel = el("select", {}, [
    { v: 10, l: "Küçük" }, { v: 12, l: "Orta" }, { v: 16, l: "Büyük" },
  ].map(({ v, l }) => el("option", { value: v, selected: v === (styleCfg.titleFontSize || 11) ? "selected" : null }, l)));
  const titleColorInput = el("input", { type: "color", value: styleCfg.titleColor || "#e6e8ec" });

  /**
   * Widget'ın stil ayarlarından (başlık punto/rengi gibi) bir kısmını günceller. patch: değiştirilecek alanlar; mevcut ayarların geri kalanı korunur. Sonra widget yeniden çizilir.
   */
  function updateStyleConfig(patch) {
    const current = getWidgetConfig(obj) || {};
    setWidgetConfig(obj, { ...current, ...patch });
    rerenderWidget(obj.id);
  }
  titleFontSel.addEventListener("change", () => updateStyleConfig({ titleFontSize: parseInt(titleFontSel.value, 10) }));
  titleColorInput.addEventListener("change", () => updateStyleConfig({ titleColor: titleColorInput.value }));

  panel.appendChild(el("div", { class: "grid-2" }, [
    el("div", {}, [el("label", { class: "small" }, "Başlık Punto"), titleFontSel]),
    el("div", {}, [el("label", { class: "small" }, "Başlık Rengi"), titleColorInput]),
  ]));
  panel.appendChild(el("div", { class: "grid-2" }, [
    el("div", {}, [el("label", { class: "small" }, "X (mm)"), xInput]),
    el("div", {}, [el("label", { class: "small" }, "Y (mm)"), yInput]),
  ]));
  panel.appendChild(el("div", { class: "grid-2" }, [
    el("div", {}, [el("label", { class: "small" }, "Genişlik (mm)"), wInput]),
    el("div", {}, [el("label", { class: "small" }, "Yükseklik (mm)"), hInput]),
  ]));

  panel.appendChild(el("hr", { style: "border-color:var(--border);margin:14px 0" }));
  panel.appendChild(el("label", {}, "Veri Bağlama"));
  renderDataBindingSection(panel, obj);
}

/**
 * Widget türüne göre 'Veri Bağlama' bölümünü seçer: metin widget'ı için metin düzenleyici, tablo/matris için tablo bağlama, diğerleri için grafik bağlama.
 */
function renderDataBindingSection(panel, obj) {
  if (obj.type === "text") {
    const config = getWidgetConfig(obj) || {};
    const textArea = el("textarea", { rows: "4" }, config.text || "");
    const fontSel = el("select", {}, [10, 13, 16, 20, 26].map(
      (n) => el("option", { value: n, selected: n === (config.textFontSize || 13) ? "selected" : null }, `${n}px`)
    ));
    const colorInput = el("input", { type: "color", value: config.textColor && config.textColor !== "var(--text)" ? config.textColor : "#e6e8ec" });
    const alignSel = el("select", {}, [
      { v: "left", l: "Sol" }, { v: "center", l: "Orta" }, { v: "right", l: "Sağ" },
    ].map(({ v, l }) => el("option", { value: v, selected: v === (config.textAlign || "left") ? "selected" : null }, l)));
    const boldCheck = el("input", { type: "checkbox" });
    boldCheck.checked = !!config.textBold;

    /**
     * Metin widget'ının tüm ayarlarını (metin, punto, renk, hizalama, kalın) toplayıp widget'a yazar ve yeniden çizer. Her alan değiştiğinde çağrılır.
     */
    function persist() {
      const current = getWidgetConfig(obj) || {};
      setWidgetConfig(obj, {
        ...current,
        text: textArea.value, textFontSize: parseInt(fontSel.value, 10),
        textColor: colorInput.value, textAlign: alignSel.value, textBold: boldCheck.checked,
      });
      rerenderWidget(obj.id);
    }
    [textArea, fontSel, colorInput, alignSel, boldCheck].forEach((el2) => el2.addEventListener("change", persist));

    panel.appendChild(el("div", {}, [el("label", { class: "small" }, "Metin"), textArea]));
    panel.appendChild(el("div", { class: "grid-2" }, [
      el("div", {}, [el("label", { class: "small" }, "Punto"), fontSel]),
      el("div", {}, [el("label", { class: "small" }, "Renk"), colorInput]),
    ]));
    panel.appendChild(el("div", { class: "grid-2" }, [
      el("div", {}, [el("label", { class: "small" }, "Hizalama"), alignSel]),
      el("div", {}, [el("label", { class: "small" }, "Kalın"), boldCheck]),
    ]));
    return;
  }

  if (obj.type === "table" || obj.type === "matrix") {
    renderTableDataBinding(panel, obj);
    return;
  }

  renderChartDataBinding(panel, obj);
}

/**
 * Tablo/matris widget'ının 'Veri Bağlama' bölümünü kurar. İki kaynak modu vardır:
 * - Manuel Bağlantı: bağlantı > tablo > kolon seçilir.
 * - Kayıtlı Sorgu: önceden kaydedilmiş bir veri seti kullanılır.
 * Gösterilecek kolonlar tıklamayla seçilir; hiçbiri seçilmezse tüm kolonlar gösterilir.
 * Parametre panel: özellik paneli; obj: widget nesnesi.
 */
function renderTableDataBinding(panel, obj) {
  const config = getWidgetConfig(obj) || {};
  const selectedCols = new Set(config.columns || []);
  let sourceMode = config.datasetId ? "dataset" : "manual";

  const sourceSel = el("select", {}, [
    el("option", { value: "manual", selected: sourceMode === "manual" ? "selected" : null }, "Manuel Bağlantı"),
    el("option", { value: "dataset", selected: sourceMode === "dataset" ? "selected" : null }, "Kayıtlı Sorgu Kullan"),
  ]);
  sourceSel.addEventListener("change", () => {
    sourceMode = sourceSel.value;
    bodyBox.innerHTML = "";
    if (sourceMode === "manual") renderManualBinding(); else renderDatasetBinding();
  });
  panel.appendChild(el("div", {}, [el("label", { class: "small" }, "Veri Kaynağı"), sourceSel]));

  const bodyBox = el("div");
  panel.appendChild(bodyBox);
  const columnsBox = el("div", { class: "pill-list", style: "margin-top:8px" });

  /**
   * Tablo bağlama ayarlarını (seçili kolonlar ve verilen ek alanlar, örn. conn_id/table) widget'a yazar ve widget'ı yeniden çizer.
   * Parametre extra: bu seferde değişen ek alanlar (kaynak değişince çağrılır).
   */
  function persistAndRerender(extra) {
    const current = getWidgetConfig(obj) || {};
    setWidgetConfig(obj, { ...current, columns: Array.from(selectedCols), ...extra });
    rerenderWidget(obj.id);
  }

  /**
   * Kolon seçim çiplerini çizer. Çipe tıklayınca kolon seçilir/çıkarılır ve hemen kaydedilip yeniden çizilir.
   * Parametreler: availableCols = kolon listesi (manuelde {name} nesneleri, veri setinde düz metin dizisi); isDatasetCols = veri seti mi kaynağı olduğunu belirten bayrak.
   */
  function renderColumnCheckboxes(availableCols, isDatasetCols) {
    columnsBox.innerHTML = "";
    const names = isDatasetCols ? availableCols : availableCols.map((c) => c.name);
    for (const name of names) {
      const included = selectedCols.has(name);
      const chip = el("span", { class: `field-chip ${included ? "included" : ""}` }, name);
      chip.addEventListener("click", () => {
        if (selectedCols.has(name)) selectedCols.delete(name);
        else selectedCols.add(name);
        renderColumnCheckboxes(availableCols, isDatasetCols);
        persistAndRerender(isDatasetCols ? { datasetId: config._lastDatasetId } : { conn_id: config._lastConnId, table: config._lastTable });
      });
      columnsBox.appendChild(chip);
    }
    if (!names.length) columnsBox.appendChild(el("p", { class: "muted small" }, "Önce kaynak seçin."));
  }

  /**
   * Tablo widget'ı için 'Manuel Bağlantı' formunu çizer: bağlantı ve tablo seçim kutuları, kolon çipleri ve 'Bağla ve Çiz' düğmesi. Açılışta daha önce seçilmiş bir bağlantı varsa tabloları otomatik yükler.
   */
  function renderManualBinding() {
    const connSel = el("select", {}, [
      el("option", { value: "" }, "Bağlantı seçin…"),
      ...state.connections.map((c) => el("option", {
        value: c.conn_id, selected: c.conn_id === config.conn_id ? "selected" : null,
      }, `${c.conn_id} (${c.database})`)),
    ]);
    const tableSel = el("select", {}, [el("option", { value: "" }, "Önce bağlantı seçin")]);

    /**
     * Seçilen bağlantının tablolarını tablo kutusuna doldurur. selectedTable verilirse o tablo seçili gelir ve kolonları da yüklenir.
     * Parametreler: connId = bağlantı kimliği; selectedTable = önceden seçili tablo (yoksa null).
     */
    async function loadTablesInto(connId, selectedTable) {
      tableSel.innerHTML = "";
      tableSel.appendChild(el("option", { value: "" }, "Yükleniyor…"));
      try {
        const res = await api.listTables(connId);
        tableSel.innerHTML = "";
        tableSel.appendChild(el("option", { value: "" }, "Tablo seçin…"));
        for (const t of res.tables || []) {
          tableSel.appendChild(el("option", { value: t, selected: t === selectedTable ? "selected" : null }, t));
        }
        if (selectedTable) await loadColumnsInto(connId, selectedTable);
      } catch (e) { handleApiError(e, "Tablolar alınamadı"); }
    }

    /**
     * Seçilen tablonun kolonlarını çeker, son bağlantı/tablo bilgisini config'e yazar ve kolon çiplerini çizer. Hata olursa kullanıcıya bildirilir.
     */
    async function loadColumnsInto(connId, table) {
      try {
        const res = await api.listColumns(connId, table);
        config._lastConnId = connId; config._lastTable = table;
        renderColumnCheckboxes(res.columns || [], false);
      } catch (e) { handleApiError(e, "Kolonlar alınamadı"); }
    }

    connSel.addEventListener("change", () => { selectedCols.clear(); loadTablesInto(connSel.value, null); });
    tableSel.addEventListener("change", () => { selectedCols.clear(); loadColumnsInto(connSel.value, tableSel.value); });

    bodyBox.appendChild(el("div", {}, [el("label", { class: "small" }, "Bağlantı"), connSel]));
    bodyBox.appendChild(el("div", {}, [el("label", { class: "small" }, "Tablo"), tableSel]));
    bodyBox.appendChild(el("div", {}, [
      el("label", { class: "small" }, "Kolonlar (tıklayarak ekle/çıkar — hiçbiri seçilmezse tüm kolonlar gösterilir)"),
      columnsBox,
    ]));

    const applyBtn = el("button", { class: "btn btn-primary btn-sm", style: "margin-top:8px" }, "Bağla ve Çiz");
    applyBtn.addEventListener("click", () => persistAndRerender({ conn_id: connSel.value, table: tableSel.value, datasetId: null }));
    bodyBox.appendChild(applyBtn);

    if (config.conn_id && !config.datasetId) loadTablesInto(config.conn_id, config.table);
  }

  /**
   * Tablo widget'ı için 'Kayıtlı Sorgu' seçimini çizer: veri setleri listesini sunucudan çeker, seçilince kolonlarını gösterir. Veri seti değişince (olay) kolon seçimi sıfırlanır.
   */
  function renderDatasetBinding() {
    const dsSel = el("select", {}, [el("option", { value: "" }, "Yükleniyor…")]);
    bodyBox.appendChild(el("div", {}, [el("label", { class: "small" }, "Kayıtlı Sorgu"), dsSel]));
    bodyBox.appendChild(el("div", {}, [
      el("label", { class: "small" }, "Kolonlar (tıklayarak ekle/çıkar — hiçbiri seçilmezse tüm kolonlar gösterilir)"),
      columnsBox,
    ]));
    const applyBtn = el("button", { class: "btn btn-primary btn-sm", style: "margin-top:8px" }, "Bağla ve Çiz");
    applyBtn.addEventListener("click", () => persistAndRerender({ datasetId: dsSel.value, conn_id: null, table: null }));
    bodyBox.appendChild(applyBtn);

    api.listDatasets().then((datasets) => {
      dsSel.innerHTML = "";
      dsSel.appendChild(el("option", { value: "" }, "Dataset seçin…"));
      for (const d of datasets) {
        dsSel.appendChild(el("option", { value: d.dataset_id, selected: d.dataset_id === config.datasetId ? "selected" : null }, d.name));
      }
      dsSel.addEventListener("change", async () => {
        selectedCols.clear();
        if (!dsSel.value) return;
        try {
          const cols = await fetchDatasetColumns(dsSel.value);
          config._lastDatasetId = dsSel.value;
          renderColumnCheckboxes(cols, true);
        } catch (e) { handleApiError(e, "Dataset kolonları alınamadı"); }
      });
      if (config.datasetId) dsSel.dispatchEvent(new Event("change"));
    }).catch((e) => handleApiError(e, "Dataset listesi alınamadı"));
  }

  if (sourceMode === "manual") renderManualBinding(); else renderDatasetBinding();
}

/**
 * Grafik widget'ları için 'Veri Bağlama' bölümünü kurar: kaynak (manuel veya veri seti), etiket (X/Y ekseni) kolonu, değer kolonu (çok seriyse birden çok) ve toplama (agg) seçimi.
 * Çok seri türlerde (MULTI_SERIES_TYPES) değer kolonları çip olarak seçilir; diğer türlerde tek bir değer kutusu kullanılır.
 * Harita için ülke adlarının İngilizce olması gerektiği not olarak yazılır.
 */
function renderChartDataBinding(panel, obj) {
  const config = getWidgetConfig(obj) || {};
  let sourceMode = config.datasetId ? "dataset" : "manual";

  if (obj.type === "map") {
    panel.appendChild(el("p", { class: "muted small" },
      "Not: Etiket kolonundaki değerler ülke adlarıyla (İngilizce, örn. 'Turkey') eşleşmeli."
    ));
  }

  const sourceSel = el("select", {}, [
    el("option", { value: "manual", selected: sourceMode === "manual" ? "selected" : null }, "Manuel Bağlantı"),
    el("option", { value: "dataset", selected: sourceMode === "dataset" ? "selected" : null }, "Kayıtlı Sorgu Kullan"),
  ]);
  sourceSel.addEventListener("change", () => {
    sourceMode = sourceSel.value;
    bodyBox.innerHTML = "";
    if (sourceMode === "manual") renderManualBinding(); else renderDatasetBinding();
  });
  panel.appendChild(el("div", {}, [el("label", { class: "small" }, "Veri Kaynağı"), sourceSel]));

  const bodyBox = el("div");
  panel.appendChild(bodyBox);

  const isMulti = MULTI_SERIES_TYPES.has(obj.type);
  const labelColSel = el("select", {}, [el("option", { value: "" }, "-")]);
  const valueColSel = el("select", {}, [el("option", { value: "" }, "-")]);
  const selectedValueCols = new Set(getValueCols(config));
  const valueColsBox = el("div", { class: "pill-list", style: "margin-top:4px" });
  const aggSel = el("select", {}, ["none", "sum", "avg", "count", "min", "max"].map(
    (a) => el("option", { value: a, selected: a === (config.agg || "sum") ? "selected" : null }, a)
  ));

  /**
   * Kolon adlarından bir seçim kutusu için seçenek öğeleri üretir. İlk seçenek '-' (seçilmedi) olur; selected ile önceden seçili kolon işaretlenir.
   * Parametreler: names = kolon adları; selected = seçili ad.
   */
  function columnOptionsFromNames(names, selected) {
    return [el("option", { value: "" }, "-")].concat(
      names.map((n) => el("option", { value: n, selected: n === selected ? "selected" : null }, n))
    );
  }

  let lastAvailableNames = [];

  /**
   * Çok seri grafikler için değer kolonu çiplerini çizer. Çipe tıklanınca seri eklenir/çıkarılır ve ayar hemen kaydedilir.
   */
  function renderValueColsChips() {
    valueColsBox.innerHTML = "";
    for (const name of lastAvailableNames) {
      const included = selectedValueCols.has(name);
      const chip = el("span", { class: `field-chip ${included ? "included" : ""}` }, name);
      chip.addEventListener("click", () => {
        if (selectedValueCols.has(name)) selectedValueCols.delete(name);
        else selectedValueCols.add(name);
        renderValueColsChips();
        persistAndRerender(
          sourceMode === "dataset" ? { datasetId: config._lastDatasetId } : { conn_id: config._lastConnId, table: config._lastTable }
        );
      });
      valueColsBox.appendChild(chip);
    }
    if (!lastAvailableNames.length) valueColsBox.appendChild(el("p", { class: "muted small" }, "Önce kaynak seçin."));
  }

  /**
   * Etiket ve değer kolonu kutularını verilen kolon adlarıyla doldurur. namesProvider: { names, optionsFor(seçili) } şeklinde bir nesne; optionsFor, her kutu için seçenek öğeleri döndürür.
   * Çok seri türde değer kutusu yerine çip listesi yenilenir.
   */
  function fillLabelValueSelects(namesProvider) {
    lastAvailableNames = namesProvider.names;
    labelColSel.innerHTML = "";
    namesProvider.optionsFor(config.labelCol).forEach((o) => labelColSel.appendChild(o));
    if (isMulti) {
      renderValueColsChips();
    } else {
      valueColSel.innerHTML = "";
      namesProvider.optionsFor(config.valueCol).forEach((o) => valueColSel.appendChild(o));
    }
  }

  /**
   * Grafik bağlama ayarlarını (etiket, değer kolonları/kolonu, toplama ve kaynak bilgisi) widget'a yazar ve yeniden çizer. Çok seri türlerde valueCols, diğerlerinde valueCol kaydedilir.
   * Parametre extra: bu seferde değişen ek alanlar (örn. kaynak değişince).
   */
  function persistAndRerender(extra) {
    const current = getWidgetConfig(obj) || {};
    const patch = isMulti
      ? { labelCol: labelColSel.value, valueCols: Array.from(selectedValueCols), agg: aggSel.value, ...extra }
      : { labelCol: labelColSel.value, valueCol: valueColSel.value, agg: aggSel.value, ...extra };
    setWidgetConfig(obj, { ...current, ...patch });
    rerenderWidget(obj.id);
  }

  labelColSel.addEventListener("change", () => persistAndRerender(
    sourceMode === "dataset" ? { datasetId: config._lastDatasetId } : { conn_id: config._lastConnId, table: config._lastTable }
  ));
  valueColSel.addEventListener("change", () => persistAndRerender(
    sourceMode === "dataset" ? { datasetId: config._lastDatasetId } : { conn_id: config._lastConnId, table: config._lastTable }
  ));
  aggSel.addEventListener("change", () => persistAndRerender(
    sourceMode === "dataset" ? { datasetId: config._lastDatasetId } : { conn_id: config._lastConnId, table: config._lastTable }
  ));

  /**
   * Manuel ve veri seti modlarında ortak olan alanları ekler: etiket kolonu, değer kolonu/kolonları ve toplama seçimi. Her iki mod da bu alanları kullanır, bu yüzden tek yerde tutulur.
   */
  function appendSharedFields() {
    const axisLabel = obj.type === "bar" ? "Etiket kolonu (Y ekseni)" : "Etiket kolonu (X ekseni)";
    bodyBox.appendChild(el("div", {}, [el("label", { class: "small" }, axisLabel), labelColSel]));
    if (isMulti) {
      bodyBox.appendChild(el("div", {}, [
        el("label", { class: "small" }, "Değer kolonları (birden fazla seçebilirsiniz — her biri ayrı bir seri olur)"),
        valueColsBox,
      ]));
    } else {
      bodyBox.appendChild(el("div", {}, [el("label", { class: "small" }, "Değer kolonu"), valueColSel]));
    }
    bodyBox.appendChild(el("div", {}, [el("label", { class: "small" }, "Toplama (aggregation)"), aggSel]));
  }

  /**
   * Grafik widget'ı için 'Manuel Bağlantı' formunu çizer (bağlantı > tablo > ortak alanlar > 'Bağla ve Çiz'). Tablo seçilince kolonlar çekilir ve kutulara yazılır.
   */
  function renderManualBinding() {
    const connSel = el("select", {}, [
      el("option", { value: "" }, "Bağlantı seçin…"),
      ...state.connections.map((c) => el("option", {
        value: c.conn_id, selected: c.conn_id === config.conn_id ? "selected" : null,
      }, `${c.conn_id} (${c.database})`)),
    ]);
    const tableSel = el("select", {}, [el("option", { value: "" }, "Önce bağlantı seçin")]);

    /**
     * Seçilen bağlantının tablolarını grafik formundaki tablo kutusuna doldurur. selectedTable verilirse o tablo seçili gelir ve kolonları yüklenir. Tablo tablo-bağlama formundaki fonksiyonla aynı işi yapar, ama farklı kutuları günceller.
     */
    async function loadTablesInto(connId, selectedTable) {
      tableSel.innerHTML = "";
      tableSel.appendChild(el("option", { value: "" }, "Yükleniyor…"));
      try {
        const res = await api.listTables(connId);
        tableSel.innerHTML = "";
        tableSel.appendChild(el("option", { value: "" }, "Tablo seçin…"));
        for (const t of res.tables || []) {
          tableSel.appendChild(el("option", { value: t, selected: t === selectedTable ? "selected" : null }, t));
        }
        if (selectedTable) await loadColumnsInto(connId, selectedTable);
      } catch (e) { handleApiError(e, "Tablolar alınamadı"); }
    }

    /**
     * Seçilen tablonun kolonlarını çekip etiket ve değer kutularını doldurur. Son bağlantı ve tablo bilgisi config'e yazılır ki sonraki kaydetme doğru kaynağı kullansın.
     */
    async function loadColumnsInto(connId, table) {
      try {
        const res = await api.listColumns(connId, table);
        config._lastConnId = connId; config._lastTable = table;
        const names = (res.columns || []).map((c) => c.name);
        // optionsFor, kutulardaki seçenekleri üretmek için kullanılır: kolon adları (names) ve hangi değerin seçili olacağı verilir. Böylece aynı kutu hem manuel hem veri seti modunda çalışır.
        fillLabelValueSelects({ names, /* optionsFor: her kutu için seçenek üreten fonksiyon */ optionsFor: (sel) => columnOptionsFromNames(names, sel) });
      } catch (e) { handleApiError(e, "Kolonlar alınamadı"); }
    }

    connSel.addEventListener("change", () => loadTablesInto(connSel.value, null));
    tableSel.addEventListener("change", () => loadColumnsInto(connSel.value, tableSel.value));

    bodyBox.appendChild(el("div", {}, [el("label", { class: "small" }, "Bağlantı"), connSel]));
    bodyBox.appendChild(el("div", {}, [el("label", { class: "small" }, "Tablo"), tableSel]));
    appendSharedFields();

    const applyBtn = el("button", { class: "btn btn-primary btn-sm", style: "margin-top:8px" }, "Bağla ve Çiz");
    applyBtn.addEventListener("click", () => persistAndRerender({ conn_id: connSel.value, table: tableSel.value, datasetId: null }));
    bodyBox.appendChild(applyBtn);

    if (config.conn_id && !config.datasetId) loadTablesInto(config.conn_id, config.table);
  }

  /**
   * Grafik widget'ı için 'Kayıtlı Sorgu' formunu çizer. Veri setleri listelenir; seçilince kolonları çekilir ve etiket/değer kutularına yazılır. Liste yüklenemezse hata bildirilir.
   */
  function renderDatasetBinding() {
    const dsSel = el("select", {}, [el("option", { value: "" }, "Yükleniyor…")]);
    bodyBox.appendChild(el("div", {}, [el("label", { class: "small" }, "Kayıtlı Sorgu"), dsSel]));
    appendSharedFields();

    const applyBtn = el("button", { class: "btn btn-primary btn-sm", style: "margin-top:8px" }, "Bağla ve Çiz");
    applyBtn.addEventListener("click", () => persistAndRerender({ datasetId: dsSel.value, conn_id: null, table: null }));
    bodyBox.appendChild(applyBtn);

    api.listDatasets().then((datasets) => {
      dsSel.innerHTML = "";
      dsSel.appendChild(el("option", { value: "" }, "Dataset seçin…"));
      for (const d of datasets) {
        dsSel.appendChild(el("option", { value: d.dataset_id, selected: d.dataset_id === config.datasetId ? "selected" : null }, d.name));
      }
      dsSel.addEventListener("change", async () => {
        if (!dsSel.value) return;
        try {
          const cols = await fetchDatasetColumns(dsSel.value);
          config._lastDatasetId = dsSel.value;
          // Veri setinden gelen kolon adları, aynı optionsFor kalıbıyla etiket ve değer kutularına dağıtılır (cols).
          fillLabelValueSelects({ names: cols, /* optionsFor: her kutu için seçenek üreten fonksiyon */ optionsFor: (sel) => columnOptionsFromNames(cols, sel) });
        } catch (e) { handleApiError(e, "Dataset kolonları alınamadı"); }
      });
      if (config.datasetId) dsSel.dispatchEvent(new Event("change"));
    }).catch((e) => handleApiError(e, "Dataset listesi alınamadı"));
  }

  if (sourceMode === "manual") renderManualBinding(); else renderDatasetBinding();
}

/* ============================================================
 * 5) Sürücüler (Drivers)
 * ==========================================================*/

/**
 * 'Sürücüler' ekranını kurar: sürücü listesini sunucudan çeker ve tabloya çevirir. Hata olursa kullanıcıya bildirilir.
 * Parametre root: ekranın ekleneceği kapsayıcı.
 */
async function renderDriversView(root) {
  root.appendChild(el("h2", {}, "Veritabanı Sürücüleri"));
  root.appendChild(el("p", { class: "muted" },
    "SQLite her zaman hazırdır. PostgreSQL/MySQL/SQL Server sürücüleri isteğe bağlı kurulur (lazy install)."
  ));

  const card = el("div", { class: "card" });
  const body = el("div", {}, el("p", { class: "muted" }, "Yükleniyor…"));
  card.appendChild(body);
  root.appendChild(card);

  try {
    state.drivers = await api.listDrivers();
    renderDriversTable(body);
  } catch (e) {
    handleApiError(e, "Sürücüler alınamadı");
  }
}

/**
 * Veritabanı sürücülerinin tablosunu çizer: tip, durum (kurulu/kurulu değil) ve 'Kur' düğmesi. Düğme yalnız admin ve kurulu olmayan sürücüler için görünür.
 * DİKKAT: Bu gizleme yalnız görünüm içindir; yetki kontrolü sunucuda yapılmalıdır.
 */
function renderDriversTable(container) {
  container.innerHTML = "";
  const table = el("table");
  table.appendChild(el("thead", {}, el("tr", {}, ["Veritabanı Tipi", "Durum", ""].map((h) => el("th", {}, h)))));
  const tbody = el("tbody");
  for (const d of state.drivers) {
    // Kur düğmesi gizleme sadece arayüz içindir. Asıl yetki kontrolü sunucudadır; bir kullanıcı API'yi doğrudan çağırırsa bu gizleme onu durdurmaz.
    const installBtn = el("button", { class: "btn btn-sm" }, "Kur");
    if (d.installed || state.role !== "admin") installBtn.style.display = "none";
    installBtn.addEventListener("click", () => withBusy(installBtn, async () => {
      try {
        await api.installDriver(d.db_type);
        toast(`${d.db_type} sürücüsü kuruldu`, "success");
        state.drivers = await api.listDrivers();
        renderDriversTable(container);
      } catch (e) { handleApiError(e, "Kurulamadı — admin yetkisi ve internet erişimi gerekir"); }
    }));
    tbody.appendChild(el("tr", {}, [
      el("td", {}, d.db_type),
      el("td", {}, el("span", { class: `badge ${d.installed ? "ok" : "warn"}` }, d.installed ? "kurulu" : "kurulu değil")),
      el("td", {}, installBtn),
    ]));
  }
  table.appendChild(tbody);
  container.appendChild(table);
}

/* ============================================================
 * Uygulama başlangıcı
 * ==========================================================*/

/**
 * Uygulamanın başlangıç noktası. Sayfa (DOMContentLoaded) hazır olunca çağrılır: giriş ve menü olaylarını bağlar, tema uygular; kayıtlı oturum varsa uygulama kabuğunu, yoksa giriş ekranını gösterir.
 */
function boot() {
  initAuthScreen();
  initNav();
  initTheme();

  if (isLoggedIn()) {
    showAppShell();
  } else {
    showAuthScreen();
  }
}

document.addEventListener("DOMContentLoaded", boot);
