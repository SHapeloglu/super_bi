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

## 2026-11-08 — Faz 0.1 + 0.2 (güvenlik) — branch fix/security-sqlite-roles

**Değişenler:**
- `app/core/sqlite_policy.py` (yeni): SQLite yolu yalnızca DATALENS_SQLITE_ROOT altında, var olan, metadata olmayan dosyalara izin verir; salt okunur (mode=ro) açılır. Root tanımsızsa SQLite kapalı.
- `connector_registry._build_url`: sqlite dalı politikadan geçiyor (reconnect dahil).
- `api/connections.py`: POST ve DELETE artık yalnız admin (require_role). Silme sahip kontrolü kaldırıldı (plan gereği).

**Testler:** tests/security/test_sqlite_and_roles.py — 11/11 (önce 0/11 kırmızı görüldü). tests/test_yetki.py 6/6.

**Veri:** Canlı DB'de SQLite bağlantısı yok; mevcut kayıtlar etkilenmez. Yedek: /root/yedekler/superbi.db.bak-20261108-0953

**Kalan risk / açık:**
- Canlı imaj eski; değişiklik deploy edilene kadar yürürlükte değil (onay bekliyor).
- Viewer'lar UI'da bağlantı oluşturma/silme butonlarını görmeye devam eder; 403 alırlar. UI gizleme ayrı iş.
- Viewer olarak sahip olunan eski bağlantıları artık yalnız admin silebilir.
- 0.4 (SSRF, ham hata metni) ve 0.3, 0.5, 0.6 bu branch'te yok.
