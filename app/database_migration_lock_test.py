import unittest
from unittest.mock import MagicMock, call, patch

from app.database import MIGRATION_LOCK_KEY, Database


class MigrationLockTestCase(unittest.TestCase):
    def setUp(self):
        with patch("app.database.create_engine"), patch("app.database.orm"):
            self.database = Database(db_url=MagicMock(), log_enabled=False)
        self.connection = MagicMock()
        self.database._engine = MagicMock()
        self.database._engine.connect.return_value.__enter__.return_value = (
            self.connection
        )

    def executed(self) -> list[str]:
        return [str(args[0][0]) for args in self.connection.execute.call_args_list]


class TestMigrationsAreSerialised(MigrationLockTestCase):
    """Two instances start at once and both run `alembic upgrade head`."""

    @patch("app.database.command")
    def test_the_lock_is_taken_before_the_upgrade(self, command):
        order = []
        self.connection.execute.side_effect = lambda *a, **k: order.append("lock")
        command.upgrade.side_effect = lambda *a, **k: order.append("upgrade")

        self.database.run_migrations()

        self.assertEqual(order[0], "lock")
        self.assertIn("upgrade", order)

    @patch("app.database.command")
    def test_the_lock_is_released_afterwards(self, command):
        self.database.run_migrations()

        statements = self.executed()
        self.assertTrue(any("pg_advisory_lock" in s for s in statements), statements)
        self.assertTrue(any("pg_advisory_unlock" in s for s in statements), statements)

    @patch("app.database.command")
    def test_both_use_the_same_key(self, command):
        self.database.run_migrations()

        for statement in self.executed():
            self.assertIn(str(MIGRATION_LOCK_KEY), statement)

    @patch("app.database.command")
    def test_a_failed_migration_still_releases_the_lock(self, command):
        command.upgrade.side_effect = RuntimeError("bad revision")

        with self.assertRaises(RuntimeError):
            self.database.run_migrations()

        self.assertTrue(
            any("pg_advisory_unlock" in s for s in self.executed()),
            "the next instance would wait forever",
        )

    @patch("app.database.command")
    def test_the_upgrade_still_runs(self, command):
        self.database.run_migrations()

        command.upgrade.assert_called_once()
        self.assertEqual(
            command.upgrade.call_args, call(command.upgrade.call_args[0][0], "head")
        )
