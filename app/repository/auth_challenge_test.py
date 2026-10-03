import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.repository.auth_challenge import AuthChallengeRepository

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


class Recorder:
    def __init__(self, returned=None) -> None:
        self.session = MagicMock()
        self.session.execute.return_value.first.return_value = returned

    @contextmanager
    def __call__(self):
        yield self.session

    def sql(self) -> str:
        statement = self.session.execute.call_args.args[0]
        return str(statement.compile(dialect=postgresql.dialect()))


class TestFailedAttempts(unittest.TestCase):
    def test_a_wrong_code_is_counted_and_the_last_one_consumes_in_one_statement(self):
        recorder = Recorder(returned=(5,))

        attempts = AuthChallengeRepository(recorder).record_failed_attempt(
            uuid4(), 5, NOW
        )

        self.assertEqual(attempts, 5)
        sql = recorder.sql()
        self.assertIn("UPDATE auth_challenges SET", sql)
        self.assertIn("auth_challenges.attempts +", sql)
        self.assertIn("CASE WHEN", sql)
        self.assertIn("auth_challenges.consumed_at IS NULL", sql)
        self.assertIn("RETURNING auth_challenges.attempts", sql)
        recorder.session.commit.assert_called_once()

    def test_a_challenge_consumed_meanwhile_counts_nothing(self):
        recorder = Recorder(returned=None)

        attempts = AuthChallengeRepository(recorder).record_failed_attempt(
            uuid4(), 5, NOW
        )

        self.assertIsNone(attempts)
