from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.tenancy.access_resource import (
    AdminTenancyRequestDetailResponse,
    AdminTenancyRequestPage,
    AdminTenancyRequestResponse,
    ApproveBody,
    DeclineBody,
    RequestCountsResponse,
)
from app.model.tenancy_access import NewTenancy
from app.service.tenancy_request import TenancyRequestService

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


@router.get("/tenancy-requests/counts", response_model=RequestCountsResponse)
@inject
def request_counts(
    service: TenancyRequestService = Depends(
        Provide[Container.tenancy_request_service]
    ),
) -> RequestCountsResponse:
    return RequestCountsResponse.model_validate(service.counts())


@router.get("/tenancy-requests", response_model=AdminTenancyRequestPage)
@inject
def list_requests(
    status: str = "open",
    kind: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    service: TenancyRequestService = Depends(
        Provide[Container.tenancy_request_service]
    ),
) -> AdminTenancyRequestPage:
    return AdminTenancyRequestPage.model_validate(
        service.queue(status, kind, q, limit, offset)
    )


@router.get(
    "/tenancy-requests/{request_id}", response_model=AdminTenancyRequestDetailResponse
)
@inject
def request_detail(
    request_id: UUID,
    service: TenancyRequestService = Depends(
        Provide[Container.tenancy_request_service]
    ),
) -> AdminTenancyRequestDetailResponse:
    return AdminTenancyRequestDetailResponse.model_validate(service.detail(request_id))


@router.post(
    "/tenancy-requests/{request_id}/approve", response_model=AdminTenancyRequestResponse
)
@inject
def approve_request(
    request_id: UUID,
    body: ApproveBody,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyRequestService = Depends(
        Provide[Container.tenancy_request_service]
    ),
) -> AdminTenancyRequestResponse:
    new_tenancy = (
        NewTenancy(
            display_name=body.new_tenancy.display_name,
            namespace=body.new_tenancy.namespace,
        )
        if body.new_tenancy is not None
        else None
    )
    return AdminTenancyRequestResponse.model_validate(
        service.approve(request_id, user_id, body.tenancy, new_tenancy)
    )


@router.post(
    "/tenancy-requests/{request_id}/decline", response_model=AdminTenancyRequestResponse
)
@inject
def decline_request(
    request_id: UUID,
    body: DeclineBody | None = None,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyRequestService = Depends(
        Provide[Container.tenancy_request_service]
    ),
) -> AdminTenancyRequestResponse:
    return AdminTenancyRequestResponse.model_validate(
        service.decline(request_id, user_id, body.message if body else None)
    )
