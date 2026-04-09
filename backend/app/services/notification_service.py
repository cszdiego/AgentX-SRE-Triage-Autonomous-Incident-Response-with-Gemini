"""
Mocked notification service.
Simulates Slack + Email delivery by writing to the notifications table.
All notifications are logged and visible in the dashboard.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from app.core.config import get_settings
from app.core.database import execute_returning

logger = logging.getLogger(__name__)
settings = get_settings()

SEVERITY_EMOJI = {"P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "🟢"}
PRIORITY_LABEL = {"P1": "CRITICAL", "P2": "HIGH", "P3": "MEDIUM", "P4": "LOW"}


def notify_team(
    incident_id: str,
    ticket_id: str,
    ticket_key: str,
    title: str,
    severity: str,
    triage_summary: str,
    affected_service: str,
    reporter_email: str,
) -> dict:
    """Send mocked team alerts via Slack and Email."""
    emoji = SEVERITY_EMOJI.get(severity, "⚪")
    label = PRIORITY_LABEL.get(severity, "UNKNOWN")

    slack_body = (
        f"{emoji} *[{ticket_key}] {label} INCIDENT — {title}*\n"
        f"> *Service:* {affected_service}\n"
        f"> *Reporter:* {reporter_email}\n"
        f"> *Summary:* {triage_summary[:300]}\n"
        f"> *Action:* Review and assign in the SRE Dashboard.\n"
        f"> _Ticket: {ticket_key}_"
    )

    email_body = f"""SRE Team,

A new {label} incident has been reported and triaged automatically.

Ticket: {ticket_key}
Title: {title}
Service: {affected_service}
Priority: {severity}

TRIAGE SUMMARY:
{triage_summary}

Please review the ticket in the SRE Dashboard and take action.

— AgentX SRE-Triage (automated)
"""
    results = []

    # Slack notification
    slack_notif = _persist_notification(
        incident_id=incident_id,
        ticket_id=ticket_id,
        notif_type="team_alert",
        channel="slack",
        recipient=settings.SRE_SLACK_CHANNEL,
        subject=f"[{ticket_key}] {label}: {title}",
        body=slack_body,
    )
    results.append(slack_notif)

    # Email notification
    email_notif = _persist_notification(
        incident_id=incident_id,
        ticket_id=ticket_id,
        notif_type="team_alert",
        channel="email",
        recipient=settings.SRE_TEAM_EMAIL,
        subject=f"[{severity}][{ticket_key}] Incident: {title}",
        body=email_body,
    )
    results.append(email_notif)

    logger.info(
        "Team notified | ticket=%s | severity=%s | channels=slack,email",
        ticket_key, severity,
    )
    return {"notifications_sent": len(results), "channels": ["slack", "email"]}


def notify_reporter_resolved(
    incident_id: str,
    ticket_id: str,
    ticket_key: str,
    title: str,
    reporter_email: str,
    reporter_name: Optional[str],
    resolution_note: Optional[str],
) -> dict:
    """Notify original reporter that their incident has been resolved."""
    name = reporter_name or reporter_email.split("@")[0]
    resolution = resolution_note or "The issue has been investigated and resolved by our SRE team."

    email_body = f"""Hello {name},

Great news! The incident you reported has been resolved.

Ticket: {ticket_key}
Title: {title}

RESOLUTION:
{resolution}

Thank you for your report. If you experience further issues, please submit a new incident report.

— AgentX SRE-Triage System
SoftServe Engineering
"""
    notif = _persist_notification(
        incident_id=incident_id,
        ticket_id=ticket_id,
        notif_type="resolved",
        channel="email",
        recipient=reporter_email,
        subject=f"[RESOLVED] {ticket_key}: {title}",
        body=email_body,
    )

    logger.info(
        "Reporter notified of resolution | ticket=%s | reporter=%s",
        ticket_key, reporter_email,
    )
    return {"notification_sent": True, "recipient": reporter_email}


def _persist_notification(
    incident_id, ticket_id, notif_type, channel, recipient, subject, body
) -> dict:
    row = execute_returning(
        """
        INSERT INTO notifications
            (incident_id, ticket_id, type, channel, recipient, subject, body, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'delivered')
        RETURNING *
        """,
        (incident_id, ticket_id, notif_type, channel, recipient, subject, body),
    )
    return row or {}
