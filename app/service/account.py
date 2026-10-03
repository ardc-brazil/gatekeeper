import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID, uuid4

from app.exception.bad_request import BadRequestException
from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.too_many_requests import TooManyRequestsException
from app.logging_config import fields
from app.model.auth_challenge import ChallengeKind
from app.model.db.auth_challenge import AuthChallenge
from app.model.user import User, UserProvider
from app.repository.auth_challenge import AuthChallengeRepository
from app.repository.email import EmailRepository
from app.repository.user import UserRepository
from app.service.challenge_code import code_hash, new_code
from app.service.email import EmailService
from app.service.email_template import EmailTemplate
from app.service.password import PasswordHasher, password_is_acceptable
from app.service.share_identity import normalise_email, normalise_orcid
from app.service.share_token import new_token
from app.service.user import UserService

CODE_LIFETIME_MINUTES = 15
CODE_LIFETIME = timedelta(minutes=CODE_LIFETIME_MINUTES)
MAX_CODE_ATTEMPTS = 5
RESEND_COOLDOWN = timedelta(seconds=90)
CODES_PER_HOUR = 5
CAP_WINDOW = timedelta(hours=1)
MAX_NAME_LENGTH = 256
ORCID_PROVIDER = "orcid"
CHALLENGE_NOT_FOUND = "challenge_not_found"
CODE_INVALID = "code_invalid"
CODE_EXPIRED = "code_expired"
CODE_ATTEMPTS_EXCEEDED = "code_attempts_exceeded"
EMAIL_TAKEN = "email_belongs_to_another_account"

TEMPLATES = {
    ChallengeKind.SIGN_UP: EmailTemplate.SIGN_UP_CODE,
    ChallengeKind.EMAIL_VERIFICATION: EmailTemplate.EMAIL_VERIFICATION_CODE,
    ChallengeKind.PASSWORD_RESET: EmailTemplate.PASSWORD_RESET,
}
CAPPED_TEMPLATES = [template.value for template in TEMPLATES.values()]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _invalid(code: str) -> IllegalStateException:
    return IllegalStateException(code)


def _email(value: str) -> str:
    try:
        return normalise_email(value)
    except BadRequestException:
        raise _invalid("invalid_email")


def _orcid(value: str) -> str:
    try:
        return normalise_orcid(value)
    except BadRequestException:
        raise _invalid("invalid_orcid")


def _name(value: str) -> str:
    name = (value or "").strip()
    if not name or len(name) > MAX_NAME_LENGTH:
        raise _invalid("invalid_name")
    return name


def _password(value: str) -> str:
    if not password_is_acceptable(value or ""):
        raise _invalid("invalid_password")
    return value


def _consumed_reason(challenge: AuthChallenge) -> str:
    if challenge.attempts >= MAX_CODE_ATTEMPTS:
        return CODE_ATTEMPTS_EXCEEDED
    if challenge.expires_at <= challenge.consumed_at:
        return CODE_EXPIRED
    return CODE_INVALID


def _can_resend(challenge: AuthChallenge) -> bool:
    return (
        challenge.kind != ChallengeKind.PASSWORD_RESET.value
        and challenge.confirmed_at is None
    )


class AccountService:
    def __init__(
        self,
        users: UserRepository,
        user_service: UserService,
        challenges: AuthChallengeRepository,
        emails: EmailRepository,
        email_service: EmailService,
        hasher: PasswordHasher,
        challenge_pepper: str,
        public_base_url: str,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._users = users
        self._user_service = user_service
        self._challenges = challenges
        self._emails = emails
        self._email = email_service
        self._hasher = hasher
        self._pepper = challenge_pepper
        self._base_url = public_base_url.rstrip("/")
        self._clock = clock
        self._logger = logging.getLogger("service:AccountService")

    def sign_up(self, name: str, email: str, password: str) -> UUID:
        name, email = _name(name), _email(email)
        password_hash = self._hasher.hash(_password(password))
        return self._issue_code(
            ChallengeKind.SIGN_UP,
            email,
            {"name": name, "password_hash": password_hash},
        )

    def confirm_sign_up(self, challenge_id: UUID, code: str) -> UUID:
        challenge = self._redeem(challenge_id, ChallengeKind.SIGN_UP, code)
        password_hash = challenge.payload["password_hash"]
        existing = self._users.fetch_by_email_any(challenge.email)
        if existing is None:
            return self._user_service.create(
                User(
                    name=challenge.payload["name"],
                    email=challenge.email,
                    providers=[],
                    roles=[],
                ),
                password_hash=password_hash,
                email_verified_at=self._clock(),
            )
        self._users.set_password(existing.id, password_hash)
        self._users.verify_email(existing.id, challenge.email, self._clock())
        return existing.id

    def request_email_verification(self, orcid: str, email: str, name: str) -> UUID:
        orcid, email, name = _orcid(orcid), _email(email), _name(name)
        return self._issue_code(
            ChallengeKind.EMAIL_VERIFICATION, email, {"orcid": orcid, "name": name}
        )

    def confirm_email_verification(self, challenge_id: UUID, code: str) -> UUID:
        challenge = self._redeem(challenge_id, ChallengeKind.EMAIL_VERIFICATION, code)
        orcid, email, now = challenge.payload["orcid"], challenge.email, self._clock()
        by_orcid = self._users.fetch_by_provider_any(
            provider_name=ORCID_PROVIDER, reference=orcid
        )
        by_email = self._users.fetch_by_email_any(email)

        if by_orcid is not None:
            if not by_orcid.is_enabled:
                raise ConflictException(EMAIL_TAKEN)
            if by_email is not None and by_email.id != by_orcid.id:
                raise ConflictException(EMAIL_TAKEN)
            self._users.verify_email(by_orcid.id, email, now)
            return by_orcid.id

        if by_email is not None:
            if not by_email.is_enabled:
                raise ConflictException(EMAIL_TAKEN)
            self._user_service.add_provider(
                id=by_email.id, provider=ORCID_PROVIDER, reference=orcid
            )
            self._users.verify_email(by_email.id, email, now)
            return by_email.id

        return self._user_service.create(
            User(
                name=challenge.payload["name"],
                email=email,
                providers=[UserProvider(name=ORCID_PROVIDER, reference=orcid)],
                roles=[],
            ),
            email_verified_at=now,
        )

    def resend(self, challenge_id: UUID) -> None:
        challenge = self._challenges.fetch(challenge_id)
        if challenge is None or not _can_resend(challenge):
            raise NotFoundException(CHALLENGE_NOT_FOUND)
        now = self._clock()
        if now - challenge.issued_at < RESEND_COOLDOWN:
            raise TooManyRequestsException("resend_too_soon")
        if self._capped(challenge.email, now):
            self._challenges.touch(challenge.id, now)
            self._log_issue(challenge.id, challenge.kind, "capped")
            return
        code = new_code()
        self._challenges.reissue(
            challenge.id,
            code_hash(self._pepper, challenge.id, code),
            now + CODE_LIFETIME,
            now,
        )
        kind = ChallengeKind(challenge.kind)
        self._send_code(kind, challenge.email, challenge.id, code, challenge.payload)
        self._log_issue(challenge.id, challenge.kind, "resent")

    def _redeem(
        self, challenge_id: UUID, kind: ChallengeKind, code: str
    ) -> AuthChallenge:
        challenge = self._challenges.fetch(challenge_id)
        if challenge is None or challenge.kind != kind.value:
            raise NotFoundException(CHALLENGE_NOT_FOUND)
        if challenge.consumed_at is not None:
            raise _invalid(_consumed_reason(challenge))
        now = self._clock()
        if challenge.expires_at <= now:
            self._challenges.consume(challenge.id, now)
            raise _invalid(CODE_EXPIRED)
        expected = code_hash(self._pepper, challenge.id, (code or "").strip())
        if not hmac.compare_digest(challenge.secret_hash, expected):
            attempts = self._challenges.record_failed_attempt(
                challenge.id, MAX_CODE_ATTEMPTS, now
            )
            if attempts is not None and attempts >= MAX_CODE_ATTEMPTS:
                raise _invalid(CODE_ATTEMPTS_EXCEEDED)
            raise _invalid(CODE_INVALID)
        if not self._challenges.confirm(challenge.id, now):
            raise _invalid(CODE_INVALID)
        return challenge

    def _issue_code(self, kind: ChallengeKind, email: str, payload: dict) -> UUID:
        now = self._clock()
        challenge_id = uuid4()
        capped = self._capped(email, now)
        code = new_code()
        secret = new_token() if capped else code
        self._challenges.replace(
            AuthChallenge(
                id=challenge_id,
                kind=kind.value,
                email=email,
                secret_hash=code_hash(self._pepper, challenge_id, secret),
                attempts=0,
                expires_at=now + CODE_LIFETIME,
                issued_at=now,
                payload=payload,
            )
        )
        if capped:
            self._log_issue(challenge_id, kind.value, "capped")
        else:
            self._send_code(kind, email, challenge_id, code, payload)
            self._log_issue(challenge_id, kind.value, "sent")
        return challenge_id

    def _send_code(
        self,
        kind: ChallengeKind,
        email: str,
        challenge_id: UUID,
        code: str,
        payload: dict,
    ) -> None:
        context = {
            "name": payload["name"],
            "code": code,
            "expires_in_minutes": CODE_LIFETIME_MINUTES,
        }
        if kind == ChallengeKind.EMAIL_VERIFICATION:
            context["orcid"] = payload["orcid"]
        self._queue(TEMPLATES[kind], email, context, frozenset({"code"}), challenge_id)

    def _queue(
        self,
        template: EmailTemplate,
        recipient: str,
        context: dict,
        secret_fields: frozenset[str],
        challenge_id: UUID,
    ) -> None:
        try:
            self._email.enqueue(
                template=template.value,
                recipient=recipient,
                context=context,
                secret_fields=secret_fields,
                related_type="auth_challenge",
                related_id=challenge_id,
            )
        except Exception:
            self._logger.error(
                "email enqueue failed",
                exc_info=True,
                extra=fields(template=template.value, challenge_id=str(challenge_id)),
            )

    def _capped(self, email: str, now: datetime) -> bool:
        sent = self._emails.count_recent(email, CAPPED_TEMPLATES, now - CAP_WINDOW)
        return sent >= CODES_PER_HOUR

    def _log_issue(self, challenge_id: UUID | None, kind: str, outcome: str) -> None:
        self._logger.info(
            "auth challenge issued",
            extra=fields(
                challenge_id=str(challenge_id) if challenge_id else None,
                kind=kind,
                outcome=outcome,
            ),
        )
