#!/usr/bin/env bash
# run_gui.sh — Inicia a interface gráfica PySide6 do Canal Soberania
#
# Pré-requisitos:
#   uv sync --extra gui          # instala PySide6
#   # No Linux, requer libGL e GStreamer para o player de vídeo:
#   sudo apt install libgl1 libxcb-cursor0 gstreamer1.0-plugins-good \
#                    gstreamer1.0-plugins-bad gstreamer1.0-libav
#   (libgl1 substitui libgl1-mesa-glx a partir do Ubuntu 22.04)
#
# Uso:
#   bash run_gui.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Verifica se PySide6 está disponível
if ! uv run python -c "import PySide6" 2>/dev/null; then
    echo "PySide6 não encontrado. Execute:"
    echo "  uv sync --extra gui"
    exit 1
fi

exec uv run cs-gui "$@"
