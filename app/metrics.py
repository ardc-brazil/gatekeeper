"""Counters for the failures that went unnoticed.

Every serious problem found in September 2026 was already visible in data
nobody was looking at: nine uploads lost over ninety days, 9.4 million
collocation errors, 169 restarts, three public DOIs with no page. Structured
logs tell whoever is already investigating. A counter with an alert is what
starts the investigation.

Plain `prometheus_client` rather than an instrumentation framework: the
middleware already measures what an instrumentator would, and one dependency
that does nothing surprising beats a second middleware stack.
"""

import re

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

_UUID = re.compile(
    r"/[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{6,12}",
    re.IGNORECASE,
)


def normalise_path(path: str) -> str:
    """One series per dataset id would be a cardinality explosion, which is how
    a metrics backend falls over."""
    return _UUID.sub("/{id}", path)


class Metrics:
    def __init__(self, registry: CollectorRegistry = None) -> None:
        self.registry = registry if registry is not None else CollectorRegistry()

        self._requests = Counter(
            "datamap_http_requests_total",
            "HTTP requests served",
            ["method", "path", "status"],
            registry=self.registry,
        )
        self._duration = Histogram(
            "datamap_http_request_duration_seconds",
            "Time spent serving a request",
            ["method", "path"],
            registry=self.registry,
        )
        self._tus_hooks = Counter(
            "datamap_tus_hook_total",
            "TUS hooks received",
            ["hook_type", "outcome"],
            registry=self.registry,
        )
        self._snapshots = Counter(
            "datamap_snapshot_publish_total",
            "Dataset snapshots published",
            ["outcome"],
            registry=self.registry,
        )
        self._collocation_pending = Gauge(
            "datamap_collocation_pending",
            "Datasets waiting for their files to be collocated",
            registry=self.registry,
        )

    def request(self, method: str, path: str, status: int, seconds: float) -> None:
        normalised = normalise_path(path)
        self._requests.labels(method=method, path=normalised, status=str(status)).inc()
        self._duration.labels(method=method, path=normalised).observe(seconds)

    def tus_hook(self, hook_type: str, status: int) -> None:
        if status >= 500:
            outcome = "error"
        elif status >= 400:
            outcome = "rejected"
        else:
            outcome = "accepted"
        self._tus_hooks.labels(hook_type=hook_type or "unknown", outcome=outcome).inc()

    def snapshot_published(self, success: bool) -> None:
        self._snapshots.labels(outcome="success" if success else "error").inc()

    def collocation_pending(self, count: int) -> None:
        self._collocation_pending.set(count)

    def render(self) -> bytes:
        return generate_latest(self.registry)


# One per process, which is what a registry is. Tests build their own.
metrics = Metrics(registry=REGISTRY)
