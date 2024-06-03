import logging
from uuid import UUID
import jwt
from app.exception.unauthorized import UnauthorizedException
from app.service.client import ClientService
from app.service.secret import check_password
from casbin import SyncedEnforcer

class AuthService:
    def __init__(
        self,
        client_service: ClientService,
        casbin_enforcer: SyncedEnforcer,
        file_upload_token_secret: str,
    ) -> None:
        self._client_service = client_service
        self._casbin_enforcer = casbin_enforcer
        self._file_upload_token_secret = file_upload_token_secret

    def authorize_client(self, api_key: str, salted_api_secret: str) -> None:
        if api_key is None or salted_api_secret is None:
            raise UnauthorizedException("missing_information")

        client = self._client_service.fetch(api_key)

        if client is None:
            logging.info(f"api_key {api_key} not found")
            raise UnauthorizedException("wrong_credentials")

        if not check_password(
            password=salted_api_secret, hashed_password=client.secret
        ):
            logging.warn(f"incorrect api_secret {salted_api_secret}")
            raise UnauthorizedException("wrong_credentials")

    def validate_jwt_and_decode(self, user_token: str) -> dict:
        """Validate JWT signature and return the token payload"""
        if user_token is None:
            raise UnauthorizedException("missing_information")

        try:
            return jwt.decode(
                jwt=user_token, key=self._user_token_secret, algorithms=["HS256"]
            )
        except jwt.ExpiredSignatureError:
            logging.warning(f"expired jwt: {user_token}")
            raise UnauthorizedException("expired")
        except jwt.InvalidTokenError:
            logging.warning(f"invalid token: {user_token}")
            raise UnauthorizedException("invalid_token")
        except Exception as e:
            logging.error(f"failed to validate jwt. {e}")
            raise e

    def authorize_user(self, user_id: UUID, resource: str, action: str) -> None:
        if user_id is None or resource is None or action is None:
            raise UnauthorizedException("missing_information")

        if not self._casbin_enforcer.enforce(str(user_id), resource, action):
            logging.info(
                "User %s is not authorized to %s %s", user_id, action, resource
            )
            raise UnauthorizedException("not_authorized")
