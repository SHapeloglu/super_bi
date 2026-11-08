# task.md — SuperBI Görevler

Kaynak: 2026-10-24 yorum taraması, 2026-10-25 denetimi ve md birleştirmesi. Eski `docs/TASKS.md` (2026-10-24) buraya taşındı; yedek: `/root/yedekler/md-birlestirme-20261025/opt/superbi/docs/TASKS.md`.

## 🔜 Sıradaki

### Güvenlik ve hata bulguları (2026-10-24 yorum taraması, kodda `TODO(kontrol)` / `DİKKAT`)
- [x] 🔴 `api/analyze.py` `get_analysis_results` sahiplik kontrolü — kodda zaten var (2026-10-26 sonrası doğrulandı; 2026-10-27 testle kanıtlandı).
- [x] 🔴 `api/query.py` `/commit` sahiplik — `QueryExecutor.commit` `user_id` karşılaştırıyor; eski TODO yorumu temizlendi (2026-10-27).
- [x] 🔴 `auth register` ilk admin yarışı — rol INSERT içinde atomik belirleniyor (2026-10-27).
- [x] `/api/health` artık DB yolunu döndürmüyor (doğrulandı). `DATALENS_DB` `.env`'de tanımlı; `/tmp` varsayılanı yalnız `.env` eksikse geçerli.
- [x] `query_executor`: cache anahtarına `sample` zaten dahil; cache isabetinde `commit=True` artık kalıcılaştırıyor (2026-10-27). `mode` bilerek anahtarda yok.
- [x] `sbx_compiler` `VisitError` — `compile_sbx` içinde yakalanıp `SBXError`'a çevriliyor (doğrulandı).
- [ ] `granularity_analyzer`: bozuk metinler ("c~apsamında", "eyybo").
- [ ] `nlq/slot_filler` çıktısı `/api/analyze` ile uyuşmuyor (`table_name` vs `table`); `plan_builder` `limit` gönderiyor, `/run` `sample` bekliyor.
- [ ] `connector_registry` `--break-system-packages` kullanıyor; `api/history.py` docstring'i güncel değil.

### Frontend (2026-10-24 yorum taraması)
- [ ] Oturum token'ı `localStorage` (`sb_token`) — XSS olursa okunur (risk düşük; kullanıcı verisi `innerHTML`'e girmiyor).
- [ ] Dashboard Ctrl+Z dinleyicisi (`app.js` ~1762) yalnız "Kapat" ile kaldırılıyor; ekran değişince birikip çoklu geri alma olabilir.
- [ ] CSV formül enjeksiyonu: `csvEscape` (`app.js` ~2198) `=`, `+`, `-`, `@` ile başlayanları kaçırmıyor.
- [ ] Admin "Kur" düğmesi yalnız istemcide gizli — sunucu yetkilendirmesi şart (doğrulanmadı).
- [ ] `api.js`: `connId`, `fingerprint`, dashboard/dataset id yolları `encodeURIComponent`'siz.
- [ ] Dünya haritası `world.json` jsDelivr'den SRI'siz indiriliyor.
- [ ] `origClose` ölü kod.
- [ ] `frontend/` altında eski `.bak*` dosyaları (`app.js.bak`…`bak6`, `api.js.bak2/bak4`, `style.css.bak`) — temizlik.

### Test ve dokümantasyon
- [ ] Undo/redo uçtan uca testi — `app.js`'te uygulandı, e2e test tamamlanmadı.
- [ ] README.md güncellemesi: NLQ motoru (`app/services/nlq/`), analyze API ve granularity/ilişki katmanı (2026-09-11, 2026-10-05) README'de yok; özellik listesi ve dizin ağacı güncellenecek.

### Çalışma düzeni (2026-10-25 denetimi)
- [ ] `/opt/superbi` çalışma ağacında 43 dosya commit'lenmemiş (`git status`, son commit 2026-10-05). Commit/temizlik kararı gerekli; kök dizinde `apply_*.py`, `patch_*.py` yama betikleri birikmiş.
- [ ] `/root/superbi/backend/sbx/` ayrı ve eski kopya (`compiler.py` md5 farklı, `grammar.lark` aynı). Silme/arşiv kararı gerekli.
- [ ] Kök dizinde 0 baytlık `superbi.db`, `pbixdb`, `odoo_test` — veri yolu karışıklığı riski (gerçek DB `data/superbi.db`).

### Sonraki sıra (öncelik sırasıyla; ayrıntı backlog.md)
- [ ] Kaydedilmiş dataset / widget şema desteği doğrulaması (`schema_name` yalnız canlı Sorgu Oluşturucu akışında).
- [ ] DuckDB ingest — tasarım + ilk entegrasyon; `datasets_relationships` üzerinde cross-DB JOIN; incremental refresh.
- [ ] Excel/CSV/JSON dosya kaynağı.
- [ ] Production VPS kapasite kararı (RAM yükseltme veya ayrı VPS).

## 🚧 Devam Eden

- [ ] Kural tabanlı Türkçe NLQ (Kademe 1, LLM yok) — ön koşullar tamam. İlk kalıp: Top-N sıralama (`sql_builder` order_by/limit altyapısı hazır). Tasarım onaylandı (2026-08-27). `app/services/nlq/` altında kod var (nlq_engine, intent_patterns, slot_filler, plan_builder, synonyms); hangi kalıbın bittiği doğrulanmalı. Üstteki 2026-10-24 slot/plan uyumsuzluğu bu işe bağlı.

## ✅ Tamamlanan

- [x] 2026-10-25 — Md seti birleştirildi: küçük harfli set (`architect.md`, `CLAUDE.md`, `backlog.md`, `session.md`, `task.md`) tek kaynak; eski `docs/` set (ARCHITECTURE, TASKS, BACKLOG, SESSION, CLAUDE) taşınıp silindi; `docs/OKUBENI_*.md` kaldı; kök CLAUDE.md'deki `@docs/CLAUDE.md` importu kaldırıldı; README atıfları düzeltildi.
- [x] 2026-10-25 — Md denetimi: kök dizinde `architect.md`, `task.md`, `backlog.md`, `session.md` oluşturuldu; `CLAUDE.md` güncellendi.
- [x] 2026-10-24 — `frontend/app.js` / `api.js` yorum taraması; bulgular yukarıda.
- [x] 2026-10-05 — Granularity + ilişki katmanı frontend entegrasyonu; "Analiz Et" DB-geneli (tüm kullanıcı şemaları, sistem hariç). (09-14 günlüğünde de geçiyor; tarih çelişkisi.)
- [x] 2026-09-14 — Dashboard şablonları (5 preset + Boş; "+ Yeni Dashboard" ve "Şablon Uygula"); Sorgu Oluşturucu şema seçici (`?schema=`); MSSQL TOP/OFFSET-FETCH + şema-qualified FROM; Sorgu Oluşturucu'da "Önerilen İlişkiler"; granularity frontend entegrasyonu.
- [x] 2026-09-11 — Granularity + ilişki katmanı backend (AdventureWorks2022'de 34 FK ilişkisi doğrulandı).
- [x] 2026-08-27 — DuckDB PoC (600K satır cross-source JOIN, 873 ms, 27 MB). SBX parantez önceliği (`_p()`) düzeltmesi deploy edildi (4 dialekt, DIVIDE testi 4/4, md5 `39a99468…`). Rekabet analizi (Metabase/Superset/Lightdash) güncellendi.
- [x] 2026-08-16 — SBX Kademe 1 (grammar + compiler + 17 fonksiyon, 4 dialekt; 5/5 senaryo); DIALECT_MAP güncellendi.
- [x] Tarih belirsiz — `docs/` klasörü + kapsamlı README.md GitHub'a push edildi (repo: `SHapeloglu/super_bi`). Rekabet araştırması genişletildi (WrenAI, Vanna, Superset SIP-166, Metabase Metabot/X-rays).
- [x] Temmuz 2026 (tarih tam bilinmiyor) — Bağlantı parolalarının Fernet ile şifrelenmesi ve restart sonrası otomatik yeniden bağlanma (`app/core/crypto.py`, `password_enc`); hesaplanmış alan formüllerinde `;` reddi; sqlglot `==25.34.1` tam sürüm pin. Sunucuda doğrulandı 2026-09-15.


## 🔐 #212 yetki/hata bulguları — çözüm karşılaştırması (2026-10-27)

Yedek: `/root/yedekler/superbi-oncesi-20261027/` (app + task.md). Canlı DB/servise dokunulmadı; commit yok. Not: 5 madde kodda önceden giderilmiş çıktı, yalnız md/yorum geride kalmıştı.

| Madde | Seçenekler (fayda / maliyet / risk) | Karar | Durum |
|---|---|---|---|
| `get_analysis_results` sahiplik | A) Fonksiyon içinde `repo.get` + owner/admin kontrolü: basit, 404 ile varlık sızdırmaz, risk düşük. B) Ortak `Depends(require_conn_owner)`: tekrarı azaltır ama tüm analyze uçlarını dokunur, orta risk. | A (zaten var; `resolve_connection_engine` ile birleştirme sonra) | Doğrulandı + test |
| `/commit` cache_key sahipliği | A) `executor.commit` içinde `entry.user_id` karşılaştırma: kilit altında atomik, tek yer. B) Endpoint'te ayrı kontrol: çift mantık, yarış riski. | A (zaten var) | Yorum düzeltildi + test |
| İlk-admin yarışı | A) INSERT içinde `CASE WHEN COUNT(*)=0`: atomik, süreçler arası güvenli, şema değişmez. B) `threading.Lock`: tek süreçte yeter, çoklu worker'da yetmez. C) Ortam değişkeniyle admin tohumlama: en sağlam ama kurulum akışını değiştirir. | A | Uygulandı + test (8 thread, tek admin) |
| Cache isabetinde commit | A) İsabette `commit=True` ise kayıt kalıcılaştır (TTL kısaltılmaz). B) Cache anahtarına `commit` ekle: çift kayıt, bellek artar. | A | Uygulandı + test |
| `/api/health` yol sızıntısı | Zaten kaldırılmış. | - | Doğrulandı |
| `VisitError` | Zaten `compile_sbx` içinde çevriliyor. | - | Doğrulandı |
| Cache anahtarı `sample`/`mode` | `sample` zaten var; `mode` bilerek yok (memory modu live kaydı okuyabilsin). Anahtara eklemek memory/live ayrımını bozar. | Değiştirme | Kapatıldı |
| NLQ ↔ analyze alan uyumsuzluğu (`table_name`/`table`, `limit`/`sample`) | A) `plan_builder` çıktısına `sample` ekle + `slot_filler` girişinde dönüştürücü (adaptör): küçük ama NLQ henüz canlı akışa bağlı değil, doğrulama verisi yok. B) Analyze çıktısını NLQ biçimine uydur: API sözleşmesini bozar, riskli. | A önerilir, uygulanmadı (NLQ henüz bağlanmadı, uçtan uca test verisi yok); bağlama işi başlayınca birlikte yapılacak | Tasarım |

### Test
`/opt/superbi/tests/test_yetki.py` (6 test, yalnız bellek içi SQLite; çalıştırma: `venv/bin/python tests/test_yetki.py`): 6/6 geçti. Sınır: venv'de pytest/httpx yok, HTTP katmanı (TestClient) denenmedi; sahiplik fonksiyon çağrısıyla test edildi.

### Yeni küçük bulgular
- [ ] `register`: kullanıcı adı kontrolü «sorgula sonra ekle»; eşzamanlı aynı ad UNIQUE ihlalinde 500 dönebilir (409 olmalı) — `IntegrityError` yakalanmalı.
- [ ] `UserRepository.count()` artık kullanılmıyor; kaldırılabilir.
- [ ] Değişikliklerin canlıya alınması için konteyner yeniden derlemesi gerekir (kullanıcı onayıyla).
