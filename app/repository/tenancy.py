from contextlib import AbstractContextManager
from typing import Callable, List
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session
from sqlalchemy.sql.expression import true

from app.exception.conflict import ConflictException
from app.model.db.dataset import Dataset
from app.model.db.tenancy import Tenancy
from app.model.db.user import User, user_tenancy_association
from app.model.tenancy import TenancyEventType
from app.repository.integrity import raise_conflict, violates
from app.repository.tenancy_event import add_event


DISPLAY_NAME_INDEX = "uq_tenancies_display_name"
NEW_TENANCY_CONFLICTS = {
    "tenancies_pkey": "tenancy_exists",
    DISPLAY_NAME_INDEX: "display_name_taken",
}


def _counted_datasets(session: Session, *columns) -> Query:
    return session.query(*columns, func.count(Dataset.id)).filter(
        Dataset.is_enabled == true()
    )


def datasets_in(session: Session, tenancy: str) -> Query:
    return _counted_datasets(session).filter(Dataset.tenancy == tenancy)


class TenancyRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def fetch(self, tenancy: str, is_enabled: bool = True) -> Tenancy:
        with self._session_factory() as session:
            return (
                session.query(Tenancy)
                .filter_by(name=tenancy, is_enabled=is_enabled)
                .first()
            )

    def fetch_all(self, is_enabled: bool = None) -> List[Tenancy]:
        with self._session_factory() as session:
            if is_enabled:
                return session.query(Tenancy).filter_by(is_enabled=is_enabled).all()
            return session.query(Tenancy).all()

    def upsert(self, tenancy: Tenancy) -> Tenancy:
        # Read before the session: after a failed commit the instance is expired.
        name = tenancy.name
        try:
            with self._session_factory() as session:
                session.add(tenancy)
                session.commit()
                session.refresh(tenancy)
                return tenancy
        except IntegrityError as error:
            if violates(error, DISPLAY_NAME_INDEX):
                raise ConflictException(
                    NEW_TENANCY_CONFLICTS[DISPLAY_NAME_INDEX]
                ) from error
            raise ConflictException(f"tenancy_already_exists: {name}") from error

    def fetch_any(self, tenancy: str) -> Tenancy | None:
        with self._session_factory() as session:
            return session.query(Tenancy).filter_by(name=tenancy).first()

    def list_all(self) -> List[Tenancy]:
        with self._session_factory() as session:
            return session.query(Tenancy).all()

    def create_with_event(
        self, name: str, display_name: str, actor_id: UUID
    ) -> Tenancy:
        try:
            with self._session_factory() as session:
                tenancy = Tenancy(name=name, display_name=display_name, is_enabled=True)
                session.add(tenancy)
                session.flush()
                add_event(
                    session,
                    tenancy=name,
                    event_type=TenancyEventType.TENANCY_CREATED,
                    actor_id=actor_id,
                )
                session.commit()
                session.refresh(tenancy)
                return tenancy
        except IntegrityError as error:
            raise_conflict(error, NEW_TENANCY_CONFLICTS)
            raise

    def member_counts(self) -> dict[str, int]:
        with self._session_factory() as session:
            rows = (
                session.query(user_tenancy_association.c.tenancy, func.count(User.id))
                .select_from(user_tenancy_association)
                .join(User, User.id == user_tenancy_association.c.user_id)
                .filter(User.is_enabled == true())
                .group_by(user_tenancy_association.c.tenancy)
                .all()
            )
            return {tenancy: count for tenancy, count in rows}

    def dataset_counts(self) -> dict[str, int]:
        with self._session_factory() as session:
            rows = (
                _counted_datasets(session, Dataset.tenancy)
                .filter(Dataset.tenancy.isnot(None))
                .group_by(Dataset.tenancy)
                .all()
            )
            return {tenancy: count for tenancy, count in rows}

    def count_datasets(self, tenancy: str) -> int:
        with self._session_factory() as session:
            return datasets_in(session, tenancy).scalar()
