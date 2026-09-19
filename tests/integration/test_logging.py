import json
import subprocess
import time
import uuid

from tests.integration.fixtures.tus_auth import create_tus_payload
from tests.integration.utils.assertions import assert_status_code

API_CONTAINER = "datamap_gatekeeper_test_integration"
SEEDED_USER_ID = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"


def _container_log(since_seconds: int = 60) -> str:
    result = subprocess.run(
        ["docker", "logs", "--since", f"{since_seconds}s", API_CONTAINER],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout + result.stderr


class TestLogIsStructured:
    def test_the_lines_the_application_writes_are_json(self, http_client):
        http_client.get("/health-check/")
        time.sleep(1)

        ours = [
            line
            for line in _container_log().splitlines()
            if '"logger"' in line and '"timestamp"' in line
        ]

        assert ours, "no structured line was written at all"
        for line in ours:
            entry = json.loads(line)
            assert entry["level"]
            assert entry["logger"]

    def test_a_response_carries_a_request_id(self, http_client):
        response = http_client.get("/health-check/")

        assert_status_code(response, 200)
        assert response.headers.get("X-Request-Id")

    def test_an_incoming_request_id_is_kept(self, http_client, valid_headers):
        given = f"req-{uuid.uuid4()}"

        response = http_client.get(
            "/health-check/", headers={**valid_headers, "X-Request-Id": given}
        )

        assert response.headers.get("X-Request-Id") == given

    def test_the_liveness_probe_is_not_written_to_the_log(self, http_client):
        marker = f"req-{uuid.uuid4()}"

        http_client.get("/health-check/", headers={"X-Request-Id": marker})
        time.sleep(1)

        assert marker not in _container_log(), "the probe is filling the log"

    def test_a_real_request_is_still_written(self, http_client, valid_headers):
        marker = f"req-{uuid.uuid4()}"

        http_client.get("/clients/", headers={**valid_headers, "X-Request-Id": marker})
        time.sleep(1)

        assert marker in _container_log(), "an actual request went unlogged"

    def test_the_request_id_reaches_the_log_once_per_event(
        self, http_client, valid_headers
    ):
        marker = f"req-{uuid.uuid4()}"

        http_client.get("/clients/", headers={**valid_headers, "X-Request-Id": marker})
        time.sleep(1)

        occurrences = [line for line in _container_log().splitlines() if marker in line]

        assert occurrences, "the request id never reached the log"
        # Two handlers on the same logger is what produced doubled lines before,
        # each in a different format.
        assert len(occurrences) == len(
            set(occurrences)
        ), f"the same line was emitted more than once: {occurrences}"


class TestCredentialsNeverReachTheLog:
    def test_a_failing_tus_hook_does_not_log_the_upload_token(
        self, http_client, valid_headers
    ):
        """The token has to be valid, or authorisation rejects the request before
        the handler runs and this asserts nothing."""
        payload = create_tus_payload(
            user_id=SEEDED_USER_ID,
            dataset_id=str(uuid.uuid4()),  # nonexistent: drives the failure path
            filename="test.txt",
        )
        token = payload["Event"]["HTTPRequest"]["Header"]["X-User-Token"][0]

        response = http_client.post("/tus/hooks", json=payload, headers=valid_headers)
        time.sleep(1)

        assert_status_code(response, 500)  # the failure path really was taken
        assert token not in _container_log(), "the upload token was written to the log"

    def test_the_failure_is_still_reported_with_the_fields_worth_having(
        self, http_client, valid_headers
    ):
        dataset_id = str(uuid.uuid4())
        payload = create_tus_payload(
            user_id=SEEDED_USER_ID, dataset_id=dataset_id, filename="test.txt"
        )

        http_client.post("/tus/hooks", json=payload, headers=valid_headers)
        time.sleep(1)

        failures = [
            json.loads(line)
            for line in _container_log().splitlines()
            if '"tus hook failed"' in line
        ]

        assert failures, "the failure was not logged at all"
        assert any(entry.get("dataset_id") == dataset_id for entry in failures)
