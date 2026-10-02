from datetime import datetime
from uuid import UUID

from app.exception.forbidden import ForbiddenException
from app.exception.not_found import NotFoundException
from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.dataset_access import AccessLevel, DatasetAccess, DatasetAction, utcnow
from app.model.embargo import Embargo, embargo_active
from app.repository.permission import PermissionRepository
from app.service.user import UserService

# Matched by the tenancy roles' policies and not by datasets_shared's, which name concrete ids.
TENANCY_ROLE_RESOURCE = "/api/v1/datasets/tenancy-scope"

_ROLE_METHOD = {
    DatasetAction.READ_METADATA: "GET",
    DatasetAction.READ_FILES: "GET",
    DatasetAction.WRITE: "PUT",
    DatasetAction.DELETE: "DELETE",
}

_PERMISSION_ACTIONS = {
    AccessLevel.WRITE: frozenset(
        {DatasetAction.READ_METADATA, DatasetAction.READ_FILES, DatasetAction.WRITE}
    ),
    AccessLevel.READ: frozenset(
        {DatasetAction.READ_METADATA, DatasetAction.READ_FILES}
    ),
}


def allows_member_edits(dataset: DatasetDBModel) -> bool:
    # None is a row not flushed yet, whose column default is true; `not None` would read it as read-only.
    return dataset.members_can_edit is not False


class DatasetAccessService:
    def __init__(
        self, permission_repository: PermissionRepository, user_service: UserService
    ) -> None:
        self._permissions = permission_repository
        self._user_service = user_service

    def embargo_active(
        self, dataset: DatasetDBModel, now: datetime | None = None
    ) -> bool:
        return embargo_active(dataset.embargo_until, now or utcnow())

    def embargo_of(
        self, dataset: DatasetDBModel, now: datetime | None = None
    ) -> Embargo | None:
        if dataset.embargo_until is None:
            return None
        return Embargo(
            until=dataset.embargo_until,
            active=self.embargo_active(dataset, now),
            metadata_visible=bool(dataset.embargo_metadata_visible),
            note=dataset.embargo_note,
        )

    def level_of(
        self,
        user_id: UUID | None,
        dataset: DatasetDBModel,
        tenancies: list[str],
        now: datetime | None = None,
    ) -> AccessLevel | None:
        if user_id is not None and dataset.owner_id == user_id:
            return AccessLevel.OWNER
        if user_id is not None:
            permission = self._permissions.fetch(dataset_id=dataset.id, user_id=user_id)
            if permission is not None:
                return AccessLevel(permission.level)
        if (
            user_id is not None
            and dataset.tenancy in tenancies
            and (
                not self.embargo_active(dataset, now)
                or dataset.embargo_metadata_visible
            )
            and self.reads_tenancy(user_id)
        ):
            return AccessLevel.TENANCY
        return None

    def reads_tenancy(self, user_id: UUID) -> bool:
        return self._role_allows(user_id, "GET")

    def permits(
        self,
        user_id: UUID,
        dataset: DatasetDBModel,
        tenancies: list[str],
        action: DatasetAction,
        now: datetime | None = None,
    ) -> bool:
        now = now or utcnow()
        level = self.level_of(user_id, dataset, tenancies, now)
        return self._permits(user_id, dataset, tenancies, level, action, now)

    def require(
        self,
        user_id: UUID,
        dataset: DatasetDBModel,
        tenancies: list[str],
        action: DatasetAction,
        now: datetime | None = None,
    ) -> AccessLevel:
        now = now or utcnow()
        level = self.level_of(user_id, dataset, tenancies, now)
        if level is None:
            raise NotFoundException(f"not_found: {dataset.id}")
        if not self._permits(user_id, dataset, tenancies, level, action, now):
            raise ForbiddenException(
                f"forbidden: {action.value} on {dataset.id} for {user_id}"
            )
        return level

    def access_flags(
        self,
        user_id: UUID,
        dataset: DatasetDBModel,
        tenancies: list[str],
        level: AccessLevel,
        now: datetime | None = None,
    ) -> DatasetAccess:
        now = now or utcnow()

        def can(action: DatasetAction) -> bool:
            return self._permits(user_id, dataset, tenancies, level, action, now)

        can_edit = can(DatasetAction.WRITE)
        return DatasetAccess(
            level=level,
            can_edit=can_edit,
            can_share=can_edit,
            can_manage_embargo=level == AccessLevel.OWNER,
            can_extend_embargo=self.embargo_active(dataset, now)
            and can(DatasetAction.EXTEND_EMBARGO),
            can_delete=can(DatasetAction.DELETE),
        )

    def owner_disabled(self, dataset: DatasetDBModel) -> bool:
        if dataset.owner_id is None:
            return True
        try:
            self._user_service.fetch_by_id(id=dataset.owner_id)
        except NotFoundException:
            return True
        return False

    def _permits(
        self,
        user_id: UUID,
        dataset: DatasetDBModel,
        tenancies: list[str],
        level: AccessLevel | None,
        action: DatasetAction,
        now: datetime,
    ) -> bool:
        if level is None:
            return False
        if level == AccessLevel.OWNER:
            return True
        if action == DatasetAction.MANAGE_EMBARGO:
            return False
        active = self.embargo_active(dataset, now)
        if action == DatasetAction.EXTEND_EMBARGO:
            return (
                active and level in _PERMISSION_ACTIONS and self.owner_disabled(dataset)
            )
        if action in _PERMISSION_ACTIONS.get(level, frozenset()):
            return True
        if dataset.tenancy not in tenancies:
            return False
        if active:
            return (
                action == DatasetAction.READ_METADATA
                and bool(dataset.embargo_metadata_visible)
                and self._role_allows(user_id, "GET")
            )
        if action in (
            DatasetAction.WRITE,
            DatasetAction.DELETE,
        ) and not allows_member_edits(dataset):
            return False
        return self._role_allows(user_id, _ROLE_METHOD[action])

    def _role_allows(self, user_id: UUID, method: str) -> bool:
        return self._user_service.enforce(
            user_id=user_id, resource=TENANCY_ROLE_RESOURCE, action=method
        )
