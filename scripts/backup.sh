#!/bin/sh
# Daily pg_dump backup — runs inside the db container via cron
# Backups land in /backups (mounted to ./backups on the host)

BACKUP_DIR="/backups"
DATE=$(date +%Y-%m-%d)
FILE="$BACKUP_DIR/sedna_ops_$DATE.sql.gz"

pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$FILE"
echo "Backup written: $FILE"

# Retain last 30 days
find "$BACKUP_DIR" -name "sedna_ops_*.sql.gz" -mtime +30 -delete
