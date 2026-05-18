"""Testes da CLI via typer.testing.CliRunner + PipelineService mockado."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from canal_soberania.cli import app
from canal_soberania.models import Video

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixture: injeta PipelineService mock via ctx.obj
# ---------------------------------------------------------------------------


@pytest.fixture
def svc() -> MagicMock:
    m = MagicMock()
    m.get_status_summary.return_value = {"discovered": 3, "downloaded": 1}
    m.get_monthly_cost.return_value = 0.42
    m.get_video.return_value = None
    m.reset_stuck_videos.return_value = 0
    m.reset_stuck_clips.return_value = 0
    return m


def _invoke(args: list[str], svc: MagicMock) -> object:
    """Invoca o app substituindo o callback de setup por um que injeta o mock."""
    with (
        patch("canal_soberania.cli.load_settings") as mock_settings,
        patch("canal_soberania.cli.get_paths") as mock_paths,
        patch("canal_soberania.cli.ensure_data_dirs"),
        patch("canal_soberania.cli.setup_logger"),
        patch("canal_soberania.db.connect"),          # lazy import dentro do callback
        patch("canal_soberania.cli.init_db"),
        patch("canal_soberania.cli.PipelineService", return_value=svc),
    ):
        settings_obj = MagicMock()
        settings_obj.dry_run = False
        settings_obj.log_level = "INFO"
        mock_settings.return_value = settings_obj

        paths_obj: dict = {
            "db_path": MagicMock(exists=lambda: True),
            "schema_path": MagicMock(),
            "log_dir": MagicMock(),
        }
        mock_paths.return_value = paths_obj

        return runner.invoke(app, args, catch_exceptions=False)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_empty_db(svc: MagicMock) -> None:
    svc.get_status_summary.return_value = {}
    result = _invoke(["status"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    assert "Banco vazio" in result.output  # type: ignore[union-attr]


def test_status_with_summary(svc: MagicMock) -> None:
    result = _invoke(["status"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    assert "discovered" in result.output  # type: ignore[union-attr]
    assert "0.4200" in result.output  # type: ignore[union-attr]


def test_status_video_not_found(svc: MagicMock) -> None:
    svc.get_video.return_value = None
    result = _invoke(["status", "--video-id", "abc123"], svc)
    assert result.exit_code == 1  # type: ignore[union-attr]
    assert "não encontrado" in result.output  # type: ignore[union-attr]


def test_status_video_found(svc: MagicMock) -> None:
    svc.get_video.return_value = Video(
        video_id="abc1234567x", canal_id="UC1", title="Título", published_at="2025-01-01"
    )
    result = _invoke(["status", "--video-id", "abc1234567x"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    assert "video_id" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------


def test_discover_delegates(svc: MagicMock) -> None:
    result = _invoke(["discover"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_discover.assert_called_once_with(dry_run=False, canal_ids=None, janela_dias=None, max_videos=None)


def test_discover_with_options(svc: MagicMock) -> None:
    result = _invoke(["discover", "--canal", "UC123", "--dias", "7", "--max", "5"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_discover.assert_called_once_with(
        dry_run=False, canal_ids=["UC123"], janela_dias=7, max_videos=5
    )


def test_discover_auto_triage(svc: MagicMock) -> None:
    result = _invoke(["discover", "--auto-triage"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_triage_metadata.assert_called_once_with(dry_run=False)
    svc.run_triage_caption.assert_called_once_with(dry_run=False)


# ---------------------------------------------------------------------------
# triage
# ---------------------------------------------------------------------------


def test_triage_metadata(svc: MagicMock) -> None:
    result = _invoke(["triage", "--stage", "metadata"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_triage_metadata.assert_called_once()


def test_triage_caption(svc: MagicMock) -> None:
    result = _invoke(["triage", "--stage", "caption"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_triage_caption.assert_called_once()


def test_triage_transcript(svc: MagicMock) -> None:
    result = _invoke(["triage", "--stage", "transcript"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_triage_transcript.assert_called_once()


# ---------------------------------------------------------------------------
# download / transcribe / find-clips / edit / thumbnail / metadata
# ---------------------------------------------------------------------------


def test_download_delegates(svc: MagicMock) -> None:
    result = _invoke(["download"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_download.assert_called_once_with(dry_run=False)


def test_transcribe_delegates(svc: MagicMock) -> None:
    result = _invoke(["transcribe"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_transcribe.assert_called_once_with(dry_run=False)


def test_find_clips_delegates(svc: MagicMock) -> None:
    result = _invoke(["find-clips"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_find_clips.assert_called_once_with(dry_run=False)


def test_edit_delegates(svc: MagicMock) -> None:
    result = _invoke(["edit"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_edit.assert_called_once_with(dry_run=False)


def test_thumbnail_delegates(svc: MagicMock) -> None:
    result = _invoke(["thumbnail"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_thumbnail.assert_called_once_with(dry_run=False)


def test_metadata_delegates(svc: MagicMock) -> None:
    result = _invoke(["metadata"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_generate_metadata.assert_called_once_with(dry_run=False)


# ---------------------------------------------------------------------------
# upload
# ---------------------------------------------------------------------------


def test_upload_youtube(svc: MagicMock) -> None:
    result = _invoke(["upload", "--platform", "youtube"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_upload_youtube.assert_called_once_with(dry_run=False)


def test_upload_tiktok(svc: MagicMock) -> None:
    result = _invoke(["upload", "--platform", "tiktok"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_upload_tiktok.assert_called_once_with(dry_run=False)


# ---------------------------------------------------------------------------
# dry-run propagation
# ---------------------------------------------------------------------------


def test_dry_run_flag_propagates(svc: MagicMock) -> None:
    result = _invoke(["--dry-run", "download"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    # --dry-run top-level chama settings.model_copy(update={"dry_run": True});
    # o resultado de model_copy é passado para effective_dry_run — checa truthy.
    svc.run_download.assert_called_once()
    assert svc.run_download.call_args.kwargs["dry_run"]


# ---------------------------------------------------------------------------
# alert
# ---------------------------------------------------------------------------


def test_alert_ok(svc: MagicMock) -> None:
    with patch("canal_soberania.alert.check_stuck", return_value=[]):
        result = _invoke(["alert"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    assert "OK" in result.output  # type: ignore[union-attr]


def test_alert_stuck(svc: MagicMock) -> None:
    with patch("canal_soberania.alert.check_stuck", return_value=[("downloading", 5)]):
        result = _invoke(["alert"], svc)
    assert result.exit_code == 1  # type: ignore[union-attr]
    assert "STUCK" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# sync-youtube
# ---------------------------------------------------------------------------


def test_sync_youtube_delegates(svc: MagicMock) -> None:
    result = _invoke(["sync-youtube"], svc)
    assert result.exit_code == 0  # type: ignore[union-attr]
    svc.run_sync_youtube.assert_called_once_with(dry_run=False)
