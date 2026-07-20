/**
 * api.js — SuperBI backend API istemcisi
 * DOM'dan bağımsız, saf fetch tabanlı fonksiyonlar. Node.js ile de test
 * edilebilir olsun diye ayrı bir modül olarak tutuldu.
 */

export function createApiClient(baseUrl, getToken) {
  async function request(method, path, body, opts = {}) {
    const headers = { "Content-Type": "application/json" };
    const token = getToken();
    if (token && !opts.noAuth) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(baseUrl + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    let data = null;
    const text = await res.text();
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
    }

    if (!res.ok) {
      const detail =
        data && typeof data === "object" && "detail" in data
          ? data.detail
          : data;
      const err = new Error(
        typeof detail === "string" ? detail : JSON.stringify(detail)
      );
      err.status = res.status;
      err.detail = detail;
      throw err;
    }
    return data;
  }

  return {
    // ---- auth ----
    register: (username, password) =>
      request("POST", "/api/auth/register", { username, password }, { noAuth: true }),
    login: (username, password) =>
      request("POST", "/api/auth/login", { username, password }, { noAuth: true }),

    // ---- connections ----
    listConnections: () => request("GET", "/api/connections"),
    createConnection: (params) => request("POST", "/api/connections", params),
    testConnection: (connId) => request("GET", `/api/connections/${connId}/test`),
    deleteConnection: (connId) => request("DELETE", `/api/connections/${connId}`),

    // ---- schema ----
    listTables: (connId) => request("GET", `/api/schema/${connId}/tables`),
    listColumns: (connId, table) =>
      request("GET", `/api/schema/${connId}/tables/${encodeURIComponent(table)}/columns`),
    listForeignKeys: (connId, table) =>
      request("GET", `/api/schema/${connId}/tables/${encodeURIComponent(table)}/foreign-keys`),

    // ---- drivers ----
    listDrivers: () => request("GET", "/api/drivers"),
    installDriver: (dbType) => request("POST", `/api/drivers/${dbType}/install`),

    // ---- query ----
    previewSql: (body) => request("POST", "/api/query/preview", body, { noAuth: true }),
    runQuery: (body) => request("POST", "/api/query/run", body),
    commitQuery: (cacheKey) => request("POST", "/api/query/commit", { cache_key: cacheKey }),
    invalidateCache: (connId) => request("DELETE", `/api/query/cache/${connId}`),

    // ---- history ----
    addHistory: (body) => request("POST", "/api/history", body),
    getGroups: (connId) =>
      request("GET", `/api/history/groups${connId ? `?conn_id=${connId}` : ""}`),
    getVersions: (fingerprint) => request("GET", `/api/history/groups/${fingerprint}`),
    getRecent: (limit = 20) => request("GET", `/api/history/recent?limit=${limit}`),
    deleteGroup: (fingerprint) => request("DELETE", `/api/history/groups/${fingerprint}`),

    // ---- dashboards ----
    listDashboards: () => request("GET", "/api/dashboards"),
    createDashboard: (body) => request("POST", "/api/dashboards", body),
    updateDashboard: (id, body) => request("PUT", `/api/dashboards/${id}`, body),
    getDashboard: (id) => request("GET", `/api/dashboards/${id}`),
    deleteDashboard: (id) => request("DELETE", `/api/dashboards/${id}`),

    // ---- datasets (kayıtlı sorgular — birden fazla widget aynı tanımı paylaşabilir) ----
    listDatasets: () => request("GET", "/api/datasets"),
    createDataset: (body) => request("POST", "/api/datasets", body),
    updateDataset: (id, body) => request("PUT", `/api/datasets/${id}`, body),
    getDataset: (id) => request("GET", `/api/datasets/${id}`),
    deleteDataset: (id) => request("DELETE", `/api/datasets/${id}`),

    // ---- health ----
    health: () => request("GET", "/api/health", undefined, { noAuth: true }),
  };
}
