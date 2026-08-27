# Mimari — SuperBI

## Backend (`/opt/superbi/app`)
- **main.py**: FastAPI entry
- **models/schemas.py**: Pydantic schemas (CalculatedFieldDef, JoinDef, FilterDef, ALLOWED_OPERATORS)
- **core/connector_registry.py**: DB connection registry (DRIVER_MAP: sqlite/postgresql/mysql/mssql/oracle)
- **services/sql_builder.py**: Query builder + calculated field entegrasyonu
- **services/expression_builder.py**: Formül doğrulama (SBX + SQL compat mode, v2)
- **services/sbx_compiler.py**: SBX → SQL derleyici (lark + sqlglot)
- **services/grammar.lark**: SBX dilbilgisi tanımı
- **services/query_executor.py**: Query execute

## Frontend (`/opt/superbi/frontend`)
- Vanilla HTML/CSS/JS
- ECharts visualization

## Veritabanı (mevcut)
- SQLite: `/opt/superbi/data/superbi.db` (metadata)
- Oracle XE, MSSQL, MySQL, PostgreSQL: Docker container'lar, canlı veri kaynakları

## 🔴 MİMARİ KARAR BEKLİYOR: DuckDB In-Memory Katmanı

**Sorun:** Şu anki mimari her sorguyu canlı olarak kaynak DB'ye gönderiyor (SQL push-down).
Bu şu demek: **cross-database JOIN (örn. Oracle tablosu + MySQL tablosu) mimari
olarak İMKANSIZ** — her JoinDef tek bir db_type'a bağlı çalışıyor.

**Çözüm (PoC ile doğrulandı, 2026-08-16):**
- DuckDB (MIT lisanslı, embedded OLAP engine) ingest katmanı olarak eklenecek
- Kaynak DB'ler artık "canlı sorgu hedefi" değil, "ingest kaynağı"
- Veri DuckDB'nin kendi columnar deposuna çekilip orada ilişkilendirilecek
- sqlglot zaten DuckDB dialect'ini destekliyor — SBX'e ek değişiklik gerekmedi
- PoC sonucu: 600.000 satır cross-source JOIN + agregasyon = 873ms, 27MB memory

**VPS kısıtı (mevcut):** 7.8 GB RAM, swap zaten 5.8GB kullanımda (12 Docker container
memory baskısı yaratıyor). Disk boş: 66GB. Bu nedenle:
- DuckDB **persisted dosya modu** kullanılacak (`:memory:` değil)
- `PRAGMA memory_limit='1.5GB'` muhafazakar limit
- `PRAGMA threads=2`
- Production'a geçişte VPS RAM yükseltmesi (16GB+) veya ayrı VPS gerekebilir

**Sonraki adım:** `sql_builder.py`/`connector_registry.py`'yi DuckDB ingest katmanına
bağlayan somut tasarım (hangi tablolar ne zaman yüklenecek, refresh stratejisi —
bkz. TASKS.md "incremental refresh" ile birleşecek).

## Key Technologies
- sqlglot==25.34.1 (pinned, AST + dialect translation)
- lark (LALR parser, SBX grammar)
- duckdb==1.5.5 (PoC aşamasında, henüz production'a entegre değil)
- SQLAlchemy ORM
- Fernet (password encryption)
