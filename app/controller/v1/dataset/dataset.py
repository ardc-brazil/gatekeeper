from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from app.container import Container
from dependency_injector.wiring import inject, Provide

from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.tenancy_parser import parse_tenancy_header
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.dataset.resource import (
    DOIChangeStateRequest,
    DOIChangeStateResponse,
    DOICreateRequest,
    DOICreateResponse,
    DOIResponse,
    DataFileDownloadResponse,
    DataFileResponse,
    DatasetCreateRequest,
    DatasetCreateResponse,
    DatasetGetResponse,
    DatasetUpdateRequest,
    DatasetVersionCreateRequest,
    DatasetVersionCreateResponse,
    DatasetVersionGetResponse,
    DatasetVersionResponse,
    PagedDatasetGetResponse,
)
from app.model.dataset import (
    DataFile,
    Dataset,
    DatasetQuery,
    DatasetVersion,
    DesignState,
)
from app.model.doi import DOI, State as DOIState, Mode as DOIMode
from app.service.dataset import DatasetService


router = APIRouter(
    prefix="/datasets",
    tags=["datasets"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


def _adapt_data_file(file: DataFile) -> DataFileResponse:
    return DataFileResponse(
        id=file.id,
        name=file.name,
        size_bytes=file.size_bytes,
        extension=file.extension,
        format=file.format,
        storage_file_name=file.storage_file_name,
        storage_path=file.storage_path,
        updated_at=file.updated_at,
        created_at=file.created_at,
        created_by=file.created_by,
    )


def _adapt_dataset_version(version: DatasetVersion) -> DatasetVersionResponse:
    return DatasetVersionResponse(
        id=version.id,
        name=version.name,
        design_state=version.design_state.name,
        is_enabled=version.is_enabled,
        files=[_adapt_data_file(file) for file in version.files_in],
        files_in=[_adapt_data_file(file) for file in version.files_in],
        doi=DOIResponse(
            identifier=version.doi.identifier,
            state=version.doi.state.name,
            mode=version.doi.mode.name,
        )
        if version.doi is not None
        else None,
        created_at=version.created_at,
        updated_at=version.updated_at,
        files_size_in_bytes=version.files_size_in_bytes,
        files_count=version.files_count,
    )


def _adapt_minimal_dataset_version(version: DatasetVersion) -> DatasetVersionResponse:
    return DatasetVersionResponse(
        id=version.id,
        name=version.name,
        design_state=version.design_state.name,
        is_enabled=version.is_enabled,
        doi=DOIResponse(
            identifier=version.doi.identifier,
            state=version.doi.state.name,
            mode=version.doi.mode.name,
        )
        if version.doi is not None
        else None,
        created_at=version.created_at,
        updated_at=version.updated_at,
        files_size_in_bytes=version.files_size_in_bytes,
        files_count=version.files_count,
    )


def _adapt_dataset_version_creation(
    version: DatasetVersion,
) -> DatasetVersionCreateResponse:
    return _adapt_dataset_version(version=version)


def _adapt_dataset(dataset: Dataset) -> DatasetGetResponse:
    return DatasetGetResponse(
        id=dataset.id,
        name=dataset.name,
        data=dataset.data,
        tenancy=dataset.tenancy,
        is_enabled=dataset.is_enabled,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        versions=[_adapt_dataset_version(version) for version in dataset.versions],
        current_version=_adapt_dataset_version(dataset.current_version)
        if dataset.current_version is not None
        else None,
        design_state=dataset.design_state.name,
    )


def _adapt_minimal_dataset(dataset: Dataset) -> DatasetGetResponse:
    return DatasetGetResponse(
        id=dataset.id,
        name=dataset.name,
        data=dataset.data,
        tenancy=dataset.tenancy,
        is_enabled=dataset.is_enabled,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        versions=[
            _adapt_minimal_dataset_version(version) for version in dataset.versions
        ],
        current_version=_adapt_minimal_dataset_version(dataset.current_version)
        if dataset.current_version is not None
        else None,
        design_state=dataset.design_state.name,
    )


def _adapt_dataset_specific_version(dataset: Dataset) -> DatasetGetResponse:
    return DatasetVersionGetResponse(
        id=dataset.id,
        name=dataset.name,
        data=dataset.data,
        tenancy=dataset.tenancy,
        is_enabled=dataset.is_enabled,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        version=_adapt_dataset_version(dataset.version),
        design_state=dataset.design_state.name,
    )


# GET /datasets
@router.get("/")
@inject
async def get_datasets(
    categories: str = None,
    level: str = None,
    data_types: str = None,
    date_from: datetime = None,
    date_to: datetime = None,
    full_text: str = None,
    include_disabled: bool = False,
    design_state: str = None,
    version: str = None,
    minimal: bool = False,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> PagedDatasetGetResponse:
    # check if categories exists, then split by comma
    query = DatasetQuery(
        categories=categories.split(",") if categories else [],
        level=level,
        data_types=data_types.split(",") if data_types else [],
        date_from=date_from,
        date_to=date_to,
        full_text=full_text,
        include_disabled=include_disabled,
        version=version,
        design_state=design_state,
        minimal=minimal,
    )

    datasets: list[Dataset] = service.search_datasets(
        query=query, user_id=user_id, tenancies=tenancies
    )

    if minimal:
        content = [_adapt_minimal_dataset(dataset) for dataset in datasets]
        return PagedDatasetGetResponse(content=content, size=len(content))

    content = [_adapt_dataset(dataset) for dataset in datasets]
    return PagedDatasetGetResponse(content=content, size=len(content))


# GET /datasets/{id}
@router.get("/{id}")
@inject
async def get_dataset(
    id: str,
    response: Response,
    user_id: UUID = Depends(parse_user_header),
    is_enabled: bool = True,
    latest_version: bool = False,
    version_design_state: DesignState = DesignState.DRAFT,
    version_is_enabled: bool = True,
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> DatasetGetResponse:
    dataset = service.fetch_dataset(
        dataset_id=id,
        is_enabled=is_enabled,
        user_id=user_id,
        tenancies=tenancies,
        latest_version=latest_version,
        version_design_state=version_design_state,
        version_is_enabled=version_is_enabled,
    )

    if dataset is not None:
        return _adapt_dataset(dataset)
    else:
        response.status_code = 404
        return response


# PUT /datasets/{id}
@router.put("/{id}")
@inject
async def update_dataset(
    id: str,
    dataset_request: DatasetUpdateRequest,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> None:
    service.update_dataset(
        dataset_id=id,
        dataset_request=Dataset(
            id=id,
            name=dataset_request.name,
            data=dataset_request.data,
            tenancy=dataset_request.tenancy,
        ),
        user_id=user_id,
        tenancies=tenancies,
    )
    return {}


# DELETE /datasets/{id}
@router.delete("/{id}")
@inject
async def delete_dataset(
    id: str,
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> None:
    service.disable_dataset(dataset_id=id, tenancies=tenancies)
    return {}


# POST /datasets
@router.post("/", status_code=201)
@inject
async def create_dataset(
    dataset_request: DatasetCreateRequest,
    user_id: UUID = Depends(parse_user_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> DatasetCreateResponse:
    created = service.create_dataset(
        dataset=Dataset(
            name=dataset_request.name,
            data=dataset_request.data,
            tenancy=dataset_request.tenancy,
        ),
        user_id=user_id,
    )

    return DatasetCreateResponse(
        id=created.id,
        name=created.name,
        data=created.data,
        design_state=created.design_state.name,
        tenancy=created.tenancy,
        versions=[_adapt_dataset_version(version) for version in created.versions],
        current_version=_adapt_dataset_version(created.current_version),
    )


# PUT /datasets/:dataset_id/enable
@router.put("/{id}/enable")
@inject
async def enable_dataset(
    id: str,
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> None:
    service.enable_dataset(dataset_id=id, tenancies=tenancies)
    return {}


# DELETE /datasets/:dataset_id/versions/:version
@router.delete("/{dataset_id}/versions/{version_name}")
@inject
async def delete_dataset_version(
    dataset_id: str,
    version_name: str,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> None:
    service.disable_dataset_version(
        dataset_id=dataset_id,
        user_id=user_id,
        version_name=version_name,
        tenancies=tenancies,
    )
    return {}


# PUT /datasets/:dataset_id/versions/:version/publish
@router.put("/{dataset_id}/versions/{version_name}/publish")
@inject
async def publish_dataset_version(
    dataset_id: str,
    version_name: str,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> None:
    service.publish_dataset_version(
        dataset_id=dataset_id,
        user_id=user_id,
        version_name=version_name,
        tenancies=tenancies,
    )
    return {}


# PUT /datasets/:dataset_id/versions/:version/enable
@router.put("/{dataset_id}/versions/{version_name}/enable")
@inject
async def enable_dataset_version(
    dataset_id: str,
    version_name: str,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> None:
    service.enable_dataset_version(
        dataset_id=dataset_id,
        user_id=user_id,
        version_name=version_name,
        tenancies=tenancies,
    )
    return {}


# PUT /datasets/:dataset_id/versions/:version/doi
@router.put("/{dataset_id}/versions/{version_name}/doi")
@inject
async def change_doi_state(
    dataset_id: str,
    version_name: str,
    change_state_request: DOIChangeStateRequest,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> DOIChangeStateResponse:
    service.change_doi_state(
        dataset_id=dataset_id,
        version_name=version_name,
        new_state=DOIState[change_state_request.state.upper()],
        user_id=user_id,
        tenancies=tenancies,
    )

    return DOIChangeStateResponse(new_state=change_state_request.state)


# POST /datasets/:dataset_id/versions/:version/doi
@router.post("/{dataset_id}/versions/{version_name}/doi")
@inject
async def create_doi(
    dataset_id: UUID,
    version_name: str,
    create_doi_request: DOICreateRequest,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> DOICreateResponse:
    res = service.create_doi(
        dataset_id=dataset_id,
        version_name=version_name,
        doi=DOI(
            identifier=create_doi_request.identifier,
            mode=DOIMode[create_doi_request.mode],
        ),
        user_id=user_id,
        tenancies=tenancies,
    )

    return DOICreateResponse(
        identifier=res.identifier, state=res.state.name, mode=res.mode.name
    )


# GET /datasets/:dataset_id/versions/:version/doi
@router.get("/{dataset_id}/versions/{version_name}/doi")
@inject
async def get_doi(
    dataset_id: str,
    version_name: str,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> DOIResponse:
    res: DOI = service.get_doi(
        dataset_id=dataset_id,
        version_name=version_name,
        user_id=user_id,
        tenancies=tenancies,
    )
    return DOIResponse(
        identifier=res.identifier, state=res.state.name, mode=res.mode.name
    )


# DELETE /datasets/:dataset_id/versions/:version/doi
@router.delete("/{dataset_id}/versions/{version_name}/doi", status_code=204)
@inject
async def delete_doi(
    dataset_id: str,
    version_name: str,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> None:
    service.delete_doi(
        dataset_id=dataset_id,
        version_name=version_name,
        user_id=user_id,
        tenancies=tenancies,
    )
    return {}


# GET /datasets/:dataset_id/versions/:version/files/:file_id
@router.get("/{dataset_id}/versions/{version_name}/files/{file_id}")
@inject
async def get_file_download_url(
    dataset_id: UUID,
    version_name: str,
    file_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> DataFileDownloadResponse:
    file = service.get_file_download_url(
        dataset_id=dataset_id,
        version_name=version_name,
        file_id=file_id,
        user_id=user_id,
        tenancies=tenancies,
    )
    return DataFileDownloadResponse(url=file)


# POST /datasets/:dataset_id/versions
@router.post("/{dataset_id}/versions")
@inject
async def create_dataset_version(
    dataset_id: UUID,
    dataset_request: DatasetVersionCreateRequest,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> DatasetVersionCreateResponse:
    new_version = service.create_new_version(
        dataset_id=dataset_id,
        datafilesPreviouslyUploaded=dataset_request.datafilesPreviouslyUploaded,
        user_id=user_id,
        tenancies=tenancies,
    )

    return _adapt_dataset_version_creation(version=new_version)


# GET /datasets/:dataset_id/versions/:version
@router.get("/{dataset_id}/versions/{version_name}")
@inject
async def get_dataset_version(
    dataset_id: UUID,
    version_name: str,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> DatasetVersionGetResponse:
    res = service.fetch_dataset_version(
        dataset_id=dataset_id,
        version_name=version_name,
        user_id=user_id,
        tenancies=tenancies,
    )
    return _adapt_dataset_specific_version(dataset=res)
