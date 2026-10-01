from dataclasses import dataclass
from datetime import datetime
import enum
from uuid import UUID


class EmailStatus(str, enum.Enum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class EmailEventType(str, enum.Enum):
    QUEUED = "queued"
    ATTEMPT_FAILED = "attempt_failed"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class EmailRecord:
    id: UUID
    template: str
    template_version: str
    recipient: str
    subject: str
    body_text: str
    context: dict
    secret_fields: list[str]
    related_type: str | None
    related_id: UUID | None
    triggered_by: UUID | None
    dedup_key: str | None
    status: EmailStatus
    attempts: int
    next_attempt_at: datetime
    smtp_message_id: str | None
    sent_at: datetime | None
    created_at: datetime


@dataclass
class EmailEventRecord:
    id: int
    event: EmailEventType
    detail: str | None
    occurred_at: datetime


@dataclass
class EmailQuery:
    recipient: str | None = None
    related_id: UUID | None = None
    template: str | None = None
    status: EmailStatus | None = None
    page: int = 1
    page_size: int = 20


@dataclass
class DispatchResult:
    queued: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    retried: int = 0
