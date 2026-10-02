from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.tenancy_parser import parse_tenancy_header
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.dataset.resource import (
    AccessResponse,
    MembersAccessRequest,
    MembersAccessResponse,
)
from app.service.members_access import MembersAccessService

router = APIRouter(
    prefix="/datasets",
    tags=["members-access"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


# PUT /datasets/{dataset_id}/members-access
@router.put("/{dataset_id}/members-access")
@inject
def set_members_access(
    dataset_id: UUID,
    request: MembersAccessRequest,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: MembersAccessService = Depends(Provide[Container.members_access_service]),
) -> MembersAccessResponse:
    result = service.set(
        dataset_id=dataset_id,
        user_id=user_id,
        tenancies=tenancies,
        members_can_edit=request.members_can_edit,
    )
    return MembersAccessResponse(
        members_can_edit=result.members_can_edit,
        access=AccessResponse(
            level=result.access.level.value,
            can_edit=result.access.can_edit,
            can_share=result.access.can_share,
            can_manage_embargo=result.access.can_manage_embargo,
            can_extend_embargo=result.access.can_extend_embargo,
            can_delete=result.access.can_delete,
        ),
    )
