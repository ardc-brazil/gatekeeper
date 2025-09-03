"""Pytest configuration and shared fixtures for integration tests."""

import pytest
import requests
from tests.integration.config import config
from tests.integration.utils.http_client import HttpClient
from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.dataset import DatasetFixture


@pytest.fixture(scope="session")
def http_client():
    """HTTP client fixture for making API requests."""
    return HttpClient()


@pytest.fixture(scope="session")
def auth_fixture():
    """Authentication fixture for getting headers."""
    return AuthFixture


@pytest.fixture(scope="session")
def dataset_fixture(http_client):
    """Dataset fixture for creating test datasets."""
    return DatasetFixture(http_client)


@pytest.fixture(scope="session")
def valid_headers(auth_fixture):
    """Valid authentication headers for API requests."""
    return auth_fixture.valid_headers()


@pytest.fixture(scope="session")
def invalid_headers(auth_fixture):
    """Invalid authentication headers for 401 testing."""
    return auth_fixture.invalid_headers()


@pytest.fixture(scope="session")
def no_auth_headers(auth_fixture):
    """Headers without authentication (for public endpoints)."""
    return auth_fixture.no_auth_headers()


@pytest.fixture(scope="session", autouse=True)
def verify_services_running():
    """Verify that required services are running before tests start."""
    # Check API is running
    try:
        response = requests.get(f"{config.base_url}/api/v1/health-check/", timeout=5)
        if response.status_code != 200:
            pytest.skip(
                f"API service not responding correctly. Status: {response.status_code}"
            )
    except requests.exceptions.RequestException as e:
        pytest.skip(
            f"API service not running or not accessible: {config.base_url}/api/v1/health-check/ - {str(e)}"
        )

    # Check WireMock is running
    try:
        response = requests.get(config.get_wiremock_admin_url("health"), timeout=5)
        if response.status_code != 200:
            pytest.skip(
                f"WireMock service not responding correctly. Status: {response.status_code}"
            )
    except requests.exceptions.RequestException as e:
        pytest.skip(
            f"WireMock service not running or not accessible: {config.get_wiremock_admin_url('health')} - {str(e)}"
        )
