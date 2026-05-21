"""Router: /output-canais"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from canal_soberania.api.auth import verify_token
from canal_soberania.api.deps import get_service
from canal_soberania.config import OutputCanal
from canal_soberania.services.pipeline_service import PipelineService

router = APIRouter(prefix="/output-canais", tags=["output-canais"])


@router.get("", response_model=list[OutputCanal])
def list_output_canais(
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> list[OutputCanal]:
    return service.get_output_canais()


@router.post("", response_model=OutputCanal, status_code=status.HTTP_201_CREATED)
def create_output_canal(
    canal: OutputCanal,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> OutputCanal:
    service.upsert_output_canal(canal)
    return canal


@router.get("/{canal_id}", response_model=OutputCanal)
def get_output_canal(
    canal_id: str,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> OutputCanal:
    result = service.get_output_canal(canal_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Output canal '{canal_id}' não encontrado")
    return OutputCanal.model_validate(result)


@router.put("/{canal_id}", response_model=OutputCanal)
def update_output_canal(
    canal_id: str,
    canal: OutputCanal,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> OutputCanal:
    if canal.id != canal_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"canal_id no path ({canal_id}) difere do body ({canal.id})",
        )
    service.upsert_output_canal(canal)
    return canal


@router.delete("/{canal_id}")
def delete_output_canal(
    canal_id: str,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, str]:
    service.delete_output_canal(canal_id)
    return {"status": "deleted", "canal_id": canal_id}


@router.get("/{canal_id}/fontes", response_model=list[str])
def get_fontes(
    canal_id: str,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> list[str]:
    return service.get_output_canal_fontes(canal_id)


@router.put("/{canal_id}/fontes", response_model=list[str])
def set_fontes(
    canal_id: str,
    fontes: list[str],
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> list[str]:
    service.set_output_canal_fontes(canal_id, fontes)
    return fontes
