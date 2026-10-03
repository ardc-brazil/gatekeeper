import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.too_many_requests import TooManyRequestsException
from app.model.auth_challenge import ChallengeKind
from app.model.db.auth_challenge import AuthChallenge
from app.model.db.user import User as UserDBModel
from app.model.user import UserProvider
from app.repository.auth_challenge import AuthChallengeRepository
from app.repository.email import EmailRepository
from app.repository.user import UserRepository
from app.service.account import AccountService
from app.service.challenge_code import code_hash
from app.service.email import EmailService
from app.service.password import PasswordHasher
from app.service.user import UserService

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
CHALLENGE_PEPPER = "challenge-pepper-of-sixteen"
PASSWORD = "correct horse battery"
ORCID = "0000-0002-1825-0097"
CODE = "042917"


def challenge(
    kind: ChallengeKind = ChallengeKind.SIGN_UP,
    email: str = "ana.souza@usp.br",
    code: str = CODE,
    payload: dict | None = None,
    **overrides,
) -> AuthChallenge:
    challenge_id = overrides.pop("id", uuid4())
    values = dict(
        id=challenge_id,
        kind=kind.value,
        email=email,
        secret_hash=code_hash(CHALLENGE_PEPPER, challenge_id, code),
        attempts=0,
        expires_at=NOW + timedelta(minutes=10),
        consumed_at=None,
        confirmed_at=None,
        issued_at=NOW - timedelta(minutes=5),
        user_id=None,
        payload=payload if payload is not None else {},
        created_at=NOW - timedelta(minutes=5),
    )
    values.update(overrides)
    return AuthChallenge(**values)


def account(**overrides) -> UserDBModel:
    values = dict(
        id=uuid4(),
        name="Ana Souza",
        email="ana.souza@usp.br",
        is_enabled=True,
        password_hash=None,
        email_verified_at=NOW - timedelta(days=1),
        failed_login_count=0,
        locked_until=None,
    )
    values.update(overrides)
    return UserDBModel(**values)


class AccountServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.users = Mock(spec=UserRepository)
        self.users.fetch_by_email_any.return_value = None
        self.users.fetch_by_provider_any.return_value = None
        self.user_service = Mock(spec=UserService)
        self.challenges = Mock(spec=AuthChallengeRepository)
        self.challenges.consume.return_value = True
        self.challenges.confirm.return_value = True
        self.emails = Mock(spec=EmailRepository)
        self.emails.count_recent.return_value = 0
        self.email_service = Mock(spec=EmailService)
        self.hasher = PasswordHasher(pepper="password-pepper-of-sixteen", rounds=4)
        self.service = AccountService(
            users=self.users,
            user_service=self.user_service,
            challenges=self.challenges,
            emails=self.emails,
            email_service=self.email_service,
            hasher=self.hasher,
            challenge_pepper=CHALLENGE_PEPPER,
            public_base_url="https://datamap.example.org/",
            clock=lambda: NOW,
        )

    def stored(self) -> AuthChallenge:
        return self.challenges.replace.call_args.args[0]

    def sent(self) -> dict:
        return self.email_service.enqueue.call_args.kwargs

    def assert_refused(self, code: str, call, *args) -> None:
        with self.assertRaises(IllegalStateException) as raised:
            call(*args)
        self.assertEqual(str(raised.exception), code)

    def assert_not_found(self, call, *args) -> None:
        with self.assertRaises(NotFoundException) as raised:
            call(*args)
        self.assertEqual(str(raised.exception), "challenge_not_found")


class TestSignUp(AccountServiceTestCase):
    def test_a_sign_up_stores_the_pending_account_and_emails_a_code(self):
        challenge_id = self.service.sign_up(
            "  Ana Souza ", " Ana.Souza@USP.br ", PASSWORD
        )

        stored = self.stored()
        self.assertIsInstance(challenge_id, UUID)
        self.assertEqual(stored.id, challenge_id)
        self.assertEqual(stored.kind, "sign_up")
        self.assertEqual(stored.email, "ana.souza@usp.br")
        self.assertEqual(stored.expires_at, NOW + timedelta(minutes=15))
        self.assertEqual(stored.issued_at, NOW)
        self.assertEqual(stored.attempts, 0)
        self.assertEqual(stored.payload["name"], "Ana Souza")
        self.assertTrue(self.hasher.verify(PASSWORD, stored.payload["password_hash"]))
        sent = self.sent()
        self.assertEqual(sent["template"], "sign_up_code")
        self.assertEqual(sent["recipient"], "ana.souza@usp.br")
        self.assertRegex(sent["context"]["code"], r"^\d{6}$")
        self.assertEqual(sent["context"]["name"], "Ana Souza")
        self.assertEqual(sent["context"]["expires_in_minutes"], 15)
        self.assertEqual(sent["secret_fields"], frozenset({"code"}))
        self.assertEqual(sent["related_type"], "auth_challenge")
        self.assertEqual(sent["related_id"], challenge_id)
        self.assertEqual(
            stored.secret_hash,
            code_hash(CHALLENGE_PEPPER, challenge_id, sent["context"]["code"]),
        )

    def test_the_password_itself_is_never_stored_or_sent(self):
        self.service.sign_up("Ana Souza", "ana.souza@usp.br", PASSWORD)

        self.assertNotIn(PASSWORD, str(self.stored().payload))
        self.assertNotIn(PASSWORD, str(self.sent()))

    def test_a_password_outside_ten_to_128_characters_is_refused(self):
        for password in ("a" * 9, "a" * 129):
            with self.subTest(length=len(password)):
                self.assert_refused(
                    "invalid_password",
                    self.service.sign_up,
                    "Ana Souza",
                    "ana.souza@usp.br",
                    password,
                )
        self.challenges.replace.assert_not_called()

    def test_a_malformed_email_is_refused(self):
        self.assert_refused(
            "invalid_email", self.service.sign_up, "Ana Souza", "not-an-email", PASSWORD
        )

    def test_a_blank_name_is_refused(self):
        self.assert_refused(
            "invalid_name", self.service.sign_up, "   ", "ana.souza@usp.br", PASSWORD
        )

    def test_the_cap_counts_every_code_and_link_sent_to_the_address_in_the_last_hour(
        self,
    ):
        self.service.sign_up("Ana Souza", "ana.souza@usp.br", PASSWORD)

        self.emails.count_recent.assert_called_once_with(
            "ana.souza@usp.br",
            ["sign_up_code", "email_verification_code", "password_reset"],
            NOW - timedelta(hours=1),
        )

    def test_four_earlier_codes_still_allow_a_fifth(self):
        self.emails.count_recent.return_value = 4

        self.service.sign_up("Ana Souza", "ana.souza@usp.br", PASSWORD)

        self.email_service.enqueue.assert_called_once()

    def test_past_five_codes_an_hour_a_challenge_is_returned_but_nothing_is_sent(self):
        self.emails.count_recent.return_value = 5

        with patch("app.service.account.new_code", return_value=CODE):
            challenge_id = self.service.sign_up(
                "Ana Souza", "ana.souza@usp.br", PASSWORD
            )

        self.assertEqual(self.stored().id, challenge_id)
        self.assertNotEqual(
            self.stored().secret_hash, code_hash(CHALLENGE_PEPPER, challenge_id, CODE)
        )
        self.email_service.enqueue.assert_not_called()

    def test_a_failure_to_queue_still_answers_with_the_challenge(self):
        self.email_service.enqueue.side_effect = RuntimeError("database gone")

        with self.assertLogs("service:AccountService", level="ERROR"):
            challenge_id = self.service.sign_up(
                "Ana Souza", "ana.souza@usp.br", PASSWORD
            )

        self.assertEqual(self.stored().id, challenge_id)


class TestConfirmSignUp(AccountServiceTestCase):
    def pending(self, **overrides) -> AuthChallenge:
        pending = challenge(
            payload={"name": "Ana Souza", "password_hash": self.hasher.hash(PASSWORD)},
            **overrides,
        )
        self.challenges.fetch.return_value = pending
        return pending

    def test_the_right_code_creates_a_confirmed_account_with_the_password(self):
        pending = self.pending()
        created = uuid4()
        self.user_service.create.return_value = created

        self.assertEqual(self.service.confirm_sign_up(pending.id, CODE), created)

        self.challenges.confirm.assert_called_once_with(pending.id, NOW)
        self.challenges.consume.assert_not_called()
        user = self.user_service.create.call_args.args[0]
        self.assertEqual(
            (user.name, user.email, user.providers, user.roles),
            ("Ana Souza", "ana.souza@usp.br", [], []),
        )
        self.assertEqual(
            self.user_service.create.call_args.kwargs,
            {
                "password_hash": pending.payload["password_hash"],
                "email_verified_at": NOW,
            },
        )

    def test_an_existing_account_gets_the_password_and_its_email_confirmed(self):
        pending = self.pending()
        existing = account(email="Ana.Souza@usp.br", email_verified_at=None)
        self.users.fetch_by_email_any.return_value = existing

        self.assertEqual(self.service.confirm_sign_up(pending.id, CODE), existing.id)

        self.users.fetch_by_email_any.assert_called_once_with("ana.souza@usp.br")
        self.users.set_password.assert_called_once_with(
            existing.id, pending.payload["password_hash"]
        )
        self.users.verify_email.assert_called_once_with(
            existing.id, "ana.souza@usp.br", NOW
        )
        self.user_service.create.assert_not_called()

    def test_surrounding_spaces_in_a_code_are_ignored(self):
        pending = self.pending()

        self.service.confirm_sign_up(pending.id, f" {CODE} ")

        self.challenges.confirm.assert_called_once_with(pending.id, NOW)

    def test_a_wrong_code_counts_an_attempt(self):
        pending = self.pending()
        self.challenges.record_failed_attempt.return_value = 1

        self.assert_refused(
            "code_invalid", self.service.confirm_sign_up, pending.id, "000000"
        )

        self.challenges.record_failed_attempt.assert_called_once_with(
            pending.id, 5, NOW
        )
        self.challenges.confirm.assert_not_called()
        self.user_service.create.assert_not_called()

    def test_the_fifth_wrong_code_uses_the_challenge_up(self):
        pending = self.pending()
        self.challenges.record_failed_attempt.return_value = 5

        self.assert_refused(
            "code_attempts_exceeded", self.service.confirm_sign_up, pending.id, "000000"
        )

    def test_a_wrong_code_on_a_challenge_consumed_meanwhile_is_invalid(self):
        pending = self.pending()
        self.challenges.record_failed_attempt.return_value = None

        self.assert_refused(
            "code_invalid", self.service.confirm_sign_up, pending.id, "000000"
        )

    def test_an_expired_code_is_refused_and_consumes_the_challenge(self):
        pending = self.pending(expires_at=NOW)

        self.assert_refused(
            "code_expired", self.service.confirm_sign_up, pending.id, CODE
        )

        self.challenges.consume.assert_called_once_with(pending.id, NOW)
        self.challenges.confirm.assert_not_called()
        self.user_service.create.assert_not_called()

    def test_a_used_code_does_not_work_again(self):
        pending = self.pending(
            consumed_at=NOW - timedelta(minutes=1),
            confirmed_at=NOW - timedelta(minutes=1),
        )

        self.assert_refused(
            "code_invalid", self.service.confirm_sign_up, pending.id, CODE
        )

    def test_a_challenge_used_up_by_wrong_codes_stays_so(self):
        pending = self.pending(consumed_at=NOW - timedelta(minutes=1), attempts=5)

        self.assert_refused(
            "code_attempts_exceeded", self.service.confirm_sign_up, pending.id, CODE
        )

    def test_a_challenge_that_expired_stays_expired(self):
        pending = self.pending(
            expires_at=NOW - timedelta(minutes=10),
            consumed_at=NOW - timedelta(minutes=5),
        )

        self.assert_refused(
            "code_expired", self.service.confirm_sign_up, pending.id, CODE
        )

    def test_a_code_confirmed_concurrently_is_invalid(self):
        pending = self.pending()
        self.challenges.confirm.return_value = False

        self.assert_refused(
            "code_invalid", self.service.confirm_sign_up, pending.id, CODE
        )
        self.user_service.create.assert_not_called()

    def test_an_unknown_challenge_is_not_found(self):
        self.challenges.fetch.return_value = None

        self.assert_not_found(self.service.confirm_sign_up, uuid4(), CODE)

    def test_a_challenge_of_another_kind_is_not_found(self):
        other = challenge(
            kind=ChallengeKind.EMAIL_VERIFICATION,
            payload={"orcid": ORCID, "name": "Ana Souza"},
        )
        self.challenges.fetch.return_value = other

        self.assert_not_found(self.service.confirm_sign_up, other.id, CODE)


class TestRequestEmailVerification(AccountServiceTestCase):
    def test_a_request_stores_the_orcid_and_emails_a_code_naming_it(self):
        challenge_id = self.service.request_email_verification(
            "https://orcid.org/0000-0002-1825-0097", "Ana.Souza@usp.br", "Ana Souza"
        )

        stored = self.stored()
        self.assertEqual(stored.id, challenge_id)
        self.assertEqual(stored.kind, "email_verification")
        self.assertEqual(stored.email, "ana.souza@usp.br")
        self.assertEqual(stored.payload, {"orcid": ORCID, "name": "Ana Souza"})
        sent = self.sent()
        self.assertEqual(sent["template"], "email_verification_code")
        self.assertEqual(sent["context"]["orcid"], ORCID)
        self.assertRegex(sent["context"]["code"], r"^\d{6}$")

    def test_a_malformed_orcid_is_refused(self):
        self.assert_refused(
            "invalid_orcid",
            self.service.request_email_verification,
            "0000-0002-1825-0098",
            "ana.souza@usp.br",
            "Ana Souza",
        )


class TestConfirmEmailVerification(AccountServiceTestCase):
    def setUp(self):
        super().setUp()
        self.pending = challenge(
            kind=ChallengeKind.EMAIL_VERIFICATION,
            payload={"orcid": ORCID, "name": "Ana Souza"},
        )
        self.challenges.fetch.return_value = self.pending

    def confirm(self) -> UUID:
        return self.service.confirm_email_verification(self.pending.id, CODE)

    def test_an_orcid_account_without_this_email_takes_it_confirmed(self):
        orcid_account = account(
            email="0000000218250097@fake.mail.com", email_verified_at=None
        )
        self.users.fetch_by_provider_any.return_value = orcid_account

        self.assertEqual(self.confirm(), orcid_account.id)

        self.users.fetch_by_provider_any.assert_called_once_with(
            provider_name="orcid", reference=ORCID
        )
        self.users.fetch_by_provider.assert_not_called()
        self.users.verify_email.assert_called_once_with(
            orcid_account.id, "ana.souza@usp.br", NOW
        )

    def test_an_orcid_account_that_already_has_this_email_is_confirmed(self):
        orcid_account = account(email_verified_at=None)
        self.users.fetch_by_provider_any.return_value = orcid_account
        self.users.fetch_by_email_any.return_value = orcid_account

        self.assertEqual(self.confirm(), orcid_account.id)

        self.users.verify_email.assert_called_once_with(
            orcid_account.id, "ana.souza@usp.br", NOW
        )

    def test_an_orcid_account_and_another_account_with_the_email_conflict(self):
        self.users.fetch_by_provider_any.return_value = account()
        self.users.fetch_by_email_any.return_value = account()

        with self.assertRaises(ConflictException) as raised:
            self.confirm()

        self.assertEqual(str(raised.exception), "email_belongs_to_another_account")
        self.users.verify_email.assert_not_called()
        self.user_service.add_provider.assert_not_called()

    def test_an_email_account_without_the_orcid_gets_it_attached(self):
        by_email = account()
        self.users.fetch_by_email_any.return_value = by_email

        self.assertEqual(self.confirm(), by_email.id)

        self.user_service.add_provider.assert_called_once_with(
            id=by_email.id, provider="orcid", reference=ORCID
        )
        self.users.verify_email.assert_called_once_with(
            by_email.id, "ana.souza@usp.br", NOW
        )

    def test_a_disabled_account_holding_the_email_is_not_reused(self):
        self.users.fetch_by_email_any.return_value = account(is_enabled=False)

        with self.assertRaises(ConflictException) as raised:
            self.confirm()

        self.assertEqual(str(raised.exception), "email_belongs_to_another_account")
        self.user_service.add_provider.assert_not_called()

    def test_neither_creates_a_confirmed_account_with_the_orcid(self):
        created = uuid4()
        self.user_service.create.return_value = created

        self.assertEqual(self.confirm(), created)

        user = self.user_service.create.call_args.args[0]
        self.assertEqual(user.name, "Ana Souza")
        self.assertEqual(user.email, "ana.souza@usp.br")
        self.assertEqual(user.providers, [UserProvider(name="orcid", reference=ORCID)])
        self.assertEqual(user.roles, [])
        self.assertEqual(
            self.user_service.create.call_args.kwargs, {"email_verified_at": NOW}
        )

    def assert_conflict_changes_nothing(self) -> None:
        with self.assertRaises(ConflictException) as raised:
            self.confirm()

        self.assertEqual(str(raised.exception), "email_belongs_to_another_account")
        self.users.verify_email.assert_not_called()
        self.user_service.add_provider.assert_not_called()
        self.user_service.create.assert_not_called()

    def test_a_disabled_orcid_account_and_a_new_email_conflict(self):
        self.users.fetch_by_provider_any.return_value = account(
            email="0000000218250097@fake.mail.com", is_enabled=False
        )

        self.assert_conflict_changes_nothing()

    def test_a_disabled_orcid_account_and_another_enabled_account_conflict(self):
        self.users.fetch_by_provider_any.return_value = account(
            email="0000000218250097@fake.mail.com", is_enabled=False
        )
        self.users.fetch_by_email_any.return_value = account()

        self.assert_conflict_changes_nothing()

    def test_a_disabled_orcid_account_holding_this_email_conflicts(self):
        disabled = account(is_enabled=False, email_verified_at=None)
        self.users.fetch_by_provider_any.return_value = disabled
        self.users.fetch_by_email_any.return_value = disabled

        self.assert_conflict_changes_nothing()

    def test_a_disabled_holder_found_beside_an_enabled_one_conflicts(self):
        disabled_holder = account(is_enabled=False)
        self.users.fetch_by_provider_any.return_value = disabled_holder
        self.users.fetch_by_email_any.return_value = account(email="ana.souza@usp.br")

        self.assert_conflict_changes_nothing()
        self.users.fetch_by_provider_any.assert_called_once_with(
            provider_name="orcid", reference=ORCID
        )

    def test_a_sign_up_challenge_is_not_found(self):
        other = challenge(kind=ChallengeKind.SIGN_UP)
        self.challenges.fetch.return_value = other

        self.assert_not_found(self.service.confirm_email_verification, other.id, CODE)

    def test_a_password_reset_challenge_is_not_found(self):
        other = challenge(kind=ChallengeKind.PASSWORD_RESET)
        self.challenges.fetch.return_value = other

        self.assert_not_found(self.service.confirm_email_verification, other.id, CODE)

    def test_a_wrong_code_changes_no_account(self):
        self.challenges.record_failed_attempt.return_value = 1

        self.assert_refused(
            "code_invalid",
            self.service.confirm_email_verification,
            self.pending.id,
            "000000",
        )

        self.users.fetch_by_provider_any.assert_not_called()
        self.users.verify_email.assert_not_called()


class TestResend(AccountServiceTestCase):
    def pending(self, kind: ChallengeKind = ChallengeKind.SIGN_UP, **overrides):
        payload = (
            {"orcid": ORCID, "name": "Ana Souza"}
            if kind == ChallengeKind.EMAIL_VERIFICATION
            else {"name": "Ana Souza", "password_hash": "$2b$04$" + "x" * 53}
        )
        pending = challenge(kind=kind, payload=payload, **overrides)
        self.challenges.fetch.return_value = pending
        return pending

    def test_a_resend_within_ninety_seconds_of_the_last_send_is_refused(self):
        pending = self.pending(issued_at=NOW - timedelta(seconds=89))

        with self.assertRaises(TooManyRequestsException) as raised:
            self.service.resend(pending.id)

        self.assertEqual(str(raised.exception), "resend_too_soon")
        self.challenges.reissue.assert_not_called()
        self.email_service.enqueue.assert_not_called()

    def test_after_ninety_seconds_a_new_code_replaces_the_old_one(self):
        pending = self.pending(issued_at=NOW - timedelta(seconds=90))

        self.service.resend(pending.id)

        challenge_id, secret_hash, expires_at, issued_at = (
            self.challenges.reissue.call_args.args
        )
        code = self.sent()["context"]["code"]
        self.assertEqual(challenge_id, pending.id)
        self.assertEqual(secret_hash, code_hash(CHALLENGE_PEPPER, pending.id, code))
        self.assertEqual((expires_at, issued_at), (NOW + timedelta(minutes=15), NOW))
        self.assertEqual(self.sent()["template"], "sign_up_code")
        self.assertEqual(self.sent()["recipient"], "ana.souza@usp.br")
        self.assertEqual(self.sent()["related_id"], pending.id)

    def test_an_email_verification_resend_names_the_orcid_again(self):
        pending = self.pending(kind=ChallengeKind.EMAIL_VERIFICATION)

        self.service.resend(pending.id)

        self.assertEqual(self.sent()["template"], "email_verification_code")
        self.assertEqual(self.sent()["context"]["orcid"], ORCID)

    def test_an_expired_challenge_can_be_resent(self):
        pending = self.pending(
            expires_at=NOW - timedelta(minutes=2),
            consumed_at=NOW - timedelta(minutes=1),
            issued_at=NOW - timedelta(minutes=17),
        )

        self.service.resend(pending.id)

        self.challenges.reissue.assert_called_once()

    def test_a_challenge_used_up_by_wrong_codes_can_be_resent(self):
        pending = self.pending(attempts=5, consumed_at=NOW - timedelta(minutes=1))

        self.service.resend(pending.id)

        self.challenges.reissue.assert_called_once()

    def test_a_challenge_replaced_by_a_newer_one_can_be_resent(self):
        pending = self.pending(consumed_at=NOW - timedelta(minutes=1))

        self.service.resend(pending.id)

        self.challenges.reissue.assert_called_once()

    def test_a_confirmed_challenge_cannot_be_resent(self):
        pending = self.pending(
            consumed_at=NOW - timedelta(minutes=1),
            confirmed_at=NOW - timedelta(minutes=1),
        )

        self.assert_not_found(self.service.resend, pending.id)
        self.challenges.reissue.assert_not_called()

    def test_a_password_reset_cannot_be_resent(self):
        pending = self.pending(kind=ChallengeKind.PASSWORD_RESET)

        self.assert_not_found(self.service.resend, pending.id)

    def test_an_unknown_challenge_is_not_found(self):
        self.challenges.fetch.return_value = None

        self.assert_not_found(self.service.resend, uuid4())

    def test_past_the_hourly_cap_a_resend_sends_nothing_and_keeps_the_old_code(self):
        pending = self.pending()
        self.emails.count_recent.return_value = 5

        self.service.resend(pending.id)

        self.challenges.touch.assert_called_once_with(pending.id, NOW)
        self.challenges.reissue.assert_not_called()
        self.email_service.enqueue.assert_not_called()
