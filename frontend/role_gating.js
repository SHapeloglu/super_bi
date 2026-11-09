/**
 * role_gating.js — rol bazlı arayüz kapısı (saf fonksiyonlar, DOM yok).
 * Sunucu yetkiyi zaten 403 ile zorluyor; bu dosya yalnız viewer'a yetkisiz düğmeleri göstermemek ve
 * paylaşılan (read) veri setlerinin üzerine yazma denememesi için kullanılır.
 * Tarayıcıda index.html bunu app.js'ten önce klasik script olarak yükler; window.SuperBIRole üzerinden erişilir.
 * Node.js'te require() ile de yüklenebilir (tests/frontend/role_gating.test.js).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SuperBIRole = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  /**
   * Bağlantı ekleme formu yalnız admin'e gösterilir (sunucu da yalnız admin'e izin verir).
   */
  function shouldShowConnectionForm(role) {
    return role === "admin";
  }

  /**
   * 'Üzerine yaz' hedefi olabilecek veri setlerini süzer.
   * Admin: hepsi. Diğerleri: permission === "write" olanlar ya da sahibi oldukları. permission === "read" olanlar listede gelmez.
   */
  // Kaydetmede isim eşleşmesi yalnız kullanıcının KENDİ veri setleriyle yapılır (admin dahil).
  // Başkasının (paylaşılmış) veri seti isimle sessizce üzerine yazılmaz; yeni kayıt oluşturulur.
  function writableDatasets(datasets, role, userId) {
    if (!Array.isArray(datasets) || userId == null) return [];
    return datasets.filter((d) => d && d.owner_id === userId);
  }

  return { shouldShowConnectionForm, writableDatasets };
});
