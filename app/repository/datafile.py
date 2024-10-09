from uuid import UUID
from app.model.db.dataset import DataFile
from contextlib import AbstractContextManager
from sqlalchemy.orm import Session
from typing import Callable


class DataFileRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def fetch_by_id(self, id: UUID) -> DataFile:
        with self._session_factory() as session:
            return (
                session.query(DataFile)
                .filter(DataFile.id == id)
                .one_or_none()
            )
