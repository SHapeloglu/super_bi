# Güvenlik Düzeltmesi — Hesaplanmış Alan Formüllerinde Noktalı Virgül

## Ne oldu?

Sunucunuzda kurulan `sqlglot` sürümü (25.34.1), benim test ettiğim sürümden
(30.12.0) farklı davrandı: `"price; DROP TABLE users --"` gibi noktalı
virgüllü bir formül, 30.x'te düzgün reddediliyordu ama 25.x'te sessizce
sadece "price" kısmını alıp gerisini atıyordu.

**Önemli:** Bu durumun ikisi de fonksiyonel olarak güvenliydi — zararlı kısım
hiçbir zaman gerçek SQL'e karışmadı, `DROP TABLE` hiç çalışmadı. Ama versiyona
göre değişen, öngörülemeyen bir davranıştı. Şimdi noktalı virgülü baştan,
açıkça ve her sürümde tutarlı şekilde reddediyoruz.

## Bu zip'te 2 dosya var

```
app/services/expression_builder.py  ← noktalı virgül artık açıkça reddediliyor
requirements.txt                     ← sqlglot artık TAM sürüme sabitlendi (25.34.1)
```

## Kurulum

```bash
```

FileZilla ile bu 2 dosyayı üzerine yükleyin, sonra:

```bash
cd /opt/superbi
source venv/bin/activate
pip install -r requirements.txt
systemctl restart superbi
systemctl status superbi
```

`pip install` bu sefer bir şey değiştirmemeli (versiyon zaten kurulu olan
25.34.1 ile eşleşiyor) ama yine de çalıştırmanız iyi bir alışkanlık.

## Neden sürüm sabitlendi (>= yerine ==)

`sqlglot`, hesaplanmış alan güvenlik whitelist'inin temeli. Sürümler arası
ayrıştırma davranışı farklılık gösterebildiği kanıtlandığı için, gelecekte
sunucu bir `pip install --upgrade` ile farklı bir sqlglot sürümüne
sıçramasın diye tam sürüme sabitledim. İleride sürüm yükseltmek isterseniz,
önce `expression_builder.py`'nin güvenlik testlerini yeni sürüme karşı
tekrar çalıştırmanızı öneririm.
