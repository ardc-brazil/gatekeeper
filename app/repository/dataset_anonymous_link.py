from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.model.db.sharing import DatasetAnonymousLink, DatasetAnonymousLinkView


class DatasetAnonymousLinkRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def create(self, link: DatasetAnonymousLink) -> DatasetAnonymousLink:
        with self._session_factory() as session:
            session.add(link)
            session.commit()
            session.refresh(link)
            return link

    def fetch(self, dataset_id: UUID, link_id: UUID) -> DatasetAnonymousLink | None:
        with self._session_factory() as session:
            return (
                session.query(DatasetAnonymousLink)
                .filter_by(id=link_id, dataset_id=dataset_id)
                .first()
            )

    def fetch_by_token_hash(self, token_hash: str) -> DatasetAnonymousLink | None:
        with self._session_factory() as session:
            return (
                session.query(DatasetAnonymousLink)
                .filter_by(token_hash=token_hash)
                .first()
            )

    def list_with_views(
        self, dataset_id: UUID
    ) -> list[tuple[DatasetAnonymousLink, int, datetime | None, datetime | None]]:
        with self._session_factory() as session:
            rows = (
                session.query(
                    DatasetAnonymousLink,
                    func.count(DatasetAnonymousLinkView.id),
                    func.min(DatasetAnonymousLinkView.viewed_at),
                    func.max(DatasetAnonymousLinkView.viewed_at),
                )
                .outerjoin(
                    DatasetAnonymousLinkView,
                    DatasetAnonymousLinkView.link_id == DatasetAnonymousLink.id,
                )
                .filter(DatasetAnonymousLink.dataset_id == dataset_id)
                .group_by(DatasetAnonymousLink.id)
                .order_by(DatasetAnonymousLink.created_at.desc())
                .all()
            )
            return [(link, count, first, last) for link, count, first, last in rows]

    def count_active(self, dataset_id: UUID) -> int:
        with self._session_factory() as session:
            return (
                session.query(func.count(DatasetAnonymousLink.id))
                .filter(
                    DatasetAnonymousLink.dataset_id == dataset_id,
                    DatasetAnonymousLink.revoked_at.is_(None),
                )
                .scalar()
            )

    def revoke(self, link_id: UUID, at: datetime) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(DatasetAnonymousLink)
                .filter(
                    DatasetAnonymousLink.id == link_id,
                    DatasetAnonymousLink.revoked_at.is_(None),
                )
                .update({"revoked_at": at}, synchronize_session=False)
            )
            session.commit()
            return updated == 1

    def record_view(self, link_id: UUID, outcome: str) -> None:
        with self._session_factory() as session:
            session.add(DatasetAnonymousLinkView(link_id=link_id, outcome=outcome))
            session.commit()
