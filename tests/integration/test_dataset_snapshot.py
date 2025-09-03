import pytest
from tests.integration.utils.assertions import (
    assert_status_code,
    assert_json_response,
    assert_snapshot_response_schema,
    assert_latest_snapshot_response_schema,
    assert_error_response_schema,
    assert_uuid_format,
    assert_contains_substring,
    assert_not_empty
)


class TestDatasetSnapshotEndpoints:
    """Integration tests for dataset snapshot endpoints."""
    
    def test_get_latest_snapshot_with_nonexistent_dataset(self, http_client, no_auth_headers, dataset_fixture):
        """Test getting latest snapshot for non-existent dataset returns 404."""
        # Arrange
        nonexistent_id = dataset_fixture.get_nonexistent_dataset_id()
        
        # Act
        response = http_client.get(
            f"/datasets/{nonexistent_id}/snapshot",
            headers=no_auth_headers
        )
        
        # Assert
        assert_status_code(response, 404)
        data = assert_json_response(response)
        assert_error_response_schema(data)
        assert_contains_substring(data["detail"], "not found", case_sensitive=False)
    
    def test_get_latest_snapshot_with_invalid_uuid(self, http_client, no_auth_headers, dataset_fixture):
        """Test getting latest snapshot with invalid UUID format returns 422."""
        # Arrange
        invalid_id = dataset_fixture.get_invalid_dataset_id()
        
        # Act
        response = http_client.get(
            f"/datasets/{invalid_id}/snapshot",
            headers=no_auth_headers
        )
        
        # Assert
        # FastAPI returns 422 for validation errors (invalid UUID format)
        assert_status_code(response, 422)
        data = assert_json_response(response)
        # FastAPI validation error response has different structure
        assert "detail" in data
    
    def test_get_version_snapshot_with_nonexistent_dataset(self, http_client, no_auth_headers, dataset_fixture):
        """Test getting version snapshot for non-existent dataset returns 404."""
        # Arrange
        nonexistent_id = dataset_fixture.get_nonexistent_dataset_id()
        version_name = "v1.0"
        
        # Act
        response = http_client.get(
            f"/datasets/{nonexistent_id}/versions/{version_name}/snapshot",
            headers=no_auth_headers
        )
        
        # Assert
        assert_status_code(response, 404)
        data = assert_json_response(response)
        assert_error_response_schema(data)
        assert_contains_substring(data["detail"], "not found", case_sensitive=False)
    
    def test_get_version_snapshot_with_nonexistent_version(self, http_client, no_auth_headers, dataset_fixture):
        """Test getting snapshot for non-existent version returns 404."""
        # Arrange
        # Create a real dataset but use non-existent version
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]
        nonexistent_version = "nonexistent-version"
        
        # Act
        response = http_client.get(
            f"/datasets/{dataset_id}/versions/{nonexistent_version}/snapshot",
            headers=no_auth_headers
        )
        
        # Assert
        assert_status_code(response, 404)
        data = assert_json_response(response)
        assert_error_response_schema(data)
        assert_contains_substring(data["detail"], "not found", case_sensitive=False)
    
    def test_get_version_snapshot_with_invalid_uuid(self, http_client, no_auth_headers, dataset_fixture):
        """Test getting version snapshot with invalid UUID format returns 422."""
        # Arrange
        invalid_id = dataset_fixture.get_invalid_dataset_id()
        version_name = "v1.0"
        
        # Act
        response = http_client.get(
            f"/datasets/{invalid_id}/versions/{version_name}/snapshot",
            headers=no_auth_headers
        )
        
        # Assert
        assert_status_code(response, 422)
        data = assert_json_response(response)
        assert "detail" in data
    
    @pytest.mark.skip(reason="Happy path test requires published dataset with snapshot - implement after DOI workflow is working")
    def test_get_latest_snapshot_success(self, http_client, no_auth_headers, dataset_fixture):
        """Test successfully getting latest snapshot for published dataset."""
        # Arrange
        # This test requires:
        # 1. Dataset with published version
        # 2. Snapshot file created in MinIO
        # 3. DOI workflow working with WireMock
        dataset = dataset_fixture.create_published_dataset_with_snapshot()
        dataset_id = dataset["id"]
        
        # Act
        response = http_client.get(
            f"/datasets/{dataset_id}/snapshot",
            headers=no_auth_headers
        )
        
        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        assert_latest_snapshot_response_schema(data)
        
        # Validate response content
        assert_uuid_format(data["dataset_id"], "dataset_id")
        assert_not_empty(data["version_name"], "version_name")
        assert_not_empty(data["data"], "data")
        
        # Validate files_summary
        files_summary = data["files_summary"]
        assert isinstance(files_summary["total_files"], int)
        assert isinstance(files_summary["total_size_bytes"], int)
        assert isinstance(files_summary["extensions_breakdown"], list)
        
        # Validate versions list
        versions = data["versions"]
        assert len(versions) > 0
        for version in versions:
            assert_not_empty(version["id"], "version.id")
            assert_not_empty(version["name"], "version.name")
    
    @pytest.mark.skip(reason="Happy path test requires published dataset with snapshot - implement after DOI workflow is working")
    def test_get_version_snapshot_success(self, http_client, no_auth_headers, dataset_fixture):
        """Test successfully getting specific version snapshot."""
        # Arrange
        dataset = dataset_fixture.create_published_dataset_with_snapshot()
        dataset_id = dataset["id"]
        version_name = dataset["current_version"]["name"]
        
        # Act
        response = http_client.get(
            f"/datasets/{dataset_id}/versions/{version_name}/snapshot",
            headers=no_auth_headers
        )
        
        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        assert_snapshot_response_schema(data)
        
        # Validate response content
        assert_uuid_format(data["dataset_id"], "dataset_id")
        assert data["version_name"] == version_name
        assert_not_empty(data["data"], "data")
        
        # Validate files_summary
        files_summary = data["files_summary"]
        assert isinstance(files_summary["total_files"], int)
        assert isinstance(files_summary["total_size_bytes"], int)
        assert isinstance(files_summary["extensions_breakdown"], list)
    
    def test_snapshot_endpoints_are_public(self, http_client, dataset_fixture):
        """Test that snapshot endpoints don't require authentication."""
        # Arrange
        nonexistent_id = dataset_fixture.get_nonexistent_dataset_id()
        
        # Act - Make requests without any auth headers
        latest_response = http_client.get(
            f"/datasets/{nonexistent_id}/snapshot",
            headers={"Content-Type": "application/json"}  # No auth headers
        )
        
        version_response = http_client.get(
            f"/datasets/{nonexistent_id}/versions/v1.0/snapshot",
            headers={"Content-Type": "application/json"}  # No auth headers
        )
        
        # Assert - Should get 404 (not found) not 401 (unauthorized)
        # This confirms the endpoints are public
        assert_status_code(latest_response, 404)
        assert_status_code(version_response, 404)
        
        # Both should return proper error responses (not auth errors)
        latest_data = assert_json_response(latest_response)
        version_data = assert_json_response(version_response)
        
        assert_error_response_schema(latest_data)
        assert_error_response_schema(version_data)
        
        # Error messages should be about "not found", not "unauthorized"
        assert_contains_substring(latest_data["detail"], "not found", case_sensitive=False)
        assert_contains_substring(version_data["detail"], "not found", case_sensitive=False)
    
    def test_snapshot_error_handling_with_corrupted_data(self, http_client, no_auth_headers, dataset_fixture):
        """
        Test snapshot error handling when MinIO returns corrupted JSON.
        
        Note: This test is tricky to implement without direct MinIO access.
        In a real scenario, you might need to:
        1. Create a dataset with snapshot
        2. Manually corrupt the snapshot file in MinIO
        3. Test that the API returns 500 with proper error message
        
        For now, this is a placeholder test.
        """
        # This would require more complex setup to actually test corrupted JSON scenarios
        # The service layer tests already cover this case with mocked MinIO
        pytest.skip("Corrupted data test requires manual MinIO manipulation - covered by unit tests")


# Additional test class for edge cases
class TestDatasetSnapshotEdgeCases:
    """Edge case tests for dataset snapshot endpoints."""
    
    def test_special_characters_in_version_name(self, http_client, no_auth_headers, dataset_fixture):
        """Test handling of special characters in version names."""
        # Arrange
        dataset_id = dataset_fixture.get_nonexistent_dataset_id()
        special_version_names = [
            "v1.0-beta",
            "v1.0_alpha",
            "v1.0%20test",  # URL encoded space
            "v1.0+build.1"
        ]
        
        for version_name in special_version_names:
            # Act
            response = http_client.get(
                f"/datasets/{dataset_id}/versions/{version_name}/snapshot",
                headers=no_auth_headers
            )
            
            # Assert - Should handle gracefully (404 for non-existent, not 400/500)
            assert response.status_code in [404, 422], f"Unexpected status for version '{version_name}': {response.status_code}"
    
    def test_very_long_version_name(self, http_client, no_auth_headers, dataset_fixture):
        """Test handling of very long version names."""
        # Arrange
        dataset_id = dataset_fixture.get_nonexistent_dataset_id()
        long_version_name = "v" + "1" * 1000  # Very long version name
        
        # Act
        response = http_client.get(
            f"/datasets/{dataset_id}/versions/{long_version_name}/snapshot",
            headers=no_auth_headers
        )
        
        # Assert - Should handle gracefully
        assert response.status_code in [404, 414, 422], f"Unexpected status for long version name: {response.status_code}"
    
    def test_empty_version_name(self, http_client, no_auth_headers, dataset_fixture):
        """Test handling of empty version name."""
        # Arrange
        dataset_id = dataset_fixture.get_nonexistent_dataset_id()
        
        # Act
        response = http_client.get(
            f"/datasets/{dataset_id}/versions//snapshot",  # Empty version name
            headers=no_auth_headers
        )
        
        # Assert - Should return 404 (path not found) or similar
        assert response.status_code in [404, 422], f"Unexpected status for empty version name: {response.status_code}"
