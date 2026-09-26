import urllib3
from urllib3.util import Retry, Timeout


def build_http_client(
    connect_timeout_seconds: float, read_timeout_seconds: float, retries: int
) -> urllib3.PoolManager:
    """The pool minio-py would build for itself, with the timeouts bounded."""
    return urllib3.PoolManager(
        timeout=Timeout(connect=connect_timeout_seconds, read=read_timeout_seconds),
        retries=Retry(
            total=retries,
            connect=0,
            backoff_factor=0.2,
            status_forcelist=[500, 502, 503, 504],
        ),
    )
