"""
Tickets API — GET /tickets, PATCH /tickets/{id}/resolve
"""
import uuid
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.database import fetchall, fetchone, execute, execute_returning
from app.services.notification_service import notify_reporter_resolved

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tickets", tags=["tickets"])


class TicketResolve(BaseModel):
    resolution_note: Optional[str] = None


@router.get("")
def list_tickets(status: Optional[str] = None, limit: int = 50):
    conditions = []
    params = []
    if status:
        conditions.append("t.status = %s")
        params.append(status)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)
    rows = fetchall(
        f"""
        SELECT t.*, i.reporter_email, i.reporter_name, i.title as incident_title,
               i.severity, i.affected_service
        FROM tickets t
        JOIN incidents i ON i.id = t.incident_id
        {where}
        ORDER BY t.created_at DESC
        LIMIT %s
        """,
        params,
    )
    return [_serialize(r) for r in rows]


@router.get("/{ticket_id}")
def get_ticket(ticket_id: str):
    row = fetchone(
        """
        SELECT t.*, i.reporter_email, i.reporter_name, i.description as incident_description,
               i.triage_summary, i.root_cause, i.runbook, i.affected_service
        FROM tickets t
        JOIN incidents i ON i.id = t.incident_id
        WHERE t.id = %s OR t.ticket_key = %s
        """,
        (ticket_id, ticket_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _serialize(row)


@router.patch("/{ticket_id}/resolve")
def resolve_ticket(ticket_id: str, body: TicketResolve):
    """
    Mark a ticket as resolved. Triggers reporter notification.
    """
    ticket = fetchone(
        """
        SELECT t.*, i.reporter_email, i.reporter_name, i.title as incident_title, i.id as incident_id
        FROM tickets t
        JOIN incidents i ON i.id = t.incident_id
        WHERE t.id = %s OR t.ticket_key = %s
        """,
        (ticket_id, ticket_id),
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket["status"] == "resolved":
        raise HTTPException(status_code=409, detail="Ticket already resolved")

    # Update ticket
    execute(
        """
        UPDATE tickets SET status='resolved', resolved_at=NOW()
        WHERE id=%s
        """,
        (ticket["id"],),
    )

    # Update incident
    execute(
        "UPDATE incidents SET status='resolved' WHERE id=%s",
        (ticket["incident_id"],),
    )

    # ── STAGE 5: Notify reporter (resolve stage) ─────────────────────────
    from app.services.langfuse_service import TraceContext, get_langfuse
    trace_id = str(uuid.uuid4())
    incident_id = str(ticket["incident_id"])

    with TraceContext(trace_id, incident_id, "resolve"):
        notify_reporter_resolved(
            incident_id=incident_id,
            ticket_id=str(ticket["id"]),
            ticket_key=ticket["ticket_key"],
            title=ticket["incident_title"],
            reporter_email=ticket["reporter_email"],
            reporter_name=ticket.get("reporter_name"),
            resolution_note=body.resolution_note,
            jira_key=ticket.get("jira_key"),
        )

    logger.info("Ticket %s resolved | incident=%s", ticket["ticket_key"], incident_id)
    return {
        "ticket_key": ticket["ticket_key"],
        "status": "resolved",
        "reporter_notified": True,
        "reporter_email": ticket["reporter_email"],
    }


@router.patch("/{ticket_id}/assign")
def assign_ticket(ticket_id: str, assignee: str):
    execute(
        "UPDATE tickets SET assigned_to=%s, status='in_progress' WHERE id=%s OR ticket_key=%s",
        (assignee, ticket_id, ticket_id),
    )
    return {"assigned_to": assignee, "status": "in_progress"}


def _serialize(row: dict) -> dict:
    result = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, uuid.UUID):
            result[k] = str(v)
        else:
            result[k] = v
    return result
