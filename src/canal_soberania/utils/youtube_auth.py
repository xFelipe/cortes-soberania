"""Helper de autenticação OAuth para a YouTube Data API v3.

Usado tanto pelo stage de upload quanto pelo de sync, para evitar duplicação
e permitir que ambos compartilhem o mesmo token OAuth em disco.
"""

from __future__ import annotations

from pathlib import Path

# Escopos necessários:
#   youtube.upload  — permite fazer upload de vídeos
#   youtube.readonly — permite listar e consultar status de vídeos próprios
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def get_youtube_service(client_secrets_path: Path, token_path: Path) -> object:
    """Retorna um serviço autenticado da YouTube Data API v3.

    No primeiro uso (ou quando o token não cobre os escopos necessários) abre
    o browser para autorização OAuth e salva o token em disco.
    """
    from google.auth.transport.requests import Request  # type: ignore[import-untyped]
    from google.oauth2.credentials import Credentials  # type: ignore[import-untyped]
    from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]
    from googleapiclient.discovery import build  # type: ignore[import-untyped]

    creds: Credentials | None = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secrets_path), YOUTUBE_SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=creds)
