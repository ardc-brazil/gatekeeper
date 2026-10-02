from contextlib import AbstractContextManager
from typing import Callable
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.model.db.dataset_access import DatasetPermission as DatasetPermissionDBModel


class PermissionRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def fetch(self, dataset_id: UUID, user_id: UUID) -> DatasetPermissionDBModel | None:
        with self._session_factory() as session:
            return (
                session.query(DatasetPermissionDBModel)
                .filter_by(dataset_id=dataset_id, user_id=user_id)
                .first()
            )

    def upsert(
        self, dataset_id: UUID, user_id: UUID, level: str, granted_by: UUID | None
    ) -> DatasetPermissionDBModel:
        statement = insert(DatasetPermissionDBModel).values(
            dataset_id=dataset_id, user_id=user_id, level=level, granted_by=granted_by
        )
        statement = statement.on_conflict_do_update(
            index_elements=["dataset_id", "user_id"],
            set_={
                "level": statement.excluded.level,
                "granted_by": statement.excluded.granted_by,
            },
        )
        with self._session_factory() as session:
            session.execute(statement)
            session.commit()
            return (
                session.query(DatasetPermissionDBModel)
                .filter_by(dataset_id=dataset_id, user_id=user_id)
                .one()
            )

    def delete(self, dataset_id: UUID, user_id: UUID) -> bool:
        with self._session_factory() as session:
            deleted = (
                session.query(DatasetPermissionDBModel)
                .filter_by(dataset_id=dataset_id, user_id=user_id)
                .delete()
            )
            session.commit()
            return deleted > 0

    def list_for_dataset(self, dataset_id: UUID) -> list[DatasetPermissionDBModel]:
        with self._session_factory() as session:
            return (
                session.query(DatasetPermissionDBModel)
                .filter_by(dataset_id=dataset_id)
                .order_by(DatasetPermissionDBModel.created_at.asc())
                .all()
            )
