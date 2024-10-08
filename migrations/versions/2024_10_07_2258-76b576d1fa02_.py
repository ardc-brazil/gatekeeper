"""Allow null version_id in data_files

Revision ID: 76b576d1fa02
Revises: f1eedf1bf8a0
Create Date: 2024-10-07 22:58:26.202449

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '76b576d1fa02'
down_revision: Union[str, None] = 'f1eedf1bf8a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('data_files', 'version_id',
               existing_type=postgresql.UUID(),
               nullable=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('data_files', 'version_id',
               existing_type=postgresql.UUID(),
               nullable=False)
    # ### end Alembic commands ###
