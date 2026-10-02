from typing import Optional
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.admin.resource import (
    EmailDetailResponse,
    EmailEventResponse,
    EmailListResponse,
    EmailSummaryResponse,
    TestEmailRequest,
    TestEmailResponse,
)
from app.model.email import EmailQuery, EmailRecord, EmailStatus
from app.service.email import EmailService
from app.service.email_masking import mask_secrets

router = APIRouter(
    prefix="/admin/emails",
    tags=["admin"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


def _summary(record: EmailRecord) -> dict:
    return dict(
        id=record.id,
        template=record.template,
        recipient=record.recipient,
        subject=record.subject,
        status=record.status.value,
        attempts=record.attempts,
        related_type=record.related_type,
        related_id=record.related_id,
        triggered_by=record.triggered_by,
        created_at=record.created_at,
        sent_at=record.sent_at,
    )


@router.get("/", response_model=EmailListResponse)
@inject
def search(
    recipient: Optional[str] = None,
    related_id: Optional[UUID] = None,
    template: Optional[str] = None,
    status: Optional[EmailStatus] = None,
    page: int = 1,
    page_size: int = 20,
    service: EmailService = Depends(Provide[Container.email_service]),
) -> EmailListResponse:
    result = service.search(
        EmailQuery(
            recipient=recipient,
            related_id=related_id,
            template=template,
            status=status,
            page=page,
            page_size=page_size,
        )
    )
    return EmailListResponse(
        items=[EmailSummaryResponse(**_summary(item)) for item in result.items],
        total_count=result.total_count,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{email_id}", response_model=EmailDetailResponse)
@inject
def fetch(
    email_id: UUID,
    service: EmailService = Depends(Provide[Container.email_service]),
) -> EmailDetailResponse:
    record, events = service.fetch(email_id)
    context, body_text = mask_secrets(
        record.context, record.body_text, record.secret_fields
    )
    return EmailDetailResponse(
        **_summary(record),
        template_version=record.template_version,
        body_text=body_text,
        context=context,
        smtp_message_id=record.smtp_message_id,
        next_attempt_at=record.next_attempt_at,
        events=[
            EmailEventResponse(
                event=event.event.value,
                detail=event.detail,
                occurred_at=event.occurred_at,
            )
            for event in events
        ],
    )


@router.post("/test", status_code=202, response_model=TestEmailResponse)
@inject
def send_test(
    request: TestEmailRequest,
    user_id: UUID = Depends(parse_user_header),
    service: EmailService = Depends(Provide[Container.email_service]),
) -> TestEmailResponse:
    return TestEmailResponse(
        id=service.send_test_message(request.recipient, triggered_by=user_id)
    )
