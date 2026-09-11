import unittest
from unittest.mock import Mock, patch

from app.database import Database


class TestRunMigrations(unittest.TestCase):
    def setUp(self):
        db_url = Mock()
        db_url.unicode_string.return_value = "postgresql+psycopg2://u:p@localhost/db"

        with patch("app.database.create_engine"):
            self.database = Database(db_url=db_url, log_enabled=False)

    def test_alembic_does_not_touch_the_logging_configuration(self):
        with patch("app.database.command.upgrade") as upgrade:
            self.database.run_migrations()

        config = upgrade.call_args.args[0]
        self.assertIs(config.attributes.get("configure_logger"), False)
