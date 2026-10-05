import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.model.tenancy import summary_of
from app.service.email import EmailService
from app.service.tenancy_notifier import TenancyNotifier, admin_addresses

BASE = "https://datamap.pcs.usp.br/"
AT = datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc)
ATTO = summary_of("datamap/production/atto", "ATTO")


def person(name="Bruna Costa", email="bruna@usp.br", verified=True):
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        email=email,
        email_verified_at=AT if verified else None,
    )


class TestAdminAddresses(unittest.TestCase):
    def test_a_comma_separated_list_is_split_and_trimmed(self):
        self.assertEqual(
            admin_addresses(" a@usp.br , b@usp.br,, "), ["a@usp.br", "b@usp.br"]
        )

    def test_an_empty_value_is_nobody(self):
        self.assertEqual(admin_addresses(""), [])


class TestTenancyNotifier(unittest.TestCase):
    def setUp(self):
        self.email = Mock(spec=EmailService)
        self.notifier = TenancyNotifier(
            email_service=self.email,
            admin_emails="admin.one@usp.br, admin.two@usp.br",
            public_base_url=BASE,
        )

    def sent(self) -> list[dict]:
        return [c.kwargs for c in self.email.enqueue.call_args_list]

    def test_every_admin_hears_about_a_request_with_a_key_of_their_own(self):
        requester = person()
        request = SimpleNamespace(
            id=uuid4(), requested_name="ATTO", reason="Fluxes", created_at=AT
        )

        self.notifier.request_received(request, requester)

        sent = self.sent()
        self.assertEqual(
            [s["recipient"] for s in sent], ["admin.one@usp.br", "admin.two@usp.br"]
        )
        self.assertEqual({s["template"] for s in sent}, {"tenancy_request_received"})
        self.assertEqual(
            sent[0]["context"],
            {
                "requester_name": "Bruna Costa",
                "requester_email": "bruna@usp.br",
                "email_confirmed": True,
                "requested_name": "ATTO",
                "reason": "Fluxes",
                "requested_at": "October 5, 2026 at 09:30 UTC",
                "review_url": f"https://datamap.pcs.usp.br/app/admin/requests?request={request.id}",
            },
        )
        self.assertEqual(len({s["dedup_key"] for s in sent}), 2)
        self.assertTrue(
            sent[0]["dedup_key"].startswith(f"tenancy_request_received:{request.id}:")
        )
        self.assertEqual(sent[0]["related_type"], "tenancy_request")
        self.assertEqual(sent[0]["related_id"], request.id)

    def test_nobody_is_told_when_the_list_is_empty(self):
        notifier = TenancyNotifier(self.email, "", BASE)
        request = SimpleNamespace(
            id=uuid4(), requested_name="ATTO", reason="r", created_at=AT
        )

        notifier.request_received(request, person())
        notifier.invitation_notice(person(), "Alan", ATTO, uuid4())

        self.email.enqueue.assert_not_called()

    def test_access_granted_goes_to_the_user_keyed_by_the_event(self):
        user, event_id = person(), uuid4()

        self.notifier.access_granted(user, "Luciana Rizzo", ATTO, 12, event_id)

        (sent,) = self.sent()
        self.assertEqual(sent["recipient"], "bruna@usp.br")
        self.assertEqual(sent["template"], "tenancy_access_granted")
        self.assertEqual(sent["dedup_key"], f"tenancy_access_granted:{event_id}")
        self.assertEqual(
            sent["context"],
            {
                "user_name": "Bruna Costa",
                "admin_name": "Luciana Rizzo",
                "tenancy_display_name": "ATTO",
                "tenancy_path": "datamap/production/atto",
                "datasets_count": 12,
                "open_url": "https://datamap.pcs.usp.br/app/tenancy",
            },
        )

    def test_a_decline_carries_the_message_or_null(self):
        user = person()
        request = SimpleNamespace(
            id=uuid4(), requested_name="ATTO", decision_message=None
        )

        self.notifier.request_declined(user, request)

        (sent,) = self.sent()
        self.assertEqual(sent["template"], "tenancy_request_declined")
        self.assertIsNone(sent["context"]["decision_message"])
        self.assertEqual(sent["dedup_key"], f"tenancy_request_declined:{request.id}")

    def test_the_invitee_and_every_admin_hear_about_an_invitation(self):
        invitee, invitation_id = person(), uuid4()

        self.notifier.invitation(invitee, "Alan Calheiros", ATTO, invitation_id)
        self.notifier.invitation_notice(invitee, "Alan Calheiros", ATTO, invitation_id)

        sent = self.sent()
        self.assertEqual(
            [s["template"] for s in sent],
            [
                "tenancy_invitation",
                "tenancy_invitation_notice",
                "tenancy_invitation_notice",
            ],
        )
        self.assertEqual(sent[0]["dedup_key"], f"tenancy_invitation:{invitation_id}")
        self.assertEqual(
            sent[0]["context"]["open_url"], "https://datamap.pcs.usp.br/app/home"
        )
        self.assertEqual(
            sent[1]["context"]["tenancy_url"],
            "https://datamap.pcs.usp.br/app/admin/tenancies?tenancy=datamap/production/atto",
        )
        self.assertEqual(sent[1]["context"]["invitee_email"], "bruna@usp.br")

    def test_a_user_without_an_email_is_skipped(self):
        self.notifier.access_granted(person(email=None), "Luciana", ATTO, 1, uuid4())
        self.notifier.invitation(person(email=None), "Alan", ATTO, uuid4())

        self.email.enqueue.assert_not_called()

    def test_no_message_carries_a_secret(self):
        self.notifier.access_granted(person(), "Luciana", ATTO, 1, uuid4())

        self.assertNotIn("secret_fields", self.sent()[0])

    def test_a_failure_to_queue_is_logged_not_raised(self):
        self.email.enqueue.side_effect = RuntimeError("database gone")

        with self.assertLogs("service:TenancyNotifier", level="ERROR"):
            self.notifier.access_granted(person(), "Luciana", ATTO, 1, uuid4())
