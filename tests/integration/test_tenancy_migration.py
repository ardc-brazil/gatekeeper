import subprocess
import uuid

import pytest

from tests.integration.utils.database import execute

pytestmark = pytest.mark.destructive_migration

GATEKEEPER_CONTAINER = "datamap_gatekeeper_test_integration"
PUBLIC = "datamap/production/public"
DATA_AMAZON = "datamap/production/data-amazon"
THIS_REVISION = "c3d4e5f6a7b8"
PREVIOUS_REVISION = "b1c2d3e4f5a6"
DATASETS_WRITE_DELETE_PATHS = (
    "/api/v1/datasets/[0-9a-fA-F-]{36}/share/(permissions|invitations)/[0-9a-fA-F-]{36}$",
    "/api/v1/datasets/[0-9a-fA-F-]{36}/anonymous-links/[0-9a-fA-F-]{36}$",
)
DATASETS_WRITE_DELETE_RULES = (
    "ptype = 'p' AND v0 = 'datasets_write' AND v2 = 'DELETE' AND v1 IN ("
    + ", ".join(f"'{path}'" for path in DATASETS_WRITE_DELETE_PATHS)
    + ")"
)
COUNTS = (
    "SELECT (SELECT count(*) FROM users_tenancies), (SELECT count(*) FROM casbin_rule)"
)


@pytest.fixture(scope="module", autouse=True)
def keep_display_names():
    execute("DROP TABLE IF EXISTS migration_test_display_names")
    execute(
        "CREATE TABLE migration_test_display_names AS "
        "SELECT name, display_name FROM tenancies WHERE display_name IS NOT NULL"
    )
    yield
    _alembic("upgrade", "head")
    execute(
        "UPDATE tenancies t SET display_name = b.display_name "
        "FROM migration_test_display_names b WHERE t.name = b.name"
    )
    execute("DROP TABLE migration_test_display_names")


def _alembic(*args: str) -> str:
    completed = subprocess.run(
        ["docker", "exec", GATEKEEPER_CONTAINER, "python3", "-m", "alembic", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout + completed.stderr


def _user(name: str) -> str:
    user_id = str(uuid.uuid4())
    execute(
        "INSERT INTO users (id, name, email, is_enabled, created_at, updated_at) "
        f"VALUES ('{user_id}', '{name}', '{user_id}@example.com', true, now(), now())"
    )
    return user_id


def _dataset(tenancy: str) -> str:
    dataset_id = str(uuid.uuid4())
    execute(
        "INSERT INTO datasets (id, name, data, is_enabled, tenancy, members_can_edit, "
        "created_at, updated_at) "
        f"VALUES ('{dataset_id}', 'migration', '{{}}'::jsonb, true, '{tenancy}', true, "
        "now(), now())"
    )
    return dataset_id


def _queued_email(template: str, status: str = "pending") -> str:
    email_id = str(uuid.uuid4())
    execute(
        "INSERT INTO email_messages (id, template, template_version, recipient, "
        "subject, body_text, context, status, next_attempt_at) "
        f"VALUES ('{email_id}', '{template}', '1', '{email_id}@example.com', "
        f"'s', 'b', '{{}}'::jsonb, '{status}', now() + interval '1 day')"
    )
    return email_id


def _email_status(email_id: str) -> str:
    return execute(
        "SELECT m.status, coalesce(e.event, ''), coalesce(e.detail, '') "
        "FROM email_messages m LEFT JOIN email_events e ON e.message_id = m.id "
        f"WHERE m.id = '{email_id}'"
    )


def _roles(user_id: str) -> list[str]:
    return execute(
        f"SELECT v1 FROM casbin_rule WHERE ptype = 'g' AND v0 = '{user_id}' ORDER BY v1"
    ).split()


class TestTheMigration:
    def test_it_backfills_public_roles_and_defaults_and_survives_a_round_trip(self):
        plain = _user("Plain Account")
        reader = _user("Read Only")
        boss = _user("Admin Only")
        clerk = _user("Users Write Only")
        execute(
            "INSERT INTO casbin_rule (ptype, v0, v1) VALUES "
            f"('g', '{reader}', 'datasets_read'), ('g', '{boss}', 'admin'), "
            f"('g', '{clerk}', 'users_write')"
        )
        outside = _dataset(DATA_AMAZON)
        inside = _dataset(PUBLIC)
        execute(
            "INSERT INTO users_tenancies (user_id, tenancy) "
            f"VALUES ('{plain}', '{DATA_AMAZON}')"
        )
        retired = _queued_email("new_account_pending")
        interrupted = _queued_email("new_account_pending", status="sending")
        current = _queued_email("tenancy_access_granted")
        execute(f"DELETE FROM casbin_rule WHERE {DATASETS_WRITE_DELETE_RULES}")

        down = _alembic("downgrade", PREVIOUS_REVISION)
        up = _alembic("upgrade", "head")

        assert f"{THIS_REVISION} -> {PREVIOUS_REVISION}" in down
        assert f"{PREVIOUS_REVISION} -> {THIS_REVISION}" in up
        assert execute("SELECT version_num FROM alembic_version") == THIS_REVISION
        assert execute(
            "SELECT v1, v3 FROM casbin_rule "
            f"WHERE {DATASETS_WRITE_DELETE_RULES} ORDER BY v1"
        ).splitlines() == [
            f"{path}|allow" for path in sorted(DATASETS_WRITE_DELETE_PATHS)
        ]
        assert (
            execute(
                "SELECT count(*) FROM casbin_rule WHERE v1 LIKE '%tenancy-invitations%'"
            )
            == "0"
        )
        assert (
            execute(
                f"SELECT display_name, is_enabled FROM tenancies WHERE name = '{PUBLIC}'"
            )
            == "Public|t"
        )
        for user_id in (plain, reader, boss, clerk):
            assert (
                execute(
                    "SELECT count(*) FROM users_tenancies "
                    f"WHERE user_id = '{user_id}' AND tenancy = '{PUBLIC}'"
                )
                == "1"
            )
            assert (
                execute(
                    f"SELECT count(*) FROM tenancy_events WHERE user_id = '{user_id}' "
                    f"AND tenancy = '{PUBLIC}' AND event_type = 'member_added' "
                    "AND actor_id IS NULL"
                )
                == "1"
            )
        assert (
            execute(
                f"SELECT count(*) FROM tenancy_events WHERE user_id = '{plain}' "
                f"AND tenancy = '{DATA_AMAZON}' AND event_type = 'member_added' "
                "AND actor_id IS NULL"
            )
            == "1"
        )
        assert _email_status(retired) == "skipped|skipped|template retired"
        assert _email_status(interrupted) == "skipped|skipped|template retired"
        assert _email_status(current) == "pending||"
        assert "lower((display_name)::text)" in execute(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'uq_tenancies_display_name'"
        )
        assert _roles(plain) == ["datasets_write"]
        assert _roles(reader) == ["datasets_read"]
        assert _roles(boss) == ["admin"]
        assert _roles(clerk) == ["datasets_write", "users_write"]
        assert (
            execute(f"SELECT members_can_edit FROM datasets WHERE id = '{outside}'")
            == "t"
        )
        assert (
            execute(f"SELECT members_can_edit FROM datasets WHERE id = '{inside}'")
            == "f"
        )
        assert (
            execute(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name = 'datasets' AND column_name = 'members_can_edit'"
            )
            == "false"
        )

    def test_a_second_round_trip_adds_no_memberships_or_rules(self):
        before = execute(COUNTS)

        _alembic("downgrade", PREVIOUS_REVISION)
        assert execute("SELECT version_num FROM alembic_version") == PREVIOUS_REVISION
        _alembic("upgrade", "head")

        assert execute("SELECT version_num FROM alembic_version") == THIS_REVISION
        assert execute(COUNTS) == before
