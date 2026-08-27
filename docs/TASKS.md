# Yapılacaklar

## 🔴 Acil
- [ ] Düzeltilmiş `compiler.py` (parantez önceliği fix) sunucuya deploy et
      — mevcut sunucu versiyonu DIVIDE gibi bileşik ifadelerde yanlış sonuç üretebilir

## Sırada
- [ ] DuckDB ingest katmanı — tasarım + ilk entegrasyon
- [ ] `datasets_relationships` tablosu (DuckDB üzerinde JOIN tanımları)
- [ ] Incremental refresh (DuckDB ingest ile birleşik tasarlanacak)

## Sonra
- [ ] Excel/CSV/JSON dosya kaynağı desteği
- [ ] Frontend SBX editörü (alan listesi + syntax highlighting)
- [ ] Kademe 2 (measure + dashboard filtre context)
- [ ] Kademe 3 (VAR/RETURN, opsiyonel)
- [ ] Undo/redo end-to-end testi
- [ ] Production VPS kapasite kararı (RAM yükseltme veya ayrı VPS)

## Tamamlandı ✅
- [x] SBX Kademe 1 — grammar + derleyici + backend entegrasyonu (2026-08-16)
- [x] Rakip analizi: Power BI/Qlik/Metabase/Superset/Lightdash (2026-08-27)
- [x] DuckDB PoC — cross-source JOIN doğrulandı, 873ms/27MB (2026-08-27)
- [x] SBX parantez önceliği bug fix — yerelde tamam, deploy bekliyor (2026-08-27)
- [x] docs/ klasörü + kapsamlı README.md GitHub'a push edildi (2026-08-27)

## İptal
- ~~SQLite frontend desteği~~ — gereksiz, talep gelmedi
