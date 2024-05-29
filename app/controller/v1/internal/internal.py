from uuid import UUID
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.service.dataset import DatasetService

from dependency_injector.wiring import inject, Provide

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[
        Depends(authenticate)
    ],  # TODO add internal authentication, maybe a new column in clients table
    responses={404: {"description": "Not found"}},
)


# POST /datasets/:dataset_id/versions/:version/files/zip/:zip_id
@router.post("/datasets/{dataset_id}/versions/{version_name}/files/zip/{zip_id}")
@inject
async def zip_callback(
    dataset_id: str,
    version_name: str,
    zip_id: UUID,
    zip_callback: dict,
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> None:
    service.update_zip_status(
        dataset_id=dataset_id,
        version_name=version_name,
        zip_id=zip_id,
        zip_status=zip_callback["status"],
    )
    return {}
