import json
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from app.logging_config import (  # noqa: F401
    fields,
    mask_path_tokens,
    request_id_var,
    setup_logging,
)
from app.metrics import metrics
from app.controller.v1.admin.email import router as admin_email_router
from app.controller.v1.admin.tenancy import router as admin_tenancy_router
from app.controller.v1.client.client import router as client_router
from app.controller.v1.infrastructure.infrastructure import (
    router as infrastructure_router,
    protected_router as infrastructure_protected_router,
)
from app.controller.v1.tenancy.tenancy import router as tenancies_router
from app.controller.v1.auth.auth import router as auth_router
from app.controller.v1.user.user import router as user_router
from app.controller.v1.user.tenancy_access import router as tenancy_access_router
from app.controller.v1.dataset.dataset_filter import router as dataset_filter_router
from app.controller.v1.dataset.dataset import router as dataset_router
from app.controller.v1.dataset.dataset_snapshot import router as dataset_snapshot_router
from app.controller.v1.dataset.embargo import router as embargo_router
from app.controller.v1.dataset.embargo_status import router as embargo_status_router
from app.controller.v1.dataset.members_access import router as members_access_router
from app.controller.v1.dataset.share import router as share_router
from app.controller.v1.dataset.anonymous_link import router as anonymous_link_router
from app.controller.v1.invitation.invitation import router as invitation_router
from app.controller.v1.anonymous.anonymous import router as anonymous_router
from app.controller.v1.internal.dataset_collocation import (
    router as internal_dataset_collocation_router,
)
from app.controller.v1.internal.notification import (
    router as internal_notification_router,
)
from app.controller.v1.tus.tus import router as tus_router
from app.exception.bad_request import BadRequestException
from app.exception.forbidden import ForbiddenException
from app.exception.unauthorized import UnauthorizedException
from app.exception.not_found import NotFoundException
from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.too_many_requests import TooManyRequestsException
from app.controller.interceptor.exception_handler import (
    bad_request_exception_handler,
    conflict_exception_handler,
    forbidden_exception_handler,
    generic_exception_handler,
    illegal_state_exception_handler,
    not_found_exception_handler,
    request_validation_exception_handler,
    too_many_requests_exception_handler,
    unauthorized_exception_handler,
)


access_logger = logging.getLogger("http.access")


def parse_tenancies(header: str) -> list[str]:
    if not header:
        return []
    return [tenancy.strip() for tenancy in header.split(";") if tenancy.strip()]


# Enough for the metadata bodies this API takes; a larger one is summarised
# rather than logged.
MAX_LOGGED_BODY_BYTES = 8192


async def _body_for_log(request: Request) -> object:
    """The request body, if it is JSON and small enough to be worth a line.

    Headers are never logged: they carry X-Api-Secret and X-User-Token. The
    body can carry a credential too — POST /clients takes one — so it goes
    through the same redaction filter as everything else, by key.
    """
    if request.method in ("GET", "HEAD", "DELETE", "OPTIONS"):
        return None
    if not request.headers.get("content-type", "").startswith("application/json"):
        return None

    body = await request.body()
    if not body:
        return None
    if len(body) > MAX_LOGGED_BODY_BYTES:
        return {"omitted": "too large", "bytes": len(body)}
    try:
        return json.loads(body)
    except ValueError:
        return {"omitted": "not valid json", "bytes": len(body)}


# Polled on a timer, so an access line each would swamp the log. A degraded
# dependency writes its own WARNING regardless.
_PROBE_PATHS = frozenset(
    {
        "/v1/health-check/",
        "/api/v1/health-check/",
        "/v1/health-check/dependencies/",
        "/api/v1/health-check/dependencies/",
    }
)


def is_probe(path: str) -> bool:
    return path.rstrip("/") + "/" in _PROBE_PATHS


def setup_middleware(fastAPIApp: FastAPI) -> None:
    @fastAPIApp.middleware("http")
    async def assign_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid4())
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        started = perf_counter()
        body = await _body_for_log(request)
        try:
            with metrics.in_progress(request.method):
                response = await call_next(request)
        except Exception:
            # uvicorn's own line is emitted outside this context, without the id.
            _log_access(request, 500, started, body)
            request_id_var.reset(token)
            raise

        try:
            response.headers["X-Request-Id"] = request_id
            _log_access(
                request,
                response.status_code,
                started,
                body,
                response_bytes=_declared_length(response.headers),
            )
            return response
        finally:
            request_id_var.reset(token)


def route_of(request: Request) -> str:
    """The template the request matched, so ids never become label values."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path is None:
        return "unmatched"
    return request.scope.get("root_path", "") + path


def _declared_length(headers) -> int | None:
    try:
        return int(headers["content-length"])
    except (KeyError, ValueError):
        return None


def _log_access(
    request: Request,
    status_code: int,
    started: float,
    body: object = None,
    response_bytes: int | None = None,
) -> None:
    if is_probe(request.url.path):
        return

    elapsed = perf_counter() - started
    route = route_of(request)
    client = getattr(request.state, "client_name", None)
    metrics.request(
        request.method,
        route,
        status_code,
        elapsed,
        client=client,
        request_bytes=_declared_length(request.headers),
        response_bytes=response_bytes,
    )
    entry = fields(
        method=request.method,
        path=mask_path_tokens(request.url.path),
        route=route,
        client=client,
        status_code=status_code,
        duration_ms=round(elapsed * 1000, 1),
        # Identifiers, not credentials: who asked, and under which tenancy —
        # which together decide what the request could see.
        user_id=request.headers.get("x-user-id"),
        tenancies=parse_tenancies(request.headers.get("x-datamap-tenancies")),
    )
    if body is not None:
        entry["body"] = body
    access_logger.info("request", extra=entry)


def setup_routes(fastAPIApp: FastAPI) -> None:
    fastAPIApp.include_router(dataset_filter_router, prefix="/v1")
    fastAPIApp.include_router(dataset_router, prefix="/v1")
    fastAPIApp.include_router(share_router, prefix="/v1")
    fastAPIApp.include_router(anonymous_link_router, prefix="/v1")
    fastAPIApp.include_router(invitation_router, prefix="/v1")
    fastAPIApp.include_router(anonymous_router, prefix="/v1")
    fastAPIApp.include_router(dataset_snapshot_router, prefix="/v1")
    fastAPIApp.include_router(embargo_router, prefix="/v1")
    fastAPIApp.include_router(embargo_status_router, prefix="/v1")
    fastAPIApp.include_router(members_access_router, prefix="/v1")
    fastAPIApp.include_router(tenancies_router, prefix="/v1")
    fastAPIApp.include_router(user_router, prefix="/v1")
    fastAPIApp.include_router(tenancy_access_router, prefix="/v1")
    fastAPIApp.include_router(auth_router, prefix="/v1")
    fastAPIApp.include_router(client_router, prefix="/v1")
    fastAPIApp.include_router(infrastructure_router, prefix="/v1")
    fastAPIApp.include_router(infrastructure_protected_router, prefix="/v1")
    fastAPIApp.include_router(internal_dataset_collocation_router, prefix="/v1")
    fastAPIApp.include_router(internal_notification_router, prefix="/v1")
    fastAPIApp.include_router(admin_email_router, prefix="/v1")
    fastAPIApp.include_router(admin_tenancy_router, prefix="/v1")
    fastAPIApp.include_router(tus_router, prefix="/v1")


def setup_error_handlers(fastAPIApp: FastAPI) -> None:
    fastAPIApp.add_exception_handler(ConflictException, conflict_exception_handler)
    fastAPIApp.add_exception_handler(NotFoundException, not_found_exception_handler)
    fastAPIApp.add_exception_handler(
        UnauthorizedException, unauthorized_exception_handler
    )
    fastAPIApp.add_exception_handler(ForbiddenException, forbidden_exception_handler)
    fastAPIApp.add_exception_handler(
        IllegalStateException, illegal_state_exception_handler
    )
    fastAPIApp.add_exception_handler(BadRequestException, bad_request_exception_handler)
    fastAPIApp.add_exception_handler(
        TooManyRequestsException, too_many_requests_exception_handler
    )
    fastAPIApp.add_exception_handler(
        RequestValidationError, request_validation_exception_handler
    )
    fastAPIApp.add_exception_handler(Exception, generic_exception_handler)
