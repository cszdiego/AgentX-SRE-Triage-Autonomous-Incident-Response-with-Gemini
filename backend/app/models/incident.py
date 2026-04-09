from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class IncidentCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=10, max_length=5000)
    reporter_email: str = Field(...)
    reporter_name: Optional[str] = None
    environment: Optional[str] = "production"
    affected_service: Optional[str] = None


class IncidentResponse(BaseModel):
    id: str
    title: str
    description: str
    reporter_email: str
    reporter_name: Optional[str]
    severity: Optional[str]
    status: str
    affected_service: Optional[str]
    environment: Optional[str]
    triage_summary: Optional[str]
    root_cause: Optional[str]
    runbook: Optional[str]
    attachment_path: Optional[str]
    attachment_type: Optional[str]
    attachment_name: Optional[str]
    duplicate_of: Optional[str]
    similarity_score: Optional[float]
    langfuse_trace_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class TriageResult(BaseModel):
    """Structured output from the AI triage agent."""
    severity: str = Field(..., description="P1, P2, P3, or P4")
    affected_service: str = Field(..., description="Name of the eShop service affected")
    triage_summary: str = Field(..., description="2-3 sentence technical summary of the incident")
    root_cause: str = Field(..., description="Identified or suspected root cause")
    runbook: str = Field(..., description="Step-by-step remediation steps as markdown")
    is_duplicate: bool = Field(default=False)
    duplicate_of: Optional[str] = Field(default=None, description="UUID of existing incident if duplicate")
    similarity_score: Optional[float] = Field(default=None)
    keywords: list[str] = Field(default_factory=list, description="Key technical terms for deduplication")
