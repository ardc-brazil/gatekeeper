from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.dataset.share_resource import (
    AcceptInvitationBody,
    AcceptResultResponse,
    ClaimResponse,
    InvitationPreviewResponse,
    adapt_invitation_preview,
)
from app.service.share import ShareService

router = APIRouter(tags=["invitations"], dependencies=[Depends(authenticate)])


@router.get("/invitations/{token}", response_model=InvitationPreviewResponse)
@inject
def preview_invitation(
    token: str,
    service: ShareService = Depends(Provide[Container.share_service]),
) -> InvitationPreviewResponse:
    return adapt_invitation_preview(service.preview(token))


@router.post("/invitations/accept", response_model=AcceptResultResponse)
@inject
def accept_invitation(
    body: AcceptInvitationBody,
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> AcceptResultResponse:
    result = service.accept(body.token, user_id)
    return AcceptResultResponse(dataset_id=result.dataset_id, level=result.level)


@router.post("/users/{user_id}/invitations/claim", response_model=ClaimResponse)
@inject
def claim_invitations(
    user_id: UUID,
    service: ShareService = Depends(Provide[Container.share_service]),
) -> ClaimResponse:
    return ClaimResponse(
        accepted=[
            AcceptResultResponse(dataset_id=result.dataset_id, level=result.level)
            for result in service.claim(user_id)
        ]
    )
