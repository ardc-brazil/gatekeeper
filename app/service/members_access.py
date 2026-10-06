from uuid import UUID

from app.exception.illegal_state import IllegalStateException
from app.model.dataset_access import (
    AccessEventType,
    DatasetAction,
    MembersAccess,
    utcnow,
)
from app.model.tenancy import DEFAULT_TENANCY
from app.repository.dataset import DatasetRepository
from app.service.dataset import DatasetService
from app.service.dataset_access import DatasetAccessService, allows_member_edits
from app.service.dataset_access_audit import DatasetAccessAudit


class MembersAccessService:
    def __init__(
        self,
        dataset_service: DatasetService,
        repository: DatasetRepository,
        access_service: DatasetAccessService,
        audit: DatasetAccessAudit,
    ) -> None:
        self._datasets = dataset_service
        self._repository = repository
        self._access = access_service
        self._audit = audit

    def set(
        self,
        dataset_id: UUID,
        user_id: UUID,
        tenancies: list[str] | None,
        members_can_edit: bool,
    ) -> MembersAccess:
        dataset, allowed, level = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.MANAGE_MEMBERS_ACCESS,
        )
        if members_can_edit and dataset.tenancy == DEFAULT_TENANCY:
            raise IllegalStateException("public_members_cannot_edit")
        before = allows_member_edits(dataset)
        if before != members_can_edit:
            dataset.members_can_edit = members_can_edit
            self._repository.upsert(dataset=dataset)
            self._audit.record(
                dataset_id=dataset.id,
                event_type=AccessEventType.MEMBERS_ACCESS_CHANGED,
                changed_by=user_id,
                old_value={"members_can_edit": before},
                new_value={"members_can_edit": members_can_edit},
            )
        return MembersAccess(
            members_can_edit=allows_member_edits(dataset),
            access=self._access.access_flags(
                user_id=user_id,
                dataset=dataset,
                tenancies=allowed,
                level=level,
                now=utcnow(),
            ),
        )
