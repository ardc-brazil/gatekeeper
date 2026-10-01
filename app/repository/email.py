from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.model.dataset import PaginatedResult
from app.model.db.email import EmailEvent, EmailMessage
from app.model.email import (
    EmailEventRecord,
    EmailEventType,
    EmailQuery,
    EmailRecord,
    EmailStatus,
)

MAX_PAGE_SIZE = 100
STALE_DETAIL = "delivery uncertain: left in sending"


def _record(row: EmailMessage) -> EmailRecord:
    return EmailRecord(
        id=row.id,
        template=row.template,
        template_version=row.template_version,
        recipient=row.recipient,
        subject=row.subject,
        body_text=row.body_text,
        context=dict(row.context or {}),
        secret_fields=list(row.secret_fields or []),
        related_type=row.related_type,
        related_id=row.related_id,
        triggered_by=row.triggered_by,
        dedup_key=row.dedup_key,
        status=EmailStatus(row.status),
        attempts=row.attempts or 0,
        next_attempt_at=row.next_attempt_at,
        smtp_message_id=row.smtp_message_id,
        sent_at=row.sent_at,
        created_at=row.created_at,
    )


class EmailRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def add(
        self, message: EmailMessage, event: EmailEventType, detail: str | None = None
    ) -> EmailRecord | None:
        dedup_key = message.dedup_key
        with self._session_factory() as session:
            try:
                session.add(message)
                session.flush()
                session.add(
                    EmailEvent(message_id=message.id, event=event.value, detail=detail)
                )
                session.commit()
            except IntegrityError:
                session.rollback()
                if dedup_key is not None and self._dedup_exists(session, dedup_key):
                    return None
                raise
            session.refresh(message)
            return _record(message)

    def claim_due(self, now: datetime, limit: int) -> list[EmailRecord]:
        with self._session_factory() as session:
            rows = (
                session.query(EmailMessage)
                .filter(
                    EmailMessage.status == EmailStatus.PENDING.value,
                    EmailMessage.next_attempt_at <= now,
                )
                .order_by(EmailMessage.next_attempt_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
                .all()
            )
            for row in rows:
                row.status = EmailStatus.SENDING.value
                row.claimed_at = now
            claimed = [_record(row) for row in rows]
            session.commit()
            return claimed

    def claim_stale_sending(self, claimed_before: datetime) -> list[EmailRecord]:
        with self._session_factory() as session:
            rows = (
                session.query(EmailMessage)
                .filter(
                    EmailMessage.status == EmailStatus.SENDING.value,
                    EmailMessage.claimed_at < claimed_before,
                )
                .with_for_update(skip_locked=True)
                .all()
            )
            for row in rows:
                row.status = EmailStatus.FAILED.value
                session.add(
                    EmailEvent(
                        message_id=row.id,
                        event=EmailEventType.FAILED.value,
                        detail=STALE_DETAIL,
                    )
                )
            stale = [_record(row) for row in rows]
            session.commit()
            return stale

    def mark_sent(
        self,
        message_id: UUID,
        smtp_message_id: str,
        sent_at: datetime,
        context: dict,
        body_text: str,
    ) -> bool:
        return self._apply(
            message_id,
            {
                "status": EmailStatus.SENT.value,
                "smtp_message_id": smtp_message_id,
                "sent_at": sent_at,
                "context": context,
                "body_text": body_text,
            },
            EmailEventType.SENT,
            None,
        )

    def mark_retry(
        self, message_id: UUID, attempts: int, next_attempt_at: datetime, detail: str
    ) -> bool:
        return self._apply(
            message_id,
            {
                "status": EmailStatus.PENDING.value,
                "attempts": attempts,
                "next_attempt_at": next_attempt_at,
                "claimed_at": None,
            },
            EmailEventType.ATTEMPT_FAILED,
            detail,
        )

    def mark_failed(
        self,
        message_id: UUID,
        attempts: int,
        detail: str,
        context: dict,
        body_text: str,
    ) -> bool:
        return self._apply(
            message_id,
            {
                "status": EmailStatus.FAILED.value,
                "attempts": attempts,
                "context": context,
                "body_text": body_text,
            },
            EmailEventType.FAILED,
            detail,
        )

    def mask(self, message_id: UUID, context: dict, body_text: str) -> None:
        with self._session_factory() as session:
            session.query(EmailMessage).filter(EmailMessage.id == message_id).update(
                {"context": context, "body_text": body_text},
                synchronize_session=False,
            )
            session.commit()

    def count_pending(self) -> int:
        with self._session_factory() as session:
            return (
                session.query(func.count(EmailMessage.id))
                .filter(EmailMessage.status == EmailStatus.PENDING.value)
                .scalar()
                or 0
            )

    def search(self, query: EmailQuery) -> PaginatedResult:
        with self._session_factory() as session:
            rows = session.query(EmailMessage)
            if query.recipient:
                rows = rows.filter(
                    func.lower(EmailMessage.recipient) == query.recipient.lower()
                )
            if query.related_id:
                rows = rows.filter(EmailMessage.related_id == query.related_id)
            if query.template:
                rows = rows.filter(EmailMessage.template == query.template)
            if query.status:
                rows = rows.filter(EmailMessage.status == query.status.value)
            rows = rows.order_by(EmailMessage.created_at.desc())

            total_count = rows.count()
            page = max(1, query.page)
            page_size = max(1, min(MAX_PAGE_SIZE, query.page_size))
            items = [
                _record(row)
                for row in rows.offset((page - 1) * page_size).limit(page_size).all()
            ]
            return PaginatedResult(
                items=items, total_count=total_count, page=page, page_size=page_size
            )

    def fetch(
        self, message_id: UUID
    ) -> tuple[EmailRecord, list[EmailEventRecord]] | None:
        with self._session_factory() as session:
            row = session.query(EmailMessage).filter_by(id=message_id).first()
            if row is None:
                return None
            events = (
                session.query(EmailEvent)
                .filter_by(message_id=message_id)
                .order_by(EmailEvent.occurred_at, EmailEvent.id)
                .all()
            )
            return _record(row), [
                EmailEventRecord(
                    id=event.id,
                    event=EmailEventType(event.event),
                    detail=event.detail,
                    occurred_at=event.occurred_at,
                )
                for event in events
            ]

    def _apply(
        self,
        message_id: UUID,
        values: dict,
        event: EmailEventType,
        detail: str | None,
    ) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(EmailMessage)
                .filter(
                    EmailMessage.id == message_id,
                    EmailMessage.status == EmailStatus.SENDING.value,
                )
                .update(values, synchronize_session=False)
            )
            if updated == 1:
                session.add(
                    EmailEvent(message_id=message_id, event=event.value, detail=detail)
                )
            session.commit()
            return updated == 1

    @staticmethod
    def _dedup_exists(session: Session, dedup_key: str) -> bool:
        return (
            session.query(EmailMessage.id).filter_by(dedup_key=dedup_key).first()
            is not None
        )
