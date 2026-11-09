# task.md — SuperBI Görevler

Son güncelleme: 2026-11-09. Kaynak: 2026-10-24 yorum taraması, 2026-10-25 md birleştirmesi, 2026-11-08/09 güvenlik fazı ve release. Bu dosyadaki tarih çelişkileri (eski kayıtlarda) düzeltilmedi; güncel durum en yeni bölümdedir.

## 🔜 Sıradaki

### Güvenlik ve yetki (2026-11-09 açık kalanlar)
- [ ] Frontend `schema_name` ve `calculated_fields` göndermiyor: "Dataset Olarak Kaydet" payload'ı (`app.js` ~1186, `buildQueryShape` alanları eksik). Backend hazır (`datasets.py`, `71d11cf`).
- [ ] Tarayıcıda paylaşılan veri seti widget testi tamamlanmadı (alıcı rolü, 404, kolon alt kümesi, RLS).
- [ ] Viewer UI: bağlantı oluştur/sil düğmeleri ve açık kayıt formu gizlenmeli (sunucu 403 döner; yalnız arayüz).
- [ ] Canlı `.env` içinde `DATALENS_ALLOWED_DB_HOSTS` tanımlı (değer doğrulanmadı); eski `127.0.0.1` kayıtları (mssql, mysql, oracle, postgresql) ve host boş kayıt temizlenmeli.
- [ ] `release/2026-11-09` (`127c74d`) `main`'e PR ile alınmalı; GitHub `main` eski.

### Test ve canlı doğrulama
- [ ] Integration testleri çalıştırılmadı: `docker compose -f docker-compose.test.yml up -d --wait` + `make test` (env yoksa testler ATLANIR).
- [ ] Oracle canlı doğrulama yok (identifier kuralı tek merkezden büyük harf; küçük/karma harfli tırnaklı adlar desteklenmez).
- [ ] Doris canlı doğrulama yok (sürücü pymysql, port 9030, dialect doris).
- [ ] Undo/redo uçtan uca testi (`app.js`) tamamlanmadı.
- [ ] README.md güncellemesi: NLQ motoru, analyze API, granularity, paylaşım/RLS, Doris ve test altyapısı README'de yok.

### Çalışma düzeni
- [ ] `/opt/superbi` çalışma ağacında commit'lenmemiş dosyalar ve kök dizindeki `apply_*.py` / `patch_*.py` yama betikleri (`scripts/archive/` altına taşınmış görünüyor; kök kalıntıları doğrulanmalı).
- [ ] `/root/superbi/backend/sbx/` ayrı ve eski kopya. Silme/arşiv kararı gerekli.
- [ ] Kök dizinde 0 baytlık `superbi.db`, `pbixdb`, `odoo_test` — veri yolu karışıklığı riski (gerçek DB `data/superbi.db`).

### Frontend (kalan)
- [ ] Oturum token'ı `localStorage` (`sb_token`) — XSS olursa okunur (risk düşük).

### Sonraki sıra (öncelik sırasıyla; ayrıntı backlog.md)
- [ ] Kural tabanlı Türkçe NLQ (Kademe 1, LLM yok): `app/services/nlq/` altında kod var; ilk kalıp Top-N. Hangi kalıbın bittiği doğrulanmalı.
- [ ] DuckDB ingest — cross-DB JOIN, incremental refresh (RAM planlaması şart).
- [ ] Excel/CSV/JSON dosya kaynağı.
- [ ] Production VPS kapasite kararı (RAM yükseltme veya ayrı VPS).

## 🚧 Devam Eden

- [ ] Yok. (Güvenlik fazı 0.1–0.6 ve Faz 1.2/1.3 tamam; açık kalanlar yukarıda.)

## ✅ Tamamlanan

### 2026-11-09
- [x] Release `release/2026-11-09` (`127c74d`) canlıya alındı; sağlık kontrolü ok. Yedekler ve imaj etiketleri `session.md` 2026-11-09 kaydında.
- [x] Doris sürücüsü (pymysql, port 9030, dialect doris) ve test altyapısı (`docker-compose.test.yml`, `tests/integration/`, `.github/workflows/ci.yml`, `Makefile`, `scripts/test.sh`) release'e entegre (canlı doğrulama açık).
- [x] Frontend hijyeni: CSV formül enjeksiyonu (`frontend/csv_escape.js`, `index.html`'de `app.js`'ten önce), `installDriver` ve id yolları `encodeURIComponent`, `origClose` kaldırıldı, `world.json` ECharts 4.9.0 + SRI, `.bak` dosyaları temizlendi, Ctrl+Z dinleyici düzeltmesi.
- [x] Backend küçük bulgular: register `IntegrityError` → 409; granularity bozuk metinleri düzeltildi; pip `sys.executable -m pip` (bayraksız); NLQ ↔ analyze sözleşmesi (`normalize_table_profiles`, `sample`).
- [x] Kaydedilmiş veri setleri: `schema_name` ve `calculated_fields` kalıcı (`datasets.py`, migration `add_column_if_missing`). Frontend gönderimi açık (bkz. 🔜).
- [x] Driver kurulumu (`POST /api/drivers/{db_type}/install`): kodda admin kontrolü var (`drivers.py`); canlı doğrulanmadı.
- [x] Oracle identifier tutarlılığı: `quote_identifier` tek merkezden büyük harf.
- [x] Dataset/widget: `POST /api/datasets/{id}/run` (sahibin bağlantısıyla; alıcı SQL/tablo/bağlantı gönderemez; kolon alt kümesi). Widget'lar paylaşılan veri setini bu uçtan alıyor.
- [x] Faz 1.3 RLS: `row_rules`, `user_attributes`, `app/core/rls.py`; kurallar `FilterDef` olarak sorguya eklenir; admin atlar; öznitelik eksikse 403; `PUT /api/users/{id}/attributes/{key}` (admin).
- [x] Güvenlik incelemesi düzeltmeleri: gizli (off) kolon sızıntısı kapatıldı; rol her istekte DB'den okunuyor (rol iptali); yazma izni yalnız adı değiştirebilir (yapı sahibe kilitli); veri seti silinince kurallar silinir; öznitelik doğrulaması.
- [x] Faz 1.2 paylaşım: `shares` tablosu, `app/core/sharing.py`, `/api/shares`; dataset/dashboard read/write; rol paylaşımı yalnız okuma; yetkisizde 404; editör rolü.
- [x] Güvenlik Faz 0.1–0.6 (2026-11-08): SQLite politikası (`sqlite_policy.py`, `DATALENS_SQLITE_ROOT`); bağlantı yalnız admin; açık kayıt kapalı (`DATALENS_ALLOW_REGISTER`); `POST /api/users` (admin); host politikası (`host_policy.py`, `DATALENS_ALLOWED_DB_HOSTS`, loopback/link-local engelli); URL.create ile escape; zorunlu sırlar (`startup_check.py`); hata mesajları sabit.
- [x] Güvenlik ve yetki testleri: `tests/security/run_all.sh`, `tests/access/`, `tests/test_yetki.py` (sürüm öncesi kırmızı-yeşil akışıyla).
- [x] 2026-11-09 — md seti (kök beş dosya) 2026-11-09 durumuna getirildi (`docs/md-2026-11-09` branch).

### 2026-10-27 — #212 yetki/hata bulguları
- [x] `get_analysis_results` sahiplik kontrolü (zaten vardı; testle doğrulandı).
- [x] `/commit` sahiplik: `QueryExecutor.commit` `user_id` karşılaştırıyor.
- [x] İlk-admin yarışı: rol INSERT içinde atomik (`CASE WHEN COUNT(*)=0`).
- [x] Cache isabetinde `commit=True` kalıcılaştırılıyor.
- [x] `/api/health` yol sızıntısı kapalı; `VisitError` `compile_sbx` içinde `SBXError`'a çevriliyor.
- [x] `UserRepository.count()` kullanılıyor (`auth.py` ilk-kullanıcı kontrolü); "kaldırılabilir" notu geçersiz.

### 2026-10-25 — Md birleştirme ve denetim
- [x] Küçük harfli set (`architect.md`, `CLAUDE.md`, `backlog.md`, `session.md`, `task.md`) tek kaynak; eski `docs/` set taşınıp silindi; `docs/OKUBENI_*.md` kaldı.
- [x] Kök `CLAUDE.md` içindeki `@docs/CLAUDE.md` importu kaldırıldı; içerik `CLAUDE.md`'ye alındı.

### 2026-10-24 — Yorum taraması
- [x] `frontend/app.js` / `api.js` yorum taraması; bulgular bu dosyanın ilgili bölümlerine dağıtıldı.

### 2026-10-05 / 2026-09-14
- [x] Granularity + ilişki katmanı frontend entegrasyonu; "Analiz Et" DB-geneli (tüm kullanıcı şemaları, sistem hariç). (Tarih çelişkisi: 09-14 kaydında da geçiyor.)
- [x] Dashboard şablonları (5 preset + Boş; "+ Yeni Dashboard" ve "Şablon Uygula").
- [x] Sorgu Oluşturucu şema seçici (`?schema=`); MSSQL TOP/OFFSET-FETCH + şema-qualified FROM; "Önerilen İlişkiler".

### 2026-09-11
- [x] Granularity + ilişki katmanı backend (AdventureWorks2022'de 34 FK ilişkisi doğrulandı).

### 2026-08-27
- [x] DuckDB PoC (600K satır cross-source JOIN, 873 ms, 27 MB).
- [x] SBX parantez önceliği (`_p()`) düzeltmesi deploy edildi (4 dialekt; md5 `39a99468…`).
- [x] Rekabet analizi (Metabase/Superset/Lightdash) güncellendi.

### 2026-08-16
- [x] SBX Kademe 1 (grammar + compiler + 17 fonksiyon, 4 dialekt; 5/5 senaryo); DIALECT_MAP güncellendi.

### Tarih belirsiz / Temmuz 2026
- [x] `docs/` klasörü + README.md GitHub'a push edildi (repo: `SHapeloglu/super_bi`).
- [x] Bağlantı parolalarının Fernet ile şifrelenmesi ve restart sonrası otomatik yeniden bağlanma (`app/core/crypto.py`, `password_enc`); hesaplanmış alan formüllerinde `;` reddi; sqlglot `==25.34.1` tam sürüm pin. Sunucuda doğrulandı 2026-09-15.

## Çalışma notları

- Yedek ve deploy ayrıntıları: `session.md`.
- Planlanmamış fikirler ve teknik borç: `backlog.md`.
