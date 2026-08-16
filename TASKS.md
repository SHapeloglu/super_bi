# Yapılacaklar

- ~~SQLite frontend desteği~~ → İPTAL (gereksiz, talep gelmedi)
- **Excel/CSV/JSON dosya kaynağı desteği** — yeni connector tipi (upload + parse)
- **İlişkisel veri modeli katmanı** (Power BI / Qlik tarzı) — dataset'ler arası join/ilişki tanımlama ekranı; sorgu builder bu modeli kullanacak
- **Incremental refresh** — dataset'lerin tam yerine artımlı (delta) yenilenmesi
  - **Kademe 1 (SBX ifade dili) — TAMAMLANDI**: lark + sqlglot derleyici, 4 dialect, 17 fonksiyon, expression_builder entegrasyonu, 5/5 test geçti
  - Kademe 2 (measure + filtre context) ve Kademe 3 (VAR/RETURN) sonraki oturumlara ertelendi
