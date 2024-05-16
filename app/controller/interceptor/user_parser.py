from typing import Annotated
from uuid import UUID
from fastapi import Body, Depends, Request
from fastapi.security import APIKeyHeader
from app.exception.unauthorized import UnauthorizedException

user_id = APIKeyHeader(
    name="X-User-Id", auto_error=False, scheme_name="X-User-Id"
)


async def parse_user_header(request: Request, user_id: str = Depends(user_id)) -> UUID:
    if not user_id:
        raise UnauthorizedException(f"unauthorized: {user_id}")

    return UUID(user_id)

async def parse_tus_user_id(request: Request) -> UUID:
    body = await request.json()
    user_id = body["Event"]["HTTPRequest"]["Header"]["X-User-Id"][0]
    if not user_id:
        raise UnauthorizedException(f"unauthorized: {user_id}")

    return UUID(user_id)

async def parse_tus_user_token(request: Request) -> str:
    body = await request.json()
    user_token = body["Event"]["HTTPRequest"]["Header"]["X-User-Token"][0]
    if not user_token:
        raise UnauthorizedException(f"unauthorized: {user_token}")

    return user_token