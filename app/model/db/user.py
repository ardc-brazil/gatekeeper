import sqlalchemy
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
from sqlalchemy import Column, String, Boolean, DateTime, Table, ForeignKey, Integer

user_provider_association = Table(
    "user_provider",
    Base.metadata,
    Column(
        "user_id", UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    ),
    Column(
        "provider_id", Integer, ForeignKey("providers.id"), primary_key=True
    ),
)

user_tenancy_association = Table(
    "users_tenancies",
    Base.metadata,
    Column(
        "user_id", UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    ),
    Column(
        "tenancy", String(256), ForeignKey("tenancies.name"), primary_key=True
    ),
)


class User(Base):
    __tablename__ = "users"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    name = Column(String(256), nullable=False)
    email = Column(String(256), nullable=True)
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

    providers = relationship(
        "Provider", lazy="subquery", secondary=user_provider_association, backref="users"
    )
    tenancies = relationship(
        "Tenancy", lazy="subquery", secondary=user_tenancy_association, backref="users"
    )

    __table_args__ = (Index("idx_users_email", email, unique=True),)


class Provider(Base):
    __tablename__ = "providers"
    id = Column(Integer, primary_key=True)
    name = Column(String(256), nullable=False)
    reference = Column(String(256), nullable=True)

    __table_args__ = (
        Index("idx_providers_reference", name, unique=False),
        Index("idx_providers_name", name, unique=False),
    )
