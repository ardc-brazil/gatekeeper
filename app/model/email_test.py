import unittest

from app.model.db.email import EmailEvent, EmailMessage
from app.model.email import DispatchResult, EmailEventType, EmailStatus


class TestEmailModel(unittest.TestCase):
    def test_status_and_event_values_are_the_ones_stored(self):
        self.assertEqual(
            [status.value for status in EmailStatus],
            ["pending", "sending", "sent", "failed", "skipped"],
        )
        self.assertEqual(
            [event.value for event in EmailEventType],
            ["queued", "attempt_failed", "sent", "failed", "skipped"],
        )

    def test_the_tables_carry_what_the_audit_needs(self):
        columns = set(EmailMessage.__table__.columns.keys())

        self.assertTrue(
            {
                "template", "template_version", "recipient", "subject", "body_text",
                "context", "secret_fields", "related_type", "related_id",
                "triggered_by", "dedup_key", "status", "attempts", "next_attempt_at",
                "claimed_at", "smtp_message_id", "sent_at", "created_at",
            }.issubset(columns)
        )  # fmt: skip
        self.assertTrue(EmailMessage.__table__.columns["dedup_key"].unique)
        self.assertEqual(
            set(EmailEvent.__table__.columns.keys()),
            {"id", "message_id", "event", "detail", "occurred_at"},
        )

    def test_a_dispatch_result_starts_at_zero(self):
        self.assertEqual(DispatchResult(), DispatchResult(0, 0, 0, 0, 0))
