"""
MITRA Backend — Webhooks Router

Endpoints:
  POST /api/v1/webhook/result  — n8n callback: receives automation results
  GET  /api/v1/webhook/status/{job_id}  — Poll n8n job status
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/webhook", tags=["webhooks"])

# In-memory job store (Phase 5 will persist to SQLite)
_job_results: dict[str, dict] = {}


class WebhookResult(BaseModel):
    job_id: str
    status: str
    data: dict | None = None
    error: str | None = None


@router.post("/result")
async def receive_webhook_result(result: WebhookResult) -> dict:
    """n8n calls this endpoint when an automation workflow completes."""
    _job_results[result.job_id] = result.model_dump()
    logger.info("webhook.result_received", job_id=result.job_id, status=result.status)
    return {"status": "received"}


@router.get("/status/{job_id}")
async def get_job_status(job_id: str) -> dict:
    """Poll the result of a previously triggered n8n job."""
    if job_id not in _job_results:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_results[job_id]
