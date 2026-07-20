#!/bin/bash
set -euo pipefail

DB_PATH="/opt/superbi/data/superbi.db"
BACKUP_DIR="/opt/superbi/backups"
RETENTION_DAYS=14
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/superbi_${TIMESTAMP}.db"

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_PATH" ]; then
    echo "[$(date)] HATA: Kaynak veritabanı bulunamadı: $DB_PATH" >&2
    exit 1
fi

sqlite3 "$DB_PATH" ".backup '${BACKUP_FILE}'"
gzip "$BACKUP_FILE"

echo "[$(date)] Yedek alındı: ${BACKUP_FILE}.gz ($(du -h "${BACKUP_FILE}.gz" | cut -f1))"

find "$BACKUP_DIR" -name "superbi_*.db.gz" -mtime "+${RETENTION_DAYS}" -delete

echo "[$(date)] ${RETENTION_DAYS} günden eski yedekler temizlendi."
echo "[$(date)] Mevcut yedek sayısı: $(find "$BACKUP_DIR" -name "superbi_*.db.gz" | wc -l)"
