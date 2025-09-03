"""Authentication fixtures for integration tests."""
from typing import Dict
from tests.integration.config import config


class AuthFixture:
    """Authentication fixture factory."""
    
    @staticmethod
    def valid_headers() -> Dict[str, str]:
        """Get valid authentication headers for API requests."""
        return {
            "X-Api-Key": config.api_key,
            "X-Api-Secret": config.api_secret,
            "X-User-Id": config.user_id,
            "X-Datamap-Tenancies": config.tenancy,
            "Content-Type": "application/json"
        }
    
    @staticmethod
    def custom_headers(
        api_key: str = None, 
        api_secret: str = None, 
        user_id: str = None, 
        tenancy: str = None
    ) -> Dict[str, str]:
        """Get custom authentication headers with optional overrides."""
        return {
            "X-Api-Key": api_key or config.api_key,
            "X-Api-Secret": api_secret or config.api_secret,
            "X-User-Id": user_id or config.user_id,
            "X-Datamap-Tenancies": tenancy or config.tenancy,
            "Content-Type": "application/json"
        }
    
    @staticmethod
    def invalid_headers() -> Dict[str, str]:
        """Get invalid authentication headers for 401 testing."""
        return {
            "X-Api-Key": "invalid-key",
            "X-Api-Secret": "invalid-secret",
            "X-User-Id": "invalid-user",
            "X-Datamap-Tenancies": "invalid/tenancy",
            "Content-Type": "application/json"
        }
    
    @staticmethod
    def no_auth_headers() -> Dict[str, str]:
        """Get headers without authentication (for public endpoints)."""
        return {
            "Content-Type": "application/json"
        }
