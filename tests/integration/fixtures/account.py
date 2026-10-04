import re
import time
import uuid

import requests

from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.embargo import client_headers, headers_for
from tests.integration.fixtures.sharing import dispatch
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.http_client import HttpClient
from tests.integration.utils.mailpit import Mailpit

PASSWORD = "correct horse battery"
ADMIN_ADDRESS = "datamap-admins@fake.mail.com"
CODE = re.compile(r"Your DataMap code: (\d{6})")
RESET_LINK = re.compile(r"/account/reset-password/([A-Za-z0-9_-]+)")


def unique_email(prefix: str = "account") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}@example.com"


def refused(response: requests.Response, status: int, detail: str) -> None:
    assert_status_code(response, status)
    assert response.json() == {"detail": detail}, response.json()


def delivered(
    http_client: HttpClient, mailpit: Mailpit, address: str, count: int = 1
) -> list[dict]:
    for _ in range(20):
        dispatch(http_client)
        found = mailpit.messages_to(address)
        if len(found) >= count:
            return found
        time.sleep(0.25)
    raise AssertionError(
        f"expected {count} message(s) to {address}, "
        f"got {len(mailpit.messages_to(address))}"
    )


def newest_text(
    http_client: HttpClient, mailpit: Mailpit, address: str, count: int = 1
) -> str:
    found = delivered(http_client, mailpit, address, count)
    newest = max(found, key=lambda message: message["Created"])
    return mailpit.message(newest["ID"])["Text"]


def newest_code(
    http_client: HttpClient, mailpit: Mailpit, address: str, count: int = 1
) -> str:
    found = CODE.search(newest_text(http_client, mailpit, address, count))
    assert found, f"no code in the newest message to {address}"
    return found.group(1)


def newest_reset_token(
    http_client: HttpClient, mailpit: Mailpit, address: str, count: int = 1
) -> str:
    found = RESET_LINK.search(newest_text(http_client, mailpit, address, count))
    assert found, f"no reset link in the newest message to {address}"
    return found.group(1)


def outbox(http_client: HttpClient, **filters) -> dict:
    response = http_client.get(
        "/admin/emails/", params=filters, headers=AuthFixture.valid_headers()
    )
    assert_status_code(response, 200)
    return response.json()


def sign_up(
    http_client: HttpClient,
    email: str,
    password: str = PASSWORD,
    name: str = "Ana Souza",
) -> requests.Response:
    return http_client.post(
        "/auth/sign-up",
        json={"name": name, "email": email, "password": password},
        headers=client_headers(),
    )


def confirm_sign_up(
    http_client: HttpClient,
    challenge_id: uuid.UUID | str,
    code: str,
    headers: dict | None = None,
) -> requests.Response:
    return http_client.post(
        f"/auth/sign-up/{challenge_id}/confirm",
        json={"code": code},
        headers=headers or client_headers(),
    )


def request_email_verification(
    http_client: HttpClient, orcid: str, email: str, name: str = "Ana Souza"
) -> requests.Response:
    return http_client.post(
        "/auth/email-verifications",
        json={"orcid": orcid, "email": email, "name": name},
        headers=client_headers(),
    )


def confirm_email_verification(
    http_client: HttpClient, challenge_id: uuid.UUID | str, code: str
) -> requests.Response:
    return http_client.post(
        f"/auth/email-verifications/{challenge_id}/confirm",
        json={"code": code},
        headers=client_headers(),
    )


def resend(http_client: HttpClient, challenge_id: uuid.UUID | str) -> requests.Response:
    return http_client.post(
        f"/auth/challenges/{challenge_id}/resend", headers=client_headers()
    )


def login(http_client: HttpClient, email: str, password: str) -> requests.Response:
    return http_client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers=client_headers(),
    )


def request_password_reset(http_client: HttpClient, email: str) -> requests.Response:
    return http_client.post(
        "/auth/password-reset", json={"email": email}, headers=client_headers()
    )


def confirm_password_reset(
    http_client: HttpClient, token: str, password: str
) -> requests.Response:
    return http_client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "password": password},
        headers=client_headers(),
    )


def change_password(
    http_client: HttpClient,
    user_id: str,
    current: str,
    new: str,
    acting_as: str | None = None,
) -> requests.Response:
    return http_client.put(
        f"/users/{user_id}/password",
        json={"current_password": current, "new_password": new},
        headers=headers_for(acting_as or user_id, None),
    )


def password_account(
    http_client: HttpClient,
    mailpit: Mailpit,
    email: str | None = None,
    password: str = PASSWORD,
) -> dict:
    email = email or unique_email()
    already = len(mailpit.messages_to(email))
    started = sign_up(http_client, email, password)
    assert_status_code(started, 202)
    code = newest_code(http_client, mailpit, email, count=already + 1)
    confirmed = confirm_sign_up(http_client, started.json()["challenge_id"], code)
    assert_status_code(confirmed, 200)
    return {"id": confirmed.json()["user_id"], "email": email, "password": password}


def user(http_client: HttpClient, user_id: str) -> dict:
    response = http_client.get(f"/users/{user_id}", headers=AuthFixture.valid_headers())
    assert_status_code(response, 200)
    return response.json()


def disable(http_client: HttpClient, user_id: str) -> None:
    response = http_client.delete(
        f"/users/{user_id}", headers=AuthFixture.valid_headers()
    )
    assert_status_code(response, 200)


def create_plain_user(
    http_client: HttpClient, email: str, providers: list[dict] | None = None
) -> str:
    response = http_client.post(
        "/users/",
        json={
            "name": "Ana Souza",
            "email": email,
            "providers": providers or [],
            "roles": [],
        },
        headers=AuthFixture.valid_headers(),
    )
    assert_status_code(response, 200)
    return response.json()["id"]


def age_challenge(challenge_id: uuid.UUID | str, column: str, seconds: int) -> None:
    execute(
        f"UPDATE auth_challenges SET {column} = now() - interval '{seconds} seconds' "
        f"WHERE id = '{challenge_id}'"
    )
