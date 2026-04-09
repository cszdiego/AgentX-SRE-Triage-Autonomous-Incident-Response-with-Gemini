"""
Incidents API — POST /incidents, GET /incidents, GET /incidents/{id}
"""
import os
import uuid
import logging
import asyncio
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.database import fetchall, fetchone, execute_returning
from app.models.incident import IncidentResponse

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/incidents", tags=["incidents"])
limiter = Limiter(key_func=get_remote_address)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp",
                 "text/plain", "application/octet-stream", "video/mp4", "video/quicktime"}
MAX_FILE_BYTES = settings.MAX_FILE_SIZE_MB * 1024 * 1024


@router.post("", status_code=202)
@limiter.limit("10/minute")
async def create_incident(
    request: Request,
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    description: str = Form(...),
    reporter_email: str = Form(...),
    reporter_name: Optional[str] = Form(None),
    environment: Optional[str] = Form("production"),
    affected_service: Optional[str] = Form(None),
    attachment: Optional[UploadFile] = File(None),
):
    """
    Submit a new incident report. Triggers the full triage pipeline asynchronously.
    """
    # Validate file
    attachment_path = None
    attachment_type = None
    attachment_name = None

    if attachment and attachment.filename:
        content_type = attachment.content_type or "application/octet-stream"
        if content_type not in ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {content_type}")

        file_data = await attachment.read()
        if len(file_data) > MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail=f"File too large (max {settings.MAX_FILE_SIZE_MB}MB)")

        # Determine type
        if content_type.startswith("image/"):
            attachment_type = "image"
        elif content_type.startswith("video/"):
            attachment_type = "video"
        else:
            attachment_type = "log"

        # Save file
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        ext = os.path.splitext(attachment.filename)[1] or ".bin"
        fname = f"{uuid.uuid4()}{ext}"
        attachment_path = os.path.join(settings.UPLOAD_DIR, fname)
        with open(attachment_path, "wb") as f:
            f.write(file_data)
        attachment_name = attachment.filename
        logger.info("Attachment saved: %s (%s)", fname, attachment_type)

    # Create incident record
    incident_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    ip = request.client.host if request.client else None

    row = execute_returning(
        """
        INSERT INTO incidents
            (id, title, description, reporter_email, reporter_name,
             environment, affected_service, attachment_path, attachment_type,
             attachment_name, status, agent_trace_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open', %s)
        RETURNING *
        """,
        (
            incident_id, title, description, reporter_email, reporter_name,
            environment, affected_service, attachment_path, attachment_type,
            attachment_name, trace_id,
        ),
    )

    # Create SSE stream BEFORE background task so emit() has a queue to write to
    from app.core.streaming import create_stream
    create_stream(incident_id)

    # Run triage pipeline in background
    background_tasks.add_task(
        _run_pipeline,
        incident_id=incident_id,
        title=title,
        description=description,
        reporter_email=reporter_email,
        reporter_name=reporter_name,
        attachment_path=attachment_path,
        attachment_type=attachment_type,
        trace_id=trace_id,
        ip_address=ip,
    )

    return {
        "incident_id": incident_id,
        "trace_id": trace_id,
        "status": "accepted",
        "message": "Incident received. Triage pipeline running...",
    }


async def _run_pipeline(**kwargs):
    from app.agents.triage_agent import run_triage_pipeline
    try:
        await run_triage_pipeline(**kwargs)
    except Exception as e:
        logger.error("Pipeline error for incident %s: %s", kwargs.get("incident_id"), e)


@router.get("/{incident_id}/stream")
async def stream_reasoning(incident_id: str):
    """
    SSE endpoint: streams live reasoning steps from the triage pipeline.
    Connect immediately after POST /incidents to see the agent thinking.
    """
    from app.core.streaming import sse_generator
    return StreamingResponse(
        sse_generator(incident_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("", response_model=list[dict])
def list_incidents(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List incidents with optional filters."""
    conditions = []
    params = []

    if status:
        conditions.append("status = %s")
        params.append(status)
    if severity:
        conditions.append("severity = %s")
        params.append(severity)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.extend([limit, offset])

    rows = fetchall(
        f"""
        SELECT i.*,
               t.ticket_key,
               t.status as ticket_status
        FROM incidents i
        LEFT JOIN tickets t ON t.incident_id = i.id
        {where}
        ORDER BY i.created_at DESC
        LIMIT %s OFFSET %s
        """,
        params,
    )
    return [_serialize(r) for r in rows]


@router.get("/stats")
def get_stats():
    """Dashboard statistics."""
    from app.core.database import fetchone as fone
    total = fone("SELECT COUNT(*) as c FROM incidents")["c"]
    by_severity = fetchall(
        "SELECT severity, COUNT(*) as c FROM incidents WHERE severity IS NOT NULL GROUP BY severity"
    )
    by_status = fetchall("SELECT status, COUNT(*) as c FROM incidents GROUP BY status")
    recent_traces = fetchall(
        "SELECT stage, status, AVG(duration_ms)::int as avg_ms, COUNT(*) as c FROM agent_traces GROUP BY stage, status ORDER BY stage"
    )
    guardrail_blocks = fone("SELECT COUNT(*) as c FROM guardrail_logs WHERE blocked = true")["c"]
    notifications_sent = fone("SELECT COUNT(*) as c FROM notifications WHERE status='delivered'")["c"]

    return {
        "total_incidents": total,
        "by_severity": {r["severity"]: r["c"] for r in by_severity},
        "by_status": {r["status"]: r["c"] for r in by_status},
        "pipeline_traces": recent_traces,
        "guardrail_blocks": guardrail_blocks,
        "notifications_sent": notifications_sent,
    }


@router.get("/{incident_id}")
def get_incident(incident_id: str):
    row = fetchone(
        """
        SELECT i.*,
               t.ticket_key, t.status as ticket_status, t.id as ticket_id,
               t.assigned_to, t.resolved_at, t.jira_key, t.jira_url
        FROM incidents i
        LEFT JOIN tickets t ON t.incident_id = i.id
        WHERE i.id = %s
        """,
        (incident_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _serialize(row)


@router.get("/{incident_id}/reasoning")
def get_reasoning(incident_id: str):
    """Return persisted agent reasoning steps for an incident."""
    return fetchall(
        """
        SELECT step, detail, stage, icon, step_order, created_at
        FROM reasoning_steps
        WHERE incident_id = %s
        ORDER BY step_order ASC
        """,
        (incident_id,),
    )


@router.get("/{incident_id}/notifications")
def get_notifications(incident_id: str):
    return fetchall(
        "SELECT * FROM notifications WHERE incident_id = %s ORDER BY created_at DESC",
        (incident_id,),
    )


@router.get("/{incident_id}/traces")
def get_traces(incident_id: str):
    return fetchall(
        "SELECT * FROM agent_traces WHERE incident_id = %s ORDER BY created_at ASC",
        (incident_id,),
    )


def _serialize(row: dict) -> dict:
    """Convert datetime objects to ISO strings for JSON."""
    result = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, uuid.UUID):
            result[k] = str(v)
        else:
            result[k] = v
    return result
