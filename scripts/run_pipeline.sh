#!/usr/bin/env bash
# Avança vídeos/clipes pendentes nas etapas caras.
# Cron: */30 * * * *
set -euo pipefail

cd "$(dirname "$0")/.."

set -a
source .env
set +a

LOG="data/logs/pipeline_$(date +%F).log"
mkdir -p data/logs

# Lock para evitar execução paralela (transcrição é pesada)
LOCKFILE="data/.pipeline.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "$(date -Iseconds) já há execução em andamento, abortando" >> "$LOG"
    exit 0
fi

{
    echo "==== $(date -Iseconds) run_pipeline.sh start ===="

    uv run cs download --pending
    uv run cs transcribe --pending
    uv run cs triage --stage transcript
    uv run cs find-clips --pending
    uv run cs edit --pending
    uv run cs thumbnail --pending
    uv run cs metadata --pending
    uv run cs upload --platform youtube --pending
    uv run cs upload --platform tiktok --pending

    echo "==== $(date -Iseconds) run_pipeline.sh end ===="
} >> "$LOG" 2>&1
