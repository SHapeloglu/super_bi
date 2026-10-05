# Yapilacaklar

## Acil
- Hepsi bitti

## Sirada
- [ ] Kural tabanli Turkce NLQ (Kademe 1, LLM yok) — on kosul (granularity +
      iliski katmani, Onerilen Iliskiler) tamamlandi, baslanabilir. Ilk kalip
      olarak Top-N siralama onerildi (sql_builder'in order_by/limit
      altyapisi zaten hazir, en az yeni kod gerektiren kalip).
- [ ] DuckDB ingest katmani — tasarim + ilk entegrasyon
- [ ] datasets_relationships uzerinde DuckDB entegrasyonu (cross-DB JOIN)
- [ ] Incremental refresh (DuckDB ingest ile birlesik tasarlanacak)
- [ ] Dogrulama bekliyor: Kaydedilmis dataset'ler ve dashboard widget'lari
      icin sema destegi. schema_name su an sadece canli Sorgu Olusturucu
      akisinda (preview/run/stream) calisiyor; "Dataset Olarak Kaydet" ve
      widget'a baglama akisi bilincli olarak dokunulmadi.

## Sonra
- [ ] Excel/CSV/JSON dosya kaynagi destegi
- [ ] Frontend SBX editoru (alan listesi + syntax highlighting)
- [ ] Kademe 2 (measure + dashboard filtre context)
- [ ] Kademe 3 (VAR/RETURN, opsiyonel)
- [ ] Undo/redo end-to-end testi
- [ ] Production VPS kapasite karari (RAM yukseltme veya ayri VPS)
- [ ] Native kolon aciklamalari -> LLM baglami (dusuk oncelik): MSSQL
      sys.extended_properties/MS_Description, Oracle
      USER_COL_COMMENTS/ALL_COL_COMMENTS, PostgreSQL pg_description,
      MySQL COLUMN_COMMENT. Sadece LLM baglami icin — granularity
      katmaninin deterministik tespitine GIRDI OLMAYACAK. Kural tabanli
      NLQ + BYOK LLM fallback'ten sonra.
- [ ] Gorsel iliski editoru (dataset/sema node-link diyagrami) — mevcut
      metin/liste formundaki "Onerilen Iliskiler"in gorsel versiyonu.

## Tamamlandi
- [x] Baglanti sifrelerinin Fernet ile sifrelenmesi — app/core/crypto.py,
      password_enc kolonu, deps.py uzerinden PostgreSQL/MySQL/MSSQL icin
      otomatik yeniden baglanma. DATALENS_DB_ENCRYPTION_KEY systemd servis
      dosyasinda ayarli. Sunucuda dogrulandi (2026-09-15) — ayri bir
      oturum notu bulunamadi, muhtemelen daha once deploy edildi (dosya
      mtime: Temmuz).
- [x] Hesaplanmis alan formullerinde noktali virgul reddi —
      expression_builder.py'de sqlglot surum farkina bagli tutarsizlik
      kapatildi, sqlglot ==25.34.1 tam surume sabitlendi. Sunucuda
      dogrulandi (2026-09-15).
- [x] Dashboard yerlesim sablonlari (5 preset: Klasik, Odak Grafik,
      Metrik Yogun, Izgara, Karma) — "+ Yeni Dashboard" template picker +
      mevcut dashboard'a toolbar'dan "Sablon Uygula"
- [x] Granularity + iliski katmani frontend entegrasyonu — Baglantilar
      sayfasina "Analiz Et" / "Sonuclar" butonlari ve sonuc tablolari baglandi
- [x] "Analiz Et" DB-geneli hale getirildi — tek tikla tum kullanici
      semalari taraniyor (sistem semalari haric)
- [x] Sorgu Olusturucu'ya "Sema" secici — /api/schema/{id}/schemas
      endpoint'i + ?schema= destegi
- [x] MSSQL SQL uretim bug fix'i — TOP/OFFSET-FETCH, sema-qualified
      base_table, preview gercek dialect'i gosteriyor
- [x] Sorgu Olusturucu'ya "Onerilen Iliskiler" — DB-geneli analiz edilmis
      iliskileri listeler, tek tik/"Tumunu Ekle" ile join ekler
- [x] SBX Kademe 1 — grammar + derleyici + backend entegrasyonu
- [x] Rakip analizi: Power BI/Qlik/Metabase/Superset/Lightdash
- [x] DuckDB PoC — cross-source JOIN dogrulandi, 873ms/27MB
- [x] SBX parantez onceligi bug fix — deploy edildi ve dogrulandi (md5
      match, DIVIDE testi 4/4 dogru, 4 dialect)
- [x] docs/ klasoru + kapsamli README.md GitHub'a push edildi
- [x] Rekabet arastirmasi genisletildi: WrenAI, Vanna, Superset SIP-166,
      Metabase Metabot/X-rays

## Iptal
- SQLite frontend destegi — gereksiz, talep gelmedi
