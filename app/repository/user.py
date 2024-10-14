from typing import List
from uuid import UUID
from app.model.user import UserQuery
from app.model.db.user import Provider, User, user_provider_association
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import true
from typing import Callable
from contextlib import AbstractContextManager
from sqlalchemy.orm import Session
from app.exception.conflict import ConflictException
from sqlalchemy.exc import IntegrityError


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
                session.add(user)
                session.commit()
                session.refresh(user)
            return user
        except IntegrityError:
            raise ConflictException(f"user_already_exists: {user.email}")

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
