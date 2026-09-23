"""HTTP client wrapper for integration tests."""

import requests
from requests.adapters import HTTPAdapter
from typing import Dict, Optional
from urllib3.util import Retry

from tests.integration.config import config


class HttpClient:
    """HTTP client wrapper for making API requests during integration tests."""

    def __init__(self):
        """Initialize HTTP client with test configuration."""
        self.base_url = config.base_url
        self.timeout = config.timeout
        self.session = requests.Session()
        # requests defaults to no retries at all, so a connection closed
        # between being picked from the pool and being written to surfaces as a
        # test failure. `read=0` on purpose: a slow endpoint must still fail.
        self.session.mount(
            "http://",
            HTTPAdapter(
                max_retries=Retry(
                    total=3,
                    connect=3,
                    read=0,
                    status=0,
                    allowed_methods=None,
                    backoff_factor=0.2,
                )
            ),
        )

    def _make_request(
        self, method: str, path: str, headers: Optional[Dict[str, str]] = None, **kwargs
    ) -> requests.Response:
        """Make HTTP request to the API."""
        url = config.get_api_url(path)

        # Set default headers
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)

        # Add timeout if not specified
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout

        try:
            response = self.session.request(
                method=method, url=url, headers=request_headers, **kwargs
            )
            return response
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {method} {url} - {str(e)}")

    def get(
        self, path: str, headers: Optional[Dict[str, str]] = None, **kwargs
    ) -> requests.Response:
        """Make GET request."""
        return self._make_request("GET", path, headers, **kwargs)

    def post(
        self, path: str, headers: Optional[Dict[str, str]] = None, **kwargs
    ) -> requests.Response:
        """Make POST request."""
        return self._make_request("POST", path, headers, **kwargs)

    def put(
        self, path: str, headers: Optional[Dict[str, str]] = None, **kwargs
    ) -> requests.Response:
        """Make PUT request."""
        return self._make_request("PUT", path, headers, **kwargs)

    def delete(
        self, path: str, headers: Optional[Dict[str, str]] = None, **kwargs
    ) -> requests.Response:
        """Make DELETE request."""
        return self._make_request("DELETE", path, headers, **kwargs)

    def head(
        self, path: str, headers: Optional[Dict[str, str]] = None, **kwargs
    ) -> requests.Response:
        """Make HEAD request."""
        return self._make_request("HEAD", path, headers, **kwargs)

    def patch(
        self, path: str, headers: Optional[Dict[str, str]] = None, **kwargs
    ) -> requests.Response:
        """Make PATCH request."""
        return self._make_request("PATCH", path, headers, **kwargs)
