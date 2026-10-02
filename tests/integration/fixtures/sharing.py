import random
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.embargo import client_headers
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.http_client import HttpClient


def create_user(http_client: HttpClient, providers: list[dict] | None = None) -> dict:
    email = f"share_{uuid.uuid4().hex[:10]}@example.com"
    response = http_client.post(
        "/users/",
        json={
            "name": "Outside Researcher",
            "email": email,
            "providers": providers or [],
            "roles": [],
        },
        headers=AuthFixture.valid_headers(),
    )
    assert_status_code(response, 200)
    return {"id": response.json()["id"], "email": email}


def set_embargo(
    http_client: HttpClient,
    dataset_id: str,
    delta: timedelta,
    tz: timezone = timezone.utc,
) -> str:
    until = (datetime.now(tz) + delta).isoformat()
    response = http_client.put(
        f"/datasets/{dataset_id}/embargo",
        json={"until": until, "metadata_visible": False, "note": None},
        headers=AuthFixture.valid_headers(),
    )
    assert_status_code(response, 200)
    return until


def share(http_client: HttpClient, dataset_id: str, body: dict):
    return http_client.post(
        f"/datasets/{dataset_id}/share", json=body, headers=AuthFixture.valid_headers()
    )


def token_of(link: str) -> str:
    return link.rsplit("/", 1)[1]


def dispatch(http_client: HttpClient) -> dict:
    response = http_client.post(
        "/internal/notifications/dispatch", headers=client_headers()
    )
    assert_status_code(response, 200)
    return response.json()


def random_orcid() -> str:
    digits = "0000" + "".join(random.choice("0123456789") for _ in range(11))
    total = 0
    for char in digits:
        total = (total + int(char)) * 2
    result = (12 - total % 11) % 11
    digits += "X" if result == 10 else str(result)
    return "-".join(digits[i : i + 4] for i in range(0, 16, 4))


@pytest.fixture
def embargoed_dataset(dataset_fixture, http_client) -> dict:
    dataset = dataset_fixture.create_test_dataset()
    set_embargo(http_client, dataset["id"], timedelta(days=30))
    return dataset
