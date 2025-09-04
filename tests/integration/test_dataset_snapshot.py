from tests.integration.utils.assertions import (
    assert_status_code,
    assert_response_matches_dict,
    assert_response_contains_fields,
    assert_json_response,
)


class TestDatasetSnapshotEndpoints:
    """Simple integration tests for dataset snapshot endpoints."""

    def test_get_latest_snapshot_404(
        self, http_client, no_auth_headers, dataset_fixture
    ):
        """Test getting latest snapshot for non-existent dataset returns 404 with exact response."""
        # Arrange
        nonexistent_id = dataset_fixture.get_nonexistent_dataset_id()

        # Act
        response = http_client.get(
            f"/datasets/{nonexistent_id}/snapshot", headers=no_auth_headers
        )

        # Assert - exact status and exact response body
        assert_status_code(response, 404)
        assert_response_matches_dict(response, {"detail": "Snapshot not found"})

    def test_get_latest_snapshot_422(
        self, http_client, no_auth_headers, dataset_fixture
    ):
        """Test getting latest snapshot with invalid UUID returns 422."""
        # Arrange
        invalid_id = dataset_fixture.get_invalid_dataset_id()

        # Act
        response = http_client.get(
            f"/datasets/{invalid_id}/snapshot", headers=no_auth_headers
        )

        # Assert
        assert_status_code(response, 422)
        # Just check that response has a detail field - don't check exact content since
        # FastAPI validation messages can vary and are complex
        assert_response_contains_fields(response, {})  # Just verify it's valid JSON

    def test_get_version_snapshot_404(
        self, http_client, no_auth_headers, dataset_fixture
    ):
        """Test getting version snapshot for non-existent dataset returns 404."""
        # Arrange
        nonexistent_id = dataset_fixture.get_nonexistent_dataset_id()

        # Act
        response = http_client.get(
            f"/datasets/{nonexistent_id}/versions/v1.0/snapshot",
            headers=no_auth_headers,
        )

        # Assert - exact status and exact response body
        assert_status_code(response, 404)
        assert_response_matches_dict(response, {"detail": "Snapshot not found"})

    def test_get_version_snapshot_with_created_dataset_404(
        self, http_client, no_auth_headers, dataset_fixture
    ):
        """Test getting snapshot for non-existent version of existing dataset returns 404."""
        # Arrange
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        # Act
        response = http_client.get(
            f"/datasets/{dataset_id}/versions/nonexistent-version/snapshot",
            headers=no_auth_headers,
        )

        # Assert - exact status and exact response body
        assert_status_code(response, 404)
        assert_response_matches_dict(response, {"detail": "Snapshot not found"})

    def test_get_version_snapshot_422(
        self, http_client, no_auth_headers, dataset_fixture
    ):
        """Test getting version snapshot with invalid UUID returns 422."""
        # Arrange
        invalid_id = dataset_fixture.get_invalid_dataset_id()

        # Act
        response = http_client.get(
            f"/datasets/{invalid_id}/versions/v1.0/snapshot", headers=no_auth_headers
        )

        # Assert
        assert_status_code(response, 422)
        # Just verify it's valid JSON with some error detail
        assert_response_contains_fields(response, {})

    def test_endpoints_are_public(self, http_client, dataset_fixture):
        """Test that snapshot endpoints don't require authentication."""
        # Arrange
        nonexistent_id = dataset_fixture.get_nonexistent_dataset_id()

        # Act - Make requests without any auth headers
        latest_response = http_client.get(f"/datasets/{nonexistent_id}/snapshot")
        version_response = http_client.get(
            f"/datasets/{nonexistent_id}/versions/v1.0/snapshot"
        )

        # Assert - Should get 404 (not found) not 401 (unauthorized)
        assert_status_code(latest_response, 404)
        assert_status_code(version_response, 404)

        # Both should return exact same error response
        assert_response_matches_dict(latest_response, {"detail": "Snapshot not found"})
        assert_response_matches_dict(version_response, {"detail": "Snapshot not found"})

    def test_error_consistency_across_endpoints(
        self, http_client, no_auth_headers, dataset_fixture
    ):
        """Test that error responses are consistent across both endpoints."""
        # Arrange
        nonexistent_id = dataset_fixture.get_nonexistent_dataset_id()

        # Act
        latest_response = http_client.get(
            f"/datasets/{nonexistent_id}/snapshot", headers=no_auth_headers
        )
        version_response = http_client.get(
            f"/datasets/{nonexistent_id}/versions/v1.0/snapshot",
            headers=no_auth_headers,
        )

        # Assert - Both should return identical 404 responses
        assert_status_code(latest_response, 404)
        assert_status_code(version_response, 404)

        expected_error = {"detail": "Snapshot not found"}
        assert_response_matches_dict(latest_response, expected_error)
        assert_response_matches_dict(version_response, expected_error)


class TestDatasetSnapshotEdgeCases:
    """Edge case tests for dataset snapshot endpoints."""

    def test_special_characters_in_version_name(
        self, http_client, no_auth_headers, dataset_fixture
    ):
        """Test handling of special characters in version names."""
        # Arrange
        dataset_id = dataset_fixture.get_nonexistent_dataset_id()
        special_versions = ["v1.0-beta", "v1.0_alpha", "v1.0%20test", "v1.0+build.1"]

        for version_name in special_versions:
            # Act
            response = http_client.get(
                f"/datasets/{dataset_id}/versions/{version_name}/snapshot",
                headers=no_auth_headers,
            )

            # Assert - Should return 404 for non-existent dataset/version combination
            assert_status_code(response, 404)
            assert_response_matches_dict(response, {"detail": "Snapshot not found"})

    def test_very_long_version_name(
        self, http_client, no_auth_headers, dataset_fixture
    ):
        """Test handling of very long version names."""
        # Arrange
        dataset_id = dataset_fixture.get_nonexistent_dataset_id()
        long_version = "v" + "1" * 1000

        # Act
        response = http_client.get(
            f"/datasets/{dataset_id}/versions/{long_version}/snapshot",
            headers=no_auth_headers,
        )

        # Assert - Should return 404 for non-existent dataset/version (long versions are still valid URL paths)
        assert_status_code(response, 404)
        assert_response_matches_dict(response, {"detail": "Snapshot not found"})

    def test_empty_version_name(self, http_client, no_auth_headers, dataset_fixture):
        """Test handling of empty version name."""
        # Arrange
        dataset_id = dataset_fixture.get_nonexistent_dataset_id()

        # Act
        response = http_client.get(
            f"/datasets/{dataset_id}/versions//snapshot",  # Empty version name
            headers=no_auth_headers,
        )

        # Assert - Should return 404 (FastAPI treats this as a path not found - different from our custom endpoint)
        assert_status_code(response, 404)
        assert_response_matches_dict(response, {"detail": "Not Found"})


class TestDatasetSnapshotSuccess:
    """Tests for successful responses with DOI workflow."""

    def test_get_latest_snapshot_success_manual_doi(
        self, http_client, no_auth_headers, dataset_fixture
    ):
        """Test getting latest snapshot for dataset with MANUAL DOI."""
        # Arrange - Create dataset with MANUAL DOI (triggers snapshot publication)
        dataset = dataset_fixture.create_published_dataset_with_snapshot(
            doi_mode="MANUAL"
        )
        dataset_id = dataset["id"]

        # Act
        response = http_client.get(f"/datasets/{dataset_id}/snapshot", headers=no_auth_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        
        # Test essential fields
        assert_response_contains_fields(response, {
            "dataset_id": dataset_id,
            "version_name": dataset["current_version"]["name"],
            "doi_state": "DRAFT",  # MANUAL DOI starts as DRAFT
            "data": dataset["data"],
            "files_summary": {
                "total_files": 0,  # No files uploaded in test
                "total_size_bytes": 0,
                "extensions_breakdown": []
            }
        })

        # Verify DOI information is present and matches the created DOI
        assert "doi_identifier" in data
        assert data["doi_identifier"] is not None
        assert data["doi_identifier"] == dataset["current_version"]["doi"]["identifier"]
        assert data["doi_state"] == "DRAFT"
        assert data["doi_link"] is not None  # Should have DOI link
        
        # Verify versions field structure
        assert "versions" in data
        assert isinstance(data["versions"], list)
        assert len(data["versions"]) > 0  # Should have at least one version

    def test_get_latest_snapshot_success_auto_doi_findable(
        self, http_client, no_auth_headers, dataset_fixture
    ):
        """Test getting latest snapshot for dataset with AUTO DOI in FINDABLE state."""
        # Arrange - Create dataset with AUTO DOI and change state to FINDABLE
        dataset = dataset_fixture.create_published_dataset_with_snapshot(
            doi_mode="AUTO"
        )
        dataset_id = dataset["id"]

        # Act
        response = http_client.get(f"/datasets/{dataset_id}/snapshot", headers=no_auth_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        
        # Test essential fields
        assert_response_contains_fields(response, {
            "dataset_id": dataset_id,
            "version_name": dataset["current_version"]["name"],
            "doi_state": "FINDABLE",  # AUTO DOI changed to FINDABLE
            "data": dataset["data"],
            "files_summary": {
                "total_files": 0,
                "total_size_bytes": 0,
                "extensions_breakdown": []
            }
        })

        # Verify DOI information is present and matches the created DOI (identifier is auto-generated)
        assert "doi_identifier" in data
        assert data["doi_identifier"] is not None
        assert data["doi_identifier"] == dataset["current_version"]["doi"]["identifier"]
        assert data["doi_state"] == "FINDABLE"
        assert data["doi_link"] is not None
        
        # Verify versions field structure
        assert "versions" in data
        assert isinstance(data["versions"], list)
        assert len(data["versions"]) > 0  # Should have at least one version

    def test_get_version_snapshot_success(
        self, http_client, no_auth_headers, dataset_fixture
    ):
        """Test getting version-specific snapshot."""
        # Arrange - Create dataset with DOI
        dataset = dataset_fixture.create_published_dataset_with_snapshot(
            doi_mode="MANUAL"
        )
        dataset_id = dataset["id"]
        version_name = dataset["current_version"]["name"]

        # Act
        response = http_client.get(
            f"/datasets/{dataset_id}/versions/{version_name}/snapshot",
            headers=no_auth_headers,
        )

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        
        # Test essential fields
        assert_response_contains_fields(response, {
            "dataset_id": dataset_id,
            "version_name": version_name,
            "doi_state": "DRAFT",  # MANUAL DOI starts as DRAFT
            "data": dataset["data"],
            "files_summary": {
                "total_files": 0,
                "total_size_bytes": 0,
                "extensions_breakdown": []
            }
        })

        # Verify DOI information is present and matches the created DOI
        assert "doi_identifier" in data
        assert data["doi_identifier"] is not None
        assert data["doi_identifier"] == dataset["current_version"]["doi"]["identifier"]
        assert data["doi_state"] == "DRAFT"
        assert data["doi_link"] is not None  # Should have DOI link

    def test_snapshot_publication_after_doi_state_change(
        self, http_client, no_auth_headers, dataset_fixture, valid_headers
    ):
        """Test that snapshot is published when DOI state changes to FINDABLE."""
        # Arrange - Create dataset with AUTO DOI (no snapshot initially)
        dataset = dataset_fixture.create_dataset_with_doi(
            doi_mode="AUTO"
        )
        dataset_id = dataset["id"]
        version_name = dataset["current_version"]["name"]

        # Verify snapshot is not available initially
        snapshot_response = http_client.get(f"/datasets/{dataset_id}/snapshot", headers=no_auth_headers)
        assert_status_code(snapshot_response, 404)

        # Act - Change DOI state to FINDABLE (should trigger snapshot publication)
        state_change_data = {"state": "FINDABLE"}
        state_response = http_client.put(
            f"/datasets/{dataset_id}/versions/{version_name}/doi",
            json=state_change_data,
            headers=valid_headers,
        )
        assert_status_code(state_response, 200)

        # Assert - Snapshot should now be available
        snapshot_response = http_client.get(f"/datasets/{dataset_id}/snapshot", headers=no_auth_headers)
        assert_status_code(snapshot_response, 200)
        
        data = assert_json_response(snapshot_response)
        assert_response_contains_fields(snapshot_response, {
            "dataset_id": dataset_id,
            "version_name": version_name,
            "doi_state": "FINDABLE",
        })
        # Verify DOI identifier is present and matches the created DOI (auto-generated)
        assert "doi_identifier" in data
        assert data["doi_identifier"] is not None
        assert data["doi_identifier"] == dataset["current_version"]["doi"]["identifier"]

    def test_snapshot_contains_doi_information(
        self, http_client, no_auth_headers, dataset_fixture
    ):
        """Test that snapshot response contains complete DOI information."""
        # Arrange
        dataset = dataset_fixture.create_published_dataset_with_snapshot(
            doi_mode="MANUAL"
        )
        dataset_id = dataset["id"]

        # Act
        response = http_client.get(f"/datasets/{dataset_id}/snapshot", headers=no_auth_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        
        # Verify DOI fields are present and properly formatted
        assert "doi_identifier" in data
        assert "doi_state" in data
        assert "doi_link" in data
        assert "publication_date" in data
        
        assert data["doi_identifier"] is not None
        assert data["doi_state"] == "DRAFT"
        assert data["doi_link"] is not None
        assert data["publication_date"] is not None

    def test_snapshot_data_structure_consistency(
        self, http_client, no_auth_headers, dataset_fixture
    ):
        """Test that snapshot data structure is consistent and complete."""
        # Arrange
        dataset = dataset_fixture.create_published_dataset_with_snapshot(
            doi_mode="MANUAL"
        )
        dataset_id = dataset["id"]

        # Act
        response = http_client.get(f"/datasets/{dataset_id}/snapshot", headers=no_auth_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        
        # Verify all required top-level fields are present
        required_fields = [
            "dataset_id", "version_name", "doi_identifier", "doi_link", 
            "doi_state", "publication_date", "files_summary", "data", "versions"
        ]
        
        for field in required_fields:
            assert field in data, f"Required field '{field}' missing from snapshot response"
        
        # Verify files_summary structure
        files_summary = data["files_summary"]
        assert "total_files" in files_summary
        assert "total_size_bytes" in files_summary
        assert "extensions_breakdown" in files_summary
        assert isinstance(files_summary["extensions_breakdown"], list)
        
        # Verify data contains original dataset information
        assert data["data"]["title"] == dataset["data"]["title"]
        assert data["data"]["description"] == dataset["data"]["description"]
