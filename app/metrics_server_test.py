import unittest
import urllib.error
import urllib.request

from prometheus_client import CollectorRegistry

from app.metrics import Metrics
from app.metrics_server import start_metrics_server


def _free_port() -> int:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class TestMetricsServer(unittest.TestCase):
    """Prometheus cannot send this API's headers — scrape configs carry basic
    auth or a bearer token, not X-Api-Key and X-Api-Secret. The metrics live on
    a port of their own, published to no host, so the docker network is the
    boundary instead of an authorisation check."""

    def setUp(self):
        self.metrics = Metrics(registry=CollectorRegistry())
        self.port = _free_port()
        self.server = start_metrics_server(self.port, registry=self.metrics.registry)
        self.addCleanup(self.server.shutdown)

    def _get(self, path: str = "/metrics") -> str:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}{path}", timeout=5
        ) as response:
            return response.read().decode()

    def test_it_serves_the_registry_it_was_given(self):
        self.metrics.tus_hook("post-finish", 500)

        self.assertIn(
            'datamap_tus_hook_total{hook_type="post-finish",outcome="error"}',
            self._get(),
        )

    def test_it_answers_on_the_root_path_too(self):
        """Scrape configs default to /metrics, but a misconfigured one should
        get an answer rather than a puzzle."""
        self.metrics.tus_hook("post-finish", 200)

        self.assertIn("datamap_tus_hook_total", self._get("/"))

    def test_it_reflects_later_changes(self):
        before = self._get()
        self.metrics.snapshot_published(success=False)

        self.assertNotIn('datamap_snapshot_publish_total{outcome="error"} 1.0', before)
        self.assertIn(
            'datamap_snapshot_publish_total{outcome="error"} 1.0', self._get()
        )

    def test_it_falls_back_to_the_global_registry(self):
        """main.py starts it without one, and `make_wsgi_app(None)` serves a 500
        rather than defaulting."""
        port = _free_port()
        server = start_metrics_server(port)
        self.addCleanup(server.shutdown)

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/metrics", timeout=5
        ) as response:
            self.assertEqual(response.status, 200)

    def test_it_stops_when_asked(self):
        self.server.shutdown()

        with self.assertRaises(urllib.error.URLError):
            self._get()
