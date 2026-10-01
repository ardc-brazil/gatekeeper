import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

from app.exception.bad_request import BadRequestException
from app.exception.forbidden import ForbiddenException
from app.model.dataset import VisibilityStatus
from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.db.dataset import DatasetVersion as DatasetVersionDBModel
from app.model.db.doi import DOI as DOIDBModel
from app.model.dataset_access import AccessEventType, AccessLevel, DatasetAction
from app.repository.dataset import DatasetRepository
from app.service.dataset import DatasetService
from app.service.dataset_access import DatasetAccessService
from app.service.embargo import EmbargoService
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.embargo_termination import EmbargoTermination

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class TestEmbargoService(unittest.TestCase):
    def setUp(self):
        self.datasets = Mock(spec=DatasetService)
        self.repository = Mock(spec=DatasetRepository)
        self.audit = Mock(spec=DatasetAccessAudit)
        self.access = DatasetAccessService(
            permission_repository=Mock(), user_service=Mock()
        )
        self.service = EmbargoService(
            dataset_service=self.datasets,
            repository=self.repository,
            access_service=self.access,
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
            embargo_until=None,
            embargo_metadata_visible=False,
        )
        self.datasets.fetch_authorized.return_value = (
            self.dataset,
            ["t"],
            AccessLevel.OWNER,
        )
        patcher = patch("app.service.embargo.utcnow", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)
        patch_access = patch("app.service.dataset_access.utcnow", return_value=NOW)
        patch_access.start()
        self.addCleanup(patch_access.stop)

    def _code(self, call) -> str:
        with self.assertRaises(BadRequestException) as raised:
            call()
        return raised.exception.errors[0].code

    def _set(self, until, visible=False):
        return self.service.set_embargo(
            dataset_id=self.dataset.id,
            user_id=self.user_id,
            tenancies=None,
            until=until,
            metadata_visible=visible,
            note="under review",
        )

    def test_setting_an_embargo(self):
        embargo = self._set(NOW + timedelta(days=30), visible=True)

        self.assertTrue(embargo.active)
        self.assertTrue(embargo.metadata_visible)
        self.assertEqual(self.dataset.embargo_until, NOW + timedelta(days=30))
        self.repository.upsert.assert_called_once_with(dataset=self.dataset)
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"], AccessEventType.CREATED
        )
        self.assertEqual(
            self.datasets.fetch_authorized.call_args.kwargs["action"],
            DatasetAction.MANAGE_EMBARGO,
        )

    def test_the_cap_applies_on_creation(self):
        self.assertEqual(
            self._code(lambda: self._set(NOW + timedelta(days=90, seconds=1))),
            "embargo_too_long",
        )

    def test_ninety_days_exactly_is_allowed(self):
        self.assertTrue(self._set(NOW + timedelta(days=90)).active)

    def test_a_date_in_the_past_is_refused(self):
        self.assertEqual(
            self._code(lambda: self._set(NOW - timedelta(minutes=1))),
            "embargo_until_in_past",
        )

    def test_a_published_dataset_cannot_be_embargoed(self):
        self.dataset.visibility = VisibilityStatus.PUBLIC
        self.assertEqual(
            self._code(lambda: self._set(NOW + timedelta(days=1))),
            "embargo_dataset_published",
        )

    def _with_manual_doi(self):
        self.dataset.versions = [
            DatasetVersionDBModel(
                name="1",
                doi=DOIDBModel(mode="MANUAL", state="FINDABLE", doi={}),
            )
        ]

    def test_a_dataset_with_a_manual_doi_cannot_be_embargoed(self):
        self._with_manual_doi()
        self.assertEqual(
            self._code(lambda: self._set(NOW + timedelta(days=1))),
            "embargo_manual_doi",
        )

    def test_the_manual_doi_check_does_not_rely_on_the_snapshot(self):
        self._with_manual_doi()
        self.dataset.visibility = VisibilityStatus.PUBLIC
        self.assertEqual(
            self._code(lambda: self._set(NOW + timedelta(days=1))),
            "embargo_manual_doi",
        )

    def test_a_datamap_doi_does_not_prevent_an_embargo(self):
        self.dataset.versions = [
            DatasetVersionDBModel(
                name="1", doi=DOIDBModel(mode="AUTO", state="DRAFT", doi={})
            )
        ]
        self.assertTrue(self._set(NOW + timedelta(days=1)).active)

    def test_an_active_embargo_cannot_be_set_again(self):
        self.dataset.embargo_until = NOW + timedelta(days=1)
        self.assertEqual(
            self._code(lambda: self._set(NOW + timedelta(days=2))),
            "embargo_already_active",
        )

    def test_an_embargo_that_ended_unpublished_can_be_set_again(self):
        self.dataset.embargo_until = NOW - timedelta(days=1)
        self.assertTrue(self._set(NOW + timedelta(days=2)).active)

    def test_a_naive_date_is_read_as_utc(self):
        naive = (NOW + timedelta(days=3)).replace(tzinfo=None)
        self.assertEqual(self._set(naive).until, NOW + timedelta(days=3))

    def _extend(self, until):
        return self.service.extend(
            dataset_id=self.dataset.id,
            user_id=self.user_id,
            tenancies=None,
            until=until,
        )

    def test_extending(self):
        self.dataset.embargo_until = NOW + timedelta(days=10)
        embargo = self._extend(NOW + timedelta(days=80))
        self.assertEqual(embargo.until, NOW + timedelta(days=80))
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"],
            AccessEventType.EXTENDED,
        )

    def test_the_cap_applies_on_every_extension(self):
        self.dataset.embargo_until = NOW + timedelta(days=10)
        self.assertEqual(
            self._code(lambda: self._extend(NOW + timedelta(days=91))),
            "embargo_too_long",
        )

    def test_an_extension_must_move_the_date_forward(self):
        self.dataset.embargo_until = NOW + timedelta(days=10)
        self.assertEqual(
            self._code(lambda: self._extend(NOW + timedelta(days=10))),
            "embargo_until_not_later",
        )

    def test_there_is_nothing_to_extend_without_an_active_embargo(self):
        self.assertEqual(
            self._code(lambda: self._extend(NOW + timedelta(days=10))),
            "embargo_not_active",
        )

    def test_a_reader_cannot_extend_while_the_owner_is_active(self):
        self.dataset.embargo_until = NOW + timedelta(days=10)
        self.dataset.owner_id = uuid4()
        self.datasets.fetch_authorized.return_value = (
            self.dataset,
            [],
            AccessLevel.READ,
        )
        self.access._permissions.fetch.return_value = Mock(level="read")
        with self.assertRaises(ForbiddenException):
            self._extend(NOW + timedelta(days=20))

    def test_ending_early(self):
        self.dataset.embargo_until = NOW + timedelta(days=10)
        embargo = self.service.end(
            dataset_id=self.dataset.id, user_id=self.user_id, tenancies=None
        )
        self.assertFalse(embargo.active)
        self.assertEqual(self.dataset.embargo_until, NOW)
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"],
            AccessEventType.ENDED_EARLY,
        )

    def test_switching_mode(self):
        self.dataset.embargo_until = NOW + timedelta(days=10)
        embargo = self.service.set_mode(
            dataset_id=self.dataset.id,
            user_id=self.user_id,
            tenancies=None,
            metadata_visible=True,
        )
        self.assertTrue(embargo.metadata_visible)
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"],
            AccessEventType.METADATA_MODE_CHANGED,
        )

    def test_status_of_an_unknown_dataset_reveals_nothing(self):
        self.repository.fetch.return_value = None
        self.assertEqual(self.service.status(uuid4()), (False, None))

    def test_status_of_an_embargoed_dataset(self):
        self.dataset.embargo_until = NOW + timedelta(days=10)
        self.repository.fetch.return_value = self.dataset
        self.assertEqual(
            self.service.status(self.dataset.id), (True, NOW + timedelta(days=10))
        )
