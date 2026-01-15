from dataclasses import dataclass
import datetime
import json
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
from app.exception.bad_request import BadRequestException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.unauthorized import UnauthorizedException
from app.gateway.object_storage.object_storage import ObjectStorageGateway
from app.model.tenancy import Tenancy
from app.repository.datafile import DataFileRepository
from app.repository.dataset import DatasetRepository
from app.repository.dataset_version import DatasetVersionRepository
from app.service.doi import DOIService
from app.service.tenancy import TenancyService
from app.service.user import UserService
from app.model.dataset import (
    Dataset,
    DatasetQuery,
    DataFile,
    DatasetVersion,
    DesignState,
    VisibilityStatus,
)
from app.model.db.dataset import (
    Dataset as DatasetDBModel,
    DatasetVersion as DatasetVersionDBModel,
    DataFile as DataFileDBModel,
)
from app.model.db.doi import DOI as DOIDBModel
from app.service.dataset import DatasetService
from app.model.user import User
from app.model.doi import (
    DOI,
    State as DOIState,
    Title as DOITitle,
    Creator as DOICreator,
    Publisher as DOIPublisher,
    Mode as DOIMode,
)
from app.adapter import doi as DOIAdapter


class TestDatasetService(unittest.TestCase):
    def setUp(self):
        self.dataset_repository = Mock(spec=DatasetRepository)
        self.dataset_version_repository = Mock(spec=DatasetVersionRepository)
        self.data_file_repository = Mock(spec=DataFileRepository)
        self.user_service = Mock(spec=UserService)
        self.doi_service = Mock(spec=DOIService)
        self.minio_gateway = Mock(spec=ObjectStorageGateway)
        self.tenancy_service = Mock(spec=TenancyService)
        self.dataset_service = DatasetService(
            repository=self.dataset_repository,
            version_repository=self.dataset_version_repository,
            data_file_repository=self.data_file_repository,
            user_service=self.user_service,
            doi_service=self.doi_service,
            minio_gateway=self.minio_gateway,
            tenancy_service=self.tenancy_service,
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
        file = Mock(spec=DataFileDBModel)
        file.size_bytes = 0
        mocked_version = Mock(spec=DatasetVersionDBModel)
        mocked_version.files = [file]
        mocked_version.files_in = [file]
        mocked_version.doi = DOIDBModel(
            mode="MANUAL",
            state="DRAFT",
            doi={"data": {"attributes": {"titles": [{"title": "aaaa"}]}}},
        )
        mocked_version.visibility = VisibilityStatus.PUBLIC

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
        mocked_version.doi = None
        mocked_version.visibility = None

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
        file = Mock(spec=DataFileDBModel)
        file.size_bytes = 0
        created_dataset_db = Mock(spec=DatasetDBModel)
        mocked_version = Mock(spec=DatasetVersionDBModel)
        mocked_version.files = [file]
        mocked_version.files_in = [file]
        mocked_version.doi = DOIDBModel(
            mode="MANUAL",
            state="DRAFT",
            doi={"data": {"attributes": {"titles": [{"title": "aaaa"}]}}},
        )
        created_dataset_db.visibility = None
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
                visibility=None,
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
            dataset_db.visibility = None

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

    def mock_tenancy(self, name, is_enabled):
        # Mocking a tenancy object with the given name and enabled status
        tenancy = Mock(Tenancy)
        tenancy.name = name
        tenancy.is_enabled = is_enabled
        return tenancy

    def test__determine_tenancies_disabled_tenancy(self):
        # given
        given_user_id = "7DC7479E-9DCD-4519-BEC8-6CBA708A7B10"
        given_tenancies = ["a", "b"]
        expected_tenancies = ["a"]

        self.user_service.fetch_by_id.return_value = self.mock_user(given_tenancies)
        self.tenancy_service.fetch.side_effect = lambda name: (
            self.mock_tenancy(name, is_enabled=True)
            if name == "a"
            else self.mock_tenancy(name, is_enabled=False)
        )

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

    def test_update_dataset_update_doi_metadata_success(self):
        dataset_id = uuid4()
        user_id = uuid4()
        now = datetime.datetime.now()
        dataset_request = Dataset(
            id=dataset_id,
            name="Updated Dataset",
            data={
                "key": "value",
                "authors": [{"name": "Author One"}],
                "institution": "Test Institution",
            },
            tenancy=["tenant1"],
            is_enabled=True,
            created_at=datetime.datetime.now(),
            updated_at=datetime.datetime.now(),
            design_state=DesignState.PUBLISHED,
            visibility=None,
            versions=[],
            current_version=None,
        )

        # Existing dataset with a current version that has a DOI
        existing_version = DatasetVersionDBModel(
            id=uuid4(),
            name="1",
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[],
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=DOIDBModel(
                identifier="10.1234/example-doi",
                mode="AUTO",
                prefix="10.1234",
                suffix="example-doi",
                url="https://example.com/doi",
                state="DRAFT",
                created_at=now,
                updated_at=now,
                created_by=user_id,
                version_id=uuid4(),
                doi={
                    "title": "Original Dataset",
                    "creators": [{"name": "Author One"}],
                    "publisher": "Test Institution",
                    "publicationYear": now.year,
                },
            ),
        )

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[existing_version],
        )
        self.dataset_repository.fetch.return_value = existing_dataset

        # Mock the update_metadata method to do nothing (assume success)
        self.doi_service.update_metadata.return_value = None

        self.user_service.fetch_by_id.return_value = self.mock_user(["tenant1"])

        self.dataset_service.update_dataset(
            dataset_id=dataset_id,
            dataset_request=dataset_request,
            user_id=user_id,
            tenancies=["tenant1"],
        )

        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id,
            tenancies=["tenant1"],
        )
        # Verify that the dataset was updated
        self.assertEqual(existing_dataset.name, "Updated Dataset")
        self.assertEqual(
            existing_dataset.data,
            {
                "key": "value",
                "authors": [{"name": "Author One"}],
                "institution": "Test Institution",
            },
        )
        self.assertEqual(existing_dataset.tenancy, ["tenant1"])
        self.assertEqual(existing_dataset.owner_id, user_id)

        # Verify that DOI was updated
        expected_doi = DOI(
            identifier="10.1234/example-doi",
            mode=DOIMode.AUTO,
            title=DOITitle(title="Updated Dataset"),
            creators=[DOICreator(name="Author One")],
            publisher=DOIPublisher(publisher="Test Institution"),
            publication_year=now.year,
            resource_type={},
            url=f"https://datamap.pcs.usp.br/doi/datasets/{existing_dataset.id}/versions/{existing_version.name}",
            state=DOIState.DRAFT,
            dataset_version_name=existing_version.name,
            dataset_id=existing_dataset.id,
            dataset_version_id=existing_version.id,
            created_by=user_id,
            provider_response={
                "title": "Original Dataset",
                "creators": [{"name": "Author One"}],
                "publisher": "Test Institution",
                "publicationYear": now.year,
            },
        )
        self.doi_service.update_metadata.assert_called_once_with(doi=expected_doi)
        self.dataset_repository.upsert.assert_called_once_with(dataset=existing_dataset)

    def test_updated_dataset_update_doi_metadata_failure(self):
        dataset_id = uuid4()
        user_id = uuid4()
        now = datetime.datetime.now()

        dataset_request = Dataset(
            id=dataset_id,
            name="Updated Dataset",
            data={
                "key": "value",
                "authors": [{"name": "Author One"}],
                "institution": "Test Institution",
            },
            tenancy=["tenant1"],
            is_enabled=True,
            created_at=datetime.datetime.now(),
            updated_at=datetime.datetime.now(),
            design_state=DesignState.PUBLISHED,
            visibility=None,
            versions=[],
            current_version=None,
        )

        # Existing dataset with a current version that has a DOI
        existing_version = DatasetVersionDBModel(
            id=uuid4(),
            name="1",
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[],
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=DOIDBModel(
                identifier="10.1234/example-doi",
                mode="AUTO",
                prefix="10.1234",
                suffix="example-doi",
                url="https://example.com/doi",
                state="DRAFT",
                created_at=now,
                updated_at=now,
                created_by=user_id,
                version_id=uuid4(),
                doi={
                    "title": "Original Dataset",
                    "creators": [{"name": "Author One"}],
                    "publisher": "Test Institution",
                    "publicationYear": now.year,
                },
            ),
        )

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[existing_version],
        )
        self.dataset_repository.fetch.return_value = existing_dataset

        # Mock the update_metadata method to simulate failure
        self.doi_service.update_metadata.side_effect = Exception("Update failed")

        self.user_service.fetch_by_id.return_value = self.mock_user(["tenant1"])

        with self.assertRaises(Exception):
            self.dataset_service.update_dataset(
                dataset_id=dataset_id,
                dataset_request=dataset_request,
                user_id=user_id,
                tenancies=["tenant1"],
            )

        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id,
            tenancies=["tenant1"],
        )

        expected_doi = DOI(
            identifier="10.1234/example-doi",
            mode=DOIMode.AUTO,
            title=DOITitle(title="Updated Dataset"),
            creators=[DOICreator(name="Author One")],
            publisher=DOIPublisher(publisher="Test Institution"),
            publication_year=now.year,
            resource_type={},
            url=f"https://datamap.pcs.usp.br/doi/datasets/{existing_dataset.id}/versions/{existing_version.name}",
            state=DOIState.DRAFT,
            dataset_version_name=existing_version.name,
            dataset_id=existing_dataset.id,
            dataset_version_id=existing_version.id,
            created_by=user_id,
            provider_response={
                "title": "Original Dataset",
                "creators": [{"name": "Author One"}],
                "publisher": "Test Institution",
                "publicationYear": now.year,
            },
        )
        self.doi_service.update_metadata.assert_called_once_with(doi=expected_doi)
        self.dataset_repository.upsert.assert_not_called()

    def test_get_file_download_url_success(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]
        now = datetime.datetime.now()
        file_id = uuid4()

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        existing_file = DataFileDBModel(
            id=file_id, 
            name="file_name", 
            size_bytes=100, 
            created_at=now, 
            updated_at=now,
            storage_path="bucket/file_name",
            storage_file_name="file_name",
        )

        existing_version = DatasetVersionDBModel(
            id=uuid4(),
            name="1",
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[existing_file],
            files_in=[existing_file],
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=None,
        )

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[existing_version],
        )
        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = (
            existing_version
        )
        self.data_file_repository.fetch_by_id.return_value = existing_file

        self.minio_gateway.get_pre_signed_url.return_value = (
            "https://example.com/download/file_name"
        )

        result = self.dataset_service.get_file_download_url(
            dataset_id, version_name, file_id, user_id, tenancies
        )

        self.assertEqual(result, "https://example.com/download/file_name")
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id,
            is_enabled=True,
            tenancies=tenancies,
            latest_version=False,
            version_design_state=None,
            version_is_enabled=True,
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(
            dataset_id=dataset_id, version_name=version_name
        )

    def test_get_file_download_url_dataset_not_found(self):
        dataset_id = uuid4()
        version_name = "1"
        file_id = uuid4()
        user_id = uuid4()
        tenancies = ["tenant1"]
        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_repository.fetch.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.get_file_download_url(
                dataset_id, version_name, file_id, user_id, tenancies
            )

        self.assertEqual(str(context.exception), f"not_found: {dataset_id}")

    def test_get_file_download_url_version_not_found(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]
        now = datetime.datetime.now()

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[],
        )
        self.dataset_repository.fetch.return_value = existing_dataset
        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_version_repository.fetch_version_by_name.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.get_file_download_url(
                dataset_id, version_name, uuid4(), user_id, tenancies
            )

        self.assertEqual(
            str(context.exception),
            f"not_found: {version_name} for dataset {dataset_id}",
        )

    def test_get_file_download_url_file_not_found(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]
        now = datetime.datetime.now()
        file_id = uuid4()

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        existing_version = DatasetVersionDBModel(
            id=uuid4(),
            name="1",
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[],  # No files in the version
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=None,
        )

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[existing_version],
        )
        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = (
            existing_version
        )

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.get_file_download_url(
                dataset_id, version_name, file_id, user_id, tenancies
            )

        self.assertEqual(str(context.exception), f"not_found: {file_id}")

    def test_create_doi_success(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]
        now = datetime.datetime.now()

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        # Existing dataset with a current version that has a DOI
        existing_version = DatasetVersionDBModel(
            id=uuid4(),
            name="1",
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[],
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=None,
        )

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[existing_version],
        )
        self.dataset_repository.fetch.return_value = existing_dataset

        expected_doi = DOI(
            identifier="10.1234/example-doi",
            mode=DOIMode.AUTO,
            title=DOITitle(title="Updated Dataset"),
            creators=[DOICreator(name="Author One")],
            publisher=DOIPublisher(publisher="Test Institution"),
            publication_year=now.year,
            resource_type={},
            url=f"https://datamap.pcs.usp.br/doi/datasets/{existing_dataset.id}/versions/{existing_version.name}",
            state=DOIState.DRAFT,
            dataset_version_name=existing_version.name,
            dataset_id=existing_dataset.id,
            dataset_version_id=existing_version.id,
            created_by=user_id,
            provider_response={
                "title": "Original Dataset",
                "creators": [{"name": "Author One"}],
                "publisher": "Test Institution",
                "publicationYear": now.year,
            },
        )

        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = (
            existing_version
        )
        self.doi_service.create.return_value = expected_doi

        result = self.dataset_service.create_doi(
            dataset_id, version_name, expected_doi, user_id, tenancies
        )

        self.assertEqual(result, expected_doi)
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(
            dataset_id=dataset_id, version_name=version_name
        )
        self.doi_service.create.assert_called_once_with(doi=expected_doi)

    def test_create_doi_dataset_not_found(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        self.dataset_repository.fetch.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.create_doi(
                dataset_id, version_name, DOI(mode=DOIMode.AUTO), user_id, tenancies
            )

        self.assertEqual(str(context.exception), f"not_found: {dataset_id}")
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )

    def test_create_doi_version_not_found(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]
        now = datetime.datetime.now()

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[],
        )
        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.create_doi(
                dataset_id, version_name, DOI(mode=DOIMode.AUTO), user_id, tenancies
            )

        self.assertEqual(
            str(context.exception),
            f"not_found: {version_name} for dataset {dataset_id}",
        )
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(
            dataset_id=dataset_id, version_name=version_name
        )

    def test_create_doi_already_exists(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]
        now = datetime.datetime.now()

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        existing_version = DatasetVersionDBModel(
            id=uuid4(),
            name="1",
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[],
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=DOIDBModel(
                identifier="10.1234/example-doi",
                mode="DRAFT",
                created_at=now,
                updated_at=now,
            ),  # DOI already exists
        )

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[existing_version],
        )

        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = (
            existing_version
        )

        with self.assertRaises(BadRequestException) as context:
            self.dataset_service.create_doi(
                dataset_id, version_name, DOI(mode=DOIMode.AUTO), user_id, tenancies
            )

        self.assertEqual(str(context.exception.errors[0].code), "already_exists")
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(
            dataset_id=dataset_id, version_name=version_name
        )

    def test_create_doi_internal_service_failure(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]
        now = datetime.datetime.now()

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        existing_version = DatasetVersionDBModel(
            id=uuid4(),
            name="1",
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[],
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=None,
        )

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[existing_version],
        )
        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = (
            existing_version
        )

        # Simulate a failure in the DOI service
        self.doi_service.create.side_effect = Exception("DOI service failure")

        with self.assertRaises(Exception) as context:
            self.dataset_service.create_doi(
                dataset_id, version_name, DOI(mode=DOIMode.AUTO), user_id, tenancies
            )

        self.assertEqual(str(context.exception), "DOI service failure")
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(
            dataset_id=dataset_id, version_name=version_name
        )

    def test_change_doi_state_success(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        new_state = DOIState.FINDABLE
        tenancies = ["tenant1"]

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        now = datetime.datetime.now()

        existing_version = DatasetVersionDBModel(
            id=uuid4(),
            name=version_name,
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[],
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=DOIDBModel(identifier="10.1234/example-doi"),
        )

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[existing_version],
        )

        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = (
            existing_version
        )

        self.dataset_service.change_doi_state(
            dataset_id, version_name, new_state, user_id, tenancies
        )

        # Verify dataset repository was called twice (DOI operation + publication)
        self.assertEqual(self.dataset_repository.fetch.call_count, 2)
        self.dataset_repository.fetch.assert_called_with(
            dataset_id=dataset_id, tenancies=tenancies
        )
        # Version repository is also called twice (DOI operation + publication)
        self.assertEqual(
            self.dataset_version_repository.fetch_version_by_name.call_count, 2
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_with(
            dataset_id=dataset_id, version_name=version_name
        )
        self.doi_service.change_state.assert_called_once_with(
            identifier=existing_version.doi.identifier, new_state=new_state
        )

    def test_change_doi_state_dataset_not_found(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        new_state = DOIState.FINDABLE
        tenancies = ["tenant1"]

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        self.dataset_repository.fetch.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.change_doi_state(
                dataset_id, version_name, new_state, user_id, tenancies
            )

        self.assertEqual(str(context.exception), f"not_found: {dataset_id}")
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )

    def test_change_doi_state_version_not_found(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        new_state = DOIState.FINDABLE
        tenancies = ["tenant1"]
        now = datetime.datetime.now()

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[],
        )

        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.change_doi_state(
                dataset_id, version_name, new_state, user_id, tenancies
            )

        self.assertEqual(
            str(context.exception),
            f"not_found: {version_name} for dataset {dataset_id}",
        )
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(
            dataset_id=dataset_id, version_name=version_name
        )

    def test_change_doi_state_doi_not_found(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        new_state = DOIState.FINDABLE
        tenancies = ["tenant1"]
        now = datetime.datetime.now()

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        existing_version = DatasetVersionDBModel(
            id=uuid4(),
            name=version_name,
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[],
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=None,  # DOI is not present
        )

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[existing_version],
        )

        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = (
            existing_version
        )

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.change_doi_state(
                dataset_id, version_name, new_state, user_id, tenancies
            )

        self.assertEqual(
            str(context.exception), f"not_found: DOI for version {version_name}"
        )
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(
            dataset_id=dataset_id, version_name=version_name
        )

    def test_get_doi_success(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        now = datetime.datetime.now()

        existing_doi = DOIDBModel(
            identifier="10.1234/example-doi",
            mode=DOIMode.AUTO.name,
            state=DOIState.DRAFT.name,
            created_by=user_id,
            prefix="10.1234",
            suffix="example-doi",
            url="https://example.com/doi",
            created_at=now,
            updated_at=now,
            version_id=uuid4(),
        )

        existing_version = DatasetVersionDBModel(
            id=uuid4(),
            name=version_name,
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[],
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=existing_doi,
        )

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[existing_version],
        )

        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = (
            existing_version
        )

        result = self.dataset_service.get_doi(
            dataset_id, version_name, user_id, tenancies
        )

        self.assertEqual(result, DOIAdapter.database_to_model(doi=existing_doi))
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(
            dataset_id=dataset_id, version_name=version_name
        )

    def test_get_doi_dataset_not_found(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        self.dataset_repository.fetch.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.get_doi(dataset_id, version_name, user_id, tenancies)

        self.assertEqual(str(context.exception), f"not_found: {dataset_id}")
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )

    def test_get_doi_version_not_found(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]
        now = datetime.datetime.now()

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[],
        )

        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.get_doi(dataset_id, version_name, user_id, tenancies)

        self.assertEqual(
            str(context.exception),
            f"not_found: {version_name} for dataset {dataset_id}",
        )
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(
            dataset_id=dataset_id, version_name=version_name
        )

    def test_get_doi_doi_not_found(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]
        now = datetime.datetime.now()

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        existing_version = DatasetVersionDBModel(
            id=uuid4(),
            name=version_name,
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[],
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=None,  # DOI is not present
        )

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[existing_version],
        )

        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = (
            existing_version
        )

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.get_doi(dataset_id, version_name, user_id, tenancies)

        self.assertEqual(
            str(context.exception), f"not_found: DOI for version {version_name}"
        )
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(
            dataset_id=dataset_id, version_name=version_name
        )

    def test_delete_doi_success(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        now = datetime.datetime.now()

        existing_doi = DOIDBModel(
            identifier="10.1234/example-doi",
            mode=DOIMode.AUTO,
            state=DOIState.DRAFT,
            created_by=user_id,
        )

        existing_version = DatasetVersionDBModel(
            id=uuid4(),
            name=version_name,
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[],
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=existing_doi,
        )

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[existing_version],
        )

        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = (
            existing_version
        )

        self.dataset_service.delete_doi(dataset_id, version_name, user_id, tenancies)

        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(
            dataset_id=dataset_id, version_name=version_name
        )
        self.doi_service.delete.assert_called_once_with(
            identifier=existing_doi.identifier
        )

    def test_delete_doi_dataset_not_found(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        self.dataset_repository.fetch.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.delete_doi(
                dataset_id, version_name, user_id, tenancies
            )

        self.assertEqual(str(context.exception), f"not_found: {dataset_id}")
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )

    def test_delete_doi_version_not_found(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]
        now = datetime.datetime.now()

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[],
        )

        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.delete_doi(
                dataset_id, version_name, user_id, tenancies
            )

        self.assertEqual(
            str(context.exception),
            f"not_found: {version_name} for dataset {dataset_id}",
        )
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(
            dataset_id=dataset_id, version_name=version_name
        )

    def test_delete_doi_doi_not_found(self):
        dataset_id = uuid4()
        version_name = "1"
        user_id = uuid4()
        tenancies = ["tenant1"]
        now = datetime.datetime.now()

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        existing_version = DatasetVersionDBModel(
            id=uuid4(),
            name=version_name,
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[],
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=None,  # DOI is not present
        )

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[existing_version],
        )

        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = (
            existing_version
        )

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.delete_doi(
                dataset_id, version_name, user_id, tenancies
            )

        self.assertEqual(
            str(context.exception), f"not_found: DOI for version {version_name}"
        )
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id, tenancies=tenancies
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(
            dataset_id=dataset_id, version_name=version_name
        )

    def test_fetch_dataset_version_success(self):
        dataset_id = uuid4()
        user_id = uuid4()
        tenancies = ["tenant1"]

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        now = datetime.datetime.now()

        existing_doi = DOIDBModel(
            identifier="10.1234/example-doi",
            mode=DOIMode.AUTO.name,
            state=DOIState.DRAFT.name,
            created_by=user_id,
            prefix="10.1234",
            suffix="example-doi",
            url="https://example.com/doi",
            created_at=now,
            updated_at=now,
            version_id=uuid4(),
        )

        existing_version_1 = DatasetVersionDBModel(
            id=uuid4(),
            name="1",
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[],
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=existing_doi,
        )

        existing_version_2 = DatasetVersionDBModel(
            id=uuid4(),
            name="2",
            description="Initial version",
            design_state=DesignState.PUBLISHED,
            is_enabled=True,
            created_by=user_id,
            files=[],
            created_at=now,
            updated_at=now,
            dataset_id=dataset_id,
            doi_identifier="10.1234/example-doi",
            doi_state="DRAFT",
            doi=existing_doi,
        )

        existing_dataset = DatasetDBModel(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            is_enabled=True,
            created_at=now,
            updated_at=now,
            tenancy=["tenant1"],
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=user_id,
            versions=[existing_version_1, existing_version_2],
        )

        self.dataset_repository.fetch.return_value = existing_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = (
            existing_version_2
        )

        result = self.dataset_service.fetch_dataset_version(
            dataset_id=dataset_id,
            version_name="2",
            user_id=user_id,
            tenancies=tenancies,
        )

        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id,
            tenancies=tenancies,
        )
        self.dataset_version_repository.fetch_version_by_name.assert_called_once_with(
            dataset_id=dataset_id,
            version_name="2",
        )

        expected_dataset = Dataset(
            id=dataset_id,
            name="Original Dataset",
            data={"key": "original"},
            tenancy=["tenant1"],
            is_enabled=True,
            created_at=now,
            updated_at=now,
            design_state=DesignState.DRAFT,
            visibility=None,
            owner_id=None,
            version=DatasetVersion(
                id=existing_version_2.id,
                name=existing_version_2.name,
                description=existing_version_2.description,
                design_state=DesignState.PUBLISHED,
                is_enabled=True,
                created_at=now,
                updated_at=now,
                created_by=user_id,
                files=[],
                files_count=0,
                files_size_in_bytes=0,
                doi=DOIAdapter.database_to_model(doi=existing_doi),
            ),
        )

        self.assertEqual(result, expected_dataset)

    def test_fetch_dataset_version_dataset_not_found(self):
        dataset_id = uuid4()
        user_id = uuid4()
        tenancies = ["tenant1"]
        version_name = "2"

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        self.dataset_repository.fetch.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.fetch_dataset_version(
                dataset_id=dataset_id,
                version_name=version_name,
                user_id=user_id,
                tenancies=tenancies,
            )

        self.assertEqual(str(context.exception), f"not_found: {dataset_id}")

    def test_fetch_dataset_version_version_not_found(self):
        dataset_id = uuid4()
        user_id = uuid4()
        tenancies = ["tenant1"]
        version_name = "2"

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        self.dataset_repository.fetch.return_value = None

        mock_dataset = Mock(spec=DatasetDBModel)
        self.dataset_repository.fetch.return_value = mock_dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.fetch_dataset_version(
                dataset_id=dataset_id,
                version_name=version_name,
                user_id=user_id,
                tenancies=tenancies,
            )

        self.assertEqual(
            str(context.exception),
            f"not_found: {version_name} for dataset {dataset_id}",
        )

    def test_search_datasets_with_visibility_filter(self):
        user_id = uuid4()
        tenancies = ["tenant1"]
        query = DatasetQuery(visibility="PUBLIC")

        mock_dataset = Mock(spec=DatasetDBModel)
        mock_dataset.id = uuid4()
        mock_dataset.name = "Test Dataset"
        mock_dataset.data = {}
        mock_dataset.is_enabled = True
        mock_dataset.created_at = datetime.datetime.now()
        mock_dataset.updated_at = datetime.datetime.now()
        mock_dataset.tenancy = tenancies
        mock_dataset.design_state = DesignState.DRAFT
        mock_dataset.visibility = VisibilityStatus.PUBLIC
        mock_dataset.versions = []

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_repository.search.return_value = [mock_dataset]

        result = self.dataset_service.search_datasets(
            query=query, user_id=user_id, tenancies=tenancies
        )

        self.dataset_repository.search.assert_called_once_with(
            query_params=query, tenancies=tenancies
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].visibility, VisibilityStatus.PUBLIC)

    def test_get_latest_published_version_success(self):
        # Arrange
        dataset_id = uuid4()
        tenancies = ["tenant1"]

        # Create dataset with multiple versions
        dataset = DatasetDBModel()
        dataset.id = dataset_id
        dataset.tenancy = tenancies[0]
        dataset.versions = []

        # Create versions with different created_at dates
        version1 = DatasetVersionDBModel()
        version1.id = uuid4()
        version1.name = "v1.0"
        version1.is_enabled = True
        version1.created_at = datetime.datetime(2024, 1, 1)
        version1.doi = DOIDBModel()
        version1.doi.identifier = "10.1234/doi1"

        version2 = DatasetVersionDBModel()
        version2.id = uuid4()
        version2.name = "v2.0"
        version2.is_enabled = True
        version2.created_at = datetime.datetime(2024, 2, 1)  # Later date
        version2.doi = DOIDBModel()
        version2.doi.identifier = "10.1234/doi2"

        version3 = DatasetVersionDBModel()
        version3.id = uuid4()
        version3.name = "v3.0"
        version3.is_enabled = True
        version3.created_at = datetime.datetime(2024, 1, 15)  # Middle date
        version3.doi = None  # No DOI - should be excluded

        dataset.versions = [version1, version2, version3]

        # Act
        result = self.dataset_service._get_latest_published_version(dataset)

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result.id, version2.id)
        self.assertEqual(result.name, "v2.0")

    def test_get_latest_published_version_no_published_versions(self):
        # Arrange
        dataset = DatasetDBModel()
        dataset.versions = []

        version1 = DatasetVersionDBModel()
        version1.is_enabled = True
        version1.doi = None  # No DOI

        version2 = DatasetVersionDBModel()
        version2.is_enabled = False
        version2.doi = DOIDBModel()  # Has DOI but disabled

        dataset.versions = [version1, version2]

        # Act
        result = self.dataset_service._get_latest_published_version(dataset)

        # Assert
        self.assertIsNone(result)

    def test_update_dataset_visibility_success(self):
        # Arrange
        dataset = DatasetDBModel()
        dataset.id = uuid4()
        dataset.visibility = VisibilityStatus.PRIVATE

        self.dataset_repository.upsert.return_value = dataset

        # Act
        self.dataset_service._update_dataset_visibility(dataset)

        # Assert
        self.assertEqual(dataset.visibility, VisibilityStatus.PUBLIC)
        self.dataset_repository.upsert.assert_called_once_with(dataset)

    def test_create_dataset_json_snapshot_without_versions_list(self):
        # Arrange
        dataset = DatasetDBModel()
        dataset.id = uuid4()
        dataset.data = {"title": "Test Dataset", "description": "A test dataset"}

        version = DatasetVersionDBModel()
        version.name = "v1.0"
        version.created_at = datetime.datetime(2024, 1, 1)
        version.doi = DOIDBModel()
        version.doi.identifier = "10.1234/test"
        version.doi.state = DOIState.FINDABLE.value

        # Act
        result = self.dataset_service._create_dataset_json_snapshot(
            dataset, version, include_versions_list=False
        )

        # Assert
        self.assertEqual(result["title"], "Test Dataset")
        self.assertEqual(result["description"], "A test dataset")
        self.assertEqual(result["dataset_id"], str(dataset.id))
        self.assertEqual(result["version_name"], "v1.0")
        self.assertEqual(result["doi_identifier"], "10.1234/test")
        self.assertEqual(result["doi_state"], DOIState.FINDABLE.value)
        self.assertIsNotNone(result["publication_date"])
        self.assertNotIn("versions", result)

    def test_create_dataset_json_snapshot_with_versions_list(self):
        # Arrange
        dataset = DatasetDBModel()
        dataset.id = uuid4()
        dataset.data = {"title": "Test Dataset"}
        dataset.versions = []

        # Create current version
        current_version = DatasetVersionDBModel()
        current_version.id = uuid4()
        current_version.name = "v2.0"
        current_version.is_enabled = True
        current_version.created_at = datetime.datetime(2024, 2, 1)
        current_version.doi = DOIDBModel()
        current_version.doi.identifier = "10.1234/current"
        current_version.doi.state = DOIState.FINDABLE.value
        current_version.doi.mode = DOIMode.AUTO.value

        # Create older version
        older_version = DatasetVersionDBModel()
        older_version.id = uuid4()
        older_version.name = "v1.0"
        older_version.is_enabled = True
        older_version.created_at = datetime.datetime(2024, 1, 1)
        older_version.doi = DOIDBModel()
        older_version.doi.identifier = "10.1234/old"
        older_version.doi.state = DOIState.FINDABLE.value
        older_version.doi.mode = DOIMode.MANUAL.value

        dataset.versions = [current_version, older_version]

        # Act
        result = self.dataset_service._create_dataset_json_snapshot(
            dataset, current_version, include_versions_list=True
        )

        # Assert
        self.assertIn("versions", result)
        self.assertEqual(len(result["versions"]), 2)

        # Check versions are ordered by created_at desc (most recent first)
        self.assertEqual(result["versions"][0]["name"], "v2.0")
        self.assertEqual(result["versions"][0]["doi_state"], DOIState.FINDABLE.value)
        self.assertEqual(result["versions"][1]["name"], "v1.0")
        self.assertEqual(
            result["versions"][1]["doi_state"], "FINDABLE"
        )  # MANUAL mode = FINDABLE

    @patch("app.service.dataset.json.dumps")
    def test_publish_dataset_snapshot_success(self, mock_json_dumps):
        # Arrange
        dataset_id = uuid4()
        version_name = "v1.0"
        user_id = uuid4()
        tenancies = ["tenant1"]

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        dataset = DatasetDBModel()
        dataset.id = dataset_id
        dataset.data = {"title": "Test Dataset"}
        dataset.visibility = VisibilityStatus.PRIVATE

        version = DatasetVersionDBModel()
        version.id = uuid4()
        version.name = version_name
        version.created_at = datetime.datetime(2024, 1, 1)
        version.is_enabled = True
        version.doi = DOIDBModel()
        version.doi.identifier = "10.1234/test"
        version.files_in = []  # Add files_in to avoid None issues

        dataset.versions = [version]

        self.dataset_repository.fetch.return_value = dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = version
        self.dataset_repository.upsert.return_value = dataset

        # Mock JSON dumps to return predictable bytes
        mock_json_dumps.return_value = '{"test": "data"}'

        # Act
        self.dataset_service._publish_dataset_snapshot(
            dataset_id, version_name, user_id, tenancies
        )

        # Assert
        self.dataset_repository.fetch.assert_called_once()
        self.dataset_version_repository.fetch_version_by_name.assert_called_once()

        # Verify dataset visibility was updated
        self.assertEqual(dataset.visibility, VisibilityStatus.PUBLIC)
        self.dataset_repository.upsert.assert_called_once_with(dataset)

        # Verify MinIO calls
        self.assertEqual(self.minio_gateway.put_file.call_count, 2)  # version + latest

        # Check version snapshot call
        version_call = self.minio_gateway.put_file.call_args_list[0]
        self.assertEqual(version_call[1]["bucket_name"], "datamap")
        self.assertEqual(
            version_call[1]["object_name"],
            f"snapshots/{dataset_id}-{version_name}.json",
        )
        self.assertEqual(version_call[1]["content_type"], "application/json")

        # Check latest snapshot call
        latest_call = self.minio_gateway.put_file.call_args_list[1]
        self.assertEqual(latest_call[1]["bucket_name"], "datamap")
        self.assertEqual(
            latest_call[1]["object_name"], f"snapshots/{dataset_id}-latest.json"
        )
        self.assertEqual(latest_call[1]["content_type"], "application/json")

    def test_publish_dataset_snapshot_dataset_not_found(self):
        # Arrange
        dataset_id = uuid4()
        version_name = "v1.0"
        user_id = uuid4()
        tenancies = ["tenant1"]

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_repository.fetch.return_value = None

        # Act & Assert
        with self.assertRaises(NotFoundException) as context:
            self.dataset_service._publish_dataset_snapshot(
                dataset_id, version_name, user_id, tenancies
            )

        self.assertIn(str(dataset_id), str(context.exception))

    def test_publish_dataset_snapshot_version_not_found(self):
        # Arrange
        dataset_id = uuid4()
        version_name = "v1.0"
        user_id = uuid4()
        tenancies = ["tenant1"]

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)

        dataset = DatasetDBModel()
        dataset.id = dataset_id

        self.dataset_repository.fetch.return_value = dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = None

        # Act & Assert
        with self.assertRaises(NotFoundException) as context:
            self.dataset_service._publish_dataset_snapshot(
                dataset_id, version_name, user_id, tenancies
            )

        self.assertIn(version_name, str(context.exception))

    def test_change_doi_state_triggers_publication_on_findable(self):
        # Arrange
        dataset_id = uuid4()
        version_name = "v1.0"
        user_id = uuid4()
        tenancies = ["tenant1"]
        new_state = DOIState.FINDABLE

        dataset = DatasetDBModel()
        dataset.id = dataset_id

        version = DatasetVersionDBModel()
        version.name = version_name
        version.doi = DOIDBModel()
        version.doi.identifier = "10.1234/test"

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_repository.fetch.return_value = dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = version

        # Mock the publication method
        with patch.object(
            self.dataset_service, "_publish_dataset_snapshot"
        ) as mock_publish:
            # Act
            self.dataset_service.change_doi_state(
                dataset_id, version_name, new_state, user_id, tenancies
            )

            # Assert
            self.doi_service.change_state.assert_called_once_with(
                identifier=version.doi.identifier, new_state=new_state
            )
            mock_publish.assert_called_once_with(
                dataset_id=dataset_id,
                version_name=version_name,
                user_id=user_id,
                tenancies=tenancies,
            )

    def test_change_doi_state_no_publication_on_non_findable(self):
        # Arrange
        dataset_id = uuid4()
        version_name = "v1.0"
        user_id = uuid4()
        tenancies = ["tenant1"]
        new_state = DOIState.REGISTERED  # Not FINDABLE

        dataset = DatasetDBModel()
        dataset.id = dataset_id

        version = DatasetVersionDBModel()
        version.name = version_name
        version.doi = DOIDBModel()
        version.doi.identifier = "10.1234/test"

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_repository.fetch.return_value = dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = version

        # Mock the publication method
        with patch.object(
            self.dataset_service, "_publish_dataset_snapshot"
        ) as mock_publish:
            # Act
            self.dataset_service.change_doi_state(
                dataset_id, version_name, new_state, user_id, tenancies
            )

            # Assert
            self.doi_service.change_state.assert_called_once_with(
                identifier=version.doi.identifier, new_state=new_state
            )
            mock_publish.assert_not_called()

    def test_create_doi_triggers_publication_on_manual_mode(self):
        # Arrange
        dataset_id = uuid4()
        version_name = "v1.0"
        user_id = uuid4()
        tenancies = ["tenant1"]

        doi = DOI(
            mode=DOIMode.MANUAL,
            identifier="10.1234/manual",
            title=DOITitle(title="Test DOI"),
        )

        dataset = DatasetDBModel()
        dataset.id = dataset_id
        dataset.name = "Test Dataset"
        dataset.data = {"authors": [{"name": "Test Author"}]}
        dataset.created_at = datetime.datetime(2024, 1, 1)

        version = DatasetVersionDBModel()
        version.name = version_name
        version.doi = None  # No existing DOI

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_repository.fetch.return_value = dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = version
        self.doi_service.create.return_value = doi

        # Mock the publication method
        with patch.object(
            self.dataset_service, "_publish_dataset_snapshot"
        ) as mock_publish:
            # Act
            result = self.dataset_service.create_doi(
                dataset_id, version_name, doi, user_id, tenancies
            )

            # Assert
            self.doi_service.create.assert_called_once()
            mock_publish.assert_called_once_with(
                dataset_id=dataset_id,
                version_name=version_name,
                user_id=user_id,
                tenancies=tenancies,
            )
            self.assertEqual(result, doi)

    def test_create_doi_no_publication_on_auto_mode(self):
        # Arrange
        dataset_id = uuid4()
        version_name = "v1.0"
        user_id = uuid4()
        tenancies = ["tenant1"]

        doi = DOI(
            mode=DOIMode.AUTO,  # Not MANUAL
            identifier="10.1234/auto",
            title=DOITitle(title="Test DOI"),
        )

        dataset = DatasetDBModel()
        dataset.id = dataset_id
        dataset.name = "Test Dataset"
        dataset.data = {"authors": [{"name": "Test Author"}]}
        dataset.created_at = datetime.datetime(2024, 1, 1)

        version = DatasetVersionDBModel()
        version.name = version_name
        version.doi = None  # No existing DOI

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_repository.fetch.return_value = dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = version
        self.doi_service.create.return_value = doi

        # Mock the publication method
        with patch.object(
            self.dataset_service, "_publish_dataset_snapshot"
        ) as mock_publish:
            # Act
            result = self.dataset_service.create_doi(
                dataset_id, version_name, doi, user_id, tenancies
            )

            # Assert
            self.doi_service.create.assert_called_once()
            mock_publish.assert_not_called()
            self.assertEqual(result, doi)

    def test_publication_error_does_not_fail_doi_operations(self):
        # Test for change_doi_state
        dataset_id = uuid4()
        version_name = "v1.0"
        user_id = uuid4()
        tenancies = ["tenant1"]
        new_state = DOIState.FINDABLE

        dataset = DatasetDBModel()
        dataset.id = dataset_id

        version = DatasetVersionDBModel()
        version.name = version_name
        version.doi = DOIDBModel()
        version.doi.identifier = "10.1234/test"

        self.user_service.fetch_by_id.return_value = self.mock_user(tenancies)
        self.dataset_repository.fetch.return_value = dataset
        self.dataset_version_repository.fetch_version_by_name.return_value = version

        # Mock publication to raise exception
        with patch.object(
            self.dataset_service, "_publish_dataset_snapshot"
        ) as mock_publish:
            mock_publish.side_effect = Exception("Publication failed")

            # Act - should not raise exception
            self.dataset_service.change_doi_state(
                dataset_id, version_name, new_state, user_id, tenancies
            )

            # Assert
            self.doi_service.change_state.assert_called_once_with(
                identifier=version.doi.identifier, new_state=new_state
            )
            mock_publish.assert_called_once()

    def test_get_dataset_latest_snapshot_success(self):
        # Arrange
        dataset_id = uuid4()
        expected_snapshot = {
            "dataset_id": str(dataset_id),
            "version_name": "v2.0",
            "doi_identifier": "10.1234/test",
            "doi_link": "https://doi.org/10.1234/test",
            "doi_state": "FINDABLE",
            "publication_date": "2024-01-01T00:00:00",
            "title": "Test Dataset",
            "files_summary": {
                "total_files": 2,
                "total_size_bytes": 1024,
                "extensions_breakdown": [
                    {"extension": ".csv", "count": 1, "total_size_bytes": 512},
                    {"extension": ".json", "count": 1, "total_size_bytes": 512},
                ],
            },
            "versions": [
                {
                    "id": str(uuid4()),
                    "name": "v2.0",
                    "doi_identifier": "10.1234/test",
                    "doi_state": "FINDABLE",
                    "created_at": "2024-01-01T00:00:00",
                }
            ],
        }

        # Mock MinIO to return JSON bytes
        json_bytes = json.dumps(expected_snapshot).encode("utf-8")
        self.minio_gateway.get_file.return_value = json_bytes

        # Act
        result = self.dataset_service.get_dataset_latest_snapshot(dataset_id)

        # Assert
        self.minio_gateway.get_file.assert_called_once_with(
            bucket_name="datamap", object_name=f"snapshots/{dataset_id}-latest.json"
        )
        self.assertEqual(result, expected_snapshot)

    def test_get_dataset_latest_snapshot_not_found(self):
        # Arrange
        dataset_id = uuid4()
        self.minio_gateway.get_file.side_effect = FileNotFoundError("Object not found")

        # Act & Assert
        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.get_dataset_latest_snapshot(dataset_id)

        self.assertIn("Latest snapshot not found", str(context.exception))
        self.assertIn(str(dataset_id), str(context.exception))

    def test_get_dataset_latest_snapshot_invalid_json(self):
        # Arrange
        dataset_id = uuid4()
        invalid_json_bytes = b'{"invalid": json}'  # Missing closing brace
        self.minio_gateway.get_file.return_value = invalid_json_bytes

        # Act & Assert
        with self.assertRaises(IllegalStateException) as context:
            self.dataset_service.get_dataset_latest_snapshot(dataset_id)

        self.assertIn("Corrupted snapshot data", str(context.exception))

    def test_get_dataset_version_snapshot_success(self):
        # Arrange
        dataset_id = uuid4()
        version_name = "v1.0"
        expected_snapshot = {
            "dataset_id": str(dataset_id),
            "version_name": version_name,
            "doi_identifier": "10.1234/test",
            "doi_link": "https://doi.org/10.1234/test",
            "doi_state": "FINDABLE",
            "publication_date": "2024-01-01T00:00:00",
            "title": "Test Dataset",
            "files_summary": {
                "total_files": 1,
                "total_size_bytes": 256,
                "extensions_breakdown": [
                    {"extension": ".txt", "count": 1, "total_size_bytes": 256}
                ],
            },
        }

        # Mock MinIO to return JSON bytes
        json_bytes = json.dumps(expected_snapshot).encode("utf-8")
        self.minio_gateway.get_file.return_value = json_bytes

        # Act
        result = self.dataset_service.get_dataset_version_snapshot(
            dataset_id, version_name
        )

        # Assert
        self.minio_gateway.get_file.assert_called_once_with(
            bucket_name="datamap",
            object_name=f"snapshots/{dataset_id}-{version_name}.json",
        )
        self.assertEqual(result, expected_snapshot)

    def test_get_dataset_version_snapshot_not_found(self):
        # Arrange
        dataset_id = uuid4()
        version_name = "v1.0"
        self.minio_gateway.get_file.side_effect = FileNotFoundError("Object not found")

        # Act & Assert
        with self.assertRaises(NotFoundException) as context:
            self.dataset_service.get_dataset_version_snapshot(dataset_id, version_name)

        self.assertIn("Snapshot not found", str(context.exception))
        self.assertIn(str(dataset_id), str(context.exception))
        self.assertIn(version_name, str(context.exception))

    def test_get_dataset_version_snapshot_invalid_json(self):
        # Arrange
        dataset_id = uuid4()
        version_name = "v1.0"
        invalid_json_bytes = b'{"invalid": json}'  # Missing closing brace
        self.minio_gateway.get_file.return_value = invalid_json_bytes

        # Act & Assert
        with self.assertRaises(IllegalStateException) as context:
            self.dataset_service.get_dataset_version_snapshot(dataset_id, version_name)

        self.assertIn("Corrupted snapshot data", str(context.exception))

    def test_create_dataset_json_snapshot_file_summary(self):
        # Arrange
        dataset = Mock()
        dataset.id = uuid4()
        dataset.data = {"title": "Test Dataset"}

        version = Mock()
        version.name = "v1.0"
        version.created_at = datetime.datetime(2024, 1, 1)
        version.doi = Mock()
        version.doi.identifier = "10.1234/test"
        version.doi.state = "FINDABLE"

        # Mock files with different extensions and sizes
        file1 = Mock()
        file1.name = "data.csv"
        file1.size_bytes = 1024

        file2 = Mock()
        file2.name = "metadata.json"
        file2.size_bytes = 512

        file3 = Mock()
        file3.name = "report.csv"
        file3.size_bytes = 2048

        file4 = Mock()
        file4.name = "readme"  # No extension
        file4.size_bytes = 256

        file5 = Mock()
        file5.name = "data.backup.csv"  # Multiple dots
        file5.size_bytes = 512

        file6 = Mock()
        file6.name = ".hidden"  # Starts with dot
        file6.size_bytes = 128

        version.files_in = [file1, file2, file3, file4, file5, file6]

        # Act
        result = self.dataset_service._create_dataset_json_snapshot(dataset, version)

        # Assert
        self.assertIn("files_summary", result)
        summary = result["files_summary"]

        self.assertEqual(summary["total_files"], 6)
        self.assertEqual(
            summary["total_size_bytes"], 4480
        )  # 1024 + 512 + 2048 + 256 + 512 + 128

        # Check extensions breakdown
        extensions = summary["extensions_breakdown"]
        self.assertEqual(len(extensions), 4)  # .csv, .json, .hidden, (no extension)

        # Find each extension
        csv_ext = next(e for e in extensions if e["extension"] == ".csv")
        json_ext = next(e for e in extensions if e["extension"] == ".json")
        hidden_ext = next(e for e in extensions if e["extension"] == ".hidden")
        no_ext = next(e for e in extensions if e["extension"] == "(no extension)")

        self.assertEqual(csv_ext["count"], 3)  # data.csv, report.csv, data.backup.csv
        self.assertEqual(csv_ext["total_size_bytes"], 3584)  # 1024 + 2048 + 512

        self.assertEqual(json_ext["count"], 1)
        self.assertEqual(json_ext["total_size_bytes"], 512)

        self.assertEqual(hidden_ext["count"], 1)  # .hidden
        self.assertEqual(hidden_ext["total_size_bytes"], 128)

        self.assertEqual(no_ext["count"], 1)  # readme only
        self.assertEqual(no_ext["total_size_bytes"], 256)


if __name__ == "__main__":
    unittest.main()
