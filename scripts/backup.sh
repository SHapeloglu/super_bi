#!/bin/bash
# SuperBI SQLite veritabanini yedekler: once sqlite3 .backup ile tutarli bir kopya alir, sonra gzip ile sikistirir.
# Calistirma: cron ile ya da elle (bash backup.sh). Cron kaydi bu dosyada yok; bilinmiyor.
# Gerekli: sqlite3 ve gzip komutlari, /opt/superbi/data/superbi.db dosyasi.
# DIKKAT: 14 gunden eski superbi_*.db.gz yedekleri SILINIR; geri alinamaz.
# Yedekler ayni diskte tutulur; disk dolarsa yedek alinamaz.
set -euo pipefail

# Yedeklenecek SQLite veritabani. Yol sabit yazilidir.
DB_PATH="/opt/superbi/data/superbi.db"
BACKUP_DIR="/opt/superbi/backups"
# Yedeklerin kac gun saklanacagi. Bu sureden eski yedekler asagida silinir.
RETENTION_DAYS=14
# Dosya adina tarih ve saat ekler; her calistirmada yeni dosya olusur, eskisinin ustune yazilmaz.
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/superbi_${TIMESTAMP}.db"

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_PATH" ]; then
    echo "[$(date)] HATA: Kaynak veritabanı bulunamadı: $DB_PATH" >&2
    exit 1
fi

# DIKKAT: cp yerine sqlite3 .backup kullanilir. Veritabani yazilirken dogrudan kopyalanirsa bozuk yedek olusabilir; .backup bunu onler.
sqlite3 "$DB_PATH" ".backup '${BACKUP_FILE}'"
# Ham .db dosyasini sikistirir. gzip varsayilan olarak orijinal .db dosyasini kaldirir; sadece .gz kalir.
gzip "$BACKUP_FILE"

echo "[$(date)] Yedek alındı: ${BACKUP_FILE}.gz ($(du -h "${BACKUP_FILE}.gz" | cut -f1))"

# Saklama suresini asan (14 gunden eski) yedekleri siler. -delete geri alinamaz. Sadece superbi_*.db.gz desenine uyanlar silinir.
find "$BACKUP_DIR" -name "superbi_*.db.gz" -mtime "+${RETENTION_DAYS}" -delete

echo "[$(date)] ${RETENTION_DAYS} günden eski yedekler temizlendi."
echo "[$(date)] Mevcut yedek sayısı: $(find "$BACKUP_DIR" -name "superbi_*.db.gz" | wc -l)"
