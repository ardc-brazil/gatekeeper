"""Domain model for extraction jobs."""

import enum
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class ExtractionStatus(enum.Enum):
    """Status of an extraction job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ExtractionJob:
    """Extraction job for metadata processing."""

    data_file_id: UUID
    status: ExtractionStatus = ExtractionStatus.PENDING
    error_message: str | None = None
    id: UUID | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
