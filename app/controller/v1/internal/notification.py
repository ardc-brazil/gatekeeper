import logging
from datetime import datetime, timezone

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.v1.internal.resource import NotificationDispatchResponse
from app.logging_config import fields
from app.service.email import EmailService
from app.service.notification import EmbargoNotificationService

router = APIRouter(
    prefix="/internal/notifications",
    tags=["internal"],
    responses={404: {"description": "Not found"}},
)

logger = logging.getLogger("controller:internal:notifications")


@router.post(
    "/dispatch",
    dependencies=[Depends(authenticate)],
    response_model=NotificationDispatchResponse,
)
@inject
def dispatch(
    notifications: EmbargoNotificationService = Depends(
        Provide[Container.embargo_notification_service]
    ),
    email_service: EmailService = Depends(Provide[Container.email_service]),
) -> NotificationDispatchResponse:
    """Queue the embargo messages that are due, then send what is due. Called by the Archivist."""
    try:
        queued = notifications.queue_due(datetime.now(timezone.utc))
    except Exception:
        logger.exception("embargo notification queue failed", extra=fields())
        queued = 0
    result = email_service.dispatch_due()
    return NotificationDispatchResponse(
        queued=queued + result.queued,
        sent=result.sent,
        failed=result.failed,
        skipped=result.skipped,
        retried=result.retried,
    )
