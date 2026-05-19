"""Geração e verificação de token de autenticação da API local."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import Header, HTTPException, Query, Request


_TOKEN_FILE = ".api_token"


def get_or_create_token(data_dir: Path) -> str:
    """Retorna o token da API, criando um novo se não existir."""
    token_path = data_dir / _TOKEN_FILE
    if token_path.exists():
        token = token_path.read_text().strip()
        if token:
            return token
    token = secrets.token_hex(24)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token)
    os.chmod(token_path, 0o600)
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
