# SuperBI Frontend — Sıfırdan Yeniden Yazıldı ve Test Edildi

## GÜNCELLEME 2 — Chart.js'ten Apache ECharts'a geçildi, harita eklendi

Grafik motoru **Apache ECharts**'a geçirildi (CDN üzerinden, build
gerektirmeden). Sebep: Superset gibi olgun BI ürünleri de ECharts
kullanıyor; büyük veri setlerinde Chart.js'ten daha performanslı, ve
en önemlisi **harita (map) desteği** getirdi — artık `map` widget'ı da
gerçekten çalışıyor (dünya haritası, ülke bazlı ısı haritası).

**Harita nasıl kullanılır:** Etiket kolonu (X ekseni) olarak seçtiğiniz
kolonun değerleri **İngilizce ülke adları** olmalı (örn. `Turkey`,
`Germany`, `United States`) — ECharts'ın dünya haritası GeoJSON'undaki
isimlerle eşleşmesi gerekiyor. Şehir/ilçe bazlı harita desteklenmiyor.

Bu geçiş de gerçek test edildi: ECharts'a sahte (mock) bir sınıf enjekte
edilip `setOption()`'a giden `series` tipinin (`pie`, `bar`, `map` vb.)
ve verinin doğru olduğu, harita için dünya GeoJSON'unun gerçekten
indirilip `registerMap` ile kayıt edildiği doğrulandı.

**Bilinen davranış (hata değil, mimari not):** Canvas'taki herhangi bir
widget'ın veri bağlama ayarı değiştiğinde, o an ekrandaki **tüm**
widget'lar yeniden render edilip verileri tekrar backend'den çekiliyor.
Az sayıda widget'ta sorun yaratmaz, çok widget'lı yoğun dashboard'larda
gereksiz API çağrısı artışına yol açabilir — ihtiyaç olursa optimize
edilebilir (sadece değişen widget'ı yeniden çekme).

---

## GÜNCELLEME 1 — Gerçek grafik render (artık ECharts ile)

Önceki notta "widget'lar sadece yer tutucu" dedim — bu artık geçerli
değil. Widget'lara gerçek veri bağlayıp gerçek grafik çizdirebilirsiniz:

- Bir widget'a tıklayın → sağdaki panelde **"Veri Bağlama"** bölümü çıkar
- Bağlantı → tablo → etiket kolonu (X ekseni) → değer kolonu (Y ekseni) → toplama (sum/avg/count/min/max) seçin → **"Bağla ve Çiz"**
- `line`/`column`/`pie`/`donut` gerçek grafik, `map` dünya haritası, `kpi` büyük rakam, `table`/`matrix` mini tablo, `text` düz metin kutusu

**Teknik not:** `query_id` alanı backend'de serbest bir string olduğu
için, veri bağlama konfigürasyonu (`{conn_id, table, labelCol, valueCol,
agg}`) JSON olarak bu alana serileştiriliyor. Backend'de herhangi bir
değişiklik gerekmedi.

---

Frontend'iniz de (backend gibi) diskte hiç bulunamadığı ve Claude sohbeti
silindiği için tamamen sıfırdan yazıldı. Build adımı GEREKTİRMEZ — düz
HTML/CSS/JS, doğrudan statik dosya olarak servis edilir.

## Nasıl test edildi?

Bu sefer sadece syntax kontrolü değil, **gerçek DOM etkileşimleriyle**
uçtan uca test edildi (jsdom + gerçek çalışan backend'e karşı):

- ✅ Kayıt formu → giriş yapma → ana uygulamaya geçiş
- ✅ Bağlantılar ekranı → formdan gerçek bir SQLite bağlantısı oluşturma
- ✅ Sorgu Oluşturucu → tablo seçme → kolon listesi çekme → SQL önizleme → sorguyu çalıştırıp sonuç tablosunu render etme
- ✅ Dashboard → yeni dashboard oluşturma → mm→px canvas hesaplaması (297mm × 3px/mm = 891px doğrulandı) → widget ekleme → widget seçince özellik panelinin dolması

Tüm bu adımlar gerçek buton tıklamaları/form submit event'leriyle simüle
edildi, sahte (mock) veri değil gerçek backend'e giden gerçek isteklerle.

## Dosyalar

```
index.html   — sayfa iskeleti
style.css    — tüm görsel tasarım
api.js       — backend API istemcisi (fetch tabanlı, DOM'dan bağımsız)
app.js       — tüm uygulama mantığı (auth, bağlantılar, sorgu oluşturucu,
               geçmiş, dashboard canvas, sürücüler)
```

## Deploy nasıl yapılır

### 1. Dosyaları sunucuya yükleyin

```bash
mkdir -p /opt/superbi/frontend
```

FileZilla'da bu 4 dosyayı (`index.html`, `style.css`, `api.js`, `app.js`)
`/opt/superbi/frontend` içine yükleyin.

### 2. Nginx config'ini GÜNCELLEYİN (önemli)

Şu anki Nginx config'iniz TÜM istekleri (`/`) backend'e (port 8000)
yönlendiriyor. Artık `/` frontend'e, sadece `/api/` backend'e gitmeli.

```bash
nano /etc/nginx/sites-available/superbi
```

İçeriği şu şekilde değiştirin (SSL kısımları certbot'un eklediği haliyle
kalsın, sadece `location` bloklarını güncelleyin):

```nginx
server {
    server_name superbi.bidanismanlik.com.tr;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        root /opt/superbi/frontend;
        try_files $uri $uri/ /index.html;
    }

    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/superbi.bidanismanlik.com.tr/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/superbi.bidanismanlik.com.tr/privkey.pem; # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot
}
server {
    if ($host = superbi.bidanismanlik.com.tr) {
        return 301 https://$host$request_uri;
    } # managed by Certbot
    listen 80;
    server_name superbi.bidanismanlik.com.tr;
    return 404; # managed by Certbot
}
```

Kaydedip test edin ve yeniden yükleyin:

```bash
nginx -t
systemctl reload nginx
```

### 3. Test edin

Tarayıcıda `https://superbi.bidanismanlik.com.tr` açın — artık Swagger
değil, gerçek SuperBI arayüzü gelmeli. İlk kayıt olduğunuz kullanıcı
otomatik admin olur.

### 4. CORS ayarını sadeleştirebilirsiniz (isteğe bağlı)

Frontend artık backend ile **aynı origin**'den (`superbi.bidanismanlik.com.tr`)
servis edildiği için CORS'a teknik olarak gerek kalmadı, ama zararı da
yok — `superbi.service` dosyasındaki `DATALENS_CORS_ORIGINS` ayarını
olduğu gibi bırakabilirsiniz.
