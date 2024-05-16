import unittest
from unittest.mock import Mock
from app.model.db.tenancy import Tenancy as DBModel
from app.model.tenancy import Tenancy
from app.repository.tenancy import TenancyRepository
from app.exception.not_found import NotFoundException
from app.service.tenancy import TenancyService


class TestTenancyService(unittest.TestCase):
    def setUp(self):
        self.repository = Mock(spec=TenancyRepository)
        self.tenancy_service = TenancyService(self.repository)

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
            name="new_tenancy", is_enabled=True, created_at=None, updated_at=None
        )
        self.tenancy_service.create(tenancy)
        self.repository.upsert.assert_called_once()

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


if __name__ == "__main__":
    unittest.main()
