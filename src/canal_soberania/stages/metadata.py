"""Stage 10: gera título, descrição e tags para o clipe via Claude Sonnet."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, cast

from canal_soberania.config import CanaisConfig, get_paths, load_canais, load_settings
from canal_soberania.db import connect, get_clips_by_status, init_db, record_api_cost
from canal_soberania.llm import extract_json
from canal_soberania.llm_backends import LLMBackend, get_llm_backend
from canal_soberania.logger import logger
from canal_soberania.models import Clip, ClipStatus

_INPUT_STATUS: ClipStatus = ClipStatus.THUMBNAIL_READY


def _load_clip_transcript(
    clip: Clip,
    conn: sqlite3.Connection,
    transcripts_dir: Path,
) -> str:
    """Retorna a transcrição do intervalo do clipe formatada como texto simples."""
    row = conn.execute(
        "SELECT transcript_path FROM videos WHERE video_id = ?",
        (clip.video_id,),
    ).fetchone()

    if not row or not row["transcript_path"]:
        return ""

    transcript_path = Path(row["transcript_path"])
    if not transcript_path.exists():
        return ""

    data = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments: list[dict[str, Any]] = data.get("segments", [])

    lines: list[str] = []
    for seg in segments:
        start: float = seg.get("start", 0)
        end: float = seg.get("end", 0)
        if end < clip.start_s or start > clip.end_s:
            continue
        lines.append(seg.get("text", "").strip())

    return " ".join(lines)


def _build_metadata_prompt(
    template: str,
    clip: Clip,
    canal_fonte_nome: str,
    canal_fonte_handle: str,
    video_title: str,
    video_url: str,
    clip_transcript: str,
) -> str:
    return template.format(
        canal_fonte_nome=canal_fonte_nome,
        canal_fonte_handle=canal_fonte_handle,
        video_url=video_url,
        video_title=video_title,
        duracao_s=int(clip.end_s - clip.start_s),
        hook=clip.hook or "",
        payoff=clip.payoff or "",
        tema_soberania=clip.tema_soberania or "",
        clip_transcript=clip_transcript or "(transcrição indisponível)",
    )


def generate_metadata_for_clip(
    clip: Clip,
    conn: sqlite3.Connection,
    llm: LLMBackend,
    model: str,
    prompt_template: str,
    canais_cfg: CanaisConfig,
    transcripts_dir: Path,
    dry_run: bool = False,
) -> bool:
    """
    Gera título/descrição/tags para o clipe. Retorna True se bem-sucedido.
    Atualiza clips.title, clips.description, clips.tags e status='metadata_ready'.
    """
    row = conn.execute(
        "SELECT v.video_id, v.title, v.canal_id FROM videos v WHERE v.video_id = ?",
        (clip.video_id,),
    ).fetchone()

    if not row:
        logger.warning("Vídeo {} não encontrado para clipe {}", clip.video_id, clip.clip_id)
        return False

    canal_id: str = row["canal_id"]
    video_title: str = row["title"]
    video_url = f"https://www.youtube.com/watch?v={clip.video_id}"

    canal_cfg = next(
        (c for c in canais_cfg.canais if c.id == canal_id),
        None,
    )
    canal_fonte_nome = canal_cfg.nome if canal_cfg else canal_id
    canal_fonte_handle = canal_cfg.handle if canal_cfg else ""

    clip_transcript = _load_clip_transcript(clip, conn, transcripts_dir)

    if dry_run:
        logger.info("[dry-run] metadata clip={}", clip.clip_id)
        return True

    # Guard de idempotência: evita chamar LLM se título e descrição já gerados
    if clip.title and clip.description:
        logger.info("metadata: clip {} já tem título/descrição, pulando LLM", clip.clip_id)
        with conn:
            conn.execute(
                f"UPDATE clips SET status='{ClipStatus.METADATA_READY}' WHERE clip_id=? AND status != '{ClipStatus.METADATA_READY}'",  # noqa: S608
                (clip.clip_id,),
            )
        return True

    prompt = _build_metadata_prompt(
        template=prompt_template,
        clip=clip,
        canal_fonte_nome=canal_fonte_nome,
        canal_fonte_handle=canal_fonte_handle,
        video_title=video_title,
        video_url=video_url,
        clip_transcript=clip_transcript,
    )

    resp = llm.complete(prompt=prompt, model=model, task="metadata")
    record_api_cost(
        conn,
        provider="anthropic" if model.startswith("claude-") else "openrouter",
        model=model,
        tokens_in=resp.tokens_in,
        tokens_out=resp.tokens_out,
        cost_usd=resp.cost_usd,
    )

    try:
        parsed = extract_json(resp.text)
    except ValueError:
        parsed = {}
    if not parsed:
        logger.warning("metadata: resposta inválida para clip={}: {!r}", clip.clip_id, resp.text[:200])
        return False

    title: str = str(parsed.get("title", ""))[:60]
    description: str = str(parsed.get("description", ""))
    tags_raw = cast(list[object], parsed.get("tags", []))
    tags: list[str] = [str(t) for t in tags_raw if t][:15]

    if not title:
        logger.warning("metadata: título vazio para clip={}", clip.clip_id)
        return False

    with conn:
        conn.execute(
            "UPDATE clips SET title=?, description=?, tags=?, status='metadata_ready' WHERE clip_id=?",
            (title, description, json.dumps(tags, ensure_ascii=False), clip.clip_id),
        )

    logger.info("metadata gerado: clip={} title={!r}", clip.clip_id, title)
    return True


def run(
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

    canais_cfg = load_canais(paths["canais_path"])
    model = settings.anthropic_model_deep
    llm = get_llm_backend(settings, training_conn=conn)

    prompt_path = paths["prompts_dir"] / "gerar_metadata_clip.txt"
    if not prompt_path.exists():
        logger.error("Prompt não encontrado: {}", prompt_path)
        return
    prompt_template = prompt_path.read_text(encoding="utf-8")

    clips = get_clips_by_status(conn, _INPUT_STATUS)
    logger.info("metadata: {} clipes para processar", len(clips))

    success = failed = 0
    for clip in clips:
        ok = generate_metadata_for_clip(
            clip=clip,
            conn=conn,
            llm=llm,
            model=model,
            prompt_template=prompt_template,
            canais_cfg=canais_cfg,
            transcripts_dir=paths["transcripts_dir"],
            dry_run=dry_run or settings.dry_run,
        )
        if ok:
            success += 1
        else:
            failed += 1

    logger.info("metadata concluído | ok={} falhas={}", success, failed)
