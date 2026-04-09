"""
Guardrails module — Prompt Injection defense + Input validation.
All blocked attempts are logged to the guardrail_logs table.
"""
import re
import logging
from datetime import datetime, timezone
from app.core.database import execute

logger = logging.getLogger(__name__)

# ── Prompt Injection patterns ──────────────────────────────────────────────
_INJECTION_PATTERNS = [
    # Classic jailbreak phrases
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous",
    r"you\s+are\s+now\s+(?:a|an|the)\s+\w+",
    r"act\s+as\s+(?:a|an|the)?\s*(?:DAN|jailbreak|unrestricted)",
    r"pretend\s+(?:you\s+are|to\s+be)",
    r"your\s+new\s+instructions?\s+are",
    r"override\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions?)",
    r"system\s*:\s*you\s+are",
    r"\[SYSTEM\]",
    r"<\|system\|>",
    r"###\s*instruction",
    r"JAILBREAK",
    r"DAN\s+mode",
    # SQL injection (in case of log injection)
    r";\s*DROP\s+TABLE",
    r";\s*DELETE\s+FROM",
    r"UNION\s+SELECT",
    # Code execution attempts
    r"__import__\s*\(",
    r"eval\s*\(",
    r"exec\s*\(",
    r"os\.system",
    r"subprocess",
    # Exfiltration attempts
    r"send\s+(?:my|your|the)\s+(?:api\s+)?key",
    r"reveal\s+(?:your\s+)?(?:system\s+)?prompt",
    r"print\s+(?:your\s+)?(?:system\s+)?prompt",
    r"what\s+(?:is|are)\s+your\s+instructions?",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _INJECTION_PATTERNS]

# ── PII patterns (warn, don't block) ──────────────────────────────────────
_PII_PATTERNS = [
    r"\b\d{3}-\d{2}-\d{4}\b",           # SSN
    r"\b4[0-9]{12}(?:[0-9]{3})?\b",     # Visa card
    r"\b(?:password|passwd)\s*[:=]\s*\S+",  # passwords
]
_PII_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PII_PATTERNS]


def check_guardrails(
    text: str,
    incident_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[bool, str | None]:
    """
    Returns (is_safe, violation_type).
    Logs violations to guardrail_logs.
    """
    if not text:
        return True, None

    # 1. Length check
    if len(text) > 8000:
        _log_violation(
            incident_id=incident_id,
            snippet=text[:200],
            violation_type="excessive_length",
            severity="low",
            blocked=False,
            action="truncated",
            ip=ip_address,
            ua=user_agent,
        )
        return True, None  # warn but don't block

    # 2. Prompt injection check
    for pattern in _COMPILED_PATTERNS:
        match = pattern.search(text)
        if match:
            snippet = text[max(0, match.start()-20):match.end()+20]
            logger.warning(
                "GUARDRAIL BLOCKED | type=prompt_injection | snippet=%r | ip=%s",
                snippet, ip_address
            )
            _log_violation(
                incident_id=incident_id,
                snippet=snippet,
                violation_type="prompt_injection",
                severity="high",
                blocked=True,
                action="request_rejected",
                ip=ip_address,
                ua=user_agent,
            )
            return False, "prompt_injection"

    # 3. PII detection (log only)
    for pattern in _PII_COMPILED:
        if pattern.search(text):
            _log_violation(
                incident_id=incident_id,
                snippet="[PII DETECTED - redacted]",
                violation_type="pii_leak",
                severity="medium",
                blocked=False,
                action="pii_flagged",
                ip=ip_address,
                ua=user_agent,
            )
            break

    return True, None


def sanitize_for_prompt(text: str) -> str:
    """
    Wrap user content so it cannot escape its context in the prompt.
    """
    # Neutralize any role-separator sequences
    text = re.sub(r"(system|user|assistant)\s*:", "[SANITIZED]:", text, flags=re.IGNORECASE)
    # Strip XML-like tags that could affect model parsing
    text = re.sub(r"<\|.*?\|>", "", text)
    text = re.sub(r"\[\s*INST\s*\]", "", text, flags=re.IGNORECASE)
    return text.strip()


def _log_violation(
    incident_id, snippet, violation_type, severity, blocked, action, ip, ua
):
    try:
        execute(
            """
            INSERT INTO guardrail_logs
                (incident_id, input_snippet, violation_type, severity, blocked, action_taken, ip_address, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (incident_id, snippet[:500], violation_type, severity, blocked, action, ip, ua),
        )
    except Exception as e:
        logger.error("Failed to log guardrail violation: %s", e)
