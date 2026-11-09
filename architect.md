# architect.md — SuperBI Mimarisi

Durum: 2026-11-09 (release `127c74d`). Önceki sürüm 2026-10-25'ti. Bu dosya kodla doğrulandı (`app/` altında grep, `release/2026-11-09`). Eski `docs/ARCHITECTURE.md` (2026-09-16) bu dosyaya birleştirildi.

## Bileşenler

```
Tarayıcı
  │  https://superbi.bidanismanlik.com.tr
  ▼
host nginx  ──► /          → /opt/superbi/frontend (statik: index.html, app.js, api.js, csv_escape.js, style.css)
            └─► /api/      → 127.0.0.1:8000  (Docker konteyner: superbi)
                              │
                              ▼
                  FastAPI (app/main.py)
                    startup_check.py   açılışta zorunlu sırlar (fail-closed)
                    api/     auth, users, shares, connections, drivers, schema, analyze, query,
                             dashboard, datasets, history
                    auth/    JWT (jwt_core.py), kullanıcı deposu (user_repository.py)
                    core/    connector_registry (DRIVER_MAP, URL.create), host_policy (DB host kuralları),
                             sqlite_policy (SQLite yol kuralları), crypto (Fernet), repository (ConnectionMeta),
                             sharing (paylaşım izinleri), rls (satır kuralları)
                    services/ sql_builder, expression_builder, sbx_compiler (+ grammar.lark),
                             granularity_analyzer, query_executor, nlq/ (kısmi kod)
                    deps.py  rol guard'ları (require_role), bağlantı motoru yönetimi, restart sonrası yeniden bağlanma
                              │
          ┌───────────────────┼────────────────────────┐
          ▼                   ▼                        ▼
  SQLite meta           kullanıcı veri kaynakları    (ileride) DuckDB ingest
  /opt/superbi/data     PostgreSQL / MySQL / MSSQL   
  (./data → /data)      / Oracle / Doris (pymysql)
                        ortak-db ağı üzerinden host adıyla
```

Frontend: Vanilla HTML/CSS/JS, Apache ECharts (6.0.0, cdnjs; SRI henüz yok). `csv_escape.js` `index.html`'de `app.js`'ten önce yüklenir (`window.SuperBICsv`). Undo/Redo, dashboard şablonları, şema seçici, "Önerilen İlişkiler", dataset çalıştırma (`api.runDataset`).

Modüller (`/opt/superbi/app`), öne çıkanlar:
- `core/sqlite_policy.py`: SQLite yolu yalnız `DATALENS_SQLITE_ROOT` altında; var olan, metadata olmayan dosyalar; salt okunur (`mode=ro`). Kök tanımsızsa SQLite kapalı.
- `core/host_policy.py`: loopback, link-local (169.254.0.0/16), unspecified, multicast, reserved reddedilir. `DATALENS_ALLOWED_DB_HOSTS` tanımlıysa yalnız listedeki hostlar. Hata mesajları sabit; ham metin yalnız logda.
- `core/startup_check.py`: `DATALENS_JWT_SECRET`, `DATALENS_DB_ENCRYPTION_KEY`, `DATALENS_DB` zorunlu; boşsa uygulama açılmaz. Rastgele anahtar üretilmez.
- `core/sharing.py`: paylaşım izinleri (`read` < `write`), `ShareRepository`, `effective_permission`.
- `core/rls.py`: `RuleRepository`, `AttributeRepository`, `build_rls_filters` (kural → `FilterDef`).
- `api/shares.py`: `POST/GET /api/shares`, `DELETE /api/shares/{share_id}`.
- `api/users.py`: `POST /api/users` (yalnız admin), `PUT /api/users/{id}/attributes/{key}` (yalnız admin).
- `api/datasets.py`: CRUD, kurallar (`/{id}/rules`, admin), `POST /api/datasets/{id}/run`.
- `core/connector_registry.py`: sqlite / postgresql / mysql / mssql / oracle / doris (Doris: pymysql, varsayılan port 9030, dialect doris).
- `services/expression_builder.py`: SBX + SQL uyum modu, `;` reddi; sqlglot 25.34.1 (doris lehçesi dahil).

## Güvenlik modeli

- **Roller:** `admin`, `editor`, `viewer`. Rol her istekte DB'den okunur; rol iptali anında geçerli. Açılışta boş sistemde ilk kullanıcı admin olur (atomik `CASE WHEN COUNT(*)=0`).
- **Kayıt:** kapalı. `DATALENS_ALLOW_REGISTER=true` ile açılır (varsayılan `false`). Yeni kullanıcı admin tarafından `POST /api/users` ile eklenir. Kullanıcı adı çakışması 409.
- **Bağlantılar:** oluşturma ve silme yalnız admin. Parolalar Fernet ile şifreli (`password_enc`). Host politikası ve `URL.create` escape'i uygulanır.
- **Sürücü kurulumu:** `POST /api/drivers/{db_type}/install` yalnız admin (`drivers.py`).
- **Paylaşım:** dataset ve dashboard, kullanıcıya ya da role `read`/`write` izniyle paylaşılır. Admin ve sahip her şeyi yapar. Rol alıcısı yalnız okuyabilir; yazma tek tek kullanıcıya verilir. Yetkisiz kaynak 404 döner (varlık sızdırılmaz). Silme yalnız sahip ya da admin. Yazma izni yalnız adı değiştirebilir; yapı (sorgu, kolonlar, bağlantı) sahibe kilitli.
- **Veri seti çalıştırma (`/run`):** sorgu sahibin bağlantısıyla çalışır. Alıcı SQL, tablo ya da bağlantı gönderemez; yalnız veri setinde tanımlı görünür kolonların alt kümesini isteyebilir. Gizli (`off`) kolonlar sızmaz.
- **Satır seviyesi güvenlik (RLS):** kurallar (`row_rules`) veri setine bağlıdır ve sorguya `FilterDef` olarak eklenir. Admin kuralları atlar. Kural bir kullanıcı özniteliğine (`user_attributes`) bağlıysa ve öznitelik eksikse istek 403 ile durur (fail-closed). Veri seti silinince kuralları da silinir.
- **Dashboard:** dashboard'a ait satır kuralı yok; widget'lar paylaşılan veri setini `/run` ucundan alır, dolayısıyla veri seti kuralları geçerlidir.
- **Açılış:** eksik zorunlu sır varsa uygulama başlamaz; yalnız değişken adları loglanır.
- **Formül güvenliği:** `;` içeren SBX/SQL formülleri reddedilir (sürümden bağımsız).

## Dağıtım

- `docker-compose.yml`: servis `superbi`, `image: superbi:latest`, `restart: unless-stopped`, `mem_limit: 384m`, port `127.0.0.1:8000:8000`, ağ `ortak-db` (external), `env_file: .env`.
- Veri: `./data` → `/data`. SQLite dosyası: `/opt/superbi/data/superbi.db`. Günlük yedek: `scripts/backup.sh` → `/opt/superbi/backups/superbi_YYYY-MM-DD_030001.db.gz` (her gece 03:00; 14 günden eski yedekler silinir).
- Deploy öncesi yedek: `/root/yedekler/predeploy-YYYYMMDD-HHMM/` (`env`, `superbi.db`) ve imaj etiketi `superbi:pre-*-YYYYMMDD-HHMM`. Son deploy: `superbi:latest` 2026-11-09 12:55 CET; geri dönüş etiketi `superbi:pre-merge-20261109-1255`.
- Ortam değişkenleri (yalnız adlar; değerler `.env`'de, git ve md'de yok):

| Değişken | Zorunlu | Not |
|---|---|---|
| `DATALENS_JWT_SECRET` | evet | Açılışta kontrol. Yedeklenmeli. |
| `DATALENS_DB_ENCRYPTION_KEY` | evet | Fernet anahtarı. Kaybolursa kayıtlı parolalar kurtarılamaz. |
| `DATALENS_DB` | evet | Uygulamanın SQLite meta dosyasının yolu. |
| `DATALENS_ALLOWED_DB_HOSTS` | hayır (önerilir) | Virgülle ayrılmış DB host listesi. Canlıda tanımlı; değeri doğrulanmadı. |
| `DATALENS_ALLOW_REGISTER` | hayır | Varsayılan `false`. Boş sistemde bootstrap açık. |
| `DATALENS_SQLITE_ROOT` | hayır | Tanımsızsa SQLite bağlantıları kapalı. |
| `DATALENS_CORS_ORIGINS` | hayır | Virgülle ayrılmış origin listesi; yoksa geliştirme varsayılanları. |
| `DATALENS_JWT_EXPIRE_MINUTES` | hayır | Varsayılan 480 (8 saat). |

- Tablolar (SQLite): `connections`, `dashboards`, `query_history`, `users`, `datasets` (`schema_name`, `calculated_fields_json` dahil), `table_profiles`, `datasets_relationships`, `shares`, `row_rules`, `user_attributes`. Yeni kolonlar `add_column_if_missing` ile eklenir.
- AutoSleep (`/opt/autosleep/ek_projeler.py`) boşta kalan konteyneri durdurabilir (2026-10-18'den beri Docker). Bu bilinçli davranış, hata değildir.
- Bağımlılıklar: `requirements.txt` (`sqlglot==25.34.1` tam sürüm sabit; diğerleri aralık), `Dockerfile`, host nginx, `ortak-db` ağı.
- Test: `make test` → `scripts/test.sh` (`security` ve `integration` aşamaları). Integration DB'leri `docker-compose.test.yml` ile ayağa kalkar; her DB yalnız kendi `DATALENS_IT_*_URL` değişkeni tanımlıysa çalışır. CI: `.github/workflows/ci.yml`.

## Veri Akışı

**Sorgu oluşturucu (canlı):**
1. Kullanıcı Sorgu Oluşturucu'da alan/filtre/hesaplanmış alan (SBX) seçer; `buildQueryShape()` tek nesne üretir (`conn_id`, `base_table`, `schema_name`, `fields`, `joins`, `filters`, `group_by`, `order_by`, `calculated_fields`).
2. `sbx_compiler` SBX formülünü sqlglot ile hedef dialekte SQL'e çevirir (`_p()` ile parantezler zorunlu).
3. `sql_builder` sorguyu kurar (şema-qualified FROM; MSSQL: TOP / OFFSET-FETCH).
4. `query_executor` bağlantı üzerinden çalıştırır; sonuç cache'lenir; `commit` sahiplik kontrolüyle kalıcılaştırılır.

**Kaydedilmiş veri seti ve widget:**
1. Veri seti kaydı: `POST/PUT /api/datasets` (sahibin bağlantısı, tablo, join, filtre, alanlar, `schema_name`, `calculated_fields`). Frontend şu an `schema_name` ve `calculated_fields` göndermiyor (bkz. task.md 🔜).
2. Widget veri isteği: `POST /api/datasets/{id}/run` (`fields`, `sample`). Sunucu: görünürlük ve kolon alt kümesi → RLS kuralları (öznitelik eksikse 403) → `FilterDef` listesi → sahibin bağlantısıyla sorgu.
3. Alıcı `read` izniyle çalıştırabilir. Bağlantı veri setinin sahibinin kimliğiyle açılır; önbellek çalıştıran kullanıcıya özeldir. `write` izni yalnız adı değiştirmeye yeter.

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

Çözüm: `QueryRequest` / `QueryRunRequest` / `SQLPreviewRequest` / dataset modeli → `schema_name`; `sql_builder.build(..., schema=schema_name, db_type=...)`; `qualified_table = f"{schema}.{base_table}" if schema else base_table`.

| Dialekt | Satır sınırlama |
|---|---|
| oracle | `FETCH FIRST n ROWS ONLY` / `OFFSET m ROWS FETCH NEXT n ROWS ONLY`. Tanımlayıcılar `quote_identifier` ile büyük harfe çevrilir (küçük/karma harfli tırnaklı adlar desteklenmez). |
| mssql | offset=0 → `SELECT TOP n`; offset>0 → `OFFSET...FETCH NEXT` (ORDER BY yoksa `ORDER BY (SELECT NULL)`) |
| postgres / mysql / doris / sqlite | `LIMIT n [OFFSET m]` (MySQL ailesinde identifier backtick) |

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

API: `POST /api/analyze/{conn_id}/tables` (body: schema_name?, tables?, all_schemas?); `POST /api/analyze/{conn_id}/relationship`; `GET /api/analyze/{conn_id}/results` (DB-geneli). NLQ ↔ analyze sözleşmesi `normalize_table_profiles` ve `sample` ile uyumlu.

Frontend: Bağlantılar sayfasında "Analiz Et" / "Sonuçlar" (tüm kullanıcı şemaları, sistem şemaları hariç); Sorgu Oluşturucu'da "Önerilen İlişkiler" (tek tık / "Tümünü Ekle").

Bağımlılık: DuckDB yok; multi-DB push-down ile çalışır.

Doğrulama (AdventureWorks2022, Sales şeması): 34 FK ilişkisi. Sales.Customer grain = CustomerID; Sales.SalesOrderDetail grain = [SalesOrderID, SalesOrderDetailID].

## Kural Tabanlı Türkçe NLQ (Kademe 1 — kısmi kod)

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

Kod durumu: `app/services/nlq/` altında `nlq_engine.py`, `intent_patterns.py`, `slot_filler.py`, `plan_builder.py`, `synonyms.py` var; `tests/unit/test_nlq_contract.py` sözleşmeyi test eder. Hangi kalıbın tamamlandığı doğrulanmalı.

Kapsam dışı: "Bu soruyu anlayamadım. Şu kalıpları deneyebilirsiniz: ..." + örnekler.

Opsiyonel (ileride, varsayılan kapalı): BYOK LLM fallback — yalnız kalıp dışı sorularda, yalnız şema metadata; satır verisi asla gönderilmez.

## Dashboard Yerleşim Şablonları

Dashboard, mm cinsinden serbest konumlu bir "sayfa": `page_w_mm=297`, `page_h_mm=210`. Widget: `{id, type, x, y, w, h, title, query_id, color}`. Koordinatlar 297x210 referansına göre oranlı ölçeklenir.

Şablonlar: classic (Klasik), focus (Odak Grafik), metrics (Metrik Yoğun), grid (Izgara), mixed (Karma) + Boş. "+ Yeni Dashboard" ile seçilir; mevcut dashboard'da toolbar'dan "Şablon Uygula".

## Undo/Redo

`app.js` içinde uygulandı. Olay dinleyici birikmesi 2026-11-09 release'inde düzeltildi. Uçtan uca test tamamlanmadı (bkz. task.md).

## Planlanan Görünümler

- **Görsel ilişki editörü (orta öncelik):** `table_profiles` + `datasets_relationships` verisini node-link diyagram olarak gösterir. Teknik seçenek: D3 force-directed ya da basit SVG.
- **RLS yönetim arayüzü:** kurallar ve öznitelikler şu an API ile yönetiliyor (bkz. backlog.md).
- **Native kolon açıklamaları → LLM bağlamı (düşük öncelik):** MSSQL `sys.extended_properties`, Oracle `USER_COL_COMMENTS` / `ALL_COL_COMMENTS`, PostgreSQL `pg_description`, MySQL `COLUMN_COMMENT`. Yalnız LLM bağlamı için; granularity tespitine girdi olmaz.
- **DuckDB ingest (ileride):** kaynak DB'lerden çekme, cross-DB JOIN, incremental refresh. Ayrıntı backlog.md.

## Veri Kaynakları ve Dialektler

Desteklenen: Oracle XE, MSSQL (named-schema destekli), MySQL, PostgreSQL, SQLite, Apache Doris (pymysql, port 9030; canlı doğrulanmadı). Oracle XE, MSSQL, MySQL, PostgreSQL test konteynerlerinde (`docker-compose.test.yml`) integration testiyle doğrulanır; testler 2026-11-09 itibarıyla çalıştırılmadı. Push-down mimarisi: sql_builder şema farkında.

## Kapasite

Kayıtlı değer (eski kayıt 2026-09-16): VPS 7.8 GB RAM, swap dolu, 12 Docker konteyneri. Güncel kapasite doğrulanmadı. Konteyner `mem_limit` 384 MB; DuckDB ingest öncesi RAM planlaması gerekli.

## Anahtar Kararlar Özeti

1. sqlglot ==25.34.1 pin — güvenlik whitelist temeli
2. `_p()` parantezleme — operatör önceliği garantisi
3. Fernet şifreleme — bağlantı parolaları at-rest şifreli
4. Noktalı virgül reddi — formül güvenliği sürümden bağımsız
5. Kural tabanlı NLQ — LLM yok, maliyet sıfır
6. Granularity-first — tamamlandı
7. Şema farkındalığı — canlı Sorgu Oluşturucu ve dataset backend'i; dataset frontend gönderimi açık
8. Veri egemenliği — self-hosted, BYOK opsiyonel
9. MS_Description ayrımı — deterministik tespitte kullanılmıyor
10. Fail-closed açılış ve yetki — zorunlu sırlar, kapalı kayıt, admin-only bağlantı, 404 ile varlık gizleme, RLS öznitelik eksikse 403
11. Dokümantasyon tek kaynağı — kök dizindeki beş dosya (2026-10-25)
