import uuid

from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.container_log import (
    access_lines,
    flush_log,
    wait_for_log,
)


def _access_lines(marker: str) -> list[dict]:
    return access_lines(wait_for_log(lambda log: marker in log), marker)


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

        lines = _access_lines(marker)
        assert lines, "no access line was written"
        assert lines[0]["body"]["name"] == name

    def test_a_get_has_no_body_field(self, http_client, valid_headers):
        marker = f"req-{uuid.uuid4()}"

        http_client.get("/datasets/", headers={**valid_headers, "X-Request-Id": marker})

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

        assert _access_lines(marker)[0]["request_id"] == marker


class TestTheTenancy:
    """Which tenancy a request was made under decides what it can see, so it
    belongs on every line. It arrives in a header, which is where the
    credentials are too — the value is logged, not the header block."""

    def test_it_is_on_a_line_with_a_body(self, http_client, valid_headers):
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

        assert _access_lines(marker)[0]["tenancies"] == [
            "datamap/production/data-amazon"
        ]

    def test_it_is_on_a_line_without_one(self, http_client, valid_headers):
        marker = f"req-{uuid.uuid4()}"

        http_client.get("/datasets/", headers={**valid_headers, "X-Request-Id": marker})

        assert _access_lines(marker)[0]["tenancies"] == [
            "datamap/production/data-amazon"
        ]

    def test_it_is_on_a_line_that_failed(self, http_client, valid_headers):
        marker = f"req-{uuid.uuid4()}"

        http_client.get(
            f"/datasets/{uuid.uuid4()}",
            headers={**valid_headers, "X-Request-Id": marker},
        )

        line = _access_lines(marker)[0]
        assert line["status_code"] >= 400
        assert line["tenancies"] == ["datamap/production/data-amazon"]

    def test_several_are_kept_apart(self, http_client, valid_headers):
        marker = f"req-{uuid.uuid4()}"

        http_client.get(
            "/datasets/",
            headers={
                **valid_headers,
                "X-Request-Id": marker,
                "X-Datamap-Tenancies": "datamap/production/data-amazon;datamap/lab",
            },
        )

        assert _access_lines(marker)[0]["tenancies"] == [
            "datamap/production/data-amazon",
            "datamap/lab",
        ]

    def test_a_request_without_one_says_so(self, http_client, valid_headers):
        marker = f"req-{uuid.uuid4()}"

        http_client.get("/health-check/dependencies", headers={"X-Request-Id": marker})

        lines = access_lines(flush_log(http_client, valid_headers), marker)
        assert lines == [] or lines[0]["tenancies"] == []


class TestTheUser:
    """Who made the request, next to which tenancy they made it under. Both are
    identifiers that arrive in headers; neither authenticates anything."""

    def test_it_is_on_the_line(self, http_client, valid_headers):
        marker = f"req-{uuid.uuid4()}"

        http_client.get("/datasets/", headers={**valid_headers, "X-Request-Id": marker})

        assert _access_lines(marker)[0]["user_id"] == valid_headers["X-User-Id"]

    def test_it_is_on_a_line_that_failed(self, http_client, valid_headers):
        marker = f"req-{uuid.uuid4()}"

        http_client.get(
            f"/datasets/{uuid.uuid4()}",
            headers={**valid_headers, "X-Request-Id": marker},
        )

        line = _access_lines(marker)[0]
        assert line["status_code"] >= 400
        assert line["user_id"] == valid_headers["X-User-Id"]

    def test_a_request_without_one_reports_nothing_rather_than_guessing(
        self, http_client, valid_headers
    ):
        marker = f"req-{uuid.uuid4()}"

        http_client.get("/health-check/dependencies", headers={"X-Request-Id": marker})

        lines = access_lines(flush_log(http_client, valid_headers), marker)
        assert lines == [] or lines[0]["user_id"] is None


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

        log = flush_log(http_client, valid_headers)
        assert secret not in log, "a client secret was written to the log"

    def test_the_rest_of_that_body_is_still_logged(self, http_client, valid_headers):
        marker = f"req-{uuid.uuid4()}"
        name = f"client-{uuid.uuid4()}"

        http_client.post(
            "/clients/",
            json={"name": name, "secret": "irrelevant"},
            headers={**valid_headers, "X-Request-Id": marker},
        )

        lines = _access_lines(marker)
        assert lines
        assert lines[0]["body"]["name"] == name
        assert lines[0]["body"]["secret"] == "[redacted]"


class TestHeadersAreNeverLogged:
    def test_no_header_reaches_the_log(self, http_client, valid_headers):
        """Headers carry the credentials. The body may be logged; they may not."""
        http_client.get("/datasets/", headers=valid_headers)

        log = flush_log(http_client, valid_headers)
        assert valid_headers["X-Api-Secret"] not in log
        assert "X-Api-Secret" not in log
