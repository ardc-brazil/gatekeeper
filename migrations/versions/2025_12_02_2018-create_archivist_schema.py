"""Create archivist_schema for archivist service

Revision ID: b2g3h4i5j6k7
Revises: a1f2c3d4e5f6
Create Date: 2025-12-02 20:18:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b2g3h4i5j6k7"
down_revision: Union[str, None] = "a1f2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create schema for archivist service
    # APScheduler will create its own tables in this schema
    op.execute("CREATE SCHEMA IF NOT EXISTS archivist_schema")


def downgrade() -> None:
    # Drop the archivist schema
    # This will fail if there are objects in the schema, which is intentional
    # to prevent accidental data loss
    op.execute("DROP SCHEMA IF EXISTS archivist_schema CASCADE")
