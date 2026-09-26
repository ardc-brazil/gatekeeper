import unittest
from unittest.mock import patch

import urllib3

from app.gateway.object_storage.http_client import build_http_client


def _client(connect: float = 2, read: float = 10, retries: int = 2):
    return build_http_client(
        connect_timeout_seconds=connect, read_timeout_seconds=read, retries=retries
    )


class TestObjectStorageHttpClient(unittest.TestCase):
    def test_the_read_timeout_is_bounded(self):
        self.assertEqual(
            _client(read=10).connection_pool_kw["timeout"].read_timeout, 10
        )

    def test_the_connect_timeout_is_its_own_shorter_bound(self):
        timeout = _client(connect=2, read=10).connection_pool_kw["timeout"]

        self.assertEqual(timeout.connect_timeout, 2)

    def test_retries_are_bounded(self):
        self.assertEqual(_client(retries=2).connection_pool_kw["retries"].total, 2)

    def test_a_storage_that_cannot_be_reached_is_tried_once(self):
        """A name that does not resolve or a refused connection means the
        container is gone; asking again 200ms later only makes the caller wait."""
        client = _client(retries=2)

        with patch(
            "urllib3.connection.connection.create_connection",
            side_effect=OSError("unreachable"),
        ) as connect:
            with self.assertRaises(urllib3.exceptions.MaxRetryError):
                client.request("GET", "http://minio:9000/datamap")

        self.assertEqual(connect.call_count, 1)

    def test_a_server_error_is_still_retried(self):
        self.assertIn(503, _client().connection_pool_kw["retries"].status_forcelist)
