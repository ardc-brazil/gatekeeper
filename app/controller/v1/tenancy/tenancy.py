from typing import Union
from fastapi import APIRouter, Depends, HTTPException, Response

from app.model.tenancy import Tenancy
from app.container import Container
from controllers.interceptor.authentication import fastapi_authenticate
from controllers.interceptor.authorization import fastapi_authorize
from app.controllers.v1.tenancy.resource import TenancyCreateRequest, TenancyGetResponse, TenancyUpdateRequest
from app.service.tenancy import TenancyService

from dependency_injector.wiring import inject, Provide

router = APIRouter(
    prefix="/tenancies",
    tags=["tenancies"],
    dependencies=[Depends(fastapi_authenticate), Depends(fastapi_authorize)],
    responses={404: {"description": "Not found"}},
)

# GET /tenancies
@router.get("/")
@inject
async def get_all(
    service: TenancyService = Depends(Provide[Container.tenancy_service]),
) -> list[TenancyGetResponse]:
    tenancies = service.fetch_all()
    return [TenancyGetResponse(name=tenancy.name, is_enabled=tenancy.is_enabled) for tenancy in tenancies]


# GET /tenancies/{name}
@router.get("/{name:path}")
@inject
async def get_by_name(
    name: str,
    response: Response,
    is_enabled: Union[bool, None] = True,
    service: TenancyService = Depends(Provide[Container.tenancy_service]),
) -> TenancyGetResponse:
    tenancy = service.fetch(name, is_enabled)
    if tenancy is not None:
        return TenancyGetResponse(name=tenancy.name, is_enabled=tenancy.is_enabled)
    else:
        response.status_code = 404
        return response

# PUT /tenancies/{name}
@router.put("/{name:path}")
@inject
async def update_by_name(
    name: str,
    payload: TenancyUpdateRequest,
    service: TenancyService = Depends(Provide[Container.tenancy_service]),
) -> None:
    service.update(name, Tenancy(payload.name, payload.is_enabled))
    return {}

# POST /tenancies
@router.post("/", status_code=201)
@inject
async def create(
    payload: TenancyCreateRequest,
    service: TenancyService = Depends(Provide[Container.tenancy_service]),
) -> None:
    service.create(Tenancy(payload.name, payload.is_enabled))
    return {}

# DELETE /tenancies/{name}
@router.delete("/{name:path}", status_code=204)
@inject
async def delete(
    name: str,
    service: TenancyService = Depends(Provide[Container.tenancy_service]),
) -> None:
    service.disable(name)
    return {}

# POST /tenancies/{name}/enable
@router.post("/{name:path}/enable")
@inject
async def enable(
    name: str,
    service: TenancyService = Depends(Provide[Container.tenancy_service]),
) -> None:
    service.enable(name)
    return {}
