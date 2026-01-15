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
        "exp": 1926260558,  # Fixed expiration for testing
    }

    return jwt.encode(payload, config.file_upload_token_secret, algorithm="HS256")


def create_tus_payload(
    user_id: str,
    dataset_id: str,
    filename: str = "test.txt",
    file_size: int = 1024,
    file_type: str = "text/plain",
    user_token: str = None,
    storage_key: str = None,
) -> dict:
    """Create a TUS webhook payload for testing.

    Args:
        user_id: User ID for authentication
        dataset_id: Dataset ID for file association
        filename: Name of the file being uploaded
        file_size: Size of the file in bytes
        file_type: MIME type of the file
        user_token: JWT token for authentication (generated if not provided)
        storage_key: Custom storage key (defaults to staged/{uuid}/{filename})

    Returns:
        TUS webhook payload dictionary
    """
    if user_token is None:
        user_token = create_tus_jwt_token(user_id)

    # Use staged/ prefix by default (mimics TUSd configuration)
    if storage_key is None:
        file_uuid = str(uuid4())
        storage_key = f"staged/{file_uuid}"

    return {
        "Type": "post-finish",
        "Event": {
            "Upload": {
                "Size": file_size,
                "MetaData": {
                    "dataset_id": dataset_id,
                    "filename": filename,
                    "filetype": file_type,
                },
                "Storage": {"Key": storage_key, "Bucket": "datamap"},
            },
            "HTTPRequest": {
                "Header": {"X-User-Id": [user_id], "X-User-Token": [user_token]}
            },
        },
    }


def create_invalid_tus_payload(user_id: str, dataset_id: str) -> dict:
    """Create an invalid TUS webhook payload for testing (invalid token)."""
    file_uuid = str(uuid4())
    return {
        "Type": "post-finish",
        "Event": {
            "Upload": {
                "Size": 1024,
                "MetaData": {
                    "dataset_id": dataset_id,
                    "filename": "test.txt",
                    "filetype": "text/plain",
                },
                "Storage": {"Key": f"staged/{file_uuid}", "Bucket": "datamap"},
            },
            "HTTPRequest": {
                "Header": {"X-User-Id": [user_id], "X-User-Token": ["invalid-token"]}
            },
        },
    }


def create_malformed_tus_payload() -> dict:
    """Create a malformed TUS webhook payload for testing (missing dataset_id)."""
    file_uuid = str(uuid4())
    return {
        "Type": "post-finish",
        "Event": {
            "Upload": {
                "Size": 1024,
                "MetaData": {
                    "filename": "test.txt",
                    "filetype": "text/plain",
                    # Missing dataset_id
                },
                "Storage": {"Key": f"staged/{file_uuid}", "Bucket": "datamap"},
            },
            "HTTPRequest": {
                "Header": {
                    "X-User-Id": ["cbb0a683-630f-4b86-8b45-91b90a6fce1c"],
                    "X-User-Token": ["valid-token"],
                }
            },
        },
    }
