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
from app.exception.illegal_state import IllegalStateException
from app.model.tenancy_access import (
    DatasetTenancyInvitationView,
    ShareLookupView,
    UserBrief,
)
from app.service.tenancy_invitation import TenancyInvitationService

AT = datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc)
CALLER = uuid4()


class DatasetInvitationRoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = Container()
        app = FastAPI()
        setup.setup_routes(app)
        setup.setup_error_handlers(app)
        app.dependency_overrides[authenticate] = lambda: None
        app.dependency_overrides[authorize] = lambda: None
        cls.client = TestClient(app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls.container.unwire()

    def setUp(self):
        self.service = Mock(spec=TenancyInvitationService)
        self.container.tenancy_invitation_service.override(
            providers.Object(self.service)
        )
        self.headers = {"X-User-Id": str(CALLER)}
        self.dataset_id = uuid4()

    def tearDown(self):
        self.container.tenancy_invitation_service.reset_override()

    def test_lookup(self):
        self.service.lookup.return_value = ShareLookupView(
            user=UserBrief(id=uuid4(), name="Bruna", email="b@usp.br"),
            tenancy_member=False,
            invitation_pending=False,
            can_invite=True,
        )

        response = self.client.get(
            f"/v1/datasets/{self.dataset_id}/share/lookup?value=b@usp.br",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["can_invite"], True)
        self.service.lookup.assert_called_once_with(self.dataset_id, CALLER, "b@usp.br")

    def test_lookup_without_a_value_or_with_a_bad_one_is_invalid_request(self):
        self.service.lookup.side_effect = IllegalStateException("invalid_request")

        missing = self.client.get(
            f"/v1/datasets/{self.dataset_id}/share/lookup", headers=self.headers
        )
        bad = self.client.get(
            f"/v1/datasets/{self.dataset_id}/share/lookup?value=nope",
            headers=self.headers,
        )

        for response in (missing, bad):
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), {"detail": "invalid_request"})

    def test_invite_answers_201_with_the_invitation_unwrapped(self):
        invitee = uuid4()
        self.service.invite.return_value = DatasetTenancyInvitationView(
            id=uuid4(),
            user=UserBrief(id=invitee, name="Bruna", email="b@usp.br"),
            invited_by=UserBrief(id=CALLER, name="Alan", email=None),
            created_at=AT,
            can_withdraw=True,
        )

        response = self.client.post(
            f"/v1/datasets/{self.dataset_id}/tenancy-invitations",
            json={"user_id": str(invitee)},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user"]["id"], str(invitee))
        self.assertTrue(response.json()["can_withdraw"])
        self.service.invite.assert_called_once_with(self.dataset_id, CALLER, invitee)

    def test_invite_keeps_the_conflict_code(self):
        self.service.invite.side_effect = ConflictException("invitation_pending")

        response = self.client.post(
            f"/v1/datasets/{self.dataset_id}/tenancy-invitations",
            json={"user_id": str(uuid4())},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "invitation_pending"})

    def test_withdraw(self):
        invitation_id = uuid4()

        response = self.client.delete(
            f"/v1/datasets/{self.dataset_id}/tenancy-invitations/{invitation_id}",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 204)
        self.service.withdraw.assert_called_once_with(
            self.dataset_id, CALLER, invitation_id
        )
