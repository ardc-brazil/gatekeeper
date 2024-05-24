from fastapi import APIRouter, Depends
from app.container import Container
from dependency_injector.wiring import inject, Provide

from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.service.dataset import DatasetService

router = APIRouter(
    prefix="/datasets",
    tags=["datasets"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


# GET /filters
@router.get("/filters")
@inject
async def get_filters(
    service: DatasetService = Depends(Provide[Container.dataset_service]),
):
    return service.fetch_available_filters()
