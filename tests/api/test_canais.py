"""Testes para /canais CRUD."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def _canal_body() -> dict[str, object]:
    return {
        "id": "canal-teste",
        "nome": "Canal Teste",
        "handle": "@canalteste",
        "channel_url": "https://youtube.com/@canalteste",
        "tema_primario": "soberania_nacional",
        "peso": 1.0,
        "auto_publish": False,
        "tolerancia_cortes": "desconhecida",
        "nota": "",
        "ativo": True,
    }


# ── GET ───────────────────────────────────────────────────────────────────────

def test_list_canais(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_canais.return_value = []
    r = client.get("/canais", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []
    mock_service.get_canais.assert_called_once()


def test_list_canais_no_auth(client: TestClient) -> None:
    r = client.get("/canais")
    assert r.status_code == 401


# ── POST ──────────────────────────────────────────────────────────────────────

def test_create_canal(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    body = _canal_body()
    r = client.post("/canais", json=body, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["id"] == "canal-teste"
    mock_service.upsert_canal.assert_called_once()


def test_create_canal_no_auth(client: TestClient) -> None:
    r = client.post("/canais", json=_canal_body())
    assert r.status_code == 401


# ── PUT ───────────────────────────────────────────────────────────────────────

def test_update_canal(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    body = _canal_body()
    r = client.put("/canais/canal-teste", json=body, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == "canal-teste"
    mock_service.upsert_canal.assert_called_once()


def test_update_canal_id_mismatch(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = _canal_body()
    r = client.put("/canais/outro-id", json=body, headers=auth_headers)
    assert r.status_code == 422


def test_update_canal_no_auth(client: TestClient) -> None:
    r = client.put("/canais/canal-teste", json=_canal_body())
    assert r.status_code == 401


# ── PATCH ─────────────────────────────────────────────────────────────────────

def test_toggle_ativo(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    r = client.patch("/canais/canal-teste/ativo", json={"ativo": False}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["canal_id"] == "canal-teste"
    assert data["ativo"] is False
    mock_service.toggle_canal_ativo.assert_called_once_with("canal-teste", False)


def test_toggle_ativo_missing_field(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.patch("/canais/canal-teste/ativo", json={}, headers=auth_headers)
    assert r.status_code == 422


def test_toggle_ativo_no_auth(client: TestClient) -> None:
    r = client.patch("/canais/canal-teste/ativo", json={"ativo": True})
    assert r.status_code == 401


# ── DELETE ────────────────────────────────────────────────────────────────────

def test_delete_canal(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    r = client.delete("/canais/canal-teste", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["canal_id"] == "canal-teste"
    mock_service.delete_canal.assert_called_once_with("canal-teste")


def test_delete_canal_no_auth(client: TestClient) -> None:
    r = client.delete("/canais/canal-teste")
    assert r.status_code == 401
