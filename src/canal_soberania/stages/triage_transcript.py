"""Stage 6: triagem final com Claude Sonnet sobre o transcript completo (Whisper)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from canal_soberania.config import CanaisConfig, get_paths, load_canais, load_settings
from canal_soberania.db import (
    connect,
    get_videos_by_status,
    init_db,
    insert_triage_result,
    record_api_cost,
    update_video_status,
)
from canal_soberania.llm import LLMClient, OpenRouterClient, extract_json, get_llm_client
from canal_soberania.logger import logger
from canal_soberania.models import TriageResult, Video
from canal_soberania.stages.transcribe import format_segments_for_prompt


def _load_transcript_segments(transcript_path: str) -> list[dict[str, object]]:
    data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    return list(data.get("segments", []))


def _build_transcript_prompt(
    template: str,
    criterios: str,
    video: Video,
    canal_nome: str,
    transcript_segmentos: str,
) -> str:
    duracao_min = str(round(video.duration_s / 60)) if video.duration_s else "?"
    return template.format(
        criterios_relevancia=criterios,
        canal_nome=canal_nome,
        title=video.title,
        duracao_min=duracao_min,
        transcript_segmentos=transcript_segmentos,
    )


def _parse_transcript_response(
    raw: str,
    video_id: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
) -> TriageResult:
    data = extract_json(raw)
    score = int(data.get("score", 0))
    is_relevant = bool(data.get("is_relevant", score >= 7))
    themes = [str(t) for t in data.get("themes_detected", [])]
    rationale = str(data.get("rationale", ""))
    return TriageResult(
        video_id=video_id,
        stage="transcript",
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


def triage_video_transcript(
    video: Video,
    conn: sqlite3.Connection,
    llm: LLMClient | OpenRouterClient,
    model: str,
    prompt_template: str,
    criterios: str,
    canais_cfg: CanaisConfig,
    threshold: int = 7,
    dry_run: bool = False,
) -> TriageResult | None:
    """
    Triagem final com transcript completo.
    - sem transcript → processing_error
    - score >= threshold → 'triage_transcript_passed'
    - senão → 'triage_transcript_rejected'
    """
    if not video.transcript_path:
        logger.error("transcript_path vazio para {} — pulando", video.video_id)
        return None

    if not Path(video.transcript_path).exists():
        logger.error("Arquivo de transcript não encontrado: {}", video.transcript_path)
        with conn:
            update_video_status(
                conn, video.video_id, "processing_error", "transcript_file_missing"
            )
        return None

    canal = next((c for c in canais_cfg.canais if c.id == video.canal_id), None)
    canal_nome = canal.nome if canal else video.canal_id

    segments = _load_transcript_segments(video.transcript_path)
    transcript_segmentos = format_segments_for_prompt(segments)

    prompt = _build_transcript_prompt(
        prompt_template, criterios, video, canal_nome, transcript_segmentos
    )

    if dry_run:
        logger.info(
            "[dry-run] triage_transcript {} | segs={} | prompt_len={}",
            video.video_id,
            len(segments),
            len(prompt),
        )
        return None

    try:
        resp = llm.complete(prompt, model=model, max_tokens=1024, task="triage_transcript")
    except Exception as exc:
        logger.error("LLM error para {}: {}", video.video_id, exc)
        with conn:
            update_video_status(conn, video.video_id, "processing_error", str(exc))
        return None

    try:
        result = _parse_transcript_response(
            resp.text, video.video_id, resp.model,
            resp.tokens_in, resp.tokens_out, resp.cost_usd
        )
    except Exception as exc:
        logger.error(
            "Parse error para {}: {} | resposta: {!r}", video.video_id, exc, resp.text[:200]
        )
        with conn:
            update_video_status(
                conn, video.video_id, "processing_error", f"parse_error: {exc}"
            )
        return None

    new_status = (
        "triage_transcript_passed" if result.score >= threshold else "triage_transcript_rejected"
    )
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
        "triage_transcript {} | score={} | {} | themes={}",
        video.video_id,
        result.score,
        new_status,
        result.themes_detected,
    )
    return result


def run(
    llm: LLMClient | OpenRouterClient | None = None,
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

    model = settings.anthropic_model_deep

    if llm is None:
        required_key = settings.anthropic_api_key if model.startswith("claude-") else settings.openrouter_api_key
        if not required_key:
            key_name = "ANTHROPIC_API_KEY" if model.startswith("claude-") else "OPENROUTER_API_KEY"
            logger.error("{} não configurada — abortando triage_transcript", key_name)
            return
        llm = get_llm_client(model, settings, training_conn=conn)
    canais_cfg = load_canais(paths["canais_path"])
    threshold = canais_cfg.parametros.threshold_triage_transcript

    prompt_path = paths["prompts_dir"] / "triagem_transcript.txt"
    criterios_path = paths["canais_path"].parent / "criterios_relevancia.md"

    if not prompt_path.exists():
        logger.error("Prompt não encontrado: {}", prompt_path)
        return

    prompt_template = prompt_path.read_text(encoding="utf-8")
    criterios = criterios_path.read_text(encoding="utf-8") if criterios_path.exists() else ""

    videos = get_videos_by_status(conn, "transcribed")
    logger.info("triage_transcript: {} vídeos para processar", len(videos))

    passed = rejected = errors = 0
    for video in videos:
        result = triage_video_transcript(
            video=video,
            conn=conn,
            llm=llm,
            model=model,
            prompt_template=prompt_template,
            criterios=criterios,
            canais_cfg=canais_cfg,
            threshold=threshold,
            dry_run=dry_run or settings.dry_run,
        )
        if result is None:
            if not (dry_run or settings.dry_run):
                errors += 1
        elif result.is_relevant:
            passed += 1
        else:
            rejected += 1

    logger.info(
        "triage_transcript concluído | passed={} rejected={} errors={}",
        passed, rejected, errors,
    )
