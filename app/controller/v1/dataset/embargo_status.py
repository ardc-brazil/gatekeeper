from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.v1.dataset.resource import EmbargoStatusResponse
from app.service.embargo import EmbargoService

router = APIRouter(prefix="/datasets", tags=["embargo"])


# GET /datasets/{dataset_id}/embargo-status
@router.get("/{dataset_id}/embargo-status", dependencies=[Depends(authenticate)])
@inject
def get_embargo_status(
    dataset_id: UUID,
    version: str | None = None,
    service: EmbargoService = Depends(Provide[Container.embargo_service]),
) -> EmbargoStatusResponse:
    embargoed, until, doi = service.status_with_doi(dataset_id, version)
    return EmbargoStatusResponse(embargoed=embargoed, until=until, doi=doi)
