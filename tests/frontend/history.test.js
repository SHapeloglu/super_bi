/**
 * history.js birim testi (dashboard geri al / yinele geçmişi). Çalıştırma: node tests/frontend/history.test.js
 * Geçmiş anlık görüntülerin (JSON metni) listesi ve bir imleçtir; index = şu anki görüntünün konumu (-1 = kayıt yok).
 */
const assert = require("node:assert/strict");
const H = require("../../frontend/history.js");

let passed = 0;
function check(name, fn) {
  fn();
  passed++;
  console.log("PASS", name);
}

// Boş geçmiş
check("boş geçmişte geri al/yinele kapalı", () => {
  assert.equal(H.canUndo(-1), false);
  assert.equal(H.canRedo([], -1), false);
});

// push: ilk kayıt
check("ilk push indeksi 0 yapar", () => {
  const r = H.push([], -1, "s1");
  assert.deepEqual(r.history, ["s1"]);
  assert.equal(r.index, 0);
});

// push: sonraki kayıtlar sona eklenir
check("push sona ekler ve indeksi son kayda taşır", () => {
  let st = H.push([], -1, "s1");
  st = H.push(st.history, st.index, "s2");
  st = H.push(st.history, st.index, "s3");
  assert.deepEqual(st.history, ["s1", "s2", "s3"]);
  assert.equal(st.index, 2);
});

// Geri al / yinele imleci
check("undo imleci bir geri taşır, en eskide durur", () => {
  const h = ["s1", "s2", "s3"];
  assert.equal(H.undo(h, 2), 1);
  assert.equal(H.undo(h, 1), 0);
  assert.equal(H.undo(h, 0), 0);
});

check("redo imleci bir ileri taşır, en yenide durur", () => {
  const h = ["s1", "s2", "s3"];
  assert.equal(H.redo(h, 0), 1);
  assert.equal(H.redo(h, 1), 2);
  assert.equal(H.redo(h, 2), 2);
});

check("canUndo/canRedo sınırları", () => {
  const h = ["s1", "s2"];
  assert.equal(H.canUndo(0), false);
  assert.equal(H.canUndo(1), true);
  assert.equal(H.canRedo(h, 1), false);
  assert.equal(H.canRedo(h, 0), true);
});

// Geri al sonrası yeni işlem ileri geçmişi siler (redo dalı temizlenir)
check("geri alındıktan sonra push ileri dalı siler", () => {
  let st = H.push([], -1, "s1");
  st = H.push(st.history, st.index, "s2");
  st = H.push(st.history, st.index, "s3");
  const back = H.undo(st.history, st.index); // 1
  const after = H.push(st.history, back, "yeni");
  assert.deepEqual(after.history, ["s1", "s2", "yeni"]);
  assert.equal(after.index, 2);
  assert.equal(H.canRedo(after.history, after.index), false);
});

// Geri al + yinele aynı görüntüye döner
check("undo sonra redo aynı anlık görüntüyü verir", () => {
  let st = H.push([], -1, "{\"a\":1}");
  st = H.push(st.history, st.index, "{\"a\":2}");
  const u = H.undo(st.history, st.index);
  assert.equal(H.snapshotAt(st.history, u), "{\"a\":1}");
  const r = H.redo(st.history, u);
  assert.equal(H.snapshotAt(st.history, r), "{\"a\":2}");
});

// Üst sınır: en fazla LIMIT kayıt, en eski düşer
check("LIMIT 50 ve en eski kayıt düşer", () => {
  assert.equal(H.LIMIT, 50);
  let st = { history: [], index: -1 };
  for (let i = 1; i <= 51; i++) st = H.push(st.history, st.index, "s" + i);
  assert.equal(st.history.length, 50);
  assert.equal(st.history[0], "s2");
  assert.equal(st.history[49], "s51");
  assert.equal(st.index, 49);
});

// snapshotAt sınır dışı indekste undefined
check("snapshotAt geçersiz indekste undefined", () => {
  assert.equal(H.snapshotAt(["s1"], -1), undefined);
  assert.equal(H.snapshotAt(["s1"], 5), undefined);
});

// push girdi dizisini değiştirmez (saf fonksiyon)
check("push girdi geçmişini değiştirmez", () => {
  const h = ["s1"];
  H.push(h, 0, "s2");
  assert.deepEqual(h, ["s1"]);
});

console.log(`\n${passed} kontrol geçti`);
