from uuid import UUID
from fastapi import APIRouter, Depends, Response
from dependency_injector.wiring import inject, Provide
from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.v1.client.resource import (
    ClientCreateRequest,
    ClientCreateResponse,
    ClientGetResponse,
    ClientUpdateRequest,
)
from app.model.client import Client
from app.service.client import ClientService

router = APIRouter(
    prefix="/clients",
    tags=["clients"],
    responses={404: {"description": "Not found"}},
)


# GET /clients
@router.get("/")
@inject
async def get_all(
    service: ClientService = Depends(Provide[Container.client_service]),
) -> list[ClientGetResponse]:
    clients: list[Client] = service.fetch_all()
    return [
        ClientGetResponse(
            key=client.key, name=client.name, is_enabled=client.is_enabled
        )
        for client in clients
    ]


# GET /clients/{key}
@router.get("/{key}", dependencies=[Depends(authenticate)])
@inject
async def get_by_key(
    key: UUID,
    response: Response,
    service: ClientService = Depends(Provide[Container.client_service]),
) -> ClientGetResponse:
    client: list[Client] = service.fetch(key)
    if client is not None:
        return ClientGetResponse(
            key=client.key, name=client.name, is_enabled=client.is_enabled
        )
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
    service.update(key=key, name=payload.name, secret=payload.secret)
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


# POST /clients/{key}/enable
@router.post("/{key}/enable")
@inject
async def enable(
    key: UUID,
    service: ClientService = Depends(Provide[Container.client_service]),
) -> None:
    service.enable(key)
    return {}
