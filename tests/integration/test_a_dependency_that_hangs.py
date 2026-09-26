"""A dependency that stops answering may fail the requests that need it, and
only those. The instance runs one worker, so a request that holds the event loop
while it waits takes every other request down with it."""

import subprocess
import threading
import time

import pytest
import requests

from tests.integration.config import config
from tests.integration.utils.assertions import assert_status_code

MINIO_CONTAINER = "datamap_min_io_test_integration"


@pytest.fixture
def object_storage_hung():
    """Paused, not stopped: the connection is accepted and nothing ever answers,
    which is what an overloaded or wedged storage looks like."""
    subprocess.run(
        ["docker", "pause", MINIO_CONTAINER], check=True, capture_output=True
    )
    try:
        yield
    finally:
        subprocess.run(
            ["docker", "unpause", MINIO_CONTAINER], check=True, capture_output=True
        )


@pytest.fixture
def datacite_hung():
    stub = requests.post(
        config.get_wiremock_admin_url("mappings"),
        json={
            "priority": 1,
            "request": {"method": "POST", "url": "/dois"},
            "response": {"status": 201, "fixedDelayMilliseconds": 30_000},
        },
        timeout=5,
    ).json()
    try:
        yield
    finally:
        requests.delete(
            config.get_wiremock_admin_url(f"mappings/{stub['id']}"), timeout=5
        )


def _in_background(call) -> threading.Thread:
    thread = threading.Thread(target=call, daemon=True)
    thread.start()
    time.sleep(0.5)
    return thread


def _timed(call) -> tuple[requests.Response, float]:
    started = time.monotonic()
    response = call()
    return response, time.monotonic() - started


class TestAHungObjectStorage:
    def test_the_liveness_probe_still_answers(
        self, http_client, valid_headers, object_storage_hung
    ):
        waiting = _in_background(
            lambda: http_client.get("/health-check/dependencies", headers=valid_headers)
        )

        response, elapsed = _timed(lambda: http_client.get("/health-check/"))

        assert_status_code(response, 200)
        assert elapsed < 1, f"liveness waited {elapsed:.1f}s behind the storage"
        waiting.join()

    def test_a_request_that_does_not_need_it_still_answers(
        self, http_client, valid_headers, object_storage_hung
    ):
        waiting = _in_background(
            lambda: http_client.get("/health-check/dependencies", headers=valid_headers)
        )

        response, elapsed = _timed(
            lambda: http_client.get("/datasets/", headers=valid_headers)
        )

        assert_status_code(response, 200)
        assert elapsed < 1, f"a database-only request waited {elapsed:.1f}s"
        waiting.join()

    def test_the_dependency_report_says_so_within_seconds(
        self, http_client, valid_headers, object_storage_hung
    ):
        response, elapsed = _timed(
            lambda: http_client.get("/health-check/dependencies", headers=valid_headers)
        )

        assert_status_code(response, 503)
        assert response.json()["checks"]["object_storage"]["status"] == "down"
        assert elapsed < 5, f"the report took {elapsed:.1f}s"


class TestAStoppedObjectStorage:
    def test_the_dependency_report_says_so_within_seconds(
        self, http_client, valid_headers, object_storage_down
    ):
        """Where a stopped container's name takes the resolver's full timeout to
        fail, as on the CI runner and in production, each retry pays it again."""
        response, elapsed = _timed(
            lambda: http_client.get("/health-check/dependencies", headers=valid_headers)
        )

        assert_status_code(response, 503)
        assert elapsed < 8, f"the report took {elapsed:.1f}s"


class TestAHungDataCite:
    def _create_auto_doi(self, http_client, valid_headers, dataset_fixture):
        dataset = dataset_fixture.create_dataset_with_version()
        version_name = dataset["current_version"]["name"]
        return lambda: http_client.post(
            f"/datasets/{dataset['id']}/versions/{version_name}/doi",
            json={"mode": "AUTO"},
            headers=valid_headers,
        )

    def test_the_request_gives_up_instead_of_waiting_forever(
        self, http_client, valid_headers, dataset_fixture, datacite_hung
    ):
        create = self._create_auto_doi(http_client, valid_headers, dataset_fixture)

        response, elapsed = _timed(create)

        assert response.status_code >= 500
        assert elapsed < 10, f"the request waited {elapsed:.1f}s on DataCite"

    def test_the_liveness_probe_still_answers(
        self, http_client, valid_headers, dataset_fixture, datacite_hung
    ):
        create = self._create_auto_doi(http_client, valid_headers, dataset_fixture)
        waiting = _in_background(create)

        response, elapsed = _timed(lambda: http_client.get("/health-check/"))

        assert_status_code(response, 200)
        assert elapsed < 1, f"liveness waited {elapsed:.1f}s behind DataCite"
        waiting.join()
