"""
TUS authentication fixtures for integration tests.
"""
import jwt
from uuid import uuid4
from tests.integration.config import config


def create_tus_jwt_token(user_id: str, file_id: str = None) -> str:
    """Create a valid JWT token for TUS authentication."""
    if file_id is None:
        file_id = f"test-file-{uuid4()}"
    
    payload = {
        "iss": "datamap_bff",
        "aud": "file_upload",
        "sub": user_id,
        "file": file_id,
        "iat": 1717453998,  # Fixed timestamp for testing
        "exp": 1926260558   # Fixed expiration for testing
    }
    
    return jwt.encode(payload, config.file_upload_token_secret, algorithm="HS256")


def create_tus_payload(user_id: str, dataset_id: str, filename: str = "test.txt", 
                      file_size: int = 1024, file_type: str = "text/plain",
                      user_token: str = None) -> dict:
    """Create a TUS webhook payload for testing."""
    if user_token is None:
        user_token = create_tus_jwt_token(user_id)
    
    return {
        "Type": "post-finish",
        "Event": {
            "Upload": {
                "Size": file_size,
                "MetaData": {
                    "dataset_id": dataset_id,
                    "filename": filename,
                    "filetype": file_type
                },
                "Storage": {
                    "Key": f"test-files/{filename}",
                    "Bucket": "test-bucket"
                }
            },
            "HTTPRequest": {
                "Header": {
                    "X-User-Id": [user_id],
                    "X-User-Token": [user_token]
                }
            }
        }
    }


def create_invalid_tus_payload(user_id: str, dataset_id: str) -> dict:
    """Create an invalid TUS webhook payload for testing."""
    return {
        "Type": "post-finish",
        "Event": {
            "Upload": {
                "Size": 1024,
                "MetaData": {
                    "dataset_id": dataset_id,
                    "filename": "test.txt",
                    "filetype": "text/plain"
                },
                "Storage": {
                    "Key": "test-files/test.txt",
                    "Bucket": "test-bucket"
                }
            },
            "HTTPRequest": {
                "Header": {
                    "X-User-Id": [user_id],
                    "X-User-Token": ["invalid-token"]
                }
            }
        }
    }


def create_malformed_tus_payload() -> dict:
    """Create a malformed TUS webhook payload for testing."""
    return {
        "Type": "post-finish",
        "Event": {
            "Upload": {
                "Size": 1024,
                "MetaData": {
                    "filename": "test.txt",
                    "filetype": "text/plain"
                    # Missing dataset_id
                },
                "Storage": {
                    "Key": "test-files/test.txt",
                    "Bucket": "test-bucket"
                }
            },
            "HTTPRequest": {
                "Header": {
                    "X-User-Id": ["cbb0a683-630f-4b86-8b45-91b90a6fce1c"],
                    "X-User-Token": ["valid-token"]
                }
            }
        }
    }
