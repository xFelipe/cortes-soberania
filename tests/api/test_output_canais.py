"""Testes para /output-canais CRUD."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from canal_soberania.config import OutputCanal


def _output_canal_body(canal_id: str = "soberania") -> dict[str, object]:
    return {
        "id": canal_id,
        "nome": "Canal Soberania",
        "tema": "Soberania nacional",
        "fontes": [],
        "criteria_path": "",
        "branding_dir": "",
        "youtube_channel_id": "",
        "youtube_token_path": "config/youtube_token.json",
        "ativo": True,
    }


def _make_output_canal(canal_id: str = "soberania") -> OutputCanal:
    return OutputCanal(**_output_canal_body(canal_id))  # type: ignore[arg-type]


# ── GET /output-canais ────────────────────────────────────────────────────────


def test_list_output_canais(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_output_canais.return_value = [_make_output_canal()]
    r = client.get("/output-canais", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == "soberania"
    mock_service.get_output_canais.assert_called_once()


def test_list_output_canais_empty(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_output_canais.return_value = []
    r = client.get("/output-canais", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_list_output_canais_no_auth(client: TestClient) -> None:
    r = client.get("/output-canais")
    assert r.status_code == 401


# ── POST /output-canais ───────────────────────────────────────────────────────


def test_create_output_canal(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    body = _output_canal_body("churrasco")
    r = client.post("/output-canais", json=body, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["id"] == "churrasco"
    mock_service.upsert_output_canal.assert_called_once()


def test_create_output_canal_no_auth(client: TestClient) -> None:
    r = client.post("/output-canais", json=_output_canal_body())
    assert r.status_code == 401


# ── GET /output-canais/{id} ───────────────────────────────────────────────────


def test_get_output_canal(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_output_canal.return_value = _make_output_canal()
    r = client.get("/output-canais/soberania", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == "soberania"
    mock_service.get_output_canal.assert_called_once_with("soberania")


def test_get_output_canal_not_found(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_output_canal.return_value = None
    r = client.get("/output-canais/nao_existe", headers=auth_headers)
    assert r.status_code == 404


def test_get_output_canal_no_auth(client: TestClient) -> None:
    r = client.get("/output-canais/soberania")
    assert r.status_code == 401


# ── PUT /output-canais/{id} ───────────────────────────────────────────────────


def test_update_output_canal(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    body = _output_canal_body("soberania")
    r = client.put("/output-canais/soberania", json=body, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == "soberania"
    mock_service.upsert_output_canal.assert_called_once()


def test_update_output_canal_id_mismatch(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = _output_canal_body("soberania")
    r = client.put("/output-canais/outro-id", json=body, headers=auth_headers)
    assert r.status_code == 422


def test_update_output_canal_no_auth(client: TestClient) -> None:
    r = client.put("/output-canais/soberania", json=_output_canal_body())
    assert r.status_code == 401


# ── DELETE /output-canais/{id} ────────────────────────────────────────────────


def test_delete_output_canal(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    r = client.delete("/output-canais/soberania", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["canal_id"] == "soberania"
    assert data["status"] == "deleted"
    mock_service.delete_output_canal.assert_called_once_with("soberania")


def test_delete_output_canal_no_auth(client: TestClient) -> None:
    r = client.delete("/output-canais/soberania")
    assert r.status_code == 401


# ── GET /output-canais/{id}/fontes ────────────────────────────────────────────


def test_get_fontes(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_output_canal_fontes.return_value = ["podpah", "flow"]
    r = client.get("/output-canais/soberania/fontes", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == ["podpah", "flow"]
    mock_service.get_output_canal_fontes.assert_called_once_with("soberania")


def test_get_fontes_no_auth(client: TestClient) -> None:
    r = client.get("/output-canais/soberania/fontes")
    assert r.status_code == 401


# ── PUT /output-canais/{id}/fontes ────────────────────────────────────────────


def test_set_fontes(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    r = client.put(
        "/output-canais/soberania/fontes",
        json=["podpah", "flow"],
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json() == ["podpah", "flow"]
    mock_service.set_output_canal_fontes.assert_called_once_with("soberania", ["podpah", "flow"])


def test_set_fontes_no_auth(client: TestClient) -> None:
    r = client.put("/output-canais/soberania/fontes", json=[])
    assert r.status_code == 401
