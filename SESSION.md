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
