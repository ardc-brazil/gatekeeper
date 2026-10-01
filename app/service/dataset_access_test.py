import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import app.model.db.doi  # noqa: F401  # registers DOI before Dataset's mapper resolves its "DOI" relationship
from app.exception.forbidden import ForbiddenException
from app.exception.not_found import NotFoundException
from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.db.dataset_access import DatasetPermission as DatasetPermissionDBModel
from app.model.dataset_access import AccessLevel, DatasetAction
from app.repository.permission import PermissionRepository
from app.service.dataset_access import DatasetAccessService
from app.service.user import UserService

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
TENANCY = "datamap/production/data-amazon"


def _dataset(owner_id=None, until=None, visible=False, tenancy=TENANCY):
    return DatasetDBModel(
        id=uuid4(),
        name="d",
        data={},
        owner_id=owner_id,
        tenancy=tenancy,
        embargo_until=until,
        embargo_metadata_visible=visible,
        embargo_note=None,
    )


class TestDatasetAccessService(unittest.TestCase):
    def setUp(self):
        self.permissions = Mock(spec=PermissionRepository)
        self.permissions.fetch.return_value = None
        self.users = Mock(spec=UserService)
        self.users.enforce.return_value = True
        self.access = DatasetAccessService(
            permission_repository=self.permissions, user_service=self.users
        )
        self.user_id = uuid4()

    def _grant(self, level: str):
        self.permissions.fetch.return_value = DatasetPermissionDBModel(
            dataset_id=uuid4(), user_id=self.user_id, level=level
        )

    def test_the_owner_is_owner_whatever_the_embargo(self):
        dataset = _dataset(owner_id=self.user_id, until=NOW + timedelta(days=5))
        self.assertEqual(
            self.access.level_of(self.user_id, dataset, [], NOW), AccessLevel.OWNER
        )

    def test_a_permission_counts_without_the_tenancy(self):
        self._grant("read")
        dataset = _dataset(until=NOW + timedelta(days=5))
        self.assertEqual(
            self.access.level_of(self.user_id, dataset, [], NOW), AccessLevel.READ
        )

    def test_a_tenancy_member_sees_a_dataset_without_embargo(self):
        dataset = _dataset()
        self.assertEqual(
            self.access.level_of(self.user_id, dataset, [TENANCY], NOW),
            AccessLevel.TENANCY,
        )

    def test_a_tenancy_member_does_not_see_a_hidden_embargo(self):
        dataset = _dataset(until=NOW + timedelta(days=5), visible=False)
        self.assertIsNone(self.access.level_of(self.user_id, dataset, [TENANCY], NOW))

    def test_a_tenancy_member_sees_an_open_embargo_but_not_its_files(self):
        dataset = _dataset(until=NOW + timedelta(days=5), visible=True)
        self.assertTrue(
            self.access.permits(
                self.user_id, dataset, [TENANCY], DatasetAction.READ_METADATA, NOW
            )
        )
        self.assertFalse(
            self.access.permits(
                self.user_id, dataset, [TENANCY], DatasetAction.READ_FILES, NOW
            )
        )
        self.assertFalse(
            self.access.permits(
                self.user_id, dataset, [TENANCY], DatasetAction.WRITE, NOW
            )
        )

    def test_an_expired_embargo_gives_the_tenancy_back_its_access(self):
        dataset = _dataset(until=NOW - timedelta(seconds=1))
        self.assertTrue(
            self.access.permits(
                self.user_id, dataset, [TENANCY], DatasetAction.READ_FILES, NOW
            )
        )

    def test_tenancy_writes_still_follow_the_role(self):
        dataset = _dataset()
        self.users.enforce.side_effect = lambda user_id, resource, action: (
            action == "GET"
        )
        self.assertTrue(
            self.access.permits(
                self.user_id, dataset, [TENANCY], DatasetAction.READ_FILES, NOW
            )
        )
        self.assertFalse(
            self.access.permits(
                self.user_id, dataset, [TENANCY], DatasetAction.WRITE, NOW
            )
        )
        self.users.enforce.assert_any_call(
            user_id=self.user_id,
            resource="/api/v1/datasets/tenancy-scope",
            action="PUT",
        )

    def test_a_read_permission_cannot_write(self):
        self._grant("read")
        dataset = _dataset(until=NOW + timedelta(days=5))
        self.assertTrue(
            self.access.permits(
                self.user_id, dataset, [], DatasetAction.READ_FILES, NOW
            )
        )
        self.assertFalse(
            self.access.permits(self.user_id, dataset, [], DatasetAction.WRITE, NOW)
        )

    def test_a_write_permission_can_write_but_not_delete(self):
        self._grant("write")
        dataset = _dataset(until=NOW + timedelta(days=5))
        self.assertTrue(
            self.access.permits(self.user_id, dataset, [], DatasetAction.WRITE, NOW)
        )
        self.assertFalse(
            self.access.permits(self.user_id, dataset, [], DatasetAction.DELETE, NOW)
        )

    def test_only_the_owner_manages_the_embargo(self):
        self._grant("write")
        dataset = _dataset(owner_id=uuid4(), until=NOW + timedelta(days=5))
        self.assertFalse(
            self.access.permits(
                self.user_id, dataset, [], DatasetAction.MANAGE_EMBARGO, NOW
            )
        )

    def test_a_permission_holder_extends_only_when_the_owner_is_disabled(self):
        self._grant("read")
        dataset = _dataset(owner_id=uuid4(), until=NOW + timedelta(days=5))
        self.assertFalse(
            self.access.permits(
                self.user_id, dataset, [], DatasetAction.EXTEND_EMBARGO, NOW
            )
        )
        self.users.fetch_by_id.side_effect = NotFoundException("disabled")
        self.assertTrue(
            self.access.permits(
                self.user_id, dataset, [], DatasetAction.EXTEND_EMBARGO, NOW
            )
        )

    def test_require_hides_what_the_caller_cannot_see(self):
        dataset = _dataset(until=NOW + timedelta(days=5), visible=False)
        with self.assertRaises(NotFoundException):
            self.access.require(
                self.user_id, dataset, [TENANCY], DatasetAction.WRITE, NOW
            )

    def test_require_forbids_what_the_caller_can_see_but_not_do(self):
        dataset = _dataset(until=NOW + timedelta(days=5), visible=True)
        with self.assertRaises(ForbiddenException):
            self.access.require(
                self.user_id, dataset, [TENANCY], DatasetAction.WRITE, NOW
            )

    def test_flags_for_the_owner(self):
        dataset = _dataset(owner_id=self.user_id, until=NOW + timedelta(days=5))
        flags = self.access.access_flags(
            self.user_id, dataset, [], AccessLevel.OWNER, NOW
        )
        self.assertEqual(flags.level, AccessLevel.OWNER)
        self.assertTrue(flags.can_edit)
        self.assertTrue(flags.can_share)
        self.assertTrue(flags.can_manage_embargo)
        self.assertTrue(flags.can_extend_embargo)
        self.assertTrue(flags.can_delete)

    def test_nobody_can_extend_an_embargo_that_is_not_active(self):
        dataset = _dataset(owner_id=self.user_id)
        flags = self.access.access_flags(
            self.user_id, dataset, [], AccessLevel.OWNER, NOW
        )
        self.assertFalse(flags.can_extend_embargo)

    def test_embargo_of_a_dataset_without_one_is_none(self):
        self.assertIsNone(self.access.embargo_of(_dataset(), NOW))

    def test_embargo_of_reports_the_state(self):
        until = NOW + timedelta(days=5)
        embargo = self.access.embargo_of(_dataset(until=until, visible=True), NOW)
        self.assertEqual(embargo.until, until)
        self.assertTrue(embargo.active)
        self.assertTrue(embargo.metadata_visible)

    def test_a_dataset_with_no_owner_counts_as_owner_disabled(self):
        self.assertTrue(self.access.owner_disabled(_dataset(owner_id=None)))

    def test_during_an_embargo_a_tenancy_role_cannot_delete(self):
        dataset = _dataset(
            owner_id=uuid4(), until=NOW + timedelta(days=5), visible=True
        )
        flags = self.access.access_flags(
            self.user_id, dataset, [TENANCY], AccessLevel.TENANCY, NOW
        )
        self.assertFalse(flags.can_delete)
        self.assertFalse(flags.can_edit)

    def test_without_an_embargo_a_tenancy_role_deletes_only_with_delete(self):
        dataset = _dataset(owner_id=uuid4())
        self.users.enforce.side_effect = lambda user_id, resource, action: (
            action != "DELETE"
        )
        self.assertFalse(
            self.access.permits(
                self.user_id, dataset, [TENANCY], DatasetAction.DELETE, NOW
            )
        )
        self.users.enforce.side_effect = None
        self.assertTrue(
            self.access.permits(
                self.user_id, dataset, [TENANCY], DatasetAction.DELETE, NOW
            )
        )

    def test_flags_for_a_permission_holder_when_the_owner_is_disabled(self):
        self._grant("write")
        self.users.fetch_by_id.side_effect = NotFoundException("disabled")
        dataset = _dataset(owner_id=uuid4(), until=NOW + timedelta(days=5))
        flags = self.access.access_flags(
            self.user_id, dataset, [], AccessLevel.WRITE, NOW
        )
        self.assertTrue(flags.can_edit)
        self.assertTrue(flags.can_extend_embargo)
        self.assertFalse(flags.can_manage_embargo)
        self.assertFalse(flags.can_delete)
