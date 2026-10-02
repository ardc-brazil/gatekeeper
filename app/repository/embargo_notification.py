from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from typing import Callable
from uuid import UUID

from sqlalchemy import and_, exists
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import true

from app.model.db.dataset import Dataset
from app.model.db.dataset_access import DatasetAccessEvent


class EmbargoNotificationRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def datasets_with_reminders_due(
        self, now: datetime, horizon: timedelta
    ) -> list[Dataset]:
        with self._session_factory() as session:
            return (
                session.query(Dataset)
                .filter(
                    Dataset.is_enabled == true(),
                    Dataset.embargo_until.isnot(None),
                    Dataset.embargo_until > now,
                    Dataset.embargo_until <= now + horizon,
                )
                .all()
            )

    def datasets_expired_unannounced(self, now: datetime) -> list[Dataset]:
        announced = exists().where(
            and_(
                DatasetAccessEvent.dataset_id == Dataset.id,
                DatasetAccessEvent.event_type == "expired",
                DatasetAccessEvent.occurred_at >= Dataset.embargo_until,
            )
        )
        with self._session_factory() as session:
            return (
                session.query(Dataset)
                .filter(
                    Dataset.is_enabled == true(),
                    Dataset.embargo_until.isnot(None),
                    Dataset.embargo_until <= now,
                    ~announced,
                )
                .all()
            )

    def ending_event(self, dataset_id: UUID) -> DatasetAccessEvent | None:
        with self._session_factory() as session:
            event = (
                session.query(DatasetAccessEvent)
                .filter(
                    DatasetAccessEvent.dataset_id == dataset_id,
                    DatasetAccessEvent.event_type.in_(
                        ("created", "extended", "ended_early")
                    ),
                )
                .order_by(DatasetAccessEvent.occurred_at.desc())
                .first()
            )
            if event is None or event.event_type != "ended_early":
                return None
            return event

    def embargo_set_at(self, dataset_id: UUID, until: datetime) -> datetime | None:
        with self._session_factory() as session:
            event = (
                session.query(DatasetAccessEvent)
                .filter(
                    DatasetAccessEvent.dataset_id == dataset_id,
                    DatasetAccessEvent.event_type.in_(("created", "extended")),
                )
                .order_by(DatasetAccessEvent.occurred_at.desc())
                .first()
            )
            return event.occurred_at if event is not None else None
