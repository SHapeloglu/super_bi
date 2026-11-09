#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch: app/services/sql_builder.py — formula_only_columns destegi

NEDEN: NLQ (ve genel olarak agregasyon iceren herhangi bir sorgu), bir
kolonu SADECE SUM()/AVG() gibi bir formul icinde kullanmak isteyebilir,
onu ham bir SELECT kolonu olarak GORUNTULEMEK istemeden. Mevcut kodda
_calculated_columns()'un allowed_columns'i SADECE fields'daki (role != "off")
kolonlardan geliyordu — bu da o kolonu otomatik olarak _select_columns()
tarafindan ham SELECT kolonu yapiyordu, GROUP BY'a sokulmadigi icin
PostgreSQL/MSSQL/Oracle'da "column must appear in GROUP BY" hatasi
uretiyordu. Ayrica base_table'a otomatik nitelendigi icin, kolon baska
bir JOIN edilmis tabloya aitse YANLIS tabloya nitelenmis oluyordu.

CALISTIRMA:
  cd /opt/superbi
  source venv/bin/activate
  python3 patch_sql_builder_formula_only_columns.py
  systemctl restart superbi
  systemctl status superbi

GERI ALMA: .bak yedeginden geri kopyalayin:
  cp app/services/sql_builder.py.bak app/services/sql_builder.py
  systemctl restart superbi
"""
import hashlib
import shutil
import sys
from pathlib import Path

TARGET = Path("app/services/sql_builder.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    """
    Metinde 'old' metnini tam 1 kez arar ve 'new' ile değiştirir. Eşleşme sayısı 1 değilse ekrana hata yazıp betiği durdurur.
    Bu sayede yanlış yere ya da iki kez yama yapılması engellenir. label: hata mesajında gösterilen ad.
    """
    count = text.count(old)
    if count != 1:
        print(f"HATA: {label!r} beklenen metin dosyada {count} kere bulundu "
              f"(1 bekleniyordu). Hicbir dosyaya dokunulmadi.")
        sys.exit(1)
    return text.replace(old, new)


def md5(path: Path) -> str:
    """Dosyanın MD5 özetini (parmak izi) hesaplar. Dosyanın değişip değişmediğini kontrol etmek için kullanılır."""
    return hashlib.md5(path.read_bytes()).hexdigest()


def main():
    """
    Yama betiğinin ana akışı: hedef dosyayı okur, değişiklikleri sırayla uygular ve sonucu yazar.
    Betik tek seferlik yazılmıştır; çalıştırmadan önce hedef dosyanın zaten yamalanıp yamalanmadığına bakın.
    """
    if not TARGET.exists():
        print(f"HATA: {TARGET} bulunamadi. Bu scripti /opt/superbi icinde calistirin.")
        sys.exit(1)

    original = TARGET.read_text(encoding="utf-8")
    before_md5 = hashlib.md5(original.encode("utf-8")).hexdigest()
    print(f"Mevcut dosya MD5: {before_md5}")

    text = original

    old1 = '''    def _calculated_columns(
        self,
        fields: dict[str, str],
        calculated_fields: list[CalculatedFieldDef],
        db_type: str,
    ) -> list[str]:
        """
        Her hesaplanmış alan için formülü doğrulayıp (whitelist) hedef
        dialect'e derler, sonra "AS alias" ekleyerek SELECT listesine
        eklenecek parçayı üretir.

        allowed_columns SADECE seçili (role != "off") fields'daki bare kolon
        adlarıdır — yani kullanıcı önce query builder'da bir kolonu "dahil"
        etmeden, o kolonu bir formülde kullanamaz. Bu bilinçli bir kısıtlama:
        SQLBuilder'ın tam şema bilgisi yok, sadece frontend'den gelen
        fields dict'ini biliyor; formülleri buna göre sınırlamak, şema
        dışı/rastgele kolon adı denemelerini baştan eler.
        """
        if not calculated_fields:
            return []

        allowed_columns = {
            (key.split(".")[-1]) for key, role in fields.items() if role != "off"
        }

        parts = []'''

    new1 = '''    def _calculated_columns(
        self,
        fields: dict[str, str],
        calculated_fields: list[CalculatedFieldDef],
        db_type: str,
        formula_only_columns: list[str] | None = None,
    ) -> list[str]:
        """
        Her hesaplanmış alan için formülü doğrulayıp (whitelist) hedef
        dialect'e derler, sonra "AS alias" ekleyerek SELECT listesine
        eklenecek parçayı üretir.

        allowed_columns iki kaynaktan gelir:
          1) Seçili (role != "off") fields'daki bare kolon adları — yani
             kullanıcı önce query builder'da bir kolonu "dahil" etmeden,
             o kolonu bir formülde kullanamaz (mevcut davranış, değişmedi).
          2) formula_only_columns — SADECE agregasyon/formül içinde
             kullanılacak, ham SELECT kolonu olarak EKLENMEYECEK kolonlar.
             Örn. "5 en çok satan ürün" sorgusunda LineTotal, SUM() içinde
             gerekli ama tek başına bir SELECT kolonu olarak (GROUP BY'a
             sokulmadığı için) sorguyu bozar — formula_only_columns bu
             kolonu whitelist'e ekler ama _select_columns hiç görmez.
        """
        if not calculated_fields:
            return []

        allowed_columns = {
            (key.split(".")[-1]) for key, role in fields.items() if role != "off"
        }
        if formula_only_columns:
            allowed_columns |= set(formula_only_columns)

        parts = []'''

    text = replace_once(text, old1, new1, "degisiklik 1 (_calculated_columns)")

    old2 = '''        calculated_fields: list[CalculatedFieldDef] | None = None,
        db_type:    str = "sqlite",
        schema:     str | None = None,
    ) -> tuple[str, dict[str, Any]]:

        if db_type == "oracle":
            base_table = base_table.upper()
            fields = {k.upper(): v for k, v in fields.items()}
            if schema:
                schema = schema.upper()
        select_cols = self._select_columns(base_table, fields)
        select_cols += self._calculated_columns(fields, calculated_fields or [], db_type)'''

    new2 = '''        calculated_fields: list[CalculatedFieldDef] | None = None,
        db_type:    str = "sqlite",
        schema:     str | None = None,
        formula_only_columns: list[str] | None = None,
    ) -> tuple[str, dict[str, Any]]:

        if db_type == "oracle":
            base_table = base_table.upper()
            fields = {k.upper(): v for k, v in fields.items()}
            if schema:
                schema = schema.upper()
        select_cols = self._select_columns(base_table, fields)
        select_cols += self._calculated_columns(
            fields, calculated_fields or [], db_type, formula_only_columns
        )'''

    text = replace_once(text, old2, new2, "degisiklik 2 (build imzasi)")

    backup_path = TARGET.with_suffix(TARGET.suffix + ".bak")
    shutil.copy2(TARGET, backup_path)
    print(f"Yedek alindi: {backup_path}")

    TARGET.write_text(text, encoding="utf-8")
    after_md5 = md5(TARGET)
    print(f"Yeni dosya MD5: {after_md5}")

    import ast
    try:
        ast.parse(text)
        print("Syntax OK (ast.parse basarili)")
    except SyntaxError as e:
        print(f"SYNTAX HATASI: {e}")
        print("Yedekten geri yukleniyor...")
        shutil.copy2(backup_path, TARGET)
        sys.exit(1)

    print("\nBASARILI. Simdi calistirin:")
    print("  systemctl restart superbi")
    print("  systemctl status superbi")


if __name__ == "__main__":
    main()
