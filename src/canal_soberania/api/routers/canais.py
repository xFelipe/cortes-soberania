"""Router: /canais"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from canal_soberania.api.auth import verify_token
from canal_soberania.config import Canal

router = APIRouter(prefix="/canais", tags=["canais"])


@router.get("", response_model=list[Canal])
def list_canais(
    request: Request,
    _: None = Depends(verify_token),
) -> list[Canal]:
    canais_cfg = request.app.state.canais_cfg
    return canais_cfg.canais  # type: ignore[no-any-return]
