import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import setup
from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import (
    authorize,
    authorize_self_or_policy,
)
from app.exception.illegal_state import IllegalStateException
from app.exception.unauthorized import UnauthorizedException
from app.model.user import User
from app.service.account import AccountService
from app.service.user import UserService

CREATED = datetime(2026, 10, 3, 14, 5, tzinfo=timezone.utc)


def _user(**overrides) -> User:
    values = dict(
        id=uuid4(),
        name="Ana Souza",
        email="ana.souza@usp.br",
        providers=[],
        tenancies=[],
        roles=[],
        is_enabled=True,
        created_at=CREATED,
        updated_at=CREATED,
        email_verified_at=None,
        has_password=False,
    )
    values.update(overrides)
    return User(**values)


class UserRoutesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = Container()
        app = FastAPI()
        setup.setup_routes(app)
        setup.setup_error_handlers(app)
        app.dependency_overrides[authenticate] = lambda: None
        app.dependency_overrides[authorize] = lambda: None
        app.dependency_overrides[authorize_self_or_policy] = lambda: None
        cls.client = TestClient(app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls.container.unwire()

    def setUp(self):
        self.users = Mock(spec=UserService)
        self.container.user_service.override(providers.Object(self.users))

    def tearDown(self):
        self.container.user_service.reset_override()


class TestProfileFields(UserRoutesTestCase):
    def test_a_confirmed_account_with_a_password_says_both(self):
        self.users.fetch_by_id.return_value = _user(
            email_verified_at=CREATED, has_password=True
        )

        body = self.client.get(f"/v1/users/{uuid4()}").json()

        self.assertEqual(body["email_verified_at"], "2026-10-03T14:05:00Z")
        self.assertIs(body["has_password"], True)

    def test_an_unconfirmed_account_without_a_password_says_null_and_false(self):
        self.users.fetch_by_id.return_value = _user()

        body = self.client.get(f"/v1/users/{uuid4()}").json()

        self.assertIn("email_verified_at", body)
        self.assertIsNone(body["email_verified_at"])
        self.assertIs(body["has_password"], False)

    def test_the_lookup_by_provider_carries_them_too(self):
        self.users.fetch_by_provider.return_value = _user(email_verified_at=CREATED)

        body = self.client.get("/v1/users/providers/orcid/0000-0002-1825-0097").json()

        self.assertEqual(body["email_verified_at"], "2026-10-03T14:05:00Z")
        self.assertIs(body["has_password"], False)

    def test_reading_a_user_asks_for_self_or_policy_not_policy_alone(self):
        route = next(
            route
            for route in self.client.app.routes
            if getattr(route, "path", None) == "/v1/users/{id}"
            and "GET" in route.methods
        )
        guards = {dependency.call for dependency in route.dependant.dependencies}

        self.assertIn(authorize_self_or_policy, guards)
        self.assertNotIn(authorize, guards)


class TestChangePasswordRoute(UserRoutesTestCase):
    def setUp(self):
        super().setUp()
        self.accounts = Mock(spec=AccountService)
        self.container.account_service.override(providers.Object(self.accounts))

    def tearDown(self):
        self.container.account_service.reset_override()
        super().tearDown()

    def put(self, user_id, acting_as):
        return self.client.put(
            f"/v1/users/{user_id}/password",
            json={
                "current_password": "correct horse battery",
                "new_password": "a brand new password",
            },
            headers={"X-User-Id": str(acting_as)},
        )

    def test_a_user_changes_their_own_password(self):
        user_id = uuid4()

        response = self.put(user_id, acting_as=user_id)

        self.assertEqual(response.status_code, 204)
        self.accounts.change_password.assert_called_once_with(
            user_id=user_id,
            current_password="correct horse battery",
            new_password="a brand new password",
        )

    def test_nobody_changes_another_users_password(self):
        response = self.put(uuid4(), acting_as=uuid4())

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "invalid_credentials"})
        self.accounts.change_password.assert_not_called()

    def test_a_wrong_current_password_is_401(self):
        user_id = uuid4()
        self.accounts.change_password.side_effect = UnauthorizedException(
            "invalid_credentials"
        )

        response = self.put(user_id, acting_as=user_id)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "invalid_credentials"})

    def test_a_new_password_out_of_policy_is_400(self):
        user_id = uuid4()
        self.accounts.change_password.side_effect = IllegalStateException(
            "invalid_password"
        )

        response = self.put(user_id, acting_as=user_id)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "invalid_password"})

    def test_the_password_route_asks_for_self_or_policy(self):
        route = next(
            route
            for route in self.client.app.routes
            if getattr(route, "path", None) == "/v1/users/{id}/password"
        )
        guards = {dependency.call for dependency in route.dependant.dependencies}

        self.assertIn(authorize_self_or_policy, guards)
        self.assertNotIn(authorize, guards)
