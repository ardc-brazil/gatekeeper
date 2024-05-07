from uuid import UUID
from app.model.db.client import Client
from contextlib import AbstractContextManager
from sqlalchemy.orm import Session
from typing import Callable, List


class ClientRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def fetch(self, api_key: UUID, is_enabled: bool = True) -> Client:
        with self._session_factory() as session:
            return (
                session.query(Client)
                .filter_by(key=api_key, is_enabled=is_enabled)
                .first()
            )

    def fetch_all(self, is_enabled: bool = True) -> List[Client]:
        with self._session_factory() as session:
            return session.query(Client).filter_by(is_enabled=is_enabled).all()

    def upsert(self, client: Client) -> Client:
        with self._session_factory() as session:
            session.add(client)
            session.commit()
            session.refresh(client)
            return client
