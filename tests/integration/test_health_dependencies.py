import uuid

from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.container_log import wait_for_log


class TestDependencyReport:
    def test_it_reports_every_dependency_as_up(self, http_client, valid_headers):
        response = http_client.get("/health-check/dependencies", headers=valid_headers)

        assert_status_code(response, 200)
        report = response.json()
        assert report["status"] == "healthy"
        assert report["checks"]["database"]["status"] == "up"
        assert report["checks"]["object_storage"]["status"] == "up"

    def test_each_check_reports_its_latency(self, http_client, valid_headers):
        response = http_client.get("/health-check/dependencies", headers=valid_headers)

        for check in response.json()["checks"].values():
            assert isinstance(check["latency_ms"], (int, float))

    def test_it_is_not_public(self, http_client):
        response = http_client.get("/health-check/dependencies")

        assert response.status_code in (401, 403), response.status_code

    def test_liveness_stays_shallow_and_public(self, http_client):
        response = http_client.get("/health-check/")

        assert_status_code(response, 200)
        assert response.json() == {"status": "online"}


class TestDependencyReportWhenSomethingIsDown:
    def test_a_stopped_object_storage_is_named(
        self, http_client, valid_headers, object_storage_down
    ):
        response = http_client.get("/health-check/dependencies", headers=valid_headers)

        assert_status_code(response, 503)
        report = response.json()
        assert report["status"] == "degraded"
        assert report["checks"]["object_storage"]["status"] == "down"

    def test_the_degradation_reaches_the_log(
        self, http_client, valid_headers, object_storage_down
    ):
        marker = f"req-{uuid.uuid4()}"
        http_client.get(
            "/health-check/dependencies",
            headers={**valid_headers, "X-Request-Id": marker},
        )

        def degraded(log: str) -> bool:
            return any(
                "dependency check degraded" in line and marker in line
                for line in log.splitlines()
            )

        assert degraded(wait_for_log(degraded))

    def test_the_database_is_still_reported_as_up(
        self, http_client, valid_headers, object_storage_down
    ):
        response = http_client.get("/health-check/dependencies", headers=valid_headers)

        assert response.json()["checks"]["database"]["status"] == "up"

    def test_liveness_still_answers_while_a_dependency_is_down(
        self, http_client, object_storage_down
    ):
        response = http_client.get("/health-check/")

        assert_status_code(response, 200)
