"""Add file_collocation_status column to datasets table

Revision ID: a1f2c3d4e5f6
Revises: 4cec224aebf5
Create Date: 2025-12-02 20:17:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1f2c3d4e5f6"
down_revision: Union[str, None] = "4cec224aebf5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type first
    file_collocation_status_enum = sa.Enum(
        "pending", "processing", "completed", name="filecollocationstatus"
    )
    file_collocation_status_enum.create(op.get_bind())

    # Then add the column using the enum type
    op.add_column(
        "datasets",
        sa.Column(
            "file_collocation_status",
            file_collocation_status_enum,
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Drop the column first
    op.drop_column("datasets", "file_collocation_status")

    # Then drop the enum type
    file_collocation_status_enum = sa.Enum(
        "pending", "processing", "completed", name="filecollocationstatus"
    )
    file_collocation_status_enum.drop(op.get_bind())
