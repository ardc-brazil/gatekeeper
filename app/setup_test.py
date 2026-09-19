"""The access line the middleware writes.

Measured in production after the first deploy that carried it: 61 of 91 lines
over ten minutes were the liveness probe, which the Compose healthcheck calls
every ten seconds. A log that is two thirds probe is a log nobody greps, and an
index nobody wants to pay for.
"""

import unittest

from app.setup import is_probe


class TestWhatCountsAsAProbe(unittest.TestCase):
    def test_the_liveness_endpoint_is_a_probe(self):
        self.assertTrue(is_probe("/api/v1/health-check/"))

    def test_the_path_without_the_root_prefix_is_one_too(self):
        self.assertTrue(is_probe("/v1/health-check/"))

    def test_the_dependency_report_is_a_probe_too(self):
        """It has no reader other than a monitor, and a degraded dependency
        writes its own WARNING line, so the access entry adds nothing."""
        self.assertTrue(is_probe("/api/v1/health-check/dependencies"))

    def test_an_ordinary_route_is_not(self):
        self.assertFalse(is_probe("/api/v1/datasets"))

    def test_a_route_that_merely_mentions_it_is_not(self):
        self.assertFalse(is_probe("/api/v1/datasets/health-check-results"))
