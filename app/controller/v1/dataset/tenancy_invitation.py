from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.tenancy.access_resource import (
    DatasetTenancyInvitationResponse,
    ShareLookupResponse,
    UserIdBody,
)
from app.service.tenancy_invitation import TenancyInvitationService

router = APIRouter(
    prefix="/datasets",
    tags=["tenancy-invitations"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


@router.get("/{dataset_id}/share/lookup", response_model=ShareLookupResponse)
@inject
def share_lookup(
    dataset_id: UUID,
    value: str,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> ShareLookupResponse:
    return ShareLookupResponse.model_validate(
        service.lookup(dataset_id, user_id, value)
    )


@router.post(
    "/{dataset_id}/tenancy-invitations",
    status_code=201,
    response_model=DatasetTenancyInvitationResponse,
)
@inject
def invite_to_tenancy(
    dataset_id: UUID,
    body: UserIdBody,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> DatasetTenancyInvitationResponse:
    return DatasetTenancyInvitationResponse.model_validate(
        service.invite(dataset_id, user_id, body.user_id)
    )


@router.delete("/{dataset_id}/tenancy-invitations/{invitation_id}", status_code=204)
@inject
def withdraw_tenancy_invitation(
    dataset_id: UUID,
    invitation_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> Response:
    service.withdraw(dataset_id, user_id, invitation_id)
    return Response(status_code=204)
