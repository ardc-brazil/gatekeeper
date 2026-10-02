from contextlib import AbstractContextManager
from typing import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.model.db.dataset_access import DatasetAccessEvent


class AccessEventRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def append(
        self,
        dataset_id: UUID,
        event_type: str,
        changed_by: UUID | None,
        old_value: dict | None,
        new_value: dict | None,
        note: str | None,
    ) -> None:
        with self._session_factory() as session:
            session.add(
                DatasetAccessEvent(
                    dataset_id=dataset_id,
                    event_type=event_type,
                    changed_by=changed_by,
                    old_value=old_value,
                    new_value=new_value,
                    note=note,
                )
            )
            session.commit()

    def list_for_dataset(
        self, dataset_id: UUID, limit: int | None = None
    ) -> list[DatasetAccessEvent]:
        with self._session_factory() as session:
            query = (
                session.query(DatasetAccessEvent)
                .filter_by(dataset_id=dataset_id)
                .order_by(
                    DatasetAccessEvent.occurred_at.desc(),
                    DatasetAccessEvent.id.desc(),
                )
            )
            if limit is not None:
                query = query.limit(limit)
            return query.all()
