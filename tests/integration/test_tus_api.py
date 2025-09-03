from uuid import uuid4

from tests.integration.fixtures.tus_auth import (
    create_tus_payload,
    create_invalid_tus_payload,
    create_malformed_tus_payload,
    create_tus_jwt_token,
)
from tests.integration.utils.assertions import assert_status_code, assert_json_response


class TestTusHooksEndpoint:
    """Integration tests for TUS hooks endpoint."""

    def test_post_finish_hook_success_200(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test successful post-finish hook processing."""
        # Arrange
        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        payload = create_tus_payload(
            user_id=user_id,
            dataset_id=dataset_id,
            filename="test-document.pdf",
            file_size=2048,
            file_type="application/pdf",
        )

        # Act
        response = http_client.post("/tus/hooks", json=payload, headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        # TUS returns empty dict on success
        assert data == {}

    def test_post_finish_hook_invalid_user_token_200(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test post-finish hook with invalid user token returns 200 (ignored)."""
        # Arrange
        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        payload = create_invalid_tus_payload(user_id, dataset_id)

        # Act
        response = http_client.post("/tus/hooks", json=payload, headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        # Invalid tokens are ignored and return empty response
        assert data == {}

    def test_post_finish_hook_missing_user_id_500(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test post-finish hook with missing user ID returns 500."""
        # Arrange
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        payload = {
            "Type": "post-finish",
            "Event": {
                "Upload": {
                    "Size": 1024,
                    "MetaData": {
                        "dataset_id": dataset_id,
                        "filename": "test.txt",
                        "filetype": "text/plain",
                    },
                    "Storage": {"Key": "test-files/test.txt", "Bucket": "test-bucket"},
                },
                "HTTPRequest": {
                    "Header": {
                        "X-User-Token": [
                            create_tus_jwt_token("cbb0a683-630f-4b86-8b45-91b90a6fce1c")
                        ]
                        # Missing X-User-Id
                    }
                },
            },
        }

        # Act
        response = http_client.post("/tus/hooks", json=payload, headers=valid_headers)

        # Assert
        assert_status_code(response, 500)
        data = assert_json_response(response)
        assert "detail" in data
        assert "'X-User-Id'" in data["detail"]

    def test_post_finish_hook_missing_user_token_500(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test post-finish hook with missing user token returns 500."""
        # Arrange
        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        payload = {
            "Type": "post-finish",
            "Event": {
                "Upload": {
                    "Size": 1024,
                    "MetaData": {
                        "dataset_id": dataset_id,
                        "filename": "test.txt",
                        "filetype": "text/plain",
                    },
                    "Storage": {"Key": "test-files/test.txt", "Bucket": "test-bucket"},
                },
                "HTTPRequest": {
                    "Header": {
                        "X-User-Id": [user_id]
                        # Missing X-User-Token
                    }
                },
            },
        }

        # Act
        response = http_client.post("/tus/hooks", json=payload, headers=valid_headers)

        # Assert
        assert_status_code(response, 500)
        data = assert_json_response(response)
        assert "detail" in data
        assert "'X-User-Token'" in data["detail"]

    def test_post_finish_hook_invalid_dataset_id_500(self, http_client, valid_headers):
        """Test post-finish hook with invalid dataset ID returns 500."""
        # Arrange
        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        invalid_dataset_id = str(uuid4())

        payload = create_tus_payload(
            user_id=user_id, dataset_id=invalid_dataset_id, filename="test.txt"
        )

        # Act
        response = http_client.post("/tus/hooks", json=payload, headers=valid_headers)

        # Assert
        assert_status_code(response, 500)
        data = assert_json_response(response)
        assert "HTTPResponse" in data
        assert data["HTTPResponse"]["StatusCode"] == 500
        assert "RejectUpload" in data
        assert data["RejectUpload"] is True

    def test_post_finish_hook_malformed_payload_500(self, http_client, valid_headers):
        """Test post-finish hook with malformed payload returns 500."""
        # Arrange
        payload = create_malformed_tus_payload()

        # Act
        response = http_client.post("/tus/hooks", json=payload, headers=valid_headers)

        # Assert
        assert_status_code(response, 500)
        data = assert_json_response(response)
        assert "HTTPResponse" in data
        assert data["HTTPResponse"]["StatusCode"] == 500
        assert "RejectUpload" in data
        assert data["RejectUpload"] is True

    def test_post_finish_hook_unauthorized_200(self, http_client, dataset_fixture):
        """Test post-finish hook without authentication returns 200 (ignored)."""
        # Arrange
        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        payload = create_tus_payload(user_id, dataset_id)

        # Act
        response = http_client.post("/tus/hooks", json=payload)  # No headers

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        # Missing authentication is ignored and returns empty response
        assert data == {}

    def test_unknown_hook_type_200(self, http_client, valid_headers, dataset_fixture):
        """Test unknown hook type returns 200 (ignored)."""
        # Arrange
        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        payload = create_tus_payload(user_id, dataset_id)
        payload["Type"] = "unknown-hook-type"

        # Act
        response = http_client.post("/tus/hooks", json=payload, headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        # Unknown hook types return empty dict
        assert data == {}

    def test_post_finish_hook_different_file_types(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test post-finish hook with different file types."""
        # Arrange
        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        file_types = [
            ("document.pdf", "application/pdf", 5000),
            ("image.jpg", "image/jpeg", 2000),
            ("data.csv", "text/csv", 1500),
            ("archive.zip", "application/zip", 10000),
        ]

        for filename, file_type, file_size in file_types:
            payload = create_tus_payload(
                user_id=user_id,
                dataset_id=dataset_id,
                filename=filename,
                file_type=file_type,
                file_size=file_size,
            )

            # Act
            response = http_client.post(
                "/tus/hooks", json=payload, headers=valid_headers
            )

            # Assert
            assert_status_code(response, 200)
            data = assert_json_response(response)
            assert data == {}

    def test_post_finish_hook_large_file(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test post-finish hook with large file."""
        # Arrange
        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        payload = create_tus_payload(
            user_id=user_id,
            dataset_id=dataset_id,
            filename="large-file.bin",
            file_type="application/octet-stream",
            file_size=100 * 1024 * 1024,  # 100MB
        )

        # Act
        response = http_client.post("/tus/hooks", json=payload, headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        assert data == {}

    def test_post_finish_hook_special_characters_filename(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test post-finish hook with special characters in filename."""
        # Arrange
        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        payload = create_tus_payload(
            user_id=user_id,
            dataset_id=dataset_id,
            filename="test file with spaces & symbols!.txt",
            file_type="text/plain",
        )

        # Act
        response = http_client.post("/tus/hooks", json=payload, headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        assert data == {}


class TestTusErrorScenarios:
    """Integration tests for TUS error scenarios."""

    def test_post_finish_hook_invalid_json_422(self, http_client, valid_headers):
        """Test post-finish hook with invalid JSON returns 422."""
        # Act
        response = http_client.post(
            "/tus/hooks",
            data="invalid json",
            headers={**valid_headers, "Content-Type": "application/json"},
        )

        # Assert
        assert_status_code(response, 422)
        data = assert_json_response(response)
        assert "detail" in data

    def test_post_finish_hook_missing_type_field_500(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test post-finish hook with missing Type field returns 500."""
        # Arrange
        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        payload = create_tus_payload(user_id, dataset_id)
        del payload["Type"]  # Remove Type field

        # Act
        response = http_client.post("/tus/hooks", json=payload, headers=valid_headers)

        # Assert
        assert_status_code(response, 500)
        data = assert_json_response(response)
        assert "detail" in data
        assert "'Type'" in data["detail"]

    def test_post_finish_hook_missing_event_field_500(
        self, http_client, valid_headers, dataset_fixture
    ):
        """Test post-finish hook with missing Event field returns 500."""
        # Arrange
        user_id = "cbb0a683-630f-4b86-8b45-91b90a6fce1c"
        dataset = dataset_fixture.create_test_dataset()
        dataset_id = dataset["id"]

        payload = create_tus_payload(user_id, dataset_id)
        del payload["Event"]  # Remove Event field

        # Act
        response = http_client.post("/tus/hooks", json=payload, headers=valid_headers)

        # Assert
        assert_status_code(response, 500)
        data = assert_json_response(response)
        assert "detail" in data
        assert "'Event'" in data["detail"]

    def test_post_finish_hook_empty_payload_500(self, http_client, valid_headers):
        """Test post-finish hook with empty payload returns 500."""
        # Act
        response = http_client.post("/tus/hooks", json={}, headers=valid_headers)

        # Assert
        assert_status_code(response, 500)
        data = assert_json_response(response)
        assert "detail" in data
        assert "'Event'" in data["detail"]
