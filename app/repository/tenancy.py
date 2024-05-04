from exception.ConflictException import ConflictException
from sqlalchemy.exc import IntegrityError
from app.model.db.tenancy import Tenancy
from contextlib import AbstractContextManager
from sqlalchemy.orm import Session
from typing import Callable, List


class TenancyRepository:
    def __init__(self, session_factory: Callable[..., AbstractContextManager[Session]]) -> None:
        self._session_factory = session_factory

    def fetch(self, tenancy: str, is_enabled: bool = True) -> Tenancy:
        with self._session_factory() as session:
            return session.query(Tenancy).filter_by(name=tenancy, is_enabled=is_enabled).first()

    def fetch_all(self, is_enabled: bool = None) -> List[Tenancy]:
        with self._session_factory() as session:
            if is_enabled:
                return session.query(Tenancy).filter_by(is_enabled=is_enabled).all()
            return session.query(Tenancy).all()

    def upsert(self, tenancy: Tenancy) -> Tenancy:
        try:
            with self._session_factory() as session:
                session.add(tenancy)
                session.commit()
                session.refresh(tenancy)
                return tenancy
        except IntegrityError:
            raise ConflictException(f"tenancy_already_exists: {tenancy.name}")
