from dependency_injector.wiring import inject, Provide

from app.container import Container
from app.service.auth import AuthService
from app.exception.UnauthorizedException import UnauthorizedException
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader


api_key = APIKeyHeader(name="X-Api-Key", auto_error=False, scheme_name="X-Api-Key")
api_secret = APIKeyHeader(
    name="X-Api-Secret", auto_error=False, scheme_name="X-Api-Secret"
)


@inject
async def authenticate(
    api_key: str = Depends(api_key),
    api_secret: str = Depends(api_secret),
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
):
    try:
        auth_service.is_client_authorized(api_key, api_secret)
    except UnauthorizedException:
        raise HTTPException(status_code=401, detail="Unauthorized")
