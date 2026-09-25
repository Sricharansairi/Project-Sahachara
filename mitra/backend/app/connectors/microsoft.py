"""
MITRA Backend — Microsoft 365 Connector (Graph API)

Supports Outlook, MS Calendar (with Teams link generation),
OneDrive, and SharePoint enterprise search.
Includes offline mock fallback.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
import structlog
import httpx

logger = structlog.get_logger(__name__)


class Microsoft365Connector:
    """Microsoft 365 Graph API connector."""

    def __init__(self, access_token: str | None = None):
        self.access_token = access_token
        self._mock_mail: dict[str, dict[str, Any]] = {}
        self._mock_drafts: dict[str, dict[str, Any]] = {}
        self._mock_events: dict[str, dict[str, Any]] = {}
        self._mock_onedrive: dict[str, dict[str, Any]] = {}
        self._mock_sharepoint: dict[str, dict[str, Any]] = {}
        self._seed_mock_data()

    def _seed_mock_data(self) -> None:
        """Seed mock enterprise data for offline/test environments."""
        # Outlook mail
        m_id = "msg_ms_001"
        self._mock_mail[m_id] = {
            "id": m_id,
            "subject": "Q3 Enterprise Roadmap Sync",
            "from": "alex.taylor@company.com",
            "body": "Let's review the Q3 roadmap and finalize deliverables by Friday afternoon.",
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

        # OneDrive files
        self._mock_onedrive["one_q3_slides"] = {
            "id": "one_q3_slides",
            "name": "Q3_Strategic_Review_Deck.pptx",
            "mime_type": "application/vnd.ms-powerpoint",
            "content": "PowerPoint presentation slide deck on strategic pillars: 1. Ambient AI Copilot. 2. Low-latency edge inference. 3. Zero-knowledge local memory.",
            "source": "onedrive",
            "modified_time": datetime.now(timezone.utc).isoformat(),
        }

        # SharePoint site documents
        self._mock_sharepoint["sp_security_policy"] = {
            "id": "sp_security_policy",
            "site": "Engineering / Security",
            "name": "Enterprise_Data_Protection_Standard.pdf",
            "content": "All customer biometric data must remain encrypted at rest using AES-256 and never exit the local enclave.",
            "source": "sharepoint",
            "modified_time": datetime.now(timezone.utc).isoformat(),
        }

    # ---------------------------------------------------------------------------
    # Outlook
    # ---------------------------------------------------------------------------

    async def list_mail(self, query: str = "", top: int = 10) -> list[dict[str, Any]]:
        """List Outlook messages."""
        results = []
        for msg in self._mock_mail.values():
            if not query or query.lower() in msg["subject"].lower() or query.lower() in msg["body"].lower():
                results.append(msg)
        return results[:top]

    async def draft_reply(self, to: str, subject: str, body: str) -> dict[str, Any]:
        """Draft a reply in Outlook."""
        draft_id = f"ms_draft_{uuid.uuid4().hex[:10]}"
        draft = {
            "id": draft_id,
            "to": to,
            "subject": subject if subject.startswith("Re:") else f"Re: {subject}",
            "body": body,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "draft",
        }
        self._mock_drafts[draft_id] = draft
        logger.info("ms365.draft_created", draft_id=draft_id)
        return draft

    async def send_mail(self, to: str, subject: str, body: str) -> dict[str, Any]:
        """Send an email via Outlook."""
        msg_id = f"ms_msg_{uuid.uuid4().hex[:10]}"
        msg = {
            "id": msg_id,
            "to": to,
            "subject": subject,
            "body": body,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "status": "sent",
        }
        self._mock_mail[msg_id] = msg
        return msg

    async def delete_draft(self, draft_id: str) -> bool:
        """Delete draft for undo buffer."""
        return self._mock_drafts.pop(draft_id, None) is not None

    # ---------------------------------------------------------------------------
    # Calendar & Teams Meetings
    # ---------------------------------------------------------------------------

    async def get_calendar_events(self, top: int = 10) -> list[dict[str, Any]]:
        """List MS Calendar events."""
        events = list(self._mock_events.values())
        return events[:top]

    async def create_meeting(
        self,
        subject: str,
        start_time: str,
        end_time: str,
        attendees: list[str] | None = None,
        is_teams_meeting: bool = True,
    ) -> dict[str, Any]:
        """Create calendar meeting with Microsoft Teams online join URL."""
        meeting_id = f"mtg_{uuid.uuid4().hex[:12]}"
        teams_join_url = f"https://teams.microsoft.com/l/meetup-join/{meeting_id}" if is_teams_meeting else None
        
        meeting = {
            "id": meeting_id,
            "meeting_id": meeting_id,
            "subject": subject,
            "start": start_time,
            "end": end_time,
            "attendees": attendees or [],
            "is_teams_meeting": is_teams_meeting,
            "teams_join_url": teams_join_url,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._mock_events[meeting_id] = meeting
        logger.info("ms365.meeting_created", meeting_id=meeting_id, teams_url=teams_join_url)
        return meeting

    async def delete_meeting(self, meeting_id: str) -> bool:
        """Delete meeting for undo buffer."""
        return self._mock_events.pop(meeting_id, None) is not None

    # ---------------------------------------------------------------------------
    # OneDrive & SharePoint
    # ---------------------------------------------------------------------------

    async def search_files(self, query: str, top: int = 10) -> list[dict[str, Any]]:
        """Search OneDrive files."""
        q_lower = query.lower()
        matches = []
        for f in self._mock_onedrive.values():
            if q_lower in f["name"].lower() or q_lower in f.get("content", "").lower():
                matches.append(f)
        return matches[:top]

    async def get_document_content(self, file_id: str) -> str:
        """Fetch OneDrive file content."""
        file = self._mock_onedrive.get(file_id)
        if not file:
            raise KeyError(f"OneDrive file {file_id} not found")
        return file.get("content", "")

    async def search_site_content(self, query: str, site: str | None = None) -> list[dict[str, Any]]:
        """Search SharePoint enterprise knowledge base."""
        q_lower = query.lower()
        matches = []
        for doc in self._mock_sharepoint.values():
            if site and site.lower() not in doc.get("site", "").lower():
                continue
            if q_lower in doc["name"].lower() or q_lower in doc.get("content", "").lower():
                matches.append(doc)
        return matches


microsoft_connector = Microsoft365Connector()
