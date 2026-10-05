from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import true

from app.exception.conflict import ConflictException
from app.model.db.dataset import Dataset
from app.model.db.dataset_access import DatasetPermission
from app.model.db.tenancy import Tenancy, TenancyEvent, TenancyInvitation
from app.model.db.user import User, user_tenancy_association
from app.model.tenancy import TenancyEventType, TenancyInvitationStatus, is_default
from app.repository.tenancy import datasets_in
from app.repository.tenancy_event import add_event
from app.repository.user import enabled_members

_member = user_tenancy_association.c


def insert_membership(session: Session, user_id: UUID, tenancy: str) -> bool:
    result = session.execute(
        pg_insert(user_tenancy_association)
        .values(user_id=user_id, tenancy=tenancy)
        .on_conflict_do_nothing()
    )
    return result.rowcount == 1


class TenancyMembershipRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def is_member(self, user_id: UUID, tenancy: str) -> bool:
        with self._session_factory() as session:
            return (
                session.query(_member.user_id)
                .filter(_member.user_id == user_id, _member.tenancy == tenancy)
                .first()
                is not None
            )

    def tenancies_of(self, user_id: UUID) -> list[Tenancy]:
        with self._session_factory() as session:
            return (
                session.query(Tenancy)
                .join(user_tenancy_association, _member.tenancy == Tenancy.name)
                .filter(_member.user_id == user_id, Tenancy.is_enabled == true())
                .all()
            )

    def list_members(
        self, tenancy: str, limit: int, offset: int
    ) -> tuple[list[User], int]:
        with self._session_factory() as session:
            query = enabled_members(session, tenancy)
            total = query.count()
            users = (
                query.order_by(func.lower(User.name), User.id)
                .limit(limit)
                .offset(offset)
                .all()
            )
            return users, total

    def added_at(self, tenancy: str, user_ids: list[UUID]) -> dict[UUID, datetime]:
        if not user_ids:
            return {}
        with self._session_factory() as session:
            rows = (
                session.query(TenancyEvent.user_id, func.max(TenancyEvent.created_at))
                .filter(
                    TenancyEvent.tenancy == tenancy,
                    TenancyEvent.event_type == TenancyEventType.MEMBER_ADDED,
                    TenancyEvent.user_id.in_(user_ids),
                )
                .group_by(TenancyEvent.user_id)
                .all()
            )
            return {user_id: at for user_id, at in rows}

    def inviters(self, tenancy: str, user_ids: list[UUID]) -> dict[UUID, UUID]:
        if not user_ids:
            return {}
        with self._session_factory() as session:
            rows = (
                session.query(TenancyInvitation.user_id, TenancyInvitation.invited_by)
                .filter(
                    TenancyInvitation.tenancy == tenancy,
                    TenancyInvitation.status == TenancyInvitationStatus.ACCEPTED,
                    TenancyInvitation.user_id.in_(user_ids),
                )
                .order_by(TenancyInvitation.closed_at.asc())
                .all()
            )
            return {
                user_id: invited_by
                for user_id, invited_by in rows
                if invited_by is not None
            }

    def removal_counts(self, tenancy: str, user_id: UUID) -> tuple[int, int, int]:
        with self._session_factory() as session:
            in_tenancy = datasets_in(session, tenancy)
            shared = (
                session.query(func.count(DatasetPermission.dataset_id))
                .join(Dataset, Dataset.id == DatasetPermission.dataset_id)
                .filter(
                    Dataset.tenancy == tenancy,
                    Dataset.is_enabled == true(),
                    DatasetPermission.user_id == user_id,
                )
            )
            owned = in_tenancy.filter(Dataset.owner_id == user_id)
            return in_tenancy.scalar(), shared.scalar(), owned.scalar()

    def add(self, tenancy: str, user_id: UUID, actor_id: UUID) -> UUID | None:
        with self._session_factory() as session:
            if not insert_membership(session, user_id, tenancy):
                return None
            event = add_event(
                session,
                tenancy=tenancy,
                event_type=TenancyEventType.MEMBER_ADDED,
                user_id=user_id,
                actor_id=actor_id,
            )
            event_id = event.id
            session.commit()
            return event_id

    def remove(self, tenancy: str, user_id: UUID, actor_id: UUID) -> bool:
        if is_default(tenancy):
            raise ConflictException("public_tenancy_locked")
        with self._session_factory() as session:
            deleted = session.execute(
                user_tenancy_association.delete().where(
                    _member.user_id == user_id, _member.tenancy == tenancy
                )
            ).rowcount
            if deleted == 0:
                session.rollback()
                return False
            session.query(TenancyInvitation).filter(
                TenancyInvitation.tenancy == tenancy,
                TenancyInvitation.user_id == user_id,
                TenancyInvitation.status == TenancyInvitationStatus.ACCEPTED,
            ).update(
                {
                    TenancyInvitation.status: TenancyInvitationStatus.REVOKED,
                    TenancyInvitation.closed_by: actor_id,
                    TenancyInvitation.closed_at: func.now(),
                },
                synchronize_session=False,
            )
            add_event(
                session,
                tenancy=tenancy,
                event_type=TenancyEventType.MEMBER_REMOVED,
                user_id=user_id,
                actor_id=actor_id,
            )
            session.commit()
            return True
