"""
Jira REST API integration.
Creates real issues in Jira Cloud via the v3 REST API.
Falls back gracefully if credentials are not configured.
"""
import logging
import base64
from typing import Optional
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Severity → Jira priority mapping
PRIORITY_MAP = {
    "P1": "Highest",
    "P2": "High",
    "P3": "Medium",
    "P4": "Low",
}

# Severity → Jira label
LABEL_MAP = {
    "P1": "critical",
    "P2": "high",
    "P3": "medium",
    "P4": "low",
}


def _auth_header() -> str:
    token = base64.b64encode(
        f"{settings.JIRA_USER_EMAIL}:{settings.JIRA_API_TOKEN}".encode()
    ).decode()
    return f"Basic {token}"


def create_jira_issue(
    title: str,
    triage_summary: str,
    root_cause: str,
    runbook: str,
    severity: str,
    affected_service: str,
    reporter_email: str,
    incident_id: str,
) -> Optional[dict]:
    """
    Create a Jira issue and return {"key": "SRE-42", "url": "https://..."}.
    Returns None if Jira is not configured or the call fails.
    """
    if not all([settings.JIRA_SITE_URL, settings.JIRA_USER_EMAIL, settings.JIRA_API_TOKEN]):
        logger.warning("Jira credentials not configured — skipping Jira issue creation")
        return None

    priority = PRIORITY_MAP.get(severity, "Medium")
    label = LABEL_MAP.get(severity, "medium")
    base_url = f"https://{settings.JIRA_SITE_URL}"

    description_adf = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Triage Summary"}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": triage_summary}],
            },
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Root Cause"}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": root_cause}],
            },
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Runbook / Next Steps"}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": runbook}],
            },
            {
                "type": "rule",
            },
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": f"Reporter: {reporter_email} | Service: {affected_service} | Incident ID: {incident_id}",
                        "marks": [{"type": "em"}],
                    }
                ],
            },
        ],
    }

    payload = {
        "fields": {
            "project": {"key": settings.JIRA_PROJECT_KEY},
            "summary": f"[{severity}] {title}",
            "description": description_adf,
            "issuetype": {"name": "Task"},
            "priority": {"name": priority},
            "labels": [label, "agentx", "sre-triage", "automated"],
        }
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                f"{base_url}/rest/api/3/issue",
                json=payload,
                headers={
                    "Authorization": _auth_header(),
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )

        if response.status_code in (200, 201):
            data = response.json()
            issue_key = data["key"]
            issue_url = f"{base_url}/browse/{issue_key}"
            logger.info("Jira issue created: %s → %s", issue_key, issue_url)
            return {"key": issue_key, "url": issue_url}

        # Jira returns 400 with details when project key is wrong
        logger.error(
            "Jira API error: status=%d body=%s", response.status_code, response.text[:500]
        )
        return None

    except Exception as exc:
        logger.error("Jira request failed: %s", exc)
        return None
