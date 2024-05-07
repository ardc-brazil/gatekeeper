from uuid import UUID
from fastapi import Depends
from fastapi.security import APIKeyHeader
from app.exception.UnauthorizedException import UnauthorizedException

user_id = APIKeyHeader(name="X-User-Id", auto_error=False, scheme_name="X-User-Id") # APIKeyHeader(name="X-User-Id", auto_error=False, scheme_name="X-User-Id")

async def parse_user_header(user_id: str = Depends(user_id)) -> UUID:
    if not user_id:
        raise UnauthorizedException(f"unauthorized: {user_id}")
        
    return UUID(user_id)
