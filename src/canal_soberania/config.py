"""Carrega .env e config/canais.yaml."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Raiz do repositório (dois níveis acima deste arquivo)
_REPO_ROOT = Path(__file__).parent.parent.parent


def _repo(rel: str) -> Path:
    return _REPO_ROOT / rel


load_dotenv(_repo(".env"), override=False)


# ---------------------------------------------------------------------------
# Settings (variáveis de ambiente)
# ---------------------------------------------------------------------------


class Settings(BaseModel):
    anthropic_api_key: str = Field(default="")
    anthropic_model_triage: str = Field(default="claude-haiku-4-5-20251001")
    anthropic_model_deep: str = Field(default="claude-sonnet-4-6")

    openrouter_api_key: str = Field(default="")

    youtube_api_key: str = Field(default="")
    youtube_oauth_client_secrets_path: str = Field(default="config/client_secrets.json")
    youtube_oauth_token_path: str = Field(default="config/youtube_token.json")

    whisper_model: str = Field(default="large-v3")
    whisper_device: str = Field(default="cpu")
    whisper_compute_type: str = Field(default="int8")

    data_dir: Path = Field(default=_repo("data"))
    log_level: str = Field(default="INFO")
    dry_run: bool = Field(default=False)

    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")


def load_settings() -> Settings:
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        anthropic_model_triage=os.getenv("ANTHROPIC_MODEL_TRIAGE", "claude-haiku-4-5-20251001"),
        anthropic_model_deep=os.getenv("ANTHROPIC_MODEL_DEEP", "claude-sonnet-4-6"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        youtube_api_key=os.getenv("YOUTUBE_API_KEY", ""),
        youtube_oauth_client_secrets_path=os.getenv(
            "YOUTUBE_OAUTH_CLIENT_SECRETS_PATH", "config/client_secrets.json"
        ),
        youtube_oauth_token_path=os.getenv("YOUTUBE_OAUTH_TOKEN_PATH", "config/youtube_token.json"),
        whisper_model=os.getenv("WHISPER_MODEL", "large-v3"),
        whisper_device=os.getenv("WHISPER_DEVICE", "cpu"),
        whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        data_dir=Path(os.getenv("DATA_DIR", str(_repo("data")))),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
    )


# ---------------------------------------------------------------------------
# Canais config (canais.yaml)
# ---------------------------------------------------------------------------


class Canal(BaseModel):
    id: str
    nome: str
    handle: str
    channel_url: str
    tema_primario: str
    peso: float = 1.0
    auto_publish: bool = False
    tolerancia_cortes: str = "desconhecida"
    nota: str = ""


class Parametros(BaseModel):
    janela_dias_discover: int = 7
    max_videos_por_canal_por_run: int = 20
    threshold_triage_metadata: int = 5
    threshold_triage_caption: int = 6
    threshold_triage_transcript: int = 7
    max_clipes_por_video: int = 5
    clip_duracao_min: int = 30
    clip_duracao_max: int = 90
    clip_duracao_ideal: int = 60


class CanaisConfig(BaseModel):
    canais: list[Canal]
    parametros: Parametros = Field(default_factory=Parametros)


def load_canais(path: Path | None = None) -> CanaisConfig:
    if path is None:
        path = _repo("config/canais.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CanaisConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# Caminhos derivados (instanciados a partir das settings globais)
# ---------------------------------------------------------------------------


def get_paths(settings: Settings) -> dict[str, Path]:
    data = settings.data_dir
    return {
        "data_dir": data,
        "log_dir": data / "logs",
        "db_path": data / "canal.db",
        "schema_path": _repo("schema.sql"),
        "canais_path": _repo("config/canais.yaml"),
        "prompts_dir": _repo("prompts"),
        "audio_dir": data / "audio",
        "video_dir": data / "video",
        "captions_dir": data / "captions",
        "transcripts_dir": data / "transcripts",
        "clips_dir": data / "clips",
        "thumbs_dir": data / "thumbs",
        "backups_dir": data / "backups",
    }
