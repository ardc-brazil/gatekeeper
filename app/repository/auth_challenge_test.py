import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.model.db.auth_challenge import AuthChallenge
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


class TestPasswordHashIsNotRetained(unittest.TestCase):
    def test_a_confirmed_challenge_drops_the_password_hash(self):
        recorder = Recorder()
        recorder.session.execute.return_value.rowcount = 1

        confirmed = AuthChallengeRepository(recorder).confirm(uuid4(), NOW)

        self.assertTrue(confirmed)
        sql = recorder.sql()
        self.assertIn("confirmed_at=", sql)
        self.assertIn("payload=((auth_challenges.payload - CAST(", sql)
        self.assertIn("auth_challenges.consumed_at IS NULL", sql)
        recorder.session.commit.assert_called_once()

    def test_a_challenge_confirmed_meanwhile_is_not_confirmed_again(self):
        recorder = Recorder()
        recorder.session.execute.return_value.rowcount = 0

        self.assertFalse(AuthChallengeRepository(recorder).confirm(uuid4(), NOW))

    def test_a_replaced_challenge_drops_the_password_hash(self):
        recorder = Recorder()
        challenge = AuthChallenge(
            id=uuid4(), kind="sign_up", email="ana.souza@usp.br", issued_at=NOW
        )

        AuthChallengeRepository(recorder).replace(challenge)

        sql = recorder.sql()
        self.assertIn("consumed_at=", sql)
        self.assertIn("payload=((auth_challenges.payload - CAST(", sql)
        self.assertIn("auth_challenges.consumed_at IS NULL", sql)
        recorder.session.add.assert_called_once_with(challenge)
        recorder.session.commit.assert_called_once()

    def test_a_challenge_replaced_by_a_resend_drops_the_password_hash(self):
        recorder = Recorder()

        AuthChallengeRepository(recorder).reissue(uuid4(), "secret", NOW, NOW)

        sql = recorder.sql()
        self.assertIn("payload=((auth_challenges.payload - CAST(", sql)
        self.assertIn("auth_challenges.id !=", sql)

    def test_the_existing_account_marker_goes_with_the_password_hash(self):
        for call in (
            lambda repository: repository.confirm(uuid4(), NOW),
            lambda repository: repository.replace(
                AuthChallenge(
                    id=uuid4(), kind="sign_up", email="a@usp.br", issued_at=NOW
                )
            ),
            lambda repository: repository.reissue(uuid4(), "secret", NOW, NOW),
        ):
            recorder = Recorder()
            recorder.session.execute.return_value.rowcount = 1

            call(AuthChallengeRepository(recorder))

            statement = recorder.session.execute.call_args.args[0]
            params = statement.compile(dialect=postgresql.dialect()).params
            self.assertIn("password_hash", params.values())
            self.assertIn("existing_account", params.values())

    def test_several_challenges_are_replaced_in_one_transaction(self):
        recorder = Recorder()
        first = AuthChallenge(
            id=uuid4(), kind="password_reset", email="a@usp.br", issued_at=NOW
        )
        second = AuthChallenge(
            id=uuid4(), kind="sign_up", email="a@usp.br", issued_at=NOW
        )

        AuthChallengeRepository(recorder).replace(first, second)

        self.assertEqual(recorder.session.execute.call_count, 2)
        self.assertEqual(
            [call.args[0] for call in recorder.session.add.call_args_list],
            [first, second],
        )
        recorder.session.commit.assert_called_once()
