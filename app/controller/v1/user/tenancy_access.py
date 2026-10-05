from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize_self
from app.controller.v1.tenancy.access_resource import (
    TenancyRequestBody,
    TenancyRequestResponse,
    TenancySummaryResponse,
)
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_request import TenancyRequestService

router = APIRouter(
    prefix="/users",
    tags=["tenancy-access"],
    dependencies=[Depends(authenticate), Depends(authorize_self)],
)


@router.get("/{id}/tenancies", response_model=list[TenancySummaryResponse])
@inject
def my_tenancies(
    id: UUID,
    service: TenancyMembershipService = Depends(
        Provide[Container.tenancy_membership_service]
    ),
) -> list[TenancySummaryResponse]:
    return [TenancySummaryResponse.model_validate(s) for s in service.summaries_for(id)]


@router.get("/{id}/tenancy-requests", response_model=list[TenancyRequestResponse])
@inject
def my_requests(
    id: UUID,
    service: TenancyRequestService = Depends(
        Provide[Container.tenancy_request_service]
    ),
) -> list[TenancyRequestResponse]:
    return [TenancyRequestResponse.model_validate(v) for v in service.list_for_user(id)]


@router.post(
    "/{id}/tenancy-requests", status_code=201, response_model=TenancyRequestResponse
)
@inject
def request_access(
    id: UUID,
    body: TenancyRequestBody,
    service: TenancyRequestService = Depends(
        Provide[Container.tenancy_request_service]
    ),
) -> TenancyRequestResponse:
    return TenancyRequestResponse.model_validate(
        service.create(id, body.tenancy_name, body.reason)
    )


@router.delete("/{id}/tenancy-requests/{request_id}", status_code=204)
@inject
def withdraw_request(
    id: UUID,
    request_id: UUID,
    service: TenancyRequestService = Depends(
        Provide[Container.tenancy_request_service]
    ),
) -> Response:
    service.withdraw(id, request_id)
    return Response(status_code=204)
