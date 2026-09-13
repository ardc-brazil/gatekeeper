import unittest
from unittest.mock import MagicMock

from app.service.health import DependencyHealthService


class TestDependencyHealth(unittest.TestCase):
    """ "I can't upload" has had at least two causes, the tenancy filter and
    MinIO being down, and no way to tell them apart without a shell on the
    host. This is what the curation team reads instead."""

    def setUp(self):
        self.database = MagicMock()
        self.object_storage = MagicMock()
        self.service = DependencyHealthService(
            database=self.database,
            object_storage=self.object_storage,
            bucket="datamap",
        )

    def test_everything_up_reports_healthy(self):
        report = self.service.check()

        self.assertEqual(report["status"], "healthy")
        self.assertEqual(report["checks"]["database"]["status"], "up")
        self.assertEqual(report["checks"]["object_storage"]["status"], "up")

    def test_a_dead_database_is_named(self):
        self.database.session.side_effect = OSError("connection refused")

        report = self.service.check()

        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["checks"]["database"]["status"], "down")
        self.assertIn("connection refused", report["checks"]["database"]["error"])

    def test_a_dead_object_storage_is_named(self):
        self.object_storage.bucket_exists.side_effect = OSError("no route to host")

        report = self.service.check()

        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["checks"]["object_storage"]["status"], "down")
        self.assertIn("no route to host", report["checks"]["object_storage"]["error"])

    def test_one_dependency_down_does_not_hide_the_other(self):
        self.object_storage.bucket_exists.side_effect = OSError("no route to host")

        report = self.service.check()

        self.assertEqual(report["checks"]["database"]["status"], "up")

    def test_a_missing_bucket_is_not_the_same_as_storage_being_down(self):
        self.object_storage.bucket_exists.return_value = False

        report = self.service.check()

        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["checks"]["object_storage"]["status"], "bucket_missing")

    def test_each_check_reports_how_long_it_took(self):
        report = self.service.check()

        for check in report["checks"].values():
            self.assertIsInstance(check["latency_ms"], float)

    def test_a_degraded_dependency_is_written_to_the_log(self):
        """The access line for this endpoint is suppressed, so this WARNING is
        the only trace a degraded dependency leaves. It has to exist."""
        self.object_storage.bucket_exists.side_effect = OSError("no route to host")

        with self.assertLogs("service:health", level="WARNING") as captured:
            self.service.check()

        self.assertIn("dependency check degraded", captured.output[0])

    def test_that_line_names_which_dependency(self):
        self.object_storage.bucket_exists.side_effect = OSError("no route to host")

        with self.assertLogs("service:health", level="WARNING") as captured:
            self.service.check()

        self.assertEqual(captured.records[0].degraded, ["object_storage"])

    def test_nothing_is_logged_while_everything_answers(self):
        with self.assertRaises(AssertionError):
            with self.assertLogs("service:health", level="WARNING"):
                self.service.check()

    def test_a_credential_in_the_error_is_not_passed_through(self):
        self.database.session.side_effect = OSError(
            "could not connect: password=hunter2"
        )

        report = self.service.check()

        self.assertNotIn("hunter2", report["checks"]["database"]["error"])
