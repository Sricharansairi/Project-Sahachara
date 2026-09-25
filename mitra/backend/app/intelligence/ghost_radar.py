"""
MITRA Backend — Ghost Follow-Up Radar (Two-Way Commitment Engine)

Detects outbound commitments ("I will send by Friday") and inbound deliverables
("John will send the report by tomorrow") across communication channels.
Provides deadline alerts (1 hour before due), 1-click polite follow-up drafts,
and resolution/snooze workflows.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
import structlog

logger = structlog.get_logger(__name__)

CommitmentDirection = Literal["outbound", "inbound"]
CommitmentStatus = Literal["pending", "resolved", "snoozed", "alerted"]

# Regex patterns for detecting commitments
OUTBOUND_PATTERNS = [
    r"i(?:'ll|\s+will|\s+promise\s+to|\s+shall)\s+([a-zA-Z\s]+(?:by|before|on|tomorrow|friday|monday|tonight)[a-zA-Z0-9\s]*)",
    r"i(?:'ll|\s+will)\s+(?:send|follow\s+up|deliver|share|review|finish|complete|email|provide|prepare)\s+([a-zA-Z0-9\s]+)",
    r"will\s+get\s+back\s+to\s+you\s+(?:by|on|before|tomorrow)\s+([a-zA-Z0-9\s]+)",
    r"let\s+me\s+(?:send|prepare|finish)\s+([a-zA-Z0-9\s]+)",
]

INBOUND_PATTERNS = [
    r"(?:[a-zA-Z]+\s+will|will|i'll)\s+(?:send|provide|deliver|share|email)\s+(?:you|us)?\s*([a-zA-Z0-9\s]+)",
    r"looking\s+forward\s+to\s+receiving\s+([a-zA-Z0-9\s]+)",
    r"(?:will\s+send|will\s+provide|will\s+deliver)\s+([a-zA-Z0-9\s]+(?:by|before|on|tomorrow)[a-zA-Z0-9\s]*)",
    r"please\s+send\s+(?:me|us)\s+([a-zA-Z0-9\s]+(?:by|before)[a-zA-Z0-9\s]*)",
]


class CommitmentRecord:
    def __init__(
        self,
        party: str,
        description: str,
        due_date: datetime,
        direction: CommitmentDirection,
        source_message_id: str | None = None,
        commitment_id: str | None = None,
    ):
        self.id = commitment_id or f"commit_{uuid.uuid4().hex[:10]}"
        self.party = party
        self.description = description
        self.due_date = due_date
        self.direction = direction
        self.source_message_id = source_message_id
        self.status: CommitmentStatus = "pending"
        self.created_at = datetime.now(timezone.utc)
        self.snoozed_until: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "party": self.party,
            "description": self.description,
            "due_date": self.due_date.isoformat(),
            "direction": self.direction,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "snoozed_until": self.snoozed_until.isoformat() if self.snoozed_until else None,
        }


class GhostFollowUpRadar:
    """Commitment extraction, deadline alert monitoring, and follow-up generation."""

    def __init__(self):
        self._commitments: dict[str, CommitmentRecord] = {}

    def extract_commitments_from_text(
        self,
        text: str,
        party: str,
        is_sent_by_user: bool = False,
        message_id: str | None = None,
    ) -> list[CommitmentRecord]:
        """
        Analyze email body text and extract promises / commitments.
        If is_sent_by_user is True -> scans for outbound commitments.
        If False -> scans for inbound deliverables promised by the other party.
        """
        extracted = []
        text_lower = text.lower()

        patterns = OUTBOUND_PATTERNS if is_sent_by_user else INBOUND_PATTERNS
        direction: CommitmentDirection = "outbound" if is_sent_by_user else "inbound"

        # Check all patterns
        for pat in patterns:
            matches = re.finditer(pat, text_lower)
            for m in matches:
                desc = m.group(0).strip()
                # Basic due date extraction fallback: default to 24 hours out or specific offsets
                due = datetime.now(timezone.utc) + timedelta(days=1)
                if "friday" in text_lower:
                    due = datetime.now(timezone.utc) + timedelta(days=2)
                elif "tomorrow" in text_lower:
                    due = datetime.now(timezone.utc) + timedelta(days=1)
                elif "hour" in text_lower:
                    due = datetime.now(timezone.utc) + timedelta(hours=2)

                record = CommitmentRecord(
                    party=party,
                    description=desc,
                    due_date=due,
                    direction=direction,
                    source_message_id=message_id,
                )
                self._commitments[record.id] = record
                extracted.append(record)
                break  # avoid multiple duplicates for same sentence

        return extracted

    def check_deadline_alerts(
        self,
        current_time: datetime | None = None,
        target_window_minutes: float = 60.0,
        tolerance_minutes: float = 5.0,
    ) -> list[dict[str, Any]]:
        """
        Detect commitments whose deadline is approximately 1 hour away (target_window_minutes).
        Returns alerts that should be triggered.
        """
        now = current_time or datetime.now(timezone.utc)
        alerts = []

        for record in self._commitments.values():
            if record.status in ("resolved", "alerted"):
                continue

            time_until_due = (record.due_date - now).total_seconds() / 60.0  # in minutes

            # Check if within window (e.g. 60 ± 5 minutes)
            if abs(time_until_due - target_window_minutes) <= tolerance_minutes:
                alerts.append({
                    "commitment_id": record.id,
                    "party": record.party,
                    "description": record.description,
                    "due_date": record.due_date.isoformat(),
                    "minutes_remaining": round(time_until_due, 1),
                    "alert_type": "deadline_1h_warning",
                })

        return alerts

    def generate_followup_draft(self, commitment_id: str) -> dict[str, str]:
        """
        Generate a 1-click polite follow-up email draft for an overdue or pending inbound item.
        """
        record = self._commitments.get(commitment_id)
        if not record:
            raise KeyError(f"Commitment {commitment_id} not found")

        subject = f"Gentle check-in regarding: {record.description[:40]}"
        body = (
            f"Hi {record.party.split('@')[0].capitalize()},\n\n"
            f"I hope you're having a productive week. Just wanted to gently follow up on "
            f"our discussion regarding '{record.description}'.\n\n"
            f"Please let me know if you need any additional context or assistance from my side.\n\n"
            f"Best regards,\nMITRA Assistant"
        )
        return {
            "commitment_id": record.id,
            "to": record.party,
            "subject": subject,
            "body": body,
        }

    def mark_resolved(self, commitment_id: str) -> bool:
        """Mark commitment as resolved."""
        record = self._commitments.get(commitment_id)
        if record:
            record.status = "resolved"
            logger.info("ghost_radar.resolved", commitment_id=commitment_id)
            return True
        return False

    def snooze(self, commitment_id: str, minutes: int = 120) -> bool:
        """Snooze a commitment."""
        record = self._commitments.get(commitment_id)
        if record:
            record.status = "snoozed"
            record.snoozed_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
            record.due_date += timedelta(minutes=minutes)
            logger.info("ghost_radar.snoozed", commitment_id=commitment_id, minutes=minutes)
            return True
        return False

    def get_commitments(self, direction: CommitmentDirection | None = None) -> list[dict[str, Any]]:
        """List active commitments."""
        items = list(self._commitments.values())
        if direction:
            items = [c for c in items if c.direction == direction]
        return [c.to_dict() for c in items]


# Singleton instance
ghost_radar = GhostFollowUpRadar()
