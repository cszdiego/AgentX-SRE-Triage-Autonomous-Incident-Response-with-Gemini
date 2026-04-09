"""
AgentX SRE Triage Agent — Core AI Pipeline
Uses Google Gemini 2.0 Flash (multimodal) for incident analysis.
PydanticAI is used for structured output validation.

Pipeline stages:
  ingest → [guardrails] → triage (Gemini) → dedup → ticket → notify → done
"""
import logging
import uuid
import base64
import json
import os
from typing import Optional

import google.generativeai as genai
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.database import fetchall, execute_returning, execute
from app.core.security import check_guardrails, sanitize_for_prompt
from app.core.streaming import emit, close_stream
from app.models.incident import TriageResult
from app.services.code_context import get_relevant_context
from app.services.jira_service import create_jira_issue
from app.services.langfuse_service import TraceContext
from app.services.notification_service import notify_team

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Severity Guide ───────────────────────────────────────────────────────────
SEVERITY_GUIDE = """
P1 (Critical): Complete service outage, data loss, security breach, revenue impact >$10k/hr, checkout broken.
P2 (High): Major degradation affecting >30% users, payment failures, significant performance regression.
P3 (Medium): Partial degradation, single feature broken, <10% users affected, non-critical path.
P4 (Low): Minor cosmetic issue, single user affected, non-production environment.
"""

SYSTEM_PROMPT = """You are an elite SRE triage specialist for an e-commerce platform built on Microsoft's eShop (.NET microservices).

Your mission: Analyze incident reports and produce a structured JSON triage output.

The eShop architecture:
- Catalog.API: Product catalog (SQL Server + EF Core). Handles product queries, image serving, price management.
- Basket.API: Shopping cart (Redis + gRPC). Manages cart state, checkout initiation.
- Ordering.API: Order processing (CQRS + DDD + MediatR + EventBus). Order creation, saga management.
- Identity.API: OAuth2/OIDC (IdentityServer). JWT token issuance, user management.
- WebApp: Blazor frontend (SSR/WASM hybrid). Consumes all APIs.
- EventBus (RabbitMQ): Async integration events between services.
- PaymentProcessor: Background worker processing payment integration events.
- Webhooks.API: Outbound webhooks for external integrations.

SEVERITY CLASSIFICATION:
""" + SEVERITY_GUIDE + """

RULES:
1. Base analysis on the actual incident description + code context provided.
2. Be specific about which service/component is affected.
3. Runbook must have numbered steps with specific commands when applicable.
4. For severity, consider business impact (revenue, user scope, data integrity).
5. For deduplication: compare with recent incidents list. If >70% similar, mark as duplicate.
6. NEVER fabricate technical details not supported by the evidence.
7. Output ONLY valid JSON — no prose, no markdown, no code blocks.

Output a single JSON object matching this exact schema:
{
  "severity": "P1|P2|P3|P4",
  "affected_service": "exact eShop service name",
  "triage_summary": "2-3 sentences technical summary",
  "root_cause": "specific suspected root cause",
  "runbook": "1. Step one\\n2. Step two\\n...",
  "is_duplicate": false,
  "duplicate_of": null,
  "similarity_score": null,
  "keywords": ["keyword1", "keyword2"]
}
"""


def _configure_gemini(model_name: str | None = None):
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel(
        model_name=model_name or settings.GEMINI_MODEL,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )


async def run_triage_pipeline(
    incident_id: str,
    title: str,
    description: str,
    reporter_email: str,
    reporter_name: Optional[str],
    attachment_path: Optional[str],
    attachment_type: Optional[str],
    trace_id: str,
    ip_address: Optional[str] = None,
) -> dict:
    """
    Full triage pipeline. Returns enriched incident data.
    """
    result = {}

    # ── STAGE 1: Ingest + Guardrails ─────────────────────────────────────
    with TraceContext(trace_id, incident_id, "ingest") as tc:
        await emit(incident_id, "Scanning input through 15 guardrail patterns...", stage="ingest", icon="shield")
        safe, violation = check_guardrails(
            title + " " + description,
            incident_id=incident_id,
            ip_address=ip_address,
        )
        tc.metadata["guardrail_passed"] = safe

        if not safe:
            logger.warning(
                "GUARDRAIL BLOCKED incident %s | violation=%s", incident_id, violation
            )
            await emit(incident_id, f"BLOCKED: {violation}", detail="Request rejected by guardrails.", stage="blocked", icon="x")
            await close_stream(incident_id)
            execute(
                "UPDATE incidents SET status='open', triage_summary=%s WHERE id=%s",
                (f"[BLOCKED: {violation}] Input failed safety check.", incident_id),
            )
            return {"blocked": True, "violation": violation}

        await emit(incident_id, "Guardrails passed — input sanitized", stage="ingest", icon="check")

    # ── STAGE 2: AI Triage ───────────────────────────────────────────────
    with TraceContext(trace_id, incident_id, "triage") as tc:
        await emit(incident_id, "Fetching recent incidents for dedup check...", stage="triage", icon="search")
        # Dedup: load recent incidents
        recent = fetchall(
            """
            SELECT id, title, triage_summary, severity
            FROM incidents
            WHERE status != 'duplicate'
              AND created_at > NOW() - INTERVAL '48 hours'
              AND id != %s
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (incident_id,),
        )
        await emit(incident_id, f"Dedup window: {len(recent)} incident(s) in last 48h to compare", stage="triage", icon="layers")

        await emit(incident_id, "Loading eShop source code context...", stage="triage", icon="code")
        # Load eShop code context
        code_ctx = get_relevant_context(f"{title} {description}")

        recent_ctx = ""
        if recent:
            recent_ctx = "\n\n## Recent Incidents (last 48h) — check for duplicates:\n"
            for r in recent:
                recent_ctx += (
                    f"- ID: {r['id']} | {r['severity']} | {r['title']}\n"
                    f"  Summary: {(r['triage_summary'] or '')[:150]}\n"
                )

        svc_hint = "relevant service" if not code_ctx.startswith("## eShop Architecture") else "architecture fallback"
        await emit(incident_id, f"Code context loaded — {svc_hint}", detail=code_ctx[:80] + "...", stage="triage", icon="file-code")

        sanitized_title = sanitize_for_prompt(title)
        sanitized_desc = sanitize_for_prompt(description)

        user_prompt = f"""## Incident Report

**Title:** {sanitized_title}
**Reporter:** {reporter_email}

**Description:**
{sanitized_desc}

{code_ctx}
{recent_ctx}

Produce the JSON triage output now."""

        # Build Gemini content parts
        content_parts: list = [SYSTEM_PROMPT + "\n\n" + user_prompt]

        # Attach multimodal content
        if attachment_path and os.path.exists(attachment_path):
            try:
                if attachment_type == "image":
                    mime = _get_image_mime(attachment_path)
                    await emit(incident_id, f"Processing image attachment with Gemini Vision...", detail=os.path.basename(attachment_path), stage="triage", icon="image")
                    with open(attachment_path, "rb") as f:
                        img_data = f.read()
                    content_parts.append({
                        "inline_data": {
                            "mime_type": mime,
                            "data": base64.b64encode(img_data).decode(),
                        }
                    })
                    content_parts.append("\n[Above: screenshot attached by reporter. Analyze visible error messages.]")
                    tc.metadata["has_attachment"] = True
                    tc.metadata["attachment_type"] = "image"
                    logger.info("Attached image: %s (%s)", attachment_path, mime)
                elif attachment_type == "video":
                    await emit(incident_id, f"Extracting error context from video recording...", detail=os.path.basename(attachment_path), stage="triage", icon="video")
                    # Read first 2MB as binary, send as base64 inline data for Gemini
                    with open(attachment_path, "rb") as f:
                        vid_data = f.read(2 * 1024 * 1024)
                    content_parts.append({
                        "inline_data": {
                            "mime_type": "video/mp4",
                            "data": base64.b64encode(vid_data).decode(),
                        }
                    })
                    content_parts.append("\n[Above: video recording of the incident. Analyze visible errors, UI state, and timestamps.]")
                    tc.metadata["has_attachment"] = True
                    tc.metadata["attachment_type"] = "video"
                    logger.info("Attached video: %s", attachment_path)
                else:
                    # Log file — read as text and append to prompt
                    await emit(incident_id, f"Parsing log file — matching patterns against eShop services...", detail=os.path.basename(attachment_path), stage="triage", icon="file-text")
                    with open(attachment_path, "r", encoding="utf-8", errors="ignore") as f:
                        log_content = f.read()[:4000]
                    content_parts[0] += f"\n\n## Attached Log File:\n```\n{log_content}\n```"
                    tc.metadata["has_attachment"] = True
                    tc.metadata["attachment_type"] = attachment_type
                    logger.info("Attached log file: %s", attachment_path)
            except Exception as e:
                logger.warning("Could not attach file %s: %s", attachment_path, e)

        await emit(incident_id, f"Sending multimodal prompt to {settings.GEMINI_MODEL}...", detail=f"Prompt: {len(content_parts[0])} chars + {len(content_parts)-1} media part(s)", stage="triage", icon="cpu")

        # Call Gemini (with fallback model on quota exhaustion)
        try:
            model = _configure_gemini()
            try:
                response = model.generate_content(content_parts)
                model_used = settings.GEMINI_MODEL
            except Exception as quota_err:
                if "RESOURCE_EXHAUSTED" in str(quota_err) or "429" in str(quota_err):
                    logger.warning("Primary model quota exceeded, trying fallback: %s", settings.GEMINI_FALLBACK_MODEL)
                    fallback = _configure_gemini(settings.GEMINI_FALLBACK_MODEL)
                    response = fallback.generate_content(content_parts)
                    model_used = settings.GEMINI_FALLBACK_MODEL
                else:
                    raise
            raw_json = response.text.strip()

            # Clean up if model wraps in markdown despite mime type setting
            if raw_json.startswith("```"):
                raw_json = raw_json.split("```")[1]
                if raw_json.startswith("json"):
                    raw_json = raw_json[4:]

            triage_dict = json.loads(raw_json)
            triage = TriageResult(**triage_dict)

            # Token usage
            try:
                usage = response.usage_metadata
                input_tokens = getattr(usage, "prompt_token_count", 0) or 0
                output_tokens = getattr(usage, "candidates_token_count", 0) or 0
            except Exception:
                input_tokens, output_tokens = 0, 0

            tc.log_generation(
                name="gemini-triage",
                model=model_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                input_data=user_prompt[:400],
                output_data=triage.model_dump(),
            )

            await emit(incident_id, f"Gemini response received — {input_tokens} input / {output_tokens} output tokens", stage="triage", icon="sparkles")
            await emit(incident_id, f"Severity classified: {triage.severity} | Service: {triage.affected_service}", stage="triage", icon="alert-triangle")
            if triage.is_duplicate:
                # Fetch the original incident's ticket key to surface it in the UI
                orig_ticket = None
                if triage.duplicate_of:
                    orig_ticket_row = fetchall(
                        "SELECT ticket_key, jira_key FROM tickets WHERE incident_id = %s LIMIT 1",
                        (triage.duplicate_of,),
                    )
                    if orig_ticket_row:
                        orig_ticket = orig_ticket_row[0]
                orig_ref = f" → original ticket: {orig_ticket['ticket_key']}" if orig_ticket else ""
                jira_ref = f" (Jira: {orig_ticket['jira_key']})" if orig_ticket and orig_ticket.get("jira_key") else ""
                await emit(
                    incident_id,
                    f"DUPLICATE DETECTED — similarity {triage.similarity_score:.0%}{orig_ref}{jira_ref}",
                    detail="Suppressing ticket creation. See original incident for details.",
                    stage="triage", icon="copy",
                )
            else:
                await emit(incident_id, "No duplicate found — unique incident confirmed", stage="triage", icon="check")

            logger.info(
                "Triage complete | incident=%s | severity=%s | service=%s | duplicate=%s | tokens=%d+%d",
                incident_id, triage.severity, triage.affected_service,
                triage.is_duplicate, input_tokens, output_tokens,
            )

        except (json.JSONDecodeError, ValidationError, Exception) as e:
            logger.error("Triage AI error: %s", e, exc_info=True)
            triage = TriageResult(
                severity="P2",
                affected_service="Unknown — review required",
                triage_summary=(
                    "Automated triage encountered an error and requires manual review. "
                    f"Error type: {type(e).__name__}. The incident has been escalated."
                ),
                root_cause="Unable to determine automatically. Please review the incident description manually.",
                runbook=(
                    "1. Review incident description manually.\n"
                    "2. Check eShop service health dashboards.\n"
                    "3. Escalate to on-call engineer.\n"
                    "4. Re-run triage if more details are available."
                ),
                is_duplicate=False,
                keywords=[],
            )

        # Persist triage results to DB
        status = "duplicate" if triage.is_duplicate else "open"
        execute(
            """
            UPDATE incidents SET
                severity = %s,
                affected_service = %s,
                triage_summary = %s,
                root_cause = %s,
                runbook = %s,
                duplicate_of = %s::uuid,
                similarity_score = %s,
                status = %s,
                langfuse_trace_id = %s
            WHERE id = %s
            """,
            (
                triage.severity,
                triage.affected_service,
                triage.triage_summary,
                triage.root_cause,
                triage.runbook,
                triage.duplicate_of,
                triage.similarity_score,
                status,
                trace_id,
                incident_id,
            ),
        )
        result["triage"] = triage.model_dump()

        if triage.is_duplicate:
            logger.info("Incident %s is duplicate of %s", incident_id, triage.duplicate_of)
            await emit(incident_id, "Writing results to database...", stage="triage", icon="database")
            await close_stream(incident_id)
            return result

        await emit(incident_id, "Writing triage results to database...", stage="triage", icon="database")

    # ── STAGE 3: Create Ticket ───────────────────────────────────────────
    with TraceContext(trace_id, incident_id, "ticket") as tc:
        await emit(incident_id, f"Creating SRE ticket [{triage.severity}]...", stage="ticket", icon="ticket")
        ticket_desc = (
            f"## Incident Summary\n{triage.triage_summary}\n\n"
            f"## Root Cause\n{triage.root_cause}\n\n"
            f"## Reporter\n- Name: {reporter_name or 'N/A'}\n- Email: {reporter_email}\n\n"
            f"## Runbook\n{triage.runbook}\n\n"
            f"---\n*Auto-generated by AgentX SRE-Triage | Trace: {trace_id}*"
        )
        ticket = execute_returning(
            """
            INSERT INTO tickets (incident_id, title, description, priority, status, assigned_to)
            VALUES (%s, %s, %s, %s, 'open', %s)
            RETURNING *
            """,
            (
                incident_id,
                f"[{triage.severity}] {title}",
                ticket_desc,
                triage.severity,
                settings.SRE_TEAM_EMAIL,
            ),
        )
        ticket_id = str(ticket["id"])
        ticket_key = ticket["ticket_key"]
        result["ticket"] = {"id": ticket_id, "key": ticket_key}
        tc.metadata["ticket_key"] = ticket_key
        await emit(incident_id, f"Internal ticket {ticket_key} created — assigned to {settings.SRE_TEAM_EMAIL}", stage="ticket", icon="check")
        logger.info("Ticket created: %s | incident=%s", ticket_key, incident_id)

        # Create real Jira issue
        await emit(incident_id, "Creating Jira issue via REST API...", stage="ticket", icon="layers")
        jira_result = create_jira_issue(
            title=title,
            triage_summary=triage.triage_summary,
            root_cause=triage.root_cause,
            runbook=triage.runbook,
            severity=triage.severity,
            affected_service=triage.affected_service,
            reporter_email=reporter_email,
            incident_id=incident_id,
        )
        jira_key = jira_url = None
        if jira_result:
            jira_key = jira_result["key"]
            jira_url = jira_result["url"]
            # Persist Jira reference in tickets table
            execute(
                "UPDATE tickets SET jira_key=%s, jira_url=%s WHERE id=%s",
                (jira_key, jira_url, ticket_id),
            )
            result["ticket"]["jira_key"] = jira_key
            result["ticket"]["jira_url"] = jira_url
            tc.metadata["jira_key"] = jira_key
            await emit(incident_id, f"Jira issue {jira_key} created", detail=jira_url, stage="ticket", icon="check")
            logger.info("Jira issue created: %s → %s", jira_key, jira_url)
        else:
            await emit(incident_id, "Jira unavailable — internal ticket only", stage="ticket", icon="alert-triangle")

    # ── STAGE 4: Notify Team ─────────────────────────────────────────────
    with TraceContext(trace_id, incident_id, "notify") as tc:
        await emit(incident_id, "Sending real Slack alert to #sre-alerts...", stage="notify", icon="bell")
        notif_result = notify_team(
            incident_id=incident_id,
            ticket_id=ticket_id,
            ticket_key=ticket_key,
            title=title,
            severity=triage.severity,
            triage_summary=triage.triage_summary,
            affected_service=triage.affected_service,
            reporter_email=reporter_email,
            jira_key=jira_key,
            jira_url=jira_url,
            root_cause=triage.root_cause,
        )
        await emit(incident_id, f"Email dispatched via Gmail → {settings.SRE_TEAM_EMAIL}", stage="notify", icon="mail")
        result["notifications"] = notif_result
        tc.metadata.update(notif_result)

        execute(
            "UPDATE incidents SET status='in_progress' WHERE id=%s",
            (incident_id,),
        )

    await emit(incident_id, f"Pipeline complete — {triage.severity} | {ticket_key} | {triage.affected_service}", stage="done", icon="check-circle")
    await close_stream(incident_id)
    return result


def _get_image_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")
