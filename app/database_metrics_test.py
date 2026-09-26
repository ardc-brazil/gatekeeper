import unittest

from prometheus_client import REGISTRY
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import QueuePool

from app.database import instrument_engine


def _queries(operation: str, outcome: str) -> float:
    return (
        REGISTRY.get_sample_value(
            "datamap_external_request_duration_seconds_count",
            {"service": "postgres", "operation": operation, "outcome": outcome},
        )
        or 0.0
    )


class TestQueryMetrics(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=QueuePool)
        instrument_engine(self.engine)

    def test_a_query_is_recorded_under_its_statement_type(self):
        before = _queries("select", "success")

        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        self.assertEqual(_queries("select", "success"), before + 1)

    def test_writes_are_told_apart_from_reads(self):
        before = _queries("insert", "success")

        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE t (x INTEGER)"))
            connection.execute(text("INSERT INTO t VALUES (1)"))

        self.assertEqual(_queries("insert", "success"), before + 1)

    def test_a_statement_that_is_not_crud_is_filed_as_other(self):
        before = _queries("other", "success")

        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE u (x INTEGER)"))

        self.assertEqual(_queries("other", "success"), before + 1)

    def test_a_failing_query_is_recorded_as_an_error(self):
        before = _queries("select", "error")

        with self.assertRaises(OperationalError):
            with self.engine.connect() as connection:
                connection.execute(text("SELECT * FROM does_not_exist"))

        self.assertEqual(_queries("select", "error"), before + 1)

    def test_the_pool_is_exposed(self):
        self.assertIsNotNone(REGISTRY.get_sample_value("datamap_db_pool_size"))
