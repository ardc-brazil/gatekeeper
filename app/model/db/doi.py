import sqlalchemy
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import (
    Index,
    Column,
    String,
    DateTime,
    ForeignKey,
)
from sqlalchemy.sql import func
from app.database import Base


class DOI(Base):
    __tablename__ = "dois"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )

    identifier = Column(String(256), nullable=False)
    mode = Column(String(256), nullable=False)
    prefix = Column(String(256), nullable=True)
    suffix = Column(String(256), nullable=True)
    url = Column(String(256), nullable=True)
    state = Column(String(256), nullable=True)
    doi = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    version_id = Column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id"), nullable=False
    )

    __table_args__ = (Index("idx_identifier", "identifier"),)
