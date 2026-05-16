"""Entry point Typer — `cs` CLI."""

from __future__ import annotations

import sqlite3
from enum import StrEnum
from typing import Annotated

import typer

from canal_soberania.config import get_paths, load_settings
from canal_soberania.db import init_db, monthly_cost, status_summary
from canal_soberania.logger import logger, setup_logger

app = typer.Typer(
    name="cs",
    help="Canal Soberania — pipeline de cortes automatizado.",
    no_args_is_help=True,
)

_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("DB não inicializado — chame o callback principal primeiro")
    return _conn


@app.callback()  # type: ignore[untyped-decorator]
def main(
    ctx: typer.Context,
    log_level: Annotated[str, typer.Option("--log-level", help="DEBUG|INFO|WARNING|ERROR")] = "",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Não executa side effects")] = False,
) -> None:
    global _conn
    settings = load_settings()
    if log_level:
        settings = settings.model_copy(update={"log_level": log_level})
    if dry_run:
        settings = settings.model_copy(update={"dry_run": True})

    paths = get_paths(settings)
    setup_logger(paths["log_dir"], settings.log_level)

    db_path = paths["db_path"]
    schema_path = paths["schema_path"]
    if not db_path.exists():
        logger.info("Banco não encontrado — inicializando em {}", db_path)
        init_db(db_path, schema_path)

    from canal_soberania.db import connect

    _conn = connect(db_path)

    ctx.ensure_object(dict)
    ctx.obj["settings"] = settings
    ctx.obj["paths"] = paths
    ctx.obj["conn"] = _conn


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@app.command()  # type: ignore[untyped-decorator]
def status(
    ctx: typer.Context,
    video_id: Annotated[str | None, typer.Option("--video-id", help="Detalhe de um vídeo")] = None,
) -> None:
    """Mostra contagem por status e custo do mês."""
    conn: sqlite3.Connection = ctx.obj["conn"]

    if video_id:
        row = conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        if row is None:
            typer.echo(f"Vídeo não encontrado: {video_id}")
            raise typer.Exit(1)
        for key in row:
            typer.echo(f"  {key}: {row[key]}")
        return

    summary = status_summary(conn)
    if not summary:
        typer.echo("Banco vazio — rode `cs discover` primeiro.")
        return

    typer.echo("\nStatus dos vídeos:")
    for s, total in sorted(summary.items(), key=lambda x: -x[1]):
        typer.echo(f"  {s:<40} {total:>5}")

    cost = monthly_cost(conn)
    typer.echo(f"\nCusto este mês: ${cost:.4f} USD")


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------


@app.command()  # type: ignore[untyped-decorator]
def discover(
    ctx: typer.Context,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Busca vídeos novos nos canais monitorados."""
    from canal_soberania.stages.discover import run as discover_run

    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    discover_run(conn=ctx.obj["conn"], dry_run=effective_dry_run)


# ---------------------------------------------------------------------------
# triage
# ---------------------------------------------------------------------------


class TriageStage(StrEnum):
    metadata = "metadata"
    caption = "caption"
    transcript = "transcript"


@app.command()  # type: ignore[untyped-decorator]
def triage(
    ctx: typer.Context,
    stage: Annotated[TriageStage, typer.Option("--stage", help="metadata|caption|transcript")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Roda uma etapa de triagem sobre vídeos pendentes."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    conn = ctx.obj["conn"]

    if stage == TriageStage.metadata:
        from canal_soberania.stages.triage_metadata import run as triage_metadata_run

        triage_metadata_run(conn=conn, dry_run=effective_dry_run)
    elif stage == TriageStage.caption:
        from canal_soberania.stages.triage_caption import run as triage_caption_run

        triage_caption_run(conn=conn, dry_run=effective_dry_run)
    else:
        logger.info("TODO: triage stage={}", stage.value)
        typer.echo(f"triage --stage {stage.value}: não implementado")


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------


@app.command()  # type: ignore[untyped-decorator]
def download(
    ctx: typer.Context,
    pending: Annotated[bool, typer.Option("--pending")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Baixa áudio/vídeo dos itens aprovados na triagem."""
    from canal_soberania.stages.download import run as download_run

    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    download_run(conn=ctx.obj["conn"], dry_run=effective_dry_run)


# ---------------------------------------------------------------------------
# transcribe
# ---------------------------------------------------------------------------


@app.command()  # type: ignore[untyped-decorator]
def transcribe(
    ctx: typer.Context,
    pending: Annotated[bool, typer.Option("--pending")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Transcreve áudio com faster-whisper."""
    from canal_soberania.stages.transcribe import run as transcribe_run

    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    transcribe_run(conn=ctx.obj["conn"], dry_run=effective_dry_run)


# ---------------------------------------------------------------------------
# find-clips
# ---------------------------------------------------------------------------


@app.command(name="find-clips")  # type: ignore[untyped-decorator]
def find_clips(
    ctx: typer.Context,
    pending: Annotated[bool, typer.Option("--pending")] = True,
) -> None:
    """Identifica trechos para clipe via Claude Sonnet."""
    logger.info("TODO: stages/find_clips.py não implementado ainda")
    typer.echo("find-clips: não implementado")


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------


@app.command()  # type: ignore[untyped-decorator]
def edit(
    ctx: typer.Context,
    pending: Annotated[bool, typer.Option("--pending")] = True,
) -> None:
    """Edita clipes: corte, reframe 9:16, legendas, intro/outro."""
    logger.info("TODO: stages/edit.py não implementado ainda")
    typer.echo("edit: não implementado")


# ---------------------------------------------------------------------------
# thumbnail
# ---------------------------------------------------------------------------


@app.command()  # type: ignore[untyped-decorator]
def thumbnail(
    ctx: typer.Context,
    pending: Annotated[bool, typer.Option("--pending")] = True,
) -> None:
    """Gera thumbnail com Pillow."""
    logger.info("TODO: stages/thumbnail.py não implementado ainda")
    typer.echo("thumbnail: não implementado")


# ---------------------------------------------------------------------------
# metadata
# ---------------------------------------------------------------------------


@app.command()  # type: ignore[untyped-decorator]
def metadata(
    ctx: typer.Context,
    pending: Annotated[bool, typer.Option("--pending")] = True,
) -> None:
    """Gera título/descrição/tags com Claude Sonnet."""
    logger.info("TODO: stages/metadata.py não implementado ainda")
    typer.echo("metadata: não implementado")


# ---------------------------------------------------------------------------
# upload
# ---------------------------------------------------------------------------


class Platform(StrEnum):
    youtube = "youtube"
    tiktok = "tiktok"


@app.command()  # type: ignore[untyped-decorator]
def upload(
    ctx: typer.Context,
    platform: Annotated[Platform, typer.Option("--platform", help="youtube|tiktok")],
    pending: Annotated[bool, typer.Option("--pending")] = True,
) -> None:
    """Sobe clipes para a plataforma especificada."""
    logger.info("TODO: stages/upload_{}.py não implementado ainda", platform.value)
    typer.echo(f"upload --platform {platform.value}: não implementado")


if __name__ == "__main__":
    app()
