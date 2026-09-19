from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.metrics import CONTENT_TYPE, metrics
from app.service.health import DependencyHealthService

router = APIRouter(prefix="/health-check", tags=["health-check"])

# The dependency report names what is reachable and how slowly; that is for the
# people who operate the system, not for the internet.
protected_router = APIRouter(
    prefix="/health-check",
    tags=["health-check"],
    dependencies=[Depends(authenticate), Depends(authorize)],
)


metrics_router = APIRouter(
    tags=["metrics"],
    dependencies=[Depends(authenticate), Depends(authorize)],
)


@metrics_router.get("/metrics")
async def prometheus_metrics():
    return Response(content=metrics.render(), media_type=CONTENT_TYPE)


@router.get("/")
async def health_check():
    """Liveness. Deliberately shallow: the deploy waits on this, and a degraded
    object storage must not stop a deploy that is fixing something else."""
    return JSONResponse(content={"status": "online"})


@protected_router.get("/dependencies")
@inject
async def dependencies(
    service: DependencyHealthService = Depends(
        Provide[Container.dependency_health_service]
    ),
):
    """What the API depends on, and whether it is answering. This is the page
    that distinguishes "the system is down" from "I hit a bug"."""
    report = service.check()
    return JSONResponse(
        content=report, status_code=200 if report["status"] == "healthy" else 503
    )
