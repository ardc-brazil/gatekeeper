"""Remove relationship tables

Revision ID: 5d694feebd55
Revises: 288049ad530c
Create Date: 2024-04-08 21:57:29.364032

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "5d694feebd55"
down_revision = "288049ad530c"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("dataset_version")
    op.drop_table("dataset_file")
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "dataset_file",
        sa.Column("dataset_id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("file_id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name="dataset_file_dataset_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["data_files.id"], name="dataset_file_file_id_fkey"
        ),
        sa.PrimaryKeyConstraint("dataset_id", "file_id", name="dataset_file_pkey"),
    )
    op.create_table(
        "dataset_version",
        sa.Column("dataset_id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("version_id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name="dataset_version_dataset_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_versions.id"],
            name="dataset_version_version_id_fkey",
        ),
        sa.PrimaryKeyConstraint(
            "dataset_id", "version_id", name="dataset_version_pkey"
        ),
    )
    # ### end Alembic commands ###
