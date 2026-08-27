# SuperBI

Self-hosted, full-stack **Business Intelligence** platformu — Power BI / Qlik Sense'e açık kaynak, kendi sunucunuzda barındırılan bir alternatif.

Verileriniz hiçbir zaman sizin altyapınızdan çıkmaz. Oracle, MSSQL, MySQL ve PostgreSQL kaynaklarınıza doğrudan bağlanır, DAX'a benzer bir ifade diliyle (**SBX**) hesaplanmış alanlar/metrikler tanımlamanızı sağlar ve sonucu ECharts ile görselleştirir.

---

## Neden SuperBI?

Kurumsal BI araçları iki uçta kutuplaşmış durumda:

- **Power BI / Qlik Sense (ücretli):** Kullanımı kolay ama veriniz bulutta (Power BI) ya da self-hosted seçenek fiilen terk ediliyor (Qlik Cloud'a geçiş).
- **Metabase / Superset (açık kaynak):** Self-hosted ama DAX benzeri bir ifade dili yok — Power BI'dan gelen kullanıcılar sıfırdan SQL öğrenmek zorunda.

**SuperBI bu ikisinin arasındaki boşluğu dolduruyor:** tamamen self-hosted, ama Excel/DAX sözdizimine yakın bir formül dili (SBX) sunuyor.

## Özellikler

- 🔌 **Çoklu veritabanı desteği** — Oracle, MSSQL, MySQL, PostgreSQL (SQLite metadata deposu olarak dahili)
- 🔐 **Şifreli bağlantı yönetimi** — bağlantı parolaları Fernet ile şifrelenip saklanır, servis yeniden başlatıldığında otomatik yeniden bağlanır
- 🧮 **SBX (SuperBI Expression Language)** — Excel/DAX benzeri sözdizimiyle hesaplanmış alan tanımlama: `IF([Kar] > 0, 'Pozitif', 'Negatif')`, `DIVIDE([Kar], [Satış], 0)`
- 🛡️ **Güvenli formül derleme** — kullanıcı formülleri whitelist tabanlı AST doğrulamasından geçer (blacklist değil); SQL injection'a kapalı
- 🔗 **Görsel sorgu oluşturucu** — tablo/kolon seçimi, JOIN, filtre, gruplama, sıralama; SQL yazmadan sorgu kurma
- 📊 **Dashboard ve görselleştirme** — Apache ECharts tabanlı grafikler
- 📜 **Sorgu geçmişi ve önbellek** — çalıştırılan sorgular gruplanır, istatistikleri tutulur, sonuç önbellekleme desteklenir
- 🌐 **Dialect-agnostic SQL üretimi** — `sqlglot` ile tek bir sorgu tanımı, hedef veritabanına göre doğru SQL'e derlenir (Oracle'da `FETCH FIRST`, MSSQL'de `TOP`/`OFFSET-FETCH` vb.)

## Mimari

```
┌────────────────────────────────────────────────────────┐
│                     Frontend (Vanilla JS)                │
│              index.html · app.js · api.js                │
└──────────────────────────┬──────────────────────────────┘
                            │ REST API
┌──────────────────────────▼───────────────────────────────┐
│                    FastAPI Backend (app/)                │
│                                                            │
│  api/        auth · connections · datasets · dashboard    │
│              drivers · history · query · schema           │
│                                                            │
│  services/   sql_builder      → sorgu inşası               │
│              expression_builder → formül doğrulama (SBX+SQL)│
│              sbx_compiler      → SBX → SQL derleyici (lark) │
│              query_executor    → sorgu çalıştırma           │
│                                                            │
│  core/       connector_registry → DB bağlantı havuzu       │
│              crypto             → Fernet şifreleme         │
│              repository         → metadata CRUD            │
│                                                            │
│  auth/       JWT tabanlı kimlik doğrulama                  │
│  db/         SQLite metadata deposu                        │
└──────┬──────────┬──────────┬──────────┬────────────────────┘
       │          │          │          │
   ┌───▼───┐  ┌───▼───┐  ┌───▼───┐  ┌───▼───┐
   │Oracle │  │ MSSQL │  │ MySQL │  │Postgre│
   │  XE   │  │       │  │       │  │  SQL  │
   └───────┘  └───────┘  └───────┘  └───────┘
```

Detaylı mimari notları için [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) dosyasına bakın.

## SBX — SuperBI Expression Language

Power BI'daki DAX'a, Excel'deki formül sözdizimine benzer bir ifade dili. Kullanıcı arayüzünde hesaplanmış alan tanımlarken şu şekilde yazılır:

```
IF([Kar] > 0, 'Pozitif', 'Negatif')
DIVIDE([Kar], [Satış], 0)
ROUND([Fiyat] * 1.20, 2)
[Ad] & ' ' & [Soyad]
SUM([Satış])
```

Bu ifadeler `lark` ile ayrıştırılıp `sqlglot` ile hedef veritabanı dialect'ine (Oracle/MSSQL/MySQL/PostgreSQL) derlenir. Desteklenen fonksiyonlar: `IF`, `DIVIDE`, `ROUND`, `CONCAT`, `DATEDIFF`, `ISNULL`, `SUM`/`AVG`/`COUNT`/`MIN`/`MAX`, `UPPER`/`LOWER`/`ABS`/`LEN`/`TRIM`/`COALESCE`.

**Güvenlik modeli:** Formüller çalıştırılmadan önce whitelist tabanlı bir AST doğrulamasından geçer — izin verilmeyen hiçbir SQL yapısı (subquery, DDL, vb.) formüle giremez.

> SBX şu an **Kademe 1** aşamasında: satır bazlı hesaplamalar için tam işlevsel. Dashboard filtrelerine duyarlı "measure" kavramı (DAX'taki `CALCULATE` benzeri context manipülasyonu) yol haritasında.

## Kurulum

### Gereksinimler

- Python 3.10+
- Bir veya daha fazla hedef veritabanı (Oracle/MSSQL/MySQL/PostgreSQL) — opsiyonel, sadece SQLite ile de çalışır

### Adımlar

```bash
git clone https://github.com/SHapeloglu/super_bi.git
cd super_bi
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Gerekli ortam değişkenlerini ayarlayın (örnek `systemd` servis dosyası aşağıda):

```bash
export DATALENS_DB=/opt/superbi/data/superbi.db
export DATALENS_JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export DATALENS_CORS_ORIGINS=https://your-domain.com
export DATALENS_DB_ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
```

> ⚠️ `DATALENS_DB_ENCRYPTION_KEY`'i güvenli bir yerde yedekleyin. Bu anahtar kaybolursa, önceden şifrelenmiş tüm PostgreSQL/MySQL/MSSQL bağlantı parolaları geri getirilemez hale gelir.

Çalıştırın:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Production (systemd + Nginx)

```ini
# /etc/systemd/system/superbi.service
[Unit]
Description=SuperBI FastAPI Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/superbi
Environment="DATALENS_DB=/opt/superbi/data/superbi.db"
Environment="DATALENS_JWT_SECRET=..."
Environment="DATALENS_CORS_ORIGINS=https://your-domain.com"
Environment="DATALENS_DB_ENCRYPTION_KEY=..."
ExecStart=/opt/superbi/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now superbi
```

Nginx ile reverse proxy + Let's Encrypt TLS önerilir.

## Veritabanı Bağlantısı Ekleme

Opsiyonel driver'lar (`psycopg2`, `PyMySQL`, `pyodbc`) lazy kurulur — gerektiğinde `/api/drivers/{db_type}/install` endpoint'i üzerinden veya elle:

```bash
pip install psycopg2-binary PyMySQL pyodbc
```

MSSQL bağlantı dizesi ODBC Driver 18 gerektirir:
```
?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
```

## Proje Yapısı

```
super_bi/
├── app/
│   ├── api/              # REST endpoint'leri (auth, connections, datasets, dashboard, query, schema, drivers, history)
│   ├── auth/              # JWT kimlik doğrulama
│   ├── core/              # connector_registry, crypto, repository
│   ├── db/                # SQLite metadata store
│   ├── models/            # Pydantic şemaları
│   ├── services/          # sql_builder, expression_builder, sbx_compiler, query_executor
│   └── main.py            # FastAPI giriş noktası
├── frontend/               # Vanilla HTML/CSS/JS + ECharts
├── scripts/                # Yedekleme betikleri
├── docs/                   # Mimari kararlar, session özetleri, backlog
└── requirements.txt
```

## Yol Haritası

Güncel durum için [`docs/TASKS.md`](docs/TASKS.md) ve [`docs/BACKLOG.md`](docs/BACKLOG.md) dosyalarına bakın. Öne çıkanlar:

- [ ] **DuckDB tabanlı in-memory ilişkisel model katmanı** — farklı kaynaklardan (örn. Oracle + MySQL) gelen veri setlerini tek bir motor üzerinde ilişkilendirme
- [ ] Incremental (delta) veri yenileme
- [ ] Excel/CSV/JSON dosya kaynağı desteği
- [ ] Frontend SBX editörü (syntax highlighting)
- [ ] SBX Kademe 2 — dashboard filtrelerine duyarlı measure'lar

## Güvenlik Notları

- Bağlantı parolaları Fernet ile şifrelenip saklanır (bkz. [`docs/OKUBENI_ENCRYPTION.md`](docs/OKUBENI_ENCRYPTION.md))
- Hesaplanmış alan formülleri whitelist tabanlı AST doğrulamasından geçer, `sqlglot` sürümü kasıtlı olarak sabitlenmiştir (bkz. [`docs/OKUBENI_FIX.md`](docs/OKUBENI_FIX.md))
- `sqlglot` sürümünü yükseltmeden önce `expression_builder.py`'nin güvenlik testlerini mutlaka yeniden çalıştırın

## Teknoloji Yığını

| Katman | Teknoloji |
|---|---|
| Backend | FastAPI, SQLAlchemy 2.x, Pydantic 2.x |
| Kimlik doğrulama | PyJWT |
| Şifreleme | `cryptography` (Fernet) |
| Formül dili | `lark` (LALR parser) + `sqlglot==25.34.1` |
| Frontend | Vanilla HTML/CSS/JS |
| Görselleştirme | Apache ECharts |
| Metadata deposu | SQLite |
| Veri kaynakları | Oracle, MSSQL, MySQL, PostgreSQL |
| Deployment | systemd, Nginx, Let's Encrypt |

## Katkıda Bulunma

Bu proje aktif geliştirme aşamasındadır. Issue ve PR'lar memnuniyetle karşılanır.

## Lisans

*(Lisans belirtilmemiş — eklemek isterseniz LICENSE dosyası oluşturun.)*
