from contextlib import AbstractContextManager
from sqlalchemy.orm import Session
from typing import Callable
from sqlalchemy.exc import IntegrityError

from app.exception.conflict import ConflictException
from app.model.db.doi import DOI


class DOIRepository:
    def __init__(self, session_factory: Callable[..., AbstractContextManager[Session]]):
        self._session_factory = session_factory

    def fetch(self, identifier: str) -> DOI:
        with self._session_factory() as session:
            return session.query(DOI).filter(DOI.identifier == identifier).one_or_none()

    def fetch_all(self) -> list[DOI]:
        with self._session_factory() as session:
            return session.query(DOI).all()

    def upsert(self, doi: DOI) -> DOI:
        try:
            with self._session_factory() as session:
                session.add(doi)
                session.commit()
                session.refresh(doi)
                return doi
        except IntegrityError:
            raise ConflictException(f"doi_already_exists: {doi.identifier}")
    
    def delete(self, identifier: DOI) -> None:
        with self._session_factory() as session:
            session.delete(identifier)
            session.commit()
