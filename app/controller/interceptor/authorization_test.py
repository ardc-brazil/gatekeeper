import unittest
from unittest.mock import Mock
from uuid import uuid4

from dependency_injector import providers
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import setup
from app.container import Container
from app.controller.interceptor.authorization import authorize_self_or_policy
from app.exception.unauthorized import UnauthorizedException
from app.service.auth import AuthService


class TestSelfOrPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = Container()
        app = FastAPI()
        setup.setup_error_handlers(app)

        @app.get("/users/{id}", dependencies=[Depends(authorize_self_or_policy)])
        def read(id: str):
            return {"id": id}

        cls.client = TestClient(app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls.container.unwire()

    def setUp(self):
        self.auth = Mock(spec=AuthService)
        self.container.auth_service.override(providers.Object(self.auth))

    def tearDown(self):
        self.container.auth_service.reset_override()

    def test_a_user_reaches_their_own_record_without_any_role(self):
        user_id = uuid4()

        response = self.client.get(
            f"/users/{user_id}", headers={"X-User-Id": str(user_id)}
        )

        self.assertEqual(response.status_code, 200)
        self.auth.authorize_user.assert_not_called()

    def test_the_same_id_written_in_capitals_is_still_themselves(self):
        user_id = uuid4()

        response = self.client.get(
            f"/users/{str(user_id).upper()}", headers={"X-User-Id": str(user_id)}
        )

        self.assertEqual(response.status_code, 200)
        self.auth.authorize_user.assert_not_called()

    def test_anyone_else_goes_through_casbin(self):
        user_id, other = uuid4(), uuid4()

        response = self.client.get(
            f"/users/{other}", headers={"X-User-Id": str(user_id)}
        )

        self.assertEqual(response.status_code, 200)
        self.auth.authorize_user.assert_called_once_with(
            user_id, f"/users/{other}", "GET"
        )

    def test_casbin_refusing_someone_else_is_401(self):
        self.auth.authorize_user.side_effect = UnauthorizedException("not_authorized")

        response = self.client.get(
            f"/users/{uuid4()}", headers={"X-User-Id": str(uuid4())}
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "not_authorized"})

    def test_a_path_id_that_is_not_a_uuid_goes_through_casbin(self):
        self.client.get("/users/everyone", headers={"X-User-Id": str(uuid4())})

        self.auth.authorize_user.assert_called_once()

    def test_without_a_user_header_it_is_401(self):
        response = self.client.get(f"/users/{uuid4()}")

        self.assertEqual(response.status_code, 401)
        self.auth.authorize_user.assert_not_called()
