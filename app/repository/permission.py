from contextlib import AbstractContextManager
from typing import Callable
from uuid import UUID

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
        with self._session_factory() as session:
            permission = (
                session.query(DatasetPermissionDBModel)
                .filter_by(dataset_id=dataset_id, user_id=user_id)
                .first()
            )
            if permission is None:
                permission = DatasetPermissionDBModel(
                    dataset_id=dataset_id,
                    user_id=user_id,
                    level=level,
                    granted_by=granted_by,
                )
                session.add(permission)
            else:
                permission.level = level
                permission.granted_by = granted_by
            session.commit()
            session.refresh(permission)
            return permission

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
