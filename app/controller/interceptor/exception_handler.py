from dataclasses import asdict
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from app.exception.bad_request import BadRequestException
from app.exception.illegal_state import IllegalStateException
from app.exception.unauthorized import UnauthorizedException
from app.exception.not_found import NotFoundException
from app.exception import conflict

logger = logging.getLogger("uvicorn")


async def conflict_exception_handler(request: Request, exc: conflict):
    logger.info(f"Conflict exception: {exc}")
    return JSONResponse(status_code=409, content={"detail": str(exc)})


async def not_found_exception_handler(request: Request, exc: NotFoundException):
    logger.info(f"Not found exception: {exc}")
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def unauthorized_exception_handler(request: Request, exc: UnauthorizedException):
    logger.info(f"Unauthorized exception: {exc}")
    return JSONResponse(status_code=401, content={"detail": str(exc)})


async def illegal_state_exception_handler(request: Request, exc: IllegalStateException):
    logger.info(f"Unauthorized exception: {exc}")
    return JSONResponse(status_code=400, content={"detail": str(exc)})


async def bad_request_exception_handler(request: Request, exc: BadRequestException):
    logger.error(f"Bad request exception: {exc}")
    return JSONResponse(status_code=400, content=[asdict(error) for error in exc.errors])


async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Generic exception: {exc}")
    return JSONResponse(status_code=500, content={"detail": str(exc)})
