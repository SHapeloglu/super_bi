/**
 * csv_escape.js birim testi. Çalıştırma: node tests/frontend/csv_escape.test.js
 */
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const { csvEscape, rowsToCsv } = require("../../frontend/csv_escape.js");

let passed = 0;
function check(name, actual, expected) {
  assert.equal(actual, expected, name);
  passed++;
}

// Formül enjeksiyonu: metin değerler ' ile kaçırılır
check("=", csvEscape("=1+1"), "'=1+1");
check("+", csvEscape("+1"), "'+1");
check("- (metin)", csvEscape("-5"), "'-5");
check("@", csvEscape("@SUM(A1)"), "'@SUM(A1)");
check("TAB", csvEscape("\tx"), "'\tx");
check("CR (tırnaklanır)", csvEscape("\rx"), "\"'\rx\"");
check("formül + tırnak", csvEscape('=HYPERLINK("u")'), "\"'=HYPERLINK(\"\"u\"\")\"");

// Sayılar ve normal metinler etkilenmez
check("negatif sayı", csvEscape(-5), "-5");
check("ondalık", csvEscape(3.5), "3.5");
check("sıfır", csvEscape(0), "0");
check("boolean", csvEscape(true), "true");
check("ortadaki tire", csvEscape("normal-metin"), "normal-metin");
check("boş metin", csvEscape(""), "");
check("null", csvEscape(null), "");
check("undefined", csvEscape(undefined), "");

// Ayırıcı ve tırnak kaçışı
check("noktalı virgül", csvEscape("a;b"), '"a;b"');
check("tırnak", csvEscape('say "hi"'), '"say ""hi"""');
check("satır sonu", csvEscape("a\nb"), '"a\nb"');

// Satır birleştirme: BOM + ; ayırıcı + \r\n
check("rowsToCsv", rowsToCsv(["a", "b"], [[1, "=x"], ["-2", 3]]), "﻿a;b\r\n1;'=x\r\n'-2;3");

// Tarayıcı yolu: module yokken window.SuperBICsv tanımlanmalı
const src = fs.readFileSync(path.join(__dirname, "../../frontend/csv_escape.js"), "utf8");
const sandbox = {};
sandbox.self = sandbox;
vm.runInNewContext(src, sandbox);
check("tarayıcı global", sandbox.SuperBICsv.csvEscape("=1"), "'=1");

console.log(`csv_escape: ${passed} test geçti`);
