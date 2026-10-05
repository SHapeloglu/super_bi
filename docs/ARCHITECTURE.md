# SuperBI Mimari

## Ust Duzey

Frontend (HTML/CSS/JS): Apache ECharts, Undo/Redo, Dashboard Sablonlari, Sema Secici, Onerilen Iliskiler
  -> FastAPI Backend:
     - SBX Compiler (Lark/sqlglot, _p() helper)
     - SQL Builder (push-down, sema-farkinda)
     - Multi-DB Support (Oracle/MSSQL/MySQL/Postgres)
     - Granularity + Relns (DB-geneli, tamamlandi)
     - Rule-based NLQ (Kademe 1, planning)
     - DuckDB Ingest (cross-DB JOIN, planning)
     - Crypto (crypto.py) — Fernet sifreleme, password_enc, DATALENS_DB_ENCRYPTION_KEY
  -> SQLite (meta), Oracle/MSSQL/MySQL/PostgreSQL (baglanti)

## Bilesenler (/opt/superbi/app)
- main.py: FastAPI entry
- models/schemas.py: Pydantic schemas (CalculatedFieldDef, JoinDef, FilterDef, ALLOWED_OPERATORS)
- core/connector_registry.py: DB connection registry (DRIVER_MAP: sqlite/postgresql/mysql/mssql/oracle)
- core/crypto.py: Fernet sifreleme/cozme (baglanti parolalari)
- core/repository.py: ConnectionMeta CRUD, password_enc/port_ alanlari
- services/sql_builder.py: Query builder + calculated field + sema destegi + MSSQL TOP/OFFSET-FETCH
- services/expression_builder.py: Formul dogrulama (SBX + SQL compat mode, v2, noktali virgul reddi)
- services/sbx_compiler.py: SBX -> SQL derleyici (lark + sqlglot, _p() parantez helper'i)
- services/grammar.lark: SBX dilbilgisi tanimi
- services/granularity_analyzer.py: grain tespiti, sutun siniflandirma, FK/orphan testi
- services/query_executor.py: Query execute
- api/analyze.py: Granularity/iliski analiz endpoint'leri
- api/schema.py: Sema/tablo/kolon kesif endpoint'leri (?schema= destekli)
- deps.py: Baglanti engine yonetimi, restart sonrasi tum dialect'ler icin otomatik reconnect

## Frontend (/opt/superbi/frontend)
- Vanilla HTML/CSS/JS, ECharts visualization
- Dashboard yerlesim sablonlari (5 preset)
- Sorgu Olusturucu: Sema secici, Onerilen Iliskiler

## Veritabani (mevcut)
- SQLite: /opt/superbi/data/superbi.db (metadata)
- Oracle XE, MSSQL, MySQL, PostgreSQL: Docker container'lar, canli veri kaynaklari

---

## Baglanti Sifreleme (Fernet)

Sorun (kok neden): PostgreSQL/MySQL/MSSQL baglanti parolalari hic
saklanmiyordu (kasitli) — servis her restart olduğunda kullanici elle
tekrar girmek zorundaydi.

Cozum:
ConnectionMeta.password_enc <- Fernet ile sifrelenmis parola
  -> app/core/crypto.py: encrypt_password() / decrypt_password()
     key: DATALENS_DB_ENCRYPTION_KEY (systemd servis dosyasinda, DB dosyasindan AYRI konumda)
  -> app/deps.py: restart sonrasi TUM dialect'ler icin (SQLite dahil) otomatik engine kurulumu

Gercek PostgreSQL sunucusuyla test edildi: DB'de parola duz metin degil
gAAAAAB... formatinda saklandigi, engine'ler bellekten silinip servis
restart'i simule edildiginde yeniden baglanmadan sorgunun calistigi
dogrulandi. test_connection endpoint'i de ayni mantiga bagli.

Guvenlik notu: Anahtar DB dosyasindan ayri tutuldugu icin sadece
superbi.db calinmasi parolalari acigac cikarmaz — ama tam bir secrets
vault kadar guclu degil, tek-VPS kurulum icin makul bir yaklasim. Anahtar
kaybolursa onceden sifrelenmis TUM parolalar kurtarilamaz hale gelir.

---

## Formul Guvenligi — Noktali Virgul Reddi

Sorun (kok neden): Sunucudaki sqlglot 25.34.1, test edilen 30.12.0'dan
farkli davraniyordu: "price; DROP TABLE users --" formulu 30.x'te
reddediliyordu, 25.x'te sessizce sadece "price" kismini alip gerisini
atiyordu. Ikisi de fonksiyonel olarak guvenliydi (zararli kisim hic
gercek SQL'e karismadi) ama versiyona bagli, ongorulemez davranisti.

Cozum: expression_builder.py artik noktali virgulu bastan, acikca ve her
surumde tutarli sekilde reddediyor. requirements.txt'te sqlglot >= yerine
==25.34.1'e tam surume sabitlendi.

---

## SBX (SuperBI Expression Language)

### Kademe 1 — Row-level Calculated Field

Giris: DAX-benzeri sozdizimi ([Alan], FUNC(...), operatorler)
Cikis: Multi-dialect SQL (CASE WHEN, fonksiyonlar vs.)

Akis:
Text Input -> Lark LALR Parser (grammar.lark) -> Parse Agaci ->
SBXTransformer (Lark->sqlglot, her operator _p() ile parantez ekler) ->
sqlglot Expression AST (elle insa) -> _p() Parantezleme ->
SQL Render (dialect-specific) -> SQL Text Output -> Query Execution

Fonksiyon Kayit Defteri:
- DAX: IF, DIVIDE (sifir korumasi), ROUND, CONCATENATE
- SQL: SUM, AVG, COUNT, MIN, MAX
- String: UPPER, LOWER, LEN, TRIM
- Date: DATEDIFF
- Null: ISNULL/COALESCE

Bagimlilik Kisiti: sqlglot pin ==25.34.1 — versiyon spesifik AST ayrismalari; upgrade kirilir

### Kademe 2 (Roadmap): Measure + dashboard filtre context
### Kademe 3 (Roadmap): VAR/RETURN, ileri context

---

## SQL Builder — Sema Destegi ve MSSQL Dialect Farklari

Sorun (kok neden): sql_builder.py her dialect icin tek bir LIMIT n
[OFFSET m] sozdizimi uretiyordu (Oracle haric). T-SQL'de LIMIT yok.
base_table hicbir zaman sema prefix'i almiyordu, app/api/schema.py da hic
?schema= parametresi desteklemiyordu.

Cozum:
QueryRequest/QueryRunRequest/SQLPreviewRequest -> schema_name alani eklendi
sql_builder.build(..., schema=schema_name, db_type=...)
  qualified_table = f"{schema}.{base_table}" if schema else base_table
  LIMIT/TOP mantigi dialect'e gore dallanir:
    oracle: FETCH FIRST n ROWS ONLY / OFFSET m ROWS FETCH NEXT n ROWS ONLY
    mssql: offset=0 -> SELECT TOP n ; offset>0 -> OFFSET...FETCH NEXT (ORDER BY yoksa otomatik fallback)
    diger (postgres/mysql/sqlite): LIMIT n [OFFSET m] (degismedi)

Sema kesfi (/api/schema):
GET /api/schema/{conn_id}/schemas
GET /api/schema/{conn_id}/tables?schema=X
GET /api/schema/{conn_id}/tables/{t}/columns?schema=X
GET /api/schema/{conn_id}/tables/{t}/foreign-keys?schema=X

Bilinen sinir: Kaydedilmis dataset'ler ve dashboard widget'lari henuz
schema_name tasimiyor — sadece canli Sorgu Olusturucu akisi sema-farkinda.

---

## Tablo Granularity + Iliski Katmani

Amac: NLQ'nun yanlis grain'de JOIN'leri tespit edip prevent etmesi.

Adimlar:
1. Grain Tespiti: COUNT(*) vs COUNT(DISTINCT col), %100 tekillik = anahtar sutun
2. Sutun Siniflandirma: kardinalite + tip -> identifier/categorical/metric/date_axis
3. Referans Butunlugu & Iliski Bulma:
   a) DB PK/FK metadata (sqlalchemy.inspect) -> source=fk_constraint, confidence=1.0
   b) Istatistiksel cikarim (orphan testi, LEFT JOIN) -> source=inferred

Depolama: table_profiles + datasets_relationships (SQLite)

API (/api/analyze):
POST /api/analyze/{conn_id}/tables (body: schema_name?, tables?, all_schemas?)
POST /api/analyze/{conn_id}/relationship
GET  /api/analyze/{conn_id}/results (DB-geneli)

Frontend: Baglantilar sayfasi "Analiz Et"/"Sonuclar"; Sorgu Olusturucu "Onerilen Iliskiler"

DuckDB Bagimliligi: Yok — multi-DB push-down ile yapilir

MS_Description notu: sp_addextendedproperty/MS_Description bu katmanda
BILINCLI olarak kullanilmiyor — deterministik yaklasimla celisir.

Dogrulama (AdventureWorks2022, Sales semasi): 34 FK iliskisi tespit
edildi. Sales.Customer grain=CustomerID, Sales.SalesOrderDetail
grain=[SalesOrderID, SalesOrderDetailID].

---

## Kural Tabanli Turkce NLQ (Planlanan, Kademe 1)

Felsefe: LLM yok, maliyet sifir, deterministic, test edilebilir
On kosul artik tamam: Granularity + iliski katmani hazir.

6 Niyet Kalibi:
1. Top-N Siralama (ONERILEN ILK ADIM)
2. Boyuta Gore Agregasyon
3. Zaman Serisi/Trend
4. Filtrelenmis Sorgu
5. Basit Metrik
6. SBX Hesaplanmis Alan

Kapsam Disi: "Bu soruyu anlayamadim. Su kaliplari deneyebilirsiniz: ..." + ornekler

Ileride Opsiyonel: BYOK LLM fallback — sadece sema metadata gonderilir, satir verisi asla gitmez.

---

## Gorsel Iliski Editoru (Planlanan, orta oncelik)

table_profiles + datasets_relationships verisini node-link diyagram olarak
gosteren bir gorunum. Teknik secenek: D3.js force-directed graph ya da basit SVG.

## Native Kolon Aciklamalari -> LLM Baglami (Planlanan, dusuk oncelik)

MSSQL sys.extended_properties, Oracle USER_COL_COMMENTS/ALL_COL_COMMENTS,
PostgreSQL pg_description, MySQL COLUMN_COMMENT okuyup LLM'e baglam olarak
vermek.

---

## Veri Kaynaklari & Diyalektler

Desteklenen: Oracle XE, MSSQL (named-schema destekli), MySQL, PostgreSQL, SQLite
Push-down Mimarisi: sql_builder.py sema-farkinda, MSSQL icin TOP/OFFSET-FETCH ayrimi var
Ileride (DuckDB): Cross-database JOIN, incremental ingest layer

## Undo/Redo
Durum: Uygulandi (app.js). Test: End-to-end tamamlanmamis.

## Dashboard Yerlesim Sablonlari

Dashboard'lar mm cinsinden serbest pozisyonlu bir "sayfa"
(page_w_mm=297/page_h_mm=210), widget {id, type, x, y, w, h, title, query_id, color}.

Sablonlar: classic (Klasik), focus (Odak Grafik), metrics (Metrik Yogun),
grid (Izgara), mixed (Karma). Koordinatlar 297x210mm referans, oranli olcekleniyor.

## VPS Kapasite & Sinirlar
Mevcut: Contabo VPS, 7.8GB RAM (swap: 5.8GB dolu), 12 Docker container
Kisitlama: DuckDB ingest layer icin RAM planlamasi gerekli, buyumede 16GB+ veya ayri VPS

## Key Decisions & Constraints
1. sqlglot ==25.34.1 Pin — guvenlik whitelist temeli
2. _p() Parantezleme — operator onceligi garantisi
3. Fernet Sifreleme — baglanti parolalari at-rest sifreli
4. Noktali Virgul Reddi — formul guvenligi surumden bagimsiz
5. Kural Tabanli NLQ — LLM yok, maliyet sifir
6. Granularity-First — TAMAMLANDI
7. Sema-Farkindalik — sadece canli Sorgu Olusturucu akisinda
8. Veri Egemenligi — self-hosted, BYOK opsiyonel
9. MS_Description Ayrimi — deterministik tespit kullanmiyor
10. Dokumantasyon Tek Kaynagi — /opt/superbi/docs/

## Referanslar
- WrenAI: Governed/plan-first NLQ
- Vanna AI: FastAPI + Claude entegrasyon ornegi
- Metabase: Metabot + X-rays
- Superset: Native NLQ yok (SIP-166)

---

Son guncelleme: 2026-09-16 (sunucu-dokuman senkronizasyonu)
