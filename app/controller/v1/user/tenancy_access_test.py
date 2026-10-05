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
from app.controller.interceptor.authorization import authorize, authorize_self
from app.exception.conflict import ConflictException
from app.exception.not_found import NotFoundException
from app.model.tenancy import DEFAULT_TENANCY, summary_of
from app.model.tenancy_access import TenancyRequestView
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_request import TenancyRequestService

AT = datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc)


def _view(**overrides) -> TenancyRequestView:
    values = dict(
        id=uuid4(),
        requested_name="ATTO",
        reason="Fluxes",
        status="pending",
        tenancy=None,
        created_tenancy=False,
        decision_message=None,
        created_at=AT,
        decided_at=None,
    )
    values.update(overrides)
    return TenancyRequestView(**values)


class SelfRoutesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = Container()
        app = FastAPI()
        setup.setup_routes(app)
        setup.setup_error_handlers(app)
        app.dependency_overrides[authenticate] = lambda: None
        app.dependency_overrides[authorize] = lambda: None
        app.dependency_overrides[authorize_self] = lambda: None
        cls.app = app
        cls.client = TestClient(app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls.container.unwire()

    def setUp(self):
        self.memberships = Mock(spec=TenancyMembershipService)
        self.requests = Mock(spec=TenancyRequestService)
        self.container.tenancy_membership_service.override(
            providers.Object(self.memberships)
        )
        self.container.tenancy_request_service.override(providers.Object(self.requests))
        self.user_id = uuid4()

    def tearDown(self):
        self.container.tenancy_membership_service.reset_override()
        self.container.tenancy_request_service.reset_override()


class TestTenancyRoutes(SelfRoutesTestCase):
    def test_my_tenancies(self):
        self.memberships.summaries_for.return_value = [
            summary_of(DEFAULT_TENANCY, "Public")
        ]

        response = self.client.get(f"/v1/users/{self.user_id}/tenancies")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {
                    "path": DEFAULT_TENANCY,
                    "display_name": "Public",
                    "is_default": True,
                    "is_legacy": False,
                }
            ],
        )
        self.memberships.summaries_for.assert_called_once_with(self.user_id)

    def test_the_routes_are_self_only_and_never_ask_casbin(self):
        for route in self.app.routes:
            path = getattr(route, "path", "")
            if path.startswith("/v1/users/{id}/tenanc"):
                with self.subTest(path=path, methods=route.methods):
                    calls = {d.call for d in route.dependant.dependencies}
                    self.assertIn(authorize_self, calls)
                    self.assertIn(authenticate, calls)
                    self.assertNotIn(authorize, calls)


class TestRequestRoutes(SelfRoutesTestCase):
    def test_creating_answers_201_with_the_request(self):
        self.requests.create.return_value = _view()

        response = self.client.post(
            f"/v1/users/{self.user_id}/tenancy-requests",
            json={"tenancy_name": "ATTO", "reason": "Fluxes"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "pending")
        self.assertEqual(response.json()["created_at"], "2026-10-05T09:30:00Z")
        self.requests.create.assert_called_once_with(self.user_id, "ATTO", "Fluxes")

    def test_a_malformed_body_is_invalid_request(self):
        response = self.client.post(
            f"/v1/users/{self.user_id}/tenancy-requests", json={"tenancy_name": "ATTO"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "invalid_request"})

    def test_a_pending_request_is_409(self):
        self.requests.create.side_effect = ConflictException("request_pending")

        response = self.client.post(
            f"/v1/users/{self.user_id}/tenancy-requests",
            json={"tenancy_name": "ATTO", "reason": "Fluxes"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "request_pending"})

    def test_listing_and_withdrawing(self):
        self.requests.list_for_user.return_value = [_view(), _view(status="declined")]
        request_id = uuid4()

        listed = self.client.get(f"/v1/users/{self.user_id}/tenancy-requests")
        withdrawn = self.client.delete(
            f"/v1/users/{self.user_id}/tenancy-requests/{request_id}"
        )

        self.assertEqual([r["status"] for r in listed.json()], ["pending", "declined"])
        self.assertEqual(withdrawn.status_code, 204)
        self.requests.withdraw.assert_called_once_with(self.user_id, request_id)

    def test_withdrawing_someone_elses_is_404(self):
        self.requests.withdraw.side_effect = NotFoundException("request_not_found")

        response = self.client.delete(
            f"/v1/users/{self.user_id}/tenancy-requests/{uuid4()}"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "request_not_found"})

    def test_the_retired_membership_routes_are_gone(self):
        for method in ("post", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    f"/v1/users/{self.user_id}/tenancies"
                )
                self.assertIn(response.status_code, (404, 405))
