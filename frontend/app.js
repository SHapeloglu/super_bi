import { createApiClient } from "./api.js";

/* ============================================================
 * Ayarlar + global state
 * ==========================================================*/

// Aynı origin'den servis edileceği için boş baseUrl -> /api/... göreli istekler.
// Geliştirme sırasında farklı bir origin'den test etmek isterseniz burayı
// "http://127.0.0.1:8000" gibi bir değere çevirin.
const API_BASE = window.__SUPERBI_API_BASE__ || "";

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
  fields: {},          // { colName: "dim" | "off" }
  joins: [],           // [{type,t1,f1,t2,f2}]
  filters: [],         // [{table,column,operator,value,value2}]
  groupBy: [],
  orderBy: [],
  calculatedFields: [],
  sample: 100,

  lastPreview: null,
  lastRun: null,

  historyRecent: [],
  historyGroups: [],

  dashboards: [],
  currentDashboard: null,   // {dashboard_id, name, scale, page_w_mm, page_h_mm, objects}
  dashZoom: 1,
  selectedWidgetId: null,

  drivers: [],
  _widgetColumnsCache: [],
};

const api = createApiClient(API_BASE, () => state.token);

/* ============================================================
 * Küçük yardımcılar
 * ==========================================================*/

function qs(sel, root = document) { return root.querySelector(sel); }
function qsa(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

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

function toast(message, type = "info") {
  const root = qs("#toast-root");
  const node = el("div", { class: `toast ${type}` }, message);
  root.appendChild(node);
  setTimeout(() => node.remove(), 4000);
}

function fmtDate(iso) {
  if (!iso) return "-";
  try { return new Date(iso).toLocaleString("tr-TR"); } catch { return iso; }
}

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

function isLoggedIn() { return !!state.token; }

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

function showAuthScreen() {
  qs("#auth-screen").style.display = "flex";
  qs("#app-shell").style.display = "none";
}

function showAppShell() {
  qs("#auth-screen").style.display = "none";
  qs("#app-shell").style.display = "flex";
  qs("#user-label").textContent = `${state.username || "?"} (${state.role || "?"})`;
  renderView(state.view);
}

let authMode = "login";

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

function renderView(name) {
  // Görünüm değişirken önceki dashboard'a ait Chart.js örnekleri DOM'dan
  // ayrılacağı için önce düzgünce yok edilmeli (memory leak önleme).
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

function initNav() {
  qsa(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => renderView(btn.dataset.view));
  });
}

/* ============================================================
 * Tema (koyu / açık) — CSS değişkenleri style.css'te body.light-theme
 * ile eziliyor, burada sadece class toggle + localStorage kalıcılığı var.
 * ==========================================================*/

function applyTheme(theme) {
  document.body.classList.toggle("light-theme", theme === "light");
  const btn = qs("#theme-toggle-btn");
  if (btn) btn.textContent = theme === "light" ? "☀️" : "🌙";
}

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

async function renderConnectionsView(root) {
  root.appendChild(el("h2", {}, "Veritabanı Bağlantıları"));

  const formCard = el("div", { class: "card" });
  formCard.appendChild(el("h3", {}, "Yeni Bağlantı Ekle"));

  const dbTypeSel = el("select", { id: "conn-db-type" }, [
    el("option", { value: "sqlite" }, "SQLite"),
    el("option", { value: "postgresql" }, "PostgreSQL"),
    el("option", { value: "mysql" }, "MySQL"),
    el("option", { value: "mssql" }, "SQL Server"),
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

async function refreshConnections() {
  state.connections = await api.listConnections();
}

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
}

/* ============================================================
 * 2) Sorgu Oluşturucu (Query Builder)
 * ==========================================================*/

const ALLOWED_OPERATORS = [
  "=", "!=", "<>", ">", "<", ">=", "<=",
  "LIKE", "NOT LIKE", "ILIKE",
  "IN", "NOT IN",
  "IS NULL", "IS NOT NULL",
  "BETWEEN",
];

const ALLOWED_JOIN_TYPES = [
  "JOIN", "INNER JOIN", "LEFT JOIN", "LEFT OUTER JOIN",
  "RIGHT JOIN", "RIGHT OUTER JOIN", "FULL JOIN", "FULL OUTER JOIN",
];

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

  // --- Bağlantı + tablo seçimi ---
  const topCard = el("div", { class: "card" });
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
      for (const c of state.columns) state.fields[c.name] = "dim"; // varsayılan: dahil
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

  await loadTablesFor(connSel.value);
}

function buildQueryShape() {
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
}

function renderBuilderCard(builderCard, resultCard) {
  builderCard.innerHTML = "";
  builderCard.appendChild(el("h3", {}, `Tablo: ${state.selectedTable}`));

  // --- Alanlar (fields) ---
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

  // --- Join'ler ---
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

  // --- Filtreler ---
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

  // --- Hesaplanmış Alanlar ---
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

  // --- Group by / Order by ---
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

  // --- Örnek boyutu + aksiyon butonları ---
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

// Tablo başına kolon listesini önbelleğe alır — aynı tabloyu birden fazla
// join satırında seçtiğinizde her seferinde yeniden istek atılmaz.
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

function renderJoinsBox(box) {
  box.innerHTML = "";
  state.joins.forEach((j, idx) => {
    const typeSel = el("select", {}, ALLOWED_JOIN_TYPES.map(
      (t) => el("option", { value: t, selected: t === j.type ? "selected" : null }, t)
    ));

    const tableOptions = (selected) => [el("option", { value: "" }, "tablo seçin")].concat(
      state.tables.map((t) => el("option", { value: t, selected: t === selected ? "selected" : null }, t))
    );

    const t1Sel = el("select", {}, tableOptions(j.t1));
    const t2Sel = el("select", {}, tableOptions(j.t2));
    const f1Sel = el("select", {}, [el("option", { value: j.f1 || "" }, j.f1 || "kolon seçin")]);
    const f2Sel = el("select", {}, [el("option", { value: j.f2 || "" }, j.f2 || "kolon seçin")]);
    const delBtn = el("button", { class: "btn btn-sm btn-danger" }, "Sil");

    async function refreshColumnSelect(tableSel, colSel, currentVal, onPick) {
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

    // İlk render'da mevcut tablo seçiliyse kolon listesini hemen doldur
    if (j.t1) refreshColumnSelect(t1Sel, f1Sel, j.f1);
    if (j.t2) refreshColumnSelect(t2Sel, f2Sel, j.f2);

    box.appendChild(el("div", { class: "join-row" }, [typeSel, t1Sel, f1Sel, t2Sel, f2Sel, delBtn]));
  });
}

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

async function doPreview(resultCard) {
  try {
    const body = { ...buildQueryShape(), limit: state.sample };
    const res = await api.previewSql(body);
    state.lastPreview = res;
    renderResultCard(resultCard);
  } catch (e) { handleApiError(e, "SQL önizleme başarısız — filtre/join alanlarını kontrol edin"); }
}

async function doRun(resultCard) {
  try {
    const body = { ...buildQueryShape(), sample: state.sample, commit: false, mode: "memory" };
    const res = await api.runQuery(body);
    state.lastRun = res;
    renderResultCard(resultCard);
    toast(`${res.row_count} satır, ${res.exec_ms}ms (${res.mode})`, "success");
  } catch (e) { handleApiError(e, "Sorgu çalıştırılamadı"); }
}

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

// Aynı join/filter/base_table şekli için tutarlı bir fingerprint üretir
// (backend'de sürüm gruplama bu değere göre yapılır).
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
 * 4) Dashboard'lar (mm tabanlı canvas, sürükle-bırak, zoom)
 * ==========================================================*/

const PX_PER_MM = 3; // 1mm = 3px @ zoom 1 (A4 yatay 297x210mm -> 891x630px)

const WIDGET_TYPES = [
  { type: "kpi", label: "KPI Kartı", w: 60, h: 40 },
  { type: "line", label: "Çizgi Grafik", w: 100, h: 70 },
  { type: "area", label: "Alan Grafik", w: 100, h: 70 },
  { type: "column", label: "Sütun Grafik", w: 100, h: 70 },
  { type: "bar", label: "Yatay Sütun", w: 100, h: 70 },
  { type: "scatter", label: "Dağılım Grafiği", w: 90, h: 70 },
  { type: "pie", label: "Pasta Grafik", w: 70, h: 70 },
  { type: "donut", label: "Halka Grafik", w: 70, h: 70 },
  { type: "table", label: "Tablo", w: 120, h: 80 },
  { type: "matrix", label: "Matris", w: 120, h: 80 },
  { type: "map", label: "Harita", w: 100, h: 90 },
  { type: "text", label: "Metin Kutusu", w: 80, h: 30 },
];

function mmToPx(mm) { return mm * PX_PER_MM * state.dashZoom; }
function pxToMm(px) { return px / (PX_PER_MM * state.dashZoom); }

function blankDashboard() {
  return { dashboard_id: null, name: "Yeni Dashboard", scale: "a4l", page_w_mm: 297, page_h_mm: 210, objects: [] };
}

async function renderDashboardsView(root) {
  root.appendChild(el("h2", {}, "Dashboard'lar"));

  // Widget veri bağlama panelindeki "Bağlantı" listesi state.connections'a
  // bakıyor — bu view'a "Bağlantılar" sekmesine hiç uğramadan direkt
  // gelinirse liste boş kalırdı, burada garantiye alıyoruz.
  if (!state.connections.length) {
    try { await refreshConnections(); } catch (e) { handleApiError(e, "Bağlantılar alınamadı"); }
  }

  const listCard = el("div", { class: "card" });
  listCard.appendChild(el("h3", {}, "Kayıtlı Dashboard'lar"));
  const newBtn = el("button", { class: "btn btn-primary btn-sm" }, "+ Yeni Dashboard");
  newBtn.addEventListener("click", () => {
    state.currentDashboard = blankDashboard();
    state.selectedWidgetId = null;
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
}

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
    });
    palette.appendChild(item);
  }
  body.appendChild(palette);

  const canvasWrap = el("div", { class: "canvas-wrap" });
  const canvasPage = el("div", { class: "canvas-page", id: "dash-canvas-page" });
  canvasWrap.appendChild(canvasPage);
  body.appendChild(canvasWrap);

  // --- Seçili widget özellik paneli ---
  const propsPanel = el("div", { class: "widget-palette", id: "dash-props-panel" });
  body.appendChild(propsPanel);

  card.appendChild(body);
  root.appendChild(card);

  renderCanvasPage(canvasPage);
  renderPropsPanel(propsPanel);
}

// ---- Widget veri konfigürasyonu ----
// query_id alanı backend'de serbest bir string; burada JSON serileştirilmiş
// bir "veri bağlama" konfigürasyonu olarak kullanıyoruz (backend değişikliği
// gerektirmeden). Chart tipine göre farklı alanlar taşır.
function getWidgetConfig(obj) {
  if (!obj.query_id) return null;
  try { return JSON.parse(obj.query_id); } catch { return null; }
}
function setWidgetConfig(obj, config) {
  obj.query_id = JSON.stringify(config);
}

const CHART_TYPES = new Set(["line", "area", "column", "bar", "scatter", "pie", "donut", "kpi", "map"]);

// Aktif ECharts örneklerini widget id'sine göre tutar — yeniden render'da
// eskisini yok etmek (dispose) için gerekli, aksi halde DOM hafıza sızdırır.
const chartInstances = new Map();

// Her widget'ın SON çekilen verisini tutar (dışa aktarma/CSV için) —
// {kind: 'chart', rawRows, rawCols} veya {kind: 'kpi', value, label} şeklinde.
const widgetDataCache = new Map();

// Dünya haritası GeoJSON'u bir kez çekilip echarts'a kayıt edilir, sonraki
// tüm map widget'ları bunu tekrar kullanır (tekrar tekrar indirmez).
let worldMapPromise = null;
function ensureWorldMapRegistered() {
  if (!worldMapPromise) {
    worldMapPromise = fetch("https://cdn.jsdelivr.net/npm/echarts@5.5.1/map/json/world.json")
      .then((r) => { if (!r.ok) throw new Error("world.json indirilemedi"); return r.json(); })
      .then((geoJson) => { window.echarts.registerMap("world", geoJson); return true; });
  }
  return worldMapPromise;
}

// Widget config'i ya doğrudan bir bağlantı+tabloya (ad-hoc) ya da kayıtlı
// bir dataset'e (datasetId) işaret edebilir. Bu, ikisini tek bir sorgu
// gövdesine indirger — dataset güncellenince onu kullanan HER widget bir
// sonraki render'da otomatik güncel tanımı çeker (ekstra kod gerekmez).
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

// Bir dataset'in GERÇEKTEN hangi kolonları döndürdüğünü öğrenmek için
// (join'ler yüzünden şema introspection'ı yetmez) küçük bir örnek çalıştırır.
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

async function fetchWidgetData(config) {
  const base = await resolveQueryBase(config);
  const fields = {};
  fields[config.labelCol] = "dim";
  fields[config.valueCol] = "dim";
  const body = { ...base, fields, sample: 500, commit: false, mode: "memory" };
  const res = await api.runQuery(body);
  const labelIdx = res.columns.indexOf(config.labelCol);
  const valueIdx = res.columns.indexOf(config.valueCol);
  let labels = res.rows.map((r) => String(r[labelIdx]));
  let values = res.rows.map((r) => Number(r[valueIdx]) || 0);

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

// Tablo/matris için çoklu kolon desteği — chart tiplerindeki labelCol/valueCol
// ikilisinden farklı olarak, kullanıcı istediği kadar kolon seçebilir.
async function fetchTableData(config) {
  const base = await resolveQueryBase(config);
  const columns = config.columns && config.columns.length ? config.columns : null;
  const fields = {};
  if (columns) {
    for (const c of columns) fields[c] = "dim";
  }
  // Hiç kolon seçilmediyse tüm kolonları getir (fields boş -> sql_builder tüm
  // tabloyu SELECT * ile döner, bkz. SQLBuilder._select_columns).
  const body = { ...base, fields, sample: 200, commit: false, mode: "memory" };
  const res = await api.runQuery(body);
  return { rawRows: res.rows, rawCols: res.columns };
}

function disposeWidgetChart(widgetId) {
  const existing = chartInstances.get(widgetId);
  if (existing) { existing.dispose(); chartInstances.delete(widgetId); }
}

async function renderWidgetChart(obj, bodyEl) {
  const config = getWidgetConfig(obj);

  // Metin kutusu — grafik değil, düzenlenebilir içerik
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

  // Tablo/matris: farklı veri şekli (çoklu kolon), ayrı fetch fonksiyonu
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
    const data = await fetchWidgetData(config);

    if (obj.type === "kpi") {
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

    if (CHART_TYPES.has(obj.type)) {
      widgetDataCache.set(obj.id, {
        kind: "chart", rawCols: [config.labelCol, config.valueCol],
        rawRows: data.labels.map((l, i) => [l, data.values[i]]),
      });
      if (typeof window.echarts === "undefined") {
        disposeWidgetChart(obj.id);
        bodyEl.innerHTML = "";
        bodyEl.appendChild(el("span", { class: "muted small" }, "ECharts yüklenemedi (CDN engellenmiş olabilir)"));
        return;
      }

      if (obj.type === "map") {
        try { await ensureWorldMapRegistered(); }
        catch (e) {
          disposeWidgetChart(obj.id);
          bodyEl.innerHTML = "";
          bodyEl.appendChild(el("span", { class: "muted small", style: "color:var(--danger)" }, "Dünya haritası verisi indirilemedi"));
          return;
        }
      }

      // Aynı widget için mevcut echarts örneği varsa onu YENİDEN KULLAN
      // (dispose+init yerine setOption) — animasyonsuz "titreme" olmadan güncellenir.
      let chart = chartInstances.get(obj.id);
      bodyEl.innerHTML = "";
      bodyEl.style.display = "block";
      bodyEl.style.padding = "0";
      const chartDiv = el("div", { style: "width:100%;height:100%" });
      bodyEl.appendChild(chartDiv);

      if (chart) chart.dispose();
      chart = window.echarts.init(chartDiv, "dark", { renderer: "canvas" });
      chartInstances.set(obj.id, chart);

      const palette = ["#378ADD", "#58c9a0", "#e5b93d", "#e5484d", "#9b6bd1", "#38b6d9"];
      const baseColor = obj.color || "#378ADD";

      let option;
      if (obj.type === "line" || obj.type === "area" || obj.type === "column") {
        option = {
          backgroundColor: "transparent",
          grid: { left: 36, right: 12, top: 16, bottom: 28 },
          tooltip: { trigger: "axis" },
          xAxis: { type: "category", data: data.labels, axisLabel: { color: "#8b93a3", fontSize: 9 }, axisLine: { lineStyle: { color: "#2a2f3a" } } },
          yAxis: { type: "value", axisLabel: { color: "#8b93a3", fontSize: 9 }, splitLine: { lineStyle: { color: "#2a2f3a" } } },
          series: [{
            type: obj.type === "column" ? "bar" : "line",
            data: data.values,
            itemStyle: { color: baseColor },
            smooth: obj.type !== "column",
            areaStyle: obj.type === "area" ? { opacity: 0.25 } : (obj.type === "line" ? { opacity: 0.08 } : undefined),
          }],
        };
      } else if (obj.type === "bar") {
        // "Yatay Sütun" — ECharts'ta bar tipi eksenleri ters çevirerek yatay olur
        option = {
          backgroundColor: "transparent",
          grid: { left: 70, right: 20, top: 16, bottom: 20 },
          tooltip: { trigger: "axis" },
          xAxis: { type: "value", axisLabel: { color: "#8b93a3", fontSize: 9 }, splitLine: { lineStyle: { color: "#2a2f3a" } } },
          yAxis: { type: "category", data: data.labels, axisLabel: { color: "#8b93a3", fontSize: 9 }, axisLine: { lineStyle: { color: "#2a2f3a" } } },
          series: [{ type: "bar", data: data.values, itemStyle: { color: baseColor } }],
        };
      } else if (obj.type === "scatter") {
        option = {
          backgroundColor: "transparent",
          grid: { left: 40, right: 16, top: 16, bottom: 28 },
          tooltip: { trigger: "item" },
          xAxis: { type: "category", data: data.labels, axisLabel: { color: "#8b93a3", fontSize: 9 }, axisLine: { lineStyle: { color: "#2a2f3a" } } },
          yAxis: { type: "value", axisLabel: { color: "#8b93a3", fontSize: 9 }, splitLine: { lineStyle: { color: "#2a2f3a" } } },
          series: [{
            type: "scatter", symbolSize: 10,
            data: data.values, itemStyle: { color: baseColor },
          }],
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

function formatNumber(n) {
  if (Number.isInteger(n)) return n.toLocaleString("tr-TR");
  return n.toLocaleString("tr-TR", { maximumFractionDigits: 2 });
}

// ---- Dışa aktarma (export) ----

function csvEscape(val) {
  if (val === null || val === undefined) return "";
  const s = String(val);
  if (/[",\n;]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
  return s;
}

function rowsToCsv(cols, rows) {
  // Excel'in Türkçe karakterleri doğru okuması için UTF-8 BOM ekliyoruz.
  const BOM = "\uFEFF";
  const lines = [cols.map(csvEscape).join(";")];
  for (const row of rows) lines.push(row.map(csvEscape).join(";"));
  return BOM + lines.join("\r\n");
}

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

function safeFilename(s) {
  return (s || "widget").replace(/[^\w\-ğüşıöçĞÜŞİÖÇ]+/g, "_").slice(0, 60);
}

function exportWidget(obj) {
  const cached = widgetDataCache.get(obj.id);
  const nameBase = safeFilename(obj.title || obj.type);

  if (CHART_TYPES.has(obj.type) && obj.type !== "kpi") {
    // Görsel grafik tipleri: PNG olarak dışa aktar (ECharts'ın kendi
    // getDataURL'i ile) — veri değil, çizilmiş grafiğin görüntüsü.
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
    // Grafik henüz çizilmediyse (veri bağlı değil vb.) CSV'ye düş.
  }

  if (!cached) {
    toast("Dışa aktarılacak veri yok — önce widget'a veri bağlayın", "error");
    return;
  }

  if (cached.kind === "kpi") {
    triggerDownload(rowsToCsv([cached.label || "değer"], [[cached.value]]), `${nameBase}.csv`, "text/csv;charset=utf-8");
    return;
  }

  // kind === 'table' | 'chart' — ikisi de rawCols/rawRows taşır
  triggerDownload(rowsToCsv(cached.rawCols, cached.rawRows), `${nameBase}.csv`, "text/csv;charset=utf-8");
}

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

// Tek bir widget'ın ayarı değiştiğinde SADECE o widget'ı yeniden çizer —
// tüm canvas'ı yeniden oluşturmaz, dolayısıyla diğer widget'ların verisini
// gereksiz yere tekrar backend'den çekmez. Widget ekleme/silme gibi liste
// boyutunu değiştiren işlemler hâlâ tam renderCanvasPage() kullanır (o
// durumlarda zaten kaçınılmaz).
function rerenderWidget(objId) {
  const canvasPage = qs("#dash-canvas-page");
  const dash = state.currentDashboard;
  const obj = dash && dash.objects.find((o) => o.id === objId);
  const oldNode = canvasPage && canvasPage.querySelector(`[data-widget-id="${objId}"]`);
  if (!canvasPage || !obj || !oldNode) {
    // Beklenmeyen bir durum (node bulunamadı vb.) — güvenli şekilde tam
    // yeniden çizime düş.
    if (canvasPage) renderCanvasPage(canvasPage);
    return;
  }
  const newNode = renderWidgetNode(obj, canvasPage);
  oldNode.replaceWith(newNode);
}

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

    function onMove(ev) {
      const dxMm = pxToMm(ev.clientX - startX);
      const dyMm = pxToMm(ev.clientY - startY);
      obj.x = Math.max(0, origX + dxMm);
      obj.y = Math.max(0, origY + dyMm);
      node.style.left = mmToPx(obj.x) + "px";
      node.style.top = mmToPx(obj.y) + "px";
    }
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    e.preventDefault();
  });

  resizeHandle.addEventListener("mousedown", (e) => {
    e.stopPropagation();
    const startX = e.clientX, startY = e.clientY;
    const origW = obj.w, origH = obj.h;

    function onMove(ev) {
      const dwMm = pxToMm(ev.clientX - startX);
      const dhMm = pxToMm(ev.clientY - startY);
      obj.w = Math.max(15, origW + dwMm);
      obj.h = Math.max(15, origH + dhMm);
      node.style.width = mmToPx(obj.w) + "px";
      node.style.height = mmToPx(obj.h) + "px";
      const chart = chartInstances.get(obj.id);
      if (chart) chart.resize();
    }
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      // KPI yazı boyutu widget yüksekliğine göre hesaplanıyor, boyut
      // değişince yeniden çizmek gerekiyor (chart tipleri resize() ile yeterli).
      if (obj.type === "kpi") renderWidgetChart(obj, bodyEl);
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    e.preventDefault();
  });

  return node;
}

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
  [
    [xInput, "x"], [yInput, "y"], [wInput, "w"], [hInput, "h"],
  ].forEach(([input, key]) => {
    input.addEventListener("change", () => {
      obj[key] = parseFloat(input.value) || 0;
      rerenderWidget(obj.id);
    });
  });

  panel.appendChild(el("div", {}, [el("label", { class: "small" }, "Başlık"), titleInput]));
  panel.appendChild(el("div", {}, [el("label", { class: "small" }, "Renk (grafik/vurgu rengi)"), colorInput]));

  // --- Başlık biçimi (punto + renk) — tüm widget tipleri için ---
  const styleCfg = getWidgetConfig(obj) || {};
  const titleFontSel = el("select", {}, [
    { v: 10, l: "Küçük" }, { v: 12, l: "Orta" }, { v: 16, l: "Büyük" },
  ].map(({ v, l }) => el("option", { value: v, selected: v === (styleCfg.titleFontSize || 11) ? "selected" : null }, l)));
  const titleColorInput = el("input", { type: "color", value: styleCfg.titleColor || "#e6e8ec" });

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

// ---- Tablo/Matris: çoklu kolon seçimi ----
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

  function persistAndRerender(extra) {
    const current = getWidgetConfig(obj) || {};
    setWidgetConfig(obj, { ...current, columns: Array.from(selectedCols), ...extra });
    rerenderWidget(obj.id);
  }

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
    if (!names.length) {
      columnsBox.appendChild(el("p", { class: "muted small" }, "Önce kaynak seçin."));
    }
  }

  // ---- Manuel bağlantı modu ----
  function renderManualBinding() {
    const connSel = el("select", {}, [
      el("option", { value: "" }, "Bağlantı seçin…"),
      ...state.connections.map((c) => el("option", {
        value: c.conn_id, selected: c.conn_id === config.conn_id ? "selected" : null,
      }, `${c.conn_id} (${c.database})`)),
    ]);
    const tableSel = el("select", {}, [el("option", { value: "" }, "Önce bağlantı seçin")]);

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

  // ---- Kayıtlı dataset modu ----
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

// ---- Chart tipleri (line/column/pie/donut/map/kpi): etiket+değer ikilisi ----
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

  const labelColSel = el("select", {}, [el("option", { value: "" }, "-")]);
  const valueColSel = el("select", {}, [el("option", { value: "" }, "-")]);
  const aggSel = el("select", {}, ["none", "sum", "avg", "count", "min", "max"].map(
    (a) => el("option", { value: a, selected: a === (config.agg || "sum") ? "selected" : null }, a)
  ));

  function columnOptionsFromNames(names, selected) {
    return [el("option", { value: "" }, "-")].concat(
      names.map((n) => el("option", { value: n, selected: n === selected ? "selected" : null }, n))
    );
  }
  function columnOptionsFromColObjs(cols, selected) {
    return columnOptionsFromNames(cols.map((c) => c.name), selected);
  }

  function fillLabelValueSelects(optionsBuilderResult) {
    labelColSel.innerHTML = ""; valueColSel.innerHTML = "";
    optionsBuilderResult(config.labelCol).forEach((o) => labelColSel.appendChild(o));
    optionsBuilderResult(config.valueCol).forEach((o) => valueColSel.appendChild(o));
  }

  function persistAndRerender(extra) {
    const current = getWidgetConfig(obj) || {};
    setWidgetConfig(obj, {
      ...current,
      labelCol: labelColSel.value, valueCol: valueColSel.value, agg: aggSel.value, ...extra,
    });
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

  function appendSharedFields() {
    bodyBox.appendChild(el("div", {}, [el("label", { class: "small" }, "Etiket kolonu (X ekseni)"), labelColSel]));
    bodyBox.appendChild(el("div", {}, [el("label", { class: "small" }, "Değer kolonu (Y ekseni)"), valueColSel]));
    bodyBox.appendChild(el("div", {}, [el("label", { class: "small" }, "Toplama (aggregation)"), aggSel]));
  }

  // ---- Manuel bağlantı modu ----
  function renderManualBinding() {
    const connSel = el("select", {}, [
      el("option", { value: "" }, "Bağlantı seçin…"),
      ...state.connections.map((c) => el("option", {
        value: c.conn_id, selected: c.conn_id === config.conn_id ? "selected" : null,
      }, `${c.conn_id} (${c.database})`)),
    ]);
    const tableSel = el("select", {}, [el("option", { value: "" }, "Önce bağlantı seçin")]);

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

    async function loadColumnsInto(connId, table) {
      try {
        const res = await api.listColumns(connId, table);
        config._lastConnId = connId; config._lastTable = table;
        fillLabelValueSelects((sel) => columnOptionsFromColObjs(res.columns || [], sel));
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

  // ---- Kayıtlı dataset modu ----
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
          fillLabelValueSelects((sel) => columnOptionsFromNames(cols, sel));
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

function renderDriversTable(container) {
  container.innerHTML = "";
  const table = el("table");
  table.appendChild(el("thead", {}, el("tr", {}, ["Veritabanı Tipi", "Durum", ""].map((h) => el("th", {}, h)))));
  const tbody = el("tbody");
  for (const d of state.drivers) {
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
