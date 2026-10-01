import unittest
from unittest.mock import Mock
from uuid import uuid4

from app.exception.not_found import NotFoundException
from app.model.db.dataset_access import DatasetPermission as DatasetPermissionDBModel
from app.model.dataset_access import AccessEventType, PermissionLevel
from app.model.user import User
from app.repository.permission import PermissionRepository
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.permission import PermissionService
from app.service.user import UserService


class TestPermissionService(unittest.TestCase):
    def setUp(self):
        self.permissions = Mock(spec=PermissionRepository)
        self.users = Mock(spec=UserService)
        self.audit = Mock(spec=DatasetAccessAudit)
        self.service = PermissionService(
            permission_repository=self.permissions,
            user_service=self.users,
            audit=self.audit,
        )
        self.dataset_id, self.user_id, self.by = uuid4(), uuid4(), uuid4()
        self.permissions.fetch.return_value = None
        self.permissions.upsert.return_value = DatasetPermissionDBModel(
            dataset_id=self.dataset_id, user_id=self.user_id, level="read"
        )

    def test_granting_gives_the_shared_role_once(self):
        self.users.fetch_by_id.return_value = User(id=self.user_id, roles=[])

        permission = self.service.grant(
            self.dataset_id, self.user_id, PermissionLevel.READ, self.by
        )

        self.assertEqual(permission.level, PermissionLevel.READ)
        self.users.add_roles.assert_called_once_with(
            id=self.user_id, roles=["datasets_shared"]
        )
        self.audit.record.assert_called_once_with(
            dataset_id=self.dataset_id,
            event_type=AccessEventType.PERMISSION_GRANTED,
            changed_by=self.by,
            old_value=None,
            new_value={"user_id": str(self.user_id), "level": "read"},
        )

    def test_a_user_who_has_the_role_is_not_given_it_again(self):
        self.users.fetch_by_id.return_value = User(
            id=self.user_id, roles=["datasets_shared"]
        )

        self.service.grant(self.dataset_id, self.user_id, PermissionLevel.READ, self.by)

        self.users.add_roles.assert_not_called()

    def test_granting_to_a_missing_user_fails_before_writing(self):
        self.users.fetch_by_id.side_effect = NotFoundException("missing")

        with self.assertRaises(NotFoundException):
            self.service.grant(
                self.dataset_id, self.user_id, PermissionLevel.READ, self.by
            )

        self.permissions.upsert.assert_not_called()

    def test_revoking_a_permission_records_it(self):
        self.permissions.fetch.return_value = DatasetPermissionDBModel(
            dataset_id=self.dataset_id, user_id=self.user_id, level="write"
        )

        self.assertTrue(self.service.revoke(self.dataset_id, self.user_id, self.by))

        self.permissions.delete.assert_called_once_with(
            dataset_id=self.dataset_id, user_id=self.user_id
        )
        self.audit.record.assert_called_once_with(
            dataset_id=self.dataset_id,
            event_type=AccessEventType.PERMISSION_REVOKED,
            changed_by=self.by,
            old_value={"user_id": str(self.user_id), "level": "write"},
        )

    def test_revoking_nothing_is_not_an_event(self):
        self.assertFalse(self.service.revoke(self.dataset_id, self.user_id, self.by))
        self.audit.record.assert_not_called()
