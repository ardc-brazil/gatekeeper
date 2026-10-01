import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import UUID, uuid4

from prometheus_client import REGISTRY

from app.exception.not_found import NotFoundException
from app.gateway.email.smtp import (
    DefiniteSendFailure,
    SmtpSender,
    UncertainSendFailure,
)
from app.model.db.email import EmailMessage
from app.model.email import EmailEventType, EmailRecord, EmailStatus
from app.repository.email import EmailRepository
from app.service.email import MAX_ATTEMPTS, RETRY_DELAYS, EmailService
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


class TestDispatch(EmailServiceTestCase):
    def setUp(self):
        super().setUp()
        self.repository.claim_stale_sending.return_value = []
        self.repository.count_pending.return_value = 0

    def test_a_due_message_is_sent_once_and_its_secret_masked_afterwards(self):
        record = _record()
        self.repository.claim_due.return_value = [record]

        result = self.service.dispatch_due()

        self.assertEqual(result.sent, 1)
        sent = self.sender.send.call_args.args[0]
        self.assertEqual(sent["To"], "someone@example.com")
        self.assertEqual(sent["From"], "DataMap <datamap.pcs@gmail.com>")
        self.assertEqual(sent["Subject"], "DataMap test message")
        self.assertTrue(sent["Message-ID"].endswith("@gmail.com>"))
        self.assertIn("c0ffee12", sent.get_body(("plain",)).get_content())
        self.assertIn("c0ffee12", sent.get_body(("html",)).get_content())

        kwargs = self.repository.mark_sent.call_args.kwargs
        self.assertEqual(kwargs["message_id"], record.id)
        self.assertEqual(kwargs["smtp_message_id"], sent["Message-ID"])
        self.assertEqual(kwargs["sent_at"], NOW)
        self.assertEqual(kwargs["context"]["code"], MASK)
        self.assertNotIn(CODE, str(kwargs["context"]))
        self.assertNotIn(CODE, kwargs["body_text"])

    def test_a_definite_refusal_is_retried_later(self):
        self.repository.claim_due.return_value = [_record(attempts=0)]
        self.sender.send.side_effect = DefiniteSendFailure("connect: refused")

        result = self.service.dispatch_due()

        self.assertEqual(result.retried, 1)
        kwargs = self.repository.mark_retry.call_args.kwargs
        self.assertEqual(kwargs["attempts"], 1)
        self.assertEqual(kwargs["next_attempt_at"], NOW + RETRY_DELAYS[0])
        self.assertIn("connect: refused", kwargs["detail"])
        self.repository.mark_failed.assert_not_called()

    def test_the_fifth_definite_refusal_is_final(self):
        self.repository.claim_due.return_value = [_record(attempts=MAX_ATTEMPTS - 1)]
        self.sender.send.side_effect = DefiniteSendFailure("refused: 550")

        result = self.service.dispatch_due()

        self.assertEqual(result.failed, 1)
        kwargs = self.repository.mark_failed.call_args.kwargs
        self.assertEqual(kwargs["attempts"], MAX_ATTEMPTS)
        self.assertEqual(kwargs["context"]["code"], MASK)
        self.repository.mark_retry.assert_not_called()

    def test_an_uncertain_outcome_is_never_retried(self):
        self.repository.claim_due.return_value = [_record(attempts=0)]
        self.sender.send.side_effect = UncertainSendFailure("during send: timed out")

        result = self.service.dispatch_due()

        self.assertEqual(result.failed, 1)
        kwargs = self.repository.mark_failed.call_args.kwargs
        self.assertTrue(kwargs["detail"].startswith("delivery uncertain"))
        self.assertEqual(kwargs["attempts"], 1)
        self.repository.mark_retry.assert_not_called()

    def test_a_message_left_in_sending_becomes_failed_not_sent_again(self):
        self.repository.claim_stale_sending.return_value = [_record()]
        self.repository.claim_due.return_value = []

        result = self.service.dispatch_due()

        self.repository.claim_stale_sending.assert_called_once_with(
            NOW - timedelta(minutes=10)
        )
        self.assertEqual(result.failed, 1)
        self.assertTrue(
            self.repository.mark_failed.call_args.kwargs["detail"].startswith(
                "delivery uncertain"
            )
        )
        self.sender.send.assert_not_called()

    def test_with_sending_off_nothing_is_claimed(self):
        self.service = self.build(enabled=False)
        self.repository.count_pending.return_value = 4

        result = self.service.dispatch_due()

        self.repository.claim_due.assert_not_called()
        self.sender.send.assert_not_called()
        self.assertEqual(result.sent, 0)
        self.assertEqual(_sample("datamap_email_pending"), 4.0)

    def test_outcomes_are_counted(self):
        before = _sample(
            "datamap_emails_total", template="notification", outcome="sent"
        )
        self.repository.claim_due.return_value = [_record(), _record()]

        self.service.dispatch_due()

        self.assertEqual(
            _sample("datamap_emails_total", template="notification", outcome="sent"),
            before + 2,
        )

    def test_a_template_that_no_longer_renders_fails_without_sending(self):
        self.repository.claim_due.return_value = [_record(context={})]

        result = self.service.dispatch_due()

        self.assertEqual(result.failed, 1)
        self.sender.send.assert_not_called()

    def test_reply_to_is_set_when_configured(self):
        service = EmailService(
            repository=self.repository,
            renderer=self.renderer,
            sender=self.sender,
            enabled=True,
            from_name="DataMap",
            from_address="datamap.pcs@gmail.com",
            reply_to="caio.maia@usp.br",
            template_version="abc1234",
            clock=lambda: NOW,
        )
        self.repository.claim_due.return_value = [_record()]

        service.dispatch_due()

        self.assertEqual(
            self.sender.send.call_args.args[0]["Reply-To"], "caio.maia@usp.br"
        )

    def test_a_record_that_raises_outside_the_gateways_does_not_abort_the_rest(self):
        first, second = _record(), _record()
        self.repository.claim_due.return_value = [first, second]
        self.repository.mark_sent.side_effect = [RuntimeError("db gone"), None]

        with self.assertLogs("service:EmailService", level="ERROR") as logs:
            result = self.service.dispatch_due()

        self.assertEqual(result.sent, 1)
        self.assertEqual(self.sender.send.call_count, 2)
        self.repository.mark_retry.assert_not_called()
        self.repository.mark_failed.assert_not_called()
        self.assertEqual(len(logs.records), 1)
        record = logs.records[0]
        self.assertEqual(record.email_id, str(first.id))
        self.assertNotIn("recipient", vars(record))
        self.assertNotIn("subject", vars(record))
        self.assertNotIn(first.recipient, logs.output[0])
        self.assertNotIn(first.subject, logs.output[0])

    def test_the_pending_gauge_is_set_even_when_a_record_raises(self):
        self.repository.claim_due.return_value = [_record()]
        self.repository.mark_sent.side_effect = RuntimeError("db gone")
        self.repository.count_pending.return_value = 7

        with self.assertLogs("service:EmailService", level="ERROR"):
            self.service.dispatch_due()

        self.assertEqual(_sample("datamap_email_pending"), 7.0)


class TestReading(EmailServiceTestCase):
    def test_an_unknown_message_is_not_found(self):
        self.repository.fetch.return_value = None

        with self.assertRaises(NotFoundException):
            self.service.fetch(uuid4())

    def test_the_test_message_carries_a_masked_code(self):
        self.repository.add.side_effect = lambda message, event, detail=None: _record(
            id=message.id, status=EmailStatus.PENDING
        )
        admin = uuid4()

        self.service.send_test_message("ops@example.com", triggered_by=admin)

        message, _, _ = self.stored()
        self.assertEqual(message.template, "notification")
        self.assertEqual(message.secret_fields, ["code"])
        self.assertEqual(len(message.context["code"]), 8)
        self.assertIn(message.context["code"], message.context["message"])
        self.assertEqual(message.subject, "DataMap test message")
        self.assertEqual(message.triggered_by, admin)
