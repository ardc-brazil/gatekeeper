import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from app.exception.UnauthorizedException import UnauthorizedException
from app.exception.NotFoundException import NotFoundException
from app.exception import ConflictException

logger = logging.getLogger("uvicorn")


async def conflict_exception_handler(request: Request, exc: ConflictException):
    logger.info(f"Conflict exception: {exc}")
    return JSONResponse(status_code=409, content={"detail": str(exc)})


async def not_found_exception_handler(request: Request, exc: NotFoundException):
    logger.info(f"Not found exception: {exc}")
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def unauthorized_exception_handler(request: Request, exc: UnauthorizedException):
    logger.info(f"Unauthorized exception: {exc}")
    return JSONResponse(status_code=401, content={"detail": str(exc)})
