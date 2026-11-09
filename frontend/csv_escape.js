/**
 * csv_escape.js — CSV yazım yardımcıları (saf fonksiyonlar, DOM yok).
 * Tarayıcıda index.html bunu app.js'ten önce klasik script olarak yükler; window.SuperBICsv üzerinden erişilir.
 * Node.js'te require() ile de yüklenebilir (tests/frontend/csv_escape.test.js).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SuperBICsv = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  /**
   * CSV hücresini güvenli hale getirir. Değer ; " veya satır sonu içeriyorsa tırnak içine alınır ve içindeki tırnaklar çift tırnak yapılır. null/undefined boş metin olur.
   * CSV formül enjeksiyonu: = + - @ TAB veya CR ile başlayan METİN değerlerin başına ' eklenir (OWASP önerisi). Sayılar (typeof number) olduğu gibi kalır.
   */
  function csvEscape(val) {
    if (val === null || val === undefined) return "";
    let s = String(val);
    if (typeof val === "string" && /^[=+\-@\t\r]/.test(s)) s = "'" + s;
    if (/[",\r\n;]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
    return s;
  }

  /**
   * Kolon adları ve satırları noktalı virgüllü (;) CSV metnine çevirir. Başta BOM (﻿) eklenir ki Excel Türkçe karakterleri doğru okusun. Satırlar \r\n ile ayrılır.
   */
  function rowsToCsv(cols, rows) {
    const BOM = "﻿";
    const lines = [cols.map(csvEscape).join(";")];
    for (const row of rows) lines.push(row.map(csvEscape).join(";"));
    return BOM + lines.join("\r\n");
  }

  return { csvEscape, rowsToCsv };
});
