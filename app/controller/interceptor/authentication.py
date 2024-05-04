from typing import Annotated
from fastapi.responses import JSONResponse
from flask import request, jsonify, make_response
from functools import wraps
from dependency_injector.wiring import inject, Provide

from app.container import Container
from service.auth import AuthService
from exception.UnauthorizedException import UnauthorizedException
# from services.auth import AuthService
# from main import app

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader


api_key = APIKeyHeader(name="X-Api-Key", auto_error=False, scheme_name="X-Api-Key")
api_secret = APIKeyHeader(name="X-Api-Secret", auto_error=False, scheme_name="X-Api-Secret")

@inject
async def fastapi_authenticate(
        api_key: str = Depends(api_key),
        api_secret: str = Depends(api_secret),
        auth_service: AuthService = Depends(Provide[Container.auth_service])):
    
    try:
        auth_service.is_client_authorized(api_key, api_secret)
    except UnauthorizedException:
        raise HTTPException(status_code=401, detail="Unauthorized")

def authenticate(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-Api-Key")
        api_secret = request.headers.get("X-Api-Secret")

        try:
            pass
            # auth_service.is_client_authorized(api_key, api_secret)
        except UnauthorizedException:
            return make_response(jsonify({"message": "Unauthorized"}), 401)

        return f(*args, **kwargs)

    return decorated
