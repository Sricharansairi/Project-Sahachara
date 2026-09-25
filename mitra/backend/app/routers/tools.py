"""
MITRA Backend — Tools Router (Phase 5 — Connectors, Undo Buffer, Safety)

Endpoints:
  POST /api/v1/tools/execute  — Execute an approved Tier-1 tool action (with NemoGuard safety & Undo Buffer)
  POST /api/v1/tools/approve  — Approve and execute a pending action
  POST /api/v1/tools/reject   — Reject a pending action
"""
from __future__ import annotations

import json
from typing import Any
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.safety import classify_input
from app.connectors.google import google_connector
from app.connectors.microsoft import microsoft_connector
from app.connectors.n8n import n8n_bridge
from app.intelligence.undo_buffer import undo_buffer

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class ToolExecuteRequest(BaseModel):
    action_type: str = Field(..., description="draft_email | create_calendar | trigger_n8n | jira_ticket")
    payload: dict = Field(..., description="Tool-specific payload from approval gate")
    approved: bool = Field(default=False)


class ToolExecuteResponse(BaseModel):
    status: str
    action_type: str
    result: dict | None = None
    message: str = ""
    action_id: str | None = None
    undo_window_seconds: float = 10.0


@router.post("/execute", response_model=ToolExecuteResponse)
async def execute_tool(req: ToolExecuteRequest) -> ToolExecuteResponse:
    """
    Execute an approved Tier-1 tool action.
    Validates input through NemoGuard safety (P5-T14).
    Registers the executed action in the 10-Second Undo Buffer (P5-T11, P5-T12).
    """
    if not req.approved:
        raise HTTPException(status_code=403, detail="Tool execution requires explicit approval")

    # Safety check on payload contents (P5-T14: Safety on connectors)
    payload_str = json.dumps(req.payload)
    is_safe, reason = await classify_input(payload_str)
    if not is_safe:
        logger.warning("tools.safety_blocked", action_type=req.action_type, reason=reason)
        raise HTTPException(
            status_code=403,
            detail=f"Security Alert: NemoGuard blocked tool execution due to malicious content: {reason}",
        )

    logger.info("tools.execute", action_type=req.action_type)

    if req.action_type == "draft_email":
        to = req.payload.get("to", "recipient@example.com")
        subject = req.payload.get("subject", "Follow up")
        body = req.payload.get("body", "")
        thread_id = req.payload.get("thread_id")

        draft = await google_connector.draft_reply(
            to=to,
            subject=subject,
            body=body,
            thread_id=thread_id,
        )

        # Register in 10-Second Undo Buffer
        undo_record = undo_buffer.register_action(
            action_type="draft_email",
            payload=req.payload,
            rollback_meta={"draft_id": draft["id"], "provider": "google"},
            window_seconds=10.0,
        )

        return ToolExecuteResponse(
            status="accepted",
            action_type="draft_email",
            result=draft,
            message="Email draft created successfully in Gmail",
            action_id=undo_record.action_id,
            undo_window_seconds=10.0,
        )

    elif req.action_type == "create_calendar":
        title = req.payload.get("title", "New Meeting")
        start = req.payload.get("start", "")
        end = req.payload.get("end", "")
        attendees = req.payload.get("attendees", [])
        description = req.payload.get("description", "")

        event = await google_connector.create_event(
            title=title,
            start_time=start,
            end_time=end,
            attendees=attendees,
            description=description,
        )

        # Register in 10-Second Undo Buffer
        undo_record = undo_buffer.register_action(
            action_type="create_calendar",
            payload=req.payload,
            rollback_meta={"event_id": event["id"], "provider": "google"},
            window_seconds=10.0,
        )

        return ToolExecuteResponse(
            status="completed",
            action_type="create_calendar",
            result=event,
            message="Calendar event scheduled successfully",
            action_id=undo_record.action_id,
            undo_window_seconds=10.0,
        )

    elif req.action_type == "trigger_n8n":
        template = req.payload.get("template", "slack_notification")
        job = await n8n_bridge.trigger(
            template=template,
            payload_data=req.payload,
        )

        undo_record = undo_buffer.register_action(
            action_type="trigger_n8n",
            payload=req.payload,
            rollback_meta={"job_id": job["job_id"]},
            window_seconds=10.0,
        )

        return ToolExecuteResponse(
            status="completed",
            action_type="trigger_n8n",
            result=job,
            message=f"n8n workflow '{template}' triggered successfully",
            action_id=undo_record.action_id,
            undo_window_seconds=10.0,
        )

    elif req.action_type == "jira_ticket":
        job = await n8n_bridge.trigger(
            template="jira_ticket",
            payload_data=req.payload,
        )

        undo_record = undo_buffer.register_action(
            action_type="jira_ticket",
            payload=req.payload,
            rollback_meta={"job_id": job["job_id"]},
            window_seconds=10.0,
        )

        return ToolExecuteResponse(
            status="completed",
            action_type="jira_ticket",
            result=job,
            message="Jira ticket created successfully via n8n",
            action_id=undo_record.action_id,
            undo_window_seconds=10.0,
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
