import sqlalchemy
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    kind = Column(String(32), nullable=False)
    email = Column(String(256), nullable=False)
    secret_hash = Column(String(128), nullable=False, unique=True)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=False)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    payload = Column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sqlalchemy.text("'{}'::jsonb"),
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('sign_up', 'email_verification', 'password_reset')",
            name="ck_auth_challenges_kind",
        ),
        Index(
            "idx_auth_challenges_open",
            "kind",
            "email",
            postgresql_where=sqlalchemy.text("consumed_at IS NULL"),
        ),
        Index("idx_auth_challenges_user", "user_id"),
    )
