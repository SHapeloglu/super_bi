"""
schemas.py — Pydantic modelleri
--------------------------------
YENİDEN OLUŞTURULDU: Bu dosya orijinal projede vardı ama diskten silindi.
query.py, sql_builder.py, connections.py içindeki import'lara ve kullanım
şekillerine bakılarak yeniden yazıldı. Alan adları/davranışlar bu dosyaları
kullanan koddan çıkarıldı; orijinaliyle birebir aynı olmayabilir.

Not: FilterDef/JoinDef validator'ları burada SQL injection'a karşı ilk
savunma hattı — sql_builder.py bunlara "zaten whitelist'ten geçti" diye
güveniyor, dolayısıyla bu validator'lar kritik.
"""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

# ---------------------------------------------------------------------------
# Operatör whitelist — sql_builder.py DES-4 kontrolünde de kullanılıyor
# ---------------------------------------------------------------------------

# Kullanıcının filtrelerde kullanabileceği SQL operatörleri (izin listesi). Listede olmayan her şey reddedilir.
ALLOWED_OPERATORS: set[str] = {
    "=", "!=", "<>", ">", "<", ">=", "<=",
    "LIKE", "NOT LIKE", "ILIKE",
    "IN", "NOT IN",
    "IS NULL", "IS NOT NULL",
    "BETWEEN",
}

# JOIN tipi de sql_builder.py'de quote_identifier'dan GEÇMEDEN doğrudan
# SQL'e ekleniyor (f"{j.type} {t2} ON ...") — bu yüzden whitelist burada,
# şema seviyesinde zorunlu.
ALLOWED_JOIN_TYPES: set[str] = {
    "JOIN", "INNER JOIN", "LEFT JOIN", "LEFT OUTER JOIN",
    "RIGHT JOIN", "RIGHT OUTER JOIN", "FULL JOIN", "FULL OUTER JOIN",
}

# TODO(kontrol): Bu regex dosyada kullanılmıyor görünüyor. Silinmedi; kullanım yoksa kaldırılabilir.
_IDENTIFIER_RE = r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$"


# ---------------------------------------------------------------------------
# Filtre / Join tanımları
# ---------------------------------------------------------------------------

class FilterDef(BaseModel):
    """
    Tek bir filtre koşulu: tablo.kolon operatör değer.
    Operatör ALLOWED_OPERATORS listesinde değilse istek reddedilir (SQL enjeksiyonuna karşı ilk savunma).
    """
    table:    str
    column:   str
    operator: str
    value:    Any = None
    value2:   Any = None   # sadece BETWEEN için kullanılır

    @field_validator("operator")
    @classmethod
    def _operator_whitelist(cls, v: str) -> str:
        """operator alanını büyük harfe çevirip izin listesinde mi diye bakar. Değilse ValueError fırlatır (Pydantic bunu 422 hatasına çevirir)."""
        v = v.strip().upper()
        if v not in ALLOWED_OPERATORS:
            raise ValueError(f"İzin verilmeyen operatör: {v!r}")
        return v

    # Model tüm alanlar atandıktan sonra çalışır; birden çok alanı birlikte kontrol etmek için kullanılır.
    @model_validator(mode="after")
    def _value_shape(self) -> "FilterDef":
        """Alanlar birlikte kontrol edilir: BETWEEN için value2 zorunlu; IN / NOT IN için boş olmayan ve NULL içermeyen liste gerekir."""
        if self.operator == "BETWEEN" and self.value2 is None:
            raise ValueError("BETWEEN operatörü için value2 zorunlu")
        if self.operator in ("IN", "NOT IN"):
            vals = self.value if isinstance(self.value, list) else [self.value]
            # IN listesi boş olamaz ve içinde NULL olamaz; NULL içeren IN karşılaştırması SQL'de beklenmeyen sonuç verir.
            if not vals or any(v is None for v in vals):
                raise ValueError("IN/NOT IN için en az 1 geçerli değer gerekli")
        return self


class JoinDef(BaseModel):
    """Bir JOIN tanımı: t1.f1 = t2.f2 şeklinde iki tablo arasındaki bağlantı. type JOIN türüdür (ör. LEFT JOIN)."""
    type: str
    t1:   str
    f1:   str
    t2:   str
    f2:   str

    @field_validator("type")
    @classmethod
    def _join_type_whitelist(cls, v: str) -> str:
        """JOIN tipini büyük harfe çevirip ALLOWED_JOIN_TYPES listesinde mi diye bakar. Değilse ValueError fırlatır."""
        v = v.strip().upper()
        if v not in ALLOWED_JOIN_TYPES:
            raise ValueError(f"İzin verilmeyen join tipi: {v!r}")
        return v


_ALIAS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CalculatedFieldDef(BaseModel):
    """
    Kullanıcının SQL'e benzer formülle tanımladığı hesaplanmış kolon
    (örn. name="kdv_dahil", formula="ROUND(price * 1.18, 2)").

    Formülün kendisi burada whitelist EDİLMEZ — asıl güvenlik kontrolü
    app.services.expression_builder.validate_and_compile() içinde, formül
    SQLGlot AST'sine çevrilip her düğüm tek tek denetlenerek yapılır. Burada
    sadece şeklen çok uzun/boş girdileri erkenden eleriz.
    """
    name:    str = Field(min_length=1, max_length=64)
    formula: str = Field(min_length=1, max_length=500)

    @field_validator("name")
    @classmethod
    def _name_whitelist(cls, v: str) -> str:
        """Hesaplanmış alan adını kontrol eder: harf, rakam ve alt çizgi olabilir, rakamla başlayamaz. Değilse ValueError fırlatır."""
        if not _ALIAS_RE.match(v):
            raise ValueError(
                f"Hesaplanmış alan adı geçersiz: {v!r} — sadece harf/rakam/alt "
                "çizgi kullanın, rakamla başlayamaz"
            )
        return v


# ---------------------------------------------------------------------------
# Sorgu istekleri
# ---------------------------------------------------------------------------

class _QueryShapeBase(BaseModel):
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
        """formula_only_columns listesindeki her kolon adının geçerli bir SQL tanımlayıcısı olup olmadığına bakar. Geçersizse ValueError fırlatır."""
        for col in v:
            # DİKKAT: Python'da $ işareti sondaki yeni satırı da kabul eder ('abc\n' geçer). Tam eşleşme için fullmatch daha sıkı olurdu.
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", col):
                raise ValueError(f"Geçersiz kolon adı: {col!r}")
        return v


class QueryRequest(_QueryShapeBase):
    """/api/query/stream için — klasik limit/offset sayfalama."""
    # Bir istekte en fazla 100 bin satır; sunucu belleğini korumak için üst sınır. 1000 varsayılan sayfa boyutudur.
    limit:  int = Field(default=1000, ge=1, le=100_000)
    offset: int = Field(default=0, ge=0)


class QueryRunRequest(_QueryShapeBase):
    """
    /api/query/run için — "önce gör, sonra al" prensibi.
    sample: önizleme için kaç satır çekilecek (10/100/1000 gibi presetler beklenir)
    commit: True ise sonucu kalıcı cache'e (5dk) yazar, False ise geçici (30sn)
    mode:   'live' her seferinde DB'ye gider, 'memory' cache'i tekrar kullanır
    """
    sample: int = Field(default=100, ge=1, le=100_000)
    commit: bool = False
    mode:   Literal["live", "memory"] = "memory"


class QueryResult(BaseModel):
    """execute()'un mantıksal şekli — dökümantasyon amaçlı, endpoint response_model olarak zorunlu değil."""
    columns:   list[str]
    rows:      list[list[Any]]
    row_count: int
    exec_ms:   float
    cache_key: str
    mode:      str
    conn_id:   str
    committed: bool = False


class SQLPreviewRequest(_QueryShapeBase):
    """Sorgu önizleme (SQL metni üretme) isteği. Veri çekmez; sadece oluşacak SQL'i gösterir. limit önizleme için en fazla kaç satır olacağını belirler."""
    limit: int = Field(default=100, ge=1, le=100_000)
    db_type: str | None = None  # sadece önizleme SQL metnini doğru dialect'te göstermek için (auth/veri erişimi yok)


class SQLPreviewResponse(BaseModel):
    """Önizleme cevabı: üretilen SQL metni ve tahmini karmaşıklık (low / medium / high)."""
    sql: str
    estimated_complexity: Literal["low", "medium", "high"]


class CacheCommitRequest(BaseModel):
    """Önbellekteki (cache) bir sonucu kalıcı yapmak için gönderilen istek. cache_key, önceki sorgu cevabında dönen anahtardır."""
    cache_key: str


class CacheCommitResponse(BaseModel):
    """Cache kalıcı yapma işleminin cevabı: başarılı mı, hangi anahtar, kullanıcıya gösterilecek mesaj."""
    success:   bool
    cache_key: str
    message:   str


# ---------------------------------------------------------------------------
# Bağlantı (connection) şemaları
# ---------------------------------------------------------------------------

class ConnectionParams(BaseModel):
    """
    Veritabanı bağlantı bilgileri. Şifre SecretStr tipindedir; loglara ve yanıtlara düz metin olarak yazılmaz.
    Sadece engine oluşturulurken get_password() ile düz metin alınır.
    """
    db_type:     str
    host:        str = ""
    port:        Optional[int] = None
    database:    str
    user:        Optional[str] = None
    # SecretStr: şifre yazdırıldığında *** görünür; gerçek değer yalnız get_password() ile alınır.
    password:    Optional[SecretStr] = None
    schema_name: Optional[str] = None

    def get_password(self) -> Optional[str]:
        """Şifreyi düz metin olarak SADECE engine oluşturulurken kullanmak için döner."""
        return self.password.get_secret_value() if self.password else None


class ConnectionResponse(BaseModel):
    """Bağlantı oluşturma/listeleme sonrası dönen özet bilgi. Şifre ve kullanıcı bilgisi içermez."""
    conn_id:  str
    db_type:  str
    host:     str
    database: str
    status:   str
    message:  str


class ConnectionTest(BaseModel):
    """Bağlantı testinin sonucu: başarılı mı, mesaj ve gecikme süresi (milisaniye)."""
    success:    bool
    message:    str
    latency_ms: float


# ---------------------------------------------------------------------------
# Auth şemaları
# ---------------------------------------------------------------------------

class UserRegister(BaseModel):
    """Yeni kullanıcı kaydı isteği. Kullanıcı adı 3-64, şifre 8-256 karakter olmalıdır."""
    # Kullanıcı adı 3-64, şifre 8-256 karakter arasında olmalı (kayıt sırasında kontrol edilir).
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)


class UserLogin(BaseModel):
    """Giriş isteği: kullanıcı adı ve şifre. Boyut kontrolü yoktur; doğrulama giriş servisinde yapılır."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Giriş başarılı olunca dönen token cevabı: erişim anahtarı (access_token), rol ve kullanıcı kimliği."""
    access_token: str
    # Standart token tipi. İstemci isteklerinde 'Authorization: Bearer <token>' başlığını kullanır.
    token_type:   str = "bearer"
    role:         str
    user_id:      str
