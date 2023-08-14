from fastapi import APIRouter, Depends
from app.services.infrastructure import InfrastructureService
from dependency_injector.wiring import inject, Provide
from app.config.container import Container

router = APIRouter(
    prefix="/health-check",
)

# @router.get("/")
# @inject
# async def root(infrastructure_service: InfrastructureService = Depends(Provide[Container.infrastructure_service])):
#     return infrastructure_service.health_check()

@router.get('')
async def root():
    return "success"