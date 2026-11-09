# session.md — SuperBI Oturum Günlüğü

Kayıtlar tarih sırasıyla (eskiden yeniye). Eski `docs/SESSION.md` kayıtları birleştirildi (2026-10-25; yedek: `/root/yedekler/md-birlestirme-20261025/opt/superbi/docs/SESSION.md`). Eski kayıtlardaki "tek kaynak docs/" ifadesi 2026-10-25 kararıyla geçersizdir; `(eski kayıt)` ile işaretlidir.

---

## Temmuz 2026 (tarih tam bilinmiyor; eski kayıt, dosya mtime 12-13 Temmuz)

**Tamamlandı:**
- Bağlantı şifreleme (Fernet): PostgreSQL/MySQL/MSSQL parolaları şifreli saklanıyor, restart sonrası otomatik yeniden bağlanıyor. Yeni: `app/core/crypto.py`. Değişen: repository.py, sqlite_store.py, connections.py, deps.py. Gerçek PostgreSQL ile test edildi.
- Formül güvenliği: `expression_builder.py` `;` içeren formülleri açıkça reddediyor; sqlglot `==25.34.1` tam sürüm pin.

## 2026-08-16

**Tamamlandı:**
- SBX Kademe 1 — prototip → sunucu: lark LALR grammar, 4 dialekte SQL, fonksiyonlar IF, DIVIDE, ROUND, CONCAT, DATEDIFF, ISNULL, SUM/AVG/COUNT/MIN/MAX. Test 5/5.
- DIALECT_MAP güncellendi.

## 2026-08-27

**Tamamlandı:**
- SBX parantez önceliği düzeltmesi (`_p()`), 4 dialektte doğrulandı, deploy edildi (md5 `39a99468c2600a31012f002cd307edc6`).
- Rekabet analizi güncellendi.
- Türkçe NLQ tasarımı (Kademe 1) onaylandı.
- DuckDB PoC (600K satır cross-source JOIN, 873 ms). (task kaydından.)

## 2026-09-11

**Tamamlandı — Granularity + ilişki katmanı (backend, tam stack):**
1. `sqlite_store.py`: `table_profiles` + `datasets_relationships` tabloları.
2. `granularity_analyzer.py`: `discover_fk_relationships()`, `detect_grain()`, `classify_columns()`, `profile_table()`.
3. `app/api/analyze.py`: 3 endpoint.
4. AdventureWorks2022'de doğrulandı: 34 FK ilişkisi.

## 2026-09-14

**Tamamlandı:**
1. Dashboard yerleşim şablonları: 5 preset + Boş.
2. Granularity + ilişki katmanının frontend entegrasyonu.
3. Çok şemalı DB desteği: `schema.py`'ye `?schema=`, `sql_builder.py`'ye MSSQL TOP/OFFSET-FETCH.
4. "Analiz Et" DB-geneli + Sorgu Oluşturucu'da "Önerilen İlişkiler".

**Sonraki adımlar (o tarihte):** Kural tabanlı Türkçe NLQ (Top-N); dataset/widget şema doğrulaması; DuckDB ingest.

## 2026-09-15 (eski kayıt, task kaydından)

- Sunucuda doğrulandı: Fernet parola şifreleme ve `;` reddi. (Ayrı oturum notu bulunamadı; muhtemelen daha önce deploy edilmiş.)

## 2026-09-16 (eski kayıt)

**Tamamlandı:** Dokümantasyon senkronizasyonu. Sunucudaki `.md` dosyalarının kodun 3-4 hafta gerisinde kaldığı tespit edildi; beş dosya (CLAUDE, ARCHITECTURE, BACKLOG, TASKS, SESSION) yeniden yazıldı. Bu kayıtta `docs/` tek doğruluk kaynağı ilan edilmişti; 2026-10-25 kararıyla kök dizindeki set tek kaynak oldu.

**Sonraki adım (o tarihte):** Kural tabanlı Türkçe NLQ (Kademe 1), Top-N kalıbıyla.

## 2026-10-05 (eski kayıt, task kaydından)

- Granularity + ilişki katmanı frontend entegrasyonu ve DB-geneli "Analiz Et" (yukarıda 09-14 olarak da geçiyor).

## 2026-10-24 (task kaydından)

- `frontend/app.js` ve `api.js` JS yorum taraması: güvenlik ve hata bulguları. 🔴 maddeler `task.md` 🔜 bölümüne taşındı.

---

## 2026-10-25

**Yapılanlar:**
- Md denetimi: kök dizinde `architect.md`, `task.md`, `backlog.md`, `session.md` oluşturuldu (önceden yoktu); `CLAUDE.md` güncellendi.
- Md birleştirme: `docs/` altındaki eski set (ARCHITECTURE, TASKS, BACKLOG, SESSION, CLAUDE) kök dosyalara birleştirildi ve silindi; yedek `/root/yedekler/md-birlestirme-20261025/`. `docs/OKUBENI_*.md` kaldı. Kök `CLAUDE.md` içindeki `@docs/CLAUDE.md` importu kaldırıldı, içerik `CLAUDE.md`'ye taşındı.
- `/root/superbi` incelendi: yalnız `backend/sbx/` var; `grammar.lark` çalışma kopyasıyla aynı, `compiler.py` farklı (md5 uyuşmuyor). Canlı kaynak olarak kullanılmadı, değiştirilmedi.
- Konteyner durumu: `superbi` `Exited (0)` (2026-10-23 02:48). `/opt/autosleep/ek_projeler.py` kaydı nedeniyle AutoSleep kaynaklı; hata sayılmadı.
- `docs/TASKS.md` içindeki 2026-10-24 yorum taramasından gelen bulgular `task.md` 🔜 bölümüne taşındı (3 madde 🔴).

**Kararlar / neden:**
- Md seti tek kaynak: kök dizindeki beş dosya. Proje md kuralı kök dizini istiyor.
- Kod, `.env`, servis ve git durumuna dokunulmadı.

**Açık sorunlar:**
- Çalışma ağacında 43 commit'lenmemiş dosya; son commit 2026-10-05.
- Kök dizinde yama betikleri (`apply_*.py`, `patch_*.py`) ve 0 baytlık dosyalar birikmiş.

**Sıradaki adım:**
- Güvenlik maddelerinin (🔴) düzeltilmesi, ayrı oturumda ve kullanıcı onayıyla.
- Commit/temizlik kararı.


## 2026-11-08 — Güvenlik fazı 0.1–0.6 ve yetki altyapısı

**Değişenler:**
- Faz 0.1–0.2 (SQLite): `app/core/sqlite_policy.py` (yeni). SQLite yolu yalnız `DATALENS_SQLITE_ROOT` altında, var olan, metadata olmayan dosyalara izin verir; salt okunur (`mode=ro`) açılır. Kök tanımsızsa SQLite kapalı. `connector_registry._build_url` SQLite dalında politikadan geçer (reconnect dahil). Bağlantı POST/DELETE yalnız admin; silmede sahip kontrolü kaldırıldı.
- Faz 0.3 (kayıt): açık kayıt kapalı (`DATALENS_ALLOW_REGISTER=true` ile açılır; boş sistemde bootstrap açık). Yeni `POST /api/users` (yalnız admin; rol admin|viewer).
- Faz 0.4 (SSRF): `app/core/host_policy.py`. Loopback, link-local (169.254.169.254), unspecified, multicast, reserved reddedilir. `DATALENS_ALLOWED_DB_HOSTS` tanımlıysa yalnız listedeki hostlar. Bağlantı hataları sabit mesajla döner; ham metin logda.
- Faz 0.5: bağlantı URL'si `URL.create` ile kurulur (escape).
- Faz 0.6: `app/core/startup_check.py`. `DATALENS_JWT_SECRET`, `DATALENS_DB_ENCRYPTION_KEY`, `DATALENS_DB` zorunlu; lifespan başında kontrol eder; yalnız değişken adlarını yazar. Rastgele anahtar ve `/tmp` varsayılanı kaldırıldı.
- Faz 0.7: `tests/security/run_all.sh` (pytest gerekmez).
- Faz 1.2–1.3 (aynı gün, branch zinciri): paylaşım (`shares`, `app/core/sharing.py`, `/api/shares`), RLS (`row_rules`, `user_attributes`, `app/core/rls.py`), dataset run.

**Testler:** Her madde için önce kırmızı görüldü. Kayıtlı sonuçlar: SQLite/rol 11/11; güvenlik 43 + yetki 6 geçti (`tests/test_yetki.py`).

**Yedekler:** `/root/yedekler/superbi.db.bak-20261108-0953`, `/root/yedekler/env.bak-20261108-1010`, `/root/yedekler/superbi-pre-commit-20261108-095127/`. Deploy öncesi katmanlar: `/root/yedekler/predeploy-20261108-1053`, `-1104`, `-1206`, `-1346`, `-1352` (her biri `env` ve `superbi.db`, 1352 ve 1255'te doğrulandı).

**Açık / dikkat:**
- Arayüz: viewer için bağlantı oluştur/sil düğmeleri ve açık kayıt formu hâlâ görünür olabilir (sunucu 403 döner). Yalnız UI işi.
- Canlı bağlantı kayıtlarından 4 tanesi `127.0.0.1` (mssql, mysql, oracle, postgresql), 1 tanesi host boş. Host politikası bunları reddeder.
- MSSQL `TrustServerCertificate=yes` sabit (MITM riski) — backlog.

## 2026-11-09 — Release `release/2026-11-09` canlıya alındı

**Kapsam:** Güvenlik ve yetki dalları (`policy`, `write`, `rls`, `roles`, `review`, `widget`, `dsschema`, `frontend`, `backend`, `oracle`, `quoting`, `doris`, `test-infra`, `integrate`) release'te birleşti. Release commit'i: `127c74d` (`Merge branch 'feat/integrate-doris-testinfra' into release/2026-11-09`).

**Değişenler (özet):**
- Paylaşım ve yetki: dataset/dashboard `read`/`write`; rol paylaşımı yalnız okuma; yetkisizde 404; editör rolü; yazma izni yalnız adı değiştirebilir (yapı sahibe kilitli); veri seti silinince kurallar silinir.
- Satır seviyesi güvenlik: kurallar `FilterDef` olarak eklenir; admin atlar; öznitelik eksikse 403; rol her istekte DB'den okunur (rol iptali anında geçerli).
- Gizli (off) kolon sızıntısı kapatıldı.
- `POST /api/datasets/{id}/run`: sahibin bağlantısı; alıcı SQL/tablo/bağlantı gönderemez; kolon alt kümesi. Widget'lar paylaşılan veri setini bu uçtan alır.
- Kaydedilmiş veri setleri: `schema_name` ve `calculated_fields` kalıcı (migration `add_column_if_missing`).
- Oracle: `quote_identifier` tek merkezden büyük harf. Küçük/karma harfli tırnaklı adlar desteklenmez.
- Doris sürücüsü (pymysql, port 9030, dialect doris); test altyapısı (`docker-compose.test.yml`, `tests/integration/` — env yoksa skip, `.github/workflows/ci.yml`, `Makefile`, `scripts/test.sh`).
- Frontend hijyeni: `frontend/csv_escape.js` (CSV formül enjeksiyonu; `index.html`'de `app.js`'ten önce), `installDriver` ve id yolları `encodeURIComponent`, `origClose` kaldırıldı, `world.json` ECharts 4.9.0 + SRI, `.bak` dosyaları temizlendi.
- Backend küçük bulgular: register `IntegrityError` → 409; granularity bozuk metinleri; pip `sys.executable -m pip` (bayraksız); NLQ ↔ analyze sözleşmesi (`normalize_table_profiles`, `sample`).

**Deploy:**
- Canlı imaj: `superbi:latest` (`94aaf4fa7cc3`), 2026-11-09 12:55 CET'de oluşturuldu, çalışıyor. Sağlık kontrolü ok.
- Geri dönüş imajı: `superbi:pre-merge-20261109-1255` (`aea21a0187d9`, 2026-11-08 13:52). Diğer etiketler: `superbi:pre-policy-20261108-1352`, `superbi:pre-review-20261108-1346`, `superbi:pre-rls-20261108-1206`, `superbi:pre-widget-20261108-1104`, `superbi:pre-release-20261108-1053`, `superbi:pre-security-20261108` (2026-10-18).
- Yedekler: `/root/yedekler/predeploy-20261109-1255/` (`env`, `superbi.db`); günlük yedek `/opt/superbi/backups/superbi_2026-11-09_030001.db.gz`.
- Canlı `.env`'de tanımlı değişken adları: `DATALENS_ALLOWED_DB_HOSTS`, `DATALENS_CORS_ORIGINS`, `DATALENS_DB`, `DATALENS_DB_ENCRYPTION_KEY`, `DATALENS_JWT_SECRET`. `DATALENS_ALLOW_REGISTER` ve `DATALENS_SQLITE_ROOT` tanımlı değil (varsayılan: kayıt kapalı, SQLite kapalı).

**Testler:** Integration testleri çalıştırılmadı (env yok). Release test sayısı bu kayda işlenmedi.

**Açık riskler:**
- Frontend `schema_name` ve `calculated_fields` göndermiyor ("Dataset Olarak Kaydet" payload'ı). Kaydedilmiş veri setinde şema ve hesaplanmış alan kaybolabilir.
- Tarayıcıda paylaşılan veri seti widget testi tamamlanmadı.
- Oracle ve Doris canlı doğrulama yok.
- Canlı `DATALENS_ALLOWED_DB_HOSTS` değeri doğrulanmadı; `127.0.0.1` kayıtları hâlâ olabilir.
- `architect.md` 2026-11-09 durumuna getirildi (bu kayıt); GitHub `main` eski, `release/2026-11-09` PR bekliyor.
- `DATALENS_JWT_SECRET` ve `DATALENS_DB_ENCRYPTION_KEY` yedeği: kaybolursa oturumlar ve kayıtlı parolalar kurtarılamaz (değerler md'de yok).

**Sıradaki adım:** Frontend payload'ına `schema_name` ve `calculated_fields` eklemek; ardından tarayıcıda paylaşılan veri seti widget testi.
