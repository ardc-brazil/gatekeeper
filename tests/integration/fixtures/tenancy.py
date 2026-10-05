import uuid

import requests

from tests.integration.config import config
from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.embargo import headers_for
from tests.integration.fixtures.tus_auth import create_tus_payload
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.http_client import HttpClient

PUBLIC = "datamap/production/public"
LEGACY = "datamap/staging/data-amazon"
ADMIN_ID = config.user_id
EVENT_COLUMNS = (
    "event_type",
    "tenancy",
    "user_id",
    "actor_id",
    "request_id",
    "invitation_id",
)


def admin() -> dict:
    return headers_for(ADMIN_ID, None)


def as_user(user_id: str, tenancy: str | None = None) -> dict:
    return headers_for(user_id, tenancy)


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def new_account(
    http_client: HttpClient,
    name: str = "Bruna Costa",
    confirmed: bool = False,
    providers: list[dict] | None = None,
) -> dict:
    email = f"{unique('tenancy')}@example.com"
    response = http_client.post(
        "/users/",
        json={"name": name, "email": email, "providers": providers or [], "roles": []},
        headers=AuthFixture.valid_headers(),
    )
    assert_status_code(response, 200)
    user_id = response.json()["id"]
    if confirmed:
        execute(f"UPDATE users SET email_verified_at = now() WHERE id = '{user_id}'")
    return {"id": user_id, "email": email, "name": name}


def set_roles(
    http_client: HttpClient, user_id: str, add: tuple = (), remove: tuple = ()
) -> None:
    if remove:
        response = http_client.delete(
            f"/users/{user_id}/roles",
            json=list(remove),
            headers=AuthFixture.valid_headers(),
        )
        assert_status_code(response, 200)
    if add:
        response = http_client.put(
            f"/users/{user_id}/roles",
            json=list(add),
            headers=AuthFixture.valid_headers(),
        )
        assert_status_code(response, 200)


def join(user_id: str, tenancy: str) -> None:
    execute(
        "INSERT INTO users_tenancies (user_id, tenancy) "
        f"VALUES ('{user_id}', '{tenancy}') ON CONFLICT DO NOTHING"
    )


def new_tenancy(display_name: str | None = None, enabled: bool = True) -> str:
    path = f"datamap/production/{unique('t')}"
    name = "NULL" if display_name is None else f"'{display_name}'"
    execute(
        "INSERT INTO tenancies (name, display_name, is_enabled, created_at, updated_at) "
        f"VALUES ('{path}', {name}, {str(enabled).lower()}, now(), now())"
    )
    return path


def display_name(path: str) -> str:
    return execute(f"SELECT display_name FROM tenancies WHERE name = '{path}'")


def create_dataset(http_client: HttpClient, user_id: str, tenancy: str) -> dict:
    response = http_client.post(
        "/datasets",
        json={
            "name": unique("Tenancy dataset"),
            "data": {
                "description": "tenancy",
                "authors": [{"name": "A"}],
                "institution": "Test Institution",
            },
            "tenancy": tenancy,
        },
        headers=as_user(user_id, tenancy),
    )
    assert_status_code(response, 201)
    return response.json()


def update_dataset(
    http_client: HttpClient, user_id: str, dataset: dict, tenancy: str | None = None
) -> requests.Response:
    return http_client.put(
        f"/datasets/{dataset['id']}",
        json={"name": "edited", "data": {}, "tenancy": dataset["tenancy"]},
        headers=as_user(user_id, tenancy or dataset["tenancy"]),
    )


def members_access(
    http_client: HttpClient, user_id: str, dataset: dict, value: bool
) -> requests.Response:
    return http_client.put(
        f"/datasets/{dataset['id']}/members-access",
        json={"members_can_edit": value},
        headers=as_user(user_id, dataset["tenancy"]),
    )


def upload(http_client: HttpClient, user_id: str, dataset: dict) -> requests.Response:
    payload = create_tus_payload(
        user_id=user_id,
        dataset_id=dataset["id"],
        filename="data.nc",
        file_size=10,
        file_type="application/x-netcdf",
    )
    return http_client.post(
        "/tus/hooks", json=payload, headers=AuthFixture.valid_headers()
    )


def events(where: str) -> list[dict]:
    output = execute(
        "SELECT event_type, coalesce(tenancy, ''), coalesce(user_id::text, ''), "
        "coalesce(actor_id::text, ''), coalesce(request_id::text, ''), "
        "coalesce(invitation_id::text, '') "
        f"FROM tenancy_events WHERE {where} ORDER BY created_at, event_type"
    )
    return [
        dict(zip(EVENT_COLUMNS, line.split("|")))
        for line in output.splitlines()
        if line
    ]


def event_types(where: str) -> list[str]:
    return sorted(event["event_type"] for event in events(where))


def roles_of(user_id: str) -> list[str]:
    return execute(
        f"SELECT v1 FROM casbin_rule WHERE ptype = 'g' AND v0 = '{user_id}' ORDER BY v1"
    ).split()


def tenancies_of(http_client: HttpClient, user_id: str) -> list[str]:
    response = http_client.get(f"/users/{user_id}/tenancies", headers=as_user(user_id))
    assert_status_code(response, 200)
    return [tenancy["path"] for tenancy in response.json()]


def request_access(
    http_client: HttpClient,
    user_id: str,
    name: str = "ATTO",
    reason: str = "I process the ATTO tower fluxes.",
) -> requests.Response:
    return http_client.post(
        f"/users/{user_id}/tenancy-requests",
        json={"tenancy_name": name, "reason": reason},
        headers=as_user(user_id),
    )
