import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.model.dataset_access import AccessLevel, DatasetAction
from app.repository.access_event import AccessEventRepository
from app.repository.dataset_anonymous_link import DatasetAnonymousLinkRepository
from app.repository.dataset_invitation import DatasetInvitationRepository
from app.repository.user import UserRepository
from app.service.access_history import AccessHistoryService
from app.service.dataset import DatasetService

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def event(event_type, by=None, old=None, new=None, note=None):
    return SimpleNamespace(
        event_type=event_type,
        changed_by=by,
        old_value=old,
        new_value=new,
        note=note,
        occurred_at=NOW,
    )


class TestAccessHistory(unittest.TestCase):
    def setUp(self):
        self.datasets = Mock(spec=DatasetService)
        self.events = Mock(spec=AccessEventRepository)
        self.users = Mock(spec=UserRepository)
        self.invitations = Mock(spec=DatasetInvitationRepository)
        self.links = Mock(spec=DatasetAnonymousLinkRepository)
        self.dataset = SimpleNamespace(id=uuid4())
        self.datasets.fetch_authorized.return_value = (
            self.dataset,
            [],
            AccessLevel.OWNER,
        )
        self.owner, self.reader = uuid4(), uuid4()
        people = {
            self.owner: SimpleNamespace(
                id=self.owner, name="Luciana Rizzo", email="l@usp.br"
            ),
            self.reader: SimpleNamespace(
                id=self.reader, name="Caio Maia", email="c@usp.br"
            ),
        }
        self.users.fetch_by_id.side_effect = lambda id, is_enabled=True: people.get(id)
        self.service = AccessHistoryService(
            dataset_service=self.datasets,
            event_repository=self.events,
            user_repository=self.users,
            invitation_repository=self.invitations,
            anonymous_link_repository=self.links,
        )

    def test_reading_the_history_needs_write_access(self):
        self.events.list_for_dataset.return_value = []

        self.service.list(self.dataset.id, self.owner, [])

        self.assertEqual(
            self.datasets.fetch_authorized.call_args.kwargs["action"],
            DatasetAction.WRITE,
        )

    def test_entries_name_who_acted_and_on_whom(self):
        link_id, invitation_id = uuid4(), uuid4()
        self.links.fetch.return_value = SimpleNamespace(label="JGR, round 1")
        self.invitations.fetch.return_value = SimpleNamespace(
            email=None, orcid="0000-0002-1825-0097"
        )
        self.events.list_for_dataset.return_value = [
            event(
                "permission_granted",
                self.owner,
                new={"user_id": str(self.reader), "level": "read"},
            ),
            event("anonymous_link_revoked", self.owner, old={"link_id": str(link_id)}),
            event(
                "invitation_created",
                self.owner,
                new={"invitation_id": str(invitation_id), "level": "read"},
            ),
            event(
                "extended",
                self.owner,
                old={"until": "a"},
                new={"until": "b"},
                note="Second round",
            ),
            event("expired"),
        ]

        entries = self.service.list(self.dataset.id, self.owner, [])

        self.assertEqual(
            [entry.actor.name if entry.actor else None for entry in entries],
            ["Luciana Rizzo"] * 4 + [None],
        )
        self.assertEqual(
            [entry.subject for entry in entries],
            ["Caio Maia", "JGR, round 1", "ORCID 0000-0002-1825-0097", None, None],
        )
        self.assertEqual(entries[3].note, "Second round")
        self.assertEqual(entries[3].new_value, {"until": "b"})

    def test_at_most_a_hundred_entries_are_returned(self):
        self.events.list_for_dataset.return_value = [
            event("expired") for _ in range(150)
        ]

        self.assertEqual(len(self.service.list(self.dataset.id, self.owner, [])), 100)
