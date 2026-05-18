"""Stage 7: identifica trechos para clipe via Claude Sonnet."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from canal_soberania.config import CanaisConfig, Parametros, get_paths, load_canais, load_settings
from canal_soberania.db import (
    connect,
    get_videos_by_status,
    init_db,
    insert_clip,
    record_api_cost,
    update_video_status,
)
from canal_soberania.llm import LLMClient, OpenRouterClient, extract_json, get_llm_client
from canal_soberania.logger import logger
from canal_soberania.models import Clip, ClipCandidate, Video


def _format_segments_seconds(segments: list[dict[str, Any]]) -> str:
    """Formata segmentos como '[start_s - end_s] texto' para o prompt de cortes."""
    lines: list[str] = []
    for seg in segments:
        start = seg["start"]
        end = seg["end"]
        text = seg["text"]
        lines.append(f"[{start:.1f} - {end:.1f}] {text}")
    return "\n".join(lines)


def _build_clips_prompt(
    template: str,
    criterios: str,
    video: Video,
    canal_nome: str,
    transcript_segmentos: str,
    params: Parametros,
) -> str:
    return template.format(
        criterios_relevancia=criterios,
        canal_nome=canal_nome,
        title=video.title,
        transcript_segmentos=transcript_segmentos,
        max_clipes=params.max_clipes_por_video,
        min_clipes=3,
        dur_min=params.clip_duracao_min,
        dur_max=params.clip_duracao_max,
        dur_ideal=params.clip_duracao_ideal,
    )


def _parse_clips_response(
    raw: str,
    video_id: str,
    params: Parametros,
) -> list[ClipCandidate]:
    """Extrai e valida candidatos a clipe da resposta do LLM."""
    data = extract_json(raw)
    raw_clips = data.get("clips", [])
    if not isinstance(raw_clips, list):
        raise ValueError(f"'clips' não é lista: {type(raw_clips)}")

    candidates: list[ClipCandidate] = []
    for item in raw_clips:
        try:
            candidate = ClipCandidate.model_validate(item)
        except Exception as exc:
            logger.warning("Clip inválido ignorado para {}: {}", video_id, exc)
            continue

        duracao = candidate.end_s - candidate.start_s
        if not (params.clip_duracao_min <= duracao <= params.clip_duracao_max):
            logger.debug(
                "Clip fora da duração ({:.0f}s) — ignorado para {}",
                duracao,
                video_id,
            )
            continue

        if candidate.score_viral < 6 or candidate.score_relevancia < 6:
            logger.debug(
                "Clip com scores baixos ({}/{}) — ignorado para {}",
                candidate.score_viral,
                candidate.score_relevancia,
                video_id,
            )
            continue

        candidates.append(candidate)

    return candidates[: params.max_clipes_por_video]


def find_clips_for_video(
    video: Video,
    conn: sqlite3.Connection,
    llm: LLMClient | OpenRouterClient,
    model: str,
    prompt_template: str,
    criterios: str,
    canais_cfg: CanaisConfig,
    dry_run: bool = False,
) -> list[Clip]:
    """
    Identifica clipes para um vídeo. Retorna lista de Clips inseridos (pode ser vazia).
    Em dry_run, retorna candidatos sem inserir no banco.
    """
    if not video.transcript_path:
        logger.error("transcript_path vazio para {} — pulando", video.video_id)
        return []

    transcript_file = Path(video.transcript_path)
    if not transcript_file.exists():
        logger.error("Transcript não encontrado: {}", transcript_file)
        with conn:
            update_video_status(
                conn, video.video_id, "processing_error", "transcript_file_missing"
            )
        return []

    data = json.loads(transcript_file.read_text(encoding="utf-8"))
    segments: list[dict[str, Any]] = data.get("segments", [])

    canal = next((c for c in canais_cfg.canais if c.id == video.canal_id), None)
    canal_nome = canal.nome if canal else video.canal_id
    params = canais_cfg.parametros

    transcript_segmentos = _format_segments_seconds(segments)
    prompt = _build_clips_prompt(
        prompt_template, criterios, video, canal_nome, transcript_segmentos, params
    )

    if dry_run:
        logger.info(
            "[dry-run] find_clips {} | segs={} | prompt_len={}",
            video.video_id,
            len(segments),
            len(prompt),
        )
        return []

    # Guard de idempotência: evita chamar LLM se clips já foram identificados
    existing_count = conn.execute(
        "SELECT COUNT(*) AS n FROM clips WHERE video_id = ?", (video.video_id,)
    ).fetchone()
    if existing_count and existing_count["n"] > 0:
        logger.info(
            "find_clips: {} já tem {} clips identificados, pulando LLM",
            video.video_id, existing_count["n"],
        )
        with conn:
            update_video_status(conn, video.video_id, "clips_found")
        return []

    with conn:
        update_video_status(conn, video.video_id, "finding_clips")

    try:
        resp = llm.complete(prompt, model=model, max_tokens=2048, task="find_clips")
    except Exception as exc:
        logger.error("LLM error para {}: {}", video.video_id, exc)
        with conn:
            update_video_status(conn, video.video_id, "processing_error", str(exc))
        return []

    try:
        candidates = _parse_clips_response(resp.text, video.video_id, params)
    except Exception as exc:
        logger.error(
            "Parse error para {}: {} | resposta: {!r}", video.video_id, exc, resp.text[:300]
        )
        with conn:
            update_video_status(
                conn, video.video_id, "processing_error", f"parse_clips_error: {exc}"
            )
        return []

    clips: list[Clip] = []
    for candidate in candidates:
        clip_id = f"{video.video_id}_{int(candidate.start_s)}_{int(candidate.end_s)}"
        clip = Clip(
            clip_id=clip_id,
            video_id=video.video_id,
            start_s=candidate.start_s,
            end_s=candidate.end_s,
            hook=candidate.hook,
            payoff=candidate.payoff,
            tema_soberania=candidate.tema_soberania,
            score_viral=candidate.score_viral,
            score_relevancia=candidate.score_relevancia,
            justificativa=candidate.justificativa,
        )
        clips.append(clip)

    with conn:
        for clip in clips:
            insert_clip(conn, clip)
        update_video_status(conn, video.video_id, "clips_found")
        record_api_cost(
            conn,
            provider="anthropic" if model.startswith("claude-") else "openrouter",
            model=model,
            tokens_in=resp.tokens_in,
            tokens_out=resp.tokens_out,
            cost_usd=resp.cost_usd,
        )

    logger.info(
        "find_clips {} | clipes={} | custo=${:.4f}",
        video.video_id,
        len(clips),
        resp.cost_usd,
    )
    return clips


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
            logger.error("{} não configurada — abortando find_clips", key_name)
            return
        llm = get_llm_client(model, settings, training_conn=conn)
    canais_cfg = load_canais(paths["canais_path"])

    prompt_path = paths["prompts_dir"] / "identificar_cortes.txt"
    criterios_path = paths["canais_path"].parent / "criterios_relevancia.md"

    if not prompt_path.exists():
        logger.error("Prompt não encontrado: {}", prompt_path)
        return

    prompt_template = prompt_path.read_text(encoding="utf-8")
    criterios = criterios_path.read_text(encoding="utf-8") if criterios_path.exists() else ""

    # Inclui "finding_clips" para recuperar orphans de crash mid-LLM
    videos = get_videos_by_status(conn, "approved_for_clips") + get_videos_by_status(conn, "finding_clips")
    logger.info("find_clips: {} vídeos para processar", len(videos))

    total_clips = 0
    for video in videos:
        clips = find_clips_for_video(
            video=video,
            conn=conn,
            llm=llm,
            model=model,
            prompt_template=prompt_template,
            criterios=criterios,
            canais_cfg=canais_cfg,
            dry_run=dry_run or settings.dry_run,
        )
        total_clips += len(clips)

    logger.info("find_clips concluído | total_clipes={}", total_clips)
