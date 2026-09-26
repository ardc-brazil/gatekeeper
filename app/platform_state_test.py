import unittest
from unittest.mock import Mock

from prometheus_client import CollectorRegistry

from app.platform_state import PlatformStateCollector


def _repository() -> Mock:
    repository = Mock()
    repository.datasets.return_value = [
        ("datamap/production/amazon-face", "PUBLISHED", "PUBLIC", 4)
    ]
    repository.files.return_value = (10, 2048)
    repository.users.return_value = [(True, 7), (False, 1)]
    repository.dois.return_value = [("FINDABLE", 3)]
    return repository


class TestPlatformState(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.repository = _repository()
        self.registry = CollectorRegistry()
        self.registry.register(
            PlatformStateCollector(
                self.repository, ttl_seconds=60, clock=lambda: self.now
            )
        )

    def value(self, name: str, **labels) -> float | None:
        return self.registry.get_sample_value(name, labels)

    def test_the_totals_are_exposed(self):
        self.assertEqual(
            self.value(
                "datamap_datasets",
                tenancy="datamap/production/amazon-face",
                design_state="PUBLISHED",
                visibility="PUBLIC",
            ),
            4.0,
        )
        self.assertEqual(self.value("datamap_stored_bytes"), 2048.0)
        self.assertEqual(self.value("datamap_users", enabled="false"), 1.0)
        self.assertEqual(self.value("datamap_dois", state="FINDABLE"), 3.0)

    def test_registering_does_not_query_the_database(self):
        repository = _repository()

        CollectorRegistry().register(PlatformStateCollector(repository))

        repository.datasets.assert_not_called()

    def test_a_scrape_within_the_ttl_is_served_from_the_cache(self):
        self.value("datamap_data_files")
        self.now += 30
        self.value("datamap_data_files")

        self.assertEqual(self.repository.files.call_count, 1)

    def test_after_the_ttl_the_database_is_read_again(self):
        self.value("datamap_data_files")
        self.now += 61
        self.value("datamap_data_files")

        self.assertEqual(self.repository.files.call_count, 2)

    def test_a_failed_read_keeps_the_last_numbers_and_does_not_fail_the_scrape(self):
        self.value("datamap_data_files")
        self.repository.files.side_effect = RuntimeError("database is down")
        self.now += 61

        self.assertEqual(self.value("datamap_data_files"), 10.0)
