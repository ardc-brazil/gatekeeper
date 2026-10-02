import sqlalchemy
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


class DatasetPermission(Base):
    __tablename__ = "dataset_permissions"
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    level = Column(String(16), nullable=False)
    granted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "level IN ('read', 'write')", name="ck_dataset_permissions_level"
        ),
        Index("idx_dataset_permissions_user", "user_id"),
    )


class DatasetAccessEvent(Base):
    __tablename__ = "dataset_access_events"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False)
    event_type = Column(String(32), nullable=False)
    old_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=True)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    note = Column(Text, nullable=True)
    occurred_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sqlalchemy.text("now()"),
    )

    __table_args__ = (
        Index(
            "idx_dataset_access_events_dataset",
            "dataset_id",
            sqlalchemy.text("occurred_at DESC"),
        ),
    )
