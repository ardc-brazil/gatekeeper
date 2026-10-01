from uuid import UUID

from app.metrics import metrics
from app.model.dataset_access import AccessEventType
from app.repository.access_event import AccessEventRepository


class DatasetAccessAudit:
    def __init__(self, event_repository: AccessEventRepository) -> None:
        self._events = event_repository

    def record(
        self,
        dataset_id: UUID,
        event_type: AccessEventType,
        changed_by: UUID | None,
        old_value: dict | None = None,
        new_value: dict | None = None,
        note: str | None = None,
    ) -> None:
        self._events.append(
            dataset_id=dataset_id,
            event_type=event_type.value,
            changed_by=changed_by,
            old_value=old_value,
            new_value=new_value,
            note=note,
        )
        metrics.dataset_access_event(event_type.value)
