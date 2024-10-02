from typing import Union
from uuid import UUID
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.v1.user.resource import (
    UserCreateResponse,
    UserEnforceRequest,
    UserEnforceResponse,
    UserProviderAddRequest,
    UserCreateRequest,
    UserGetResponse,
    UserProvider,
    UserTenanciesRequest,
    UserUpdateRequest,
)
from app.model.user import User, UserQuery
from app.service.user import UserService
from dependency_injector.wiring import inject, Provide

router = APIRouter(
    prefix="/users",
    tags=["users"],
)


def _adapt_get_response(user: User) -> UserGetResponse:
    return UserGetResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        roles=user.roles,
        is_enabled=user.is_enabled,
        created_at=user.created_at,
        updated_at=user.updated_at,
        providers=[
            UserProvider(name=provider.name, reference=provider.reference)
            for provider in user.providers
        ],
        tenancies=user.tenancies,
    )


def _adapt_post_response(user_id: UUID) -> UserCreateResponse:
    return UserCreateResponse(id=user_id)


# GET /users
@router.get("/")
@inject
async def search(
    email: str = None,
    is_enabled: Union[bool, None] = True,
    service: UserService = Depends(Provide[Container.user_service]),
) -> list[UserGetResponse]:
    query = UserQuery(email=email, is_enabled=is_enabled)
    users = service.search(query)
    return [_adapt_get_response(user) for user in users]


# GET /users/{id}
@router.get("/{id}")
@inject
async def get(
    id: UUID,
    is_enabled: Union[bool, None] = True,
    service: UserService = Depends(Provide[Container.user_service]),
) -> UserGetResponse:
    user: User = service.fetch_by_id(id=id, is_enabled=is_enabled)
    return _adapt_get_response(user)


# POST /users
@router.post("/")
@inject
async def create(
    payload: UserCreateRequest,
    service: UserService = Depends(Provide[Container.user_service]),
) -> UserCreateResponse:
    user_id = service.create(
        User(
            name=payload.name,
            email=payload.email,
            providers=payload.providers,
            roles=payload.roles,
        )
    )

    return _adapt_post_response(user_id=user_id)


# PUT /users/{id}
@router.put("/{id}")
@inject
async def update(
    id: UUID,
    payload: UserUpdateRequest,
    service: UserService = Depends(Provide[Container.user_service]),
) -> UserGetResponse:
    user: User = service.update(id=id, name=payload.name, email=payload.email)
    return _adapt_get_response(user)


# DELETE /users/{id}
@router.delete("/{id}")
@inject
async def delete(
    id: UUID,
    service: UserService = Depends(Provide[Container.user_service]),
) -> None:
    service.disable(id=id)
    return {}


# PUT /users/{id}/enable
@router.put("/{id}/enable")
@inject
async def enable(
    id: UUID,
    service: UserService = Depends(Provide[Container.user_service]),
) -> None:
    service.enable(id=id)
    return {}


# PUT /users/{id}/roles
@router.put("/{id}/roles")
@inject
async def add_roles(
    id: UUID,
    roles: list[str],
    service: UserService = Depends(Provide[Container.user_service]),
) -> None:
    service.add_roles(id=id, roles=roles)
    return {}


# DELETE /users/{id}/roles
@router.delete("/{id}/roles")
@inject
async def remove_roles(
    id: UUID,
    roles: list[str],
    service: UserService = Depends(Provide[Container.user_service]),
) -> None:
    service.remove_roles(id=id, roles=roles)
    return {}


# PUT /users/{id}/providers
@router.put("/{id}/providers")
@inject
async def add_provider(
    id: UUID,
    payload: UserProviderAddRequest,
    service: UserService = Depends(Provide[Container.user_service]),
) -> None:
    service.add_provider(id=id, provider=payload.provider, reference=payload.reference)
    return {}


# DELETE /users/{id}/providers
@router.delete("/{id}/providers")
@inject
async def remove_provider(
    id: UUID,
    provider: str,
    reference: str,
    service: UserService = Depends(Provide[Container.user_service]),
) -> None:
    service.remove_provider(id=id, provider_name=provider, reference=reference)
    return {}


# GET /users/providers/{provider}/{reference}
@router.get("/providers/{provider}/{reference}")
@inject
async def get_by_provider_reference(
    provider: str,
    reference: str,
    is_enabled: Union[bool, None] = True,
    service: UserService = Depends(Provide[Container.user_service]),
) -> UserGetResponse:
    user: User = service.fetch_by_provider(
        provider_name=provider, reference=reference, is_enabled=is_enabled
    )
    return _adapt_get_response(user)


# POST /users/{id}/tenancies
@router.post("/{id}/tenancies")
@inject
async def add_tenancy(
    id: UUID,
    payload: UserTenanciesRequest,
    service: UserService = Depends(Provide[Container.user_service]),
) -> None:
    service.add_tenancies(user_id=id, tenancies=payload.tenancies)
    return {}


# DELETE /users/{id}/tenancies
@router.delete("/{id}/tenancies")
@inject
async def remove_tenancy(
    id: UUID,
    payload: UserTenanciesRequest,
    service: UserService = Depends(Provide[Container.user_service]),
) -> None:
    service.remove_tenancies(id=id, tenancies=payload.tenancies)
    return {}


# POST /users/{id}/enforce
@router.post("/{id}/enforce")
@inject
async def enforce(
    id: UUID,
    payload: UserEnforceRequest,
    service: UserService = Depends(Provide[Container.user_service]),
) -> UserEnforceResponse:
    is_authorized: bool = service.enforce(
        id=id, resource=payload.resource, action=payload.action
    )
    return UserEnforceResponse(is_authorized=is_authorized)


# POST /force-policy-reload
@router.post("/force-policy-reload")
@inject
async def force_policy_reload(
    service: UserService = Depends(Provide[Container.user_service]),
) -> None:
    service.load_policy()
    return {}
