from uuid import UUID
from app.model.dataset import DesignState
from app.model.db.dataset import DatasetVersion
from sqlalchemy import desc
from contextlib import AbstractContextManager
from sqlalchemy.orm import Session
from typing import Callable
from app.exception.conflict import ConflictException
from sqlalchemy.exc import IntegrityError


class DatasetVersionRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def fetch_draft_version(self, dataset_id) -> DatasetVersion:
        with self._session_factory() as session:
            return (
                session.query(DatasetVersion)
                .filter_by(dataset_id=dataset_id, design_state=DesignState.DRAFT)
                .order_by(desc(DatasetVersion.created_at))
                .first()
            )

    def upsert(self, dataset_version: DatasetVersion) -> DatasetVersion:
        try:
            with self._session_factory() as session:
                session.add(dataset_version)
                session.commit()
                session.refresh(dataset_version)
                return dataset_version
        except IntegrityError:
            raise ConflictException(
                f"dataset_version_already_exists: {dataset_version.id}"
            )

    def fetch_version_by_name(self, dataset_id, version_name) -> DatasetVersion:
        with self._session_factory() as session:
            return (
                session.query(DatasetVersion)
                .filter_by(dataset_id=dataset_id, name=version_name)
                .first()
            )
    
    def fetch_by_id(self, id: UUID) -> DatasetVersion:
        with self._session_factory() as session:
            return session.query(DatasetVersion).filter(DatasetVersion.id == id).one_or_none()
