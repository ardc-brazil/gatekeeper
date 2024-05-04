from functools import wraps
from uuid import UUID
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader
from flask import request, g

from exception.UnauthorizedException import UnauthorizedException


def parse_user_header(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = request.headers.get("X-User-Id")
        if user_id:
            g.user_id = user_id

        return f(*args, **kwargs)

    return decorated

user_id = APIKeyHeader(name="X-User-Id", auto_error=False, scheme_name="X-User-Id") # APIKeyHeader(name="X-User-Id", auto_error=False, scheme_name="X-User-Id")

async def fastapi_parse_user_header(user_id: str = Depends(user_id)) -> UUID:
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    return UUID(user_id)
