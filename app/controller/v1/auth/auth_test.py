import inspect
import unittest
from unittest.mock import Mock
from uuid import uuid4

from dependency_injector import providers
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import setup
from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.too_many_requests import TooManyRequestsException
from app.exception.unauthorized import UnauthorizedException
from app.service.account import AccountService

PASSWORD = "correct horse battery"


class AuthRoutesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = Container()
        cls.app = FastAPI()
        setup.setup_routes(cls.app)
        setup.setup_error_handlers(cls.app)
        cls.app.dependency_overrides[authenticate] = lambda: None
        cls.client = TestClient(cls.app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls.container.unwire()

    def setUp(self):
        self.accounts = Mock(spec=AccountService)
        self.container.account_service.override(providers.Object(self.accounts))

    def tearDown(self):
        self.container.account_service.reset_override()


class TestSignUpRoutes(AuthRoutesTestCase):
    def test_a_sign_up_answers_202_with_the_challenge(self):
        challenge_id = uuid4()
        self.accounts.sign_up.return_value = challenge_id

        response = self.client.post(
            "/v1/auth/sign-up",
            json={"name": "Ana Souza", "email": "ana@usp.br", "password": PASSWORD},
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"challenge_id": str(challenge_id)})
        self.accounts.sign_up.assert_called_once_with(
            "Ana Souza", "ana@usp.br", PASSWORD
        )

    def test_a_validation_failure_is_400_with_its_code(self):
        self.accounts.sign_up.side_effect = IllegalStateException("invalid_password")

        response = self.client.post(
            "/v1/auth/sign-up",
            json={"name": "Ana Souza", "email": "ana@usp.br", "password": "short"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "invalid_password"})

    def test_a_confirmed_sign_up_answers_the_user(self):
        user_id, challenge_id = uuid4(), uuid4()
        self.accounts.confirm_sign_up.return_value = user_id

        response = self.client.post(
            f"/v1/auth/sign-up/{challenge_id}/confirm", json={"code": "042917"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"user_id": str(user_id)})
        self.accounts.confirm_sign_up.assert_called_once_with(challenge_id, "042917")

    def test_code_errors_are_400_with_their_code(self):
        for code in ("code_invalid", "code_expired", "code_attempts_exceeded"):
            with self.subTest(code=code):
                self.accounts.confirm_sign_up.side_effect = IllegalStateException(code)

                response = self.client.post(
                    f"/v1/auth/sign-up/{uuid4()}/confirm", json={"code": "042917"}
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"detail": code})

    def test_an_unknown_challenge_is_404(self):
        self.accounts.confirm_sign_up.side_effect = NotFoundException(
            "challenge_not_found"
        )

        response = self.client.post(
            f"/v1/auth/sign-up/{uuid4()}/confirm", json={"code": "042917"}
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "challenge_not_found"})

    def test_a_challenge_id_that_is_not_a_uuid_is_404_without_reaching_the_service(
        self,
    ):
        response = self.client.post(
            "/v1/auth/sign-up/not-a-uuid/confirm", json={"code": "042917"}
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "challenge_not_found"})
        self.accounts.confirm_sign_up.assert_not_called()


class TestEmailVerificationRoutes(AuthRoutesTestCase):
    def test_a_request_answers_202_with_the_challenge(self):
        challenge_id = uuid4()
        self.accounts.request_email_verification.return_value = challenge_id

        response = self.client.post(
            "/v1/auth/email-verifications",
            json={
                "orcid": "0000-0002-1825-0097",
                "email": "ana@usp.br",
                "name": "Ana Souza",
            },
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"challenge_id": str(challenge_id)})
        self.accounts.request_email_verification.assert_called_once_with(
            "0000-0002-1825-0097", "ana@usp.br", "Ana Souza"
        )

    def test_a_confirmation_answers_the_user(self):
        user_id, challenge_id = uuid4(), uuid4()
        self.accounts.confirm_email_verification.return_value = user_id

        response = self.client.post(
            f"/v1/auth/email-verifications/{challenge_id}/confirm",
            json={"code": "042917"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"user_id": str(user_id)})

    def test_an_email_of_another_account_is_409(self):
        self.accounts.confirm_email_verification.side_effect = ConflictException(
            "email_belongs_to_another_account"
        )

        response = self.client.post(
            f"/v1/auth/email-verifications/{uuid4()}/confirm", json={"code": "042917"}
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(), {"detail": "email_belongs_to_another_account"}
        )

    def test_a_challenge_id_that_is_not_a_uuid_is_404_without_reaching_the_service(
        self,
    ):
        response = self.client.post(
            "/v1/auth/email-verifications/not-a-uuid/confirm", json={"code": "042917"}
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "challenge_not_found"})
        self.accounts.confirm_email_verification.assert_not_called()


class TestResendRoute(AuthRoutesTestCase):
    def test_a_resend_answers_202_with_no_body(self):
        challenge_id = uuid4()

        response = self.client.post(f"/v1/auth/challenges/{challenge_id}/resend")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content, b"")
        self.accounts.resend.assert_called_once_with(challenge_id)

    def test_a_resend_too_soon_is_429(self):
        self.accounts.resend.side_effect = TooManyRequestsException("resend_too_soon")

        response = self.client.post(f"/v1/auth/challenges/{uuid4()}/resend")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), {"detail": "resend_too_soon"})

    def test_a_challenge_id_that_is_not_a_uuid_is_404_without_reaching_the_service(
        self,
    ):
        response = self.client.post("/v1/auth/challenges/not-a-uuid/resend")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "challenge_not_found"})
        self.accounts.resend.assert_not_called()


class TestLoginRoute(AuthRoutesTestCase):
    def test_a_sign_in_answers_the_user(self):
        user_id = uuid4()
        self.accounts.login.return_value = user_id

        response = self.client.post(
            "/v1/auth/login", json={"email": "ana@usp.br", "password": PASSWORD}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"user_id": str(user_id)})
        self.accounts.login.assert_called_once_with("ana@usp.br", PASSWORD)

    def test_every_refusal_is_401_invalid_credentials(self):
        self.accounts.login.side_effect = UnauthorizedException("invalid_credentials")

        response = self.client.post(
            "/v1/auth/login", json={"email": "ana@usp.br", "password": PASSWORD}
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "invalid_credentials"})


class TestPasswordResetRoutes(AuthRoutesTestCase):
    def test_a_reset_request_answers_202_with_no_body(self):
        response = self.client.post(
            "/v1/auth/password-reset", json={"email": "ana@usp.br"}
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content, b"")
        self.accounts.request_password_reset.assert_called_once_with("ana@usp.br")

    def test_a_reset_confirmation_answers_204(self):
        response = self.client.post(
            "/v1/auth/password-reset/confirm",
            json={"token": "tok", "password": "a brand new password"},
        )

        self.assertEqual(response.status_code, 204)
        self.accounts.confirm_password_reset.assert_called_once_with(
            "tok", "a brand new password"
        )

    def test_an_invalid_token_is_400(self):
        self.accounts.confirm_password_reset.side_effect = IllegalStateException(
            "token_invalid"
        )

        response = self.client.post(
            "/v1/auth/password-reset/confirm",
            json={"token": "tok", "password": "a brand new password"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "token_invalid"})


class TestTheRoutesStayOffTheEventLoop(AuthRoutesTestCase):
    def test_every_route_that_hashes_is_a_plain_function_run_in_the_threadpool(self):
        routes = [
            route
            for route in self.app.routes
            if isinstance(route, APIRoute)
            and (
                route.path.startswith("/v1/auth/")
                or route.path == "/v1/users/{id}/password"
            )
        ]

        self.assertEqual(len(routes), 9)
        for route in routes:
            with self.subTest(path=route.path):
                self.assertFalse(inspect.iscoroutinefunction(route.endpoint))
