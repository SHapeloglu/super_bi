"""
expression_builder.py (v2 — SBX + SQL compat mode)
----------------------
Kullanıcının SQL'e benzer VEYA SBX (SuperBI Expression Language) formül
metinlerini güvenli bir şekilde hedef DB dialect'ine SQL'e çevirir.

Syntax desteği:
  - SQL: "price * qty", "ROUND(price * 1.18, 2)"
  - SBX:  "[Fiyat] * [Miktar]", "ROUND([Fiyat] * 1.20, 2)", "IF([Kar]>0, 'Pozitif', 'Negatif')"

GÜVENLİK MODELİ — whitelist tabanlı:
  - SBX: lark + sqlglot AST derlemesi, whitelist'd fonksiyonlar
  - SQL: sqlglot parse → AST walk, ALLOWED_NODE_TYPES whitelist
  - Her ikisinde de allowed_columns kontrolü zorunlu
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

try:
    from app.services.sbx_compiler import compile_sbx, SBXError
except ImportError:
    compile_sbx = None
    SBXError = Exception

DIALECT_MAP = {
    "sqlite":     "sqlite",
    "postgresql": "postgres",
    "mysql":      "mysql",
    "mssql":      "tsql",
    "oracle":     "oracle",
}

MAX_FORMULA_LENGTH = 500

ALLOWED_NODE_TYPES = (
    exp.Column, exp.Identifier, exp.Literal, exp.Null, exp.Paren, exp.Tuple,
    exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod, exp.Neg,
    exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
    exp.And, exp.Or, exp.Not, exp.Is, exp.Between, exp.In,
    exp.Case, exp.If,
    exp.Cast, exp.DataType,
    exp.Sum, exp.Avg, exp.Count, exp.Min, exp.Max,
    exp.Round, exp.Abs, exp.Coalesce, exp.Concat,
    exp.Upper, exp.Lower, exp.Length, exp.Trim,
)


class ExpressionError(ValueError):
    """Kullanıcıya doğrudan gösterilebilecek, anlaşılır bir hata mesajı."""


def validate_and_compile(formula: str, db_type: str, allowed_columns: set[str]) -> str:
    """
    formula:          SBX VEYA SQL ifadesi
    db_type:          "sqlite" | "postgresql" | "mysql" | "mssql"
    allowed_columns:  bu sorguda var olan kolon adları (whitelist)

    Döner: hedef dialect'te derlenmiş, güvenli SQL ifadesi.
    """
    if not formula or not formula.strip():
        raise ExpressionError("Formül boş olamaz")
    if len(formula) > MAX_FORMULA_LENGTH:
        raise ExpressionError(f"Formül çok uzun (maksimum {MAX_FORMULA_LENGTH} karakter)")
    if ";" in formula:
        raise ExpressionError("Formülde noktalı virgül (;) kullanılamaz")

    dialect = DIALECT_MAP.get(db_type)
    if dialect is None:
        raise ExpressionError(f"Desteklenmeyen veritabanı tipi: {db_type!r}")

    # ADIM 1: SBX olarak dene (eğer [ varsa, SBX olabilir)
    if "[" in formula and compile_sbx is not None:
        try:
            compiled_sql = compile_sbx(formula, dialect=dialect)
            # SBX sonucu SQL olarak doğrula (güvenlik)
            tree = sqlglot.parse_one(compiled_sql, read=dialect)
            if tree:
                _validate_node_tree(tree, allowed_columns)
                return compiled_sql
        except (SBXError, ExpressionError, Exception):
            # SBX başarısız oldu, SQL olarak devam et
            pass

    # ADIM 2: SQL olarak dene (fallback veya direkt SQL)
    try:
        tree = sqlglot.parse_one(formula, read=dialect)
    except Exception as e:
        raise ExpressionError(f"Formül anlaşılamadı (SBX veya SQL): {e}")

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
        if getattr(node, "comments", None):
            raise ExpressionError("Formülde yorum satırı (-- veya /* */) kullanılamaz")
