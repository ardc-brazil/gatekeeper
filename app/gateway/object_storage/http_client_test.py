import unittest

from app.gateway.object_storage.http_client import build_http_client


class TestObjectStorageHttpClient(unittest.TestCase):
    def test_the_read_timeout_is_bounded(self):
        client = build_http_client(timeout_seconds=10, retries=2)

        self.assertEqual(client.connection_pool_kw["timeout"].read_timeout, 10)

    def test_the_connect_timeout_is_bounded(self):
        client = build_http_client(timeout_seconds=10, retries=2)

        self.assertEqual(client.connection_pool_kw["timeout"].connect_timeout, 10)

    def test_retries_are_bounded(self):
        client = build_http_client(timeout_seconds=10, retries=2)

        self.assertEqual(client.connection_pool_kw["retries"].total, 2)

    def test_the_worst_case_is_a_small_multiple_of_the_timeout(self):
        timeout, retries = 10, 2

        client = build_http_client(timeout_seconds=timeout, retries=retries)

        worst_case = client.connection_pool_kw["timeout"].read_timeout * (
            client.connection_pool_kw["retries"].total + 1
        )
        self.assertLessEqual(worst_case, 60)
