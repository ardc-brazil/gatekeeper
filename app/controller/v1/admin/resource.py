from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EmailSummaryResponse(BaseModel):
    id: UUID
    template: str
    recipient: str
    subject: str
    status: str
    attempts: int
    related_type: Optional[str]
    related_id: Optional[UUID]
    triggered_by: Optional[UUID]
    created_at: datetime
    sent_at: Optional[datetime]


class EmailListResponse(BaseModel):
    items: list[EmailSummaryResponse]
    total_count: int
    page: int
    page_size: int


class EmailEventResponse(BaseModel):
    event: str
    detail: Optional[str]
    occurred_at: datetime


class EmailDetailResponse(EmailSummaryResponse):
    template_version: str
    body_text: str
    context: dict
    smtp_message_id: Optional[str]
    next_attempt_at: datetime
    events: list[EmailEventResponse]


class TestEmailRequest(BaseModel):
    recipient: str = Field(..., min_length=3, max_length=256, description="Address")


class TestEmailResponse(BaseModel):
    id: UUID
