import uuid

import pytest

from tests.integration.fixtures.account import (
    PASSWORD,
    age_challenge,
    confirm_sign_up,
    create_plain_user,
    delivered,
    login,
    newest_code,
    outbox,
    refused,
    resend,
    sign_up,
    unique_email,
    user,
)
from tests.integration.fixtures.embargo import client_headers
from tests.integration.fixtures.sharing import dispatch
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.container_log import access_lines, wait_for_log
from tests.integration.utils.mailpit import Mailpit


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


def _started(http_client, email: str) -> str:
    response = sign_up(http_client, email)
    assert_status_code(response, 202)
    return response.json()["challenge_id"]


class TestSignUp:
    def test_a_new_email_becomes_a_confirmed_account_that_signs_in(
        self, http_client, mailpit
    ):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email)

        confirmed = confirm_sign_up(http_client, challenge_id, code)

        assert_status_code(confirmed, 200)
        user_id = confirmed.json()["user_id"]
        profile = user(http_client, user_id)
        assert profile["email"] == email
        assert profile["has_password"] is True
        assert profile["email_verified_at"] is not None
        signed_in = login(http_client, email, PASSWORD)
        assert_status_code(signed_in, 200)
        assert signed_in.json() == {"user_id": user_id}

    def test_an_existing_account_gets_the_password_and_its_email_confirmed(
        self, http_client, mailpit
    ):
        email = unique_email()
        user_id = create_plain_user(http_client, email)
        before = user(http_client, user_id)

        challenge_id = _started(http_client, email.upper())
        code = newest_code(http_client, mailpit, email)
        confirmed = confirm_sign_up(http_client, challenge_id, code)

        assert_status_code(confirmed, 200)
        assert confirmed.json() == {"user_id": user_id}
        after = user(http_client, user_id)
        assert (before["has_password"], before["email_verified_at"]) == (False, None)
        assert after["has_password"] is True
        assert after["email_verified_at"] is not None

    def test_a_known_and_an_unknown_email_get_the_same_answer(self, http_client):
        known = unique_email()
        create_plain_user(http_client, known)

        answers = [sign_up(http_client, address) for address in (known, unique_email())]

        assert [answer.status_code for answer in answers] == [202, 202]
        assert [set(answer.json()) for answer in answers] == [
            {"challenge_id"},
            {"challenge_id"},
        ]

    def test_a_password_shorter_than_ten_characters_is_refused(self, http_client):
        refused(
            sign_up(http_client, unique_email(), password="too short"),
            400,
            "invalid_password",
        )

    def test_a_malformed_email_is_refused(self, http_client):
        refused(sign_up(http_client, "not-an-email"), 400, "invalid_email")


class TestCodes:
    def test_a_wrong_code_is_refused_and_the_right_one_still_works(
        self, http_client, mailpit
    ):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email)
        wrong = "000000" if code != "000000" else "111111"

        refused(confirm_sign_up(http_client, challenge_id, wrong), 400, "code_invalid")
        assert_status_code(confirm_sign_up(http_client, challenge_id, code), 200)

    def test_five_wrong_codes_use_the_challenge_up(self, http_client, mailpit):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email)
        wrong = "000000" if code != "000000" else "111111"

        answers = [
            confirm_sign_up(http_client, challenge_id, wrong).json()["detail"]
            for _ in range(5)
        ]

        assert answers == ["code_invalid"] * 4 + ["code_attempts_exceeded"]
        refused(
            confirm_sign_up(http_client, challenge_id, code),
            400,
            "code_attempts_exceeded",
        )

    def test_an_expired_code_is_refused_for_good(self, http_client, mailpit):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email)
        age_challenge(challenge_id, "expires_at", 1)

        refused(confirm_sign_up(http_client, challenge_id, code), 400, "code_expired")
        refused(confirm_sign_up(http_client, challenge_id, code), 400, "code_expired")

    def test_a_code_works_once(self, http_client, mailpit):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email)

        assert_status_code(confirm_sign_up(http_client, challenge_id, code), 200)
        refused(confirm_sign_up(http_client, challenge_id, code), 400, "code_invalid")

    def test_a_new_sign_up_retires_the_previous_code(self, http_client, mailpit):
        email = unique_email()
        first = _started(http_client, email)
        first_code = newest_code(http_client, mailpit, email, count=1)
        second = _started(http_client, email)
        second_code = newest_code(http_client, mailpit, email, count=2)

        refused(confirm_sign_up(http_client, first, first_code), 400, "code_invalid")
        assert_status_code(confirm_sign_up(http_client, second, second_code), 200)

    def test_an_unknown_challenge_is_not_found(self, http_client):
        refused(
            confirm_sign_up(http_client, uuid.uuid4(), "123456"),
            404,
            "challenge_not_found",
        )
        refused(
            confirm_sign_up(http_client, "not-a-uuid", "123456"),
            404,
            "challenge_not_found",
        )


class TestResend:
    def test_a_resend_within_ninety_seconds_is_refused(self, http_client, mailpit):
        email = unique_email()
        challenge_id = _started(http_client, email)
        delivered(http_client, mailpit, email)

        refused(resend(http_client, challenge_id), 429, "resend_too_soon")

    def test_a_resend_after_ninety_seconds_sends_a_new_code_and_retires_the_old(
        self, http_client, mailpit
    ):
        email = unique_email()
        challenge_id = _started(http_client, email)
        old = newest_code(http_client, mailpit, email, count=1)
        age_challenge(challenge_id, "issued_at", 91)

        again = resend(http_client, challenge_id)

        assert_status_code(again, 202)
        assert again.content == b""
        new = newest_code(http_client, mailpit, email, count=2)
        refused(confirm_sign_up(http_client, challenge_id, old), 400, "code_invalid")
        assert_status_code(confirm_sign_up(http_client, challenge_id, new), 200)

    def test_an_expired_challenge_can_be_resent(self, http_client, mailpit):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email, count=1)
        age_challenge(challenge_id, "expires_at", 1)
        refused(confirm_sign_up(http_client, challenge_id, code), 400, "code_expired")
        age_challenge(challenge_id, "issued_at", 91)

        assert_status_code(resend(http_client, challenge_id), 202)

        new = newest_code(http_client, mailpit, email, count=2)
        assert_status_code(confirm_sign_up(http_client, challenge_id, new), 200)

    def test_a_challenge_out_of_attempts_can_be_resent(self, http_client, mailpit):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email, count=1)
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            confirm_sign_up(http_client, challenge_id, wrong)
        refused(
            confirm_sign_up(http_client, challenge_id, code),
            400,
            "code_attempts_exceeded",
        )
        age_challenge(challenge_id, "issued_at", 91)

        assert_status_code(resend(http_client, challenge_id), 202)

        new = newest_code(http_client, mailpit, email, count=2)
        assert_status_code(confirm_sign_up(http_client, challenge_id, new), 200)

    def test_a_confirmed_challenge_cannot_be_resent(self, http_client, mailpit):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email)
        assert_status_code(confirm_sign_up(http_client, challenge_id, code), 200)
        age_challenge(challenge_id, "issued_at", 91)

        refused(resend(http_client, challenge_id), 404, "challenge_not_found")


class TestHourlyCap:
    def test_past_five_codes_an_hour_nothing_is_sent_and_the_challenge_never_confirms(
        self, http_client, mailpit
    ):
        email = unique_email()
        for sent in range(1, 6):
            _started(http_client, email)
            delivered(http_client, mailpit, email, count=sent)
        last_code = newest_code(http_client, mailpit, email, count=5)

        capped = sign_up(http_client, email)

        assert_status_code(capped, 202)
        assert set(capped.json()) == {"challenge_id"}
        assert (
            outbox(http_client, recipient=email, template="sign_up_code")["total_count"]
            == 5
        )
        refused(
            confirm_sign_up(http_client, capped.json()["challenge_id"], last_code),
            400,
            "code_invalid",
        )
        dispatch(http_client)
        assert len(mailpit.messages_to(email)) == 5


class TestWhatReachesTheLog:
    def test_the_access_line_of_a_confirmation_redacts_the_code(
        self, http_client, mailpit
    ):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email)
        marker = f"req-{uuid.uuid4()}"

        confirm_sign_up(
            http_client,
            challenge_id,
            code,
            headers={**client_headers(), "X-Request-Id": marker},
        )

        lines = access_lines(wait_for_log(lambda log: marker in log), marker)
        assert lines
        assert lines[0]["body"] == {"code": "[redacted]"}

    def test_the_access_line_of_a_sign_up_redacts_the_password(self, http_client):
        marker = f"req-{uuid.uuid4()}"

        response = http_client.post(
            "/auth/sign-up",
            json={"name": "Ana Souza", "email": unique_email(), "password": PASSWORD},
            headers={**client_headers(), "X-Request-Id": marker},
        )

        assert_status_code(response, 202)
        lines = access_lines(wait_for_log(lambda log: marker in log), marker)
        assert lines
        assert lines[0]["body"]["password"] == "[redacted]"
        assert PASSWORD not in str(lines[0])
