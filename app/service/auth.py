import logging
from uuid import UUID
import jwt
from controller.interceptor.authorization_container import AuthorizationContainer
from exception.UnauthorizedException import UnauthorizedException
from app.service.client import ClientService
from app.service.secret import check_password
from flask import current_app as app

# client_service = ClientService()


class AuthService:
    def __init__(self, client_service: ClientService) -> None:
        self._client_service = client_service

    def is_client_authorized(self, api_key: str, salted_api_secret: str):
        if api_key is None or salted_api_secret is None:
            raise UnauthorizedException("missing_information")

        client = self._client_service.fetch(api_key)

        if client is None:
            logging.info(f"api_key {api_key} not found")
            raise UnauthorizedException("wrong_credentials")

        if not check_password(salted_api_secret, client["secret"]):
            logging.warn(f"incorrect api_secret {salted_api_secret}")
            raise UnauthorizedException("wrong_credentials")

    def validate_jwt_and_decode(self, user_token: str) -> dict:
        """Validate JWT signature and return the token payload"""
        if user_token is None:
            raise UnauthorizedException("missing_information")

        try:
            return jwt.decode(
                user_token, app.config["USER_TOKEN_SECRET"], algorithms=["HS256"]
            )
        except jwt.ExpiredSignatureError:
            logging.warn(f"expired jwt: {user_token}")
            raise UnauthorizedException("expired")
        except jwt.InvalidTokenError:
            logging.warn(f"invalid token: {user_token}")
            raise UnauthorizedException("invalid_token")
        except Exception as e:
            logging.error(f"failed to validate jwt. {e}")
            raise e

    def is_user_authorized(self, user_id: UUID, resource: str, action: str):
        if user_id is None or resource is None or action is None:
            raise UnauthorizedException("missing_information")

        if (
            not AuthorizationContainer.instance()
            .getEnforcer()
            .enforce(str(user_id), resource, action)
        ):
            logging.info(
                "User %s is not authorized to %s %s", user_id, action, resource
            )
            raise UnauthorizedException("not_authorized")
