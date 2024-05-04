import json
from uuid import UUID
from fastapi import Depends, HTTPException, Request
from flask import make_response, request, jsonify, g
from functools import wraps

from dependency_injector.wiring import inject, Provide

from app.container import Container
from controllers.interceptor.user_parser import fastapi_parse_user_header
from exception.UnauthorizedException import UnauthorizedException
from model.tus import TusResult
from service.auth import AuthService

# auth_service = AuthService(None)


def __get_user_from_request(request) -> UUID:
    if request.headers.get("X-User-Id") is None:
        return None

    return UUID(request.headers.get("X-User-Id"))


def authorize(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = __get_user_from_request(request)
        resource = request.path
        action = request.method

        try:
            pass
            # auth_service.is_user_authorized(user_id, resource, action)
        except UnauthorizedException as e:
            if str(e) == "missing_information":
                return make_response(jsonify({"message": "Unauthorized"}), 401)
            elif str(e) == "not_authorized":
                return make_response(jsonify({"message": "Forbidden"}), 403)
            else:
                return make_response(jsonify({"message": "Forbidden"}), 403)

        return f(*args, **kwargs)

    return decorated

@inject
async def fastapi_authorize(request: Request, 
                            user_id: UUID = Depends(fastapi_parse_user_header),
                            auth_service: AuthService = Depends(Provide[Container.auth_service])):
    resource = request.url.path
    action = request.method

    try:
        # TODO solve this issue, the enforcer is not available
        # auth_service.is_user_authorized(user_id, resource, action)
        pass
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
        user_token = request.get_json()["Event"]["HTTPRequest"]["Header"][
            "X-User-Token"
        ][0]
        # TODO get user_id from token when available
        user_id = UUID(
            request.get_json()["Event"]["HTTPRequest"]["Header"]["X-User-Id"][0]
        )
        resource = request.path
        action = request.method

        try:
            # auth_service.validate_jwt_and_decode(user_token)
            # auth_service.is_user_authorized(user_id, resource, action)
            pass
            # set user_id in context
            g.user_id = user_id
        except UnauthorizedException as e:
            return make_response(_adapt_tus_response(TusResult(401, str(e), True)), 401)
        except Exception as e:
            return make_response(_adapt_tus_response(TusResult(500, str(e), True)), 500)

        return f(*args, **kwargs)

    return decorated
