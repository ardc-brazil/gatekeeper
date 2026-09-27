from dependency_injector.wiring import inject, Provide

from app.container import Container
from app.service.auth import AuthService
from app.exception.unauthorized import UnauthorizedException
from app.metrics import metrics
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader


api_key = APIKeyHeader(name="X-Api-Key", auto_error=False, scheme_name="X-Api-Key")
api_secret = APIKeyHeader(
    name="X-Api-Secret", auto_error=False, scheme_name="X-Api-Secret"
)


@inject
def authenticate(
    request: Request,
    api_key: str = Depends(api_key),
    api_secret: str = Depends(api_secret),
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
):
    try:
        client = auth_service.authorize_client(
            api_key=api_key, salted_api_secret=api_secret
        )
    except UnauthorizedException as e:
        metrics.auth_failure("authn", str(e))
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Read by the request middleware as the `client` metric label.
    request.state.client_name = client.name
