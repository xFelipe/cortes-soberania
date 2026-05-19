#!/usr/bin/env bash
# Verifica saúde do pipeline e notifica via Telegram se houver problema.
# Cron sugerido: */15 * * * * /caminho/para/scripts/healthcheck.sh
set -euo pipefail

cd "$(dirname "$0")/.."

set -a
source .env
set +a

LOG="data/logs/healthcheck_$(date +%F).log"
mkdir -p data/logs

HEARTBEAT="data/.pipeline_heartbeat"

{
    echo "==== $(date -Iseconds) healthcheck start ===="
    uv run cs health-check \
        --heartbeat "$HEARTBEAT" \
        --notify
    echo "==== $(date -Iseconds) healthcheck end ===="
} >> "$LOG" 2>&1
