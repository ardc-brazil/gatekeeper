from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize_self
from app.controller.v1.tenancy.access_resource import (
    AcceptedInvitationResponse,
    InviteeLookupResponse,
    TenancyInvitationResponse,
    TenancyRequestBody,
    TenancyRequestResponse,
    TenancySummaryResponse,
    UserIdBody,
    WorkspaceInvitationResponse,
    WorkspaceMemberPage,
)
from app.service.tenancy_invitation import TenancyInvitationService
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


@router.delete(
    "/{id}/tenancies/{path:path}/invitations/{invitation_id}", status_code=204
)
@inject
def withdraw_workspace_invitation(
    id: UUID,
    path: str,
    invitation_id: UUID,
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> Response:
    service.withdraw(id, path, invitation_id)
    return Response(status_code=204)


@router.get("/{id}/tenancies/{path:path}/members", response_model=WorkspaceMemberPage)
@inject
def workspace_members(
    id: UUID,
    path: str,
    limit: int = 50,
    offset: int = 0,
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> WorkspaceMemberPage:
    return WorkspaceMemberPage.model_validate(service.members(id, path, limit, offset))


@router.get(
    "/{id}/tenancies/{path:path}/invitations",
    response_model=list[WorkspaceInvitationResponse],
)
@inject
def workspace_invitations(
    id: UUID,
    path: str,
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> list[WorkspaceInvitationResponse]:
    return [
        WorkspaceInvitationResponse.model_validate(v)
        for v in service.pending_in(id, path)
    ]


@router.post(
    "/{id}/tenancies/{path:path}/invitations",
    status_code=201,
    response_model=WorkspaceInvitationResponse,
)
@inject
def invite_to_workspace(
    id: UUID,
    path: str,
    body: UserIdBody,
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> WorkspaceInvitationResponse:
    return WorkspaceInvitationResponse.model_validate(
        service.invite(id, path, body.user_id)
    )


@router.get("/{id}/tenancies/{path:path}/lookup", response_model=InviteeLookupResponse)
@inject
def lookup_invitee(
    id: UUID,
    path: str,
    value: str,
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> InviteeLookupResponse:
    return InviteeLookupResponse.model_validate(service.lookup(id, path, value))


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


@router.get("/{id}/tenancy-invitations", response_model=list[TenancyInvitationResponse])
@inject
def my_invitations(
    id: UUID,
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> list[TenancyInvitationResponse]:
    return [
        TenancyInvitationResponse.model_validate(v)
        for v in service.pending_for_user(id)
    ]


@router.post(
    "/{id}/tenancy-invitations/{invitation_id}/accept",
    response_model=AcceptedInvitationResponse,
)
@inject
def accept_invitation(
    id: UUID,
    invitation_id: UUID,
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> AcceptedInvitationResponse:
    return AcceptedInvitationResponse(
        tenancy=TenancySummaryResponse.model_validate(service.accept(id, invitation_id))
    )


@router.post("/{id}/tenancy-invitations/{invitation_id}/decline", status_code=204)
@inject
def decline_invitation(
    id: UUID,
    invitation_id: UUID,
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> Response:
    service.decline(id, invitation_id)
    return Response(status_code=204)
