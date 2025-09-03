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
    """Assert DatasetSnapshotResponse has correct schema and types."""
    # Required fields for DatasetSnapshotResponse
    required_fields = [
        "dataset_id",
        "version_name", 
        "files_summary",
        "data"
    ]
    assert_response_schema(data, required_fields)
    
    # Validate field types
    assert_uuid_format(data["dataset_id"], "dataset_id")
    assert isinstance(data["version_name"], str), f"version_name should be str, got {type(data['version_name'])}"
    assert isinstance(data["data"], dict), f"data should be dict, got {type(data['data'])}"
    
    # Optional fields validation
    if "doi_identifier" in data and data["doi_identifier"] is not None:
        assert isinstance(data["doi_identifier"], str), f"doi_identifier should be str or None, got {type(data['doi_identifier'])}"
    
    if "doi_link" in data and data["doi_link"] is not None:
        assert isinstance(data["doi_link"], str), f"doi_link should be str or None, got {type(data['doi_link'])}"
        # Basic URL validation
        if not (data["doi_link"].startswith("http://") or data["doi_link"].startswith("https://")):
            raise AssertionError(f"doi_link should be a valid URL, got: {data['doi_link']}")
    
    if "doi_state" in data and data["doi_state"] is not None:
        assert isinstance(data["doi_state"], str), f"doi_state should be str or None, got {type(data['doi_state'])}"
        # Validate DOI state values (based on DataCite states)
        valid_doi_states = ["draft", "registered", "findable"]
        if data["doi_state"].lower() not in valid_doi_states:
            raise AssertionError(f"doi_state should be one of {valid_doi_states}, got: {data['doi_state']}")
    
    if "publication_date" in data and data["publication_date"] is not None:
        assert_iso_datetime_format(data["publication_date"], "publication_date")
    
    # Validate files_summary schema
    assert_files_summary_schema(data["files_summary"])


def assert_latest_snapshot_response_schema(data: Dict[str, Any]):
    """Assert DatasetLatestSnapshotResponse has correct schema including versions."""
    # First check base snapshot schema
    assert_snapshot_response_schema(data)
    
    # Check for versions field (required for latest snapshot)
    if "versions" not in data:
        raise AssertionError("Latest snapshot response missing 'versions' field")
    
    versions = data["versions"]
    if not isinstance(versions, list):
        raise AssertionError(f"'versions' should be a list, got {type(versions)}")
    
    # Validate each version info (DatasetVersionInfo schema)
    for i, version in enumerate(versions):
        assert_dataset_version_info_schema(version, f"versions[{i}]")


def assert_files_summary_schema(files_summary: Dict[str, Any]):
    """Assert FilesSummary has correct schema and types."""
    required_fields = ["total_files", "total_size_bytes", "extensions_breakdown"]
    assert_response_schema(files_summary, required_fields)
    
    # Validate field types
    assert isinstance(files_summary["total_files"], int), f"total_files should be int, got {type(files_summary['total_files'])}"
    assert isinstance(files_summary["total_size_bytes"], int), f"total_size_bytes should be int, got {type(files_summary['total_size_bytes'])}"
    assert isinstance(files_summary["extensions_breakdown"], list), f"extensions_breakdown should be list, got {type(files_summary['extensions_breakdown'])}"
    
    # Validate non-negative values
    if files_summary["total_files"] < 0:
        raise AssertionError(f"total_files should be non-negative, got: {files_summary['total_files']}")
    if files_summary["total_size_bytes"] < 0:
        raise AssertionError(f"total_size_bytes should be non-negative, got: {files_summary['total_size_bytes']}")
    
    # Validate each extension breakdown item (FileExtensionSummary schema)
    for i, ext_summary in enumerate(files_summary["extensions_breakdown"]):
        assert_file_extension_summary_schema(ext_summary, f"extensions_breakdown[{i}]")


def assert_file_extension_summary_schema(ext_summary: Dict[str, Any], context: str = "extension_summary"):
    """Assert FileExtensionSummary has correct schema and types."""
    required_fields = ["extension", "count", "total_size_bytes"]
    try:
        assert_response_schema(ext_summary, required_fields)
    except AssertionError as e:
        raise AssertionError(f"{context}: {str(e)}")
    
    # Validate field types
    assert isinstance(ext_summary["extension"], str), f"{context}: extension should be str, got {type(ext_summary['extension'])}"
    assert isinstance(ext_summary["count"], int), f"{context}: count should be int, got {type(ext_summary['count'])}"
    assert isinstance(ext_summary["total_size_bytes"], int), f"{context}: total_size_bytes should be int, got {type(ext_summary['total_size_bytes'])}"
    
    # Validate non-negative values
    if ext_summary["count"] < 0:
        raise AssertionError(f"{context}: count should be non-negative, got: {ext_summary['count']}")
    if ext_summary["total_size_bytes"] < 0:
        raise AssertionError(f"{context}: total_size_bytes should be non-negative, got: {ext_summary['total_size_bytes']}")
    
    # Validate extension format (should start with dot)
    if not ext_summary["extension"].startswith('.'):
        raise AssertionError(f"{context}: extension should start with '.', got: {ext_summary['extension']}")


def assert_dataset_version_info_schema(version: Dict[str, Any], context: str = "version"):
    """Assert DatasetVersionInfo has correct schema and types."""
    required_fields = ["id", "name"]
    try:
        assert_response_schema(version, required_fields)
    except AssertionError as e:
        raise AssertionError(f"{context}: {str(e)}")
    
    # Validate field types
    assert isinstance(version["id"], str), f"{context}: id should be str, got {type(version['id'])}"
    assert isinstance(version["name"], str), f"{context}: name should be str, got {type(version['name'])}"
    
    # Optional fields validation
    if "doi_identifier" in version and version["doi_identifier"] is not None:
        assert isinstance(version["doi_identifier"], str), f"{context}: doi_identifier should be str or None, got {type(version['doi_identifier'])}"
    
    if "doi_state" in version and version["doi_state"] is not None:
        assert isinstance(version["doi_state"], str), f"{context}: doi_state should be str or None, got {type(version['doi_state'])}"
        valid_doi_states = ["draft", "registered", "findable"]
        if version["doi_state"].lower() not in valid_doi_states:
            raise AssertionError(f"{context}: doi_state should be one of {valid_doi_states}, got: {version['doi_state']}")
    
    if "created_at" in version and version["created_at"] is not None:
        assert_iso_datetime_format(version["created_at"], f"{context}.created_at")


def assert_error_response_schema(data: Dict[str, Any]):
    """Assert HTTPException error response has correct schema."""
    # FastAPI HTTPException format
    if "detail" not in data:
        raise AssertionError(f"Error response missing 'detail' field. Data: {data}")
    
    # Validate detail is string
    assert isinstance(data["detail"], str), f"detail should be str, got {type(data['detail'])}"
    assert_not_empty(data["detail"], "detail")


def assert_fastapi_validation_error_schema(data: Dict[str, Any]):
    """Assert FastAPI validation error (422) has correct schema."""
    if "detail" not in data:
        raise AssertionError(f"Validation error response missing 'detail' field. Data: {data}")
    
    detail = data["detail"]
    # FastAPI validation errors have detail as list of error objects
    if isinstance(detail, list):
        for i, error in enumerate(detail):
            if not isinstance(error, dict):
                raise AssertionError(f"Validation error detail[{i}] should be dict, got {type(error)}")
            
            # Validate error object structure
            if "loc" not in error or "msg" not in error or "type" not in error:
                raise AssertionError(f"Validation error detail[{i}] missing required fields (loc, msg, type). Got: {error}")
    elif isinstance(detail, str):
        # Sometimes it's just a string
        assert_not_empty(detail, "detail")
    else:
        raise AssertionError(f"Validation error detail should be list or str, got {type(detail)}")


def assert_response_matches_dict(response: requests.Response, expected_dict: Dict[str, Any]):
    """Assert response JSON exactly matches the expected dictionary."""
    actual_data = assert_json_response(response)
    
    if actual_data != expected_dict:
        raise AssertionError(
            f"Response body does not match expected.\n"
            f"Expected: {expected_dict}\n"
            f"Actual: {actual_data}"
        )


def assert_response_matches_json_string(response: requests.Response, expected_json_string: str):
    """Assert response JSON exactly matches the expected JSON string."""
    import json
    try:
        expected_dict = json.loads(expected_json_string)
    except json.JSONDecodeError as e:
        raise AssertionError(f"Expected JSON string is not valid JSON: {str(e)}")
    
    assert_response_matches_dict(response, expected_dict)


def assert_response_contains_fields(response: requests.Response, expected_fields: Dict[str, Any]):
    """Assert response JSON contains all specified fields with exact values."""
    actual_data = assert_json_response(response)
    
    for field, expected_value in expected_fields.items():
        if field not in actual_data:
            raise AssertionError(f"Response missing field '{field}'. Response: {actual_data}")
        
        actual_value = actual_data[field]
        if actual_value != expected_value:
            raise AssertionError(
                f"Field '{field}' value mismatch.\n"
                f"Expected: {expected_value}\n"
                f"Actual: {actual_value}"
            )


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
