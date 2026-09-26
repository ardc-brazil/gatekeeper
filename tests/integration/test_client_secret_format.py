import subprocess
import time

import pytest

from tests.integration.config import config
from tests.integration.utils.assertions import assert_status_code

PSQL = [
    "docker",
    "exec",
    "datamap_postgres_test_integration",
    "psql",
    "-U",
    "gk_admin",
    "-d",
    "gatekeeper_db",
    "-tAc",
]


def _stored_secret(api_key: str) -> str:
    result = subprocess.run(
        PSQL + [f"select secret from clients where key = '{api_key}'"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


class TestClientSecretFormat:
    """The stored hash format, and the upgrade away from bcrypt."""

    def test_a_bcrypt_hash_from_the_seed_still_authenticates(
        self, http_client, valid_headers
    ):
        response = http_client.get("/clients", headers=valid_headers)

        assert_status_code(response, 200)

    def test_authenticating_upgrades_the_stored_hash_away_from_bcrypt(
        self, http_client, valid_headers
    ):
        http_client.get("/clients", headers=valid_headers)

        stored = _stored_secret(config.api_key)

        assert stored.startswith("hmac-sha256$"), stored[:10]

    def test_the_secret_keeps_working_after_the_upgrade(
        self, http_client, valid_headers
    ):
        http_client.get("/clients", headers=valid_headers)

        response = http_client.get("/clients", headers=valid_headers)

        assert_status_code(response, 200)

    def test_a_wrong_secret_is_still_rejected_after_the_upgrade(
        self, http_client, valid_headers
    ):
        http_client.get("/clients", headers=valid_headers)

        wrong = dict(valid_headers)
        wrong["X-Api-Secret"] = "not-the-secret"
        response = http_client.get("/clients", headers=wrong)

        assert_status_code(response, 401)

    def test_a_client_created_through_the_api_is_stored_in_the_new_format(
        self, http_client, valid_headers
    ):
        response = http_client.post(
            "/clients",
            headers=valid_headers,
            json={"name": "format check", "secret": "a-secret-for-the-format-check"},
        )
        assert_status_code(response, 201)
        created_key = response.json()["key"]

        try:
            assert _stored_secret(created_key).startswith("hmac-sha256$")
        finally:
            http_client.delete(f"/clients/{created_key}", headers=valid_headers)

    @pytest.mark.parametrize("_", range(3))
    def test_an_authenticated_request_is_not_slowed_by_the_hash(
        self, http_client, valid_headers, _
    ):
        http_client.get("/clients", headers=valid_headers)

        start = time.perf_counter()
        http_client.get("/clients", headers=valid_headers)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 100, f"{elapsed_ms:.0f}ms"
