import uvicorn
from fastapi import FastAPI

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
from app.container import Container

from app.controller.v1.client.client import router as client_router
from app.controller.v1.infrastructure.infrastructure import (
    router as infrastructure_router,
)
from app.controller.v1.tenancy.tenancy import router as tenancies_router
from app.controller.v1.user.user import router as user_router
from app.controller.v1.dataset.dataset_filter import router as dataset_filter_router
from app.controller.v1.dataset.dataset import router as dataset_router

container = Container()

# Create database
db = container.db()
db.create_database()

# Setup casbin auto reload policy
# casbin_enforcer = container.casbin_enforcer()
# casbin_enforcer.enable_auto_build_role_links(True)
# casbin_enforcer.start_auto_load_policy(5)  # reload policy every 5 seconds

app = FastAPI(
    title="Gatekeeper API",
    description="Gatekeeper API is the main backend for DataMap",
    version="0.0.1",
    redirect_slashes=True,
    root_path="/api",
)

app.container = container

# API routes
app.include_router(dataset_router, prefix="/v1")
app.include_router(dataset_filter_router, prefix="/v1")
app.include_router(tenancies_router, prefix="/v1")
app.include_router(user_router, prefix="/v1")
app.include_router(client_router, prefix="/v1")
app.include_router(infrastructure_router, prefix="/v1")

app.add_exception_handler(ConflictException, conflict_exception_handler)
app.add_exception_handler(NotFoundException, not_found_exception_handler)
app.add_exception_handler(UnauthorizedException, unauthorized_exception_handler)
app.add_exception_handler(IllegalStateException, illegal_state_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Migrate(app, db)

# db.init_app(app)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="localhost",
        port=9092,
    )
