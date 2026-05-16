#!/usr/bin/env bash
# Roda discover + triagens baratas (metadata + caption).
# Cron: 0 8,20 * * *
set -euo pipefail

cd "$(dirname "$0")/.."

# carrega .env (export todas as vars)
set -a
source .env
set +a

LOG="data/logs/discover_$(date +%F).log"
mkdir -p data/logs

{
    echo "==== $(date -Iseconds) run_discover.sh start ===="

    uv run cs discover
    uv run cs triage --stage metadata
    uv run cs triage --stage caption

    echo "==== $(date -Iseconds) run_discover.sh end ===="
} >> "$LOG" 2>&1
