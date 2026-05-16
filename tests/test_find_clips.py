"""Testes para stages/find_clips.py."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from canal_soberania.config import Canal, CanaisConfig, Parametros
from canal_soberania.db import connect, get_clips_by_status, get_videos_by_status, init_db, insert_video
from canal_soberania.llm import LLMResponse
from canal_soberania.models import Video
from canal_soberania.stages.find_clips import (
    _format_segments_seconds,
    _parse_clips_response,
    find_clips_for_video,
)

SCHEMA = Path(__file__).parent.parent / "schema.sql"
PROMPT_TEMPLATE = Path(__file__).parent.parent / "prompts" / "identificar_cortes.txt"
CRITERIOS = Path(__file__).parent.parent / "config" / "criterios_relevancia.md"

_SAMPLE_SEGMENTS = [
    {"start": 0.0, "end": 30.0, "text": "Boas-vindas ao podcast."},
    {"start": 30.0, "end": 120.0, "text": "O Brasil está perdendo soberania industrial rapidamente."},
    {"start": 120.0, "end": 200.0, "text": "O pré-sal é o maior ativo estratégico do país."},
    {"start": 200.0, "end": 290.0, "text": "Precisamos de política industrial concreta agora."},
    {"start": 290.0, "end": 350.0, "text": "A BRICS pode ser a saída para desdolarização."},
    {"start": 350.0, "end": 380.0, "text": "Obrigado, se inscreva no canal."},
]

_GOOD_CLIPS_RESPONSE = json.dumps({
    "clips": [
        {
            "start_s": 30.0,
            "end_s": 100.0,
            "duracao_s": 70.0,
            "hook": "O Brasil está perdendo soberania",
            "payoff": "industrial rapidamente",
            "tema_soberania": "industria_defesa",
            "score_viral": 8,
            "score_relevancia": 9,
            "justificativa": "Afirmação forte com impacto direto sobre soberania.",
        },
        {
            "start_s": 200.0,
            "end_s": 290.0,
            "duracao_s": 90.0,
            "hook": "Precisamos de política industrial",
            "payoff": "concreta agora",
            "tema_soberania": "economia_soberana",
            "score_viral": 7,
            "score_relevancia": 8,
            "justificativa": "Proposta de ação concreta, engaja audiência.",
        },
    ]
})


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


@pytest.fixture
def transcript_file(tmp_path: Path) -> Path:
    tdir = tmp_path / "transcripts"
    tdir.mkdir()
    path = tdir / "dQw4w9WgXcQ.json"
    path.write_text(
        json.dumps({"video_id": "dQw4w9WgXcQ", "language": "pt", "segments": _SAMPLE_SEGMENTS}),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def video(transcript_file: Path) -> Video:
    return Video(
        video_id="dQw4w9WgXcQ",
        canal_id="arte_da_guerra",
        title="Soberania industrial: o debate urgente",
        published_at="2026-05-10T12:00:00Z",
        duration_s=3600,
        status="triage_transcript_passed",
        transcript_path=str(transcript_file),
    )


@pytest.fixture
def canais_cfg() -> CanaisConfig:
    canal = Canal(
        id="arte_da_guerra",
        nome="Arte da Guerra",
        handle="@ARTEDAGUERRA",
        channel_url="https://www.youtube.com/@ARTEDAGUERRA",
        tema_primario="geopolitica_defesa",
    )
    return CanaisConfig(canais=[canal], parametros=Parametros())


@pytest.fixture
def prompt_template() -> str:
    return PROMPT_TEMPLATE.read_text(encoding="utf-8")


@pytest.fixture
def criterios() -> str:
    return CRITERIOS.read_text(encoding="utf-8")


def _make_llm(response: str = _GOOD_CLIPS_RESPONSE) -> MagicMock:
    llm = MagicMock()
    llm.complete.return_value = LLMResponse(
        text=response,
        model="claude-sonnet-4-6",
        tokens_in=5000,
        tokens_out=400,
        cost_usd=0.021,
    )
    return llm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_format_segments_seconds() -> None:
    result = _format_segments_seconds(_SAMPLE_SEGMENTS)
    assert "[30.0 - 120.0]" in result
    assert "pré-sal" in result


def test_format_segments_seconds_empty() -> None:
    assert _format_segments_seconds([]) == ""


def test_parse_clips_response_valid() -> None:
    params = Parametros()
    candidates = _parse_clips_response(_GOOD_CLIPS_RESPONSE, "dQw4w9WgXcQ", params)
    assert len(candidates) == 2
    assert candidates[0].start_s == 30.0
    assert candidates[0].score_viral == 8


def test_parse_clips_response_filters_by_duration() -> None:
    params = Parametros(clip_duracao_min=30, clip_duracao_max=90)
    raw = json.dumps({
        "clips": [
            {
                "start_s": 0.0, "end_s": 10.0, "duracao_s": 10.0,  # muito curto
                "hook": "x", "payoff": "y", "tema_soberania": "z",
                "score_viral": 8, "score_relevancia": 8, "justificativa": "ok",
            },
            {
                "start_s": 0.0, "end_s": 200.0, "duracao_s": 200.0,  # muito longo
                "hook": "x", "payoff": "y", "tema_soberania": "z",
                "score_viral": 8, "score_relevancia": 8, "justificativa": "ok",
            },
            {
                "start_s": 30.0, "end_s": 90.0, "duracao_s": 60.0,  # OK
                "hook": "hook", "payoff": "pay", "tema_soberania": "ind",
                "score_viral": 8, "score_relevancia": 9, "justificativa": "bom",
            },
        ]
    })
    candidates = _parse_clips_response(raw, "vid", params)
    assert len(candidates) == 1
    assert candidates[0].start_s == 30.0


def test_parse_clips_response_filters_low_scores() -> None:
    params = Parametros()
    raw = json.dumps({
        "clips": [
            {
                "start_s": 30.0, "end_s": 90.0, "duracao_s": 60.0,
                "hook": "x", "payoff": "y", "tema_soberania": "z",
                "score_viral": 5, "score_relevancia": 9,  # viral baixo
                "justificativa": "ok",
            },
            {
                "start_s": 100.0, "end_s": 170.0, "duracao_s": 70.0,
                "hook": "a", "payoff": "b", "tema_soberania": "c",
                "score_viral": 8, "score_relevancia": 8,
                "justificativa": "bom",
            },
        ]
    })
    candidates = _parse_clips_response(raw, "vid", params)
    assert len(candidates) == 1
    assert candidates[0].start_s == 100.0


def test_parse_clips_response_respects_max_clipes() -> None:
    params = Parametros(max_clipes_por_video=2)
    clips_list = [
        {
            "start_s": float(i * 100),
            "end_s": float(i * 100 + 60),
            "duracao_s": 60.0,
            "hook": f"hook {i}",
            "payoff": f"pay {i}",
            "tema_soberania": "ind",
            "score_viral": 8,
            "score_relevancia": 8,
            "justificativa": "ok",
        }
        for i in range(5)
    ]
    raw = json.dumps({"clips": clips_list})
    candidates = _parse_clips_response(raw, "vid", params)
    assert len(candidates) == 2


# ---------------------------------------------------------------------------
# find_clips_for_video integration
# ---------------------------------------------------------------------------


def test_find_clips_inserts_clips(
    db: sqlite3.Connection, video: Video, canais_cfg: CanaisConfig,
    prompt_template: str, criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    clips = find_clips_for_video(
        video=video, conn=db, llm=_make_llm(), model="claude-sonnet-4-6",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg,
    )

    assert len(clips) == 2
    identified = get_clips_by_status(db, "identified")
    assert len(identified) == 2
    assert all(c.video_id == "dQw4w9WgXcQ" for c in identified)


def test_find_clips_video_status_updated(
    db: sqlite3.Connection, video: Video, canais_cfg: CanaisConfig,
    prompt_template: str, criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    find_clips_for_video(
        video=video, conn=db, llm=_make_llm(), model="claude-sonnet-4-6",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg,
    )

    assert len(get_videos_by_status(db, "clips_found")) == 1


def test_find_clips_clip_id_format(
    db: sqlite3.Connection, video: Video, canais_cfg: CanaisConfig,
    prompt_template: str, criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    clips = find_clips_for_video(
        video=video, conn=db, llm=_make_llm(), model="claude-sonnet-4-6",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg,
    )

    assert clips[0].clip_id == "dQw4w9WgXcQ_30_100"
    assert clips[1].clip_id == "dQw4w9WgXcQ_200_290"


def test_find_clips_dry_run(
    db: sqlite3.Connection, video: Video, canais_cfg: CanaisConfig,
    prompt_template: str, criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    llm = _make_llm()
    clips = find_clips_for_video(
        video=video, conn=db, llm=llm, model="claude-sonnet-4-6",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg, dry_run=True,
    )

    assert clips == []
    llm.complete.assert_not_called()
    assert len(get_clips_by_status(db, "identified")) == 0


def test_find_clips_llm_error(
    db: sqlite3.Connection, video: Video, canais_cfg: CanaisConfig,
    prompt_template: str, criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    llm = MagicMock()
    llm.complete.side_effect = RuntimeError("overloaded")

    clips = find_clips_for_video(
        video=video, conn=db, llm=llm, model="claude-sonnet-4-6",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg,
    )

    assert clips == []
    assert len(get_videos_by_status(db, "processing_error")) == 1


def test_find_clips_no_transcript_path(
    db: sqlite3.Connection, canais_cfg: CanaisConfig,
    prompt_template: str, criterios: str,
) -> None:
    v = Video(
        video_id="dQw4w9WgXcQ",
        canal_id="arte_da_guerra",
        title="Teste",
        published_at="2026-05-10T12:00:00Z",
        status="triage_transcript_passed",
        transcript_path=None,
    )
    with db:
        insert_video(db, v)

    clips = find_clips_for_video(
        video=v, conn=db, llm=_make_llm(), model="claude-sonnet-4-6",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg,
    )

    assert clips == []
