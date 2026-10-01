import json
import uuid

import pytest

from tests.integration.test_metrics import _sample, _scrape
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.mailpit import Mailpit


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


@pytest.fixture
def client_headers(valid_headers):
    return {
        "X-Api-Key": valid_headers["X-Api-Key"],
        "X-Api-Secret": valid_headers["X-Api-Secret"],
        "Content-Type": "application/json",
    }


def _recipient() -> str:
    return f"email_test_{uuid.uuid4().hex[:12]}@example.com"


def _queue_test_message(http_client, headers, recipient: str) -> str:
    response = http_client.post(
        "/admin/emails/test", headers=headers, json={"recipient": recipient}
    )
    assert_status_code(response, 202)
    return response.json()["id"]


def _dispatch(http_client, client_headers) -> dict:
    response = http_client.post(
        "/internal/notifications/dispatch", headers=client_headers
    )
    assert_status_code(response, 200)
    return response.json()


class TestEmailDelivery:
    def test_a_queued_message_is_delivered_exactly_once(
        self, http_client, valid_headers, client_headers, mailpit
    ):
        recipient = _recipient()
        _queue_test_message(http_client, valid_headers, recipient)

        first = _dispatch(http_client, client_headers)
        delivered = mailpit.wait_for(recipient)
        _dispatch(http_client, client_headers)

        assert first["sent"] >= 1, first
        assert len(delivered) == 1, delivered
        assert len(mailpit.messages_to(recipient)) == 1
        assert delivered[0]["Subject"] == "DataMap test message"

    def test_the_record_keeps_what_was_sent_but_not_the_secret(
        self, http_client, valid_headers, client_headers, mailpit
    ):
        recipient = _recipient()
        email_id = _queue_test_message(http_client, valid_headers, recipient)

        _dispatch(http_client, client_headers)
        delivered = mailpit.wait_for(recipient)
        body = mailpit.message(delivered[0]["ID"])["Text"]
        record = http_client.get(f"/admin/emails/{email_id}", headers=valid_headers)

        assert_status_code(record, 200)
        detail = record.json()
        code = body.split("Verification code: ")[1].split()[0]
        assert detail["status"] == "sent"
        assert detail["recipient"] == recipient
        assert detail["context"]["code"] == "[masked]"
        assert code not in json.dumps(detail["context"])
        assert code not in detail["body_text"]
        assert "[masked]" in detail["body_text"]
        assert detail["smtp_message_id"].strip("<>") == delivered[0]["MessageID"]
        assert [event["event"] for event in detail["events"]] == ["queued", "sent"]

    def test_a_placeholder_address_is_recorded_and_never_sent(
        self, http_client, valid_headers, client_headers, mailpit
    ):
        recipient = f"orcid_{uuid.uuid4().hex[:12]}@fake.mail.com"
        email_id = _queue_test_message(http_client, valid_headers, recipient)

        _dispatch(http_client, client_headers)
        record = http_client.get(f"/admin/emails/{email_id}", headers=valid_headers)

        assert record.json()["status"] == "skipped"
        assert mailpit.messages_to(recipient) == []

    def test_the_record_can_be_searched_by_recipient(
        self, http_client, valid_headers, client_headers
    ):
        recipient = _recipient()
        email_id = _queue_test_message(http_client, valid_headers, recipient)

        response = http_client.get(
            "/admin/emails/",
            headers=valid_headers,
            params={"recipient": recipient.upper()},
        )

        assert_status_code(response, 200)
        assert [item["id"] for item in response.json()["items"]] == [email_id]

    def test_sending_is_counted(self, http_client, valid_headers, client_headers):
        _dispatch(http_client, client_headers)
        before = _sample(
            _scrape(), "datamap_emails_total", template="notification", outcome="sent"
        )
        _queue_test_message(http_client, valid_headers, _recipient())

        _dispatch(http_client, client_headers)

        after = _sample(
            _scrape(), "datamap_emails_total", template="notification", outcome="sent"
        )
        assert after == before + 1

    def test_the_dispatch_route_refuses_a_caller_without_client_credentials(
        self, http_client
    ):
        response = http_client.post(
            "/internal/notifications/dispatch",
            headers={"Content-Type": "application/json"},
        )

        assert_status_code(response, 401)
