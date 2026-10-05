import inspect
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.exception.conflict import ConflictException
from app.exception.forbidden import ForbiddenException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.model.tenancy import (
    TenancyEventType,
    TenancyInvitationStatus,
    summary_of,
)
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_invitation import TenancyInvitationRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.user import UserRepository
from app.service.tenancy_invitation import TenancyInvitationService
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_notifier import TenancyNotifier

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
ATTO = "datamap/production/atto"
CALLER = uuid4()


def person(name="Bruna Costa", email="bruna@usp.br", providers=()):
    return SimpleNamespace(
        id=uuid4(), name=name, email=email, providers=list(providers)
    )


def invitation_row(**overrides):
    values = dict(
        id=uuid4(),
        tenancy=ATTO,
        user_id=uuid4(),
        invited_by=CALLER,
        status=TenancyInvitationStatus.PENDING,
        created_at=NOW,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class InvitationServiceTestCase(unittest.TestCase):
    def setUp(self):
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
        self.members = {(CALLER, ATTO)}
        self.memberships.is_member.side_effect = lambda user_id, tenancy: (
            (user_id, tenancy) in self.members
        )
        self.invitations.has_pending.return_value = False
        self.invitations.pending_for_tenancy.return_value = []
        self.invitations.create.side_effect = (
            lambda tenancy, user_id, invited_by: invitation_row(
                tenancy=tenancy, user_id=user_id, invited_by=invited_by
            )
        )
        self.service = TenancyInvitationService(
            invitations=self.invitations,
            memberships=self.memberships,
            membership_service=self.membership_service,
            tenancies=self.tenancies,
            users=self.users,
            notifier=self.notifier,
        )

    def outsider(self) -> None:
        self.members = set()


class TestWhoReachesTheWorkspace(InvitationServiceTestCase):
    def calls(self):
        return {
            "members": lambda: self.service.members(CALLER, ATTO, 50, 0),
            "pending_in": lambda: self.service.pending_in(CALLER, ATTO),
            "lookup": lambda: self.service.lookup(CALLER, ATTO, "bruna@usp.br"),
            "invite": lambda: self.service.invite(CALLER, ATTO, self.invitee.id),
            "withdraw": lambda: self.service.withdraw(CALLER, ATTO, uuid4()),
        }

    def test_a_non_member_gets_tenancy_not_found_everywhere(self):
        self.outsider()

        for name, call in self.calls().items():
            with self.subTest(route=name):
                with self.assertRaises(NotFoundException) as raised:
                    call()
                self.assertEqual(str(raised.exception), "tenancy_not_found")
        self.invitations.create.assert_not_called()
        self.memberships.list_members.assert_not_called()

    def test_a_tenancy_closed_to_members_answers_its_code_everywhere(self):
        for code in (
            "public_tenancy_locked",
            "legacy_tenancy_read_only",
            "tenancy_disabled",
        ):
            self.membership_service.require_open_for_members.side_effect = (
                ConflictException(code)
            )
            for name, call in self.calls().items():
                with self.subTest(route=name, code=code):
                    with self.assertRaises(ConflictException) as raised:
                        call()
                    self.assertEqual(str(raised.exception), code)
        self.invitations.create.assert_not_called()

    def test_an_admin_who_is_not_a_member_gets_tenancy_not_found(self):
        self.outsider()

        with self.assertRaises(NotFoundException) as raised:
            self.service.invite(CALLER, ATTO, self.invitee.id)

        self.assertEqual(str(raised.exception), "tenancy_not_found")
        self.assertNotIn(
            "user_service", inspect.signature(TenancyInvitationService).parameters
        )
        self.invitations.create.assert_not_called()


class TestMembers(InvitationServiceTestCase):
    def test_names_and_orcid_ids_without_emails(self):
        orcid = SimpleNamespace(name="orcid", reference="0000-0002-1825-0097")
        ana, bruna = person("Ana", "ana@usp.br", [orcid]), person()
        self.memberships.list_members.return_value = ([ana, bruna], 7)

        page = self.service.members(CALLER, ATTO, 2, 4)

        self.memberships.list_members.assert_called_once_with(ATTO, 2, 4)
        self.assertEqual(
            [(m.id, m.name, m.orcid) for m in page.items],
            [(ana.id, "Ana", "0000-0002-1825-0097"), (bruna.id, "Bruna Costa", None)],
        )
        self.assertFalse(any(hasattr(m, "email") for m in page.items))
        self.assertEqual((page.total_count, page.limit, page.offset), (7, 2, 4))

    def test_a_page_out_of_bounds_is_invalid_request(self):
        for limit, offset in ((0, 0), (101, 0), (10, -1)):
            with self.subTest(limit=limit, offset=offset):
                with self.assertRaises(IllegalStateException) as raised:
                    self.service.members(CALLER, ATTO, limit, offset)
                self.assertEqual(str(raised.exception), "invalid_request")


class TestPendingInTheWorkspace(InvitationServiceTestCase):
    def test_only_the_inviter_may_withdraw_and_no_email_is_shown(self):
        mine = invitation_row(user_id=self.invitee.id)
        theirs = invitation_row(user_id=self.invitee.id, invited_by=None)
        self.invitations.pending_for_tenancy.return_value = [mine, theirs]

        views = self.service.pending_in(CALLER, ATTO)

        self.invitations.pending_for_tenancy.assert_called_once_with(ATTO)
        self.assertEqual([v.can_withdraw for v in views], [True, False])
        self.assertEqual(views[0].user.name, "Bruna Costa")
        self.assertEqual(views[0].invited_by.name, "Alan Calheiros")
        self.assertIsNone(views[1].invited_by)
        self.assertFalse(hasattr(views[0].user, "email"))

    def test_a_deleted_invitee_is_named_as_such(self):
        self.invitations.pending_for_tenancy.return_value = [invitation_row()]

        (view,) = self.service.pending_in(CALLER, ATTO)

        self.assertEqual(view.user.name, "Deleted account")


class TestInviteRules(InvitationServiceTestCase):
    def code(self) -> str:
        with self.assertRaises((ConflictException, NotFoundException)) as raised:
            self.service.invite(CALLER, ATTO, self.invitee.id)
        return str(raised.exception)

    def test_a_member_invites(self):
        view = self.service.invite(CALLER, ATTO, self.invitee.id)

        self.invitations.create.assert_called_once_with(ATTO, self.invitee.id, CALLER)
        self.assertEqual(view.user.name, "Bruna Costa")
        self.assertEqual(view.invited_by.name, "Alan Calheiros")
        self.assertTrue(view.can_withdraw)

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
        view = self.service.invite(CALLER, ATTO, self.invitee.id)

        for notify in (self.notifier.invitation, self.notifier.invitation_notice):
            notify.assert_called_once_with(
                self.invitee, "Alan Calheiros", summary_of(ATTO, "ATTO"), view.id
            )

    def test_a_failed_notice_still_returns_the_committed_invitation(self):
        self.notifier.invitation.side_effect = RuntimeError("smtp")

        with self.assertLogs("service:TenancyNotifier", "ERROR"):
            view = self.service.invite(CALLER, ATTO, self.invitee.id)

        self.assertEqual(view.user.name, "Bruna Costa")
        self.invitations.create.assert_called_once()


class TestLookup(InvitationServiceTestCase):
    def test_an_exact_email_outside_the_tenancy_can_be_invited(self):
        self.users.fetch_by_email_insensitive.return_value = self.invitee

        found = self.service.lookup(CALLER, ATTO, "  Bruna@USP.br ")

        self.users.fetch_by_email_insensitive.assert_called_once_with("bruna@usp.br")
        self.assertEqual(found.user.email, "bruna@usp.br")
        self.assertFalse(found.tenancy_member)
        self.assertFalse(found.invitation_pending)
        self.assertTrue(found.can_invite)
        self.assertEqual(found.datasets, 12)
        self.tenancies.count_datasets.assert_called_once_with(ATTO)

    def test_an_orcid_is_looked_up_as_a_provider(self):
        self.users.fetch_by_provider.return_value = self.invitee

        self.service.lookup(CALLER, ATTO, "https://orcid.org/0000-0002-1825-0097")

        self.users.fetch_by_provider.assert_called_once_with(
            provider_name="orcid", reference="0000-0002-1825-0097"
        )

    def test_a_lookup_by_orcid_does_not_reveal_the_email(self):
        self.users.fetch_by_provider.return_value = self.invitee
        self.members.add((self.invitee.id, ATTO))

        found = self.service.lookup(CALLER, ATTO, "0000-0002-1825-0097")

        self.assertEqual(
            (found.user.id, found.user.name, found.user.email),
            (self.invitee.id, "Bruna Costa", None),
        )
        self.assertTrue(found.tenancy_member)
        self.assertFalse(found.can_invite)

    def test_every_lookup_is_logged_without_the_value(self):
        self.users.fetch_by_provider.return_value = self.invitee
        self.users.fetch_by_email_insensitive.return_value = None
        orcid, email = "0000-0002-1825-0097", "ghost@usp.br"

        with self.assertLogs("service:TenancyInvitationService", "INFO") as logs:
            self.service.lookup(CALLER, ATTO, orcid)
            with self.assertRaises(NotFoundException):
                self.service.lookup(CALLER, ATTO, email)

        found, missing = logs.records
        for record, lookup_by, matched in (
            (found, "orcid", True),
            (missing, "email", False),
        ):
            self.assertEqual(
                (record.user_id, record.tenancy, record.lookup_by, record.matched),
                (str(CALLER), ATTO, lookup_by, matched),
            )
            logged = repr(vars(record)) + record.getMessage()
            self.assertNotIn(orcid, logged)
            self.assertNotIn(email, logged)

    def test_a_pending_invitee_cannot_be_invited_again(self):
        self.users.fetch_by_email_insensitive.return_value = self.invitee
        self.invitations.has_pending.return_value = True

        found = self.service.lookup(CALLER, ATTO, "bruna@usp.br")

        self.assertTrue(found.invitation_pending)
        self.assertFalse(found.can_invite)

    def test_a_malformed_value_is_invalid_request(self):
        for value in ("not an address", "0000-0002-1825-0098", ""):
            with self.subTest(value=value):
                with self.assertRaises(IllegalStateException) as raised:
                    self.service.lookup(CALLER, ATTO, value)
                self.assertEqual(str(raised.exception), "invalid_request")

    def test_nobody_found_is_no_account(self):
        self.users.fetch_by_email_insensitive.return_value = None

        with self.assertRaises(NotFoundException) as raised:
            self.service.lookup(CALLER, ATTO, "ghost@usp.br")

        self.assertEqual(str(raised.exception), "no_account")


class TestWithdraw(InvitationServiceTestCase):
    def test_the_inviter_withdraws(self):
        invitation = invitation_row()
        self.invitations.fetch.return_value = invitation
        self.invitations.close.return_value = True

        self.service.withdraw(CALLER, ATTO, invitation.id)

        self.invitations.close.assert_called_once_with(
            invitation.id,
            TenancyInvitationStatus.WITHDRAWN,
            CALLER,
            TenancyEventType.INVITATION_WITHDRAWN,
        )

    def test_another_member_is_forbidden(self):
        self.invitations.fetch.return_value = invitation_row(invited_by=uuid4())

        with self.assertRaises(ForbiddenException):
            self.service.withdraw(CALLER, ATTO, uuid4())
        self.invitations.close.assert_not_called()

    def test_an_invitation_of_another_tenancy_or_not_pending_is_not_found(self):
        for row in (
            invitation_row(tenancy="datamap/production/other"),
            invitation_row(status=TenancyInvitationStatus.ACCEPTED),
            None,
        ):
            with self.subTest(row=row):
                self.invitations.fetch.return_value = row
                with self.assertRaises(NotFoundException) as raised:
                    self.service.withdraw(CALLER, ATTO, uuid4())
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
    def test_pending_invitations_say_who_and_how_many_datasets(self):
        invitation = invitation_row(user_id=self.invitee.id)
        self.invitations.pending_for_user.return_value = [invitation]

        (view,) = self.service.pending_for_user(self.invitee.id)

        self.assertEqual(view.tenancy, summary_of(ATTO, "ATTO"))
        self.assertEqual(view.invited_by.name, "Alan Calheiros")
        self.assertEqual(view.datasets, 12)
        self.assertFalse(hasattr(view, "dataset"))

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
