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
from lark.exceptions import VisitError
import sqlglot
from sqlglot import exp

# grammar.lark dosyası (SBX dil kuralları) modül yüklenirken bir kez okunur. Dosya yoksa import hata verir.
GRAMMAR_PATH = os.path.join(os.path.dirname(__file__), "grammar.lark")
with open(GRAMMAR_PATH, "r", encoding="utf-8") as f:
    _GRAMMAR = f.read()

# LALR: hızlı tek geçişli ayrıştırıcı. Kurallar bir kez derlenir, her çağrıda yeniden yapılmaz.
_parser = Lark(_GRAMMAR, start="start", parser="lalr")


def _p(expr):
    """Bileşik (binary/unary/mantıksal) alt ifadeleri açıkça parantezle
    sarar, böylece render sırasında operatör önceliği hiçbir zaman
    belirsiz kalmaz. Zaten parantezli bir ifadeyi tekrar sarmaz."""
    if isinstance(expr, exp.Paren):
        return expr
    # Bileşik ifadeler (ikili işlem, mantıksal, tekli) parantezlenir. Sayı, alan adı, metin gibi basit değerler olduğu gibi kalır.
    if isinstance(expr, (exp.Binary, exp.Connector, exp.Unary, exp.Not)):
        return exp.Paren(this=expr)
    return expr


# ---------------------------------------------------------------------------
# Fonksiyon kayıt defteri: SBX fonksiyon adı -> sqlglot exp üretici
# Yeni fonksiyon eklemek = buraya bir satır eklemek.
# ---------------------------------------------------------------------------
def _f_if(args):
    """
    SBX IF(koşul, doğru_değer, yanlış_değer) fonksiyonunu SQL CASE WHEN ifadesine çevirir.
    args: [koşul, doğru değer, yanlış değer]. Koşul _p() ile parantezlenir.
    """
    cond, then, else_ = args
    return exp.Case(ifs=[exp.If(this=_p(cond), true=then)], default=else_)


def _f_divide(args):
    # DAX'taki DIVIDE gibi: sıfıra bölmeyi güvenli hale getirir
    """
    DIVIDE(pay, payda, [yedek]) fonksiyonu: payda 0 ise yedek değeri (yoksa NULL), değilse pay / payda döner.
    Sıfıra bölme hatasını SQL seviyesinde önler. Benzer DAX fonksiyonu ile aynı mantıktadır.
    """
    num, den = _p(args[0]), _p(args[1])
    # DIVIDE'ın 3. argümanı: payda 0 ise dönecek değer. Verilmezse NULL kullanılır.
    fallback = args[2] if len(args) > 2 else exp.Null()
    safe_div = exp.Div(this=num, expression=den)
    # Payda 0 mı diye kontrol eder. Böylece veritabanı 'sıfıra bölme' hatası vermez.
    zero_check = exp.EQ(this=den, expression=exp.Literal.number(0))
    return exp.Case(ifs=[exp.If(this=zero_check, true=fallback)], default=safe_div)


def _f_round(args):
    """ROUND(sayı, [basamak]) -> SQL ROUND. Basamak verilmezse yalnız sayı ile çağrılır."""
    return exp.Round(this=args[0], decimals=args[1] if len(args) > 1 else None)


def _f_concat(args):
    """CONCAT(a, b, ...) -> SQL CONCAT. Verilen tüm argümanları sırayla birleştirir."""
    return exp.Concat(expressions=args)


def _f_datediff(args):
    # DATEDIFF(birim, baslangic, bitis)
    """
    DATEDIFF(birim, başlangıç, bitiş) -> iki tarih arasındaki farkı verir.
    birim 'day', 'month' gibi metin olmalıdır. SQL'de argüman sırası ters yazıldığı için bitiş önce gelir.
    """
    unit, start, end = args
    # Birim ('day' gibi) tırnaklı metin olarak gelir; tırnaksız gelirse str() ile metne çevrilir.
    unit_str = unit.this if isinstance(unit, exp.Literal) else str(unit)
    # DİKKAT: SQL'de DATEDIFF argüman sırası bitiş, başlangıç şeklindedir. SBX'teki sıranın tersi burada yazılır.
    return exp.DateDiff(this=end, expression=start, unit=exp.var(unit_str))


def _f_isnull(args):
    """ISNULL(değer, yedek) -> SQL COALESCE. Değer NULL ise yedek değer döner."""
    return exp.Coalesce(this=args[0], expressions=[args[1]])


def _agg(name):
    """
    SUM, AVG, COUNT, MIN, MAX gibi toplama fonksiyonları için bir üretici döner.
    name: fonksiyon adı (ör. 'SUM'). Dönen fonksiyon argüman listesini alır.
    """
    def _fn(args):
        """Asıl üretici: argüman listesinden ilgili toplama ifadesini (ör. SUM(x)) kurar. Argüman yoksa yıldız (*) kullanır."""
        # name yalnızca bu dosyadaki sabit adlardan (SUM, AVG...) gelir; bu yüzden sözlükte her zaman bulunur.
        cls = {"SUM": exp.Sum, "AVG": exp.Avg, "COUNT": exp.Count,
               "MIN": exp.Min, "MAX": exp.Max}[name]
        # Argüman yoksa yıldız (*) kullanılır: COUNT() -> COUNT(*).
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
        """Sayı belirteçini (ör. 12.5) SQL sayı değerine çevirir."""
        return exp.Literal.number(str(tok))

    def string(self, tok):
        """'metin' biçimindeki belirteçten dıştaki tek tırnakları atar ve SQL metin değeri üretir."""
        # DİKKAT: Baştaki ve sondaki tek tırnak atılır. İçindeki '' (çift tırnak kaçışı) çözülmez, olduğu gibi kalır.
        return exp.Literal.string(str(tok)[1:-1])

    def true_(self):
        """TRUE sözcüğünü SQL doğru (TRUE) değerine çevirir."""
        return exp.true()

    def false_(self):
        """FALSE sözcüğünü SQL yanlış (FALSE) değerine çevirir."""
        return exp.false()

    def null_(self):
        """NULL sözcüğünü SQL NULL ifadesine çevirir."""
        return exp.Null()

    def field(self, name_tok):
        """[Alan Adı] biçimindeki alan referansını SQL kolonuna çevirir. Baş ve sondaki boşlukları siler."""
        col_name = str(name_tok).strip()
        return exp.column(col_name)

    def func_call(self, name_tok, arglist=None):
        """
        SBX fonksiyon çağrısını (ör. ROUND(x, 2)) FUNCTIONS sözlüğündeki karşılığıyla SQL'e çevirir.
        Bilinmeyen fonksiyon adında SBXError fırlatır. Argüman sayısı yanlışsa da SBXError'a çevrilir.
        """
        fn_name = str(name_tok).upper()
        args = list(arglist) if arglist is not None else []
        if fn_name not in FUNCTIONS:
            raise SBXError(f"Bilinmeyen fonksiyon: {fn_name}")
        # Argüman sayısı/tipi yanlışsa (ör. ROUND() hiç argümansız, IF(1,2) unpack hatası) IndexError/KeyError/ValueError/TypeError düşer; aşağıda SBXError'a çevrilir.
        try:
            return FUNCTIONS[fn_name](list(args))
        except (IndexError, KeyError, ValueError, TypeError) as e:
            raise SBXError(f"{fn_name} fonksiyonu argüman hatası: {e}")

    def arglist(self, *items):
        """Virgülle ayrılmış argüman listesini tuple olarak döner. func_call argümanı parametre olarak alır."""
        return items

    # -- Aritmetik operatörler: alt ifadeler _p() ile parantezlenir --
    def add(self, l, r):
        """Toplama (+): iki tarafı _p() ile parantezleyip SQL toplamasına çevirir."""
        return exp.Add(this=_p(l), expression=_p(r))

    def sub(self, l, r):
        """Çıkarma (-): iki tarafı _p() ile parantezleyip SQL çıkarmasına çevirir."""
        return exp.Sub(this=_p(l), expression=_p(r))

    def mul(self, l, r):
        """Çarpma (*): iki tarafı _p() ile parantezleyip SQL çarpmasına çevirir."""
        return exp.Mul(this=_p(l), expression=_p(r))

    def div(self, l, r):
        """Bölme (/): iki tarafı _p() ile parantezleyip SQL bölmesine çevirir. Sıfıra bölme için DIVIDE fonksiyonu kullanılır."""
        return exp.Div(this=_p(l), expression=_p(r))

    def concat(self, l, r):
        """Metin birleştirme (&): iki tarafı SQL CONCAT ile birleştirir."""
        return exp.Concat(expressions=[_p(l), _p(r)])

    def neg(self, x):
        """Tekli eksi (-x): değeri _p() ile parantezleyip SQL negatifine çevirir."""
        return exp.Neg(this=_p(x))

    # -- Karşılaştırma operatörleri --
    def eq(self, l, r):
        """Eşitlik (=) karşılaştırması."""
        return exp.EQ(this=_p(l), expression=_p(r))

    def neq(self, l, r):
        """Eşit değil (<>) karşılaştırması."""
        return exp.NEQ(this=_p(l), expression=_p(r))

    def gt(self, l, r):
        """Büyük (>) karşılaştırması."""
        return exp.GT(this=_p(l), expression=_p(r))

    def gte(self, l, r):
        """Büyük eşit (>=) karşılaştırması."""
        return exp.GTE(this=_p(l), expression=_p(r))

    def lt(self, l, r):
        """Küçük (<) karşılaştırması."""
        return exp.LT(this=_p(l), expression=_p(r))

    def lte(self, l, r):
        """Küçük eşit (<=) karşılaştırması."""
        return exp.LTE(this=_p(l), expression=_p(r))

    # -- Mantıksal operatörler --
    def and_(self, l, r):
        """Mantıksal VE (AND) işlemi. İki tarafı parantezler."""
        return exp.And(this=_p(l), expression=_p(r))

    def or_(self, l, r):
        """Mantıksal VEYA (OR) işlemi. İki tarafı parantezler."""
        return exp.Or(this=_p(l), expression=_p(r))

    def not_(self, x):
        """Mantıksal DEĞİL (NOT) işlemi. Argümanı parantezler."""
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
    try:
        sql_exp = SBXTransformer().transform(tree)
    except VisitError as e:
        # Lark, transformer içindeki hatayı VisitError ile sarar. Asıl hata SBXError ise onu olduğu gibi ilet.
        orig = e.orig_exc
        if isinstance(orig, SBXError):
            raise orig
        raise SBXError(f"İfade derlenemedi: {orig}")
    if dialect == "oracle":
        sql_exp = _oracle_datediff(sql_exp)
    return sql_exp.sql(dialect=dialect)


def _oracle_datediff(tree):
    """
    Oracle'da DATEDIFF fonksiyonu yoktur. Oracle için DATEDIFF düğümlerini
    eşdeğer Oracle ifadelerine çevirir: gün -> TRUNC farkı, ay -> MONTHS_BETWEEN,
    yıl -> ay farkının 12'ye bölümü (kesirsiz). Diğer birimler SBXError verir.
    """
    def _repl(node):
        if not isinstance(node, exp.DateDiff):
            return node
        unit_node = node.args.get("unit")
        unit = unit_node.name.lower() if unit_node is not None else ""
        end, start = node.this.copy(), node.expression.copy()
        if unit == "day":
            res = exp.Sub(
                this=exp.Anonymous(this="TRUNC", expressions=[end]),
                expression=exp.Anonymous(this="TRUNC", expressions=[start]),
            )
        elif unit == "month":
            res = exp.Anonymous(this="MONTHS_BETWEEN", expressions=[end, start])
        elif unit == "year":
            months = exp.Anonymous(this="MONTHS_BETWEEN", expressions=[end, start])
            res = exp.Anonymous(this="TRUNC", expressions=[exp.Div(this=_p(months), expression=exp.Literal.number(12))])
        else:
            raise SBXError(f"DATEDIFF Oracle için desteklenmeyen birim: {unit}")
        return exp.Paren(this=res)

    return tree.transform(_repl)


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
