#!/usr/bin/env bash
# Checa itens presos no pipeline e alerta via Telegram se configurado.
# Cron: */5 * * * *  (ou chamar no final de run_pipeline.sh)
set -euo pipefail

cd "$(dirname "$0")/.."

set -a
source .env
set +a

uv run cs alert --threshold 50
