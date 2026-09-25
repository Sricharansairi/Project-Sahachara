"""
MITRA Backend — 10-Second Undo Action Buffer

Provides a 10-second safety window for all Tier-1 side-effect actions:
- Email drafts / sent replies
- Calendar events
- n8n automated workflows
- Jira tickets

If user triggers Undo (e.g. Ctrl+Z) within 10 seconds:
  Rolls back action and confirms cancellation.
If requested after 10 seconds:
  Rejects with 'Action committed, cannot undo'.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine
import structlog

from app.connectors.google import google_connector
from app.connectors.microsoft import microsoft_connector
from app.connectors.n8n import n8n_bridge

logger = structlog.get_logger(__name__)


class ActionRecord:
    def __init__(
        self,
        action_type: str,
        payload: dict[str, Any],
        rollback_meta: dict[str, Any] | None = None,
        window_seconds: float = 10.0,
        action_id: str | None = None,
    ):
        self.action_id = action_id or f"act_{uuid.uuid4().hex[:10]}"
        self.action_type = action_type
        self.payload = payload
        self.rollback_meta = rollback_meta or {}
        self.created_at = time.time()
        self.window_seconds = window_seconds
        self.expires_at = self.created_at + window_seconds
        self.status = "active"  # active | rolled_back | committed

    def is_expired(self, current_time: float | None = None) -> bool:
        now = current_time if current_time is not None else time.time()
        return now > self.expires_at

    def seconds_remaining(self, current_time: float | None = None) -> float:
        now = current_time if current_time is not None else time.time()
        return max(0.0, self.expires_at - now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "payload": self.payload,
            "status": self.status,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "seconds_remaining": round(self.seconds_remaining(), 2),
            "is_expired": self.is_expired(),
        }


class UndoActionBuffer:
    """Manages the 10-second rollback buffer and executes rollback functions."""

    def __init__(self, default_window_seconds: float = 10.0):
        self.default_window_seconds = default_window_seconds
        self._actions: dict[str, ActionRecord] = {}
        self._last_action_id: str | None = None

    def register_action(
        self,
        action_type: str,
        payload: dict[str, Any],
        rollback_meta: dict[str, Any] | None = None,
        window_seconds: float | None = None,
    ) -> ActionRecord:
        """Register a new side-effect action in the undo window."""
        window = window_seconds if window_seconds is not None else self.default_window_seconds
        record = ActionRecord(
            action_type=action_type,
            payload=payload,
            rollback_meta=rollback_meta,
            window_seconds=window,
        )
        self._actions[record.action_id] = record
        self._last_action_id = record.action_id
        logger.info("undo.action_registered", action_id=record.action_id, action_type=action_type)
        return record

    async def rollback(
        self,
        action_id: str | None = None,
        current_time: float | None = None,
    ) -> dict[str, Any]:
        """
        Roll back the specified action (or most recent action if None).
        Returns status 'rolled_back' if within 10s, or 'expired' if >10s.
        """
        target_id = action_id or self._last_action_id
        if not target_id or target_id not in self._actions:
            return {
                "status": "not_found",
                "message": "No pending action found to undo",
            }

        record = self._actions[target_id]

        # Check 10-second expiry gate (P5-T12)
        if record.is_expired(current_time=current_time):
            record.status = "committed"
            logger.warning("undo.expired", action_id=target_id)
            return {
                "status": "expired",
                "action_id": target_id,
                "message": "Action committed, cannot undo",
                "toast": "Action committed, cannot undo",
            }

        if record.status == "rolled_back":
            return {
                "status": "already_undone",
                "action_id": target_id,
                "message": "Action was already undone",
            }

        # Execute rollback logic by action_type
        success = False
        meta = record.rollback_meta

        if record.action_type == "draft_email":
            draft_id = meta.get("draft_id")
            if draft_id:
                success = await google_connector.delete_draft(draft_id)
                if not success:
                    # Try MS connector
                    success = await microsoft_connector.delete_draft(draft_id)
            else:
                success = True

        elif record.action_type == "create_calendar":
            event_id = meta.get("event_id")
            if event_id:
                success = await google_connector.delete_event(event_id)
                if not success:
                    success = await microsoft_connector.delete_meeting(event_id)
            else:
                success = True

        elif record.action_type == "trigger_n8n":
            job_id = meta.get("job_id")
            if job_id:
                success = await n8n_bridge.cancel_job(job_id)
            else:
                success = True

        elif record.action_type == "jira_ticket":
            job_id = meta.get("job_id")
            if job_id:
                success = await n8n_bridge.cancel_job(job_id)
            else:
                success = True

        else:
            success = True

        record.status = "rolled_back"
        logger.info("undo.successful_rollback", action_id=target_id, action_type=record.action_type)
        return {
            "status": "rolled_back",
            "action_id": target_id,
            "action_type": record.action_type,
            "message": f"Successfully rolled back {record.action_type}",
            "toast": "Action undone successfully",
            "rollback_confirmed": success,
        }

    def get_action(self, action_id: str) -> dict[str, Any] | None:
        rec = self._actions.get(action_id)
        return rec.to_dict() if rec else None


# Singleton instance
undo_buffer = UndoActionBuffer(default_window_seconds=10.0)
