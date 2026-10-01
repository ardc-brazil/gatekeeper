import subprocess
import uuid
from datetime import datetime, timedelta, timezone

import requests

from tests.integration.config import config
from tests.integration.fixtures.auth import AuthFixture
from tests.integration.utils.http_client import HttpClient

POSTGRES_CONTAINER = "datamap_postgres_test_integration"
TENANCY = config.tenancy


def until(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def headers_for(user_id: str, tenancy: str | None) -> dict:
    headers = {
        "X-Api-Key": config.api_key,
        "X-Api-Secret": config.api_secret,
        "X-User-Id": user_id,
        "Content-Type": "application/json",
    }
    if tenancy:
        headers["X-Datamap-Tenancies"] = tenancy
    return headers


def client_headers() -> dict:
    return {
        "X-Api-Key": config.api_key,
        "X-Api-Secret": config.api_secret,
        "Content-Type": "application/json",
    }


def create_user(http_client: HttpClient, roles: list[str], tenancies: list[str]) -> str:
    admin = AuthFixture.valid_headers()
    response = http_client.post(
        "/users/",
        json={
            "name": "Embargo Test User",
            "email": f"embargo_{uuid.uuid4().hex[:10]}@example.com",
            "providers": [],
            "roles": [],
        },
        headers=admin,
    )
    assert response.status_code == 200, response.text
    user_id = response.json()["id"]
    if roles:
        response = http_client.put(f"/users/{user_id}/roles", json=roles, headers=admin)
        assert response.status_code == 200, response.text
    if tenancies:
        response = http_client.post(
            f"/users/{user_id}/tenancies", json={"tenancies": tenancies}, headers=admin
        )
        assert response.status_code == 200, response.text
    return user_id


def grant(http_client: HttpClient, dataset_id: str, user_id: str, level: str) -> None:
    sql = (
        "INSERT INTO dataset_permissions (dataset_id, user_id, level) "
        f"VALUES ('{dataset_id}', '{user_id}', '{level}') "
        "ON CONFLICT (dataset_id, user_id) DO UPDATE SET level = EXCLUDED.level"
    )
    subprocess.run(
        [
            "docker",
            "exec",
            POSTGRES_CONTAINER,
            "psql",
            "-U",
            "gk_admin",
            "-d",
            "gatekeeper_db",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        check=True,
        capture_output=True,
    )
    response = http_client.put(
        f"/users/{user_id}/roles",
        json=["datasets_shared"],
        headers=AuthFixture.valid_headers(),
    )
    assert response.status_code == 200, response.text


def create_dataset(http_client: HttpClient, headers: dict) -> dict:
    response = http_client.post(
        "/datasets",
        json={
            "name": f"Embargo Test {uuid.uuid4().hex[:8]}",
            "data": {"description": "embargo", "authors": [{"name": "A"}]},
            "tenancy": TENANCY,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def set_embargo(
    http_client: HttpClient,
    dataset_id: str,
    headers: dict,
    visible: bool,
    days: int = 30,
) -> requests.Response:
    return http_client.put(
        f"/datasets/{dataset_id}/embargo",
        json={"until": until(days), "metadata_visible": visible, "note": "review"},
        headers=headers,
    )


def manual_doi(
    http_client: HttpClient,
    dataset: dict,
    headers: dict,
    end_embargo: bool | None = None,
) -> requests.Response:
    body = {"identifier": f"10.82978/MANUAL{uuid.uuid4().hex[:8]}", "mode": "MANUAL"}
    if end_embargo is not None:
        body["end_embargo"] = end_embargo
    version = dataset["current_version"]["name"]
    return http_client.post(
        f"/datasets/{dataset['id']}/versions/{version}/doi", json=body, headers=headers
    )


def auto_doi(
    http_client: HttpClient, dataset: dict, headers: dict
) -> requests.Response:
    version = dataset["current_version"]["name"]
    return http_client.post(
        f"/datasets/{dataset['id']}/versions/{version}/doi",
        json={"mode": "AUTO"},
        headers=headers,
    )


def make_findable(
    http_client: HttpClient, dataset: dict, headers: dict
) -> requests.Response:
    version = dataset["current_version"]["name"]
    return http_client.put(
        f"/datasets/{dataset['id']}/versions/{version}/doi",
        json={"state": "FINDABLE"},
        headers=headers,
    )
