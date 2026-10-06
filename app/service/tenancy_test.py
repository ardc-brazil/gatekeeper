import unittest
from unittest.mock import Mock
from app.model.db.tenancy import Tenancy as DBModel
from app.model.tenancy import Tenancy
from app.repository.tenancy import TenancyRepository
from app.exception.conflict import ConflictException
from app.exception.not_found import NotFoundException
from app.model.tenancy import DEFAULT_TENANCY
from app.exception.illegal_state import IllegalStateException
from app.service.tenancy import TenancyService
from app.service.tenancy_membership import TenancyMembershipService


class TestTenancyService(unittest.TestCase):
    def setUp(self):
        self.repository = Mock(spec=TenancyRepository)
        self.membership_service = Mock(spec=TenancyMembershipService)
        self.membership_service.check_new_tenancy.side_effect = (
            lambda display_name, namespace: (
                f"datamap/production/{namespace}",
                display_name,
            )
        )
        self.tenancy_service = TenancyService(self.repository, self.membership_service)

    def test_fetch_success(self):
        name = "tenancy1"
        db_tenancy = DBModel(
            name=name, is_enabled=True, created_at=None, updated_at=None
        )
        self.repository.fetch.return_value = db_tenancy

        tenancy = self.tenancy_service.fetch(name)
        self.assertIsNotNone(tenancy)
        self.assertEqual(tenancy.name, name)

    def test_fetch_not_found(self):
        self.repository.fetch.return_value = None
        tenancy = self.tenancy_service.fetch("non_existent_tenancy")
        self.assertIsNone(tenancy)

    def test_fetch_all_success(self):
        db_tenancies = [
            DBModel(name="tenancy1", is_enabled=True, created_at=None, updated_at=None),
            DBModel(name="tenancy2", is_enabled=True, created_at=None, updated_at=None),
        ]
        self.repository.fetch_all.return_value = db_tenancies

        tenancies = self.tenancy_service.fetch_all()
        self.assertEqual(len(tenancies), 2)
        self.assertEqual(tenancies[0].name, "tenancy1")
        self.assertEqual(tenancies[1].name, "tenancy2")

    def test_fetch_all_empty(self):
        self.repository.fetch_all.return_value = []
        tenancies = self.tenancy_service.fetch_all()
        self.assertEqual(len(tenancies), 0)

    def test_create(self):
        tenancy = Tenancy(
            name="datamap/production/atto-lab",
            is_enabled=True,
            created_at=None,
            updated_at=None,
        )
        self.tenancy_service.create(tenancy)

        self.membership_service.check_new_tenancy.assert_called_once_with(
            "Atto Lab", "atto-lab"
        )
        (created,), _ = self.repository.upsert.call_args
        self.assertEqual(created.name, "datamap/production/atto-lab")
        self.assertIsNone(created.display_name)

    def test_create_follows_the_rules_of_a_new_tenancy(self):
        self.membership_service.check_new_tenancy.side_effect = ConflictException(
            "display_name_taken"
        )

        with self.assertRaises(ConflictException):
            self.tenancy_service.create(Tenancy(name="datamap/production/atto"))

        self.repository.upsert.assert_not_called()

    def test_create_refuses_a_path_outside_production(self):
        for name in ("datamap/staging/atto", "test/tenancy/atto", "atto"):
            with self.subTest(name=name):
                with self.assertRaises(IllegalStateException) as raised:
                    self.tenancy_service.create(Tenancy(name=name))
                self.assertEqual(str(raised.exception), "namespace_invalid")
        self.membership_service.check_new_tenancy.assert_not_called()
        self.repository.upsert.assert_not_called()

    def test_update_success(self):
        old_name = "old_tenancy"
        updated_tenancy = Tenancy(
            name="updated_tenancy", is_enabled=True, created_at=None, updated_at=None
        )
        db_tenancy = DBModel(
            name=old_name, is_enabled=True, created_at=None, updated_at=None
        )
        self.repository.fetch.return_value = db_tenancy

        self.tenancy_service.update(old_name, updated_tenancy)
        self.repository.upsert.assert_called_once()
        self.assertEqual(db_tenancy.name, "updated_tenancy")
        self.assertEqual(db_tenancy.is_enabled, True)

    def test_update_not_found(self):
        self.repository.fetch.return_value = None
        with self.assertRaises(NotFoundException):
            self.tenancy_service.update(
                "non_existent_tenancy",
                Tenancy(
                    name="updated_tenancy",
                    is_enabled=True,
                    created_at=None,
                    updated_at=None,
                ),
            )

    def test_disable_success(self):
        name = "tenancy1"
        db_tenancy = DBModel(
            name=name, is_enabled=True, created_at=None, updated_at=None
        )
        self.repository.fetch.return_value = db_tenancy

        self.tenancy_service.disable(name)
        self.repository.upsert.assert_called_once()
        self.assertFalse(db_tenancy.is_enabled)

    def test_disable_not_found(self):
        self.repository.fetch.return_value = None
        with self.assertRaises(NotFoundException):
            self.tenancy_service.disable("non_existent_tenancy")

    def test_enable_success(self):
        name = "tenancy1"
        db_tenancy = DBModel(
            name=name, is_enabled=False, created_at=None, updated_at=None
        )
        self.repository.fetch.return_value = db_tenancy

        self.tenancy_service.enable(name)
        self.repository.upsert.assert_called_once()
        self.assertTrue(db_tenancy.is_enabled)

    def test_enable_not_found(self):
        self.repository.fetch.return_value = None
        with self.assertRaises(NotFoundException):
            self.tenancy_service.enable("non_existent_tenancy")


class TestPublicIsLocked(unittest.TestCase):
    def setUp(self):
        self.repository = Mock(spec=TenancyRepository)
        self.service = TenancyService(
            self.repository, Mock(spec=TenancyMembershipService)
        )

    def test_public_cannot_be_renamed_or_changed(self):
        with self.assertRaises(ConflictException) as raised:
            self.service.update(DEFAULT_TENANCY, Tenancy(name="x", is_enabled=True))

        self.assertEqual(str(raised.exception), "public_tenancy_locked")
        self.repository.upsert.assert_not_called()

    def test_public_cannot_be_disabled(self):
        with self.assertRaises(ConflictException) as raised:
            self.service.disable(DEFAULT_TENANCY)

        self.assertEqual(str(raised.exception), "public_tenancy_locked")
        self.repository.upsert.assert_not_called()


if __name__ == "__main__":
    unittest.main()
