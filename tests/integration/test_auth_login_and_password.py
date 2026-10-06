import uuid

import pytest

from tests.integration.fixtures.account import (
    PASSWORD,
    change_password,
    confirm_email_verification,
    confirm_password_reset,
    create_plain_user,
    delivered,
    disable,
    login,
    newest_code,
    newest_reset_token,
    outbox,
    password_account,
    refused,
    request_email_verification,
    request_password_reset,
    sign_up,
    unique_email,
)
from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.embargo import client_headers, headers_for
from tests.integration.fixtures.sharing import dispatch, random_orcid
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.container_log import access_lines, wait_for_log
from tests.integration.utils.database import execute
from tests.integration.utils.mailpit import Mailpit

NEW_PASSWORD = "a brand new password"


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


def _fail(http_client, email: str, times: int) -> None:
    for _ in range(times):
        assert_status_code(login(http_client, email, "not the password"), 401)


def _reset(http_client, mailpit, email: str, count: int, password: str = NEW_PASSWORD):
    assert_status_code(request_password_reset(http_client, email), 202)
    token = newest_reset_token(http_client, mailpit, email, count=count)
    return confirm_password_reset(http_client, token, password)


class TestSignIn:
    def test_the_right_password_signs_in(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        response = login(http_client, account["email"].upper(), PASSWORD)

        assert_status_code(response, 200)
        assert response.json() == {"user_id": account["id"]}

    def test_every_failure_is_the_same_401(self, http_client, mailpit):
        account = password_account(http_client, mailpit)
        no_password = unique_email()
        create_plain_user(http_client, no_password)
        unconfirmed = password_account(http_client, mailpit)
        execute(
            f"UPDATE users SET email_verified_at = NULL WHERE id = '{unconfirmed['id']}'"
        )
        disabled = password_account(http_client, mailpit)
        disable(http_client, disabled["id"])

        answers = [
            login(http_client, unique_email(), PASSWORD),
            login(http_client, account["email"], "not the password"),
            login(http_client, no_password, PASSWORD),
            login(http_client, unconfirmed["email"], PASSWORD),
            login(http_client, disabled["email"], PASSWORD),
            login(http_client, "not-an-email", PASSWORD),
        ]

        assert [(answer.status_code, answer.json()) for answer in answers] == [
            (401, {"detail": "invalid_credentials"})
        ] * 6


class TestLock:
    def test_nine_wrong_passwords_do_not_lock(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        _fail(http_client, account["email"], 9)

        assert_status_code(login(http_client, account["email"], PASSWORD), 200)

    def test_the_tenth_locks_even_against_the_right_password(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)

        _fail(http_client, account["email"], 10)

        refused(
            login(http_client, account["email"], PASSWORD), 401, "invalid_credentials"
        )
        assert (
            execute(
                "SELECT locked_until > now() + interval '14 minutes' "
                f"FROM users WHERE id = '{account['id']}'"
            )
            == "t"
        )

    def test_the_lock_ends_after_its_time_and_a_success_clears_it(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)
        _fail(http_client, account["email"], 10)
        execute(
            "UPDATE users SET locked_until = now() - interval '1 second' "
            f"WHERE id = '{account['id']}'"
        )

        assert_status_code(login(http_client, account["email"], PASSWORD), 200)

        assert (
            execute(
                "SELECT failed_login_count, locked_until IS NULL "
                f"FROM users WHERE id = '{account['id']}'"
            )
            == "0|t"
        )

    def test_after_a_lock_expires_the_first_wrong_password_locks_again(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)
        _fail(http_client, account["email"], 10)
        execute(
            "UPDATE users SET locked_until = now() - interval '1 second' "
            f"WHERE id = '{account['id']}'"
        )

        _fail(http_client, account["email"], 1)

        refused(
            login(http_client, account["email"], PASSWORD), 401, "invalid_credentials"
        )
        assert (
            execute(
                "SELECT locked_until > now() + interval '14 minutes' "
                f"FROM users WHERE id = '{account['id']}'"
            )
            == "t"
        )

    def test_a_reset_lifts_the_lock(self, http_client, mailpit):
        account = password_account(http_client, mailpit)
        _fail(http_client, account["email"], 10)

        assert_status_code(_reset(http_client, mailpit, account["email"], count=2), 204)

        assert (
            execute(
                "SELECT failed_login_count, locked_until IS NULL "
                f"FROM users WHERE id = '{account['id']}'"
            )
            == "0|t"
        )
        assert_status_code(login(http_client, account["email"], NEW_PASSWORD), 200)


class TestPasswordReset:
    def test_a_reset_link_sets_a_new_password(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        assert_status_code(_reset(http_client, mailpit, account["email"], count=2), 204)

        refused(
            login(http_client, account["email"], PASSWORD), 401, "invalid_credentials"
        )
        assert_status_code(login(http_client, account["email"], NEW_PASSWORD), 200)

    def test_a_link_works_once(self, http_client, mailpit):
        account = password_account(http_client, mailpit)
        assert_status_code(request_password_reset(http_client, account["email"]), 202)
        token = newest_reset_token(http_client, mailpit, account["email"], count=2)

        assert_status_code(
            confirm_password_reset(http_client, token, NEW_PASSWORD), 204
        )
        refused(
            confirm_password_reset(http_client, token, "another new password"),
            400,
            "token_invalid",
        )

    def test_an_expired_link_is_refused(self, http_client, mailpit):
        account = password_account(http_client, mailpit)
        assert_status_code(request_password_reset(http_client, account["email"]), 202)
        token = newest_reset_token(http_client, mailpit, account["email"], count=2)
        execute(
            "UPDATE auth_challenges SET expires_at = now() - interval '1 second' "
            f"WHERE user_id = '{account['id']}' AND kind = 'password_reset'"
        )

        refused(
            confirm_password_reset(http_client, token, NEW_PASSWORD),
            400,
            "token_invalid",
        )

    def test_a_new_link_retires_the_previous_one(self, http_client, mailpit):
        account = password_account(http_client, mailpit)
        assert_status_code(request_password_reset(http_client, account["email"]), 202)
        first = newest_reset_token(http_client, mailpit, account["email"], count=2)
        assert_status_code(request_password_reset(http_client, account["email"]), 202)
        second = newest_reset_token(http_client, mailpit, account["email"], count=3)

        refused(
            confirm_password_reset(http_client, first, NEW_PASSWORD),
            400,
            "token_invalid",
        )
        assert_status_code(
            confirm_password_reset(http_client, second, NEW_PASSWORD), 204
        )

    def test_a_known_and_an_unknown_email_get_the_same_answer(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)

        answers = [
            request_password_reset(http_client, address)
            for address in (account["email"], unique_email())
        ]

        assert [(answer.status_code, answer.content) for answer in answers] == [
            (202, b"")
        ] * 2

    def test_an_unknown_email_is_sent_nothing(self, http_client):
        address = unique_email()

        assert_status_code(request_password_reset(http_client, address), 202)

        assert outbox(http_client, recipient=address)["total_count"] == 0

    def test_an_unconfirmed_account_is_sent_nothing(self, http_client):
        address = unique_email()
        create_plain_user(http_client, address)

        assert_status_code(request_password_reset(http_client, address), 202)

        assert (
            outbox(http_client, recipient=address, template="password_reset")[
                "total_count"
            ]
            == 0
        )

    def test_an_orcid_account_sets_its_first_password_through_the_link(
        self, http_client, mailpit
    ):
        email = unique_email()
        started = request_email_verification(http_client, random_orcid(), email)
        code = newest_code(http_client, mailpit, email)
        assert_status_code(
            confirm_email_verification(
                http_client, started.json()["challenge_id"], code
            ),
            200,
        )

        assert_status_code(_reset(http_client, mailpit, email, count=2), 204)

        assert_status_code(login(http_client, email, NEW_PASSWORD), 200)

    def test_a_short_password_is_refused(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        refused(
            _reset(
                http_client, mailpit, account["email"], count=2, password="too short"
            ),
            400,
            "invalid_password",
        )


class TestSelfAccess:
    def test_an_account_without_a_role_reads_itself(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        response = http_client.get(
            f"/users/{account['id']}", headers=headers_for(account["id"], None)
        )

        assert_status_code(response, 200)
        assert response.json()["id"] == account["id"]
        assert response.json()["roles"] == ["datasets_write"]
        assert response.json()["tenancies"] == ["datamap/production/public"]
        assert response.json()["has_password"] is True

    def test_an_account_without_a_role_cannot_read_anyone_else(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)
        other = password_account(http_client, mailpit)

        refused(
            http_client.get(
                f"/users/{other['id']}", headers=headers_for(account["id"], None)
            ),
            401,
            "not_authorized",
        )


class TestChangePassword:
    def test_an_account_without_a_role_changes_its_own_password(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)

        response = change_password(http_client, account["id"], PASSWORD, NEW_PASSWORD)

        assert_status_code(response, 204)
        refused(
            login(http_client, account["email"], PASSWORD), 401, "invalid_credentials"
        )
        assert_status_code(login(http_client, account["email"], NEW_PASSWORD), 200)

    def test_a_wrong_current_password_is_refused(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        refused(
            change_password(
                http_client, account["id"], "not the password", NEW_PASSWORD
            ),
            401,
            "invalid_credentials",
        )
        assert_status_code(login(http_client, account["email"], PASSWORD), 200)

    def test_an_account_without_a_role_cannot_change_anyone_elses(
        self, http_client, mailpit
    ):
        victim = password_account(http_client, mailpit)
        attacker = password_account(http_client, mailpit)

        refused(
            change_password(
                http_client,
                victim["id"],
                PASSWORD,
                NEW_PASSWORD,
                acting_as=attacker["id"],
            ),
            401,
            "not_authorized",
        )
        assert_status_code(login(http_client, victim["email"], PASSWORD), 200)

    def test_even_a_role_that_may_write_users_cannot_change_anyone_elses(
        self, http_client, mailpit
    ):
        victim = password_account(http_client, mailpit)
        attacker = password_account(http_client, mailpit)
        granted = http_client.put(
            f"/users/{attacker['id']}/roles",
            json=["users_write"],
            headers=AuthFixture.valid_headers(),
        )
        assert_status_code(granted, 200)

        refused(
            change_password(
                http_client,
                victim["id"],
                PASSWORD,
                NEW_PASSWORD,
                acting_as=attacker["id"],
            ),
            401,
            "invalid_credentials",
        )
        assert_status_code(login(http_client, victim["email"], PASSWORD), 200)

    def test_a_new_password_out_of_policy_is_refused(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        refused(
            change_password(http_client, account["id"], PASSWORD, "too short"),
            400,
            "invalid_password",
        )

    def test_ten_wrong_current_passwords_lock_sign_in_too(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        for _ in range(10):
            refused(
                change_password(
                    http_client, account["id"], "not the password", NEW_PASSWORD
                ),
                401,
                "invalid_credentials",
            )

        refused(
            login(http_client, account["email"], PASSWORD), 401, "invalid_credentials"
        )
        refused(
            change_password(http_client, account["id"], PASSWORD, NEW_PASSWORD),
            401,
            "invalid_credentials",
        )
        assert (
            execute(
                "SELECT failed_login_count, locked_until > now() "
                f"FROM users WHERE id = '{account['id']}'"
            )
            == "10|t"
        )

    def test_a_wrong_current_password_counts_even_with_a_short_new_one(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)

        refused(
            change_password(http_client, account["id"], "not the password", "short"),
            401,
            "invalid_credentials",
        )

        assert (
            execute(
                f"SELECT failed_login_count FROM users WHERE id = '{account['id']}'"
            )
            == "1"
        )

    def test_a_change_retires_an_open_reset_link(self, http_client, mailpit):
        account = password_account(http_client, mailpit)
        assert_status_code(request_password_reset(http_client, account["email"]), 202)
        token = newest_reset_token(http_client, mailpit, account["email"], count=2)

        assert_status_code(
            change_password(http_client, account["id"], PASSWORD, NEW_PASSWORD), 204
        )

        refused(
            confirm_password_reset(http_client, token, "yet another password"),
            400,
            "token_invalid",
        )
        assert_status_code(login(http_client, account["email"], NEW_PASSWORD), 200)


class TestHourlyCapAcrossKinds:
    def test_codes_and_links_share_five_an_hour(self, http_client, mailpit):
        account = password_account(http_client, mailpit)
        email = account["email"]
        for sent in (2, 3):
            assert_status_code(request_password_reset(http_client, email), 202)
            delivered(http_client, mailpit, email, count=sent)
        assert_status_code(sign_up(http_client, email), 202)
        delivered(http_client, mailpit, email, count=4)
        assert_status_code(
            request_email_verification(http_client, random_orcid(), email), 202
        )
        delivered(http_client, mailpit, email, count=5)

        assert_status_code(request_password_reset(http_client, email), 202)
        assert_status_code(sign_up(http_client, email), 202)
        assert_status_code(
            request_email_verification(http_client, random_orcid(), email), 202
        )

        dispatch(http_client)
        assert len(mailpit.messages_to(email)) == 5
        assert outbox(http_client, recipient=email)["total_count"] == 5
        assert {
            template: outbox(http_client, recipient=email, template=template)[
                "total_count"
            ]
            for template in (
                "sign_up_code",
                "password_reset",
                "sign_up_existing_account",
                "email_verification_code",
            )
        } == {
            "sign_up_code": 1,
            "password_reset": 2,
            "sign_up_existing_account": 1,
            "email_verification_code": 1,
        }


class TestWhatReachesTheLog:
    def _access_line(self, marker: str) -> dict:
        lines = access_lines(wait_for_log(lambda log: marker in log), marker)
        assert lines
        return lines[0]

    def test_the_access_line_of_a_sign_in_redacts_the_password(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)
        marker = f"req-{uuid.uuid4()}"

        response = http_client.post(
            "/auth/login",
            json={"email": account["email"], "password": PASSWORD},
            headers={**client_headers(), "X-Request-Id": marker},
        )

        assert_status_code(response, 200)
        line = self._access_line(marker)
        assert line["body"]["password"] == "[redacted]"
        assert PASSWORD not in str(line)

    def test_the_access_line_of_a_reset_redacts_the_token_and_password(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)
        assert_status_code(request_password_reset(http_client, account["email"]), 202)
        token = newest_reset_token(http_client, mailpit, account["email"], count=2)
        marker = f"req-{uuid.uuid4()}"

        response = http_client.post(
            "/auth/password-reset/confirm",
            json={"token": token, "password": NEW_PASSWORD},
            headers={**client_headers(), "X-Request-Id": marker},
        )

        assert_status_code(response, 204)
        line = self._access_line(marker)
        assert line["body"]["token"] == "[redacted]"
        assert line["body"]["password"] == "[redacted]"
        assert token not in str(line)
        assert NEW_PASSWORD not in str(line)

    def test_the_access_line_of_a_password_change_redacts_both_passwords(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)
        marker = f"req-{uuid.uuid4()}"

        response = http_client.put(
            f"/users/{account['id']}/password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers={**headers_for(account["id"], None), "X-Request-Id": marker},
        )

        assert_status_code(response, 204)
        line = self._access_line(marker)
        assert line["body"]["current_password"] == "[redacted]"
        assert line["body"]["new_password"] == "[redacted]"
        assert PASSWORD not in str(line)
        assert NEW_PASSWORD not in str(line)
