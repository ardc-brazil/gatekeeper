from typing import List
from uuid import UUID
from app.model.user import UserQuery
from app.model.db.user import (
    Provider,
    User,
    user_provider_association,
    user_tenancy_association,
)
from sqlalchemy import func, or_
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import true
from typing import Callable
from contextlib import AbstractContextManager
from sqlalchemy.orm import Session
from app.exception.conflict import ConflictException
from sqlalchemy.exc import IntegrityError


def like_pattern(term: str) -> str:
    escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class UserRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def fetch_by_id(self, id: UUID, is_enabled: bool = True) -> User:
        with self._session_factory() as session:
            return session.query(User).filter_by(id=id, is_enabled=is_enabled).first()

    def fetch_by_email(self, email: str, is_enabled: bool = True) -> User:
        with self._session_factory() as session:
            return (
                session.query(User)
                .filter_by(email=email, is_enabled=is_enabled)
                .first()
            )

    def fetch_by_provider(
        self, provider_name: str, reference: str, is_enabled: bool = True
    ) -> User:
        provider_alias = aliased(Provider)
        with self._session_factory() as session:
            user = (
                session.query(User)
                .join(user_provider_association)
                .join(
                    provider_alias,
                    provider_alias.id == user_provider_association.c.provider_id,
                )
                .filter(
                    provider_alias.name == provider_name,
                    provider_alias.reference == reference,
                    User.is_enabled == is_enabled,
                )
                .first()
            )

        return user

    def upsert(self, user: User) -> User:
        try:
            with self._session_factory() as session:
                merged_user = session.merge(user)
                session.commit()
                session.refresh(merged_user)
            return merged_user
        except IntegrityError:
            raise ConflictException(f"user_already_exists: {user.email}")

    def fetch_by_email_insensitive(self, email: str) -> User | None:
        with self._session_factory() as session:
            return (
                session.query(User)
                .filter(
                    func.lower(User.email) == email.lower(), User.is_enabled == true()
                )
                .first()
            )

    def search_share_candidates(
        self, tenancy: str, term: str, exclude_ids: list[UUID], limit: int = 10
    ) -> List[User]:
        pattern = like_pattern(term)
        with self._session_factory() as session:
            query = (
                session.query(User)
                .join(
                    user_tenancy_association,
                    user_tenancy_association.c.user_id == User.id,
                )
                .filter(
                    user_tenancy_association.c.tenancy == tenancy,
                    User.is_enabled == true(),
                    or_(
                        User.name.ilike(pattern, escape="\\"),
                        User.email.ilike(pattern, escape="\\"),
                    ),
                )
            )
            if exclude_ids:
                query = query.filter(User.id.notin_(exclude_ids))
            return query.order_by(User.name).limit(limit).all()

    def search(self, query_params: UserQuery) -> List[User]:
        with self._session_factory() as session:
            query = session.query(User)

            # TODO test these
            if query_params.email is not None:
                query = query.filter(User.email == query_params.email)

            if query_params.is_enabled is not None:
                query = query.filter(User.is_enabled == query_params.is_enabled)
            else:
                query = query.filter(User.is_enabled == true())

            return query.all()
