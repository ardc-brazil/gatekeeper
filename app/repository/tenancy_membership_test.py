import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query, Session

from app.exception.conflict import ConflictException
from app.model.tenancy import (
    DEFAULT_TENANCY,
    TenancyEventType,
    TenancyInvitationStatus,
)
from app.repository import tenancy_membership
from app.repository.tenancy_membership import TenancyMembershipRepository, join_tenancy

ATTO = "datamap/production/atto"


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


class TestJoinTenancy(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.pending = SimpleNamespace(
            id=uuid4(),
            status=TenancyInvitationStatus.PENDING,
            closed_by=None,
            closed_at=None,
        )
        query = self.session.query.return_value.filter.return_value
        query.with_for_update.return_value.all.return_value = [self.pending]
        self.user_id, self.actor_id, self.request_id = uuid4(), uuid4(), uuid4()

    def join(self, inserted: bool = True):
        with patch.object(
            tenancy_membership, "insert_membership", return_value=inserted
        ), patch.object(tenancy_membership, "add_event") as add_event:
            add_event.side_effect = lambda session, **kwargs: SimpleNamespace(
                id=uuid4(), **kwargs
            )
            event_id = join_tenancy(
                self.session, ATTO, self.user_id, self.actor_id, self.request_id
            )
        return event_id, add_event

    def test_joining_records_the_member_and_withdraws_pending_invitations(self):
        event_id, add_event = self.join()

        self.assertIsNotNone(event_id)
        added, withdrawn = (c.kwargs for c in add_event.call_args_list)
        self.assertEqual(
            (added["event_type"], added["user_id"], added["request_id"]),
            (TenancyEventType.MEMBER_ADDED, self.user_id, self.request_id),
        )
        self.assertEqual(
            (
                withdrawn["event_type"],
                withdrawn["actor_id"],
                withdrawn["invitation_id"],
            ),
            (TenancyEventType.INVITATION_WITHDRAWN, self.actor_id, self.pending.id),
        )
        self.assertEqual(self.pending.status, TenancyInvitationStatus.WITHDRAWN)
        self.assertEqual(self.pending.closed_by, self.actor_id)
        self.assertIsNotNone(self.pending.closed_at)

    def test_someone_already_in_is_not_joined_and_nothing_is_withdrawn(self):
        event_id, add_event = self.join(inserted=False)

        self.assertIsNone(event_id)
        add_event.assert_not_called()
        self.assertEqual(self.pending.status, TenancyInvitationStatus.PENDING)
