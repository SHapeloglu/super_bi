/**
 * shared_connections.js — alıcı için paylaşılan bağlantılar ve izinli tablo seçenekleri (saf fonksiyonlar, DOM yok).
 * Kaynak: GET /api/connections/shared → [{conn_id, db_type, name, tables: [{schema_name, table_name}]}].
 * Tarayıcıda index.html bunu app.js'ten önce klasik script olarak yükler; window.SuperBIShared üzerinden erişilir.
 * Node.js'te require() ile de yüklenebilir (tests/frontend/shared_connections.test.js).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SuperBIShared = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  /**
   * Bağlantı seçici seçenekleri: önce kendi bağlantıları, sonra paylaşılanlar (paylaşılan olduğu etiketle).
   * Dönen her öğe: { value, label, shared }.
   */
  function connectionOptions(ownConns, sharedConns) {
    const own = (ownConns || []).map((c) => ({
      value: c.conn_id, label: `${c.conn_id} (${c.database})`, shared: false,
    }));
    const shared = (sharedConns || []).map((c) => ({
      value: c.conn_id, label: `${c.conn_id} (${c.db_type}, paylaşılan)`, shared: true,
    }));
    return own.concat(shared);
  }

  /** Bu bağlantı kimliği paylaşılan bağlantılardan biri mi? */
  function isShared(sharedConns, connId) {
    return (sharedConns || []).some((c) => c.conn_id === connId);
  }

  /**
   * Paylaşılan bağlantının izinli tablo seçenekleri, ada göre sıralı.
   * Dönen her öğe: { text, schema, table }. text: şemalıysa 'şema.tablo', değilse 'tablo'.
   */
  function sharedTableOptions(sharedConns, connId) {
    const conn = (sharedConns || []).find((c) => c.conn_id === connId);
    if (!conn) return [];
    return (conn.tables || [])
      .map((t) => {
        const schema = t.schema_name || null;
        const table = t.table_name;
        return { text: schema ? `${schema}.${table}` : table, schema, table };
      })
      .sort((a, b) => (a.text < b.text ? -1 : a.text > b.text ? 1 : 0));
  }

  /** Seçenek metninden tabloyu bulur; yoksa null. */
  function findSharedTable(options, text) {
    return (options || []).find((o) => o.text === text) || null;
  }

  /**
   * "Önerilen İlişkiler" yalnız bağlantının sahibinde çalışır (analiz sonucu sahibe aittir;
   * alıcıda sunucu 404 döner). Paylaşılan bağlantıda false.
   */
  function canSuggestRelationships(sharedConns, connId) {
    return !isShared(sharedConns, connId);
  }

  return { connectionOptions, isShared, sharedTableOptions, findSharedTable, canSuggestRelationships };
});
