"""
SuperBI Expression Language (SBX) -> SQL Derleyici
Kademe 1: Row-level calculated field (context yok, saf ifade -> SQL).

Kullanım:
    sql_text = compile_sbx("IF([Kar] > 0, 'Pozitif', 'Negatif')", dialect="oracle")

Bağımlılıklar: lark, sqlglot==25.34.1 (proje ile aynı pin)

Değişiklik notu (2026-08-27):
    _p() yardımcı fonksiyonu eklendi. sqlglot elle inşa edilen (parse
    edilmemiş, doğrudan Python'da kurulan) expression ağaçlarında
    operatör önceliğini otomatik korumuyor. Örn. eskiden
    DIVIDE([tutar]-[maliyet], [tutar], 0) ifadesi parantezsiz
    "tutar - maliyet / tutar" olarak render ediliyordu ki bu SQL'de
    "tutar - (maliyet / tutar)" anlamına gelir -- istenen
    "(tutar - maliyet) / tutar" DEĞİL. Sessiz, yanlış sonuç.
    Artık tüm ikili/tekli operatör kurucuları alt ifadeleri _p() ile
    açıkça parantezliyor. Fazladan parantez SQL açısından zararsız;
    eksik parantez ise yanlış sonuç demek -- bu yüzden her yerde
    tutarlı şekilde uygulandı.
"""
from __future__ import annotations

import os
from lark import Lark, Transformer, v_args
import sqlglot
from sqlglot import exp

GRAMMAR_PATH = os.path.join(os.path.dirname(__file__), "grammar.lark")
with open(GRAMMAR_PATH, "r", encoding="utf-8") as f:
    _GRAMMAR = f.read()

_parser = Lark(_GRAMMAR, start="start", parser="lalr")


def _p(expr):
    """Bileşik (binary/unary/mantıksal) alt ifadeleri açıkça parantezle
    sarar, böylece render sırasında operatör önceliği hiçbir zaman
    belirsiz kalmaz. Zaten parantezli bir ifadeyi tekrar sarmaz."""
    if isinstance(expr, exp.Paren):
        return expr
    if isinstance(expr, (exp.Binary, exp.Connector, exp.Unary, exp.Not)):
        return exp.Paren(this=expr)
    return expr


# ---------------------------------------------------------------------------
# Fonksiyon kayıt defteri: SBX fonksiyon adı -> sqlglot exp üretici
# Yeni fonksiyon eklemek = buraya bir satır eklemek.
# ---------------------------------------------------------------------------
def _f_if(args):
    cond, then, else_ = args
    return exp.Case(ifs=[exp.If(this=_p(cond), true=then)], default=else_)


def _f_divide(args):
    # DAX'taki DIVIDE gibi: sıfıra bölmeyi güvenli hale getirir
    num, den = _p(args[0]), _p(args[1])
    fallback = args[2] if len(args) > 2 else exp.Null()
    safe_div = exp.Div(this=num, expression=den)
    zero_check = exp.EQ(this=den, expression=exp.Literal.number(0))
    return exp.Case(ifs=[exp.If(this=zero_check, true=fallback)], default=safe_div)


def _f_round(args):
    return exp.Round(this=args[0], decimals=args[1] if len(args) > 1 else None)


def _f_concat(args):
    return exp.Concat(expressions=args)


def _f_datediff(args):
    # DATEDIFF(birim, baslangic, bitis)
    unit, start, end = args
    unit_str = unit.this if isinstance(unit, exp.Literal) else str(unit)
    return exp.DateDiff(this=end, expression=start, unit=exp.var(unit_str))


def _f_isnull(args):
    return exp.Coalesce(this=args[0], expressions=[args[1]])


def _agg(name):
    def _fn(args):
        cls = {"SUM": exp.Sum, "AVG": exp.Avg, "COUNT": exp.Count,
               "MIN": exp.Min, "MAX": exp.Max}[name]
        return cls(this=args[0] if args else exp.Star())
    return _fn


FUNCTIONS = {
    "IF": _f_if,
    "DIVIDE": _f_divide,
    "ROUND": _f_round,
    "CONCAT": _f_concat,
    "DATEDIFF": _f_datediff,
    "ISNULL": _f_isnull,
    "SUM": _agg("SUM"),
    "AVG": _agg("AVG"),
    "COUNT": _agg("COUNT"),
    "MIN": _agg("MIN"),
    "MAX": _agg("MAX"),
    "UPPER": lambda a: exp.Upper(this=a[0]),
    "LOWER": lambda a: exp.Lower(this=a[0]),
    "ABS": lambda a: exp.Abs(this=a[0]),
    "LEN": lambda a: exp.Length(this=a[0]),
    "TRIM": lambda a: exp.Trim(this=a[0]),
    "COALESCE": lambda a: exp.Coalesce(this=a[0], expressions=a[1:]),
}


class SBXError(Exception):
    """SBX ayrıştırma/derleme hatası - kullanıcıya gösterilecek mesaj."""


@v_args(inline=True)
class SBXTransformer(Transformer):
    """Lark parse ağacını sqlglot expression ağacına çevirir."""

    def number(self, tok):
        return exp.Literal.number(str(tok))

    def string(self, tok):
        return exp.Literal.string(str(tok)[1:-1])

    def true_(self):
        return exp.true()

    def false_(self):
        return exp.false()

    def null_(self):
        return exp.Null()

    def field(self, name_tok):
        col_name = str(name_tok).strip()
        return exp.column(col_name)

    def func_call(self, name_tok, arglist=None):
        fn_name = str(name_tok).upper()
        args = list(arglist) if arglist is not None else []
        if fn_name not in FUNCTIONS:
            raise SBXError(f"Bilinmeyen fonksiyon: {fn_name}")
        try:
            return FUNCTIONS[fn_name](list(args))
        except (IndexError, KeyError) as e:
            raise SBXError(f"{fn_name} fonksiyonu argüman hatası: {e}")

    def arglist(self, *items):
        return items  # func_call bunu .children ile okuyor, bkz. yukarı

    # -- Aritmetik operatörler: alt ifadeler _p() ile parantezlenir --
    def add(self, l, r):
        return exp.Add(this=_p(l), expression=_p(r))

    def sub(self, l, r):
        return exp.Sub(this=_p(l), expression=_p(r))

    def mul(self, l, r):
        return exp.Mul(this=_p(l), expression=_p(r))

    def div(self, l, r):
        return exp.Div(this=_p(l), expression=_p(r))

    def concat(self, l, r):
        return exp.Concat(expressions=[_p(l), _p(r)])

    def neg(self, x):
        return exp.Neg(this=_p(x))

    # -- Karşılaştırma operatörleri --
    def eq(self, l, r):
        return exp.EQ(this=_p(l), expression=_p(r))

    def neq(self, l, r):
        return exp.NEQ(this=_p(l), expression=_p(r))

    def gt(self, l, r):
        return exp.GT(this=_p(l), expression=_p(r))

    def gte(self, l, r):
        return exp.GTE(this=_p(l), expression=_p(r))

    def lt(self, l, r):
        return exp.LT(this=_p(l), expression=_p(r))

    def lte(self, l, r):
        return exp.LTE(this=_p(l), expression=_p(r))

    # -- Mantıksal operatörler --
    def and_(self, l, r):
        return exp.And(this=_p(l), expression=_p(r))

    def or_(self, l, r):
        return exp.Or(this=_p(l), expression=_p(r))

    def not_(self, x):
        return exp.Not(this=_p(x))


def compile_sbx(expression_text: str, dialect: str = "oracle") -> str:
    """
    SBX ifadesini verilen SQL lehçesine derler.
    dialect: sqlglot lehçe adı ("oracle", "tsql", "postgres", "mysql", "sqlite")
    Dönüş: SQL ifade metni (SELECT olmadan, tek bir expression)
    """
    try:
        tree = _parser.parse(expression_text)
    except Exception as e:
        raise SBXError(f"Sözdizimi hatası: {e}")
    sql_exp = SBXTransformer().transform(tree)
    return sql_exp.sql(dialect=dialect)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        "[Satış] - [Maliyet]",
        "IF([Kar] > 0, 'Pozitif', 'Negatif')",
        "DIVIDE([Kar], [Satış], 0)",
        "DIVIDE([tutar] - [maliyet], [tutar], 0)",
        "ROUND([Fiyat] * 1.20, 2)",
        "[Ad] & ' ' & [Soyad]",
        "SUM([Satış])",
        "DATEDIFF('day', [BaslangicTarihi], [BitisTarihi])",
        "ISNULL([Bölge], 'Bilinmiyor')",
    ]
    for t in tests:
        for dialect in ("oracle", "tsql", "postgres", "mysql"):
            try:
                print(f"[{dialect:10}] {t}  ->   {compile_sbx(t, dialect)}")
            except SBXError as e:
                print(f"[{dialect:10}] {t}  ->  HATA:   {e}")
        print()
