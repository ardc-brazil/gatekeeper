import logging
import secrets
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, getaddresses, make_msgid
from typing import Callable
from uuid import UUID, uuid4

from app.exception.bad_request import BadRequestException, ErrorDetails
from app.exception.not_found import NotFoundException
from app.gateway.email.smtp import (
    DefiniteSendFailure,
    SmtpSender,
    UncertainSendFailure,
)
from app.logging_config import fields
from app.metrics import metrics
from app.model.db.email import EmailMessage
from app.model.dataset import PaginatedResult
from app.model.email import (
    DispatchResult,
    EmailEventRecord,
    EmailEventType,
    EmailQuery,
    EmailRecord,
    EmailStatus,
)
from app.repository.email import EmailRepository
from app.service.email_masking import mask_secrets
from app.service.email_template import EmailTemplate, EmailTemplateRenderer

PLACEHOLDER_DOMAIN = "@fake.mail.com"
MAX_ATTEMPTS = 5
RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
)
STALE_SENDING_AFTER = timedelta(minutes=10)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _single_address(recipient: str) -> str:
    address = recipient.strip()
    parsed = getaddresses([recipient])
    if not address or len(parsed) != 1 or parsed[0] != ("", address):
        raise BadRequestException(errors=[ErrorDetails(code="invalid_recipient")])
    return address


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
        recipient = _single_address(recipient)
        rendered = self._renderer.render(EmailTemplate(template), context)
        skipped = recipient.lower().endswith(PLACEHOLDER_DOMAIN)

        stored_context, body_text = dict(context), rendered.text
        if skipped:
            stored_context, body_text = mask_secrets(context, body_text, secret_fields)

        message = EmailMessage(
            id=uuid4(),
            template=template,
            template_version=self._template_version,
            recipient=recipient,
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

    def dispatch_due(self, limit: int = 50) -> DispatchResult:
        result = DispatchResult()
        now = self._clock()

        try:
            for stale in self._repository.claim_stale_sending(
                now - STALE_SENDING_AFTER
            ):
                try:
                    self._fail(
                        stale,
                        stale.attempts,
                        "delivery uncertain: left in sending",
                        result,
                    )
                except Exception:
                    self._dispatch_error(stale)

            if self._enabled:
                for record in self._repository.claim_due(now, limit):
                    try:
                        self._deliver(record, now, result)
                    except Exception:
                        self._dispatch_error(record)
        finally:
            metrics.email_pending(self._repository.count_pending())

        return result

    def _dispatch_error(self, record: EmailRecord) -> None:
        self._logger.exception(
            "email dispatch error",
            extra=fields(
                email_id=str(record.id), template=record.template, outcome="error"
            ),
        )

    def search(self, query: EmailQuery) -> PaginatedResult:
        return self._repository.search(query)

    def fetch(self, message_id: UUID) -> tuple[EmailRecord, list[EmailEventRecord]]:
        found = self._repository.fetch(message_id)
        if found is None:
            raise NotFoundException(f"not_found: {message_id}")
        return found

    def send_test_message(self, recipient: str, triggered_by: UUID | None) -> UUID:
        code = secrets.token_hex(4)
        return self.enqueue(
            template=EmailTemplate.NOTIFICATION.value,
            recipient=recipient,
            context={
                "title": "DataMap test message",
                "preheader": "A test message from DataMap.",
                "message": "If this reached your inbox, the platform can send email. "
                f"Verification code: {code}",
                "cta_label": "Open DataMap",
                "cta_url": self._renderer.site_url,
                "reason": "You received this email because a DataMap administrator "
                "sent a test message to this address.",
                "code": code,
            },
            secret_fields=frozenset({"code"}),
            triggered_by=triggered_by,
        )

    def _deliver(
        self, record: EmailRecord, now: datetime, result: DispatchResult
    ) -> None:
        attempts = record.attempts + 1
        try:
            message = self._mime(record)
        except Exception as e:
            # Only the type: a render error's text can quote context values.
            self._fail(record, attempts, f"render: {type(e).__name__}", result)
            return

        try:
            self._sender.send(message)
        except DefiniteSendFailure as e:
            if attempts >= MAX_ATTEMPTS:
                self._fail(record, attempts, str(e), result)
                return
            self._repository.mark_retry(
                message_id=record.id,
                attempts=attempts,
                next_attempt_at=now + RETRY_DELAYS[attempts - 1],
                detail=str(e),
            )
            result.retried += 1
            self._count(record, "retried")
            return
        except UncertainSendFailure as e:
            self._fail(record, attempts, f"delivery uncertain: {e}", result)
            return

        context, body_text = mask_secrets(
            record.context, record.body_text, record.secret_fields
        )
        self._repository.mark_sent(
            message_id=record.id,
            smtp_message_id=message["Message-ID"],
            sent_at=now,
            context=context,
            body_text=body_text,
        )
        result.sent += 1
        self._count(record, "sent")

    def _fail(
        self, record: EmailRecord, attempts: int, detail: str, result: DispatchResult
    ) -> None:
        context, body_text = mask_secrets(
            record.context, record.body_text, record.secret_fields
        )
        self._repository.mark_failed(
            message_id=record.id,
            attempts=attempts,
            detail=detail,
            context=context,
            body_text=body_text,
        )
        result.failed += 1
        self._count(record, "failed")

    def _count(self, record: EmailRecord, outcome: str) -> None:
        metrics.email_outcome(record.template, outcome)
        log = self._logger.warning if outcome == "failed" else self._logger.info
        log(
            f"email {outcome}",
            extra=fields(
                email_id=str(record.id), template=record.template, outcome=outcome
            ),
        )

    def _mime(self, record: EmailRecord) -> MimeMessage:
        rendered = self._renderer.render(EmailTemplate(record.template), record.context)
        message = MimeMessage()
        message["From"] = formataddr((self._from_name, self._from_address))
        message["To"] = record.recipient
        message["Subject"] = record.subject
        if self._reply_to:
            message["Reply-To"] = self._reply_to
        message["Message-ID"] = make_msgid(domain=self._from_address.rsplit("@", 1)[-1])
        message.set_content(rendered.text)
        message.add_alternative(rendered.html, subtype="html")
        return message
