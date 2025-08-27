import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.controller.v1.dataset.dataset_snapshot import router
from app.service.dataset import DatasetService
from app.exception.not_found import NotFoundException
from app.exception.illegal_state import IllegalStateException


class TestDatasetSnapshotController(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)
        
        # Mock the dataset service
        self.mock_dataset_service = Mock(spec=DatasetService)

    @patch('app.controller.v1.dataset.dataset_snapshot.Container.dataset_service')
    def test_get_dataset_latest_snapshot_success(self, mock_service_provider):
        # Arrange
        dataset_id = uuid4()
        mock_snapshot = {
            "dataset_id": str(dataset_id),
            "version_name": "v2.0",
            "doi_identifier": "10.1234/test",
            "doi_state": "FINDABLE",
            "publication_date": "2024-01-01T00:00:00",
            "title": "Test Dataset",
            "description": "A test dataset",
            "versions": [
                {
                    "id": str(uuid4()),
                    "name": "v2.0",
                    "doi_identifier": "10.1234/test",
                    "doi_state": "FINDABLE",
                    "created_at": "2024-01-01T00:00:00"
                }
            ]
        }
        
        # Mock dependency injection
        mock_service_provider.return_value = self.mock_dataset_service
        self.mock_dataset_service.get_dataset_latest_snapshot.return_value = mock_snapshot
        
        # Act
        response = self.client.get(f"/datasets/{dataset_id}/snapshot")
        
        # Assert
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["dataset_id"], str(dataset_id))
        self.assertEqual(data["version_name"], "v2.0")
        self.assertEqual(data["doi_identifier"], "10.1234/test")
        self.assertEqual(data["doi_state"], "FINDABLE")
        self.assertEqual(data["publication_date"], "2024-01-01T00:00:00")
        
        # Check that typed fields are excluded from data
        self.assertIn("title", data["data"])
        self.assertIn("description", data["data"])
        self.assertNotIn("dataset_id", data["data"])
        self.assertNotIn("version_name", data["data"])
        self.assertNotIn("versions", data["data"])
        
        # Check versions list
        self.assertEqual(len(data["versions"]), 1)
        self.assertEqual(data["versions"][0]["name"], "v2.0")
        
        self.mock_dataset_service.get_dataset_latest_snapshot.assert_called_once_with(dataset_id)

    @patch('app.controller.v1.dataset.dataset_snapshot.Container.dataset_service')
    def test_get_dataset_latest_snapshot_not_found(self, mock_service_provider):
        # Arrange
        dataset_id = uuid4()
        mock_service_provider.return_value = self.mock_dataset_service
        self.mock_dataset_service.get_dataset_latest_snapshot.side_effect = NotFoundException("Not found")
        
        # Act
        response = self.client.get(f"/datasets/{dataset_id}/snapshot")
        
        # Assert
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Snapshot not found")

    @patch('app.controller.v1.dataset.dataset_snapshot.Container.dataset_service')
    def test_get_dataset_latest_snapshot_invalid_data(self, mock_service_provider):
        # Arrange
        dataset_id = uuid4()
        mock_service_provider.return_value = self.mock_dataset_service
        self.mock_dataset_service.get_dataset_latest_snapshot.side_effect = IllegalStateException("Invalid data")
        
        # Act
        response = self.client.get(f"/datasets/{dataset_id}/snapshot")
        
        # Assert
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Invalid snapshot data")

    @patch('app.controller.v1.dataset.dataset_snapshot.Container.dataset_service')
    def test_get_dataset_version_snapshot_success(self, mock_service_provider):
        # Arrange
        dataset_id = uuid4()
        version_name = "v1.0"
        mock_snapshot = {
            "dataset_id": str(dataset_id),
            "version_name": version_name,
            "doi_identifier": "10.1234/test",
            "doi_state": "FINDABLE",
            "publication_date": "2024-01-01T00:00:00",
            "title": "Test Dataset",
            "description": "A test dataset"
        }
        
        # Mock dependency injection
        mock_service_provider.return_value = self.mock_dataset_service
        self.mock_dataset_service.get_dataset_version_snapshot.return_value = mock_snapshot
        
        # Act
        response = self.client.get(f"/datasets/{dataset_id}/versions/{version_name}/snapshot")
        
        # Assert
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["dataset_id"], str(dataset_id))
        self.assertEqual(data["version_name"], version_name)
        self.assertEqual(data["doi_identifier"], "10.1234/test")
        self.assertEqual(data["doi_state"], "FINDABLE")
        self.assertEqual(data["publication_date"], "2024-01-01T00:00:00")
        
        # Check that typed fields are excluded from data
        self.assertIn("title", data["data"])
        self.assertIn("description", data["data"])
        self.assertNotIn("dataset_id", data["data"])
        self.assertNotIn("version_name", data["data"])
        
        # Version snapshot should not have versions list
        self.assertNotIn("versions", data)
        
        self.mock_dataset_service.get_dataset_version_snapshot.assert_called_once_with(dataset_id, version_name)

    @patch('app.controller.v1.dataset.dataset_snapshot.Container.dataset_service')
    def test_get_dataset_version_snapshot_not_found(self, mock_service_provider):
        # Arrange
        dataset_id = uuid4()
        version_name = "v1.0"
        mock_service_provider.return_value = self.mock_dataset_service
        self.mock_dataset_service.get_dataset_version_snapshot.side_effect = NotFoundException("Not found")
        
        # Act
        response = self.client.get(f"/datasets/{dataset_id}/versions/{version_name}/snapshot")
        
        # Assert
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Snapshot not found")

    @patch('app.controller.v1.dataset.dataset_snapshot.Container.dataset_service')
    def test_get_dataset_version_snapshot_invalid_data(self, mock_service_provider):
        # Arrange
        dataset_id = uuid4()
        version_name = "v1.0"
        mock_service_provider.return_value = self.mock_dataset_service
        self.mock_dataset_service.get_dataset_version_snapshot.side_effect = IllegalStateException("Invalid data")
        
        # Act
        response = self.client.get(f"/datasets/{dataset_id}/versions/{version_name}/snapshot")
        
        # Assert
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Invalid snapshot data")

    def test_response_content_type_is_json(self):
        # Test that responses have application/json content type
        dataset_id = uuid4()
        
        with patch('app.controller.v1.dataset.dataset_snapshot.Container.dataset_service') as mock_service_provider:
            mock_service_provider.return_value = self.mock_dataset_service
            self.mock_dataset_service.get_dataset_latest_snapshot.side_effect = NotFoundException("Not found")
            
            response = self.client.get(f"/datasets/{dataset_id}/snapshot")
            
            self.assertEqual(response.headers["content-type"], "application/json")


if __name__ == "__main__":
    unittest.main()
