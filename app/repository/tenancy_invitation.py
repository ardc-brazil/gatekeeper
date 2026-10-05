from contextlib import AbstractContextManager
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exception.conflict import ConflictException
from app.model.db.dataset import Dataset
from app.model.db.tenancy import TenancyInvitation
from app.model.tenancy import TenancyEventType, TenancyInvitationStatus
from app.repository.integrity import violates
from app.repository.tenancy_event import add_event
from app.repository.tenancy_membership import insert_membership

PENDING = TenancyInvitationStatus.PENDING


class TenancyInvitationRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def create(
        self, tenancy: str, user_id: UUID, invited_by: UUID, dataset_id: UUID | None
    ) -> TenancyInvitation:
        try:
            with self._session_factory() as session:
                invitation = TenancyInvitation(
                    id=uuid4(),
                    tenancy=tenancy,
                    user_id=user_id,
                    invited_by=invited_by,
                    dataset_id=dataset_id,
                    status=PENDING,
                )
                session.add(invitation)
                session.flush()
                add_event(
                    session,
                    tenancy=tenancy,
                    event_type=TenancyEventType.INVITATION_CREATED,
                    user_id=user_id,
                    actor_id=invited_by,
                    invitation_id=invitation.id,
                )
                session.commit()
                session.refresh(invitation)
                return invitation
        except IntegrityError as error:
            if violates(error, "uq_tenancy_invitations_pending"):
                raise ConflictException("invitation_pending")
            raise

    def fetch(self, invitation_id: UUID) -> TenancyInvitation | None:
        with self._session_factory() as session:
            return session.query(TenancyInvitation).filter_by(id=invitation_id).first()

    def has_pending(self, tenancy: str, user_id: UUID) -> bool:
        with self._session_factory() as session:
            return (
                session.query(TenancyInvitation.id)
                .filter_by(tenancy=tenancy, user_id=user_id, status=PENDING)
                .first()
                is not None
            )

    def _pending(self, **filters) -> list[TenancyInvitation]:
        with self._session_factory() as session:
            return (
                session.query(TenancyInvitation)
                .filter_by(status=PENDING, **filters)
                .order_by(TenancyInvitation.created_at.desc())
                .all()
            )

    def pending_for_user(self, user_id: UUID) -> list[TenancyInvitation]:
        return self._pending(user_id=user_id)

    def pending_for_dataset(self, dataset_id: UUID) -> list[TenancyInvitation]:
        return self._pending(dataset_id=dataset_id)

    def pending_for_tenancy(self, tenancy: str) -> list[TenancyInvitation]:
        return self._pending(tenancy=tenancy)

    def dataset_names(self, dataset_ids: list[UUID | None]) -> dict[UUID, str]:
        ids = [dataset_id for dataset_id in dataset_ids if dataset_id is not None]
        if not ids:
            return {}
        with self._session_factory() as session:
            rows = (
                session.query(Dataset.id, Dataset.name)
                .filter(Dataset.id.in_(ids))
                .all()
            )
            return {dataset_id: name for dataset_id, name in rows}

    def close(
        self,
        invitation_id: UUID,
        status: TenancyInvitationStatus,
        closed_by: UUID,
        event_type: TenancyEventType,
    ) -> bool:
        with self._session_factory() as session:
            invitation = (
                session.query(TenancyInvitation)
                .filter_by(id=invitation_id, status=PENDING)
                .with_for_update()
                .first()
            )
            if invitation is None:
                return False
            invitation.status = status
            invitation.closed_by = closed_by
            invitation.closed_at = func.now()
            add_event(
                session,
                tenancy=invitation.tenancy,
                event_type=event_type,
                user_id=invitation.user_id,
                actor_id=closed_by,
                invitation_id=invitation.id,
            )
            session.commit()
            return True

    def accept(self, invitation_id: UUID, user_id: UUID) -> bool:
        with self._session_factory() as session:
            invitation = (
                session.query(TenancyInvitation)
                .filter_by(id=invitation_id, user_id=user_id, status=PENDING)
                .with_for_update()
                .first()
            )
            if invitation is None:
                return False
            invitation.status = TenancyInvitationStatus.ACCEPTED
            invitation.closed_by = user_id
            invitation.closed_at = func.now()
            add_event(
                session,
                tenancy=invitation.tenancy,
                event_type=TenancyEventType.INVITATION_ACCEPTED,
                user_id=user_id,
                actor_id=user_id,
                invitation_id=invitation.id,
            )
            if insert_membership(session, user_id, invitation.tenancy):
                add_event(
                    session,
                    tenancy=invitation.tenancy,
                    event_type=TenancyEventType.MEMBER_ADDED,
                    user_id=user_id,
                    actor_id=user_id,
                    invitation_id=invitation.id,
                )
            session.commit()
            return True
