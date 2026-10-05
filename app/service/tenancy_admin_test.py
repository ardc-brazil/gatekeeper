import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.model.tenancy import DEFAULT_TENANCY, TenancyInvitationStatus
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_invitation import TenancyInvitationRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.user import UserRepository
from app.service.tenancy_admin import TenancyAdminService
from app.service.tenancy_membership import TenancyMembershipService

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
ATTO = "datamap/production/atto"
LEGACY = "datamap/staging/data-amazon"


def tenancy_row(name, display_name=None, is_enabled=True):
    return SimpleNamespace(name=name, display_name=display_name, is_enabled=is_enabled)


def user_row(name="Ana Lima", email="ana@usp.br"):
    return SimpleNamespace(
        id=uuid4(), name=name, email=email, created_at=NOW - timedelta(days=90)
    )


class AdminServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.tenancies = Mock(spec=TenancyRepository)
        self.memberships = Mock(spec=TenancyMembershipRepository)
        self.membership_service = Mock(spec=TenancyMembershipService)
        self.invitations = Mock(spec=TenancyInvitationRepository)
        self.users = Mock(spec=UserRepository)
        self.rows = {
            DEFAULT_TENANCY: tenancy_row(DEFAULT_TENANCY, "Public"),
            ATTO: tenancy_row(ATTO, "ATTO"),
            "datamap/production/beta": tenancy_row(
                "datamap/production/beta", None, False
            ),
            LEGACY: tenancy_row(LEGACY),
        }
        self.tenancies.fetch_any.side_effect = self.rows.get
        self.tenancies.list_all.return_value = [
            self.rows[LEGACY],
            self.rows["datamap/production/beta"],
            self.rows[ATTO],
            self.rows[DEFAULT_TENANCY],
        ]
        self.admin = user_row(name="Luciana Rizzo")
        self.member = user_row()
        self.people = {self.admin.id: self.admin, self.member.id: self.member}
        self.users.fetch_any_by_id.side_effect = self.people.get
        self.users.fetch_by_id.side_effect = (
            lambda id, is_enabled=True: self.people.get(id)
        )
        self.service = TenancyAdminService(
            tenancies=self.tenancies,
            memberships=self.memberships,
            membership_service=self.membership_service,
            invitations=self.invitations,
            users=self.users,
            clock=lambda: NOW,
        )


class TestList(AdminServiceTestCase):
    def test_every_tenancy_with_counts_in_the_shared_order(self):
        self.tenancies.member_counts.return_value = {DEFAULT_TENANCY: 120, ATTO: 4}
        self.tenancies.dataset_counts.return_value = {ATTO: 9}

        views = self.service.list()

        self.assertEqual(
            [v.path for v in views],
            [DEFAULT_TENANCY, ATTO, "datamap/production/beta", LEGACY],
        )
        public, atto, beta, legacy = views
        self.assertEqual(
            (public.members, public.datasets, public.is_default), (120, 0, True)
        )
        self.assertEqual(
            (atto.members, atto.datasets, atto.display_name), (4, 9, "ATTO")
        )
        self.assertEqual((beta.display_name, beta.is_enabled), ("Beta", False))
        self.assertTrue(legacy.is_legacy)


class TestCreate(AdminServiceTestCase):
    def test_a_new_tenancy_is_validated_then_created_with_its_event(self):
        self.membership_service.check_new_tenancy.return_value = (
            "datamap/production/cerrado-flux",
            "Cerrado Flux",
        )

        view = self.service.create(self.admin.id, "Cerrado Flux", "cerrado-flux")

        self.tenancies.create_with_event.assert_called_once_with(
            "datamap/production/cerrado-flux", "Cerrado Flux", self.admin.id
        )
        self.assertEqual(view.path, "datamap/production/cerrado-flux")
        self.assertEqual((view.members, view.datasets, view.is_enabled), (0, 0, True))

    def test_the_validation_codes_pass_through(self):
        self.membership_service.check_new_tenancy.side_effect = ConflictException(
            "display_name_taken"
        )

        with self.assertRaises(ConflictException):
            self.service.create(self.admin.id, "ATTO", "atto-2")
        self.tenancies.create_with_event.assert_not_called()


class TestMembers(AdminServiceTestCase):
    def test_members_with_since_and_who_invited_them(self):
        other = user_row(name="Bruno")
        self.people[other.id] = other
        self.memberships.list_members.return_value = ([self.member, other], 2)
        added = NOW - timedelta(days=3)
        self.memberships.added_at.return_value = {self.member.id: added}
        self.memberships.inviters.return_value = {other.id: self.admin.id}
        self.invitations.pending_for_tenancy.return_value = []

        view = self.service.members(ATTO, 50, 0)

        first, second = view.members.items
        self.assertEqual(first.since, added)
        self.assertIsNone(first.invited_by)
        self.assertEqual(second.since, other.created_at)
        self.assertEqual(second.invited_by.name, "Luciana Rizzo")
        self.assertEqual(view.members.total_count, 2)
        self.memberships.list_members.assert_called_once_with(ATTO, 50, 0)

    def test_pending_invitations_come_with_them_except_in_public_and_legacy(self):
        self.memberships.list_members.return_value = ([], 0)
        self.memberships.added_at.return_value = {}
        self.memberships.inviters.return_value = {}
        invitation = SimpleNamespace(
            id=uuid4(),
            user_id=self.member.id,
            invited_by=self.admin.id,
            dataset_id=uuid4(),
            status=TenancyInvitationStatus.PENDING,
            created_at=NOW,
        )
        self.invitations.pending_for_tenancy.return_value = [invitation]
        self.invitations.dataset_names.return_value = {invitation.dataset_id: "Ozone"}

        atto = self.service.members(ATTO, 50, 0)
        public = self.service.members(DEFAULT_TENANCY, 50, 0)
        legacy = self.service.members(LEGACY, 50, 0)

        (pending,) = atto.invitations
        self.assertEqual(pending.user.email, "ana@usp.br")
        self.assertEqual(pending.invited_by.name, "Luciana Rizzo")
        self.assertEqual(pending.dataset.name, "Ozone")
        self.assertEqual(public.invitations, [])
        self.assertEqual(legacy.invitations, [])

    def test_an_unknown_tenancy_or_bad_paging(self):
        with self.assertRaises(NotFoundException) as raised:
            self.service.members("datamap/production/none", 50, 0)
        self.assertEqual(str(raised.exception), "tenancy_not_found")
        for limit, offset in ((0, 0), (101, 0), (50, -1)):
            with self.subTest(limit=limit, offset=offset):
                with self.assertRaises(IllegalStateException):
                    self.service.members(ATTO, limit, offset)


class TestRemovalImpact(AdminServiceTestCase):
    def test_what_removing_a_member_changes(self):
        self.memberships.is_member.return_value = True
        self.memberships.added_at.return_value = {}
        self.memberships.removal_counts.return_value = (9, 2, 1)

        impact = self.service.removal_impact(ATTO, self.member.id)

        self.assertEqual(impact.member_since, self.member.created_at)
        self.assertEqual(
            (impact.datasets_in_tenancy, impact.shared_with_user, impact.owned_by_user),
            (9, 2, 1),
        )

    def test_someone_who_is_not_a_member(self):
        self.memberships.is_member.return_value = False

        with self.assertRaises(NotFoundException) as raised:
            self.service.removal_impact(ATTO, self.member.id)

        self.assertEqual(str(raised.exception), "member_not_found")


class TestAddAndRemove(AdminServiceTestCase):
    def test_adding_a_member_records_and_announces_it(self):
        self.memberships.is_member.return_value = False
        event_id = uuid4()
        self.memberships.add.return_value = event_id

        view = self.service.add(ATTO, self.member.id, self.admin.id)

        self.membership_service.require_open_for_members.assert_called_once_with(ATTO)
        self.memberships.add.assert_called_once_with(
            ATTO, self.member.id, self.admin.id
        )
        self.membership_service.announce_access.assert_called_once_with(
            self.member.id, self.admin.id, ATTO, event_id
        )
        self.assertEqual(
            (view.id, view.since, view.invited_by), (self.member.id, NOW, None)
        )

    def test_adding_refusals(self):
        self.membership_service.require_open_for_members.side_effect = (
            ConflictException("public_tenancy_locked")
        )
        with self.assertRaises(ConflictException):
            self.service.add(DEFAULT_TENANCY, self.member.id, self.admin.id)

        self.membership_service.require_open_for_members.side_effect = None
        with self.assertRaises(NotFoundException) as raised:
            self.service.add(ATTO, uuid4(), self.admin.id)
        self.assertEqual(str(raised.exception), "no_account")

        self.memberships.is_member.return_value = True
        with self.assertRaises(ConflictException) as raised:
            self.service.add(ATTO, self.member.id, self.admin.id)
        self.assertEqual(str(raised.exception), "already_member")
        self.memberships.add.assert_not_called()

    def test_removing(self):
        self.memberships.remove.return_value = True

        self.service.remove(ATTO, self.member.id, self.admin.id)

        self.memberships.remove.assert_called_once_with(
            ATTO, self.member.id, self.admin.id
        )

    def test_removal_refusals_in_order(self):
        cases = (
            ("datamap/production/none", NotFoundException, "tenancy_not_found"),
            (DEFAULT_TENANCY, ConflictException, "public_tenancy_locked"),
            (LEGACY, ConflictException, "legacy_tenancy_read_only"),
        )
        for path, exception, code in cases:
            with self.subTest(path=path):
                with self.assertRaises(exception) as raised:
                    self.service.remove(path, self.member.id, self.admin.id)
                self.assertEqual(str(raised.exception), code)
        self.memberships.remove.assert_not_called()

        self.memberships.remove.return_value = False
        with self.assertRaises(NotFoundException) as raised:
            self.service.remove(ATTO, self.member.id, self.admin.id)
        self.assertEqual(str(raised.exception), "member_not_found")


class TestUserSearch(AdminServiceTestCase):
    def test_at_least_two_characters(self):
        for q in (None, "", " a "):
            with self.subTest(q=q):
                with self.assertRaises(IllegalStateException) as raised:
                    self.service.search_users(q)
                self.assertEqual(str(raised.exception), "invalid_request")

    def test_hits_are_id_name_and_email(self):
        self.users.search_admin.return_value = [self.member]

        (hit,) = self.service.search_users("  an ")

        self.users.search_admin.assert_called_once_with("an", 10)
        self.assertEqual(
            (hit.id, hit.name, hit.email), (self.member.id, "Ana Lima", "ana@usp.br")
        )
