import json
from uuid import UUID
from fastapi import Depends, HTTPException, Request
from flask import make_response
from functools import wraps

from dependency_injector.wiring import inject, Provide

from app.container import Container
from app.controller.interceptor.user_parser import parse_user_header
from app.exception.UnauthorizedException import UnauthorizedException
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

    try:
        auth_service.is_user_authorized(user_id, resource, action)
    except UnauthorizedException as e:
        if str(e) == "missing_information":
            raise HTTPException(status_code=401, detail="Unauthorized")
        elif str(e) == "not_authorized":
            raise HTTPException(status_code=403, detail="Forbidden")
        else:
            raise HTTPException(status_code=403, detail="Forbidden")


def _adapt_tus_response(res: TusResult):
    return {
        "HTTPResponse": {
            "StatusCode": res.status_code,
            "Body": json.dumps({"message": res.body_msg}),
            "Header": {"Content-Type": "application/json"},
        }
    }


def authorize_tus(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # user_token = request.get_json()["Event"]["HTTPRequest"]["Header"][
        #     "X-User-Token"
        # ][0]
        # TODO get user_id from token when available
        # user_id = UUID(
        #     request.get_json()["Event"]["HTTPRequest"]["Header"]["X-User-Id"][0]
        # )
        # resource = request.path
        # action = request.method

        try:
            # self._auth_service.validate_jwt_and_decode(user_token)
            # self._auth_service.is_user_authorized(user_id, resource, action)
            pass
            # set user_id in context
            # g.user_id = user_id
        except UnauthorizedException as e:
            return make_response(_adapt_tus_response(TusResult(401, str(e), True)), 401)
        except Exception as e:
            return make_response(_adapt_tus_response(TusResult(500, str(e), True)), 500)

        return f(*args, **kwargs)

    return decorated
