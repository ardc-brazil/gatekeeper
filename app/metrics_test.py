"""Counters for the failures that went unnoticed this year.

Nine uploads lost over ninety days, 9.4 million collocation errors, three
public DOIs with no page. Every one was visible in data nobody was looking at.
A log tells whoever is already investigating; a counter is what starts the
investigation.
"""

import unittest

from prometheus_client import CollectorRegistry

from app.metrics import Metrics


class MetricsTestCase(unittest.TestCase):
    def setUp(self):
        self.metrics = Metrics(registry=CollectorRegistry())

    def value(self, name: str, **labels) -> float:
        return self.metrics.registry.get_sample_value(name, labels) or 0.0


class TestUploadHooks(MetricsTestCase):
    """The bug that lost three uploads answered 500 nine times over ninety days
    and nobody was told. This is the line that would have shown it."""

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
    """Three datasets carry a FINDABLE DOI and no snapshot. The failure was
    swallowed for months; this counts it."""

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
    """9.4 million identical errors came from datasets that could never be
    collocated and were retried every minute forever. A backlog that does not
    drain is the shape of that."""

    def test_the_backlog_is_a_gauge_not_a_counter(self):
        self.metrics.collocation_pending(7)
        self.metrics.collocation_pending(3)

        self.assertEqual(self.value("datamap_collocation_pending"), 3.0)

    def test_an_empty_backlog_is_reported_as_zero(self):
        self.metrics.collocation_pending(0)

        self.assertEqual(self.value("datamap_collocation_pending"), 0.0)


class TestRequests(MetricsTestCase):
    def test_requests_are_counted_by_route_and_status(self):
        self.metrics.request("GET", "/v1/datasets", 200, 0.012)
        self.metrics.request("GET", "/v1/datasets", 500, 0.100)

        self.assertEqual(
            self.value(
                "datamap_http_requests_total",
                method="GET",
                path="/v1/datasets",
                status="500",
            ),
            1.0,
        )

    def test_the_duration_is_observed(self):
        self.metrics.request("GET", "/v1/datasets", 200, 0.012)

        self.assertEqual(
            self.value(
                "datamap_http_request_duration_seconds_count",
                method="GET",
                path="/v1/datasets",
            ),
            1.0,
        )

    def test_a_path_with_an_id_in_it_does_not_become_its_own_metric(self):
        """One series per dataset would be a cardinality explosion, which is how
        a metrics backend falls over."""
        self.metrics.request(
            "GET", "/v1/datasets/7a9b5d5e-fa6d-4c18-a42c-34f28f", 200, 0.01
        )
        self.metrics.request(
            "GET", "/v1/datasets/08a711f0-a304-4b05-83ef-c6d41a", 200, 0.01
        )

        self.assertEqual(
            self.value(
                "datamap_http_requests_total",
                method="GET",
                path="/v1/datasets/{id}",
                status="200",
            ),
            2.0,
        )


class TestExposition(MetricsTestCase):
    def test_it_renders_in_the_prometheus_text_format(self):
        self.metrics.tus_hook("post-finish", 500)

        rendered = self.metrics.render().decode()

        self.assertIn("datamap_tus_hook_total", rendered)
        self.assertIn('outcome="error"', rendered)
