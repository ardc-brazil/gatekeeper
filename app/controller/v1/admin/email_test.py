import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app import setup
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.v1.admin import email as email_routes
from app.model.email import EmailRecord, EmailStatus
from app.service.email import EmailService
from app.service.email_masking import MASK


class TestEmailRoutes(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        setup.setup_routes(app)
        self.routes = {
            (route.path, method): route
            for route in app.routes
            if isinstance(route, APIRoute)
            for method in route.methods
        }

    def guards(self, path: str, method: str) -> set:
        return {
            dependency.call
            for dependency in self.routes[(path, method)].dependant.dependencies
        }

    def test_the_archivist_dispatch_route_takes_client_credentials_only(self):
        guards = self.guards("/v1/internal/notifications/dispatch", "POST")

        self.assertIn(authenticate, guards)
        self.assertNotIn(authorize, guards)

    def test_the_email_record_is_behind_casbin(self):
        for key in [
            ("/v1/admin/emails/", "GET"),
            ("/v1/admin/emails/{email_id}", "GET"),
            ("/v1/admin/emails/test", "POST"),
        ]:
            self.assertTrue({authenticate, authorize} <= self.guards(*key), key)


class TestEmailDetail(unittest.TestCase):
    def test_a_pending_message_does_not_show_its_secret(self):
        now = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
        record = EmailRecord(
            id=uuid4(),
            template="notification",
            template_version="abc1234",
            recipient="someone@example.com",
            subject="DataMap test message",
            body_text="Verification code: c0ffee12",
            context={"message": "Verification code: c0ffee12", "code": "c0ffee12"},
            secret_fields=["code"],
            related_type=None,
            related_id=None,
            triggered_by=None,
            dedup_key=None,
            status=EmailStatus.PENDING,
            attempts=0,
            next_attempt_at=now,
            smtp_message_id=None,
            sent_at=None,
            created_at=now,
        )
        service = Mock(spec=EmailService)
        service.fetch.return_value = (record, [])

        response = email_routes.fetch(email_id=record.id, service=service)

        self.assertEqual(response.context["code"], MASK)
        self.assertNotIn("c0ffee12", str(response.context))
        self.assertNotIn("c0ffee12", response.body_text)
