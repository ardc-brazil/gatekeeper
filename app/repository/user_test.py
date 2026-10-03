import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.repository.user import UserRepository

LOCK_UNTIL = datetime(2026, 10, 3, 12, 15, tzinfo=timezone.utc)


class Recorder:
    def __init__(self) -> None:
        self.session = MagicMock()

    @contextmanager
    def __call__(self):
        yield self.session

    def sql(self) -> str:
        statement = self.session.execute.call_args.args[0]
        return str(statement.compile(dialect=postgresql.dialect()))


class TestFailedLogins(unittest.TestCase):
    def test_a_failure_is_counted_and_the_tenth_locks_in_one_statement(self):
        recorder = Recorder()

        UserRepository(recorder).record_failed_login(
            uuid4(), threshold=10, lock_until=LOCK_UNTIL
        )

        sql = recorder.sql()
        self.assertIn("UPDATE users SET", sql)
        self.assertIn("users.failed_login_count +", sql)
        self.assertIn("CASE WHEN", sql)
        self.assertIn("ELSE users.locked_until", sql)
        self.assertIn("WHERE users.id =", sql)
        recorder.session.commit.assert_called_once()
