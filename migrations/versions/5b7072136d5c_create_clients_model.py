"""Create clients model

Revision ID: 5b7072136d5c
Revises: d6ce4ea9f762
Create Date: 2023-08-03 23:30:11.588621

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "5b7072136d5c"
down_revision = "d6ce4ea9f762"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "clients",
        sa.Column(
            "key",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("secret", sa.String(length=256), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("clients")
    # ### end Alembic commands ###
