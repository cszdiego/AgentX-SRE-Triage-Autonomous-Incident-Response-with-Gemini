"""
Real notification service — Slack Incoming Webhook + SMTP email (Mailhog/production).
Every notification is also persisted to the notifications table for audit and UI display.
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import httpx
from app.core.config import get_settings
from app.core.database import execute_returning

logger = logging.getLogger(__name__)
settings = get_settings()

SEVERITY_EMOJI = {"P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "🟢"}
PRIORITY_LABEL = {"P1": "CRITICAL", "P2": "HIGH", "P3": "MEDIUM", "P4": "LOW"}


# ── Slack ────────────────────────────────────────────────────────────────────

def _send_slack(message: str) -> bool:
    """POST a message to the real Slack Incoming Webhook. Returns True on success."""
    if not settings.SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL not set — skipping Slack notification")
        return False
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(settings.SLACK_WEBHOOK_URL, json={"text": message})
        if resp.status_code == 200:
            logger.info("Slack notification sent (HTTP 200)")
            return True
        logger.error("Slack webhook returned HTTP %d: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.error("Slack webhook request failed: %s", exc)
        return False


# ── Email / SMTP ─────────────────────────────────────────────────────────────

def _send_email(to: str, subject: str, body: str) -> bool:
    """Send an email via SMTP (Mailhog in Docker, real SMTP in production). Returns True on success."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.sendmail(settings.SMTP_FROM, [to], msg.as_string())

        logger.info("Email sent to %s via %s:%d", to, settings.SMTP_HOST, settings.SMTP_PORT)
        return True
    except Exception as exc:
        logger.error("SMTP send failed (to=%s): %s", to, exc)
        return False


# ── Public API ───────────────────────────────────────────────────────────────

def notify_team(
    incident_id: str,
    ticket_id: str,
    ticket_key: str,
    title: str,
    severity: str,
    triage_summary: str,
    affected_service: str,
    reporter_email: str,
    jira_key: Optional[str] = None,
    jira_url: Optional[str] = None,
) -> dict:
    """Send real team alerts via Slack webhook and SMTP email."""
    emoji = SEVERITY_EMOJI.get(severity, "⚪")
    label = PRIORITY_LABEL.get(severity, "UNKNOWN")
    jira_line = f"\n> *Jira:* <{jira_url}|{jira_key}>" if jira_key and jira_url else ""

    slack_msg = (
        f"{emoji} *[{ticket_key}] {label} INCIDENT — {title}*\n"
        f"> *Service:* {affected_service}\n"
        f"> *Reporter:* {reporter_email}\n"
        f"> *Summary:* {triage_summary[:300]}\n"
        f"> *Action:* Review and assign in the SRE Dashboard."
        f"{jira_line}"
    )

    email_subject = f"[{severity}][{ticket_key}] Incident: {title}"
    jira_section = f"\nJira Ticket: {jira_url}\n" if jira_url else ""
    email_body = f"""SRE Team,

A new {label} incident has been reported and triaged automatically by AgentX.

Ticket: {ticket_key}
Title: {title}
Service: {affected_service}
Priority: {severity}
{jira_section}
TRIAGE SUMMARY:
{triage_summary}

Please review the ticket in the SRE Dashboard and take action.

— AgentX SRE-Triage (automated)
"""

    slack_ok = _send_slack(slack_msg)
    email_ok = _send_email(settings.SRE_TEAM_EMAIL, email_subject, email_body)

    slack_status = "delivered" if slack_ok else "failed"
    email_status = "delivered" if email_ok else "failed"

    _persist_notification(
        incident_id=incident_id,
        ticket_id=ticket_id,
        notif_type="team_alert",
        channel="slack",
        recipient=settings.SRE_SLACK_CHANNEL,
        subject=f"[{ticket_key}] {label}: {title}",
        body=slack_msg,
        status=slack_status,
    )
    _persist_notification(
        incident_id=incident_id,
        ticket_id=ticket_id,
        notif_type="team_alert",
        channel="email",
        recipient=settings.SRE_TEAM_EMAIL,
        subject=email_subject,
        body=email_body,
        status=email_status,
    )

    logger.info(
        "Team notifications | ticket=%s | severity=%s | slack=%s | email=%s",
        ticket_key, severity, slack_status, email_status,
    )
    return {
        "notifications_sent": 2,
        "channels": ["slack", "email"],
        "slack_status": slack_status,
        "email_status": email_status,
    }


def notify_reporter_resolved(
    incident_id: str,
    ticket_id: str,
    ticket_key: str,
    title: str,
    reporter_email: str,
    reporter_name: Optional[str],
    resolution_note: Optional[str],
) -> dict:
    """Email the original reporter to confirm their incident has been resolved."""
    name = reporter_name or reporter_email.split("@")[0]
    resolution = resolution_note or "The issue has been investigated and resolved by our SRE team."

    subject = f"[RESOLVED] {ticket_key}: {title}"
    body = f"""Hello {name},

Great news! The incident you reported has been resolved.

Ticket: {ticket_key}
Title: {title}

RESOLUTION:
{resolution}

Thank you for your report. If you experience further issues, please submit a new incident report.

— AgentX SRE-Triage System
SoftServe Engineering
"""
    email_ok = _send_email(reporter_email, subject, body)
    status = "delivered" if email_ok else "failed"

    _persist_notification(
        incident_id=incident_id,
        ticket_id=ticket_id,
        notif_type="resolved",
        channel="email",
        recipient=reporter_email,
        subject=subject,
        body=body,
        status=status,
    )

    logger.info(
        "Reporter resolution notification | ticket=%s | reporter=%s | status=%s",
        ticket_key, reporter_email, status,
    )
    return {"notification_sent": True, "recipient": reporter_email, "status": status}


# ── Internal ─────────────────────────────────────────────────────────────────

def _persist_notification(
    incident_id, ticket_id, notif_type, channel, recipient, subject, body, status="delivered"
) -> dict:
    row = execute_returning(
        """
        INSERT INTO notifications
            (incident_id, ticket_id, type, channel, recipient, subject, body, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (incident_id, ticket_id, notif_type, channel, recipient, subject, body, status),
    )
    return row or {}
