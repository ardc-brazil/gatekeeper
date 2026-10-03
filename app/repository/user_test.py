import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query, Session

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


def compiled_lookup(call) -> str:
    @contextmanager
    def session_factory():
        yield Session()

    with patch.object(Query, "first", autospec=True) as first:
        call(UserRepository(session_factory))

    query = first.call_args.args[0]
    return str(query.statement.compile(dialect=postgresql.dialect()))


class TestFetchByProvider(unittest.TestCase):
    def test_only_accounts_in_the_asked_state_are_found(self):
        sql = compiled_lookup(
            lambda users: users.fetch_by_provider("orcid", "0000-0002-1825-0097")
        )

        where = sql.split("WHERE", 1)[1]
        self.assertIn("providers_1.name =", where)
        self.assertIn("providers_1.reference =", where)
        self.assertIn("users.is_enabled =", where)
        self.assertNotIn("ORDER BY", sql)


class TestFetchByProviderAny(unittest.TestCase):
    def test_the_lookup_ignores_whether_the_account_is_enabled(self):
        sql = compiled_lookup(
            lambda users: users.fetch_by_provider_any("orcid", "0000-0002-1825-0097")
        )

        where = sql.split("WHERE", 1)[1]
        self.assertIn("providers_1.name =", where)
        self.assertIn("providers_1.reference =", where)
        self.assertNotIn("is_enabled", where.split("ORDER BY", 1)[0])

    def test_a_disabled_holder_of_a_shared_reference_comes_first(self):
        sql = compiled_lookup(
            lambda users: users.fetch_by_provider_any("orcid", "0000-0002-1825-0097")
        )

        self.assertIn("ORDER BY users.is_enabled ASC", sql)
