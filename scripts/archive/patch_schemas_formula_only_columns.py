#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch: app/models/schemas.py — formula_only_columns alani (_QueryShapeBase)

sql_builder.py'deki formula_only_columns destegiyle birlikte deploy
edilmelidir (patch_sql_builder_formula_only_columns.py). Bu alan
QueryRequest/QueryRunRequest/SQLPreviewRequest'e (_QueryShapeBase'den
inherit ettikleri icin) otomatik olarak eklenir.

CALISTIRMA:
  cd /opt/superbi
  source venv/bin/activate
  python3 patch_schemas_formula_only_columns.py
  systemctl restart superbi

GERI ALMA:
  cp app/models/schemas.py.bak app/models/schemas.py
  systemctl restart superbi
"""
import hashlib
import shutil
import sys
from pathlib import Path

TARGET = Path("app/models/schemas.py")


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

    old = '''class _QueryShapeBase(BaseModel):
    """QueryRequest ve QueryRunRequest'in ortak SELECT/JOIN/WHERE gövdesi."""
    conn_id:    str
    base_table: str
    schema_name: str | None = None  # çok şemalı DB'lerde (MSSQL/Postgres) hedef şema
    fields:     dict[str, str]        = Field(default_factory=dict)  # {kolon: rol} rol="off" hariç seçilir
    joins:      list[JoinDef]         = Field(default_factory=list)
    filters:    list[FilterDef]       = Field(default_factory=list)
    group_by:   list[str]             = Field(default_factory=list)
    order_by:   list[str]             = Field(default_factory=list)
    calculated_fields: list[CalculatedFieldDef] = Field(default_factory=list)'''

    new = '''class _QueryShapeBase(BaseModel):
    """QueryRequest ve QueryRunRequest'in ortak SELECT/JOIN/WHERE gövdesi."""
    conn_id:    str
    base_table: str
    schema_name: str | None = None  # çok şemalı DB'lerde (MSSQL/Postgres) hedef şema
    fields:     dict[str, str]        = Field(default_factory=dict)  # {kolon: rol} rol="off" hariç seçilir
    joins:      list[JoinDef]         = Field(default_factory=list)
    filters:    list[FilterDef]       = Field(default_factory=list)
    group_by:   list[str]             = Field(default_factory=list)
    order_by:   list[str]             = Field(default_factory=list)
    calculated_fields: list[CalculatedFieldDef] = Field(default_factory=list)
    formula_only_columns: list[str]   = Field(default_factory=list)
    # formula_only_columns: SADECE calculated_fields formüllerinde (örn.
    # SUM(...) içinde) kullanılabilecek, ham SELECT kolonu olarak EKLENMEYECEK
    # kolon adları. NLQ katmanı ve agregasyon içeren sorgular için gerekli —
    # aksi halde agregasyona giren bir kolonu formülde kullanabilmek icin onu
    # fields'a "off" olmayan bir rolle eklemek gerekir, bu da onu GROUP BY'a
    # sokulmamış ham bir SELECT kolonu yapar ve sorguyu bozar.

    @field_validator("formula_only_columns")
    @classmethod
    def _formula_only_columns_whitelist(cls, v: list[str]) -> list[str]:
        for col in v:
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", col):
                raise ValueError(f"Geçersiz kolon adı: {col!r}")
        return v'''

    text = replace_once(original, old, new, "_QueryShapeBase formula_only_columns")

    backup_path = TARGET.with_suffix(TARGET.suffix + ".bak")
    shutil.copy2(TARGET, backup_path)
    print(f"Yedek alindi: {backup_path}")

    TARGET.write_text(text, encoding="utf-8")
    after_md5 = hashlib.md5(text.encode("utf-8")).hexdigest()
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

    print("\nBASARILI. sql_builder.py patch'ini de uyguladiktan sonra:")
    print("  systemctl restart superbi")
    print("  systemctl status superbi")


if __name__ == "__main__":
    main()
