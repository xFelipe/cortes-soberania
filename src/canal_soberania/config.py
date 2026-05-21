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

    # Alertas SMTP
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from: str = Field(default="")
    smtp_to: str = Field(default="")

    # Canais de alerta ativos (comma-separated: "telegram,smtp" | "telegram" | "smtp" | "none")
    alert_channels: str = Field(default="telegram")
    # Threshold para alertar sobre itens presos num mesmo status
    alert_stuck_threshold: int = Field(default=50)

    # Backends plugáveis (Onda 1)
    llm_backend: str = Field(default="anthropic")      # anthropic | ollama | hybrid | openai
    whisper_backend: str = Field(default="local_cpu")  # local_cpu | local_cuda | groq | openai

    # Ollama
    ollama_base_url: str = Field(default="http://localhost:11434/v1/chat/completions")
    ollama_model_triage: str = Field(default="qwen2.5:14b-instruct-q4_K_M")
    ollama_model_deep: str = Field(default="qwen2.5:32b-instruct-q4_K_M")

    # APIs de escape hatch
    groq_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")

    # Pipeline loop
    pipeline_loop_interval: int = Field(default=60)


def get_repo_root() -> Path:
    """Retorna a raiz do repositório (usado externamente para localizar o .env)."""
    return _REPO_ROOT


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
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_from=os.getenv("SMTP_FROM", ""),
        smtp_to=os.getenv("SMTP_TO", ""),
        alert_channels=os.getenv("ALERT_CHANNELS", "telegram"),
        alert_stuck_threshold=int(os.getenv("ALERT_STUCK_THRESHOLD", "50")),
        llm_backend=os.getenv("LLM_BACKEND", "anthropic"),
        whisper_backend=os.getenv("WHISPER_BACKEND", "local_cpu"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1/chat/completions"),
        ollama_model_triage=os.getenv("OLLAMA_MODEL_TRIAGE", "qwen2.5:14b-instruct-q4_K_M"),
        ollama_model_deep=os.getenv("OLLAMA_MODEL_DEEP", "qwen2.5:32b-instruct-q4_K_M"),
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        pipeline_loop_interval=int(os.getenv("PIPELINE_LOOP_INTERVAL", "60")),
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
    ativo: bool = True


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
# Output canais config (output_canais.yaml)
# ---------------------------------------------------------------------------


class OutputCanal(BaseModel):
    id: str
    nome: str
    tema: str = ""
    fontes: list[str] = Field(default_factory=list)
    criteria_path: str = ""
    branding_dir: str = ""
    youtube_channel_id: str = ""
    youtube_token_path: str = "config/youtube_token.json"
    ativo: bool = True


class OutputCanaisConfig(BaseModel):
    output_canais: list[OutputCanal]


def load_output_canais(path: Path | None = None) -> OutputCanaisConfig:
    if path is None:
        path = _repo("config/output_canais.yaml")
    if not path.exists():
        return OutputCanaisConfig(output_canais=[])
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return OutputCanaisConfig.model_validate(raw)


def resolve_criteria_path(output_canal: OutputCanal) -> Path:
    if output_canal.criteria_path:
        p = _REPO_ROOT / output_canal.criteria_path
        if p.exists():
            return p
    slug_path = _REPO_ROOT / "config" / "criterios" / f"{output_canal.id}.md"
    if slug_path.exists():
        return slug_path
    return _REPO_ROOT / "config" / "criterios_relevancia.md"


def resolve_prompt_path(output_canal_id: str, prompt_name: str, version: str = "v1") -> Path:
    suffix = "" if version == "v1" else f"_{version}"
    canal_specific = _REPO_ROOT / "prompts" / output_canal_id / f"{prompt_name}{suffix}.txt"
    if canal_specific.exists():
        return canal_specific
    return _REPO_ROOT / "prompts" / f"{prompt_name}{suffix}.txt"


# ---------------------------------------------------------------------------
# Caminhos derivados (instanciados a partir das settings globais)
# ---------------------------------------------------------------------------


_DATA_SUBDIRS = (
    "log_dir",
    "audio_dir",
    "video_dir",
    "captions_dir",
    "transcripts_dir",
    "clips_dir",
    "thumbs_dir",
    "backups_dir",
)


def ensure_data_dirs(paths: dict[str, Path]) -> None:
    """Cria todos os diretórios de dados se ainda não existirem."""
    for key in _DATA_SUBDIRS:
        paths[key].mkdir(parents=True, exist_ok=True)


def get_paths(settings: Settings) -> dict[str, Path]:
    data = settings.data_dir
    return {
        "data_dir": data,
        "log_dir": data / "logs",
        "db_path": data / "canal.db",
        "schema_path": _repo("schema.sql"),
        "canais_path": _repo("config/canais.yaml"),
        "output_canais_path": _repo("config/output_canais.yaml"),
        "prompts_dir": _repo("prompts"),
        "audio_dir": data / "audio",
        "video_dir": data / "video",
        "captions_dir": data / "captions",
        "transcripts_dir": data / "transcripts",
        "clips_dir": data / "clips",
        "thumbs_dir": data / "thumbs",
        "backups_dir": data / "backups",
    }
