#!/usr/bin/env bash
# Detecta pipeline parado >2h e reinicia o loop.
# Cron sugerido: */30 * * * * /caminho/para/scripts/restart_pipeline.sh
set -euo pipefail

cd "$(dirname "$0")/.."

set -a
source .env
set +a

LOG="data/logs/restart_$(date +%F).log"
mkdir -p data/logs

HEARTBEAT="data/.pipeline_heartbeat"
PIDFILE="data/.pipeline_loop.pid"
LOOP_CMD="uv run cs pipeline-loop --interval 60"

# Threshold em segundos (2 horas)
IDLE_THRESHOLD=7200

restart_loop() {
    echo "$(date -Iseconds) Reiniciando pipeline-loop…" >> "$LOG"

    # Mata processo anterior se existir
    if [ -f "$PIDFILE" ]; then
        OLD_PID=$(cat "$PIDFILE")
        if kill -0 "$OLD_PID" 2>/dev/null; then
            kill "$OLD_PID" && echo "$(date -Iseconds) Processo $OLD_PID encerrado" >> "$LOG"
        fi
        rm -f "$PIDFILE"
    fi

    # Inicia em background e salva PID
    nohup $LOOP_CMD >> "$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    echo "$(date -Iseconds) Loop reiniciado (PID=$!)" >> "$LOG"

    # Alerta operador via cs alert-test (reutiliza router configurado)
    uv run cs alert-test --level warning >> "$LOG" 2>&1 || true
}

# Se heartbeat não existe, inicia loop pela primeira vez
if [ ! -f "$HEARTBEAT" ]; then
    echo "$(date -Iseconds) Heartbeat não encontrado — iniciando loop" >> "$LOG"
    restart_loop
    exit 0
fi

# Calcula idle time
MTIME=$(stat -c %Y "$HEARTBEAT")
NOW=$(date +%s)
IDLE=$(( NOW - MTIME ))

if [ "$IDLE" -gt "$IDLE_THRESHOLD" ]; then
    echo "$(date -Iseconds) Loop idle há ${IDLE}s (threshold=${IDLE_THRESHOLD}s) — reiniciando" >> "$LOG"
    restart_loop
else
    echo "$(date -Iseconds) Loop OK (idle=${IDLE}s)" >> "$LOG"
fi
