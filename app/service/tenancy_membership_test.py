import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.model.tenancy import DEFAULT_TENANCY, summary_of
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.user import UserRepository
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_notifier import TenancyNotifier

ATTO = "datamap/production/atto"


def row(name, display_name=None, is_enabled=True):
    return SimpleNamespace(name=name, display_name=display_name, is_enabled=is_enabled)


class MembershipServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.tenancies = Mock(spec=TenancyRepository)
        self.memberships = Mock(spec=TenancyMembershipRepository)
        self.users = Mock(spec=UserRepository)
        self.notifier = Mock(spec=TenancyNotifier)
        self.rows = {
            DEFAULT_TENANCY: row(DEFAULT_TENANCY, "Public"),
            ATTO: row(ATTO, "ATTO"),
            "datamap/production/lba": row("datamap/production/lba"),
            "datamap/production/old": row("datamap/production/old", "Old", False),
            "datamap/staging/data-amazon": row("datamap/staging/data-amazon"),
        }
        self.tenancies.fetch_any.side_effect = self.rows.get
        self.tenancies.list_all.return_value = list(self.rows.values())
        self.service = TenancyMembershipService(
            tenancies=self.tenancies,
            memberships=self.memberships,
            users=self.users,
            notifier=self.notifier,
        )


class TestSummaries(MembershipServiceTestCase):
    def test_a_summary_reads_the_column_or_derives_the_name(self):
        self.assertEqual(self.service.summary(ATTO), summary_of(ATTO, "ATTO"))
        self.assertEqual(
            self.service.summary("datamap/production/lba").display_name, "Lba"
        )
        self.assertEqual(
            self.service.summary("datamap/production/gone").display_name, "Gone"
        )

    def test_a_users_tenancies_come_in_the_shared_order(self):
        self.memberships.tenancies_of.return_value = [
            self.rows["datamap/staging/data-amazon"],
            self.rows["datamap/production/lba"],
            self.rows[DEFAULT_TENANCY],
            self.rows[ATTO],
        ]

        paths = [s.path for s in self.service.summaries_for(uuid4())]

        self.assertEqual(
            paths,
            [
                DEFAULT_TENANCY,
                ATTO,
                "datamap/production/lba",
                "datamap/staging/data-amazon",
            ],
        )


class TestOpenForMembers(MembershipServiceTestCase):
    def refused(self, path) -> str:
        with self.assertRaises((NotFoundException, ConflictException)) as raised:
            self.service.require_open_for_members(path)
        return str(raised.exception)

    def test_the_codes_in_order(self):
        self.assertEqual(self.refused("datamap/production/none"), "tenancy_not_found")
        self.assertEqual(self.refused(DEFAULT_TENANCY), "public_tenancy_locked")
        self.assertEqual(
            self.refused("datamap/staging/data-amazon"), "legacy_tenancy_read_only"
        )
        self.assertEqual(self.refused("datamap/production/old"), "tenancy_disabled")

    def test_an_enabled_production_tenancy_is_open(self):
        self.assertIs(self.service.require_open_for_members(ATTO), self.rows[ATTO])


class TestNewTenancy(MembershipServiceTestCase):
    def code(self, display_name, namespace) -> str:
        with self.assertRaises((IllegalStateException, ConflictException)) as raised:
            self.service.check_new_tenancy(display_name, namespace)
        return str(raised.exception)

    def test_a_valid_one_gives_its_path_and_trimmed_name(self):
        self.assertEqual(
            self.service.check_new_tenancy("  Cerrado Flux ", " cerrado-flux "),
            ("datamap/production/cerrado-flux", "Cerrado Flux"),
        )

    def test_the_namespace_is_checked_first(self):
        self.assertEqual(self.code("", "Bad NS"), "namespace_invalid")
        self.assertEqual(self.code("Public", "public"), "namespace_invalid")
        self.assertEqual(self.code("Members", "members"), "namespace_invalid")

    def test_then_the_display_name(self):
        self.assertEqual(self.code("   ", "fine"), "display_name_invalid")
        self.assertEqual(self.code("x" * 65, "fine"), "display_name_invalid")

    def test_an_existing_path_enabled_or_not_is_taken(self):
        self.assertEqual(self.code("Anything", "old"), "tenancy_exists")
        self.assertEqual(self.code("Anything", "atto"), "tenancy_exists")

    def test_a_display_name_is_unique_among_enabled_production_case_insensitively(self):
        self.assertEqual(self.code("atto", "atto-2"), "display_name_taken")
        self.assertEqual(self.code("LBA", "lba-2"), "display_name_taken")
        self.assertEqual(
            self.service.check_new_tenancy("Old", "old-2"),
            ("datamap/production/old-2", "Old"),
        )
        self.assertEqual(
            self.service.check_new_tenancy("Data Amazon", "data-amazon-2"),
            ("datamap/production/data-amazon-2", "Data Amazon"),
        )


class TestAnnounceAccess(MembershipServiceTestCase):
    def test_the_user_is_told_who_gave_access_and_how_many_datasets_there_are(self):
        user = SimpleNamespace(id=uuid4(), name="Bruna", email="b@usp.br")
        admin = SimpleNamespace(id=uuid4(), name="Luciana Rizzo", email="l@usp.br")
        self.users.fetch_any_by_id.side_effect = {user.id: user, admin.id: admin}.get
        self.tenancies.count_datasets.return_value = 7
        event_id = uuid4()

        self.service.announce_access(user.id, admin.id, ATTO, event_id)

        self.notifier.access_granted.assert_called_once_with(
            user, "Luciana Rizzo", summary_of(ATTO, "ATTO"), 7, event_id
        )

    def test_an_unknown_admin_reads_as_an_administrator(self):
        user = SimpleNamespace(id=uuid4(), name="Bruna", email="b@usp.br")
        self.users.fetch_any_by_id.side_effect = {user.id: user}.get
        self.tenancies.count_datasets.return_value = 0

        self.service.announce_access(user.id, uuid4(), ATTO, uuid4())

        self.assertEqual(
            self.notifier.access_granted.call_args.args[1], "An administrator"
        )

    def test_nobody_is_told_when_the_user_no_longer_exists(self):
        self.users.fetch_any_by_id.return_value = None

        self.service.announce_access(uuid4(), uuid4(), ATTO, uuid4())

        self.notifier.access_granted.assert_not_called()
        self.tenancies.count_datasets.assert_not_called()
