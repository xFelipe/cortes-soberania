"""Stage 3: baixa auto-captions via yt-dlp e triagem com Claude Haiku."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, cast

import yt_dlp
import yt_dlp.utils as ydl_utils
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from canal_soberania.config import (
    CanaisConfig,
    OutputCanal,
    get_paths,
    load_canais,
    load_settings,
    resolve_criteria_path,
    resolve_prompt_path,
)
from canal_soberania.db import (
    connect,
    get_videos_by_status,
    init_db,
    insert_triage_result,
    record_api_cost,
    update_video_paths,
    update_video_status,
)
from canal_soberania.llm import extract_json
from canal_soberania.llm_backends import LLMBackend, get_llm_backend
from canal_soberania.logger import logger
from canal_soberania.models import TriageResult, TriageStage, Video, VideoStatus

_MIN_RELEVANCE_SCORE = 6

# Línguas de preferência para auto-captions
_CAPTION_LANGS = ["pt", "pt-BR", "en"]

# Máximo de caracteres da caption para o prompt (≈30min de fala em PT-BR)
_CAPTION_MAX_CHARS = 6000


def download_captions(
    video_id: str,
    captions_dir: Path,
    dry_run: bool = False,
) -> Path | None:
    """
    Baixa auto-captions do vídeo. Retorna o Path do arquivo VTT ou None se indisponível.
    Tenta PT-BR/PT primeiro, depois EN.
    """
    captions_dir.mkdir(parents=True, exist_ok=True)

    # Verifica se já baixou
    for lang in _CAPTION_LANGS:
        existing = captions_dir / f"{video_id}.{lang}.vtt"
        if existing.exists():
            logger.debug("Caption já existe: {}", existing)
            return existing

    if dry_run:
        logger.info("[dry-run] download_captions {}", video_id)
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts: dict[str, Any] = {
        "writeautomaticsub": True,
        "subtitleslangs": _CAPTION_LANGS,
        "skip_download": True,
        "outtmpl": str(captions_dir / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "sleep_interval": 3,
        "max_sleep_interval": 6,
        "retries": 5,
        "socket_timeout": 30,
    }

    @retry(
        retry=retry_if_exception_type(ydl_utils.DownloadError),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        stop=stop_after_attempt(3),
        reraise=False,
    )
    def _do_download() -> None:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    try:
        _do_download()
    except Exception as exc:
        logger.warning("yt-dlp captions erro para {} (não crítico): {}", video_id, exc)
        return None

    for lang in _CAPTION_LANGS:
        path = captions_dir / f"{video_id}.{lang}.vtt"
        if path.exists() and path.stat().st_size > 0:
            return path

    return None


def parse_vtt(path: Path, max_chars: int = _CAPTION_MAX_CHARS) -> str:
    """
    Converte VTT para texto simples. Remove timestamps, tags HTML e linhas duplicadas.
    Trunca em max_chars para evitar prompts muito longos.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")

    lines: list[str] = []
    seen: set[str] = set()

    for raw_line in raw.splitlines():
        line = raw_line.strip()
        # Pula cabeçalho, linhas de timing, metadata e vazias
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}", line):
            continue
        if re.match(r"^\d+$", line):
            continue

        # Remove tags HTML/VTT: <00:00:00.000>, <c>, </c>, etc.
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if not clean or clean in seen:
            continue

        seen.add(clean)
        lines.append(clean)

    text = " ".join(lines)
    return text[:max_chars]


def _build_caption_prompt(
    template: str,
    criterios: str,
    video: Video,
    canal_nome: str,
    caption_texto: str,
) -> str:
    duracao_min = str(round(video.duration_s / 60)) if video.duration_s else "?"
    return template.format(
        criterios_relevancia=criterios,
        canal_nome=canal_nome,
        title=video.title,
        duracao_min=duracao_min,
        caption_texto=caption_texto,
    )


def _parse_caption_response(
    raw: str,
    video_id: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
) -> TriageResult:
    data = extract_json(raw)
    score = int(cast(int, data.get("score", 0)))
    is_relevant = bool(data.get("is_relevant", score >= _MIN_RELEVANCE_SCORE))
    themes = [str(t) for t in cast(list[object], data.get("themes_detected", []))]
    rationale = str(data.get("rationale", ""))
    return TriageResult(
        video_id=video_id,
        stage=TriageStage.CAPTION,
        score=score,
        is_relevant=is_relevant,
        themes_detected=themes,
        rationale=rationale,
        raw_response=raw,
        model_used=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
    )


def triage_video_caption(
    video: Video,
    conn: sqlite3.Connection,
    llm: LLMBackend,
    model: str,
    prompt_template: str,
    criterios: str,
    canais_cfg: CanaisConfig,
    captions_dir: Path,
    threshold: int = 6,
    dry_run: bool = False,
) -> TriageResult | None:
    """
    Roda triagem de caption em um vídeo.
    - Se não houver caption → status='triage_caption_skipped' (continua pipeline).
    - Se score >= threshold → 'triage_caption_passed'.
    - Senão → 'triage_caption_rejected'.
    Retorna TriageResult ou None.
    """
    canal = next((c for c in canais_cfg.canais if c.id == video.canal_id), None)
    canal_nome = canal.nome if canal else video.canal_id

    caption_path = download_captions(video.video_id, captions_dir, dry_run=dry_run)

    if caption_path is None:
        if not dry_run:
            logger.info("Sem caption para {} — marcando como skipped", video.video_id)
            with conn:
                update_video_status(conn, video.video_id, VideoStatus.TRIAGE_CAPTION_SKIPPED)
        return None

    caption_texto = parse_vtt(caption_path)
    if not caption_texto.strip():
        logger.warning("Caption vazia para {} — marcando como skipped", video.video_id)
        if not dry_run:
            with conn:
                update_video_status(conn, video.video_id, VideoStatus.TRIAGE_CAPTION_SKIPPED)
        return None

    # Persiste o path da caption
    if not dry_run:
        with conn:
            update_video_paths(conn, video.video_id, caption_path=str(caption_path))

    prompt = _build_caption_prompt(
        prompt_template, criterios, video, canal_nome, caption_texto
    )

    if dry_run:
        logger.info(
            "[dry-run] triage_caption {} | caption_chars={} | prompt_len={}",
            video.video_id,
            len(caption_texto),
            len(prompt),
        )
        return None

    # Guard de idempotência: evita chamar LLM se triagem já foi feita
    existing = conn.execute(
        "SELECT score, is_relevant FROM triage_results WHERE video_id = ? AND stage = 'caption'"
        " ORDER BY created_at DESC LIMIT 1",
        (video.video_id,),
    ).fetchone()
    if existing is not None:
        new_status = VideoStatus.TRIAGE_CAPTION_PASSED if existing["is_relevant"] else VideoStatus.TRIAGE_CAPTION_REJECTED
        logger.info(
            "triage_caption {} já feita (score={}), pulando LLM → {}",
            video.video_id, existing["score"], new_status,
        )
        with conn:
            update_video_status(conn, video.video_id, new_status)
        return None

    try:
        resp = llm.complete(prompt, model=model, max_tokens=512, task="triage_caption")
    except Exception as exc:
        logger.error("LLM error para {}: {}", video.video_id, exc)
        with conn:
            update_video_status(conn, video.video_id, VideoStatus.PROCESSING_ERROR, str(exc))
        return None

    try:
        result = _parse_caption_response(
            resp.text, video.video_id, resp.model,
            resp.tokens_in, resp.tokens_out, resp.cost_usd
        )
    except Exception as exc:
        logger.error(
            "Parse error para {}: {} | resposta: {!r}", video.video_id, exc, resp.text[:200]
        )
        with conn:
            update_video_status(
                conn, video.video_id, VideoStatus.PROCESSING_ERROR, f"parse_error: {exc}"
            )
        return None

    new_status = VideoStatus.TRIAGE_CAPTION_PASSED if result.score >= threshold else VideoStatus.TRIAGE_CAPTION_REJECTED
    with conn:
        insert_triage_result(conn, result)
        update_video_status(conn, video.video_id, new_status)
        record_api_cost(
            conn,
            provider="anthropic" if model.startswith("claude-") else "openrouter",
            model=model,
            tokens_in=resp.tokens_in,
            tokens_out=resp.tokens_out,
            cost_usd=resp.cost_usd,
        )

    logger.info(
        "triage_caption {} | score={} | {} | themes={}",
        video.video_id,
        result.score,
        new_status,
        result.themes_detected,
    )
    return result


def run(  # noqa: C901
    llm: LLMBackend | None = None,
    conn: sqlite3.Connection | None = None,
    dry_run: bool = False,
) -> None:
    """Entry point chamado pelo CLI."""
    settings = load_settings()
    paths = get_paths(settings)

    if conn is None:
        if not paths["db_path"].exists():
            init_db(paths["db_path"], paths["schema_path"])
        conn = connect(paths["db_path"])

    model = settings.anthropic_model_triage

    if llm is None:
        llm = get_llm_backend(settings, training_conn=conn)
    canais_cfg = load_canais(paths["canais_path"])
    threshold = canais_cfg.parametros.threshold_triage_caption

    prompt_path = paths["prompts_dir"] / "triagem_caption.txt"
    criterios_path = paths["canais_path"].parent / "criterios_relevancia.md"

    if not prompt_path.exists():
        logger.error("Prompt não encontrado: {}", prompt_path)
        return

    global_prompt = prompt_path.read_text(encoding="utf-8")
    global_criterios = criterios_path.read_text(encoding="utf-8") if criterios_path.exists() else ""
    captions_dir = paths["captions_dir"]

    _canal_cache: dict[str, tuple[str, str]] = {}

    def _get_resources(target_canal_id: str) -> tuple[str, str]:
        if target_canal_id not in _canal_cache:
            oc = OutputCanal(id=target_canal_id, nome=target_canal_id)
            pt_path = resolve_prompt_path(target_canal_id, "triagem_caption")
            crit_path = resolve_criteria_path(oc)
            pt = pt_path.read_text(encoding="utf-8") if pt_path.exists() else global_prompt
            crit = crit_path.read_text(encoding="utf-8") if crit_path.exists() else global_criterios
            _canal_cache[target_canal_id] = (pt, crit)
        return _canal_cache[target_canal_id]

    videos = get_videos_by_status(conn, VideoStatus.TRIAGE_METADATA_PASSED)
    logger.info("triage_caption: {} vídeos para processar", len(videos))

    passed = rejected = skipped = errors = 0
    for video in videos:
        prompt_template, criterios = _get_resources(video.target_canal_id)
        result = triage_video_caption(
            video=video,
            conn=conn,
            llm=llm,
            model=model,
            prompt_template=prompt_template,
            criterios=criterios,
            canais_cfg=canais_cfg,
            captions_dir=captions_dir,
            threshold=threshold,
            dry_run=dry_run or settings.dry_run,
        )
        if result is None:
            # pode ser skipped (sem caption) ou dry_run ou error
            status_check = conn.execute(
                "SELECT status FROM videos WHERE video_id = ?", (video.video_id,)
            ).fetchone()
            if status_check and "skipped" in (status_check["status"] or ""):
                skipped += 1
            elif status_check and "error" in (status_check["status"] or ""):
                errors += 1
        elif result.is_relevant:
            passed += 1
        else:
            rejected += 1

    logger.info(
        "triage_caption concluído | passed={} rejected={} skipped={} errors={}",
        passed, rejected, skipped, errors,
    )
