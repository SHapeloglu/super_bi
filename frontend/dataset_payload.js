/**
 * dataset_payload.js — "Dataset Olarak Kaydet" istek gövdesini kurar (saf fonksiyon, DOM yok).
 * Tarayıcıda index.html bunu app.js'ten önce klasik script olarak yükler; window.SuperBIDatasetPayload üzerinden erişilir.
 * Node.js'te require() ile de yüklenebilir (tests/frontend/dataset_payload.test.js).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SuperBIDatasetPayload = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  /**
   * Sorgu şeklinden (buildQueryShape çıktısı) veri seti kayıt gövdesini üretir.
   * - schema_name yalnız şema seçiliyse eklenir (boşsa anahtar hiç yazılmaz).
   * - calculated_fields her zaman dizidir ve state'ten kopyalanır (referans paylaşılmaz).
   */
  function buildDatasetPayload(shape, name) {
    const payload = {
      name,
      conn_id: shape.conn_id,
      base_table: shape.base_table,
      fields: shape.fields,
      joins: shape.joins,
      filters: shape.filters,
      group_by: shape.group_by,
      order_by: shape.order_by,
      calculated_fields: (shape.calculated_fields || []).map((cf) => ({ ...cf })),
    };
    if (shape.schema_name) payload.schema_name = shape.schema_name;
    return payload;
  }

  return { buildDatasetPayload };
});
