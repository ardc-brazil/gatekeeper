from dataclasses import asdict
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from app.exception.bad_request import BadRequestException
from app.exception.forbidden import ForbiddenException
from app.exception.illegal_state import IllegalStateException
from app.exception.unauthorized import UnauthorizedException
from app.exception.not_found import NotFoundException
from app.exception.too_many_requests import TooManyRequestsException
from app.exception import conflict
from app.logging_config import fields, request_id_var

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


async def forbidden_exception_handler(request: Request, exc: ForbiddenException):
    logger.info(f"Forbidden exception: {exc}")
    return JSONResponse(status_code=403, content={"detail": "forbidden"})


async def too_many_requests_exception_handler(
    request: Request, exc: TooManyRequestsException
):
    logger.info(f"Too many requests exception: {exc}")
    return JSONResponse(status_code=429, content={"detail": str(exc)})


async def illegal_state_exception_handler(request: Request, exc: IllegalStateException):
    logger.info(f"Illegal State exception: {exc}")
    return JSONResponse(status_code=400, content={"detail": str(exc)})


async def bad_request_exception_handler(request: Request, exc: BadRequestException):
    logger.error(f"Bad request exception: {exc}")
    return JSONResponse(
        status_code=400,
        content={
            "details": "Invalid client input",
            "errors": [asdict(error) for error in exc.errors],
        },
    )


def _request_id(request: Request) -> str:
    # This handler runs outside the middleware, where request_id_var is unset.
    state = getattr(request, "state", None)
    return getattr(state, "request_id", None) or request_id_var.get()


async def generic_exception_handler(request: Request, exc: Exception):
    request_id = _request_id(request)
    logger.error(
        "Unhandled exception", exc_info=exc, extra=fields(request_id=request_id)
    )
    # Never the exception text: it can carry SQL, paths and parameters.
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )
