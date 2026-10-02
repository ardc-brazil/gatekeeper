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
from app.model.sharing import (
    GrantResult,
    InvitationView,
    PermissionView,
    ShareUser,
)
from app.service.anonymous_link import AnonymousLinkService
from app.service.share import ShareService

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class SharingRoutesTestCase(unittest.TestCase):
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
        self.share = Mock(spec=ShareService)
        self.links = Mock(spec=AnonymousLinkService)
        self.container.share_service.override(providers.Object(self.share))
        self.container.anonymous_link_service.override(providers.Object(self.links))
        self.user_id = uuid4()
        self.dataset_id = uuid4()
        self.headers = {"X-User-Id": str(self.user_id)}

    def tearDown(self):
        self.container.share_service.reset_override()
        self.container.anonymous_link_service.reset_override()


class TestGrant(SharingRoutesTestCase):
    def test_a_new_email_invitation_keeps_its_nulls_and_has_no_permission(self):
        self.share.grant.return_value = GrantResult(
            kind="invitation",
            invitation=InvitationView(
                id=uuid4(),
                email="dora@ufam.edu.br",
                orcid=None,
                level="read",
                created_at=NOW,
            ),
            link="https://datamap.pcs.usp.br/invitations/t",
        )

        response = self.client.post(
            f"/v1/datasets/{self.dataset_id}/share",
            json={"level": "read", "email": "dora@ufam.edu.br"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["kind"], "invitation")
        self.assertEqual(body["link"], "https://datamap.pcs.usp.br/invitations/t")
        self.assertIsNone(body["invitation"]["orcid"])
        self.assertIn("orcid", body["invitation"])
        self.assertIsNone(body["invitation"]["accepted_at"])
        self.assertIn("accepted_at", body["invitation"])
        self.assertIn("revoked_at", body["invitation"])
        self.assertNotIn("permission", body)

    def test_a_direct_permission_keeps_its_nulls_and_has_no_invitation_or_link(self):
        self.share.grant.return_value = GrantResult(
            kind="permission",
            permission=PermissionView(
                user=ShareUser(id=uuid4(), name="Dora", email=None),
                level="read",
                granted_at=NOW,
            ),
        )

        response = self.client.post(
            f"/v1/datasets/{self.dataset_id}/share",
            json={"level": "read", "user_id": str(uuid4())},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(set(body), {"kind", "permission"})
        self.assertIsNone(body["permission"]["granted_by"])
        self.assertIn("granted_by", body["permission"])
        self.assertIsNone(body["permission"]["user"]["email"])
        self.assertIn("email", body["permission"]["user"])
