from contextlib import AbstractContextManager
from typing import Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.model.db.dataset import DataFile, Dataset
from app.model.db.doi import DOI
from app.model.db.user import User


def label(value) -> str:
    """Prometheus label values must be strings; an enum's value may not be."""
    if value is None:
        return "none"
    return str(getattr(value, "name", value))


class PlatformStateRepository:
    """Counts across the whole platform, for the metrics. Tenancy is not applied."""

    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def datasets(self) -> list[tuple[str, str, str, int]]:
        with self._session_factory() as session:
            rows = (
                session.query(
                    Dataset.tenancy,
                    Dataset.design_state,
                    Dataset.visibility,
                    func.count(Dataset.id),
                )
                .filter(Dataset.is_enabled.is_(True))
                .group_by(Dataset.tenancy, Dataset.design_state, Dataset.visibility)
                .all()
            )
        return [
            (label(tenancy), label(state), label(visibility), count)
            for tenancy, state, visibility, count in rows
        ]

    def files(self) -> tuple[int, int]:
        with self._session_factory() as session:
            count, size = session.query(
                func.count(DataFile.id), func.coalesce(func.sum(DataFile.size_bytes), 0)
            ).one()
        return int(count), int(size)

    def users(self) -> list[tuple[bool, int]]:
        with self._session_factory() as session:
            return [
                (bool(enabled), count)
                for enabled, count in session.query(
                    User.is_enabled, func.count(User.id)
                )
                .group_by(User.is_enabled)
                .all()
            ]

    def dois(self) -> list[tuple[str, int]]:
        with self._session_factory() as session:
            return [
                (label(state), count)
                for state, count in session.query(DOI.state, func.count(DOI.id))
                .group_by(DOI.state)
                .all()
            ]
