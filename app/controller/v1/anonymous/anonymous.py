from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.v1.dataset.share_resource import adapt_anonymous_page
from app.service.anonymous_link import AnonymousLinkService

router = APIRouter(
    prefix="/anonymous", tags=["anonymous"], dependencies=[Depends(authenticate)]
)


@router.get("/{token}")
@inject
def anonymous_page(
    token: str,
    service: AnonymousLinkService = Depends(Provide[Container.anonymous_link_service]),
) -> dict:
    return adapt_anonymous_page(service.view(token))
