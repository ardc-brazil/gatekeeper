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
    AdminTenancyView,
    NewTenancy,
    Page,
    RemovalImpactView,
    RequestCounts,
    Requester,
    TenancyMembersView,
    TenancyMemberView,
    UserBrief,
)
from app.service.tenancy_admin import TenancyAdminService
from app.service.tenancy_invitation import TenancyInvitationService
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


class TestAdminInvitationRoutes(AdminRoutesTestCase):
    def setUp(self):
        super().setUp()
        self.invitations = Mock(spec=TenancyInvitationService)
        self.container.tenancy_invitation_service.override(
            providers.Object(self.invitations)
        )

    def tearDown(self):
        self.container.tenancy_invitation_service.reset_override()
        super().tearDown()

    def test_an_admin_withdraws_an_invitation(self):
        invitation_id = uuid4()

        response = self.client.delete(
            f"/v1/admin/tenancy-invitations/{invitation_id}", headers=self.headers
        )

        self.assertEqual(response.status_code, 204)
        self.invitations.withdraw_as_admin.assert_called_once_with(invitation_id, ADMIN)


class TestAdminTenancyRoutes(AdminRoutesTestCase):
    def setUp(self):
        super().setUp()
        self.admin_service = Mock(spec=TenancyAdminService)
        self.container.tenancy_admin_service.override(
            providers.Object(self.admin_service)
        )

    def tearDown(self):
        self.container.tenancy_admin_service.reset_override()
        super().tearDown()

    def test_list_and_create(self):
        view = AdminTenancyView(
            path="datamap/production/atto",
            display_name="ATTO",
            members=4,
            datasets=9,
            is_default=False,
            is_legacy=False,
            is_enabled=True,
        )
        self.admin_service.list.return_value = [view]
        self.admin_service.create.return_value = view

        listed = self.client.get("/v1/admin/tenancies", headers=self.headers)
        created = self.client.post(
            "/v1/admin/tenancies",
            json={"display_name": "ATTO", "namespace": "atto"},
            headers=self.headers,
        )

        self.assertEqual(listed.json()[0]["members"], 4)
        self.assertEqual(created.status_code, 201)
        self.admin_service.create.assert_called_once_with(ADMIN, "ATTO", "atto")

    def test_the_tenancy_path_travels_unencoded(self):
        self.admin_service.members.return_value = TenancyMembersView(
            members=Page(items=[], total_count=0, limit=50, offset=0), invitations=[]
        )
        user_id = uuid4()
        self.admin_service.removal_impact.return_value = RemovalImpactView(
            member_since=AT, datasets_in_tenancy=1, shared_with_user=0, owned_by_user=0
        )

        members = self.client.get(
            "/v1/admin/tenancies/datamap/production/atto/members?limit=50&offset=0",
            headers=self.headers,
        )
        impact = self.client.get(
            f"/v1/admin/tenancies/datamap/production/atto/members/{user_id}",
            headers=self.headers,
        )
        removed = self.client.delete(
            f"/v1/admin/tenancies/datamap/production/atto/members/{user_id}",
            headers=self.headers,
        )

        self.assertEqual(members.status_code, 200)
        self.admin_service.members.assert_called_once_with(
            "datamap/production/atto", 50, 0
        )
        self.assertEqual(impact.json()["datasets_in_tenancy"], 1)
        self.admin_service.removal_impact.assert_called_once_with(
            "datamap/production/atto", user_id
        )
        self.assertEqual(removed.status_code, 204)
        self.admin_service.remove.assert_called_once_with(
            "datamap/production/atto", user_id, ADMIN
        )

    def test_adding_a_member_answers_201_with_the_member(self):
        user_id = uuid4()
        self.admin_service.add.return_value = TenancyMemberView(
            id=user_id, name="Ana", email="a@usp.br", since=AT, invited_by=None
        )

        response = self.client.post(
            "/v1/admin/tenancies/datamap/production/atto/members",
            json={"user_id": str(user_id)},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], str(user_id))
        self.admin_service.add.assert_called_once_with(
            "datamap/production/atto", user_id, ADMIN
        )

    def test_user_search(self):
        self.admin_service.search_users.return_value = [
            UserBrief(id=uuid4(), name="Ana", email="a@usp.br")
        ]

        response = self.client.get("/v1/admin/users?q=an", headers=self.headers)

        self.assertEqual(response.json()[0]["name"], "Ana")
        self.admin_service.search_users.assert_called_once_with("an")
