# backlog.md — SuperBI Fikirler ve Teknik Borç

Son güncelleme: 2026-11-09. Kaynak: eski `docs/BACKLOG.md` (2026-10-25 birleştirmesi). Burada yalnız planlanmamış maddeler; planlananlar `task.md` 🔜 bölümünde, tamamlananlar `task.md` ✅ bölümünde.

## Özellik fikirleri

### DuckDB ingest — incremental refresh
- **Kategori:** yeni özellik
- **Neden:** cross-DB JOIN için kaynak verinin yerelde tutulup kademeli yenilenmesi.
- **Notlar:** DuckDB PoC (600K satır, 873 ms, 27 MB) başarılı. Persisted dosya modu, memory_limit=1.5 GB, threads=2. SBX derleyici hedefi tek dialekt (duckdb). RAM planlaması gerekli (konteyner `mem_limit` 384 MB). Incremental refresh delta yükleme stratejisi; DuckDB ingest ile birlikte tasarlanacak.

### Excel / CSV / JSON dosya kaynağı
- **Kategori:** yeni özellik
- **Neden:** veri kaynağı olarak dosya desteği; veritabanı dışı kullanıcılar.
- **Notlar:** DuckDB ingest ile birlikte tasarlanabilir. Dosya kaynağı SQLite politikasından (`DATALENS_SQLITE_ROOT`) bağımsız ayrı bir giriş yolu olmalı.

### SBX Kademe 2 ve 3
- **Kategori:** yeni özellik
- **Neden:** measure + dashboard filtre bağlamı (Kademe 2); VAR/RETURN (Kademe 3, opsiyonel).
- **Notlar:** Kademe 1 tamam; sqlglot sürüm sabiti dikkate alınmalı.

### Frontend SBX editörü
- **Kategori:** iyileştirme
- **Neden:** alan listesi ve sözdizimi renklendirme (syntax highlighting).

### Görsel ilişki editörü
- **Kategori:** yeni özellik
- **Neden:** "Önerilen İlişkiler" listesinin node-link diyagram hali.

### Native kolon açıklamaları → LLM bağlamı
- **Kategori:** araştırma (düşük öncelik)
- **Neden:** MS_Description, Oracle COL_COMMENTS, pg_description, COLUMN_COMMENT.
- **Notlar:** yalnız LLM bağlamı için; granularity tespitine girdi olmayacak. Kural tabanlı NLQ ve BYOK LLM fallback'ten sonra.

### RLS kurallarının UI'da yönetimi
- **Kategori:** iyileştirme
- **Neden:** kurallar (`row_rules`) ve kullanıcı öznitelikleri (`user_attributes`) şu an yalnız API ile yönetiliyor (`/api/datasets/{id}/rules`, `/api/users/{id}/attributes/{key}`).
- **Notlar:** admin-only öznitelik ayarı zaten API'de. UI için veri seti detayında kural listesi ve öznitelik formu gerekir. Kural değeri (`value_json`) ve öznitelik adı (`attr_name`) birlikte doğrulanmalı.

### Dashboard satır kuralları
- **Kategori:** yeni özellik
- **Neden:** RLS şu an yalnız veri seti seviyesinde. Dashboard'a paylaşılan widget'lar veri setinin kurallarını miras alır; dashboard seviyesinde ek kural yok.
- **Notlar:** tasarım kararı gerekir (dashboard kuralı veri seti kuralının üstüne mi biner, yoksa ayrı mı?). Mevcut `FilterDef` akışına eklenebilir.

### Oracle küçük harf / karma harfli tırnaklı adlar
- **Kategori:** teknik borç
- **Neden:** `quote_identifier` Oracle'da tüm adları büyük harfe çeviriyor; küçük/karma harfli tırnaklı adı olan tablolar/kolonlar yanlış adla sorgulanır.
- **Notlar:** şu an desteklenmiyor (bilinen sınır). Çözüm: tabloların gerçek adını `ALL_TAB_COLUMNS` / `ALL_TABLES` üzerinden eşleyip kesin adla tırnaklamak. Canlı Oracle ile doğrulanmadı (`task.md` 🔜).

### Oracle join GROUP BY / ORDER BY tablo nitelemesi
- **Kategori:** teknik borç (belirsizlik riski)
- **Neden:** join sorgularında GROUP BY / ORDER BY ifadelerindeki kolon adı tablo nitelemesi olmadan yazılırsa aynı adlı kolonlarda belirsizlik hatası veya yanlış tablo eşleşmesi riski var.
- **Notlar:** `sql_builder` üretimi için tablo öneki tutarlılığı doğrulanmalı. Canlı Oracle yok; integration testi (`tests/integration/test_oracle.py`) çalıştırılmadı.

### MSSQL `TrustServerCertificate=yes` (MITM)
- **Kategori:** güvenlik (teknik borç)
- **Neden:** MSSQL bağlantı URL'sinde sertifika doğrulaması kapalı; ağ üzerinde ara adam saldırısı riski.
- **Notlar:** sertifika doğrulaması açık ve CA ayarlı olmalı. Kurulum gereksinimleri (ortak DB sertifikası) belirlenince yapılacak. Kaynak: `app/core/connector_registry.py` (`TrustServerCertificate: yes`).

### PyPI / npm bağımlılık sabitleme
- **Kategori:** teknik borç
- **Neden:** `requirements.txt` çoğu paketi aralıkla veriyor (`fastapi>=0.110,<1.0`, `cryptography>=42.0,<50.0`); kilit dosyası (lock) yok. Yalnız `sqlglot==25.34.1` tam sürüme sabit.
- **Notlar:** tekrarlanabilir kurulum için tam sürüm sabiti veya lock dosyası. Sqlglot sabiti değişmez. Frontend tarafında paket yöneticisi yok (CDN'den yükleme); sürüm sabiti yalnız CDN URL'lerinde.

### SRI for ECharts 6 (cdnjs)
- **Kategori:** güvenlik (teknik borç)
- **Neden:** `frontend/index.html` ECharts 6.0.0'ı cdnjs'ten `integrity` özniteliği olmadan yüklüyor. CDN ele geçirilirse kötü kod çalışır.
- **Notlar:** world.json (ECharts 4.9.0) zaten SRI ile yükleniyor (2026-11-09). ECharts 6 için aynı SRI hash'i üretilmeli; `crossorigin` özniteliği de eklenmeli.

### Calc alanlarının frontend'e taşınması (hesaplanmış alan kayıt akışı)
- **Kategori:** teknik borç
- **Neden:** backend `calculated_fields` alanını kalıcı tutuyor (`datasets.py`), ama frontend "Dataset Olarak Kaydet" payload'ında göndermiyor (`app.js` ~1186). Kaydedilen veri setinde hesaplanmış alanlar kayboluyor.
- **Notlar:** `buildQueryShape()` çıktısındaki `schema_name` ve `calculated_fields` payload'a eklenmeli; güncelleme yolundaki eşitlik kontrolü (`datasets.py` ~129) ile birlikte test edilmeli. Küçük iş, ama task.md 🔜 maddesi olarak öncelikli.

## Teknik borç

### Rekabet ve pazar araştırması
- **Kategori:** araştırma
- **Notlar:** Metabase, Superset, Lightdash, WrenAI, Vanna karşılaştırması aşağıdaki "Rekabet notları" bölümünde. Yeni bulgu yoksa ek iş yok.

### Production kapasite kararı
- **Kategori:** teknik borç
- **Neden:** VPS 7.8 GB RAM (kayıt 2026-09-16), swap dolu; DuckDB ingest öncesi RAM yükseltme veya ayrı VPS kararı. 2026-11-09 itibarıyla güncel değer ölçülmedi.

### Undo/Redo uçtan uca testi
- **Kategori:** teknik borç
- **Neden:** `app.js` içinde uygulandı, e2e test yok. Olay dinleyici birikmesi (Ctrl+Z) 2026-11-09 release'inde düzeltildi; test ile doğrulanmalı.

## Dokümantasyon / Repo

- [x] docs/ klasörü + README.md GitHub'a eklendi (tarih belirsiz; bkz. task.md ✅).
- [ ] LICENSE dosyası eklenmedi.
- [ ] README.md: NLQ, analyze, granularity, paylaşım/RLS, Doris ve test altyapısı bölümleri yok (bkz. task.md 🔜).

## Rekabet notları (referans, aksiyon değil)

- **Lightdash:** dbt'ye kilitli; SuperBI'nin "dbt'siz formül" konumu benzersiz.
- **Superset:** çekirdekte native NLQ / text-to-SQL yok (SIP-166 hâlâ öneri aşamasında).
- **Metabase:** NLQ (Metabot, BYOK) ve otomatik veri profilleme (X-rays) mevcut ve iyi durumda. SuperBI'nin gerçek fark noktaları: (1) SBX hâlâ DAX seviyesinde formül dili; (2) Türkçe öncelikli NLQ tasarımı; (3) NLQ çıktısının SBX hesaplanmış alanlarıyla entegre çalışması; (4) DuckDB ile gerçek cross-database JOIN.
- **Qlik:** self-hosted'i fiilen terk ediyor. **Power BI:** tamamen bulut.
- **WrenAI:** governed / plan-first NLQ. **Vanna AI:** FastAPI + Claude entegrasyon örneği. **Metabase Metabot / X-rays** ve **Superset SIP-166** yukarıdaki notların kaynağı.

## İptal edilenler

- SQLite frontend connector — gereksiz, talep gelmedi.

## Ekleme Şablonu

```markdown
### Başlık
- **Kategori:** yeni özellik / iyileştirme / teknik borç / güvenlik (teknik borç) / araştırma
- **Neden:** kısa gerekçe
- **Notlar:** büyüklük, bağımlılıklar, riskler
```

### Viewer kendi veri seti için bağlantı
- **Kategori:** karar bekliyor (ürün)
- **Neden:** Viewer bağlantı oluşturamadığı için kendi veri setini kaydedemez; paylaşılan veri setlerini yalnız çalıştırır.
- **Notlar:** Seçenekler: (a) viewer'a paylaşılmış bağlantıyla kayıt; (b) bağlantı paylaşımı (`shares` tablosunu bağlantıya genişletmek). Güvenlik etkisi: bağlantı kimlik bilgisi paylaşımı; dikkatli tasarım gerekir.
