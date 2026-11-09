# CLAUDE.md

Bu projenin tek Claude talimat ve bağlam dosyası budur. Eski `docs/CLAUDE.md` (2026-09-16) buraya birleştirildi (2026-10-25); eski dosya silindi, yedeği `/root/yedekler/md-birlestirme-20261025/opt/superbi/docs/CLAUDE.md`. Eski kayıtlarda `(eski kayıt)` ile işaretli bilgi, güncel doğrulama ile çelişirse güncel olan geçerlidir.

## Proje

SuperBI: self-hosted BI platformu (Power BI / Qlik Sense alternatifi). FastAPI + SQLAlchemy (Python), Vanilla HTML/CSS/JS, Apache ECharts. SBX formül dili (Lark + sqlglot), kural tabanlı Türkçe NLQ (planlama aşamasında), çok veritabanlı bağlantılar (PostgreSQL / MySQL / MSSQL / Oracle), granularity ve ilişki analizi.

**Hedef:** DAX benzeri formül dili + Türkçe doğal dil SQL asistanı + cross-database JOIN; tümü self-hosted, maliyet sıfır.

**Repo:** https://github.com/SHapeloglu/super_bi (public, `main`).

**Geliştirici/yönetici:** powerbiegitimi.com (eski kayıt; alan adı doğrulanmalı).

## Konum

- **Çalışma kopyası (tek kaynak):** `/opt/superbi` — git deposu. Canlı kod `release/2026-11-09` (`127c74d`, 2026-11-09). GitHub `main` eski; release PR bekliyor. Özellik dalları `/opt/superbi-wt/<ad>` worktree'lerinde.
- `/root/superbi/` — yalnız `backend/sbx/` içeriyor (eski/ayrı kopya; `compiler.py` `/opt/superbi/app/services/sbx_compiler.py` ile aynı değil). Canlı kaynak sayılmaz; değiştirilmeden bırakılır.
- Canlı alan adı: `superbi.bidanismanlik.com.tr` (host nginx: `/` → `frontend/`, `/api/` → `127.0.0.1:8000`).

## Çalıştırma

```bash
cd /opt/superbi && docker compose up -d --build     # konteyner: superbi (127.0.0.1:8000)
docker logs --tail 100 superbi
docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' superbi
```

- AutoSleep (`/opt/autosleep/ek_projeler.py`, 2026-10-18'den beri Docker'da) boşta kalan konteyneri durdurabilir; bu bilinçli davranıştır, hata değildir. Konteyner 2026-11-09 release'inden beri çalışıyor.
- Veri: `/opt/superbi/data/superbi.db` (konteynerde `/data`). Günlük yedek: `scripts/backup.sh` → `/opt/superbi/backups/`.
- Eski kayıt (2026-09-16): servis systemd idi; Docker'a geçildi.

## Kurallar

- Canlıya dokunan işlemler (restart, deploy, nginx) kullanıcı onayıyla yapılır.
- Deploy: önce `/root/yedekler/predeploy-YYYYMMDD-HHMM/` yedeği ve `superbi:pre-*-YYYYMMDD-HHMM` imaj etiketi; sonra `docker compose up -d --build`. Geri dönüş etiketli imajla yapılır.
- Test: önce sandbox'ta doğrula (`make test`), sonra canlıya al. Görevler sıralı tamamlanır (hatasız, tam test → production).
- `sqlglot==25.34.1` sabit; hiçbir zaman yükseltilmez. Yükseltme SBX derlemesini kırar; yükseltmeden önce `expression_builder` güvenlik testleri çalıştırılır.
- `_p()` parantez helper'ı SBX derleyicisinde zorunlu; kaldırılmaz. Elle inşa edilen sqlglot expression'larında SQL'e `exp.Paren()` ile sarılmadan parantez garanti değil.
- SQL string'i elle yazılmaz; sqlglot AST üzerinde çalışılır.
- `;` içeren formüller `expression_builder.py`'de reddedilir; bu davranış kaldırılmaz.
- `.env` ve `DATALENS_DB_ENCRYPTION_KEY` değerleri md'ye ve git'e yazılmaz; yalnız değişken adı geçer.
- Kök dizindeki `apply_*.py` / `patch_*.py` betikleri ve boş dosyalar (`odoo_test`, `pbixdb`, `superbi.db`) eski yamalardır; veri kaynağı değildir.
- Md dosyaları Türkçe yazılır. Md seti kök dizindeki beş dosya: `architect.md`, `CLAUDE.md`, `backlog.md`, `session.md`, `task.md` (tek kaynak). Yeni açık madde `task.md` 🔜 bölümüne; planlanmamış fikir `backlog.md`ye yazılır.
- Dokümantasyon senkron kaybı: md dosyaları koddan geride kalabiliyor (2026-09-16'da 3-4 hafta gerideydi). Her oturum sonunda md dosyalarının GERÇEKTEN sunucuya yazıldığı doğrulanır.

## Dosya transferi ve sunucu çalışması (eski kayıt, 2026-09-16)

- Kayıtta: Claude'un sunucuya doğrudan erişimi yoktu; SSH ile kullanıcı komut çalıştırıp çıktıyı yapıştırıyordu. Güncel erişim durumu her oturumda doğrulanır.
- Dosya transferi: scp tercih edilir (Windows Downloads → sunucu). Patch'ler sandbox'ta yazılıp syntax + fonksiyonel test edildikten sonra `.py` patch script olarak teslim edilir (str_replace tabanlı, replace_once güvenlik kontrolüyle). Her transferde md5 doğrulanır.
- Uzun heredoc SSH terminalinde ~1024 karakterde kesiliyor ve Türkçe karakter sorunu çıkarıyor → `base64 -w76` ile sarma veya scp.
- FileZilla transferlerinde dosya boyutu kontrol edilir.

## İletişim

- Türkçe, kısa ve doğrudan. Mümkünse liste yerine düz yazı; başta özet.
- Öneri verilirken kendi önerini yap; açık uçlu seçim sunma ("Şunu yapıyoruz" dili, "Ne düşünüyorsun?" yok).
- Sorun: önce kök nedeni tartış, sonra çözüm.

## Teknik kısıtlar ve tuzaklar

- **sqlglot pin 25.34.1:** AST ayrıştırması sürüme özgü. Yükseltme SBX'i kırar.
- **Operatör önceliği:** Binary, Connector, Unary, Not node'ları `_p()` ile sarılır. Fazla parantez zararsız; eksik parantez sessiz yanlış sonuç.
- **Formül güvenliği:** `;` reddi sürümden bağımsız. (Eski kayıt: sqlglot 25.x `;` kısmını sessizce kırpıyordu, 30.x reddediyordu.)
- **MSSQL'de LIMIT yok:** `sql_builder` offset=0 için `SELECT TOP n`, offset>0 için `OFFSET...FETCH NEXT` üretir (ORDER BY yoksa `ORDER BY (SELECT NULL)`).
- **Önizleme dialekti:** Preview endpoint'i seçili bağlantının gerçek `db_type`'ını kullanır (önceden hep sqlite varsayılıyordu).
- **Çok şemalı DB'ler (MSSQL/PostgreSQL):** `?schema=` parametresi var. AdventureWorks2022 gibi named-schema DB'lerde asıl tablolar dbo DIŞINDA (Sales, Production, Person, HumanResources, Purchasing).
- **Şema desteği sınırı:** `schema_name` canlı Sorgu Oluşturucu'da ve dataset backend'inde var. Frontend "Dataset Olarak Kaydet" payload'ı `schema_name` ve `calculated_fields`'i henüz göndermiyor (task.md 🔜).
- **Fernet anahtarı:** `DATALENS_DB_ENCRYPTION_KEY` yedeklenmeli (JWT secret gibi). Kaybolursa kayıtlı parolalar kurtarılamaz. Anahtar DB dosyasından ayrı tutulur.
- **Zorunlu ortam değişkenleri:** `DATALENS_JWT_SECRET`, `DATALENS_DB_ENCRYPTION_KEY`, `DATALENS_DB` (eksikse uygulama açılmaz). Kayıt kapalı (`DATALENS_ALLOW_REGISTER`), SQLite kökü (`DATALENS_SQLITE_ROOT`) ve DB host listesi (`DATALENS_ALLOWED_DB_HOSTS`) ayrı kurallardır. Değerleri yazılmaz.
- **Kapasite (eski kayıt 2026-09-16):** 7.8 GB RAM, swap dolu, 12 konteyner. DuckDB ingest öncesi RAM planlaması şart; büyümede 16 GB+ veya ayrı VPS. Güncel değer doğrulanmalı.
- **Dokümantasyon senkron kaybı:** bkz. Kurallar.

## Araç sürümleri

| Kütüphane | Sürüm | Not |
|---|---|---|
| sqlglot | 25.34.1 | Pinned (==). AST ayrıştırması sürüme özgü; whitelist güvenliğinin temeli. |
| lark | latest | LALR parser (SBX grammar) |
| FastAPI | latest | REST backend |
| SQLAlchemy | 2.x | ORM |
| duckdb | 1.5.5 | PoC'te test edildi; prod'da henüz yok. |
| cryptography | latest | Fernet şifreleme (bağlantı parolaları) |

## Kod konvansiyonları

- Backend: Python 3.x, type hints, Pydantic 2.x.
- Frontend: Vanilla JS (transpile yok).
- SQL: sqlglot AST; string birleştirme yok.
- Test: sandbox'ta doğrula, sonra production'a deploy.

## Mimari (özet; ayrıntı `architect.md`)

- Granularity: grain tespiti (COUNT(*) vs COUNT(DISTINCT col), %100 tekillik = anahtar); sütun sınıflandırma (identifier/categorical/metric/date_axis); ilişki bulma: FK constraint (confidence 1.0) + LEFT JOIN orphan testi (inferred).
- NLQ: 6 niyet kalıbı, LLM yok; kalıp dışı sorularda `Anlayamadım, şu kalıpları deneyin` yanıtı. İsteğe bağlı BYOK LLM fallback yalnız şema metadata ile.
- DuckDB ingest yapılandırması (planlı): persisted mod, memory_limit 1.5 GB, threads=2, SBX hedefi tek dialekt duckdb (ayrıntı backlog.md).

## Diğer çalışma dosyaları

- Md seti (kök, tek kaynak): `architect.md` · `task.md` · `backlog.md` · `session.md` · `CLAUDE.md`
- `docs/OKUBENI_ENCRYPTION.md` · `docs/OKUBENI_FIX.md` (ek belgeler; kalır)
- `README.md` (public-facing; güncelleme bekliyor, bkz. task.md)

---

Son güncelleme: 2026-11-09 (release `127c74d` durumu, yetki/RLS, deploy kuralı).
