"""Add tenancy to users

Revision ID: 1a67325e7c53
Revises: dda42082853d
Create Date: 2024-02-13 19:03:16.708713

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '1a67325e7c53'
down_revision = 'dda42082853d'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('users_tenancies',
    sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('tenancy', sa.String(length=256), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'tenancy')
    )
    op.create_index('idx_users_tenancies_user_id', 'users_tenancies', ['user_id'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('idx_users_tenancies_user_id', table_name='users_tenancies')
    op.drop_table('users_tenancies')
    # ### end Alembic commands ###
