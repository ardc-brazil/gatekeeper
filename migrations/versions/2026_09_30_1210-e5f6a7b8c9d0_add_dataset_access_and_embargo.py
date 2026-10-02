"""Add per-dataset permissions, the access audit trail and the embargo columns

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-30 12:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column("embargo_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "datasets",
        sa.Column(
            "embargo_metadata_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("datasets", sa.Column("embargo_note", sa.Text(), nullable=True))

    op.create_table(
        "dataset_permissions",
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datasets.id"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            primary_key=True,
        ),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column(
            "granted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "level IN ('read', 'write')", name="ck_dataset_permissions_level"
        ),
    )
    op.create_index("idx_dataset_permissions_user", "dataset_permissions", ["user_id"])

    op.create_table(
        "dataset_access_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datasets.id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column(
            "changed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_dataset_access_events_dataset",
        "dataset_access_events",
        ["dataset_id", sa.text("occurred_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_dataset_access_events_dataset", table_name="dataset_access_events"
    )
    op.drop_table("dataset_access_events")
    op.drop_index("idx_dataset_permissions_user", table_name="dataset_permissions")
    op.drop_table("dataset_permissions")
    op.drop_column("datasets", "embargo_note")
    op.drop_column("datasets", "embargo_metadata_visible")
    op.drop_column("datasets", "embargo_until")
