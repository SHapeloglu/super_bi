# Tasarım notu: Viewer için bağlantı paylaşımı

Durum: **ilk dilim uygulandı (dal `feat/viewer-connection-share`).** Karar: seçenek B'nin sınırlı hali; varsayılanlar kabul edildi (yalnız admin'in seçtiği tablolar, kullanım log'u yok, şema listesi gizli). Test: `tests/access/test_connection_share.py` (24 kontrol). İlgili backlog maddesi: "Viewer kendi veri seti için bağlantı" (`backlog.md`).

## Sorun

Viewer bağlantı oluşturamadığı için (yalnız admin, bkz. `app/api/connections.py`) kendi veri setini kaydedemez. Viewer yalnızca başkasının paylaştığı veri setlerini çalıştırabiliyor. Kullanıcı bunu "veri setini kaydet" akışında hata olarak görüyor.

## Mevcut durum (kod referansları)

- Bağlantılar sahibine aittir; `list_connections` yalnız `owner_id` eşleşenleri döner (`app/api/connections.py`).
- Veri seti çalıştırma, veri setinin `conn_id` bağlantısının **sahibinin** kimliğiyle yapılır (`app/api/datasets.py`: `owner = SimpleNamespace(user_id=ds.owner_id, role="viewer")`, sonra `resolve_connection_engine`). Yani bağlantı kimlik bilgisi sorguyu çalıştıran kişiye değil, veri setinin sahibine ait.
- Paylaşım tablosu (`shares`) yalnız veri seti ve dashboard için var; bağlantıya uygulanmıyor.

## Seçenekler

**A. Admin'in paylaştığı bağlantıyla kayıt (yalnız okuma).**
Admin bir bağlantıyı viewer'a `read` yetkisiyle paylaşır. Viewer bu bağlantıyı yeni veri setinde kullanabilir; yeni veri setinin sahibi viewer olur.
- Güvenlik: Viewer kimlik bilgisini görmez, yalnız kullanır. Sorgu bağlantının sahibi (admin) kimliğiyle çalışırsa viewer, admin'in tüm tablolarına erişebilir. Bu kabul edilemez; sorgu viewer kimliğiyle değil, **veri seti sahibinin** izin verdiği tablolarla sınırlı olmalı.
- Bu yüzden A, yalnız "bağlantı kullanma" izni olarak tasarlanmalı: viewer bağlantıyı yalnızca veri seti tanımında kullanabilir, serbest SQL çalıştıramaz.

**B. Bağlantı paylaşımını `shares` tablosuna genişletmek (`resource_type = "connection"`).**
Tek bir paylaşım mekanizması, tutarlı. Ama bağlantı kimlik bilgisi paylaşımı tek bir hatayla büyük etki yaratır.
- Güvenlik: Parola, API'ye hiçbir zaman dönmemeli; yalnız "bu bağlantıyla veri seti oluşturabilirsin" yetkisi. Kullanım log'lanmalı.

**C. Viewer için ayrı, sınırlı bağlantı türü (örn. admin tanımlı "paylaşılan kaynak").**
Admin kaynağı bir kez tanımlar, şema/tablo beyaz listesi koyar, viewer yalnız o beyaz listedeki tablolardan veri seti kurar. En güvenli ama en çok iş gerektiren seçenek.

## Öneri

**B'nin sınırlı hali**, tek bir ek kuralla:
1. Admin bir bağlantıyı viewer'a `use` yetkisiyle paylaşır (`shares.resource_type="connection"`, `permission="read"` ya da yeni `use`).
2. Viewer bu bağlantı üzerinde veri seti **oluşturabilir** ama bağlantının şema/tablo listesini ve serbest SQL'i görmez; yalnız mevcut veri seti tanım akışı (tablo, alan, filtre) kullanılır.
3. Veri seti çalıştırma **mevcut mantıkla** (sahibin kimliği, `resolve_connection_engine`) çalışır; RLS kuralları değişmez.
4. Parola hiçbir API yanıtında dönmez (mevcut davranış korunur).
5. Yazma (write) yetkisi bağlantı için yok; bağlantıyı yalnız admin değiştirir/siler.

Bu, A'nın güvenlik sorununu (admin kimliğiyle serbest sorgu) önler, B'nin tek mekanizma avantajını korur.

## Uygulama notu (ilk dilim)

- `shares.resource_type='connection'`, `permission='use'`, yalnız kullanıcıya; tablo listesi `connection_share_tables` (şema, tablo).
- Alıcı bağlantı listesinde yalnız `conn_id`, `db_type`, `name`, `shared` görür.
- Veri seti kurma ve çalıştırma yalnız izinli tablolarla; çalıştırma bağlantıyı veri seti sahibi adına açar (`resolve_dataset_connection`).
- Şema, sorgu, bağlantı testi uçları yalnız sahip/admin için açık kalır (alıcıya 404).
- Alıcı tablo seçici: `GET /api/connections/shared` (bağlantı + izinli tablolar) ve `GET /api/connections/shared/{conn}/tables/{table}/columns` (yalnız izinli tablo, aksi 404). Sorgu Oluşturucu'da paylaşılan bağlantıda tablo listesi izin listesinden gelir; önizleme ve doğrudan çalıştırma kapalıdır (veri seti kaydedilip Veri Setleri'nden çalıştırılır).
- Açık kalanlar: dashboard widget yolu (paylaşılan bağlantıda hâlâ `listColumns`), "Önerilen İlişkiler" ve analiz (paylaşılan bağlantı için kapsam dışı), kullanım log'u (karar: yok), join tablolarının ana şemada varsayılması.

## Kararlar (2026-11-25 itibarıyla)

- Viewer'a bağlantı kullanım yetkisi: evet, admin/sahip tek tek seçer (`use` izni).
- Hangi tablolar: yalnız sahibin seçtiği tablolar görünür.
- Kullanım denetimi (kim, hangi veri seti, ne zaman): log yok, karar bu yönde kaldı.
- Şema listesi: alıcıya gösterilmez (bilgi sızıntısı riski); izinli tablolar tek liste olarak gelir.

## Test planı (kod onayından sonra; önce kırmızı)

- Viewer, paylaşılmamış bağlantıyla veri seti oluşturamaz (403/404).
- Viewer, `use` paylaşımı olan bağlantıyla veri seti oluşturabilir; bağlantı listesinde parola alanı yok.
- Viewer, bağlantı üzerinde serbest SQL çalıştıramaz (`/api/query/run` yalnız bağlantı sahibine açık kalır).
- Viewer, bağlantıyı silemez/değiştiremez.
- Veri seti çalıştırmada RLS kuralları ve sahibin kimliği korunur (mevcut `tests/access/test_dataset_run.py` ve `test_rls.py` geçer).
