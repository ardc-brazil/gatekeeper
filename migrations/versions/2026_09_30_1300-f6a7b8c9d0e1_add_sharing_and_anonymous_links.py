"""Add dataset invitations, anonymous links and their views

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-30 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dataset_invitations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datasets.id"),
            nullable=False,
        ),
        sa.Column("email", sa.String(256), nullable=True),
        sa.Column("orcid", sa.String(32), nullable=True),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "invited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "accepted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "email IS NOT NULL OR orcid IS NOT NULL",
            name="ck_dataset_invitations_target",
        ),
    )
    op.create_index(
        "idx_dataset_invitations_dataset", "dataset_invitations", ["dataset_id"]
    )
    op.create_index("idx_dataset_invitations_orcid", "dataset_invitations", ["orcid"])
    op.execute(
        "CREATE INDEX idx_dataset_invitations_email "
        "ON dataset_invitations (lower(email))"
    )

    op.create_table(
        "dataset_anonymous_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datasets.id"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_dataset_anonymous_links_dataset", "dataset_anonymous_links", ["dataset_id"]
    )

    op.create_table(
        "dataset_anonymous_link_views",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "link_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dataset_anonymous_links.id"),
            nullable=False,
        ),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column(
            "viewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_dataset_anonymous_link_views_link",
        "dataset_anonymous_link_views",
        ["link_id", "viewed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_dataset_anonymous_link_views_link",
        table_name="dataset_anonymous_link_views",
    )
    op.drop_table("dataset_anonymous_link_views")
    op.drop_index(
        "idx_dataset_anonymous_links_dataset", table_name="dataset_anonymous_links"
    )
    op.drop_table("dataset_anonymous_links")
    op.execute("DROP INDEX IF EXISTS idx_dataset_invitations_email")
    op.drop_index("idx_dataset_invitations_orcid", table_name="dataset_invitations")
    op.drop_index("idx_dataset_invitations_dataset", table_name="dataset_invitations")
    op.drop_table("dataset_invitations")
