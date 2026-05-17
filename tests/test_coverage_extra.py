"""Testes extras para cobrir caminhos não exercitados nos testes principais.

Objetivo: elevar cobertura de canal_soberania para ≥ 75%.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from canal_soberania.config import CanaisConfig, Canal, Parametros
from canal_soberania.db import connect, init_db, insert_video
from canal_soberania.llm import LLMResponse
from canal_soberania.models import Video

SCHEMA = Path(__file__).parent.parent / "schema.sql"
PROMPTS = Path(__file__).parent.parent / "prompts"
CRITERIOS = Path(__file__).parent.parent / "config" / "criterios_relevancia.md"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


def _video(**kw: object) -> Video:
    defaults: dict[str, object] = {
        "video_id": "dQw4w9WgXcQ",
        "canal_id": "flow_podcast",
        "title": "Test",
        "published_at": "2024-01-01T00:00:00Z",
        "status": "triage_transcript_passed",
    }
    defaults.update(kw)
    return Video.model_validate(defaults)


def _llm_response(text: str = '{"score": 8, "is_relevant": true, "themes": [], "rationale": "ok"}') -> MagicMock:
    resp = MagicMock(spec=LLMResponse)
    resp.text = text
    resp.model = "claude-haiku-4-5-20251001"
    resp.tokens_in = 100
    resp.tokens_out = 50
    resp.cost_usd = 0.001
    return resp


def _canais_cfg() -> CanaisConfig:
    canal = Canal(
        id="flow_podcast",
        nome="Flow Podcast",
        handle="@flowpodcast",
        channel_url="https://youtube.com/@flowpodcast",
        tema_primario="soberania",
        auto_publish=False,
    )
    return CanaisConfig(canais=[canal], parametros=Parametros())


# ---------------------------------------------------------------------------
# utils/retry.py
# ---------------------------------------------------------------------------


def test_network_retry_decorator_applies() -> None:
    from canal_soberania.utils.retry import network_retry
    decorator = network_retry((ConnectionError,), attempts=2)
    assert callable(decorator)


def test_network_retry_retries_on_error() -> None:
    from canal_soberania.utils.retry import network_retry
    calls: list[int] = []

    @network_retry((ValueError,), attempts=3, min_wait=0, max_wait=0)
    def flaky() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("transient")
        return "ok"

    result = flaky()
    assert result == "ok"
    assert len(calls) == 2


def test_network_retry_reraises_after_exhausting() -> None:
    from canal_soberania.utils.retry import network_retry
    import pytest

    @network_retry((RuntimeError,), attempts=2, min_wait=0, max_wait=0)
    def always_fails() -> None:
        raise RuntimeError("permanent")

    with pytest.raises(RuntimeError):
        always_fails()


# ---------------------------------------------------------------------------
# logger.py — setup_logger
# ---------------------------------------------------------------------------


def test_setup_logger_creates_log_dir(tmp_path: Path) -> None:
    from canal_soberania.logger import setup_logger
    log_dir = tmp_path / "logs" / "sub"
    setup_logger(log_dir, level="DEBUG")
    assert log_dir.exists()


def test_setup_logger_creates_file_handler(tmp_path: Path) -> None:
    from canal_soberania.logger import setup_logger, logger
    log_dir = tmp_path / "logs"
    setup_logger(log_dir, level="INFO")
    logger.info("test log entry")
    # Verifica que algum arquivo de log foi criado
    log_files = list(log_dir.glob("pipeline_*.log"))
    assert len(log_files) >= 1


# ---------------------------------------------------------------------------
# strategies/transcription.py — FasterWhisperBackend (modelo mockado)
# ---------------------------------------------------------------------------


def test_faster_whisper_name() -> None:
    from canal_soberania.strategies.transcription import FasterWhisperBackend
    b = FasterWhisperBackend(model_size="medium")
    assert "faster_whisper" in b.name
    assert "medium" in b.name


def test_faster_whisper_lazy_loads_model(tmp_path: Path) -> None:
    from canal_soberania.strategies.transcription import FasterWhisperBackend
    b = FasterWhisperBackend()
    assert b._model is None


def test_faster_whisper_transcribe_with_mock(tmp_path: Path) -> None:
    from canal_soberania.strategies.transcription import FasterWhisperBackend
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")

    mock_word = MagicMock()
    mock_word.word = "hello"
    mock_word.start = 0.0
    mock_word.end = 0.5

    mock_seg = MagicMock()
    mock_seg.start = 0.0
    mock_seg.end = 1.0
    mock_seg.text = "  hello world  "
    mock_seg.words = [mock_word]

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_seg], MagicMock())

    with patch("canal_soberania.strategies.transcription.FasterWhisperBackend._get_model", return_value=mock_model):
        b = FasterWhisperBackend()
        b._model = mock_model
        segments = b.transcribe(audio)

    assert len(segments) == 1
    assert segments[0].text == "hello world"
    assert segments[0].words[0]["word"] == "hello"


def test_faster_whisper_satisfies_protocol() -> None:
    from canal_soberania.core.strategies import TranscriptionBackend
    from canal_soberania.strategies.transcription import FasterWhisperBackend
    assert isinstance(FasterWhisperBackend(), TranscriptionBackend)


# ---------------------------------------------------------------------------
# stages/triage_metadata — idempotência e parse error
# ---------------------------------------------------------------------------


def test_triage_metadata_idempotency_guard(db: sqlite3.Connection) -> None:
    from canal_soberania.db import insert_triage_result
    from canal_soberania.models import TriageResult
    from canal_soberania.stages.triage_metadata import triage_video_metadata

    video = _video(status="discovered")
    insert_video(db, video)

    existing = TriageResult(
        video_id="dQw4w9WgXcQ",
        stage="metadata",
        score=8,
        is_relevant=True,
        model_used="claude-haiku-4-5-20251001",
    )
    insert_triage_result(db, existing)
    db.commit()

    prompt_template = (PROMPTS / "triagem_metadata.txt").read_text()
    criterios = CRITERIOS.read_text() if CRITERIOS.exists() else ""

    mock_llm = MagicMock()
    result = triage_video_metadata(
        video=video,
        conn=db,
        llm=mock_llm,
        model="claude-haiku-4-5-20251001",
        prompt_template=prompt_template,
        criterios=criterios,
        canais_cfg=_canais_cfg(),
        youtube=None,
        threshold=5,
        dry_run=False,
    )
    mock_llm.complete.assert_not_called()
    assert result is None


def test_triage_metadata_parse_error(db: sqlite3.Connection) -> None:
    from canal_soberania.stages.triage_metadata import triage_video_metadata

    video = _video(status="discovered")
    insert_video(db, video)

    prompt_template = (PROMPTS / "triagem_metadata.txt").read_text()
    criterios = CRITERIOS.read_text() if CRITERIOS.exists() else ""

    mock_llm = MagicMock()
    bad_resp = _llm_response("INVALID JSON {{{")
    mock_llm.complete.return_value = bad_resp

    result = triage_video_metadata(
        video=video,
        conn=db,
        llm=mock_llm,
        model="claude-haiku-4-5-20251001",
        prompt_template=prompt_template,
        criterios=criterios,
        canais_cfg=_canais_cfg(),
        youtube=None,
        threshold=5,
        dry_run=False,
    )
    assert result is None
    row = db.execute("SELECT status FROM videos WHERE video_id='dQw4w9WgXcQ'").fetchone()
    assert row["status"] == "processing_error"


# ---------------------------------------------------------------------------
# stages/triage_metadata — run() function
# ---------------------------------------------------------------------------


def test_triage_metadata_run_empty_db(db: sqlite3.Connection) -> None:
    from canal_soberania.stages.triage_metadata import run

    mock_llm = MagicMock()
    run(conn=db, llm=mock_llm, dry_run=True)
    mock_llm.complete.assert_not_called()


def test_triage_metadata_run_dry_run_with_video(db: sqlite3.Connection) -> None:
    from canal_soberania.stages.triage_metadata import run

    insert_video(db, _video(status="discovered"))
    mock_llm = MagicMock()
    run(conn=db, llm=mock_llm, dry_run=True)
    mock_llm.complete.assert_not_called()


# ---------------------------------------------------------------------------
# stages/triage_transcript — idempotência e run()
# ---------------------------------------------------------------------------


def test_triage_transcript_run_empty_db(db: sqlite3.Connection) -> None:
    from canal_soberania.stages.triage_transcript import run

    mock_llm = MagicMock()
    run(conn=db, llm=mock_llm, dry_run=True)
    mock_llm.complete.assert_not_called()


def test_triage_transcript_missing_transcript_file(db: sqlite3.Connection) -> None:
    from canal_soberania.stages.triage_transcript import triage_video_transcript

    video = _video(transcript_path="/nonexistent/path/transcript.json")
    insert_video(db, video)

    mock_llm = MagicMock()
    result = triage_video_transcript(
        video=video,
        conn=db,
        llm=mock_llm,
        model="claude-haiku-4-5-20251001",
        prompt_template="test",
        criterios="",
        canais_cfg=_canais_cfg(),
        threshold=5,
        dry_run=False,
    )
    assert result is None
    mock_llm.complete.assert_not_called()


def test_triage_transcript_idempotency_guard(db: sqlite3.Connection, tmp_path: Path) -> None:
    from canal_soberania.db import insert_triage_result
    from canal_soberania.models import TriageResult
    from canal_soberania.stages.triage_transcript import triage_video_transcript

    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(
        json.dumps({"segments": [{"start": 0, "end": 5, "text": "test"}]}),
        encoding="utf-8",
    )

    video = _video(transcript_path=str(transcript_path))
    insert_video(db, video)

    existing = TriageResult(
        video_id="dQw4w9WgXcQ",
        stage="transcript",
        score=8,
        is_relevant=True,
        model_used="claude-haiku-4-5-20251001",
    )
    insert_triage_result(db, existing)
    db.commit()

    prompt_template = (PROMPTS / "triagem_transcript.txt").read_text()
    criterios = CRITERIOS.read_text() if CRITERIOS.exists() else ""

    mock_llm = MagicMock()
    result = triage_video_transcript(
        video=video,
        conn=db,
        llm=mock_llm,
        model="claude-haiku-4-5-20251001",
        prompt_template=prompt_template,
        criterios=criterios,
        canais_cfg=_canais_cfg(),
        threshold=5,
        dry_run=False,
    )
    mock_llm.complete.assert_not_called()
    assert result is None


# ---------------------------------------------------------------------------
# stages/find_clips — transcript not found
# ---------------------------------------------------------------------------


def test_find_clips_transcript_file_missing(db: sqlite3.Connection) -> None:
    from canal_soberania.stages.find_clips import find_clips_for_video

    video = _video(
        status="triage_transcript_passed",
        transcript_path="/nonexistent/transcript.json",
    )
    insert_video(db, video)

    mock_llm = MagicMock()
    result = find_clips_for_video(
        video=video,
        conn=db,
        llm=mock_llm,
        model="claude-sonnet-4-6",
        prompt_template="test",
        criterios="",
        canais_cfg=_canais_cfg(),
        dry_run=False,
    )
    assert result == []
    mock_llm.complete.assert_not_called()


def test_find_clips_empty_transcript_path(db: sqlite3.Connection) -> None:
    from canal_soberania.stages.find_clips import find_clips_for_video

    video = _video(status="triage_transcript_passed", transcript_path=None)
    insert_video(db, video)

    mock_llm = MagicMock()
    result = find_clips_for_video(
        video=video,
        conn=db,
        llm=mock_llm,
        model="claude-sonnet-4-6",
        prompt_template="test",
        criterios="",
        canais_cfg=_canais_cfg(),
        dry_run=False,
    )
    assert result == []
    mock_llm.complete.assert_not_called()


def test_find_clips_run_empty_db(db: sqlite3.Connection) -> None:
    from canal_soberania.stages.find_clips import run

    mock_llm = MagicMock()
    run(conn=db, llm=mock_llm, dry_run=True)
    mock_llm.complete.assert_not_called()


# ---------------------------------------------------------------------------
# stages/metadata — run()
# ---------------------------------------------------------------------------


def test_metadata_run_empty_db(db: sqlite3.Connection) -> None:
    from canal_soberania.stages.metadata import run

    mock_llm = MagicMock()
    run(conn=db, dry_run=True)
    # nenhum clip no DB → sem chamadas LLM


# ---------------------------------------------------------------------------
# stages/discover — parse_duration edge cases
# ---------------------------------------------------------------------------


def test_parse_duration_full() -> None:
    from canal_soberania.stages.discover import _parse_duration
    assert _parse_duration("PT1H30M45S") == 5445


def test_parse_duration_minutes_only() -> None:
    from canal_soberania.stages.discover import _parse_duration
    assert _parse_duration("PT5M") == 300


def test_parse_duration_invalid() -> None:
    from canal_soberania.stages.discover import _parse_duration
    assert _parse_duration("INVALID") is None


# ---------------------------------------------------------------------------
# stages/discover — run()
# ---------------------------------------------------------------------------


def test_discover_run_with_mock_youtube(db: sqlite3.Connection) -> None:
    from canal_soberania.stages.discover import run

    mock_youtube = MagicMock()
    with patch("canal_soberania.stages.discover.discover_canal", return_value=(0, 0)):
        run(conn=db, youtube=mock_youtube, dry_run=True)


def test_discover_run_dry_run(db: sqlite3.Connection) -> None:
    from canal_soberania.stages.discover import run

    mock_youtube = MagicMock()
    with patch("canal_soberania.stages.discover.discover_canal", return_value=(2, 1)):
        run(conn=db, youtube=mock_youtube, dry_run=True)


# ---------------------------------------------------------------------------
# stages/triage_caption — run()
# ---------------------------------------------------------------------------


def test_triage_caption_run_empty_db(db: sqlite3.Connection) -> None:
    from canal_soberania.stages.triage_caption import run

    mock_llm = MagicMock()
    run(conn=db, llm=mock_llm, dry_run=True)
    mock_llm.complete.assert_not_called()


# ---------------------------------------------------------------------------
# stages/upload_tiktok — run()
# ---------------------------------------------------------------------------


def test_upload_tiktok_run_empty_db(db: sqlite3.Connection, tmp_path: Path) -> None:
    from canal_soberania.stages.upload_tiktok import run

    with patch("canal_soberania.stages.upload_tiktok.get_paths") as mock_paths:
        mock_paths.return_value = {
            "db_path": tmp_path / "test.db",
            "schema_path": SCHEMA,
            "clips_dir": tmp_path / "clips",
            "log_dir": tmp_path / "logs",
        }
        run(conn=db, dry_run=True)


# ---------------------------------------------------------------------------
# db.py — funções não cobertas
# ---------------------------------------------------------------------------


def test_get_videos_by_statuses(db: sqlite3.Connection) -> None:
    from canal_soberania.db import get_videos_by_statuses

    insert_video(db, _video(video_id="aaaaaaaaa11", status="discovered"))
    insert_video(db, _video(video_id="bbbbbbbbb22", status="triage_metadata_passed"))
    insert_video(db, _video(video_id="ccccccccc33", status="downloaded"))

    results = get_videos_by_statuses(db, ["discovered", "downloaded"])
    assert len(results) == 2
    statuses = {v.status for v in results}
    assert statuses == {"discovered", "downloaded"}


def test_update_clip_status_with_error(db: sqlite3.Connection) -> None:
    from canal_soberania.db import get_clips_by_status, insert_clip, update_clip_status
    from canal_soberania.models import Clip

    insert_video(db, _video())
    clip = Clip(clip_id="dQw4w9WgXcQ_0_30", video_id="dQw4w9WgXcQ", start_s=0.0, end_s=30.0)
    insert_clip(db, clip)
    update_clip_status(db, "dQw4w9WgXcQ_0_30", "processing_error", "test error")
    db.commit()

    row = db.execute("SELECT status, error_message FROM clips WHERE clip_id=?", ("dQw4w9WgXcQ_0_30",)).fetchone()
    assert row["status"] == "processing_error"
    assert row["error_message"] == "test error"


def test_get_training_examples_with_task_filter(db: sqlite3.Connection) -> None:
    from canal_soberania.db import get_training_examples, log_training_example

    log_training_example(db, "triage", "prompt1", "completion1", "claude-haiku-4-5")
    log_training_example(db, "metadata", "prompt2", "completion2", "claude-sonnet-4-6")
    db.commit()

    examples = get_training_examples(db, task="triage")
    assert len(examples) == 1
    assert examples[0]["task"] == "triage"


def test_get_training_examples_approved_only(db: sqlite3.Connection) -> None:
    from canal_soberania.db import get_training_examples, log_training_example

    log_training_example(db, "triage", "p1", "c1", "claude-haiku-4-5")
    log_training_example(db, "triage", "p2", "c2", "claude-haiku-4-5")
    db.execute("UPDATE training_examples SET approved=1 WHERE prompt='p1'")
    db.commit()

    all_ex = get_training_examples(db)
    approved = get_training_examples(db, approved_only=True)
    assert len(all_ex) == 2
    assert len(approved) == 1


def test_training_stats(db: sqlite3.Connection) -> None:
    from canal_soberania.db import log_training_example, training_stats

    log_training_example(db, "triage", "p1", "c1", "model")
    log_training_example(db, "triage", "p2", "c2", "model")
    db.commit()

    stats = training_stats(db)
    assert "triage" in stats
    assert stats["triage"]["total"] == 2


def test_export_training_jsonl(db: sqlite3.Connection, tmp_path: Path) -> None:
    from canal_soberania.db import export_training_jsonl, log_training_example

    log_training_example(db, "triage", "prompt", "completion", "model")
    db.execute("UPDATE training_examples SET approved=1")
    db.commit()

    output = tmp_path / "export.jsonl"
    n = export_training_jsonl(db, output, approved_only=True)
    assert n == 1
    assert output.exists()
    import json as json_mod
    line = json_mod.loads(output.read_text().strip())
    assert "messages" in line


def test_export_training_jsonl_with_system_prompt(db: sqlite3.Connection, tmp_path: Path) -> None:
    """Covers db.py line 323 — system_prompt branch in export_training_jsonl."""
    from canal_soberania.db import export_training_jsonl, log_training_example

    log_training_example(
        db, "triage", "my_prompt", "my_completion", "model",
        system_prompt="You are a helpful assistant."
    )
    db.execute("UPDATE training_examples SET approved=1")
    db.commit()

    output = tmp_path / "export_sys.jsonl"
    n = export_training_jsonl(db, output, approved_only=True)
    assert n == 1
    line = json.loads(output.read_text().strip())
    roles = [m["role"] for m in line["messages"]]
    assert "system" in roles


def test_update_video_paths_no_valid_keys(db: sqlite3.Connection) -> None:
    """Covers db.py line 76 — early return when no valid path columns given."""
    from canal_soberania.db import update_video_paths
    video = _video()
    insert_video(db, video)
    # Should return early without error when given no valid column keys
    update_video_paths(db, video.video_id, invalid_key="/some/path")


# ---------------------------------------------------------------------------
# PipelineService — uncovered branches
# ---------------------------------------------------------------------------


def test_pipeline_service_transition_clip(db: sqlite3.Connection) -> None:
    """Covers pipeline_service.py line 100 — transition_clip."""
    from canal_soberania.services.pipeline_service import PipelineService
    from canal_soberania.config import Settings
    svc = PipelineService(conn=db, settings=Settings(), paths={})
    # Valid transition: identified → editing (no exception expected)
    svc.transition_clip("clip_abc", "identified", "editing")


def test_pipeline_service_run_stage_fallback_fn(db: sqlite3.Connection) -> None:
    """Covers pipeline_service.py lines 114-115, 130 — fallback stage_fn when stage not in registry."""
    from canal_soberania.services.pipeline_service import PipelineService
    from canal_soberania.config import Settings

    called: list[bool] = []

    def fake_fn(**_kw: object) -> None:
        called.append(True)

    svc = PipelineService(conn=db, settings=Settings(), paths={})
    # Patch get_stage to raise KeyError so fallback path executes
    with patch("canal_soberania.services.pipeline_service.__builtins__", {}):
        pass  # noop — use direct call below
    with patch("canal_soberania.stages.wrappers.get_stage", side_effect=KeyError("unknown")):
        svc._run_stage("unknown_stage", fake_fn, True)

    assert called


def test_pipeline_service_stage_will_retry_event(db: sqlite3.Connection) -> None:
    """Covers pipeline_service.py line 125 — stage_will_retry event."""
    from canal_soberania.services.pipeline_service import PipelineService
    from canal_soberania.config import Settings
    from canal_soberania.core.events import EventBus, PipelineEvent
    from canal_soberania.core.stage import StageResult

    events: list[str] = []
    bus = EventBus()
    bus.subscribe("*", lambda e: events.append(e.type))

    svc = PipelineService(conn=db, settings=Settings(), paths={}, event_bus=bus)

    mock_stage = MagicMock()
    mock_stage.name = "mock_stage"
    err = RuntimeError("transient")
    mock_stage.execute.return_value = StageResult(success=False, error=err)
    mock_stage.can_retry.return_value = True

    with patch("canal_soberania.stages.wrappers.get_stage", return_value=mock_stage):
        with pytest.raises(RuntimeError):
            svc._run_stage("mock_stage", MagicMock(), False)

    assert "stage_will_retry" in events


# ---------------------------------------------------------------------------
# Strategy — mediapipe + faster-whisper mocked paths
# ---------------------------------------------------------------------------


def test_face_detection_with_mocked_mediapipe() -> None:
    """Covers reframe.py lines 57-65 — cv2/mediapipe code path via mocks."""
    import numpy as np
    from canal_soberania.strategies.reframe import FaceDetectionReframe

    fake_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    mock_lm = MagicMock()
    mock_lm.x = 0.5
    mock_face = MagicMock()
    mock_face.landmark = [mock_lm] * 10
    mock_results = MagicMock()
    mock_results.multi_face_landmarks = [mock_face]

    mock_fm_instance = MagicMock()
    mock_fm_instance.__enter__ = MagicMock(return_value=mock_fm_instance)
    mock_fm_instance.__exit__ = MagicMock(return_value=False)
    mock_fm_instance.process.return_value = mock_results

    mock_mp = MagicMock()
    mock_mp.solutions.face_mesh.FaceMesh.return_value = mock_fm_instance

    mock_cv2 = MagicMock()
    mock_cv2.cvtColor.return_value = fake_frame
    mock_cv2.COLOR_BGR2RGB = 4

    with patch.dict("sys.modules", {"cv2": mock_cv2, "mediapipe": mock_mp}):
        strategy = FaceDetectionReframe()
        params = strategy.get_crop_params(
            frame=fake_frame,
            source_width=1920,
            source_height=1080,
        )

    assert params.width > 0


def test_faster_whisper_backend_lazy_load(tmp_path: Path) -> None:
    """Covers transcription.py lines 29-36 — lazy model loading with mocked faster_whisper."""
    from canal_soberania.strategies.transcription import FasterWhisperBackend

    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fake")

    mock_word = MagicMock()
    mock_word.word = "hello"
    mock_word.start = 0.0
    mock_word.end = 0.5

    mock_seg = MagicMock()
    mock_seg.start = 0.0
    mock_seg.end = 0.5
    mock_seg.text = " hello"
    mock_seg.words = [mock_word]

    mock_model_instance = MagicMock()
    mock_model_instance.transcribe.return_value = ([mock_seg], MagicMock())

    MockWhisperModel = MagicMock(return_value=mock_model_instance)
    mock_fw = MagicMock()
    mock_fw.WhisperModel = MockWhisperModel

    with patch.dict("sys.modules", {"faster_whisper": mock_fw}):
        backend = FasterWhisperBackend(model_size="tiny", device="cpu", compute_type="int8")
        # First call triggers lazy load
        results = backend.transcribe(audio)

    assert len(results) == 1
    assert results[0].text == "hello"
    MockWhisperModel.assert_called_once_with("tiny", device="cpu", compute_type="int8")
