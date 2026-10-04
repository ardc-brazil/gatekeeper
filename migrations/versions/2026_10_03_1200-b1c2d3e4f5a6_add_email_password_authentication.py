"""Email and password authentication: credentials on users, pending challenges

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-10-03 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(128), nullable=True))
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "failed_login_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table(
        "auth_challenges",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("secret_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('sign_up', 'email_verification', 'password_reset')",
            name="ck_auth_challenges_kind",
        ),
    )
    op.create_index(
        "idx_auth_challenges_open",
        "auth_challenges",
        ["kind", "email"],
        postgresql_where=sa.text("consumed_at IS NULL"),
    )
    op.create_index("idx_auth_challenges_user", "auth_challenges", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_auth_challenges_user", table_name="auth_challenges")
    op.drop_index("idx_auth_challenges_open", table_name="auth_challenges")
    op.drop_table("auth_challenges")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "password_hash")
