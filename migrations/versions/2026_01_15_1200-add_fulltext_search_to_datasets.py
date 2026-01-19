"""Add full-text search support to datasets table

Revision ID: c3h4i5j6k7l8
Revises: b2g3h4i5j6k7
Create Date: 2026-01-15 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3h4i5j6k7l8"
down_revision: Union[str, None] = "b2g3h4i5j6k7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable unaccent extension for accent-insensitive search
    # Note: DB user needs CREATE privilege, or extension pre-installed on managed DBs
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # 2. Add search_vector column to store normalized searchable text
    op.add_column("datasets", sa.Column("search_vector", sa.Text(), nullable=True))

    # 3. Create GIN index for fast full-text search
    op.execute(
        """
        CREATE INDEX idx_datasets_search_vector
        ON datasets USING GIN(to_tsvector('simple', coalesce(search_vector, '')))
        """
    )

    # 4. Create trigger function to keep search_vector updated on INSERT/UPDATE
    op.execute(
        """
        CREATE OR REPLACE FUNCTION datasets_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := unaccent(
                coalesce(NEW.name, '') || ' ' ||
                coalesce(NEW.data->>'category', '') || ' ' ||
                coalesce(NEW.data->>'institution', '') || ' ' ||
                coalesce(NEW.data->>'description', '')
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # 5. Create trigger to automatically update search_vector
    op.execute(
        """
        CREATE TRIGGER datasets_search_vector_trigger
        BEFORE INSERT OR UPDATE ON datasets
        FOR EACH ROW EXECUTE FUNCTION datasets_search_vector_update();
        """
    )

    # 6. Populate search_vector for existing records by triggering an update
    op.execute("UPDATE datasets SET name = name WHERE name IS NOT NULL")


def downgrade() -> None:
    # Drop trigger first
    op.execute("DROP TRIGGER IF EXISTS datasets_search_vector_trigger ON datasets")

    # Drop trigger function
    op.execute("DROP FUNCTION IF EXISTS datasets_search_vector_update()")

    # Drop index
    op.execute("DROP INDEX IF EXISTS idx_datasets_search_vector")

    # Drop column
    op.drop_column("datasets", "search_vector")

    # Note: Not dropping unaccent extension as other things may depend on it
