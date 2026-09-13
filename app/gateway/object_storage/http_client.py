import urllib3
from urllib3.util import Retry, Timeout


def build_http_client(timeout_seconds: int, retries: int) -> urllib3.PoolManager:
    """The pool minio-py would otherwise build for itself, with the timeouts
    bounded. Its defaults are five minutes and five retries, which turns an
    unreachable object storage into a request worker held for twenty-five."""
    return urllib3.PoolManager(
        timeout=Timeout(connect=timeout_seconds, read=timeout_seconds),
        retries=Retry(
            total=retries,
            backoff_factor=0.2,
            status_forcelist=[500, 502, 503, 504],
        ),
    )
