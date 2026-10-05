# Claude.md — SuperBI Context

## Kişi
powerbiegitimi.com — SuperBI geliştiricisi ve yöneticisi

## Proje Özeti
**SuperBI**: Self-hosted, full-stack Business Intelligence platformu (Power BI / Qlik Sense alternatifi)

**Stack:**
- Backend: FastAPI + SQLAlchemy, Python 3.x
- Frontend: Vanilla HTML/CSS/JS, Apache ECharts
- Database: SQLite (metadata), Oracle/MSSQL/MySQL/PostgreSQL (veri kaynakları)
- Expression Language: SBX (Lark parser + sqlglot==25.34.1)
- Deployment: Contabo VPS (`vmi3389964`, `superbi.bidanismanlik.com.tr`), systemd service, Nginx + Let's Encrypt

**Hedef:** DAX-benzeri formül dili + Türkçe doğal dil SQL asistanı + cross-database JOIN — tüm self-hosted, maliyet sıfır

## Durum (2026-09-14, en son doğrulanan oturum)

### Tamamlanan
- Bağlantı şifreleme (Fernet) — password_enc, otomatik reconnect (Temmuz, tarih tam bilinmiyor)
- Formül güvenliği — noktalı virgül reddi + sqlglot ==25.34.1 sabitleme (Temmuz)
- SBX Kademe 1 (grammar + compiler + 17 fonksiyon, 4 dialect) — 16 Ağustos
- Parantez Önceliği Bug Fix (_p() helper) — PRODUCTION DEPLOY, doğrulandı
- Rekabet Analizi (Metabase/Superset/Lightdash) — 27 Ağustos
- DuckDB PoC (600K satır cross-source JOIN, 873ms, 27MB) — 27 Ağustos
- Türkçe NLQ Tasarımı (6 niyet kalıbı, rule-based, LLM yok) — henüz kod yazılmadı
- Granularity + İlişki Katmanı — backend (grain tespiti, sütun sınıflandırma, FK keşfi, orphan testi) — 11 Eylül, AdventureWorks'te doğrulandı (34 FK ilişkisi)
- Dashboard Yerleşim Şablonları (5 preset + Boş) — 14 Eylül
- Granularity + İlişki Katmanı — frontend entegrasyonu (Analiz Et/Sonuçlar, DB-geneli) — 14 Eylül
- Sorgu Oluşturucu Şema Desteği (?schema= + seçici) — 14 Eylül
- MSSQL SQL Üretim Bug Fix (TOP/OFFSET-FETCH, şema-qualified FROM) — 14 Eylül
- Sorgu Oluşturucu'da Önerilen İlişkiler — 14 Eylül
- Dokümantasyon (README, ARCHITECTURE, SESSION, BACKLOG, TASKS)

### Bilinen Boşluk (2026-09-16 tespit edildi)
Sunucudaki .md dosyaları kodun gerisinde kalmıştı — 7 Eylül ve 14 Eylül
oturumlarının çıktıları koda (ve Claude proje hafızasına) işlendi ama
sunucudaki /opt/superbi/*.md ve /opt/superbi/docs/*.md dosyalarına hiç
yazılmamıştı (en eski kök dosyalar 16 Ağustos, docs/ 27 Ağustos'ta donmuştu).
Bu oturumda (2026-09-16) beş dosya da birleştirilip güncellendi — bundan
sonra tek doğruluk kaynağı /opt/superbi/docs/ altındaki dosyalardır.
Kök dizindeki eski kopyalar (/opt/superbi/*.md) kaldırıldı.

### Acil
- Hepsi bitti

### Sırada
1. Kural Tabanlı Türkçe NLQ (Kademe 1) — ön koşul tamam, başlanabilir. Önerilen ilk kalıp: Top-N sıralama (en az efor)
2. Doğrulama: Kaydedilmiş dataset/widget akışında şema desteği (henüz test edilmedi — datasets.py modeli schema_name almıyor olabilir)
3. DuckDB Ingest — cross-DB JOIN, incremental refresh
4. Excel/CSV/JSON dosya kaynağı desteği
5. Native kolon açıklamaları → LLM bağlamı (MS_Description/COL_COMMENTS/pg_description/COLUMN_COMMENT) — NLQ + BYOK'tan sonra
6. Görsel ilişki editörü (node-link diyagram) — orta öncelik, ayrı oturum

### Farklar (Rakibine Karşı)
- SBX: DAX-benzeri formül dili (Metabase/Superset'te yok)
- Türkçe NLQ: Kural tabanlı, LLM gerektirmez
- NLQ + SBX: Doğal dil sorusu → SBX hesaplanmış alanlarıyla entegre
- Cross-DB JOIN: DuckDB ingest (Metabase vanilla tekli bağlantı)
- Otomatik İlişki Keşfi: Granularity katmanı + "Önerilen İlişkiler"
- Veri Egemenliği: Self-hosted, hiçbir satır verisi buluta gitmez

## Tercihler

**İletişim:** Türkçe, kısa ve doğrudan
**Claude tavırı:** Kendi önerileri yap, açık uçlu seçim sunma
**İş akışı:** Sequential task completion (hatasız, full test → production)
**Server Work:** SSH, kişi komut çalıştırır + output yapıştırır (Claude'un sunucuya doğrudan erişimi YOK — bu önemli, unutulmamalı)
**Dosya Transfer:** scp (Windows Downloads klasörü → sunucu) tercih ediliyor; patch'ler Claude tarafından sandbox'ta yazılıp syntax + fonksiyonel test edildikten sonra .py "patch script" olarak teslim edilir (str_replace tabanlı, replace_once güvenlik kontrolüyle). MD5 doğrulama her transferde standart.
**Büyük Dosyalar:** base64 -w76 (heredoc+Türkçe karakter problemi nedeni)

## Teknik Kısıtlar & Notlar

**sqlglot Pin 25.34.1:**
- AST parsing davranışı versiyon spesifik
- Upgrade → SBX compilation kırılır
- Yükseltmeden önce expression_builder güvenlik testleri tekrar çalıştırılmalı

**Operatör Önceliği (_p() Helper):**
- Elle inşa edilen sqlglot expression'larda render sırasında garanti edilmiyor
- Çözüm: Binary, Connector, Unary, Not node'lar otomatik exp.Paren() ile sarılır
- Fazladan parantez zararsız; eksik parantez = sessiz yanlış sonuç

**Bağlantı Şifreleme (Fernet):**
- app/core/crypto.py — şifreleme/çözme modülü
- ConnectionMeta.password_enc alanında saklanıyor, düz metin yok
- DATALENS_DB_ENCRYPTION_KEY systemd servis dosyasında (DB dosyasından ayrı yerde) — kaybolursa mevcut şifreli parolalar kurtarılamaz, JWT secret gibi yedeklenmeli
- deps.py restart sonrası PostgreSQL/MySQL/MSSQL için de otomatik yeniden bağlanıyor (önceden sadece SQLite bunu yapabiliyordu)

**Formül Güvenliği — Noktalı Virgül Reddi:**
- expression_builder.py artık ; içeren formülleri sürümden bağımsız açıkça reddediyor (kök neden: sqlglot 25.x/30.x arası tutarsız davranış — 25.x sessizce kırpıyordu, zararlı kısım hiç SQL'e karışmıyordu ama öngörülemezdi)
- sqlglot requirements.txt'te ==25.34.1 tam sürüme sabitli (>= değil)

**MSSQL'de LIMIT Yok:**
- T-SQL'de LIMIT sözdizimi geçersiz — sql_builder.py artık offset=0 için SELECT TOP n, offset>0 için OFFSET...FETCH NEXT (ORDER BY yoksa otomatik ORDER BY (SELECT NULL)) üretiyor
- Preview endpoint'i artık seçili bağlantının gerçek db_type'ını kullanıyor (önceden hep sqlite varsayıyordu)

**Çok Şemalı DB'ler (MSSQL/Postgres):**
- app/api/schema.py'ye ?schema= parametresi + /schemas endpoint'i eklendi (önceden hiç şema desteği yoktu, MSSQL'de sadece dbo görünüyordu)
- AdventureWorks2022 gibi named-schema DB'lerde asıl tablolar dbo DIŞINDA (Sales, Production, Person, HumanResources, Purchasing)

**Türkçe Karakter & SSH:**
- Heredoc uzun satırlarda SSH terminal maksimum satır uzunluğuna (~1024) çarpıyor → base64 -w76 ile sarma veya scp tercih edilir

**VPS Kapasite (7.8GB RAM, swap 5.8GB dolu):**
- 12 Docker container çalışıyor (test DB'leri)
- DuckDB ingest planında RAM planlaması gerekli
- Büyümede: 16GB+ veya ayrı VPS

## Mimari Kararlar

**Granularity Layer (backend + frontend tamam):**
- Grain tespiti: COUNT(*) vs COUNT(DISTINCT col)
- Sütun sınıflandırma: kardinalite + tip → identifier/categorical/metric/date_axis
- İlişki bulma: FK constraint (source=fk_constraint, confidence=1.0) + LEFT JOIN orphan test (source=inferred)
- analyze_tables() all_schemas=True ile tüm (sistem hariç) şemaları tek istekte tarayabiliyor

**Türkçe NLQ (Kademe 1, henüz kod yazılmadı):**
- Niyet tespiti: 6 kalıp (top-N, agregasyon, trend, filtre, metrik, SBX)
- Slot doldurma: fuzzy string matching
- JSON plan → sql_builder → SQL
- Fallback: "Anlayamadım, şu kalıpları deneyin"
- LLM fallback (opsiyonel, BYOK): sadece kalıp dışı sorular, şema metadata only

**DuckDB Ingest:**
- Kaynak DB'lerden veri çekme
- Persisted mode, memory_limit 1.5GB, threads=2
- SBX compiler target: single dialect (duckdb)
- Incremental refresh mekanizması

## Tools & Versiyonlar

| Kütüphane | Versiyon | Not |
|---|---|---|
| sqlglot | 25.34.1 | Pinned (==) — AST parsing spesifik + whitelist güvenliğinin temeli |
| lark | latest | LALR parser (SBX grammar) |
| FastAPI | latest | REST backend |
| SQLAlchemy | 2.x | ORM |
| duckdb | 1.5.5 | PoC'te test, prod'ta henüz değil |
| cryptography | latest | Fernet şifrelemesi (bağlantı şifreleri) |

## GitHub & Dokümantasyon

**Repo:** https://github.com/SHapeloglu/super_bi (public, main branch)
**Docs Dosyaları (tek doğruluk kaynağı):** /opt/superbi/docs/
- CLAUDE.md — Bu dosya (context)
- ARCHITECTURE.md — Mimari detay, bileşenler, veri akışı
- SESSION.md — Son oturumların notu
- TASKS.md — Yapılacaklar (öncelik sırasıyla)
- BACKLOG.md — Tüm items, notlar, rekabet analizi
- README.md — Public-facing kurulum, özellikler, teknoloji

## Kod Konvansiyonları

- Backend: Python 3.x, type hints (Pydantic 2.x)
- Frontend: Vanilla JS (no transpile)
- SQL: sqlglot AST üzerinde çalış; SQL string'i elle yazmayın
- Testing: Sandbox + production deploy

## Bilinen Gotcha'lar

1. Test çalıştırma: Sandbox'ta test edip sonra server'a deploy etmeli
2. sqlglot upgrade: Hiçbir zaman yapmayın (min/tam 25.34.1, pin'li)
3. FileZilla transfers: Dosya boyutu kontrol etmeli
4. SSH line breaks: Uzun komutlar terminal kesebilir — -w76 veya scp
5. VPS RAM: Swap zaten dolu, DuckDB heavy lifting çok dikkatli
6. Dataset/widget şema desteği: schema_name şu an sadece canlı Sorgu Oluşturucu akışında var
7. Dokümantasyon senkron kaybı: .md dosyaları koddan geride kalabiliyor — her oturum sonunda docs/ altındaki dosyaların GERÇEKTEN sunucuya yazıldığını doğrulamak gerekir

## İletişim Stil

- Türkçe: Yazışmalar Türkçe
- Kısalık: Mümkün olunca bullet/liste yerine prose; başında summary
- Öneriler: "Ne düşünüyorsun?" yerine "Şunu yapıyoruz" söyle
- Sorunlar: Kök nedeni tartış, sonra çözüm
- Test: Sandbox'ta validate, sonra production

---

Son güncelleme: 2026-09-16 (Sunucu ile dokümantasyon senkronizasyonu)
