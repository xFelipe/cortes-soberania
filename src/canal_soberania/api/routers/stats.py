"""Router: /stats"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from canal_soberania.api.auth import verify_token
from canal_soberania.api.deps import get_service
from canal_soberania.services.pipeline_service import PipelineService

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/summary")
def get_summary(
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, int]:
    return service.get_status_summary()


@router.get("/costs")
def get_costs(
    request: Request,
    _: None = Depends(verify_token),
) -> dict[str, float]:
    service: PipelineService = request.app.state.service
    return {"total_usd": service.get_monthly_cost()}


@router.get("/costs/detail")
def get_costs_detail(
    request: Request,
    _: None = Depends(verify_token),
) -> list[dict[str, object]]:
    """Retorna custo detalhado por data/provider/model (últimos 30 dias)."""
    conn = request.app.state.conn
    rows = conn.execute(
        """SELECT date, provider, model, tokens_in, tokens_out, requests, cost_usd
           FROM api_costs ORDER BY date DESC LIMIT 90"""
    ).fetchall()
    return [dict(row) for row in rows]
