from contextlib import contextmanager, AbstractContextManager
from alembic import command
from alembic.config import Config
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

    def run_migrations(self) -> None:
        """Bring the schema up to head.

        The schema used to be built from the model metadata, which meant no
        migration was ever executed by the application or by any test. Alembic
        resolves the connection through `migrations/env.py`, which reads the
        same settings the app does.
        """
        config = Config("alembic.ini")
        # Keep alembic away from the logging configuration: fileConfig would
        # disable every logger it does not name, leaving the app silent.
        config.attributes["configure_logger"] = False
        self._logger.info("running database migrations")
        command.upgrade(config, "head")
        self._logger.info("database migrations are up to date")

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
