import logging
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID, uuid4

from app.gateway.email.smtp import SmtpSender
from app.logging_config import fields
from app.metrics import metrics
from app.model.db.email import EmailMessage
from app.model.email import EmailEventType, EmailStatus
from app.repository.email import EmailRepository
from app.service.email_masking import mask_secrets
from app.service.email_template import EmailTemplate, EmailTemplateRenderer

PLACEHOLDER_DOMAIN = "@fake.mail.com"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmailService:
    def __init__(
        self,
        repository: EmailRepository,
        renderer: EmailTemplateRenderer,
        sender: SmtpSender,
        enabled: bool,
        from_name: str,
        from_address: str,
        reply_to: str | None,
        template_version: str,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._repository = repository
        self._renderer = renderer
        self._sender = sender
        self._enabled = enabled
        self._from_name = from_name
        self._from_address = from_address
        self._reply_to = reply_to or None
        self._template_version = template_version
        self._clock = clock
        self._logger = logging.getLogger("service:EmailService")

    def enqueue(
        self,
        *,
        template: str,
        recipient: str,
        context: dict,
        secret_fields: frozenset[str] = frozenset(),
        related_type: str | None = None,
        related_id: UUID | None = None,
        triggered_by: UUID | None = None,
        dedup_key: str | None = None,
    ) -> UUID | None:
        rendered = self._renderer.render(EmailTemplate(template), context)
        skipped = recipient.strip().lower().endswith(PLACEHOLDER_DOMAIN)

        stored_context, body_text = dict(context), rendered.text
        if skipped:
            stored_context, body_text = mask_secrets(context, body_text, secret_fields)

        message = EmailMessage(
            id=uuid4(),
            template=template,
            template_version=self._template_version,
            recipient=recipient.strip(),
            subject=rendered.subject,
            body_text=body_text,
            context=stored_context,
            secret_fields=sorted(secret_fields),
            related_type=related_type,
            related_id=related_id,
            triggered_by=triggered_by,
            dedup_key=dedup_key,
            status=(EmailStatus.SKIPPED if skipped else EmailStatus.PENDING).value,
            attempts=0,
            next_attempt_at=self._clock(),
        )
        record = self._repository.add(
            message,
            EmailEventType.SKIPPED if skipped else EmailEventType.QUEUED,
            "placeholder address" if skipped else None,
        )
        if record is None:
            return None

        if skipped:
            metrics.email_outcome(template, "skipped")
        self._logger.info(
            "email queued",
            extra=fields(
                email_id=str(record.id),
                template=template,
                outcome="skipped" if skipped else "queued",
            ),
        )
        return record.id
