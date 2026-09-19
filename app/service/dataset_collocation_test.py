"""What the collocation service says while nothing is happening.

The Archivist polls `/internal/datasets/collocation/pending` every minute, and
this service wrote two INFO lines for each of those, forever. After the probe
lines were removed, it was the largest remaining source in the production log:
six of seventeen lines over ten minutes, all of them saying nothing happened.
"""

import logging
import unittest
from unittest.mock import MagicMock

from app.service.dataset_collocation import DatasetCollocationService


class TestPollingAnEmptyQueue(unittest.TestCase):
    def setUp(self):
        self.repository = MagicMock()
        self.service = DatasetCollocationService(
            dataset_repository=self.repository,
            datafile_repository=MagicMock(),
        )

    def test_nothing_is_said_at_info_when_there_is_nothing_pending(self):
        self.repository.fetch_by_collocation_status.return_value = []

        with self.assertRaises(AssertionError):
            with self.assertLogs("service:DatasetCollocationService", level="INFO"):
                self.service.get_pending_datasets()

    def test_work_waiting_is_worth_a_line(self):
        self.repository.fetch_by_collocation_status.return_value = [MagicMock()]

        with self.assertLogs(
            "service:DatasetCollocationService", level="INFO"
        ) as captured:
            self.service.get_pending_datasets()

        self.assertIn("pending collocation", captured.output[0])

    def test_the_line_says_how_many(self):
        self.repository.fetch_by_collocation_status.return_value = [
            MagicMock(),
            MagicMock(),
        ]

        with self.assertLogs(
            "service:DatasetCollocationService", level="INFO"
        ) as captured:
            self.service.get_pending_datasets()

        self.assertEqual(captured.records[0].count, 2)

    def test_the_empty_poll_is_still_visible_at_debug(self):
        self.repository.fetch_by_collocation_status.return_value = []

        with self.assertLogs(
            "service:DatasetCollocationService", level=logging.DEBUG
        ) as captured:
            self.service.get_pending_datasets()

        self.assertTrue(captured.output)
