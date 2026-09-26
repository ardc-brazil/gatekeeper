import logging
from time import monotonic
from typing import Callable, Iterator

from prometheus_client.core import GaugeMetricFamily, Metric

from app.repository.platform_state import PlatformStateRepository


class PlatformStateCollector:
    """Platform totals read from the database when Prometheus scrapes.

    Cached, so a 15-second scrape costs a few GROUP BYs a minute. Both instances
    report the same numbers: dashboards take max(), never sum().
    """

    def __init__(
        self,
        repository: PlatformStateRepository,
        ttl_seconds: float = 60,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._logger = logging.getLogger("metrics:platform_state")
        self._repository = repository
        self._ttl = ttl_seconds
        self._clock = clock
        self._cached: list[Metric] | None = None
        self._read_at = 0.0

    def describe(self) -> list[Metric]:
        # Registering must not query the database.
        return []

    def collect(self) -> Iterator[Metric]:
        if self._cached is None or self._clock() - self._read_at >= self._ttl:
            try:
                self._cached = self._read()
                self._read_at = self._clock()
            except Exception:
                # A failed read must not fail the scrape: the other metrics
                # are the ones that say what is wrong.
                self._logger.warning("could not read the platform state", exc_info=True)
                return iter(self._cached or [])
        return iter(self._cached)

    def _read(self) -> list[Metric]:
        datasets = GaugeMetricFamily(
            "datamap_datasets",
            "Enabled datasets",
            labels=["tenancy", "design_state", "visibility"],
        )
        for tenancy, state, visibility, count in self._repository.datasets():
            datasets.add_metric([str(tenancy), str(state), str(visibility)], count)

        file_count, stored_bytes = self._repository.files()
        files = GaugeMetricFamily(
            "datamap_data_files", "Files recorded", value=file_count
        )
        stored = GaugeMetricFamily(
            "datamap_stored_bytes", "Size of every file recorded", value=stored_bytes
        )

        users = GaugeMetricFamily("datamap_users", "Users", labels=["enabled"])
        for enabled, count in self._repository.users():
            users.add_metric(["true" if enabled else "false"], count)

        dois = GaugeMetricFamily("datamap_dois", "DOIs by state", labels=["state"])
        for state, count in self._repository.dois():
            dois.add_metric([str(state)], count)

        return [datasets, files, stored, users, dois]
