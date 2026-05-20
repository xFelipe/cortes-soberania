"""Testes de get_or_create_token — dual-write data_dir + XDG."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from canal_soberania.api.auth import get_or_create_token


@pytest.fixture()
def tmp_data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture()
def tmp_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redireciona XDG_TOKEN_PATH para um diretório temporário."""
    xdg_dir = tmp_path / "config" / "canal-soberania"
    xdg_path = xdg_dir / ".api_token"
    monkeypatch.setattr("canal_soberania.api.auth.XDG_TOKEN_PATH", xdg_path)
    return xdg_path


class TestGetOrCreateToken:
    def test_gera_novo_token_quando_nenhum_existe(
        self, tmp_data_dir: Path, tmp_xdg: Path
    ) -> None:
        token = get_or_create_token(tmp_data_dir)
        assert len(token) == 48  # secrets.token_hex(24)
        assert tmp_xdg.exists()
        assert tmp_xdg.read_text().strip() == token

    def test_grava_em_data_dir_e_xdg(
        self, tmp_data_dir: Path, tmp_xdg: Path
    ) -> None:
        token = get_or_create_token(tmp_data_dir)
        data_token = (tmp_data_dir / ".api_token").read_text().strip()
        xdg_token = tmp_xdg.read_text().strip()
        assert data_token == token
        assert xdg_token == token

    def test_chmod_600_em_ambos(
        self, tmp_data_dir: Path, tmp_xdg: Path
    ) -> None:
        get_or_create_token(tmp_data_dir)
        data_stat = os.stat(tmp_data_dir / ".api_token")
        xdg_stat = os.stat(tmp_xdg)
        assert oct(data_stat.st_mode)[-3:] == "600"
        assert oct(xdg_stat.st_mode)[-3:] == "600"

    def test_reutiliza_token_existente_no_xdg(
        self, tmp_data_dir: Path, tmp_xdg: Path
    ) -> None:
        # Primeira chamada — gera token
        token1 = get_or_create_token(tmp_data_dir)
        # Segunda chamada — deve reutilizar
        token2 = get_or_create_token(tmp_data_dir)
        assert token1 == token2

    def test_copia_token_de_data_dir_para_xdg(
        self, tmp_data_dir: Path, tmp_xdg: Path
    ) -> None:
        # Simula estado pré-XDG: token só em data_dir
        existing = "aabbccddeeff" * 4
        data_token_path = tmp_data_dir / ".api_token"
        data_token_path.write_text(existing)
        os.chmod(data_token_path, 0o600)

        token = get_or_create_token(tmp_data_dir)

        assert token == existing
        assert tmp_xdg.read_text().strip() == existing

    def test_xdg_tem_prioridade_sobre_data_dir(
        self, tmp_data_dir: Path, tmp_xdg: Path
    ) -> None:
        # XDG tem token A, data_dir tem token B
        token_a = "aaaa" * 12
        token_b = "bbbb" * 12
        tmp_xdg.parent.mkdir(parents=True, exist_ok=True)
        tmp_xdg.write_text(token_a)
        (tmp_data_dir / ".api_token").write_text(token_b)

        token = get_or_create_token(tmp_data_dir)

        assert token == token_a
        # data_dir fica sincronizado com XDG
        assert (tmp_data_dir / ".api_token").read_text().strip() == token_a
