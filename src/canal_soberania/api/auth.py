"""Geração e verificação de token de autenticação da API local."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import Header, HTTPException, Query, Request


_TOKEN_FILE = ".api_token"
XDG_TOKEN_PATH = Path.home() / ".config" / "canal-soberania" / ".api_token"


def _write_token(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token)
    os.chmod(path, 0o600)


def get_or_create_token(data_dir: Path) -> str:
    """Retorna o token da API, criando-o se não existir.

    Grava em dois locais:
    - data_dir/.api_token  (legado, usado pelo backend)
    - ~/.config/canal-soberania/.api_token  (XDG, lido pelo Tauri)
    """
    data_token_path = data_dir / _TOKEN_FILE
    xdg_path = XDG_TOKEN_PATH

    # Tenta carregar token existente (XDG tem prioridade)
    if xdg_path.exists():
        token = xdg_path.read_text().strip()
        if token:
            # Sincroniza para data_dir se necessário
            if not data_token_path.exists() or data_token_path.read_text().strip() != token:
                _write_token(data_token_path, token)
            return token

    if data_token_path.exists():
        token = data_token_path.read_text().strip()
        if token:
            _write_token(xdg_path, token)
            return token

    token = secrets.token_hex(24)
    _write_token(data_token_path, token)
    _write_token(xdg_path, token)
    return token


def verify_token(
    request: Request,
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> None:
    """Dependency FastAPI: valida Bearer token ou query param `token`."""
    valid = request.app.state.api_token
    provided: str | None = None

    if authorization and authorization.startswith("Bearer "):
        provided = authorization[7:]
    elif token:
        provided = token

    if provided is None or not secrets.compare_digest(provided, valid):
        raise HTTPException(status_code=401, detail="Token de autenticação inválido")
