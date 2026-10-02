import sqlalchemy
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


class EmailMessage(Base):
    __tablename__ = "email_messages"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    template = Column(String(64), nullable=False)
    template_version = Column(String(64), nullable=False)
    recipient = Column(String(256), nullable=False)
    subject = Column(Text, nullable=False)
    body_text = Column(Text, nullable=False)
    context = Column(JSONB, nullable=False)
    secret_fields = Column(
        JSONB, nullable=False, server_default=sqlalchemy.text("'[]'::jsonb")
    )
    related_type = Column(String(32), nullable=True)
    related_id = Column(UUID(as_uuid=True), nullable=True)
    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    dedup_key = Column(String(256), nullable=True, unique=True)
    status = Column(String(16), nullable=False, server_default="pending")
    attempts = Column(Integer, nullable=False, server_default="0")
    next_attempt_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    smtp_message_id = Column(String(256), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "idx_email_messages_due",
            "next_attempt_at",
            postgresql_where=sqlalchemy.text("status = 'pending'"),
        ),
        Index("idx_email_messages_related", "related_type", "related_id", "created_at"),
    )


class EmailEvent(Base):
    __tablename__ = "email_events"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    message_id = Column(
        UUID(as_uuid=True), ForeignKey("email_messages.id"), nullable=False
    )
    event = Column(String(16), nullable=False)
    detail = Column(Text, nullable=True)
    occurred_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_email_events_message", "message_id", "occurred_at"),)
