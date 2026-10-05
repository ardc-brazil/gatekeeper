import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.repository.user import UserRepository
from app.service.user_refs import dataset_ref, user_brief, user_ref


def user_row(name="Ana Lima", email="ana@usp.br"):
    return SimpleNamespace(id=uuid4(), name=name, email=email)


class TestUserBrief(unittest.TestCase):
    def setUp(self):
        self.users = Mock(spec=UserRepository)

    def test_found(self):
        user = user_row()
        self.users.fetch_any_by_id.return_value = user

        brief = user_brief(self.users, user.id)

        self.assertEqual(
            (brief.id, brief.name, brief.email), (user.id, user.name, user.email)
        )

    def test_deleted_account(self):
        user_id = uuid4()
        self.users.fetch_any_by_id.return_value = None

        brief = user_brief(self.users, user_id)

        self.assertEqual(
            (brief.id, brief.name, brief.email), (user_id, "Deleted account", None)
        )


class TestUserRef(unittest.TestCase):
    def setUp(self):
        self.users = Mock(spec=UserRepository)

    def test_found(self):
        user = user_row()
        self.users.fetch_any_by_id.return_value = user

        ref = user_ref(self.users, user.id)

        self.assertEqual((ref.id, ref.name), (user.id, user.name))

    def test_deleted_account(self):
        self.users.fetch_any_by_id.return_value = None

        ref = user_ref(self.users, uuid4())

        self.assertIsNone(ref)

    def test_none_id(self):
        ref = user_ref(self.users, None)

        self.assertIsNone(ref)
        self.users.fetch_any_by_id.assert_not_called()


class TestDatasetRef(unittest.TestCase):
    def test_present(self):
        dataset_id = uuid4()
        names = {dataset_id: "atto-flux"}

        ref = dataset_ref(names, dataset_id)

        self.assertEqual((ref.id, ref.name), (dataset_id, "atto-flux"))

    def test_absent(self):
        ref = dataset_ref({}, uuid4())

        self.assertIsNone(ref)
