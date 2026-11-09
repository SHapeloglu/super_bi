/**
 * dataset_payload.js birim testi (Dataset Olarak Kaydet payload'ı). Çalıştırma: node tests/frontend/dataset_payload.test.js
 */
const assert = require("node:assert/strict");
const { buildDatasetPayload } = require("../../frontend/dataset_payload.js");

let passed = 0;
function check(name, fn) {
  fn();
  passed++;
}

const shape = {
  conn_id: "c1",
  base_table: "EMP",
  schema_name: "HR",
  fields: { cols: ["ID", "SAL"] },
  joins: [],
  filters: [{ col: "SAL", op: ">", val: 0 }],
  group_by: [],
  order_by: [{ col: "ID", dir: "asc" }],
  calculated_fields: [{ name: "kdv", formula: "ROUND(SAL * 1.18, 2)" }],
};

check("şema seçiliyse schema_name gönderilir", () => {
  const p = buildDatasetPayload(shape, "ornek");
  assert.equal(p.schema_name, "HR");
});

check("hesaplanmış alanlar gönderilir", () => {
  const p = buildDatasetPayload(shape, "ornek");
  assert.deepEqual(p.calculated_fields, [{ name: "kdv", formula: "ROUND(SAL * 1.18, 2)" }]);
});

check("mevcut alanlar değişmeden kalır", () => {
  const p = buildDatasetPayload(shape, "ornek");
  assert.deepEqual(p, {
    name: "ornek",
    conn_id: "c1",
    base_table: "EMP",
    schema_name: "HR",
    fields: { cols: ["ID", "SAL"] },
    joins: [],
    filters: [{ col: "SAL", op: ">", val: 0 }],
    group_by: [],
    order_by: [{ col: "ID", dir: "asc" }],
    calculated_fields: [{ name: "kdv", formula: "ROUND(SAL * 1.18, 2)" }],
  });
});

check("şema seçili değilse schema_name hiç eklenmez", () => {
  const p = buildDatasetPayload({ ...shape, schema_name: null }, "ornek");
  assert.equal("schema_name" in p, false);
});

check("boş string şema da eklenmez", () => {
  const p = buildDatasetPayload({ ...shape, schema_name: "" }, "ornek");
  assert.equal("schema_name" in p, false);
});

check("hesaplanmış alan yoksa boş dizi gönderilir", () => {
  const p = buildDatasetPayload({ ...shape, calculated_fields: undefined }, "ornek");
  assert.deepEqual(p.calculated_fields, []);
});

check("dönen calculated_fields state'e referans değildir", () => {
  const p = buildDatasetPayload(shape, "ornek");
  p.calculated_fields[0].formula = "DEĞİŞTİ";
  assert.equal(shape.calculated_fields[0].formula, "ROUND(SAL * 1.18, 2)");
});

console.log(`dataset_payload: ${passed} test geçti`);
