#!/usr/bin/env bash
# Backup do SQLite. Cron: 0 3 * * *
set -euo pipefail

cd "$(dirname "$0")/.."

mkdir -p data/backups
DATE=$(date +%F)
DEST="data/backups/canal_${DATE}.db"

# .backup do sqlite3 é seguro mesmo com pipeline rodando (WAL)
sqlite3 data/canal.db ".backup '${DEST}'"

# Manter últimos 30 dias
find data/backups -name 'canal_*.db' -mtime +30 -delete

echo "$(date -Iseconds) backup ok: ${DEST}"
