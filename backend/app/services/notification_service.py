"""
Real notification service — Slack Incoming Webhook + Gmail SMTP_SSL.
Emails use professional HTML templates with CSS inline for maximum client compatibility.
All notifications are also persisted to the notifications table for audit and UI display.
Email sending runs in a thread pool to avoid blocking the async triage pipeline.
"""
import logging
import smtplib
import asyncio
from concurrent.futures import ThreadPoolExecutor
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import httpx
from app.core.config import get_settings
from app.core.database import execute_returning

logger = logging.getLogger(__name__)
settings = get_settings()

SEVERITY_EMOJI  = {"P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "🟢"}
PRIORITY_LABEL  = {"P1": "CRITICAL", "P2": "HIGH", "P3": "MEDIUM", "P4": "LOW"}
SEVERITY_COLOR  = {"P1": "#FF4444", "P2": "#FF8C00", "P3": "#FFD700", "P4": "#44CC44"}
SEVERITY_BG     = {"P1": "#3D0000", "P2": "#2D1500", "P3": "#2D2700", "P4": "#002D00"}

_executor = ThreadPoolExecutor(max_workers=4)


# ── HTML Templates ────────────────────────────────────────────────────────────

def _html_new_incident(
    ticket_key: str,
    jira_key: Optional[str],
    jira_url: Optional[str],
    title: str,
    severity: str,
    affected_service: str,
    reporter_email: str,
    triage_summary: str,
    root_cause: str,
    incident_id: str,
) -> str:
    sev_color = SEVERITY_COLOR.get(severity, "#888888")
    sev_bg    = SEVERITY_BG.get(severity, "#1a1a1a")
    sev_label = PRIORITY_LABEL.get(severity, "UNKNOWN")
    jira_row  = f"""
      <tr>
        <td style="padding:10px 16px;border-bottom:1px solid #2a2a3a;color:#888;font-size:13px;width:160px">Jira Issue</td>
        <td style="padding:10px 16px;border-bottom:1px solid #2a2a3a;font-size:13px">
          <a href="{jira_url}" style="color:#4e9af1;text-decoration:none;font-weight:bold">{jira_key}</a>
        </td>
      </tr>""" if jira_key and jira_url else ""

    dashboard_url = f"http://localhost:3000/incidents/{incident_id}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background-color:#0d0d1a;font-family:'Segoe UI',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0d1a;padding:32px 0">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#13131f;border-radius:12px;overflow:hidden;border:1px solid #2a2a3a;max-width:600px">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#13131f 0%,#1a1a2e 100%);padding:28px 32px;border-bottom:2px solid {sev_color}">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <div style="font-size:11px;letter-spacing:3px;color:#666;text-transform:uppercase;margin-bottom:4px">AgentX SRE-Triage</div>
                  <div style="font-size:22px;font-weight:700;color:#ffffff;line-height:1.3">{title}</div>
                </td>
                <td align="right" valign="top">
                  <div style="background:{sev_bg};border:1px solid {sev_color};border-radius:6px;padding:8px 14px;text-align:center;display:inline-block">
                    <div style="font-size:11px;color:{sev_color};letter-spacing:2px;font-weight:700">{severity}</div>
                    <div style="font-size:10px;color:{sev_color};opacity:0.8">{sev_label}</div>
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Incident Details Table -->
        <tr>
          <td style="padding:0">
            <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">
              <tr>
                <td style="padding:10px 16px;border-bottom:1px solid #2a2a3a;color:#888;font-size:13px;width:160px;background:#0f0f1c">Ticket</td>
                <td style="padding:10px 16px;border-bottom:1px solid #2a2a3a;font-size:13px;color:#00f5d4;font-family:monospace;font-weight:bold;background:#0f0f1c">{ticket_key}</td>
              </tr>
              <tr>
                <td style="padding:10px 16px;border-bottom:1px solid #2a2a3a;color:#888;font-size:13px">Service Affected</td>
                <td style="padding:10px 16px;border-bottom:1px solid #2a2a3a;font-size:13px;color:#e0e0e0">{affected_service}</td>
              </tr>
              <tr>
                <td style="padding:10px 16px;border-bottom:1px solid #2a2a3a;color:#888;font-size:13px">Reporter</td>
                <td style="padding:10px 16px;border-bottom:1px solid #2a2a3a;font-size:13px;color:#e0e0e0">{reporter_email}</td>
              </tr>
              {jira_row}
            </table>
          </td>
        </tr>

        <!-- Triage Summary -->
        <tr>
          <td style="padding:24px 32px 8px">
            <div style="font-size:11px;letter-spacing:2px;color:#00f5d4;text-transform:uppercase;margin-bottom:10px">AI Triage Summary</div>
            <div style="font-size:14px;color:#c0c0d0;line-height:1.7;background:#0f0f1c;border-left:3px solid #00f5d4;padding:14px 18px;border-radius:4px">{triage_summary}</div>
          </td>
        </tr>

        <!-- Root Cause -->
        <tr>
          <td style="padding:8px 32px 24px">
            <div style="font-size:11px;letter-spacing:2px;color:{sev_color};text-transform:uppercase;margin-bottom:10px">Root Cause Detected</div>
            <div style="font-size:14px;color:#c0c0d0;line-height:1.7;background:#0f0f1c;border-left:3px solid {sev_color};padding:14px 18px;border-radius:4px">{root_cause}</div>
          </td>
        </tr>

        <!-- CTA Button -->
        <tr>
          <td style="padding:8px 32px 32px;text-align:center">
            <a href="{dashboard_url}"
               style="display:inline-block;background:linear-gradient(135deg,#00f5d4,#00b8a0);color:#0d0d1a;font-weight:700;font-size:14px;padding:14px 36px;border-radius:8px;text-decoration:none;letter-spacing:1px">
              VIEW FULL ANALYSIS →
            </a>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#0a0a14;padding:16px 32px;border-top:1px solid #2a2a3a">
            <div style="font-size:11px;color:#444;text-align:center">
              AgentX SRE-Triage · Autonomous Incident Response · Powered by Gemini 2.5 Flash
            </div>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _html_resolved(
    ticket_key: str,
    jira_key: Optional[str],
    title: str,
    reporter_name: str,
    resolution: str,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background-color:#0d0d1a;font-family:'Segoe UI',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0d1a;padding:32px 0">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#13131f;border-radius:12px;overflow:hidden;border:1px solid #2a2a3a;max-width:600px">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#0a1f1a 0%,#0d2a20 100%);padding:28px 32px;border-bottom:2px solid #00c896">
            <div style="font-size:11px;letter-spacing:3px;color:#666;text-transform:uppercase;margin-bottom:4px">AgentX SRE-Triage</div>
            <div style="display:flex;align-items:center;gap:12px">
              <div style="width:36px;height:36px;background:#00c896;border-radius:50%;display:inline-block;text-align:center;line-height:36px;font-size:20px;margin-right:12px;vertical-align:middle">✓</div>
              <div style="display:inline-block;vertical-align:middle">
                <div style="font-size:20px;font-weight:700;color:#ffffff">Incident Resolved</div>
                <div style="font-size:13px;color:#00c896;margin-top:2px">{ticket_key}{' · ' + jira_key if jira_key else ''}</div>
              </div>
            </div>
          </td>
        </tr>

        <!-- Greeting -->
        <tr>
          <td style="padding:28px 32px 16px">
            <div style="font-size:16px;color:#e0e0e0;line-height:1.6">
              Hello <strong style="color:#ffffff">{reporter_name}</strong>,
            </div>
            <div style="font-size:14px;color:#909090;margin-top:8px;line-height:1.7">
              Great news — the incident you reported has been investigated and successfully mitigated by our SRE team.
            </div>
          </td>
        </tr>

        <!-- Incident Title -->
        <tr>
          <td style="padding:0 32px 16px">
            <div style="background:#0f0f1c;border:1px solid #2a2a3a;border-radius:8px;padding:16px 20px">
              <div style="font-size:11px;letter-spacing:2px;color:#666;text-transform:uppercase;margin-bottom:6px">Incident</div>
              <div style="font-size:15px;color:#e0e0e0;font-weight:600">{title}</div>
            </div>
          </td>
        </tr>

        <!-- Resolution -->
        <tr>
          <td style="padding:0 32px 24px">
            <div style="font-size:11px;letter-spacing:2px;color:#00c896;text-transform:uppercase;margin-bottom:10px">Resolution Summary</div>
            <div style="font-size:14px;color:#c0c0d0;line-height:1.7;background:#0a1f1a;border-left:3px solid #00c896;padding:14px 18px;border-radius:4px">{resolution}</div>
          </td>
        </tr>

        <!-- Success Banner -->
        <tr>
          <td style="padding:0 32px 32px">
            <div style="background:linear-gradient(135deg,#0a2a1f,#0d3325);border:1px solid #00c896;border-radius:8px;padding:18px 24px;text-align:center">
              <div style="font-size:15px;font-weight:700;color:#00c896">
                {ticket_key} has been successfully mitigated
              </div>
              <div style="font-size:12px;color:#509070;margin-top:4px">
                If you experience further issues, please submit a new incident report.
              </div>
            </div>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#0a0a14;padding:16px 32px;border-top:1px solid #2a2a3a">
            <div style="font-size:11px;color:#444;text-align:center">
              AgentX SRE-Triage · Autonomous Incident Response · Powered by Gemini 2.5 Flash
            </div>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ── Slack ────────────────────────────────────────────────────────────────────

def _send_slack(message: str) -> bool:
    if not settings.SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL not set — skipping Slack notification")
        return False
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(settings.SLACK_WEBHOOK_URL, json={"text": message})
        if resp.status_code == 200:
            logger.info("Slack notification sent (HTTP 200)")
            return True
        logger.error("Slack webhook HTTP %d: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.error("Slack webhook failed: %s", exc)
        return False


# ── Email / Gmail SMTP_SSL ────────────────────────────────────────────────────

def _send_email_sync(to: str, subject: str, html_body: str, text_body: str) -> bool:
    """Synchronous SMTP_SSL send — runs in thread pool."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP_USER/SMTP_PASSWORD not set — skipping email")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"AgentX SRE-Triage <{settings.SMTP_FROM or settings.SMTP_USER}>"
        msg["To"]      = to
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html",  "utf-8"))

        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM or settings.SMTP_USER, [to], msg.as_string())

        logger.info("Email sent to %s via %s:%d", to, settings.SMTP_HOST, settings.SMTP_PORT)
        return True
    except Exception as exc:
        logger.error("SMTP send failed (to=%s): %s", to, exc)
        return False


async def _send_email_async(to: str, subject: str, html_body: str, text_body: str) -> bool:
    """Async wrapper — offloads blocking SMTP to thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor, _send_email_sync, to, subject, html_body, text_body
    )


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
    root_cause: str = "",
) -> dict:
    """Send real Slack alert + Gmail HTML email to SRE team (synchronous wrapper for pipeline)."""
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
    html_body = _html_new_incident(
        ticket_key=ticket_key,
        jira_key=jira_key,
        jira_url=jira_url,
        title=title,
        severity=severity,
        affected_service=affected_service,
        reporter_email=reporter_email,
        triage_summary=triage_summary,
        root_cause=root_cause or "Under investigation",
        incident_id=incident_id,
    )
    text_body = f"[{severity}] {title}\nService: {affected_service}\nTicket: {ticket_key}\n\n{triage_summary}"

    slack_ok  = _send_slack(slack_msg)
    email_ok  = _send_email_sync(settings.SRE_TEAM_EMAIL, email_subject, html_body, text_body)

    slack_status = "delivered" if slack_ok else "failed"
    email_status = "delivered" if email_ok else "failed"

    _persist_notification(
        incident_id=incident_id, ticket_id=ticket_id,
        notif_type="team_alert", channel="slack",
        recipient=settings.SRE_SLACK_CHANNEL,
        subject=f"[{ticket_key}] {label}: {title}",
        body=slack_msg, status=slack_status,
    )
    _persist_notification(
        incident_id=incident_id, ticket_id=ticket_id,
        notif_type="team_alert", channel="email",
        recipient=settings.SRE_TEAM_EMAIL,
        subject=email_subject, body=text_body, status=email_status,
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
    jira_key: Optional[str] = None,
) -> dict:
    """Send HTML resolution email to original reporter."""
    name       = reporter_name or reporter_email.split("@")[0].capitalize()
    resolution = resolution_note or "The issue has been investigated and resolved by our SRE team."

    subject   = f"[RESOLVED] {ticket_key}: {title}"
    html_body = _html_resolved(
        ticket_key=ticket_key,
        jira_key=jira_key,
        title=title,
        reporter_name=name,
        resolution=resolution,
    )
    text_body = f"Hello {name},\n\nYour incident '{title}' ({ticket_key}) has been resolved.\n\nResolution: {resolution}\n\n— AgentX SRE-Triage"

    email_ok = _send_email_sync(reporter_email, subject, html_body, text_body)
    status   = "delivered" if email_ok else "failed"

    _persist_notification(
        incident_id=incident_id, ticket_id=ticket_id,
        notif_type="resolved", channel="email",
        recipient=reporter_email, subject=subject,
        body=text_body, status=status,
    )

    logger.info("Reporter resolution email | ticket=%s | reporter=%s | status=%s", ticket_key, reporter_email, status)
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
