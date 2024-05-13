import json
from uuid import UUID
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from flask import make_response
from functools import wraps

from dependency_injector.wiring import inject, Provide

from app.container import Container
from app.controller.interceptor.user_parser import parse_user_header
from app.exception.unauthorized import UnauthorizedException
from app.model.tus import TusResult
from app.service.auth import AuthService


@inject
async def authorize(
    request: Request,
    user_id: UUID = Depends(parse_user_header),
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
):
    resource = request.url.path
    action = request.method

    auth_service.authorize_user(user_id, resource, action)    

def _adapt_tus_response(res: TusResult):
    return {
        "HTTPResponse": {
            "StatusCode": res.status_code,
            "Body": json.dumps({"message": res.body_msg}),
            "Header": {"Content-Type": "application/json"},
        }
    }

user_token = APIKeyHeader(
    name="X-User-Token", auto_error=False, scheme_name="X-User-Token"
)

@inject
async def authorize_tus(
    request: Request,
    user_id: UUID = Depends(parse_user_header),
    user_token: str = Depends(user_token),
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
):
    resource = request.url.path
    action = request.method

    try:
        auth_service.authorize_user(user_id, resource, action)
    except UnauthorizedException as e:
        return JSONResponse(content=_adapt_tus_response(TusResult(401, str(e), True)), status_code=401)
    except Exception as e:
        return JSONResponse(content=_adapt_tus_response(TusResult(500, str(e), True)), status_code=500)
