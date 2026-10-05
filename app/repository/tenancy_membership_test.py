import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query, Session

import app.model.db.doi  # noqa: F401  # registers DOI before Dataset's mapper resolves its "DOI" relationship
from app.exception.conflict import ConflictException
from app.model.tenancy import DEFAULT_TENANCY
from app.repository.tenancy_membership import TenancyMembershipRepository


class TestRemove(unittest.TestCase):
    def test_nobody_is_ever_removed_from_the_public_tenancy(self):
        session_factory = MagicMock()

        with self.assertRaises(ConflictException) as raised:
            TenancyMembershipRepository(session_factory).remove(
                DEFAULT_TENANCY, uuid4(), uuid4()
            )

        self.assertEqual(str(raised.exception), "public_tenancy_locked")
        session_factory.assert_not_called()


class TestInviters(unittest.TestCase):
    def test_a_dated_acceptance_is_read_after_an_undated_one(self):
        @contextmanager
        def session_factory():
            yield Session()

        with patch.object(Query, "all", autospec=True, return_value=[]) as all_rows:
            TenancyMembershipRepository(session_factory).inviters(
                "datamap/production/atto", [uuid4()]
            )

        query = all_rows.call_args.args[0]
        sql = str(query.statement.compile(dialect=postgresql.dialect()))
        self.assertIn("ORDER BY tenancy_invitations.closed_at ASC NULLS FIRST", sql)
