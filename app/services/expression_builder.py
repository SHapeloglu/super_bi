"""
expression_builder.py
----------------------
Kullanıcının SQL'e benzer formül metinlerini (örn. "price * qty",
"ROUND(price * 1.18, 2)", "CASE WHEN status='paid' THEN amount ELSE 0 END")
güvenli bir şekilde hedef veritabanı dialect'ine SQL ifadesine çevirir.

Neden SQLGlot: kullanıcının yazdığı formül metni SQL'e çok yakın, SQLGlot
bunu doğrudan parse edip bir AST verir (Lark/ANTLR gibi sıfırdan gramer
yazmaya gerek yok). Ayrıca 4 farklı DB (SQLite/Postgres/MySQL/MSSQL) dialect
farkını (örn. IFNULL vs COALESCE) SQLGlot kendisi çözer.

GÜVENLİK MODELİ — whitelist, blacklist DEĞİL:
  - Formül parse edildikten sonra AST'nin HER düğümü gezilir (walk())
  - Düğüm tipi ALLOWED_NODE_TYPES içinde değilse → reddedilir
  - Bir Column referansı allowed_columns kümesinde değilse → reddedilir
  - exp.Anonymous (SQLGlot'un TANIMADIĞI, adı bilinmeyen herhangi bir
    fonksiyon çağrısı) HER ZAMAN reddedilir — böylece "izin verilen
    fonksiyon adları" listesini string karşılaştırmasıyla değil, SQLGlot'un
    kendi sınıflandırmasıyla (tip whitelist) uygularız; bu daha az kırılgan.
  - Bu sayede Subquery/Select/Table/From gibi düğümler otomatik reddedilir
    (whitelist'te yoklar) — yani "(SELECT password FROM users)" gibi bir
    formül denemesi baştan başarısız olur.
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

# Hedef DB tipini SQLGlot dialect adına çevir (bkz. connector_registry.DRIVER_MAP)
DIALECT_MAP = {
    "sqlite":     "sqlite",
    "postgresql": "postgres",
    "mysql":      "mysql",
    "mssql":      "tsql",
}

MAX_FORMULA_LENGTH = 500

# İzin verilen düğüm tipleri — SADECE bunlara izin verilir, geri kalan HER ŞEY
# (Subquery, Select, Command, Anonymous fonksiyon, vb.) reddedilir.
ALLOWED_NODE_TYPES = (
    # Temel yapı taşları
    exp.Column, exp.Identifier, exp.Literal, exp.Null, exp.Paren, exp.Tuple,
    # Aritmetik
    exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod, exp.Neg,
    # Karşılaştırma / mantıksal
    exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
    exp.And, exp.Or, exp.Not, exp.Is, exp.Between, exp.In,
    # Koşullu ifade
    exp.Case, exp.If,
    # Tip dönüşümü
    exp.Cast, exp.DataType,
    # İzin verilen agregasyon/fonksiyonlar (her biri SQLGlot'ta özel bir sınıf)
    exp.Sum, exp.Avg, exp.Count, exp.Min, exp.Max,
    exp.Round, exp.Abs, exp.Coalesce,
    exp.Upper, exp.Lower, exp.Length, exp.Trim,
)


class ExpressionError(ValueError):
    """Kullanıcıya doğrudan gösterilebilecek, anlaşılır bir hata mesajı taşır."""


def validate_and_compile(formula: str, db_type: str, allowed_columns: set[str]) -> str:
    """
    formula:          kullanıcının yazdığı SQL ifadesi (örn. "price * qty")
    db_type:          "sqlite" | "postgresql" | "mysql" | "mssql"
    allowed_columns:  bu sorguda GERÇEKTEN var olan kolon adları (whitelist)

    Döner: hedef dialect'te derlenmiş, güvenli SQL ifadesi (string).
    Hata:  ExpressionError — formülde sorun varsa (kullanıcıya gösterilebilir).
    """
    if not formula or not formula.strip():
        raise ExpressionError("Formül boş olamaz")
    if len(formula) > MAX_FORMULA_LENGTH:
        raise ExpressionError(f"Formül çok uzun (maksimum {MAX_FORMULA_LENGTH} karakter)")
    if ";" in formula:
        # SQLGlot sürümleri noktalı virgülden sonrasını FARKLI şekillerde ele
        # alıyor (bazıları sessizce atıyor, bazıları "Block" düğümü olarak
        # sarıp whitelist'ten reddediyor). İkisi de fonksiyonel olarak güvenli
        # olsa da, versiyona bağlı örtük davranışa güvenmek yerine burada
        # açıkça ve tutarlı şekilde reddediyoruz — tek bir ifade formülünde
        # noktalı virgülün meşru bir kullanım senaryosu zaten yok.
        raise ExpressionError("Formülde noktalı virgül (;) kullanılamaz")

    dialect = DIALECT_MAP.get(db_type)
    if dialect is None:
        raise ExpressionError(f"Desteklenmeyen veritabanı tipi: {db_type!r}")

    try:
        tree = sqlglot.parse_one(formula, read=dialect)
    except Exception as e:
        raise ExpressionError(f"Formül anlaşılamadı: {e}")

    if tree is None:
        raise ExpressionError("Formül boş bir ifadeye çözüldü")

    _validate_node_tree(tree, allowed_columns)

    try:
        compiled = tree.sql(dialect=dialect)
    except Exception as e:
        raise ExpressionError(f"Formül hedef veritabanına çevrilemedi: {e}")

    if not compiled or not compiled.strip():
        raise ExpressionError("Formül geçerli bir SQL ifadesine dönüşmedi")

    return compiled


def _validate_node_tree(root: exp.Expression, allowed_columns: set[str]) -> None:
    for node in root.walk():
        if not isinstance(node, ALLOWED_NODE_TYPES):
            raise ExpressionError(
                f"İzin verilmeyen ifade: {type(node).__name__} "
                f"({node.sql() if hasattr(node, 'sql') else node!r})"
            )
        if isinstance(node, exp.Column):
            col_name = node.name
            if col_name not in allowed_columns:
                raise ExpressionError(f"Bilinmeyen veya izin verilmeyen kolon: {col_name!r}")
        # SQL yorumları (--  /* */) fonksiyonel olarak zararsızdır (motor
        # tarafından çalıştırılmaz) ama savunma derinliği için tamamen
        # reddediyoruz — formülde yorum olmasının meşru bir kullanım senaryosu
        # yok, ve "gizli" metin taşıma ihtimalini baştan kapatıyoruz.
        if getattr(node, "comments", None):
            raise ExpressionError("Formülde yorum satırı (-- veya /* */) kullanılamaz")
