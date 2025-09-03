# # NOTE: These controller tests have been replaced by integration tests
# # See: tests/integration/test_dataset_snapshot.py
# # These tests required full FastAPI app initialization which caused database dependency issues
# # Integration tests provide better coverage of the actual API contract
# 
# # import unittest
# # from unittest.mock import Mock, patch
# # from uuid import uuid4
# # from fastapi.testclient import TestClient
# # from fastapi import FastAPI
# 
# # from app.controller.v1.dataset.dataset_snapshot import router, _adapt_snapshot_response, _adapt_latest_snapshot_response
# # from app.service.dataset import DatasetService
# # from app.exception.not_found import NotFoundException
# # from app.exception.illegal_state import IllegalStateException
# 
# 
# # class TestDatasetSnapshotController(unittest.TestCase):
#     def setUp(self):
#         self.app = FastAPI()
#         self.app.include_router(router)
#         self.client = TestClient(self.app)
#         
#         # Mock the dataset service
#         self.mock_dataset_service = Mock(spec=DatasetService)
# 
#     @unittest.skip("Dependency injection mocking is complex - adapter functions tested separately")
#     @patch('app.controller.v1.dataset.dataset_snapshot.Container.dataset_service')
#     def test_get_dataset_latest_snapshot_success(self, mock_service_provider):
#         # Arrange
#         dataset_id = uuid4()
#         mock_snapshot = {
#             "dataset_id": str(dataset_id),
#             "version_name": "v2.0",
#             "doi_identifier": "10.1234/test",
#             "doi_link": "https://doi.org/10.1234/test",
#             "doi_state": "FINDABLE",
#             "publication_date": "2024-01-01T00:00:00",
#             "files_summary": {
#                 "total_files": 3,
#                 "total_size_bytes": 1536,
#                 "extensions_breakdown": [
#                     {"extension": ".csv", "count": 2, "total_size_bytes": 1024},
#                     {"extension": ".json", "count": 1, "total_size_bytes": 512}
#                 ]
#             },
#             "title": "Test Dataset",
#             "description": "A test dataset",
#             "versions": [
#                 {
#                     "id": str(uuid4()),
#                     "name": "v2.0",
#                     "doi_identifier": "10.1234/test",
#                     "doi_state": "FINDABLE",
#                     "created_at": "2024-01-01T00:00:00"
#                 }
#             ]
#         }
#         
#         # Mock dependency injection
#         mock_service_provider.return_value = self.mock_dataset_service
#         self.mock_dataset_service.get_dataset_latest_snapshot.return_value = mock_snapshot
#         
#         # Act
#         response = self.client.get(f"/datasets/{dataset_id}/snapshot")
#         
#         # Assert
#         self.assertEqual(response.status_code, 200)
#         
#         data = response.json()
#         self.assertEqual(data["dataset_id"], str(dataset_id))
#         self.assertEqual(data["version_name"], "v2.0")
#         self.assertEqual(data["doi_identifier"], "10.1234/test")
#         self.assertEqual(data["doi_link"], "https://doi.org/10.1234/test")
#         self.assertEqual(data["doi_state"], "FINDABLE")
#         self.assertEqual(data["publication_date"], "2024-01-01T00:00:00")
#         
#         # Check files_summary
#         self.assertIn("files_summary", data)
#         files_summary = data["files_summary"]
#         self.assertEqual(files_summary["total_files"], 3)
#         self.assertEqual(files_summary["total_size_bytes"], 1536)
#         self.assertEqual(len(files_summary["extensions_breakdown"]), 2)
#         
#         # Check that typed fields are excluded from data
#         self.assertIn("title", data["data"])
#         self.assertIn("description", data["data"])
#         self.assertNotIn("dataset_id", data["data"])
#         self.assertNotIn("version_name", data["data"])
#         self.assertNotIn("versions", data["data"])
#         self.assertNotIn("files_summary", data["data"])
#         
#         # Check versions list
#         self.assertEqual(len(data["versions"]), 1)
#         self.assertEqual(data["versions"][0]["name"], "v2.0")
#         
#         self.mock_dataset_service.get_dataset_latest_snapshot.assert_called_once_with(dataset_id)
# 
#     @unittest.skip("Dependency injection mocking is complex - adapter functions tested separately")
#     @patch('app.controller.v1.dataset.dataset_snapshot.Container.dataset_service')
#     def test_get_dataset_latest_snapshot_not_found(self, mock_service_provider):
#         # Arrange
#         dataset_id = uuid4()
#         mock_service_provider.return_value = self.mock_dataset_service
#         self.mock_dataset_service.get_dataset_latest_snapshot.side_effect = NotFoundException("Not found")
#         
#         # Act
#         response = self.client.get(f"/datasets/{dataset_id}/snapshot")
#         
#         # Assert
#         self.assertEqual(response.status_code, 404)
#         self.assertEqual(response.json()["detail"], "Snapshot not found")
# 
#     @unittest.skip("Dependency injection mocking is complex - adapter functions tested separately")
#     @patch('app.controller.v1.dataset.dataset_snapshot.Container.dataset_service')
#     def test_get_dataset_latest_snapshot_invalid_data(self, mock_service_provider):
#         # Arrange
#         dataset_id = uuid4()
#         mock_service_provider.return_value = self.mock_dataset_service
#         self.mock_dataset_service.get_dataset_latest_snapshot.side_effect = IllegalStateException("Invalid data")
#         
#         # Act
#         response = self.client.get(f"/datasets/{dataset_id}/snapshot")
#         
#         # Assert
#         self.assertEqual(response.status_code, 500)
#         self.assertEqual(response.json()["detail"], "Invalid snapshot data")
# 
#     @unittest.skip("Dependency injection mocking is complex - adapter functions tested separately")
#     @patch('app.controller.v1.dataset.dataset_snapshot.Container.dataset_service')
#     def test_get_dataset_version_snapshot_success(self, mock_service_provider):
#         # Arrange
#         dataset_id = uuid4()
#         version_name = "v1.0"
#         mock_snapshot = {
#             "dataset_id": str(dataset_id),
#             "version_name": version_name,
#             "doi_identifier": "10.1234/test",
#             "doi_link": "https://doi.org/10.1234/test",
#             "doi_state": "FINDABLE",
#             "publication_date": "2024-01-01T00:00:00",
#             "files_summary": {
#                 "total_files": 2,
#                 "total_size_bytes": 768,
#                 "extensions_breakdown": [
#                     {"extension": ".txt", "count": 1, "total_size_bytes": 256},
#                     {"extension": ".csv", "count": 1, "total_size_bytes": 512}
#                 ]
#             },
#             "title": "Test Dataset",
#             "description": "A test dataset"
#         }
#         
#         # Mock dependency injection
#         mock_service_provider.return_value = self.mock_dataset_service
#         self.mock_dataset_service.get_dataset_version_snapshot.return_value = mock_snapshot
#         
#         # Act
#         response = self.client.get(f"/datasets/{dataset_id}/versions/{version_name}/snapshot")
#         
#         # Assert
#         self.assertEqual(response.status_code, 200)
#         
#         data = response.json()
#         self.assertEqual(data["dataset_id"], str(dataset_id))
#         self.assertEqual(data["version_name"], version_name)
#         self.assertEqual(data["doi_identifier"], "10.1234/test")
#         self.assertEqual(data["doi_link"], "https://doi.org/10.1234/test")
#         self.assertEqual(data["doi_state"], "FINDABLE")
#         self.assertEqual(data["publication_date"], "2024-01-01T00:00:00")
#         
#         # Check files_summary
#         self.assertIn("files_summary", data)
#         files_summary = data["files_summary"]
#         self.assertEqual(files_summary["total_files"], 2)
#         self.assertEqual(files_summary["total_size_bytes"], 768)
#         self.assertEqual(len(files_summary["extensions_breakdown"]), 2)
#         
#         # Check that typed fields are excluded from data
#         self.assertIn("title", data["data"])
#         self.assertIn("description", data["data"])
#         self.assertNotIn("dataset_id", data["data"])
#         self.assertNotIn("version_name", data["data"])
#         self.assertNotIn("files_summary", data["data"])
#         
#         # Version snapshot should not have versions list
#         self.assertNotIn("versions", data)
#         
#         self.mock_dataset_service.get_dataset_version_snapshot.assert_called_once_with(dataset_id, version_name)
# 
#     @unittest.skip("Dependency injection mocking is complex - adapter functions tested separately")
#     @patch('app.controller.v1.dataset.dataset_snapshot.Container.dataset_service')
#     def test_get_dataset_version_snapshot_not_found(self, mock_service_provider):
#         # Arrange
#         dataset_id = uuid4()
#         version_name = "v1.0"
#         mock_service_provider.return_value = self.mock_dataset_service
#         self.mock_dataset_service.get_dataset_version_snapshot.side_effect = NotFoundException("Not found")
#         
#         # Act
#         response = self.client.get(f"/datasets/{dataset_id}/versions/{version_name}/snapshot")
#         
#         # Assert
#         self.assertEqual(response.status_code, 404)
#         self.assertEqual(response.json()["detail"], "Snapshot not found")
# 
#     @unittest.skip("Dependency injection mocking is complex - adapter functions tested separately")
#     @patch('app.controller.v1.dataset.dataset_snapshot.Container.dataset_service')
#     def test_get_dataset_version_snapshot_invalid_data(self, mock_service_provider):
#         # Arrange
#         dataset_id = uuid4()
#         version_name = "v1.0"
#         mock_service_provider.return_value = self.mock_dataset_service
#         self.mock_dataset_service.get_dataset_version_snapshot.side_effect = IllegalStateException("Invalid data")
#         
#         # Act
#         response = self.client.get(f"/datasets/{dataset_id}/versions/{version_name}/snapshot")
#         
#         # Assert
#         self.assertEqual(response.status_code, 500)
#         self.assertEqual(response.json()["detail"], "Invalid snapshot data")
# 
#     @unittest.skip("Dependency injection mocking is complex - adapter functions tested separately")
#     def test_response_content_type_is_json(self):
#         # Test that responses have application/json content type
#         dataset_id = uuid4()
#         
#         with patch('app.controller.v1.dataset.dataset_snapshot.Container.dataset_service') as mock_service_provider:
#             mock_service_provider.return_value = self.mock_dataset_service
#             self.mock_dataset_service.get_dataset_latest_snapshot.side_effect = NotFoundException("Not found")
#             
#             response = self.client.get(f"/datasets/{dataset_id}/snapshot")
#             
#             self.assertEqual(response.headers["content-type"], "application/json")
# 
#     def test_adapt_snapshot_response(self):
#         # Test the adapter function for version snapshots
#         dataset_id = uuid4()
#         snapshot_data = {
#             "dataset_id": str(dataset_id),
#             "version_name": "v1.0",
#             "doi_identifier": "10.1234/test",
#             "doi_link": "https://doi.org/10.1234/test",
#             "doi_state": "FINDABLE",
#             "publication_date": "2024-01-01T00:00:00",
#             "files_summary": {
#                 "total_files": 2,
#                 "total_size_bytes": 768,
#                 "extensions_breakdown": [
#                     {"extension": ".txt", "count": 1, "total_size_bytes": 256},
#                     {"extension": ".csv", "count": 1, "total_size_bytes": 512}
#                 ]
#             },
#             "title": "Test Dataset",
#             "description": "A test dataset",
#             "some_other_field": "should be in data"
#         }
#         
#         result = _adapt_snapshot_response(snapshot_data)
#         
#         # Check typed fields
#         self.assertEqual(result.dataset_id, str(dataset_id))
#         self.assertEqual(result.version_name, "v1.0")
#         self.assertEqual(result.doi_identifier, "10.1234/test")
#         self.assertEqual(result.doi_link, "https://doi.org/10.1234/test")
#         self.assertEqual(result.doi_state, "FINDABLE")
#         self.assertEqual(result.publication_date, "2024-01-01T00:00:00")
#         self.assertEqual(result.files_summary.total_files, 2)
#         
#         # Check data field contains non-typed fields
#         self.assertIn("title", result.data)
#         self.assertIn("description", result.data)
#         self.assertIn("some_other_field", result.data)
#         
#         # Check typed fields are NOT in data
#         self.assertNotIn("dataset_id", result.data)
#         self.assertNotIn("version_name", result.data)
#         self.assertNotIn("doi_identifier", result.data)
#         self.assertNotIn("files_summary", result.data)
# 
#     def test_adapt_latest_snapshot_response(self):
#         # Test the adapter function for latest snapshots
#         dataset_id = uuid4()
#         snapshot_data = {
#             "dataset_id": str(dataset_id),
#             "version_name": "v2.0",
#             "doi_identifier": "10.1234/test",
#             "doi_link": "https://doi.org/10.1234/test",
#             "doi_state": "FINDABLE",
#             "publication_date": "2024-01-01T00:00:00",
#             "files_summary": {
#                 "total_files": 3,
#                 "total_size_bytes": 1536,
#                 "extensions_breakdown": [
#                     {"extension": ".csv", "count": 2, "total_size_bytes": 1024},
#                     {"extension": ".json", "count": 1, "total_size_bytes": 512}
#                 ]
#             },
#             "title": "Test Dataset",
#             "description": "A test dataset",
#             "versions": [
#                 {
#                     "id": str(uuid4()),
#                     "name": "v2.0",
#                     "doi_identifier": "10.1234/test",
#                     "doi_state": "FINDABLE",
#                     "created_at": "2024-01-01T00:00:00"
#                 }
#             ]
#         }
#         
#         result = _adapt_latest_snapshot_response(snapshot_data)
#         
#         # Check typed fields
#         self.assertEqual(result.dataset_id, str(dataset_id))
#         self.assertEqual(result.version_name, "v2.0")
#         self.assertEqual(result.doi_identifier, "10.1234/test")
#         self.assertEqual(result.doi_link, "https://doi.org/10.1234/test")
#         self.assertEqual(result.doi_state, "FINDABLE")
#         self.assertEqual(result.publication_date, "2024-01-01T00:00:00")
#         self.assertEqual(result.files_summary.total_files, 3)
#         
#         # Check versions
#         self.assertEqual(len(result.versions), 1)
#         self.assertEqual(result.versions[0].name, "v2.0")
#         
#         # Check data field contains non-typed fields
#         self.assertIn("title", result.data)
#         self.assertIn("description", result.data)
#         
#         # Check typed fields are NOT in data
#         self.assertNotIn("dataset_id", result.data)
#         self.assertNotIn("versions", result.data)
#         self.assertNotIn("files_summary", result.data)
# 
# 
# if __name__ == "__main__":
#     unittest.main()
