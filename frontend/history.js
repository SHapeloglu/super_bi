/**
 * history.js — dashboard geri al / yinele geçmişi (saf fonksiyonlar, DOM yok).
 * Geçmiş: anlık görüntülerin (JSON metni) dizisi. index: şu an hangi görüntüde olduğumuz (-1 = kayıt yok).
 * Fonksiyonlar geçmişi DEĞİŞTİRMEZ; yeni dizi/indeks döner.
 * Tarayıcıda index.html bunu app.js'ten önce klasik script olarak yükler; window.SuperBIHistory üzerinden erişilir.
 * Node.js'te require() ile de yüklenebilir (tests/frontend/history.test.js).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SuperBIHistory = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  // Bellek tasarrufu: en fazla bu kadar anlık görüntü saklanır.
  const LIMIT = 50;

  /**
   * Yeni bir görüntü ekler. İmlecin ötesindeki (geri alınmış) kayıtlar silinir; limit aşılırsa en eski kayıt düşer.
   * Dönen: { history, index } — index her zaman son kaydı gösterir.
   */
  function push(history, index, snapshot, limit = LIMIT) {
    const next = history.slice(0, index + 1);
    next.push(snapshot);
    if (next.length > limit) next.shift();
    return { history: next, index: next.length - 1 };
  }

  /** Bir adım geri alınabilir mi? */
  function canUndo(index) {
    return index > 0;
  }

  /** Bir adım ileri alınabilir mi? */
  function canRedo(history, index) {
    return index < history.length - 1;
  }

  /** Geri al: imleci bir geri taşır; en eskide aynı kalır. */
  function undo(history, index) {
    return canUndo(index) ? index - 1 : index;
  }

  /** İleri al: imleci bir ileri taşır; en yenide aynı kalır. */
  function redo(history, index) {
    return canRedo(history, index) ? index + 1 : index;
  }

  /** Verilen indeksteki görüntü; geçersizse undefined. */
  function snapshotAt(history, index) {
    if (index < 0 || index >= history.length) return undefined;
    return history[index];
  }

  return { LIMIT, push, canUndo, canRedo, undo, redo, snapshotAt };
});
