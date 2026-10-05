import sqlalchemy
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base
from app.model.tenancy import (
    TenancyEventType,
    TenancyInvitationStatus,
    TenancyRequestStatus,
)


def _values(enum_class) -> list[str]:
    return [member.value for member in enum_class]


class Tenancy(Base):
    __tablename__ = "tenancies"
    name = Column(String(256), primary_key=True)
    display_name = Column(String(64), nullable=True)
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


class TenancyRequest(Base):
    __tablename__ = "tenancy_requests"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    requested_name = Column(String(128), nullable=False)
    reason = Column(String(1000), nullable=False)
    status = Column(
        Enum(
            TenancyRequestStatus,
            name="tenancy_request_status",
            values_callable=_values,
        ),
        nullable=False,
        default=TenancyRequestStatus.PENDING,
        server_default="pending",
    )
    tenancy = Column(String(256), ForeignKey("tenancies.name"), nullable=True)
    created_tenancy = Column(
        Boolean, nullable=False, default=False, server_default=sqlalchemy.false()
    )
    decision_message = Column(String(1000), nullable=True)
    decided_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index(
            "uq_tenancy_requests_pending",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_tenancy_requests_status_created", "status", "created_at"),
    )


class TenancyInvitation(Base):
    __tablename__ = "tenancy_invitations"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    tenancy = Column(String(256), ForeignKey("tenancies.name"), nullable=False)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    invited_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    dataset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
    )
    status = Column(
        Enum(
            TenancyInvitationStatus,
            name="tenancy_invitation_status",
            values_callable=_values,
        ),
        nullable=False,
        default=TenancyInvitationStatus.PENDING,
        server_default="pending",
    )
    closed_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index(
            "uq_tenancy_invitations_pending",
            "tenancy",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_tenancy_invitations_user_status", "user_id", "status"),
    )


class TenancyEvent(Base):
    __tablename__ = "tenancy_events"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    tenancy = Column(String(256), nullable=True)
    event_type = Column(
        Enum(TenancyEventType, name="tenancy_event_type", values_callable=_values),
        nullable=False,
    )
    user_id = Column(UUID(as_uuid=True), nullable=True)
    actor_id = Column(UUID(as_uuid=True), nullable=True)
    request_id = Column(UUID(as_uuid=True), nullable=True)
    invitation_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_tenancy_events_created", "created_at"),
        Index("ix_tenancy_events_user", "user_id", "created_at"),
    )
