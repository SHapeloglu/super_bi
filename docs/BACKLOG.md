# Backlog — SuperBI

## 🔴 Acil / Bug Fix
- [ ] Düzeltilmiş `compiler.py` (parantez önceliği fix) sunucuya deploy edilmeli
      — sunucu versiyonu DIVIDE gibi bileşik ifadelerde yanlış sonuç üretebilir
      (bkz. SESSION.md, 2026-08-27 girdisi — kök neden ve test detayları orada)

## Mimari (yüksek öncelik)
- [ ] DuckDB ingest katmanı tasarımı ve entegrasyonu
  - Kaynak DB'lerden (Oracle/MSSQL/MySQL/Postgres) DuckDB'ye veri çekme mekanizması
  - Persisted dosya modu, memory_limit=1.5GB, threads=2 (VPS kısıtına göre)
  - SBX compiler hedefini tek dialect'e (duckdb) sabitleme
  - PoC sonucu doğrulandı: 600K satır cross-source JOIN = 873ms, 27MB memory
- [ ] `datasets_relationships` tablosu — DuckDB üzerinde JOIN tanımları
- [ ] Incremental refresh — DuckDB ingest'in delta yükleme stratejisi
- [ ] Production VPS kapasitesi kararı — mevcut 7.8GB RAM sınırlı (swap zaten
      5.8GB dolu, 12 Docker container çalışıyor), büyümede 16GB+ veya ayrı VPS

## Özellikler
- [ ] Excel/CSV/JSON dosya kaynağı desteği (upload + parse connector)
- [ ] Frontend SBX editörü (alan listesi + syntax highlighting)
- [ ] Kademe 2 (SBX): measure + dashboard filtre context
- [ ] Kademe 3 (SBX): VAR/RETURN, ileri context manipülasyonu (opsiyonel)
- [ ] Undo/redo end-to-end testi (özellik hazır, test bekliyor)

## Dokümantasyon / Repo
- [x] docs/ klasörü + kapsamlı README.md GitHub'a eklendi (2026-08-27)
- [ ] LICENSE dosyası eklenmedi — proje açık kaynak yayınlanacaksa gerekli

## İptal edilenler
- ~~SQLite frontend connector~~ — gereksiz, talep gelmedi

## Rekabet notları (referans, aksiyon değil)
- Lightdash: dbt'ye kilitli, SuperBI'nin "dbt'siz formül" konumu benzersiz
- Metabase/Superset: DAX-benzeri ifade dili yok
- Qlik: self-hosted'ı fiilen terk ediyor, Power BI tamamen bulut —
  "veri egemenliği" mesajı SuperBI için boşluk
