from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.model.db.sharing import DatasetInvitation


class DatasetInvitationRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def create(self, invitation: DatasetInvitation) -> DatasetInvitation:
        with self._session_factory() as session:
            session.add(invitation)
            session.commit()
            session.refresh(invitation)
            return invitation

    def fetch(self, dataset_id: UUID, invitation_id: UUID) -> DatasetInvitation | None:
        with self._session_factory() as session:
            return (
                session.query(DatasetInvitation)
                .filter_by(id=invitation_id, dataset_id=dataset_id)
                .first()
            )

    def fetch_by_token_hash(self, token_hash: str) -> DatasetInvitation | None:
        with self._session_factory() as session:
            return (
                session.query(DatasetInvitation)
                .filter_by(token_hash=token_hash)
                .first()
            )

    def list_for_dataset(self, dataset_id: UUID) -> list[DatasetInvitation]:
        with self._session_factory() as session:
            return (
                session.query(DatasetInvitation)
                .filter_by(dataset_id=dataset_id)
                .order_by(DatasetInvitation.created_at.desc())
                .all()
            )

    def list_pending_for(
        self, email: str | None, orcid: str | None
    ) -> list[DatasetInvitation]:
        matches = []
        if email:
            matches.append(func.lower(DatasetInvitation.email) == email.lower())
        if orcid:
            matches.append(DatasetInvitation.orcid == orcid)
        if not matches:
            return []
        with self._session_factory() as session:
            return (
                session.query(DatasetInvitation)
                .filter(
                    DatasetInvitation.accepted_at.is_(None),
                    DatasetInvitation.revoked_at.is_(None),
                    or_(*matches),
                )
                .all()
            )

    def find_pending(
        self, dataset_id: UUID, email: str | None, orcid: str | None
    ) -> DatasetInvitation | None:
        return next(
            (
                invitation
                for invitation in self.list_pending_for(email, orcid)
                if invitation.dataset_id == dataset_id
            ),
            None,
        )

    def mark_accepted(self, invitation_id: UUID, user_id: UUID, at: datetime) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(DatasetInvitation)
                .filter(
                    DatasetInvitation.id == invitation_id,
                    DatasetInvitation.accepted_at.is_(None),
                    DatasetInvitation.revoked_at.is_(None),
                )
                .update(
                    {"accepted_at": at, "accepted_by": user_id},
                    synchronize_session=False,
                )
            )
            session.commit()
            return updated == 1

    def revoke(self, invitation_id: UUID, at: datetime) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(DatasetInvitation)
                .filter(
                    DatasetInvitation.id == invitation_id,
                    DatasetInvitation.revoked_at.is_(None),
                )
                .update({"revoked_at": at}, synchronize_session=False)
            )
            session.commit()
            return updated == 1

    def replace_token(self, invitation_id: UUID, token_hash: str) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(DatasetInvitation)
                .filter(
                    DatasetInvitation.id == invitation_id,
                    DatasetInvitation.accepted_at.is_(None),
                    DatasetInvitation.revoked_at.is_(None),
                )
                .update({"token_hash": token_hash}, synchronize_session=False)
            )
            session.commit()
            return updated == 1
