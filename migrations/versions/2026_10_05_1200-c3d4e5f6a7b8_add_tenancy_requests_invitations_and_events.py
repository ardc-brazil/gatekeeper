"""Public tenancy for everyone, datasets_write for accounts without a dataset role,
datasets closed to members by default, tenancy requests, invitations and events

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-10-05 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PUBLIC = "datamap/production/public"
RETIRED_TEMPLATE = "new_account_pending"

ENUMS = {
    "tenancy_request_status": ("pending", "approved", "declined", "withdrawn"),
    "tenancy_invitation_status": (
        "pending",
        "accepted",
        "declined",
        "withdrawn",
        "revoked",
    ),
    "tenancy_event_type": (
        "tenancy_created",
        "member_added",
        "member_removed",
        "request_created",
        "request_approved",
        "request_declined",
        "request_withdrawn",
        "invitation_created",
        "invitation_accepted",
        "invitation_declined",
        "invitation_withdrawn",
    ),
}

DATASETS_WRITE_DELETE_PATHS = (
    "/api/v1/datasets/[0-9a-fA-F-]{36}/share/(permissions|invitations)/[0-9a-fA-F-]{36}$",
    "/api/v1/datasets/[0-9a-fA-F-]{36}/tenancy-invitations/[0-9a-fA-F-]{36}$",
    "/api/v1/datasets/[0-9a-fA-F-]{36}/anonymous-links/[0-9a-fA-F-]{36}$",
)


def _create_enum(name: str, values: tuple[str, ...]) -> None:
    labels = ", ".join(f"'{value}'" for value in values)
    op.execute(
        f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({labels}); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tenancies ADD COLUMN IF NOT EXISTS display_name VARCHAR(64)"
    )

    op.execute(
        f"""
        INSERT INTO tenancies (name, display_name, is_enabled, created_at, updated_at)
        VALUES ('{PUBLIC}', 'Public', true, now(), now())
        ON CONFLICT (name) DO UPDATE
        SET is_enabled = true,
            display_name = COALESCE(tenancies.display_name, 'Public')
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tenancies_display_name "
        "ON tenancies (lower(display_name)) "
        "WHERE display_name IS NOT NULL AND is_enabled "
        "AND name LIKE 'datamap/production/%'"
    )

    op.execute(
        f"""
        INSERT INTO users_tenancies (user_id, tenancy)
        SELECT id, '{PUBLIC}' FROM users
        ON CONFLICT DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO casbin_rule (ptype, v0, v1)
        SELECT 'g', CAST(u.id AS VARCHAR), 'datasets_write'
        FROM users u
        WHERE NOT EXISTS (
            SELECT 1 FROM casbin_rule c
            WHERE c.ptype = 'g'
              AND c.v0 = CAST(u.id AS VARCHAR)
              AND c.v1 IN ('admin', 'datasets_read', 'datasets_write', 'datasets_admin')
        )
        """
    )

    for path in DATASETS_WRITE_DELETE_PATHS:
        op.execute(
            f"""
            INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5)
            SELECT 'p', 'datasets_write', '{path}', 'DELETE', 'allow', NULL, NULL
            WHERE NOT EXISTS (
                SELECT 1 FROM casbin_rule c
                WHERE c.ptype = 'p'
                  AND c.v0 = 'datasets_write'
                  AND c.v1 = '{path}'
                  AND c.v2 = 'DELETE'
                  AND c.v3 = 'allow'
            )
            """
        )

    op.execute("ALTER TABLE datasets ALTER COLUMN members_can_edit SET DEFAULT false")
    op.execute(
        f"UPDATE datasets SET members_can_edit = false "
        f"WHERE tenancy = '{PUBLIC}' AND members_can_edit"
    )

    for name, values in ENUMS.items():
        _create_enum(name, values)

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenancy_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            requested_name VARCHAR(128) NOT NULL,
            reason VARCHAR(1000) NOT NULL,
            status tenancy_request_status NOT NULL DEFAULT 'pending',
            tenancy VARCHAR(256) REFERENCES tenancies (name),
            created_tenancy BOOLEAN NOT NULL DEFAULT false,
            decision_message VARCHAR(1000),
            decided_by UUID REFERENCES users (id) ON DELETE SET NULL,
            decided_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tenancy_requests_pending "
        "ON tenancy_requests (user_id) WHERE status = 'pending'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenancy_requests_status_created "
        "ON tenancy_requests (status, created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenancy_invitations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenancy VARCHAR(256) NOT NULL REFERENCES tenancies (name),
            user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            invited_by UUID REFERENCES users (id) ON DELETE SET NULL,
            dataset_id UUID REFERENCES datasets (id) ON DELETE SET NULL,
            status tenancy_invitation_status NOT NULL DEFAULT 'pending',
            closed_by UUID REFERENCES users (id) ON DELETE SET NULL,
            closed_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tenancy_invitations_pending "
        "ON tenancy_invitations (tenancy, user_id) WHERE status = 'pending'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenancy_invitations_user_status "
        "ON tenancy_invitations (user_id, status)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenancy_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenancy VARCHAR(256),
            event_type tenancy_event_type NOT NULL,
            user_id UUID,
            actor_id UUID,
            request_id UUID,
            invitation_id UUID,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenancy_events_created "
        "ON tenancy_events (created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenancy_events_user "
        "ON tenancy_events (user_id, created_at)"
    )

    op.execute(
        """
        INSERT INTO tenancy_events (tenancy, event_type, user_id)
        SELECT ut.tenancy, 'member_added', ut.user_id
        FROM users_tenancies ut
        WHERE NOT EXISTS (
            SELECT 1 FROM tenancy_events e
            WHERE e.tenancy = ut.tenancy
              AND e.user_id = ut.user_id
              AND e.event_type = 'member_added'
        )
        """
    )

    op.execute(
        f"""
        WITH retired AS (
            UPDATE email_messages SET status = 'skipped'
            WHERE template = '{RETIRED_TEMPLATE}' AND status = 'pending'
            RETURNING id
        )
        INSERT INTO email_events (message_id, event, detail)
        SELECT id, 'skipped', 'template retired' FROM retired
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenancy_events")
    op.execute("DROP TABLE IF EXISTS tenancy_invitations")
    op.execute("DROP TABLE IF EXISTS tenancy_requests")
    for name in reversed(list(ENUMS)):
        op.execute(f"DROP TYPE IF EXISTS {name}")
    op.execute("ALTER TABLE datasets ALTER COLUMN members_can_edit SET DEFAULT true")
    op.execute("ALTER TABLE tenancies DROP COLUMN IF EXISTS display_name")
