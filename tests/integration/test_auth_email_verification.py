import pytest

from tests.integration.fixtures.account import (
    confirm_email_verification,
    create_plain_user,
    newest_code,
    newest_text,
    refused,
    request_email_verification,
    unique_email,
    user,
)
from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.embargo import client_headers
from tests.integration.fixtures.sharing import random_orcid
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.mailpit import Mailpit


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


def _orcid_account(http_client, orcid: str, email: str | None = None) -> str:
    return create_plain_user(
        http_client,
        email or f"{orcid.replace('-', '')}@fake.mail.com",
        providers=[{"name": "orcid", "reference": orcid}],
    )


def _confirmed(http_client, mailpit, orcid: str, email: str):
    started = request_email_verification(http_client, orcid, email)
    assert_status_code(started, 202)
    code = newest_code(http_client, mailpit, email)
    return confirm_email_verification(http_client, started.json()["challenge_id"], code)


def _disable(http_client, user_id: str) -> None:
    response = http_client.delete(
        f"/users/{user_id}", headers=AuthFixture.valid_headers()
    )
    assert_status_code(response, 200)


def _users_with_email(http_client, email: str, is_enabled: bool) -> list[dict]:
    response = http_client.get(
        "/users/",
        params={"email": email, "is_enabled": is_enabled},
        headers=AuthFixture.valid_headers(),
    )
    assert_status_code(response, 200)
    return response.json()


class TestEmailVerificationTable:
    def test_an_orcid_account_without_this_email_takes_it_confirmed(
        self, http_client, mailpit
    ):
        orcid = random_orcid()
        user_id = _orcid_account(http_client, orcid)
        email = unique_email()

        confirmed = _confirmed(http_client, mailpit, orcid, email)

        assert_status_code(confirmed, 200)
        assert confirmed.json() == {"user_id": user_id}
        profile = user(http_client, user_id)
        assert profile["email"] == email
        assert profile["email_verified_at"] is not None

    def test_an_orcid_account_that_already_has_this_email_is_confirmed(
        self, http_client, mailpit
    ):
        orcid, email = random_orcid(), unique_email()
        user_id = _orcid_account(http_client, orcid, email)

        confirmed = _confirmed(http_client, mailpit, orcid, email)

        assert_status_code(confirmed, 200)
        assert confirmed.json() == {"user_id": user_id}
        assert user(http_client, user_id)["email_verified_at"] is not None

    def test_an_orcid_account_and_another_account_with_the_email_conflict(
        self, http_client, mailpit
    ):
        orcid, email = random_orcid(), unique_email()
        orcid_user = _orcid_account(http_client, orcid)
        other = create_plain_user(http_client, email)

        refused(
            _confirmed(http_client, mailpit, orcid, email),
            409,
            "email_belongs_to_another_account",
        )
        assert user(http_client, other)["email_verified_at"] is None
        assert user(http_client, orcid_user)["email_verified_at"] is None

    def test_an_email_account_gets_the_orcid_attached(self, http_client, mailpit):
        orcid, email = random_orcid(), unique_email()
        user_id = create_plain_user(http_client, email)

        confirmed = _confirmed(http_client, mailpit, orcid, email)

        assert_status_code(confirmed, 200)
        assert confirmed.json() == {"user_id": user_id}
        by_provider = http_client.get(
            f"/users/providers/orcid/{orcid}", headers=client_headers()
        )
        assert_status_code(by_provider, 200)
        assert by_provider.json()["id"] == user_id
        assert by_provider.json()["email_verified_at"] is not None
        assert by_provider.json()["has_password"] is False

    def test_neither_creates_a_confirmed_account_with_the_orcid(
        self, http_client, mailpit
    ):
        orcid, email = random_orcid(), unique_email()

        confirmed = _confirmed(http_client, mailpit, orcid, email)

        assert_status_code(confirmed, 200)
        profile = user(http_client, confirmed.json()["user_id"])
        assert profile["email"] == email
        assert profile["email_verified_at"] is not None
        assert profile["has_password"] is False
        assert profile["providers"] == [{"name": "orcid", "reference": orcid}]


class TestDisabledOrcidHolders:
    def test_a_disabled_orcid_account_and_a_new_email_conflict_without_a_new_user(
        self, http_client, mailpit
    ):
        orcid, email = random_orcid(), unique_email()
        _disable(http_client, _orcid_account(http_client, orcid))

        refused(
            _confirmed(http_client, mailpit, orcid, email),
            409,
            "email_belongs_to_another_account",
        )
        assert _users_with_email(http_client, email, is_enabled=True) == []
        assert _users_with_email(http_client, email, is_enabled=False) == []

    def test_a_disabled_orcid_account_never_has_the_orcid_attached_elsewhere(
        self, http_client, mailpit
    ):
        orcid, email = random_orcid(), unique_email()
        _disable(http_client, _orcid_account(http_client, orcid))
        other = create_plain_user(http_client, email)

        refused(
            _confirmed(http_client, mailpit, orcid, email),
            409,
            "email_belongs_to_another_account",
        )
        profile = user(http_client, other)
        assert profile["providers"] == []
        assert profile["email_verified_at"] is None

    def test_a_disabled_and_an_enabled_holder_of_one_orcid_conflict(
        self, http_client, mailpit
    ):
        orcid, email = random_orcid(), unique_email()
        _disable(http_client, _orcid_account(http_client, orcid))
        enabled = create_plain_user(http_client, unique_email())
        attached = http_client.put(
            f"/users/{enabled}/providers",
            json={"name": "orcid", "reference": orcid},
            headers=AuthFixture.valid_headers(),
        )
        assert_status_code(attached, 200)

        refused(
            _confirmed(http_client, mailpit, orcid, email),
            409,
            "email_belongs_to_another_account",
        )
        profile = user(http_client, enabled)
        assert profile["email"] != email
        assert profile["email_verified_at"] is None
        assert _users_with_email(http_client, email, is_enabled=True) == []


class TestEmailVerificationRequests:
    def test_a_known_and_an_unknown_email_get_the_same_answer(self, http_client):
        known = unique_email()
        create_plain_user(http_client, known)

        answers = [
            request_email_verification(http_client, random_orcid(), address)
            for address in (known, unique_email())
        ]

        assert [answer.status_code for answer in answers] == [202, 202]
        assert [set(answer.json()) for answer in answers] == [
            {"challenge_id"},
            {"challenge_id"},
        ]

    def test_a_malformed_orcid_is_refused(self, http_client):
        refused(
            request_email_verification(
                http_client, "0000-0002-1825-0098", unique_email()
            ),
            400,
            "invalid_orcid",
        )

    def test_the_email_names_the_orcid_being_linked(self, http_client, mailpit):
        orcid, email = random_orcid(), unique_email()

        assert_status_code(request_email_verification(http_client, orcid, email), 202)

        assert f"ORCID iD: {orcid}" in newest_text(http_client, mailpit, email)
