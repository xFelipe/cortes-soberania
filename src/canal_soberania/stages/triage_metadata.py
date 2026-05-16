"""Stage 2: triagem por metadados (título, descrição, tags, comentários) via Claude Haiku."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from canal_soberania.config import CanaisConfig, get_paths, load_canais, load_settings
from canal_soberania.db import (
    connect,
    get_videos_by_status,
    init_db,
    insert_triage_result,
    record_api_cost,
    update_video_status,
)
from canal_soberania.llm import LLMClient, extract_json
from canal_soberania.logger import logger
from canal_soberania.models import TriageResult, Video


def _fetch_top_comments(youtube: Any, video_id: str, max_results: int = 20) -> list[str]:
    """Retorna os top comentários de um vídeo. Retorna lista vazia se desabilitados."""
    try:
        resp = (
            youtube.commentThreads()
            .list(
                part="snippet",
                videoId=video_id,
                maxResults=max_results,
                order="relevance",
                textFormat="plainText",
            )
            .execute()
        )
    except Exception as exc:
        # Comentários desabilitados ou erro de API — não é fatal
        logger.debug("Comentários indisponíveis para {}: {}", video_id, exc)
        return []

    comments: list[str] = []
    for item in resp.get("items", []):
        text = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
        comments.append(text.strip())
    return comments


def _build_prompt(
    template: str,
    criterios: str,
    video: Video,
    canal_nome: str,
    canal_tema: str,
    comentarios: list[str],
) -> str:
    tags_str = ", ".join(video.tags) if video.tags else "(sem tags)"
    comentarios_str = (
        "\n".join(f"- {c[:200]}" for c in comentarios[:20])
        if comentarios
        else "(sem comentários disponíveis)"
    )
    return template.format(
        criterios_relevancia=criterios,
        canal_nome=canal_nome,
        canal_tema=canal_tema,
        title=video.title,
        description=(video.description or "")[:2000],
        tags=tags_str,
        comentarios=comentarios_str,
    )


def _parse_triage_response(
    raw: str, video_id: str, model: str, tokens_in: int, tokens_out: int, cost_usd: float
) -> TriageResult:
    data = extract_json(raw)
    score = int(data.get("score", 0))
    is_relevant = bool(data.get("is_relevant", score >= 5))
    themes = [str(t) for t in data.get("themes_detected", [])]
    rationale = str(data.get("rationale", ""))
    return TriageResult(
        video_id=video_id,
        stage="metadata",
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


def triage_video_metadata(
    video: Video,
    conn: sqlite3.Connection,
    llm: LLMClient,
    model: str,
    prompt_template: str,
    criterios: str,
    canais_cfg: CanaisConfig,
    youtube: Any | None = None,
    threshold: int = 5,
    dry_run: bool = False,
) -> TriageResult | None:
    """Roda triagem de metadados em um vídeo. Retorna TriageResult ou None em caso de erro."""
    canal = next((c for c in canais_cfg.canais if c.id == video.canal_id), None)
    canal_nome = canal.nome if canal else video.canal_id
    canal_tema = canal.tema_primario if canal else "desconhecido"

    comentarios: list[str] = []
    if youtube is not None:
        comentarios = _fetch_top_comments(youtube, video.video_id)

    prompt = _build_prompt(
        prompt_template, criterios, video, canal_nome, canal_tema, comentarios
    )

    if dry_run:
        logger.info(
            "[dry-run] triage_metadata {} | prompt_len={}", video.video_id, len(prompt)
        )
        return None

    try:
        resp = llm.complete(prompt, model=model, max_tokens=512, task="triage_metadata")
    except Exception as exc:
        logger.error("LLM error para {}: {}", video.video_id, exc)
        with conn:
            update_video_status(conn, video.video_id, "processing_error", str(exc))
        return None

    try:
        result = _parse_triage_response(
            resp.text, video.video_id, resp.model, resp.tokens_in, resp.tokens_out, resp.cost_usd
        )
    except Exception as exc:
        logger.error("Parse error para {}: {} | resposta: {!r}", video.video_id, exc, resp.text[:200])
        with conn:
            update_video_status(conn, video.video_id, "processing_error", f"parse_error: {exc}")
        return None

    new_status = (
        "triage_metadata_passed" if result.score >= threshold else "triage_metadata_rejected"
    )
    with conn:
        insert_triage_result(conn, result)
        update_video_status(conn, video.video_id, new_status)
        record_api_cost(
            conn,
            provider="anthropic",
            model=model,
            tokens_in=resp.tokens_in,
            tokens_out=resp.tokens_out,
            cost_usd=resp.cost_usd,
        )

    logger.info(
        "triage_metadata {} | score={} | {} | themes={}",
        video.video_id,
        result.score,
        new_status,
        result.themes_detected,
    )
    return result


def run(
    llm: LLMClient | None = None,
    conn: sqlite3.Connection | None = None,
    youtube: Any | None = None,
    dry_run: bool = False,
) -> None:
    """Entry point chamado pelo CLI."""
    settings = load_settings()
    paths = get_paths(settings)

    if conn is None:
        if not paths["db_path"].exists():
            init_db(paths["db_path"], paths["schema_path"])
        conn = connect(paths["db_path"])

    if not settings.anthropic_api_key and llm is None:
        logger.error("ANTHROPIC_API_KEY não configurada — abortando triage_metadata")
        return

    if llm is None:
        llm = LLMClient(api_key=settings.anthropic_api_key, training_conn=conn)

    model = settings.anthropic_model_triage
    canais_cfg = load_canais(paths["canais_path"])
    threshold = canais_cfg.parametros.threshold_triage_metadata

    prompt_path = paths["prompts_dir"] / "triagem_metadata.txt"
    criterios_path = paths["canais_path"].parent / "criterios_relevancia.md"

    if not prompt_path.exists():
        logger.error("Prompt não encontrado: {}", prompt_path)
        return

    prompt_template = prompt_path.read_text(encoding="utf-8")
    criterios = criterios_path.read_text(encoding="utf-8") if criterios_path.exists() else ""

    if youtube is None and settings.youtube_api_key:
        try:
            from googleapiclient.discovery import build  # type: ignore[import-untyped]

            youtube = build("youtube", "v3", developerKey=settings.youtube_api_key)
        except Exception as exc:
            logger.warning("Não foi possível inicializar YouTube API: {}", exc)

    videos = get_videos_by_status(conn, "discovered")
    logger.info("triage_metadata: {} vídeos para processar", len(videos))

    passed = rejected = errors = 0
    for video in videos:
        result = triage_video_metadata(
            video=video,
            conn=conn,
            llm=llm,
            model=model,
            prompt_template=prompt_template,
            criterios=criterios,
            canais_cfg=canais_cfg,
            youtube=youtube,
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
        "triage_metadata concluído | passed={} rejected={} errors={}",
        passed,
        rejected,
        errors,
    )
