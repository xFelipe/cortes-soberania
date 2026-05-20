"""Router: /config — leitura e escrita não-destrutiva das configurações editáveis."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from canal_soberania.api.auth import verify_token
from canal_soberania.config import get_repo_root, load_settings

router = APIRouter(prefix="/config", tags=["config"])

# Chaves expostas via GET (valores visíveis)
EDITABLE_KEYS: frozenset[str] = frozenset({
    "LLM_BACKEND",
    "WHISPER_BACKEND",
    "WHISPER_DEVICE",
    "WHISPER_COMPUTE_TYPE",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL_TRIAGE",
    "OLLAMA_MODEL_DEEP",
    "ALERT_CHANNELS",
    "ALERT_STUCK_THRESHOLD",
    "TELEGRAM_CHAT_ID",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_FROM",
    "SMTP_TO",
    "LOG_LEVEL",
    "DRY_RUN",
    "PIPELINE_LOOP_INTERVAL",
})

# Chaves que também são graváveis, mas retornam "***" no GET
SECRET_KEYS: frozenset[str] = frozenset({
    "SMTP_PASSWORD",
    "TELEGRAM_BOT_TOKEN",
})

ALL_WRITABLE: frozenset[str] = EDITABLE_KEYS | SECRET_KEYS

_SETTINGS_ATTR: dict[str, str] = {
    "LLM_BACKEND": "llm_backend",
    "WHISPER_BACKEND": "whisper_backend",
    "WHISPER_DEVICE": "whisper_device",
    "WHISPER_COMPUTE_TYPE": "whisper_compute_type",
    "OLLAMA_BASE_URL": "ollama_base_url",
    "OLLAMA_MODEL_TRIAGE": "ollama_model_triage",
    "OLLAMA_MODEL_DEEP": "ollama_model_deep",
    "ALERT_CHANNELS": "alert_channels",
    "ALERT_STUCK_THRESHOLD": "alert_stuck_threshold",
    "TELEGRAM_CHAT_ID": "telegram_chat_id",
    "SMTP_HOST": "smtp_host",
    "SMTP_PORT": "smtp_port",
    "SMTP_FROM": "smtp_from",
    "SMTP_TO": "smtp_to",
    "LOG_LEVEL": "log_level",
    "DRY_RUN": "dry_run",
    "PIPELINE_LOOP_INTERVAL": "pipeline_loop_interval",
}


def _env_path() -> Path:
    return get_repo_root() / ".env"


def _merge_env(env_path: Path, patch: dict[str, str]) -> None:
    """Atualiza ou insere chaves no .env preservando comentários e demais linhas."""
    existing_lines: list[str] = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    updated: set[str] = set()
    result: list[str] = []
    for line in existing_lines:
        m = re.match(r"^([A-Z_][A-Z0-9_]*)=", line)
        if m and m.group(1) in patch:
            key = m.group(1)
            result.append(f"{key}={patch[key]}")
            updated.add(key)
        else:
            result.append(line)

    for key, val in patch.items():
        if key not in updated:
            result.append(f"{key}={val}")

    env_path.write_text("\n".join(result) + "\n", encoding="utf-8")


@router.get("")
def get_config(
    _: None = Depends(verify_token),
) -> dict[str, Any]:
    settings = load_settings()
    out: dict[str, Any] = {}
    for env_key, attr in _SETTINGS_ATTR.items():
        out[env_key] = getattr(settings, attr)
    return out


@router.put("")
def put_config(
    patch: dict[str, str],
    _: None = Depends(verify_token),
) -> dict[str, object]:
    invalid = set(patch.keys()) - ALL_WRITABLE
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chaves não permitidas: {sorted(invalid)}. Permitidas: {sorted(ALL_WRITABLE)}",
        )
    if not patch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Body vazio")

    env_path = _env_path()
    _merge_env(env_path, patch)
    return {"status": "saved", "restart_required": True, "updated": sorted(patch.keys())}
