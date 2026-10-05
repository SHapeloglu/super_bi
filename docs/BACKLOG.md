# Backlog — SuperBI

## Acil / Bug Fix
- Hepsi bitti — sirasiyla: SBX parantez onceligi, baglanti sifreleme
  (Fernet), noktali virgul reddi, MSSQL LIMIT->TOP/OFFSET-FETCH + sema-qualified FROM

## Guvenlik (sunucuda dogrulandi 2026-09-15, deploy tarihi belirsiz)

- [x] Baglanti sifreleri sifreleniyor — app/core/crypto.py (Fernet),
  ConnectionMeta.password_enc, sqlite_store.py migration. deps.py artik
  PostgreSQL/MySQL/MSSQL baglantilarini da restart sonrasi otomatik
  yeniden kuruyor. DATALENS_DB_ENCRYPTION_KEY systemd servis dosyasinda,
  veritabani dosyasindan ayri tutuluyor — tam bir secrets vault kadar
  guclu degil ama tek-VPS kurulum icin makul bir yaklasim. Anahtar
  kaybolursa/degisirse onceden sifrelenmis tum sifreler kurtarilamaz —
  yedeklenmesi kritik, JWT secret gibi ele alinmali.

- [x] Formullerde noktali virgul reddi — kok neden: sunucudaki sqlglot
  25.34.1, test edilen 30.12.0'dan farkli davraniyordu (bir formulu 25.x
  sessizce kirpip sadece bir kismini aliyordu, 30.x reddediyordu). Ikisi
  de fonksiyonel olarak guvenliydi ama versiyona bagli ongorulemez
  davranis riskliydi. expression_builder.py artik noktali virgulu acikca,
  surumden bagimsiz reddediyor. requirements.txt'te sqlglot ==25.34.1'e
  tam surume sabitlendi.

## Mimari (yuksek oncelik)

- [x] Tablo granularity + iliski katmani — datasets_relationships'i
  genisletir. Backend (grain tespiti, sutun siniflandirma, referans
  butunlugu/orphan testi, FK kesfi) zaten tamdi; frontend'e baglandi
  (Baglantilar -> Analiz Et/Sonuclar) ve DB-geneli hale getirildi.

- [ ] DuckDB ingest katmani tasarimi ve entegrasyonu
  - Kaynak DB'lerden DuckDB'ye veri cekme mekanizmasi
  - Persisted dosya modu, memory_limit=1.5GB, threads=2
  - SBX compiler hedefini tek dialect'e (duckdb) sabitleme
  - PoC sonucu dogrulandi: 600K satir cross-source JOIN = 873ms, 27MB memory
- [ ] Incremental refresh — DuckDB ingest'in delta yukleme stratejisi
- [ ] Production VPS kapasitesi karari — mevcut 7.8GB RAM sinirli

## Sorgu Olusturucu / Cok Semali DB Destegi

- [x] Sema secici — /api/schema/{conn_id}/schemas endpoint'i +
  tables/columns/foreign-keys'e opsiyonel ?schema= parametresi.
- [x] MSSQL SQL uretimi — offset=0 icin SELECT TOP n, offset>0 icin
  OFFSET...FETCH NEXT (ORDER BY yoksa otomatik fallback). base_table
  artik schema.table olarak qualify ediliyor.
- [x] Onerilen Iliskiler — Sorgu Olusturucu'da tablo secilince,
  /api/analyze/{conn_id}/results'tan ilgili iliskileri cekip join
  onerisi olarak gosterir.
- [ ] Bilinen sinir / dogrulanmamis: Kaydedilmis dataset'ler ve dashboard
  widget'lari schema_name'i HENUZ tasimiyor.

## Ozellikler

- [x] Dashboard yerlesim sablonlari (Klasik / Odak grafik / Metrik yogun /
      Izgara / Karma) — saf frontend, "+ Yeni Dashboard" template picker
- [ ] Kural tabanli Turkce NLQ (Kademe 1) — LLM/ucretli servis YOK.
  On kosul artik tamam. Onerilen ilk adim: Top-N kalibi.
  - Niyet tespiti: anahtar kelime + regex kaliplari
  - Slot doldurma: fuzzy string matching
  - Doldurulan slotlar dogrudan sql_builder.py'nin JSON planina donusur
  - Kapsam disi sorularda kullaniciya desteklenen kalip ornekleri gosterilir
  - Ileride opsiyonel/varsayilan-kapali: BYOK LLM fallback
- [ ] Excel/CSV/JSON dosya kaynagi destegi
- [ ] Frontend SBX editoru
- [ ] Kademe 2 (SBX): measure + dashboard filtre context
- [ ] Kademe 3 (SBX): VAR/RETURN
- [ ] Undo/redo end-to-end testi

## Native Kolon Aciklamalari -> LLM Baglami (dusuk oncelik)
- [ ] Her DB tipinin sistem katalogundan kolon aciklamalarini okuyan bir
      servis fonksiyonu — kural tabanli NLQ'nun DISINDA, sadece LLM
      baglami icin.
  - MSSQL: sys.extended_properties
  - Oracle: USER_COL_COMMENTS, ALL_COL_COMMENTS (DBA_COL_COMMENTS degil)
  - PostgreSQL: pg_description
  - MySQL: INFORMATION_SCHEMA.COLUMNS.COLUMN_COMMENT
  - Not: granularity_analyzer.py'nin MS_Description'i deterministik
    tespitten haric tutma karariyla CELISMIYOR.

## Gorsel Iliski Editoru (Dataset/Sema Grafigi) — orta oncelik
- [ ] table_profiles + datasets_relationships verisini node-link diyagram
      olarak gosteren bir gorunum.

## Dokumantasyon / Repo
- [x] docs/ klasoru + kapsamli README.md GitHub'a eklendi
- [ ] LICENSE dosyasi eklenmedi

## Iptal edilenler
- SQLite frontend connector — gereksiz, talep gelmedi

## Rekabet notlari (referans, aksiyon degil)
- Lightdash: dbt'ye kilitli, SuperBI'nin "dbt'siz formul" konumu benzersiz
- Superset: Cekirdekte native NLQ/text-to-SQL yok (SIP-166 hala oneri asamasinda)
- Metabase: NLQ (Metabot, BYOK) VE otomatik veri profilleme (X-rays) zaten
  mevcut ve iyi durumda. Gercek fark noktalari: (1) SBX hala DAX seviyesinde
  bir formul dili sunuyor; (2) Turkce-oncelikli NLQ tasarimi; (3) NLQ
  ciktisinin SBX hesaplanmis alanlariyla entegre calismasi; (4) DuckDB ile
  gercek cross-database JOIN.
- Qlik: self-hosted'i fiilen terk ediyor, Power BI tamamen bulut
