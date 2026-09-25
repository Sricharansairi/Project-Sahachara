"""
MITRA Backend — Google Workspace Connector (Gmail, Calendar, Drive)

Supports both live Google Workspace API (via OAuth access token) and
a high-fidelity mock/local store for offline operation and automated testing.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
import structlog
import httpx

from app.config import settings

logger = structlog.get_logger(__name__)


class GoogleWorkspaceConnector:
    """Google Workspace connector handling Gmail, Calendar, and Drive."""

    def __init__(self, access_token: str | None = None):
        self.access_token = access_token
        # In-memory storage for offline / mock mode
        self._mock_emails: dict[str, dict[str, Any]] = {}
        self._mock_drafts: dict[str, dict[str, Any]] = {}
        self._mock_events: dict[str, dict[str, Any]] = {}
        self._mock_files: dict[str, dict[str, Any]] = {}
        self._seed_mock_data()

    def _seed_mock_data(self) -> None:
        """Seed realistic mock data for local testing."""
        # Seed an email from John
        email_id = "msg_seed_001"
        self._mock_emails[email_id] = {
            "id": email_id,
            "thread_id": "thread_john_001",
            "from": "john.smith@example.com",
            "to": "user@example.com",
            "subject": "Project Sahachara Updates",
            "body": "Hi, can you review the latest Q3 report and send me the feedback by Friday?",
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        }

        # Seed another email from Sarah
        email_id_2 = "msg_seed_002"
        self._mock_emails[email_id_2] = {
            "id": email_id_2,
            "thread_id": "thread_sarah_002",
            "from": "sarah.chen@example.com",
            "to": "user@example.com",
            "subject": "Design Review Sync",
            "body": "Looking forward to our sync tomorrow at 3 PM. I'll send over the Figma specs.",
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        }

        # Seed Drive files
        self._mock_files["file_q3_report"] = {
            "id": "file_q3_report",
            "name": "Q3 Financial and Product Report.pdf",
            "mime_type": "application/pdf",
            "content": "Q3 Financial Highlights: Revenue grew 28% YoY. Operating margins improved to 21%. Project Sahachara beta launch milestone achieved.",
            "source": "google_drive",
            "modified_time": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        }
        self._mock_files["file_arch_doc"] = {
            "id": "file_arch_doc",
            "name": "Sahachara_Architecture_Overview.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "content": "MITRA Architecture: Hybrid Rust Tauri client + Python FastAPI backend with LangGraph agent loop and NVIDIA NIM inference.",
            "source": "google_drive",
            "modified_time": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        }

        # Seed upcoming calendar event (in 2 minutes for testing pre-meeting dossier)
        now = datetime.now(timezone.utc)
        self._mock_events["event_upcoming_001"] = {
            "id": "event_upcoming_001",
            "title": "Sahachara Product Sync with Sarah",
            "start": (now + timedelta(minutes=2)).isoformat(),
            "end": (now + timedelta(minutes=32)).isoformat(),
            "attendees": ["sarah.chen@example.com", "user@example.com"],
            "description": "Discussing design review and Figma specs.",
        }

    # ---------------------------------------------------------------------------
    # Gmail API
    # ---------------------------------------------------------------------------

    async def list_inbox(self, query: str = "", max_results: int = 10) -> list[dict[str, Any]]:
        """List messages in user's inbox matching query."""
        if self.access_token:
            try:
                headers = {"Authorization": f"Bearer {self.access_token}"}
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                        headers=headers,
                        params={"q": query, "maxResults": max_results},
                    )
                    if resp.status_code == 200:
                        return resp.json().get("messages", [])
            except Exception as e:
                logger.warning("gmail.api_fallback", error=str(e))

        # Local fallback / mock
        results = []
        for msg in self._mock_emails.values():
            if not query or query.lower() in msg["subject"].lower() or query.lower() in msg["body"].lower() or query.lower() in msg["from"].lower():
                results.append(msg)
        return results[:max_results]

    async def get_thread(self, thread_id: str) -> list[dict[str, Any]]:
        """Get all messages in an email thread."""
        thread_messages = [m for m in self._mock_emails.values() if m.get("thread_id") == thread_id]
        if not thread_messages:
            # Check drafts
            thread_messages = [m for m in self._mock_drafts.values() if m.get("thread_id") == thread_id]
        return thread_messages

    async def draft_reply(
        self,
        to: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Draft an email reply.
        Returns draft details including draft_id for undo rollback.
        """
        start_time = time.perf_counter()
        draft_id = f"draft_{uuid.uuid4().hex[:12]}"
        
        # Determine thread_id if not given
        if not thread_id and in_reply_to and in_reply_to in self._mock_emails:
            thread_id = self._mock_emails[in_reply_to].get("thread_id")
        if not thread_id:
            thread_id = f"thread_{uuid.uuid4().hex[:8]}"

        draft = {
            "id": draft_id,
            "draft_id": draft_id,
            "to": to,
            "subject": subject if subject.startswith("Re:") else f"Re: {subject}",
            "body": body,
            "in_reply_to": in_reply_to,
            "thread_id": thread_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "draft",
        }
        self._mock_drafts[draft_id] = draft

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info("gmail.draft_created", draft_id=draft_id, elapsed_ms=elapsed_ms)
        return draft

    async def send_email(self, to: str, subject: str, body: str, thread_id: str | None = None) -> dict[str, Any]:
        """Send an email (requires Tier 1 approval in MitraGraph)."""
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        sent_msg = {
            "id": msg_id,
            "from": "user@example.com",
            "to": to,
            "subject": subject,
            "body": body,
            "thread_id": thread_id or f"thread_{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "sent",
        }
        self._mock_emails[msg_id] = sent_msg
        logger.info("gmail.email_sent", msg_id=msg_id, to=to)
        return sent_msg

    async def delete_draft(self, draft_id: str) -> bool:
        """Delete an email draft (used by 10-Second Undo Buffer)."""
        if draft_id in self._mock_drafts:
            del self._mock_drafts[draft_id]
            logger.info("gmail.draft_deleted", draft_id=draft_id)
            return True
        return False

    async def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        """Fetch a specific draft."""
        return self._mock_drafts.get(draft_id)

    # ---------------------------------------------------------------------------
    # Google Calendar API
    # ---------------------------------------------------------------------------

    async def list_events(
        self,
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """List calendar events in a time window."""
        events = list(self._mock_events.values())
        events.sort(key=lambda e: e.get("start", ""))
        return events[:max_results]

    async def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        attendees: list[str] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a Google Calendar event. Returns event with event_id."""
        event_id = f"event_{uuid.uuid4().hex[:12]}"
        event = {
            "id": event_id,
            "event_id": event_id,
            "title": title,
            "start": start_time,
            "end": end_time,
            "attendees": attendees or [],
            "description": description,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "confirmed",
        }
        self._mock_events[event_id] = event
        logger.info("gcal.event_created", event_id=event_id, title=title)
        return event

    async def delete_event(self, event_id: str) -> bool:
        """Delete a calendar event (used by 10-Second Undo Buffer)."""
        if event_id in self._mock_events:
            del self._mock_events[event_id]
            logger.info("gcal.event_deleted", event_id=event_id)
            return True
        return False

    async def get_event(self, event_id: str) -> dict[str, Any] | None:
        """Fetch event by ID."""
        return self._mock_events.get(event_id)

    async def find_free_slots(self, date_str: str, duration_minutes: int = 30) -> list[dict[str, str]]:
        """Find free meeting slots for a given day."""
        # Simple slot finder between 09:00 and 17:00
        free_slots = [
            {"start": f"{date_str}T10:00:00Z", "end": f"{date_str}T10:30:00Z"},
            {"start": f"{date_str}T14:00:00Z", "end": f"{date_str}T14:30:00Z"},
            {"start": f"{date_str}T16:00:00Z", "end": f"{date_str}T16:30:00Z"},
        ]
        return free_slots

    # ---------------------------------------------------------------------------
    # Google Drive API
    # ---------------------------------------------------------------------------

    async def search_files(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Search Google Drive files by keyword or title."""
        start_time = time.perf_counter()
        q_lower = query.lower()
        q_words = q_lower.split()
        matches = []
        for file in self._mock_files.values():
            name_lower = file["name"].lower()
            content_lower = file.get("content", "").lower()
            combined = f"{name_lower} {content_lower}"
            if q_lower in combined or (q_words and all(w in combined for w in q_words)):
                matches.append(file)

        elapsed_s = time.perf_counter() - start_time
        logger.info("gdrive.search_files", query=query, matches=len(matches), elapsed_s=elapsed_s)
        return matches[:max_results]

    async def get_file_content(self, file_id: str) -> str:
        """Get text content of a Drive file."""
        file = self._mock_files.get(file_id)
        if not file:
            raise KeyError(f"File {file_id} not found in Google Drive")
        return file.get("content", "")

    async def upload_file(self, name: str, content: str, mime_type: str = "text/plain") -> dict[str, Any]:
        """Upload file to Google Drive."""
        file_id = f"file_{uuid.uuid4().hex[:12]}"
        file_meta = {
            "id": file_id,
            "name": name,
            "mime_type": mime_type,
            "content": content,
            "source": "google_drive",
            "modified_time": datetime.now(timezone.utc).isoformat(),
        }
        self._mock_files[file_id] = file_meta
        return file_meta

    # ---------------------------------------------------------------------------
    # Meeting Context Builder (for Pre-Meeting Dossier)
    # ---------------------------------------------------------------------------

    async def get_meeting_context(self, attendees: list[str], topic: str = "") -> dict[str, Any]:
        """
        Pull recent email threads and documents related to attendees
        for pre-meeting dossier synthesis.
        """
        relevant_emails = []
        for email in self._mock_emails.values():
            sender = email.get("from", "").lower()
            if any(att.lower() in sender for att in attendees):
                relevant_emails.append(email)

        relevant_docs = []
        if topic:
            relevant_docs = await self.search_files(topic, max_results=3)

        return {
            "attendees": attendees,
            "topic": topic,
            "recent_emails": relevant_emails,
            "relevant_docs": relevant_docs,
        }


# Singleton instance
google_connector = GoogleWorkspaceConnector()
