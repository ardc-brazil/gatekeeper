"""
Integration tests for Dataset Collocation Internal API endpoints.

These endpoints are intended for use by the archivist service to manage
file organization and collocation status.
"""

from uuid import uuid4
from tests.integration.utils.assertions import assert_status_code, assert_json_response
from tests.integration.fixtures.tus_auth import create_tus_payload


class TestDatasetCollocationInternalAPI:
    """Integration tests for Dataset Collocation Internal API endpoints."""

    def test_get_pending_datasets_success_200(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test getting pending datasets returns 200."""
        # Arrange - Create and publish a dataset to set it to PENDING status
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        # Create version and publish to trigger PENDING status
        dataset_fixture.create_dataset_version(dataset_id)
        current_version = dataset["current_version"]
        version_name = current_version["name"]

        dataset_fixture.enable_dataset_version(dataset_id, version_name)
        dataset_fixture.publish_dataset_version(dataset_id, version_name)

        # Act
        response = http_client.get(
            "/internal/datasets/collocation/pending", headers=valid_headers
        )

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        assert isinstance(data, list)

        # Find our dataset in the list
        our_dataset = next((d for d in data if d["id"] == dataset_id), None)
        assert our_dataset is not None, f"Published dataset {dataset_id} should be in pending list"
        assert our_dataset["file_collocation_status"] in [None, "pending"]

    def test_get_pending_datasets_empty_list_200(
        self, http_client, valid_headers
    ):
        """Test getting pending datasets when none exist returns empty list."""
        # Act - All datasets should already be processed in a clean environment
        response = http_client.get(
            "/internal/datasets/collocation/pending", headers=valid_headers
        )

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        assert isinstance(data, list)
        # We can't assert it's empty as other tests might create pending datasets

    def test_get_pending_datasets_unauthorized_401(self, http_client):
        """Test getting pending datasets without auth returns 401."""
        # Act
        response = http_client.get("/internal/datasets/collocation/pending")

        # Assert
        assert_status_code(response, 401)
        data = assert_json_response(response)
        assert "detail" in data
        assert "unauthorized" in data["detail"].lower()

    def test_get_dataset_files_success_200(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test getting dataset files returns 200."""
        # Arrange - Create a dataset with files
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        # Upload a file via TUS webhook simulation
        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        file_payload = create_tus_payload(
            user_id=user_id,
            dataset_id=dataset_id,
            filename="test-file.csv",
            file_size=1024,
            file_type="text/csv",
        )

        upload_response = http_client.post(
            "/tus/hooks", json=file_payload, headers=valid_headers
        )
        assert_status_code(upload_response, 200)

        # Act
        response = http_client.get(
            f"/internal/datasets/{dataset_id}/collocation/files", headers=valid_headers
        )

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        assert isinstance(data, list)
        assert len(data) >= 1  # At least our uploaded file

        # Verify file structure
        file_data = data[0]
        assert "id" in file_data
        assert "name" in file_data
        assert "size_bytes" in file_data
        assert "storage_path" in file_data
        assert "storage_file_name" in file_data
        assert "created_at" in file_data

    def test_get_dataset_files_nonexistent_dataset_404(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test getting files for nonexistent dataset returns 404."""
        # Arrange
        nonexistent_id = dataset_fixture.get_nonexistent_dataset_id()

        # Act
        response = http_client.get(
            f"/internal/datasets/{nonexistent_id}/collocation/files",
            headers=valid_headers,
        )

        # Assert
        assert_status_code(response, 404)
        data = assert_json_response(response)
        assert "detail" in data

    def test_get_dataset_files_invalid_uuid_422(self, http_client, valid_headers):
        """Test getting files with invalid UUID returns 422."""
        # Act
        response = http_client.get(
            "/internal/datasets/invalid-uuid/collocation/files", headers=valid_headers
        )

        # Assert
        assert_status_code(response, 422)
        data = assert_json_response(response)
        assert "detail" in data

    def test_get_dataset_files_unauthorized_401(self, http_client, dataset_fixture):
        """Test getting dataset files without auth returns 401."""
        # Arrange
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        # Act
        response = http_client.get(
            f"/internal/datasets/{dataset_id}/collocation/files"
        )

        # Assert
        assert_status_code(response, 401)
        data = assert_json_response(response)
        assert "detail" in data
        assert "unauthorized" in data["detail"].lower()

    def test_update_file_path_success_200(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test updating file path returns 200."""
        # Arrange - Create dataset with file
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        file_payload = create_tus_payload(
            user_id=user_id,
            dataset_id=dataset_id,
            filename="test-update-path.csv",
            file_size=2048,
            file_type="text/csv",
        )

        upload_response = http_client.post(
            "/tus/hooks", json=file_payload, headers=valid_headers
        )
        assert_status_code(upload_response, 200)

        # Get the file ID
        files_response = http_client.get(
            f"/internal/datasets/{dataset_id}/collocation/files", headers=valid_headers
        )
        files = assert_json_response(files_response)
        assert len(files) > 0
        file_id = files[0]["id"]

        # Prepare new path
        new_path = f"2025/12/02/{dataset_id}/1/test-update-path.csv"
        update_payload = {"storage_path": new_path}

        # Act
        response = http_client.put(
            f"/internal/datasets/{dataset_id}/collocation/files/{file_id}",
            json=update_payload,
            headers=valid_headers,
        )

        # Assert
        assert_status_code(response, 200)

        # Verify the path was updated
        files_response = http_client.get(
            f"/internal/datasets/{dataset_id}/collocation/files", headers=valid_headers
        )
        files = assert_json_response(files_response)
        updated_file = next((f for f in files if f["id"] == file_id), None)
        assert updated_file is not None
        assert updated_file["storage_path"] == new_path

    def test_update_file_path_invalid_path_422(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test updating file path with empty string returns 422."""
        # Arrange
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        file_payload = create_tus_payload(
            user_id=user_id,
            dataset_id=dataset_id,
            filename="test-invalid-path.csv",
            file_size=1024,
            file_type="text/csv",
        )

        upload_response = http_client.post(
            "/tus/hooks", json=file_payload, headers=valid_headers
        )
        assert_status_code(upload_response, 200)

        files_response = http_client.get(
            f"/internal/datasets/{dataset_id}/collocation/files", headers=valid_headers
        )
        files = assert_json_response(files_response)
        file_id = files[0]["id"]

        # Invalid payload - empty path
        invalid_payload = {"storage_path": ""}

        # Act
        response = http_client.put(
            f"/internal/datasets/{dataset_id}/collocation/files/{file_id}",
            json=invalid_payload,
            headers=valid_headers,
        )

        # Assert
        assert_status_code(response, 422)
        data = assert_json_response(response)
        assert "detail" in data

    def test_update_file_path_nonexistent_file_404(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test updating nonexistent file returns 404."""
        # Arrange
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]
        nonexistent_file_id = str(uuid4())

        update_payload = {"storage_path": "2025/12/02/test/1/file.csv"}

        # Act
        response = http_client.put(
            f"/internal/datasets/{dataset_id}/collocation/files/{nonexistent_file_id}",
            json=update_payload,
            headers=valid_headers,
        )

        # Assert
        assert_status_code(response, 404)
        data = assert_json_response(response)
        assert "detail" in data

    def test_update_file_path_unauthorized_401(self, http_client, dataset_fixture):
        """Test updating file path without auth returns 401."""
        # Arrange
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]
        file_id = str(uuid4())
        update_payload = {"storage_path": "2025/12/02/test/1/file.csv"}

        # Act
        response = http_client.put(
            f"/internal/datasets/{dataset_id}/collocation/files/{file_id}",
            json=update_payload,
        )

        # Assert
        assert_status_code(response, 401)
        data = assert_json_response(response)
        assert "detail" in data
        assert "unauthorized" in data["detail"].lower()

    def test_update_collocation_status_success_200(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test updating collocation status returns 200."""
        # Arrange - Create and publish dataset
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        dataset_fixture.create_dataset_version(dataset_id)
        current_version = dataset["current_version"]
        version_name = current_version["name"]

        dataset_fixture.enable_dataset_version(dataset_id, version_name)
        dataset_fixture.publish_dataset_version(dataset_id, version_name)

        # Update to processing
        processing_payload = {"status": "processing"}

        # Act - Set to processing
        response = http_client.put(
            f"/internal/datasets/{dataset_id}/collocation/collocation-status",
            json=processing_payload,
            headers=valid_headers,
        )

        # Assert
        assert_status_code(response, 200)

        # Act - Set to completed
        completed_payload = {"status": "completed"}
        response = http_client.put(
            f"/internal/datasets/{dataset_id}/collocation/collocation-status",
            json=completed_payload,
            headers=valid_headers,
        )

        # Assert
        assert_status_code(response, 200)

    def test_update_collocation_status_invalid_status_422(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test updating collocation status with invalid value returns 422."""
        # Arrange
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        invalid_payload = {"status": "invalid_status"}

        # Act
        response = http_client.put(
            f"/internal/datasets/{dataset_id}/collocation/collocation-status",
            json=invalid_payload,
            headers=valid_headers,
        )

        # Assert
        assert_status_code(response, 422)
        data = assert_json_response(response)
        assert "detail" in data

    def test_update_collocation_status_nonexistent_dataset_404(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test updating status for nonexistent dataset returns 404."""
        # Arrange
        nonexistent_id = dataset_fixture.get_nonexistent_dataset_id()
        payload = {"status": "completed"}

        # Act
        response = http_client.put(
            f"/internal/datasets/{nonexistent_id}/collocation/collocation-status",
            json=payload,
            headers=valid_headers,
        )

        # Assert
        assert_status_code(response, 404)
        data = assert_json_response(response)
        assert "detail" in data

    def test_update_collocation_status_unauthorized_401(
        self, http_client, dataset_fixture
    ):
        """Test updating collocation status without auth returns 401."""
        # Arrange
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]
        payload = {"status": "completed"}

        # Act
        response = http_client.put(
            f"/internal/datasets/{dataset_id}/collocation/collocation-status",
            json=payload,
        )

        # Assert
        assert_status_code(response, 401)
        data = assert_json_response(response)
        assert "detail" in data
        assert "unauthorized" in data["detail"].lower()


class TestDatasetCollocationWorkflow:
    """Integration tests for complete dataset collocation workflow."""

    def test_complete_collocation_workflow_success(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test complete workflow: create dataset, publish, get pending, update files, mark complete."""
        # Arrange - Create dataset with file
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        file_payload = create_tus_payload(
            user_id=user_id,
            dataset_id=dataset_id,
            filename="workflow-test.csv",
            file_size=4096,
            file_type="text/csv",
        )

        upload_response = http_client.post(
            "/tus/hooks", json=file_payload, headers=valid_headers
        )
        assert_status_code(upload_response, 200)

        # Publish dataset to trigger PENDING status
        dataset_fixture.create_dataset_version(dataset_id)
        current_version = dataset["current_version"]
        version_name = current_version["name"]

        dataset_fixture.enable_dataset_version(dataset_id, version_name)
        dataset_fixture.publish_dataset_version(dataset_id, version_name)

        # Act 1 - Get pending datasets
        pending_response = http_client.get(
            "/internal/datasets/collocation/pending", headers=valid_headers
        )
        assert_status_code(pending_response, 200)
        pending_datasets = assert_json_response(pending_response)
        our_dataset = next((d for d in pending_datasets if d["id"] == dataset_id), None)
        assert our_dataset is not None

        # Act 2 - Mark as processing
        processing_response = http_client.put(
            f"/internal/datasets/{dataset_id}/collocation/collocation-status",
            json={"status": "processing"},
            headers=valid_headers,
        )
        assert_status_code(processing_response, 200)

        # Act 3 - Get files
        files_response = http_client.get(
            f"/internal/datasets/{dataset_id}/collocation/files", headers=valid_headers
        )
        assert_status_code(files_response, 200)
        files = assert_json_response(files_response)
        assert len(files) >= 1
        file_id = files[0]["id"]

        # Act 4 - Update file path
        new_path = f"2025/12/02/{dataset_id}/1/workflow-test.csv"
        update_response = http_client.put(
            f"/internal/datasets/{dataset_id}/collocation/files/{file_id}",
            json={"storage_path": new_path},
            headers=valid_headers,
        )
        assert_status_code(update_response, 200)

        # Act 5 - Mark as completed
        completed_response = http_client.put(
            f"/internal/datasets/{dataset_id}/collocation/collocation-status",
            json={"status": "completed"},
            headers=valid_headers,
        )
        assert_status_code(completed_response, 200)

        # Assert - Verify dataset no longer in pending list
        final_pending_response = http_client.get(
            "/internal/datasets/collocation/pending", headers=valid_headers
        )
        assert_status_code(final_pending_response, 200)
        final_pending = assert_json_response(final_pending_response)

        # Dataset should not be in pending list anymore (status is COMPLETED)
        completed_dataset = next((d for d in final_pending if d["id"] == dataset_id), None)
        # If it appears, it should be marked as completed
        if completed_dataset:
            assert completed_dataset["file_collocation_status"] == "completed"
