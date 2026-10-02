from datetime import datetime, timezone
from uuid import UUID

from app.exception.bad_request import BadRequestException, ErrorDetails
from app.exception.forbidden import ForbiddenException
from app.model.dataset import VisibilityStatus
from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.doi import Mode as DOIMode
from app.model.dataset_access import AccessEventType, DatasetAction, utcnow
from app.model.embargo import MAX_EMBARGO_PERIOD, Embargo
from app.repository.dataset import DatasetRepository
from app.service.dataset import DatasetService
from app.service.dataset_access import DatasetAccessService
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.embargo_termination import EmbargoTermination, embargo_state


def _bad(code: str) -> BadRequestException:
    return BadRequestException(errors=[ErrorDetails(code=code)])


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _has_manual_doi(dataset: DatasetDBModel) -> bool:
    return any(
        version.doi is not None and version.doi.mode == DOIMode.MANUAL.name
        for version in dataset.versions
    )


def _validate_until(until: datetime, now: datetime) -> None:
    if until <= now:
        raise _bad("embargo_until_in_past")
    if until > now + MAX_EMBARGO_PERIOD:
        raise _bad("embargo_too_long")


class EmbargoService:
    def __init__(
        self,
        dataset_service: DatasetService,
        repository: DatasetRepository,
        access_service: DatasetAccessService,
        audit: DatasetAccessAudit,
        termination: EmbargoTermination,
    ) -> None:
        self._datasets = dataset_service
        self._repository = repository
        self._access = access_service
        self._audit = audit
        self._termination = termination

    def set_embargo(
        self,
        dataset_id: UUID,
        user_id: UUID,
        tenancies: list[str] | None,
        until: datetime,
        metadata_visible: bool,
        note: str | None,
    ) -> Embargo:
        dataset, _, _ = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.MANAGE_EMBARGO,
        )
        now = utcnow()
        until = _aware(until)
        if self._access.embargo_active(dataset, now):
            raise _bad("embargo_already_active")
        if _has_manual_doi(dataset):
            raise _bad("embargo_manual_doi")
        if dataset.visibility == VisibilityStatus.PUBLIC:
            raise _bad("embargo_dataset_published")
        _validate_until(until, now)

        before = embargo_state(dataset)
        dataset.embargo_until = until
        dataset.embargo_metadata_visible = metadata_visible
        dataset.embargo_note = note
        self._repository.upsert(dataset=dataset)
        self._audit.record(
            dataset_id=dataset.id,
            event_type=AccessEventType.CREATED,
            changed_by=user_id,
            old_value=before,
            new_value=embargo_state(dataset),
            note=note,
        )
        return self._access.embargo_of(dataset, now)

    def extend(
        self,
        dataset_id: UUID,
        user_id: UUID,
        tenancies: list[str] | None,
        until: datetime,
        reason: str | None = None,
    ) -> Embargo:
        dataset, allowed, _ = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.READ_METADATA,
        )
        now = utcnow()
        until = _aware(until)
        if not self._access.embargo_active(dataset, now):
            raise _bad("embargo_not_active")
        if not self._access.permits(
            user_id=user_id,
            dataset=dataset,
            tenancies=allowed,
            action=DatasetAction.EXTEND_EMBARGO,
            now=now,
        ):
            raise ForbiddenException(f"forbidden: extend {dataset.id} for {user_id}")
        if until <= dataset.embargo_until:
            raise _bad("embargo_until_not_later")
        _validate_until(until, now)

        before = embargo_state(dataset)
        dataset.embargo_until = until
        self._repository.upsert(dataset=dataset)
        self._audit.record(
            dataset_id=dataset.id,
            event_type=AccessEventType.EXTENDED,
            changed_by=user_id,
            old_value=before,
            new_value=embargo_state(dataset),
            note=reason,
        )
        return self._access.embargo_of(dataset, now)

    def end(
        self, dataset_id: UUID, user_id: UUID, tenancies: list[str] | None
    ) -> Embargo:
        dataset, _, _ = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.MANAGE_EMBARGO,
        )
        now = utcnow()
        if not self._access.embargo_active(dataset, now):
            raise _bad("embargo_not_active")

        self._termination.end(dataset=dataset, ended_by=user_id, now=now)
        return self._access.embargo_of(dataset, now)

    def set_mode(
        self,
        dataset_id: UUID,
        user_id: UUID,
        tenancies: list[str] | None,
        metadata_visible: bool,
    ) -> Embargo:
        dataset, _, _ = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.MANAGE_EMBARGO,
        )
        now = utcnow()
        if not self._access.embargo_active(dataset, now):
            raise _bad("embargo_not_active")

        if bool(dataset.embargo_metadata_visible) != metadata_visible:
            before = embargo_state(dataset)
            dataset.embargo_metadata_visible = metadata_visible
            self._repository.upsert(dataset=dataset)
            self._audit.record(
                dataset_id=dataset.id,
                event_type=AccessEventType.METADATA_MODE_CHANGED,
                changed_by=user_id,
                old_value=before,
                new_value=embargo_state(dataset),
            )
        return self._access.embargo_of(dataset, now)

    def set_note(
        self,
        dataset_id: UUID,
        user_id: UUID,
        tenancies: list[str] | None,
        note: str | None,
    ) -> Embargo:
        dataset, _, _ = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.MANAGE_EMBARGO,
        )
        now = utcnow()
        if not self._access.embargo_active(dataset, now):
            raise _bad("embargo_not_active")
        note = (note or "").strip() or None
        if dataset.embargo_note != note:
            before = dataset.embargo_note
            dataset.embargo_note = note
            self._repository.upsert(dataset=dataset)
            self._audit.record(
                dataset_id=dataset.id,
                event_type=AccessEventType.NOTE_CHANGED,
                changed_by=user_id,
                old_value={"note": before},
                new_value={"note": note},
            )
        return self._access.embargo_of(dataset, now)

    def _fetch_for_status(self, dataset_id: UUID) -> DatasetDBModel | None:
        return self._repository.fetch(
            dataset_id=dataset_id, version_is_enabled=False, restrict_by_tenancy=False
        )

    def _doi_in(self, dataset: DatasetDBModel, version_name: str) -> str | None:
        for version in dataset.versions:
            if version.name == version_name and version.doi is not None:
                return version.doi.identifier
        return None

    def status(self, dataset_id: UUID) -> tuple[bool, datetime | None]:
        dataset = self._fetch_for_status(dataset_id)
        if dataset is None or not self._access.embargo_active(dataset):
            return False, None
        return True, dataset.embargo_until

    def status_with_doi(
        self, dataset_id: UUID, version_name: str | None
    ) -> tuple[bool, datetime | None, str | None]:
        dataset = self._fetch_for_status(dataset_id)
        if dataset is None or not self._access.embargo_active(dataset):
            return False, None, None
        doi = self._doi_in(dataset, version_name) if version_name else None
        return True, dataset.embargo_until, doi
