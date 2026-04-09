from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TicketResponse(BaseModel):
    id: str
    incident_id: str
    ticket_key: str
    title: str
    description: str
    priority: Optional[str]
    status: str
    assigned_to: Optional[str]
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime]


class TicketResolve(BaseModel):
    resolution_note: Optional[str] = None
