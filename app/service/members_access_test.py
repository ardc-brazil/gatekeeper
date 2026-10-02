import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

from app.exception.forbidden import ForbiddenException
from app.model.dataset import VisibilityStatus
from app.model.dataset_access import AccessEventType, AccessLevel, DatasetAction
from app.model.db.dataset import Dataset as DatasetDBModel
from app.repository.dataset import DatasetRepository
from app.service.dataset import DatasetService
from app.service.dataset_access import DatasetAccessService
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.members_access import MembersAccessService

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


class TestMembersAccessService(unittest.TestCase):
    def setUp(self):
        self.datasets = Mock(spec=DatasetService)
        self.repository = Mock(spec=DatasetRepository)
        self.audit = Mock(spec=DatasetAccessAudit)
        self.service = MembersAccessService(
            dataset_service=self.datasets,
            repository=self.repository,
            access_service=DatasetAccessService(
                permission_repository=Mock(), user_service=Mock()
            ),
            audit=self.audit,
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
            members_can_edit=True,
        )
        self.datasets.fetch_authorized.return_value = (
            self.dataset,
            ["t"],
            AccessLevel.OWNER,
        )
        for target in (
            "app.service.members_access.utcnow",
            "app.service.dataset_access.utcnow",
        ):
            patcher = patch(target, return_value=NOW)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _set(self, members_can_edit: bool):
        return self.service.set(
            dataset_id=self.dataset.id,
            user_id=self.user_id,
            tenancies=None,
            members_can_edit=members_can_edit,
        )

    def test_the_owner_makes_members_read_only_and_it_is_recorded(self):
        result = self._set(False)

        self.assertFalse(self.dataset.members_can_edit)
        self.repository.upsert.assert_called_once_with(dataset=self.dataset)
        self.audit.record.assert_called_once_with(
            dataset_id=self.dataset.id,
            event_type=AccessEventType.MEMBERS_ACCESS_CHANGED,
            changed_by=self.user_id,
            old_value={"members_can_edit": True},
            new_value={"members_can_edit": False},
        )
        self.assertFalse(result.members_can_edit)
        self.assertEqual(result.access.level, AccessLevel.OWNER)
        self.assertTrue(result.access.can_edit)

    def test_the_change_is_asked_of_the_access_rule_as_an_owner_action(self):
        self._set(False)

        self.assertEqual(
            self.datasets.fetch_authorized.call_args.kwargs["action"],
            DatasetAction.MANAGE_MEMBERS_ACCESS,
        )

    def test_setting_the_value_it_already_has_changes_and_records_nothing(self):
        result = self._set(True)

        self.repository.upsert.assert_not_called()
        self.audit.record.assert_not_called()
        self.assertTrue(result.members_can_edit)

    def test_it_can_be_changed_during_an_embargo(self):
        self.dataset.embargo_until = NOW + timedelta(days=30)

        result = self._set(False)

        self.assertFalse(result.members_can_edit)
        self.audit.record.assert_called_once()

    def test_a_caller_who_is_not_the_owner_is_refused_before_anything_changes(self):
        self.datasets.fetch_authorized.side_effect = ForbiddenException("forbidden")

        with self.assertRaises(ForbiddenException):
            self._set(False)

        self.assertTrue(self.dataset.members_can_edit)
        self.repository.upsert.assert_not_called()
        self.audit.record.assert_not_called()
