from contextlib import AbstractContextManager
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.model.db.tenancy import TenancyEvent, TenancyInvitation
from app.model.tenancy import TenancyEventType, TenancyInvitationStatus


def add_event(
    session: Session,
    tenancy: str | None,
    event_type: TenancyEventType,
    user_id: UUID | None = None,
    actor_id: UUID | None = None,
    request_id: UUID | None = None,
    invitation_id: UUID | None = None,
) -> TenancyEvent:
    event = TenancyEvent(
        id=uuid4(),
        tenancy=tenancy,
        event_type=event_type,
        user_id=user_id,
        actor_id=actor_id,
        request_id=request_id,
        invitation_id=invitation_id,
    )
    session.add(event)
    return event


def close_invitation(
    session: Session,
    invitation: TenancyInvitation,
    status: TenancyInvitationStatus,
    actor_id: UUID,
    event_type: TenancyEventType,
) -> None:
    invitation.status = status
    invitation.closed_by = actor_id
    invitation.closed_at = func.now()
    add_event(
        session,
        tenancy=invitation.tenancy,
        event_type=event_type,
        user_id=invitation.user_id,
        actor_id=actor_id,
        invitation_id=invitation.id,
    )


class TenancyEventRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def append(
        self,
        tenancy: str | None,
        event_type: TenancyEventType,
        user_id: UUID | None = None,
        actor_id: UUID | None = None,
        request_id: UUID | None = None,
        invitation_id: UUID | None = None,
    ) -> UUID:
        with self._session_factory() as session:
            event = add_event(
                session,
                tenancy=tenancy,
                event_type=event_type,
                user_id=user_id,
                actor_id=actor_id,
                request_id=request_id,
                invitation_id=invitation_id,
            )
            event_id = event.id
            session.commit()
            return event_id
