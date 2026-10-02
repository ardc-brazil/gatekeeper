from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.exception.not_found import NotFoundException
from app.service.share_test import NOW, OWNER, ShareServiceTestCase, user_row


class TestPreview(ShareServiceTestCase):
    def setUp(self):
        super().setUp()
        self.inviter = uuid4()
        self.invitation = SimpleNamespace(
            id=uuid4(),
            dataset_id=self.dataset.id,
            email="fernanda@inpe.br",
            orcid=None,
            level="read",
            invited_by=self.inviter,
            accepted_at=None,
            accepted_by=None,
            revoked_at=None,
        )
        self.invitations.fetch_by_token_hash.return_value = self.invitation
        people = {
            self.inviter: user_row(self.inviter, name="Alan Calheiros"),
            OWNER: user_row(OWNER, name="Luciana Rizzo"),
        }
        self.users.fetch_by_id.side_effect = lambda id, is_enabled=True: people.get(id)

    def test_a_pending_invitation_shows_what_accepting_gives(self):
        preview = self.service.preview("tok")

        self.assertEqual(preview.state, "pending")
        self.assertEqual(preview.dataset_name, "Ozone at ATTO")
        self.assertEqual(preview.inviter_name, "Alan Calheiros")
        self.assertEqual(preview.owner_name, "Luciana Rizzo")
        self.assertEqual(preview.level, "read")
        self.assertEqual(preview.invited_as, "fernanda@inpe.br")
        self.assertEqual(preview.embargo_until, self.dataset.embargo_until)
        self.assertIsNone(preview.accepted_at)
        self.assertIsNone(preview.dataset_id)

    def test_an_orcid_invitation_is_shown_as_orcid(self):
        self.invitation.email = None
        self.invitation.orcid = "0000-0002-1825-0097"

        self.assertEqual(
            self.service.preview("tok").invited_as, "ORCID 0000-0002-1825-0097"
        )

    def test_an_accepted_invitation_says_when(self):
        self.invitation.accepted_at = NOW - timedelta(days=2)

        preview = self.service.preview("tok")

        self.assertEqual(preview.state, "accepted")
        self.assertEqual(preview.accepted_at, NOW - timedelta(days=2))
        self.assertEqual(preview.dataset_id, self.dataset.id)

    def test_a_revoked_or_unknown_token_is_not_found(self):
        self.invitation.revoked_at = NOW
        with self.assertRaises(NotFoundException):
            self.service.preview("tok")

        self.invitations.fetch_by_token_hash.return_value = None
        with self.assertRaises(NotFoundException):
            self.service.preview("tok")


class TestStateExtras(ShareServiceTestCase):
    def test_a_permission_that_came_from_an_invitation_names_its_address(self):
        holder = uuid4()
        self.permissions.list_for_dataset.return_value = [
            SimpleNamespace(
                user_id=holder, level="read", created_at=NOW, granted_by=OWNER
            )
        ]
        self.invitations.list_for_dataset.return_value = [
            SimpleNamespace(
                id=uuid4(),
                email="fernanda@inpe.br",
                orcid=None,
                level="read",
                created_at=NOW,
                accepted_at=NOW,
                accepted_by=holder,
                revoked_at=None,
            )
        ]
        self.anonymous_links.list_with_views.return_value = []
        self.users.fetch_by_id.side_effect = lambda id, is_enabled=True: user_row(id)

        state = self.service.state(self.dataset.id, OWNER)

        self.assertEqual(state.permissions[0].invited_as, "fernanda@inpe.br")

    def test_the_tenancy_row_appears_only_without_an_active_embargo(self):
        self.invitations.list_for_dataset.return_value = []
        self.anonymous_links.list_with_views.return_value = []
        self.users.count_in_tenancy.return_value = 14

        self.assertIsNone(self.service.state(self.dataset.id, OWNER).tenancy)

        self.dataset.embargo_until = None
        tenancy = self.service.state(self.dataset.id, OWNER).tenancy

        self.assertEqual(tenancy.name, "Data Amazon")
        self.assertEqual(tenancy.path, "datamap/production/data-amazon")
        self.assertEqual(tenancy.members, 14)

    def test_the_tenancy_row_says_what_members_can_do(self):
        self.invitations.list_for_dataset.return_value = []
        self.anonymous_links.list_with_views.return_value = []
        self.users.count_in_tenancy.return_value = 14
        self.dataset.embargo_until = None

        self.assertTrue(
            self.service.state(self.dataset.id, OWNER).tenancy.members_can_edit
        )

        self.dataset.members_can_edit = False

        self.assertFalse(
            self.service.state(self.dataset.id, OWNER).tenancy.members_can_edit
        )
