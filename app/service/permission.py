from uuid import UUID

from app.model.db.dataset_access import DatasetPermission as DatasetPermissionDBModel
from app.model.dataset_access import (
    SHARED_ROLE,
    AccessEventType,
    DatasetPermission,
    PermissionLevel,
)
from app.repository.permission import PermissionRepository
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.user import UserService


def _adapt(permission: DatasetPermissionDBModel) -> DatasetPermission:
    return DatasetPermission(
        dataset_id=permission.dataset_id,
        user_id=permission.user_id,
        level=PermissionLevel(permission.level),
        granted_by=permission.granted_by,
        created_at=permission.created_at,
    )


class PermissionService:
    def __init__(
        self,
        permission_repository: PermissionRepository,
        user_service: UserService,
        audit: DatasetAccessAudit,
    ) -> None:
        self._permissions = permission_repository
        self._user_service = user_service
        self._audit = audit

    def grant(
        self,
        dataset_id: UUID,
        user_id: UUID,
        level: PermissionLevel,
        granted_by: UUID | None,
    ) -> DatasetPermission:
        user = self._user_service.fetch_by_id(id=user_id)
        previous = self._permissions.fetch(dataset_id=dataset_id, user_id=user_id)
        saved = self._permissions.upsert(
            dataset_id=dataset_id,
            user_id=user_id,
            level=level.value,
            granted_by=granted_by,
        )
        if SHARED_ROLE not in (user.roles or []):
            self._user_service.add_roles(id=user_id, roles=[SHARED_ROLE])
        self._audit.record(
            dataset_id=dataset_id,
            event_type=AccessEventType.PERMISSION_GRANTED,
            changed_by=granted_by,
            old_value={"user_id": str(user_id), "level": previous.level}
            if previous is not None
            else None,
            new_value={"user_id": str(user_id), "level": level.value},
        )
        return _adapt(saved)

    def revoke(self, dataset_id: UUID, user_id: UUID, revoked_by: UUID | None) -> bool:
        previous = self._permissions.fetch(dataset_id=dataset_id, user_id=user_id)
        if previous is None:
            return False
        self._permissions.delete(dataset_id=dataset_id, user_id=user_id)
        self._audit.record(
            dataset_id=dataset_id,
            event_type=AccessEventType.PERMISSION_REVOKED,
            changed_by=revoked_by,
            old_value={"user_id": str(user_id), "level": previous.level},
        )
        return True

    def list_for_dataset(self, dataset_id: UUID) -> list[DatasetPermission]:
        return [
            _adapt(permission)
            for permission in self._permissions.list_for_dataset(dataset_id=dataset_id)
        ]
