/**
 * shared_connections.js birim testi. Çalıştırma: node tests/frontend/shared_connections.test.js
 * Paylaşılan bağlantılar (alıcı için) ve izinli tablo seçenekleri.
 */
const assert = require("node:assert/strict");
const S = require("../../frontend/shared_connections.js");

let passed = 0;
function check(name, fn) {
  fn();
  passed++;
  console.log("PASS", name);
}

const own = [{ conn_id: "c1", database: "db1", db_type: "postgresql" }];
const shared = [{
  conn_id: "c9", db_type: "mssql", name: "Ortak",
  tables: [
    { schema_name: null, table_name: "sales" },
    { schema_name: "hr", table_name: "people" },
  ],
}];

check("seçenekler: önce kendi bağlantılar, sonra paylaşılanlar (paylaşılan işaretli)", () => {
  const opts = S.connectionOptions(own, shared);
  assert.deepEqual(opts.map((o) => o.value), ["c1", "c9"]);
  assert.equal(opts[0].shared, false);
  assert.equal(opts[1].shared, true);
  assert.match(opts[1].label, /paylaşılan/);
});

check("paylaşılan bağlantı kimliği tanınır", () => {
  assert.equal(S.isShared(shared, "c9"), true);
  assert.equal(S.isShared(shared, "c1"), false);
  assert.equal(S.isShared(undefined, "c9"), false);
});

check("izinli tablo seçenekleri: şemasız metin, şemalı 'şema.tablo'", () => {
  const t = S.sharedTableOptions(shared, "c9");
  assert.deepEqual(t.map((x) => x.text), ["hr.people", "sales"]);
  assert.deepEqual(t[0], { text: "hr.people", schema: "hr", table: "people" });
  assert.deepEqual(t[1], { text: "sales", schema: null, table: "sales" });
});

check("paylaşılmayan bağlantının tablo seçeneği yok", () => {
  assert.deepEqual(S.sharedTableOptions(shared, "c1"), []);
});

check("metinden tablo bulunur; yoksa null", () => {
  const t = S.sharedTableOptions(shared, "c9");
  assert.deepEqual(S.findSharedTable(t, "hr.people"), { text: "hr.people", schema: "hr", table: "people" });
  assert.equal(S.findSharedTable(t, "payroll"), null);
});

console.log(`\n${passed} kontrol geçti`);
