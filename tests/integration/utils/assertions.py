"""Common assertion helpers for integration tests."""
import json
from typing import Dict, Any, List, Optional
import requests


def assert_status_code(response: requests.Response, expected_status: int):
    """Assert response has expected status code with detailed error message."""
    if response.status_code != expected_status:
        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError):
            body = response.text
        
        raise AssertionError(
            f"Expected status {expected_status}, got {response.status_code}. "
            f"Response: {body}"
        )


def assert_json_response(response: requests.Response) -> Dict[str, Any]:
    """Assert response is valid JSON and return parsed data."""
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError) as e:
        raise AssertionError(f"Response is not valid JSON: {str(e)}. Body: {response.text}")


def assert_response_schema(data: Dict[str, Any], required_fields: List[str]):
    """Assert response data contains all required fields."""
    missing_fields = []
    for field in required_fields:
        if field not in data:
            missing_fields.append(field)
    
    if missing_fields:
        raise AssertionError(f"Missing required fields: {missing_fields}. Data: {data}")


def assert_uuid_format(value: str, field_name: str = "id"):
    """Assert value is a valid UUID format."""
    import uuid
    try:
        uuid.UUID(value)
    except (ValueError, TypeError):
        raise AssertionError(f"Field '{field_name}' is not a valid UUID: {value}")


def assert_iso_datetime_format(value: str, field_name: str = "timestamp"):
    """Assert value is a valid ISO datetime format."""
    from datetime import datetime
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        raise AssertionError(f"Field '{field_name}' is not a valid ISO datetime: {value}")


def assert_snapshot_response_schema(data: Dict[str, Any]):
    """Assert snapshot response has correct schema."""
    required_fields = [
        "dataset_id",
        "version_name", 
        "files_summary",
        "data"
    ]
    assert_response_schema(data, required_fields)
    
    # Validate files_summary schema
    files_summary = data["files_summary"]
    files_summary_fields = ["total_files", "total_size_bytes", "extensions_breakdown"]
    assert_response_schema(files_summary, files_summary_fields)
    
    # Validate extensions_breakdown
    extensions = files_summary["extensions_breakdown"]
    if not isinstance(extensions, list):
        raise AssertionError(f"extensions_breakdown should be a list, got {type(extensions)}")


def assert_latest_snapshot_response_schema(data: Dict[str, Any]):
    """Assert latest snapshot response has correct schema including versions."""
    # First check base snapshot schema
    assert_snapshot_response_schema(data)
    
    # Check for versions field
    if "versions" not in data:
        raise AssertionError("Latest snapshot response missing 'versions' field")
    
    versions = data["versions"]
    if not isinstance(versions, list):
        raise AssertionError(f"'versions' should be a list, got {type(versions)}")
    
    # Validate each version info
    for i, version in enumerate(versions):
        version_fields = ["id", "name"]
        try:
            assert_response_schema(version, version_fields)
        except AssertionError as e:
            raise AssertionError(f"Version {i} invalid: {str(e)}")


def assert_error_response_schema(data: Dict[str, Any]):
    """Assert error response has correct schema."""
    if "detail" not in data:
        raise AssertionError(f"Error response missing 'detail' field. Data: {data}")


def assert_contains_substring(text: str, substring: str, case_sensitive: bool = True):
    """Assert text contains substring."""
    search_text = text if case_sensitive else text.lower()
    search_substring = substring if case_sensitive else substring.lower()
    
    if search_substring not in search_text:
        raise AssertionError(f"Text does not contain '{substring}'. Text: {text}")


def assert_not_empty(value: Any, field_name: str = "value"):
    """Assert value is not empty (not None, empty string, empty list, etc.)."""
    if not value:
        raise AssertionError(f"Field '{field_name}' should not be empty, got: {value}")
