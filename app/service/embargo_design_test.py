import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from app.exception.bad_request import BadRequestException
from app.exception.not_found import NotFoundException
from app.model.dataset import Dataset, VisibilityStatus
from app.model.dataset_access import AccessEventType, AccessLevel, DatasetAction
from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.user import User
from app.repository.dataset import DatasetRepository
from app.service.dataset import DatasetService
from app.service.dataset_access import DatasetAccessService
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.embargo import EmbargoService
from app.service.embargo_termination import EmbargoTermination
from app.service.user import UserService

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class EmbargoDesignTestCase(unittest.TestCase):
    def setUp(self):
        self.datasets = Mock(spec=DatasetService)
        self.repository = Mock(spec=DatasetRepository)
        self.audit = Mock(spec=DatasetAccessAudit)
        self.service = EmbargoService(
            dataset_service=self.datasets,
            repository=self.repository,
            access_service=DatasetAccessService(
                permission_repository=Mock(), user_service=Mock()
            ),
            audit=self.audit,
            termination=EmbargoTermination(
                repository=self.repository, audit=self.audit
            ),
        )
        self.user_id = uuid4()
        self.dataset = DatasetDBModel(
            id=uuid4(),
            name="d",
            data={},
            owner_id=self.user_id,
            tenancy="t",
            visibility=VisibilityStatus.PRIVATE,
            embargo_until=NOW + timedelta(days=30),
            embargo_metadata_visible=False,
            embargo_note="Under review",
        )
        self.datasets.fetch_authorized.return_value = (
            self.dataset,
            ["t"],
            AccessLevel.OWNER,
        )
        for target in (
            "app.service.embargo.utcnow",
            "app.service.dataset_access.utcnow",
        ):
            patcher = patch(target, return_value=NOW)
            patcher.start()
            self.addCleanup(patcher.stop)


class TestExtendReason(EmbargoDesignTestCase):
    def test_the_reason_is_recorded_as_the_events_note(self):
        self.service.extend(
            self.dataset.id,
            self.user_id,
            None,
            NOW + timedelta(days=80),
            reason="Second review round",
        )

        self.assertEqual(
            self.audit.record.call_args.kwargs["note"], "Second review round"
        )
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"], AccessEventType.EXTENDED
        )


class TestSetNote(EmbargoDesignTestCase):
    def test_the_owner_changes_the_note_and_it_is_recorded(self):
        embargo = self.service.set_note(
            self.dataset.id, self.user_id, None, "Accepted with revisions"
        )

        self.assertEqual(self.dataset.embargo_note, "Accepted with revisions")
        self.assertEqual(embargo.note, "Accepted with revisions")
        self.assertEqual(
            self.datasets.fetch_authorized.call_args.kwargs["action"],
            DatasetAction.MANAGE_EMBARGO,
        )
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"],
            AccessEventType.NOTE_CHANGED,
        )

    def test_the_same_note_is_not_an_event(self):
        self.service.set_note(self.dataset.id, self.user_id, None, "Under review")

        self.audit.record.assert_not_called()

    def test_without_an_active_embargo_there_is_no_note_to_change(self):
        self.dataset.embargo_until = NOW - timedelta(days=1)

        with self.assertRaises(BadRequestException):
            self.service.set_note(self.dataset.id, self.user_id, None, "x")


class TestDoiFor(EmbargoDesignTestCase):
    def test_the_doi_of_the_named_version_is_returned(self):
        dataset = SimpleNamespace(
            versions=[
                SimpleNamespace(
                    name="1", doi=SimpleNamespace(identifier="10.5281/datamap.1")
                ),
                SimpleNamespace(name="2", doi=None),
            ]
        )
        self.repository.fetch.return_value = dataset

        self.assertEqual(
            self.service.doi_for(self.dataset.id, "1"), "10.5281/datamap.1"
        )
        self.assertIsNone(self.service.doi_for(self.dataset.id, "2"))
        self.assertIsNone(self.service.doi_for(self.dataset.id, "9"))


class TestOwnerName(unittest.TestCase):
    def setUp(self):
        self.users = Mock(spec=UserService)
        self.access = Mock(spec=DatasetAccessService)
        self.access.require.return_value = AccessLevel.OWNER
        self.access.permits.return_value = True
        self.access.embargo_of.return_value = None
        self.repository = Mock(spec=DatasetRepository)
        self.service = DatasetService(
            repository=self.repository,
            version_repository=Mock(),
            data_file_repository=Mock(),
            user_service=self.users,
            doi_service=Mock(),
            minio_gateway=Mock(),
            tenancy_service=Mock(),
            access_service=self.access,
            embargo_termination=Mock(),
            dataset_bucket="b",
        )
        self.owner_id = uuid4()
        self.repository.fetch.return_value = SimpleNamespace(owner_id=self.owner_id)
        self.service._determine_tenancies = Mock(return_value=["t"])
        self.service._adapt_dataset = Mock(
            side_effect=lambda dataset: Dataset(name="d", data={})
        )

    def test_the_detail_names_the_owner(self):
        self.users.fetch_by_id.return_value = User(
            id=self.owner_id, name="Luciana Rizzo"
        )

        dataset = self.service.fetch_dataset(dataset_id=uuid4(), user_id=uuid4())

        self.assertEqual(dataset.owner_name, "Luciana Rizzo")

    def test_a_disabled_owner_is_still_named(self):
        def fetch_by_id(id, is_enabled=True):
            if is_enabled:
                raise NotFoundException("not_found")
            return User(id=id, name="Luciana Rizzo")

        self.users.fetch_by_id.side_effect = fetch_by_id

        dataset = self.service.fetch_dataset(dataset_id=uuid4(), user_id=uuid4())

        self.assertEqual(dataset.owner_name, "Luciana Rizzo")

    def test_an_owner_who_cannot_be_read_leaves_no_name(self):
        self.users.fetch_by_id.side_effect = NotFoundException("not_found")

        dataset = self.service.fetch_dataset(dataset_id=uuid4(), user_id=uuid4())

        self.assertIsNone(dataset.owner_name)
