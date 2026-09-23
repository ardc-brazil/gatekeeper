import subprocess
import uuid

from tests.integration.fixtures.tus_auth import create_tus_payload
from tests.integration.utils.assertions import assert_status_code

API_CONTAINER = "datamap_gatekeeper_test_integration"
SEEDED_USER_ID = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"


def _scrape() -> str:
    """As Prometheus does: from inside the docker network, on the metrics port."""
    result = subprocess.run(
        [
            "docker",
            "exec",
            API_CONTAINER,
            "python3",
            "-c",
            "import urllib.request;"
            "print(urllib.request.urlopen('http://127.0.0.1:9095/metrics')"
            ".read().decode())",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _sample(body: str, name: str, **labels) -> float:
    wanted = ",".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
    for line in body.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        head, _, value = line.rpartition(" ")
        if wanted and wanted not in head:
            continue
        return float(value)
    return 0.0


class TestTheMetricsPort:
    def test_it_serves_the_prometheus_format(self):
        assert "datamap_http_requests_total" in _scrape()

    def test_it_is_not_reachable_through_the_api(self, http_client, valid_headers):
        """It carries no authentication, so it must not be on the surface nginx
        proxies. The docker network is the boundary."""
        response = http_client.get("/metrics", headers=valid_headers)

        assert response.status_code == 404, response.status_code


class TestTheCountersMove:
    def test_a_failing_upload_hook_is_counted_as_an_error(
        self, http_client, valid_headers
    ):
        before = _sample(
            _scrape(),
            "datamap_tus_hook_total",
            hook_type="post-finish",
            outcome="error",
        )

        payload = create_tus_payload(
            user_id=SEEDED_USER_ID,
            dataset_id=str(uuid.uuid4()),
            filename="test.txt",
        )
        assert_status_code(
            http_client.post("/tus/hooks", json=payload, headers=valid_headers), 500
        )

        after = _sample(
            _scrape(),
            "datamap_tus_hook_total",
            hook_type="post-finish",
            outcome="error",
        )
        assert after == before + 1

    def test_a_request_is_counted_under_a_path_without_its_id(
        self, http_client, valid_headers, dataset_fixture
    ):
        dataset = dataset_fixture.create_test_dataset()

        http_client.get(f"/datasets/{dataset['id']}", headers=valid_headers)

        body = _scrape()
        assert 'path="/api/v1/datasets/{id}"' in body
        assert dataset["id"] not in body
