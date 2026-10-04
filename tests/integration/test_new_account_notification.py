import pytest

from tests.integration.fixtures.account import (
    ADMIN_ADDRESS,
    confirm_email_verification,
    create_plain_user,
    newest_code,
    outbox,
    password_account,
    request_email_verification,
    unique_email,
)
from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.sharing import random_orcid
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.mailpit import Mailpit


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


def _notifications(http_client, user_id: str) -> list[dict]:
    return outbox(http_client, related_id=user_id, template="new_account_pending")[
        "items"
    ]


def _body(http_client, email_id: str) -> str:
    response = http_client.get(
        f"/admin/emails/{email_id}", headers=AuthFixture.valid_headers()
    )
    assert_status_code(response, 200)
    return response.json()["body_text"]


class TestNewAccountNotification:
    def test_an_account_created_through_the_api_is_announced(self, http_client):
        email = unique_email()
        user_id = create_plain_user(http_client, email)

        items = _notifications(http_client, user_id)

        assert [item["recipient"] for item in items] == [ADMIN_ADDRESS]
        assert items[0]["subject"] == "New DataMap account: Ana Souza"
        body = _body(http_client, items[0]["id"])
        assert email in body
        assert "Created through the API" in body

    def test_a_password_sign_up_is_announced(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        items = _notifications(http_client, account["id"])

        assert [item["recipient"] for item in items] == [ADMIN_ADDRESS]
        body = _body(http_client, items[0]["id"])
        assert account["email"] in body
        assert "Email and password" in body

    def test_an_orcid_sign_up_is_announced(self, http_client, mailpit):
        orcid, email = random_orcid(), unique_email()
        started = request_email_verification(http_client, orcid, email)
        code = newest_code(http_client, mailpit, email)
        confirmed = confirm_email_verification(
            http_client, started.json()["challenge_id"], code
        )
        assert_status_code(confirmed, 200)

        items = _notifications(http_client, confirmed.json()["user_id"])

        assert [item["recipient"] for item in items] == [ADMIN_ADDRESS]
        assert "ORCID" in _body(http_client, items[0]["id"])

    def test_a_password_set_on_an_existing_account_announces_nothing_new(
        self, http_client, mailpit
    ):
        email = unique_email()
        user_id = create_plain_user(http_client, email)

        account = password_account(http_client, mailpit, email=email)

        assert account["id"] == user_id
        assert len(_notifications(http_client, user_id)) == 1
