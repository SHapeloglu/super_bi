# Session Notu — Temmuz 2026 (tarih tam bilinmiyor, dosya mtime: 12-13 Temmuz)

## Tamamlandi

### 1. Baglanti Sifreleme (Fernet)
PostgreSQL/MySQL/MSSQL baglanti parolalari artik sifrelenip saklaniyor,
restart sonrasi otomatik yeniden baglaniyor.
- Yeni: app/core/crypto.py
- Degisen: repository.py, sqlite_store.py, connections.py, deps.py
- Gercek PostgreSQL sunucusuyla test edildi

### 2. Formul Guvenligi — Noktali Virgul Reddi
sqlglot surum farkina bagli tutarsiz davranis kapatildi,
expression_builder.py'de ; artik acikca reddediliyor. sqlglot ==25.34.1'e
tam surume sabitlendi.

---

# Session Notu — 2026-08-16

## Tamamlanan
1. SBX Kademe 1 — Prototip -> Sunucuya entegrasyon
   - Grammar: lark LALR parser, 4 dialect'e SQL donusumu
   - Fonksiyonlar: IF, DIVIDE, ROUND, CONCAT, DATEDIFF, ISNULL, SUM/AVG/COUNT/MIN/MAX
   - Test: 5/5 senaryoda basarili
2. DIALECT_MAP guncelleme

---

# Session Notu — 2026-08-27

## Tamamlandi
1. SBX Compiler Parantez Onceligi Bug Fix — _p() helper, 4 dialect'te
   dogrulandi, deploy edildi (md5: 39a99468c2600a31012f002cd307edc6)
2. Rekabet Analizi Guncellendi
3. Turkce NLQ Tasarimi (Kademe 1) Onaylandi

---

# Session Notu — 2026-09-11

## Tamamlandi — Granularity + Iliski Katmani (backend, tam stack)
1. sqlite_store.py — table_profiles + datasets_relationships tablolari
2. granularity_analyzer.py — discover_fk_relationships(), detect_grain(),
   classify_columns(), profile_table()
3. app/api/analyze.py — 3 endpoint
4. AdventureWorks2022'de dogrulandi: 34 FK iliskisi

## Sonraki Adim
- Dashboard yerlesim sablonlari

---

# Session Notu — 2026-09-14

## Tamamlanan
1. Dashboard Yerlesim Sablonlari — 5 preset + Bos
2. Granularity + Iliski Katmaninin Frontend Entegrasyonu
3. Cok Semali Veritabani Destegi — schema.py'ye ?schema=,
   sql_builder.py'ye MSSQL TOP/OFFSET-FETCH
4. "Analiz Et" DB-Geneli + Sorgu Olusturucu'da Onerilen Iliskiler

## Sonraki Adimlar
1. Kural Tabanli Turkce NLQ (Kademe 1) — Top-N kalibi
2. Dogrulama: Dataset/Widget Sema Destegi
3. DuckDB Ingest Katmani

---

# Session Notu — 2026-09-16

## Tamamlandi
Dokumantasyon senkronizasyonu. Sunucudaki .md dosyalarinin kodun 3-4
hafta gerisinde kaldigi tespit edildi. Bes dosya (CLAUDE.md,
ARCHITECTURE.md, BACKLOG.md, TASKS.md, SESSION.md) Temmuz'dan bu yana tum
oturumlar birlestirilerek yeniden yazildi. /opt/superbi/docs/ artik tek
dogruluk kaynagi.

## Sonraki Adim
- Kural Tabanli Turkce NLQ (Kademe 1), Top-N kalibi ile baslanacak
