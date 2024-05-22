import logging
from fastapi import FastAPI
from app.config import settings
from app.controller.v1.client.client import router as client_router
from app.controller.v1.infrastructure.infrastructure import (
    router as infrastructure_router,
)
from app.controller.v1.tenancy.tenancy import router as tenancies_router
from app.controller.v1.user.user import router as user_router
from app.controller.v1.dataset.dataset_filter import router as dataset_filter_router
from app.controller.v1.dataset.dataset import router as dataset_router
from app.controller.v1.tus.tus import router as tus_router
from app.exception.unauthorized import UnauthorizedException
from app.exception.not_found import NotFoundException
from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.controller.interceptor.exception_handler import (
    conflict_exception_handler,
    generic_exception_handler,
    illegal_state_exception_handler,
    not_found_exception_handler,
    unauthorized_exception_handler,
)


def setup_logging() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL)

    modules = [
        {"name": "uvicorn", "level": settings.LOG_LEVEL},
        {"name": "tests", "level": logging.INFO},
    ]
    for module in modules:
        logger = logging.getLogger(module["name"])
        logger.setLevel(module["level"])
        log_formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] " + " %(module)s - %(name)s: %(message)s"
        )
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)
        logger.addHandler(console_handler)


def setup_routes(fastAPIApp: FastAPI) -> None:
    fastAPIApp.include_router(dataset_filter_router, prefix="/v1")
    fastAPIApp.include_router(dataset_router, prefix="/v1")
    fastAPIApp.include_router(tenancies_router, prefix="/v1")
    fastAPIApp.include_router(user_router, prefix="/v1")
    fastAPIApp.include_router(client_router, prefix="/v1")
    fastAPIApp.include_router(infrastructure_router, prefix="/v1")
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
    fastAPIApp.add_exception_handler(Exception, generic_exception_handler)
