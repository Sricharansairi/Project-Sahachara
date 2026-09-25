"""
MITRA Backend — Intelligence Router (Phase 5)

Endpoints:
  Ghost Follow-Up Radar:
    POST /api/v1/intelligence/ghost-radar/extract
    GET  /api/v1/intelligence/ghost-radar/commitments
    GET  /api/v1/intelligence/ghost-radar/alerts
    POST /api/v1/intelligence/ghost-radar/followup
    POST /api/v1/intelligence/ghost-radar/resolve/{id}
    POST /api/v1/intelligence/ghost-radar/snooze/{id}

  Meeting Guard:
    POST /api/v1/intelligence/meeting/audio-session
    GET  /api/v1/intelligence/meeting/status
    POST /api/v1/intelligence/meeting/dossier/{event_id}

  Intelligent Clipboard Augmenter:
    POST /api/v1/intelligence/clipboard/classify
    POST /api/v1/intelligence/clipboard/format-table
    POST /api/v1/intelligence/clipboard/summarize
    POST /api/v1/intelligence/clipboard/json

  10-Second Undo Action Buffer:
    POST /api/v1/intelligence/undo/rollback
    GET  /api/v1/intelligence/undo/action/{action_id}
"""
from __future__ import annotations

from typing import Any
import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.intelligence.ghost_radar import ghost_radar
from app.intelligence.meeting_guard import meeting_guard
from app.intelligence.clipboard import clipboard_augmenter
from app.intelligence.undo_buffer import undo_buffer

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])


# ---------------------------------------------------------------------------
# Ghost Follow-Up Radar
# ---------------------------------------------------------------------------

class ExtractCommitmentsRequest(BaseModel):
    text: str
    party: str
    is_sent_by_user: bool = False
    message_id: str | None = None


class FollowupDraftRequest(BaseModel):
    commitment_id: str


@router.post("/ghost-radar/extract")
async def extract_commitments(req: ExtractCommitmentsRequest) -> dict[str, Any]:
    records = ghost_radar.extract_commitments_from_text(
        text=req.text,
        party=req.party,
        is_sent_by_user=req.is_sent_by_user,
        message_id=req.message_id,
    )
    return {"count": len(records), "commitments": [r.to_dict() for r in records]}


@router.get("/ghost-radar/commitments")
async def get_commitments(direction: str | None = None) -> dict[str, Any]:
    items = ghost_radar.get_commitments(direction=direction)  # type: ignore
    return {"count": len(items), "commitments": items}


@router.get("/ghost-radar/alerts")
async def get_deadline_alerts(target_window_minutes: float = 60.0) -> dict[str, Any]:
    alerts = ghost_radar.check_deadline_alerts(target_window_minutes=target_window_minutes)
    return {"count": len(alerts), "alerts": alerts}


@router.post("/ghost-radar/followup")
async def create_followup_draft(req: FollowupDraftRequest) -> dict[str, Any]:
    try:
        draft = ghost_radar.generate_followup_draft(req.commitment_id)
        return {"status": "success", "draft": draft}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/ghost-radar/resolve/{commitment_id}")
async def resolve_commitment(commitment_id: str) -> dict[str, Any]:
    success = ghost_radar.mark_resolved(commitment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Commitment not found")
    return {"status": "resolved", "commitment_id": commitment_id}


@router.post("/ghost-radar/snooze/{commitment_id}")
async def snooze_commitment(commitment_id: str, minutes: int = 120) -> dict[str, Any]:
    success = ghost_radar.snooze(commitment_id, minutes=minutes)
    if not success:
        raise HTTPException(status_code=404, detail="Commitment not found")
    return {"status": "snoozed", "commitment_id": commitment_id, "minutes": minutes}


# ---------------------------------------------------------------------------
# Meeting Guard
# ---------------------------------------------------------------------------

class AudioSessionEvent(BaseModel):
    process_name: str
    has_audio: bool


@router.post("/meeting/audio-session")
async def meeting_audio_session_event(event: AudioSessionEvent) -> dict[str, Any]:
    result = meeting_guard.on_audio_session_changed(
        process_name=event.process_name,
        has_audio=event.has_audio,
    )
    return result


@router.get("/meeting/status")
async def meeting_status() -> dict[str, Any]:
    return {
        "is_meeting_active": meeting_guard._is_meeting_active,
        "detected_app": meeting_guard._detected_app,
        "is_ducked": meeting_guard.is_ducked(),
    }


@router.post("/meeting/dossier/{event_id}")
async def generate_meeting_dossier(event_id: str) -> dict[str, Any]:
    dossier = await meeting_guard.generate_dossier(event_id)
    return {"status": "success", "dossier": dossier}


# ---------------------------------------------------------------------------
# Intelligent Clipboard Augmenter
# ---------------------------------------------------------------------------

class ClipboardTextRequest(BaseModel):
    content: str


@router.post("/clipboard/classify")
async def classify_clipboard(req: ClipboardTextRequest) -> dict[str, Any]:
    classification = clipboard_augmenter.classify(req.content)
    return {"classification": classification}


@router.post("/clipboard/format-table")
async def format_table_clipboard(req: ClipboardTextRequest) -> dict[str, Any]:
    result = clipboard_augmenter.clean_and_format_table(req.content)
    return result


@router.post("/clipboard/summarize")
async def summarize_clipboard(req: ClipboardTextRequest) -> dict[str, Any]:
    result = clipboard_augmenter.summarize_to_bullets(req.content)
    return result


@router.post("/clipboard/json")
async def json_clipboard(req: ClipboardTextRequest) -> dict[str, Any]:
    result = clipboard_augmenter.convert_to_json(req.content)
    return result


# ---------------------------------------------------------------------------
# 10-Second Undo Action Buffer
# ---------------------------------------------------------------------------

class RollbackRequest(BaseModel):
    action_id: str | None = None


@router.post("/undo/rollback")
async def undo_rollback_action(req: RollbackRequest = RollbackRequest()) -> dict[str, Any]:
    result = await undo_buffer.rollback(action_id=req.action_id)
    if result.get("status") == "expired":
        return result
    elif result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="No action found to undo")
    return result


@router.get("/undo/action/{action_id}")
async def get_undo_action(action_id: str) -> dict[str, Any]:
    action = undo_buffer.get_action(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return action
