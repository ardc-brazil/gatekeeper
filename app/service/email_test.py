import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import UUID, uuid4

from prometheus_client import REGISTRY

from app.gateway.email.smtp import SmtpSender
from app.model.db.email import EmailMessage
from app.model.email import EmailEventType, EmailRecord, EmailStatus
from app.repository.email import EmailRepository
from app.service.email import EmailService
from app.service.email_masking import MASK
from app.service.email_template import EmailTemplateRenderer

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

CODE = "c0ffee12"
TEST_CONTEXT = {
    "title": "DataMap test message",
    "preheader": "A test message from DataMap.",
    "message": f"If this reached your inbox, the platform can send email. Verification code: {CODE}",
    "cta_label": "Open DataMap",
    "cta_url": "https://datamap.example",
    "reason": "You received this email because a DataMap administrator sent a test message to this address.",
    "code": CODE,
}


def _sample(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def _record(**overrides) -> EmailRecord:
    values = dict(
        id=uuid4(),
        template="notification",
        template_version="abc1234",
        recipient="someone@example.com",
        subject="DataMap test message",
        body_text="Verification code: c0ffee12",
        context=dict(TEST_CONTEXT),
        secret_fields=["code"],
        related_type=None,
        related_id=None,
        triggered_by=None,
        dedup_key=None,
        status=EmailStatus.SENDING,
        attempts=0,
        next_attempt_at=NOW,
        smtp_message_id=None,
        sent_at=None,
        created_at=NOW,
    )
    values.update(overrides)
    return EmailRecord(**values)


class EmailServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.repository = Mock(spec=EmailRepository)
        self.sender = Mock(spec=SmtpSender)
        self.renderer = EmailTemplateRenderer(site_url="https://datamap.example")
        self.service = self.build(enabled=True)

    def build(self, enabled: bool) -> EmailService:
        return EmailService(
            repository=self.repository,
            renderer=self.renderer,
            sender=self.sender,
            enabled=enabled,
            from_name="DataMap",
            from_address="datamap.pcs@gmail.com",
            reply_to=None,
            template_version="abc1234",
            clock=lambda: NOW,
        )

    def stored(self) -> tuple[EmailMessage, EmailEventType, str | None]:
        args, kwargs = self.repository.add.call_args
        message = kwargs.get("message", args[0] if args else None)
        event = kwargs.get("event", args[1] if len(args) > 1 else None)
        detail = kwargs.get("detail", args[2] if len(args) > 2 else None)
        return message, event, detail


class TestEnqueue(EmailServiceTestCase):
    def test_a_message_is_rendered_and_stored_pending_with_a_queued_event(self):
        self.repository.add.side_effect = lambda message, event, detail=None: _record(
            id=message.id, status=EmailStatus.PENDING
        )
        related = uuid4()

        message_id = self.service.enqueue(
            template="notification",
            recipient="someone@example.com",
            context=TEST_CONTEXT,
            secret_fields=frozenset({"code"}),
            related_type="dataset",
            related_id=related,
            dedup_key="test:1",
        )

        message, event, _ = self.stored()
        self.assertIsInstance(message_id, UUID)
        self.assertEqual(message.id, message_id)
        self.assertEqual(message.status, EmailStatus.PENDING.value)
        self.assertEqual(event, EmailEventType.QUEUED)
        self.assertEqual(message.subject, "DataMap test message")
        self.assertIn("c0ffee12", message.body_text)
        self.assertEqual(message.context, TEST_CONTEXT)
        self.assertEqual(message.secret_fields, ["code"])
        self.assertEqual(message.template_version, "abc1234")
        self.assertEqual(
            (message.related_type, message.related_id), ("dataset", related)
        )
        self.assertEqual(message.dedup_key, "test:1")

    def test_a_duplicate_dedup_key_returns_none(self):
        self.repository.add.return_value = None

        self.assertIsNone(
            self.service.enqueue(
                template="notification",
                recipient="someone@example.com",
                context=TEST_CONTEXT,
                dedup_key="test:1",
            )
        )

    def test_a_placeholder_address_is_recorded_as_skipped_and_masked(self):
        self.repository.add.side_effect = lambda message, event, detail=None: _record(
            id=message.id, status=EmailStatus.SKIPPED
        )
        before = _sample(
            "datamap_emails_total", template="notification", outcome="skipped"
        )

        self.service.enqueue(
            template="notification",
            recipient="0000-0002-1825-0097@fake.mail.com",
            context=TEST_CONTEXT,
            secret_fields=frozenset({"code"}),
        )

        message, event, detail = self.stored()
        self.assertEqual(message.status, EmailStatus.SKIPPED.value)
        self.assertEqual(event, EmailEventType.SKIPPED)
        self.assertEqual(detail, "placeholder address")
        self.assertEqual(message.context["code"], MASK)
        self.assertNotIn(CODE, str(message.context))
        self.assertNotIn(CODE, message.body_text)
        self.assertEqual(
            _sample("datamap_emails_total", template="notification", outcome="skipped"),
            before + 1,
        )
        self.sender.send.assert_not_called()

    def test_a_template_that_cannot_render_fails_where_it_was_asked_for(self):
        with self.assertRaises(Exception):  # noqa: B017 - render() can raise any jinja2 error
            self.service.enqueue(
                template="notification", recipient="a@example.com", context={}
            )

        self.repository.add.assert_not_called()
