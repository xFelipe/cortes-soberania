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


@router.get("/by-canal")
def get_stats_by_canal(
    request: Request,
    _: None = Depends(verify_token),
) -> list[dict[str, object]]:
    """Estatísticas agregadas por canal: vídeos, aprovados, clips gerados, clips publicados."""
    conn = request.app.state.conn
    rows = conn.execute(
        """
        SELECT
            v.canal_id,
            COUNT(DISTINCT v.video_id)                                          AS total_videos,
            COUNT(DISTINCT CASE WHEN v.status IN (
                'approved_for_clips','finding_clips','clips_found'
            ) THEN v.video_id END)                                              AS videos_aprovados,
            COUNT(DISTINCT c.clip_id)                                           AS clips_gerados,
            COUNT(DISTINCT CASE WHEN c.status IN (
                'uploaded_youtube','scheduled_youtube','uploaded_tiktok',
                'pending_tiktok_manual'
            ) THEN c.clip_id END)                                               AS clips_publicados
        FROM videos v
        LEFT JOIN clips c ON c.video_id = v.video_id
        GROUP BY v.canal_id
        ORDER BY total_videos DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


@router.get("/throughput")
def get_stats_throughput(
    request: Request,
    _: None = Depends(verify_token),
) -> list[dict[str, object]]:
    """Throughput semanal das últimas 4 semanas: vídeos, clips criados, clips publicados."""
    conn = request.app.state.conn
    rows = conn.execute(
        """
        SELECT
            strftime('%Y-%W', v.created_at)                                     AS semana,
            COUNT(DISTINCT v.video_id)                                          AS videos_descobertos,
            COUNT(DISTINCT c.clip_id)                                           AS clips_criados,
            COUNT(DISTINCT CASE WHEN c.status IN (
                'uploaded_youtube','scheduled_youtube','uploaded_tiktok',
                'pending_tiktok_manual'
            ) THEN c.clip_id END)                                               AS clips_publicados
        FROM videos v
        LEFT JOIN clips c ON c.video_id = v.video_id
        WHERE v.created_at >= datetime('now', '-28 days')
        GROUP BY semana
        ORDER BY semana ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]
