import json
from uuid import UUID
from fastapi import Depends, HTTPException, Request

from dependency_injector.wiring import inject, Provide

from app.container import Container
from app.controller.interceptor.user_parser import (
    parse_tus_dataset_id,
    parse_tus_user_id,
    parse_tus_user_token,
    parse_user_header,
)
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


@inject
async def authorize_tus(
    request: Request,
    user_id: UUID = Depends(parse_tus_user_id),
    user_token: str = Depends(parse_tus_user_token),
    dataset_id: str = Depends(parse_tus_dataset_id),
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
):
    resource = request.url.path
    action = request.method

    try:
        token_payload = auth_service.validate_jwt_and_decode(user_token=user_token)

        # The header alone says nothing: only the signed token proves who the
        # uploader is, and the uploader decides which tenancies the dataset
        # lookup runs under. Bind them.
        if token_payload.get("sub") != str(user_id):
            raise UnauthorizedException("user_id_does_not_match_token")

        # The BFF issues the token for one dataset and puts its id in the "file"
        # claim. Without this, a token handed out for one dataset uploads into
        # any other the person can reach.
        if dataset_id is not None and token_payload.get("file") != dataset_id:
            raise UnauthorizedException("token_not_issued_for_this_dataset")

        auth_service.authorize_user(user_id=user_id, resource=resource, action=action)
    except UnauthorizedException as e:
        # This has to be raised, not returned. A dependency that returns a
        # Response does not stop the request: FastAPI simply takes it as the
        # dependency's value and calls the endpoint anyway, which left this
        # write endpoint reachable with an invalid token and no credentials.
        raise HTTPException(
            status_code=401, detail=_adapt_tus_response(TusResult(401, str(e), True))
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_adapt_tus_response(TusResult(500, str(e), True))
        )
