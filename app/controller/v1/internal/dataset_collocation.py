from uuid import UUID
from fastapi import APIRouter, Depends
from dependency_injector.wiring import inject, Provide
from typing import List

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.v1.internal.resource import (
    DatasetPendingCollocationResponse,
    DataFileCollocationResponse,
    UpdateFilePathRequest,
    UpdateCollocationStatusRequest,
)
from app.service.dataset_collocation import DatasetCollocationService
from app.model.db.dataset import Dataset, DataFile


router = APIRouter(
    prefix="/internal/datasets",
    tags=["internal"],
    responses={404: {"description": "Not found"}},
)


@router.get(
    "/collocation/pending",
    dependencies=[Depends(authenticate)],
    response_model=List[DatasetPendingCollocationResponse],
)
@inject
async def get_pending_datasets(
    service: DatasetCollocationService = Depends(
        Provide[Container.dataset_collocation_service]
    ),
) -> List[DatasetPendingCollocationResponse]:
    """
    Get all datasets with file_collocation_status IS NULL or 'PENDING'.
    Used by archivist service to fetch datasets that need file collocation.
    """
    datasets = service.get_pending_datasets()

    return [
        DatasetPendingCollocationResponse(
            id=dataset.id,
            name=dataset.name,
            created_at=dataset.created_at,
            file_collocation_status=(
                dataset.file_collocation_status.value
                if dataset.file_collocation_status
                else None
            ),
            file_count=len(
                [
                    file
                    for version in dataset.versions
                    for file in version.files_in
                ]
            ),
        )
        for dataset in datasets
    ]


@router.get(
    "/{dataset_id}/files",
    dependencies=[Depends(authenticate)],
    response_model=List[DataFileCollocationResponse],
)
@inject
async def get_dataset_files(
    dataset_id: UUID,
    service: DatasetCollocationService = Depends(
        Provide[Container.dataset_collocation_service]
    ),
) -> List[DataFileCollocationResponse]:
    """
    Get all files for a specific dataset across all versions.
    Used by archivist service to fetch files that need to be moved.
    """
    files = service.get_dataset_files(dataset_id)

    return [
        DataFileCollocationResponse(
            id=file.id,
            name=file.name,
            size_bytes=file.size_bytes,
            storage_path=file.storage_path,
            storage_file_name=file.storage_file_name,
            extension=file.extension,
            format=file.format,
            created_at=file.created_at,
            created_by=file.created_by,
        )
        for file in files
    ]


@router.put(
    "/{dataset_id}/files/{file_id}",
    dependencies=[Depends(authenticate)],
    status_code=204,
)
@inject
async def update_file_path(
    dataset_id: UUID,
    file_id: UUID,
    payload: UpdateFilePathRequest,
    service: DatasetCollocationService = Depends(
        Provide[Container.dataset_collocation_service]
    ),
) -> None:
    """
    Update the storage_path for a specific file.
    Used by archivist service after moving a file to its new location.
    """
    service.update_file_path(file_id=file_id, new_path=payload.storage_path)


@router.put(
    "/{dataset_id}/collocation-status",
    dependencies=[Depends(authenticate)],
    status_code=204,
)
@inject
async def update_collocation_status(
    dataset_id: UUID,
    payload: UpdateCollocationStatusRequest,
    service: DatasetCollocationService = Depends(
        Provide[Container.dataset_collocation_service]
    ),
) -> None:
    """
    Update the file_collocation_status for a dataset.
    Used by archivist service to mark datasets as PROCESSING or COMPLETED.
    """
    service.update_collocation_status(dataset_id=dataset_id, status=payload.status)
