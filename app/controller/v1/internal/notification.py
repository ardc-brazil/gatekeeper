from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.v1.internal.resource import NotificationDispatchResponse
from app.service.email import EmailService

router = APIRouter(
    prefix="/internal/notifications",
    tags=["internal"],
    responses={404: {"description": "Not found"}},
)


@router.post(
    "/dispatch",
    dependencies=[Depends(authenticate)],
    response_model=NotificationDispatchResponse,
)
@inject
def dispatch(
    email_service: EmailService = Depends(Provide[Container.email_service]),
) -> NotificationDispatchResponse:
    """Send the email that is due. Called by the Archivist every few minutes."""
    result = email_service.dispatch_due()
    return NotificationDispatchResponse(
        queued=result.queued,
        sent=result.sent,
        failed=result.failed,
        skipped=result.skipped,
        retried=result.retried,
    )
