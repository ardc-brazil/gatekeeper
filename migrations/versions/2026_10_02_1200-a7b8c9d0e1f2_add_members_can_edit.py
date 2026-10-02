"""Members of a dataset's tenancy may edit it, or only read it

Revision ID: a7b8c9d0e1f2
Revises: a8b9c0d1e2f3
Create Date: 2026-10-02 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column(
            "members_can_edit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    # Emails queued before this column existed render with the templates that now require the key.
    op.execute(
        """
        UPDATE email_messages
        SET context = context || '{"members_can_edit": true}'::jsonb
        WHERE template IN ('embargo_reminder', 'embargo_ended')
          AND status = 'pending'
          AND NOT context ? 'members_can_edit'
        """
    )


def downgrade() -> None:
    op.drop_column("datasets", "members_can_edit")
