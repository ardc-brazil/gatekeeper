import unittest

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY, generate_latest

from app.setup import is_probe, setup_middleware


class TestWhatCountsAsAProbe(unittest.TestCase):
    def test_the_liveness_endpoint_is_a_probe(self):
        self.assertTrue(is_probe("/api/v1/health-check/"))

    def test_the_path_without_the_root_prefix_is_one_too(self):
        self.assertTrue(is_probe("/v1/health-check/"))

    def test_the_dependency_report_is_a_probe_too(self):
        self.assertTrue(is_probe("/api/v1/health-check/dependencies"))

    def test_an_ordinary_route_is_not(self):
        self.assertFalse(is_probe("/api/v1/datasets"))

    def test_a_route_that_merely_mentions_it_is_not(self):
        self.assertFalse(is_probe("/api/v1/datasets/health-check-results"))


def _sample(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


class TestRequestMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI(root_path="/api")
        setup_middleware(app)

        @app.get("/v1/things/{thing_id}")
        def get_thing(thing_id: str, request: Request):
            request.state.client_name = "metrics-test-client"
            return {"id": thing_id}

        @app.get("/v1/health-check/")
        def health():
            return {}

        @app.get("/v1/broken")
        def broken():
            raise RuntimeError("boom")

        cls.client = TestClient(app, raise_server_exceptions=False)

    def count(self, route: str, status: str, client: str) -> float:
        return _sample(
            "datamap_http_requests_total",
            method="GET",
            route=route,
            status=status,
            client=client,
        )

    def test_the_route_template_is_the_label_not_the_path_with_its_id(self):
        before = self.count("/api/v1/things/{thing_id}", "200", "metrics-test-client")

        self.client.get("/api/v1/things/a-tenancy-name")
        self.client.get("/api/v1/things/another-one")

        after = self.count("/api/v1/things/{thing_id}", "200", "metrics-test-client")
        self.assertEqual(after, before + 2)
        self.assertNotIn(b"a-tenancy-name", generate_latest(REGISTRY))

    def test_a_path_that_matches_no_route_is_filed_as_unmatched(self):
        before = self.count("unmatched", "404", "none")

        self.client.get("/api/v1/does-not-exist/some-id")

        self.assertEqual(self.count("unmatched", "404", "none"), before + 1)

    def test_a_handler_that_raises_is_counted_as_a_500_on_its_route(self):
        before = self.count("/api/v1/broken", "500", "none")

        self.client.get("/api/v1/broken")

        self.assertEqual(self.count("/api/v1/broken", "500", "none"), before + 1)

    def test_probes_are_not_counted(self):
        before = self.count("/api/v1/health-check/", "200", "none")

        self.client.get("/api/v1/health-check/")

        self.assertEqual(self.count("/api/v1/health-check/", "200", "none"), before)

    def test_the_response_size_is_observed(self):
        labels = {"method": "GET", "route": "/api/v1/things/{thing_id}"}
        before = _sample("datamap_http_response_size_bytes_count", **labels)

        self.client.get("/api/v1/things/x")

        self.assertEqual(
            _sample("datamap_http_response_size_bytes_count", **labels), before + 1
        )
