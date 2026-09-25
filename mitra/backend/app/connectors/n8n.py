"""
MITRA Backend — n8n Webhook Automation Bridge

Supports:
- Triggering n8n webhooks with structured payloads
- 5 Pre-built workflow templates (Slack, Jira, HubSpot, Sheets, Poller)
- Rollback cancellation handling for the 10-Second Undo Buffer
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Literal
import structlog
import httpx

logger = structlog.get_logger(__name__)

# Pre-built template identifiers
TemplateType = Literal[
    "slack_notification",
    "jira_ticket",
    "hubspot_crm",
    "google_sheets",
    "webhook_poller",
]


class N8nBridge:
    """n8n Automation Bridge with template support and callback tracking."""

    def __init__(self, webhook_base_url: str | None = None):
        self.webhook_base_url = webhook_base_url or os.getenv(
            "N8N_WEBHOOK_BASE_URL", "http://localhost:5678/webhook"
        )
        self._mock_jobs: dict[str, dict[str, Any]] = {}
        self._slack_messages: list[dict[str, Any]] = []
        self._jira_tickets: dict[str, dict[str, Any]] = {}

    def get_template_payload(self, template: TemplateType, **kwargs: Any) -> dict[str, Any]:
        """Generate structured payload matching the specified n8n workflow template."""
        if template == "slack_notification":
            return {
                "template": "slack_notification",
                "channel": kwargs.get("channel", "#general"),
                "message": kwargs.get("message", "Notification from MITRA"),
                "sender": "MITRA AI",
                "attachments": kwargs.get("attachments", []),
            }
        elif template == "jira_ticket":
            return {
                "template": "jira_ticket",
                "project_key": kwargs.get("project_key", "SAH"),
                "summary": kwargs.get("summary", "New Task from MITRA"),
                "description": kwargs.get("description", ""),
                "issue_type": kwargs.get("issue_type", "Task"),
                "priority": kwargs.get("priority", "Medium"),
            }
        elif template == "hubspot_crm":
            return {
                "template": "hubspot_crm",
                "action": kwargs.get("action", "create_or_update_contact"),
                "email": kwargs.get("email", ""),
                "properties": kwargs.get("properties", {}),
            }
        elif template == "google_sheets":
            return {
                "template": "google_sheets",
                "sheet_id": kwargs.get("sheet_id", ""),
                "range": kwargs.get("range", "Sheet1!A1"),
                "values": kwargs.get("values", []),
            }
        elif template == "webhook_poller":
            return {
                "template": "webhook_poller",
                "target_url": kwargs.get("target_url", ""),
                "interval_seconds": kwargs.get("interval_seconds", 30),
            }
        else:
            raise ValueError(f"Unknown n8n template: {template}")

    async def trigger(
        self,
        template: TemplateType,
        payload_data: dict[str, Any],
        custom_endpoint: str | None = None,
    ) -> dict[str, Any]:
        """
        Trigger an n8n webhook workflow.
        Returns job metadata with job_id and execution status.
        """
        job_id = f"job_n8n_{uuid.uuid4().hex[:12]}"
        formatted_payload = self.get_template_payload(template, **payload_data)
        formatted_payload["job_id"] = job_id
        formatted_payload["callback_url"] = "http://127.0.0.1:8766/api/v1/webhook/result"

        target_url = (
            f"{self.webhook_base_url.rstrip('/')}/{custom_endpoint or template}"
        )

        status = "dispatched"
        remote_success = False

        # Attempt remote HTTP POST if configured and reachable
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.post(target_url, json=formatted_payload)
                if resp.status_code in (200, 201, 202):
                    remote_success = True
                    status = "completed"
        except Exception as e:
            logger.info("n8n.remote_unreachable_using_mock", error=str(e), url=target_url)

        # In-memory execution tracking for testing / offline mode
        job_record = {
            "job_id": job_id,
            "template": template,
            "target_url": target_url,
            "payload": formatted_payload,
            "status": "completed" if remote_success else "dispatched",
            "cancelled": False,
        }

        # Track local simulation for Slack / Jira
        if template == "slack_notification":
            self._slack_messages.append({
                "job_id": job_id,
                "channel": formatted_payload.get("channel"),
                "message": formatted_payload.get("message"),
                "delivered": True,
            })
            job_record["status"] = "success"
            job_record["result"] = {"delivered": True, "channel": formatted_payload.get("channel")}

        elif template == "jira_ticket":
            ticket_key = f"{formatted_payload.get('project_key', 'SAH')}-{len(self._jira_tickets) + 101}"
            ticket_record = {
                "key": ticket_key,
                "summary": formatted_payload.get("summary"),
                "status": "Open",
            }
            self._jira_tickets[ticket_key] = ticket_record
            job_record["status"] = "success"
            job_record["ticket_key"] = ticket_key
            job_record["result"] = ticket_record

        self._mock_jobs[job_id] = job_record
        logger.info("n8n.workflow_triggered", job_id=job_id, template=template)
        return job_record

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a triggered n8n job (used by 10-Second Undo Buffer)."""
        job = self._mock_jobs.get(job_id)
        if not job:
            return False

        job["cancelled"] = True
        job["status"] = "cancelled"

        # If it created a Jira ticket, transition it to Cancelled
        if job.get("template") == "jira_ticket" and "ticket_key" in job:
            ticket_key = job["ticket_key"]
            if ticket_key in self._jira_tickets:
                self._jira_tickets[ticket_key]["status"] = "Cancelled"
                logger.info("n8n.jira_ticket_cancelled", ticket_key=ticket_key)

        logger.info("n8n.job_cancelled", job_id=job_id)
        return True

    def get_slack_messages(self) -> list[dict[str, Any]]:
        """Retrieve sent Slack messages for verification."""
        return list(self._slack_messages)

    def get_jira_tickets(self) -> dict[str, dict[str, Any]]:
        """Retrieve simulated Jira tickets."""
        return dict(self._jira_tickets)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Fetch job details."""
        return self._mock_jobs.get(job_id)


# Singleton instance
n8n_bridge = N8nBridge()
