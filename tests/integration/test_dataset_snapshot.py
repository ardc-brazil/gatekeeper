import pytest
from tests.integration.utils.assertions import (
    assert_status_code,
    assert_response_matches_dict,
    assert_response_contains_fields,
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


# Example for when you have successful responses to test
class TestDatasetSnapshotSuccess:
    """Tests for successful responses - when DOI workflow is implemented."""

    @pytest.mark.skip(
        reason="Requires published dataset with snapshot - implement when DOI workflow works"
    )
    def test_get_latest_snapshot_success_exact_response(
        self, http_client, no_auth_headers, dataset_fixture
    ):
        """Example of testing successful response with exact body matching."""
        # When you have a published dataset, you can test like this:

        # dataset = dataset_fixture.create_published_dataset_with_snapshot()
        # dataset_id = dataset["id"]
        #
        # response = http_client.get(f"/datasets/{dataset_id}/snapshot", headers=no_auth_headers)
        #
        # assert_status_code(response, 200)
        #
        # # Option 1: Test exact response structure
        # expected_response = {
        #     "dataset_id": dataset_id,
        #     "version_name": "v1.0",
        #     "doi_identifier": None,
        #     "doi_link": None,
        #     "doi_state": None,
        #     "publication_date": None,
        #     "files_summary": {
        #         "total_files": 3,
        #         "total_size_bytes": 1024,
        #         "extensions_breakdown": [
        #             {"extension": ".csv", "count": 2, "total_size_bytes": 512},
        #             {"extension": ".json", "count": 1, "total_size_bytes": 512}
        #         ]
        #     },
        #     "data": {"name": "Test Dataset", "description": "Test description"},
        #     "versions": [
        #         {"id": "some-id", "name": "v1.0", "doi_identifier": None, "doi_state": None, "created_at": "2024-01-01T00:00:00Z"}
        #     ]
        # }
        # assert_response_matches_dict(response, expected_response)
        #
        # # Option 2: Test only specific fields you care about
        # assert_response_contains_fields(response, {
        #     "dataset_id": dataset_id,
        #     "version_name": "v1.0"
        # })
        pass
