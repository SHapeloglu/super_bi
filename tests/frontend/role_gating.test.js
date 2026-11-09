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

// Viewer: sahip olunan + write izni olanlar; read olanlar hariç
check("viewer yazılabilirleri",
  writableDatasets(list, "viewer", "u1").map((d) => d.dataset_id),
  [1, 3, 4]);
check("viewer sahibi olmadığı read veri setini görmez",
  writableDatasets([list[1]], "viewer", "u1"), []);
check("sahip olmayan viewer, yalnız write izinli olanları görür (read olanlar hariç)",
  writableDatasets(list, "viewer", "u9").map((d) => d.dataset_id),
  [1, 3]);

// Admin: değişmez, hepsi
check("admin hepsini görür",
  writableDatasets(list, "admin", "u1").map((d) => d.dataset_id),
  [1, 2, 3, 4]);

// Girdi koruması
check("liste yoksa boş", writableDatasets(null, "viewer", "u1"), []);
check("boş liste", writableDatasets([], "viewer", "u1"), []);

console.log(`role_gating.test.js: ${passed} kontrol geçti`);
