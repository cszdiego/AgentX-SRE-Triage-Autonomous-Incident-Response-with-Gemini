from fastapi import APIRouter
from app.core.database import fetchone, fetchall
from app.core.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
def health_check():
    db_ok = False
    try:
        fetchone("SELECT 1 as ok")
        db_ok = True
    except Exception:
        pass

    return {
        "status": "healthy" if db_ok else "degraded",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": "connected" if db_ok else "unavailable",
        "model": settings.GEMINI_MODEL,
    }


@router.get("/api/v1/health/metrics")
def get_metrics():
    """
    Structured metrics endpoint for observability and demo.
    Returns key counters across the full triage pipeline.
    """
    try:
        # Incident totals
        totals = fetchone(
            """
            SELECT
                COUNT(*) AS incidents_total,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') AS incidents_last_24h,
                COUNT(*) FILTER (WHERE status = 'resolved') AS incidents_resolved,
                COUNT(*) FILTER (WHERE status = 'duplicate') AS incidents_duplicate,
                COUNT(*) FILTER (WHERE status = 'in_progress') AS incidents_in_progress
            FROM incidents
            """
        ) or {}

        # Severity breakdown
        severity_rows = fetchall(
            "SELECT severity, COUNT(*) as c FROM incidents WHERE severity IS NOT NULL GROUP BY severity ORDER BY severity"
        ) or []
        by_severity = {r["severity"]: r["c"] for r in severity_rows}

        # Avg triage time (from agent_traces)
        perf = fetchone(
            """
            SELECT
                ROUND(AVG(duration_ms))::int AS avg_triage_ms,
                SUM(input_tokens)  AS tokens_input_total,
                SUM(output_tokens) AS tokens_output_total
            FROM agent_traces
            WHERE stage = 'triage' AND status = 'success'
            """
        ) or {}

        # Guardrails
        guardrails = fetchone(
            "SELECT COUNT(*) AS blocks_total FROM guardrail_logs WHERE blocked = TRUE"
        ) or {}

        # Jira tickets created
        jira = fetchone(
            "SELECT COUNT(*) AS jira_tickets FROM tickets WHERE jira_key IS NOT NULL"
        ) or {}

        # Notifications by channel and status
        notif_rows = fetchall(
            "SELECT channel, status, COUNT(*) as c FROM notifications GROUP BY channel, status"
        ) or []
        slack_delivered = sum(r["c"] for r in notif_rows if r["channel"] == "slack" and r["status"] == "delivered")
        email_delivered = sum(r["c"] for r in notif_rows if r["channel"] == "email" and r["status"] == "delivered")
        slack_failed    = sum(r["c"] for r in notif_rows if r["channel"] == "slack" and r["status"] == "failed")
        email_failed    = sum(r["c"] for r in notif_rows if r["channel"] == "email" and r["status"] == "failed")

        return {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "model": settings.GEMINI_MODEL,
            # Incidents
            "incidents_total":       totals.get("incidents_total", 0),
            "incidents_last_24h":    totals.get("incidents_last_24h", 0),
            "incidents_resolved":    totals.get("incidents_resolved", 0),
            "incidents_duplicate":   totals.get("incidents_duplicate", 0),
            "incidents_in_progress": totals.get("incidents_in_progress", 0),
            "incidents_by_severity": by_severity,
            # Performance
            "avg_triage_ms":         perf.get("avg_triage_ms", 0),
            "tokens_input_total":    int(perf.get("tokens_input_total") or 0),
            "tokens_output_total":   int(perf.get("tokens_output_total") or 0),
            # Security
            "guardrail_blocks_total": guardrails.get("blocks_total", 0),
            # External systems
            "jira_tickets_created": jira.get("jira_tickets", 0),
            # Notifications
            "slack_delivered":  slack_delivered,
            "slack_failed":     slack_failed,
            "email_delivered":  email_delivered,
            "email_failed":     email_failed,
        }
    except Exception as exc:
        return {"error": str(exc), "status": "metrics_unavailable"}
