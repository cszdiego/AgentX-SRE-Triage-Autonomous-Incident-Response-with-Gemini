"""
Langfuse observability wrapper.
Traces every stage: ingest → triage → ticket → notify → resolve
"""
import logging
import time
from typing import Any, Optional
from app.core.config import get_settings
from app.core.database import execute

logger = logging.getLogger(__name__)
settings = get_settings()

_langfuse_client = None


def get_langfuse():
    global _langfuse_client
    if _langfuse_client is None:
        try:
            from langfuse import Langfuse
            _langfuse_client = Langfuse(
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                secret_key=settings.LANGFUSE_SECRET_KEY,
                host=settings.LANGFUSE_BASE_URL,
            )
            logger.info("Langfuse client initialized")
        except Exception as e:
            logger.warning("Langfuse not available, using local-only tracing: %s", e)
            _langfuse_client = _NoOpLangfuse()
    return _langfuse_client


class TraceContext:
    """Context manager for tracing a pipeline stage."""

    def __init__(
        self,
        trace_id: str,
        incident_id: Optional[str],
        stage: str,
        metadata: Optional[dict] = None,
    ):
        self.trace_id = trace_id
        self.incident_id = incident_id
        self.stage = stage
        self.metadata = metadata or {}
        self._start = time.time()
        self._span = None
        self._lf = get_langfuse()
        self._trace = None

    def __enter__(self):
        try:
            self._trace = self._lf.trace(
                id=self.trace_id,
                name=f"sre-triage:{self.stage}",
                metadata={
                    "incident_id": self.incident_id,
                    "stage": self.stage,
                    **self.metadata,
                },
            )
            self._span = self._trace.span(name=self.stage)
        except Exception as e:
            logger.debug("Langfuse trace init failed: %s", e)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.time() - self._start) * 1000)
        status = "error" if exc_type else "success"
        error_msg = str(exc_val) if exc_val else None

        try:
            if self._span:
                self._span.end(
                    status_message=status,
                    metadata={"duration_ms": duration_ms},
                )
        except Exception as e:
            logger.debug("Langfuse span end failed: %s", e)

        # Always log locally
        _persist_trace(
            incident_id=self.incident_id,
            trace_id=self.trace_id,
            stage=self.stage,
            status=status,
            duration_ms=duration_ms,
            error_msg=error_msg,
            metadata=self.metadata,
        )

    def log_generation(
        self,
        name: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        input_data: Any = None,
        output_data: Any = None,
    ):
        try:
            if self._trace:
                self._trace.generation(
                    name=name,
                    model=model,
                    usage={"input": input_tokens, "output": output_tokens},
                    input=str(input_data)[:2000] if input_data else None,
                    output=str(output_data)[:2000] if output_data else None,
                )
        except Exception as e:
            logger.debug("Langfuse generation log failed: %s", e)

        # Also persist token usage locally
        _persist_trace(
            incident_id=self.incident_id,
            trace_id=self.trace_id,
            stage=self.stage,
            status="success",
            duration_ms=0,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_used=model,
            metadata={"generation": name},
        )


def _persist_trace(
    incident_id,
    trace_id,
    stage,
    status,
    duration_ms=0,
    input_tokens=0,
    output_tokens=0,
    model_used=None,
    error_msg=None,
    metadata=None,
):
    try:
        import json
        execute(
            """
            INSERT INTO agent_traces
                (incident_id, trace_id, stage, status, duration_ms,
                 input_tokens, output_tokens, model_used, error_msg, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                incident_id,
                trace_id,
                stage,
                status,
                duration_ms,
                input_tokens or 0,
                output_tokens or 0,
                model_used,
                error_msg,
                json.dumps(metadata or {}),
            ),
        )
    except Exception as e:
        logger.error("Failed to persist trace: %s", e)


class _NoOpLangfuse:
    """Fallback when Langfuse is unavailable — keeps local-only logging."""
    def trace(self, **kwargs):
        return _NoOpTrace()

    def flush(self):
        pass


class _NoOpTrace:
    def span(self, **kwargs):
        return _NoOpSpan()

    def generation(self, **kwargs):
        pass


class _NoOpSpan:
    def end(self, **kwargs):
        pass
