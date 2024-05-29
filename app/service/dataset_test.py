import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.gateway.zipper.resource import CreateZipResponse
from app.gateway.zipper.zipper import ZipperGateway
from app.repository.dataset import DatasetRepository
from app.repository.dataset_version import DatasetVersionRepository
from app.service.user import UserService
from app.model.dataset import (
    Dataset,
    DatasetQuery,
    DataFile,
    DesignState,
)
from app.model.db.dataset import (
    Dataset as DatasetDBModel,
    DatasetVersion as DatasetVersionDBModel,
    DataFile as DataFileDBModel,
)
from app.service.dataset import DatasetService
from app.model.user import User


class TestDatasetService(unittest.TestCase):
    def setUp(self):
        self.dataset_repository = Mock(spec=DatasetRepository)
        self.dataset_version_repository = Mock(spec=DatasetVersionRepository)
        self.user_service = Mock(spec=UserService)
        self.zipper_gateway = Mock(spec=ZipperGateway)
        self.dataset_service = DatasetService(
            repository=self.dataset_repository,
            version_repository=self.dataset_version_repository,
            user_service=self.user_service,
            zipper_gateway=self.zipper_gateway,
            default_file_bucket="bucket",
        )

    def mock_user(self, tenancies):
        user = Mock(spec=User)
        user.tenancies = tenancies
        return user

    def test_fetch_dataset_not_found(self):
        dataset_id = uuid4()
        user_id = uuid4()
        self.user_service.fetch_by_id.return_value = self.mock_user(["tenancy1"])
        self.dataset_repository.fetch.return_value = None

        result = self.dataset_service.fetch_dataset(
            dataset_id=dataset_id, user_id=user_id
        )
        self.assertIsNone(result)

    def test_fetch_dataset_success(self):
        dataset_id = uuid4()
        user_id = uuid4()
        tenancies = ["tenancy1"]
        dataset_db = Mock(spec=DatasetDBModel)
        mocked_version = Mock(spec=DatasetVersionDBModel)
        mocked_version.files = [Mock(spec=DataFileDBModel)]
        dataset_db.versions = [mocked_version]
        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_repository.fetch.return_value = dataset_db

        result = self.dataset_service.fetch_dataset(
            dataset_id=dataset_id, user_id=user_id, tenancies=tenancies
        )
        self.assertIsNotNone(result)
        self.dataset_repository.fetch.assert_called_once()

    def test_update_dataset_not_found(self):
        dataset_id = uuid4()
        user_id = uuid4()
        tenancies = ["tenancy1"]
        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_repository.fetch.return_value = None
        dataset = Mock(spec=Dataset)

        with self.assertRaises(NotFoundException):
            self.dataset_service.update_dataset(
                dataset_id=dataset_id,
                dataset=dataset,
                user_id=user_id,
                tenancies=tenancies,
            )

    def test_create_dataset_success(self):
        dataset = Mock(spec=Dataset)
        dataset.name = "test"
        dataset.data = {}
        user_id = uuid4()
        created_dataset_db = Mock(spec=DatasetDBModel)
        mocked_version = Mock(spec=DatasetVersionDBModel)
        mocked_version.files = [Mock(spec=DataFileDBModel)]
        created_dataset_db.versions = [mocked_version]
        self.dataset_repository.upsert.return_value = created_dataset_db

        result = self.dataset_service.create_dataset(dataset=dataset, user_id=user_id)
        self.assertIsNotNone(result)
        self.dataset_repository.upsert.assert_called_once()

    def test_disable_dataset_not_found(self):
        dataset_id = uuid4()
        self.user_service.fetch_by_id.return_value = self.mock_user(["tenancy1"])
        self.dataset_repository.fetch.return_value = None

        with self.assertRaises(NotFoundException):
            self.dataset_service.disable_dataset(dataset_id=dataset_id)

    def test_enable_dataset_not_found(self):
        dataset_id = uuid4()
        self.user_service.fetch_by_id.return_value = self.mock_user(["tenancy1"])
        self.dataset_repository.fetch.return_value = None

        with self.assertRaises(NotFoundException):
            self.dataset_service.enable_dataset(dataset_id=dataset_id)

    def test_enable_dataset_version_not_found(self):
        dataset_id = uuid4()
        user_id = uuid4()
        version_name = "1"
        tenancies = ["tenancy1"]
        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_repository.fetch.return_value = Mock(spec=DatasetDBModel)
        self.dataset_version_repository.fetch_version_by_name.return_value = None

        with self.assertRaises(NotFoundException):
            self.dataset_service.enable_dataset_version(
                dataset_id=dataset_id,
                user_id=user_id,
                version_name=version_name,
                tenancies=tenancies,
            )

    def test_disable_dataset_version_illegal_state(self):
        dataset_id = uuid4()
        user_id = uuid4()
        version_name = "1"
        tenancies = ["tenancy1"]
        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        dataset = Mock(spec=DatasetDBModel)
        dataset.versions = [Mock(spec=DatasetVersionDBModel)]
        self.dataset_repository.fetch.return_value = dataset

        with self.assertRaises(IllegalStateException):
            self.dataset_service.disable_dataset_version(
                dataset_id=dataset_id,
                user_id=user_id,
                version_name=version_name,
                tenancies=tenancies,
            )

    def test_fetch_available_filters(self):
        with patch(
            "builtins.open", unittest.mock.mock_open(read_data='{"filters": "data"}')
        ):
            filters = self.dataset_service.fetch_available_filters()
            self.assertEqual(filters, {"filters": "data"})

    def test_search_datasets(self):
        query = Mock(spec=DatasetQuery)
        user_id = uuid4()
        tenancies = ["tenancy1"]
        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_repository.search.return_value = []

        result = self.dataset_service.search_datasets(
            query=query, user_id=user_id, tenancies=tenancies
        )
        self.assertIsInstance(result, list)
        self.dataset_repository.search.assert_called_once()

    def test_create_data_file(self):
        file = Mock(spec=DataFile)
        file.name = "test"
        file.size_bytes = 100
        dataset_id = uuid4()
        user_id = uuid4()
        dataset = Mock(spec=DatasetDBModel)
        version = Mock(spec=DatasetVersionDBModel)
        self.dataset_service.fetch_dataset = Mock(return_value=dataset)
        self.dataset_version_repository.fetch_draft_version.return_value = version
        self.user_service.fetch_by_id.return_value = self.mock_user(["tenancy1"])

        self.dataset_service.create_data_file(
            file=file, dataset_id=dataset_id, user_id=user_id
        )
        self.dataset_version_repository.upsert.assert_called_once()

    def test_publish_dataset_version(self):
        dataset_id = uuid4()
        user_id = uuid4()
        version_name = "1"
        tenancies = ["tenancy1"]
        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        dataset = Mock(spec=DatasetDBModel)
        dataset.design_state = DesignState.DRAFT
        version = Mock(spec=DatasetVersionDBModel)
        version.files = [Mock(spec=DataFileDBModel)]
        self.dataset_repository.fetch.return_value = dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = version
        self.zipper_gateway.create_zip.return_value = CreateZipResponse(id=uuid4(), status="IN_PROGRESS")
        self.dataset_service.publish_dataset_version(
            dataset_id=dataset_id,
            user_id=user_id,
            version_name=version_name,
            tenancies=tenancies,
        )
        self.dataset_version_repository.upsert.assert_called_once()
        self.dataset_repository.upsert.assert_called_once()
        self.zipper_gateway.create_zip.assert_called_once()

    def test_publish_dataset_version_dataset_desing_state_bot_in_draft(self):
        dataset_id = uuid4()
        user_id = uuid4()
        version_name = "1"
        tenancies = ["tenancy1"]
        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        dataset = Mock(spec=DatasetDBModel)
        dataset.design_state = DesignState.PUBLISHED
        version = Mock(spec=DatasetVersionDBModel)
        version.files = [Mock(spec=DataFileDBModel)]
        self.dataset_repository.fetch.return_value = dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = version
        self.zipper_gateway.create_zip.return_value = CreateZipResponse(id=uuid4(), status="IN_PROGRESS")
        self.dataset_service.publish_dataset_version(
            dataset_id=dataset_id,
            user_id=user_id,
            version_name=version_name,
            tenancies=tenancies,
        )
        self.dataset_version_repository.upsert.assert_called_once()
        self.dataset_repository.upsert.assert_not_called()
        self.zipper_gateway.create_zip.assert_called_once()

    def test_publish_dataset_version_not_found(self):
        dataset_id = uuid4()
        user_id = uuid4()
        version_name = "1"
        tenancies = ["tenancy1"]
        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_repository.fetch.return_value = None

        with self.assertRaises(NotFoundException):
            self.dataset_service.publish_dataset_version(
                dataset_id=dataset_id,
                user_id=user_id,
                version_name=version_name,
                tenancies=tenancies,
            )
    
    def test_publish_dataset_version_illegal_state(self):
        dataset_id = uuid4()
        user_id = uuid4()
        version_name = "1"
        tenancies = ["tenancy1"]
        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        dataset = Mock(spec=DatasetDBModel)
        dataset.design_state = DesignState.DRAFT
        version = Mock(spec=DatasetVersionDBModel)
        version.files = [Mock(spec=DataFileDBModel)]
        self.dataset_repository.fetch.return_value = dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = version
        self.zipper_gateway.create_zip.return_value = CreateZipResponse(id=uuid4(), status="ERROR")
        
        with self.assertRaises(IllegalStateException):
            self.dataset_service.publish_dataset_version(
                dataset_id=dataset_id,
                user_id=user_id,
                version_name=version_name,
                tenancies=tenancies,
            )
    
    @patch('app.service.dataset.logging')
    def test_update_zip_status_success(self, logging_mock):
        dataset_id = uuid4()
        version_name = '1'
        zip_id = uuid4()
        zip_status = 'SUCCESS'

        version_mock = Mock(spec=DatasetVersionDBModel)
        self.dataset_version_repository.fetch_version_by_name.return_value = version_mock

        self.dataset_service.update_zip_status(dataset_id, version_name, zip_id, zip_status)

        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(dataset_id=dataset_id, version_name=version_name)
        self.assertEqual(version_mock.zip_status, zip_status)
        self.dataset_version_repository.upsert.assert_called_once_with(version_mock)
        logging_mock.info.assert_called_once_with(f"zip {zip_id} status updated: {zip_status} for dataset {dataset_id} version {version_name}")

    @patch('app.service.dataset.logging')
    def test_update_zip_status_version_not_found(self, logging_mock):
        dataset_id = uuid4()
        version_name = '1'
        zip_id = uuid4()
        zip_status = 'SUCESS'

        self.dataset_version_repository.fetch_version_by_name.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.update_zip_status(dataset_id, version_name, zip_id, zip_status)

        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(dataset_id=dataset_id, version_name=version_name)
        self.assertEqual(str(context.exception), f"not_found: {version_name} for dataset {dataset_id}")
        self.dataset_version_repository.upsert.assert_not_called()
        logging_mock.info.assert_not_called()
    
if __name__ == "__main__":
    unittest.main()
