/**
 * role_gating.js birim testi (viewer yetki gizleme yardımcıları). Çalıştırma: node tests/frontend/role_gating.test.js
 */
const assert = require("node:assert/strict");
const { shouldShowConnectionForm, writableDatasets } = require("../../frontend/role_gating.js");

let passed = 0;
function check(name, actual, expected) {
  assert.deepEqual(actual, expected, name);
  passed++;
}

// Bağlantı formu yalnız admin'e gösterilir
check("admin formu görür", shouldShowConnectionForm("admin"), true);
check("viewer formu görmez", shouldShowConnectionForm("viewer"), false);
check("editor formu görmez", shouldShowConnectionForm("editor"), false);
check("rol yok", shouldShowConnectionForm(null), false);
check("rol undefined", shouldShowConnectionForm(undefined), false);

const list = [
  { dataset_id: 1, name: "benim", owner_id: "u1", permission: "write" },
  { dataset_id: 2, name: "paylasilan_read", owner_id: "u2", permission: "read" },
  { dataset_id: 3, name: "paylasilan_write", owner_id: "u2", permission: "write" },
  { dataset_id: 4, name: "sahibim_ama_read", owner_id: "u1", permission: "read" },
];

// İsim eşleşmesi yalnız sahip olunan veri setleriyle (write paylaşımı dahil değil)
check("sahip olunanlar (read olan kendi dahil)",
  writableDatasets(list, "viewer", "u1").map((d) => d.dataset_id),
  [1, 4]);
check("paylaşılan write veri seti eşleşmeye girmez",
  writableDatasets([list[2]], "viewer", "u1"), []);
check("sahip olmayan kullanıcı hiçbir şeyi eşleştirmez",
  writableDatasets(list, "viewer", "u9"), []);
check("admin da yalnız kendi veri setlerini eşleştirir (başkasınınkini ezmez)",
  writableDatasets(list, "admin", "u1").map((d) => d.dataset_id),
  [1, 4]);
check("userId yoksa boş", writableDatasets(list, "admin", undefined), []);

// Girdi koruması
check("liste yoksa boş", writableDatasets(null, "viewer", "u1"), []);
check("boş liste", writableDatasets([], "viewer", "u1"), []);

console.log(`role_gating.test.js: ${passed} kontrol geçti`);
