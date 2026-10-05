import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.logging_config import fields
from app.model.tenancy import TenancySummary
from app.service.email import EmailService
from app.service.email_format import long_date
from app.service.email_template import EmailTemplate
from app.service.share_token import hash_token


def admin_addresses(value: str) -> list[str]:
    return [address.strip() for address in (value or "").split(",") if address.strip()]


def moment(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    return f"{long_date(utc)} at {utc:%H:%M} UTC"


def address_hash(address: str) -> str:
    return hash_token(address.lower())[:16]


class TenancyNotifier:
    def __init__(
        self, email_service: EmailService, admin_emails: str, public_base_url: str
    ) -> None:
        self._email = email_service
        self._admins = admin_addresses(admin_emails)
        self._base_url = public_base_url.rstrip("/")
        self._logger = logging.getLogger("service:TenancyNotifier")

    def request_received(self, request: Any, requester: Any) -> None:
        context = {
            "requester_name": requester.name,
            "requester_email": requester.email,
            "email_confirmed": requester.email_verified_at is not None,
            "requested_name": request.requested_name,
            "reason": request.reason,
            "requested_at": moment(request.created_at),
            "review_url": f"{self._base_url}/app/admin/requests?request={request.id}",
        }
        for address in self._admins:
            self._queue(
                EmailTemplate.TENANCY_REQUEST_RECEIVED,
                recipient=address,
                context=context,
                related_type="tenancy_request",
                related_id=request.id,
                triggered_by=requester.id,
                dedup_key=f"tenancy_request_received:{request.id}:{address_hash(address)}",
            )

    def access_granted(
        self,
        user: Any,
        admin_name: str,
        tenancy: TenancySummary,
        datasets: int,
        event_id: UUID,
    ) -> None:
        if not user.email:
            return
        self._queue(
            EmailTemplate.TENANCY_ACCESS_GRANTED,
            recipient=user.email,
            context={
                "user_name": user.name,
                "admin_name": admin_name,
                "tenancy_display_name": tenancy.display_name,
                "tenancy_path": tenancy.path,
                "datasets_count": datasets,
                "open_url": f"{self._base_url}/app/tenancy",
            },
            related_type="user",
            related_id=user.id,
            dedup_key=f"tenancy_access_granted:{event_id}",
        )

    def request_declined(self, user: Any, request: Any) -> None:
        if not user.email:
            return
        self._queue(
            EmailTemplate.TENANCY_REQUEST_DECLINED,
            recipient=user.email,
            context={
                "user_name": user.name,
                "requested_name": request.requested_name,
                "decision_message": request.decision_message,
                "open_url": f"{self._base_url}/app/tenancy",
            },
            related_type="tenancy_request",
            related_id=request.id,
            dedup_key=f"tenancy_request_declined:{request.id}",
        )

    def invitation(
        self,
        invitee: Any,
        inviter_name: str,
        tenancy: TenancySummary,
        dataset_name: str,
        invitation_id: UUID,
    ) -> None:
        if not invitee.email:
            return
        self._queue(
            EmailTemplate.TENANCY_INVITATION,
            recipient=invitee.email,
            context={
                "invitee_name": invitee.name,
                "inviter_name": inviter_name,
                "tenancy_display_name": tenancy.display_name,
                "tenancy_path": tenancy.path,
                "dataset_name": dataset_name,
                "open_url": f"{self._base_url}/app/home",
            },
            related_type="tenancy_invitation",
            related_id=invitation_id,
            dedup_key=f"tenancy_invitation:{invitation_id}",
        )

    def invitation_notice(
        self,
        invitee: Any,
        inviter_name: str,
        tenancy: TenancySummary,
        dataset_name: str,
        invitation_id: UUID,
    ) -> None:
        context = {
            "inviter_name": inviter_name,
            "invitee_name": invitee.name,
            "invitee_email": invitee.email,
            "tenancy_display_name": tenancy.display_name,
            "tenancy_path": tenancy.path,
            "dataset_name": dataset_name,
            "tenancy_url": f"{self._base_url}/app/admin/tenancies?tenancy={tenancy.path}",
        }
        for address in self._admins:
            self._queue(
                EmailTemplate.TENANCY_INVITATION_NOTICE,
                recipient=address,
                context=context,
                related_type="tenancy_invitation",
                related_id=invitation_id,
                dedup_key=f"tenancy_invitation_notice:{invitation_id}:{address_hash(address)}",
            )

    def _queue(self, template: EmailTemplate, **kwargs: Any) -> None:
        try:
            self._email.enqueue(template=template.value, **kwargs)
        except Exception:
            self._logger.error(
                "email enqueue failed",
                exc_info=True,
                extra=fields(
                    template=template.value, related_id=str(kwargs.get("related_id"))
                ),
            )
