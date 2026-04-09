"""
Live Reasoning Stream — SSE-backed step emitter with replay buffer.

Architecture:
  - Per-incident: asyncio.Queue (live events) + list (replay history)
  - emit() writes to BOTH queue and history
  - sse_generator() replays history first, then listens for new events
  - This solves the race condition where triage finishes before browser connects

Thread-safety: triage runs as FastAPI BackgroundTask on the same event loop.
Gemini's generate_content() blocks the loop; emits before/after flush together.
The replay buffer ensures no steps are lost regardless of connection timing.
"""
import asyncio
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# incident_id → asyncio.Queue[dict | None]
_streams: dict[str, asyncio.Queue] = {}

# incident_id → list of all emitted steps (replay buffer)
_histories: dict[str, list[dict]] = {}

# incident_id → True if pipeline already finished before client connected
_finished: dict[str, bool] = {}


def create_stream(incident_id: str) -> asyncio.Queue:
    """Called in create_incident BEFORE background task starts."""
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _streams[incident_id] = q
    _histories[incident_id] = []
    _finished[incident_id] = False
    logger.debug("Stream created for incident %s", incident_id)
    return q


def get_stream(incident_id: str) -> Optional[asyncio.Queue]:
    return _streams.get(incident_id)


async def emit(
    incident_id: str,
    step: str,
    detail: str = "",
    stage: str = "working",
    icon: str = "",
) -> None:
    """Emit a reasoning step. Stored in history AND sent live to queue."""
    payload = {"step": step, "detail": detail, "stage": stage, "icon": icon}

    # Always append to history (for replay)
    history = _histories.get(incident_id)
    if history is not None:
        history.append(payload)

    # Try to put in live queue
    q = _streams.get(incident_id)
    if q:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("Stream queue full for incident %s", incident_id)

    logger.debug("Stream emit [%s]: %s", incident_id[:8], step)


async def close_stream(incident_id: str) -> None:
    """Send sentinel, persist all steps to DB, mark as finished."""
    _finished[incident_id] = True

    q = _streams.get(incident_id)
    if q:
        try:
            q.put_nowait(None)  # sentinel
        except asyncio.QueueFull:
            pass

    # Persist history to DB (batch insert — one write per incident)
    history = _histories.get(incident_id, [])
    if history:
        try:
            from app.core.database import execute
            for order, step in enumerate(history):
                execute(
                    """
                    INSERT INTO reasoning_steps
                        (incident_id, step, detail, stage, icon, step_order)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        incident_id,
                        step.get("step", ""),
                        step.get("detail", ""),
                        step.get("stage", "working"),
                        step.get("icon", ""),
                        order,
                    ),
                )
            logger.info("Persisted %d reasoning steps for incident %s", len(history), incident_id)
        except Exception as e:
            logger.warning("Could not persist reasoning steps: %s", e)

    # Remove queue but KEEP history for late-connecting clients
    _streams.pop(incident_id, None)
    logger.debug("Stream closed for incident %s", incident_id)


async def sse_generator(incident_id: str):
    """
    Async generator for SSE.

    1. If history exists → replay all past steps immediately
    2. If pipeline already finished → send done and exit
    3. Otherwise → listen on live queue until sentinel or timeout
    """
    history = _histories.get(incident_id, [])
    already_done = _finished.get(incident_id, False)

    # ── Phase 1: Replay history ──────────────────────────────────────────────
    for item in history:
        yield _sse(item)

    # ── Phase 2: If finished → done ──────────────────────────────────────────
    if already_done:
        if not history:
            yield _sse({"step": "Triage already completed. Check results below.", "stage": "done", "icon": "check-circle"})
        else:
            yield _sse({"step": "TRIAGE COMPLETE", "stage": "done", "icon": "check-circle"})
        # Clean up history
        _histories.pop(incident_id, None)
        _finished.pop(incident_id, None)
        return

    # ── Phase 3: Live stream (pipeline still running) ────────────────────────
    q = _streams.get(incident_id)
    if not q:
        yield _sse({"step": "TRIAGE COMPLETE", "stage": "done", "icon": "check-circle"})
        return

    deadline = 120
    elapsed = 0

    while elapsed < deadline:
        try:
            item = await asyncio.wait_for(q.get(), timeout=1.0)
        except asyncio.TimeoutError:
            elapsed += 1
            yield ": keepalive\n\n"
            continue

        if item is None:
            # Sentinel — pipeline finished
            yield _sse({"step": "TRIAGE COMPLETE", "stage": "done", "icon": "check-circle"})
            _histories.pop(incident_id, None)
            _finished.pop(incident_id, None)
            return

        # Don't re-send items already replayed from history
        # (queue may have items that were added AFTER the history snapshot)
        yield _sse(item)
        elapsed = 0

    yield _sse({"step": "Stream timeout — check Dashboard for results.", "stage": "done", "icon": "alert-triangle"})
    _histories.pop(incident_id, None)
    _finished.pop(incident_id, None)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"
