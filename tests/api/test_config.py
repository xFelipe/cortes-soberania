"""Testes para GET/PUT /config."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ── GET ───────────────────────────────────────────────────────────────────────

def test_get_config(client: TestClient, auth_headers: dict[str, str]) -> None:
    r = client.get("/config", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "LLM_BACKEND" in data
    assert "WHISPER_BACKEND" in data
    assert "PIPELINE_LOOP_INTERVAL" in data
    # segredos não devem aparecer
    assert "ANTHROPIC_API_KEY" not in data
    assert "SMTP_PASSWORD" not in data


def test_get_config_no_auth(client: TestClient) -> None:
    r = client.get("/config")
    assert r.status_code == 401


# ── PUT ───────────────────────────────────────────────────────────────────────

def test_put_config_merges_env(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# comentário\nLOG_LEVEL=INFO\nEXISTING=kept\n", encoding="utf-8")

    import canal_soberania.api.routers.config as cfg_module
    monkeypatch.setattr(cfg_module, "_env_path", lambda: env_file)

    r = client.put("/config", json={"LLM_BACKEND": "ollama", "DRY_RUN": "true"}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "saved"
    assert body["restart_required"] is True
    assert "LLM_BACKEND" in body["updated"]

    written = env_file.read_text(encoding="utf-8")
    assert "LLM_BACKEND=ollama" in written
    assert "DRY_RUN=true" in written
    assert "EXISTING=kept" in written
    assert "LOG_LEVEL=INFO" in written
    assert "# comentário" in written


def test_put_config_invalid_key(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.put("/config", json={"ANTHROPIC_API_KEY": "hack"}, headers=auth_headers)
    assert r.status_code == 400


def test_put_config_empty_body(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.put("/config", json={}, headers=auth_headers)
    assert r.status_code == 400


def test_put_config_no_auth(client: TestClient) -> None:
    r = client.put("/config", json={"LLM_BACKEND": "ollama"})
    assert r.status_code == 401


def test_put_config_creates_env_if_missing(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / "new.env"
    assert not env_file.exists()

    import canal_soberania.api.routers.config as cfg_module
    monkeypatch.setattr(cfg_module, "_env_path", lambda: env_file)

    r = client.put("/config", json={"LOG_LEVEL": "DEBUG"}, headers=auth_headers)
    assert r.status_code == 200
    assert "LOG_LEVEL=DEBUG" in env_file.read_text(encoding="utf-8")
