from contextlib import contextmanager, AbstractContextManager
from alembic import command
from alembic.config import Config
from typing import Callable
import logging

from pydantic import PostgresDsn
from sqlalchemy import create_engine, orm, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

Base = declarative_base()

# Arbitrary but fixed: every instance has to name the same lock.
MIGRATION_LOCK_KEY = 4915623


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
        """Bring the schema up to head, one instance at a time.

        Every instance runs this at startup, so the lock is what keeps two of
        them from migrating the same database at once.
        """
        config = Config("alembic.ini")
        # Keep alembic away from the logging configuration: fileConfig would
        # disable every logger it does not name, leaving the app silent.
        config.attributes["configure_logger"] = False

        with self._engine.connect() as connection:
            self._logger.info("waiting for the migration lock")
            connection.execute(text(f"SELECT pg_advisory_lock({MIGRATION_LOCK_KEY})"))
            try:
                self._logger.info("running database migrations")
                command.upgrade(config, "head")
                self._logger.info("database migrations are up to date")
            finally:
                connection.execute(
                    text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_KEY})")
                )

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
