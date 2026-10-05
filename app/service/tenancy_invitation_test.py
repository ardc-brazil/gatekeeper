import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.exception.conflict import ConflictException
from app.exception.forbidden import ForbiddenException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.model.dataset_access import AccessLevel, DatasetAction
from app.model.tenancy import (
    DEFAULT_TENANCY,
    TenancyEventType,
    TenancyInvitationStatus,
    summary_of,
)
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_invitation import TenancyInvitationRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.user import UserRepository
from app.service.dataset import DatasetService
from app.service.tenancy_invitation import TenancyInvitationService
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_notifier import TenancyNotifier

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
ATTO = "datamap/production/atto"
CALLER = uuid4()


def person(name="Bruna Costa", email="bruna@usp.br"):
    return SimpleNamespace(id=uuid4(), name=name, email=email)


def invitation_row(**overrides):
    values = dict(
        id=uuid4(),
        tenancy=ATTO,
        user_id=uuid4(),
        invited_by=CALLER,
        dataset_id=uuid4(),
        status=TenancyInvitationStatus.PENDING,
        created_at=NOW,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class InvitationServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.datasets = Mock(spec=DatasetService)
        self.invitations = Mock(spec=TenancyInvitationRepository)
        self.memberships = Mock(spec=TenancyMembershipRepository)
        self.membership_service = Mock(spec=TenancyMembershipService)
        self.membership_service.summary.side_effect = lambda path: summary_of(
            path, "ATTO"
        )
        self.tenancies = Mock(spec=TenancyRepository)
        self.tenancies.fetch_any.side_effect = lambda path: SimpleNamespace(
            name=path, display_name=None, is_enabled=True
        )
        self.tenancies.count_datasets.return_value = 12
        self.users = Mock(spec=UserRepository)
        self.notifier = Mock(spec=TenancyNotifier)
        self.caller = SimpleNamespace(
            id=CALLER, name="Alan Calheiros", email="alan@usp.br"
        )
        self.invitee = person()
        self.people = {CALLER: self.caller, self.invitee.id: self.invitee}
        self.users.fetch_any_by_id.side_effect = self.people.get
        self.users.fetch_by_id.side_effect = (
            lambda id, is_enabled=True: self.people.get(id)
        )
        self.dataset = SimpleNamespace(
            id=uuid4(), name="Ozone at ATTO", tenancy=ATTO, embargo_until=None
        )
        self.level = AccessLevel.OWNER
        self.datasets.fetch_authorized.side_effect = lambda **kwargs: (
            self.dataset,
            [ATTO],
            self.level,
        )
        self.members = {(CALLER, ATTO)}
        self.memberships.is_member.side_effect = lambda user_id, tenancy: (
            (user_id, tenancy) in self.members
        )
        self.invitations.has_pending.return_value = False
        self.invitations.create.side_effect = (
            lambda tenancy, user_id, invited_by, dataset_id: invitation_row(
                tenancy=tenancy,
                user_id=user_id,
                invited_by=invited_by,
                dataset_id=dataset_id,
            )
        )
        self.service = TenancyInvitationService(
            dataset_service=self.datasets,
            invitations=self.invitations,
            memberships=self.memberships,
            membership_service=self.membership_service,
            tenancies=self.tenancies,
            users=self.users,
            notifier=self.notifier,
            clock=lambda: NOW,
        )

    def embargo(self, days: int = 30) -> None:
        self.dataset.embargo_until = NOW + timedelta(days=days)


class TestWhoMayInvite(InvitationServiceTestCase):
    def invite(self):
        return self.service.invite(self.dataset.id, CALLER, self.invitee.id)

    def test_the_owner_who_is_a_member_invites(self):
        view = self.invite()

        self.invitations.create.assert_called_once_with(
            ATTO, self.invitee.id, CALLER, self.dataset.id
        )
        self.assertEqual(view.user.name, "Bruna Costa")
        self.assertEqual(view.invited_by.name, "Alan Calheiros")
        self.assertTrue(view.can_withdraw)
        self.assertEqual(
            self.datasets.fetch_authorized.call_args.kwargs["action"],
            DatasetAction.WRITE,
        )

    def test_a_write_collaborator_who_is_a_member_invites(self):
        self.level = AccessLevel.WRITE

        self.invite()

        self.invitations.create.assert_called_once()

    def test_a_member_who_edits_only_because_members_can_edit_may_not(self):
        self.level = AccessLevel.TENANCY

        with self.assertRaises(ForbiddenException):
            self.invite()

    def test_a_write_collaborator_outside_the_tenancy_may_not(self):
        self.level = AccessLevel.WRITE
        self.members = set()

        with self.assertRaises(ForbiddenException):
            self.invite()
        self.invitations.create.assert_not_called()

    def test_nobody_invites_while_the_dataset_is_embargoed(self):
        self.embargo()

        with self.assertRaises(ForbiddenException) as raised:
            self.invite()

        self.assertEqual(raised.exception.detail, "forbidden")
        self.invitations.create.assert_not_called()

    def test_an_embargo_that_has_ended_does_not_stop_an_invitation(self):
        self.embargo(days=-1)

        self.invite()

        self.invitations.create.assert_called_once()

    def test_a_reader_may_not(self):
        self.datasets.fetch_authorized.side_effect = ForbiddenException("forbidden")

        with self.assertRaises(ForbiddenException):
            self.invite()


class TestInviteRules(InvitationServiceTestCase):
    def code(self) -> str:
        with self.assertRaises((ConflictException, NotFoundException)) as raised:
            self.service.invite(self.dataset.id, CALLER, self.invitee.id)
        return str(raised.exception)

    def test_the_tenancy_must_be_open_for_members(self):
        self.membership_service.require_open_for_members.side_effect = (
            ConflictException("legacy_tenancy_read_only")
        )

        self.assertEqual(self.code(), "legacy_tenancy_read_only")
        self.membership_service.require_open_for_members.assert_called_once_with(ATTO)

    def test_an_unknown_or_disabled_invitee_has_no_account(self):
        self.people.pop(self.invitee.id)

        self.assertEqual(self.code(), "no_account")

    def test_a_member_is_already_in(self):
        self.members.add((self.invitee.id, ATTO))

        self.assertEqual(self.code(), "already_member")

    def test_one_pending_invitation_per_person_and_tenancy(self):
        self.invitations.has_pending.return_value = True

        self.assertEqual(self.code(), "invitation_pending")

    def test_the_invitee_and_the_admins_are_told(self):
        view = self.service.invite(self.dataset.id, CALLER, self.invitee.id)

        self.notifier.invitation.assert_called_once_with(
            self.invitee,
            "Alan Calheiros",
            summary_of(ATTO, "ATTO"),
            "Ozone at ATTO",
            view.id,
        )
        self.notifier.invitation_notice.assert_called_once_with(
            self.invitee,
            "Alan Calheiros",
            summary_of(ATTO, "ATTO"),
            "Ozone at ATTO",
            view.id,
        )


class TestLookup(InvitationServiceTestCase):
    def test_an_exact_email_outside_the_tenancy_can_be_invited(self):
        self.users.fetch_by_email_insensitive.return_value = self.invitee

        found = self.service.lookup(self.dataset.id, CALLER, "  Bruna@USP.br ")

        self.users.fetch_by_email_insensitive.assert_called_once_with("bruna@usp.br")
        self.assertEqual(found.user.email, "bruna@usp.br")
        self.assertFalse(found.tenancy_member)
        self.assertFalse(found.invitation_pending)
        self.assertTrue(found.can_invite)

    def test_an_orcid_is_looked_up_as_a_provider(self):
        self.users.fetch_by_provider.return_value = self.invitee

        self.service.lookup(
            self.dataset.id, CALLER, "https://orcid.org/0000-0002-1825-0097"
        )

        self.users.fetch_by_provider.assert_called_once_with(
            provider_name="orcid", reference="0000-0002-1825-0097"
        )

    def test_a_member_or_a_pending_invitee_cannot_be_invited_again(self):
        self.users.fetch_by_email_insensitive.return_value = self.invitee
        self.invitations.has_pending.return_value = True

        found = self.service.lookup(self.dataset.id, CALLER, "bruna@usp.br")

        self.assertTrue(found.invitation_pending)
        self.assertFalse(found.can_invite)

    def test_nobody_can_be_invited_while_the_dataset_is_embargoed(self):
        self.embargo()
        self.users.fetch_by_email_insensitive.return_value = self.invitee

        self.assertFalse(
            self.service.lookup(self.dataset.id, CALLER, "bruna@usp.br").can_invite
        )

    def test_in_public_nobody_can_be_invited(self):
        self.dataset.tenancy = DEFAULT_TENANCY
        self.members.add((CALLER, DEFAULT_TENANCY))
        self.users.fetch_by_email_insensitive.return_value = self.invitee

        self.assertFalse(
            self.service.lookup(self.dataset.id, CALLER, "bruna@usp.br").can_invite
        )

    def test_a_malformed_value_is_invalid_request(self):
        for value in ("not an address", "0000-0002-1825-0098", ""):
            with self.subTest(value=value):
                with self.assertRaises(IllegalStateException) as raised:
                    self.service.lookup(self.dataset.id, CALLER, value)
                self.assertEqual(str(raised.exception), "invalid_request")

    def test_nobody_found_is_no_account(self):
        self.users.fetch_by_email_insensitive.return_value = None

        with self.assertRaises(NotFoundException) as raised:
            self.service.lookup(self.dataset.id, CALLER, "ghost@usp.br")

        self.assertEqual(str(raised.exception), "no_account")


class TestWithdraw(InvitationServiceTestCase):
    def test_the_inviter_withdraws_through_the_dataset(self):
        invitation = invitation_row(dataset_id=self.dataset.id)
        self.invitations.fetch.return_value = invitation
        self.invitations.close.return_value = True

        self.service.withdraw(self.dataset.id, CALLER, invitation.id)

        self.invitations.close.assert_called_once_with(
            invitation.id,
            TenancyInvitationStatus.WITHDRAWN,
            CALLER,
            TenancyEventType.INVITATION_WITHDRAWN,
        )

    def test_another_editor_is_forbidden(self):
        self.invitations.fetch.return_value = invitation_row(
            dataset_id=self.dataset.id, invited_by=uuid4()
        )

        with self.assertRaises(ForbiddenException):
            self.service.withdraw(self.dataset.id, CALLER, uuid4())

    def test_an_invitation_of_another_dataset_or_not_pending_is_not_found(self):
        for row in (
            invitation_row(),
            invitation_row(
                dataset_id=self.dataset.id, status=TenancyInvitationStatus.ACCEPTED
            ),
            None,
        ):
            with self.subTest(row=row):
                self.invitations.fetch.return_value = row
                with self.assertRaises(NotFoundException) as raised:
                    self.service.withdraw(self.dataset.id, CALLER, uuid4())
                self.assertEqual(str(raised.exception), "invitation_not_found")

    def test_an_admin_withdraws_any_pending_one(self):
        self.invitations.close.return_value = True
        admin, invitation_id = uuid4(), uuid4()

        self.service.withdraw_as_admin(invitation_id, admin)

        self.invitations.close.assert_called_once_with(
            invitation_id,
            TenancyInvitationStatus.WITHDRAWN,
            admin,
            TenancyEventType.INVITATION_WITHDRAWN,
        )

    def test_an_admin_withdrawing_a_closed_one_is_not_found(self):
        self.invitations.close.return_value = False

        with self.assertRaises(NotFoundException):
            self.service.withdraw_as_admin(uuid4(), uuid4())


class TestInviteeSide(InvitationServiceTestCase):
    def test_pending_invitations_say_who_from_where_and_how_many_datasets(self):
        invitation = invitation_row(user_id=self.invitee.id)
        self.invitations.pending_for_user.return_value = [invitation]
        self.invitations.dataset_names.return_value = {
            invitation.dataset_id: "Ozone at ATTO"
        }

        (view,) = self.service.pending_for_user(self.invitee.id)

        self.assertEqual(view.tenancy, summary_of(ATTO, "ATTO"))
        self.assertEqual(view.invited_by.name, "Alan Calheiros")
        self.assertEqual(view.dataset.name, "Ozone at ATTO")
        self.assertEqual(view.datasets, 12)

    def test_a_dataset_that_is_gone_is_null(self):
        invitation = invitation_row(user_id=self.invitee.id, dataset_id=None)
        self.invitations.pending_for_user.return_value = [invitation]
        self.invitations.dataset_names.return_value = {}

        self.assertIsNone(self.service.pending_for_user(self.invitee.id)[0].dataset)

    def test_accepting_joins_the_tenancy(self):
        invitation = invitation_row(user_id=self.invitee.id)
        self.invitations.fetch.return_value = invitation
        self.invitations.accept.return_value = True

        summary = self.service.accept(self.invitee.id, invitation.id)

        self.invitations.accept.assert_called_once_with(invitation.id, self.invitee.id)
        self.assertEqual(summary, summary_of(ATTO, "ATTO"))

    def test_only_the_invitee_accepts_a_pending_one(self):
        for row in (
            invitation_row(),
            invitation_row(
                user_id=self.invitee.id, status=TenancyInvitationStatus.WITHDRAWN
            ),
            None,
        ):
            with self.subTest(row=row):
                self.invitations.fetch.return_value = row
                with self.assertRaises(NotFoundException) as raised:
                    self.service.accept(self.invitee.id, uuid4())
                self.assertEqual(str(raised.exception), "invitation_not_found")

    def test_a_disabled_tenancy_cannot_be_joined(self):
        self.invitations.fetch.return_value = invitation_row(user_id=self.invitee.id)
        self.tenancies.fetch_any.side_effect = lambda path: SimpleNamespace(
            name=path, display_name=None, is_enabled=False
        )

        with self.assertRaises(ConflictException) as raised:
            self.service.accept(self.invitee.id, uuid4())

        self.assertEqual(str(raised.exception), "tenancy_disabled")
        self.invitations.accept.assert_not_called()

    def test_declining(self):
        invitation = invitation_row(user_id=self.invitee.id)
        self.invitations.fetch.return_value = invitation
        self.invitations.close.return_value = True

        self.service.decline(self.invitee.id, invitation.id)

        self.invitations.close.assert_called_once_with(
            invitation.id,
            TenancyInvitationStatus.DECLINED,
            self.invitee.id,
            TenancyEventType.INVITATION_DECLINED,
        )


class TestShareAdditions(InvitationServiceTestCase):
    def test_pending_invitations_of_the_dataset_and_whether_the_caller_may_invite(self):
        mine = invitation_row(user_id=self.invitee.id, dataset_id=self.dataset.id)
        theirs = invitation_row(
            user_id=self.invitee.id, dataset_id=self.dataset.id, invited_by=None
        )
        self.invitations.pending_for_dataset.return_value = [mine, theirs]

        views, can_invite = self.service.share_additions(
            self.dataset, AccessLevel.OWNER, CALLER
        )

        self.assertEqual([v.can_withdraw for v in views], [True, False])
        self.assertIsNone(views[1].invited_by)
        self.assertTrue(can_invite)

    def test_an_embargoed_dataset_lists_its_pending_invitations_but_invites_no_one(
        self,
    ):
        self.embargo()
        pending = invitation_row(user_id=self.invitee.id, dataset_id=self.dataset.id)
        self.invitations.pending_for_dataset.return_value = [pending]

        views, can_invite = self.service.share_additions(
            self.dataset, AccessLevel.OWNER, CALLER
        )

        self.assertEqual([v.id for v in views], [pending.id])
        self.assertTrue(views[0].can_withdraw)
        self.assertFalse(can_invite)

    def test_a_staging_or_disabled_tenancy_cannot_be_invited_to(self):
        self.dataset.tenancy = "datamap/staging/data-amazon"
        self.members.add((CALLER, self.dataset.tenancy))

        self.assertFalse(
            self.service.may_invite(self.dataset, AccessLevel.OWNER, CALLER)
        )

    def test_a_disabled_production_tenancy_cannot_be_invited_to(self):
        self.tenancies.fetch_any.side_effect = lambda path: SimpleNamespace(
            name=path, display_name=None, is_enabled=False
        )

        self.assertFalse(
            self.service.may_invite(self.dataset, AccessLevel.OWNER, CALLER)
        )

    def test_an_owner_outside_the_tenancy_may_not_invite(self):
        self.members = set()

        self.assertFalse(
            self.service.may_invite(self.dataset, AccessLevel.OWNER, CALLER)
        )
