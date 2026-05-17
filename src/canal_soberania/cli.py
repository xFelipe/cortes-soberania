"""Entry point Typer — `cs` CLI."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from canal_soberania.config import ensure_data_dirs, get_paths, load_settings
from canal_soberania.db import init_db
from canal_soberania.logger import logger, setup_logger
from canal_soberania.services.pipeline_service import PipelineService

app = typer.Typer(
    name="cs",
    help="Canal Soberania — pipeline de cortes automatizado.",
    no_args_is_help=True,
)


@app.callback()  # type: ignore[untyped-decorator]
def main(
    ctx: typer.Context,
    log_level: Annotated[str, typer.Option("--log-level", help="DEBUG|INFO|WARNING|ERROR")] = "",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Não executa side effects")] = False,
) -> None:
    settings = load_settings()
    if log_level:
        settings = settings.model_copy(update={"log_level": log_level})
    if dry_run:
        settings = settings.model_copy(update={"dry_run": True})

    paths = get_paths(settings)
    ensure_data_dirs(paths)
    setup_logger(paths["log_dir"], settings.log_level)

    db_path = paths["db_path"]
    schema_path = paths["schema_path"]
    if not db_path.exists():
        logger.info("Banco não encontrado — inicializando em {}", db_path)
        init_db(db_path, schema_path)

    from canal_soberania.db import connect

    conn = connect(db_path)
    service = PipelineService(conn=conn, settings=settings, paths=paths)

    ctx.ensure_object(dict)
    ctx.obj["settings"] = settings
    ctx.obj["paths"] = paths
    ctx.obj["conn"] = conn
    ctx.obj["service"] = service


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@app.command()  # type: ignore[untyped-decorator]
def status(
    ctx: typer.Context,
    video_id: Annotated[str | None, typer.Option("--video-id", help="Detalhe de um vídeo")] = None,
) -> None:
    """Mostra contagem por status e custo do mês."""
    service: PipelineService = ctx.obj["service"]

    if video_id:
        video = service.get_video(video_id)
        if video is None:
            typer.echo(f"Vídeo não encontrado: {video_id}")
            raise typer.Exit(1)
        for key, val in video.model_dump().items():
            typer.echo(f"  {key}: {val}")
        return

    summary = service.get_status_summary()
    if not summary:
        typer.echo("Banco vazio — rode `cs discover` primeiro.")
        return

    typer.echo("\nStatus dos vídeos:")
    for s, total in sorted(summary.items(), key=lambda x: -x[1]):
        typer.echo(f"  {s:<40} {total:>5}")

    cost = service.get_monthly_cost()
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
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    ctx.obj["service"].run_discover(dry_run=effective_dry_run)


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
    service: PipelineService = ctx.obj["service"]

    if stage == TriageStage.metadata:
        service.run_triage_metadata(dry_run=effective_dry_run)
    elif stage == TriageStage.caption:
        service.run_triage_caption(dry_run=effective_dry_run)
    elif stage == TriageStage.transcript:
        service.run_triage_transcript(dry_run=effective_dry_run)
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
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    ctx.obj["service"].run_download(dry_run=effective_dry_run)


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
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    ctx.obj["service"].run_transcribe(dry_run=effective_dry_run)


# ---------------------------------------------------------------------------
# find-clips
# ---------------------------------------------------------------------------


@app.command(name="find-clips")  # type: ignore[untyped-decorator]
def find_clips(
    ctx: typer.Context,
    pending: Annotated[bool, typer.Option("--pending")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Identifica trechos para clipe via Claude Sonnet."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    ctx.obj["service"].run_find_clips(dry_run=effective_dry_run)


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------


@app.command()  # type: ignore[untyped-decorator]
def edit(
    ctx: typer.Context,
    pending: Annotated[bool, typer.Option("--pending")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Edita clipes: corte, reframe 9:16, legendas, intro/outro."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    ctx.obj["service"].run_edit(dry_run=effective_dry_run)


# ---------------------------------------------------------------------------
# thumbnail
# ---------------------------------------------------------------------------


@app.command()  # type: ignore[untyped-decorator]
def thumbnail(
    ctx: typer.Context,
    pending: Annotated[bool, typer.Option("--pending")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Gera thumbnail com Pillow."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    ctx.obj["service"].run_thumbnail(dry_run=effective_dry_run)


# ---------------------------------------------------------------------------
# metadata
# ---------------------------------------------------------------------------


@app.command()  # type: ignore[untyped-decorator]
def metadata(
    ctx: typer.Context,
    pending: Annotated[bool, typer.Option("--pending")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Gera título/descrição/tags com Claude Sonnet."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    ctx.obj["service"].run_generate_metadata(dry_run=effective_dry_run)


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
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Sobe clipes para a plataforma especificada."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    service: PipelineService = ctx.obj["service"]

    if platform == Platform.youtube:
        service.run_upload_youtube(dry_run=effective_dry_run)
    elif platform == Platform.tiktok:
        service.run_upload_tiktok(dry_run=effective_dry_run)


# ---------------------------------------------------------------------------
# training
# ---------------------------------------------------------------------------


@app.command(name="training-stats")  # type: ignore[untyped-decorator]
def training_stats(ctx: typer.Context) -> None:
    """Mostra contagem de exemplos de treino por task e status de curadoria."""
    from canal_soberania.db import training_stats as _training_stats

    stats = _training_stats(ctx.obj["conn"])
    if not stats:
        typer.echo("Nenhum exemplo registrado ainda. Rode o pipeline com ANTHROPIC_API_KEY.")
        return

    typer.echo(f"\n{'Task':<25} {'Total':>7} {'Aprovado':>9} {'Rejeitado':>10} {'Não curado':>11}")
    typer.echo("-" * 65)
    for task, counts in sorted(stats.items()):
        typer.echo(
            f"{task:<25} {counts['total']:>7} {counts['approved']:>9} "
            f"{counts['rejected']:>10} {counts['uncurated']:>11}"
        )


@app.command(name="export-training")  # type: ignore[untyped-decorator]
def export_training(
    ctx: typer.Context,
    task: Annotated[str | None, typer.Option("--task", help="Filtrar por task específica")] = None,
    all_examples: Annotated[bool, typer.Option("--all", help="Exportar todos (sem curar)")] = False,
    output: Annotated[str, typer.Option("--output", help="Arquivo de saída (.jsonl)")] = "",
) -> None:
    """Exporta exemplos de treino em formato ChatML (JSONL) para fine-tuning."""
    from canal_soberania.db import export_training_jsonl
    from canal_soberania.config import get_paths

    paths = get_paths(ctx.obj["settings"])
    approved_only = not all_examples

    if not output:
        suffix = f"_{task}" if task else "_all"
        output = str(paths["data_dir"] / "training" / f"export{suffix}.jsonl")

    out_path = Path(output)
    n = export_training_jsonl(
        conn=ctx.obj["conn"],
        output_path=out_path,
        task=task,
        approved_only=approved_only,
    )

    if n == 0:
        flag = "aprovados" if approved_only else "totais"
        typer.echo(f"Nenhum exemplo {flag} encontrado{f' para task={task}' if task else ''}.")
        typer.echo("Use --all para exportar sem curadoria, ou aprove exemplos via SQLite.")
    else:
        typer.echo(f"Exportados {n} exemplos → {out_path}")


# ---------------------------------------------------------------------------
# alert
# ---------------------------------------------------------------------------


@app.command()  # type: ignore[untyped-decorator]
def alert(
    ctx: typer.Context,
    threshold: Annotated[int, typer.Option("--threshold", help="Itens presos para disparar alerta")] = 50,
) -> None:
    """Verifica itens presos no pipeline e alerta via Telegram se configurado."""
    from canal_soberania.alert import check_stuck

    settings = ctx.obj["settings"]
    stuck = check_stuck(
        conn=ctx.obj["conn"],
        threshold=threshold,
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )
    if stuck:
        for status, count in stuck:
            typer.echo(f"STUCK: {status} → {count} itens")
        raise typer.Exit(1)
    else:
        typer.echo("OK: nenhum status crítico")


if __name__ == "__main__":
    app()
