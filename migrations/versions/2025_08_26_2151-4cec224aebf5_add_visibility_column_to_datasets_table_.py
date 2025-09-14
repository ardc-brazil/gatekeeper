"""Add visibility column to datasets table with VisibilityStatus enum

Revision ID: 4cec224aebf5
Revises: cd7a3d29e3f3
Create Date: 2025-08-26 21:51:10.650689

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4cec224aebf5"
down_revision: Union[str, None] = "cd7a3d29e3f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type first
    visibility_status_enum = sa.Enum("PRIVATE", "PUBLIC", name="visibilitystatus")
    visibility_status_enum.create(op.get_bind())
    
    # Then add the column using the enum type
    op.add_column(
        "datasets",
        sa.Column(
            "visibility",
            visibility_status_enum,
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Drop the column first
    op.drop_column("datasets", "visibility")
    
    # Then drop the enum type
    visibility_status_enum = sa.Enum("PRIVATE", "PUBLIC", name="visibilitystatus")
    visibility_status_enum.drop(op.get_bind())
