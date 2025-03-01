"""Create DOI table

Revision ID: ae1eb2a4c03a
Revises: 25a8f93fb344
Create Date: 2024-09-15 21:33:37.837053

"""

from sqlalchemy import inspect
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "ae1eb2a4c03a"
down_revision: Union[str, None] = "25a8f93fb344"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name, column_name):
    bind = op.get_context().bind
    insp = inspect(bind)
    columns = insp.get_columns(table_name)
    return any(c["name"] == column_name for c in columns)


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "dois",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("identifier", sa.String(length=256), nullable=False),
        sa.Column("mode", sa.String(length=256), nullable=False),
        sa.Column("prefix", sa.String(length=256), nullable=True),
        sa.Column("suffix", sa.String(length=256), nullable=True),
        sa.Column("url", sa.String(length=256), nullable=True),
        sa.Column("state", sa.String(length=256), nullable=True),
        sa.Column("doi", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_versions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_identifier", "dois", ["identifier"], unique=False)
    op.add_column(
        "dataset_versions",
        sa.Column("doi_identifier", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "dataset_versions", sa.Column("doi_state", sa.String(length=256), nullable=True)
    )
    if column_exists("dataset_versions", "zip_status"):
        op.drop_column("dataset_versions", "zip_status")

    if column_exists("dataset_versions", "zip_id"):
        op.drop_column("dataset_versions", "zip_id")
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "dataset_versions",
        sa.Column("zip_id", postgresql.UUID(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "dataset_versions",
        sa.Column(
            "zip_status", sa.VARCHAR(length=64), autoincrement=False, nullable=True
        ),
    )
    op.drop_column("dataset_versions", "doi_state")
    op.drop_column("dataset_versions", "doi_identifier")
    op.drop_index("idx_identifier", table_name="dois")
    op.drop_table("dois")
    # ### end Alembic commands ###
