# RFC 008 PR 1 — Gatekeeper email and password authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the gatekeeper everything the webapp needs for email and password accounts: credentials and confirmation state on `users`, a table of pending challenges, sign-up and ORCID email verification confirmed by a 6-digit code, password sign-in with a lock, password reset by link, password change, the four emails, and a notification to the admins for every new account. Nothing in the webapp changes in this PR.

**Architecture:** The gatekeeper owns accounts (RFC 008, decision 5). A new `AccountService` (`app/service/account.py`) holds every rule of the flows and talks to the existing `UserRepository`/`UserService`, a new `AuthChallengeRepository`, the email outbox (`EmailService.enqueue`, plus `EmailRepository.count_recent` for the hourly cap) and a `PasswordHasher` singleton. Passwords are `bcrypt(cost=10, base64(HMAC-SHA256(AUTH_PASSWORD_PEPPER, password)))`; codes are `HMAC-SHA256(AUTH_CHALLENGE_PEPPER, challenge_id || code)`; reset tokens reuse `new_token()`/`hash_token()`. The `/v1/auth/*` router is guarded by `authenticate` only. `GET /v1/users/{id}` and `PUT /v1/users/{id}/password` use a new `authorize_self_or_policy` dependency: a caller whose `X-User-Id` equals `{id}` skips Casbin (a brand-new account has no role), anyone else goes through Casbin as today, and the password route still refuses any `{id}` other than `X-User-Id`. Every email, codes and links included, goes through the outbox and leaves on the Archivist's dispatch (every minute in production). Every route is a plain `def`, so FastAPI runs it through Starlette's `run_in_threadpool` and bcrypt never blocks the event loop. `UserService.create` enqueues `new_account_pending` for each address in `ADMIN_NOTIFICATION_EMAILS` so every creation path is covered.

**Tech Stack:** Python 3.10 (production image `python:3.10.14-alpine`), FastAPI 0.111, Starlette 0.37.2, Pydantic 2.7 / pydantic-settings, SQLAlchemy 1.4.23, Alembic, dependency-injector, bcrypt 4.0.1, Jinja2, Casbin 1.23; pytest + `unittest.mock`; integration tests against Docker (PostgreSQL, MinIO, WireMock, Mailpit).

## Global Constraints

- Spec: `docs/rfcs/008-email-password-authentication.md` (on branch `docs/rfc-008-email-password-auth`). Names, paths, bodies, statuses and `detail` codes come from `docs/superpowers/plans/2026-10-03-rfc-008-contract.md`, which wins over this plan.
- Work in the worktree `/Users/caio.maia/workspace/datamap/gatekeeper/.claude/worktrees/rfc-008-gatekeeper-auth` (called **W** below) on branch `feat/rfc-008-gatekeeper-auth`, branched from `main` (`abf1055`). Every relative path and command in this plan is relative to W.
- Never modify, stage or commit `docs/rfcs/007-notebooks.md`, the RFC 008 file or the contract file; they live in the main checkout only.
- Python 3.10 only: no `datetime.UTC`, `typing.Self`, `StrEnum`, `except*`. Enums are `class X(str, enum.Enum)`. Type hints everywhere.
- Comments (CLAUDE.md): none narrating code; one line only where a reader would otherwise undo something on purpose.
- Migration: file `migrations/versions/2026_10_03_1200-b1c2d3e4f5a6_add_email_password_authentication.py`, `revision = "b1c2d3e4f5a6"`, `down_revision = "a7b8c9d0e1f2"` (the current head, `add_members_can_edit`).
- `users` gains `password_hash String(128) NULL`, `email_verified_at DateTime(tz) NULL`, `failed_login_count Integer NOT NULL DEFAULT 0`, `locked_until DateTime(tz) NULL`. Existing rows keep `email_verified_at = NULL`. The password never becomes a `providers` row.
- `auth_challenges`: `id UUID PK`, `kind String(32)` checked to `sign_up | email_verification | password_reset`, `email String(256)` lower-cased, `secret_hash String(128) UNIQUE`, `attempts Integer DEFAULT 0`, `expires_at DateTime(tz)`, `consumed_at DateTime(tz) NULL`, `confirmed_at DateTime(tz) NULL` (set only by a successful code confirmation, which is what makes a challenge final), `issued_at DateTime(tz)` (when the current code was issued, for the resend cooldown), `user_id UUID NULL FK users ON DELETE CASCADE`, `payload JSONB DEFAULT '{}'`, `created_at DateTime(tz) DEFAULT now()`.
- Password hash: `bcrypt.hashpw(base64(HMAC-SHA256(AUTH_PASSWORD_PEPPER, password)), gensalt(rounds=10))` — 44-byte input, under bcrypt's 72-byte truncation and NUL-free. Unknown emails and accounts without a password still run one bcrypt check against a fixed dummy hash.
- Password policy: 10 to 128 characters, no composition rules; otherwise `400 {"detail": "invalid_password"}`.
- Codes: `f"{secrets.randbelow(1_000_000):06d}"`; stored as `hmac.new(AUTH_CHALLENGE_PEPPER, f"{challenge_id}{code}", sha256).hexdigest()`; valid 15 minutes; 5 attempts; single use; a new challenge of the same kind for the same email consumes the open one.
- Reset tokens: `new_token()`, stored with `hash_token()`; valid 1 hour; link `{PUBLIC_BASE_URL}/account/reset-password/{token}`; sent only to an enabled account whose email is confirmed; confirming sets the password, clears the lock and consumes every open `password_reset` challenge of the user.
- Resend: works on any code challenge whose `confirmed_at` is null — open, expired, out of attempts or replaced — and issues a new code on the same `challenge_id` (attempts 0, new `expires_at`, `consumed_at` cleared, other open challenges of the same kind and email consumed); not within 90 seconds of its last send (one production dispatch cycle of 60 seconds, so the first code has had a chance to arrive), else `429 {"detail": "resend_too_soon"}`; subject to the hourly cap; a confirmed challenge or a `password_reset` answers `404 challenge_not_found`.
- Delivery: every email, codes and links included, is enqueued through `EmailService.enqueue` and leaves on the Archivist's dispatch (`POST /internal/notifications/dispatch`, every minute in production); nothing is sent from the request. The integration tests trigger that dispatch themselves, as `test_email_delivery.py` does.
- Hourly cap: at most 5 code or link emails (`sign_up_code`, `email_verification_code`, `password_reset`) per address per hour, counted in `email_messages`; past it the endpoint still answers as usual, nothing is queued, and a new code challenge stores a hash no code can match (`400 code_invalid` to every code).
- Sign-in: every failure is `401 {"detail": "invalid_credentials"}` (unknown email, wrong password, no password, unconfirmed email, disabled, locked, malformed email). 10 consecutive wrong passwords set `locked_until = now + 15 min`; a success or a reset clears both counters.
- Error mapping, existing handlers only, body `{"detail": "<code>"}`: `IllegalStateException` → 400 (`invalid_email`, `invalid_name`, `invalid_password`, `invalid_orcid`, `code_invalid`, `code_expired`, `code_attempts_exceeded`, `token_invalid`); `UnauthorizedException` → 401 (`invalid_credentials`); `NotFoundException` → 404 (`challenge_not_found`); `ConflictException` → 409 (`email_belongs_to_another_account`); new `TooManyRequestsException` → 429 (`resend_too_soon`).
- Routes (all under `/v1`, JSON snake_case): `POST /auth/sign-up` 202 `{challenge_id}`; `POST /auth/sign-up/{challenge_id}/confirm` 200 `{user_id}`; `POST /auth/email-verifications` 202 `{challenge_id}`; `POST /auth/email-verifications/{challenge_id}/confirm` 200 `{user_id}`; `POST /auth/challenges/{challenge_id}/resend` 202 (empty); `POST /auth/login` 200 `{user_id}`; `POST /auth/password-reset` 202 (empty); `POST /auth/password-reset/confirm` 204; `PUT /users/{id}/password` 204.
- A `challenge_id` that is not a UUID answers `404 challenge_not_found`, not 422.
- User responses (`GET /users/{id}`, `GET /users/`, `GET /users/providers/{provider}/{reference}`, `PUT /users/{id}`) gain `email_verified_at` (ISO-8601 or `null`) and `has_password` (boolean).
- Templates: `sign_up_code`, `email_verification_code`, `password_reset`, `new_account_pending`, each `.html` + `.txt`, extending `base.html`/`base.txt`; `secret_fields` `{"code"}` or `{"link"}`; a code or link never appears in a subject; codes are written `Your DataMap code: NNNNNN` in the text part.
- `new_account_pending`: enqueued from `UserService.create` for each address in `ADMIN_NOTIFICATION_EMAILS` (comma-separated, empty disables), `related_type="user"`, `related_id=user_id`, `dedup_key=f"new_account_pending:{user_id}:{hash_token(address.lower())[:16]}"`; a failure to queue never undoes the account.
- Config: `AUTH_PASSWORD_PEPPER` and `AUTH_CHALLENGE_PEPPER` required, `min_length=16` (as `AUTH_CLIENT_SECRET_PEPPER`); `ADMIN_NOTIFICATION_EMAILS` default `""`.
- Self-access: `GET /users/{id}` and `PUT /users/{id}/password` depend on `authenticate` + `authorize_self_or_policy`. When `{id}` parses to the UUID in `X-User-Id`, Casbin is not consulted; otherwise `AuthService.authorize_user` decides as in `authorize`. No new Casbin row: for someone else's record `users_write` (`/api/v1/users`, `(GET|POST|PUT)`, `regexMatch`) still matches, and the password route then refuses with `401 invalid_credentials`.
- Logging: only through `fields()` from `app/logging_config.py`; never a code, token, password, hash or whole payload; count-worthy values (`kind`, `outcome`, `reason`, `challenge_id`, `user_id`) as fields. The access-log body key `code` is redacted (exact key match).
- Integration: `ADMIN_NOTIFICATION_EMAILS=datamap-admins@fake.mail.com` in `integration-test.env`, so the notification is recorded (`status=skipped`) and never piles up ahead of other tests' mail in the 50-per-dispatch queue.
- Unit tests are `module_test.py` next to the module, run with `pytest <path> -v` (`pytest.ini` sets `pythonpath = .`). Activate `/Users/caio.maia/workspace/datamap/gatekeeper/.venv` first.
- Validation loop after the last task: `pytest`, `make ENV_FILE_PATH=integration-test.env integration-test-full` (verified, see Task 16), `ruff check`, `ruff check --fix`, `ruff format`.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `app/config.py` | modify | `AUTH_PASSWORD_PEPPER`, `AUTH_CHALLENGE_PEPPER`, `ADMIN_NOTIFICATION_EMAILS` |
| `app/config_auth_test.py` | create | The three settings |
| `app/config_email_test.py` | modify | `REQUIRED` gains both peppers |
| `local.env.template`, `integration-test.env` | modify | The three settings |
| `app/service/password.py`, `app/service/password_test.py` | create | `PasswordHasher`, `password_is_acceptable` |
| `app/service/challenge_code.py`, `app/service/challenge_code_test.py` | create | `new_code`, `code_hash` |
| `app/model/auth_challenge.py` | create | `ChallengeKind` |
| `app/model/db/auth_challenge.py`, `app/model/db/auth_challenge_test.py` | create | `AuthChallenge` table; tests of both tables' columns |
| `app/model/db/user.py` | modify | Four credential columns |
| `migrations/versions/2026_10_03_1200-b1c2d3e4f5a6_add_email_password_authentication.py` | create | Schema |
| `migrations/env.py` | modify | Import the new model module for autogenerate |
| `app/repository/auth_challenge.py`, `app/repository/auth_challenge_test.py` | create | Challenge persistence; atomic attempt count; `confirm` |
| `app/repository/user.py`, `app/repository/user_test.py` | modify / create | Lookup by email in any state, password, confirmation, failed-login counter |
| `app/repository/email.py` | modify | `count_recent` for the hourly cap |
| `app/controller/interceptor/authorization.py`, `app/controller/interceptor/authorization_test.py` | modify / create | `authorize_self_or_policy` |
| `app/exception/too_many_requests.py` | create | `TooManyRequestsException` |
| `app/controller/interceptor/exception_handler.py`, `..._test.py` | modify | 429 handler |
| `app/setup.py` | modify | 429 handler; auth router |
| `app/logging_config.py`, `app/logging_config_test.py` | modify | Redact the `code` key |
| `app/service/email_template.py`, `app/service/email_template_test.py` | modify | Four `EmailTemplate` members and their tests |
| `app/resources/email_templates/{sign_up_code,email_verification_code,password_reset,new_account_pending}.{html,txt}` | create | The emails |
| `app/resources/email_templates/README.md` | modify | Their variables |
| `app/model/user.py` | modify | `User.email_verified_at`, `User.has_password` |
| `app/service/user.py`, `app/service/user_test.py` | modify | Profile fields; `create(..., password_hash, email_verified_at)`; admin notification; email change drops the confirmation |
| `app/controller/v1/user/resource.py`, `app/controller/v1/user/user.py` | modify | Response fields; self-access on `GET /users/{id}`; `PUT /users/{id}/password` |
| `app/controller/v1/user/user_test.py` | create | Route tests for the fields and the password change |
| `app/service/account.py`, `app/service/account_test.py` | create | `AccountService`: every flow |
| `app/controller/v1/auth/__init__.py`, `auth.py`, `resource.py`, `auth_test.py` | create | `/v1/auth/*` |
| `app/container.py` | modify | Email providers moved above `user_service`; `password_hasher`, `auth_challenge_repository`, `account_service`; wiring |
| `tests/integration/fixtures/account.py` | create | Helpers: sign-up, codes from Mailpit, outbox, SQL ageing |
| `tests/integration/test_auth_sign_up.py` | create | Sign-up, codes, resend, cap, log redaction, migration round trip |
| `tests/integration/test_auth_email_verification.py` | create | Every row of the email-verification table |
| `tests/integration/test_new_account_notification.py` | create | `new_account_pending` on the three creation paths |
| `tests/integration/test_auth_login_and_password.py` | create | Sign-in, lock, reset, change, self-access |

---

### Task 1: Worktree and branch

**Files:** none changed.

**Interfaces:** Consumes: local `main` at `abf1055`. Produces: W on `feat/rfc-008-gatekeeper-auth`, with `local.env` and a green baseline.

The main checkout is on `docs/rfc-008-email-password-auth` with an uncommitted change to the RFC file and two untracked files, so `git switch` there would refuse (the RFC file does not exist on `main`). A worktree leaves them untouched.

- [ ] **Step 1: Confirm the main checkout's state and leave it alone**

Run: `git -C /Users/caio.maia/workspace/datamap/gatekeeper status --short`
Expected:
```
 M docs/rfcs/008-email-password-authentication.md
?? docs/rfcs/007-notebooks.md
?? docs/superpowers/plans/2026-10-03-rfc-008-contract.md
?? docs/superpowers/plans/2026-10-03-rfc-008-pr1-gatekeeper-auth.md
```
Do not stage, stash or commit any of them.

- [ ] **Step 2: Create the worktree from `main`**

```bash
git -C /Users/caio.maia/workspace/datamap/gatekeeper worktree add \
  .claude/worktrees/rfc-008-gatekeeper-auth -b feat/rfc-008-gatekeeper-auth main
```
Expected: `Preparing worktree (new branch 'feat/rfc-008-gatekeeper-auth')` and `HEAD is now at abf1055`.

- [ ] **Step 3: Configuration and environment for the unit tests**

```bash
cd /Users/caio.maia/workspace/datamap/gatekeeper/.claude/worktrees/rfc-008-gatekeeper-auth
cp local.env.template local.env
source /Users/caio.maia/workspace/datamap/gatekeeper/.venv/bin/activate
python --version
```
Expected: `Python 3.10.x`. `local.env` is git-ignored (`.gitignore` line `local.env`); CI creates it the same way.

- [ ] **Step 4: Baseline**

Run: `pytest -q`
Expected: `N passed`, 0 failed. Write N down; every later task only adds to it.

- [ ] **Step 5: Commit**

Nothing to commit. `git status --short` must be empty.

---

### Task 2: Configuration for the peppers and the admin list

**Files:**
- Create: `app/config_auth_test.py`
- Modify: `app/config.py`, `app/config_email_test.py`, `local.env.template`, `integration-test.env`
- Owner step (not the agent): `secrets/production/gatekeeper.env`

**Interfaces:** Produces `settings.AUTH_PASSWORD_PEPPER: str`, `settings.AUTH_CHALLENGE_PEPPER: str` (both ≥ 16 characters, required) and `settings.ADMIN_NOTIFICATION_EMAILS: str` (default `""`), reachable in the container as `config.AUTH_PASSWORD_PEPPER`, `config.AUTH_CHALLENGE_PEPPER`, `config.ADMIN_NOTIFICATION_EMAILS`.

- [ ] **Step 1: Write the failing test**

In `app/config_email_test.py`, add two entries to `REQUIRED`, right after `"AUTH_CLIENT_SECRET_PEPPER": "pepper-of-sixteen-chars",`:

```python
    "AUTH_PASSWORD_PEPPER": "password-pepper-of-sixteen",
    "AUTH_CHALLENGE_PEPPER": "challenge-pepper-of-sixteen",
```

Create `app/config_auth_test.py`:

```python
import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.config import Config
from app.config_email_test import REQUIRED


class TestAuthSettings(unittest.TestCase):
    def build(self, **overrides) -> Config:
        with patch.dict(os.environ, {**REQUIRED, **overrides}, clear=True):
            return Config(_env_file=None)

    def without(self, key: str) -> Config:
        values = {name: value for name, value in REQUIRED.items() if name != key}
        with patch.dict(os.environ, values, clear=True):
            return Config(_env_file=None)

    def test_both_peppers_are_read_as_written(self):
        config = self.build()

        self.assertEqual(config.AUTH_PASSWORD_PEPPER, "password-pepper-of-sixteen")
        self.assertEqual(config.AUTH_CHALLENGE_PEPPER, "challenge-pepper-of-sixteen")

    def test_the_application_does_not_start_without_a_password_pepper(self):
        with self.assertRaises(ValidationError):
            self.without("AUTH_PASSWORD_PEPPER")

    def test_the_application_does_not_start_without_a_challenge_pepper(self):
        with self.assertRaises(ValidationError):
            self.without("AUTH_CHALLENGE_PEPPER")

    def test_a_pepper_shorter_than_sixteen_characters_is_refused(self):
        for key in ("AUTH_PASSWORD_PEPPER", "AUTH_CHALLENGE_PEPPER"):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                self.build(**{key: "fifteen-chars-x"})

    def test_admin_notifications_are_off_unless_configured(self):
        self.assertEqual(self.build().ADMIN_NOTIFICATION_EMAILS, "")

    def test_the_admin_list_is_kept_as_written(self):
        config = self.build(ADMIN_NOTIFICATION_EMAILS="a@usp.br, b@usp.br")

        self.assertEqual(config.ADMIN_NOTIFICATION_EMAILS, "a@usp.br, b@usp.br")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest app/config_auth_test.py -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'AUTH_PASSWORD_PEPPER'` in the read tests and `AssertionError: ValidationError not raised` in the refusal tests (the model ignores unknown keys).

- [ ] **Step 3: Implement**

In `app/config.py`, directly after the `AUTH_CLIENT_SECRET_PEPPER` field:

```python
    AUTH_PASSWORD_PEPPER: str = Field(
        ...,
        min_length=16,
        description="Server-side key every password hash is derived from; changing it invalidates every password",
    )
    AUTH_CHALLENGE_PEPPER: str = Field(
        ...,
        min_length=16,
        description="Server-side key the stored confirmation code hashes are derived from",
    )
    ADMIN_NOTIFICATION_EMAILS: str = Field(
        "",
        description="Comma-separated addresses told about every new account; empty sends nothing",
    )
```

In `local.env.template`, after `AUTH_CLIENT_SECRET_PEPPER=CHANGE_ME_openssl_rand_base64_32`:

```
AUTH_PASSWORD_PEPPER=CHANGE_ME_openssl_rand_base64_32
AUTH_CHALLENGE_PEPPER=CHANGE_ME_openssl_rand_base64_32

# Comma-separated; empty sends no new-account notification (RFC 008).
ADMIN_NOTIFICATION_EMAILS=
```

In `integration-test.env`, after `AUTH_CLIENT_SECRET_PEPPER=integration-test-pepper-not-a-real-one`:

```
AUTH_PASSWORD_PEPPER=integration-test-password-pepper-not-a-real-one
AUTH_CHALLENGE_PEPPER=integration-test-challenge-pepper-not-a-real-one
ADMIN_NOTIFICATION_EMAILS=datamap-admins@fake.mail.com
```

Refresh the worktree's own configuration, which the suite imports: `cp local.env.template local.env`.

- [ ] **Step 4: Run it and watch it pass**

Run: `pytest app/config_auth_test.py app/config_email_test.py -v`
Expected: PASS, all tests.

Run: `pytest -q`
Expected: the Task 1 count + 6, 0 failed.

- [ ] **Step 5: Owner-only step, before this branch merges (not executed by the agent)**

`main` deploys on push, and the deploy decrypts `secrets/production/gatekeeper.env`. Without both peppers the new required settings stop the API from starting. The maintainer, who holds the age key, runs:

```bash
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
openssl rand -base64 32   # value for AUTH_PASSWORD_PEPPER
openssl rand -base64 32   # value for AUTH_CHALLENGE_PEPPER
sops secrets/production/gatekeeper.env
```
and adds `AUTH_PASSWORD_PEPPER=…`, `AUTH_CHALLENGE_PEPPER=…` and `ADMIN_NOTIFICATION_EMAILS=` (the admins' addresses, or empty) in the editor, then commits the re-encrypted file on this branch. Record in the PR description that this was done; the agent must not attempt it.

- [ ] **Step 6: Commit**

```bash
ruff check app/config.py app/config_auth_test.py app/config_email_test.py
ruff format app/config.py app/config_auth_test.py app/config_email_test.py
git add app/config.py app/config_auth_test.py app/config_email_test.py local.env.template integration-test.env
git commit -m "$(cat <<'EOF'
feat: configuration for the password and code peppers and the admin notification list

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Password hashing

**Files:**
- Create: `app/service/password.py`, `app/service/password_test.py`

**Interfaces:**
- Consumes: `app.service.secret.BCRYPT_LENGTH` (60), `app.service.secret.MIN_PEPPER_LENGTH` (16).
- Produces: `BCRYPT_ROUNDS = 10`, `MIN_PASSWORD_LENGTH = 10`, `MAX_PASSWORD_LENGTH = 128`, `password_is_acceptable(password: str) -> bool`, `class PasswordHasher(pepper: str, rounds: int = BCRYPT_ROUNDS)` with `hash(password: str) -> str`, `verify(password: str, stored: str) -> bool`, `burn(password: str) -> None`.

- [ ] **Step 1: Write the failing test**

Create `app/service/password_test.py`:

```python
import unittest
from unittest.mock import patch

from app.service.password import (
    BCRYPT_ROUNDS,
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    PasswordHasher,
    password_is_acceptable,
)

PEPPER = "password-pepper-of-sixteen"
FAST = 4


class TestPasswordHasher(unittest.TestCase):
    def setUp(self):
        self.hasher = PasswordHasher(pepper=PEPPER, rounds=FAST)

    def test_a_hashed_password_verifies(self):
        stored = self.hasher.hash("correct horse battery")

        self.assertTrue(self.hasher.verify("correct horse battery", stored))

    def test_a_different_password_does_not_verify(self):
        stored = self.hasher.hash("correct horse battery")

        self.assertFalse(self.hasher.verify("correct horse batterz", stored))

    def test_the_same_password_hashes_differently_each_time(self):
        self.assertNotEqual(
            self.hasher.hash("correct horse battery"),
            self.hasher.hash("correct horse battery"),
        )

    def test_a_hash_is_useless_without_its_pepper(self):
        stored = self.hasher.hash("correct horse battery")
        other = PasswordHasher(pepper="another-pepper-of-sixteen", rounds=FAST)

        self.assertFalse(other.verify("correct horse battery", stored))

    def test_the_hash_is_bcrypt_at_cost_ten_by_default(self):
        stored = PasswordHasher(pepper=PEPPER).hash("correct horse battery")

        self.assertEqual(BCRYPT_ROUNDS, 10)
        self.assertTrue(stored.startswith("$2b$10$"))
        self.assertEqual(len(stored), 60)

    def test_passwords_longer_than_what_bcrypt_reads_are_still_told_apart(self):
        prefix = "x" * 100
        stored = self.hasher.hash(prefix + "a")

        self.assertFalse(self.hasher.verify(prefix + "b", stored))

    def test_a_stored_value_of_another_shape_is_refused_without_reaching_bcrypt(self):
        for stored in ("", "$2b$10$short", "hmac-sha256$abc"):
            with self.subTest(stored=stored):
                self.assertFalse(self.hasher.verify("correct horse battery", stored))

    def test_burning_a_check_runs_bcrypt_once(self):
        with patch(
            "app.service.password.bcrypt.checkpw", return_value=False
        ) as checkpw:
            self.assertIsNone(self.hasher.burn("whatever was typed"))

        checkpw.assert_called_once()

    def test_a_short_pepper_is_refused(self):
        with self.assertRaises(ValueError):
            PasswordHasher(pepper="fifteen-chars-x")


class TestPasswordPolicy(unittest.TestCase):
    def test_ten_to_one_hundred_and_twenty_eight_characters_are_accepted(self):
        self.assertEqual((MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH), (10, 128))
        self.assertTrue(password_is_acceptable("a" * 10))
        self.assertTrue(password_is_acceptable("a" * 128))

    def test_shorter_or_longer_is_refused(self):
        self.assertFalse(password_is_acceptable("a" * 9))
        self.assertFalse(password_is_acceptable("a" * 129))
        self.assertFalse(password_is_acceptable(""))

    def test_no_composition_rule_applies(self):
        self.assertTrue(password_is_acceptable("aaaaaaaaaa"))
        self.assertTrue(password_is_acceptable("só letras e espaços"))
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest app/service/password_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.service.password'`.

- [ ] **Step 3: Implement**

Create `app/service/password.py`:

```python
import base64
import hashlib
import hmac
import secrets

import bcrypt

from app.service.secret import BCRYPT_LENGTH, MIN_PEPPER_LENGTH

BCRYPT_ROUNDS = 10
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128


def password_is_acceptable(password: str) -> bool:
    return MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH


def _is_bcrypt_hash(stored: str) -> bool:
    return len(stored) == BCRYPT_LENGTH and stored.startswith("$2")


class PasswordHasher:
    def __init__(self, pepper: str, rounds: int = BCRYPT_ROUNDS) -> None:
        if len(pepper) < MIN_PEPPER_LENGTH:
            raise ValueError(
                f"the password pepper must be at least {MIN_PEPPER_LENGTH} characters"
            )
        self._pepper = pepper.encode("utf-8")
        self._rounds = rounds
        self._dummy = self.hash(secrets.token_urlsafe(32))

    def hash(self, password: str) -> str:
        salt = bcrypt.gensalt(rounds=self._rounds)
        return bcrypt.hashpw(self._peppered(password), salt).decode("utf-8")

    def verify(self, password: str, stored: str) -> bool:
        # A value of another shape can panic inside bcrypt's Rust extension.
        if not _is_bcrypt_hash(stored):
            return False
        return bcrypt.checkpw(self._peppered(password), stored.encode("utf-8"))

    def burn(self, password: str) -> None:
        self.verify(password, self._dummy)

    def _peppered(self, password: str) -> bytes:
        digest = hmac.new(
            self._pepper, password.encode("utf-8"), hashlib.sha256
        ).digest()
        return base64.b64encode(digest)
```

- [ ] **Step 4: Run it and watch it pass**

Run: `pytest app/service/password_test.py -v`
Expected: PASS, 12 tests.

- [ ] **Step 5: Commit**

```bash
ruff check app/service/password.py app/service/password_test.py
ruff format app/service/password.py app/service/password_test.py
git add app/service/password.py app/service/password_test.py
git commit -m "$(cat <<'EOF'
feat: peppered bcrypt password hashing at cost 10

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Confirmation codes

**Files:**
- Create: `app/service/challenge_code.py`, `app/service/challenge_code_test.py`

**Interfaces:**
- Consumes: `app.service.secret.MIN_PEPPER_LENGTH`.
- Produces: `CODE_LENGTH = 6`, `new_code() -> str`, `code_hash(pepper: str, challenge_id: UUID, code: str) -> str` (64 hex characters).

- [ ] **Step 1: Write the failing test**

Create `app/service/challenge_code_test.py`:

```python
import hashlib
import hmac
import unittest
from unittest.mock import patch
from uuid import UUID

from app.service.challenge_code import CODE_LENGTH, code_hash, new_code

PEPPER = "challenge-pepper-of-sixteen"
CHALLENGE = UUID("6f1c2b8e-0d1a-4c55-9a43-2f6f0a1b9c11")
OTHER_CHALLENGE = UUID("0b7d4d3a-8f33-4f0e-9a8c-6c2a4f1e7d20")


class TestNewCode(unittest.TestCase):
    def test_a_code_is_six_digits(self):
        self.assertEqual(CODE_LENGTH, 6)
        for _ in range(1000):
            self.assertRegex(new_code(), r"^\d{6}$")

    def test_codes_are_drawn_from_the_whole_million(self):
        with patch(
            "app.service.challenge_code.secrets.randbelow", return_value=0
        ) as draw:
            self.assertEqual(new_code(), "000000")
        draw.assert_called_once_with(1_000_000)

        with patch(
            "app.service.challenge_code.secrets.randbelow", return_value=999_999
        ):
            self.assertEqual(new_code(), "999999")

    def test_leading_zeros_are_kept(self):
        with patch("app.service.challenge_code.secrets.randbelow", return_value=42):
            self.assertEqual(new_code(), "000042")


class TestCodeHash(unittest.TestCase):
    def test_it_is_hmac_sha256_of_the_challenge_id_followed_by_the_code(self):
        expected = hmac.new(
            PEPPER.encode("utf-8"),
            f"{CHALLENGE}123456".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        self.assertEqual(code_hash(PEPPER, CHALLENGE, "123456"), expected)
        self.assertRegex(expected, r"^[0-9a-f]{64}$")

    def test_the_same_code_on_another_challenge_hashes_differently(self):
        self.assertNotEqual(
            code_hash(PEPPER, CHALLENGE, "123456"),
            code_hash(PEPPER, OTHER_CHALLENGE, "123456"),
        )

    def test_another_pepper_hashes_differently(self):
        self.assertNotEqual(
            code_hash(PEPPER, CHALLENGE, "123456"),
            code_hash("another-pepper-of-sixteen", CHALLENGE, "123456"),
        )

    def test_another_code_hashes_differently(self):
        self.assertNotEqual(
            code_hash(PEPPER, CHALLENGE, "123456"),
            code_hash(PEPPER, CHALLENGE, "123457"),
        )

    def test_a_short_pepper_is_refused(self):
        with self.assertRaises(ValueError):
            code_hash("fifteen-chars-x", CHALLENGE, "123456")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest app/service/challenge_code_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.service.challenge_code'`.

- [ ] **Step 3: Implement**

Create `app/service/challenge_code.py`:

```python
import hashlib
import hmac
import secrets
from uuid import UUID

from app.service.secret import MIN_PEPPER_LENGTH

CODE_LENGTH = 6
CODE_SPACE = 10**CODE_LENGTH


def new_code() -> str:
    return f"{secrets.randbelow(CODE_SPACE):0{CODE_LENGTH}d}"


def code_hash(pepper: str, challenge_id: UUID, code: str) -> str:
    if len(pepper) < MIN_PEPPER_LENGTH:
        raise ValueError(
            f"the challenge pepper must be at least {MIN_PEPPER_LENGTH} characters"
        )
    message = f"{challenge_id}{code}".encode("utf-8")
    return hmac.new(pepper.encode("utf-8"), message, hashlib.sha256).hexdigest()
```

- [ ] **Step 4: Run it and watch it pass**

Run: `pytest app/service/challenge_code_test.py -v`
Expected: PASS, 8 tests.

- [ ] **Step 5: Commit**

```bash
ruff check app/service/challenge_code.py app/service/challenge_code_test.py
ruff format app/service/challenge_code.py app/service/challenge_code_test.py
git add app/service/challenge_code.py app/service/challenge_code_test.py
git commit -m "$(cat <<'EOF'
feat: six-digit confirmation codes stored as a peppered HMAC

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Schema — user credentials and `auth_challenges`

**Files:**
- Create: `app/model/auth_challenge.py`, `app/model/db/auth_challenge.py`, `app/model/db/auth_challenge_test.py`, `migrations/versions/2026_10_03_1200-b1c2d3e4f5a6_add_email_password_authentication.py`
- Modify: `app/model/db/user.py`, `migrations/env.py`

**Interfaces:**
- Produces: `ChallengeKind(str, Enum)` with `SIGN_UP = "sign_up"`, `EMAIL_VERIFICATION = "email_verification"`, `PASSWORD_RESET = "password_reset"`; ORM `AuthChallenge` (table `auth_challenges`); `User.password_hash`, `User.email_verified_at`, `User.failed_login_count`, `User.locked_until`; migration `b1c2d3e4f5a6`.

- [ ] **Step 1: Write the failing test**

Create `app/model/db/auth_challenge_test.py`:

```python
import unittest

from app.model.auth_challenge import ChallengeKind
from app.model.db.auth_challenge import AuthChallenge
from app.model.db.user import User


class TestAuthChallengeTable(unittest.TestCase):
    def test_it_has_the_columns_the_rfc_names_and_the_issue_time(self):
        self.assertEqual(
            set(AuthChallenge.__table__.columns.keys()),
            {
                "id",
                "kind",
                "email",
                "secret_hash",
                "attempts",
                "expires_at",
                "consumed_at",
                "confirmed_at",
                "issued_at",
                "user_id",
                "payload",
                "created_at",
            },
        )

    def test_a_secret_hash_is_unique(self):
        self.assertTrue(AuthChallenge.__table__.c.secret_hash.unique)

    def test_a_challenge_goes_away_with_its_user(self):
        (foreign_key,) = AuthChallenge.__table__.c.user_id.foreign_keys

        self.assertEqual(foreign_key.column.table.name, "users")
        self.assertEqual(foreign_key.ondelete, "CASCADE")
        self.assertTrue(AuthChallenge.__table__.c.user_id.nullable)

    def test_only_consumption_confirmation_and_the_user_are_optional(self):
        columns = AuthChallenge.__table__.c
        optional = {column.name for column in columns if column.nullable}

        self.assertEqual(optional, {"consumed_at", "confirmed_at", "user_id"})

    def test_the_kinds_are_the_three_flows(self):
        self.assertEqual(
            {kind.value for kind in ChallengeKind},
            {"sign_up", "email_verification", "password_reset"},
        )


class TestUserCredentialColumns(unittest.TestCase):
    def test_users_carry_a_password_a_confirmation_and_a_lock(self):
        self.assertTrue(
            {
                "password_hash",
                "email_verified_at",
                "failed_login_count",
                "locked_until",
            }
            <= set(User.__table__.columns.keys())
        )

    def test_only_the_failure_count_is_required(self):
        columns = User.__table__.c

        self.assertTrue(columns.password_hash.nullable)
        self.assertTrue(columns.email_verified_at.nullable)
        self.assertTrue(columns.locked_until.nullable)
        self.assertFalse(columns.failed_login_count.nullable)
        self.assertEqual(columns.failed_login_count.server_default.arg, "0")

    def test_a_password_hash_column_holds_a_bcrypt_hash(self):
        self.assertEqual(User.__table__.c.password_hash.type.length, 128)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest app/model/db/auth_challenge_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.model.auth_challenge'`.

- [ ] **Step 3: Implement the models**

Create `app/model/auth_challenge.py`:

```python
import enum


class ChallengeKind(str, enum.Enum):
    SIGN_UP = "sign_up"
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"
```

Create `app/model/db/auth_challenge.py`:

```python
import sqlalchemy
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    kind = Column(String(32), nullable=False)
    email = Column(String(256), nullable=False)
    secret_hash = Column(String(128), nullable=False, unique=True)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=False)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    payload = Column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sqlalchemy.text("'{}'::jsonb"),
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('sign_up', 'email_verification', 'password_reset')",
            name="ck_auth_challenges_kind",
        ),
        Index(
            "idx_auth_challenges_open",
            "kind",
            "email",
            postgresql_where=sqlalchemy.text("consumed_at IS NULL"),
        ),
        Index("idx_auth_challenges_user", "user_id"),
    )
```

In `app/model/db/user.py`, inside `class User(Base)`, directly after `is_enabled = Column(Boolean, nullable=False, default=True)`:

```python
    password_hash = Column(String(128), nullable=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    failed_login_count = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    locked_until = Column(DateTime(timezone=True), nullable=True)
```

(`Integer` and `DateTime` are already imported in that file.)

- [ ] **Step 4: Write the migration**

Create `migrations/versions/2026_10_03_1200-b1c2d3e4f5a6_add_email_password_authentication.py`:

```python
"""Email and password authentication: credentials on users, pending challenges

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-10-03 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(128), nullable=True))
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "failed_login_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table(
        "auth_challenges",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("secret_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('sign_up', 'email_verification', 'password_reset')",
            name="ck_auth_challenges_kind",
        ),
    )
    op.create_index(
        "idx_auth_challenges_open",
        "auth_challenges",
        ["kind", "email"],
        postgresql_where=sa.text("consumed_at IS NULL"),
    )
    op.create_index("idx_auth_challenges_user", "auth_challenges", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_auth_challenges_user", table_name="auth_challenges")
    op.drop_index("idx_auth_challenges_open", table_name="auth_challenges")
    op.drop_table("auth_challenges")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "password_hash")
```

In `migrations/env.py`, after `from app.model.db import sharing  # noqa: E402, F401`:

```python
from app.model.db import auth_challenge  # noqa: E402, F401
```

- [ ] **Step 5: Run the tests and check the chain**

Run: `pytest app/model/db/auth_challenge_test.py -v`
Expected: PASS, 8 tests.

Run: `python -m alembic heads`
Expected: `b1c2d3e4f5a6 (head)` and nothing else. (Reads the scripts only; no database needed.) The migration itself runs against PostgreSQL in Task 13.

Run: `pytest -q`
Expected: 0 failed.

- [ ] **Step 6: Commit**

```bash
ruff check app/model migrations
ruff format app/model/auth_challenge.py app/model/db/auth_challenge.py app/model/db/auth_challenge_test.py app/model/db/user.py migrations/env.py migrations/versions/2026_10_03_1200-b1c2d3e4f5a6_add_email_password_authentication.py
git add app/model/auth_challenge.py app/model/db/auth_challenge.py app/model/db/auth_challenge_test.py app/model/db/user.py migrations/env.py migrations/versions/2026_10_03_1200-b1c2d3e4f5a6_add_email_password_authentication.py
git commit -m "$(cat <<'EOF'
feat: credentials on users and the auth_challenges table

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Repositories

**Files:**
- Create: `app/repository/auth_challenge.py`, `app/repository/auth_challenge_test.py`, `app/repository/user_test.py`
- Modify: `app/repository/user.py`, `app/repository/email.py`

**Interfaces:**
- Consumes: `AuthChallenge`, `ChallengeKind`, `User` (DB), `EmailMessage`.
- Produces:
  - `AuthChallengeRepository(session_factory)` with `replace(challenge: AuthChallenge) -> None`, `fetch(challenge_id: UUID) -> AuthChallenge | None`, `fetch_open_by_secret(secret_hash: str, kind: ChallengeKind) -> AuthChallenge | None`, `consume(challenge_id: UUID, now: datetime) -> bool`, `confirm(challenge_id: UUID, now: datetime) -> bool`, `record_failed_attempt(challenge_id: UUID, max_attempts: int, now: datetime) -> int | None`, `reissue(challenge_id: UUID, secret_hash: str, expires_at: datetime, issued_at: datetime) -> None`, `touch(challenge_id: UUID, issued_at: datetime) -> None`, `consume_open_for_user(user_id: UUID, kind: ChallengeKind, now: datetime) -> None`.
  - `UserRepository.fetch_by_email_any(email: str) -> User | None`, `verify_email(id: UUID, email: str, verified_at: datetime) -> None`, `set_password(id: UUID, password_hash: str) -> None`, `record_failed_login(id: UUID, threshold: int, lock_until: datetime) -> None`, `clear_failed_logins(id: UUID) -> None`.
  - `EmailRepository.count_recent(recipient: str, templates: list[str], since: datetime) -> int`.

The query shapes are proven against PostgreSQL in Tasks 13–15. The unit tests here pin the two statements whose correctness is their atomicity.

- [ ] **Step 1: Write the failing tests**

Create `app/repository/auth_challenge_test.py`:

```python
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.repository.auth_challenge import AuthChallengeRepository

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


class Recorder:
    def __init__(self, returned=None) -> None:
        self.session = MagicMock()
        self.session.execute.return_value.first.return_value = returned

    @contextmanager
    def __call__(self):
        yield self.session

    def sql(self) -> str:
        statement = self.session.execute.call_args.args[0]
        return str(statement.compile(dialect=postgresql.dialect()))


class TestFailedAttempts(unittest.TestCase):
    def test_a_wrong_code_is_counted_and_the_last_one_consumes_in_one_statement(self):
        recorder = Recorder(returned=(5,))

        attempts = AuthChallengeRepository(recorder).record_failed_attempt(
            uuid4(), 5, NOW
        )

        self.assertEqual(attempts, 5)
        sql = recorder.sql()
        self.assertIn("UPDATE auth_challenges SET", sql)
        self.assertIn("auth_challenges.attempts +", sql)
        self.assertIn("CASE WHEN", sql)
        self.assertIn("auth_challenges.consumed_at IS NULL", sql)
        self.assertIn("RETURNING auth_challenges.attempts", sql)
        recorder.session.commit.assert_called_once()

    def test_a_challenge_consumed_meanwhile_counts_nothing(self):
        recorder = Recorder(returned=None)

        attempts = AuthChallengeRepository(recorder).record_failed_attempt(
            uuid4(), 5, NOW
        )

        self.assertIsNone(attempts)
```

Create `app/repository/user_test.py`:

```python
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.repository.user import UserRepository

LOCK_UNTIL = datetime(2026, 10, 3, 12, 15, tzinfo=timezone.utc)


class Recorder:
    def __init__(self) -> None:
        self.session = MagicMock()

    @contextmanager
    def __call__(self):
        yield self.session

    def sql(self) -> str:
        statement = self.session.execute.call_args.args[0]
        return str(statement.compile(dialect=postgresql.dialect()))


class TestFailedLogins(unittest.TestCase):
    def test_a_failure_is_counted_and_the_tenth_locks_in_one_statement(self):
        recorder = Recorder()

        UserRepository(recorder).record_failed_login(
            uuid4(), threshold=10, lock_until=LOCK_UNTIL
        )

        sql = recorder.sql()
        self.assertIn("UPDATE users SET", sql)
        self.assertIn("users.failed_login_count +", sql)
        self.assertIn("CASE WHEN", sql)
        self.assertIn("ELSE users.locked_until", sql)
        self.assertIn("WHERE users.id =", sql)
        recorder.session.commit.assert_called_once()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest app/repository/auth_challenge_test.py app/repository/user_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.repository.auth_challenge'` and `AttributeError: 'UserRepository' object has no attribute 'record_failed_login'`.

- [ ] **Step 3: Implement**

Create `app/repository/auth_challenge.py`:

```python
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable
from uuid import UUID

from sqlalchemy import case, update
from sqlalchemy.orm import Session

from app.model.auth_challenge import ChallengeKind
from app.model.db.auth_challenge import AuthChallenge


class AuthChallengeRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def replace(self, challenge: AuthChallenge) -> None:
        with self._session_factory() as session:
            session.query(AuthChallenge).filter(
                AuthChallenge.kind == challenge.kind,
                AuthChallenge.email == challenge.email,
                AuthChallenge.consumed_at.is_(None),
            ).update(
                {AuthChallenge.consumed_at: challenge.issued_at},
                synchronize_session=False,
            )
            session.add(challenge)
            session.commit()

    def fetch(self, challenge_id: UUID) -> AuthChallenge | None:
        with self._session_factory() as session:
            return session.query(AuthChallenge).filter_by(id=challenge_id).first()

    def fetch_open_by_secret(
        self, secret_hash: str, kind: ChallengeKind
    ) -> AuthChallenge | None:
        with self._session_factory() as session:
            return (
                session.query(AuthChallenge)
                .filter(
                    AuthChallenge.secret_hash == secret_hash,
                    AuthChallenge.kind == kind.value,
                    AuthChallenge.consumed_at.is_(None),
                )
                .first()
            )

    def consume(self, challenge_id: UUID, now: datetime) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(AuthChallenge)
                .filter(
                    AuthChallenge.id == challenge_id,
                    AuthChallenge.consumed_at.is_(None),
                )
                .update({AuthChallenge.consumed_at: now}, synchronize_session=False)
            )
            session.commit()
            return updated == 1

    def confirm(self, challenge_id: UUID, now: datetime) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(AuthChallenge)
                .filter(
                    AuthChallenge.id == challenge_id,
                    AuthChallenge.consumed_at.is_(None),
                )
                .update(
                    {AuthChallenge.consumed_at: now, AuthChallenge.confirmed_at: now},
                    synchronize_session=False,
                )
            )
            session.commit()
            return updated == 1

    def record_failed_attempt(
        self, challenge_id: UUID, max_attempts: int, now: datetime
    ) -> int | None:
        table = AuthChallenge.__table__
        statement = (
            update(table)
            .where(table.c.id == challenge_id, table.c.consumed_at.is_(None))
            .values(
                attempts=table.c.attempts + 1,
                consumed_at=case(
                    (table.c.attempts + 1 >= max_attempts, now), else_=None
                ),
            )
            .returning(table.c.attempts)
        )
        with self._session_factory() as session:
            row = session.execute(statement).first()
            session.commit()
            return row[0] if row is not None else None

    def reissue(
        self,
        challenge_id: UUID,
        secret_hash: str,
        expires_at: datetime,
        issued_at: datetime,
    ) -> None:
        with self._session_factory() as session:
            challenge = (
                session.query(AuthChallenge)
                .filter_by(id=challenge_id)
                .with_for_update()
                .one()
            )
            session.query(AuthChallenge).filter(
                AuthChallenge.kind == challenge.kind,
                AuthChallenge.email == challenge.email,
                AuthChallenge.consumed_at.is_(None),
                AuthChallenge.id != challenge_id,
            ).update({AuthChallenge.consumed_at: issued_at}, synchronize_session=False)
            challenge.secret_hash = secret_hash
            challenge.attempts = 0
            challenge.expires_at = expires_at
            challenge.issued_at = issued_at
            challenge.consumed_at = None
            session.commit()

    def touch(self, challenge_id: UUID, issued_at: datetime) -> None:
        with self._session_factory() as session:
            session.query(AuthChallenge).filter(
                AuthChallenge.id == challenge_id
            ).update({AuthChallenge.issued_at: issued_at}, synchronize_session=False)
            session.commit()

    def consume_open_for_user(
        self, user_id: UUID, kind: ChallengeKind, now: datetime
    ) -> None:
        with self._session_factory() as session:
            session.query(AuthChallenge).filter(
                AuthChallenge.user_id == user_id,
                AuthChallenge.kind == kind.value,
                AuthChallenge.consumed_at.is_(None),
            ).update({AuthChallenge.consumed_at: now}, synchronize_session=False)
            session.commit()
```

In `app/repository/user.py`:

Replace the imports at the top of the file:

```python
from typing import List
from uuid import UUID
from app.model.user import UserQuery
from app.model.db.user import (
    Provider,
    User,
    user_provider_association,
    user_tenancy_association,
)
from sqlalchemy import func, or_
```

with:

```python
from datetime import datetime
from typing import List
from uuid import UUID
from app.model.user import UserQuery
from app.model.db.user import (
    Provider,
    User,
    user_provider_association,
    user_tenancy_association,
)
from sqlalchemy import case, func, or_, update
```

Add these methods to `UserRepository`, after `fetch_by_email_insensitive`:

```python
    def fetch_by_email_any(self, email: str) -> User | None:
        with self._session_factory() as session:
            return (
                session.query(User)
                .filter(func.lower(User.email) == email.lower())
                .order_by(User.is_enabled.desc())
                .first()
            )

    def verify_email(self, id: UUID, email: str, verified_at: datetime) -> None:
        try:
            self._update(id, {User.email: email, User.email_verified_at: verified_at})
        except IntegrityError:
            raise ConflictException("email_belongs_to_another_account")

    def set_password(self, id: UUID, password_hash: str) -> None:
        self._update(
            id,
            {
                User.password_hash: password_hash,
                User.failed_login_count: 0,
                User.locked_until: None,
            },
        )

    def clear_failed_logins(self, id: UUID) -> None:
        self._update(id, {User.failed_login_count: 0, User.locked_until: None})

    def record_failed_login(
        self, id: UUID, threshold: int, lock_until: datetime
    ) -> None:
        table = User.__table__
        statement = (
            update(table)
            .where(table.c.id == id)
            .values(
                failed_login_count=table.c.failed_login_count + 1,
                locked_until=case(
                    (table.c.failed_login_count + 1 >= threshold, lock_until),
                    else_=table.c.locked_until,
                ),
            )
        )
        with self._session_factory() as session:
            session.execute(statement)
            session.commit()

    def _update(self, id: UUID, values: dict) -> None:
        with self._session_factory() as session:
            session.query(User).filter(User.id == id).update(
                values, synchronize_session=False
            )
            session.commit()
```

In `app/repository/email.py`, add after `count_pending`:

```python
    def count_recent(
        self, recipient: str, templates: list[str], since: datetime
    ) -> int:
        with self._session_factory() as session:
            return (
                session.query(func.count(EmailMessage.id))
                .filter(
                    func.lower(EmailMessage.recipient) == recipient.lower(),
                    EmailMessage.template.in_(templates),
                    EmailMessage.created_at >= since,
                )
                .scalar()
                or 0
            )
```

- [ ] **Step 4: Run them and watch them pass**

Run: `pytest app/repository/auth_challenge_test.py app/repository/user_test.py -v`
Expected: PASS, 3 tests.

Run: `pytest -q`
Expected: 0 failed.

- [ ] **Step 5: Commit**

```bash
ruff check app/repository
ruff format app/repository/auth_challenge.py app/repository/auth_challenge_test.py app/repository/user.py app/repository/user_test.py app/repository/email.py
git add app/repository/auth_challenge.py app/repository/auth_challenge_test.py app/repository/user.py app/repository/user_test.py app/repository/email.py
git commit -m "$(cat <<'EOF'
feat: repositories for challenges, password sign-in and the hourly code count

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: 429 answers and codes kept out of the access log

**Files:**
- Create: `app/exception/too_many_requests.py`
- Modify: `app/controller/interceptor/exception_handler.py`, `app/controller/interceptor/exception_handler_test.py`, `app/setup.py`, `app/logging_config.py`, `app/logging_config_test.py`

**Interfaces:**
- Produces: `TooManyRequestsException(Exception)`; `too_many_requests_exception_handler(request, exc) -> JSONResponse` (429, `{"detail": str(exc)}`), registered by `setup_error_handlers`; `Redactor.scrub_field` redacts a key named exactly `code` (any case).

The middleware logs every JSON request body through the redaction filter. `password`, `current_password`, `new_password` and `token` already match `_SECRET_WORDS`; the confirmation `code` does not, and a substring rule would also hide `status_code`.

- [ ] **Step 1: Write the failing tests**

Append to `app/controller/interceptor/exception_handler_test.py`, before the `if __name__ == "__main__":` block, and add `from app.exception.too_many_requests import TooManyRequestsException` to its imports:

```python
class TestTooManyRequestsHandler(unittest.TestCase):
    def test_a_refused_retry_answers_429_with_its_code(self):
        app = FastAPI()
        setup.setup_error_handlers(app)

        @app.post("/again")
        def again():
            raise TooManyRequestsException("resend_too_soon")

        response = TestClient(app, raise_server_exceptions=False).post("/again")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), {"detail": "resend_too_soon"})
```

Append to `class TestRedaction` in `app/logging_config_test.py`:

```python
    def test_a_confirmation_code_in_a_body_is_redacted(self):
        self.assertEqual(Redactor.scrub({"code": "042917"})["code"], "[redacted]")
        self.assertEqual(Redactor.scrub({"Code": "042917"})["Code"], "[redacted]")

    def test_it_is_redacted_inside_the_access_line_body_too(self):
        scrubbed = Redactor.scrub({"body": {"code": "042917"}})

        self.assertEqual(scrubbed["body"]["code"], "[redacted]")

    def test_a_field_that_merely_ends_in_code_is_left_alone(self):
        self.assertEqual(Redactor.scrub({"status_code": 401})["status_code"], 401)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest app/controller/interceptor/exception_handler_test.py app/logging_config_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.exception.too_many_requests'` (collection error for the handler file) and `AssertionError: '042917' != '[redacted]'`.

- [ ] **Step 3: Implement**

Create `app/exception/too_many_requests.py`:

```python
class TooManyRequestsException(Exception):
    pass
```

In `app/controller/interceptor/exception_handler.py`, add the import `from app.exception.too_many_requests import TooManyRequestsException` and, after `forbidden_exception_handler`:

```python
async def too_many_requests_exception_handler(
    request: Request, exc: TooManyRequestsException
):
    logger.info(f"Too many requests exception: {exc}")
    return JSONResponse(status_code=429, content={"detail": str(exc)})
```

In `app/setup.py`: add `from app.exception.too_many_requests import TooManyRequestsException` next to the other exception imports; add `too_many_requests_exception_handler,` to the import list from `app.controller.interceptor.exception_handler`; and in `setup_error_handlers`, directly before the `Exception` handler:

```python
    fastAPIApp.add_exception_handler(
        TooManyRequestsException, too_many_requests_exception_handler
    )
```

In `app/logging_config.py`, after the `_SECRET_WORDS` line:

```python
# An exact match: `status_code` and the like must stay readable.
_SECRET_KEYS = frozenset({"code"})
```

and change the first line of `Redactor.scrub_field` from `if cls.KEY_PATTERN.search(key):` to:

```python
        if key.lower() in _SECRET_KEYS or cls.KEY_PATTERN.search(key):
```

- [ ] **Step 4: Run them and watch them pass**

Run: `pytest app/controller/interceptor/exception_handler_test.py app/logging_config_test.py app/setup_test.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff check app/exception app/controller/interceptor app/setup.py app/logging_config.py app/logging_config_test.py
ruff format app/exception/too_many_requests.py app/controller/interceptor/exception_handler.py app/controller/interceptor/exception_handler_test.py app/setup.py app/logging_config.py app/logging_config_test.py
git add app/exception/too_many_requests.py app/controller/interceptor/exception_handler.py app/controller/interceptor/exception_handler_test.py app/setup.py app/logging_config.py app/logging_config_test.py
git commit -m "$(cat <<'EOF'
feat: answer 429 with its code, and keep confirmation codes out of the access log

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: The four emails

**Files:**
- Create: `app/resources/email_templates/sign_up_code.html`, `sign_up_code.txt`, `email_verification_code.html`, `email_verification_code.txt`, `password_reset.html`, `password_reset.txt`, `new_account_pending.html`, `new_account_pending.txt`
- Modify: `app/service/email_template.py`, `app/service/email_template_test.py`, `app/resources/email_templates/README.md`

**Interfaces:**
- Produces: `EmailTemplate.SIGN_UP_CODE = "sign_up_code"` (context `name`, `code`, `expires_in_minutes`), `EmailTemplate.EMAIL_VERIFICATION_CODE = "email_verification_code"` (`name`, `code`, `orcid`, `expires_in_minutes`), `EmailTemplate.PASSWORD_RESET = "password_reset"` (`name`, `link`), `EmailTemplate.NEW_ACCOUNT_PENDING = "new_account_pending"` (`name`, `email`, `sign_in_method`, `created_at`).

- [ ] **Step 1: Write the failing test**

Append to the end of `app/service/email_template_test.py`:

```python
CONTEXTS[EmailTemplate.SIGN_UP_CODE] = {
    "name": "Ana Souza",
    "code": "042917",
    "expires_in_minutes": 15,
}
CONTEXTS[EmailTemplate.EMAIL_VERIFICATION_CODE] = {
    "name": "Ana Souza",
    "code": "042917",
    "orcid": "0000-0002-1825-0097",
    "expires_in_minutes": 15,
}
CONTEXTS[EmailTemplate.PASSWORD_RESET] = {
    "name": "Ana Souza",
    "link": "https://datamap.example.org/account/reset-password/tok-123",
}
CONTEXTS[EmailTemplate.NEW_ACCOUNT_PENDING] = {
    "name": "Ana Souza",
    "email": "ana.souza@usp.br",
    "sign_in_method": "Email and password",
    "created_at": "October 3, 2026 at 14:05 UTC",
}

ACCOUNT = frozenset(
    {
        EmailTemplate.SIGN_UP_CODE,
        EmailTemplate.EMAIL_VERIFICATION_CODE,
        EmailTemplate.PASSWORD_RESET,
        EmailTemplate.NEW_ACCOUNT_PENDING,
    }
)


class TestAccountTemplates(unittest.TestCase):
    def setUp(self):
        self.renderer = EmailTemplateRenderer(site_url=SITE_URL)

    def render(self, template):
        return self.renderer.render(template, CONTEXTS[template])

    def test_every_account_template_has_a_written_text_part(self):
        for template in ACCOUNT:
            with self.subTest(template=template):
                self.assertTrue((TEMPLATES_DIR / f"{template.value}.txt").is_file())

    def test_a_code_is_in_both_bodies_and_never_in_the_subject(self):
        for template in (
            EmailTemplate.SIGN_UP_CODE,
            EmailTemplate.EMAIL_VERIFICATION_CODE,
        ):
            with self.subTest(template=template):
                email = self.render(template)

                self.assertIn("042917", email.html)
                self.assertIn("Your DataMap code: 042917", email.text)
                self.assertNotIn("042917", email.subject)

    def test_the_sign_up_code_tells_a_stranger_to_ignore_it(self):
        email = self.render(EmailTemplate.SIGN_UP_CODE)

        self.assertEqual(email.subject, "Confirm your email for DataMap")
        self.assertIn("If this wasn't you, ignore this email.", email.text)
        self.assertIn("It expires in 15 minutes.", email.text)

    def test_the_email_verification_names_the_orcid_being_linked(self):
        email = self.render(EmailTemplate.EMAIL_VERIFICATION_CODE)

        self.assertEqual(email.subject, "Confirm your email to sign in with ORCID")
        self.assertIn("0000-0002-1825-0097", email.html)
        self.assertIn("ORCID iD: 0000-0002-1825-0097", email.text)

    def test_the_reset_link_is_in_both_bodies_and_valid_for_an_hour(self):
        email = self.render(EmailTemplate.PASSWORD_RESET)
        link = "https://datamap.example.org/account/reset-password/tok-123"

        self.assertEqual(email.subject, "Reset your DataMap password")
        self.assertIn(link, email.html)
        self.assertIn(link, email.text)
        self.assertNotIn("tok-123", email.subject)
        self.assertIn("valid for 1 hour", email.text)

    def test_the_admin_notification_lists_the_account(self):
        email = self.render(EmailTemplate.NEW_ACCOUNT_PENDING)

        self.assertEqual(email.subject, "New DataMap account: Ana Souza")
        for value in (
            "Ana Souza",
            "ana.souza@usp.br",
            "Email and password",
            "October 3, 2026 at 14:05 UTC",
        ):
            with self.subTest(value=value):
                self.assertIn(value, email.text)
                self.assertIn(value, email.html)

    def test_account_messages_do_not_claim_to_be_about_a_dataset(self):
        for template in ACCOUNT:
            with self.subTest(template=template):
                email = self.render(template)
                self.assertNotIn("transactional message about a dataset", email.html)
                self.assertNotIn("transactional message about a dataset", email.text)

    def test_a_name_is_escaped_in_html(self):
        email = self.renderer.render(
            EmailTemplate.SIGN_UP_CODE,
            {**CONTEXTS[EmailTemplate.SIGN_UP_CODE], "name": "<b>Ana</b>"},
        )

        self.assertNotIn("<b>Ana</b>", email.html)
        self.assertIn("&lt;b&gt;Ana&lt;/b&gt;", email.html)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest app/service/email_template_test.py -v`
Expected: FAIL — collection error `AttributeError: SIGN_UP_CODE` (the enum has no such member).

- [ ] **Step 3: Implement**

In `app/service/email_template.py`, add to `class EmailTemplate` after `EMBARGO_ENDED = "embargo_ended"`:

```python
    SIGN_UP_CODE = "sign_up_code"
    EMAIL_VERIFICATION_CODE = "email_verification_code"
    PASSWORD_RESET = "password_reset"
    NEW_ACCOUNT_PENDING = "new_account_pending"
```

Create `app/resources/email_templates/sign_up_code.html`:

```html
{% extends "base.html" %}
{% import "_macros.html" as m %}
{% block title %}Confirm your email for DataMap{% endblock %}
{% block preheader %}Your code expires in {{ expires_in_minutes }} minutes.{% endblock %}
{% block label %}Sign-up{% endblock %}
{% block content %}
{{ m.heading("Confirm your email") }}
{% call m.paragraph() %}Hi {{ name }}, enter this code on the DataMap screen where you created your account.{% endcall %}
{{ m.details([{"label": "Your code", "value": code}, {"label": "Expires in", "value": expires_in_minutes ~ " minutes"}]) }}
{% call m.note(bottom=16) %}If this wasn't you, ignore this email. Nobody can use this address on DataMap without the code.{% endcall %}
{% endblock %}
{% block reason %}You received this email because someone used this address to create a DataMap account.{% endblock %}
```

Create `app/resources/email_templates/sign_up_code.txt`:

```
{% extends "base.txt" %}
{% block content %}
Hi {{ name }},

Enter this code on the DataMap screen where you created your account.

Your DataMap code: {{ code }}

It expires in {{ expires_in_minutes }} minutes.

If this wasn't you, ignore this email. Nobody can use this address on DataMap without the code.
{% endblock %}
{% block reason %}You received this email because someone used this address to create a DataMap account.{% endblock %}
```

Create `app/resources/email_templates/email_verification_code.html`:

```html
{% extends "base.html" %}
{% import "_macros.html" as m %}
{% block title %}Confirm your email to sign in with ORCID{% endblock %}
{% block preheader %}Your code expires in {{ expires_in_minutes }} minutes.{% endblock %}
{% block label %}Sign-in{% endblock %}
{% block content %}
{{ m.heading("Confirm your email") }}
{% call m.paragraph() %}Hi {{ name }}, enter this code on DataMap to confirm this address and link it to your ORCID iD.{% endcall %}
{{ m.details([{"label": "Your code", "value": code}, {"label": "ORCID iD", "value": orcid}, {"label": "Expires in", "value": expires_in_minutes ~ " minutes"}]) }}
{% call m.note(bottom=16) %}If you didn't sign in to DataMap with this ORCID iD, ignore this email. Nothing is linked without the code.{% endcall %}
{% endblock %}
{% block reason %}You received this email because someone signing in to DataMap with ORCID gave this address.{% endblock %}
```

Create `app/resources/email_templates/email_verification_code.txt`:

```
{% extends "base.txt" %}
{% block content %}
Hi {{ name }},

Enter this code on DataMap to confirm this address and link it to your ORCID iD.

Your DataMap code: {{ code }}
ORCID iD: {{ orcid }}

It expires in {{ expires_in_minutes }} minutes.

If you didn't sign in to DataMap with this ORCID iD, ignore this email. Nothing is linked without the code.
{% endblock %}
{% block reason %}You received this email because someone signing in to DataMap with ORCID gave this address.{% endblock %}
```

Create `app/resources/email_templates/password_reset.html`:

```html
{% extends "base.html" %}
{% import "_macros.html" as m %}
{% block title %}Reset your DataMap password{% endblock %}
{% block preheader %}The link is valid for 1 hour.{% endblock %}
{% block label %}Password{% endblock %}
{% block content %}
{{ m.heading("Choose a new password") }}
{% call m.paragraph() %}Hi {{ name }}, someone asked to reset the password of your DataMap account. The link below is valid for 1 hour and works once.{% endcall %}
{{ m.button("Choose a new password", link) }}
{{ m.spacer(16) }}
{% call m.note(bottom=16) %}If you didn't ask for this, ignore this email. Your password stays as it is.{% endcall %}
{{ m.link_fallback(link) }}
{% endblock %}
{% block reason %}You received this email because a password reset was requested for this address on DataMap.{% endblock %}
```

Create `app/resources/email_templates/password_reset.txt`:

```
{% extends "base.txt" %}
{% block content %}
Hi {{ name }},

Someone asked to reset the password of your DataMap account.

Choose a new password: {{ link }}

The link is valid for 1 hour and works once.

If you didn't ask for this, ignore this email. Your password stays as it is.
{% endblock %}
{% block reason %}You received this email because a password reset was requested for this address on DataMap.{% endblock %}
```

Create `app/resources/email_templates/new_account_pending.html`:

```html
{% extends "base.html" %}
{% import "_macros.html" as m %}
{% block title %}New DataMap account: {{ name }}{% endblock %}
{% block preheader %}{{ name }} is waiting for a workspace.{% endblock %}
{% block label %}New account{% endblock %}
{% block content %}
{{ m.heading("A new account is waiting for a workspace") }}
{% call m.paragraph() %}{{ m.strong(name) }} created a DataMap account. Until someone gives it a workspace and a role, it cannot use DataMap.{% endcall %}
{{ m.details([{"label": "Name", "value": name}, {"label": "Email", "value": email}, {"label": "Sign-in method", "value": sign_in_method}, {"label": "Created", "value": created_at}]) }}
{% endblock %}
{% block reason %}You received this email because your address is on DataMap's list of administrators to notify about new accounts.{% endblock %}
```

Create `app/resources/email_templates/new_account_pending.txt`:

```
{% extends "base.txt" %}
{% block content %}
{{ name }} created a DataMap account. Until someone gives it a workspace and a role, it cannot use DataMap.

Name: {{ name }}
Email: {{ email }}
Sign-in method: {{ sign_in_method }}
Created: {{ created_at }}
{% endblock %}
{% block reason %}You received this email because your address is on DataMap's list of administrators to notify about new accounts.{% endblock %}
```

In `app/resources/email_templates/README.md`, append to the table:

```
| `sign_up_code` | `name`, `code`, `expires_in_minutes` | |
| `email_verification_code` | `name`, `code`, `orcid`, `expires_in_minutes` | |
| `password_reset` | `name`, `link` | |
| `new_account_pending` | `name`, `email`, `sign_in_method`, `created_at` | |
```

- [ ] **Step 4: Run it and watch it pass**

Run: `pytest app/service/email_template_test.py app/service/email_text_test.py app/service/email_test.py -v`
Expected: PASS — including `test_every_template_renders_with_its_context`, `test_no_template_links_to_preferences_or_unsubscribe` and `test_footer_datasets_link_points_to_the_dataset_list`, which now loop over the four new members too.

- [ ] **Step 5: Commit**

```bash
ruff check app/service/email_template.py app/service/email_template_test.py
ruff format app/service/email_template.py app/service/email_template_test.py
git add app/service/email_template.py app/service/email_template_test.py app/resources/email_templates
git commit -m "$(cat <<'EOF'
feat: sign-up, email verification, password reset and new account emails

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: User responses, self-access and the new-account notification

**Files:**
- Create: `app/controller/v1/user/user_test.py`, `app/controller/interceptor/authorization_test.py`
- Modify: `app/model/user.py`, `app/service/user.py`, `app/service/user_test.py`, `app/controller/v1/user/resource.py`, `app/controller/v1/user/user.py`, `app/controller/interceptor/authorization.py`, `app/container.py`

**Interfaces:**
- Consumes: `EmailService.enqueue(...)`, `EmailTemplate.NEW_ACCOUNT_PENDING`, `long_date`, `hash_token`, `config.ADMIN_NOTIFICATION_EMAILS`; `parse_user_header`, `AuthService.authorize_user(user_id, resource, action)`.
- Produces:
  - `authorize_self_or_policy(request, user_id=Depends(parse_user_header), auth_service=...)` in `app/controller/interceptor/authorization.py`; `GET /users/{id}` depends on it instead of `authorize`.
  - `User.email_verified_at: datetime | None = None`, `User.has_password: bool = False`.
  - `UserService(repository, tenancy_repository, casbin_enforcer, email_service: EmailService | None = None, admin_emails: str = "")`.
  - `UserService.create(user: User, password_hash: str | None = None, email_verified_at: datetime | None = None) -> UUID`.
  - `admin_addresses(value: str) -> list[str]`, `sign_in_method(providers: list, has_password: bool) -> str`, `created_on(moment: datetime) -> str` in `app/service/user.py`.
  - `UserGetResponse.email_verified_at: datetime | None`, `UserGetResponse.has_password: bool`.

- [ ] **Step 1: Write the failing tests**

Append to `app/service/user_test.py` (add the imports at the top of the file: `from datetime import datetime, timezone`, `from app.service.email import EmailService`, and change `from app.service.user import UserService` to `from app.service.user import UserService, admin_addresses`):

```python
CREATED = datetime(2026, 10, 3, 14, 5, tzinfo=timezone.utc)
BCRYPT_LIKE = "$2b$10$" + "x" * 53


class TestNewAccountNotification(unittest.TestCase):
    def setUp(self):
        self.user_repository = Mock(spec=UserRepository)
        self.tenancy_repository = Mock(spec=TenancyRepository)
        self.casbin_enforcer = Mock(spec=SyncedEnforcer)
        self.email_service = Mock(spec=EmailService)
        self.user_id = uuid4()
        persisted = Mock(spec=UserDBModel)
        persisted.id = self.user_id
        persisted.created_at = CREATED
        self.user_repository.upsert.return_value = persisted

    def service(self, admin_emails: str) -> UserService:
        return UserService(
            self.user_repository,
            self.tenancy_repository,
            self.casbin_enforcer,
            email_service=self.email_service,
            admin_emails=admin_emails,
        )

    def orcid_user(self) -> User:
        return User(
            name="Ana Souza",
            email="ana.souza@usp.br",
            providers=[UserProvider(name="orcid", reference="0000-0002-1825-0097")],
            roles=[],
        )

    def sent(self) -> list[dict]:
        return [call.kwargs for call in self.email_service.enqueue.call_args_list]

    def test_every_admin_is_told_about_a_new_account(self):
        self.service("admin.one@usp.br, admin.two@usp.br").create(self.orcid_user())

        self.assertEqual(
            [kwargs["recipient"] for kwargs in self.sent()],
            ["admin.one@usp.br", "admin.two@usp.br"],
        )

    def test_the_message_names_the_account_and_how_it_signs_in(self):
        self.service("admin.one@usp.br").create(self.orcid_user())

        (kwargs,) = self.sent()
        self.assertEqual(kwargs["template"], "new_account_pending")
        self.assertEqual(
            kwargs["context"],
            {
                "name": "Ana Souza",
                "email": "ana.souza@usp.br",
                "sign_in_method": "ORCID",
                "created_at": "October 3, 2026 at 14:05 UTC",
            },
        )
        self.assertEqual(kwargs["related_type"], "user")
        self.assertEqual(kwargs["related_id"], self.user_id)
        self.assertTrue(
            kwargs["dedup_key"].startswith(f"new_account_pending:{self.user_id}:")
        )
        self.assertLessEqual(len(kwargs["dedup_key"]), 256)

    def test_each_admin_has_a_dedup_key_of_its_own(self):
        self.service("admin.one@usp.br,admin.two@usp.br").create(self.orcid_user())

        keys = {kwargs["dedup_key"] for kwargs in self.sent()}
        self.assertEqual(len(keys), 2)

    def test_an_account_created_with_a_password_is_stored_confirmed_and_says_so(self):
        self.service("admin.one@usp.br").create(
            User(name="Ana Souza", email="ana.souza@usp.br", providers=[], roles=[]),
            password_hash=BCRYPT_LIKE,
            email_verified_at=CREATED,
        )

        created = self.user_repository.upsert.call_args.kwargs["user"]
        self.assertEqual(created.password_hash, BCRYPT_LIKE)
        self.assertEqual(created.email_verified_at, CREATED)
        self.assertEqual(self.sent()[0]["context"]["sign_in_method"], "Email and password")

    def test_an_account_created_through_the_api_without_a_provider_says_so(self):
        self.service("admin.one@usp.br").create(
            User(name="Ana Souza", email="ana.souza@usp.br", providers=[], roles=[])
        )

        self.assertEqual(
            self.sent()[0]["context"]["sign_in_method"], "Created through the API"
        )

    def test_nobody_is_told_when_the_list_is_empty(self):
        self.service("").create(self.orcid_user())

        self.email_service.enqueue.assert_not_called()

    def test_a_failure_to_queue_does_not_undo_the_account(self):
        self.email_service.enqueue.side_effect = RuntimeError("database gone")

        with self.assertLogs("service:UserService", level="ERROR"):
            user_id = self.service("admin.one@usp.br").create(self.orcid_user())

        self.assertEqual(user_id, self.user_id)


class TestAdminAddresses(unittest.TestCase):
    def test_a_comma_separated_list_is_split_and_trimmed(self):
        self.assertEqual(
            admin_addresses(" a@usp.br , b@usp.br,, "), ["a@usp.br", "b@usp.br"]
        )

    def test_an_empty_value_is_nobody(self):
        self.assertEqual(admin_addresses(""), [])


class TestCredentialFields(unittest.TestCase):
    def setUp(self):
        self.user_repository = Mock(spec=UserRepository)
        self.casbin_enforcer = Mock(spec=SyncedEnforcer)
        self.casbin_enforcer.get_roles_for_user.return_value = []
        self.service = UserService(
            self.user_repository, Mock(spec=TenancyRepository), self.casbin_enforcer
        )

    def test_a_user_says_whether_it_has_a_password_and_when_its_email_was_confirmed(
        self,
    ):
        user_id = uuid4()
        self.user_repository.fetch_by_id.return_value = UserDBModel(
            id=user_id,
            name="Ana Souza",
            email="ana.souza@usp.br",
            is_enabled=True,
            password_hash=BCRYPT_LIKE,
            email_verified_at=CREATED,
        )

        user = self.service.fetch_by_id(user_id)

        self.assertTrue(user.has_password)
        self.assertEqual(user.email_verified_at, CREATED)

    def test_an_account_without_either_says_so(self):
        user_id = uuid4()
        self.user_repository.fetch_by_id.return_value = UserDBModel(
            id=user_id, name="Ana Souza", email="ana.souza@usp.br", is_enabled=True
        )

        user = self.service.fetch_by_id(user_id)

        self.assertFalse(user.has_password)
        self.assertIsNone(user.email_verified_at)

    def test_a_new_address_is_no_longer_confirmed(self):
        db_user = UserDBModel(
            id=uuid4(),
            name="Ana Souza",
            email="ana.souza@usp.br",
            is_enabled=True,
            email_verified_at=CREATED,
        )
        self.user_repository.fetch_by_id.return_value = db_user
        self.user_repository.upsert.return_value = db_user

        self.service.update(db_user.id, name="Ana Souza", email="ana@ufam.edu.br")

        self.assertIsNone(db_user.email_verified_at)

    def test_the_same_address_in_another_case_stays_confirmed(self):
        db_user = UserDBModel(
            id=uuid4(),
            name="Ana Souza",
            email="ana.souza@usp.br",
            is_enabled=True,
            email_verified_at=CREATED,
        )
        self.user_repository.fetch_by_id.return_value = db_user
        self.user_repository.upsert.return_value = db_user

        self.service.update(db_user.id, name="Ana Souza", email="Ana.Souza@USP.br")

        self.assertEqual(db_user.email_verified_at, CREATED)
```

Create `app/controller/interceptor/authorization_test.py`:

```python
import unittest
from unittest.mock import Mock
from uuid import uuid4

from dependency_injector import providers
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import setup
from app.container import Container
from app.controller.interceptor.authorization import authorize_self_or_policy
from app.exception.unauthorized import UnauthorizedException
from app.service.auth import AuthService


class TestSelfOrPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = Container()
        app = FastAPI()
        setup.setup_error_handlers(app)

        @app.get("/users/{id}", dependencies=[Depends(authorize_self_or_policy)])
        def read(id: str):
            return {"id": id}

        cls.client = TestClient(app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls.container.unwire()

    def setUp(self):
        self.auth = Mock(spec=AuthService)
        self.container.auth_service.override(providers.Object(self.auth))

    def tearDown(self):
        self.container.auth_service.reset_override()

    def test_a_user_reaches_their_own_record_without_any_role(self):
        user_id = uuid4()

        response = self.client.get(
            f"/users/{user_id}", headers={"X-User-Id": str(user_id)}
        )

        self.assertEqual(response.status_code, 200)
        self.auth.authorize_user.assert_not_called()

    def test_the_same_id_written_in_capitals_is_still_themselves(self):
        user_id = uuid4()

        response = self.client.get(
            f"/users/{str(user_id).upper()}", headers={"X-User-Id": str(user_id)}
        )

        self.assertEqual(response.status_code, 200)
        self.auth.authorize_user.assert_not_called()

    def test_anyone_else_goes_through_casbin(self):
        user_id, other = uuid4(), uuid4()

        response = self.client.get(
            f"/users/{other}", headers={"X-User-Id": str(user_id)}
        )

        self.assertEqual(response.status_code, 200)
        self.auth.authorize_user.assert_called_once_with(
            user_id, f"/users/{other}", "GET"
        )

    def test_casbin_refusing_someone_else_is_401(self):
        self.auth.authorize_user.side_effect = UnauthorizedException("not_authorized")

        response = self.client.get(
            f"/users/{uuid4()}", headers={"X-User-Id": str(uuid4())}
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "not_authorized"})

    def test_a_path_id_that_is_not_a_uuid_goes_through_casbin(self):
        self.client.get("/users/everyone", headers={"X-User-Id": str(uuid4())})

        self.auth.authorize_user.assert_called_once()

    def test_without_a_user_header_it_is_401(self):
        response = self.client.get(f"/users/{uuid4()}")

        self.assertEqual(response.status_code, 401)
        self.auth.authorize_user.assert_not_called()
```

Create `app/controller/v1/user/user_test.py`:

```python
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import setup
from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import (
    authorize,
    authorize_self_or_policy,
)
from app.model.user import User
from app.service.user import UserService

CREATED = datetime(2026, 10, 3, 14, 5, tzinfo=timezone.utc)


def _user(**overrides) -> User:
    values = dict(
        id=uuid4(),
        name="Ana Souza",
        email="ana.souza@usp.br",
        providers=[],
        tenancies=[],
        roles=[],
        is_enabled=True,
        created_at=CREATED,
        updated_at=CREATED,
        email_verified_at=None,
        has_password=False,
    )
    values.update(overrides)
    return User(**values)


class UserRoutesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = Container()
        app = FastAPI()
        setup.setup_routes(app)
        setup.setup_error_handlers(app)
        app.dependency_overrides[authenticate] = lambda: None
        app.dependency_overrides[authorize] = lambda: None
        app.dependency_overrides[authorize_self_or_policy] = lambda: None
        cls.client = TestClient(app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls.container.unwire()

    def setUp(self):
        self.users = Mock(spec=UserService)
        self.container.user_service.override(providers.Object(self.users))

    def tearDown(self):
        self.container.user_service.reset_override()


class TestProfileFields(UserRoutesTestCase):
    def test_a_confirmed_account_with_a_password_says_both(self):
        self.users.fetch_by_id.return_value = _user(
            email_verified_at=CREATED, has_password=True
        )

        body = self.client.get(f"/v1/users/{uuid4()}").json()

        self.assertEqual(body["email_verified_at"], "2026-10-03T14:05:00Z")
        self.assertIs(body["has_password"], True)

    def test_an_unconfirmed_account_without_a_password_says_null_and_false(self):
        self.users.fetch_by_id.return_value = _user()

        body = self.client.get(f"/v1/users/{uuid4()}").json()

        self.assertIn("email_verified_at", body)
        self.assertIsNone(body["email_verified_at"])
        self.assertIs(body["has_password"], False)

    def test_the_lookup_by_provider_carries_them_too(self):
        self.users.fetch_by_provider.return_value = _user(email_verified_at=CREATED)

        body = self.client.get("/v1/users/providers/orcid/0000-0002-1825-0097").json()

        self.assertEqual(body["email_verified_at"], "2026-10-03T14:05:00Z")
        self.assertIs(body["has_password"], False)

    def test_reading_a_user_asks_for_self_or_policy_not_policy_alone(self):
        route = next(
            route
            for route in self.client.app.routes
            if getattr(route, "path", None) == "/v1/users/{id}"
            and "GET" in route.methods
        )
        guards = {dependency.call for dependency in route.dependant.dependencies}

        self.assertIn(authorize_self_or_policy, guards)
        self.assertNotIn(authorize, guards)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest app/service/user_test.py app/controller/v1/user/user_test.py app/controller/interceptor/authorization_test.py -v`
Expected: FAIL — `ImportError: cannot import name 'admin_addresses' from 'app.service.user'`, and `ImportError: cannot import name 'authorize_self_or_policy'` for both controller test files.

- [ ] **Step 3: Implement the domain and the service**

Replace `app/model/user.py` with:

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class UserProvider:
    name: str
    reference: str


@dataclass
class User:
    id: str = None
    name: str = None
    email: str = None
    providers: list[UserProvider] = None
    tenancies: list[str] = None
    roles: list[str] = None
    is_enabled: bool = True
    created_at: str = None
    updated_at: str = None
    email_verified_at: datetime | None = None
    has_password: bool = False


@dataclass
class UserQuery:
    email: str | None = None
    is_enabled: bool | None = True
```

In `app/service/user.py`, replace the import block with:

```python
import logging
from datetime import datetime, timezone
from uuid import UUID
from app.exception.not_found import NotFoundException
from app.logging_config import fields
from app.model.db.user import Provider as ProviderDBModel, User as UserDBModel
from app.model.user import User, UserProvider, UserQuery
from app.repository.tenancy import TenancyRepository
from app.repository.user import UserRepository
from app.service.email import EmailService
from app.service.email_format import long_date
from app.service.email_template import EmailTemplate
from app.service.share_token import hash_token
from casbin import SyncedEnforcer

PROVIDER_LABELS = {"orcid": "ORCID", "github": "GitHub"}


def admin_addresses(value: str) -> list[str]:
    return [address.strip() for address in (value or "").split(",") if address.strip()]


def sign_in_method(providers: list, has_password: bool) -> str:
    if has_password:
        return "Email and password"
    if providers:
        return ", ".join(
            PROVIDER_LABELS.get(provider.name, provider.name) for provider in providers
        )
    return "Created through the API"


def created_on(moment: datetime) -> str:
    utc = moment.astimezone(timezone.utc)
    return f"{long_date(utc)} at {utc:%H:%M} UTC"
```

Replace `UserService.__init__` with:

```python
    def __init__(
        self,
        repository: UserRepository,
        tenancy_repository: TenancyRepository,
        casbin_enforcer: SyncedEnforcer,
        email_service: EmailService | None = None,
        admin_emails: str = "",
    ) -> None:
        self._repository: UserRepository = repository
        self._tenancy_repository: TenancyRepository = tenancy_repository
        self._casbin_enforcer: SyncedEnforcer = casbin_enforcer
        self._email = email_service
        self._admin_emails = admin_addresses(admin_emails)
        self._logger = logging.getLogger("service:UserService")
```

In `__adapt_user`, add two arguments to the `User(...)` call, after `updated_at=user.updated_at,`:

```python
            email_verified_at=user.email_verified_at,
            has_password=user.password_hash is not None,
```

Replace `create` with:

```python
    def create(
        self,
        user: User,
        password_hash: str | None = None,
        email_verified_at: datetime | None = None,
    ) -> UUID:
        dbUser = UserDBModel(
            name=user.name,
            email=user.email,
            password_hash=password_hash,
            email_verified_at=email_verified_at,
        )

        for provider in user.providers:
            dbUser.providers.append(
                ProviderDBModel(name=provider.name, reference=provider.reference)
            )

        for tenancy in user.tenancies or []:
            dbUser.tenancies.append(self._tenancy_repository.fetch(tenancy=tenancy))

        created = self._repository.upsert(user=dbUser)
        user_id = created.id

        for role in user.roles:
            self._casbin_enforcer.add_grouping_policy(str(user_id), role)

        self._notify_admins(
            user_id, user, created.created_at, password_hash is not None
        )
        return user_id

    def _notify_admins(
        self, user_id: UUID, user: User, created_at: datetime, has_password: bool
    ) -> None:
        if self._email is None:
            return
        for recipient in self._admin_emails:
            try:
                self._email.enqueue(
                    template=EmailTemplate.NEW_ACCOUNT_PENDING.value,
                    recipient=recipient,
                    context={
                        "name": user.name,
                        "email": user.email,
                        "sign_in_method": sign_in_method(
                            user.providers or [], has_password
                        ),
                        "created_at": created_on(created_at),
                    },
                    related_type="user",
                    related_id=user_id,
                    dedup_key=f"new_account_pending:{user_id}:{hash_token(recipient.lower())[:16]}",
                )
            except Exception:
                self._logger.error(
                    "email enqueue failed",
                    exc_info=True,
                    extra=fields(
                        template=EmailTemplate.NEW_ACCOUNT_PENDING.value,
                        user_id=str(user_id),
                    ),
                )
```

In `update`, replace

```python
        user.name = name
        user.email = email
```

with

```python
        if (user.email or "").lower() != (email or "").lower():
            user.email_verified_at = None
        user.name = name
        user.email = email
```

- [ ] **Step 4: Implement the response, self-access and the container**

In `app/controller/v1/user/resource.py`, add to `UserGetResponse` after `tenancies`:

```python
    email_verified_at: datetime | None = Field(
        None, description="When the email was confirmed; null if it never was"
    )
    has_password: bool = Field(
        False, description="Whether the account can sign in with a password"
    )
```

In `app/controller/v1/user/user.py`, add to the `UserGetResponse(...)` call in `_adapt_get_response`, after `tenancies=user.tenancies,`:

```python
        email_verified_at=user.email_verified_at,
        has_password=user.has_password,
```

In `app/controller/interceptor/authorization.py`, add after `authorize`:

```python
def _is_self(request: Request, user_id: UUID) -> bool:
    try:
        return UUID(request.path_params.get("id", "")) == user_id
    except ValueError:
        return False


@inject
def authorize_self_or_policy(
    request: Request,
    user_id: UUID = Depends(parse_user_header),
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
):
    if _is_self(request, user_id):
        return
    try:
        auth_service.authorize_user(user_id, request.url.path, request.method)
    except UnauthorizedException as e:
        metrics.auth_failure("authz", str(e))
        raise
```

In `app/controller/v1/user/user.py`, import it (`from app.controller.interceptor.authorization import authorize, authorize_self_or_policy`) and change only the `GET /users/{id}` decorator to:

```python
@router.get(
    "/{id}", dependencies=[Depends(authenticate), Depends(authorize_self_or_policy)]
)
```

Every other user route keeps `authorize`.

In `app/container.py`, move these four providers, unchanged, from below `permission_service` to directly above `user_repository` (the user service now needs `email_service`, and a declarative container only references providers defined before it):

```python
    email_repository = providers.Factory(
        EmailRepository,
        session_factory=db.provided.session,
    )

    email_renderer = providers.Singleton(
        EmailTemplateRenderer,
        site_url=config.PUBLIC_BASE_URL,
    )

    smtp_sender = providers.Factory(
        SmtpSender,
        host=config.SMTP_HOST,
        port=config.SMTP_PORT,
        username=config.SMTP_USERNAME,
        password=config.SMTP_PASSWORD,
        starttls=config.SMTP_STARTTLS,
        timeout_seconds=config.SMTP_TIMEOUT_SECONDS,
        local_hostname=providers.Callable(public_hostname, config.PUBLIC_BASE_URL),
    )

    email_service = providers.Factory(
        EmailService,
        repository=email_repository,
        renderer=email_renderer,
        sender=smtp_sender,
        enabled=config.EMAIL_ENABLED,
        from_name=config.EMAIL_FROM_NAME,
        from_address=config.EMAIL_FROM_ADDRESS,
        reply_to=config.EMAIL_REPLY_TO,
        template_version=config.BUILD_COMMIT,
    )
```

and replace `user_service` with:

```python
    user_service = providers.Factory(
        UserService,
        repository=user_repository,
        tenancy_repository=tenancy_repository,
        casbin_enforcer=casbin_enforcer,
        email_service=email_service,
        admin_emails=config.ADMIN_NOTIFICATION_EMAILS,
    )
```

- [ ] **Step 5: Run them and watch them pass**

Run: `pytest app/service/user_test.py app/controller/v1/user/user_test.py app/controller/interceptor/authorization_test.py app/controller/routes_security_test.py -v`
Expected: PASS — the new tests, every existing `TestUserService` test (they build `UserService` with three arguments, so no email is sent), and the route-security test (`GET /v1/users/{id}` still has `authenticate`).

Run: `pytest -q`
Expected: 0 failed.

The interceptor change is proven against the real pipeline in Task 15 (`TestSelfAccess`), as CLAUDE.md requires for anything in `app/controller/interceptor/`.

- [ ] **Step 6: Commit**

```bash
ruff check app/model/user.py app/service/user.py app/service/user_test.py app/controller/v1/user app/controller/interceptor app/container.py
ruff format app/model/user.py app/service/user.py app/service/user_test.py app/controller/v1/user/resource.py app/controller/v1/user/user.py app/controller/v1/user/user_test.py app/controller/interceptor/authorization.py app/controller/interceptor/authorization_test.py app/container.py
git add app/model/user.py app/service/user.py app/service/user_test.py app/controller/v1/user/resource.py app/controller/v1/user/user.py app/controller/v1/user/user_test.py app/controller/interceptor/authorization.py app/controller/interceptor/authorization_test.py app/container.py
git commit -m "$(cat <<'EOF'
feat: a user reads their own record without a role; responses show the confirmed email and the password; admins hear of every new account

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: `AccountService` — sign-up, email verification and resend

**Files:**
- Create: `app/service/account.py`, `app/service/account_test.py`

**Interfaces:**
- Consumes: `UserRepository.fetch_by_email_any`, `.fetch_by_provider(provider_name=, reference=)`, `.set_password`, `.verify_email`; `UserService.create(user, password_hash=, email_verified_at=)`, `.add_provider(id=, provider=, reference=)`; every `AuthChallengeRepository` method (including `confirm`); `EmailRepository.count_recent`; `EmailService.enqueue`; `PasswordHasher.hash`; `new_code`, `code_hash`, `new_token`; `normalise_email`, `normalise_orcid`; `TooManyRequestsException`.
- Produces: `AccountService(users, user_service, challenges, emails, email_service, hasher, challenge_pepper, public_base_url, clock=_utcnow)` with `sign_up(name: str, email: str, password: str) -> UUID`, `confirm_sign_up(challenge_id: UUID, code: str) -> UUID`, `request_email_verification(orcid: str, email: str, name: str) -> UUID`, `confirm_email_verification(challenge_id: UUID, code: str) -> UUID`, `resend(challenge_id: UUID) -> None`.

Emails are only enqueued here; the Archivist's dispatch (every minute in production) sends them, which is why the resend cooldown is 90 seconds.

Rules this task fixes, beyond the RFC text: a successful confirmation sets `confirmed_at` as well as `consumed_at`, and only that makes a challenge final — resend works on every other code challenge (expired, out of attempts, replaced), which is what "Code expired, request a new one" asks the person to do. A disabled account holding the email is never reused by email verification (`409 email_belongs_to_another_account`).

- [ ] **Step 1: Write the failing test**

Create `app/service/account_test.py`:

```python
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
        self.users.fetch_by_provider.return_value = None
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

        self.assert_refused("code_expired", self.service.confirm_sign_up, pending.id, CODE)

        self.challenges.consume.assert_called_once_with(pending.id, NOW)
        self.challenges.confirm.assert_not_called()
        self.user_service.create.assert_not_called()

    def test_a_used_code_does_not_work_again(self):
        pending = self.pending(
            consumed_at=NOW - timedelta(minutes=1),
            confirmed_at=NOW - timedelta(minutes=1),
        )

        self.assert_refused("code_invalid", self.service.confirm_sign_up, pending.id, CODE)

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

        self.assert_refused("code_expired", self.service.confirm_sign_up, pending.id, CODE)

    def test_a_code_confirmed_concurrently_is_invalid(self):
        pending = self.pending()
        self.challenges.confirm.return_value = False

        self.assert_refused("code_invalid", self.service.confirm_sign_up, pending.id, CODE)
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
        self.users.fetch_by_provider.return_value = orcid_account

        self.assertEqual(self.confirm(), orcid_account.id)

        self.users.fetch_by_provider.assert_called_once_with(
            provider_name="orcid", reference=ORCID
        )
        self.users.verify_email.assert_called_once_with(
            orcid_account.id, "ana.souza@usp.br", NOW
        )

    def test_an_orcid_account_that_already_has_this_email_is_confirmed(self):
        orcid_account = account(email_verified_at=None)
        self.users.fetch_by_provider.return_value = orcid_account
        self.users.fetch_by_email_any.return_value = orcid_account

        self.assertEqual(self.confirm(), orcid_account.id)

        self.users.verify_email.assert_called_once_with(
            orcid_account.id, "ana.souza@usp.br", NOW
        )

    def test_an_orcid_account_and_another_account_with_the_email_conflict(self):
        self.users.fetch_by_provider.return_value = account()
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

    def test_a_wrong_code_changes_no_account(self):
        self.challenges.record_failed_attempt.return_value = 1

        self.assert_refused(
            "code_invalid",
            self.service.confirm_email_verification,
            self.pending.id,
            "000000",
        )

        self.users.fetch_by_provider.assert_not_called()
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
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest app/service/account_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.service.account'`.

- [ ] **Step 3: Implement**

Create `app/service/account.py`:

```python
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
        by_orcid = self._users.fetch_by_provider(
            provider_name=ORCID_PROVIDER, reference=orcid
        )
        by_email = self._users.fetch_by_email_any(email)

        if by_orcid is not None:
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
```

- [ ] **Step 4: Run it and watch it pass**

Run: `pytest app/service/account_test.py app/model/db/auth_challenge_test.py -v`
Expected: PASS — 41 tests in `account_test.py`.

- [ ] **Step 5: Commit**

```bash
ruff check app/service/account.py app/service/account_test.py
ruff format app/service/account.py app/service/account_test.py
git add app/service/account.py app/service/account_test.py
git commit -m "$(cat <<'EOF'
feat: sign-up and email verification confirmed by code, with resend and the hourly cap

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: `AccountService` — sign-in, password reset and password change

**Files:**
- Modify: `app/service/account.py`, `app/service/account_test.py`

**Interfaces:**
- Consumes: `UserRepository.fetch_by_id(id=)`, `.fetch_by_email_any`, `.record_failed_login(id, threshold, lock_until)`, `.clear_failed_logins`, `.set_password`; `AuthChallengeRepository.replace`, `.fetch_open_by_secret`, `.consume_open_for_user`; `PasswordHasher.verify`, `.burn`, `.hash`; `hash_token`, `new_token`.
- Produces: `AccountService.login(email: str, password: str) -> UUID`, `.request_password_reset(email: str) -> None`, `.reset_link(token: str) -> str`, `.confirm_password_reset(token: str, password: str) -> None`, `.change_password(user_id: UUID, current_password: str, new_password: str) -> None`.

- [ ] **Step 1: Write the failing tests**

In `app/service/account_test.py`, add to the imports `from app.exception.unauthorized import UnauthorizedException` and `from app.service.share_token import hash_token`, then append:

```python
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
        pending = challenge(
            kind=ChallengeKind.PASSWORD_RESET,
            secret_hash=hash_token("tok"),
            user_id=uuid4(),
            **overrides,
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

    def test_an_unknown_or_used_token_is_invalid(self):
        self.challenges.fetch_open_by_secret.return_value = None

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
        self.users.record_failed_login.assert_not_called()

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
```

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest app/service/account_test.py -v`
Expected: FAIL — `AttributeError: 'AccountService' object has no attribute 'login'` (and `request_password_reset`, `confirm_password_reset`, `change_password`); the Task 10 tests still pass.

- [ ] **Step 3: Implement**

In `app/service/account.py`:

Replace `from app.service.share_token import new_token` with `from app.service.share_token import hash_token, new_token`; add `from app.exception.unauthorized import UnauthorizedException` after the `too_many_requests` import and `from app.model.db.user import User as UserDBModel` after the `auth_challenge` model import.

Add after `CAP_WINDOW = timedelta(hours=1)`:

```python
RESET_LIFETIME = timedelta(hours=1)
MAX_FAILED_LOGINS = 10
LOCK_DURATION = timedelta(minutes=15)
INVALID_CREDENTIALS = "invalid_credentials"
```

Add these methods to `AccountService`, after `resend`:

```python
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
        now = self._clock()
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
            EmailTemplate.PASSWORD_RESET,
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
        if challenge is None or challenge.user_id is None or challenge.expires_at <= now:
            raise _invalid("token_invalid")
        self._users.set_password(challenge.user_id, self._hasher.hash(password))
        self._challenges.consume_open_for_user(
            challenge.user_id, ChallengeKind.PASSWORD_RESET, now
        )

    def change_password(
        self, user_id: UUID, current_password: str, new_password: str
    ) -> None:
        _password(new_password)
        current_password = current_password or ""
        found = self._users.fetch_by_id(id=user_id)
        if found is None or found.password_hash is None:
            self._hasher.burn(current_password)
            raise self._refused("unknown" if found is None else "no_password", found)
        if not self._hasher.verify(current_password, found.password_hash):
            raise self._refused("wrong_password", found)
        self._users.set_password(found.id, self._hasher.hash(new_password))

    def _account_for_login(self, email: str) -> UserDBModel | None:
        try:
            return self._users.fetch_by_email_any(normalise_email(email))
        except BadRequestException:
            return None

    def _refused(
        self, reason: str, found: UserDBModel | None
    ) -> UnauthorizedException:
        self._logger.info(
            "password check refused",
            extra=fields(
                reason=reason, user_id=str(found.id) if found is not None else None
            ),
        )
        return UnauthorizedException(INVALID_CREDENTIALS)
```

- [ ] **Step 4: Run them and watch them pass**

Run: `pytest app/service/account_test.py -v`
Expected: PASS, 66 tests.

- [ ] **Step 5: Commit**

```bash
ruff check app/service/account.py app/service/account_test.py
ruff format app/service/account.py app/service/account_test.py
git add app/service/account.py app/service/account_test.py
git commit -m "$(cat <<'EOF'
feat: password sign-in with a lock, password reset by link and password change

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Routes — `/v1/auth/*` and `PUT /v1/users/{id}/password`

**Files:**
- Create: `app/controller/v1/auth/__init__.py` (empty), `app/controller/v1/auth/resource.py`, `app/controller/v1/auth/auth.py`, `app/controller/v1/auth/auth_test.py`
- Modify: `app/controller/v1/user/resource.py`, `app/controller/v1/user/user.py`, `app/controller/v1/user/user_test.py`, `app/container.py`, `app/setup.py`

**Interfaces:**
- Consumes: every `AccountService` method; `authenticate`, `authorize_self_or_policy`, `parse_user_header`.
- Produces: the nine routes of the contract; `Container.password_hasher` (Singleton), `Container.auth_challenge_repository`, `Container.account_service`.

- [ ] **Step 1: Write the failing tests**

Create `app/controller/v1/auth/auth_test.py`:

```python
import inspect
import unittest
from unittest.mock import Mock
from uuid import uuid4

from dependency_injector import providers
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import setup
from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.too_many_requests import TooManyRequestsException
from app.exception.unauthorized import UnauthorizedException
from app.service.account import AccountService

PASSWORD = "correct horse battery"


class AuthRoutesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = Container()
        cls.app = FastAPI()
        setup.setup_routes(cls.app)
        setup.setup_error_handlers(cls.app)
        cls.app.dependency_overrides[authenticate] = lambda: None
        cls.client = TestClient(cls.app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls.container.unwire()

    def setUp(self):
        self.accounts = Mock(spec=AccountService)
        self.container.account_service.override(providers.Object(self.accounts))

    def tearDown(self):
        self.container.account_service.reset_override()


class TestSignUpRoutes(AuthRoutesTestCase):
    def test_a_sign_up_answers_202_with_the_challenge(self):
        challenge_id = uuid4()
        self.accounts.sign_up.return_value = challenge_id

        response = self.client.post(
            "/v1/auth/sign-up",
            json={"name": "Ana Souza", "email": "ana@usp.br", "password": PASSWORD},
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"challenge_id": str(challenge_id)})
        self.accounts.sign_up.assert_called_once_with("Ana Souza", "ana@usp.br", PASSWORD)

    def test_a_validation_failure_is_400_with_its_code(self):
        self.accounts.sign_up.side_effect = IllegalStateException("invalid_password")

        response = self.client.post(
            "/v1/auth/sign-up",
            json={"name": "Ana Souza", "email": "ana@usp.br", "password": "short"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "invalid_password"})

    def test_a_confirmed_sign_up_answers_the_user(self):
        user_id, challenge_id = uuid4(), uuid4()
        self.accounts.confirm_sign_up.return_value = user_id

        response = self.client.post(
            f"/v1/auth/sign-up/{challenge_id}/confirm", json={"code": "042917"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"user_id": str(user_id)})
        self.accounts.confirm_sign_up.assert_called_once_with(challenge_id, "042917")

    def test_code_errors_are_400_with_their_code(self):
        for code in ("code_invalid", "code_expired", "code_attempts_exceeded"):
            with self.subTest(code=code):
                self.accounts.confirm_sign_up.side_effect = IllegalStateException(code)

                response = self.client.post(
                    f"/v1/auth/sign-up/{uuid4()}/confirm", json={"code": "042917"}
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"detail": code})

    def test_an_unknown_challenge_is_404(self):
        self.accounts.confirm_sign_up.side_effect = NotFoundException(
            "challenge_not_found"
        )

        response = self.client.post(
            f"/v1/auth/sign-up/{uuid4()}/confirm", json={"code": "042917"}
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "challenge_not_found"})

    def test_a_challenge_id_that_is_not_a_uuid_is_404_without_reaching_the_service(
        self,
    ):
        response = self.client.post(
            "/v1/auth/sign-up/not-a-uuid/confirm", json={"code": "042917"}
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "challenge_not_found"})
        self.accounts.confirm_sign_up.assert_not_called()


class TestEmailVerificationRoutes(AuthRoutesTestCase):
    def test_a_request_answers_202_with_the_challenge(self):
        challenge_id = uuid4()
        self.accounts.request_email_verification.return_value = challenge_id

        response = self.client.post(
            "/v1/auth/email-verifications",
            json={
                "orcid": "0000-0002-1825-0097",
                "email": "ana@usp.br",
                "name": "Ana Souza",
            },
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"challenge_id": str(challenge_id)})
        self.accounts.request_email_verification.assert_called_once_with(
            "0000-0002-1825-0097", "ana@usp.br", "Ana Souza"
        )

    def test_a_confirmation_answers_the_user(self):
        user_id, challenge_id = uuid4(), uuid4()
        self.accounts.confirm_email_verification.return_value = user_id

        response = self.client.post(
            f"/v1/auth/email-verifications/{challenge_id}/confirm",
            json={"code": "042917"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"user_id": str(user_id)})

    def test_an_email_of_another_account_is_409(self):
        self.accounts.confirm_email_verification.side_effect = ConflictException(
            "email_belongs_to_another_account"
        )

        response = self.client.post(
            f"/v1/auth/email-verifications/{uuid4()}/confirm", json={"code": "042917"}
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(), {"detail": "email_belongs_to_another_account"}
        )


class TestResendRoute(AuthRoutesTestCase):
    def test_a_resend_answers_202_with_no_body(self):
        challenge_id = uuid4()

        response = self.client.post(f"/v1/auth/challenges/{challenge_id}/resend")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content, b"")
        self.accounts.resend.assert_called_once_with(challenge_id)

    def test_a_resend_too_soon_is_429(self):
        self.accounts.resend.side_effect = TooManyRequestsException("resend_too_soon")

        response = self.client.post(f"/v1/auth/challenges/{uuid4()}/resend")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), {"detail": "resend_too_soon"})


class TestLoginRoute(AuthRoutesTestCase):
    def test_a_sign_in_answers_the_user(self):
        user_id = uuid4()
        self.accounts.login.return_value = user_id

        response = self.client.post(
            "/v1/auth/login", json={"email": "ana@usp.br", "password": PASSWORD}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"user_id": str(user_id)})
        self.accounts.login.assert_called_once_with("ana@usp.br", PASSWORD)

    def test_every_refusal_is_401_invalid_credentials(self):
        self.accounts.login.side_effect = UnauthorizedException("invalid_credentials")

        response = self.client.post(
            "/v1/auth/login", json={"email": "ana@usp.br", "password": PASSWORD}
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "invalid_credentials"})


class TestPasswordResetRoutes(AuthRoutesTestCase):
    def test_a_reset_request_answers_202_with_no_body(self):
        response = self.client.post(
            "/v1/auth/password-reset", json={"email": "ana@usp.br"}
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content, b"")
        self.accounts.request_password_reset.assert_called_once_with("ana@usp.br")

    def test_a_reset_confirmation_answers_204(self):
        response = self.client.post(
            "/v1/auth/password-reset/confirm",
            json={"token": "tok", "password": "a brand new password"},
        )

        self.assertEqual(response.status_code, 204)
        self.accounts.confirm_password_reset.assert_called_once_with(
            "tok", "a brand new password"
        )

    def test_an_invalid_token_is_400(self):
        self.accounts.confirm_password_reset.side_effect = IllegalStateException(
            "token_invalid"
        )

        response = self.client.post(
            "/v1/auth/password-reset/confirm",
            json={"token": "tok", "password": "a brand new password"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "token_invalid"})


class TestTheRoutesStayOffTheEventLoop(AuthRoutesTestCase):
    def test_every_route_that_hashes_is_a_plain_function_run_in_the_threadpool(self):
        routes = [
            route
            for route in self.app.routes
            if isinstance(route, APIRoute)
            and (
                route.path.startswith("/v1/auth/")
                or route.path == "/v1/users/{id}/password"
            )
        ]

        self.assertEqual(len(routes), 9)
        for route in routes:
            with self.subTest(path=route.path):
                self.assertFalse(inspect.iscoroutinefunction(route.endpoint))
```

Append to `app/controller/v1/user/user_test.py` (add the imports `from app.exception.illegal_state import IllegalStateException`, `from app.exception.unauthorized import UnauthorizedException` and `from app.service.account import AccountService`):

```python
class TestChangePasswordRoute(UserRoutesTestCase):
    def setUp(self):
        super().setUp()
        self.accounts = Mock(spec=AccountService)
        self.container.account_service.override(providers.Object(self.accounts))

    def tearDown(self):
        self.container.account_service.reset_override()
        super().tearDown()

    def put(self, user_id, acting_as):
        return self.client.put(
            f"/v1/users/{user_id}/password",
            json={
                "current_password": "correct horse battery",
                "new_password": "a brand new password",
            },
            headers={"X-User-Id": str(acting_as)},
        )

    def test_a_user_changes_their_own_password(self):
        user_id = uuid4()

        response = self.put(user_id, acting_as=user_id)

        self.assertEqual(response.status_code, 204)
        self.accounts.change_password.assert_called_once_with(
            user_id=user_id,
            current_password="correct horse battery",
            new_password="a brand new password",
        )

    def test_nobody_changes_another_users_password(self):
        response = self.put(uuid4(), acting_as=uuid4())

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "invalid_credentials"})
        self.accounts.change_password.assert_not_called()

    def test_a_wrong_current_password_is_401(self):
        user_id = uuid4()
        self.accounts.change_password.side_effect = UnauthorizedException(
            "invalid_credentials"
        )

        response = self.put(user_id, acting_as=user_id)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "invalid_credentials"})

    def test_a_new_password_out_of_policy_is_400(self):
        user_id = uuid4()
        self.accounts.change_password.side_effect = IllegalStateException(
            "invalid_password"
        )

        response = self.put(user_id, acting_as=user_id)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "invalid_password"})

    def test_the_password_route_asks_for_self_or_policy(self):
        route = next(
            route
            for route in self.client.app.routes
            if getattr(route, "path", None) == "/v1/users/{id}/password"
        )
        guards = {dependency.call for dependency in route.dependant.dependencies}

        self.assertIn(authorize_self_or_policy, guards)
        self.assertNotIn(authorize, guards)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest app/controller/v1/auth/auth_test.py app/controller/v1/user/user_test.py -v`
Expected: FAIL — `AttributeError: type object 'Container' has no attribute 'account_service'` in `setUp`, and 404 on `PUT /v1/users/{id}/password`.

- [ ] **Step 3: Implement the auth router**

Create `app/controller/v1/auth/__init__.py` as an empty file.

Create `app/controller/v1/auth/resource.py`:

```python
from uuid import UUID

from pydantic import BaseModel, Field


class SignUpRequest(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address; the account's identity")
    password: str = Field(..., description="10 to 128 characters")


class EmailVerificationRequest(BaseModel):
    orcid: str = Field(..., description="ORCID iD of the signed-in ORCID session")
    email: str = Field(..., description="Email address to confirm")
    name: str = Field(..., description="Name given by ORCID")


class CodeRequest(BaseModel):
    code: str = Field(..., description="The 6-digit code from the email")


class LoginRequest(BaseModel):
    email: str = Field(..., description="Email address")
    password: str = Field(..., description="Password")


class PasswordResetRequest(BaseModel):
    email: str = Field(..., description="Email address of the account")


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(..., description="Token from the reset link")
    password: str = Field(..., description="New password, 10 to 128 characters")


class ChallengeResponse(BaseModel):
    challenge_id: UUID = Field(..., description="Challenge to confirm or resend")


class UserIdResponse(BaseModel):
    user_id: UUID = Field(..., description="Gatekeeper user id")
```

Create `app/controller/v1/auth/auth.py`:

```python
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.v1.auth.resource import (
    ChallengeResponse,
    CodeRequest,
    EmailVerificationRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    SignUpRequest,
    UserIdResponse,
)
from app.exception.not_found import NotFoundException
from app.service.account import AccountService

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(authenticate)],
)


def _challenge_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise NotFoundException("challenge_not_found")


@router.post("/sign-up", status_code=202, response_model=ChallengeResponse)
@inject
def sign_up(
    body: SignUpRequest,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> ChallengeResponse:
    return ChallengeResponse(
        challenge_id=service.sign_up(body.name, body.email, body.password)
    )


@router.post("/sign-up/{challenge_id}/confirm", response_model=UserIdResponse)
@inject
def confirm_sign_up(
    challenge_id: str,
    body: CodeRequest,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> UserIdResponse:
    return UserIdResponse(
        user_id=service.confirm_sign_up(_challenge_id(challenge_id), body.code)
    )


@router.post("/email-verifications", status_code=202, response_model=ChallengeResponse)
@inject
def request_email_verification(
    body: EmailVerificationRequest,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> ChallengeResponse:
    return ChallengeResponse(
        challenge_id=service.request_email_verification(
            body.orcid, body.email, body.name
        )
    )


@router.post(
    "/email-verifications/{challenge_id}/confirm", response_model=UserIdResponse
)
@inject
def confirm_email_verification(
    challenge_id: str,
    body: CodeRequest,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> UserIdResponse:
    return UserIdResponse(
        user_id=service.confirm_email_verification(
            _challenge_id(challenge_id), body.code
        )
    )


@router.post("/challenges/{challenge_id}/resend", status_code=202)
@inject
def resend(
    challenge_id: str,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> Response:
    service.resend(_challenge_id(challenge_id))
    return Response(status_code=202)


@router.post("/login", response_model=UserIdResponse)
@inject
def login(
    body: LoginRequest,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> UserIdResponse:
    return UserIdResponse(user_id=service.login(body.email, body.password))


@router.post("/password-reset", status_code=202)
@inject
def request_password_reset(
    body: PasswordResetRequest,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> Response:
    service.request_password_reset(body.email)
    return Response(status_code=202)


@router.post("/password-reset/confirm", status_code=204)
@inject
def confirm_password_reset(
    body: PasswordResetConfirmRequest,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> Response:
    service.confirm_password_reset(body.token, body.password)
    return Response(status_code=204)
```

- [ ] **Step 4: Implement the password change route**

In `app/controller/v1/user/resource.py`, append:

```python
class UserPasswordChangeRequest(BaseModel):
    current_password: str = Field(..., description="The account's current password")
    new_password: str = Field(..., description="New password, 10 to 128 characters")
```

In `app/controller/v1/user/user.py`: change `from fastapi import APIRouter, Depends` to `from fastapi import APIRouter, Depends, Response`; add `UserPasswordChangeRequest,` to the import list from `app.controller.v1.user.resource`; add the imports `from app.controller.interceptor.user_parser import parse_user_header`, `from app.exception.unauthorized import UnauthorizedException` and `from app.service.account import AccountService` (`authorize_self_or_policy` is already imported since Task 9); then add, after the `PUT /users/{id}/enable` route:

```python
# PUT /users/{id}/password
@router.put(
    "/{id}/password",
    status_code=204,
    dependencies=[Depends(authenticate), Depends(authorize_self_or_policy)],
)
@inject
def change_password(
    id: UUID,
    payload: UserPasswordChangeRequest,
    user_id: UUID = Depends(parse_user_header),
    service: AccountService = Depends(Provide[Container.account_service]),
) -> Response:
    if user_id != id:
        raise UnauthorizedException("invalid_credentials")
    service.change_password(
        user_id=id,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return Response(status_code=204)
```

- [ ] **Step 5: Wire the container and the app**

In `app/container.py`, add the imports:

```python
from app.repository.auth_challenge import AuthChallengeRepository
from app.service.account import AccountService
from app.service.password import PasswordHasher
```

add `"app.controller.v1.auth.auth",` to `wiring_config.modules` (after `"app.controller.interceptor.authorization",`), and add at the end of the class:

```python
    password_hasher = providers.Singleton(
        PasswordHasher,
        pepper=config.AUTH_PASSWORD_PEPPER,
    )

    auth_challenge_repository = providers.Factory(
        AuthChallengeRepository,
        session_factory=db.provided.session,
    )

    account_service = providers.Factory(
        AccountService,
        users=user_repository,
        user_service=user_service,
        challenges=auth_challenge_repository,
        emails=email_repository,
        email_service=email_service,
        hasher=password_hasher,
        challenge_pepper=config.AUTH_CHALLENGE_PEPPER,
        public_base_url=config.PUBLIC_BASE_URL,
    )
```

In `app/setup.py`, add `from app.controller.v1.auth.auth import router as auth_router` with the other router imports, and in `setup_routes`, after `fastAPIApp.include_router(user_router, prefix="/v1")`:

```python
    fastAPIApp.include_router(auth_router, prefix="/v1")
```

- [ ] **Step 6: Run them and watch them pass**

Run: `pytest app/controller/v1/auth/auth_test.py app/controller/v1/user/user_test.py app/controller/routes_security_test.py -v`
Expected: PASS — including `test_every_route_is_authenticated_or_listed_as_public`, which now sees the eight `/v1/auth/*` routes guarded by the router's `authenticate`.

Run: `pytest -q`
Expected: 0 failed.

- [ ] **Step 7: Commit**

```bash
ruff check app/controller app/container.py app/setup.py
ruff format app/controller/v1/auth app/controller/v1/user app/container.py app/setup.py
git add app/controller/v1/auth app/controller/v1/user/resource.py app/controller/v1/user/user.py app/controller/v1/user/user_test.py app/container.py app/setup.py
git commit -m "$(cat <<'EOF'
feat: /v1/auth routes and PUT /users/{id}/password

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: Integration — sign-up, codes, resend and the hourly cap

**Files:**
- Create: `tests/integration/fixtures/account.py`, `tests/integration/test_auth_sign_up.py`

**Interfaces:**
- Consumes: the routes of Task 12; `dispatch()` (`POST /internal/notifications/dispatch`, as `test_email_delivery.py` uses it) and `random_orcid()` from `tests/integration/fixtures/sharing.py`; `client_headers()`, `headers_for()` from `tests/integration/fixtures/embargo.py`; `execute()` from `tests/integration/utils/database.py`; `Mailpit`; `access_lines`, `wait_for_log`.
- Produces (fixtures): `PASSWORD`, `ADMIN_ADDRESS`, `unique_email()`, `refused(response, status, detail)`, `delivered()`, `newest_text()`, `newest_code()`, `newest_reset_token()`, `outbox(http_client, **filters)`, `sign_up()`, `confirm_sign_up()`, `request_email_verification()`, `confirm_email_verification()`, `resend()`, `login()`, `request_password_reset()`, `confirm_password_reset()`, `change_password()`, `password_account()`, `user()`, `create_plain_user()`, `age_challenge()`.

Codes and links are read from Mailpit after `POST /internal/notifications/dispatch`, which is how the Archivist sends every email. Expiry and cooldown are reached by moving timestamps in the database rather than by waiting.

- [ ] **Step 1: Write the helpers**

Create `tests/integration/fixtures/account.py`:

```python
import re
import time
import uuid

import requests

from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.embargo import client_headers, headers_for
from tests.integration.fixtures.sharing import dispatch
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.http_client import HttpClient
from tests.integration.utils.mailpit import Mailpit

PASSWORD = "correct horse battery"
ADMIN_ADDRESS = "datamap-admins@fake.mail.com"
CODE = re.compile(r"Your DataMap code: (\d{6})")
RESET_LINK = re.compile(r"/account/reset-password/([A-Za-z0-9_-]+)")


def unique_email(prefix: str = "account") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}@example.com"


def refused(response: requests.Response, status: int, detail: str) -> None:
    assert_status_code(response, status)
    assert response.json() == {"detail": detail}, response.json()


def delivered(
    http_client: HttpClient, mailpit: Mailpit, address: str, count: int = 1
) -> list[dict]:
    for _ in range(20):
        dispatch(http_client)
        found = mailpit.messages_to(address)
        if len(found) >= count:
            return found
        time.sleep(0.25)
    raise AssertionError(
        f"expected {count} message(s) to {address}, "
        f"got {len(mailpit.messages_to(address))}"
    )


def newest_text(
    http_client: HttpClient, mailpit: Mailpit, address: str, count: int = 1
) -> str:
    found = delivered(http_client, mailpit, address, count)
    newest = max(found, key=lambda message: message["Created"])
    return mailpit.message(newest["ID"])["Text"]


def newest_code(
    http_client: HttpClient, mailpit: Mailpit, address: str, count: int = 1
) -> str:
    found = CODE.search(newest_text(http_client, mailpit, address, count))
    assert found, f"no code in the newest message to {address}"
    return found.group(1)


def newest_reset_token(
    http_client: HttpClient, mailpit: Mailpit, address: str, count: int = 1
) -> str:
    found = RESET_LINK.search(newest_text(http_client, mailpit, address, count))
    assert found, f"no reset link in the newest message to {address}"
    return found.group(1)


def outbox(http_client: HttpClient, **filters) -> dict:
    response = http_client.get(
        "/admin/emails/", params=filters, headers=AuthFixture.valid_headers()
    )
    assert_status_code(response, 200)
    return response.json()


def sign_up(
    http_client: HttpClient,
    email: str,
    password: str = PASSWORD,
    name: str = "Ana Souza",
) -> requests.Response:
    return http_client.post(
        "/auth/sign-up",
        json={"name": name, "email": email, "password": password},
        headers=client_headers(),
    )


def confirm_sign_up(
    http_client: HttpClient, challenge_id, code: str, headers: dict | None = None
) -> requests.Response:
    return http_client.post(
        f"/auth/sign-up/{challenge_id}/confirm",
        json={"code": code},
        headers=headers or client_headers(),
    )


def request_email_verification(
    http_client: HttpClient, orcid: str, email: str, name: str = "Ana Souza"
) -> requests.Response:
    return http_client.post(
        "/auth/email-verifications",
        json={"orcid": orcid, "email": email, "name": name},
        headers=client_headers(),
    )


def confirm_email_verification(
    http_client: HttpClient, challenge_id, code: str
) -> requests.Response:
    return http_client.post(
        f"/auth/email-verifications/{challenge_id}/confirm",
        json={"code": code},
        headers=client_headers(),
    )


def resend(http_client: HttpClient, challenge_id) -> requests.Response:
    return http_client.post(
        f"/auth/challenges/{challenge_id}/resend", headers=client_headers()
    )


def login(http_client: HttpClient, email: str, password: str) -> requests.Response:
    return http_client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers=client_headers(),
    )


def request_password_reset(http_client: HttpClient, email: str) -> requests.Response:
    return http_client.post(
        "/auth/password-reset", json={"email": email}, headers=client_headers()
    )


def confirm_password_reset(
    http_client: HttpClient, token: str, password: str
) -> requests.Response:
    return http_client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "password": password},
        headers=client_headers(),
    )


def change_password(
    http_client: HttpClient,
    user_id: str,
    current: str,
    new: str,
    acting_as: str | None = None,
) -> requests.Response:
    return http_client.put(
        f"/users/{user_id}/password",
        json={"current_password": current, "new_password": new},
        headers=headers_for(acting_as or user_id, None),
    )


def password_account(
    http_client: HttpClient,
    mailpit: Mailpit,
    email: str | None = None,
    password: str = PASSWORD,
) -> dict:
    email = email or unique_email()
    already = len(mailpit.messages_to(email))
    started = sign_up(http_client, email, password)
    assert_status_code(started, 202)
    code = newest_code(http_client, mailpit, email, count=already + 1)
    confirmed = confirm_sign_up(http_client, started.json()["challenge_id"], code)
    assert_status_code(confirmed, 200)
    return {"id": confirmed.json()["user_id"], "email": email, "password": password}


def user(http_client: HttpClient, user_id: str) -> dict:
    response = http_client.get(f"/users/{user_id}", headers=AuthFixture.valid_headers())
    assert_status_code(response, 200)
    return response.json()


def create_plain_user(
    http_client: HttpClient, email: str, providers: list[dict] | None = None
) -> str:
    response = http_client.post(
        "/users/",
        json={
            "name": "Ana Souza",
            "email": email,
            "providers": providers or [],
            "roles": [],
        },
        headers=AuthFixture.valid_headers(),
    )
    assert_status_code(response, 200)
    return response.json()["id"]


def age_challenge(challenge_id, column: str, seconds: int) -> None:
    execute(
        f"UPDATE auth_challenges SET {column} = now() - interval '{seconds} seconds' "
        f"WHERE id = '{challenge_id}'"
    )
```

- [ ] **Step 2: Write the tests**

Create `tests/integration/test_auth_sign_up.py`:

```python
import uuid

import pytest

from tests.integration.fixtures.account import (
    PASSWORD,
    age_challenge,
    confirm_sign_up,
    create_plain_user,
    delivered,
    login,
    newest_code,
    outbox,
    refused,
    resend,
    sign_up,
    unique_email,
    user,
)
from tests.integration.fixtures.embargo import client_headers
from tests.integration.fixtures.sharing import dispatch
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.container_log import access_lines, wait_for_log
from tests.integration.utils.mailpit import Mailpit


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


def _started(http_client, email: str) -> str:
    response = sign_up(http_client, email)
    assert_status_code(response, 202)
    return response.json()["challenge_id"]


class TestSignUp:
    def test_a_new_email_becomes_a_confirmed_account_that_signs_in(
        self, http_client, mailpit
    ):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email)

        confirmed = confirm_sign_up(http_client, challenge_id, code)

        assert_status_code(confirmed, 200)
        user_id = confirmed.json()["user_id"]
        profile = user(http_client, user_id)
        assert profile["email"] == email
        assert profile["has_password"] is True
        assert profile["email_verified_at"] is not None
        signed_in = login(http_client, email, PASSWORD)
        assert_status_code(signed_in, 200)
        assert signed_in.json() == {"user_id": user_id}

    def test_an_existing_account_gets_the_password_and_its_email_confirmed(
        self, http_client, mailpit
    ):
        email = unique_email()
        user_id = create_plain_user(http_client, email)
        before = user(http_client, user_id)

        challenge_id = _started(http_client, email.upper())
        code = newest_code(http_client, mailpit, email)
        confirmed = confirm_sign_up(http_client, challenge_id, code)

        assert_status_code(confirmed, 200)
        assert confirmed.json() == {"user_id": user_id}
        after = user(http_client, user_id)
        assert (before["has_password"], before["email_verified_at"]) == (False, None)
        assert after["has_password"] is True
        assert after["email_verified_at"] is not None

    def test_a_known_and_an_unknown_email_get_the_same_answer(self, http_client):
        known = unique_email()
        create_plain_user(http_client, known)

        answers = [sign_up(http_client, address) for address in (known, unique_email())]

        assert [answer.status_code for answer in answers] == [202, 202]
        assert [set(answer.json()) for answer in answers] == [
            {"challenge_id"},
            {"challenge_id"},
        ]

    def test_a_password_shorter_than_ten_characters_is_refused(self, http_client):
        refused(
            sign_up(http_client, unique_email(), password="too short"),
            400,
            "invalid_password",
        )

    def test_a_malformed_email_is_refused(self, http_client):
        refused(sign_up(http_client, "not-an-email"), 400, "invalid_email")


class TestCodes:
    def test_a_wrong_code_is_refused_and_the_right_one_still_works(
        self, http_client, mailpit
    ):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email)
        wrong = "000000" if code != "000000" else "111111"

        refused(confirm_sign_up(http_client, challenge_id, wrong), 400, "code_invalid")
        assert_status_code(confirm_sign_up(http_client, challenge_id, code), 200)

    def test_five_wrong_codes_use_the_challenge_up(self, http_client, mailpit):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email)
        wrong = "000000" if code != "000000" else "111111"

        answers = [
            confirm_sign_up(http_client, challenge_id, wrong).json()["detail"]
            for _ in range(5)
        ]

        assert answers == ["code_invalid"] * 4 + ["code_attempts_exceeded"]
        refused(
            confirm_sign_up(http_client, challenge_id, code),
            400,
            "code_attempts_exceeded",
        )

    def test_an_expired_code_is_refused_for_good(self, http_client, mailpit):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email)
        age_challenge(challenge_id, "expires_at", 1)

        refused(confirm_sign_up(http_client, challenge_id, code), 400, "code_expired")
        refused(confirm_sign_up(http_client, challenge_id, code), 400, "code_expired")

    def test_a_code_works_once(self, http_client, mailpit):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email)

        assert_status_code(confirm_sign_up(http_client, challenge_id, code), 200)
        refused(confirm_sign_up(http_client, challenge_id, code), 400, "code_invalid")

    def test_a_new_sign_up_retires_the_previous_code(self, http_client, mailpit):
        email = unique_email()
        first = _started(http_client, email)
        first_code = newest_code(http_client, mailpit, email, count=1)
        second = _started(http_client, email)
        second_code = newest_code(http_client, mailpit, email, count=2)

        refused(confirm_sign_up(http_client, first, first_code), 400, "code_invalid")
        assert_status_code(confirm_sign_up(http_client, second, second_code), 200)

    def test_an_unknown_challenge_is_not_found(self, http_client):
        refused(
            confirm_sign_up(http_client, uuid.uuid4(), "123456"),
            404,
            "challenge_not_found",
        )
        refused(
            confirm_sign_up(http_client, "not-a-uuid", "123456"),
            404,
            "challenge_not_found",
        )


class TestResend:
    def test_a_resend_within_ninety_seconds_is_refused(self, http_client, mailpit):
        email = unique_email()
        challenge_id = _started(http_client, email)
        delivered(http_client, mailpit, email)

        refused(resend(http_client, challenge_id), 429, "resend_too_soon")

    def test_a_resend_after_ninety_seconds_sends_a_new_code_and_retires_the_old(
        self, http_client, mailpit
    ):
        email = unique_email()
        challenge_id = _started(http_client, email)
        old = newest_code(http_client, mailpit, email, count=1)
        age_challenge(challenge_id, "issued_at", 91)

        again = resend(http_client, challenge_id)

        assert_status_code(again, 202)
        assert again.content == b""
        new = newest_code(http_client, mailpit, email, count=2)
        refused(confirm_sign_up(http_client, challenge_id, old), 400, "code_invalid")
        assert_status_code(confirm_sign_up(http_client, challenge_id, new), 200)

    def test_an_expired_challenge_can_be_resent(self, http_client, mailpit):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email, count=1)
        age_challenge(challenge_id, "expires_at", 1)
        refused(confirm_sign_up(http_client, challenge_id, code), 400, "code_expired")
        age_challenge(challenge_id, "issued_at", 91)

        assert_status_code(resend(http_client, challenge_id), 202)

        new = newest_code(http_client, mailpit, email, count=2)
        assert_status_code(confirm_sign_up(http_client, challenge_id, new), 200)

    def test_a_challenge_out_of_attempts_can_be_resent(self, http_client, mailpit):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email, count=1)
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            confirm_sign_up(http_client, challenge_id, wrong)
        refused(
            confirm_sign_up(http_client, challenge_id, code),
            400,
            "code_attempts_exceeded",
        )
        age_challenge(challenge_id, "issued_at", 91)

        assert_status_code(resend(http_client, challenge_id), 202)

        new = newest_code(http_client, mailpit, email, count=2)
        assert_status_code(confirm_sign_up(http_client, challenge_id, new), 200)

    def test_a_confirmed_challenge_cannot_be_resent(self, http_client, mailpit):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email)
        assert_status_code(confirm_sign_up(http_client, challenge_id, code), 200)
        age_challenge(challenge_id, "issued_at", 91)

        refused(resend(http_client, challenge_id), 404, "challenge_not_found")


class TestHourlyCap:
    def test_past_five_codes_an_hour_nothing_is_sent_and_the_challenge_never_confirms(
        self, http_client, mailpit
    ):
        email = unique_email()
        for sent in range(1, 6):
            _started(http_client, email)
            delivered(http_client, mailpit, email, count=sent)
        last_code = newest_code(http_client, mailpit, email, count=5)

        capped = sign_up(http_client, email)

        assert_status_code(capped, 202)
        assert set(capped.json()) == {"challenge_id"}
        assert outbox(http_client, recipient=email, template="sign_up_code")[
            "total_count"
        ] == 5
        refused(
            confirm_sign_up(http_client, capped.json()["challenge_id"], last_code),
            400,
            "code_invalid",
        )
        dispatch(http_client)
        assert len(mailpit.messages_to(email)) == 5


class TestWhatReachesTheLog:
    def test_the_access_line_of_a_confirmation_redacts_the_code(
        self, http_client, mailpit
    ):
        email = unique_email()
        challenge_id = _started(http_client, email)
        code = newest_code(http_client, mailpit, email)
        marker = f"req-{uuid.uuid4()}"

        confirm_sign_up(
            http_client,
            challenge_id,
            code,
            headers={**client_headers(), "X-Request-Id": marker},
        )

        lines = access_lines(wait_for_log(lambda log: marker in log), marker)
        assert lines
        assert lines[0]["body"] == {"code": "[redacted]"}

    def test_the_access_line_of_a_sign_up_redacts_the_password(self, http_client):
        marker = f"req-{uuid.uuid4()}"

        http_client.post(
            "/auth/sign-up",
            json={"name": "Ana Souza", "email": unique_email(), "password": PASSWORD},
            headers={**client_headers(), "X-Request-Id": marker},
        )

        lines = access_lines(wait_for_log(lambda log: marker in log), marker)
        assert lines
        assert lines[0]["body"]["password"] == "[redacted]"
        assert PASSWORD not in str(lines[0])
```

- [ ] **Step 3: Prove the tests can fail — run them against `main`**

A test that passes before the feature exists is testing nothing (CLAUDE.md). Build the stack from a worktree of `main` with these two files copied in:

```bash
G=/Users/caio.maia/workspace/datamap/gatekeeper
B=$G/.claude/worktrees/rfc-008-baseline
W=$G/.claude/worktrees/rfc-008-gatekeeper-auth
git -C "$G" worktree add --detach "$B" main
cp "$W/tests/integration/fixtures/account.py" "$B/tests/integration/fixtures/account.py"
cp "$W/tests/integration/test_auth_sign_up.py" "$B/tests/integration/test_auth_sign_up.py"
cd "$B" && make ENV_FILE_PATH=integration-test.env integration-test-clean
cd "$B" && mkdir -p "$(grep STORAGE_DOCKER_VOLUME integration-test.env | cut -d= -f2)_test_integration/datamap"
cd "$B" && make ENV_FILE_PATH=integration-test.env integration-test-build
cd "$B" && make ENV_FILE_PATH=integration-test.env integration-test-up
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/
```
Expected: `200`. If `integration-test-up` fails on `port is already allocated`, check `docker ps --format "{{.Names}}\t{{.Ports}}" | grep 5433` (CLAUDE.md).

Seed, then wait for Casbin, which reloads its policy every 5 seconds — running the suite straight after seeding gives a batch of 401s unrelated to the change:

```bash
cd "$B" && docker exec -i datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db < tests/integration/fixtures/seed_clients.sql
until [ "$(curl -s -o /dev/null -w '%{http_code}' -H 'X-Api-Key: 5060b1a2-9aaf-48db-871a-0839007fd478' -H 'X-Api-Secret: integration-test-not-a-real-secret' -H 'X-User-Id: cbb0a683-630f-4b86-8b45-91b90a6fce1c' http://localhost:9094/api/v1/clients/)" = 200 ]; do sleep 1; done
cd "$B" && make ENV_FILE_PATH=integration-test.env TEST_PATH=tests/integration/test_auth_sign_up.py integration-test-run-specific
```
Expected: FAIL — every one of the 19 tests fails (`404` on `/api/v1/auth/...`, or `KeyError: 'has_password'`), 0 passed. Any test that passes here is wrong; fix it before going on. Then:

```bash
cd "$B" && make ENV_FILE_PATH=integration-test.env integration-test-down
```

Keep `$B`; Tasks 14 and 15 use it the same way.

- [ ] **Step 4: Run them against this branch, with a migration round trip**

```bash
cd "$W" && make ENV_FILE_PATH=integration-test.env integration-test-clean
cd "$W" && mkdir -p "$(grep STORAGE_DOCKER_VOLUME integration-test.env | cut -d= -f2)_test_integration/datamap"
cd "$W" && make ENV_FILE_PATH=integration-test.env integration-test-build
cd "$W" && make ENV_FILE_PATH=integration-test.env integration-test-up
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/
```
Expected: `200`. The application applies the migrations at startup; if the container never becomes healthy, read `docker logs datamap_gatekeeper_test_integration` before anything else — a failing `b1c2d3e4f5a6` shows there.

Prove the migration goes down and back up against PostgreSQL:

```bash
docker exec datamap_gatekeeper_test_integration python3 -m alembic downgrade -1
docker exec datamap_gatekeeper_test_integration python3 -m alembic upgrade head
docker exec datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db -tA -c "SELECT version_num FROM alembic_version"
docker exec datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db -tA -c "SELECT count(*) FROM information_schema.columns WHERE table_name = 'users' AND column_name IN ('password_hash', 'email_verified_at', 'failed_login_count', 'locked_until')"
```
Expected: `Running downgrade b1c2d3e4f5a6 -> a7b8c9d0e1f2`, then `Running upgrade a7b8c9d0e1f2 -> b1c2d3e4f5a6`, then `b1c2d3e4f5a6`, then `4`.

Seed, wait for Casbin's reload, run:

```bash
cd "$W" && docker exec -i datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db < tests/integration/fixtures/seed_clients.sql
until [ "$(curl -s -o /dev/null -w '%{http_code}' -H 'X-Api-Key: 5060b1a2-9aaf-48db-871a-0839007fd478' -H 'X-Api-Secret: integration-test-not-a-real-secret' -H 'X-User-Id: cbb0a683-630f-4b86-8b45-91b90a6fce1c' http://localhost:9094/api/v1/clients/)" = 200 ]; do sleep 1; done
cd "$W" && make ENV_FILE_PATH=integration-test.env TEST_PATH=tests/integration/test_auth_sign_up.py integration-test-run-specific
```
Expected: PASS — `19 passed`, 0 failed, 0 skipped. A summary with `skipped` means `verify_services_running` could not reach the API: nothing ran.

- [ ] **Step 5: Full cycle**

```bash
cd "$W" && make ENV_FILE_PATH=integration-test.env integration-test-full
```
While it runs, after it prints `Integration test containers ready`, confirm the API answered:
`curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/` → `200`.

Expected: the pytest summary for `tests/integration/` shows `0 failed`, no `skipped` from `verify_services_running`, and `test_auth_sign_up.py` among the collected files. `integration-test-full` swallows failures (`|| echo "may have failed"`) and its readiness wait uses `timeout`, which macOS lacks: read the summary yourself, never the exit code, and never pipe `make` into `tail`/`grep`. Because this target seeds and starts the tests immediately, a batch of 401s in the first files is Casbin's 5-second reload, not this change: read that log first, then run `make ENV_FILE_PATH=integration-test.env integration-test-up`, seed, wait for `/clients/` to answer 200 as in Step 4, and run `make ENV_FILE_PATH=integration-test.env integration-test-run`.

- [ ] **Step 6: Commit**

```bash
ruff check tests/integration/fixtures/account.py tests/integration/test_auth_sign_up.py
ruff format tests/integration/fixtures/account.py tests/integration/test_auth_sign_up.py
git add tests/integration/fixtures/account.py tests/integration/test_auth_sign_up.py
git commit -m "$(cat <<'EOF'
test: sign-up, codes, resend and the hourly cap end to end

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: Integration — email verification and the new-account notification

**Files:**
- Create: `tests/integration/test_auth_email_verification.py`, `tests/integration/test_new_account_notification.py`

**Interfaces:**
- Consumes: Task 13's fixtures; `random_orcid()`; `GET /admin/emails/` and `GET /admin/emails/{id}`.
- Produces: coverage of every row of the RFC's email-verification table and of `new_account_pending` on the three creation paths.

- [ ] **Step 1: Write the tests**

Create `tests/integration/test_auth_email_verification.py`:

```python
import pytest

from tests.integration.fixtures.account import (
    confirm_email_verification,
    create_plain_user,
    newest_code,
    newest_text,
    refused,
    request_email_verification,
    unique_email,
    user,
)
from tests.integration.fixtures.embargo import client_headers
from tests.integration.fixtures.sharing import random_orcid
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.mailpit import Mailpit


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


def _orcid_account(http_client, orcid: str, email: str | None = None) -> str:
    return create_plain_user(
        http_client,
        email or f"{orcid.replace('-', '')}@fake.mail.com",
        providers=[{"name": "orcid", "reference": orcid}],
    )


def _confirmed(http_client, mailpit, orcid: str, email: str):
    started = request_email_verification(http_client, orcid, email)
    assert_status_code(started, 202)
    code = newest_code(http_client, mailpit, email)
    return confirm_email_verification(http_client, started.json()["challenge_id"], code)


class TestEmailVerificationTable:
    def test_an_orcid_account_without_this_email_takes_it_confirmed(
        self, http_client, mailpit
    ):
        orcid = random_orcid()
        user_id = _orcid_account(http_client, orcid)
        email = unique_email()

        confirmed = _confirmed(http_client, mailpit, orcid, email)

        assert_status_code(confirmed, 200)
        assert confirmed.json() == {"user_id": user_id}
        profile = user(http_client, user_id)
        assert profile["email"] == email
        assert profile["email_verified_at"] is not None

    def test_an_orcid_account_that_already_has_this_email_is_confirmed(
        self, http_client, mailpit
    ):
        orcid, email = random_orcid(), unique_email()
        user_id = _orcid_account(http_client, orcid, email)

        confirmed = _confirmed(http_client, mailpit, orcid, email)

        assert_status_code(confirmed, 200)
        assert confirmed.json() == {"user_id": user_id}
        assert user(http_client, user_id)["email_verified_at"] is not None

    def test_an_orcid_account_and_another_account_with_the_email_conflict(
        self, http_client, mailpit
    ):
        orcid, email = random_orcid(), unique_email()
        orcid_user = _orcid_account(http_client, orcid)
        other = create_plain_user(http_client, email)

        refused(
            _confirmed(http_client, mailpit, orcid, email),
            409,
            "email_belongs_to_another_account",
        )
        assert user(http_client, other)["email_verified_at"] is None
        assert user(http_client, orcid_user)["email_verified_at"] is None

    def test_an_email_account_gets_the_orcid_attached(self, http_client, mailpit):
        orcid, email = random_orcid(), unique_email()
        user_id = create_plain_user(http_client, email)

        confirmed = _confirmed(http_client, mailpit, orcid, email)

        assert_status_code(confirmed, 200)
        assert confirmed.json() == {"user_id": user_id}
        by_provider = http_client.get(
            f"/users/providers/orcid/{orcid}", headers=client_headers()
        )
        assert_status_code(by_provider, 200)
        assert by_provider.json()["id"] == user_id
        assert by_provider.json()["email_verified_at"] is not None
        assert by_provider.json()["has_password"] is False

    def test_neither_creates_a_confirmed_account_with_the_orcid(
        self, http_client, mailpit
    ):
        orcid, email = random_orcid(), unique_email()

        confirmed = _confirmed(http_client, mailpit, orcid, email)

        assert_status_code(confirmed, 200)
        profile = user(http_client, confirmed.json()["user_id"])
        assert profile["email"] == email
        assert profile["email_verified_at"] is not None
        assert profile["has_password"] is False
        assert profile["providers"] == [{"name": "orcid", "reference": orcid}]


class TestEmailVerificationRequests:
    def test_a_known_and_an_unknown_email_get_the_same_answer(self, http_client):
        known = unique_email()
        create_plain_user(http_client, known)

        answers = [
            request_email_verification(http_client, random_orcid(), address)
            for address in (known, unique_email())
        ]

        assert [answer.status_code for answer in answers] == [202, 202]
        assert [set(answer.json()) for answer in answers] == [
            {"challenge_id"},
            {"challenge_id"},
        ]

    def test_a_malformed_orcid_is_refused(self, http_client):
        refused(
            request_email_verification(
                http_client, "0000-0002-1825-0098", unique_email()
            ),
            400,
            "invalid_orcid",
        )

    def test_the_email_names_the_orcid_being_linked(self, http_client, mailpit):
        orcid, email = random_orcid(), unique_email()

        assert_status_code(request_email_verification(http_client, orcid, email), 202)

        assert f"ORCID iD: {orcid}" in newest_text(http_client, mailpit, email)
```

Create `tests/integration/test_new_account_notification.py`:

```python
import pytest

from tests.integration.fixtures.account import (
    ADMIN_ADDRESS,
    confirm_email_verification,
    create_plain_user,
    newest_code,
    outbox,
    password_account,
    request_email_verification,
    unique_email,
)
from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.sharing import random_orcid
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.mailpit import Mailpit


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


def _notifications(http_client, user_id: str) -> list[dict]:
    return outbox(http_client, related_id=user_id, template="new_account_pending")[
        "items"
    ]


def _body(http_client, email_id: str) -> str:
    response = http_client.get(
        f"/admin/emails/{email_id}", headers=AuthFixture.valid_headers()
    )
    assert_status_code(response, 200)
    return response.json()["body_text"]


class TestNewAccountNotification:
    def test_an_account_created_through_the_api_is_announced(self, http_client):
        email = unique_email()
        user_id = create_plain_user(http_client, email)

        items = _notifications(http_client, user_id)

        assert [item["recipient"] for item in items] == [ADMIN_ADDRESS]
        assert items[0]["subject"] == "New DataMap account: Ana Souza"
        body = _body(http_client, items[0]["id"])
        assert email in body
        assert "Created through the API" in body

    def test_a_password_sign_up_is_announced(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        items = _notifications(http_client, account["id"])

        assert [item["recipient"] for item in items] == [ADMIN_ADDRESS]
        body = _body(http_client, items[0]["id"])
        assert account["email"] in body
        assert "Email and password" in body

    def test_an_orcid_sign_up_is_announced(self, http_client, mailpit):
        orcid, email = random_orcid(), unique_email()
        started = request_email_verification(http_client, orcid, email)
        code = newest_code(http_client, mailpit, email)
        confirmed = confirm_email_verification(
            http_client, started.json()["challenge_id"], code
        )
        assert_status_code(confirmed, 200)

        items = _notifications(http_client, confirmed.json()["user_id"])

        assert [item["recipient"] for item in items] == [ADMIN_ADDRESS]
        assert "ORCID" in _body(http_client, items[0]["id"])

    def test_a_password_set_on_an_existing_account_announces_nothing_new(
        self, http_client, mailpit
    ):
        email = unique_email()
        user_id = create_plain_user(http_client, email)

        account = password_account(http_client, mailpit, email=email)

        assert account["id"] == user_id
        assert len(_notifications(http_client, user_id)) == 1
```

- [ ] **Step 2: Prove the tests can fail — run them against `main`**

```bash
G=/Users/caio.maia/workspace/datamap/gatekeeper
B=$G/.claude/worktrees/rfc-008-baseline
W=$G/.claude/worktrees/rfc-008-gatekeeper-auth
cp "$W/tests/integration/fixtures/account.py" "$B/tests/integration/fixtures/account.py"
cp "$W/tests/integration/test_auth_email_verification.py" "$W/tests/integration/test_new_account_notification.py" "$B/tests/integration/"
cd "$B" && make ENV_FILE_PATH=integration-test.env integration-test-clean
cd "$B" && make ENV_FILE_PATH=integration-test.env integration-test-up
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/
cd "$B" && docker exec -i datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db < tests/integration/fixtures/seed_clients.sql
until [ "$(curl -s -o /dev/null -w '%{http_code}' -H 'X-Api-Key: 5060b1a2-9aaf-48db-871a-0839007fd478' -H 'X-Api-Secret: integration-test-not-a-real-secret' -H 'X-User-Id: cbb0a683-630f-4b86-8b45-91b90a6fce1c' http://localhost:9094/api/v1/clients/)" = 200 ]; do sleep 1; done
cd "$B" && make ENV_FILE_PATH=integration-test.env TEST_PATH="tests/integration/test_auth_email_verification.py tests/integration/test_new_account_notification.py" integration-test-run-specific
cd "$B" && make ENV_FILE_PATH=integration-test.env integration-test-down
```
Expected: health check `200` (the `main` image was built in Task 13; rebuild with `integration-test-build` if `docker images` no longer has it); then FAIL — all 12 tests fail (`404` on `/api/v1/auth/...`; on `main`, `POST /users` queues no `new_account_pending`, so `test_an_account_created_through_the_api_is_announced` fails on an empty list), 0 passed.

- [ ] **Step 3: Run them against this branch**

```bash
cd "$W" && make ENV_FILE_PATH=integration-test.env integration-test-clean
cd "$W" && make ENV_FILE_PATH=integration-test.env integration-test-build
cd "$W" && make ENV_FILE_PATH=integration-test.env integration-test-up
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/
cd "$W" && docker exec -i datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db < tests/integration/fixtures/seed_clients.sql
until [ "$(curl -s -o /dev/null -w '%{http_code}' -H 'X-Api-Key: 5060b1a2-9aaf-48db-871a-0839007fd478' -H 'X-Api-Secret: integration-test-not-a-real-secret' -H 'X-User-Id: cbb0a683-630f-4b86-8b45-91b90a6fce1c' http://localhost:9094/api/v1/clients/)" = 200 ]; do sleep 1; done
cd "$W" && make ENV_FILE_PATH=integration-test.env TEST_PATH="tests/integration/test_auth_email_verification.py tests/integration/test_new_account_notification.py" integration-test-run-specific
```
Expected: health check `200`; the `until` loop ends (Casbin has loaded the seeded policy — it reloads every 5 seconds); PASS — `12 passed`, 0 failed, 0 skipped.

- [ ] **Step 4: Full cycle**

```bash
cd "$W" && make ENV_FILE_PATH=integration-test.env integration-test-full
```
While it runs, after `Integration test containers ready`: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/` → `200`.
Expected: the pytest summary shows `0 failed`, no `skipped` from `verify_services_running`, and both new files collected. Read the summary, not the exit code; do not pipe `make` into `tail`/`grep`. A batch of 401s at the start is Casbin's 5-second reload after the seed: read the log, then bring the stack up, seed, wait for `/clients/` to answer 200 and run `make ENV_FILE_PATH=integration-test.env integration-test-run`.

- [ ] **Step 5: Commit**

```bash
ruff check tests/integration/test_auth_email_verification.py tests/integration/test_new_account_notification.py
ruff format tests/integration/test_auth_email_verification.py tests/integration/test_new_account_notification.py
git add tests/integration/test_auth_email_verification.py tests/integration/test_new_account_notification.py
git commit -m "$(cat <<'EOF'
test: every row of the email verification table and the new account notification end to end

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 15: Integration — sign-in, lock, reset, self-access and password change

**Files:**
- Create: `tests/integration/test_auth_login_and_password.py`

**Interfaces:**
- Consumes: Task 13's fixtures; `execute()`; `headers_for()`; `PUT /users/{id}/roles`, `DELETE /users/{id}`, `GET /users/{id}`.
- Produces: coverage of every sign-in refusal, the lock and its two ways out, the reset link, self-access without a role (`authorize_self_or_policy` against the real pipeline, as CLAUDE.md requires for interceptor changes) and the password change.

Every account here comes from a sign-up, so it has no Casbin role — the case the self-access rule exists for. Roles granted through `PUT /users/{id}/roles` take effect at once (the API's own enforcer adds them); only rows seeded straight into `casbin_rule` wait for the 5-second reload.

- [ ] **Step 1: Write the tests**

Create `tests/integration/test_auth_login_and_password.py`:

```python
import pytest

from tests.integration.fixtures.account import (
    PASSWORD,
    change_password,
    confirm_email_verification,
    confirm_password_reset,
    create_plain_user,
    login,
    newest_code,
    newest_reset_token,
    outbox,
    password_account,
    refused,
    request_email_verification,
    request_password_reset,
    unique_email,
)
from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.embargo import headers_for
from tests.integration.fixtures.sharing import random_orcid
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.mailpit import Mailpit

NEW_PASSWORD = "a brand new password"


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


def _fail(http_client, email: str, times: int) -> None:
    for _ in range(times):
        assert_status_code(login(http_client, email, "not the password"), 401)


def _reset(http_client, mailpit, email: str, count: int, password: str = NEW_PASSWORD):
    assert_status_code(request_password_reset(http_client, email), 202)
    token = newest_reset_token(http_client, mailpit, email, count=count)
    return confirm_password_reset(http_client, token, password)


class TestSignIn:
    def test_the_right_password_signs_in(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        response = login(http_client, account["email"].upper(), PASSWORD)

        assert_status_code(response, 200)
        assert response.json() == {"user_id": account["id"]}

    def test_every_failure_is_the_same_401(self, http_client, mailpit):
        account = password_account(http_client, mailpit)
        no_password = unique_email()
        create_plain_user(http_client, no_password)
        unconfirmed = password_account(http_client, mailpit)
        execute(
            f"UPDATE users SET email_verified_at = NULL WHERE id = '{unconfirmed['id']}'"
        )
        disabled = password_account(http_client, mailpit)
        assert_status_code(
            http_client.delete(
                f"/users/{disabled['id']}", headers=AuthFixture.valid_headers()
            ),
            200,
        )

        answers = [
            login(http_client, unique_email(), PASSWORD),
            login(http_client, account["email"], "not the password"),
            login(http_client, no_password, PASSWORD),
            login(http_client, unconfirmed["email"], PASSWORD),
            login(http_client, disabled["email"], PASSWORD),
            login(http_client, "not-an-email", PASSWORD),
        ]

        assert [(answer.status_code, answer.json()) for answer in answers] == [
            (401, {"detail": "invalid_credentials"})
        ] * 6


class TestLock:
    def test_nine_wrong_passwords_do_not_lock(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        _fail(http_client, account["email"], 9)

        assert_status_code(login(http_client, account["email"], PASSWORD), 200)

    def test_the_tenth_locks_even_against_the_right_password(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)

        _fail(http_client, account["email"], 10)

        refused(login(http_client, account["email"], PASSWORD), 401, "invalid_credentials")
        assert (
            execute(
                "SELECT locked_until > now() + interval '14 minutes' "
                f"FROM users WHERE id = '{account['id']}'"
            )
            == "t"
        )

    def test_the_lock_ends_after_its_time_and_a_success_clears_it(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)
        _fail(http_client, account["email"], 10)
        execute(
            "UPDATE users SET locked_until = now() - interval '1 second' "
            f"WHERE id = '{account['id']}'"
        )

        assert_status_code(login(http_client, account["email"], PASSWORD), 200)

        assert (
            execute(
                "SELECT failed_login_count, locked_until IS NULL "
                f"FROM users WHERE id = '{account['id']}'"
            )
            == "0|t"
        )

    def test_a_reset_lifts_the_lock(self, http_client, mailpit):
        account = password_account(http_client, mailpit)
        _fail(http_client, account["email"], 10)

        assert_status_code(_reset(http_client, mailpit, account["email"], count=2), 204)

        assert_status_code(login(http_client, account["email"], NEW_PASSWORD), 200)


class TestPasswordReset:
    def test_a_reset_link_sets_a_new_password(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        assert_status_code(_reset(http_client, mailpit, account["email"], count=2), 204)

        refused(login(http_client, account["email"], PASSWORD), 401, "invalid_credentials")
        assert_status_code(login(http_client, account["email"], NEW_PASSWORD), 200)

    def test_a_link_works_once(self, http_client, mailpit):
        account = password_account(http_client, mailpit)
        assert_status_code(request_password_reset(http_client, account["email"]), 202)
        token = newest_reset_token(http_client, mailpit, account["email"], count=2)

        assert_status_code(confirm_password_reset(http_client, token, NEW_PASSWORD), 204)
        refused(
            confirm_password_reset(http_client, token, "another new password"),
            400,
            "token_invalid",
        )

    def test_an_expired_link_is_refused(self, http_client, mailpit):
        account = password_account(http_client, mailpit)
        assert_status_code(request_password_reset(http_client, account["email"]), 202)
        token = newest_reset_token(http_client, mailpit, account["email"], count=2)
        execute(
            "UPDATE auth_challenges SET expires_at = now() - interval '1 second' "
            f"WHERE user_id = '{account['id']}' AND kind = 'password_reset'"
        )

        refused(
            confirm_password_reset(http_client, token, NEW_PASSWORD), 400, "token_invalid"
        )

    def test_a_new_link_retires_the_previous_one(self, http_client, mailpit):
        account = password_account(http_client, mailpit)
        assert_status_code(request_password_reset(http_client, account["email"]), 202)
        first = newest_reset_token(http_client, mailpit, account["email"], count=2)
        assert_status_code(request_password_reset(http_client, account["email"]), 202)
        second = newest_reset_token(http_client, mailpit, account["email"], count=3)

        refused(
            confirm_password_reset(http_client, first, NEW_PASSWORD), 400, "token_invalid"
        )
        assert_status_code(confirm_password_reset(http_client, second, NEW_PASSWORD), 204)

    def test_a_known_and_an_unknown_email_get_the_same_answer(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)

        answers = [
            request_password_reset(http_client, address)
            for address in (account["email"], unique_email())
        ]

        assert [(answer.status_code, answer.content) for answer in answers] == [
            (202, b"")
        ] * 2

    def test_an_unknown_email_is_sent_nothing(self, http_client):
        address = unique_email()

        assert_status_code(request_password_reset(http_client, address), 202)

        assert outbox(http_client, recipient=address)["total_count"] == 0

    def test_an_unconfirmed_account_is_sent_nothing(self, http_client):
        address = unique_email()
        create_plain_user(http_client, address)

        assert_status_code(request_password_reset(http_client, address), 202)

        assert (
            outbox(http_client, recipient=address, template="password_reset")[
                "total_count"
            ]
            == 0
        )

    def test_an_orcid_account_sets_its_first_password_through_the_link(
        self, http_client, mailpit
    ):
        email = unique_email()
        started = request_email_verification(http_client, random_orcid(), email)
        code = newest_code(http_client, mailpit, email)
        assert_status_code(
            confirm_email_verification(http_client, started.json()["challenge_id"], code),
            200,
        )

        assert_status_code(_reset(http_client, mailpit, email, count=2), 204)

        assert_status_code(login(http_client, email, NEW_PASSWORD), 200)

    def test_a_short_password_is_refused(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        refused(
            _reset(http_client, mailpit, account["email"], count=2, password="too short"),
            400,
            "invalid_password",
        )


class TestSelfAccess:
    def test_an_account_without_a_role_reads_itself(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        response = http_client.get(
            f"/users/{account['id']}", headers=headers_for(account["id"], None)
        )

        assert_status_code(response, 200)
        assert response.json()["id"] == account["id"]
        assert response.json()["roles"] == []
        assert response.json()["has_password"] is True

    def test_an_account_without_a_role_cannot_read_anyone_else(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)
        other = password_account(http_client, mailpit)

        refused(
            http_client.get(
                f"/users/{other['id']}", headers=headers_for(account["id"], None)
            ),
            401,
            "not_authorized",
        )


class TestChangePassword:
    def test_an_account_without_a_role_changes_its_own_password(
        self, http_client, mailpit
    ):
        account = password_account(http_client, mailpit)

        response = change_password(http_client, account["id"], PASSWORD, NEW_PASSWORD)

        assert_status_code(response, 204)
        refused(login(http_client, account["email"], PASSWORD), 401, "invalid_credentials")
        assert_status_code(login(http_client, account["email"], NEW_PASSWORD), 200)

    def test_a_wrong_current_password_is_refused(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        refused(
            change_password(http_client, account["id"], "not the password", NEW_PASSWORD),
            401,
            "invalid_credentials",
        )
        assert_status_code(login(http_client, account["email"], PASSWORD), 200)

    def test_an_account_without_a_role_cannot_change_anyone_elses(
        self, http_client, mailpit
    ):
        victim = password_account(http_client, mailpit)
        attacker = password_account(http_client, mailpit)

        refused(
            change_password(
                http_client,
                victim["id"],
                PASSWORD,
                NEW_PASSWORD,
                acting_as=attacker["id"],
            ),
            401,
            "not_authorized",
        )
        assert_status_code(login(http_client, victim["email"], PASSWORD), 200)

    def test_even_a_role_that_may_write_users_cannot_change_anyone_elses(
        self, http_client, mailpit
    ):
        victim = password_account(http_client, mailpit)
        attacker = password_account(http_client, mailpit)
        granted = http_client.put(
            f"/users/{attacker['id']}/roles",
            json=["users_write"],
            headers=AuthFixture.valid_headers(),
        )
        assert_status_code(granted, 200)

        refused(
            change_password(
                http_client,
                victim["id"],
                PASSWORD,
                NEW_PASSWORD,
                acting_as=attacker["id"],
            ),
            401,
            "invalid_credentials",
        )
        assert_status_code(login(http_client, victim["email"], PASSWORD), 200)

    def test_a_new_password_out_of_policy_is_refused(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        refused(
            change_password(http_client, account["id"], PASSWORD, "too short"),
            400,
            "invalid_password",
        )
```

- [ ] **Step 2: Prove the tests can fail — run them against `main`**

```bash
G=/Users/caio.maia/workspace/datamap/gatekeeper
B=$G/.claude/worktrees/rfc-008-baseline
W=$G/.claude/worktrees/rfc-008-gatekeeper-auth
cp "$W/tests/integration/fixtures/account.py" "$B/tests/integration/fixtures/account.py"
cp "$W/tests/integration/test_auth_login_and_password.py" "$B/tests/integration/"
cd "$B" && make ENV_FILE_PATH=integration-test.env integration-test-clean
cd "$B" && make ENV_FILE_PATH=integration-test.env integration-test-up
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/
cd "$B" && docker exec -i datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db < tests/integration/fixtures/seed_clients.sql
until [ "$(curl -s -o /dev/null -w '%{http_code}' -H 'X-Api-Key: 5060b1a2-9aaf-48db-871a-0839007fd478' -H 'X-Api-Secret: integration-test-not-a-real-secret' -H 'X-User-Id: cbb0a683-630f-4b86-8b45-91b90a6fce1c' http://localhost:9094/api/v1/clients/)" = 200 ]; do sleep 1; done
cd "$B" && make ENV_FILE_PATH=integration-test.env TEST_PATH=tests/integration/test_auth_login_and_password.py integration-test-run-specific
cd "$B" && make ENV_FILE_PATH=integration-test.env integration-test-down
```
Expected: health check `200`; FAIL — all 22 tests fail (`404` on `/api/v1/auth/...` and on `PUT /api/v1/users/{id}/password`; every account is made by a sign-up, so the self-access tests fail at their setup too), 0 passed.

Then remove the baseline worktree: `git -C "$G" worktree remove --force "$B"`.

- [ ] **Step 3: Run them against this branch**

```bash
cd "$W" && make ENV_FILE_PATH=integration-test.env integration-test-clean
cd "$W" && make ENV_FILE_PATH=integration-test.env integration-test-build
cd "$W" && make ENV_FILE_PATH=integration-test.env integration-test-up
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/
cd "$W" && docker exec -i datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db < tests/integration/fixtures/seed_clients.sql
until [ "$(curl -s -o /dev/null -w '%{http_code}' -H 'X-Api-Key: 5060b1a2-9aaf-48db-871a-0839007fd478' -H 'X-Api-Secret: integration-test-not-a-real-secret' -H 'X-User-Id: cbb0a683-630f-4b86-8b45-91b90a6fce1c' http://localhost:9094/api/v1/clients/)" = 200 ]; do sleep 1; done
cd "$W" && make ENV_FILE_PATH=integration-test.env TEST_PATH=tests/integration/test_auth_login_and_password.py integration-test-run-specific
```
Expected: health check `200`; the seeded policy loaded (Casbin's 5-second reload); PASS — `22 passed`, 0 failed, 0 skipped.

- [ ] **Step 4: Full cycle**

```bash
cd "$W" && make ENV_FILE_PATH=integration-test.env integration-test-full
```
While it runs, after `Integration test containers ready`: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/` → `200`.
Expected: `0 failed` in the pytest summary for `tests/integration/`, no `skipped` from `verify_services_running`, all four new files collected. Read the summary; never the exit code, never through a pipe. Early 401s right after the seed are Casbin's 5-second reload: read the log, then up, seed, wait for `/clients/` → 200, `make ENV_FILE_PATH=integration-test.env integration-test-run`.

- [ ] **Step 5: Commit**

```bash
ruff check tests/integration/test_auth_login_and_password.py
ruff format tests/integration/test_auth_login_and_password.py
git add tests/integration/test_auth_login_and_password.py
git commit -m "$(cat <<'EOF'
test: password sign-in, the lock, reset, self-access and password change end to end

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 16: Validation loop

**Files:** none changed unless a check fails.

**Interfaces:** Consumes everything above. Produces a branch that passes the loop CLAUDE.md requires.

- [ ] **Step 1: Unit tests**

Run: `pytest`
Expected: PASS, 0 failed — the Task 1 count plus every test this plan added.

- [ ] **Step 2: Integration tests, full cycle, verified**

Run: `make ENV_FILE_PATH=integration-test.env integration-test-full`

While it runs, once `Integration test containers ready` is printed:
`curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/`
Expected: `200`.

Expected in the output: the pytest summary for `tests/integration/` with `0 failed`; no test skipped by `verify_services_running`; `test_auth_sign_up.py`, `test_auth_email_verification.py`, `test_new_account_notification.py` and `test_auth_login_and_password.py` among the collected files; every pre-existing file still green (in particular `test_user_api.py`, `test_email_delivery.py`, `test_sharing_api.py`, `test_request_body_logging.py`).

`integration-test-full` hides failures behind `|| echo "may have failed"` and waits with `timeout`, absent on macOS; read the summary yourself and do not pipe `make` into `tail`/`grep`. If the container never became healthy, it is a migration failing at startup: `docker logs datamap_gatekeeper_test_integration`. If the first files show 401s, it is Casbin's 5-second reload after the seed: bring the stack up, seed, poll `/api/v1/clients/` until 200, then `make ENV_FILE_PATH=integration-test.env integration-test-run`.

- [ ] **Step 3: Lint**

Run: `ruff check`
Expected: `All checks passed!`

- [ ] **Step 4: Auto-fix**

Run: `ruff check --fix`
Expected: `All checks passed!` with nothing fixed. If it fixed anything, rerun Step 1.

- [ ] **Step 5: Format**

Run: `ruff format`
Expected: `N files left unchanged`. If it reformatted files, rerun `ruff check` and Step 1.

- [ ] **Step 6: Commit any formatting change**

```bash
git status --short
git add -u
git commit -m "$(cat <<'EOF'
style: ruff format

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```
Skip when `git status --short` is empty. Never `git add` `docs/rfcs/007-notebooks.md` or the RFC/contract files (they are not in W, and must stay that way).

- [ ] **Step 7: Before the PR**

Confirm the owner step of Task 2 is done (both peppers and `ADMIN_NOTIFICATION_EMAILS` in `secrets/production/gatekeeper.env`); without it the deploy on merge cannot start the API. State in the PR description: the `issued_at` and `confirmed_at` columns, the outbox-based hourly cap, resend on every unconfirmed challenge, the 90-second resend cooldown, self-access on `GET /users/{id}` and `PUT /users/{id}/password` (the contract said Casbin for the latter), the per-admin `dedup_key`, and that the integration admin address is a placeholder so its messages are recorded as `skipped`.

---

## Self-review against the spec

| RFC 008 / contract requirement | Where |
|---|---|
| `users.password_hash String(128)` null, `email_verified_at`, `failed_login_count` default 0, `locked_until` | Task 5 (model, migration, tests); Task 13 Step 4 (migration down/up against PostgreSQL) |
| Password is not a `providers` row; "has a password" is `password_hash is not null` | Task 9 (`has_password = password_hash is not None`) |
| `auth_challenges` with every RFC column, `secret_hash` unique, FK `ON DELETE CASCADE`, payload JSONB | Task 5 |
| Codes 6 digits `000000`–`999999` from `secrets.randbelow` | Task 4 |
| Codes stored as `HMAC-SHA256(AUTH_CHALLENGE_PEPPER, challenge_id ‖ code)` | Task 4; Task 10 (`_issue_code`, `_redeem`) |
| Reset tokens `new_token()` / `hash_token()` | Task 11 (`request_password_reset`, `confirm_password_reset`) |
| Codes 15 min, 5 attempts; reset 1 h; single use; new same kind+email consumes previous | Task 6 (`replace`, `record_failed_attempt`, `consume`); Task 10/11; Task 13 (`TestCodes`), Task 15 (`test_a_new_link_retires_the_previous_one`) |
| Existing users start with `email_verified_at = null` | Task 5 (nullable, no backfill); Task 13 (`before` profile of a plain user) |
| bcrypt cost 10 over base64 HMAC-SHA256 pepper; 44-byte input | Task 3 |
| Hash off the event loop (`run_in_threadpool`) | Task 12 (`def` routes; `TestTheRoutesStayOffTheEventLoop`) |
| Password policy 10–128, no composition rules | Task 3; Task 10 (`invalid_password`); Task 13/15 |
| All nine endpoints, bodies, statuses | Task 12 (routes + unit tests); Tasks 13–15 |
| Identical responses for existing and unknown emails | Task 13, 14, 15 (`test_a_known_and_an_unknown_email_get_the_same_answer` ×3) |
| `400 code_invalid / code_expired / code_attempts_exceeded`; last two consume | Task 10; Task 13 `TestCodes` |
| `404 challenge_not_found` (incl. non-UUID id) | Task 12; Task 13 |
| Sign-up: new email creates user with hash and `email_verified_at = now()` | Task 10; Task 13 |
| Sign-up: existing email sets hash and confirms | Task 10; Task 13 |
| Email verification table, all five rows incl. `409 email_belongs_to_another_account` | Task 10 `TestConfirmEmailVerification`; Task 14 `TestEmailVerificationTable` |
| Login `401 invalid_credentials` for unknown, wrong, no password, unconfirmed, disabled | Task 11 `TestLogin`; Task 15 `test_every_failure_is_the_same_401` |
| Dummy bcrypt for unknown email | Task 3 (`burn`); Task 11 (`test_an_unknown_email_still_runs_bcrypt`) |
| 10 failures → `locked_until = now + 15 min`; lock answers 401; success or reset clears both | Task 6 (`record_failed_login`); Task 11; Task 15 `TestLock` |
| Reset link `{PUBLIC_BASE_URL}/account/reset-password/{token}` only for an existing confirmed account | Task 11; Task 15 `TestPasswordReset` |
| Reset confirm sets the password, clears the lock, consumes every open `password_reset` of the user | Task 6 (`set_password`, `consume_open_for_user`); Task 11; Task 15 (`test_a_reset_lifts_the_lock`, `test_a_link_works_once`) |
| Resend cooldown, else `429 resend_too_soon` — 90 s after the last send per the lead's correction (RFC said 60 s) | Task 7 (handler); Task 10 (`RESEND_COOLDOWN`, 89 s refused / 90 s allowed); Task 13 `TestResend` |
| Lead decision 3: resend issues a new code on any challenge not successfully confirmed (expired, out of attempts, replaced); a confirmed one is `404`; `confirmed_at` column | Task 5 (column, migration); Task 6 (`confirm`, `reissue`); Task 10 (`_can_resend`, `TestResend`); Task 13 (`test_an_expired_challenge_can_be_resent`, `test_a_challenge_out_of_attempts_can_be_resent`, `test_a_confirmed_challenge_cannot_be_resent`) |
| ≤ 5 challenges per email per hour; past it 202, no email, code never valid | Task 6 (`count_recent`); Task 10; Task 13 `TestHourlyCap` |
| Lead decision 2 (corrected): auth emails use the normal outbox, dispatched every minute; integration tests trigger the dispatch | Global Constraints (Delivery); Task 13 helpers (`delivered` calls `POST /internal/notifications/dispatch`) |
| `PUT /users/{id}/password` 204 / 401, authn + authz | Task 12; Task 15 `TestChangePassword` |
| Lead decision 1: self-access without a role on `GET /users/{id}` and `PUT /users/{id}/password`; Casbin for anyone else | Task 9 (`authorize_self_or_policy`, unit tests); Task 12 (password route); Task 15 `TestSelfAccess` (reads self 200, other 401) and `TestChangePassword` (own 204, other's 401) |
| User responses gain `email_verified_at` and `has_password` | Task 9 (service, response, route test); Tasks 13–14 (real responses) |
| Four templates, English, code/token in `secret_fields` | Task 8; Task 10/11 (`secret_fields`); Task 13 (code redacted from the access log) |
| `new_account_pending` from `UserService.create` for every path, to `ADMIN_NOTIFICATION_EMAILS`, dedup by user | Task 9; Task 14 `test_new_account_notification.py` (API, password, ORCID) |
| None when the list is empty | Task 9 `test_nobody_is_told_when_the_list_is_empty` (unit; one running stack cannot hold two values of the setting) |
| `AUTH_PASSWORD_PEPPER`, `AUTH_CHALLENGE_PEPPER` ≥ 16 chars; `ADMIN_NOTIFICATION_EMAILS` comma-separated, empty disables | Task 2 |
| Settings in `integration-test.env` and the local template | Task 2 |
| Codes or tokens never in logs or the admin email view | Task 7 (`code` redaction); Task 8 (never in subjects); Task 10/11 (`secret_fields`); Task 13 `TestWhatReachesTheLog` |
| Unit: hashing round-trip and pepper dependence; code generation range and format | Task 3; Task 4 |
| Integration: every flow end to end against Mailpit | Tasks 13–15 |
| Validation loop | Task 16 |

Gaps found while writing and fixed in place:

- The contract's `{"detail": "<code>"}` for validation errors does not match the existing `BadRequestException` handler (`{"details", "errors"}`), so every auth 400 goes through `IllegalStateException`, whose handler already answers `400 {"detail": str(exc)}`. Missing or mistyped JSON fields still get FastAPI's 422.
- `new_account_pending` with `dedup_key = user_id` would drop every admin after the first (`email_messages.dedup_key` is unique), so the key carries a hash of the recipient.
- The resend cooldown needs to know when the current code was issued, which no RFC column records: `issued_at`.
- After `code_expired` the person is told to request a new code; with the challenge consumed, resend would have been a dead end. Per the lead's decision, resend reopens every challenge whose `confirmed_at` is null, and only a successful confirmation sets it.
- A sign-up account has no role, so Casbin alone would have refused it its own profile and its own password change; per the lead's decision, `authorize_self_or_policy` lets a caller reach their own `{id}` without one.
- A code sent by a dispatch that runs every minute could leave a person pressing Resend before the first code arrived; per the lead's correction the cooldown is 90 seconds rather than the RFC's 60.
- The access log writes request bodies; `code` was not a secret key, so it was added as an exact match.
- Changing a user's email through `PUT /users/{id}` would have kept the old address's confirmation; it now clears `email_verified_at`.
- A disabled account holding the email would have made email verification attach ORCID to an account that cannot sign in, or fail on the unique index: it answers `409 email_belongs_to_another_account`.
- 50 admin notifications queued by other test files' `POST /users` would have pushed `test_email_delivery.py`'s message past the 50-per-dispatch limit; the integration admin address uses the placeholder domain so they are recorded as `skipped`.
