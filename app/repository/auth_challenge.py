from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable
from uuid import UUID

from sqlalchemy import case, update
from sqlalchemy.orm import Session

from app.model.auth_challenge import ChallengeKind
from app.model.db.auth_challenge import AuthChallenge


class AuthChallengeRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def replace(self, challenge: AuthChallenge) -> None:
        with self._session_factory() as session:
            session.query(AuthChallenge).filter(
                AuthChallenge.kind == challenge.kind,
                AuthChallenge.email == challenge.email,
                AuthChallenge.consumed_at.is_(None),
            ).update(
                {AuthChallenge.consumed_at: challenge.issued_at},
                synchronize_session=False,
            )
            session.add(challenge)
            session.commit()

    def fetch(self, challenge_id: UUID) -> AuthChallenge | None:
        with self._session_factory() as session:
            return session.query(AuthChallenge).filter_by(id=challenge_id).first()

    def fetch_open_by_secret(
        self, secret_hash: str, kind: ChallengeKind
    ) -> AuthChallenge | None:
        with self._session_factory() as session:
            return (
                session.query(AuthChallenge)
                .filter(
                    AuthChallenge.secret_hash == secret_hash,
                    AuthChallenge.kind == kind.value,
                    AuthChallenge.consumed_at.is_(None),
                )
                .first()
            )

    def consume(self, challenge_id: UUID, now: datetime) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(AuthChallenge)
                .filter(
                    AuthChallenge.id == challenge_id,
                    AuthChallenge.consumed_at.is_(None),
                )
                .update({AuthChallenge.consumed_at: now}, synchronize_session=False)
            )
            session.commit()
            return updated == 1

    def confirm(self, challenge_id: UUID, now: datetime) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(AuthChallenge)
                .filter(
                    AuthChallenge.id == challenge_id,
                    AuthChallenge.consumed_at.is_(None),
                )
                .update(
                    {AuthChallenge.consumed_at: now, AuthChallenge.confirmed_at: now},
                    synchronize_session=False,
                )
            )
            session.commit()
            return updated == 1

    def record_failed_attempt(
        self, challenge_id: UUID, max_attempts: int, now: datetime
    ) -> int | None:
        table = AuthChallenge.__table__
        statement = (
            update(table)
            .where(table.c.id == challenge_id, table.c.consumed_at.is_(None))
            .values(
                attempts=table.c.attempts + 1,
                consumed_at=case(
                    (table.c.attempts + 1 >= max_attempts, now), else_=None
                ),
            )
            .returning(table.c.attempts)
        )
        with self._session_factory() as session:
            row = session.execute(statement).first()
            session.commit()
            return row[0] if row is not None else None

    def reissue(
        self,
        challenge_id: UUID,
        secret_hash: str,
        expires_at: datetime,
        issued_at: datetime,
    ) -> None:
        with self._session_factory() as session:
            challenge = (
                session.query(AuthChallenge)
                .filter_by(id=challenge_id)
                .with_for_update()
                .one()
            )
            session.query(AuthChallenge).filter(
                AuthChallenge.kind == challenge.kind,
                AuthChallenge.email == challenge.email,
                AuthChallenge.consumed_at.is_(None),
                AuthChallenge.id != challenge_id,
            ).update({AuthChallenge.consumed_at: issued_at}, synchronize_session=False)
            challenge.secret_hash = secret_hash
            challenge.attempts = 0
            challenge.expires_at = expires_at
            challenge.issued_at = issued_at
            challenge.consumed_at = None
            session.commit()

    def touch(self, challenge_id: UUID, issued_at: datetime) -> None:
        with self._session_factory() as session:
            session.query(AuthChallenge).filter(
                AuthChallenge.id == challenge_id
            ).update({AuthChallenge.issued_at: issued_at}, synchronize_session=False)
            session.commit()

    def consume_open_for_user(
        self, user_id: UUID, kind: ChallengeKind, now: datetime
    ) -> None:
        with self._session_factory() as session:
            session.query(AuthChallenge).filter(
                AuthChallenge.user_id == user_id,
                AuthChallenge.kind == kind.value,
                AuthChallenge.consumed_at.is_(None),
            ).update({AuthChallenge.consumed_at: now}, synchronize_session=False)
            session.commit()
