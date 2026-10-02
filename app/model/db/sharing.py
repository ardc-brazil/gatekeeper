import sqlalchemy
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class DatasetInvitation(Base):
    __tablename__ = "dataset_invitations"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False)
    email = Column(String(256), nullable=True)
    orcid = Column(String(32), nullable=True)
    level = Column(String(16), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    accepted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "email IS NOT NULL OR orcid IS NOT NULL",
            name="ck_dataset_invitations_target",
        ),
        Index("idx_dataset_invitations_dataset", "dataset_id"),
        Index("idx_dataset_invitations_orcid", "orcid"),
    )


class DatasetAnonymousLink(Base):
    __tablename__ = "dataset_anonymous_links"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    label = Column(String(256), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_dataset_anonymous_links_dataset", "dataset_id"),)


class DatasetAnonymousLinkView(Base):
    __tablename__ = "dataset_anonymous_link_views"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    link_id = Column(
        UUID(as_uuid=True), ForeignKey("dataset_anonymous_links.id"), nullable=False
    )
    outcome = Column(String(32), nullable=False)
    viewed_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_dataset_anonymous_link_views_link", "link_id", "viewed_at"),
    )
