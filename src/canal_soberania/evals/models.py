"""Modelos de dados para o sistema de eval de prompts."""

from __future__ import annotations

from pydantic import BaseModel


class GroundTruth(BaseModel):
    is_relevant: bool
    score_expected: int | None = None  # 0–10, opcional; para referência


class EvalEntry(BaseModel):
    video_id: str
    title: str
    description: str
    tags: list[str]
    canal_id: str
    transcript_path: str | None = None  # caminho absoluto para o JSON de transcrição
    captions: str | None = None          # texto plano das auto-captions, para triage_caption
    ground_truth: dict[str, GroundTruth]  # stage → ground truth esperado
    notes: str = ""


class EvalResult(BaseModel):
    video_id: str
    stage: str
    is_relevant_predicted: bool
    score_predicted: int
    is_relevant_expected: bool
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model_used: str
    raw_response: str
    correct: bool   # is_relevant_predicted == is_relevant_expected
    error: str | None = None


class RunSummary(BaseModel):
    run_id: str
    stage: str
    backend: str
    prompt_version: str
    precision: float
    recall: float
    f1: float
    accuracy: float
    total_cost_usd: float
    total_tokens_in: int
    total_tokens_out: int
    total_entries: int
    ts: str
