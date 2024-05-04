from uuid import UUID
from fastapi import APIRouter, Depends, Response
from dependency_injector.wiring import inject, Provide
from container import Container
from controller.interceptor.authentication import fastapi_authenticate
from controller.v1.client.resource import ClientCreateRequest, ClientCreateResponse, ClientGetResponse, ClientUpdateRequest
from service.client import ClientService
from model.client import Client

router = APIRouter(
    prefix="/clients",
    tags=["clients"],
    responses={404: {"description": "Not found"}},
)

# GET /clients/{key}
@router.get("/{key}", dependencies=[Depends(fastapi_authenticate)])
@inject
async def get_by_key(
    key: UUID,
    response: Response,
    service: ClientService = Depends(Provide[Container.client_service]),
) -> ClientGetResponse:
    client = service.fetch(key)
    if client is not None:
        return ClientGetResponse(key=client["key"], name=client["name"], is_enabled=client["is_enabled"])
    else:
        response.status_code = 404
        return response

# PUT /clients/{key}
@router.put("/{key}")
@inject
async def update_by_key(
    key: UUID,
    payload: ClientUpdateRequest,
    service: ClientService = Depends(Provide[Container.client_service]),
) -> None:
    service.update(key, payload.name, payload.secret)
    return {}

# POST /clients
@router.post("/", status_code=201)
@inject
async def create(
    payload: ClientCreateRequest,
    service: ClientService = Depends(Provide[Container.client_service]),
) -> ClientCreateResponse:
    key = service.create(name=payload.name, secret=payload.secret)
    return ClientCreateResponse(key=key)

# DELETE /clients/{key}
@router.delete("/{key}", status_code=204)
@inject
async def delete(
    key: UUID,
    service: ClientService = Depends(Provide[Container.client_service]),
) -> None:
    service.disable(key)
    return {}

# GET /clients
@router.get("/")
@inject
async def get_all(
    service: ClientService = Depends(Provide[Container.client_service]),
) -> list[ClientGetResponse]:
    clients = service.fetch_all()
    return [ClientGetResponse(key=client["key"], name=client["name"], is_enabled=client["is_enabled"]) for client in clients]

# POST /clients/{key}/enable
@router.post("/{key}/enable")
@inject
async def enable(
    key: UUID,
    service: ClientService = Depends(Provide[Container.client_service]),
) -> None:
    service.enable(key)
    return {}
