"""Entry point Typer — `cs` CLI."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from canal_soberania.config import ensure_data_dirs, get_paths, load_settings
from canal_soberania.db import init_db
from canal_soberania.logger import logger, setup_logger
from canal_soberania.models import TriageStage
from canal_soberania.services.pipeline_service import PipelineService

app = typer.Typer(
    name="cs",
    help="Canal Soberania — pipeline de cortes automatizado.",
    no_args_is_help=True,
)


@app.callback()
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
    ctx.call_on_close(conn.close)
    service = PipelineService(conn=conn, settings=settings, paths=paths)

    ctx.ensure_object(dict)
    ctx.obj["settings"] = settings
    ctx.obj["paths"] = paths
    ctx.obj["conn"] = conn
    ctx.obj["service"] = service


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@app.command()
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


@app.command()
def discover(
    ctx: typer.Context,
    canal: Annotated[list[str] | None, typer.Option("--canal", help="ID do canal (pode repetir). Padrão: todos ativos.")] = None,
    dias: Annotated[int | None, typer.Option("--dias", help="Janela de dias (override do YAML).")] = None,
    max_videos: Annotated[int | None, typer.Option("--max", help="Máx. vídeos por canal (override do YAML).")] = None,
    auto_triage: Annotated[bool, typer.Option("--auto-triage", help="Roda triagem metadata+caption logo após.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Busca vídeos novos nos canais monitorados."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    service: PipelineService = ctx.obj["service"]
    service.run_discover(
        dry_run=effective_dry_run,
        canal_ids=canal or None,
        janela_dias=dias,
        max_videos=max_videos,
    )
    if auto_triage and not effective_dry_run:
        service.run_triage_metadata(dry_run=False)
        service.run_triage_caption(dry_run=False)


# ---------------------------------------------------------------------------
# triage
# ---------------------------------------------------------------------------


@app.command()
def triage(
    ctx: typer.Context,
    stage: Annotated[TriageStage, typer.Option("--stage", help="metadata|caption|transcript")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Roda uma etapa de triagem sobre vídeos pendentes."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    service: PipelineService = ctx.obj["service"]

    if stage == TriageStage.METADATA:
        service.run_triage_metadata(dry_run=effective_dry_run)
    elif stage == TriageStage.CAPTION:
        service.run_triage_caption(dry_run=effective_dry_run)
    elif stage == TriageStage.TRANSCRIPT:
        service.run_triage_transcript(dry_run=effective_dry_run)
    else:
        logger.info("TODO: triage stage={}", stage.value)
        typer.echo(f"triage --stage {stage.value}: não implementado")


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------


@app.command()
def download(
    ctx: typer.Context,
    _pending: Annotated[bool, typer.Option("--pending")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Baixa áudio/vídeo dos itens aprovados na triagem."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    ctx.obj["service"].run_download(dry_run=effective_dry_run)


# ---------------------------------------------------------------------------
# transcribe
# ---------------------------------------------------------------------------


@app.command()
def transcribe(
    ctx: typer.Context,
    _pending: Annotated[bool, typer.Option("--pending")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Transcreve áudio com faster-whisper."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    ctx.obj["service"].run_transcribe(dry_run=effective_dry_run)


# ---------------------------------------------------------------------------
# find-clips
# ---------------------------------------------------------------------------


@app.command(name="find-clips")
def find_clips(
    ctx: typer.Context,
    _pending: Annotated[bool, typer.Option("--pending")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Identifica trechos para clipe via Claude Sonnet."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    ctx.obj["service"].run_find_clips(dry_run=effective_dry_run)


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------


@app.command()
def edit(
    ctx: typer.Context,
    _pending: Annotated[bool, typer.Option("--pending")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Edita clipes: corte, reframe 9:16, legendas, intro/outro."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    ctx.obj["service"].run_edit(dry_run=effective_dry_run)


# ---------------------------------------------------------------------------
# thumbnail
# ---------------------------------------------------------------------------


@app.command()
def thumbnail(
    ctx: typer.Context,
    _pending: Annotated[bool, typer.Option("--pending")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Gera thumbnail com Pillow."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    ctx.obj["service"].run_thumbnail(dry_run=effective_dry_run)


# ---------------------------------------------------------------------------
# metadata
# ---------------------------------------------------------------------------


@app.command()
def metadata(
    ctx: typer.Context,
    _pending: Annotated[bool, typer.Option("--pending")] = True,
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


@app.command()
def upload(
    ctx: typer.Context,
    platform: Annotated[Platform, typer.Option("--platform", help="youtube|tiktok")],
    _pending: Annotated[bool, typer.Option("--pending")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Sobe clipes para a plataforma especificada."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    service: PipelineService = ctx.obj["service"]

    if platform == Platform.youtube:
        service.run_upload_youtube(dry_run=effective_dry_run)
    elif platform == Platform.tiktok:
        service.run_upload_tiktok(dry_run=effective_dry_run)


@app.command(name="sync-youtube")
def sync_youtube(
    ctx: typer.Context,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Sincroniza status e métricas dos clipes já enviados ao YouTube."""
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    service: PipelineService = ctx.obj["service"]
    service.run_sync_youtube(dry_run=effective_dry_run)


# ---------------------------------------------------------------------------
# training
# ---------------------------------------------------------------------------


@app.command(name="training-stats")
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


@app.command(name="export-training")
def export_training(
    ctx: typer.Context,
    task: Annotated[str | None, typer.Option("--task", help="Filtrar por task específica")] = None,
    all_examples: Annotated[bool, typer.Option("--all", help="Exportar todos (sem curar)")] = False,
    output: Annotated[str, typer.Option("--output", help="Arquivo de saída (.jsonl)")] = "",
) -> None:
    """Exporta exemplos de treino em formato ChatML (JSONL) para fine-tuning."""
    from canal_soberania.config import get_paths
    from canal_soberania.db import export_training_jsonl

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


@app.command()
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


# ---------------------------------------------------------------------------
# pipeline-loop
# ---------------------------------------------------------------------------


@app.command(name="pipeline-loop")
def pipeline_loop(
    ctx: typer.Context,
    interval: Annotated[int, typer.Option("--interval", help="Segundos entre iterações")] = 60,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Roda o pipeline completo em loop, resetando itens travados antes de cada iteração.

    Processa automaticamente: triagem → download → transcrição → cortes →
    edição → thumbnail → metadados. Pressione Ctrl+C para encerrar.

    Timeouts de reset (itens travados são devolvidos ao estado processável):
      downloading   > 90 min  → triage_caption_passed
      transcribing  > 180 min → downloaded
      finding_clips > 45 min  → triage_transcript_passed
      editing       > 60 min  → identified
    """
    import signal
    import time
    from datetime import datetime

    service: PipelineService = ctx.obj["service"]
    effective_dry_run = dry_run or ctx.obj["settings"].dry_run
    heartbeat_path = ctx.obj["paths"]["data_dir"] / ".pipeline_heartbeat"

    typer.echo(f"Pipeline loop iniciado (intervalo={interval}s). Ctrl+C para parar.")
    logger.info("pipeline-loop iniciado | interval={}s | dry_run={}", interval, effective_dry_run)

    running = True

    def _stop(sig: int, frame: object) -> None:
        nonlocal running
        running = False
        service.cancel()
        typer.echo("\nEncerrando após a iteração atual…")
        logger.info("pipeline-loop: sinal {} recebido — encerrando", sig)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    iteration = 0
    while running:
        iteration += 1
        ts = datetime.now().strftime("%H:%M:%S")
        typer.echo(f"\n[{ts}] Iteração #{iteration}")
        logger.info("pipeline-loop: iteração #{}", iteration)

        stuck = service.reset_stuck_videos() + service.reset_stuck_clips()
        if stuck:
            typer.echo(f"  ↺ {stuck} item(s) resetados (stuck timeout)")

        service.reset_cancel()
        try:
            service.run_pipeline_auto(dry_run=effective_dry_run)
            typer.echo(f"  ✓ iteração #{iteration} concluída")
        except Exception as exc:
            logger.error("pipeline-loop: erro na iteração #{}: {}", iteration, exc)
            typer.echo(f"  ✗ ERRO: {exc}")

        # Heartbeat para restart_pipeline.sh detectar loop ativo
        try:
            heartbeat_path.touch()
        except Exception:
            pass

        if running:
            typer.echo(f"  … aguardando {interval}s")
            time.sleep(interval)

    typer.echo("Pipeline loop encerrado.")
    logger.info("pipeline-loop encerrado após {} iterações", iteration)


# ---------------------------------------------------------------------------
# health-check
# ---------------------------------------------------------------------------


@app.command(name="health-check")
def health_check(
    ctx: typer.Context,
    heartbeat: Annotated[str, typer.Option("--heartbeat", help="Arquivo de heartbeat do loop")] = "",
    notify: Annotated[bool, typer.Option("--notify", help="Envia alerta se houver problema")] = False,
) -> None:
    """Verifica saúde do pipeline: DB, disco, itens presos e loop ativo."""
    from canal_soberania.alerts.router import AlertRouter
    from canal_soberania.health.check import run_health_check

    settings = ctx.obj["settings"]
    paths = ctx.obj["paths"]
    heartbeat_path = Path(heartbeat) if heartbeat else None

    result = run_health_check(
        conn=ctx.obj["conn"],
        settings=settings,
        paths=paths,
        loop_heartbeat_file=heartbeat_path,
        stuck_threshold=settings.alert_stuck_threshold,
    )

    typer.echo(result.summary())

    if notify and (not result.ok or result.warnings):
        router = AlertRouter.from_settings(settings)
        level = "error" if not result.ok else "warning"
        router.send("Healthcheck", result.summary(), level=level)

    if not result.ok:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# alert-test
# ---------------------------------------------------------------------------


@app.command(name="alert-test")
def alert_test(
    ctx: typer.Context,
    level: Annotated[str, typer.Option("--level", help="info|warning|error|critical")] = "warning",
) -> None:
    """Dispara alerta de teste em todos os canais configurados."""
    from canal_soberania.alerts.router import AlertRouter

    settings = ctx.obj["settings"]
    router = AlertRouter.from_settings(settings)
    sent = router.send(
        title="Teste de alerta",
        body="Se você recebeu isso, os alertas estão funcionando.",
        level=level,
    )
    if sent:
        typer.echo(f"✓ Alerta enviado para {sent} canal(is)")
    else:
        typer.echo("✗ Nenhum canal configurado ou todos falharam")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
