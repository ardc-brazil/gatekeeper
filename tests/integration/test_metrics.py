import uuid

from tests.integration.fixtures.tus_auth import create_tus_payload
from tests.integration.utils.assertions import assert_status_code

SEEDED_USER_ID = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"


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


class TestTheEndpoint:
    def test_it_renders_in_the_prometheus_format(self, http_client, valid_headers):
        response = http_client.get("/metrics", headers=valid_headers)

        assert_status_code(response, 200)
        assert "datamap_http_requests_total" in response.text

    def test_it_is_not_public(self, http_client):
        response = http_client.get("/metrics")

        assert response.status_code in (401, 403), response.status_code

    def test_scraping_it_does_not_fill_the_access_log(self, http_client, valid_headers):
        import subprocess
        import time

        http_client.get("/metrics", headers=valid_headers)
        time.sleep(1)

        log = subprocess.run(
            ["docker", "logs", "--since", "30s", "datamap_gatekeeper_test_integration"],
            capture_output=True,
            text=True,
            check=True,
        )

        assert '"path": "/api/v1/metrics"' not in log.stdout + log.stderr


class TestTheCountersMove:
    def _metrics(self, http_client, valid_headers) -> str:
        return http_client.get("/metrics", headers=valid_headers).text

    def test_a_failing_upload_hook_is_counted_as_an_error(
        self, http_client, valid_headers
    ):
        before = _sample(
            self._metrics(http_client, valid_headers),
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
            self._metrics(http_client, valid_headers),
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

        body = self._metrics(http_client, valid_headers)
        assert 'path="/api/v1/datasets/{id}"' in body
        assert dataset["id"] not in body
