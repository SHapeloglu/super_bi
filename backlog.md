# backlog.md — SuperBI Fikirler ve Teknik Borç

Kaynak: eski `docs/BACKLOG.md` (birleştirildi, 2026-10-25; yedek: `/root/yedekler/md-birlestirme-20261025/opt/superbi/docs/BACKLOG.md`). Burada yalnız planlanmamış maddeler; planlananlar `task.md` içinde, tamamlananlar `task.md` ✅ bölümünde.

## Özellik fikirleri

### DuckDB ingest — incremental refresh
- **Kategori:** yeni özellik
- **Neden:** cross-DB JOIN için kaynak verinin yerelde tutulup kademeli yenilenmesi.
- **Notlar:** DuckDB PoC (600K satır, 873 ms, 27 MB) başarılı. Persisted dosya modu, memory_limit=1.5 GB, threads=2. SBX derleyici hedefi tek dialekt (duckdb) olacak. RAM planlaması gerekli (konteyner `mem_limit` 384 MB). Incremental refresh delta yükleme stratejisi; DuckDB ingest ile birlikte tasarlanacak.

### Excel / CSV / JSON dosya kaynağı
- **Kategori:** yeni özellik
- **Neden:** veri kaynağı olarak dosya desteği; veritabanı dışı kullanıcılar.
- **Notlar:** DuckDB ingest ile birlikte tasarlanabilir.

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

### Kaydedilmiş dataset / widget şema desteği doğrulaması
- **Kategori:** teknik borç
- **Neden:** `schema_name` şu an yalnız canlı Sorgu Oluşturucu akışında çalışıyor; "Dataset Olarak Kaydet" ve widget bağlama akışı test edilmedi (`datasets.py` modeli `schema_name` almıyor olabilir).

## Teknik borç

### Rekabet ve pazar araştırması
- **Kategori:** araştırma
- **Notlar:** Metabase, Superset, Lightdash, WrenAI, Vanna karşılaştırması aşağıdaki "Rekabet notları" bölümünde. Yeni bulgu yoksa ek iş yok.

### Production kapasite kararı
- **Kategori:** teknik borç
- **Neden:** VPS 7.8 GB RAM (kayıt 2026-09-16), swap dolu; DuckDB ingest öncesi RAM yükseltme veya ayrı VPS kararı.

## Dokümantasyon / Repo

- [x] docs/ klasörü + kapsamlı README.md GitHub'a eklendi (tarih belirsiz; bkz. task.md ✅).
- [ ] LICENSE dosyası eklenmedi.

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
- **Kategori:** yeni özellik / iyileştirme / teknik borç / araştırma
- **Neden:** kısa gerekçe
- **Notlar:** büyüklük, bağımlılıklar, riskler
```
