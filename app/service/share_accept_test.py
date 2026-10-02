from types import SimpleNamespace
from uuid import uuid4

from app.exception.conflict import ConflictException
from app.exception.not_found import NotFoundException
from app.model.dataset_access import PermissionLevel
from app.model.user import User, UserProvider
from app.service.share_token import hash_token
from app.service.share_test import NOW, OWNER, ShareServiceTestCase


def pending(dataset_id, level="read", email=None, orcid=None):
    return SimpleNamespace(
        id=uuid4(),
        dataset_id=dataset_id,
        level=level,
        email=email,
        orcid=orcid,
        accepted_at=None,
        revoked_at=None,
    )


class TestAccept(ShareServiceTestCase):
    def setUp(self):
        super().setUp()
        self.invitee = uuid4()
        self.user_service.fetch_by_id.return_value = User(
            id=self.invitee, name="Dora", email="dora@ufam.edu.br", providers=[]
        )
        self.invitation = pending(self.dataset.id, level="write")
        self.invitations.fetch_by_token_hash.return_value = self.invitation
        self.invitations.mark_accepted.return_value = True

    def test_any_account_that_opens_the_link_gets_the_permission(self):
        result = self.service.accept("the-token", self.invitee)

        self.invitations.fetch_by_token_hash.assert_called_once_with(
            hash_token("the-token")
        )
        self.invitations.mark_accepted.assert_called_once_with(
            self.invitation.id, self.invitee, NOW
        )
        self.permission_service.grant.assert_called_once_with(
            self.dataset.id, self.invitee, PermissionLevel.WRITE, None
        )
        self.assertEqual(result.dataset_id, self.dataset.id)
        self.assertEqual(result.level, "write")

    def test_an_unknown_token_is_not_found(self):
        self.invitations.fetch_by_token_hash.return_value = None
        with self.assertRaises(NotFoundException):
            self.service.accept("nope", self.invitee)

    def test_a_revoked_invitation_is_not_found(self):
        self.invitation.revoked_at = NOW
        with self.assertRaises(NotFoundException):
            self.service.accept("the-token", self.invitee)

    def test_a_used_invitation_is_a_conflict(self):
        self.invitation.accepted_at = NOW
        with self.assertRaises(ConflictException) as caught:
            self.service.accept("the-token", self.invitee)
        self.assertEqual(str(caught.exception), "invitation_already_accepted")

    def test_losing_the_race_to_accept_is_a_conflict(self):
        self.invitations.mark_accepted.return_value = False
        with self.assertRaises(ConflictException):
            self.service.accept("the-token", self.invitee)
        self.permission_service.grant.assert_not_called()

    def test_an_existing_higher_permission_is_not_lowered(self):
        self.invitation.level = "read"
        self.permissions.fetch.return_value = SimpleNamespace(level="write")

        result = self.service.accept("the-token", self.invitee)

        self.permission_service.grant.assert_not_called()
        self.assertEqual(result.level, "write")

    def test_the_owner_accepting_gets_nothing_new(self):
        self.user_service.fetch_by_id.return_value = User(
            id=OWNER, name="Owner", providers=[]
        )
        result = self.service.accept("the-token", OWNER)
        self.permission_service.grant.assert_not_called()
        self.assertEqual(result.level, "owner")


class TestClaim(ShareServiceTestCase):
    def test_pending_invitations_matching_email_or_orcid_are_accepted(self):
        user_id = uuid4()
        self.user_service.fetch_by_id.return_value = User(
            id=user_id,
            name="Eva",
            email="Eva@USP.br",
            providers=[UserProvider(name="orcid", reference="0000-0002-1825-0097")],
        )
        first, second = (
            pending(self.dataset.id),
            pending(self.dataset.id, level="write"),
        )
        self.invitations.list_pending_for.return_value = [first, second]
        self.invitations.mark_accepted.return_value = True

        accepted = self.service.claim(user_id)

        self.invitations.list_pending_for.assert_called_once_with(
            "eva@usp.br", "0000-0002-1825-0097"
        )
        self.assertEqual(len(accepted), 2)

    def test_a_placeholder_email_is_not_matched(self):
        user_id = uuid4()
        self.user_service.fetch_by_id.return_value = User(
            id=user_id, name="Eva", email="eva@fake.mail.com", providers=[]
        )
        self.invitations.list_pending_for.return_value = []

        self.assertEqual(self.service.claim(user_id), [])
        self.invitations.list_pending_for.assert_called_once_with(None, None)
