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
from app.service.dataset_access import DatasetAccessService, allows_member_edits
from app.service.user import UserService

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
TENANCY = "datamap/production/data-amazon"


def _dataset(
    owner_id=None, until=None, visible=False, tenancy=TENANCY, members_can_edit=True
):
    return DatasetDBModel(
        id=uuid4(),
        name="d",
        data={},
        owner_id=owner_id,
        tenancy=tenancy,
        embargo_until=until,
        embargo_metadata_visible=visible,
        embargo_note=None,
        members_can_edit=members_can_edit,
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

    def test_a_tenancy_member_whose_role_refuses_get_has_no_level(self):
        self.users.enforce.return_value = False
        self.assertIsNone(
            self.access.level_of(self.user_id, _dataset(), [TENANCY], NOW)
        )
        self.users.enforce.assert_called_with(
            user_id=self.user_id,
            resource="/api/v1/datasets/tenancy-scope",
            action="GET",
        )

    def test_a_tenancy_member_whose_role_allows_get_is_tenancy(self):
        self.users.enforce.side_effect = lambda user_id, resource, action: (
            action == "GET"
        )
        self.assertEqual(
            self.access.level_of(self.user_id, _dataset(), [TENANCY], NOW),
            AccessLevel.TENANCY,
        )

    def test_the_owner_needs_no_role(self):
        self.users.enforce.return_value = False
        dataset = _dataset(owner_id=self.user_id)
        self.assertEqual(
            self.access.level_of(self.user_id, dataset, [TENANCY], NOW),
            AccessLevel.OWNER,
        )

    def test_a_permission_holder_needs_no_role(self):
        self.users.enforce.return_value = False
        self._grant("write")
        self.assertEqual(
            self.access.level_of(self.user_id, _dataset(), [TENANCY], NOW),
            AccessLevel.WRITE,
        )

    def test_reads_the_tenancy_follows_the_get_role(self):
        self.users.enforce.return_value = False
        self.assertFalse(self.access.reads_tenancy(self.user_id))
        self.users.enforce.return_value = True
        self.assertTrue(self.access.reads_tenancy(self.user_id))

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


class TestMembersAccess(unittest.TestCase):
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

    def _permits(self, dataset, action, tenancies=(TENANCY,)):
        return self.access.permits(self.user_id, dataset, list(tenancies), action, NOW)

    def test_read_only_members_still_read_and_download(self):
        dataset = _dataset(owner_id=uuid4(), members_can_edit=False)

        self.assertTrue(self._permits(dataset, DatasetAction.READ_METADATA))
        self.assertTrue(self._permits(dataset, DatasetAction.READ_FILES))

    def test_read_only_members_neither_write_nor_delete_whatever_their_role(self):
        dataset = _dataset(owner_id=uuid4(), members_can_edit=False)

        self.assertFalse(self._permits(dataset, DatasetAction.WRITE))
        self.assertFalse(self._permits(dataset, DatasetAction.DELETE))
        asked = [call.kwargs["action"] for call in self.users.enforce.call_args_list]
        self.assertNotIn("PUT", asked)
        self.assertNotIn("DELETE", asked)

    def test_by_default_members_write_and_delete_as_their_role_allows(self):
        dataset = _dataset(owner_id=uuid4())

        self.assertTrue(self._permits(dataset, DatasetAction.WRITE))
        self.assertTrue(self._permits(dataset, DatasetAction.DELETE))

    def test_a_read_permission_does_not_borrow_the_roles_write_in_read_only_mode(self):
        self._grant("read")
        dataset = _dataset(owner_id=uuid4())
        self.assertTrue(self._permits(dataset, DatasetAction.WRITE))

        dataset.members_can_edit = False

        self.assertFalse(self._permits(dataset, DatasetAction.WRITE))
        self.assertTrue(self._permits(dataset, DatasetAction.READ_FILES))

    def test_a_write_permission_still_writes_in_read_only_mode(self):
        self._grant("write")
        dataset = _dataset(owner_id=uuid4(), members_can_edit=False)

        self.assertTrue(self._permits(dataset, DatasetAction.WRITE, tenancies=()))
        self.assertTrue(self._permits(dataset, DatasetAction.WRITE))
        self.assertFalse(self._permits(dataset, DatasetAction.DELETE))

    def test_the_owner_keeps_everything_in_read_only_mode(self):
        dataset = _dataset(owner_id=self.user_id, members_can_edit=False)

        flags = self.access.access_flags(
            self.user_id, dataset, [TENANCY], AccessLevel.OWNER, NOW
        )

        self.assertTrue(flags.can_edit)
        self.assertTrue(flags.can_share)
        self.assertTrue(flags.can_delete)

    def test_the_flags_of_a_read_only_member(self):
        dataset = _dataset(owner_id=uuid4(), members_can_edit=False)

        flags = self.access.access_flags(
            self.user_id, dataset, [TENANCY], AccessLevel.TENANCY, NOW
        )

        self.assertEqual(flags.level, AccessLevel.TENANCY)
        self.assertFalse(flags.can_edit)
        self.assertFalse(flags.can_share)
        self.assertFalse(flags.can_delete)
        self.assertFalse(flags.can_manage_embargo)

    def test_the_setting_is_inert_during_an_embargo(self):
        for members_can_edit in (True, False):
            with self.subTest(members_can_edit=members_can_edit):
                dataset = _dataset(
                    owner_id=uuid4(),
                    until=NOW + timedelta(days=5),
                    visible=True,
                    members_can_edit=members_can_edit,
                )

                self.assertTrue(self._permits(dataset, DatasetAction.READ_METADATA))
                self.assertFalse(self._permits(dataset, DatasetAction.READ_FILES))
                self.assertFalse(self._permits(dataset, DatasetAction.WRITE))

    def test_the_setting_decides_what_members_get_back_when_the_embargo_ends(self):
        ended = NOW - timedelta(seconds=1)
        read_only = _dataset(owner_id=uuid4(), until=ended, members_can_edit=False)
        editable = _dataset(owner_id=uuid4(), until=ended, members_can_edit=True)

        self.assertTrue(self._permits(read_only, DatasetAction.READ_FILES))
        self.assertFalse(self._permits(read_only, DatasetAction.WRITE))
        self.assertTrue(self._permits(editable, DatasetAction.WRITE))

    def test_a_row_not_yet_flushed_reads_as_the_default(self):
        dataset = _dataset(owner_id=uuid4())
        dataset.members_can_edit = None

        self.assertTrue(allows_member_edits(dataset))
        self.assertTrue(self._permits(dataset, DatasetAction.WRITE))
        self.assertFalse(allows_member_edits(_dataset(members_can_edit=False)))

    def test_only_the_owner_changes_what_members_can_do(self):
        dataset = _dataset(owner_id=self.user_id)
        self.assertTrue(self._permits(dataset, DatasetAction.MANAGE_MEMBERS_ACCESS))

        self._grant("write")
        others = _dataset(owner_id=uuid4())

        self.assertFalse(self._permits(others, DatasetAction.MANAGE_MEMBERS_ACCESS))
        self.users.enforce.assert_not_called()
