"""
MITRA Backend — Connectors and Search Router (Phase 5)

Endpoints:
  GET  /api/v1/search/everything            — Hybrid search across Drive, OneDrive, Local Disk
  GET  /api/v1/connectors/google/inbox      — List Gmail inbox messages
  POST /api/v1/connectors/google/draft      — Create Gmail draft
  GET  /api/v1/connectors/google/calendar   — List Calendar events
  POST /api/v1/connectors/google/calendar   — Schedule Calendar event
  GET  /api/v1/connectors/google/drive      — Search Google Drive files
  GET  /api/v1/connectors/microsoft/mail    — List Outlook emails
  POST /api/v1/connectors/microsoft/meeting — Create Teams meeting
  GET  /api/v1/connectors/microsoft/onedrive— Search OneDrive files
  POST /api/v1/connectors/n8n/trigger       — Trigger n8n workflow template
"""
from __future__ import annotations

from typing import Any
import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.connectors.google import google_connector
from app.connectors.microsoft import microsoft_connector
from app.connectors.n8n import n8n_bridge, TemplateType
from app.connectors.search import search_engine

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["connectors"])


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@router.get("/search/everything")
async def search_everything_endpoint(
    q: str = Query(..., description="Natural language search query"),
    sources: list[str] | None = Query(None, description="Filter sources: google_drive, onedrive, local_disk, sharepoint"),
    top_k: int = Query(5, ge=1, le=50),
) -> dict[str, Any]:
    """Unified hybrid semantic search (BM25 + Cosine + RRF) across all storage sources."""
    results = search_engine.search_everything(query=q, sources=sources, top_k=top_k)
    return {"query": q, "count": len(results), "results": results}


# ---------------------------------------------------------------------------
# Google Workspace
# ---------------------------------------------------------------------------

class DraftEmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    in_reply_to: str | None = None
    thread_id: str | None = None


class CreateEventRequest(BaseModel):
    title: str
    start: str
    end: str
    attendees: list[str] = Field(default_factory=list)
    description: str = ""


@router.get("/connectors/google/inbox")
async def google_list_inbox(q: str = "", max_results: int = 10) -> dict[str, Any]:
    messages = await google_connector.list_inbox(query=q, max_results=max_results)
    return {"count": len(messages), "messages": messages}


@router.post("/connectors/google/draft")
async def google_draft_reply(req: DraftEmailRequest) -> dict[str, Any]:
    draft = await google_connector.draft_reply(
        to=req.to,
        subject=req.subject,
        body=req.body,
        in_reply_to=req.in_reply_to,
        thread_id=req.thread_id,
    )
    return {"status": "created", "draft": draft}


@router.get("/connectors/google/calendar")
async def google_list_events(max_results: int = 10) -> dict[str, Any]:
    events = await google_connector.list_events(max_results=max_results)
    return {"count": len(events), "events": events}


@router.post("/connectors/google/calendar")
async def google_create_event(req: CreateEventRequest) -> dict[str, Any]:
    event = await google_connector.create_event(
        title=req.title,
        start_time=req.start,
        end_time=req.end,
        attendees=req.attendees,
        description=req.description,
    )
    return {"status": "created", "event": event}


@router.get("/connectors/google/drive")
async def google_search_drive(q: str = Query(...), max_results: int = 10) -> dict[str, Any]:
    files = await google_connector.search_files(query=q, max_results=max_results)
    return {"count": len(files), "files": files}


# ---------------------------------------------------------------------------
# Microsoft 365
# ---------------------------------------------------------------------------

class CreateTeamsMeetingRequest(BaseModel):
    subject: str
    start: str
    end: str
    attendees: list[str] = Field(default_factory=list)


@router.get("/connectors/microsoft/mail")
async def ms_list_mail(q: str = "", top: int = 10) -> dict[str, Any]:
    messages = await microsoft_connector.list_mail(query=q, top=top)
    return {"count": len(messages), "messages": messages}


@router.post("/connectors/microsoft/meeting")
async def ms_create_meeting(req: CreateTeamsMeetingRequest) -> dict[str, Any]:
    meeting = await microsoft_connector.create_meeting(
        subject=req.subject,
        start_time=req.start,
        end_time=req.end,
        attendees=req.attendees,
        is_teams_meeting=True,
    )
    return {"status": "created", "meeting": meeting}


@router.get("/connectors/microsoft/onedrive")
async def ms_search_onedrive(q: str = Query(...), top: int = 10) -> dict[str, Any]:
    files = await microsoft_connector.search_files(query=q, top=top)
    return {"count": len(files), "files": files}


# ---------------------------------------------------------------------------
# n8n Automation Bridge
# ---------------------------------------------------------------------------

class N8nTriggerRequest(BaseModel):
    template: TemplateType
    payload: dict[str, Any]


@router.post("/connectors/n8n/trigger")
async def n8n_trigger_endpoint(req: N8nTriggerRequest) -> dict[str, Any]:
    job = await n8n_bridge.trigger(
        template=req.template,
        payload_data=req.payload,
    )
    return {"status": "success", "job": job}
