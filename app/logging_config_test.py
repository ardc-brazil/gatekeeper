import io
import json
import logging
import unittest

from app.logging_config import Redactor, fields, mask_path_tokens, setup_logging


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

    def test_a_confirmation_code_in_a_body_is_redacted(self):
        self.assertEqual(Redactor.scrub({"code": "042917"})["code"], "[redacted]")
        self.assertEqual(Redactor.scrub({"Code": "042917"})["Code"], "[redacted]")

    def test_it_is_redacted_inside_the_access_line_body_too(self):
        scrubbed = Redactor.scrub({"body": {"code": "042917"}})

        self.assertEqual(scrubbed["body"]["code"], "[redacted]")

    def test_a_field_that_merely_ends_in_code_is_left_alone(self):
        self.assertEqual(Redactor.scrub({"status_code": 401})["status_code"], 401)


class TestReservedAttributes(unittest.TestCase):
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


class TestPathTokenMasking(unittest.TestCase):
    def tearDown(self):
        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)

    def test_an_anonymous_link_token_is_masked(self):
        self.assertEqual(
            mask_path_tokens("/api/v1/anonymous/s3cr3t-T0ken"),
            "/api/v1/anonymous/{token}",
        )

    def test_an_invitation_token_is_masked(self):
        self.assertEqual(
            mask_path_tokens("/api/v1/invitations/s3cr3t-T0ken"),
            "/api/v1/invitations/{token}",
        )

    def test_the_path_without_the_root_prefix_is_masked_too(self):
        self.assertEqual(
            mask_path_tokens("/v1/anonymous/s3cr3t"), "/v1/anonymous/{token}"
        )

    def test_a_full_link_is_masked(self):
        self.assertEqual(
            mask_path_tokens("https://datamap.pcs.usp.br/invitations/s3cr3t?x=1"),
            "https://datamap.pcs.usp.br/invitations/{token}?x=1",
        )

    def test_the_accept_route_is_left_alone(self):
        self.assertEqual(
            mask_path_tokens("/api/v1/invitations/accept"),
            "/api/v1/invitations/accept",
        )

    def test_the_claim_route_is_left_alone(self):
        path = "/api/v1/users/7a9b5d5e/invitations/claim"
        self.assertEqual(mask_path_tokens(path), path)

    def test_an_invitation_id_under_a_dataset_is_left_alone(self):
        path = "/api/v1/datasets/7a9b5d5e/share/invitations/0c1d2e3f"
        self.assertEqual(mask_path_tokens(path), path)
        self.assertEqual(mask_path_tokens(path + "/link"), path + "/link")

    def test_an_unrelated_path_is_left_alone(self):
        self.assertEqual(mask_path_tokens("/api/v1/datasets"), "/api/v1/datasets")

    def test_a_path_field_on_any_line_is_masked(self):
        entry = _capture(
            extra={"path": "/api/v1/anonymous/leaked", "url": "/v1/invitations/leaked"}
        )

        self.assertNotIn("leaked", json.dumps(entry))
        self.assertEqual(entry["path"], "/api/v1/anonymous/{token}")
        self.assertEqual(entry["url"], "/v1/invitations/{token}")
