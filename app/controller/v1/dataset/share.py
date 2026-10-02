from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.dataset.share_resource import (
    GrantRequestBody,
    GrantResultResponse,
    LinkResponse,
    PermissionResponse,
    ShareStateResponse,
    ShareUserResponse,
    UpdatePermissionBody,
    adapt_grant_result,
    adapt_permission,
    adapt_share_state,
    adapt_user,
)
from app.model.sharing import GrantRequest
from app.service.share import ShareService

router = APIRouter(
    prefix="/datasets",
    tags=["sharing"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


@router.get("/{dataset_id}/share/candidates", response_model=list[ShareUserResponse])
@inject
def share_candidates(
    dataset_id: UUID,
    q: str = "",
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> list[ShareUserResponse]:
    return [adapt_user(user) for user in service.candidates(dataset_id, user_id, q)]


@router.get("/{dataset_id}/share", response_model=ShareStateResponse)
@inject
def share_state(
    dataset_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> ShareStateResponse:
    return adapt_share_state(service.state(dataset_id, user_id))


@router.post(
    "/{dataset_id}/share",
    status_code=201,
    response_model=GrantResultResponse,
    response_model_exclude_unset=True,
)
@inject
def grant(
    dataset_id: UUID,
    body: GrantRequestBody,
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> GrantResultResponse:
    result = service.grant(
        dataset_id,
        user_id,
        GrantRequest(
            level=body.level, user_id=body.user_id, email=body.email, orcid=body.orcid
        ),
    )
    return adapt_grant_result(result)


@router.put(
    "/{dataset_id}/share/permissions/{target_user_id}",
    response_model=PermissionResponse,
)
@inject
def update_permission(
    dataset_id: UUID,
    target_user_id: UUID,
    body: UpdatePermissionBody,
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> PermissionResponse:
    return adapt_permission(
        service.update_permission(dataset_id, user_id, target_user_id, body.level)
    )


@router.delete("/{dataset_id}/share/permissions/{target_user_id}", status_code=204)
@inject
def revoke_permission(
    dataset_id: UUID,
    target_user_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> Response:
    service.revoke_permission(dataset_id, user_id, target_user_id)
    return Response(status_code=204)


@router.delete("/{dataset_id}/share/invitations/{invitation_id}", status_code=204)
@inject
def revoke_invitation(
    dataset_id: UUID,
    invitation_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> Response:
    service.revoke_invitation(dataset_id, user_id, invitation_id)
    return Response(status_code=204)


@router.post(
    "/{dataset_id}/share/invitations/{invitation_id}/link",
    response_model=LinkResponse,
)
@inject
def regenerate_invitation_link(
    dataset_id: UUID,
    invitation_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> LinkResponse:
    return LinkResponse(
        link=service.regenerate_link(dataset_id, user_id, invitation_id)
    )
