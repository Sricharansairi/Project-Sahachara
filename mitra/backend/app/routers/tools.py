"""
MITRA Backend — Tools Router

Endpoints:
  POST /api/v1/tools/execute  — Execute an approved Tier-1 tool action
  POST /api/v1/tools/approve  — Approve a pending action
  POST /api/v1/tools/reject   — Reject a pending action
"""
from __future__ import annotations

import json
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class ToolExecuteRequest(BaseModel):
    action_type: str = Field(..., description="draft_email | create_calendar | trigger_n8n")
    payload: dict = Field(..., description="Tool-specific payload from approval gate")
    approved: bool = Field(default=False)


class ToolExecuteResponse(BaseModel):
    status: str
    action_type: str
    result: dict | None = None
    message: str = ""


@router.post("/execute", response_model=ToolExecuteResponse)
async def execute_tool(req: ToolExecuteRequest) -> ToolExecuteResponse:
    """
    Execute an approved Tier-1 tool action.
    The frontend must have received an approval gate event and user confirmed.
    """
    if not req.approved:
        raise HTTPException(status_code=403, detail="Tool execution requires explicit approval")

    logger.info("tools.execute", action_type=req.action_type)

    if req.action_type == "draft_email":
        # In Phase 5 this will call Google/MS connector
        # For now: return stub confirming receipt
        return ToolExecuteResponse(
            status="accepted",
            action_type="draft_email",
            result=req.payload,
            message="Email draft queued for connector (Phase 5)",
        )
    elif req.action_type == "create_calendar":
        return ToolExecuteResponse(
            status="accepted",
            action_type="create_calendar",
            result=req.payload,
            message="Calendar event queued for connector (Phase 5)",
        )
    elif req.action_type == "trigger_n8n":
        return ToolExecuteResponse(
            status="accepted",
            action_type="trigger_n8n",
            result=req.payload,
            message="n8n webhook queued (Phase 5)",
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action_type: {req.action_type}")


@router.post("/approve")
async def approve_action(action_type: str, payload: dict) -> dict:
    """Approve and immediately execute a pending action."""
    req = ToolExecuteRequest(action_type=action_type, payload=payload, approved=True)
    result = await execute_tool(req)
    return {"status": "approved", "result": result.model_dump()}


@router.post("/reject")
async def reject_action(action_type: str) -> dict:
    """Reject a pending action — no side effects."""
    logger.info("tools.rejected", action_type=action_type)
    return {"status": "rejected", "action_type": action_type}
