from datetime import datetime
from uuid import UUID

from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.dataset_access import AccessEventType
from app.repository.dataset import DatasetRepository
from app.service.dataset_access_audit import DatasetAccessAudit


def embargo_state(dataset: DatasetDBModel) -> dict:
    return {
        "until": dataset.embargo_until.isoformat() if dataset.embargo_until else None,
        "metadata_visible": bool(dataset.embargo_metadata_visible),
    }


class EmbargoTermination:
    def __init__(
        self, repository: DatasetRepository, audit: DatasetAccessAudit
    ) -> None:
        self._repository = repository
        self._audit = audit

    def end(
        self,
        dataset: DatasetDBModel,
        ended_by: UUID | None,
        now: datetime,
        note: str | None = None,
    ) -> None:
        before = embargo_state(dataset)
        dataset.embargo_until = now
        self._repository.upsert(dataset=dataset)
        self._audit.record(
            dataset_id=dataset.id,
            event_type=AccessEventType.ENDED_EARLY,
            changed_by=ended_by,
            old_value=before,
            new_value=embargo_state(dataset),
            note=note,
        )
