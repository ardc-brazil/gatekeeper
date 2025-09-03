"""Integration test configuration management."""
import os
from typing import Optional


class IntegrationTestConfig:
    """Configuration for integration tests."""
    
    def __init__(self):
        """Initialize configuration from environment variables."""
        self.base_url = os.getenv("INTEGRATION_BASE_URL", "http://localhost:9094")
        self.timeout = int(os.getenv("INTEGRATION_TIMEOUT", "30"))
        self.api_key = os.getenv("INTEGRATION_API_KEY", "5060b1a2-9aaf-48db-871a-0839007fd478")
        self.api_secret = os.getenv("INTEGRATION_API_SECRET", "g*aZkbWom3deiAX-vtoT")
        self.user_id = os.getenv("INTEGRATION_USER_ID", "cbb0a683-630f-4b86-8b45-91b90a6fce1c")
        self.tenancy = os.getenv("INTEGRATION_TENANCY", "datamap/production/data-amazon")
        self.file_upload_token_secret = os.getenv("FILE_UPLOAD_TOKEN_SECRET", "fake_secret_for_jwt_token")
        
        # WireMock configuration - handle both container and host modes
        doi_base_url = os.getenv("DOI_BASE_URL", "http://localhost:8083")
        if "wiremock_test_integration" in doi_base_url:
            # Container mode - use external port for test client
            self.wiremock_url = "http://localhost:8083"
        else:
            self.wiremock_url = doi_base_url
        
        # Environment detection
        self.environment = os.getenv("ENVIRONMENT", "integration-test")
        self.is_container_mode = self.environment == "integration-test"
        
    def get_api_url(self, path: str) -> str:
        """Get full API URL for a given path."""
        path = path.lstrip("/")
        return f"{self.base_url}/api/v1/{path}"
    
    def get_wiremock_admin_url(self, path: str = "") -> str:
        """Get WireMock admin URL for a given path."""
        path = path.lstrip("/")
        return f"{self.wiremock_url}/__admin/{path}"


# Global config instance
config = IntegrationTestConfig()
