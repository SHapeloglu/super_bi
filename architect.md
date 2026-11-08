# architect.md — SuperBI Mimarisi

Durum: 2026-10-25. Eski `docs/ARCHITECTURE.md` (2026-09-16) bu dosyaya birleştirildi; eski dosya silindi (yedek: `/root/yedekler/md-birlestirme-20261025/opt/superbi/docs/ARCHITECTURE.md`).

## Bileşenler

```
Tarayıcı
  │  https://superbi.bidanismanlik.com.tr
  ▼
host nginx  ──► /          → /opt/superbi/frontend (statik: index.html, app.js, api.js, style.css)
            └─► /api/      → 127.0.0.1:8000  (Docker konteyner: superbi)
                              │
                              ▼
                  FastAPI (app/main.py)
                    api/        auth, connections, schema, analyze, query, dashboard, datasets, history, drivers
                    auth/       JWT (jwt_core.py), kullanıcı deposu
                    core/       connector_registry (DRIVER_MAP), crypto (Fernet), repository (ConnectionMeta)
                    services/   sql_builder, expression_builder, sbx_compiler (+ grammar.lark),
                                granularity_analyzer, query_executor, nlq/ (planlama aşamasında)
                    deps.py     bağlantı motoru yönetimi; restart sonrası otomatik yeniden bağlanma
                              │
          ┌───────────────────┼────────────────────────┐
          ▼                   ▼                        ▼
  SQLite meta           kullanıcı veri kaynakları    (ileride) DuckDB ingest
  /opt/superbi/data     PostgreSQL / MySQL / MSSQL / Oracle
  (./data → /data)      ortak-db ağı üzerinden host adıyla
```

Frontend: Vanilla HTML/CSS/JS, Apache ECharts; Undo/Redo, dashboard şablonları, şema seçici, "Önerilen İlişkiler".

Modüller (`/opt/superbi/app`): `models/schemas.py` (CalculatedFieldDef, JoinDef, FilterDef, ALLOWED_OPERATORS), `core/connector_registry.py` (sqlite/postgresql/mysql/mssql/oracle), `core/crypto.py`, `core/repository.py` (password_enc, port_ alanları), `services/expression_builder.py` (SBX + SQL uyum modu, v2, `;` reddi), `services/sbx_compiler.py`, `services/query_executor.py`, `api/analyze.py`, `api/schema.py`.

## Dağıtım

- `docker-compose.yml`: servis `superbi`, `image: superbi:latest`, `restart: unless-stopped`, `mem_limit: 384m`, port `127.0.0.1:8000:8000`, ağ `ortak-db` (external).
- Veri: `./data` → `/data` (SQLite). Yedek: `scripts/backup.sh` → `/opt/superbi/backups/superbi_YYYY-AA-GG_030002.db.gz` (her gece 03:00).
- AutoSleep (`/opt/autosleep/ek_projeler.py`) boşta kalınca `superbi` konteynerini durdurur (2026-10-18 itibarıyla Docker'a geçti). Bu bilinçli davranış, hata değildir.
- Bağımlılıklar: `requirements.txt` (sqlglot==25.34.1, lark, FastAPI ekosistemi), `Dockerfile`, host nginx, `ortak-db` ağı.

## Veri Akışı (sorgu)

1. Kullanıcı Sorgu Oluşturucu'da alan/filtre/hesaplanmış alan (SBX) seçer.
2. `sbx_compiler` SBX formülünü sqlglot ile hedef dialekte SQL'e çevirir (`_p()` ile parantezler zorunlu).
3. `sql_builder` sorguyu kurar (şema-qualified FROM; MSSQL: TOP / OFFSET-FETCH).
4. `query_executor` bağlantı üzerinden çalıştırır; sonuç cache'lenir.

## Önemli Kararlar

- **Kendi kendine barındırma (self-hosted):** veri satırları buluta gitmez (veri egemenliği). BYOK LLM isteğe bağlı, varsayılan kapalı.
- **sqlglot ==25.34.1 sabit:** sürüm yükseltmesi SBX derlemesini kırabilir. Yükseltmeden önce `expression_builder` güvenlik testleri çalıştırılır.
- **Operatör önceliği (`_p()`):** elle inşa edilen sqlglot expression'larında render sırasında parantez garanti değil. Binary, Connector, Unary, Not node'ları otomatik `exp.Paren()` ile sarılır. Fazla parantez zararsız; eksik parantez sessiz yanlış sonuç üretir.
- **Noktalı virgül reddi:** sqlglot 30.12.0 `;` içeren formülü reddederken 25.34.1 sessizce kırpıyordu. `expression_builder.py` `;` içeren formülleri sürümden bağımsız açıkça reddeder.
- **Parola şifreleme (Fernet):** `ConnectionMeta.password_enc`. Anahtar `DATALENS_DB_ENCRYPTION_KEY` (ortam değişkeni; değeri md/git'te yok). Anahtar kaybolursa kayıtlı parolalar kurtarılamaz; JWT secret gibi yedeklenmeli. Neden: PostgreSQL/MySQL/MSSQL parolaları önceden kasıtlı saklanmıyordu, her restart'ta yeniden giriliyordu. `deps.py` restart sonrası tüm dialect'ler için (SQLite dahil) otomatik engine kurar. (Eski kayıt 2026-09-16: anahtar systemd servis dosyasındaydı; Docker'a geçişle değişti.) Gerçek PostgreSQL ile test edildi; parola DB'de şifreli saklanıyor.
- **Bağlantı host adı:** `127.0.0.1` konteynerden çalışmaz; ortak DB'ler `postgres-ortak` / `mysql-ortak` adıyla bağlanır.
- **Kural tabanlı NLQ:** Türkçe doğal dil sorgusu LLM olmadan, niyet kalıplarıyla.
- **Granularity-first:** NLQ, yanlış grain'de JOIN'leri tespit edip önlemek için tablo grain/ilişki katmanını kullanır (aşağıda).
- **Sema farkındalığı:** şu an yalnız canlı Sorgu Oluşturucu akışında (preview/run/stream). Kaydedilmiş dataset ve widget akışı henüz taşımıyor (bkz. backlog.md).
- **MS_Description bilinçli kullanılmıyor:** granularity tespiti deterministik olduğu için native açıklamalar girdi olmaz; yalnız LLM bağlamı için düşünülür.

## SBX (SuperBI Expression Language)

Giriş: DAX benzeri sözdizimi (`[Alan]`, `FUNC(...)`, operatörler). Çıkış: çok dialekt SQL (CASE WHEN, fonksiyonlar vb.).

Akış: metin → Lark LALR parser (`grammar.lark`) → parse ağacı → SBXTransformer (Lark→sqlglot; her operatör `_p()` ile) → sqlglot AST (elle inşa) → `_p()` parantezleme → dialekte özgü render → SQL → query execution.

**Kademe 1 — tamam** (2026-08-16; grammar + compiler + 17 fonksiyon, 4 dialekt; 5/5 senaryo):
- DAX benzeri: IF, DIVIDE (sıfır koruması), ROUND, CONCATENATE
- SQL: SUM, AVG, COUNT, MIN, MAX
- String: UPPER, LOWER, LEN, TRIM
- Date: DATEDIFF
- Null: ISNULL / COALESCE

Kısıt: sqlglot pin ==25.34.1 (versiyon spesifik AST ayrışımları).

**Kademe 2 (planlı):** measure + dashboard filtre bağlamı. **Kademe 3 (opsiyonel):** VAR/RETURN.

## SQL Builder — Şema Desteği ve Dialekt Farkları

Sorun (kök neden): sql_builder her dialekt için tek `LIMIT n [OFFSET m]` üretiyordu; T-SQL'de LIMIT yok. `base_table` hiç şema öneki almıyordu.

Çözüm: `QueryRequest` / `QueryRunRequest` / `SQLPreviewRequest` → `schema_name`; `sql_builder.build(..., schema=schema_name, db_type=...)`; `qualified_table = f"{schema}.{base_table}" if schema else base_table`.

| Dialekt | Satır sınırlama |
|---|---|
| oracle | `FETCH FIRST n ROWS ONLY` / `OFFSET m ROWS FETCH NEXT n ROWS ONLY` |
| mssql | offset=0 → `SELECT TOP n`; offset>0 → `OFFSET...FETCH NEXT` (ORDER BY yoksa `ORDER BY (SELECT NULL)`) |
| postgres / mysql / sqlite | `LIMIT n [OFFSET m]` |

Şema keşfi (`/api/schema`): `GET /{conn_id}/schemas`; `GET /{conn_id}/tables?schema=X`; `GET /{conn_id}/tables/{t}/columns?schema=X`; `GET /{conn_id}/tables/{t}/foreign-keys?schema=X`.

Named-schema DB'lerde (ör. AdventureWorks2022) asıl tablolar dbo dışındadır (Sales, Production, Person, HumanResources, Purchasing).

## Tablo Granularity + İlişki Katmanı

Amaç: NLQ'nun yanlış grain'de JOIN'leri tespit edip önlemesi.

1. **Grain tespiti:** COUNT(*) vs COUNT(DISTINCT col); %100 tekillik = anahtar sütun.
2. **Sütun sınıflandırma:** kardinalite + tip → identifier / categorical / metric / date_axis.
3. **Referans bütünlüğü ve ilişki bulma:**
   a) DB PK/FK metadata (sqlalchemy.inspect) → source=fk_constraint, confidence=1.0
   b) İstatistiksel çıkarım (orphan testi, LEFT JOIN) → source=inferred

Depolama: `table_profiles` + `datasets_relationships` (SQLite).

API: `POST /api/analyze/{conn_id}/tables` (body: schema_name?, tables?, all_schemas?); `POST /api/analyze/{conn_id}/relationship`; `GET /api/analyze/{conn_id}/results` (DB-geneli).

Frontend: Bağlantılar sayfasında "Analiz Et" / "Sonuçlar" (tüm kullanıcı şemaları, sistem şemaları hariç); Sorgu Oluşturucu'da "Önerilen İlişkiler" (tek tık / "Tümünü Ekle").

Bağımlılık: DuckDB yok; multi-DB push-down ile çalışır.

Doğrulama (AdventureWorks2022, Sales şeması): 34 FK ilişkisi. Sales.Customer grain = CustomerID; Sales.SalesOrderDetail grain = [SalesOrderID, SalesOrderDetailID].

## Kural Tabanlı Türkçe NLQ (Kademe 1 — planlama/kısmi kod)

Felsefe: LLM yok, maliyet sıfır, deterministik, test edilebilir.

Ön koşul (granularity + ilişki + Önerilen İlişkiler) tamam.

6 niyet kalıbı:
1. Top-N sıralama (önerilen ilk adım; sql_builder order_by/limit altyapısı hazır)
2. Boyuta göre agregasyon
3. Zaman serisi / trend
4. Filtrelenmiş sorgu
5. Basit metrik
6. SBX hesaplanmış alan

Yöntem: niyet tespiti anahtar kelime + regex; slot doldurma fuzzy string matching; doldurulan slotlar JSON plana dönüşür → `sql_builder` → SQL.

Kod durumu: `app/services/nlq/` altında `nlq_engine.py`, `intent_patterns.py`, `slot_filler.py`, `plan_builder.py`, `synonyms.py` var (2026-10-24 bulguları için bkz. task.md). Hangi kalıbın tamamlandığı doğrulanmalı.

Kapsam dışı: "Bu soruyu anlayamadım. Şu kalıpları deneyebilirsiniz: ..." + örnekler.

Opsiyonel (ileride, varsayılan kapalı): BYOK LLM fallback — yalnız kalıp dışı sorularda, yalnız şema metadata; satır verisi asla gönderilmez.

## Dashboard Yerleşim Şablonları

Dashboard, mm cinsinden serbest konumlu bir "sayfa": `page_w_mm=297`, `page_h_mm=210`. Widget: `{id, type, x, y, w, h, title, query_id, color}`. Koordinatlar 297x210 referansına göre oranlı ölçeklenir.

Şablonlar: classic (Klasik), focus (Odak Grafik), metrics (Metrik Yoğun), grid (Izgara), mixed (Karma) + Boş. "+ Yeni Dashboard" ile seçilir; mevcut dashboard'da toolbar'dan "Şablon Uygula".

## Undo/Redo

`app.js` içinde uygulandı. Uçtan uca test tamamlanmadı (bkz. task.md).

## Planlanan Görünümler

- **Görsel ilişki editörü (orta öncelik):** `table_profiles` + `datasets_relationships` verisini node-link diyagram olarak gösterir. Teknik seçenek: D3 force-directed ya da basit SVG.
- **Native kolon açıklamaları → LLM bağlamı (düşük öncelik):** MSSQL `sys.extended_properties`, Oracle `USER_COL_COMMENTS` / `ALL_COL_COMMENTS`, PostgreSQL `pg_description`, MySQL `COLUMN_COMMENT`. Yalnız LLM bağlamı için; granularity tespitine girdi olmaz.
- **DuckDB ingest (ileride):** kaynak DB'lerden çekme, cross-DB JOIN, incremental refresh. Ayrıntı backlog.md.

## Veri Kaynakları ve Dialektler

Desteklenen: Oracle XE, MSSQL (named-schema destekli), MySQL, PostgreSQL, SQLite. Oracle XE, MSSQL, MySQL, PostgreSQL Docker konteynerlerinde canlı veri kaynağı olarak çalışır. Push-down mimarisi: sql_builder şema farkında.

## Kapasite

Kayıtlı değer (eski kayıt 2026-09-16): VPS 7.8 GB RAM, swap dolu, 12 Docker konteyneri. Güncel kapasite doğrulanmalı. Konteyner `mem_limit` 384 MB; DuckDB ingest öncesi RAM planlaması gerekli.

## Anahtar Kararlar Özeti

1. sqlglot ==25.34.1 pin — güvenlik whitelist temeli
2. `_p()` parantezleme — operatör önceliği garantisi
3. Fernet şifreleme — bağlantı parolaları at-rest şifreli
4. Noktalı virgül reddi — formül güvenliği sürümden bağımsız
5. Kural tabanlı NLQ — LLM yok, maliyet sıfır
6. Granularity-first — tamamlandı
7. Şema farkındalığı — yalnız canlı Sorgu Oluşturucu akışında
8. Veri egemenliği — self-hosted, BYOK opsiyonel
9. MS_Description ayrımı — deterministik tespitte kullanılmıyor
10. Dokümantasyon tek kaynağı — kök dizindeki beş dosya (2026-10-25; eski kayıt 2026-09-16 `docs/` diyordu)
