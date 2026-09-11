import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request

from app.logging_config import fields, request_id_var, setup_logging  # noqa: F401
from app.controller.v1.client.client import router as client_router
from app.controller.v1.infrastructure.infrastructure import (
    router as infrastructure_router,
    protected_router as infrastructure_protected_router,
)
from app.controller.v1.tenancy.tenancy import router as tenancies_router
from app.controller.v1.user.user import router as user_router
from app.controller.v1.dataset.dataset_filter import router as dataset_filter_router
from app.controller.v1.dataset.dataset import router as dataset_router
from app.controller.v1.dataset.dataset_snapshot import router as dataset_snapshot_router
from app.controller.v1.internal.dataset_collocation import (
    router as internal_dataset_collocation_router,
)
from app.controller.v1.tus.tus import router as tus_router
from app.exception.bad_request import BadRequestException
from app.exception.unauthorized import UnauthorizedException
from app.exception.not_found import NotFoundException
from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.controller.interceptor.exception_handler import (
    bad_request_exception_handler,
    conflict_exception_handler,
    generic_exception_handler,
    illegal_state_exception_handler,
    not_found_exception_handler,
    unauthorized_exception_handler,
)


access_logger = logging.getLogger("http.access")


def setup_middleware(fastAPIApp: FastAPI) -> None:
    @fastAPIApp.middleware("http")
    async def assign_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid4())
        token = request_id_var.set(request_id)
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # uvicorn's own access line is emitted outside this context and
            # carries no request id, so a failed request would lose its only
            # correlatable record.
            _log_access(request, 500, started)
            request_id_var.reset(token)
            raise

        try:
            response.headers["X-Request-Id"] = request_id
            _log_access(request, response.status_code, started)
            return response
        finally:
            request_id_var.reset(token)


def _log_access(request: Request, status_code: int, started: float) -> None:
    access_logger.info(
        "request",
        extra=fields(
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=round((perf_counter() - started) * 1000, 1),
        ),
    )


def setup_routes(fastAPIApp: FastAPI) -> None:
    fastAPIApp.include_router(dataset_filter_router, prefix="/v1")
    fastAPIApp.include_router(dataset_router, prefix="/v1")
    fastAPIApp.include_router(dataset_snapshot_router, prefix="/v1")
    fastAPIApp.include_router(tenancies_router, prefix="/v1")
    fastAPIApp.include_router(user_router, prefix="/v1")
    fastAPIApp.include_router(client_router, prefix="/v1")
    fastAPIApp.include_router(infrastructure_router, prefix="/v1")
    fastAPIApp.include_router(infrastructure_protected_router, prefix="/v1")
    fastAPIApp.include_router(internal_dataset_collocation_router, prefix="/v1")
    fastAPIApp.include_router(tus_router, prefix="/v1")


def setup_error_handlers(fastAPIApp: FastAPI) -> None:
    fastAPIApp.add_exception_handler(ConflictException, conflict_exception_handler)
    fastAPIApp.add_exception_handler(NotFoundException, not_found_exception_handler)
    fastAPIApp.add_exception_handler(
        UnauthorizedException, unauthorized_exception_handler
    )
    fastAPIApp.add_exception_handler(
        IllegalStateException, illegal_state_exception_handler
    )
    fastAPIApp.add_exception_handler(BadRequestException, bad_request_exception_handler)
    fastAPIApp.add_exception_handler(Exception, generic_exception_handler)
