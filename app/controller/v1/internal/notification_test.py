import unittest
from datetime import timezone
from unittest.mock import Mock

from app.controller.v1.internal.notification import dispatch
from app.model.email import DispatchResult
from app.service.email import EmailService
from app.service.notification import EmbargoNotificationService


class TestDispatch(unittest.TestCase):
    def test_embargo_messages_are_queued_before_sending_and_counted_as_queued(self):
        order = []
        notifications = Mock(spec=EmbargoNotificationService)
        notifications.queue_due.side_effect = lambda now: order.append("queue") or 3
        email_service = Mock(spec=EmailService)
        email_service.dispatch_due.side_effect = lambda: order.append(
            "send"
        ) or DispatchResult(queued=1, sent=4, failed=1, skipped=2, retried=1)

        response = dispatch(notifications=notifications, email_service=email_service)

        self.assertEqual(order, ["queue", "send"])
        self.assertEqual(notifications.queue_due.call_args.args[0].tzinfo, timezone.utc)
        self.assertEqual(
            response.model_dump(),
            {"queued": 4, "sent": 4, "failed": 1, "skipped": 2, "retried": 1},
        )

    def test_a_failing_queue_still_dispatches_and_reports_dispatch_counts_only(self):
        notifications = Mock(spec=EmbargoNotificationService)
        notifications.queue_due.side_effect = RuntimeError("boom")
        email_service = Mock(spec=EmailService)
        email_service.dispatch_due.return_value = DispatchResult(
            queued=1, sent=4, failed=1, skipped=2, retried=1
        )

        response = dispatch(notifications=notifications, email_service=email_service)

        email_service.dispatch_due.assert_called_once()
        self.assertEqual(
            response.model_dump(),
            {"queued": 1, "sent": 4, "failed": 1, "skipped": 2, "retried": 1},
        )
