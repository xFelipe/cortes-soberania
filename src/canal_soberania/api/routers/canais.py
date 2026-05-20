"""Router: /canais"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from canal_soberania.api.auth import verify_token
from canal_soberania.api.deps import get_service
from canal_soberania.config import Canal
from canal_soberania.services.pipeline_service import PipelineService

router = APIRouter(prefix="/canais", tags=["canais"])


@router.get("", response_model=list[Canal])
def list_canais(
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> list[Canal]:
    return service.get_canais()


@router.post("", response_model=Canal, status_code=status.HTTP_201_CREATED)
def create_canal(
    canal: Canal,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> Canal:
    service.upsert_canal(canal)
    return canal


@router.put("/{canal_id}", response_model=Canal)
def update_canal(
    canal_id: str,
    canal: Canal,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> Canal:
    if canal.id != canal_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"canal_id no path ({canal_id}) difere do body ({canal.id})",
        )
    service.upsert_canal(canal)
    return canal


@router.patch("/{canal_id}/ativo")
def toggle_ativo(
    canal_id: str,
    body: dict[str, bool],
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, object]:
    ativo = body.get("ativo")
    if ativo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campo 'ativo' é obrigatório",
        )
    service.toggle_canal_ativo(canal_id, ativo)
    return {"canal_id": canal_id, "ativo": ativo}


@router.delete("/{canal_id}")
def delete_canal(
    canal_id: str,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, str]:
    service.delete_canal(canal_id)
    return {"status": "deleted", "canal_id": canal_id}
