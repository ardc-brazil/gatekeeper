import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.repository.user import UserRepository
from app.service.user_refs import orcid_of, user_brief, user_ref


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


class TestOrcidOf(unittest.TestCase):
    def test_the_orcid_provider_reference(self):
        user = SimpleNamespace(
            providers=[
                SimpleNamespace(name="github", reference="ana"),
                SimpleNamespace(name="orcid", reference="0000-0002-1825-0097"),
            ]
        )

        self.assertEqual(orcid_of(user), "0000-0002-1825-0097")

    def test_none_without_one(self):
        for providers in ([], None):
            with self.subTest(providers=providers):
                self.assertIsNone(orcid_of(SimpleNamespace(providers=providers)))
