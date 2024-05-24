import sqlalchemy
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base

from sqlalchemy import Column, String, Boolean, DateTime


class Client(Base):
    __tablename__ = "clients"
    key = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    secret = Column(String(256), nullable=False)
    name = Column(String(256), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
