import json
import unittest

from app.controller.interceptor.exception_handler import bad_request_exception_handler
from app.exception.bad_request import BadRequestException, ErrorDetails


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


if __name__ == "__main__":
    unittest.main()
