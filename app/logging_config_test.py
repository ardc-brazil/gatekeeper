import io
import json
import logging
import unittest

from app.logging_config import Redactor, fields, setup_logging


def _capture(logger_name: str = "test", **kwargs) -> dict:
    stream = io.StringIO()
    setup_logging(stream=stream)
    logging.getLogger(logger_name).error("a message", **kwargs)
    return json.loads(stream.getvalue().strip().splitlines()[-1])


class TestLoggingConfiguration(unittest.TestCase):
    def tearDown(self):
        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)

    def test_the_root_logger_gets_exactly_one_handler(self):
        setup_logging(stream=io.StringIO())
        setup_logging(stream=io.StringIO())

        self.assertEqual(len(logging.getLogger().handlers), 1)

    def test_named_loggers_carry_no_handler_of_their_own(self):
        setup_logging(stream=io.StringIO())

        for name in (
            "uvicorn",
            "uvicorn.access",
            "casbin.enforcer",
            "sqlalchemy.engine",
        ):
            self.assertEqual(
                logging.getLogger(name).handlers,
                [],
                f"{name} has its own handler, so its lines are emitted twice",
            )

    def test_a_line_is_json_with_the_fields_worth_querying(self):
        entry = _capture("service:tus")

        self.assertEqual(entry["message"], "a message")
        self.assertEqual(entry["level"], "ERROR")
        self.assertEqual(entry["logger"], "service:tus")
        self.assertIn("timestamp", entry)

    def test_extra_fields_are_emitted_as_fields(self):
        entry = _capture(extra={"dataset_id": "abc", "hook_type": "post-finish"})

        self.assertEqual(entry["dataset_id"], "abc")
        self.assertEqual(entry["hook_type"], "post-finish")

    def test_a_request_id_is_attached_when_one_is_set(self):
        from app.logging_config import request_id_var

        token = request_id_var.set("req-123")
        try:
            entry = _capture()
        finally:
            request_id_var.reset(token)

        self.assertEqual(entry["request_id"], "req-123")


class TestRedaction(unittest.TestCase):
    def tearDown(self):
        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)

    def test_a_credential_header_never_reaches_the_output(self):
        entry = _capture(extra={"headers": {"X-User-Token": "eyJhbGciOi.secret"}})

        self.assertNotIn("eyJhbGciOi.secret", json.dumps(entry))

    def test_redaction_reaches_nested_values(self):
        payload = {"Event": {"HTTPRequest": {"Header": {"X-User-Token": ["leaked"]}}}}

        entry = _capture(extra={"payload": payload})

        self.assertNotIn("leaked", json.dumps(entry))

    def test_every_credential_key_is_covered(self):
        for key in (
            "X-User-Token",
            "Authorization",
            "X-Api-Secret",
            "password",
            "access_token",
        ):
            with self.subTest(key=key):
                self.assertEqual(Redactor.scrub({key: "sensitive"})[key], "[redacted]")

    def test_an_unrelated_field_is_left_alone(self):
        self.assertEqual(
            Redactor.scrub({"dataset_id": "7a9b5d5e"})["dataset_id"], "7a9b5d5e"
        )

    def test_a_credential_interpolated_into_the_message_is_still_removed(self):
        stream = io.StringIO()
        setup_logging(stream=stream)

        logging.getLogger("test").error(
            "rejected {'X-User-Token': ['eyJhbGciOi.secret']}"
        )

        self.assertNotIn("eyJhbGciOi.secret", stream.getvalue())


class TestReservedAttributes(unittest.TestCase):
    """`logging` refuses a record whose extras collide with LogRecord's own
    attributes, and raises where the call site is. A field named `filename` made
    every TUS hook answer 500."""

    def tearDown(self):
        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)

    def test_a_reserved_name_does_not_break_the_call(self):
        stream = io.StringIO()
        setup_logging(stream=stream)

        logging.getLogger("test").info(
            "upload received",
            extra=fields(filename="a.txt", module="x", dataset_id="d"),
        )

        entry = json.loads(stream.getvalue().strip().splitlines()[-1])
        self.assertEqual(entry["dataset_id"], "d")

    def test_the_value_survives_under_a_prefixed_name(self):
        self.assertEqual(fields(filename="a.txt")["log_filename"], "a.txt")

    def test_an_ordinary_name_is_untouched(self):
        self.assertEqual(fields(dataset_id="d"), {"dataset_id": "d"})
