import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import jwt
from app.exception.unauthorized import UnauthorizedException
from app.service.auth import AuthService


class TestAuthService(unittest.TestCase):
    def setUp(self):
        self.client_service = Mock()
        self.casbin_enforcer = Mock()
        self.file_upload_token_secret = "fake_secret_for_jwt_token"
        self.auth_service = AuthService(
            self.client_service, self.casbin_enforcer, self.file_upload_token_secret
        )

    def test_authorize_client_success(self):
        api_key = "test_api_key"
        salted_api_secret = "test_salted_secret"
        client_secret = "hashed_secret"
        client_mock = Mock(secret=client_secret)
        self.client_service.fetch.return_value = client_mock

        with patch("app.service.auth.check_password") as mock_check_password:
            mock_check_password.return_value = True
            self.assertIsNone(
                self.auth_service.authorize_client(api_key, salted_api_secret)
            )
            self.client_service.fetch.assert_called_once_with(api_key)
            mock_check_password.assert_called_once_with(
                password=salted_api_secret, hashed_password=client_secret
            )

    def test_authorize_client_missing_information(self):
        with self.assertRaises(UnauthorizedException):
            self.auth_service.authorize_client(None, None)

    def test_authorize_client_wrong_credentials(self):
        api_key = "test_api_key"
        salted_api_secret = "test_salted_secret"
        self.client_service.fetch.return_value = None

        with patch("app.service.auth.check_password") as mock_check_password:
            mock_check_password.return_value = False
            with self.assertRaises(UnauthorizedException):
                self.auth_service.authorize_client(api_key, salted_api_secret)

    def test_validate_jwt_and_decode_success(self):
        user_token = "test_user_token"
        decoded_token = {"user_id": str(uuid4())}
        with patch("app.service.auth.jwt.decode", return_value=decoded_token):
            result = self.auth_service.validate_jwt_and_decode(user_token)

        self.assertEqual(result, decoded_token)

    def test_validate_jwt_and_decode_missing_information(self):
        with self.assertRaises(UnauthorizedException) as context:
            self.auth_service.validate_jwt_and_decode(None)

        self.assertEqual(str(context.exception), "missing_information")

    def test_validate_jwt_and_decode_expired_token(self):
        user_token = "test_user_token"
        with patch(
            "app.service.auth.jwt.decode", side_effect=jwt.ExpiredSignatureError
        ):
            with self.assertRaises(UnauthorizedException) as context:
                self.auth_service.validate_jwt_and_decode(user_token)

        self.assertEqual(str(context.exception), "expired")

    def test_validate_jwt_and_decode_invalid_token(self):
        user_token = "test_user_token"
        with patch("app.service.auth.jwt.decode", side_effect=jwt.InvalidTokenError):
            with self.assertRaises(UnauthorizedException) as context:
                self.auth_service.validate_jwt_and_decode(user_token)

        self.assertEqual(str(context.exception), "invalid_token")

    def test_validate_jwt_and_decode_failed_to_validate(self):
        user_token = "test_user_token"
        error_message = "test_error_message"
        with patch("app.service.auth.jwt.decode", side_effect=Exception(error_message)):
            with self.assertRaises(Exception) as context:
                self.auth_service.validate_jwt_and_decode(user_token)

        self.assertIn(error_message, str(context.exception))

    def test_authorize_user_success(self):
        user_id = uuid4()
        resource = "test_resource"
        action = "test_action"
        self.casbin_enforcer.enforce.return_value = True

        self.assertIsNone(self.auth_service.authorize_user(user_id, resource, action))
        self.casbin_enforcer.enforce.assert_called_once_with(
            str(user_id), resource, action
        )

    def test_authorize_user_missing_information(self):
        with self.assertRaises(UnauthorizedException) as context:
            self.auth_service.authorize_user(None, None, None)

        self.assertEqual(str(context.exception), "missing_information")

    def test_authorize_user_not_authorized(self):
        user_id = uuid4()
        resource = "test_resource"
        action = "test_action"
        self.casbin_enforcer.enforce.return_value = False

        with self.assertRaises(UnauthorizedException) as context:
            self.auth_service.authorize_user(user_id, resource, action)

        self.assertEqual(str(context.exception), "not_authorized")


if __name__ == "__main__":
    unittest.main()
