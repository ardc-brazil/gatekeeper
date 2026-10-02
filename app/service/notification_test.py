import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.model.dataset_access import AccessEventType
from app.repository.dataset_anonymous_link import DatasetAnonymousLinkRepository
from app.repository.embargo_notification import EmbargoNotificationRepository
from app.repository.permission import PermissionRepository
from app.repository.user import UserRepository
from app.service.email import EmailService
from app.service.email_template import EmailTemplate, EmailTemplateRenderer
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.notification import EmbargoNotificationService, due_offset

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
OFFSETS = (15, 10, 5, 1)


class TestDueOffset(unittest.TestCase):
    def test_nothing_is_due_before_fifteen_days(self):
        self.assertIsNone(
            due_offset(NOW + timedelta(days=16), NOW - timedelta(days=60), NOW, OFFSETS)
        )

    def test_the_nearest_passed_offset_is_due(self):
        self.assertEqual(
            due_offset(NOW + timedelta(days=4), NOW - timedelta(days=60), NOW, OFFSETS),
            5,
        )

    def test_an_offset_already_past_when_the_date_was_set_is_never_due(self):
        set_at = NOW - timedelta(hours=1)
        self.assertIsNone(due_offset(NOW + timedelta(days=3), set_at, NOW, (15, 10)))
        self.assertEqual(
            due_offset(
                NOW + timedelta(days=3), set_at - timedelta(days=3), NOW, OFFSETS
            ),
            5,
        )

    def test_an_unknown_set_time_allows_every_offset(self):
        self.assertEqual(due_offset(NOW + timedelta(hours=2), None, NOW, OFFSETS), 1)


class TestQueueDue(unittest.TestCase):
    def setUp(self):
        self.repository = Mock(spec=EmbargoNotificationRepository)
        self.permissions = Mock(spec=PermissionRepository)
        self.users = Mock(spec=UserRepository)
        self.links = Mock(spec=DatasetAnonymousLinkRepository)
        self.links.count_active.return_value = 2
        self.audit = Mock(spec=DatasetAccessAudit)
        self.email = Mock(spec=EmailService)
        self.email.enqueue.return_value = uuid4()
        self.owner = SimpleNamespace(
            id=uuid4(), name="Ana Lima", email="ana@usp.br", is_enabled=True
        )
        self.reader = SimpleNamespace(
            id=uuid4(), name="Bruno", email="bruno@inpa.gov.br", is_enabled=True
        )
        self.people = {self.owner.id: self.owner, self.reader.id: self.reader}
        self.users.fetch_by_id.side_effect = lambda id, is_enabled=True: (
            self.people.get(id)
            if self.people.get(id) and self.people[id].is_enabled == is_enabled
            else None
        )
        self.dataset = SimpleNamespace(
            id=uuid4(),
            name="Ozone",
            owner_id=self.owner.id,
            tenancy="datamap/production/data-amazon",
            embargo_until=NOW + timedelta(days=4, hours=6),
            versions=[],
        )
        self.permissions.list_for_dataset.return_value = [
            SimpleNamespace(user_id=self.reader.id, granted_by=self.owner.id)
        ]
        self.repository.datasets_with_reminders_due.return_value = [self.dataset]
        self.repository.datasets_expired_unannounced.return_value = []
        self.repository.embargo_set_at.return_value = NOW - timedelta(days=60)
        self.repository.ending_event.return_value = None
        self.service = EmbargoNotificationService(
            notification_repository=self.repository,
            permission_repository=self.permissions,
            user_repository=self.users,
            anonymous_link_repository=self.links,
            audit=self.audit,
            email_service=self.email,
            public_base_url="https://datamap.pcs.usp.br",
        )

    def ended(self, versions=()):
        return SimpleNamespace(
            id=uuid4(),
            name="Ozone",
            owner_id=self.owner.id,
            tenancy="datamap/production/data-amazon",
            embargo_until=NOW - timedelta(minutes=3),
            versions=list(versions),
        )

    def test_owner_and_permission_holders_each_get_the_reminder_once_keyed(self):
        queued = self.service.queue_due(NOW)

        self.assertEqual(queued, 2)
        calls = [call.kwargs for call in self.email.enqueue.call_args_list]
        self.assertEqual(
            {call["recipient"] for call in calls}, {"ana@usp.br", "bruno@inpa.gov.br"}
        )
        until = self.dataset.embargo_until.isoformat()
        self.assertEqual(
            {call["dedup_key"] for call in calls},
            {
                f"embargo_reminder:{self.dataset.id}:{until}:5:{self.owner.id}",
                f"embargo_reminder:{self.dataset.id}:{until}:5:{self.reader.id}",
            },
        )
        by_recipient = {call["recipient"]: call["context"] for call in calls}
        owner, reader = by_recipient["ana@usp.br"], by_recipient["bruno@inpa.gov.br"]
        self.assertTrue(owner["is_owner"])
        self.assertTrue(owner["can_extend"])
        self.assertFalse(reader["is_owner"])
        self.assertFalse(reader["can_extend"])
        self.assertEqual(owner["days_remaining"], 5)
        self.assertEqual(owner["later_offsets"], [1])
        self.assertTrue(owner["others_notified"])
        self.assertEqual(owner["people_with_access"], ["You", "Bruno"])
        self.assertEqual(owner["anonymous_link_count"], 2)
        self.assertEqual(owner["tenancy_name"], "Data Amazon")
        self.assertEqual(owner["embargo_until_date"], "October 5, 2026")
        self.assertEqual(owner["embargo_until_short"], "October 5")
        self.assertEqual(reader["owner_name"], "Ana Lima")
        self.assertEqual(reader["owner_email"], "ana@usp.br")
        self.assertEqual(reader["shared_by_name"], "Ana Lima")

    def test_when_the_owner_is_disabled_the_others_can_extend(self):
        self.owner.is_enabled = False

        self.service.queue_due(NOW)

        calls = [call.kwargs for call in self.email.enqueue.call_args_list]
        self.assertEqual([call["recipient"] for call in calls], ["bruno@inpa.gov.br"])
        context = calls[0]["context"]
        self.assertTrue(context["can_extend"])
        self.assertFalse(context["owner_active"])
        self.assertEqual(context["owner_name"], "Ana Lima")

    def test_a_person_without_an_email_is_left_out(self):
        self.reader.email = None
        self.assertEqual(self.service.queue_due(NOW), 1)

    def test_a_placeholder_address_is_passed_on_to_be_recorded_as_skipped(self):
        self.reader.email = "bruno@fake.mail.com"
        self.service.queue_due(NOW)
        recipients = [
            call.kwargs["recipient"] for call in self.email.enqueue.call_args_list
        ]
        self.assertIn("bruno@fake.mail.com", recipients)

    def test_an_already_queued_reminder_is_not_counted(self):
        self.email.enqueue.return_value = None
        self.assertEqual(self.service.queue_due(NOW), 0)

    def test_an_ended_embargo_is_announced_and_marked_expired(self):
        doi = SimpleNamespace(identifier="10.5281/datamap.3f9c1e", state="REGISTERED")
        ended = self.ended(
            versions=[SimpleNamespace(created_at=NOW - timedelta(days=60), doi=doi)]
        )
        self.repository.datasets_with_reminders_due.return_value = []
        self.repository.datasets_expired_unannounced.return_value = [ended]

        self.service.queue_due(NOW)

        calls = [call.kwargs for call in self.email.enqueue.call_args_list]
        self.assertEqual({call["template"] for call in calls}, {"embargo_ended"})
        self.assertEqual(
            {call["dedup_key"] for call in calls},
            {
                f"embargo_ended:{ended.id}:{ended.embargo_until.isoformat()}:{self.owner.id}",
                f"embargo_ended:{ended.id}:{ended.embargo_until.isoformat()}:{self.reader.id}",
            },
        )
        self.audit.record.assert_called_once()
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"], AccessEventType.EXPIRED
        )
        self.assertIsNone(self.audit.record.call_args.kwargs["changed_by"])
        owner = next(
            call["context"] for call in calls if call["recipient"] == "ana@usp.br"
        )
        self.assertFalse(owner["ended_early"])
        self.assertTrue(owner["is_owner"])
        self.assertEqual(owner["doi"], "10.5281/datamap.3f9c1e")
        self.assertTrue(owner["doi_registered"])
        self.assertEqual(owner["ended_on_date"], "October 1, 2026")

    def test_an_embargo_ended_by_a_manual_doi_says_so(self):
        ended = self.ended()
        self.repository.datasets_with_reminders_due.return_value = []
        self.repository.datasets_expired_unannounced.return_value = [ended]
        self.repository.ending_event.return_value = SimpleNamespace(
            event_type="ended_early", note="manual DOI"
        )

        self.service.queue_due(NOW)

        context = self.email.enqueue.call_args_list[0].kwargs["context"]
        self.assertTrue(context["ended_early"])
        self.assertTrue(context["ended_by_manual_doi"])

    def assert_every_queued_message_renders(self, expected: int):
        renderer = EmailTemplateRenderer(site_url="https://datamap.pcs.usp.br")
        calls = [call.kwargs for call in self.email.enqueue.call_args_list]
        self.assertEqual(len(calls), expected)
        for call in calls:
            rendered = renderer.render(EmailTemplate(call["template"]), call["context"])
            self.assertIn("Ozone", rendered.html)
            self.assertIn("Ozone", rendered.text)

    def test_every_reminder_variant_renders(self):
        self.service.queue_due(NOW)
        self.owner.is_enabled = False
        self.service.queue_due(NOW)

        self.assert_every_queued_message_renders(expected=3)

    def test_a_dataset_raising_in_the_reminder_pass_does_not_stop_the_next_one(self):
        other = SimpleNamespace(
            id=uuid4(),
            name="Rain",
            owner_id=self.owner.id,
            tenancy="datamap/production/data-amazon",
            embargo_until=NOW + timedelta(days=4, hours=6),
            versions=[],
        )
        self.repository.datasets_with_reminders_due.return_value = [
            self.dataset,
            other,
        ]
        self.repository.embargo_set_at.side_effect = [
            RuntimeError("boom"),
            NOW - timedelta(days=60),
        ]

        queued = self.service.queue_due(NOW)

        self.assertEqual(queued, 2)
        recipients = {
            call.kwargs["recipient"] for call in self.email.enqueue.call_args_list
        }
        self.assertEqual(recipients, {"ana@usp.br", "bruno@inpa.gov.br"})

    def test_a_dataset_raising_in_the_ended_pass_does_not_stop_the_next_one(self):
        failing = self.ended()
        ok = self.ended()
        self.repository.datasets_with_reminders_due.return_value = []
        self.repository.datasets_expired_unannounced.return_value = [failing, ok]
        self.repository.ending_event.side_effect = [RuntimeError("boom"), None]

        queued = self.service.queue_due(NOW)

        self.assertEqual(queued, 2)
        self.audit.record.assert_called_once()
        self.assertEqual(self.audit.record.call_args.kwargs["dataset_id"], ok.id)

    def test_a_late_reminder_reports_the_real_days_remaining_not_the_offset(self):
        self.dataset.embargo_until = NOW + timedelta(days=3)

        self.service.queue_due(NOW)

        context = next(
            call.kwargs["context"]
            for call in self.email.enqueue.call_args_list
            if call.kwargs["recipient"] == "ana@usp.br"
        )
        self.assertEqual(context["days_remaining"], 3)

    def test_the_last_reminder_never_says_zero_days(self):
        self.dataset.embargo_until = NOW + timedelta(hours=20)

        self.service.queue_due(NOW)

        context = next(
            call.kwargs["context"]
            for call in self.email.enqueue.call_args_list
            if call.kwargs["recipient"] == "ana@usp.br"
        )
        self.assertEqual(context["days_remaining"], 1)

    def test_an_enqueue_failure_for_one_recipient_still_queues_the_other(self):
        self.email.enqueue.side_effect = [RuntimeError("boom"), uuid4()]

        queued = self.service.queue_due(NOW)

        self.assertEqual(queued, 1)
        recipients = [
            call.kwargs["recipient"] for call in self.email.enqueue.call_args_list
        ]
        self.assertEqual(len(recipients), 2)

    def test_queued_messages_carry_the_dataset_as_related_and_no_secret_fields(self):
        doi = SimpleNamespace(identifier="10.5281/datamap.3f9c1e", state="REGISTERED")
        ended = self.ended(
            versions=[SimpleNamespace(created_at=NOW - timedelta(days=60), doi=doi)]
        )
        self.repository.datasets_expired_unannounced.return_value = [ended]

        self.service.queue_due(NOW)

        calls = [call.kwargs for call in self.email.enqueue.call_args_list]
        self.assertTrue(calls)
        for call in calls:
            self.assertEqual(call["related_type"], "dataset")
            self.assertNotIn("secret_fields", call)
        reminder_ids = {
            call["related_id"]
            for call in calls
            if call["template"] == "embargo_reminder"
        }
        ended_ids = {
            call["related_id"] for call in calls if call["template"] == "embargo_ended"
        }
        self.assertEqual(reminder_ids, {self.dataset.id})
        self.assertEqual(ended_ids, {ended.id})

    def test_every_end_variant_renders(self):
        doi = SimpleNamespace(identifier="10.5281/datamap.3f9c1e", state="REGISTERED")
        version = SimpleNamespace(created_at=NOW - timedelta(days=60), doi=doi)
        self.repository.datasets_with_reminders_due.return_value = []
        self.repository.datasets_expired_unannounced.return_value = [
            self.ended(versions=[version]),
            self.ended(),
        ]
        self.service.queue_due(NOW)
        self.repository.ending_event.return_value = SimpleNamespace(
            event_type="ended_early", note=None
        )
        self.service.queue_due(NOW)
        self.repository.datasets_expired_unannounced.return_value = [
            self.ended(versions=[version])
        ]
        self.repository.ending_event.return_value = SimpleNamespace(
            event_type="ended_early", note="manual DOI"
        )
        self.service.queue_due(NOW)

        self.assert_every_queued_message_renders(expected=10)
