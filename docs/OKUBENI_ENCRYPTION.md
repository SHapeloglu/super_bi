# Kalıcı Çözüm — PostgreSQL/MySQL/MSSQL Şifreleri Artık Şifreli Saklanıyor

## Ne değişti?

Bağlantı şifreleri artık **Fernet ile şifrelenip** veritabanında saklanıyor.
Servis restart olduğunda (`systemctl restart superbi`), PostgreSQL/MySQL/MSSQL
bağlantıları da SQLite gibi **otomatik olarak kendini yeniden kuruyor** —
"Bağlantılar" sekmesine gidip şifreyi tekrar girmenize gerek kalmıyor.

## Gerçek PostgreSQL ile test edildi

Sandbox'ta gerçek bir PostgreSQL sunucusu kurup, gerçek şifreyle bir bağlantı
oluşturdum, veritabanında şifrenin düz metin DEĞİL şifreli
(`gAAAAAB...` formatında) saklandığını doğruladım, sonra sunucu restart'ını
simüle edip (engine'leri bellekten silip) **yeniden bağlanmadan** sorgunun
başarıyla çalıştığını kanıtladım. `test_connection` endpoint'i de aynı
mantığa bağlandı, o da artık restart sonrası otomatik yeniden bağlanıyor.

## Bu zip'te 6 dosya var

```
app/core/crypto.py           ← YENİ — şifreleme/çözme modülü
app/core/repository.py       ← ConnectionMeta'ya port + password_enc eklendi
app/db/sqlite_store.py       ← port_/password_enc kolonları için migration
app/api/connections.py       ← şifre artık şifrelenerek kaydediliyor
app/deps.py                  ← otomatik yeniden bağlanma TÜM DB tiplerine genişletildi
requirements.txt             ← cryptography paketi eklendi
```

## KURULUM — SIRAYI TAKİP EDİN (önemli)

### 1. Önce yeni bir şifreleme anahtarı üretin

```bash
cd /opt/superbi
source venv/bin/activate
pip install -r requirements.txt
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Çıkan değeri (örn. `guUxa6WB87aMT7DDRPNDa40eg7HAfErlgGaFMh1hjzE=`) kopyalayın —
**bir daha görmeyeceksiniz, not edin.**

### 2. Bu anahtarı systemd servis dosyasına ekleyin

```bash
nano /etc/systemd/system/superbi.service
```

`Environment="DATALENS_JWT_SECRET=..."` satırının altına yeni bir satır ekleyin:

```ini
Environment="DATALENS_DB_ENCRYPTION_KEY=BURAYA_URETTIGINIZ_ANAHTARI_YAPISTIRIN"
```

**ÇOK ÖNEMLİ:** Bu anahtarı JWT secret gibi **sabit tutun ve yedekleyin**.
Eğer bu anahtar kaybolur veya değişirse, önceden şifrelenmiş TÜM
PostgreSQL/MySQL/MSSQL şifreleri çözülemez hale gelir — o bağlantıları
şifreyi tekrar girerek yeniden oluşturmanız gerekir (SQLite bağlantıları
etkilenmez, onlar zaten şifre kullanmıyor).

### 3. Dosyaları yükleyip servisi yeniden başlatın

FileZilla ile 5 Python dosyasını + `requirements.txt`'i üzerine yükleyin,
sonra:

```bash
systemctl daemon-reload
systemctl restart superbi
systemctl status superbi
```

### 4. Mevcut PostgreSQL/MySQL/MSSQL bağlantılarınızı YENİDEN oluşturun

**Önemli:** Bu değişiklik öncesi oluşturduğunuz bağlantıların şifreleri hiç
saklanmamıştı (kasıtlı olarak) — yani mevcut `ca568f0a` ve `df49c8e1` gibi
eski bağlantılarınızın şifresi hâlâ yok. Bunları bir kez daha, son kez elle
yeniden oluşturmanız gerekiyor. Bundan sonraki restart'larda bu sorunu bir
daha yaşamayacaksınız.

## Güvenlik notu

Şifreleme anahtarı veritabanı dosyasıyla AYNI yerde durmuyor (systemd servis
dosyasında) — yani biri sadece `superbi.db` dosyasını çalarsa şifreleri
çözemez, sistemd servis dosyasına da erişmesi gerekir. Bu, tam bir secrets
vault (Vault/AWS Secrets Manager) kadar güçlü değildir ama tek-VPS'lik bir
kurulum için makul ve standart bir "encryption at rest" yaklaşımıdır.
