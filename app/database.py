from contextlib import contextmanager, AbstractContextManager
from typing import Callable
import logging

from pydantic import PostgresDsn
from sqlalchemy import create_engine, orm
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

Base = declarative_base()


class Database:
    def __init__(self, db_url: PostgresDsn, log_enabled: bool) -> None:
        self._logger = logging.getLogger("database")
        self._engine = create_engine(db_url.unicode_string(), echo=log_enabled)
        self._session_factory = orm.scoped_session(
            orm.sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self._engine,
            ),
        )

    def create_database(self) -> None:
        Base.metadata.create_all(self._engine)

    @contextmanager
    def session(self) -> Callable[..., AbstractContextManager[Session]]:
        session: Session = self._session_factory()
        try:
            yield session
        except Exception:
            self._logger.exception("Session rollback because of exception")
            session.rollback()
            raise
        finally:
            session.close()

    def get_engine(self):
        return self._engine
