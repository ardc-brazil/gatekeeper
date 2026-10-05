from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exception.conflict import ConflictException
from app.exception.not_found import NotFoundException
from app.model.db.tenancy import Tenancy, TenancyRequest
from app.model.db.user import User
from app.model.tenancy import TenancyEventType, TenancyRequestStatus
from app.repository.integrity import violates
from app.repository.tenancy_event import add_event
from app.repository.tenancy_membership import insert_membership
from app.repository.user import user_matches

CLOSED = (TenancyRequestStatus.APPROVED, TenancyRequestStatus.DECLINED)


class TenancyRequestRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def create(self, user_id: UUID, requested_name: str, reason: str) -> TenancyRequest:
        try:
            with self._session_factory() as session:
                request = TenancyRequest(
                    id=uuid4(),
                    user_id=user_id,
                    requested_name=requested_name,
                    reason=reason,
                    status=TenancyRequestStatus.PENDING,
                    created_tenancy=False,
                )
                session.add(request)
                session.flush()
                add_event(
                    session,
                    tenancy=None,
                    event_type=TenancyEventType.REQUEST_CREATED,
                    user_id=user_id,
                    actor_id=user_id,
                    request_id=request.id,
                )
                session.commit()
                session.refresh(request)
                return request
        except IntegrityError as error:
            if violates(error, "uq_tenancy_requests_pending"):
                raise ConflictException("request_pending")
            raise

    def fetch(self, request_id: UUID) -> TenancyRequest | None:
        with self._session_factory() as session:
            return session.query(TenancyRequest).filter_by(id=request_id).first()

    def pending_for(self, user_id: UUID) -> TenancyRequest | None:
        with self._session_factory() as session:
            return (
                session.query(TenancyRequest)
                .filter_by(user_id=user_id, status=TenancyRequestStatus.PENDING)
                .first()
            )

    def count_since(self, user_id: UUID, since: datetime) -> int:
        with self._session_factory() as session:
            return (
                session.query(func.count(TenancyRequest.id))
                .filter(
                    TenancyRequest.user_id == user_id,
                    TenancyRequest.created_at >= since,
                )
                .scalar()
            )

    def latest_for(self, user_id: UUID, limit: int) -> list[TenancyRequest]:
        with self._session_factory() as session:
            return (
                session.query(TenancyRequest)
                .filter_by(user_id=user_id)
                .order_by(TenancyRequest.created_at.desc())
                .limit(limit)
                .all()
            )

    def withdraw(self, request_id: UUID, user_id: UUID) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(TenancyRequest)
                .filter(
                    TenancyRequest.id == request_id,
                    TenancyRequest.user_id == user_id,
                    TenancyRequest.status == TenancyRequestStatus.PENDING,
                )
                .update(
                    {TenancyRequest.status: TenancyRequestStatus.WITHDRAWN},
                    synchronize_session=False,
                )
            )
            if updated == 0:
                session.rollback()
                return False
            add_event(
                session,
                tenancy=None,
                event_type=TenancyEventType.REQUEST_WITHDRAWN,
                user_id=user_id,
                actor_id=user_id,
                request_id=request_id,
            )
            session.commit()
            return True

    def _queue(self, session: Session, term: str | None, statuses) -> object:
        query = (
            session.query(TenancyRequest)
            .join(User, User.id == TenancyRequest.user_id)
            .filter(TenancyRequest.status.in_(statuses))
        )
        if term:
            query = query.filter(user_matches(term))
        return query

    def list_pending(self, term: str | None) -> list[TenancyRequest]:
        with self._session_factory() as session:
            return (
                self._queue(session, term, [TenancyRequestStatus.PENDING])
                .order_by(TenancyRequest.created_at.asc(), TenancyRequest.id.asc())
                .all()
            )

    def list_closed(
        self, term: str | None, limit: int, offset: int
    ) -> tuple[list[TenancyRequest], int]:
        with self._session_factory() as session:
            query = self._queue(session, term, CLOSED)
            total = query.count()
            rows = (
                query.order_by(
                    TenancyRequest.decided_at.desc().nullslast(),
                    TenancyRequest.created_at.desc(),
                    TenancyRequest.id.desc(),
                )
                .limit(limit)
                .offset(offset)
                .all()
            )
            return rows, total

    def count_closed(self) -> int:
        with self._session_factory() as session:
            return (
                session.query(func.count(TenancyRequest.id))
                .filter(TenancyRequest.status.in_(CLOSED))
                .scalar()
            )

    def _locked_pending(self, session: Session, request_id: UUID) -> TenancyRequest:
        request = (
            session.query(TenancyRequest)
            .filter_by(id=request_id)
            .with_for_update()
            .first()
        )
        if request is None or request.status == TenancyRequestStatus.WITHDRAWN:
            raise NotFoundException("request_not_found")
        if request.status != TenancyRequestStatus.PENDING:
            raise ConflictException("request_not_pending")
        return request

    def approve(
        self,
        request_id: UUID,
        decided_by: UUID,
        tenancy: str,
        display_name: str | None,
        now: datetime,
    ) -> tuple[TenancyRequest, UUID]:
        try:
            with self._session_factory() as session:
                request = self._locked_pending(session, request_id)
                if display_name is not None:
                    session.add(
                        Tenancy(
                            name=tenancy, display_name=display_name, is_enabled=True
                        )
                    )
                    session.flush()
                    add_event(
                        session,
                        tenancy=tenancy,
                        event_type=TenancyEventType.TENANCY_CREATED,
                        actor_id=decided_by,
                        request_id=request.id,
                    )
                if not insert_membership(session, request.user_id, tenancy):
                    raise ConflictException("already_member")
                member_added = add_event(
                    session,
                    tenancy=tenancy,
                    event_type=TenancyEventType.MEMBER_ADDED,
                    user_id=request.user_id,
                    actor_id=decided_by,
                    request_id=request.id,
                )
                event_id = member_added.id
                request.status = TenancyRequestStatus.APPROVED
                request.tenancy = tenancy
                request.created_tenancy = display_name is not None
                request.decided_by = decided_by
                request.decided_at = now
                add_event(
                    session,
                    tenancy=tenancy,
                    event_type=TenancyEventType.REQUEST_APPROVED,
                    user_id=request.user_id,
                    actor_id=decided_by,
                    request_id=request.id,
                )
                session.commit()
                session.refresh(request)
                return request, event_id
        except IntegrityError as error:
            if violates(error, "tenancies_pkey"):
                raise ConflictException("tenancy_exists")
            raise

    def decline(
        self,
        request_id: UUID,
        decided_by: UUID,
        message: str | None,
        now: datetime,
    ) -> TenancyRequest:
        with self._session_factory() as session:
            request = self._locked_pending(session, request_id)
            request.status = TenancyRequestStatus.DECLINED
            request.decision_message = message
            request.decided_by = decided_by
            request.decided_at = now
            add_event(
                session,
                tenancy=None,
                event_type=TenancyEventType.REQUEST_DECLINED,
                user_id=request.user_id,
                actor_id=decided_by,
                request_id=request.id,
            )
            session.commit()
            session.refresh(request)
            return request
