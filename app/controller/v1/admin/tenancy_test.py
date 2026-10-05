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
from app.controller.interceptor.authorization import authorize
from app.exception.conflict import ConflictException
from app.model.tenancy_access import (
    AdminTenancyRequestView,
    NewTenancy,
    Page,
    RequestCounts,
    Requester,
)
from app.service.tenancy_request import TenancyRequestService

AT = datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc)
ADMIN = uuid4()


def _row(**overrides) -> AdminTenancyRequestView:
    values = dict(
        id=uuid4(),
        requester=Requester(uuid4(), "Bruna", "b@usp.br", True, None),
        requested_name="ATTO",
        reason="r",
        status="pending",
        kind="new",
        suggested_tenancy=None,
        created_at=AT,
        tenancy=None,
        created_tenancy=False,
        decision_message=None,
        decided_by=None,
        decided_at=None,
    )
    values.update(overrides)
    return AdminTenancyRequestView(**values)


class AdminRoutesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = Container()
        app = FastAPI()
        setup.setup_routes(app)
        setup.setup_error_handlers(app)
        app.dependency_overrides[authenticate] = lambda: None
        app.dependency_overrides[authorize] = lambda: None
        cls.app = app
        cls.client = TestClient(app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls.container.unwire()

    def setUp(self):
        self.requests = Mock(spec=TenancyRequestService)
        self.container.tenancy_request_service.override(providers.Object(self.requests))
        self.headers = {"X-User-Id": str(ADMIN)}

    def tearDown(self):
        self.container.tenancy_request_service.reset_override()


class TestAdminGuard(AdminRoutesTestCase):
    def test_every_admin_tenancy_route_goes_through_casbin(self):
        for route in self.app.routes:
            path = getattr(route, "path", "")
            if path.startswith(("/v1/admin/tenanc", "/v1/admin/users")):
                with self.subTest(path=path, methods=route.methods):
                    calls = {d.call for d in route.dependant.dependencies}
                    self.assertIn(authenticate, calls)
                    self.assertIn(authorize, calls)


class TestRequestQueueRoutes(AdminRoutesTestCase):
    def test_counts(self):
        self.requests.counts.return_value = RequestCounts(
            open=3, join=1, new=2, closed=9
        )

        response = self.client.get(
            "/v1/admin/tenancy-requests/counts", headers=self.headers
        )

        self.assertEqual(response.json(), {"open": 3, "join": 1, "new": 2, "closed": 9})

    def test_the_list_passes_the_query_through(self):
        self.requests.queue.return_value = Page(
            items=[_row()], total_count=1, limit=10, offset=0
        )

        response = self.client.get(
            "/v1/admin/tenancy-requests?status=open&kind=join&q=ana&limit=10&offset=0",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_count"], 1)
        self.assertEqual(response.json()["items"][0]["requester"]["name"], "Bruna")
        self.requests.queue.assert_called_once_with("open", "join", "ana", 10, 0)

    def test_the_defaults_are_open_50_0(self):
        self.requests.queue.return_value = Page(
            items=[], total_count=0, limit=50, offset=0
        )

        self.client.get("/v1/admin/tenancy-requests", headers=self.headers)

        self.requests.queue.assert_called_once_with("open", None, None, 50, 0)

    def test_a_limit_that_is_not_a_number_is_invalid_request(self):
        response = self.client.get(
            "/v1/admin/tenancy-requests?limit=many", headers=self.headers
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "invalid_request"})

    def test_approve_into_an_existing_tenancy_as_the_caller(self):
        request_id = uuid4()
        self.requests.approve.return_value = _row(id=request_id, status="approved")

        response = self.client.post(
            f"/v1/admin/tenancy-requests/{request_id}/approve",
            json={"tenancy": "datamap/production/atto"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "approved")
        self.requests.approve.assert_called_once_with(
            request_id, ADMIN, "datamap/production/atto", None
        )

    def test_approve_with_a_new_tenancy(self):
        request_id = uuid4()
        self.requests.approve.return_value = _row(id=request_id, status="approved")

        self.client.post(
            f"/v1/admin/tenancy-requests/{request_id}/approve",
            json={"new_tenancy": {"display_name": "ATTO", "namespace": "atto"}},
            headers=self.headers,
        )

        self.requests.approve.assert_called_once_with(
            request_id, ADMIN, None, NewTenancy(display_name="ATTO", namespace="atto")
        )

    def test_decline_with_and_without_a_body(self):
        request_id = uuid4()
        self.requests.decline.return_value = _row(id=request_id, status="declined")

        with_message = self.client.post(
            f"/v1/admin/tenancy-requests/{request_id}/decline",
            json={"message": "Ask Alan"},
            headers=self.headers,
        )
        without = self.client.post(
            f"/v1/admin/tenancy-requests/{request_id}/decline", headers=self.headers
        )

        self.assertEqual(with_message.status_code, 200)
        self.assertEqual(without.status_code, 200)
        self.assertEqual(
            [c.args for c in self.requests.decline.call_args_list],
            [(request_id, ADMIN, "Ask Alan"), (request_id, ADMIN, None)],
        )

    def test_a_conflict_keeps_its_code(self):
        self.requests.decline.side_effect = ConflictException("request_not_pending")

        response = self.client.post(
            f"/v1/admin/tenancy-requests/{uuid4()}/decline",
            json={},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "request_not_pending"})
