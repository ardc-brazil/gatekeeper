from uuid import UUID
from app.model.db.dataset import DataFile, DatasetVersion
from contextlib import AbstractContextManager
from sqlalchemy.orm import Session
from typing import Callable, List


class DataFileRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def fetch_by_id(self, id: UUID) -> DataFile:
        with self._session_factory() as session:
            return session.query(DataFile).filter(DataFile.id == id).one_or_none()

    def fetch_by_dataset_id(self, dataset_id: UUID) -> List[DataFile]:
        """
        Fetch all files associated with a dataset across all its versions.
        Uses the many-to-many relationship table.
        """
        with self._session_factory() as session:
            # Query files through the dataset_versions_data_files association
            query = (
                session.query(DataFile)
                .join(DataFile.dataset_versions)
                .filter(DatasetVersion.dataset_id == dataset_id)
                .distinct()
            )
            return query.all()

    def upsert(self, file: DataFile) -> DataFile:
        """Insert or update a DataFile."""
        with self._session_factory() as session:
            session.add(file)
            session.commit()
            session.refresh(file)
            return file
