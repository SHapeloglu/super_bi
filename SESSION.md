# SuperBI Session — 2026-08-16

## Tamamlanan

1. **SBX (SuperBI Expression Language) Kademe 1** — Prototip → Sunucuya entegrasyon
   - Grammar: lark LALR parser (Excel/DAX-benzeri syntax)
   - Derleyici: sqlglot ile 4 dialect'e (Oracle/TSQL/Postgres/MySQL) SQL dönüşümü
   - Fonksiyonlar: IF, DIVIDE, ROUND, CONCAT, DATEDIFF, ISNULL, SUM/AVG/COUNT/MIN/MAX, UPPER/LOWER/ABS/LEN/TRIM/COALESCE
   - Entegrasyon: expression_builder.py (compat mod — SBX + SQL fallback)
   - Test: 5/5 senaryoda başarılı (Oracle/MSSQL/Postgres/MySQL)
   - Dosyalar: `/opt/superbi/app/services/sbx_compiler.py`, `grammar.lark`, `expression_builder.py` (v2)

2. **DIALECT_MAP güncelleme** — oracle/postgresql key'leri eklendi

## Sıradaki

- **İlişkisel veri modeli katmanı** (`datasets_relationships` table, JOIN otomasyonu)
- **Incremental refresh** (dataset delta yenileme)
- **Excel/CSV/JSON dosya kaynağı** (upload + parse)
- **Frontend SBX editörü** (alan listesi, syntax highlight)
- **Kademe 2** (measure + filtre context — ilişki katmanıyla birlikte)

## İnfra Notları

- Sunucu: `/opt/superbi`, systemd service aktif
- venv: `/opt/superbi/venv` (lark, sqlglot==25.34.1 kurulu)
- DB: SQLite metadata, Oracle/MSSQL/Postgres/MySQL veri kaynakları

---

# Session Notu — 2026-09-11

## ✅ Tamamlandı

### Granularity + İlişki Katmanı (tam stack)

1. **sqlite_store.py** — `table_profiles` + `datasets_relationships` tabloları eklendi
2. **granularity_analyzer.py** — 4 fonksiyon:
   - `discover_fk_relationships()` — sqlalchemy.inspect, PK/FK metadata, verified=1 confidence=1.0
   - `detect_grain()` — COUNT(*) vs COUNT(DISTINCT), single + composite fallback
   - `classify_columns()` — kardinalite + tip → identifier/categorical/metric/date_axis
   - `profile_table()` — tek tabloda tam profil
   - `_split_schema_table()` — "Schema.Table" ayrıştırma (sqlalchemy inspect parametresi)
   - Boşluklu kolon adları "unsupported" olarak güvenli atlanıyor
3. **app/api/analyze.py** — 3 endpoint:
   - POST /api/analyze/{conn_id}/tables
   - POST /api/analyze/{conn_id}/relationship
   - GET /api/analyze/{conn_id}/results
4. **main.py** — import + include_router eklendi
5. **AdventureWorks2022** üzerinde doğrulandı:
   - 34 FK ilişkisi (Sales şeması, cross-schema dahil)
   - Sales.Customer grain=CustomerID, Sales.SalesOrderDetail grain=[SalesOrderID, SalesOrderDetailID]
   - Orphan testi: SalesOrderDetail.ProductID→Production.Product.ProductID confidence=1.0

## Sonraki Adım
- Dashboard yerleşim şablonları (paralel, saf frontend)
