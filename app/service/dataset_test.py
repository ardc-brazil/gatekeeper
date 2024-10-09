from dataclasses import dataclass
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.unauthorized import UnauthorizedException
from app.gateway.object_storage.object_storage import ObjectStorageGateway
from app.model.doi import Mode
from app.repository.datafile import DataFileRepository
from app.repository.dataset import DatasetRepository
from app.repository.dataset_version import DatasetVersionRepository
from app.service.doi import DOIService
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
from app.model.db.doi import (
    DOI as DOIDBModel,
)
from app.service.dataset import DatasetService
from app.model.user import User


class TestDatasetService(unittest.TestCase):
    def setUp(self):
        self.dataset_repository = Mock(spec=DatasetRepository)
        self.dataset_version_repository = Mock(spec=DatasetVersionRepository)
        self.data_file_repository = Mock(spec=DataFileRepository)
        self.user_service = Mock(spec=UserService)
        self.doi_service = Mock(spec=DOIService)
        self.minio_gateway = Mock(spec=ObjectStorageGateway)
        self.dataset_service = DatasetService(
            repository=self.dataset_repository,
            version_repository=self.dataset_version_repository,
            data_file_repository=self.data_file_repository,
            user_service=self.user_service,
            doi_service=self.doi_service,
            minio_gateway=self.minio_gateway,
            dataset_bucket="dataset_bucket",
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
        mocked_version.files_in = [Mock(spec=DataFileDBModel)]
        mocked_version.doi = DOIDBModel(
            mode="MANUAL",
            state="DRAFT",
            doi={
                'data':{
                    'attributes':{
                        'titles':[
                            { 'title': "aaaa"}
                        ]
                    }
                }
            },
        )
        
        dataset_db.versions = [mocked_version]
        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_repository.fetch.return_value = dataset_db

        result = self.dataset_service.fetch_dataset(
            dataset_id=dataset_id, user_id=user_id, tenancies=tenancies
        )
        self.assertIsNotNone(result)
        self.dataset_repository.fetch.assert_called_once()

    def test_fetch_dataset_by_user_not_found(self):
        dataset_id = uuid4()
        user_id = uuid4()
        tenancies = ["tenancy1"]
        dataset_db = Mock(spec=DatasetDBModel)
        mocked_version = Mock(spec=DatasetVersionDBModel)
        mocked_version.files = [Mock(spec=DataFileDBModel)]
        mocked_version.files_in = [Mock(spec=DataFileDBModel)]
        dataset_db.versions = [mocked_version]
        self.user_service.fetch_by_id.side_effect = NotFoundException("user not found")

        # when + then
        with self.assertRaises(UnauthorizedException):
            self.dataset_service.fetch_dataset(
                dataset_id=dataset_id, user_id=user_id, tenancies=tenancies
            )

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
                dataset_request=dataset,
                user_id=user_id,
                tenancies=tenancies,
            )

    def test_update_dataset(self):
        # given
        dataset_id = uuid4()
        user_id = uuid4()
        tenancies = ["tenancy1"]
        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        dataset_db = Mock(spec=DatasetDBModel)
        dataset_db.name = "dataset.name"
        dataset_db.data = {"category": "AEROSOLS"}
        dataset_db.tenancy = "dataset.tenancy"
        dataset_db.owner_id = "user_id"

        mocked_version = Mock(spec=DatasetVersionDBModel)
        mocked_version.name = "1"
        mocked_version.files = [Mock(spec=DataFileDBModel)]
        mocked_version.files_in = [Mock(spec=DataFileDBModel)]
        mocked_version.is_enabled = True
        mocked_version.design_state = DesignState.DRAFT

        dataset_db.versions = [mocked_version]

        dataset = Mock(spec=Dataset)
        dataset.name = "new_name"
        dataset.data = {"category": "AEROSOLS"}
        dataset.tenancy = "new_name"
        dataset.owner_id = "new_name"

        self.dataset_repository.fetch.return_value = dataset_db

        # when
        self.dataset_service.update_dataset(
            dataset_id=dataset_id,
            dataset_request=dataset,
            user_id=user_id,
            tenancies=tenancies,
        )

        # then
        self.assertEqual(dataset_db.versions, [mocked_version])
        self.dataset_repository.upsert.assert_called_once()

    def test_create_dataset_success(self):
        dataset = Mock(spec=Dataset)
        dataset.name = "test"
        dataset.data = {}
        user_id = uuid4()
        created_dataset_db = Mock(spec=DatasetDBModel)
        mocked_version = Mock(spec=DatasetVersionDBModel)
        mocked_version.files = [Mock(spec=DataFileDBModel)]
        mocked_version.files_in = [Mock(spec=DataFileDBModel)]
        mocked_version.doi = DOIDBModel(
            mode="MANUAL",
            state="DRAFT",
            doi={
                'data':{
                    'attributes':{
                        'titles':[
                            { 'title': "aaaa"}
                        ]
                    }
                }
            },
        )
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
        self.dataset_repository.fetch.return_value = dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = version

        self.dataset_service.publish_dataset_version(
            dataset_id=dataset_id,
            user_id=user_id,
            version_name=version_name,
            tenancies=tenancies,
        )
        self.dataset_version_repository.upsert.assert_called_once()
        self.dataset_repository.upsert.assert_called_once()

    def test__should_create_new_version(self):
        @dataclass
        class TestCase:
            name: str
            given_version: DatasetVersionDBModel
            expected: bool

        testcases = [
            TestCase(
                name="version_published_enabled",
                given_version=DatasetVersionDBModel(
                    name="1", design_state=DesignState.PUBLISHED, is_enabled=True
                ),
                expected=False,
            ),
            TestCase(
                name="version_published_disabled",
                given_version=DatasetVersionDBModel(
                    name="1", design_state=DesignState.PUBLISHED, is_enabled=False
                ),
                expected=True,
            ),
            TestCase(
                name="version_draft_enabled",
                given_version=DatasetVersionDBModel(
                    name="1", design_state=DesignState.DRAFT, is_enabled=True
                ),
                expected=False,
            ),
            TestCase(
                name="version_draft_disabled",
                given_version=DatasetVersionDBModel(
                    name="1", design_state=DesignState.DRAFT, is_enabled=False
                ),
                expected=True,
            ),
        ]

        # Add a new line to improve the test output
        print()

        for case in testcases:
            # given
            dataset_db = DatasetDBModel(
                name="dataset.name",
                data={"category": "AEROSOLS"},
                tenancy="dataset.tenancy",
                owner_id="user_id",
                versions=[case.given_version],
            )

            dataset_request = Dataset(
                name="name",
                data={"category": "AEROSOLS"},
            )

            # when
            actual = self.dataset_service._should_create_new_version(
                dataset_db, dataset_request
            )

            # then
            self.assertEqual(
                actual,
                case.expected,
                "failed test {} expected {}, actual {}".format(
                    case.name, case.expected, actual
                ),
            )

    def test__create_new_version(self):
        @dataclass
        class TestCase:
            name: str
            given_versions: int
            expected_version_name: str

        testcases = [
            TestCase(name="first_version", expected_version_name="1", given_versions=0),
            TestCase(name="fifth_version", expected_version_name="5", given_versions=5),
        ]

        for case in testcases:
            # given
            user_id = uuid4()

            dataset_db = DatasetDBModel()
            dataset_db.name = "dataset.name"
            dataset_db.data = {"dataFiles": ["a/c/b"]}
            dataset_db.tenancy = "dataset.tenancy"
            dataset_db.owner_id = "user_id"
            dataset_db.versions = []

            last_version_number = case.given_versions
            for i in range(last_version_number):
                version = DatasetVersionDBModel()
                version.name = str(i)
                dataset_db.versions.append(version)

            # when
            actual_version_created = self.dataset_service._create_new_version(
                dataset_db, user_id
            )

            # then
            self.assertEqual(
                actual_version_created.name,
                case.expected_version_name,
                "failed test {} expected {}, actual {}".format(
                    case.name, case.expected_version_name, actual_version_created
                ),
            )
            self.assertEqual(
                actual_version_created.design_state,
                DesignState.DRAFT,
                "failed test {} expected {}, actual {}".format(
                    case.name, case.expected_version_name, actual_version_created
                ),
            )

    def test__determine_tenancies(self):
        # given
        given_user_id = "7DC7479E-9DCD-4519-BEC8-6CBA708A7B10"
        given_tenancies = ["a", "b"]
        expected_tenancies = ["a", "b"]

        self.user_service.fetch_by_id.return_value = self.mock_user(given_tenancies)

        # when
        actual = self.dataset_service._determine_tenancies(
            user_id=given_user_id, tenancies=given_tenancies
        )

        # then
        self.assertEqual(actual, expected_tenancies)

    def test__determine_tenancies_unauthorized_when_user_not_found(self):
        # given
        given_user_id = "7DC7479E-9DCD-4519-BEC8-6CBA708A7B10"
        given_tenancies = ["a", "b"]
        expected_raise_fetch_user = UnauthorizedException(
            f"unauthorized_tenancy '{given_tenancies}' for user '{given_user_id}'"
        )
        self.user_service.fetch_by_id.side_effect = NotFoundException("user not found")

        # when
        with self.assertRaises(type(expected_raise_fetch_user)) as cm:
            self.dataset_service._determine_tenancies(
                user_id=given_user_id, tenancies=given_tenancies
            )

        # then
        self.assertEqual(str(cm.exception), str(expected_raise_fetch_user))

    def test__determine_tenancies_unauthorized_list_of_tenancies_are_invalid(self):
        # given
        given_user_id = "7DC7479E-9DCD-4519-BEC8-6CBA708A7B10"
        given_request_tenancies = ["a", "b", "c"]
        given_tenancies = ["a", "b"]
        expected_raise_fetch_user = UnauthorizedException(
            "unauthorized_tenancy: ['a', 'b', 'c']"
        )
        self.user_service.fetch_by_id.return_value = self.mock_user(given_tenancies)

        # when
        with self.assertRaises(type(expected_raise_fetch_user)) as cm:
            self.dataset_service._determine_tenancies(
                user_id=given_user_id, tenancies=given_request_tenancies
            )

        # then
        self.assertEqual(str(cm.exception), str(expected_raise_fetch_user))


if __name__ == "__main__":
    unittest.main()
