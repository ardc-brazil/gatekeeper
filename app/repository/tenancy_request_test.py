import unittest
from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query, Session

import app.model.db.doi  # noqa: F401  # registers DOI before Dataset's mapper resolves its "DOI" relationship
from app.repository.tenancy_request import TenancyRequestRepository


class TestListPending(unittest.TestCase):
    def test_requests_made_at_the_same_moment_keep_a_stable_order(self):
        @contextmanager
        def session_factory():
            yield Session()

        with patch.object(Query, "all", autospec=True, return_value=[]) as all_rows:
            TenancyRequestRepository(session_factory).list_pending(None)

        query = all_rows.call_args.args[0]
        sql = str(query.statement.compile(dialect=postgresql.dialect()))
        self.assertIn(
            "ORDER BY tenancy_requests.created_at ASC, tenancy_requests.id ASC", sql
        )
