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
                "institution": "Test Institution",
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

        if response.status_code not in [200, 201]:
            raise Exception(
                f"Failed to create dataset version: {response.status_code} - {response.text}"
            )

        # Get updated dataset with version
        response = self.http_client.get(
            f"/datasets/{dataset_id}", headers=self.auth_headers
        )

        return response.json()

    def create_published_dataset_with_snapshot_legacy(self) -> Dict[str, Any]:
        """
        Create a dataset with a published version and snapshot (legacy method).

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

    def create_dataset_with_doi(
        self, doi_identifier: str = None, doi_mode: str = "MANUAL"
    ) -> Dict[str, Any]:
        """Create a dataset with version and DOI."""
        # Create dataset with version
        dataset = self.create_dataset_with_version()
        dataset_id = dataset["id"]
        current_version = dataset["current_version"]
        version_name = current_version["name"]

        # Enable and publish the version first
        enable_response = self.http_client.put(
            f"/datasets/{dataset_id}/versions/{version_name}/enable",
            headers=self.auth_headers,
        )

        if enable_response.status_code != 200:
            raise Exception(
                f"Failed to enable dataset version: {enable_response.status_code} - {enable_response.text}"
            )

        publish_response = self.http_client.put(
            f"/datasets/{dataset_id}/versions/{version_name}/publish",
            headers=self.auth_headers,
        )

        if publish_response.status_code != 200:
            raise Exception(
                f"Failed to publish dataset version: {publish_response.status_code} - {publish_response.text}"
            )

        # Create DOI
        doi_data = {"mode": doi_mode}
        
        if doi_mode == "MANUAL":
            if doi_identifier is None:
                unique_id = str(uuid.uuid4())[:8]
                doi_identifier = f"10.82978/MANUAL{unique_id}"
            doi_data["identifier"] = doi_identifier
        # For AUTO mode, no identifier is provided - it's auto-generated by the service

        doi_response = self.http_client.post(
            f"/datasets/{dataset_id}/versions/{version_name}/doi",
            json=doi_data,
            headers=self.auth_headers,
        )

        if doi_response.status_code not in [200, 201]:
            raise Exception(
                f"Failed to create DOI: {doi_response.status_code} - {doi_response.text}"
            )

        # Get updated dataset
        response = self.http_client.get(
            f"/datasets/{dataset_id}", headers=self.auth_headers
        )

        if response.status_code != 200:
            raise Exception(
                f"Failed to get updated dataset: {response.status_code} - {response.text}"
            )

        return response.json()

    def create_published_dataset_with_snapshot(
        self, doi_identifier: str = None, doi_mode: str = "MANUAL"
    ) -> Dict[str, Any]:
        """
        Create a dataset with a published version, DOI, and snapshot.
        
        This creates a complete workflow: dataset -> version -> publish -> DOI -> snapshot
        """
        # Create dataset with DOI (this will trigger snapshot publication for MANUAL mode)
        dataset = self.create_dataset_with_doi(doi_identifier, doi_mode)
        dataset_id = dataset["id"]

        # For AUTO mode, we need to change DOI state to FINDABLE to trigger snapshot
        if doi_mode == "AUTO":
            current_version = dataset["current_version"]
            version_name = current_version["name"]

            state_change_data = {"state": "FINDABLE"}

            state_response = self.http_client.put(
                f"/datasets/{dataset_id}/versions/{version_name}/doi",
                json=state_change_data,
                headers=self.auth_headers,
            )

            if state_response.status_code != 200:
                raise Exception(
                    f"Failed to change DOI state: {state_response.status_code} - {state_response.text}"
                )

        return dataset

    def create_dataset_version(
        self, dataset_id: str, datafiles_previously_uploaded: list = None
    ) -> Dict[str, Any]:
        """Create a new version for an existing dataset."""
        if datafiles_previously_uploaded is None:
            datafiles_previously_uploaded = []

        version_data = {"datafilesPreviouslyUploaded": datafiles_previously_uploaded}

        response = self.http_client.post(
            f"/datasets/{dataset_id}/versions",
            json=version_data,
            headers=self.auth_headers,
        )

        if response.status_code not in [200, 201]:
            raise Exception(
                f"Failed to create dataset version: {response.status_code} - {response.text}"
            )

        return response.json()

    def publish_dataset_version(
        self, dataset_id: str, version_name: str
    ) -> Dict[str, Any]:
        """Publish a dataset version."""
        response = self.http_client.put(
            f"/datasets/{dataset_id}/versions/{version_name}/publish",
            headers=self.auth_headers,
        )

        if response.status_code != 200:
            raise Exception(
                f"Failed to publish dataset version: {response.status_code} - {response.text}"
            )

        return response.json()

    def enable_dataset_version(
        self, dataset_id: str, version_name: str
    ) -> Dict[str, Any]:
        """Enable a dataset version."""
        response = self.http_client.put(
            f"/datasets/{dataset_id}/versions/{version_name}/enable",
            headers=self.auth_headers,
        )

        if response.status_code != 200:
            raise Exception(
                f"Failed to enable dataset version: {response.status_code} - {response.text}"
            )

        return response.json()

    def create_doi_for_version(
        self, dataset_id: str, version_name: str, doi_identifier: str = None, doi_mode: str = "MANUAL"
    ) -> Dict[str, Any]:
        """Create a DOI for a specific dataset version."""
        doi_data = {"mode": doi_mode}
        
        if doi_mode == "MANUAL":
            if doi_identifier is None:
                unique_id = str(uuid.uuid4())[:8]
                doi_identifier = f"10.82978/MANUAL{unique_id}"
            doi_data["identifier"] = doi_identifier
        # For AUTO mode, no identifier is provided - it's auto-generated by the service

        response = self.http_client.post(
            f"/datasets/{dataset_id}/versions/{version_name}/doi",
            json=doi_data,
            headers=self.auth_headers,
        )

        if response.status_code not in [200, 201]:
            raise Exception(
                f"Failed to create DOI: {response.status_code} - {response.text}"
            )

        return response.json()

    def change_doi_state(
        self, dataset_id: str, version_name: str, new_state: str
    ) -> Dict[str, Any]:
        """Change the state of a DOI."""
        state_change_data = {"state": new_state}

        response = self.http_client.put(
            f"/datasets/{dataset_id}/versions/{version_name}/doi",
            json=state_change_data,
            headers=self.auth_headers,
        )

        if response.status_code != 200:
            raise Exception(
                f"Failed to change DOI state: {response.status_code} - {response.text}"
            )

        return response.json()
