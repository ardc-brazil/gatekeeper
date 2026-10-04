import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.too_many_requests import TooManyRequestsException
from app.exception.unauthorized import UnauthorizedException
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
from app.service.share_token import hash_token
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

    def test_a_name_with_a_control_character_is_refused(self):
        for name in (
            "Ana\nSouza",
            "Ana\rSouza",
            "Ana\tSouza",
            "Ana Souza\n",
            "Ana\x00Souza",
            "Ana\x7fSouza",
            "Ana\x85Souza",
        ):
            with self.subTest(name=repr(name)):
                self.assert_refused(
                    "invalid_name",
                    self.service.sign_up,
                    name,
                    "ana.souza@usp.br",
                    PASSWORD,
                )
                self.assert_refused(
                    "invalid_name",
                    self.service.request_email_verification,
                    ORCID,
                    "ana.souza@usp.br",
                    name,
                )
        self.challenges.replace.assert_not_called()

    def test_the_cap_counts_every_code_and_link_sent_to_the_address_in_the_last_hour(
        self,
    ):
        self.service.sign_up("Ana Souza", "ana.souza@usp.br", PASSWORD)

        self.emails.count_recent.assert_called_once_with(
            "ana.souza@usp.br",
            [
                "sign_up_code",
                "email_verification_code",
                "password_reset",
                "sign_up_existing_account",
            ],
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


class TestSignUpForAnExistingAccount(AccountServiceTestCase):
    def existing(self, **overrides) -> UserDBModel:
        found = account(password_hash=self.hasher.hash(PASSWORD), **overrides)
        self.users.fetch_by_email_any.return_value = found
        return found

    def stored_by_kind(self) -> dict:
        return {
            call.args[0].kind: call.args[0]
            for call in self.challenges.replace.call_args_list
        }

    def test_an_account_with_a_password_is_emailed_a_reset_link_not_a_code(self):
        found = self.existing()

        with patch("app.service.account.new_code", return_value=CODE):
            challenge_id = self.service.sign_up(
                "Someone Else", " Ana.Souza@USP.br ", PASSWORD
            )

        self.users.fetch_by_email_any.assert_called_once_with("ana.souza@usp.br")
        stored = self.stored_by_kind()
        reset, answered = stored["password_reset"], stored["sign_up"]
        self.assertEqual(answered.id, challenge_id)
        self.assertEqual(answered.email, "ana.souza@usp.br")
        self.assertEqual(
            answered.payload, {"name": "Someone Else", "existing_account": True}
        )
        self.assertNotEqual(
            answered.secret_hash, code_hash(CHALLENGE_PEPPER, challenge_id, CODE)
        )
        self.assertEqual(reset.user_id, found.id)
        self.assertEqual(reset.email, "ana.souza@usp.br")
        self.assertEqual(reset.expires_at, NOW + timedelta(hours=1))
        self.assertEqual(reset.issued_at, NOW)
        self.email_service.enqueue.assert_called_once()
        sent = self.sent()
        prefix = "https://datamap.example.org/account/reset-password/"
        link = sent["context"]["link"]
        self.assertEqual(sent["template"], "sign_up_existing_account")
        self.assertEqual(sent["recipient"], "ana.souza@usp.br")
        self.assertEqual(sent["context"]["name"], "Ana Souza")
        self.assertEqual(sent["secret_fields"], frozenset({"link"}))
        self.assertEqual(sent["related_id"], reset.id)
        self.assertTrue(link.startswith(prefix))
        self.assertEqual(reset.secret_hash, hash_token(link[len(prefix) :]))
        self.assertNotIn("code", sent["context"])

    def test_past_the_hourly_cap_nothing_is_sent_and_no_link_is_made(self):
        self.existing()
        self.emails.count_recent.return_value = 5

        challenge_id = self.service.sign_up("Ana Souza", "ana.souza@usp.br", PASSWORD)

        self.assertEqual(set(self.stored_by_kind()), {"sign_up"})
        self.assertEqual(self.stored().id, challenge_id)
        self.email_service.enqueue.assert_not_called()

    def test_an_account_without_a_password_still_gets_a_code(self):
        self.users.fetch_by_email_any.return_value = account(password_hash=None)

        self.service.sign_up("Ana Souza", "ana.souza@usp.br", PASSWORD)

        self.assertEqual(self.sent()["template"], "sign_up_code")
        self.assertIn("password_hash", self.stored().payload)

    def test_a_disabled_account_with_a_password_still_gets_a_code(self):
        self.existing(is_enabled=False)

        self.service.sign_up("Ana Souza", "ana.souza@usp.br", PASSWORD)

        self.assertEqual(self.sent()["template"], "sign_up_code")

    def test_a_resend_of_the_answer_sends_the_link_again_not_a_code(self):
        found = self.existing()
        answered = challenge(
            payload={"name": "Ana Souza", "existing_account": True},
            issued_at=NOW - timedelta(seconds=91),
        )
        self.challenges.fetch.return_value = answered

        self.service.resend(answered.id)

        self.challenges.reissue.assert_not_called()
        self.challenges.touch.assert_called_once_with(answered.id, NOW)
        self.assertEqual(self.stored().user_id, found.id)
        self.assertEqual(self.sent()["template"], "sign_up_existing_account")

    def test_a_resend_of_the_answer_within_ninety_seconds_is_refused(self):
        self.existing()
        answered = challenge(
            payload={"name": "Ana Souza", "existing_account": True},
            issued_at=NOW - timedelta(seconds=89),
        )
        self.challenges.fetch.return_value = answered

        with self.assertRaises(TooManyRequestsException):
            self.service.resend(answered.id)

        self.email_service.enqueue.assert_not_called()

    def test_a_resend_of_the_answer_past_the_cap_sends_nothing(self):
        self.existing()
        self.emails.count_recent.return_value = 5
        answered = challenge(
            payload={"name": "Ana Souza", "existing_account": True},
            issued_at=NOW - timedelta(seconds=91),
        )
        self.challenges.fetch.return_value = answered

        self.service.resend(answered.id)

        self.challenges.replace.assert_not_called()
        self.email_service.enqueue.assert_not_called()


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
        self.users.set_password_and_verify_email.assert_called_once_with(
            existing.id, pending.payload["password_hash"], "ana.souza@usp.br", NOW
        )
        self.users.set_password.assert_not_called()
        self.users.verify_email.assert_not_called()
        self.user_service.create.assert_not_called()

    def test_an_existing_account_has_its_open_reset_links_retired(self):
        pending = self.pending()
        existing = account()
        self.users.fetch_by_email_any.return_value = existing

        self.service.confirm_sign_up(pending.id, CODE)

        self.challenges.consume_open_for_user.assert_called_once_with(
            existing.id, ChallengeKind.PASSWORD_RESET, NOW
        )

    def test_a_disabled_account_with_the_email_conflicts_and_is_left_alone(self):
        pending = self.pending()
        self.users.fetch_by_email_any.return_value = account(is_enabled=False)

        with self.assertRaises(ConflictException) as raised:
            self.service.confirm_sign_up(pending.id, CODE)

        self.assertEqual(str(raised.exception), "email_belongs_to_another_account")
        self.users.set_password.assert_not_called()
        self.users.verify_email.assert_not_called()
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
        pending = self.pending(
            kind=ChallengeKind.EMAIL_VERIFICATION,
            consumed_at=NOW - timedelta(minutes=1),
        )

        self.service.resend(pending.id)

        self.challenges.reissue.assert_called_once()

    def test_a_sign_up_replaced_without_its_password_cannot_be_resent(self):
        replaced = challenge(
            payload={"name": "Ana Souza"}, consumed_at=NOW - timedelta(minutes=1)
        )
        self.challenges.fetch.return_value = replaced

        self.assert_not_found(self.service.resend, replaced.id)
        self.challenges.reissue.assert_not_called()
        self.email_service.enqueue.assert_not_called()

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


class TestLogin(AccountServiceTestCase):
    def with_password(self, **overrides) -> UserDBModel:
        found = account(password_hash=self.hasher.hash(PASSWORD), **overrides)
        self.users.fetch_by_email_any.return_value = found
        return found

    def assert_invalid_credentials(self, email: str, password: str) -> None:
        with self.assertRaises(UnauthorizedException) as raised:
            self.service.login(email, password)
        self.assertEqual(str(raised.exception), "invalid_credentials")

    def test_the_right_password_signs_in_and_clears_the_failures(self):
        found = self.with_password(failed_login_count=3)

        self.assertEqual(self.service.login(" Ana.Souza@USP.br ", PASSWORD), found.id)

        self.users.fetch_by_email_any.assert_called_once_with("ana.souza@usp.br")
        self.users.clear_failed_logins.assert_called_once_with(found.id)

    def test_a_clean_sign_in_writes_nothing(self):
        self.with_password()

        self.service.login("ana.souza@usp.br", PASSWORD)

        self.users.clear_failed_logins.assert_not_called()

    def test_a_wrong_password_is_counted_toward_the_lock(self):
        found = self.with_password()

        self.assert_invalid_credentials("ana.souza@usp.br", "not the password")

        self.users.record_failed_login.assert_called_once_with(
            found.id, 10, NOW + timedelta(minutes=15)
        )

    def test_an_unknown_email_still_runs_bcrypt(self):
        with patch.object(self.hasher, "burn") as burn:
            self.assert_invalid_credentials("nobody@usp.br", PASSWORD)

        burn.assert_called_once_with(PASSWORD)
        self.users.record_failed_login.assert_not_called()

    def test_a_malformed_email_is_answered_like_an_unknown_one(self):
        with patch.object(self.hasher, "burn") as burn:
            self.assert_invalid_credentials("not-an-email", PASSWORD)

        burn.assert_called_once_with(PASSWORD)
        self.users.fetch_by_email_any.assert_not_called()

    def test_an_account_without_a_password_is_refused_after_bcrypt(self):
        self.users.fetch_by_email_any.return_value = account(password_hash=None)

        with patch.object(self.hasher, "burn") as burn:
            self.assert_invalid_credentials("ana.souza@usp.br", PASSWORD)

        burn.assert_called_once_with(PASSWORD)

    def test_a_locked_account_is_refused_even_with_the_right_password(self):
        self.with_password(locked_until=NOW + timedelta(minutes=1))

        with patch.object(self.hasher, "burn") as burn:
            self.assert_invalid_credentials("ana.souza@usp.br", PASSWORD)

        burn.assert_called_once_with(PASSWORD)
        self.users.record_failed_login.assert_not_called()
        self.users.clear_failed_logins.assert_not_called()

    def test_an_expired_lock_lets_the_right_password_in(self):
        found = self.with_password(
            failed_login_count=10, locked_until=NOW - timedelta(seconds=1)
        )

        self.assertEqual(self.service.login("ana.souza@usp.br", PASSWORD), found.id)

        self.users.clear_failed_logins.assert_called_once_with(found.id)

    def test_after_a_lock_expires_the_first_wrong_password_locks_again(self):
        found = self.with_password(failed_login_count=10, locked_until=NOW)

        self.assert_invalid_credentials("ana.souza@usp.br", "not the password")

        self.users.record_failed_login.assert_called_once_with(
            found.id, 10, NOW + timedelta(minutes=15)
        )
        self.users.clear_failed_logins.assert_not_called()

    def test_an_unconfirmed_email_is_refused(self):
        self.with_password(email_verified_at=None)

        self.assert_invalid_credentials("ana.souza@usp.br", PASSWORD)

        self.users.clear_failed_logins.assert_not_called()

    def test_a_disabled_account_is_refused(self):
        self.with_password(is_enabled=False)

        self.assert_invalid_credentials("ana.souza@usp.br", PASSWORD)


class TestRequestPasswordReset(AccountServiceTestCase):
    def test_a_confirmed_account_gets_a_link_valid_for_an_hour(self):
        found = account()
        self.users.fetch_by_email_any.return_value = found

        self.service.request_password_reset(" Ana.Souza@usp.br ")

        stored = self.stored()
        self.assertEqual(stored.kind, "password_reset")
        self.assertEqual(stored.email, "ana.souza@usp.br")
        self.assertEqual(stored.user_id, found.id)
        self.assertEqual(stored.expires_at, NOW + timedelta(hours=1))
        self.assertEqual(stored.issued_at, NOW)
        sent = self.sent()
        prefix = "https://datamap.example.org/account/reset-password/"
        link = sent["context"]["link"]
        self.assertEqual(sent["template"], "password_reset")
        self.assertEqual(sent["recipient"], "ana.souza@usp.br")
        self.assertEqual(sent["context"]["name"], "Ana Souza")
        self.assertEqual(sent["secret_fields"], frozenset({"link"}))
        self.assertEqual(sent["related_id"], stored.id)
        self.assertTrue(link.startswith(prefix))
        self.assertEqual(stored.secret_hash, hash_token(link[len(prefix) :]))

    def test_an_account_without_a_password_can_ask_for_one(self):
        self.users.fetch_by_email_any.return_value = account(password_hash=None)

        self.service.request_password_reset("ana.souza@usp.br")

        self.email_service.enqueue.assert_called_once()

    def test_an_unknown_email_gets_nothing(self):
        self.service.request_password_reset("nobody@usp.br")

        self.challenges.replace.assert_not_called()
        self.email_service.enqueue.assert_not_called()

    def test_an_unconfirmed_email_gets_nothing(self):
        self.users.fetch_by_email_any.return_value = account(email_verified_at=None)

        self.service.request_password_reset("ana.souza@usp.br")

        self.email_service.enqueue.assert_not_called()

    def test_a_disabled_account_gets_nothing(self):
        self.users.fetch_by_email_any.return_value = account(is_enabled=False)

        self.service.request_password_reset("ana.souza@usp.br")

        self.email_service.enqueue.assert_not_called()

    def test_a_malformed_email_gets_nothing_and_no_error(self):
        self.assertIsNone(self.service.request_password_reset("not-an-email"))

        self.users.fetch_by_email_any.assert_not_called()

    def test_past_the_hourly_cap_nothing_is_sent(self):
        self.users.fetch_by_email_any.return_value = account()
        self.emails.count_recent.return_value = 5

        self.service.request_password_reset("ana.souza@usp.br")

        self.challenges.replace.assert_not_called()
        self.email_service.enqueue.assert_not_called()


class TestConfirmPasswordReset(AccountServiceTestCase):
    def pending(self, **overrides) -> AuthChallenge:
        values = dict(user_id=uuid4())
        values.update(overrides)
        pending = challenge(
            kind=ChallengeKind.PASSWORD_RESET,
            secret_hash=hash_token("tok"),
            **values,
        )
        self.challenges.fetch_open_by_secret.return_value = pending
        return pending

    def test_a_valid_token_sets_the_password_and_retires_every_open_link(self):
        pending = self.pending()

        self.service.confirm_password_reset("tok", "a brand new password")

        self.challenges.fetch_open_by_secret.assert_called_once_with(
            hash_token("tok"), ChallengeKind.PASSWORD_RESET
        )
        user_id, stored_hash = self.users.set_password.call_args.args
        self.assertEqual(user_id, pending.user_id)
        self.assertTrue(self.hasher.verify("a brand new password", stored_hash))
        self.challenges.consume_open_for_user.assert_called_once_with(
            pending.user_id, ChallengeKind.PASSWORD_RESET, NOW
        )

    def test_the_token_is_consumed_before_the_password_is_set(self):
        pending = self.pending()
        manager = Mock()
        manager.attach_mock(self.challenges.consume, "consume")
        manager.attach_mock(self.users.set_password, "set_password")

        self.service.confirm_password_reset("tok", "a brand new password")

        self.challenges.consume.assert_called_once_with(pending.id, NOW)
        self.assertEqual(
            [call[0] for call in manager.mock_calls], ["consume", "set_password"]
        )

    def test_a_token_already_consumed_by_a_concurrent_submit_is_invalid(self):
        self.pending()
        self.challenges.consume.return_value = False

        self.assert_refused(
            "token_invalid",
            self.service.confirm_password_reset,
            "tok",
            "a brand new password",
        )
        self.users.set_password.assert_not_called()

    def test_an_unknown_or_used_token_is_invalid(self):
        self.challenges.fetch_open_by_secret.return_value = None

        self.assert_refused(
            "token_invalid",
            self.service.confirm_password_reset,
            "tok",
            "a brand new password",
        )
        self.users.set_password.assert_not_called()

    def test_a_token_without_a_user_is_invalid(self):
        self.pending(user_id=None)

        self.assert_refused(
            "token_invalid",
            self.service.confirm_password_reset,
            "tok",
            "a brand new password",
        )
        self.users.set_password.assert_not_called()

    def test_an_expired_token_is_invalid(self):
        self.pending(expires_at=NOW)

        self.assert_refused(
            "token_invalid",
            self.service.confirm_password_reset,
            "tok",
            "a brand new password",
        )
        self.users.set_password.assert_not_called()

    def test_a_short_password_is_refused_before_the_token_is_looked_at(self):
        self.assert_refused(
            "invalid_password", self.service.confirm_password_reset, "tok", "too short"
        )

        self.challenges.fetch_open_by_secret.assert_not_called()


class TestChangePassword(AccountServiceTestCase):
    def test_the_current_password_lets_a_new_one_in(self):
        found = account(password_hash=self.hasher.hash(PASSWORD))
        self.users.fetch_by_id.return_value = found

        self.service.change_password(found.id, PASSWORD, "a brand new password")

        self.users.fetch_by_id.assert_called_once_with(id=found.id)
        user_id, stored_hash = self.users.set_password.call_args.args
        self.assertEqual(user_id, found.id)
        self.assertTrue(self.hasher.verify("a brand new password", stored_hash))

    def test_a_wrong_current_password_is_refused(self):
        found = account(password_hash=self.hasher.hash(PASSWORD))
        self.users.fetch_by_id.return_value = found

        with self.assertRaises(UnauthorizedException) as raised:
            self.service.change_password(
                found.id, "not the password", "a brand new password"
            )

        self.assertEqual(str(raised.exception), "invalid_credentials")
        self.users.set_password.assert_not_called()
        self.users.record_failed_login.assert_called_once_with(
            found.id, 10, NOW + timedelta(minutes=15)
        )

    def test_a_locked_account_is_refused_even_with_the_right_password(self):
        found = account(
            password_hash=self.hasher.hash(PASSWORD),
            failed_login_count=10,
            locked_until=NOW + timedelta(minutes=1),
        )
        self.users.fetch_by_id.return_value = found

        with self.assertRaises(UnauthorizedException) as raised:
            self.service.change_password(found.id, PASSWORD, "a brand new password")

        self.assertEqual(str(raised.exception), "invalid_credentials")
        self.users.set_password.assert_not_called()
        self.users.record_failed_login.assert_not_called()

    def test_an_expired_lock_lets_the_right_password_change_it(self):
        found = account(
            password_hash=self.hasher.hash(PASSWORD),
            failed_login_count=10,
            locked_until=NOW,
        )
        self.users.fetch_by_id.return_value = found

        self.service.change_password(found.id, PASSWORD, "a brand new password")

        self.users.set_password.assert_called_once()

    def test_a_change_retires_every_open_reset_link(self):
        found = account(password_hash=self.hasher.hash(PASSWORD))
        self.users.fetch_by_id.return_value = found

        self.service.change_password(found.id, PASSWORD, "a brand new password")

        self.challenges.consume_open_for_user.assert_called_once_with(
            found.id, ChallengeKind.PASSWORD_RESET, NOW
        )

    def test_an_account_without_a_password_is_refused(self):
        self.users.fetch_by_id.return_value = account(password_hash=None)

        with self.assertRaises(UnauthorizedException) as raised:
            self.service.change_password(uuid4(), PASSWORD, "a brand new password")

        self.assertEqual(str(raised.exception), "invalid_credentials")

    def test_a_short_new_password_is_refused(self):
        self.assert_refused(
            "invalid_password",
            self.service.change_password,
            uuid4(),
            PASSWORD,
            "too short",
        )

        self.users.fetch_by_id.assert_not_called()
