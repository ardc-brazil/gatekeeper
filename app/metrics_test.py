import unittest

from prometheus_client import CollectorRegistry

from app.metrics import Metrics


class MetricsTestCase(unittest.TestCase):
    def setUp(self):
        self.metrics = Metrics(registry=CollectorRegistry())

    def value(self, name: str, **labels) -> float:
        return self.metrics.registry.get_sample_value(name, labels) or 0.0


class TestUploadHooks(MetricsTestCase):
    def test_a_rejected_hook_is_counted_apart_from_an_accepted_one(self):
        self.metrics.tus_hook("post-finish", 200)
        self.metrics.tus_hook("post-finish", 500)
        self.metrics.tus_hook("post-finish", 500)

        self.assertEqual(
            self.value(
                "datamap_tus_hook_total", hook_type="post-finish", outcome="error"
            ),
            2.0,
        )
        self.assertEqual(
            self.value(
                "datamap_tus_hook_total", hook_type="post-finish", outcome="accepted"
            ),
            1.0,
        )

    def test_each_hook_type_is_counted_separately(self):
        self.metrics.tus_hook("pre-create", 200)
        self.metrics.tus_hook("post-finish", 200)

        self.assertEqual(
            self.value(
                "datamap_tus_hook_total", hook_type="pre-create", outcome="accepted"
            ),
            1.0,
        )

    def test_a_client_error_is_not_filed_as_a_server_error(self):
        self.metrics.tus_hook("post-finish", 401)

        self.assertEqual(
            self.value(
                "datamap_tus_hook_total", hook_type="post-finish", outcome="rejected"
            ),
            1.0,
        )


class TestSnapshotPublication(MetricsTestCase):
    def test_a_failed_publication_is_counted(self):
        self.metrics.snapshot_published(success=False)

        self.assertEqual(
            self.value("datamap_snapshot_publish_total", outcome="error"), 1.0
        )

    def test_a_successful_one_is_counted_apart(self):
        self.metrics.snapshot_published(success=True)

        self.assertEqual(
            self.value("datamap_snapshot_publish_total", outcome="success"), 1.0
        )


class TestCollocationBacklog(MetricsTestCase):
    def test_the_backlog_is_a_gauge_not_a_counter(self):
        self.metrics.collocation_pending(7)
        self.metrics.collocation_pending(3)

        self.assertEqual(self.value("datamap_collocation_pending"), 3.0)

    def test_an_empty_backlog_is_reported_as_zero(self):
        self.metrics.collocation_pending(0)

        self.assertEqual(self.value("datamap_collocation_pending"), 0.0)


class TestRequests(MetricsTestCase):
    def test_requests_are_counted_by_route_status_and_client(self):
        self.metrics.request("GET", "/v1/datasets/{id}", 200, 0.012, client="webapp")
        self.metrics.request("GET", "/v1/datasets/{id}", 500, 0.100, client="webapp")

        self.assertEqual(
            self.value(
                "datamap_http_requests_total",
                method="GET",
                route="/v1/datasets/{id}",
                status="500",
                client="webapp",
            ),
            1.0,
        )

    def test_a_request_with_no_authenticated_client_is_filed_under_none(self):
        self.metrics.request("GET", "/v1/datasets/{id}/snapshot", 200, 0.01)

        self.assertEqual(
            self.value(
                "datamap_http_requests_total",
                method="GET",
                route="/v1/datasets/{id}/snapshot",
                status="200",
                client="none",
            ),
            1.0,
        )

    def test_the_duration_is_observed(self):
        self.metrics.request("GET", "/v1/datasets", 200, 0.012)

        self.assertEqual(
            self.value(
                "datamap_http_request_duration_seconds_count",
                method="GET",
                route="/v1/datasets",
            ),
            1.0,
        )

    def test_a_slow_request_lands_in_a_bucket_above_ten_seconds(self):
        self.metrics.request("GET", "/v1/datasets", 200, 20.0)

        self.assertEqual(
            self.value(
                "datamap_http_request_duration_seconds_bucket",
                method="GET",
                route="/v1/datasets",
                le="10.0",
            ),
            0.0,
        )
        self.assertEqual(
            self.value(
                "datamap_http_request_duration_seconds_bucket",
                method="GET",
                route="/v1/datasets",
                le="30.0",
            ),
            1.0,
        )

    def test_request_and_response_sizes_are_observed(self):
        self.metrics.request(
            "POST", "/v1/datasets", 201, 0.05, request_bytes=900, response_bytes=40
        )

        self.assertEqual(
            self.value(
                "datamap_http_request_size_bytes_sum",
                method="POST",
                route="/v1/datasets",
            ),
            900.0,
        )
        self.assertEqual(
            self.value(
                "datamap_http_response_size_bytes_sum",
                method="POST",
                route="/v1/datasets",
            ),
            40.0,
        )

    def test_an_unknown_size_is_not_observed_as_zero(self):
        self.metrics.request("GET", "/v1/datasets", 200, 0.05)

        self.assertEqual(
            self.value(
                "datamap_http_response_size_bytes_count",
                method="GET",
                route="/v1/datasets",
            ),
            0.0,
        )

    def test_requests_in_progress_are_counted_while_they_run(self):
        with self.metrics.in_progress("GET"):
            self.assertEqual(
                self.value("datamap_http_requests_in_progress", method="GET"), 1.0
            )

        self.assertEqual(
            self.value("datamap_http_requests_in_progress", method="GET"), 0.0
        )


class ReadTimeoutError(Exception):
    pass


class MaxRetryError(Exception):
    def __init__(self, reason):
        self.reason = reason


class HTTPError(Exception):
    def __init__(self, status):
        self.response = type("Response", (), {"status": status})()


class TestExternalCalls(MetricsTestCase):
    def outcome_count(self, outcome: str) -> float:
        return self.value(
            "datamap_external_request_duration_seconds_count",
            service="datacite",
            operation="doi.create",
            outcome=outcome,
        )

    def test_a_call_that_returns_is_a_success(self):
        with self.metrics.external_call("datacite", "doi.create"):
            pass

        self.assertEqual(self.outcome_count("success"), 1.0)

    def test_the_status_it_answered_with_decides_the_outcome(self):
        with self.assertRaises(RuntimeError):
            with self.metrics.external_call("datacite", "doi.create") as call:
                call.status = 422
                raise RuntimeError("Error creating DOI")

        self.assertEqual(self.outcome_count("client_error"), 1.0)

    def test_a_5xx_is_a_server_error(self):
        with self.metrics.external_call("datacite", "doi.create") as call:
            call.status = 503

        self.assertEqual(self.outcome_count("server_error"), 1.0)

    def test_an_unexpected_2xx_that_the_caller_rejects_is_an_error(self):
        with self.assertRaises(RuntimeError):
            with self.metrics.external_call("datacite", "doi.create") as call:
                call.status = 200
                raise RuntimeError("expected 201")

        self.assertEqual(self.outcome_count("error"), 1.0)

    def test_a_timeout_is_told_apart_from_other_failures(self):
        with self.assertRaises(ReadTimeoutError):
            with self.metrics.external_call("datacite", "doi.create"):
                raise ReadTimeoutError()

        self.assertEqual(self.outcome_count("timeout"), 1.0)

    def test_a_timeout_wrapped_in_a_retry_error_is_still_a_timeout(self):
        with self.assertRaises(MaxRetryError):
            with self.metrics.external_call("datacite", "doi.create"):
                raise MaxRetryError(ReadTimeoutError())

        self.assertEqual(self.outcome_count("timeout"), 1.0)

    def test_the_status_carried_by_an_exception_is_used(self):
        with self.assertRaises(HTTPError):
            with self.metrics.external_call("datacite", "doi.create"):
                raise HTTPError(404)

        self.assertEqual(self.outcome_count("client_error"), 1.0)

    def test_any_other_exception_is_an_error(self):
        with self.assertRaises(ConnectionError):
            with self.metrics.external_call("datacite", "doi.create"):
                raise ConnectionError()

        self.assertEqual(self.outcome_count("error"), 1.0)


class TestConnectionPool(MetricsTestCase):
    def test_the_pool_is_read_when_scraped_not_when_registered(self):
        pool = type(
            "Pool",
            (),
            {
                "checkedout": lambda self: 3,
                "checkedin": lambda self: 2,
                "overflow": lambda self: -1,
                "size": lambda self: 5,
            },
        )()
        self.metrics.watch_pool(pool)

        self.assertEqual(
            self.value("datamap_db_pool_connections", state="checked_out"), 3.0
        )
        self.assertEqual(self.value("datamap_db_pool_connections", state="idle"), 2.0)
        self.assertEqual(self.value("datamap_db_pool_size"), 5.0)

    def test_overflow_is_never_reported_below_zero(self):
        pool = type(
            "Pool",
            (),
            {
                "checkedout": lambda self: 0,
                "checkedin": lambda self: 0,
                "overflow": lambda self: -5,
                "size": lambda self: 5,
            },
        )()
        self.metrics.watch_pool(pool)

        self.assertEqual(
            self.value("datamap_db_pool_connections", state="overflow"), 0.0
        )


class TestBusinessEvents(MetricsTestCase):
    def test_dataset_actions_are_counted_by_action(self):
        self.metrics.dataset_event("created")
        self.metrics.dataset_event("version_published")

        self.assertEqual(
            self.value("datamap_dataset_events_total", action="created"), 1.0
        )

    def test_a_search_is_counted_by_what_it_asked_and_whether_it_found_anything(self):
        self.metrics.search(has_text=True, has_filters=False, found=0)

        self.assertEqual(
            self.value(
                "datamap_search_total",
                has_text="true",
                has_filters="false",
                empty="true",
            ),
            1.0,
        )

    def test_an_issued_download_counts_the_url_and_its_bytes(self):
        self.metrics.download_url_issued("datamap/production/amazon-face", "csv", 2048)
        self.metrics.download_url_issued("datamap/production/amazon-face", "csv", 1024)

        self.assertEqual(
            self.value(
                "datamap_download_urls_issued_total",
                tenancy="datamap/production/amazon-face",
                format="csv",
            ),
            2.0,
        )
        self.assertEqual(
            self.value(
                "datamap_download_bytes_issued_total",
                tenancy="datamap/production/amazon-face",
            ),
            3072.0,
        )

    def test_a_completed_upload_counts_the_file_and_its_bytes(self):
        self.metrics.upload_completed("datamap/staging/data-amazon", "nc", 500)

        self.assertEqual(
            self.value(
                "datamap_uploads_completed_total",
                tenancy="datamap/staging/data-amazon",
                format="nc",
            ),
            1.0,
        )
        self.assertEqual(
            self.value(
                "datamap_upload_bytes_total", tenancy="datamap/staging/data-amazon"
            ),
            500.0,
        )

    def test_a_format_nobody_expects_does_not_become_its_own_series(self):
        self.metrics.upload_completed("t", "x-evil-" + "a" * 50, 1)
        self.metrics.upload_completed("t", "application/x-netcdf", 1)

        self.assertEqual(
            self.value("datamap_uploads_completed_total", tenancy="t", format="other"),
            2.0,
        )

    def test_the_format_is_normalised_from_an_extension(self):
        self.metrics.upload_completed("t", ".XLSX", 1)

        self.assertEqual(
            self.value("datamap_uploads_completed_total", tenancy="t", format="xlsx"),
            1.0,
        )

    def test_a_missing_tenancy_is_filed_as_none(self):
        self.metrics.upload_completed(None, "csv", 1)

        self.assertEqual(
            self.value("datamap_uploads_completed_total", tenancy="none", format="csv"),
            1.0,
        )

    def test_doi_operations_are_counted_with_their_outcome(self):
        self.metrics.doi_operation("create", success=False, mode="MANUAL")

        self.assertEqual(
            self.value(
                "datamap_doi_operations_total",
                operation="create",
                mode="MANUAL",
                outcome="error",
            ),
            1.0,
        )


class TestAuthFailures(MetricsTestCase):
    def test_a_failure_is_counted_by_where_and_why(self):
        self.metrics.auth_failure("authz", "not_authorized")

        self.assertEqual(
            self.value(
                "datamap_auth_failures_total", kind="authz", reason="not_authorized"
            ),
            1.0,
        )

    def test_an_unknown_reason_does_not_become_its_own_series(self):
        self.metrics.auth_failure("tus", "some message with an id 1234")

        self.assertEqual(
            self.value("datamap_auth_failures_total", kind="tus", reason="other"), 1.0
        )


class TestEmail(MetricsTestCase):
    def test_each_outcome_is_counted_per_template(self):
        self.metrics.email_outcome("invitation", "sent")
        self.metrics.email_outcome("invitation", "sent")
        self.metrics.email_outcome("invitation", "failed")

        self.assertEqual(
            self.value("datamap_emails_total", template="invitation", outcome="sent"),
            2.0,
        )
        self.assertEqual(
            self.value("datamap_emails_total", template="invitation", outcome="failed"),
            1.0,
        )

    def test_the_pending_gauge_shows_the_last_count(self):
        self.metrics.email_pending(7)
        self.metrics.email_pending(3)

        self.assertEqual(self.value("datamap_email_pending"), 3.0)


class TestExposition(MetricsTestCase):
    def test_it_renders_in_the_prometheus_text_format(self):
        self.metrics.tus_hook("post-finish", 500)

        rendered = self.metrics.render().decode()

        self.assertIn("datamap_tus_hook_total", rendered)
        self.assertIn('outcome="error"', rendered)
