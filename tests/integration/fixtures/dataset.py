"""Dataset fixtures for integration tests."""

import uuid
from typing import Dict, Any
from tests.integration.utils.http_client import HttpClient
from tests.integration.fixtures.auth import AuthFixture


class DatasetFixture:
    """Dataset fixture factory for creating test datasets."""

    def __init__(self, http_client: HttpClient):
        """Initialize with HTTP client."""
        self.http_client = http_client
        self.auth_headers = AuthFixture.valid_headers()

    def get_basic_dataset_data(self) -> Dict[str, Any]:
        """Get basic dataset data for creation."""
        unique_id = str(uuid.uuid4())[:8]
        return {
            "name": f"Integration Test Dataset {unique_id}",
            "data": {
                "title": f"Integration Test Dataset {unique_id}",
                "description": "Dataset created for integration testing",
                "keywords": ["integration", "test", "dataset"],
                "authors": [{"name": "Test Author", "email": "test@example.com"}],
                "license": "MIT",
                "version": "1.0.0",
            },
            "tenancy": "datamap/production/data-amazon",
        }

    def create_test_dataset(self) -> Dict[str, Any]:
        """Create a new test dataset via API and return its data."""
        dataset_data = self.get_basic_dataset_data()

        response = self.http_client.post(
            "/datasets", json=dataset_data, headers=self.auth_headers
        )

        if response.status_code != 201:
            raise Exception(
                f"Failed to create test dataset: {response.status_code} - {response.text}"
            )

        return response.json()

    def create_dataset_with_version(self) -> Dict[str, Any]:
        """Create a dataset and add a version to it."""
        dataset = self.create_test_dataset()
        dataset_id = dataset["id"]

        # Create a version
        version_data = {"datafilesPreviouslyUploaded": []}

        response = self.http_client.post(
            f"/datasets/{dataset_id}/versions",
            json=version_data,
            headers=self.auth_headers,
        )

        if response.status_code != 201:
            raise Exception(
                f"Failed to create dataset version: {response.status_code} - {response.text}"
            )

        # Get updated dataset with version
        response = self.http_client.get(
            f"/datasets/{dataset_id}", headers=self.auth_headers
        )

        return response.json()

    def create_published_dataset_with_snapshot(self) -> Dict[str, Any]:
        """
        Create a dataset with a published version and snapshot.

        Note: This would require DOI creation and publishing workflow.
        For now, returns a dataset with version that can be used for snapshot testing.
        """
        dataset = self.create_dataset_with_version()
        dataset_id = dataset["id"]

        # Get the current version name
        current_version = dataset.get("current_version")
        if not current_version:
            raise Exception("No current version found on created dataset")

        version_name = current_version["name"]

        # Enable the version (prerequisite for publishing)
        response = self.http_client.put(
            f"/datasets/{dataset_id}/versions/{version_name}/enable",
            headers=self.auth_headers,
        )

        if response.status_code != 200:
            raise Exception(
                f"Failed to enable dataset version: {response.status_code} - {response.text}"
            )

        # Try to publish the version
        # Note: This might fail if DOI creation is required and not properly mocked
        try:
            response = self.http_client.put(
                f"/datasets/{dataset_id}/versions/{version_name}/publish",
                headers=self.auth_headers,
            )

            if response.status_code == 200:
                # Successfully published, get updated dataset
                response = self.http_client.get(
                    f"/datasets/{dataset_id}", headers=self.auth_headers
                )
                return response.json()
        except Exception:
            # Publishing failed, but we still have a dataset with version
            pass

        return dataset

    def get_nonexistent_dataset_id(self) -> str:
        """Get a UUID that doesn't exist in the database."""
        return str(uuid.uuid4())

    def get_invalid_dataset_id(self) -> str:
        """Get an invalid UUID format for validation testing."""
        return "invalid-uuid-format"
