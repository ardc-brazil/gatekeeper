from sqlalchemy.sql import func
from database import Base
from sqlalchemy import Column, String, Boolean, DateTime

class Tenancy(Base):
    __tablename__ = "tenancies"
    name = Column(String(256), primary_key=True)
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
    # TODO add created_by
