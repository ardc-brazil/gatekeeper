import sqlalchemy
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import (
    Index,
    Enum,
    Column,
    String,
    DateTime,
    ForeignKey,
)
from sqlalchemy.sql import func
from app.database import Base
from app.model.extraction_job import ExtractionStatus


class ExtractionJob(Base):
    __tablename__ = "extraction_jobs"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    data_file_id = Column(
        UUID(as_uuid=True),
        ForeignKey("data_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(
        Enum(
            ExtractionStatus,
            name="extractionstatus",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=ExtractionStatus.PENDING,
    )
    error_message = Column(String(2048), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_extraction_jobs_status", "status"),
        Index("idx_extraction_jobs_data_file_id", "data_file_id"),
    )
