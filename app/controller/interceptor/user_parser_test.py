from dataclasses import dataclass
import unittest
from uuid import UUID

from fastapi import Request

from app.controller.interceptor.user_parser import parse_user_header
from app.exception.unauthorized import UnauthorizedException


class TestUserParserInterceptor(unittest.IsolatedAsyncioTestCase):
    async def test_parse_user_header(self):
        @dataclass
        class TestCase:
            name: str
            given_request: Request = None
            given_user_id: str = None
            expected: str = None
            expected_raise: Exception = None

        # given
        testcases = [
            TestCase(
                name="success",
                given_user_id="8572EBBA-2A3C-45D7-8FC6-13950BCED3BC",
                expected="8572EBBA-2A3C-45D7-8FC6-13950BCED3BC",
            ),
            TestCase(
                name="none_user_id",
                given_user_id=None,
                expected_raise=UnauthorizedException("user_id header not found"),
            ),
        ]

        for case in testcases:
            if case.expected_raise is not None:
                with self.assertRaises(UnauthorizedException) as cm:
                    actual = await parse_user_header(
                        request=case.given_request, user_id=case.given_user_id
                    )

                self.assertEqual(str(cm.exception), str(case.expected_raise))

            else:
                # when
                actual = await parse_user_header(
                    request=case.given_request, user_id=case.given_user_id
                )

                # then
                self.assertEqual(
                    actual,
                    UUID(case.expected),
                    "failed test {} expected {}, actual {}".format(
                        case.name, case.expected, actual
                    ),
                )
