import hmac
import logging
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID, uuid4

from app.exception.bad_request import BadRequestException
from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.too_many_requests import TooManyRequestsException
from app.exception.unauthorized import UnauthorizedException
from app.logging_config import fields
from app.model.auth_challenge import ChallengeKind
from app.model.db.auth_challenge import AuthChallenge
from app.model.db.user import User as UserDBModel
from app.model.user import User, UserProvider
from app.repository.auth_challenge import AuthChallengeRepository
from app.repository.email import EmailRepository
from app.repository.user import UserRepository
from app.service.challenge_code import code_hash, new_code
from app.service.email import EmailService
from app.service.email_template import EmailTemplate
from app.service.password import PasswordHasher, password_is_acceptable
from app.service.share_identity import normalise_email, normalise_orcid
from app.service.share_token import hash_token, new_token
from app.service.user import UserService

CODE_LIFETIME_MINUTES = 15
CODE_LIFETIME = timedelta(minutes=CODE_LIFETIME_MINUTES)
MAX_CODE_ATTEMPTS = 5
RESEND_COOLDOWN = timedelta(seconds=90)
CODES_PER_HOUR = 5
CAP_WINDOW = timedelta(hours=1)
RESET_LIFETIME = timedelta(hours=1)
MAX_FAILED_LOGINS = 10
LOCK_DURATION = timedelta(minutes=15)
INVALID_CREDENTIALS = "invalid_credentials"
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
CAPPED_TEMPLATES = [template.value for template in TEMPLATES.values()] + [
    EmailTemplate.SIGN_UP_EXISTING_ACCOUNT.value
]


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
    value = value or ""
    name = value.strip()
    if (
        not name
        or len(name) > MAX_NAME_LENGTH
        or any(unicodedata.category(character) == "Cc" for character in value)
    ):
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


def _signs_in_with_password(found: UserDBModel | None) -> bool:
    return (
        found is not None
        and found.is_enabled
        and found.password_hash is not None
        and found.email_verified_at is not None
    )


def _answers_an_existing_account(challenge: AuthChallenge) -> bool:
    return (
        challenge.kind == ChallengeKind.SIGN_UP.value
        and challenge.payload.get("existing_account") is True
    )


def _can_resend(challenge: AuthChallenge) -> bool:
    if challenge.kind == ChallengeKind.SIGN_UP.value and not (
        "password_hash" in challenge.payload or _answers_an_existing_account(challenge)
    ):
        return False
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
        found = self._users.fetch_by_email_any(email)
        if _signs_in_with_password(found):
            return self._answer_existing_account(found, email, name)
        return self._issue_code(
            ChallengeKind.SIGN_UP,
            email,
            {"name": name, "password_hash": password_hash},
        )

    def confirm_sign_up(self, challenge_id: UUID, code: str) -> UUID:
        challenge = self._redeem(challenge_id, ChallengeKind.SIGN_UP, code)
        password_hash = challenge.payload["password_hash"]
        existing = self._users.fetch_by_email_any(challenge.email)
        if existing is not None and not existing.is_enabled:
            raise ConflictException(EMAIL_TAKEN)
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
        now = self._clock()
        self._users.set_password_and_verify_email(
            existing.id, password_hash, challenge.email, now
        )
        self._challenges.consume_open_for_user(
            existing.id, ChallengeKind.PASSWORD_RESET, now
        )
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
        if _answers_an_existing_account(challenge):
            self._challenges.touch(challenge.id, now)
            found = self._users.fetch_by_email_any(challenge.email)
            if _signs_in_with_password(found):
                self._send_reset_link(
                    found, challenge.email, now, EmailTemplate.SIGN_UP_EXISTING_ACCOUNT
                )
            return
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

    def login(self, email: str, password: str) -> UUID:
        now = self._clock()
        password = password or ""
        found = self._account_for_login(email)
        if found is None or found.password_hash is None:
            self._hasher.burn(password)
            raise self._refused("unknown" if found is None else "no_password", found)
        if found.locked_until is not None and found.locked_until > now:
            self._hasher.burn(password)
            raise self._refused("locked", found)
        if not self._hasher.verify(password, found.password_hash):
            self._users.record_failed_login(
                found.id, MAX_FAILED_LOGINS, now + LOCK_DURATION
            )
            raise self._refused("wrong_password", found)
        if not found.is_enabled:
            raise self._refused("disabled", found)
        if found.email_verified_at is None:
            raise self._refused("unverified", found)
        if found.failed_login_count or found.locked_until is not None:
            self._users.clear_failed_logins(found.id)
        return found.id

    def request_password_reset(self, email: str) -> None:
        try:
            address = normalise_email(email)
        except BadRequestException:
            return
        found = self._users.fetch_by_email_any(address)
        if found is None or not found.is_enabled or found.email_verified_at is None:
            return
        self._send_reset_link(
            found, address, self._clock(), EmailTemplate.PASSWORD_RESET
        )

    def _send_reset_link(
        self, found: UserDBModel, address: str, now: datetime, template: EmailTemplate
    ) -> None:
        if self._capped(address, now):
            self._log_issue(None, ChallengeKind.PASSWORD_RESET.value, "capped")
            return
        token, challenge_id = new_token(), uuid4()
        self._challenges.replace(
            AuthChallenge(
                id=challenge_id,
                kind=ChallengeKind.PASSWORD_RESET.value,
                email=address,
                secret_hash=hash_token(token),
                attempts=0,
                expires_at=now + RESET_LIFETIME,
                issued_at=now,
                user_id=found.id,
                payload={},
            )
        )
        self._queue(
            template,
            address,
            {"name": found.name, "link": self.reset_link(token)},
            frozenset({"link"}),
            challenge_id,
        )
        self._log_issue(challenge_id, ChallengeKind.PASSWORD_RESET.value, "sent")

    def reset_link(self, token: str) -> str:
        return f"{self._base_url}/account/reset-password/{token}"

    def confirm_password_reset(self, token: str, password: str) -> None:
        _password(password)
        now = self._clock()
        challenge = self._challenges.fetch_open_by_secret(
            hash_token(token or ""), ChallengeKind.PASSWORD_RESET
        )
        if (
            challenge is None
            or challenge.user_id is None
            or challenge.expires_at <= now
        ):
            raise _invalid("token_invalid")
        if not self._challenges.consume(challenge.id, now):
            raise _invalid("token_invalid")
        self._users.set_password(challenge.user_id, self._hasher.hash(password))
        self._challenges.consume_open_for_user(
            challenge.user_id, ChallengeKind.PASSWORD_RESET, now
        )

    def change_password(
        self, user_id: UUID, current_password: str, new_password: str
    ) -> None:
        _password(new_password)
        now = self._clock()
        current_password = current_password or ""
        found = self._users.fetch_by_id(id=user_id)
        if found is None or found.password_hash is None:
            self._hasher.burn(current_password)
            raise self._refused("unknown" if found is None else "no_password", found)
        if found.locked_until is not None and found.locked_until > now:
            self._hasher.burn(current_password)
            raise self._refused("locked", found)
        if not self._hasher.verify(current_password, found.password_hash):
            self._users.record_failed_login(
                found.id, MAX_FAILED_LOGINS, now + LOCK_DURATION
            )
            raise self._refused("wrong_password", found)
        self._users.set_password(found.id, self._hasher.hash(new_password))
        self._challenges.consume_open_for_user(
            found.id, ChallengeKind.PASSWORD_RESET, now
        )

    def _account_for_login(self, email: str) -> UserDBModel | None:
        try:
            return self._users.fetch_by_email_any(normalise_email(email))
        except BadRequestException:
            return None

    def _refused(self, reason: str, found: UserDBModel | None) -> UnauthorizedException:
        self._logger.info(
            "password check refused",
            extra=fields(
                reason=reason, user_id=str(found.id) if found is not None else None
            ),
        )
        return UnauthorizedException(INVALID_CREDENTIALS)

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

    def _answer_existing_account(
        self, found: UserDBModel, email: str, name: str
    ) -> UUID:
        now, challenge_id = self._clock(), uuid4()
        self._send_reset_link(found, email, now, EmailTemplate.SIGN_UP_EXISTING_ACCOUNT)
        self._challenges.replace(
            AuthChallenge(
                id=challenge_id,
                kind=ChallengeKind.SIGN_UP.value,
                email=email,
                secret_hash=code_hash(self._pepper, challenge_id, new_token()),
                attempts=0,
                expires_at=now + CODE_LIFETIME,
                issued_at=now,
                payload={"name": name, "existing_account": True},
            )
        )
        self._log_issue(challenge_id, ChallengeKind.SIGN_UP.value, "existing_account")
        return challenge_id

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
