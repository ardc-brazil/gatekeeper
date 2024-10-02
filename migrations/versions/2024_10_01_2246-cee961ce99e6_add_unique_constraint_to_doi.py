"""Add unique constraint to DOI

Revision ID: cee961ce99e6
Revises: ae1eb2a4c03a
Create Date: 2024-10-01 22:46:30.944613

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cee961ce99e6'
down_revision: Union[str, None] = 'ae1eb2a4c03a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('idx_identifier', table_name='dois')
    op.create_index('idx_identifier', 'dois', ['identifier'], unique=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('idx_identifier', table_name='dois')
    op.create_index('idx_identifier', 'dois', ['identifier'], unique=False)
    # ### end Alembic commands ###
