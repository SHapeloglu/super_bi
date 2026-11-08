/**
 * api.js — SuperBI backend API istemcisi
 * DOM'dan bağımsız, saf fetch tabanlı fonksiyonlar. Node.js ile de test
 * edilebilir olsun diye ayrı bir modül olarak tutuldu.
 */

/**
 * SuperBI backend'i ile konuşan API istemcisini oluşturur.
 * Parametreler:
 * - baseUrl: Sunucu adresi (örn. "https://ornek.com"), yollara başta eklenir.
 * - getToken: Her istekte çağrılan fonksiyon; oturum token'ını döndürür (yoksa boş/null).
 * Dönüş: Her endpoint için bir fonksiyon içeren nesne. Her fonksiyon bir Promise döndürür; sunucu hata verirse Promise reddedilir.
 * Neden fabrika fonksiyonu: token her istekte taze okunsun diye, token değişince yeniden kurmaya gerek kalmasın.
 */
export function createApiClient(baseUrl, getToken) {
  /**
   * Ortak HTTP istek yardımcısı. Tüm endpoint fonksiyonları bunu kullanır.
   * Parametreler:
   * - method: "GET", "POST", "PUT" veya "DELETE".
   * - path: "/api/..." ile başlayan yol.
   * - body: JSON olarak gönderilecek veri; undefined ise gövde gönderilmez.
   * - opts.noAuth: true ise Authorization başlığı eklenmez (giriş/kayıt gibi token gerektirmeyen istekler için).
   * Dönüş: Cevap JSON ise nesne, JSON değilse düz metin, cevap boşsa null.
   * Hata: HTTP durumu 2xx dışındaysa Error fırlatır; err.status HTTP kodunu, err.detail sunucunun detay mesajını taşır.
   */
  async function request(method, path, body, opts = {}) {
    const headers = { "Content-Type": "application/json" };
    const token = getToken();
    // Token varsa ve bu istek noAuth değilse Authorization başlığı eklenir. Giriş/kayıt isteklerinde token gönderilmez.
    if (token && !opts.noAuth) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(baseUrl + path, {
      method,
      headers,
      // GET isteklerinde gövde yoktur; body undefined ise fetch'e undefined verilir ve gövde gönderilmez.
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    let data = null;
    // Cevap gövdesi önce metin olarak okunur. JSON olarak çözülemezse (örn. düz metin hata sayfası) ham metin kullanılır; boş cevap null kalır.
    const text = await res.text();
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
    }

    // HTTP hata kodu (4xx/5xx) gelirse hata fırlatılır. FastAPI tarzı hatalarda mesaj 'detail' alanında olduğu için önce o alınır.
    if (!res.ok) {
      const detail =
        data && typeof data === "object" && "detail" in data
          ? data.detail
          : data;
      const err = new Error(
        typeof detail === "string" ? detail : JSON.stringify(detail)
      );
      // Çağıran kod hata durumunu err.status ile ayırt edebilsin diye HTTP kodu hataya eklenir (örn. 401 = oturum süresi dolmuş).
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
    /** Kayıt açık mı? Döner: { open: boolean }. Kimlik gerektirmez. */
    registrationStatus: () =>
      request("GET", "/api/auth/registration", undefined, { noAuth: true }),
    /**
     * Kullanıcı girişi. Başarılıysa sunucu token döndürür (token sonraki isteklerde kullanılır).
     */
    login: (username, password) =>
      request("POST", "/api/auth/login", { username, password }, { noAuth: true }),

    // ---- connections ----
    listConnections: () => request("GET", "/api/connections"),
    /**
     * Yeni veritabanı bağlantısı oluşturur. params: bağlantı bilgileri (sunucu adı, veritabanı, kullanıcı vb.).
     */
    createConnection: (params) => request("POST", "/api/connections", params),
    /**
     * Verilen bağlantıya gerçekten bağlanıp bağlanamadığını dener.
     */
    testConnection: (connId) => request("GET", `/api/connections/${encodeURIComponent(connId)}/test`),
    /**
     * Bağlantıyı siler.
     */
    deleteConnection: (connId) => request("DELETE", `/api/connections/${encodeURIComponent(connId)}`),

    // ---- schema ----
    listSchemas: (connId) => request("GET", `/api/schema/${encodeURIComponent(connId)}/schemas`),
    /**
     * Şemadaki tablo listesini getirir. schema verilmezse sunucunun varsayılan şeması kullanılır.
     */
    listTables: (connId, schema) =>
      request("GET", `/api/schema/${encodeURIComponent(connId)}/tables${schema ? `?schema=${encodeURIComponent(schema)}` : ""}`),
    /**
     * Bir tablonun kolonlarını getirir. Tablo adı URL'de güvenli hale getirilir (encodeURIComponent), çünkü boşluk veya özel karakter içerebilir.
     */
    listColumns: (connId, table, schema) =>
      request("GET", `/api/schema/${encodeURIComponent(connId)}/tables/${encodeURIComponent(table)}/columns${schema ? `?schema=${encodeURIComponent(schema)}` : ""}`),
    /**
     * Bir tablonun yabancı anahtar (foreign key) ilişkilerini getirir. İlişki keşfi ekranında kullanılır.
     */
    listForeignKeys: (connId, table, schema) =>
      request("GET", `/api/schema/${encodeURIComponent(connId)}/tables/${encodeURIComponent(table)}/foreign-keys${schema ? `?schema=${encodeURIComponent(schema)}` : ""}`),

    // ---- analyze (granularity + ilişki keşfi) ----
    analyzeTables: (connId, body) => request("POST", `/api/analyze/${encodeURIComponent(connId)}/tables`, body || {}),
    /**
     * İki tablo arasındaki ilişkiyi sunucuda test eder. body: hangi tabloların/kolonların eşleştirileceğini anlatan nesne.
     */
    testRelationship: (connId, body) => request("POST", `/api/analyze/${encodeURIComponent(connId)}/relationship`, body),
    /**
     * Daha önce yapılmış analiz (granülarite/ilişki) sonuçlarını getirir.
     */
    getAnalysisResults: (connId) => request("GET", `/api/analyze/${encodeURIComponent(connId)}/results`),

    // ---- drivers ----
    listDrivers: () => request("GET", "/api/drivers"),
    /**
     * Belirtilen veritabanı türü için sürücü (driver) kurulumunu başlatır. Kurulum uzun sürebilir.
     */
    installDriver: (dbType) => request("POST", `/api/drivers/${dbType}/install`),

    // ---- query ----
    previewSql: (body) => request("POST", "/api/query/preview", body, { noAuth: true }),
    /**
     * SQL sorgusunu çalıştırır. body: sorgu ve bağlantı bilgisi. Dönen cevapta sonuç ile birlikte cache_key gelir; bu anahtar commit için kullanılır.
     */
    runQuery: (body) => request("POST", "/api/query/run", body),
    /**
     * Daha önce çalıştırılıp önbelleğe alınmış bir sorguyu kalıcı hale getirir. cacheKey: runQuery'nin döndürdüğü anahtar.
     */
    commitQuery: (cacheKey) => request("POST", "/api/query/commit", { cache_key: cacheKey }),
    /**
     * Bir bağlantının sorgu önbelleğini temizler (şema veya veri değiştiğinde eski sonuçları silmek için).
     */
    invalidateCache: (connId) => request("DELETE", `/api/query/cache/${encodeURIComponent(connId)}`),

    // ---- history ----
    addHistory: (body) => request("POST", "/api/history", body),
    /**
     * Sorgu geçmişini gruplar halinde getirir. connId verilirse yalnız o bağlantının geçmişi gelir.
     */
    getGroups: (connId) =>
      request("GET", `/api/history/groups${connId ? `?conn_id=${encodeURIComponent(connId)}` : ""}`),
    /**
     * Bir sorgu grubunun (fingerprint ile tanımlanır) tüm sürümlerini getirir.
     */
    getVersions: (fingerprint) => request("GET", `/api/history/groups/${encodeURIComponent(fingerprint)}`),
    /**
     * En son çalıştırılan sorguları getirir. limit: kaç kayıt dönsün (varsayılan 20).
     */
    getRecent: (limit = 20) => request("GET", `/api/history/recent?limit=${limit}`),
    /**
     * Bir sorgu grubunu geçmişten siler.
     */
    deleteGroup: (fingerprint) => request("DELETE", `/api/history/groups/${encodeURIComponent(fingerprint)}`),

    // ---- dashboards ----
    listDashboards: () => request("GET", "/api/dashboards"),
    /**
     * Yeni dashboard oluşturur. body: dashboard adı ve widget tanımları.
     */
    createDashboard: (body) => request("POST", "/api/dashboards", body),
    /**
     * Mevcut bir dashboard'u id ile günceller. PUT olduğu için gönderilen gövde tam kaydın yerini alır.
     */
    updateDashboard: (id, body) => request("PUT", `/api/dashboards/${encodeURIComponent(id)}`, body),
    /**
     * Tek bir dashboard'un içeriğini id ile getirir.
     */
    getDashboard: (id) => request("GET", `/api/dashboards/${encodeURIComponent(id)}`),
    /**
     * Dashboard'u id ile siler.
     */
    deleteDashboard: (id) => request("DELETE", `/api/dashboards/${encodeURIComponent(id)}`),

    // ---- datasets (kayıtlı sorgular — birden fazla widget aynı tanımı paylaşabilir) ----
    listDatasets: () => request("GET", "/api/datasets"),
    /**
     * Yeni bir veri seti (kayıtlı sorgu) oluşturur.
     */
    createDataset: (body) => request("POST", "/api/datasets", body),
    /**
     * Mevcut bir veri setini id ile günceller (PUT, gövde tam kaydın yerini alır).
     */
    updateDataset: (id, body) => request("PUT", `/api/datasets/${encodeURIComponent(id)}`, body),
    /**
     * Tek bir veri setini id ile getirir.
     */
    getDataset: (id) => request("GET", `/api/datasets/${encodeURIComponent(id)}`),
    /**
     * Kayıtlı veri setini sunucuda çalıştırır (okuma izni yeterli; bağlantı sahibinin kimliğiyle).
     * body: { fields?: {kolon: rol}, sample, mode }. fields yalnız veri setinin kolonlarından olabilir.
     */
    runDataset: (id, body) => request("POST", `/api/datasets/${encodeURIComponent(id)}/run`, body),
    /**
     * Veri setini id ile siler. Başka widget'lar bu seti kullanıyorsa dikkat edilmeli.
     */
    deleteDataset: (id) => request("DELETE", `/api/datasets/${encodeURIComponent(id)}`),

    // ---- health ----
    health: () => request("GET", "/api/health", undefined, { noAuth: true }),
  };
}
