"""Keep a short hint of each anonymous link's token

Revision ID: a8b9c0d1e2f3
Revises: f6a7b8c9d0e1
Create Date: 2026-09-30 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset_anonymous_links", sa.Column("token_hint", sa.String(16), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("dataset_anonymous_links", "token_hint")
