import subprocess
import uuid

import pytest

from tests.integration.utils.database import execute

GATEKEEPER_CONTAINER = "datamap_gatekeeper_test_integration"
PUBLIC = "datamap/production/public"
DATA_AMAZON = "datamap/production/data-amazon"
COUNTS = (
    "SELECT (SELECT count(*) FROM users_tenancies), (SELECT count(*) FROM casbin_rule), "
    "(SELECT count(*) FROM tenancy_events)"
)


@pytest.fixture(scope="module", autouse=True)
def keep_display_names():
    execute("DROP TABLE IF EXISTS migration_test_display_names")
    execute(
        "CREATE TABLE migration_test_display_names AS "
        "SELECT name, display_name FROM tenancies WHERE display_name IS NOT NULL"
    )
    yield
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


def _roles(user_id: str) -> list[str]:
    return execute(
        f"SELECT v1 FROM casbin_rule WHERE ptype = 'g' AND v0 = '{user_id}' ORDER BY v1"
    ).split()


class TestTheMigration:
    def test_it_backfills_public_roles_and_defaults_and_survives_a_round_trip(self):
        plain = _user("Plain Account")
        reader = _user("Read Only")
        boss = _user("Admin Only")
        execute(
            "INSERT INTO casbin_rule (ptype, v0, v1) VALUES "
            f"('g', '{reader}', 'datasets_read'), ('g', '{boss}', 'admin')"
        )
        outside = _dataset(DATA_AMAZON)
        inside = _dataset(PUBLIC)

        down = _alembic("downgrade", "-1")
        up = _alembic("upgrade", "head")

        assert "c3d4e5f6a7b8 -> b1c2d3e4f5a6" in down
        assert "b1c2d3e4f5a6 -> c3d4e5f6a7b8" in up
        assert execute("SELECT version_num FROM alembic_version") == "c3d4e5f6a7b8"
        assert (
            execute(
                f"SELECT display_name, is_enabled FROM tenancies WHERE name = '{PUBLIC}'"
            )
            == "Public|t"
        )
        for user_id in (plain, reader, boss):
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
        assert _roles(plain) == ["datasets_write"]
        assert _roles(reader) == ["datasets_read"]
        assert _roles(boss) == ["admin"]
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

    def test_running_the_upgrade_twice_changes_nothing(self):
        before = execute(COUNTS)

        _alembic("downgrade", "-1")
        _alembic("upgrade", "head")
        after = execute(COUNTS)

        users, rules, _ = before.split("|")
        assert after.split("|")[:2] == [users, rules]
