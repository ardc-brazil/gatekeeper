from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.tenancy_parser import parse_tenancy_header
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.dataset.resource import (
    AccessHistoryEntryResponse,
    AccessHistoryResponse,
    AccessHistoryUserResponse,
    EmbargoExtendRequest,
    EmbargoModeRequest,
    EmbargoNoteRequest,
    EmbargoResponse,
    EmbargoSetRequest,
)
from app.model.embargo import Embargo
from app.service.access_history import AccessHistoryEntry, AccessHistoryService
from app.service.embargo import EmbargoService

router = APIRouter(
    prefix="/datasets",
    tags=["embargo"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


def _adapt_entry(entry: AccessHistoryEntry) -> AccessHistoryEntryResponse:
    return AccessHistoryEntryResponse(
        event_type=entry.event_type,
        occurred_at=entry.occurred_at,
        actor=AccessHistoryUserResponse(id=entry.actor.id, name=entry.actor.name)
        if entry.actor
        else None,
        subject=entry.subject,
        old_value=entry.old_value,
        new_value=entry.new_value,
        note=entry.note,
    )


def _adapt(embargo: Embargo) -> EmbargoResponse:
    return EmbargoResponse(
        until=embargo.until,
        active=embargo.active,
        metadata_visible=embargo.metadata_visible,
        note=embargo.note,
    )


# PUT /datasets/{dataset_id}/embargo
@router.put("/{dataset_id}/embargo")
@inject
def set_embargo(
    dataset_id: UUID,
    request: EmbargoSetRequest,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: EmbargoService = Depends(Provide[Container.embargo_service]),
) -> EmbargoResponse:
    return _adapt(
        service.set_embargo(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            until=request.until,
            metadata_visible=request.metadata_visible,
            note=request.note,
        )
    )


# POST /datasets/{dataset_id}/embargo/extend
@router.post("/{dataset_id}/embargo/extend")
@inject
def extend_embargo(
    dataset_id: UUID,
    request: EmbargoExtendRequest,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: EmbargoService = Depends(Provide[Container.embargo_service]),
) -> EmbargoResponse:
    return _adapt(
        service.extend(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            until=request.until,
            reason=request.reason,
        )
    )


# POST /datasets/{dataset_id}/embargo/end
@router.post("/{dataset_id}/embargo/end")
@inject
def end_embargo(
    dataset_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: EmbargoService = Depends(Provide[Container.embargo_service]),
) -> EmbargoResponse:
    return _adapt(
        service.end(dataset_id=dataset_id, user_id=user_id, tenancies=tenancies)
    )


# PUT /datasets/{dataset_id}/embargo/mode
@router.put("/{dataset_id}/embargo/mode")
@inject
def set_embargo_mode(
    dataset_id: UUID,
    request: EmbargoModeRequest,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: EmbargoService = Depends(Provide[Container.embargo_service]),
) -> EmbargoResponse:
    return _adapt(
        service.set_mode(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            metadata_visible=request.metadata_visible,
        )
    )


# PUT /datasets/{dataset_id}/embargo/note
@router.put("/{dataset_id}/embargo/note")
@inject
def set_embargo_note(
    dataset_id: UUID,
    request: EmbargoNoteRequest,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: EmbargoService = Depends(Provide[Container.embargo_service]),
) -> EmbargoResponse:
    return _adapt(
        service.set_note(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            note=request.note,
        )
    )


# GET /datasets/{dataset_id}/access-events
@router.get("/{dataset_id}/access-events")
@inject
def access_events(
    dataset_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: AccessHistoryService = Depends(Provide[Container.access_history_service]),
) -> AccessHistoryResponse:
    return AccessHistoryResponse(
        items=[
            _adapt_entry(entry)
            for entry in service.list(
                dataset_id=dataset_id, user_id=user_id, tenancies=tenancies
            )
        ]
    )
