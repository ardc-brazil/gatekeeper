"""Fix dataset version

Revision ID: 5e0cc8b6adec
Revises: 1b734026a7dc
Create Date: 2024-04-07 22:41:57.987285

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '5e0cc8b6adec'
down_revision = '1b734026a7dc'
branch_labels = None
depends_on = None

def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('datasets', sa.Column('version_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_unique_constraint('datasets_version_id_fkey', 'datasets', ['version_id'])
    op.create_foreign_key('datasets_version_id_key', 'datasets', 'dataset_versions', ['version_id'], ['id'])
    op.drop_table('dataset_version')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('datasets_version_id_fkey', 'datasets', type_='foreignkey')
    op.drop_constraint('datasets_version_id_key', 'datasets', type_='unique')
    op.drop_column('datasets', 'version_id')
    op.create_table('dataset_version',
    sa.Column('dataset_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('version_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ),
    sa.ForeignKeyConstraint(['version_id'], ['dataset_versions.id'], ),
    sa.PrimaryKeyConstraint('dataset_id', 'version_id')
    )
    # ### end Alembic commands ###
