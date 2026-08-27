# SuperBI Session — 2026-08-27

## Bu oturumda tamamlanan

### 1. SBX Kademe 1 — Sunucuya entegre edildi (önceki oturum, 08-16)
- `app/services/sbx_compiler.py`, `grammar.lark` deploy edildi
- `expression_builder.py` v2: SBX + SQL compat mode
- Test: 5/5 senaryo başarılı

### 2. Rakip analizi
- Power BI / Qlik Sense (ücretli) vs Metabase / Superset / Lightdash (açık kaynak)
- Bulgu: SBX'e en yakın rakip Lightdash ama dbt'ye kilitli; SuperBI'nin
  "dbt'siz formül" konumu benzersiz

### 3. Kritik mimari tespit: 4 mihenk taşı
Hedef: (1) kolay kullanım, (2) kolay karmaşık metrik, (3) memory'de depolama,
(4) memory'de veri seti ilişkisi. Mevcut SQL push-down mimarisi 3. ve 4.'yü
karşılamıyor — cross-database JOIN mimari olarak imkansız.

### 4. DuckDB PoC + KRİTİK BUG FIX
- 600K satır cross-source JOIN testi: 873ms, 27MB memory — başarılı
- sqlglot DuckDB dialect'i sorunsuz çalıştı
- **BULUNAN BUG:** `DIVIDE([tutar]-[maliyet], [tutar], 0)` gibi ifadelerde
  parantez eksikliği yüzünden SESSİZCE YANLIŞ SONUÇ üretiliyordu
- **DÜZELTİLDİ (yerelde):** `compiler.py`'ye `_p()` fonksiyonu eklendi
- ⚠️ **BU DÜZELTME HÂLÂ SUNUCUYA DEPLOY EDİLMEDİ** — sunucudaki
  `/opt/superbi/app/services/sbx_compiler.py` hâlâ eski/hatalı versiyon

### 5. Dokümantasyon + GitHub
- `docs/` klasörü oluşturuldu: ARCHITECTURE, SESSION, BACKLOG, CLAUDE, TASKS,
  OKUBENI_FIX, OKUBENI_ENCRYPTION
- Kapsamlı `README.md` yazıldı ve repo köküne eklendi
- Git commit geçmişi:
  - `05bfc84` İlk commit
  - `85775d5` feat: SBX Kademe 1
  - `9fc435d` docs: OKUBENI notları docs/ altına
  - `6e14ac6` docs: kapsamlı README.md
- Repo: https://github.com/SHapeloglu/super_bi (public, main branch)

## Sıradaki adım (öncelik sırasına göre)

1. 🔴 **ACİL: Düzeltilmiş `compiler.py`'yi (parantez bug fix) sunucuya deploy et**
   — şu an sunucudaki SBX, DIVIDE gibi bileşik ifadelerde yanlış sonuç üretebilir
2. DuckDB ingest katmanı tasarımı (hangi tablolar ne zaman yüklenecek, refresh stratejisi)
3. `datasets_relationships` tablosu (DuckDB üzerinde)
4. Frontend SBX editörü

## İnfra Notları
- Sunucu: `/opt/superbi`, systemd service (`superbi.service`) aktif
- venv: lark, sqlglot==25.34.1, duckdb==1.5.5 kurulu (duckdb henüz production'a bağlanmadı)
- VPS: 7.8GB RAM (swap 5.8GB dolu — memory baskısı var), 66GB disk boş
- GitHub repo: SHapeloglu/super_bi — README + docs/ güncel
