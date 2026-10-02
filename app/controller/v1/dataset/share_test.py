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
from app.exception.not_found import NotFoundException
from app.model.sharing import (
    AnonymousLinkView,
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


class TestRevocations(SharingRoutesTestCase):
    def test_revoking_a_permission_answers_204(self):
        target = uuid4()

        response = self.client.delete(
            f"/v1/datasets/{self.dataset_id}/share/permissions/{target}",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 204)
        self.share.revoke_permission.assert_called_once_with(
            self.dataset_id, self.user_id, target
        )

    def test_revoking_an_invitation_answers_204(self):
        invitation_id = uuid4()

        response = self.client.delete(
            f"/v1/datasets/{self.dataset_id}/share/invitations/{invitation_id}",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 204)
        self.share.revoke_invitation.assert_called_once_with(
            self.dataset_id, self.user_id, invitation_id
        )

    def test_revoking_an_anonymous_link_answers_204(self):
        link_id = uuid4()

        response = self.client.delete(
            f"/v1/datasets/{self.dataset_id}/anonymous-links/{link_id}",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 204)
        self.links.revoke.assert_called_once_with(
            self.dataset_id, self.user_id, link_id
        )


class TestAnonymousLinks(SharingRoutesTestCase):
    def test_a_link_is_created_with_its_stripped_label(self):
        self.links.create.return_value = (
            AnonymousLinkView(id=uuid4(), label="JGR round 1", created_at=NOW),
            "https://datamap.pcs.usp.br/anonymous/t",
        )

        response = self.client.post(
            f"/v1/datasets/{self.dataset_id}/anonymous-links",
            json={"label": "  JGR round 1 "},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["link"], "https://datamap.pcs.usp.br/anonymous/t"
        )
        self.links.create.assert_called_once_with(
            self.dataset_id, self.user_id, "JGR round 1"
        )

    def test_a_blank_label_is_rejected(self):
        response = self.client.post(
            f"/v1/datasets/{self.dataset_id}/anonymous-links",
            json={"label": "   "},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 422)
        self.links.create.assert_not_called()

    def test_an_unknown_token_is_404_without_echoing_it(self):
        self.links.view.side_effect = NotFoundException("anonymous_link_not_found")

        response = self.client.get("/v1/anonymous/unknown-s3cr3t-token")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "anonymous_link_not_found"})
        self.assertNotIn("unknown-s3cr3t-token", response.text)


class TestInvitations(SharingRoutesTestCase):
    def test_accepting_an_accepted_invitation_is_409(self):
        self.share.accept.side_effect = ConflictException("invitation_already_accepted")

        response = self.client.post(
            "/v1/invitations/accept", json={"token": "t"}, headers=self.headers
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "invitation_already_accepted"})
        self.share.accept.assert_called_once_with("t", self.user_id)
