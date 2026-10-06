from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.tenancy.access_resource import (
    AdminTenancyRequestDetailResponse,
    AdminTenancyRequestPage,
    AdminTenancyRequestResponse,
    AdminTenancyResponse,
    ApproveBody,
    DeclineBody,
    RemovalImpactResponse,
    RequestCountsResponse,
    TenancyCreateBody,
    TenancyMemberResponse,
    TenancyMembersResponse,
    UserBriefResponse,
    UserIdBody,
)
from app.model.tenancy_access import NewTenancy
from app.service.tenancy_admin import TenancyAdminService
from app.service.tenancy_invitation import TenancyInvitationService
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


@router.delete("/tenancy-invitations/{invitation_id}", status_code=204)
@inject
def withdraw_invitation(
    invitation_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> Response:
    service.withdraw_as_admin(invitation_id, user_id)
    return Response(status_code=204)


@router.get("/tenancies", response_model=list[AdminTenancyResponse])
@inject
def list_tenancies(
    service: TenancyAdminService = Depends(Provide[Container.tenancy_admin_service]),
) -> list[AdminTenancyResponse]:
    return [AdminTenancyResponse.model_validate(v) for v in service.list()]


@router.post("/tenancies", status_code=201, response_model=AdminTenancyResponse)
@inject
def create_tenancy(
    body: TenancyCreateBody,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyAdminService = Depends(Provide[Container.tenancy_admin_service]),
) -> AdminTenancyResponse:
    return AdminTenancyResponse.model_validate(
        service.create(user_id, body.display_name, body.namespace)
    )


@router.get(
    "/tenancies/{path:path}/members/{member_id}", response_model=RemovalImpactResponse
)
@inject
def removal_impact(
    path: str,
    member_id: UUID,
    service: TenancyAdminService = Depends(Provide[Container.tenancy_admin_service]),
) -> RemovalImpactResponse:
    return RemovalImpactResponse.model_validate(service.removal_impact(path, member_id))


@router.delete("/tenancies/{path:path}/members/{member_id}", status_code=204)
@inject
def remove_member(
    path: str,
    member_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyAdminService = Depends(Provide[Container.tenancy_admin_service]),
) -> Response:
    service.remove(path, member_id, user_id)
    return Response(status_code=204)


@router.get("/tenancies/{path:path}/members", response_model=TenancyMembersResponse)
@inject
def list_members(
    path: str,
    limit: int = 50,
    offset: int = 0,
    service: TenancyAdminService = Depends(Provide[Container.tenancy_admin_service]),
) -> TenancyMembersResponse:
    return TenancyMembersResponse.model_validate(service.members(path, limit, offset))


@router.post(
    "/tenancies/{path:path}/members",
    status_code=201,
    response_model=TenancyMemberResponse,
)
@inject
def add_member(
    path: str,
    body: UserIdBody,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyAdminService = Depends(Provide[Container.tenancy_admin_service]),
) -> TenancyMemberResponse:
    return TenancyMemberResponse.model_validate(
        service.add(path, body.user_id, user_id)
    )


@router.get("/users", response_model=list[UserBriefResponse])
@inject
def search_users(
    q: str = "",
    service: TenancyAdminService = Depends(Provide[Container.tenancy_admin_service]),
) -> list[UserBriefResponse]:
    return [UserBriefResponse.model_validate(hit) for hit in service.search_users(q)]
