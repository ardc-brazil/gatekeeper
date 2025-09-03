from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from app.container import Container
from dependency_injector.wiring import inject, Provide

from app.controller.v1.dataset.resource import (
    DatasetSnapshotResponse,
    DatasetLatestSnapshotResponse,
    DatasetVersionInfo,
)
from app.service.dataset import DatasetService
from app.exception.not_found import NotFoundException
from app.exception.illegal_state import IllegalStateException


router = APIRouter(
    prefix="/datasets",
    tags=["dataset-snapshots"],
    responses={404: {"description": "Snapshot not found"}},
)


def _adapt_snapshot_response(snapshot_data: dict) -> DatasetSnapshotResponse:
    """Adapt snapshot JSON data to DatasetSnapshotResponse"""
    # Extract typed fields
    dataset_id = snapshot_data.get("dataset_id")
    version_name = snapshot_data.get("version_name")
    doi_identifier = snapshot_data.get("doi_identifier")
    doi_link = snapshot_data.get("doi_link")
    doi_state = snapshot_data.get("doi_state")
    publication_date = snapshot_data.get("publication_date")
    files_summary = snapshot_data.get("files_summary", {})

    # Create a copy for data without the typed fields
    data = {
        k: v
        for k, v in snapshot_data.items()
        if k
        not in [
            "dataset_id",
            "version_name",
            "doi_identifier",
            "doi_link",
            "doi_state",
            "publication_date",
            "files_summary",
            "versions",
        ]
    }

    return DatasetSnapshotResponse(
        dataset_id=dataset_id,
        version_name=version_name,
        doi_identifier=doi_identifier,
        doi_link=doi_link,
        doi_state=doi_state,
        publication_date=publication_date,
        files_summary=files_summary,
        data=data,
    )


def _adapt_latest_snapshot_response(
    snapshot_data: dict,
) -> DatasetLatestSnapshotResponse:
    """Adapt latest snapshot JSON data to DatasetLatestSnapshotResponse"""
    # Extract typed fields
    dataset_id = snapshot_data.get("dataset_id")
    version_name = snapshot_data.get("version_name")
    doi_identifier = snapshot_data.get("doi_identifier")
    doi_link = snapshot_data.get("doi_link")
    doi_state = snapshot_data.get("doi_state")
    publication_date = snapshot_data.get("publication_date")
    files_summary = snapshot_data.get("files_summary", {})
    versions_raw = snapshot_data.get("versions", [])

    # Convert versions to typed objects
    versions = [
        DatasetVersionInfo(
            id=v.get("id"),
            name=v.get("name"),
            doi_identifier=v.get("doi_identifier"),
            doi_state=v.get("doi_state"),
            created_at=v.get("created_at"),
        )
        for v in versions_raw
    ]

    # Create a copy for data without the typed fields
    data = {
        k: v
        for k, v in snapshot_data.items()
        if k
        not in [
            "dataset_id",
            "version_name",
            "doi_identifier",
            "doi_link",
            "doi_state",
            "publication_date",
            "files_summary",
            "versions",
        ]
    }

    return DatasetLatestSnapshotResponse(
        dataset_id=dataset_id,
        version_name=version_name,
        doi_identifier=doi_identifier,
        doi_link=doi_link,
        doi_state=doi_state,
        publication_date=publication_date,
        files_summary=files_summary,
        data=data,
        versions=versions,
    )


# GET /datasets/{dataset_id}/snapshot
@router.get("/{dataset_id}/snapshot", response_model=DatasetLatestSnapshotResponse)
@inject
async def get_dataset_latest_snapshot(
    dataset_id: UUID,
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> DatasetLatestSnapshotResponse:
    """
    Get the latest published snapshot of a dataset.

    This endpoint returns the most recent published version of the dataset
    along with a list of all published versions.

    TODO: Add rate limiting for public endpoints to prevent abuse
    """
    try:
        snapshot_data = service.get_dataset_latest_snapshot(dataset_id)
        return _adapt_latest_snapshot_response(snapshot_data)
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    except IllegalStateException:
        raise HTTPException(status_code=500, detail="Invalid snapshot data")


# GET /datasets/{dataset_id}/versions/{version_name}/snapshot
@router.get(
    "/{dataset_id}/versions/{version_name}/snapshot",
    response_model=DatasetSnapshotResponse,
)
@inject
async def get_dataset_version_snapshot(
    dataset_id: UUID,
    version_name: str,
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> DatasetSnapshotResponse:
    """
    Get a specific version snapshot of a dataset.

    This endpoint returns the metadata for a specific published version
    of the dataset.

    TODO: Add rate limiting for public endpoints to prevent abuse
    """
    try:
        snapshot_data = service.get_dataset_version_snapshot(dataset_id, version_name)
        return _adapt_snapshot_response(snapshot_data)
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    except IllegalStateException:
        raise HTTPException(status_code=500, detail="Invalid snapshot data")
