from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.dataset.share_resource import (
    AnonymousLinkResponse,
    CreateAnonymousLinkBody,
    adapt_anonymous_link,
)
from app.service.anonymous_link import AnonymousLinkService

router = APIRouter(
    prefix="/datasets",
    tags=["anonymous-links"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


@router.post(
    "/{dataset_id}/anonymous-links",
    status_code=201,
    response_model=AnonymousLinkResponse,
)
@inject
def create_anonymous_link(
    dataset_id: UUID,
    body: CreateAnonymousLinkBody,
    user_id: UUID = Depends(parse_user_header),
    service: AnonymousLinkService = Depends(Provide[Container.anonymous_link_service]),
) -> AnonymousLinkResponse:
    view, url = service.create(dataset_id, user_id, body.label)
    return adapt_anonymous_link(view, url)


@router.delete("/{dataset_id}/anonymous-links/{link_id}", status_code=204)
@inject
def revoke_anonymous_link(
    dataset_id: UUID,
    link_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: AnonymousLinkService = Depends(Provide[Container.anonymous_link_service]),
) -> Response:
    service.revoke(dataset_id, user_id, link_id)
    return Response(status_code=204)
