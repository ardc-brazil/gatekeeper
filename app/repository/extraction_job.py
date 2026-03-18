from uuid import UUID
from contextlib import AbstractContextManager
from sqlalchemy.orm import Session
from typing import Callable

from app.model.db.extraction_job import ExtractionJob as ExtractionJobDB
from app.model.extraction_job import ExtractionStatus


class ExtractionJobRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def create(self, data_file_id: UUID) -> ExtractionJobDB:
        """Create a new extraction job for a data file."""
        with self._session_factory() as session:
            job = ExtractionJobDB(
                data_file_id=data_file_id,
                status=ExtractionStatus.PENDING,
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

    def fetch_by_data_file_id(self, data_file_id: UUID) -> ExtractionJobDB | None:
        """Fetch extraction job by data file ID."""
        with self._session_factory() as session:
            return (
                session.query(ExtractionJobDB)
                .filter(ExtractionJobDB.data_file_id == data_file_id)
                .first()
            )
