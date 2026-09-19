import unittest

from app.setup import is_probe


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
