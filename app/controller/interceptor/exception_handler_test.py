import json
import unittest
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import setup
from app.controller.interceptor.exception_handler import (
    bad_request_exception_handler,
    generic_exception_handler,
)
from app.exception.bad_request import BadRequestException, ErrorDetails
from app.exception.forbidden import ForbiddenException
from app.exception.too_many_requests import TooManyRequestsException


class TestExceptionHandler(unittest.IsolatedAsyncioTestCase):
    async def test_bad_response(self):
        # given
        request = None
        exception = BadRequestException(
            errors=[ErrorDetails(code="missing_field", field="field1")]
        )

        # when
        response = await bad_request_exception_handler(request=request, exc=exception)

        # then
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.body)
        self.assertEqual(data["details"], "Invalid client input")
        self.assertListEqual(
            data["errors"], [{"code": "missing_field", "field": "field1"}]
        )


class TestUnexpectedErrors(unittest.IsolatedAsyncioTestCase):
    async def test_the_caller_is_told_nothing_about_what_failed_inside(self):
        exception = RuntimeError(
            'invalid input syntax for type uuid: "x" [SQL: SELECT clients.key FROM clients]'
        )

        with self.assertLogs("uvicorn", level="ERROR"):
            response = await generic_exception_handler(request=None, exc=exception)

        self.assertEqual(response.status_code, 500)
        body = response.body.decode()
        self.assertNotIn("SELECT", body)
        self.assertNotIn("uuid", body)
        self.assertEqual(json.loads(body)["detail"], "Internal server error")

    async def test_the_response_carries_the_request_id_to_find_it_in_the_logs(self):
        # The handler runs outside the middleware's context, so the id has to
        # come from the request itself, as it does in a real failure.
        request = SimpleNamespace(state=SimpleNamespace(request_id="req-123"))

        with self.assertLogs("uvicorn", level="ERROR"):
            response = await generic_exception_handler(
                request=request, exc=RuntimeError("boom")
            )

        self.assertEqual(json.loads(response.body)["request_id"], "req-123")

    async def test_the_log_line_carries_the_same_request_id(self):
        request = SimpleNamespace(state=SimpleNamespace(request_id="req-456"))

        with self.assertLogs("uvicorn", level="ERROR") as logs:
            await generic_exception_handler(request=request, exc=RuntimeError("boom"))

        self.assertEqual(getattr(logs.records[0], "request_id", None), "req-456")

    async def test_the_whole_error_still_reaches_the_log(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError as raised:
            exception = raised

        with self.assertLogs("uvicorn", level="ERROR") as logs:
            await generic_exception_handler(request=None, exc=exception)

        self.assertIn("boom", "".join(logs.output))
        self.assertIn("Traceback", "".join(logs.output))


class TestForbiddenHandler(unittest.TestCase):
    def test_a_forbidden_action_answers_403_without_the_exception_text(self):
        app = FastAPI()
        setup.setup_error_handlers(app)

        @app.get("/boom")
        def boom():
            raise ForbiddenException("user x may not delete dataset y")

        response = TestClient(app, raise_server_exceptions=False).get("/boom")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "forbidden"})


class TestTooManyRequestsHandler(unittest.TestCase):
    def test_a_refused_retry_answers_429_with_its_code(self):
        app = FastAPI()
        setup.setup_error_handlers(app)

        @app.post("/again")
        def again():
            raise TooManyRequestsException("resend_too_soon")

        response = TestClient(app, raise_server_exceptions=False).post("/again")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), {"detail": "resend_too_soon"})


if __name__ == "__main__":
    unittest.main()
