#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
"Analiz Et" butonuna şema adı sorma özelliği ekler. Çok şemalı veritabanlarında
(MSSQL AdventureWorks: Sales/Production/Person/HumanResources/Purchasing gibi)
schema_name gönderilmezse sadece varsayılan (dbo) şema taranıyordu.

Kullanım: /opt/superbi/venv/bin/python3 apply_analyze_schema_prompt.py
Çalıştırılacağı dizin: /opt/superbi
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPJS = ROOT / "frontend" / "app.js"


def replace_once(text, old, new, label):
    """
    Metinde 'old' metnini tam 1 kez arar ve 'new' ile değiştirir. Eşleşme sayısı 1 değilse ekrana hata yazıp betiği durdurur.
    Bu sayede yanlış yere ya da iki kez yama yapılması engellenir. label: hata mesajında gösterilen ad.
    """
    count = text.count(old)
    if count != 1:
        print(f"[HATA] '{label}' — beklenen 1 eşleşme, bulunan: {count}")
        print("---- ARANAN METİN (ilk 200 karakter) ----")
        print(old[:200])
        sys.exit(1)
    return text.replace(old, new, 1)


def main():
    """
    Yama betiğinin ana akışı: hedef dosyayı okur, değişiklikleri sırayla uygular ve sonucu yazar.
    Betik tek seferlik yazılmıştır; çalıştırmadan önce hedef dosyanın zaten yamalanıp yamalanmadığına bakın.
    """
    if not APPJS.exists():
        print(f"[HATA] Bulunamadı: {APPJS}")
        sys.exit(1)

    appjs = APPJS.read_text(encoding="utf-8")

    OLD = '''    analyzeBtn.addEventListener("click", () =>
      withBusy(analyzeBtn, async () => {
        try {
          const res = await api.analyzeTables(c.conn_id, {});
          toast(
            `Analiz tamam: ${res.tables_profiled}/${res.tables_found} tablo, ${res.fk_relationships} FK ilişkisi bulundu`,
            "success"
          );
          if (res.errors && res.errors.length) {
            console.warn("Analiz hataları:", res.errors);
            toast(`${res.errors.length} tabloda hata oluştu — konsolu kontrol edin`, "error");
          }
          await showAnalysisResults(c.conn_id);
        } catch (e) { handleApiError(e, "Analiz başarısız"); }
      })
    );'''
    NEW = '''    analyzeBtn.addEventListener("click", () =>
      withBusy(analyzeBtn, async () => {
        const schemaName = prompt(
          "Şema adı (opsiyonel). Boş bırakırsanız veritabanının varsayılan şeması taranır.\\n" +
          "Çok şemalı veritabanlarında (örn. MSSQL: Sales, Production, Person, HumanResources, " +
          "Purchasing) her şemayı ayrı ayrı analiz etmeniz gerekir.",
          ""
        );
        if (schemaName === null) return; // iptal edildi
        try {
          const res = await api.analyzeTables(c.conn_id, { schema_name: schemaName || null });
          toast(
            `Analiz tamam${schemaName ? ` (${schemaName})` : ""}: ${res.tables_profiled}/${res.tables_found} tablo, ${res.fk_relationships} FK ilişkisi bulundu`,
            "success"
          );
          if (res.errors && res.errors.length) {
            console.warn("Analiz hataları:", res.errors);
            toast(`${res.errors.length} tabloda hata oluştu — konsolu kontrol edin`, "error");
          }
          await showAnalysisResults(c.conn_id);
        } catch (e) { handleApiError(e, "Analiz başarısız"); }
      })
    );'''
    appjs = replace_once(appjs, OLD, NEW, "analyzeBtn şema promptu")

    shutil.copy2(APPJS, str(APPJS) + ".bak3")
    APPJS.write_text(appjs, encoding="utf-8")

    print("[OK] app.js güncellendi. Yedek: app.js.bak3")
    print("Sonra: systemctl restart superbi, tarayıcıda hard-refresh.")


if __name__ == "__main__":
    main()
