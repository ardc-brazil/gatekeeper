import json
import subprocess
import time
import uuid

from tests.integration.utils.assertions import assert_status_code

API_CONTAINER = "datamap_gatekeeper_test_integration"


def _log(since_seconds: int = 30) -> str:
    result = subprocess.run(
        ["docker", "logs", "--since", f"{since_seconds}s", API_CONTAINER],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout + result.stderr


def _access_lines(marker: str) -> list[dict]:
    return [
        entry
        for line in _log().splitlines()
        if marker in line
        for entry in [json.loads(line)]
        if entry.get("logger") == "http.access"
    ]


class TestTheRequestStillWorks:
    def test_a_body_still_reaches_the_endpoint(self, http_client, valid_headers):
        """Reading the body in middleware consumes the stream. If it is not
        replayed, every POST hangs or arrives empty."""
        name = f"dataset-{uuid.uuid4()}"

        response = http_client.post(
            "/datasets/",
            json={
                "name": name,
                "data": {"description": "body logging"},
                "tenancy": "datamap/production/data-amazon",
            },
            headers=valid_headers,
        )

        assert_status_code(response, 201)

    def test_the_dataset_was_created_with_what_was_sent(
        self, http_client, valid_headers
    ):
        name = f"dataset-{uuid.uuid4()}"

        created = http_client.post(
            "/datasets/",
            json={
                "name": name,
                "data": {"description": "body logging"},
                "tenancy": "datamap/production/data-amazon",
            },
            headers=valid_headers,
        )
        fetched = http_client.get(
            f"/datasets/{created.json()['id']}", headers=valid_headers
        )

        assert fetched.json()["name"] == name


class TestWhatIsLogged:
    def test_the_body_is_in_the_access_line(self, http_client, valid_headers):
        marker = f"req-{uuid.uuid4()}"
        name = f"dataset-{uuid.uuid4()}"

        http_client.post(
            "/datasets/",
            json={
                "name": name,
                "data": {},
                "tenancy": "datamap/production/data-amazon",
            },
            headers={**valid_headers, "X-Request-Id": marker},
        )
        time.sleep(1)

        lines = _access_lines(marker)
        assert lines, "no access line was written"
        assert lines[0]["body"]["name"] == name

    def test_a_get_has_no_body_field(self, http_client, valid_headers):
        marker = f"req-{uuid.uuid4()}"

        http_client.get("/datasets/", headers={**valid_headers, "X-Request-Id": marker})
        time.sleep(1)

        lines = _access_lines(marker)
        assert lines
        assert "body" not in lines[0]

    def test_the_correlation_id_is_on_the_same_line(self, http_client, valid_headers):
        marker = f"req-{uuid.uuid4()}"

        http_client.post(
            "/datasets/",
            json={
                "name": f"dataset-{uuid.uuid4()}",
                "data": {},
                "tenancy": "datamap/production/data-amazon",
            },
            headers={**valid_headers, "X-Request-Id": marker},
        )
        time.sleep(1)

        assert _access_lines(marker)[0]["request_id"] == marker


class TestCredentialsInABody:
    def test_a_secret_in_the_body_is_not_logged(self, http_client, valid_headers):
        """POST /clients takes an API secret in its body. Logging bodies without
        redacting them would put it in the log."""
        secret = f"secret-{uuid.uuid4()}"

        http_client.post(
            "/clients/",
            json={"name": f"client-{uuid.uuid4()}", "secret": secret},
            headers=valid_headers,
        )
        time.sleep(1)

        assert secret not in _log(), "a client secret was written to the log"

    def test_the_rest_of_that_body_is_still_logged(self, http_client, valid_headers):
        marker = f"req-{uuid.uuid4()}"
        name = f"client-{uuid.uuid4()}"

        http_client.post(
            "/clients/",
            json={"name": name, "secret": "irrelevant"},
            headers={**valid_headers, "X-Request-Id": marker},
        )
        time.sleep(1)

        lines = _access_lines(marker)
        assert lines
        assert lines[0]["body"]["name"] == name
        assert lines[0]["body"]["secret"] == "[redacted]"


class TestHeadersAreNeverLogged:
    def test_no_header_reaches_the_log(self, http_client, valid_headers):
        """Headers carry the credentials. The body may be logged; they may not."""
        http_client.get("/datasets/", headers=valid_headers)
        time.sleep(1)

        log = _log()
        assert valid_headers["X-Api-Secret"] not in log
        assert "X-Api-Secret" not in log
