from contextlib import contextmanager, AbstractContextManager
from alembic import command
from alembic.config import Config
from time import perf_counter
from typing import Callable
import logging

from pydantic import PostgresDsn
from sqlalchemy import create_engine, event, orm, text
from sqlalchemy.engine import Engine

from app.metrics import metrics
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

Base = declarative_base()

# Arbitrary but fixed: every instance has to name the same lock.
MIGRATION_LOCK_KEY = 4915623


_CRUD = frozenset({"select", "insert", "update", "delete"})


def _statement_type(statement: str) -> str:
    words = statement.lstrip().split(None, 1)
    kind = words[0].lower() if words else ""
    return kind if kind in _CRUD else "other"


def instrument_engine(engine: Engine) -> None:
    """Time every statement as a call to postgres, and expose the pool."""

    @event.listens_for(engine, "before_cursor_execute")
    def _started(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("query_started", []).append(perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _finished(conn, cursor, statement, parameters, context, executemany):
        _record(conn, statement, "success")

    @event.listens_for(engine, "handle_error")
    def _failed(context):
        if context.connection is not None:
            _record(context.connection, context.statement or "", "error")

    if hasattr(engine.pool, "checkedout"):
        metrics.watch_pool(engine.pool)


def _record(conn, statement: str, outcome: str) -> None:
    started = conn.info.get("query_started")
    if not started:
        return
    metrics.external_call_finished(
        "postgres", _statement_type(statement), outcome, perf_counter() - started.pop()
    )


class Database:
    def __init__(self, db_url: PostgresDsn, log_enabled: bool) -> None:
        self._logger = logging.getLogger("database")
        self._engine = create_engine(
            db_url.unicode_string(), echo=log_enabled, hide_parameters=True
        )
        instrument_engine(self._engine)
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
