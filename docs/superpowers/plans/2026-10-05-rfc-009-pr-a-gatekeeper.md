# RFC 009 PR A — Gatekeeper tenancies, requests, invitations and admin routes Implementation Plan

> **Superseded — historical.** This plan records how PR A was first built. Tenancy invitations have since moved from a dataset's share dialog to the workspace Members page (`/users/{id}/tenancies/{path}/…`), so the dataset-side invitation routes, the share lookup and `tenancy_invitations.dataset_id` described below no longer exist. The contract (`2026-10-05-rfc-009-contract.md`) and RFC 009 (`docs/rfcs/009-tenancies-and-admin.md`) are authoritative.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every account lands in `datamap/production/public` with the global `datasets_write` role, from its first sign-in and by every creation path; datasets start closed to tenancy members and are never member-editable in public; users ask for tenancies and owners invite colleagues from inside the app; DataMap admins decide through `/v1/admin/*`; every membership change is written to `tenancy_events`; five emails go through the outbox. Nothing in the webapp changes in this PR.

**Architecture:** One Alembic revision adds `tenancies.display_name`, the public tenancy, the backfilled memberships and `datasets_write` grants, the `members_can_edit = false` default and the three tables. Persistence lives in four repositories (`tenancy_event`, `tenancy_membership`, `tenancy_request`, `tenancy_invitation`) plus additions to `TenancyRepository` and `UserRepository`; every multi-row change (approval, acceptance, removal, invitation, request) runs in one session and writes its events in the same commit. Rules live in four services: `TenancyMembershipService` (summaries, the "open for members" rule, new-tenancy validation, the access-granted email), `TenancyRequestService` (user requests and the admin queue), `TenancyInvitationService` (dataset-side invitations, the share lookup, user-side accept/decline, admin withdraw) and `TenancyAdminService` (tenancy list, create, members, removal, user search). `TenancyNotifier` owns the five templates. Three routers: self routes under `/v1/users/{id}/…` guarded by a new `authorize_self`, dataset routes under `/v1/datasets/{id}/…` guarded by `authorize` then the service, admin routes under `/v1/admin/…` guarded by `authorize` (only `admin`'s `/*` matches). `UserService.create` adds public and `datasets_write`; `allows_member_edits` refuses public; `new_account_pending` and `POST/DELETE /users/{id}/tenancies` are removed. Admin dataset access is unchanged: no admin bypass anywhere.

**Tech Stack:** Python 3.10 (production `python:3.10.14-alpine`), FastAPI 0.111, Pydantic 2.7, SQLAlchemy 1.4.23, Alembic 1.11.2, dependency-injector, Casbin 1.23 (`regexMatch`, effect `allow && !deny`), Jinja2 3.1; pytest + `unittest.mock`; integration tests against Docker (PostgreSQL, MinIO, WireMock, Mailpit).

## Global Constraints

- Spec: `docs/rfcs/009-tenancies-and-admin.md`. Names, paths, bodies, statuses and `detail` codes come from `docs/superpowers/plans/2026-10-05-rfc-009-contract.md`, which wins over this plan. Do not edit either file.
- Work only in the worktree `/Users/caio.maia/workspace/datamap/gatekeeper/.claude/worktrees/rfc-009-gatekeeper` (called **W**), branch `feat/rfc-009-gatekeeper`, created in Task 1 from `docs/rfc-009-tenancies`. Every relative path and command is relative to W. Before every commit run `pwd` and `command git branch --show-current` and check they print W and `feat/rfc-009-gatekeeper`. Always `command git`, never bare `git`.
- Python: `/Users/caio.maia/workspace/datamap/gatekeeper/.venv/bin/python` (called **PY**). Unit tests: `$PY -m pytest <path> -q`. Never create another venv.
- Python 3.10 only: no `datetime.UTC`, `typing.Self`, `StrEnum`, `except*`. Enums are `class X(str, enum.Enum)`. Type hints everywhere.
- Comments: none narrating code; one line only where a reader would otherwise undo something on purpose.
- `DEFAULT_TENANCY = "datamap/production/public"`, `PRODUCTION_PREFIX = "datamap/production/"`, `LEGACY_PREFIX = "datamap/staging/"` live in `app/model/tenancy.py`, not settings. `DEFAULT_ROLE = "datasets_write"` lives in `app/model/user.py`.
- Migration: file `migrations/versions/2026_10_05_1200-c3d4e5f6a7b8_add_tenancy_requests_invitations_and_events.py`, `revision = "c3d4e5f6a7b8"`, `down_revision = "b1c2d3e4f5a6"`. Every step is idempotent (`IF NOT EXISTS`, `ON CONFLICT`, guarded `CREATE TYPE`). Downgrade drops tables, enums and `display_name` and restores the `true` server default; it leaves the public tenancy, memberships, granted roles and `members_can_edit` values.
- `display_name` in any response is the resolved name: the column, else the namespace title-cased (`derived_display_name`). Never `null`.
- Tenancy lists are ordered: public first, then everything else by `display_name` case-insensitively, then `datamap/staging/*` by path.
- Validation (trimmed): `tenancy_name` 1–128, `reason` 1–1000, `message` 0–1000 (empty → `null`), `display_name` 1–64 and unique among enabled production tenancies case-insensitively (resolved names), `namespace` `^[a-z0-9-]+$`, 2–63, not `public`.
- Errors use existing handlers and the body `{"detail": "<code>"}`: `IllegalStateException` → 400 (`invalid_request`, `tenancy_name_invalid`, `reason_invalid`, `namespace_invalid`, `display_name_invalid`, `message_invalid`, `public_members_cannot_edit`), `ForbiddenException` → 403 `forbidden`, `NotFoundException` → 404 (`request_not_found`, `invitation_not_found`, `tenancy_not_found`, `no_account`, `member_not_found`), `ConflictException` → 409 (`request_pending`, `request_not_pending`, `already_member`, `invitation_pending`, `tenancy_exists`, `display_name_taken`, `requester_email_unverified`, `public_tenancy_locked`, `legacy_tenancy_read_only`, `tenancy_disabled`), `TooManyRequestsException` → 429 `too_many_requests`, `UnauthorizedException` → 401. `BadRequestException` is never used by this PR (its body is not `{"detail"}`).
- Every new route answers `400 {"detail": "invalid_request"}` for a body, path or query it cannot parse (the quiet validation handler).
- Requests: one pending per user (service check + partial unique index), at most 3 created per user in 24 hours, withdrawn included.
- Emails: outbox only (`EmailService.enqueue`), `secret_fields` empty, base shell `base.html`/`base.txt` (see Task 9), admin messages one per address of `ADMIN_NOTIFICATION_EMAILS` with `dedup_key = {template}:{object id}:{hash_token(address.lower())[:16]}`, user messages with the dedup keys in the contract; CTA URLs absolute from `PUBLIC_BASE_URL`. Integration sets `ADMIN_NOTIFICATION_EMAILS=datamap-admins@fake.mail.com` (placeholder domain): admin messages are recorded with `status=skipped` and are asserted through `GET /admin/emails/`, never Mailpit.
- Logging only through `fields()` from `app/logging_config.py`; no whole payloads.
- No new Casbin `p` rows. No admin bypass of dataset access anywhere.
- Validation loop after the last task: `$PY -m pytest -q`, the integration suite (see *Running the integration suite*), `ruff check`, `ruff check --fix`, `ruff format`.

---

## Running the integration suite

Only one integration stack can run on this machine at a time: the container names (`datamap_*_test_integration`) are fixed in `docker-compose-integration-test.yaml`. Every integration step below starts with these commands, in zsh, from W:

```bash
cd /Users/caio.maia/workspace/datamap/gatekeeper/.claude/worktrees/rfc-009-gatekeeper
export ENV_FILE_PATH=integration-test.env
PY=/Users/caio.maia/workspace/datamap/gatekeeper/.venv/bin/python
dc() { docker compose -p rfc-009 -f docker-compose-integration-test.yaml "$@"; }
docker ps --filter name=_test_integration --format '{{.Label "com.docker.compose.project"}}' | sort -u
```

If the last command prints a project other than `rfc-009`, stop it first, without `-v` (its volumes belong to someone else): `docker compose -p <that-project> down`. Port 5433 must be free: `docker ps --format "{{.Names}}\t{{.Ports}}" | grep 5433` prints nothing.

The Docker VM clock drifts on macOS; resync it before every run (code expiry and `24 h` windows depend on it):

```bash
docker run --rm --privileged --pid=host alpine nsenter -t 1 -m -u -n -i date -u -s "@$(date -u +%s)"
```

Bring the stack up from a clean state (MinIO does not create its bucket directory):

```bash
dc down -v
mkdir -p "$(grep STORAGE_DOCKER_VOLUME integration-test.env | cut -d= -f2)_test_integration/datamap"
dc build gatekeeper_test_integration
dc up -d
for i in $(seq 1 60); do c=$(curl -s -m 3 -o /dev/null -w "%{http_code}" http://localhost:9094/api/v1/health-check/); echo "$i $c"; [ "$c" = 200 ] && break; sleep 2; done
```

Expected: the loop ends on a line `N 200`. If it never does, the application failed at startup, usually a migration: `docker logs datamap_gatekeeper_test_integration 2>&1 | tail -80` and read it before anything else. (`dc build gatekeeper_test_integration`: if the service has another name, `dc config --services` lists them; build the gatekeeper one.)

Seed, then wait for Casbin's 5-second policy reload — running straight after the seed gives a batch of unrelated 401s:

```bash
docker exec -i datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db < tests/integration/fixtures/seed_clients.sql
for i in $(seq 1 30); do c=$(curl -s -m 3 -o /dev/null -w '%{http_code}' -H 'X-Api-Key: 5060b1a2-9aaf-48db-871a-0839007fd478' -H 'X-Api-Secret: integration-test-not-a-real-secret' -H 'X-User-Id: cbb0a683-630f-4b86-8b45-91b90a6fce1c' http://localhost:9094/api/v1/clients/); echo "$i $c"; [ "$c" = 200 ] && break; sleep 1; done
```

Expected: ends on `N 200`.

Run tests (one file, or the whole suite in the final task only):

```bash
$PY -m pytest tests/integration/test_tenancy_requests_api.py -q -p no:cacheprovider
```

Read the pytest summary line yourself: it must show `0 failed` and no `skipped` (a skip from `verify_services_running` means the API was unreachable and nothing ran). Never pipe a test run or `make` into `tail`/`grep` and trust the exit code. Integration subagents run only the files of their task; the controller runs the whole suite in Task 18.

Bring it down at the end of the task, without `-v` if you want to keep the data, with `-v` otherwise: `dc down`.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `app/model/tenancy.py`, `app/model/tenancy_test.py` | modify / create | Constants, status/event enums, `TenancySummary`, path predicates, display-name resolution, ordering, matching key, validation helpers |
| `app/model/tenancy_access.py` | create | View dataclasses returned by the new services |
| `app/model/user.py` | modify | `DEFAULT_ROLE` |
| `app/model/dataset.py` | modify | `Dataset.members_can_edit` defaults to `False` |
| `app/model/sharing.py` | modify | `TenancyAccess` gains `is_default`, `is_legacy`, `datasets`; `ShareState` gains `tenancy_invitations`, `can_invite_to_tenancy` |
| `app/model/db/tenancy.py`, `app/model/db/tenancy_test.py` | modify / create | `display_name`; `TenancyRequest`, `TenancyInvitation`, `TenancyEvent` tables |
| `app/model/db/dataset.py` | modify | `members_can_edit` default `false` |
| `migrations/versions/2026_10_05_1200-c3d4e5f6a7b8_add_tenancy_requests_invitations_and_events.py` | create | The revision |
| `app/service/email_format.py` | modify | `tenancy_display_name` delegates to the model |
| `app/repository/tenancy_event.py` | create | `add_event`, `TenancyEventRepository` |
| `app/repository/tenancy_membership.py` | create | `insert_membership`, membership reads and add/remove |
| `app/repository/tenancy_request.py` | create | Request persistence, queue queries, atomic approve/decline |
| `app/repository/tenancy_invitation.py` | create | Invitation persistence, atomic accept/close |
| `app/repository/tenancy.py` | modify | `fetch_any`, `list_all`, `create_with_event`, member and dataset counts |
| `app/repository/user.py` | modify | `user_matches`, `fetch_any_by_id`, `search_admin` |
| `app/service/dataset_access.py`, `app/service/dataset_access_test.py` | modify | Public is never member-editable |
| `app/service/members_access.py`, `app/service/members_access_test.py` | modify | `400 public_members_cannot_edit` |
| `app/service/dataset.py`, `app/service/dataset_test.py` | modify | New datasets closed; moving into public stores `false` |
| `app/controller/v1/dataset/resource.py` | modify | Response defaults `False` |
| `app/service/user.py`, `app/service/user_test.py` | modify | Public + `datasets_write` + `member_added` at creation; `new_account_pending` and membership methods removed |
| `app/controller/v1/user/user.py`, `app/controller/v1/user/resource.py` | modify | Retired membership routes and `UserTenanciesRequest` removed |
| `app/service/email_template.py`, `app/service/email_template_test.py`, `app/resources/email_templates/*` | modify / create / delete | Five new templates, `new_account_pending` removed |
| `app/service/tenancy_notifier.py`, `app/service/tenancy_notifier_test.py` | create | The five emails; `admin_addresses` moved here |
| `app/service/tenancy.py`, `app/service/tenancy_test.py` | modify | Public lock on `PUT`/`DELETE /tenancies/{public}` |
| `app/service/tenancy_membership.py`, `app/service/tenancy_membership_test.py` | create | `TenancyMembershipService` |
| `app/service/tenancy_request.py`, `app/service/tenancy_request_test.py` | create | `TenancyRequestService` |
| `app/service/tenancy_invitation.py`, `app/service/tenancy_invitation_test.py` | create | `TenancyInvitationService` |
| `app/service/tenancy_admin.py`, `app/service/tenancy_admin_test.py` | create | `TenancyAdminService` |
| `app/service/share.py`, `app/service/share_test.py` | modify | Candidates off in public; share state additions (`share_preview_test.py` is unchanged and must still pass) |
| `app/controller/v1/dataset/share_resource.py` | modify | Share state response fields |
| `app/controller/interceptor/authorization.py`, `app/controller/interceptor/authorization_test.py` | modify | `authorize_self` |
| `app/controller/interceptor/exception_handler.py`, `app/controller/interceptor/exception_handler_test.py` | modify | Quiet `400 invalid_request` on the new routes |
| `app/controller/v1/tenancy/access_resource.py` | create | Pydantic request/response models of the new routes |
| `app/controller/v1/user/tenancy_access.py`, `app/controller/v1/user/tenancy_access_test.py` | create | Self routes |
| `app/controller/v1/dataset/tenancy_invitation.py`, `app/controller/v1/dataset/tenancy_invitation_test.py` | create | Lookup, invite, withdraw |
| `app/controller/v1/admin/tenancy.py`, `app/controller/v1/admin/tenancy_test.py` | create | Admin routes |
| `app/container.py`, `app/setup.py` | modify | Providers, wiring, routers |
| `tests/integration/fixtures/seed_clients.sql` | modify | The seeded user is in public |
| `tests/integration/fixtures/embargo.py` | modify | `create_user` no longer calls the retired route and keeps the roles it is given |
| `tests/integration/fixtures/tenancy.py` | create | Helpers for the new integration tests |
| `tests/integration/test_user_api.py`, `test_auth_login_and_password.py`, `test_dataset_members_access.py` | modify | New defaults |
| `tests/integration/test_new_account_notification.py` | delete | Template retired |
| `tests/integration/test_public_tenancy_api.py` | create | Creation paths, new-account flow, dataset defaults, public lock, candidates, lookup |
| `tests/integration/test_tenancy_requests_api.py` | create | Requests and the admin queue |
| `tests/integration/test_tenancy_invitations_api.py` | create | Invitations |
| `tests/integration/test_admin_tenancies_api.py` | create | Admin tenancies, members, users, `/admin` refusal, retired routes |
| `tests/integration/test_tenancy_migration.py` | create | Backfill and round trip |

---
### Task 1: Worktree, environment and baseline

**Files:** none changed.

**Interfaces:** Produces the worktree W on branch `feat/rfc-009-gatekeeper`, branched from `docs/rfc-009-tenancies` (which carries the RFC and the contract on top of `origin/main`).

- [ ] **Step 1: Create the worktree**

```bash
command git -C /Users/caio.maia/workspace/datamap/gatekeeper fetch origin
command git -C /Users/caio.maia/workspace/datamap/gatekeeper worktree add -b feat/rfc-009-gatekeeper .claude/worktrees/rfc-009-gatekeeper docs/rfc-009-tenancies
cd /Users/caio.maia/workspace/datamap/gatekeeper/.claude/worktrees/rfc-009-gatekeeper
pwd
command git branch --show-current
command git log --oneline -3
```

Expected: `pwd` prints W, the branch is `feat/rfc-009-gatekeeper`, and the log's top commit is `docs: RFC 009 contract between the plans` (or a later docs commit of `docs/rfc-009-tenancies`, e.g. this plan).

- [ ] **Step 2: Local environment file**

```bash
cp local.env.template local.env
command git status --short
```

Expected: `git status` prints nothing (`local.env` is ignored). Never commit `local.env`.

- [ ] **Step 3: Baseline unit tests**

```bash
PY=/Users/caio.maia/workspace/datamap/gatekeeper/.venv/bin/python
$PY --version
$PY -m pytest -q -p no:cacheprovider 2>&1 | tail -3
```

Expected: `Python 3.10.x`, and a summary line with `passed` and no `failed`. Write the number of passed tests down; every later full run must pass at least that many minus the tests this plan deletes. (Piping into `tail` is fine here: it is the summary you read, not an exit code.) If anything fails on the untouched branch, stop and report it — do not start Task 2 on a red baseline.

No commit.

---

### Task 2: Tenancy model — constants, enums, display names, matching, validation

**Files:**
- Modify: `app/model/tenancy.py`
- Modify: `app/model/user.py`
- Modify: `app/service/email_format.py`
- Create: `app/model/tenancy_access.py`
- Test: `app/model/tenancy_test.py`

**Interfaces:**
- Produces (`app/model/tenancy.py`): `DEFAULT_TENANCY`, `PRODUCTION_PREFIX`, `LEGACY_PREFIX`, `NAMESPACE_MIN_LENGTH = 2`, `NAMESPACE_MAX_LENGTH = 63`, `DISPLAY_NAME_MAX_LENGTH = 64`, `TENANCY_NAME_MAX_LENGTH = 128`, `REASON_MAX_LENGTH = 1000`, `MESSAGE_MAX_LENGTH = 1000`; `Tenancy` (gains `display_name`); `TenancySummary(path, display_name, is_default, is_legacy)`; `TenancyRequestStatus`, `TenancyInvitationStatus`, `TenancyEventType`; `is_default(path) -> bool`, `is_legacy(path) -> bool`, `is_production(path) -> bool`, `namespace_of(path) -> str`, `derived_display_name(path) -> str`, `display_name_of(path, display_name) -> str`, `summary_of(path, display_name) -> TenancySummary`, `tenancy_order(path, display_name) -> tuple[int, str]`, `match_key(value) -> str`, `namespace_is_valid(namespace) -> bool`, `trimmed_within(value, minimum, maximum) -> str | None`.
- Produces (`app/model/user.py`): `DEFAULT_ROLE = "datasets_write"`.
- Produces (`app/model/tenancy_access.py`): the view dataclasses listed in the code below, used by Tasks 10–13.

- [ ] **Step 1: Write the failing test**

Create `app/model/tenancy_test.py`:

```python
import unittest

from app.model.tenancy import (
    DEFAULT_TENANCY,
    TenancyEventType,
    TenancyInvitationStatus,
    TenancyRequestStatus,
    derived_display_name,
    display_name_of,
    is_default,
    is_legacy,
    is_production,
    match_key,
    namespace_is_valid,
    namespace_of,
    summary_of,
    tenancy_order,
    trimmed_within,
)
from app.model.user import DEFAULT_ROLE
from app.service.email_format import tenancy_display_name


class TestPaths(unittest.TestCase):
    def test_the_default_tenancy_is_public_in_production(self):
        self.assertEqual(DEFAULT_TENANCY, "datamap/production/public")
        self.assertTrue(is_default(DEFAULT_TENANCY))
        self.assertFalse(is_default("datamap/production/atto"))

    def test_staging_is_legacy_and_not_production(self):
        self.assertTrue(is_legacy("datamap/staging/data-amazon"))
        self.assertFalse(is_production("datamap/staging/data-amazon"))
        self.assertTrue(is_production("datamap/production/data-amazon"))
        self.assertFalse(is_legacy("datamap/production/data-amazon"))

    def test_the_namespace_is_the_last_segment(self):
        self.assertEqual(namespace_of("datamap/production/cerrado-flux"), "cerrado-flux")


class TestDisplayNames(unittest.TestCase):
    def test_the_column_wins(self):
        self.assertEqual(display_name_of("datamap/production/atto", "ATTO"), "ATTO")

    def test_without_the_column_the_namespace_is_title_cased(self):
        self.assertEqual(
            display_name_of("datamap/production/lba-legacy", None), "Lba Legacy"
        )
        self.assertEqual(derived_display_name("datamap/staging/data_amazon"), "Data Amazon")

    def test_an_empty_column_falls_back_too(self):
        self.assertEqual(display_name_of("datamap/production/atto", ""), "Atto")

    def test_the_email_helper_uses_the_same_rule(self):
        self.assertEqual(tenancy_display_name("datamap/production/data-amazon"), "Data Amazon")
        self.assertEqual(tenancy_display_name(None), "the workspace")

    def test_a_summary_flags_public_and_legacy(self):
        self.assertEqual(
            summary_of(DEFAULT_TENANCY, "Public"),
            summary_of(DEFAULT_TENANCY, "Public"),
        )
        public = summary_of(DEFAULT_TENANCY, "Public")
        legacy = summary_of("datamap/staging/data-amazon", None)
        self.assertTrue(public.is_default)
        self.assertFalse(public.is_legacy)
        self.assertTrue(legacy.is_legacy)
        self.assertEqual(legacy.display_name, "Data Amazon")


class TestOrder(unittest.TestCase):
    def test_public_then_production_by_name_then_legacy_by_path(self):
        rows = [
            ("datamap/staging/b", "B"),
            ("datamap/production/zeta", "zeta"),
            (DEFAULT_TENANCY, "Public"),
            ("datamap/staging/a", "Z"),
            ("datamap/production/alpha", "Alpha"),
        ]

        ordered = [path for path, name in sorted(rows, key=lambda r: tenancy_order(*r))]

        self.assertEqual(
            ordered,
            [
                DEFAULT_TENANCY,
                "datamap/production/alpha",
                "datamap/production/zeta",
                "datamap/staging/a",
                "datamap/staging/b",
            ],
        )


class TestMatching(unittest.TestCase):
    def test_case_and_spaces_versus_hyphens_do_not_matter(self):
        self.assertEqual(match_key("Cerrado Flux"), match_key("cerrado-flux"))
        self.assertEqual(match_key("  LBA   legacy "), match_key("lba-legacy"))

    def test_different_names_do_not_match(self):
        self.assertNotEqual(match_key("ATTO"), match_key("ATTO tower"))


class TestValidation(unittest.TestCase):
    def test_a_namespace_is_lower_case_digits_and_hyphens(self):
        for valid in ("atto", "lba-legacy", "a1", "x" * 63):
            with self.subTest(valid=valid):
                self.assertTrue(namespace_is_valid(valid))
        for invalid in ("a", "x" * 64, "Atto", "lba legacy", "lba_legacy", "public", ""):
            with self.subTest(invalid=invalid):
                self.assertFalse(namespace_is_valid(invalid))

    def test_trimmed_within_trims_and_checks_the_length(self):
        self.assertEqual(trimmed_within("  ATTO  ", 1, 128), "ATTO")
        self.assertIsNone(trimmed_within("   ", 1, 128))
        self.assertIsNone(trimmed_within(None, 1, 128))
        self.assertIsNone(trimmed_within("x" * 129, 1, 128))
        self.assertEqual(trimmed_within("", 0, 1000), "")


class TestEnums(unittest.TestCase):
    def test_the_values_the_rfc_names(self):
        self.assertEqual(
            [s.value for s in TenancyRequestStatus],
            ["pending", "approved", "declined", "withdrawn"],
        )
        self.assertEqual(
            [s.value for s in TenancyInvitationStatus],
            ["pending", "accepted", "declined", "withdrawn", "revoked"],
        )
        self.assertEqual(
            [s.value for s in TenancyEventType],
            [
                "tenancy_created",
                "member_added",
                "member_removed",
                "request_created",
                "request_approved",
                "request_declined",
                "request_withdrawn",
                "invitation_created",
                "invitation_accepted",
                "invitation_declined",
                "invitation_withdrawn",
            ],
        )

    def test_every_new_account_gets_datasets_write(self):
        self.assertEqual(DEFAULT_ROLE, "datasets_write")
```

- [ ] **Step 2: Run it and see it fail**

```bash
$PY -m pytest app/model/tenancy_test.py -q -p no:cacheprovider
```

Expected: collection error `ImportError: cannot import name 'DEFAULT_TENANCY' from 'app.model.tenancy'`.

- [ ] **Step 3: Implement**

Replace the whole content of `app/model/tenancy.py` with:

```python
import enum
import re
from dataclasses import dataclass
from datetime import datetime

DEFAULT_TENANCY = "datamap/production/public"
PRODUCTION_PREFIX = "datamap/production/"
LEGACY_PREFIX = "datamap/staging/"
RESERVED_NAMESPACE = "public"
NAMESPACE_PATTERN = re.compile(r"^[a-z0-9-]+$")
NAMESPACE_MIN_LENGTH = 2
NAMESPACE_MAX_LENGTH = 63
DISPLAY_NAME_MAX_LENGTH = 64
TENANCY_NAME_MAX_LENGTH = 128
REASON_MAX_LENGTH = 1000
MESSAGE_MAX_LENGTH = 1000


@dataclass
class Tenancy:
    name: str
    is_enabled: bool = True
    created_at: datetime = None
    updated_at: datetime = None
    display_name: str | None = None


@dataclass
class TenancySummary:
    path: str
    display_name: str
    is_default: bool
    is_legacy: bool


class TenancyRequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


class TenancyInvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"
    REVOKED = "revoked"


class TenancyEventType(str, enum.Enum):
    TENANCY_CREATED = "tenancy_created"
    MEMBER_ADDED = "member_added"
    MEMBER_REMOVED = "member_removed"
    REQUEST_CREATED = "request_created"
    REQUEST_APPROVED = "request_approved"
    REQUEST_DECLINED = "request_declined"
    REQUEST_WITHDRAWN = "request_withdrawn"
    INVITATION_CREATED = "invitation_created"
    INVITATION_ACCEPTED = "invitation_accepted"
    INVITATION_DECLINED = "invitation_declined"
    INVITATION_WITHDRAWN = "invitation_withdrawn"


def is_default(path: str | None) -> bool:
    return path == DEFAULT_TENANCY


def is_legacy(path: str | None) -> bool:
    return bool(path) and path.startswith(LEGACY_PREFIX)


def is_production(path: str | None) -> bool:
    return bool(path) and path.startswith(PRODUCTION_PREFIX)


def namespace_of(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1]


def derived_display_name(path: str) -> str:
    return namespace_of(path).replace("-", " ").replace("_", " ").title()


def display_name_of(path: str, display_name: str | None) -> str:
    return display_name or derived_display_name(path)


def summary_of(path: str, display_name: str | None) -> TenancySummary:
    return TenancySummary(
        path=path,
        display_name=display_name_of(path, display_name),
        is_default=is_default(path),
        is_legacy=is_legacy(path),
    )


def tenancy_order(path: str, display_name: str) -> tuple[int, str]:
    if is_default(path):
        return (0, "")
    if is_legacy(path):
        return (2, path)
    return (1, display_name.casefold())


def match_key(value: str) -> str:
    return re.sub(r"[\s-]+", "-", (value or "").strip().casefold()).strip("-")


def namespace_is_valid(namespace: str) -> bool:
    return (
        NAMESPACE_MIN_LENGTH <= len(namespace) <= NAMESPACE_MAX_LENGTH
        and NAMESPACE_PATTERN.match(namespace) is not None
        and namespace != RESERVED_NAMESPACE
    )


def trimmed_within(value: str | None, minimum: int, maximum: int) -> str | None:
    text = (value or "").strip()
    return text if minimum <= len(text) <= maximum else None
```

In `app/model/user.py`, replace

```python
from dataclasses import dataclass
from datetime import datetime
```

with

```python
from dataclasses import dataclass
from datetime import datetime

DEFAULT_ROLE = "datasets_write"
```

In `app/service/email_format.py`, replace

```python
from datetime import date, datetime
```

with

```python
from datetime import date, datetime

from app.model.tenancy import derived_display_name
```

and replace

```python
    if not tenancy:
        return "the workspace"
    return (
        tenancy.rstrip("/")
        .rsplit("/", 1)[-1]
        .replace("-", " ")
        .replace("_", " ")
        .title()
    )
```

with

```python
    if not tenancy:
        return "the workspace"
    return derived_display_name(tenancy)
```

Create `app/model/tenancy_access.py`:

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from app.model.tenancy import TenancySummary

T = TypeVar("T")


@dataclass
class UserRef:
    id: UUID
    name: str


@dataclass
class UserBrief:
    id: UUID
    name: str
    email: str | None = None


@dataclass
class DatasetRef:
    id: UUID
    name: str


@dataclass
class Page(Generic[T]):
    items: list[T]
    total_count: int
    limit: int
    offset: int


@dataclass
class NewTenancy:
    display_name: str
    namespace: str


@dataclass
class TenancyRequestView:
    id: UUID
    requested_name: str
    reason: str
    status: str
    tenancy: TenancySummary | None
    created_tenancy: bool
    decision_message: str | None
    created_at: datetime
    decided_at: datetime | None


@dataclass
class Requester:
    id: UUID
    name: str
    email: str | None
    email_verified: bool
    orcid: str | None


@dataclass
class AdminTenancyRequestView:
    id: UUID
    requester: Requester
    requested_name: str
    reason: str
    status: str
    kind: str
    suggested_tenancy: TenancySummary | None
    created_at: datetime
    tenancy: TenancySummary | None
    created_tenancy: bool
    decision_message: str | None
    decided_by: UserRef | None
    decided_at: datetime | None


@dataclass
class AdminTenancyRequestDetailView(AdminTenancyRequestView):
    requester_tenancies: list[TenancySummary] = field(default_factory=list)
    suggested_tenancy_members: int | None = None


@dataclass
class RequestCounts:
    open: int
    join: int
    new: int
    closed: int


@dataclass
class TenancyInvitationView:
    id: UUID
    tenancy: TenancySummary
    invited_by: UserRef | None
    dataset: DatasetRef | None
    datasets: int
    created_at: datetime


@dataclass
class DatasetTenancyInvitationView:
    id: UUID
    user: UserBrief
    invited_by: UserBrief | None
    created_at: datetime
    can_withdraw: bool


@dataclass
class ShareLookupView:
    user: UserBrief
    tenancy_member: bool
    invitation_pending: bool
    can_invite: bool


@dataclass
class AdminTenancyView:
    path: str
    display_name: str
    members: int
    datasets: int
    is_default: bool
    is_legacy: bool
    is_enabled: bool


@dataclass
class TenancyMemberView:
    id: UUID
    name: str
    email: str | None
    since: datetime
    invited_by: UserRef | None


@dataclass
class AdminTenancyInvitationView:
    id: UUID
    user: UserBrief
    invited_by: UserRef | None
    dataset: DatasetRef | None
    created_at: datetime


@dataclass
class TenancyMembersView:
    members: Page[TenancyMemberView]
    invitations: list[AdminTenancyInvitationView]


@dataclass
class RemovalImpactView:
    member_since: datetime
    datasets_in_tenancy: int
    shared_with_user: int
    owned_by_user: int
```

- [ ] **Step 4: Run it and see it pass**

```bash
$PY -m pytest app/model/tenancy_test.py app/service/email_format_test.py app/service/tenancy_test.py -q -p no:cacheprovider
```

Expected: all pass (the existing `email_format_test.py` still passes: the derived name is unchanged).

- [ ] **Step 5: Commit**

```bash
pwd && command git branch --show-current
command git add app/model/tenancy.py app/model/tenancy_test.py app/model/tenancy_access.py app/model/user.py app/service/email_format.py
command git commit -m "feat: tenancy constants, display names and request matching (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Schema — `display_name`, requests, invitations, events, the migration

**Files:**
- Modify: `app/model/db/tenancy.py`
- Modify: `app/model/db/dataset.py`
- Modify: `app/model/dataset.py`
- Modify: `app/controller/v1/dataset/resource.py`
- Create: `migrations/versions/2026_10_05_1200-c3d4e5f6a7b8_add_tenancy_requests_invitations_and_events.py`
- Modify: `tests/integration/fixtures/seed_clients.sql`
- Test: `app/model/db/tenancy_test.py`

**Interfaces:**
- Consumes: the enums of Task 2.
- Produces: SQLAlchemy models `Tenancy.display_name`, `TenancyRequest`, `TenancyInvitation`, `TenancyEvent` (in `app/model/db/tenancy.py`); `datasets.members_can_edit` `default=False, server_default=false()`; revision `c3d4e5f6a7b8`.

- [ ] **Step 1: Write the failing test**

Create `app/model/db/tenancy_test.py`:

```python
import unittest

from app.model.db.dataset import Dataset
from app.model.db.tenancy import (
    Tenancy,
    TenancyEvent,
    TenancyInvitation,
    TenancyRequest,
)
from app.model.dataset import Dataset as DatasetModel


def _indexes(table) -> dict:
    return {index.name: index for index in table.indexes}


class TestTenancyTable(unittest.TestCase):
    def test_a_display_name_is_optional_and_short(self):
        column = Tenancy.__table__.c.display_name
        self.assertTrue(column.nullable)
        self.assertEqual(column.type.length, 64)


class TestRequestTable(unittest.TestCase):
    def test_it_has_the_columns_the_rfc_names(self):
        self.assertEqual(
            set(TenancyRequest.__table__.columns.keys()),
            {
                "id",
                "user_id",
                "requested_name",
                "reason",
                "status",
                "tenancy",
                "created_tenancy",
                "decision_message",
                "decided_by",
                "decided_at",
                "created_at",
                "updated_at",
            },
        )

    def test_one_pending_request_per_user_is_an_index(self):
        index = _indexes(TenancyRequest.__table__)["uq_tenancy_requests_pending"]
        self.assertTrue(index.unique)
        self.assertEqual([c.name for c in index.columns], ["user_id"])
        self.assertEqual(
            str(index.dialect_options["postgresql"]["where"]), "status = 'pending'"
        )
        self.assertIn("ix_tenancy_requests_status_created", _indexes(TenancyRequest.__table__))

    def test_a_request_goes_away_with_its_user(self):
        (foreign_key,) = TenancyRequest.__table__.c.user_id.foreign_keys
        self.assertEqual(foreign_key.ondelete, "CASCADE")
        (decider,) = TenancyRequest.__table__.c.decided_by.foreign_keys
        self.assertEqual(decider.ondelete, "SET NULL")


class TestInvitationTable(unittest.TestCase):
    def test_it_has_the_columns_the_rfc_names(self):
        self.assertEqual(
            set(TenancyInvitation.__table__.columns.keys()),
            {
                "id",
                "tenancy",
                "user_id",
                "invited_by",
                "dataset_id",
                "status",
                "closed_by",
                "closed_at",
                "created_at",
                "updated_at",
            },
        )

    def test_one_pending_invitation_per_user_and_tenancy(self):
        index = _indexes(TenancyInvitation.__table__)["uq_tenancy_invitations_pending"]
        self.assertTrue(index.unique)
        self.assertEqual([c.name for c in index.columns], ["tenancy", "user_id"])
        self.assertIn(
            "ix_tenancy_invitations_user_status", _indexes(TenancyInvitation.__table__)
        )

    def test_the_dataset_it_came_from_may_disappear(self):
        (foreign_key,) = TenancyInvitation.__table__.c.dataset_id.foreign_keys
        self.assertEqual(foreign_key.ondelete, "SET NULL")


class TestEventTable(unittest.TestCase):
    def test_user_ids_and_tenancy_are_not_foreign_keys(self):
        table = TenancyEvent.__table__
        for name in ("tenancy", "user_id", "actor_id", "request_id", "invitation_id"):
            with self.subTest(column=name):
                self.assertEqual(table.c[name].foreign_keys, set())
                self.assertTrue(table.c[name].nullable)
        self.assertEqual(
            set(_indexes(table)), {"ix_tenancy_events_created", "ix_tenancy_events_user"}
        )


class TestDatasetDefault(unittest.TestCase):
    def test_new_datasets_are_closed_to_members(self):
        column = Dataset.__table__.c.members_can_edit
        self.assertFalse(column.default.arg)
        self.assertEqual(str(column.server_default.arg), "false")
        self.assertFalse(DatasetModel(name="d", data={}).members_can_edit)
```

- [ ] **Step 2: Run it and see it fail**

```bash
$PY -m pytest app/model/db/tenancy_test.py -q -p no:cacheprovider
```

Expected: `ImportError: cannot import name 'TenancyEvent' from 'app.model.db.tenancy'`.

- [ ] **Step 3: Implement the models**

Replace the whole content of `app/model/db/tenancy.py` with:

```python
import sqlalchemy
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base
from app.model.tenancy import (
    TenancyEventType,
    TenancyInvitationStatus,
    TenancyRequestStatus,
)


def _values(enum_class) -> list[str]:
    return [member.value for member in enum_class]


class Tenancy(Base):
    __tablename__ = "tenancies"
    name = Column(String(256), primary_key=True)
    display_name = Column(String(64), nullable=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TenancyRequest(Base):
    __tablename__ = "tenancy_requests"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    requested_name = Column(String(128), nullable=False)
    reason = Column(String(1000), nullable=False)
    status = Column(
        Enum(
            TenancyRequestStatus,
            name="tenancy_request_status",
            values_callable=_values,
        ),
        nullable=False,
        default=TenancyRequestStatus.PENDING,
        server_default="pending",
    )
    tenancy = Column(String(256), ForeignKey("tenancies.name"), nullable=True)
    created_tenancy = Column(
        Boolean, nullable=False, default=False, server_default=sqlalchemy.false()
    )
    decision_message = Column(String(1000), nullable=True)
    decided_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index(
            "uq_tenancy_requests_pending",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_tenancy_requests_status_created", "status", "created_at"),
    )


class TenancyInvitation(Base):
    __tablename__ = "tenancy_invitations"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    tenancy = Column(String(256), ForeignKey("tenancies.name"), nullable=False)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    invited_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    dataset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
    )
    status = Column(
        Enum(
            TenancyInvitationStatus,
            name="tenancy_invitation_status",
            values_callable=_values,
        ),
        nullable=False,
        default=TenancyInvitationStatus.PENDING,
        server_default="pending",
    )
    closed_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index(
            "uq_tenancy_invitations_pending",
            "tenancy",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_tenancy_invitations_user_status", "user_id", "status"),
    )


class TenancyEvent(Base):
    __tablename__ = "tenancy_events"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    tenancy = Column(String(256), nullable=True)
    event_type = Column(
        Enum(TenancyEventType, name="tenancy_event_type", values_callable=_values),
        nullable=False,
    )
    user_id = Column(UUID(as_uuid=True), nullable=True)
    actor_id = Column(UUID(as_uuid=True), nullable=True)
    request_id = Column(UUID(as_uuid=True), nullable=True)
    invitation_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_tenancy_events_created", "created_at"),
        Index("ix_tenancy_events_user", "user_id", "created_at"),
    )
```

`tenancy_events.tenancy` is nullable, unlike the RFC's sketch: `request_created`, `request_declined` and `request_withdrawn` have no tenancy to name (the request's text is not a tenancy). This is reported as a deviation.

In `app/model/db/dataset.py`, replace

```python
    members_can_edit = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sqlalchemy.true(),
    )
```

with

```python
    members_can_edit = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sqlalchemy.false(),
    )
```

In `app/model/dataset.py`, replace

```python
    owner_name: str | None = None
    members_can_edit: bool = True
```

with

```python
    owner_name: str | None = None
    members_can_edit: bool = False
```

In `app/controller/v1/dataset/resource.py`, replace both occurrences (use `replace_all`) of

```python
    members_can_edit: bool = Field(
        True, title="Members of the tenancy may edit when no embargo is active"
    )
```

with

```python
    members_can_edit: bool = Field(
        False, title="Members of the tenancy may edit when no embargo is active"
    )
```

- [ ] **Step 4: Write the migration**

Create `migrations/versions/2026_10_05_1200-c3d4e5f6a7b8_add_tenancy_requests_invitations_and_events.py`:

```python
"""Public tenancy for everyone, datasets_write for accounts without a dataset role,
datasets closed to members by default, tenancy requests, invitations and events

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-10-05 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PUBLIC = "datamap/production/public"

ENUMS = {
    "tenancy_request_status": ("pending", "approved", "declined", "withdrawn"),
    "tenancy_invitation_status": (
        "pending",
        "accepted",
        "declined",
        "withdrawn",
        "revoked",
    ),
    "tenancy_event_type": (
        "tenancy_created",
        "member_added",
        "member_removed",
        "request_created",
        "request_approved",
        "request_declined",
        "request_withdrawn",
        "invitation_created",
        "invitation_accepted",
        "invitation_declined",
        "invitation_withdrawn",
    ),
}


def _create_enum(name: str, values: tuple[str, ...]) -> None:
    labels = ", ".join(f"'{value}'" for value in values)
    op.execute(
        f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({labels}); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )


def upgrade() -> None:
    op.execute("ALTER TABLE tenancies ADD COLUMN IF NOT EXISTS display_name VARCHAR(64)")

    op.execute(
        f"""
        INSERT INTO tenancies (name, display_name, is_enabled, created_at, updated_at)
        VALUES ('{PUBLIC}', 'Public', true, now(), now())
        ON CONFLICT (name) DO UPDATE
        SET is_enabled = true,
            display_name = COALESCE(tenancies.display_name, 'Public')
        """
    )

    op.execute(
        f"""
        INSERT INTO users_tenancies (user_id, tenancy)
        SELECT id, '{PUBLIC}' FROM users
        ON CONFLICT DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO casbin_rule (ptype, v0, v1)
        SELECT 'g', CAST(u.id AS VARCHAR), 'datasets_write'
        FROM users u
        WHERE NOT EXISTS (
            SELECT 1 FROM casbin_rule c
            WHERE c.ptype = 'g'
              AND c.v0 = CAST(u.id AS VARCHAR)
              AND c.v1 IN ('admin', 'datasets_read', 'datasets_write', 'datasets_admin')
        )
        """
    )

    op.execute("ALTER TABLE datasets ALTER COLUMN members_can_edit SET DEFAULT false")
    op.execute(
        f"UPDATE datasets SET members_can_edit = false "
        f"WHERE tenancy = '{PUBLIC}' AND members_can_edit"
    )

    for name, values in ENUMS.items():
        _create_enum(name, values)

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenancy_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            requested_name VARCHAR(128) NOT NULL,
            reason VARCHAR(1000) NOT NULL,
            status tenancy_request_status NOT NULL DEFAULT 'pending',
            tenancy VARCHAR(256) REFERENCES tenancies (name),
            created_tenancy BOOLEAN NOT NULL DEFAULT false,
            decision_message VARCHAR(1000),
            decided_by UUID REFERENCES users (id) ON DELETE SET NULL,
            decided_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tenancy_requests_pending "
        "ON tenancy_requests (user_id) WHERE status = 'pending'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenancy_requests_status_created "
        "ON tenancy_requests (status, created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenancy_invitations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenancy VARCHAR(256) NOT NULL REFERENCES tenancies (name),
            user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            invited_by UUID REFERENCES users (id) ON DELETE SET NULL,
            dataset_id UUID REFERENCES datasets (id) ON DELETE SET NULL,
            status tenancy_invitation_status NOT NULL DEFAULT 'pending',
            closed_by UUID REFERENCES users (id) ON DELETE SET NULL,
            closed_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tenancy_invitations_pending "
        "ON tenancy_invitations (tenancy, user_id) WHERE status = 'pending'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenancy_invitations_user_status "
        "ON tenancy_invitations (user_id, status)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenancy_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenancy VARCHAR(256),
            event_type tenancy_event_type NOT NULL,
            user_id UUID,
            actor_id UUID,
            request_id UUID,
            invitation_id UUID,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenancy_events_created "
        "ON tenancy_events (created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenancy_events_user "
        "ON tenancy_events (user_id, created_at)"
    )

    op.execute(
        f"""
        INSERT INTO tenancy_events (tenancy, event_type, user_id)
        SELECT ut.tenancy, 'member_added', ut.user_id
        FROM users_tenancies ut
        WHERE ut.tenancy = '{PUBLIC}'
          AND NOT EXISTS (
              SELECT 1 FROM tenancy_events e
              WHERE e.tenancy = ut.tenancy
                AND e.user_id = ut.user_id
                AND e.event_type = 'member_added'
          )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenancy_events")
    op.execute("DROP TABLE IF EXISTS tenancy_invitations")
    op.execute("DROP TABLE IF EXISTS tenancy_requests")
    for name in reversed(list(ENUMS)):
        op.execute(f"DROP TYPE IF EXISTS {name}")
    op.execute("ALTER TABLE datasets ALTER COLUMN members_can_edit SET DEFAULT true")
    op.execute("ALTER TABLE tenancies DROP COLUMN IF EXISTS display_name")
```

The last `INSERT` writes one `member_added` event, with no actor, for every public membership that has none: the migration's additions are membership changes too, and `since` in the admin member list reads them.

- [ ] **Step 5: The seeded integration user is in public**

The integration database is migrated empty, then seeded, so the migration's backfill never sees the seeded user. Production has no such gap. In `tests/integration/fixtures/seed_clients.sql`, replace

```sql
-- Connect user to tenancy
INSERT INTO users_tenancies (user_id, tenancy)
VALUES (
    'cbb0a683-630f-4b86-8b45-91b90a6fce1c'::uuid,
    'datamap/production/data-amazon'
) ON CONFLICT (user_id, tenancy) DO NOTHING;
```

with

```sql
-- Connect user to tenancy
INSERT INTO users_tenancies (user_id, tenancy)
VALUES (
    'cbb0a683-630f-4b86-8b45-91b90a6fce1c'::uuid,
    'datamap/production/data-amazon'
) ON CONFLICT (user_id, tenancy) DO NOTHING;

-- Every account is in public (RFC 009); the migration ran before this user existed.
INSERT INTO users_tenancies (user_id, tenancy)
VALUES (
    'cbb0a683-630f-4b86-8b45-91b90a6fce1c'::uuid,
    'datamap/production/public'
) ON CONFLICT (user_id, tenancy) DO NOTHING;
```

- [ ] **Step 6: Run the unit test and see it pass**

```bash
$PY -m pytest app/model/db/tenancy_test.py app/model/db/auth_challenge_test.py -q -p no:cacheprovider
```

Expected: all pass.

- [ ] **Step 7: Prove the migration against PostgreSQL, both ways**

Follow *Running the integration suite* up to and including the health poll (no seed needed yet). Then:

```bash
docker exec datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db -tA -c "SELECT version_num FROM alembic_version"
docker exec datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db -tA -c "SELECT name, display_name, is_enabled FROM tenancies WHERE name = 'datamap/production/public'"
docker exec datamap_gatekeeper_test_integration python3 -m alembic downgrade -1
docker exec datamap_gatekeeper_test_integration python3 -m alembic upgrade head
docker exec datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db -tA -c "SELECT count(*) FROM information_schema.tables WHERE table_name IN ('tenancy_requests', 'tenancy_invitations', 'tenancy_events')"
docker exec datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db -tA -c "SELECT column_default FROM information_schema.columns WHERE table_name = 'datasets' AND column_name = 'members_can_edit'"
```

Expected, in order: `c3d4e5f6a7b8`; `datamap/production/public|Public|t`; `Running downgrade c3d4e5f6a7b8 -> b1c2d3e4f5a6`; `Running upgrade b1c2d3e4f5a6 -> c3d4e5f6a7b8`; `3`; `false`.

Check autogenerate sees no drift between the models and the migration:

```bash
docker exec datamap_gatekeeper_test_integration sh -c "python3 -m alembic revision --autogenerate -m drift-check 2>&1 | tail -5; ls migrations/versions | grep drift_check"
```

Expected: the generated file's body has `pass` in both functions. Read it with `docker exec datamap_gatekeeper_test_integration sh -c 'cat migrations/versions/*drift_check*.py'`. If it proposes changes to the three new tables, the `display_name` column or `members_can_edit`, fix the model or the migration so they agree and repeat. The file exists only inside the container; nothing to delete in W. Then `dc down`.

- [ ] **Step 8: Commit**

```bash
pwd && command git branch --show-current
command git add app/model/db/tenancy.py app/model/db/tenancy_test.py app/model/db/dataset.py app/model/dataset.py app/controller/v1/dataset/resource.py migrations/versions/2026_10_05_1200-c3d4e5f6a7b8_add_tenancy_requests_invitations_and_events.py tests/integration/fixtures/seed_clients.sql
command git commit -m "feat: public tenancy, closed datasets and tenancy request, invitation and event tables (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 4: Owners decide collaboration — closed by default, never member-editable in public

**Files:**
- Modify: `app/service/dataset_access.py`
- Modify: `app/service/members_access.py`
- Modify: `app/service/dataset.py`
- Test: `app/service/dataset_access_test.py`, `app/service/members_access_test.py`, `app/service/dataset_test.py`

**Interfaces:**
- Consumes: `DEFAULT_TENANCY` (Task 2).
- Produces: `allows_member_edits(dataset) -> bool` is `False` for `dataset.tenancy == DEFAULT_TENANCY` and for an unflushed `None`; `MembersAccessService.set(...)` raises `IllegalStateException("public_members_cannot_edit")` for `True` on public, after the owner check; `DatasetService.create_dataset` stores `members_can_edit=False`; `DatasetService.update_dataset` stores `False` when the dataset ends up in public.

- [ ] **Step 1: Write the failing tests**

In `app/service/dataset_access_test.py`, replace

```python
    def test_a_row_not_yet_flushed_reads_as_the_default(self):
        dataset = _dataset(owner_id=uuid4())
        dataset.members_can_edit = None

        self.assertTrue(allows_member_edits(dataset))
        self.assertTrue(self._permits(dataset, DatasetAction.WRITE))
        self.assertFalse(allows_member_edits(_dataset(members_can_edit=False)))
```

with

```python
    def test_a_row_not_yet_flushed_reads_as_the_default_which_is_closed(self):
        dataset = _dataset(owner_id=uuid4())
        dataset.members_can_edit = None

        self.assertFalse(allows_member_edits(dataset))
        self.assertFalse(self._permits(dataset, DatasetAction.WRITE))
        self.assertFalse(allows_member_edits(_dataset(members_can_edit=False)))

    def test_public_is_never_member_editable_whatever_the_column_says(self):
        dataset = _dataset(
            owner_id=uuid4(), tenancy=DEFAULT_TENANCY, members_can_edit=True
        )

        self.assertFalse(allows_member_edits(dataset))
        self.assertTrue(
            self._permits(dataset, DatasetAction.READ_METADATA, (DEFAULT_TENANCY,))
        )
        self.assertTrue(
            self._permits(dataset, DatasetAction.READ_FILES, (DEFAULT_TENANCY,))
        )
        self.assertFalse(self._permits(dataset, DatasetAction.WRITE, (DEFAULT_TENANCY,)))
        self.assertFalse(
            self._permits(dataset, DatasetAction.DELETE, (DEFAULT_TENANCY,))
        )

    def test_in_public_the_owner_and_a_write_permission_still_edit(self):
        owned = _dataset(owner_id=self.user_id, tenancy=DEFAULT_TENANCY)
        self.assertTrue(self._permits(owned, DatasetAction.WRITE, (DEFAULT_TENANCY,)))

        self._grant("write")
        shared = _dataset(owner_id=uuid4(), tenancy=DEFAULT_TENANCY)
        self.assertTrue(self._permits(shared, DatasetAction.WRITE, (DEFAULT_TENANCY,)))
```

and replace

```python
from app.service.dataset_access import DatasetAccessService, allows_member_edits
from app.service.user import UserService
```

with

```python
from app.model.tenancy import DEFAULT_TENANCY
from app.service.dataset_access import DatasetAccessService, allows_member_edits
from app.service.user import UserService
```

In `app/service/members_access_test.py`, replace

```python
from app.exception.forbidden import ForbiddenException
```

with

```python
from app.exception.forbidden import ForbiddenException
from app.exception.illegal_state import IllegalStateException
from app.model.tenancy import DEFAULT_TENANCY
```

and append to the end of the class `TestMembersAccessService` (after `test_a_caller_who_is_not_the_owner_is_refused_before_anything_changes`, whose last line is `        self.assertTrue(self.dataset.members_can_edit)`), as new methods:

```python

    def test_opening_a_public_dataset_to_members_is_refused(self):
        self.dataset.tenancy = DEFAULT_TENANCY
        self.dataset.members_can_edit = False

        with self.assertRaises(IllegalStateException) as raised:
            self._set(True)

        self.assertEqual(str(raised.exception), "public_members_cannot_edit")
        self.repository.upsert.assert_not_called()
        self.audit.record.assert_not_called()

    def test_closing_a_public_dataset_is_a_no_op_even_when_the_column_is_true(self):
        self.dataset.tenancy = DEFAULT_TENANCY
        self.dataset.members_can_edit = True

        result = self._set(False)

        self.assertFalse(result.members_can_edit)
        self.repository.upsert.assert_not_called()
        self.audit.record.assert_not_called()

    def test_the_owner_check_comes_before_the_public_rule(self):
        self.dataset.tenancy = DEFAULT_TENANCY
        self.datasets.fetch_authorized.side_effect = ForbiddenException("forbidden")

        with self.assertRaises(ForbiddenException):
            self._set(True)
```

In `app/service/dataset_test.py`, replace

```python
        result = self.dataset_service.create_dataset(dataset=dataset, user_id=user_id)
        self.assertIsNotNone(result)
        self.dataset_repository.upsert.assert_called_once()
```

with

```python
        result = self.dataset_service.create_dataset(dataset=dataset, user_id=user_id)
        self.assertIsNotNone(result)
        self.dataset_repository.upsert.assert_called_once()
        stored = self.dataset_repository.upsert.call_args.kwargs["dataset"]
        self.assertIs(stored.members_can_edit, False)

    def test_moving_a_dataset_into_public_closes_it_to_members(self):
        self.user_service.fetch_by_id.return_value = self.mock_user(["tenancy1"])
        dataset_db = Mock(spec=DatasetDBModel)
        dataset_db.tenancy = "tenancy1"
        dataset_db.members_can_edit = True
        version = Mock(spec=DatasetVersionDBModel)
        version.name = "1"
        version.is_enabled = True
        version.design_state = DesignState.DRAFT
        version.doi = None
        dataset_db.versions = [version]
        self.dataset_repository.fetch.return_value = dataset_db
        request = Dataset(name="n", data={}, tenancy=DEFAULT_TENANCY)

        self.dataset_service.update_dataset(
            dataset_id=uuid4(),
            dataset_request=request,
            user_id=uuid4(),
            tenancies=["tenancy1"],
        )

        self.assertEqual(dataset_db.tenancy, DEFAULT_TENANCY)
        self.assertIs(dataset_db.members_can_edit, False)

    def test_an_edit_outside_public_keeps_what_the_owner_chose(self):
        self.user_service.fetch_by_id.return_value = self.mock_user(["tenancy1"])
        dataset_db = Mock(spec=DatasetDBModel)
        dataset_db.tenancy = "tenancy1"
        dataset_db.members_can_edit = True
        version = Mock(spec=DatasetVersionDBModel)
        version.name = "1"
        version.is_enabled = True
        version.design_state = DesignState.DRAFT
        version.doi = None
        dataset_db.versions = [version]
        self.dataset_repository.fetch.return_value = dataset_db

        self.dataset_service.update_dataset(
            dataset_id=uuid4(),
            dataset_request=Dataset(name="n", data={}, tenancy="tenancy1"),
            user_id=uuid4(),
            tenancies=["tenancy1"],
        )

        self.assertIs(dataset_db.members_can_edit, True)
```

and replace

```python
from app.model.tenancy import Tenancy
```

with

```python
from app.model.tenancy import DEFAULT_TENANCY, Tenancy
```

- [ ] **Step 2: Run them and see them fail**

```bash
$PY -m pytest app/service/dataset_access_test.py app/service/members_access_test.py app/service/dataset_test.py -q -p no:cacheprovider
```

Expected: failures in `test_a_row_not_yet_flushed_reads_as_the_default_which_is_closed`, `test_public_is_never_member_editable_whatever_the_column_says`, `test_opening_a_public_dataset_to_members_is_refused`, `test_create_dataset_success` (`members_can_edit` is not `False`), `test_moving_a_dataset_into_public_closes_it_to_members`. The other new tests may pass already; that is fine for these two (`..._owner_and_a_write_permission_still_edit`, `..._keeps_what_the_owner_chose`, `..._no_op_even_when_the_column_is_true`, `..._owner_check_comes_before...`) because they pin behaviour that must not regress.

- [ ] **Step 3: Implement**

In `app/service/dataset_access.py`, replace

```python
from app.model.embargo import Embargo, embargo_active
```

with

```python
from app.model.embargo import Embargo, embargo_active
from app.model.tenancy import DEFAULT_TENANCY
```

and replace

```python
def allows_member_edits(dataset: DatasetDBModel) -> bool:
    # None is an unflushed row whose column default is true, not a read-only one.
    return dataset.members_can_edit is not False
```

with

```python
def allows_member_edits(dataset: DatasetDBModel) -> bool:
    return dataset.tenancy != DEFAULT_TENANCY and bool(dataset.members_can_edit)
```

In `app/service/members_access.py`, replace

```python
from uuid import UUID

from app.model.dataset_access import (
```

with

```python
from uuid import UUID

from app.exception.illegal_state import IllegalStateException
from app.model.dataset_access import (
```

replace

```python
from app.repository.dataset import DatasetRepository
```

with

```python
from app.model.tenancy import DEFAULT_TENANCY
from app.repository.dataset import DatasetRepository
```

and replace

```python
        before = allows_member_edits(dataset)
        if before != members_can_edit:
```

with

```python
        if members_can_edit and dataset.tenancy == DEFAULT_TENANCY:
            raise IllegalStateException("public_members_cannot_edit")
        before = allows_member_edits(dataset)
        if before != members_can_edit:
```

In `app/service/dataset.py`, replace

```python
from app.service.embargo_termination import EmbargoTermination
```

with

```python
from app.service.embargo_termination import EmbargoTermination
from app.model.tenancy import DEFAULT_TENANCY
```

replace

```python
        if dataset_request.tenancy and level in (
            AccessLevel.OWNER,
            AccessLevel.TENANCY,
        ):
            dataset_db.tenancy = dataset_request.tenancy
```

with

```python
        if dataset_request.tenancy and level in (
            AccessLevel.OWNER,
            AccessLevel.TENANCY,
        ):
            dataset_db.tenancy = dataset_request.tenancy
        if dataset_db.tenancy == DEFAULT_TENANCY:
            dataset_db.members_can_edit = False
```

and replace

```python
            tenancy=dataset.tenancy,
            design_state=DesignState.DRAFT,
            owner_id=user_id,
        )
```

with

```python
            tenancy=dataset.tenancy,
            design_state=DesignState.DRAFT,
            owner_id=user_id,
            members_can_edit=False,
        )
```

- [ ] **Step 4: Run them and see them pass**

```bash
$PY -m pytest app/service/dataset_access_test.py app/service/members_access_test.py app/service/dataset_test.py app/service/share_preview_test.py app/service/notification_test.py app/service/embargo_design_test.py -q -p no:cacheprovider
```

Expected: all pass. If an existing test elsewhere built a dataset with `members_can_edit=None` and expected edits, it is now wrong by design: change its expectation, not the rule.

- [ ] **Step 5: Commit**

```bash
pwd && command git branch --show-current
command git add app/service/dataset_access.py app/service/dataset_access_test.py app/service/members_access.py app/service/members_access_test.py app/service/dataset.py app/service/dataset_test.py
command git commit -m "feat: datasets start closed to members and public is never member-editable (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Account creation — public and `datasets_write` by every path; retire `new_account_pending` and the membership routes

**Files:**
- Create: `app/repository/tenancy_event.py`
- Modify: `app/service/user.py`, `app/service/user_test.py`
- Modify: `app/controller/v1/user/user.py`, `app/controller/v1/user/resource.py`
- Modify: `app/service/email_template.py`, `app/service/email_template_test.py`, `app/resources/email_templates/README.md`
- Delete: `app/resources/email_templates/new_account_pending.html`, `app/resources/email_templates/new_account_pending.txt`, `tests/integration/test_new_account_notification.py`
- Modify: `app/container.py`

**Interfaces:**
- Produces: `add_event(session, tenancy, event_type, user_id=None, actor_id=None, request_id=None, invitation_id=None) -> TenancyEvent` and `TenancyEventRepository.append(tenancy, event_type, user_id=None, actor_id=None, request_id=None, invitation_id=None) -> UUID` (`app/repository/tenancy_event.py`).
- Produces: `UserService(repository, tenancy_repository, casbin_enforcer, tenancy_events: TenancyEventRepository | None = None)`; `UserService.create` attaches the payload's tenancies then `DEFAULT_TENANCY` (each once), grants the payload's roles then `DEFAULT_ROLE` (each once), appends one `member_added` event per membership with no actor, and enqueues nothing. `UserService.add_tenancies`, `remove_tenancies` and the helpers `admin_addresses`, `sign_in_method`, `created_on`, `PROVIDER_LABELS` are gone (`admin_addresses` reappears in Task 9).
- Removes: `POST /v1/users/{id}/tenancies`, `DELETE /v1/users/{id}/tenancies`, `UserTenanciesRequest`, `EmailTemplate.NEW_ACCOUNT_PENDING`.

- [ ] **Step 1: Write the failing tests**

In `app/service/user_test.py`:

Replace the import block

```python
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4
from app.exception.not_found import NotFoundException
from app.model.user import User, UserProvider
from app.model.db.user import User as UserDBModel, Provider as ProviderDBModel
from app.model.db.tenancy import Tenancy as TenancyDBModel
from app.repository.tenancy import TenancyRepository
from app.repository.user import UserRepository
from app.service.email import EmailService
from app.service.user import UserService, admin_addresses
from casbin import SyncedEnforcer
```

with

```python
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, call
from uuid import uuid4
from app.exception.not_found import NotFoundException
from app.model.tenancy import DEFAULT_TENANCY, TenancyEventType
from app.model.user import User, UserProvider
from app.model.db.user import User as UserDBModel, Provider as ProviderDBModel
from app.model.db.tenancy import Tenancy as TenancyDBModel
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_event import TenancyEventRepository
from app.repository.user import UserRepository
from app.service.email_template import EmailTemplate
from app.service.user import UserService
from casbin import SyncedEnforcer
```

In `test_create_persists_the_tenancies_it_was_given`, replace

```python
        self.tenancy_repository.fetch.assert_called_once_with(
            tenancy="datamap/production/data-amazon"
        )
```

with

```python
        self.tenancy_repository.fetch.assert_any_call(
            tenancy="datamap/production/data-amazon"
        )
```

Delete the two tests of the removed methods, i.e. the text from the line `    def test_remove_tenancies_success(self):` up to, not including, the line `    def test_update_success(self):`. Delete the classes `TestNewAccountNotification` and `TestAdminAddresses`, i.e. the text from the line `class TestNewAccountNotification(unittest.TestCase):` up to, not including, the line `class TestCredentialFields(unittest.TestCase):`. Do both with this script, which fails loudly if an anchor is missing:

```bash
$PY - <<'EOF'
from pathlib import Path
path = Path("app/service/user_test.py")
text = path.read_text()
for start, end in (
    ("    def test_remove_tenancies_success(self):", "    def test_update_success(self):"),
    ("class TestNewAccountNotification(unittest.TestCase):", "class TestCredentialFields(unittest.TestCase):"),
):
    i, j = text.index(start), text.index(end)
    text = text[:i] + text[j:]
path.write_text(text)
EOF
```

Then insert, immediately before the line `class TestCredentialFields(unittest.TestCase):`, this class:

```python
class TestDefaultAccess(unittest.TestCase):
    def setUp(self):
        self.user_repository = Mock(spec=UserRepository)
        self.tenancy_repository = Mock(spec=TenancyRepository)
        self.tenancy_repository.fetch.side_effect = lambda tenancy: TenancyDBModel(
            name=tenancy, is_enabled=True
        )
        self.casbin_enforcer = Mock(spec=SyncedEnforcer)
        self.events = Mock(spec=TenancyEventRepository)
        self.user_id = uuid4()
        persisted = Mock(spec=UserDBModel)
        persisted.id = self.user_id
        self.user_repository.upsert.return_value = persisted
        self.service = UserService(
            self.user_repository,
            self.tenancy_repository,
            self.casbin_enforcer,
            tenancy_events=self.events,
        )

    def account(self, **overrides) -> User:
        values = dict(name="Ana Souza", email="ana.souza@usp.br", providers=[], roles=[])
        values.update(overrides)
        return User(**values)

    def created(self) -> UserDBModel:
        return self.user_repository.upsert.call_args.kwargs["user"]

    def test_a_new_account_is_in_public(self):
        self.service.create(self.account())

        self.assertEqual([t.name for t in self.created().tenancies], [DEFAULT_TENANCY])

    def test_public_comes_after_the_tenancies_given_and_only_once(self):
        self.service.create(
            self.account(tenancies=["datamap/production/data-amazon", DEFAULT_TENANCY])
        )

        self.assertEqual(
            [t.name for t in self.created().tenancies],
            ["datamap/production/data-amazon", DEFAULT_TENANCY],
        )

    def test_a_new_account_can_work_at_once(self):
        self.service.create(self.account())

        self.casbin_enforcer.add_grouping_policy.assert_called_once_with(
            str(self.user_id), "datasets_write"
        )

    def test_datasets_write_is_added_to_the_roles_given_once(self):
        self.service.create(self.account(roles=["admin", "datasets_write"]))

        self.assertEqual(
            self.casbin_enforcer.add_grouping_policy.call_args_list,
            [call(str(self.user_id), "admin"), call(str(self.user_id), "datasets_write")],
        )

    def test_every_membership_is_recorded_with_no_actor(self):
        self.service.create(self.account(tenancies=["datamap/production/data-amazon"]))

        self.assertEqual(
            self.events.append.call_args_list,
            [
                call(
                    tenancy="datamap/production/data-amazon",
                    event_type=TenancyEventType.MEMBER_ADDED,
                    user_id=self.user_id,
                ),
                call(
                    tenancy=DEFAULT_TENANCY,
                    event_type=TenancyEventType.MEMBER_ADDED,
                    user_id=self.user_id,
                ),
            ],
        )

    def test_a_failure_to_record_does_not_undo_the_account(self):
        self.events.append.side_effect = RuntimeError("database gone")

        with self.assertLogs("service:UserService", level="ERROR"):
            user_id = self.service.create(self.account())

        self.assertEqual(user_id, self.user_id)

    def test_an_account_created_with_a_password_is_stored_confirmed(self):
        self.service.create(
            self.account(), password_hash=BCRYPT_LIKE, email_verified_at=CREATED
        )

        self.assertEqual(self.created().password_hash, BCRYPT_LIKE)
        self.assertEqual(self.created().email_verified_at, CREATED)

    def test_nobody_is_emailed_about_a_new_account_any_more(self):
        self.assertNotIn("new_account_pending", [t.value for t in EmailTemplate])


```

`CREATED` and `BCRYPT_LIKE` stay defined above (the deletion keeps the lines `CREATED = ...` and `BCRYPT_LIKE = ...`, which sit before `class TestNewAccountNotification`). Check with `grep -n "^CREATED\|^BCRYPT_LIKE" app/service/user_test.py`: both must still be present; if the script removed them, re-add these two lines before `class TestDefaultAccess`:

```python
CREATED = datetime(2026, 10, 3, 14, 5, tzinfo=timezone.utc)
BCRYPT_LIKE = "$2b$10$" + "x" * 53
```

In `app/service/email_template_test.py`, delete

```python
CONTEXTS[EmailTemplate.NEW_ACCOUNT_PENDING] = {
    "name": "Ana Souza",
    "email": "ana.souza@usp.br",
    "sign_in_method": "Email and password",
    "created_at": "October 3, 2026 at 14:05 UTC",
}

```

replace

```python
        EmailTemplate.SIGN_UP_EXISTING_ACCOUNT,
        EmailTemplate.NEW_ACCOUNT_PENDING,
    }
)
```

with

```python
        EmailTemplate.SIGN_UP_EXISTING_ACCOUNT,
    }
)
```

and delete the test

```python
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

```

- [ ] **Step 2: Run them and see them fail**

```bash
$PY -m pytest app/service/user_test.py -q -p no:cacheprovider
```

Expected: collection error `ModuleNotFoundError: No module named 'app.repository.tenancy_event'`.

- [ ] **Step 3: Implement**

Create `app/repository/tenancy_event.py`:

```python
from contextlib import AbstractContextManager
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.model.db.tenancy import TenancyEvent
from app.model.tenancy import TenancyEventType


def add_event(
    session: Session,
    tenancy: str | None,
    event_type: TenancyEventType,
    user_id: UUID | None = None,
    actor_id: UUID | None = None,
    request_id: UUID | None = None,
    invitation_id: UUID | None = None,
) -> TenancyEvent:
    event = TenancyEvent(
        id=uuid4(),
        tenancy=tenancy,
        event_type=event_type,
        user_id=user_id,
        actor_id=actor_id,
        request_id=request_id,
        invitation_id=invitation_id,
    )
    session.add(event)
    return event


class TenancyEventRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def append(
        self,
        tenancy: str | None,
        event_type: TenancyEventType,
        user_id: UUID | None = None,
        actor_id: UUID | None = None,
        request_id: UUID | None = None,
        invitation_id: UUID | None = None,
    ) -> UUID:
        with self._session_factory() as session:
            event = add_event(
                session,
                tenancy=tenancy,
                event_type=event_type,
                user_id=user_id,
                actor_id=actor_id,
                request_id=request_id,
                invitation_id=invitation_id,
            )
            event_id = event.id
            session.commit()
            return event_id
```

In `app/service/user.py`, replace the text from the first line of the file through the constructor, i.e.

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


class UserService:
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

with

```python
import logging
from datetime import datetime
from uuid import UUID
from app.exception.not_found import NotFoundException
from app.logging_config import fields
from app.model.db.user import Provider as ProviderDBModel, User as UserDBModel
from app.model.tenancy import DEFAULT_TENANCY, TenancyEventType
from app.model.user import DEFAULT_ROLE, User, UserProvider, UserQuery
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_event import TenancyEventRepository
from app.repository.user import UserRepository
from casbin import SyncedEnforcer


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        tenancy_repository: TenancyRepository,
        casbin_enforcer: SyncedEnforcer,
        tenancy_events: TenancyEventRepository | None = None,
    ) -> None:
        self._repository: UserRepository = repository
        self._tenancy_repository: TenancyRepository = tenancy_repository
        self._casbin_enforcer: SyncedEnforcer = casbin_enforcer
        self._tenancy_events = tenancy_events
        self._logger = logging.getLogger("service:UserService")
```

Replace the tail of `create` and the whole `_notify_admins` method, i.e.

```python
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

with

```python
        tenancies = list(dict.fromkeys([*(user.tenancies or []), DEFAULT_TENANCY]))
        for tenancy in tenancies:
            dbUser.tenancies.append(self._tenancy_repository.fetch(tenancy=tenancy))

        created = self._repository.upsert(user=dbUser)
        user_id = created.id

        for role in dict.fromkeys([*(user.roles or []), DEFAULT_ROLE]):
            self._casbin_enforcer.add_grouping_policy(str(user_id), role)

        self._record_memberships(user_id, tenancies)
        return user_id

    def _record_memberships(self, user_id: UUID, tenancies: list[str]) -> None:
        if self._tenancy_events is None:
            return
        for tenancy in tenancies:
            try:
                self._tenancy_events.append(
                    tenancy=tenancy,
                    event_type=TenancyEventType.MEMBER_ADDED,
                    user_id=user_id,
                )
            except Exception:
                self._logger.error(
                    "tenancy event not recorded",
                    exc_info=True,
                    extra=fields(user_id=str(user_id), tenancy=tenancy),
                )
```

Delete the two methods at the end of the file, i.e. everything from

```python
    def add_tenancies(self, user_id: UUID, tenancies: list[str]) -> None:
```

to the end of the file (the last line is `        self._repository.upsert(user=user)` of `remove_tenancies`), leaving `load_policy` as the last method.

In `app/controller/v1/user/user.py`, replace

```python
    UserProvider,
    UserTenanciesRequest,
    UserPasswordChangeRequest,
```

with

```python
    UserProvider,
    UserPasswordChangeRequest,
```

and delete

```python
# POST /users/{id}/tenancies
@router.post(
    "/{id}/tenancies", dependencies=[Depends(authenticate), Depends(authorize)]
)
@inject
def add_tenancy(
    id: UUID,
    payload: UserTenanciesRequest,
    service: UserService = Depends(Provide[Container.user_service]),
) -> None:
    service.add_tenancies(user_id=id, tenancies=payload.tenancies)
    return {}


# DELETE /users/{id}/tenancies
@router.delete(
    "/{id}/tenancies", dependencies=[Depends(authenticate), Depends(authorize)]
)
@inject
def remove_tenancy(
    id: UUID,
    payload: UserTenanciesRequest,
    service: UserService = Depends(Provide[Container.user_service]),
) -> None:
    service.remove_tenancies(user_id=id, tenancies=payload.tenancies)
    return {}


```

In `app/controller/v1/user/resource.py`, delete

```python
class UserTenanciesRequest(BaseModel):
    tenancies: list[str] = Field([], description="Tenancies name")


```

In `app/service/email_template.py`, replace

```python
    SIGN_UP_EXISTING_ACCOUNT = "sign_up_existing_account"
    NEW_ACCOUNT_PENDING = "new_account_pending"
```

with

```python
    SIGN_UP_EXISTING_ACCOUNT = "sign_up_existing_account"
```

In `app/resources/email_templates/README.md`, delete the line

```
| `new_account_pending` | `name`, `email`, `sign_in_method`, `created_at` | |
```

Delete the files:

```bash
command git rm -q app/resources/email_templates/new_account_pending.html app/resources/email_templates/new_account_pending.txt tests/integration/test_new_account_notification.py
```

In `app/container.py`, replace

```python
from app.repository.permission import PermissionRepository
from app.repository.user import UserRepository
```

with

```python
from app.repository.permission import PermissionRepository
from app.repository.tenancy_event import TenancyEventRepository
from app.repository.user import UserRepository
```

and replace

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

with

```python
    tenancy_event_repository = providers.Factory(
        TenancyEventRepository,
        session_factory=db.provided.session,
    )

    user_service = providers.Factory(
        UserService,
        repository=user_repository,
        tenancy_repository=tenancy_repository,
        casbin_enforcer=casbin_enforcer,
        tenancy_events=tenancy_event_repository,
    )
```

- [ ] **Step 4: Run them and see them pass**

```bash
grep -rn "add_tenancies\|remove_tenancies\|NEW_ACCOUNT_PENDING\|new_account_pending\|UserTenanciesRequest\|admin_addresses" app tests
$PY -m pytest app/service/user_test.py app/service/email_template_test.py app/controller/v1/user/user_test.py app/controller/routes_security_test.py app/service/account_test.py -q -p no:cacheprovider
```

Expected: the `grep` prints nothing; all tests pass.

- [ ] **Step 5: Commit**

```bash
pwd && command git branch --show-current
command git add app/repository/tenancy_event.py app/service/user.py app/service/user_test.py app/controller/v1/user/user.py app/controller/v1/user/resource.py app/service/email_template.py app/service/email_template_test.py app/resources/email_templates/README.md app/container.py
command git commit -m "feat: every account lands in public with datasets_write; retire new_account_pending and the membership routes (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Existing integration tests follow the new defaults

**Files:**
- Modify: `tests/integration/fixtures/embargo.py`
- Modify: `tests/integration/test_user_api.py`
- Modify: `tests/integration/test_auth_login_and_password.py`
- Modify: `tests/integration/test_dataset_members_access.py`

**Interfaces:**
- Produces: `tests/integration/fixtures/embargo.create_user(http_client, roles, tenancies) -> str` keeps its signature and meaning: the account ends with exactly `roles` (plus nothing else), and is a member of `tenancies` plus public. It no longer calls the retired route; memberships are inserted with SQL, which `_determine_tenancies` reads on every call.

- [ ] **Step 1: Run the affected files against the branch and see them fail**

Follow *Running the integration suite* (stack up, seeded, `/clients/` → 200), then:

```bash
$PY -m pytest tests/integration/test_dataset_members_access.py tests/integration/test_dataset_embargo.py tests/integration/test_user_api.py tests/integration/test_auth_login_and_password.py -q -p no:cacheprovider
```

Expected: failures, among them every test using `embargo.create_user` with a tenancy (`405` from the retired `POST /users/{id}/tenancies`), `TestUserTenancyOperations`, `test_user_full_lifecycle`, `test_an_account_without_a_role_reads_itself` (`roles == ['datasets_write']`), and the members-access tests that relied on the old `true` default.

- [ ] **Step 2: Fix the fixture**

In `tests/integration/fixtures/embargo.py`, replace

```python
from tests.integration.utils.http_client import HttpClient
```

with

```python
from tests.integration.utils.database import execute
from tests.integration.utils.http_client import HttpClient
```

and replace

```python
    assert response.status_code == 200, response.text
    user_id = response.json()["id"]
    if roles:
        response = http_client.put(f"/users/{user_id}/roles", json=roles, headers=admin)
        assert response.status_code == 200, response.text
    if tenancies:
        response = http_client.post(
            f"/users/{user_id}/tenancies", json={"tenancies": tenancies}, headers=admin
        )
        assert response.status_code == 200, response.text
    return user_id
```

with

```python
    assert response.status_code == 200, response.text
    user_id = response.json()["id"]
    if "datasets_write" not in roles:
        response = http_client.delete(
            f"/users/{user_id}/roles", json=["datasets_write"], headers=admin
        )
        assert response.status_code == 200, response.text
    if roles:
        response = http_client.put(f"/users/{user_id}/roles", json=roles, headers=admin)
        assert response.status_code == 200, response.text
    for tenancy in tenancies:
        execute(
            "INSERT INTO users_tenancies (user_id, tenancy) "
            f"VALUES ('{user_id}', '{tenancy}') ON CONFLICT DO NOTHING"
        )
    return user_id
```

- [ ] **Step 3: Fix the user API tests**

In `tests/integration/test_user_api.py`, delete the class `TestUserTenancyOperations` (from the line `class TestUserTenancyOperations:` up to, not including, `class TestUserEnforceOperations:`) and step 6 of the lifecycle test:

```bash
$PY - <<'EOF'
from pathlib import Path
path = Path("tests/integration/test_user_api.py")
text = path.read_text()
start, end = "class TestUserTenancyOperations:", "class TestUserEnforceOperations:"
text = text[: text.index(start)] + text[text.index(end):]
step = '''        # 6. Add tenancy
        tenancy_data = {"tenancies": ["datamap/production/data-amazon"]}
        tenancy_response = http_client.post(
            f"/users/{user_id}/tenancies", json=tenancy_data, headers=valid_headers
        )
        assert_status_code(tenancy_response, 200)

'''
assert step in text
text = text.replace(step, "")
path.write_text(text)
EOF
```

The retired routes get their own test in Task 16.

In `tests/integration/test_auth_login_and_password.py`, replace

```python
        assert response.json()["roles"] == []
        assert response.json()["has_password"] is True
```

with

```python
        assert response.json()["roles"] == ["datasets_write"]
        assert response.json()["tenancies"] == ["datamap/production/public"]
        assert response.json()["has_password"] is True
```

- [ ] **Step 4: Fix the members-access tests for the `false` default**

In `tests/integration/test_dataset_members_access.py`:

Replace

```python
class TestByDefault:
    def test_a_new_dataset_lets_members_edit_as_today(self, http_client, owner, editor):
        dataset = create_dataset(http_client, owner)
        _, headers = editor

        as_member = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        update = _update(http_client, dataset["id"], headers)

        assert_status_code(as_member, 200)
        assert as_member.json()["members_can_edit"] is True
        assert as_member.json()["access"]["can_edit"] is True
        assert_status_code(update, 200)
```

with

```python
def _open(http_client, owner: dict) -> dict:
    dataset = create_dataset(http_client, owner)
    assert_status_code(_members(http_client, dataset["id"], owner, True), 200)
    return dataset


class TestByDefault:
    def test_a_new_dataset_is_closed_to_members(self, http_client, owner, editor):
        dataset = create_dataset(http_client, owner)
        _, headers = editor

        as_member = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        update = _update(http_client, dataset["id"], headers)

        assert_status_code(as_member, 200)
        assert as_member.json()["members_can_edit"] is False
        assert as_member.json()["access"]["can_edit"] is False
        assert_status_code(update, 403)

    def test_the_owner_opens_it_and_members_edit(self, http_client, owner, editor):
        dataset = _open(http_client, owner)
        _, headers = editor

        as_member = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        update = _update(http_client, dataset["id"], headers)

        assert as_member.json()["members_can_edit"] is True
        assert as_member.json()["access"]["can_edit"] is True
        assert_status_code(update, 200)
```

Replace

```python
        _, headers = deleter
        read_only = create_dataset(http_client, owner)
        editable = create_dataset(http_client, owner)
        assert_status_code(_members(http_client, read_only["id"], owner, False), 200)
```

with

```python
        _, headers = deleter
        read_only = create_dataset(http_client, owner)
        editable = _open(http_client, owner)
```

Replace

```python
        dataset = create_dataset(http_client, owner)
        user_id, headers = editor
        grant(http_client, dataset["id"], user_id, "read")
        assert_status_code(_update(http_client, dataset["id"], headers), 200)
```

with

```python
        dataset = _open(http_client, owner)
        user_id, headers = editor
        grant(http_client, dataset["id"], user_id, "read")
        assert_status_code(_update(http_client, dataset["id"], headers), 200)
```

Replace

```python
    def test_by_default_members_edit_again_after_the_embargo(
        self, http_client, owner, editor
    ):
        dataset = create_dataset(http_client, owner)
```

with

```python
    def test_an_open_dataset_lets_members_edit_again_after_the_embargo(
        self, http_client, owner, editor
    ):
        dataset = _open(http_client, owner)
```

Replace

```python
        detail = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()
        assert detail["members_can_edit"] is True
```

with

```python
        detail = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()
        assert detail["members_can_edit"] is False
```

Replace

```python
        dataset = create_dataset(http_client, owner)
        _members(http_client, dataset["id"], owner, False)
        _members(http_client, dataset["id"], owner, False)

        history = http_client.get(
```

with

```python
        dataset = create_dataset(http_client, owner)
        _members(http_client, dataset["id"], owner, True)
        _members(http_client, dataset["id"], owner, True)

        history = http_client.get(
```

Replace

```python
        assert changes[0]["old_value"] == {"members_can_edit": True}
        assert changes[0]["new_value"] == {"members_can_edit": False}
```

with

```python
        assert changes[0]["old_value"] == {"members_can_edit": False}
        assert changes[0]["new_value"] == {"members_can_edit": True}
```

Replace

```python
        before = http_client.get(f"/datasets/{dataset['id']}/share", headers=owner)
        _members(http_client, dataset["id"], owner, False)
        after = http_client.get(f"/datasets/{dataset['id']}/share", headers=owner)
```

with

```python
        before = http_client.get(f"/datasets/{dataset['id']}/share", headers=owner)
        _members(http_client, dataset["id"], owner, True)
        after = http_client.get(f"/datasets/{dataset['id']}/share", headers=owner)
```

and

```python
        assert before.json()["tenancy"]["members_can_edit"] is True
        assert after.json()["tenancy"]["members_can_edit"] is False
```

with

```python
        assert before.json()["tenancy"]["members_can_edit"] is False
        assert after.json()["tenancy"]["members_can_edit"] is True
```

- [ ] **Step 5: Run the affected files and every other file that builds users or datasets**

The stack must be rebuilt only if application code changed since Step 1 (it did not; these are test files). Run:

```bash
$PY -m pytest tests/integration/test_dataset_members_access.py tests/integration/test_dataset_embargo.py tests/integration/test_user_api.py tests/integration/test_auth_login_and_password.py tests/integration/test_sharing_api.py tests/integration/test_embargo_notifications.py tests/integration/test_dataset_api.py tests/integration/test_tus_api.py tests/integration/test_auth_sign_up.py tests/integration/test_auth_email_verification.py -q -p no:cacheprovider
```

Expected: `0 failed`, no `skipped` from `verify_services_running`. A remaining failure caused by the new defaults is fixed by the same rule as above — a test that needs members to edit opens the dataset with `PUT /datasets/{id}/members-access {"members_can_edit": true}` first; a test that needs an account without a role removes `datasets_write` with `DELETE /users/{id}/roles` — and never by changing application code. A failure unrelated to RFC 009 is reported, not fixed here. `dc down` when done.

- [ ] **Step 6: Commit**

```bash
pwd && command git branch --show-current
command git add tests/integration/fixtures/embargo.py tests/integration/test_user_api.py tests/integration/test_auth_login_and_password.py tests/integration/test_dataset_members_access.py
command git commit -m "test: integration tests follow public membership, datasets_write and closed datasets (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 7: The five emails and `TenancyNotifier`

**Files:**
- Modify: `app/service/email_template.py`
- Create: `app/resources/email_templates/tenancy_request_received.html`, `.txt`; `tenancy_access_granted.html`, `.txt`; `tenancy_request_declined.html`, `.txt`; `tenancy_invitation.html`, `.txt`; `tenancy_invitation_notice.html`, `.txt`
- Modify: `app/resources/email_templates/README.md`
- Create: `app/service/tenancy_notifier.py`
- Test: `app/service/email_template_test.py`, `app/service/tenancy_notifier_test.py`

**Interfaces:**
- Produces: `EmailTemplate.TENANCY_REQUEST_RECEIVED`, `TENANCY_ACCESS_GRANTED`, `TENANCY_REQUEST_DECLINED`, `TENANCY_INVITATION`, `TENANCY_INVITATION_NOTICE` with the contexts of the contract.
- Produces (`app/service/tenancy_notifier.py`): `admin_addresses(value: str) -> list[str]`; `TenancyNotifier(email_service: EmailService, admin_emails: str, public_base_url: str)` with
  - `request_received(request, requester) -> None` (request: `id, requested_name, reason, created_at`; requester: `id, name, email, email_verified_at`)
  - `access_granted(user, admin_name: str, tenancy: TenancySummary, datasets: int, event_id: UUID) -> None`
  - `request_declined(user, request) -> None` (request: `id, requested_name, decision_message`)
  - `invitation(invitee, inviter_name: str, tenancy: TenancySummary, dataset_name: str, invitation_id: UUID) -> None`
  - `invitation_notice(invitee, inviter_name: str, tenancy: TenancySummary, dataset_name: str, invitation_id: UUID) -> None`
  A user without an email is skipped; a placeholder address is recorded `skipped` by `EmailService`; a failure to enqueue is logged and never raised.

The templates extend `base.html`/`base.txt`, like every RFC 008 account message, not `_transactional.html`: that shell's footer says "This is a transactional message about a dataset you have access to; it is sent to everyone the dataset depends on", which is false for all five, and `email_template_test.py` already asserts account messages never claim it. Reported as a deviation from the RFC's wording.

- [ ] **Step 1: Write the failing tests**

Append to `app/service/email_template_test.py`:

```python


CONTEXTS[EmailTemplate.TENANCY_REQUEST_RECEIVED] = {
    "requester_name": "Bruna Costa",
    "requester_email": "bruna.costa@usp.br",
    "email_confirmed": True,
    "requested_name": "ATTO",
    "reason": "I process the ATTO tower fluxes.",
    "requested_at": "October 5, 2026 at 09:30 UTC",
    "review_url": "https://datamap.example.org/app/admin/requests?request=7d1c",
}
CONTEXTS[EmailTemplate.TENANCY_ACCESS_GRANTED] = {
    "user_name": "Bruna Costa",
    "admin_name": "Luciana Rizzo",
    "tenancy_display_name": "ATTO",
    "tenancy_path": "datamap/production/atto",
    "datasets_count": 12,
    "open_url": "https://datamap.example.org/app/tenancy",
}
CONTEXTS[EmailTemplate.TENANCY_REQUEST_DECLINED] = {
    "user_name": "Bruna Costa",
    "requested_name": "ATTO",
    "decision_message": "Ask Alan to invite you from a dataset.",
    "open_url": "https://datamap.example.org/app/tenancy",
}
CONTEXTS[EmailTemplate.TENANCY_INVITATION] = {
    "invitee_name": "Bruna Costa",
    "inviter_name": "Alan Calheiros",
    "tenancy_display_name": "ATTO",
    "tenancy_path": "datamap/production/atto",
    "dataset_name": "Ozone at ATTO",
    "open_url": "https://datamap.example.org/app/home",
}
CONTEXTS[EmailTemplate.TENANCY_INVITATION_NOTICE] = {
    "inviter_name": "Alan Calheiros",
    "invitee_name": "Bruna Costa",
    "invitee_email": "bruna.costa@usp.br",
    "tenancy_display_name": "ATTO",
    "tenancy_path": "datamap/production/atto",
    "dataset_name": "Ozone at ATTO",
    "tenancy_url": "https://datamap.example.org/app/admin/tenancies?tenancy=datamap/production/atto",
}

TENANCY = frozenset(
    {
        EmailTemplate.TENANCY_REQUEST_RECEIVED,
        EmailTemplate.TENANCY_ACCESS_GRANTED,
        EmailTemplate.TENANCY_REQUEST_DECLINED,
        EmailTemplate.TENANCY_INVITATION,
        EmailTemplate.TENANCY_INVITATION_NOTICE,
    }
)


class TestTenancyTemplates(unittest.TestCase):
    def setUp(self):
        self.renderer = EmailTemplateRenderer(site_url=SITE_URL)

    def render(self, template, **overrides):
        return self.renderer.render(template, {**CONTEXTS[template], **overrides})

    def test_every_tenancy_template_has_a_written_text_part(self):
        for template in TENANCY:
            with self.subTest(template=template):
                self.assertTrue((TEMPLATES_DIR / f"{template.value}.txt").is_file())

    def test_none_claims_to_be_about_a_dataset_you_have_access_to(self):
        for template in TENANCY:
            with self.subTest(template=template):
                email = self.render(template)
                self.assertNotIn("transactional message about a dataset", email.html)
                self.assertNotIn("transactional message about a dataset", email.text)

    def test_the_subjects(self):
        expected = {
            EmailTemplate.TENANCY_REQUEST_RECEIVED: "Tenancy request from Bruna Costa",
            EmailTemplate.TENANCY_ACCESS_GRANTED: "You now have access to ATTO",
            EmailTemplate.TENANCY_REQUEST_DECLINED: "Your request for ATTO",
            EmailTemplate.TENANCY_INVITATION: "Alan Calheiros invited you to ATTO",
            EmailTemplate.TENANCY_INVITATION_NOTICE: "Alan Calheiros invited Bruna Costa to ATTO",
        }
        for template, subject in expected.items():
            with self.subTest(template=template):
                self.assertEqual(self.render(template).subject, subject)

    def test_the_request_lists_who_what_and_why_for_the_admins(self):
        email = self.render(EmailTemplate.TENANCY_REQUEST_RECEIVED)

        for value in (
            "Bruna Costa asked for access to a tenancy.",
            "bruna.costa@usp.br (confirmed)",
            "ATTO",
            "I process the ATTO tower fluxes.",
            "October 5, 2026 at 09:30 UTC",
            "Review request",
            "list of administrators",
        ):
            with self.subTest(value=value):
                self.assertIn(value, email.text)
        self.assertIn('href="https://datamap.example.org/app/admin/requests?request=7d1c"', email.html)

    def test_an_unconfirmed_or_missing_email_says_so(self):
        unconfirmed = self.render(EmailTemplate.TENANCY_REQUEST_RECEIVED, email_confirmed=False)
        missing = self.render(EmailTemplate.TENANCY_REQUEST_RECEIVED, requester_email=None)

        self.assertIn("bruna.costa@usp.br (not confirmed)", unconfirmed.text)
        self.assertIn("No email", missing.text)

    def test_access_granted_names_the_admin_the_path_and_public(self):
        email = self.render(EmailTemplate.TENANCY_ACCESS_GRANTED)

        for value in (
            "Luciana Rizzo gave you access to ATTO on DataMap.",
            "datamap/production/atto",
            "12",
            "Your datasets in Public stay where they are.",
            "Open DataMap",
        ):
            with self.subTest(value=value):
                self.assertIn(value, email.text)

    def test_a_decline_quotes_the_message_only_when_there_is_one(self):
        with_message = self.render(EmailTemplate.TENANCY_REQUEST_DECLINED)
        without = self.renderer.render(
            EmailTemplate.TENANCY_REQUEST_DECLINED,
            {
                key: value
                for key, value in CONTEXTS[EmailTemplate.TENANCY_REQUEST_DECLINED].items()
                if key != "decision_message"
            },
        )

        self.assertIn("An administrator could not give you access to ATTO.", with_message.text)
        self.assertIn("Ask Alan to invite you from a dataset.", with_message.text)
        self.assertIn("You can still work in Public and can send another request.", with_message.text)
        self.assertNotIn("Ask Alan", without.text)

    def test_the_invitation_cannot_accept_for_you(self):
        email = self.render(EmailTemplate.TENANCY_INVITATION)

        self.assertIn(
            "Alan Calheiros invited you to join ATTO on DataMap, from the dataset “Ozone at ATTO”.",
            email.text,
        )
        self.assertIn("Sign in to accept or decline. This email cannot accept for you.", email.text)
        self.assertIn('href="https://datamap.example.org/app/home"', email.html)

    def test_the_admin_notice_says_no_approval_is_needed(self):
        email = self.render(EmailTemplate.TENANCY_INVITATION_NOTICE)

        self.assertIn("No approval is needed.", email.text)
        self.assertIn("remove Bruna Costa later, from Admin › Tenancies", email.text)
        self.assertIn("Open tenancy", email.text)

    def test_a_name_is_escaped_in_html(self):
        email = self.render(EmailTemplate.TENANCY_INVITATION, inviter_name="<b>Alan</b>")

        self.assertNotIn("<b>Alan</b>", email.html)
        self.assertIn("&lt;b&gt;Alan&lt;/b&gt;", email.html)
```

Create `app/service/tenancy_notifier_test.py`:

```python
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.model.tenancy import summary_of
from app.service.email import EmailService
from app.service.tenancy_notifier import TenancyNotifier, admin_addresses

BASE = "https://datamap.pcs.usp.br/"
AT = datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc)
ATTO = summary_of("datamap/production/atto", "ATTO")


def person(name="Bruna Costa", email="bruna@usp.br", verified=True):
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        email=email,
        email_verified_at=AT if verified else None,
    )


class TestAdminAddresses(unittest.TestCase):
    def test_a_comma_separated_list_is_split_and_trimmed(self):
        self.assertEqual(
            admin_addresses(" a@usp.br , b@usp.br,, "), ["a@usp.br", "b@usp.br"]
        )

    def test_an_empty_value_is_nobody(self):
        self.assertEqual(admin_addresses(""), [])


class TestTenancyNotifier(unittest.TestCase):
    def setUp(self):
        self.email = Mock(spec=EmailService)
        self.notifier = TenancyNotifier(
            email_service=self.email,
            admin_emails="admin.one@usp.br, admin.two@usp.br",
            public_base_url=BASE,
        )

    def sent(self) -> list[dict]:
        return [c.kwargs for c in self.email.enqueue.call_args_list]

    def test_every_admin_hears_about_a_request_with_a_key_of_their_own(self):
        requester = person()
        request = SimpleNamespace(
            id=uuid4(), requested_name="ATTO", reason="Fluxes", created_at=AT
        )

        self.notifier.request_received(request, requester)

        sent = self.sent()
        self.assertEqual(
            [s["recipient"] for s in sent], ["admin.one@usp.br", "admin.two@usp.br"]
        )
        self.assertEqual({s["template"] for s in sent}, {"tenancy_request_received"})
        self.assertEqual(
            sent[0]["context"],
            {
                "requester_name": "Bruna Costa",
                "requester_email": "bruna@usp.br",
                "email_confirmed": True,
                "requested_name": "ATTO",
                "reason": "Fluxes",
                "requested_at": "October 5, 2026 at 09:30 UTC",
                "review_url": f"https://datamap.pcs.usp.br/app/admin/requests?request={request.id}",
            },
        )
        self.assertEqual(len({s["dedup_key"] for s in sent}), 2)
        self.assertTrue(
            sent[0]["dedup_key"].startswith(f"tenancy_request_received:{request.id}:")
        )
        self.assertEqual(sent[0]["related_type"], "tenancy_request")
        self.assertEqual(sent[0]["related_id"], request.id)

    def test_nobody_is_told_when_the_list_is_empty(self):
        notifier = TenancyNotifier(self.email, "", BASE)
        request = SimpleNamespace(id=uuid4(), requested_name="ATTO", reason="r", created_at=AT)

        notifier.request_received(request, person())
        notifier.invitation_notice(person(), "Alan", ATTO, "Ozone", uuid4())

        self.email.enqueue.assert_not_called()

    def test_access_granted_goes_to_the_user_keyed_by_the_event(self):
        user, event_id = person(), uuid4()

        self.notifier.access_granted(user, "Luciana Rizzo", ATTO, 12, event_id)

        (sent,) = self.sent()
        self.assertEqual(sent["recipient"], "bruna@usp.br")
        self.assertEqual(sent["template"], "tenancy_access_granted")
        self.assertEqual(sent["dedup_key"], f"tenancy_access_granted:{event_id}")
        self.assertEqual(
            sent["context"],
            {
                "user_name": "Bruna Costa",
                "admin_name": "Luciana Rizzo",
                "tenancy_display_name": "ATTO",
                "tenancy_path": "datamap/production/atto",
                "datasets_count": 12,
                "open_url": "https://datamap.pcs.usp.br/app/tenancy",
            },
        )

    def test_a_decline_carries_the_message_or_null(self):
        user = person()
        request = SimpleNamespace(id=uuid4(), requested_name="ATTO", decision_message=None)

        self.notifier.request_declined(user, request)

        (sent,) = self.sent()
        self.assertEqual(sent["template"], "tenancy_request_declined")
        self.assertIsNone(sent["context"]["decision_message"])
        self.assertEqual(sent["dedup_key"], f"tenancy_request_declined:{request.id}")

    def test_the_invitee_and_every_admin_hear_about_an_invitation(self):
        invitee, invitation_id = person(), uuid4()

        self.notifier.invitation(invitee, "Alan Calheiros", ATTO, "Ozone at ATTO", invitation_id)
        self.notifier.invitation_notice(invitee, "Alan Calheiros", ATTO, "Ozone at ATTO", invitation_id)

        sent = self.sent()
        self.assertEqual(
            [s["template"] for s in sent],
            ["tenancy_invitation", "tenancy_invitation_notice", "tenancy_invitation_notice"],
        )
        self.assertEqual(sent[0]["dedup_key"], f"tenancy_invitation:{invitation_id}")
        self.assertEqual(sent[0]["context"]["open_url"], "https://datamap.pcs.usp.br/app/home")
        self.assertEqual(
            sent[1]["context"]["tenancy_url"],
            "https://datamap.pcs.usp.br/app/admin/tenancies?tenancy=datamap/production/atto",
        )
        self.assertEqual(sent[1]["context"]["invitee_email"], "bruna@usp.br")

    def test_a_user_without_an_email_is_skipped(self):
        self.notifier.access_granted(person(email=None), "Luciana", ATTO, 1, uuid4())
        self.notifier.invitation(person(email=None), "Alan", ATTO, "Ozone", uuid4())

        self.email.enqueue.assert_not_called()

    def test_no_message_carries_a_secret(self):
        self.notifier.access_granted(person(), "Luciana", ATTO, 1, uuid4())

        self.assertNotIn("secret_fields", self.sent()[0])

    def test_a_failure_to_queue_is_logged_not_raised(self):
        self.email.enqueue.side_effect = RuntimeError("database gone")

        with self.assertLogs("service:TenancyNotifier", level="ERROR"):
            self.notifier.access_granted(person(), "Luciana", ATTO, 1, uuid4())
```

- [ ] **Step 2: Run them and see them fail**

```bash
$PY -m pytest app/service/email_template_test.py app/service/tenancy_notifier_test.py -q -p no:cacheprovider
```

Expected: `AttributeError: TENANCY_REQUEST_RECEIVED` at import of the template test and `ModuleNotFoundError: No module named 'app.service.tenancy_notifier'`.

- [ ] **Step 3: Register the templates**

In `app/service/email_template.py`, replace

```python
    SIGN_UP_EXISTING_ACCOUNT = "sign_up_existing_account"
```

with

```python
    SIGN_UP_EXISTING_ACCOUNT = "sign_up_existing_account"
    TENANCY_REQUEST_RECEIVED = "tenancy_request_received"
    TENANCY_ACCESS_GRANTED = "tenancy_access_granted"
    TENANCY_REQUEST_DECLINED = "tenancy_request_declined"
    TENANCY_INVITATION = "tenancy_invitation"
    TENANCY_INVITATION_NOTICE = "tenancy_invitation_notice"
```

and replace

```python
        "anonymous_link_count": 0,
        "shared_by_name": None,
    },
}
```

(the end of the `EMBARGO_ENDED` entry and of `_OPTIONAL_DEFAULTS`) with

```python
        "anonymous_link_count": 0,
        "shared_by_name": None,
    },
    EmailTemplate.TENANCY_REQUEST_DECLINED: {"decision_message": None},
}
```

- [ ] **Step 4: Write the templates**

`app/resources/email_templates/tenancy_request_received.html`:

```html
{% extends "base.html" %}
{% import "_macros.html" as m %}
{% block title %}Tenancy request from {{ requester_name }}{% endblock %}
{% block preheader %}{{ requester_name }} asked for access to {{ requested_name }}.{% endblock %}
{% block label %}Tenancy request{% endblock %}
{% block content %}
{{ m.heading("A tenancy request is waiting") }}
{% call m.paragraph() %}{{ m.strong(requester_name) }} asked for access to a tenancy.{% endcall %}
{{ m.details([{"label": "Name", "value": requester_name}, {"label": "Email", "value": (requester_email or "No email") ~ (" (confirmed)" if email_confirmed else " (not confirmed)")}, {"label": "Tenancy asked for", "value": requested_name}, {"label": "Why", "value": reason}, {"label": "Requested", "value": requested_at}]) }}
{{ m.button("Review request", review_url) }}
{% endblock %}
{% block reason %}You received this email because your address is on DataMap's list of administrators.{% endblock %}
```

`app/resources/email_templates/tenancy_request_received.txt`:

```
{% extends "base.txt" %}
{% block content %}
{{ requester_name }} asked for access to a tenancy.

Name: {{ requester_name }}
Email: {{ requester_email or "No email" }} ({{ "confirmed" if email_confirmed else "not confirmed" }})
Tenancy asked for: {{ requested_name }}
Why: {{ reason }}
Requested: {{ requested_at }}

Review request: {{ review_url }}
{% endblock %}
{% block reason %}You received this email because your address is on DataMap's list of administrators.{% endblock %}
```

`app/resources/email_templates/tenancy_access_granted.html`:

```html
{% extends "base.html" %}
{% import "_macros.html" as m %}
{% block title %}You now have access to {{ tenancy_display_name }}{% endblock %}
{% block preheader %}{{ admin_name }} gave you access to {{ tenancy_display_name }}.{% endblock %}
{% block label %}Tenancy{% endblock %}
{% block content %}
{{ m.heading("You have a new tenancy") }}
{% call m.paragraph() %}Hi {{ user_name }}, {{ admin_name }} gave you access to {{ m.strong(tenancy_display_name) }} on DataMap.{% endcall %}
{{ m.details([{"label": "Tenancy", "value": tenancy_display_name ~ " · " ~ tenancy_path}, {"label": "Datasets", "value": datasets_count|string}]) }}
{% call m.paragraph() %}Your datasets in Public stay where they are.{% endcall %}
{{ m.button("Open DataMap", open_url) }}
{% endblock %}
{% block reason %}You received this email because an administrator gave your DataMap account access to a tenancy.{% endblock %}
```

`app/resources/email_templates/tenancy_access_granted.txt`:

```
{% extends "base.txt" %}
{% block content %}
Hi {{ user_name }},

{{ admin_name }} gave you access to {{ tenancy_display_name }} on DataMap.

Tenancy: {{ tenancy_display_name }} ({{ tenancy_path }})
Datasets: {{ datasets_count }}

Your datasets in Public stay where they are.

Open DataMap: {{ open_url }}
{% endblock %}
{% block reason %}You received this email because an administrator gave your DataMap account access to a tenancy.{% endblock %}
```

`app/resources/email_templates/tenancy_request_declined.html`:

```html
{% extends "base.html" %}
{% import "_macros.html" as m %}
{% block title %}Your request for {{ requested_name }}{% endblock %}
{% block preheader %}An administrator answered your request for {{ requested_name }}.{% endblock %}
{% block label %}Tenancy request{% endblock %}
{% block content %}
{{ m.heading("Your request was not approved") }}
{% call m.paragraph() %}Hi {{ user_name }}, an administrator could not give you access to {{ m.strong(requested_name) }}.{% endcall %}
{% if decision_message %}
{% call m.note(bottom=16) %}“{{ decision_message }}”{% endcall %}
{% endif %}
{% call m.paragraph() %}You can still work in Public and can send another request.{% endcall %}
{{ m.button("Open DataMap", open_url) }}
{% endblock %}
{% block reason %}You received this email because you asked for access to a tenancy on DataMap.{% endblock %}
```

`app/resources/email_templates/tenancy_request_declined.txt`:

```
{% extends "base.txt" %}
{% block content %}
Hi {{ user_name }},

An administrator could not give you access to {{ requested_name }}.
{% if decision_message %}

“{{ decision_message }}”
{% endif %}

You can still work in Public and can send another request.

Open DataMap: {{ open_url }}
{% endblock %}
{% block reason %}You received this email because you asked for access to a tenancy on DataMap.{% endblock %}
```

`app/resources/email_templates/tenancy_invitation.html`:

```html
{% extends "base.html" %}
{% import "_macros.html" as m %}
{% block title %}{{ inviter_name }} invited you to {{ tenancy_display_name }}{% endblock %}
{% block preheader %}Sign in to accept or decline.{% endblock %}
{% block label %}Invitation{% endblock %}
{% block content %}
{{ m.heading("You are invited to a tenancy") }}
{% call m.paragraph() %}Hi {{ invitee_name }}, {{ inviter_name }} invited you to join {{ m.strong(tenancy_display_name) }} on DataMap, from the dataset “{{ dataset_name }}”.{% endcall %}
{{ m.details([{"label": "Tenancy", "value": tenancy_display_name ~ " · " ~ tenancy_path}, {"label": "Dataset", "value": dataset_name}]) }}
{% call m.paragraph() %}Sign in to accept or decline. This email cannot accept for you.{% endcall %}
{{ m.button("Open DataMap", open_url) }}
{% endblock %}
{% block reason %}You received this email because someone invited your DataMap account to a tenancy.{% endblock %}
```

`app/resources/email_templates/tenancy_invitation.txt`:

```
{% extends "base.txt" %}
{% block content %}
Hi {{ invitee_name }},

{{ inviter_name }} invited you to join {{ tenancy_display_name }} on DataMap, from the dataset “{{ dataset_name }}”.

Tenancy: {{ tenancy_display_name }} ({{ tenancy_path }})

Sign in to accept or decline. This email cannot accept for you.

Open DataMap: {{ open_url }}
{% endblock %}
{% block reason %}You received this email because someone invited your DataMap account to a tenancy.{% endblock %}
```

`app/resources/email_templates/tenancy_invitation_notice.html`:

```html
{% extends "base.html" %}
{% import "_macros.html" as m %}
{% block title %}{{ inviter_name }} invited {{ invitee_name }} to {{ tenancy_display_name }}{% endblock %}
{% block preheader %}No approval is needed.{% endblock %}
{% block label %}Tenancy invitation{% endblock %}
{% block content %}
{{ m.heading("A member invited someone to a tenancy") }}
{{ m.details([{"label": "Inviter", "value": inviter_name}, {"label": "Invitee", "value": invitee_name ~ " · " ~ (invitee_email or "No email")}, {"label": "Tenancy", "value": tenancy_display_name ~ " · " ~ tenancy_path}, {"label": "Dataset", "value": dataset_name}]) }}
{% call m.paragraph() %}No approval is needed. You can withdraw it, or remove {{ invitee_name }} later, from Admin › Tenancies.{% endcall %}
{{ m.button("Open tenancy", tenancy_url) }}
{% endblock %}
{% block reason %}You received this email because your address is on DataMap's list of administrators.{% endblock %}
```

`app/resources/email_templates/tenancy_invitation_notice.txt`:

```
{% extends "base.txt" %}
{% block content %}
{{ inviter_name }} invited {{ invitee_name }} to {{ tenancy_display_name }}.

Inviter: {{ inviter_name }}
Invitee: {{ invitee_name }} ({{ invitee_email or "No email" }})
Tenancy: {{ tenancy_display_name }} ({{ tenancy_path }})
Dataset: {{ dataset_name }}

No approval is needed. You can withdraw it, or remove {{ invitee_name }} later, from Admin › Tenancies.

Open tenancy: {{ tenancy_url }}
{% endblock %}
{% block reason %}You received this email because your address is on DataMap's list of administrators.{% endblock %}
```

In `app/resources/email_templates/README.md`, replace

```
| `sign_up_existing_account` | `name`, `link` | |
```

with

```
| `sign_up_existing_account` | `name`, `link` | |
| `tenancy_request_received` | `requester_name`, `requester_email`, `email_confirmed`, `requested_name`, `reason`, `requested_at`, `review_url` | |
| `tenancy_access_granted` | `user_name`, `admin_name`, `tenancy_display_name`, `tenancy_path`, `datasets_count`, `open_url` | |
| `tenancy_request_declined` | `user_name`, `requested_name`, `open_url` | `decision_message` |
| `tenancy_invitation` | `invitee_name`, `inviter_name`, `tenancy_display_name`, `tenancy_path`, `dataset_name`, `open_url` | |
| `tenancy_invitation_notice` | `inviter_name`, `invitee_name`, `invitee_email`, `tenancy_display_name`, `tenancy_path`, `dataset_name`, `tenancy_url` | |
```

- [ ] **Step 5: Write the notifier**

Create `app/service/tenancy_notifier.py`:

```python
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
```

The tenancy path goes into the query string unencoded: the contract sends tenancy segments unencoded everywhere, and `/` is legal in a query.

- [ ] **Step 6: Run them and see them pass**

```bash
$PY -m pytest app/service/email_template_test.py app/service/tenancy_notifier_test.py -q -p no:cacheprovider
```

Expected: all pass, including the existing generic tests (`test_every_template_renders_with_its_context`, the footer tests) over the five new templates.

- [ ] **Step 7: Commit**

```bash
pwd && command git branch --show-current
command git add app/service/email_template.py app/service/email_template_test.py app/resources/email_templates app/service/tenancy_notifier.py app/service/tenancy_notifier_test.py
command git commit -m "feat: tenancy request, access, decline and invitation emails (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 8: Membership persistence, `TenancyMembershipService` and the public lock on `/tenancies`

**Files:**
- Modify: `app/repository/tenancy.py`
- Create: `app/repository/tenancy_membership.py`
- Modify: `app/repository/user.py`
- Create: `app/service/tenancy_membership.py`
- Modify: `app/service/tenancy.py`
- Modify: `app/container.py`
- Test: `app/service/tenancy_membership_test.py`, `app/service/tenancy_test.py`

**Interfaces:**
- Consumes: `add_event` (Task 5), `TenancyNotifier` (Task 7), model helpers (Task 2).
- Produces (`TenancyRepository`): `fetch_any(tenancy) -> Tenancy | None` (enabled or not), `list_all() -> list[Tenancy]`, `create_with_event(name, display_name, actor_id) -> Tenancy` (`ConflictException("tenancy_exists")` on a duplicate), `member_counts() -> dict[str, int]` (enabled users), `dataset_counts() -> dict[str, int]` (enabled datasets), `count_datasets(tenancy) -> int`.
- Produces (`app/repository/tenancy_membership.py`): `insert_membership(session, user_id, tenancy) -> bool` (`False` when already a member); `TenancyMembershipRepository` with `is_member(user_id, tenancy) -> bool`, `tenancies_of(user_id) -> list[Tenancy]` (enabled), `count(tenancy) -> int` (enabled users), `list_members(tenancy, limit, offset) -> tuple[list[User], int]` (enabled users by name), `added_at(tenancy, user_ids) -> dict[UUID, datetime]` (latest `member_added`), `inviters(tenancy, user_ids) -> dict[UUID, UUID]` (inviter of the latest accepted invitation), `removal_counts(tenancy, user_id) -> tuple[int, int, int]` (datasets in the tenancy, of those shared with the user, of those owned by the user), `add(tenancy, user_id, actor_id) -> UUID | None` (the `member_added` event id, `None` if already a member), `remove(tenancy, user_id, actor_id) -> bool` (also revokes accepted invitations and writes `member_removed`).
- Produces (`app/repository/user.py`): `user_matches(term)` SQL predicate on name, email or ORCID iD (case-insensitive substring); `UserRepository.fetch_any_by_id(id) -> User | None`; `UserRepository.search_admin(term, limit=10) -> list[User]` (enabled only, by name).
- Produces (`app/service/tenancy_membership.py`): `TenancyMembershipService(tenancies, memberships, users, notifier)` with `summary(path) -> TenancySummary`, `summaries_for(user_id) -> list[TenancySummary]` (shared order), `require_open_for_members(path) -> Tenancy` (404 `tenancy_not_found`, 409 `public_tenancy_locked`, `legacy_tenancy_read_only`, `tenancy_disabled` — in that order), `check_new_tenancy(display_name, namespace) -> tuple[str, str]` (400 `namespace_invalid`, `display_name_invalid`, 409 `tenancy_exists`, `display_name_taken` — in that order), `display_name_taken(name) -> bool`, `announce_access(user_id, admin_id, path, event_id) -> None`.
- Produces: `TenancyService.update` and `TenancyService.disable` raise `ConflictException("public_tenancy_locked")` for `DEFAULT_TENANCY`.

The repositories are exercised against PostgreSQL by the integration tests of Tasks 14–17; their unit coverage here is through the services, with the repositories mocked (CLAUDE.md: query shape is only visible to integration tests).

- [ ] **Step 1: Write the failing tests**

Create `app/service/tenancy_membership_test.py`:

```python
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.model.tenancy import DEFAULT_TENANCY, summary_of
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.user import UserRepository
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_notifier import TenancyNotifier

ATTO = "datamap/production/atto"


def row(name, display_name=None, is_enabled=True):
    return SimpleNamespace(name=name, display_name=display_name, is_enabled=is_enabled)


class MembershipServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.tenancies = Mock(spec=TenancyRepository)
        self.memberships = Mock(spec=TenancyMembershipRepository)
        self.users = Mock(spec=UserRepository)
        self.notifier = Mock(spec=TenancyNotifier)
        self.rows = {
            DEFAULT_TENANCY: row(DEFAULT_TENANCY, "Public"),
            ATTO: row(ATTO, "ATTO"),
            "datamap/production/lba": row("datamap/production/lba"),
            "datamap/production/old": row("datamap/production/old", "Old", False),
            "datamap/staging/data-amazon": row("datamap/staging/data-amazon"),
        }
        self.tenancies.fetch_any.side_effect = self.rows.get
        self.tenancies.list_all.return_value = list(self.rows.values())
        self.service = TenancyMembershipService(
            tenancies=self.tenancies,
            memberships=self.memberships,
            users=self.users,
            notifier=self.notifier,
        )


class TestSummaries(MembershipServiceTestCase):
    def test_a_summary_reads_the_column_or_derives_the_name(self):
        self.assertEqual(self.service.summary(ATTO), summary_of(ATTO, "ATTO"))
        self.assertEqual(self.service.summary("datamap/production/lba").display_name, "Lba")
        self.assertEqual(self.service.summary("datamap/production/gone").display_name, "Gone")

    def test_a_users_tenancies_come_in_the_shared_order(self):
        self.memberships.tenancies_of.return_value = [
            self.rows["datamap/staging/data-amazon"],
            self.rows["datamap/production/lba"],
            self.rows[DEFAULT_TENANCY],
            self.rows[ATTO],
        ]

        paths = [s.path for s in self.service.summaries_for(uuid4())]

        self.assertEqual(
            paths,
            [DEFAULT_TENANCY, ATTO, "datamap/production/lba", "datamap/staging/data-amazon"],
        )


class TestOpenForMembers(MembershipServiceTestCase):
    def refused(self, path) -> str:
        with self.assertRaises((NotFoundException, ConflictException)) as raised:
            self.service.require_open_for_members(path)
        return str(raised.exception)

    def test_the_codes_in_order(self):
        self.assertEqual(self.refused("datamap/production/none"), "tenancy_not_found")
        self.assertEqual(self.refused(DEFAULT_TENANCY), "public_tenancy_locked")
        self.assertEqual(self.refused("datamap/staging/data-amazon"), "legacy_tenancy_read_only")
        self.assertEqual(self.refused("datamap/production/old"), "tenancy_disabled")

    def test_an_enabled_production_tenancy_is_open(self):
        self.assertIs(self.service.require_open_for_members(ATTO), self.rows[ATTO])


class TestNewTenancy(MembershipServiceTestCase):
    def code(self, display_name, namespace) -> str:
        with self.assertRaises((IllegalStateException, ConflictException)) as raised:
            self.service.check_new_tenancy(display_name, namespace)
        return str(raised.exception)

    def test_a_valid_one_gives_its_path_and_trimmed_name(self):
        self.assertEqual(
            self.service.check_new_tenancy("  Cerrado Flux ", " cerrado-flux "),
            ("datamap/production/cerrado-flux", "Cerrado Flux"),
        )

    def test_the_namespace_is_checked_first(self):
        self.assertEqual(self.code("", "Bad NS"), "namespace_invalid")
        self.assertEqual(self.code("Public", "public"), "namespace_invalid")

    def test_then_the_display_name(self):
        self.assertEqual(self.code("   ", "fine"), "display_name_invalid")
        self.assertEqual(self.code("x" * 65, "fine"), "display_name_invalid")

    def test_an_existing_path_enabled_or_not_is_taken(self):
        self.assertEqual(self.code("Anything", "old"), "tenancy_exists")
        self.assertEqual(self.code("Anything", "atto"), "tenancy_exists")

    def test_a_display_name_is_unique_among_enabled_production_case_insensitively(self):
        self.assertEqual(self.code("atto", "atto-2"), "display_name_taken")
        self.assertEqual(self.code("LBA", "lba-2"), "display_name_taken")
        self.assertEqual(
            self.service.check_new_tenancy("Old", "old-2"),
            ("datamap/production/old-2", "Old"),
        )
        self.assertEqual(
            self.service.check_new_tenancy("Data Amazon", "data-amazon-2"),
            ("datamap/production/data-amazon-2", "Data Amazon"),
        )


class TestAnnounceAccess(MembershipServiceTestCase):
    def test_the_user_is_told_who_gave_access_and_how_many_datasets_there_are(self):
        user = SimpleNamespace(id=uuid4(), name="Bruna", email="b@usp.br")
        admin = SimpleNamespace(id=uuid4(), name="Luciana Rizzo", email="l@usp.br")
        self.users.fetch_any_by_id.side_effect = {user.id: user, admin.id: admin}.get
        self.tenancies.count_datasets.return_value = 7
        event_id = uuid4()

        self.service.announce_access(user.id, admin.id, ATTO, event_id)

        self.notifier.access_granted.assert_called_once_with(
            user, "Luciana Rizzo", summary_of(ATTO, "ATTO"), 7, event_id
        )

    def test_an_unknown_admin_reads_as_an_administrator(self):
        user = SimpleNamespace(id=uuid4(), name="Bruna", email="b@usp.br")
        self.users.fetch_any_by_id.side_effect = {user.id: user}.get
        self.tenancies.count_datasets.return_value = 0

        self.service.announce_access(user.id, uuid4(), ATTO, uuid4())

        self.assertEqual(self.notifier.access_granted.call_args.args[1], "An administrator")
```

Append to `app/service/tenancy_test.py`:

```python


class TestPublicIsLocked(unittest.TestCase):
    def setUp(self):
        self.repository = Mock(spec=TenancyRepository)
        self.service = TenancyService(self.repository)

    def test_public_cannot_be_renamed_or_changed(self):
        with self.assertRaises(ConflictException) as raised:
            self.service.update(DEFAULT_TENANCY, Tenancy(name="x", is_enabled=True))

        self.assertEqual(str(raised.exception), "public_tenancy_locked")
        self.repository.upsert.assert_not_called()

    def test_public_cannot_be_disabled(self):
        with self.assertRaises(ConflictException) as raised:
            self.service.disable(DEFAULT_TENANCY)

        self.assertEqual(str(raised.exception), "public_tenancy_locked")
        self.repository.upsert.assert_not_called()
```

and in its imports replace

```python
from app.exception.not_found import NotFoundException
from app.service.tenancy import TenancyService
```

with

```python
from app.exception.conflict import ConflictException
from app.exception.not_found import NotFoundException
from app.model.tenancy import DEFAULT_TENANCY
from app.service.tenancy import TenancyService
```

- [ ] **Step 2: Run them and see them fail**

```bash
$PY -m pytest app/service/tenancy_membership_test.py app/service/tenancy_test.py -q -p no:cacheprovider
```

Expected: `ModuleNotFoundError: No module named 'app.repository.tenancy_membership'` for the first file; in the second, `test_public_cannot_be_renamed_or_changed` and `test_public_cannot_be_disabled` fail (`ConflictException` not raised).

- [ ] **Step 3: Implement the repositories**

In `app/repository/tenancy.py`, replace

```python
from app.exception.conflict import ConflictException
from sqlalchemy.exc import IntegrityError
from app.model.db.tenancy import Tenancy
from contextlib import AbstractContextManager
from sqlalchemy.orm import Session
from typing import Callable, List
```

with

```python
from contextlib import AbstractContextManager
from typing import Callable, List
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import true

from app.exception.conflict import ConflictException
from app.model.db.dataset import Dataset
from app.model.db.tenancy import Tenancy
from app.model.db.user import User, user_tenancy_association
from app.model.tenancy import TenancyEventType
from app.repository.tenancy_event import add_event
```

and replace

```python
        except IntegrityError:
            raise ConflictException(f"tenancy_already_exists: {tenancy.name}")
```

with

```python
        except IntegrityError:
            raise ConflictException(f"tenancy_already_exists: {tenancy.name}")

    def fetch_any(self, tenancy: str) -> Tenancy | None:
        with self._session_factory() as session:
            return session.query(Tenancy).filter_by(name=tenancy).first()

    def list_all(self) -> List[Tenancy]:
        with self._session_factory() as session:
            return session.query(Tenancy).all()

    def create_with_event(
        self, name: str, display_name: str, actor_id: UUID
    ) -> Tenancy:
        try:
            with self._session_factory() as session:
                tenancy = Tenancy(name=name, display_name=display_name, is_enabled=True)
                session.add(tenancy)
                session.flush()
                add_event(
                    session,
                    tenancy=name,
                    event_type=TenancyEventType.TENANCY_CREATED,
                    actor_id=actor_id,
                )
                session.commit()
                session.refresh(tenancy)
                return tenancy
        except IntegrityError:
            raise ConflictException("tenancy_exists")

    def member_counts(self) -> dict[str, int]:
        with self._session_factory() as session:
            rows = (
                session.query(user_tenancy_association.c.tenancy, func.count(User.id))
                .select_from(user_tenancy_association)
                .join(User, User.id == user_tenancy_association.c.user_id)
                .filter(User.is_enabled == true())
                .group_by(user_tenancy_association.c.tenancy)
                .all()
            )
            return {tenancy: count for tenancy, count in rows}

    def dataset_counts(self) -> dict[str, int]:
        with self._session_factory() as session:
            rows = (
                session.query(Dataset.tenancy, func.count(Dataset.id))
                .filter(Dataset.is_enabled == true(), Dataset.tenancy.isnot(None))
                .group_by(Dataset.tenancy)
                .all()
            )
            return {tenancy: count for tenancy, count in rows}

    def count_datasets(self, tenancy: str) -> int:
        with self._session_factory() as session:
            return (
                session.query(func.count(Dataset.id))
                .filter(Dataset.tenancy == tenancy, Dataset.is_enabled == true())
                .scalar()
            )
```

Create `app/repository/tenancy_membership.py`:

```python
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import true

from app.model.db.dataset import Dataset
from app.model.db.dataset_access import DatasetPermission
from app.model.db.tenancy import Tenancy, TenancyEvent, TenancyInvitation
from app.model.db.user import User, user_tenancy_association
from app.model.tenancy import TenancyEventType, TenancyInvitationStatus
from app.repository.tenancy_event import add_event

_member = user_tenancy_association.c


def insert_membership(session: Session, user_id: UUID, tenancy: str) -> bool:
    result = session.execute(
        pg_insert(user_tenancy_association)
        .values(user_id=user_id, tenancy=tenancy)
        .on_conflict_do_nothing()
    )
    return result.rowcount == 1


class TenancyMembershipRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def is_member(self, user_id: UUID, tenancy: str) -> bool:
        with self._session_factory() as session:
            return (
                session.query(_member.user_id)
                .filter(_member.user_id == user_id, _member.tenancy == tenancy)
                .first()
                is not None
            )

    def tenancies_of(self, user_id: UUID) -> list[Tenancy]:
        with self._session_factory() as session:
            return (
                session.query(Tenancy)
                .join(user_tenancy_association, _member.tenancy == Tenancy.name)
                .filter(_member.user_id == user_id, Tenancy.is_enabled == true())
                .all()
            )

    def _members(self, session: Session, tenancy: str):
        return (
            session.query(User)
            .join(user_tenancy_association, _member.user_id == User.id)
            .filter(_member.tenancy == tenancy, User.is_enabled == true())
        )

    def count(self, tenancy: str) -> int:
        with self._session_factory() as session:
            return self._members(session, tenancy).count()

    def list_members(
        self, tenancy: str, limit: int, offset: int
    ) -> tuple[list[User], int]:
        with self._session_factory() as session:
            query = self._members(session, tenancy)
            total = query.count()
            users = (
                query.order_by(func.lower(User.name), User.id)
                .limit(limit)
                .offset(offset)
                .all()
            )
            return users, total

    def added_at(self, tenancy: str, user_ids: list[UUID]) -> dict[UUID, datetime]:
        if not user_ids:
            return {}
        with self._session_factory() as session:
            rows = (
                session.query(TenancyEvent.user_id, func.max(TenancyEvent.created_at))
                .filter(
                    TenancyEvent.tenancy == tenancy,
                    TenancyEvent.event_type == TenancyEventType.MEMBER_ADDED,
                    TenancyEvent.user_id.in_(user_ids),
                )
                .group_by(TenancyEvent.user_id)
                .all()
            )
            return {user_id: at for user_id, at in rows}

    def inviters(self, tenancy: str, user_ids: list[UUID]) -> dict[UUID, UUID]:
        if not user_ids:
            return {}
        with self._session_factory() as session:
            rows = (
                session.query(TenancyInvitation.user_id, TenancyInvitation.invited_by)
                .filter(
                    TenancyInvitation.tenancy == tenancy,
                    TenancyInvitation.status == TenancyInvitationStatus.ACCEPTED,
                    TenancyInvitation.user_id.in_(user_ids),
                )
                .order_by(TenancyInvitation.closed_at.asc())
                .all()
            )
            return {
                user_id: invited_by
                for user_id, invited_by in rows
                if invited_by is not None
            }

    def removal_counts(self, tenancy: str, user_id: UUID) -> tuple[int, int, int]:
        with self._session_factory() as session:
            in_tenancy = session.query(func.count(Dataset.id)).filter(
                Dataset.tenancy == tenancy, Dataset.is_enabled == true()
            )
            shared = (
                session.query(func.count(DatasetPermission.dataset_id))
                .join(Dataset, Dataset.id == DatasetPermission.dataset_id)
                .filter(
                    Dataset.tenancy == tenancy,
                    Dataset.is_enabled == true(),
                    DatasetPermission.user_id == user_id,
                )
            )
            owned = in_tenancy.filter(Dataset.owner_id == user_id)
            return in_tenancy.scalar(), shared.scalar(), owned.scalar()

    def add(self, tenancy: str, user_id: UUID, actor_id: UUID) -> UUID | None:
        with self._session_factory() as session:
            if not insert_membership(session, user_id, tenancy):
                return None
            event = add_event(
                session,
                tenancy=tenancy,
                event_type=TenancyEventType.MEMBER_ADDED,
                user_id=user_id,
                actor_id=actor_id,
            )
            event_id = event.id
            session.commit()
            return event_id

    def remove(self, tenancy: str, user_id: UUID, actor_id: UUID) -> bool:
        with self._session_factory() as session:
            deleted = session.execute(
                user_tenancy_association.delete().where(
                    _member.user_id == user_id, _member.tenancy == tenancy
                )
            ).rowcount
            if deleted == 0:
                session.rollback()
                return False
            session.query(TenancyInvitation).filter(
                TenancyInvitation.tenancy == tenancy,
                TenancyInvitation.user_id == user_id,
                TenancyInvitation.status == TenancyInvitationStatus.ACCEPTED,
            ).update(
                {
                    TenancyInvitation.status: TenancyInvitationStatus.REVOKED,
                    TenancyInvitation.closed_by: actor_id,
                    TenancyInvitation.closed_at: func.now(),
                },
                synchronize_session=False,
            )
            add_event(
                session,
                tenancy=tenancy,
                event_type=TenancyEventType.MEMBER_REMOVED,
                user_id=user_id,
                actor_id=actor_id,
            )
            session.commit()
            return True
```

`remove` overwrites `closed_by`/`closed_at` of the accepted invitation with the removing admin and time: the RFC says "the removal is the revocation", and the accepting user's `closed_by` is already in the `invitation_accepted` event. `inviters` orders by `closed_at` so the latest accepted invitation wins.

In `app/repository/user.py`, replace

```python
from sqlalchemy import case, func, or_, update
```

with

```python
from sqlalchemy import case, func, or_, select, update
```

replace

```python
def _by_provider(session: Session, provider_name: str, reference: str) -> Query:
```

with

```python
def user_matches(term: str):
    pattern = like_pattern(term)
    orcid_holders = (
        select(user_provider_association.c.user_id)
        .join(Provider, Provider.id == user_provider_association.c.provider_id)
        .where(Provider.name == "orcid", Provider.reference.ilike(pattern, escape="\\"))
    )
    return or_(
        User.name.ilike(pattern, escape="\\"),
        User.email.ilike(pattern, escape="\\"),
        User.id.in_(orcid_holders),
    )


def _by_provider(session: Session, provider_name: str, reference: str) -> Query:
```

and replace

```python
    def search(self, query_params: UserQuery) -> List[User]:
```

with

```python
    def fetch_any_by_id(self, id: UUID) -> User | None:
        with self._session_factory() as session:
            return session.query(User).filter_by(id=id).first()

    def search_admin(self, term: str, limit: int = 10) -> List[User]:
        with self._session_factory() as session:
            return (
                session.query(User)
                .filter(User.is_enabled == true(), user_matches(term))
                .order_by(func.lower(User.name), User.id)
                .limit(limit)
                .all()
            )

    def search(self, query_params: UserQuery) -> List[User]:
```

- [ ] **Step 4: Implement the services**

Create `app/service/tenancy_membership.py`:

```python
from uuid import UUID

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.model.db.tenancy import Tenancy as TenancyDBModel
from app.model.tenancy import (
    DISPLAY_NAME_MAX_LENGTH,
    PRODUCTION_PREFIX,
    TenancySummary,
    display_name_of,
    is_default,
    is_legacy,
    is_production,
    namespace_is_valid,
    summary_of,
    tenancy_order,
    trimmed_within,
)
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.user import UserRepository
from app.service.tenancy_notifier import TenancyNotifier


class TenancyMembershipService:
    def __init__(
        self,
        tenancies: TenancyRepository,
        memberships: TenancyMembershipRepository,
        users: UserRepository,
        notifier: TenancyNotifier,
    ) -> None:
        self._tenancies = tenancies
        self._memberships = memberships
        self._users = users
        self._notifier = notifier

    def summary(self, path: str) -> TenancySummary:
        row = self._tenancies.fetch_any(path)
        return summary_of(path, row.display_name if row else None)

    def summaries_for(self, user_id: UUID) -> list[TenancySummary]:
        summaries = [
            summary_of(row.name, row.display_name)
            for row in self._memberships.tenancies_of(user_id)
        ]
        return sorted(summaries, key=lambda s: tenancy_order(s.path, s.display_name))

    def require_open_for_members(self, path: str) -> TenancyDBModel:
        row = self._tenancies.fetch_any(path)
        if row is None:
            raise NotFoundException("tenancy_not_found")
        if is_default(path):
            raise ConflictException("public_tenancy_locked")
        if is_legacy(path):
            raise ConflictException("legacy_tenancy_read_only")
        if not row.is_enabled or not is_production(path):
            raise ConflictException("tenancy_disabled")
        return row

    def check_new_tenancy(self, display_name: str, namespace: str) -> tuple[str, str]:
        slug = (namespace or "").strip()
        if not namespace_is_valid(slug):
            raise IllegalStateException("namespace_invalid")
        name = trimmed_within(display_name, 1, DISPLAY_NAME_MAX_LENGTH)
        if name is None:
            raise IllegalStateException("display_name_invalid")
        path = PRODUCTION_PREFIX + slug
        if self._tenancies.fetch_any(path) is not None:
            raise ConflictException("tenancy_exists")
        if self.display_name_taken(name):
            raise ConflictException("display_name_taken")
        return path, name

    def display_name_taken(self, name: str) -> bool:
        wanted = name.casefold()
        return any(
            display_name_of(row.name, row.display_name).casefold() == wanted
            for row in self._tenancies.list_all()
            if row.is_enabled and is_production(row.name)
        )

    def announce_access(
        self, user_id: UUID, admin_id: UUID, path: str, event_id: UUID
    ) -> None:
        user = self._users.fetch_any_by_id(user_id)
        if user is None:
            return
        admin = self._users.fetch_any_by_id(admin_id)
        self._notifier.access_granted(
            user,
            admin.name if admin else "An administrator",
            self.summary(path),
            self._tenancies.count_datasets(path),
            event_id,
        )
```

`test_a_display_name_is_unique_...` relies on `display_name_taken` comparing *resolved* names over enabled production tenancies: `LBA` collides with the derived `Lba`, a disabled `Old` does not, and the staging `Data Amazon` does not.

In `app/service/tenancy.py`, replace

```python
from app.exception.not_found import NotFoundException
```

with

```python
from app.exception.conflict import ConflictException
from app.exception.not_found import NotFoundException
from app.model.tenancy import DEFAULT_TENANCY
```

replace

```python
    def update(self, old_name: str, updated_tenancy: Tenancy) -> None:
        old_tenancy: DBModel = self._repository.fetch(tenancy=old_name)
```

with

```python
    def update(self, old_name: str, updated_tenancy: Tenancy) -> None:
        if old_name == DEFAULT_TENANCY:
            raise ConflictException("public_tenancy_locked")
        old_tenancy: DBModel = self._repository.fetch(tenancy=old_name)
```

and replace

```python
    def disable(self, name: str) -> None:
        tenancy: DBModel = self._repository.fetch(tenancy=name)
```

with

```python
    def disable(self, name: str) -> None:
        if name == DEFAULT_TENANCY:
            raise ConflictException("public_tenancy_locked")
        tenancy: DBModel = self._repository.fetch(tenancy=name)
```

- [ ] **Step 5: Register the providers**

In `app/container.py`, replace

```python
from app.repository.tenancy_event import TenancyEventRepository
```

with

```python
from app.repository.tenancy_event import TenancyEventRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_notifier import TenancyNotifier
```

and replace

```python
    auth_service = providers.Factory(
        AuthService,
```

with

```python
    tenancy_membership_repository = providers.Factory(
        TenancyMembershipRepository,
        session_factory=db.provided.session,
    )

    tenancy_notifier = providers.Factory(
        TenancyNotifier,
        email_service=email_service,
        admin_emails=config.ADMIN_NOTIFICATION_EMAILS,
        public_base_url=config.PUBLIC_BASE_URL,
    )

    tenancy_membership_service = providers.Factory(
        TenancyMembershipService,
        tenancies=tenancy_repository,
        memberships=tenancy_membership_repository,
        users=user_repository,
        notifier=tenancy_notifier,
    )

    auth_service = providers.Factory(
        AuthService,
```

- [ ] **Step 6: Run them and see them pass**

```bash
$PY -m pytest app/service/tenancy_membership_test.py app/service/tenancy_test.py app/repository app/controller/routes_security_test.py -q -p no:cacheprovider
$PY -c "from app.container import Container; c = Container(); print(type(c.tenancy_membership_service()).__name__)"
```

Expected: all pass; the second command prints `TenancyMembershipService` (it builds the object graph without a database call). If it fails on a missing environment variable, run it with `set -a; . ./local.env; set +a` first.

- [ ] **Step 7: Commit**

```bash
pwd && command git branch --show-current
command git add app/repository/tenancy.py app/repository/tenancy_membership.py app/repository/user.py app/service/tenancy_membership.py app/service/tenancy_membership_test.py app/service/tenancy.py app/service/tenancy_test.py app/container.py
command git commit -m "feat: tenancy membership persistence and rules; public tenancy is locked (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 9: `authorize_self`, quiet `400 invalid_request`, and the response models

**Files:**
- Modify: `app/controller/interceptor/authorization.py`, `app/controller/interceptor/authorization_test.py`
- Modify: `app/controller/interceptor/exception_handler.py`, `app/controller/interceptor/exception_handler_test.py`
- Create: `app/controller/v1/tenancy/access_resource.py`, `app/controller/v1/tenancy/access_resource_test.py`

**Interfaces:**
- Produces: `authorize_self(request, user_id=Depends(parse_user_header)) -> None` — `{id}` in the path must parse to the UUID in `X-User-Id`, else `UnauthorizedException("not_authorized")` (401); Casbin is never consulted.
- Produces: the quiet validation handler also answers `400 {"detail": "invalid_request"}` for every route template starting with `/v1/admin/tenanc`, `/v1/admin/users`, `/v1/users/{id}/tenanc`, `/v1/datasets/{dataset_id}/tenancy-invitations`, `/v1/datasets/{dataset_id}/share/lookup`.
- Produces (`app/controller/v1/tenancy/access_resource.py`): Pydantic models built from the view dataclasses with `from_attributes=True`: `TenancySummaryResponse`, `UserRefResponse`, `UserBriefResponse`, `DatasetRefResponse`, `TenancyRequestResponse`, `TenancyInvitationResponse`, `AcceptedInvitationResponse`, `DatasetTenancyInvitationResponse`, `ShareLookupResponse`, `RequesterResponse`, `AdminTenancyRequestResponse`, `AdminTenancyRequestDetailResponse`, `AdminTenancyRequestPage`, `RequestCountsResponse`, `AdminTenancyResponse`, `TenancyMemberResponse`, `TenancyMemberPage`, `AdminTenancyInvitationResponse`, `TenancyMembersResponse`, `RemovalImpactResponse`; bodies `TenancyRequestBody{tenancy_name, reason}`, `NewTenancyBody{display_name, namespace}`, `ApproveBody{tenancy?, new_tenancy?}`, `DeclineBody{message?}`, `TenancyCreateBody{display_name, namespace}`, `UserIdBody{user_id}`.

- [ ] **Step 1: Write the failing tests**

Append to `app/controller/interceptor/authorization_test.py`:

```python


class TestSelfOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = Container()
        app = FastAPI()
        setup.setup_error_handlers(app)

        @app.get("/users/{id}/tenancies", dependencies=[Depends(authorize_self)])
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

    def test_a_user_reaches_their_own_route_without_any_role(self):
        user_id = uuid4()

        response = self.client.get(
            f"/users/{user_id}/tenancies", headers={"X-User-Id": str(user_id)}
        )

        self.assertEqual(response.status_code, 200)
        self.auth.authorize_user.assert_not_called()

    def test_anyone_else_is_refused_even_an_admin_and_casbin_is_not_asked(self):
        response = self.client.get(
            f"/users/{uuid4()}/tenancies", headers={"X-User-Id": str(uuid4())}
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "not_authorized"})
        self.auth.authorize_user.assert_not_called()

    def test_a_path_id_that_is_not_a_uuid_is_refused(self):
        response = self.client.get(
            "/users/everyone/tenancies", headers={"X-User-Id": str(uuid4())}
        )

        self.assertEqual(response.status_code, 401)

    def test_without_a_user_header_it_is_401(self):
        self.assertEqual(self.client.get(f"/users/{uuid4()}/tenancies").status_code, 401)
```

and replace

```python
from app.controller.interceptor.authorization import authorize_self_or_policy
```

with

```python
from app.controller.interceptor.authorization import (
    authorize_self,
    authorize_self_or_policy,
)
```

Append to `app/controller/interceptor/exception_handler_test.py`:

```python


class TestQuietValidation(unittest.TestCase):
    def request(self, method: str, path: str) -> SimpleNamespace:
        return SimpleNamespace(method=method, scope={"route": SimpleNamespace(path=path)})

    def test_the_tenancy_routes_answer_invalid_request(self):
        for method, path in (
            ("POST", "/v1/users/{id}/tenancy-requests"),
            ("GET", "/v1/users/{id}/tenancies"),
            ("POST", "/v1/users/{id}/tenancy-invitations/{invitation_id}/accept"),
            ("GET", "/v1/datasets/{dataset_id}/share/lookup"),
            ("POST", "/v1/datasets/{dataset_id}/tenancy-invitations"),
            ("GET", "/v1/admin/tenancy-requests"),
            ("POST", "/v1/admin/tenancies/{path:path}/members"),
            ("GET", "/v1/admin/users"),
        ):
            with self.subTest(path=path):
                self.assertTrue(_answers_quietly(self.request(method, path)))

    def test_other_routes_keep_the_default(self):
        for method, path in (
            ("POST", "/v1/datasets/"),
            ("PUT", "/v1/users/{id}/roles"),
            ("GET", "/v1/admin/emails/"),
            ("POST", "/v1/datasets/{dataset_id}/share"),
        ):
            with self.subTest(path=path):
                self.assertFalse(_answers_quietly(self.request(method, path)))
```

and replace

```python
from app.controller.interceptor.exception_handler import (
    bad_request_exception_handler,
    generic_exception_handler,
)
```

with

```python
from app.controller.interceptor.exception_handler import (
    _answers_quietly,
    bad_request_exception_handler,
    generic_exception_handler,
)
```

Create `app/controller/v1/tenancy/access_resource_test.py`:

```python
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.controller.v1.tenancy.access_resource import (
    AdminTenancyRequestDetailResponse,
    TenancyMembersResponse,
)
from app.model.tenancy import summary_of
from app.model.tenancy_access import (
    AdminTenancyRequestDetailView,
    Page,
    Requester,
    TenancyMembersView,
    TenancyMemberView,
    UserRef,
)

AT = datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc)


class TestFromViews(unittest.TestCase):
    def test_a_detail_view_with_nested_views_becomes_json(self):
        view = AdminTenancyRequestDetailView(
            id=uuid4(),
            requester=Requester(uuid4(), "Bruna", None, False, "0000-0002-1825-0097"),
            requested_name="ATTO",
            reason="r",
            status="pending",
            kind="join",
            suggested_tenancy=summary_of("datamap/production/atto", "ATTO"),
            created_at=AT,
            tenancy=None,
            created_tenancy=False,
            decision_message=None,
            decided_by=None,
            decided_at=None,
            requester_tenancies=[summary_of("datamap/production/public", "Public")],
            suggested_tenancy_members=4,
        )

        body = AdminTenancyRequestDetailResponse.model_validate(view).model_dump(mode="json")

        self.assertEqual(body["suggested_tenancy"]["display_name"], "ATTO")
        self.assertEqual(body["requester"]["email"], None)
        self.assertEqual(body["requester_tenancies"][0]["is_default"], True)
        self.assertEqual(body["suggested_tenancy_members"], 4)
        self.assertEqual(body["created_at"], "2026-10-05T09:30:00Z")

    def test_a_page_of_members(self):
        view = TenancyMembersView(
            members=Page(
                items=[
                    TenancyMemberView(uuid4(), "Ana", "a@usp.br", AT, UserRef(uuid4(), "Alan"))
                ],
                total_count=1,
                limit=50,
                offset=0,
            ),
            invitations=[],
        )

        body = TenancyMembersResponse.model_validate(view).model_dump(mode="json")

        self.assertEqual(body["members"]["total_count"], 1)
        self.assertEqual(body["members"]["items"][0]["invited_by"]["name"], "Alan")
        self.assertEqual(body["invitations"], [])
```

- [ ] **Step 2: Run them and see them fail**

```bash
$PY -m pytest app/controller/interceptor/authorization_test.py app/controller/interceptor/exception_handler_test.py app/controller/v1/tenancy/access_resource_test.py -q -p no:cacheprovider
```

Expected: `ImportError: cannot import name 'authorize_self'`, `cannot import name '_answers_quietly'` resolves (it exists) but `test_the_tenancy_routes_answer_invalid_request` fails, and `ModuleNotFoundError: No module named 'app.controller.v1.tenancy.access_resource'`.

- [ ] **Step 3: Implement**

In `app/controller/interceptor/authorization.py`, replace

```python
def _adapt_tus_response(res: TusResult):
```

with

```python
def authorize_self(
    request: Request,
    user_id: UUID = Depends(parse_user_header),
) -> None:
    if not _is_self(request, user_id):
        metrics.auth_failure("authz", "not_self")
        raise UnauthorizedException("not_authorized")


def _adapt_tus_response(res: TusResult):
```

In `app/controller/interceptor/exception_handler.py`, replace

```python
QUIET_VALIDATION_PREFIX = "/v1/auth/"
QUIET_VALIDATION_ROUTES = {("PUT", "/v1/users/{id}/password")}


def _answers_quietly(request: Request) -> bool:
    path = _route_template(request)
    return (
        path.startswith(QUIET_VALIDATION_PREFIX)
        or (request.method, path) in QUIET_VALIDATION_ROUTES
    )
```

with

```python
QUIET_VALIDATION_PREFIX = "/v1/auth/"
QUIET_VALIDATION_ROUTES = {("PUT", "/v1/users/{id}/password")}
TENANCY_VALIDATION_PREFIXES = (
    "/v1/admin/tenanc",
    "/v1/admin/users",
    "/v1/users/{id}/tenanc",
    "/v1/datasets/{dataset_id}/tenancy-invitations",
    "/v1/datasets/{dataset_id}/share/lookup",
)


def _answers_quietly(request: Request) -> bool:
    path = _route_template(request)
    return (
        path.startswith(QUIET_VALIDATION_PREFIX)
        or path.startswith(TENANCY_VALIDATION_PREFIXES)
        or (request.method, path) in QUIET_VALIDATION_ROUTES
    )
```

Create `app/controller/v1/tenancy/access_resource.py`:

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class _FromViews(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TenancySummaryResponse(_FromViews):
    path: str
    display_name: str
    is_default: bool
    is_legacy: bool


class UserRefResponse(_FromViews):
    id: UUID
    name: str


class UserBriefResponse(_FromViews):
    id: UUID
    name: str
    email: str | None = None


class DatasetRefResponse(_FromViews):
    id: UUID
    name: str


class TenancyRequestResponse(_FromViews):
    id: UUID
    requested_name: str
    reason: str
    status: str
    tenancy: TenancySummaryResponse | None
    created_tenancy: bool
    decision_message: str | None
    created_at: datetime
    decided_at: datetime | None


class TenancyInvitationResponse(_FromViews):
    id: UUID
    tenancy: TenancySummaryResponse
    invited_by: UserRefResponse | None
    dataset: DatasetRefResponse | None
    datasets: int
    created_at: datetime


class AcceptedInvitationResponse(_FromViews):
    tenancy: TenancySummaryResponse


class DatasetTenancyInvitationResponse(_FromViews):
    id: UUID
    user: UserBriefResponse
    invited_by: UserBriefResponse | None
    created_at: datetime
    can_withdraw: bool


class ShareLookupResponse(_FromViews):
    user: UserBriefResponse
    tenancy_member: bool
    invitation_pending: bool
    can_invite: bool


class RequesterResponse(_FromViews):
    id: UUID
    name: str
    email: str | None
    email_verified: bool
    orcid: str | None


class AdminTenancyRequestResponse(_FromViews):
    id: UUID
    requester: RequesterResponse
    requested_name: str
    reason: str
    status: str
    kind: str
    suggested_tenancy: TenancySummaryResponse | None
    created_at: datetime
    tenancy: TenancySummaryResponse | None
    created_tenancy: bool
    decision_message: str | None
    decided_by: UserRefResponse | None
    decided_at: datetime | None


class AdminTenancyRequestDetailResponse(AdminTenancyRequestResponse):
    requester_tenancies: list[TenancySummaryResponse]
    suggested_tenancy_members: int | None


class AdminTenancyRequestPage(_FromViews):
    items: list[AdminTenancyRequestResponse]
    total_count: int
    limit: int
    offset: int


class RequestCountsResponse(_FromViews):
    open: int
    join: int
    new: int
    closed: int


class AdminTenancyResponse(_FromViews):
    path: str
    display_name: str
    members: int
    datasets: int
    is_default: bool
    is_legacy: bool
    is_enabled: bool


class TenancyMemberResponse(_FromViews):
    id: UUID
    name: str
    email: str | None
    since: datetime
    invited_by: UserRefResponse | None


class TenancyMemberPage(_FromViews):
    items: list[TenancyMemberResponse]
    total_count: int
    limit: int
    offset: int


class AdminTenancyInvitationResponse(_FromViews):
    id: UUID
    user: UserBriefResponse
    invited_by: UserRefResponse | None
    dataset: DatasetRefResponse | None
    created_at: datetime


class TenancyMembersResponse(_FromViews):
    members: TenancyMemberPage
    invitations: list[AdminTenancyInvitationResponse]


class RemovalImpactResponse(_FromViews):
    member_since: datetime
    datasets_in_tenancy: int
    shared_with_user: int
    owned_by_user: int


class TenancyRequestBody(BaseModel):
    tenancy_name: str
    reason: str


class NewTenancyBody(BaseModel):
    display_name: str
    namespace: str


class ApproveBody(BaseModel):
    tenancy: str | None = None
    new_tenancy: NewTenancyBody | None = None


class DeclineBody(BaseModel):
    message: str | None = None


class TenancyCreateBody(BaseModel):
    display_name: str
    namespace: str


class UserIdBody(BaseModel):
    user_id: UUID
```

- [ ] **Step 4: Run them and see them pass**

```bash
$PY -m pytest app/controller/interceptor app/controller/v1/tenancy/access_resource_test.py app/controller/v1/user/user_test.py -q -p no:cacheprovider
```

Expected: all pass, including `test_another_user_route_keeps_the_default_422` in `user_test.py`.

- [ ] **Step 5: Commit**

```bash
pwd && command git branch --show-current
command git add app/controller/interceptor/authorization.py app/controller/interceptor/authorization_test.py app/controller/interceptor/exception_handler.py app/controller/interceptor/exception_handler_test.py app/controller/v1/tenancy/access_resource.py app/controller/v1/tenancy/access_resource_test.py
command git commit -m "feat: self-only routes, quiet invalid_request and response models for tenancy access (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 10: Tenancy requests — the user side and `GET /users/{id}/tenancies`

**Files:**
- Create: `app/repository/tenancy_request.py`
- Create: `app/service/tenancy_request.py`, `app/service/tenancy_request_test.py`
- Create: `app/controller/v1/user/tenancy_access.py`, `app/controller/v1/user/tenancy_access_test.py`
- Modify: `app/container.py`, `app/setup.py`

**Interfaces:**
- Consumes: `TenancyMembershipService` (Task 8), `TenancyNotifier` (Task 7), `authorize_self` and the response models (Task 9).
- Produces (`TenancyRequestRepository`): `create(user_id, requested_name, reason) -> TenancyRequest` (writes `request_created`; `ConflictException("request_pending")` on the partial unique index), `fetch(request_id)`, `pending_for(user_id)`, `count_since(user_id, since) -> int`, `latest_for(user_id, limit) -> list`, `withdraw(request_id, user_id) -> bool` (pending and theirs only; writes `request_withdrawn`), `list_pending(term) -> list` (oldest first), `list_closed(term, limit, offset) -> tuple[list, int]` (newest decision first), `count_closed() -> int`, `approve(request_id, decided_by, tenancy, display_name, now) -> tuple[TenancyRequest, UUID]`, `decline(request_id, decided_by, message, now) -> TenancyRequest`. `approve` and `decline` lock the row (`FOR UPDATE`), raise `NotFoundException("request_not_found")` / `ConflictException("request_not_pending")`, and write their events in the same commit; `approve` with a `display_name` creates the tenancy first (`tenancy_created`), raises `ConflictException("already_member")` when the membership exists and `ConflictException("tenancy_exists")` on a duplicate path, and returns the `member_added` event id.
- Produces (`TenancyRequestService`, user side): `list_for_user(user_id) -> list[TenancyRequestView]` (latest 5), `create(user_id, tenancy_name, reason) -> TenancyRequestView`, `withdraw(user_id, request_id) -> None`.
- Produces routes (self): `GET /v1/users/{id}/tenancies` → `200 TenancySummary[]`; `GET /v1/users/{id}/tenancy-requests` → `200 TenancyRequest[]`; `POST /v1/users/{id}/tenancy-requests` → `201 TenancyRequest`; `DELETE /v1/users/{id}/tenancy-requests/{request_id}` → `204`.

- [ ] **Step 1: Write the failing tests**

Create `app/service/tenancy_request_test.py`:

```python
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.too_many_requests import TooManyRequestsException
from app.model.tenancy import DEFAULT_TENANCY, TenancyRequestStatus, summary_of
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.tenancy_request import TenancyRequestRepository
from app.repository.user import UserRepository
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_notifier import TenancyNotifier
from app.service.tenancy_request import TenancyRequestService

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
ATTO = "datamap/production/atto"


def request_row(user_id, **overrides):
    values = dict(
        id=uuid4(),
        user_id=user_id,
        requested_name="ATTO",
        reason="Fluxes",
        status=TenancyRequestStatus.PENDING,
        tenancy=None,
        created_tenancy=False,
        decision_message=None,
        decided_by=None,
        decided_at=None,
        created_at=NOW,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def tenancy_row(name, display_name=None, is_enabled=True):
    return SimpleNamespace(name=name, display_name=display_name, is_enabled=is_enabled)


def user_row(name="Bruna Costa", email="bruna@usp.br", verified=True, orcid=None):
    providers = [SimpleNamespace(name="orcid", reference=orcid)] if orcid else []
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        email=email,
        email_verified_at=NOW if verified else None,
        providers=providers,
        created_at=NOW,
    )


class RequestServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.requests = Mock(spec=TenancyRequestRepository)
        self.tenancies = Mock(spec=TenancyRepository)
        self.memberships = Mock(spec=TenancyMembershipRepository)
        self.membership_service = Mock(spec=TenancyMembershipService)
        self.membership_service.summary.side_effect = lambda path: summary_of(
            path, "ATTO" if path == ATTO else None
        )
        self.users = Mock(spec=UserRepository)
        self.notifier = Mock(spec=TenancyNotifier)
        self.user = user_row()
        self.users.fetch_any_by_id.side_effect = lambda id: (
            self.user if id == self.user.id else None
        )
        self.requests.pending_for.return_value = None
        self.requests.count_since.return_value = 0
        self.requests.create.side_effect = lambda user_id, requested_name, reason: request_row(
            user_id, requested_name=requested_name, reason=reason
        )
        self.service = TenancyRequestService(
            requests=self.requests,
            tenancies=self.tenancies,
            memberships=self.memberships,
            membership_service=self.membership_service,
            users=self.users,
            notifier=self.notifier,
            clock=lambda: NOW,
        )


class TestCreate(RequestServiceTestCase):
    def code(self, name, reason) -> str:
        with self.assertRaises(
            (IllegalStateException, ConflictException, TooManyRequestsException)
        ) as raised:
            self.service.create(self.user.id, name, reason)
        return str(raised.exception)

    def test_a_request_is_stored_trimmed_and_the_admins_are_told(self):
        view = self.service.create(self.user.id, "  ATTO ", " Fluxes ")

        self.requests.create.assert_called_once_with(self.user.id, "ATTO", "Fluxes")
        self.assertEqual(view.status, "pending")
        self.assertEqual(view.requested_name, "ATTO")
        self.assertIsNone(view.tenancy)
        (request, requester), _ = self.notifier.request_received.call_args
        self.assertEqual(request.requested_name, "ATTO")
        self.assertIs(requester, self.user)

    def test_the_lengths(self):
        self.assertEqual(self.code("   ", "why"), "tenancy_name_invalid")
        self.assertEqual(self.code("x" * 129, "why"), "tenancy_name_invalid")
        self.assertEqual(self.code("ATTO", ""), "reason_invalid")
        self.assertEqual(self.code("ATTO", "x" * 1001), "reason_invalid")
        self.requests.create.assert_not_called()

    def test_one_pending_request_per_user(self):
        self.requests.pending_for.return_value = request_row(self.user.id)

        self.assertEqual(self.code("ATTO", "why"), "request_pending")

    def test_three_a_day_withdrawn_included(self):
        self.requests.count_since.return_value = 3

        self.assertEqual(self.code("ATTO", "why"), "too_many_requests")
        self.requests.count_since.assert_called_once_with(
            self.user.id, NOW - timedelta(hours=24)
        )

    def test_two_today_still_allows_a_third(self):
        self.requests.count_since.return_value = 2

        self.assertEqual(self.service.create(self.user.id, "ATTO", "why").status, "pending")


class TestUserSide(RequestServiceTestCase):
    def test_the_latest_five_with_the_tenancy_once_approved(self):
        approved = request_row(
            self.user.id,
            status=TenancyRequestStatus.APPROVED,
            tenancy=ATTO,
            decided_at=NOW,
        )
        declined = request_row(
            self.user.id,
            status=TenancyRequestStatus.DECLINED,
            decision_message="Ask Alan",
        )
        self.requests.latest_for.return_value = [approved, declined]

        views = self.service.list_for_user(self.user.id)

        self.requests.latest_for.assert_called_once_with(self.user.id, 5)
        self.assertEqual(views[0].tenancy, summary_of(ATTO, "ATTO"))
        self.assertEqual(views[0].status, "approved")
        self.assertIsNone(views[1].tenancy)
        self.assertEqual(views[1].decision_message, "Ask Alan")

    def test_withdrawing_what_is_not_pending_or_not_theirs_is_not_found(self):
        self.requests.withdraw.return_value = False

        with self.assertRaises(NotFoundException) as raised:
            self.service.withdraw(self.user.id, uuid4())

        self.assertEqual(str(raised.exception), "request_not_found")

    def test_a_withdrawal_is_passed_to_the_repository_as_the_user(self):
        self.requests.withdraw.return_value = True
        request_id = uuid4()

        self.service.withdraw(self.user.id, request_id)

        self.requests.withdraw.assert_called_once_with(request_id, self.user.id)

```

Create `app/controller/v1/user/tenancy_access_test.py`:

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
from app.controller.interceptor.authorization import authorize, authorize_self
from app.exception.conflict import ConflictException
from app.exception.not_found import NotFoundException
from app.model.tenancy import DEFAULT_TENANCY, summary_of
from app.model.tenancy_access import TenancyRequestView
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_request import TenancyRequestService

AT = datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc)


def _view(**overrides) -> TenancyRequestView:
    values = dict(
        id=uuid4(),
        requested_name="ATTO",
        reason="Fluxes",
        status="pending",
        tenancy=None,
        created_tenancy=False,
        decision_message=None,
        created_at=AT,
        decided_at=None,
    )
    values.update(overrides)
    return TenancyRequestView(**values)


class SelfRoutesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = Container()
        app = FastAPI()
        setup.setup_routes(app)
        setup.setup_error_handlers(app)
        app.dependency_overrides[authenticate] = lambda: None
        app.dependency_overrides[authorize] = lambda: None
        app.dependency_overrides[authorize_self] = lambda: None
        cls.app = app
        cls.client = TestClient(app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls.container.unwire()

    def setUp(self):
        self.memberships = Mock(spec=TenancyMembershipService)
        self.requests = Mock(spec=TenancyRequestService)
        self.container.tenancy_membership_service.override(providers.Object(self.memberships))
        self.container.tenancy_request_service.override(providers.Object(self.requests))
        self.user_id = uuid4()

    def tearDown(self):
        self.container.tenancy_membership_service.reset_override()
        self.container.tenancy_request_service.reset_override()


class TestTenancyRoutes(SelfRoutesTestCase):
    def test_my_tenancies(self):
        self.memberships.summaries_for.return_value = [summary_of(DEFAULT_TENANCY, "Public")]

        response = self.client.get(f"/v1/users/{self.user_id}/tenancies")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {
                    "path": DEFAULT_TENANCY,
                    "display_name": "Public",
                    "is_default": True,
                    "is_legacy": False,
                }
            ],
        )
        self.memberships.summaries_for.assert_called_once_with(self.user_id)

    def test_the_routes_are_self_only_and_never_ask_casbin(self):
        for route in self.app.routes:
            path = getattr(route, "path", "")
            if path.startswith("/v1/users/{id}/tenanc"):
                with self.subTest(path=path, methods=route.methods):
                    calls = {d.call for d in route.dependant.dependencies}
                    self.assertIn(authorize_self, calls)
                    self.assertIn(authenticate, calls)
                    self.assertNotIn(authorize, calls)


class TestRequestRoutes(SelfRoutesTestCase):
    def test_creating_answers_201_with_the_request(self):
        self.requests.create.return_value = _view()

        response = self.client.post(
            f"/v1/users/{self.user_id}/tenancy-requests",
            json={"tenancy_name": "ATTO", "reason": "Fluxes"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "pending")
        self.assertEqual(response.json()["created_at"], "2026-10-05T09:30:00Z")
        self.requests.create.assert_called_once_with(self.user_id, "ATTO", "Fluxes")

    def test_a_malformed_body_is_invalid_request(self):
        response = self.client.post(
            f"/v1/users/{self.user_id}/tenancy-requests", json={"tenancy_name": "ATTO"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "invalid_request"})

    def test_a_pending_request_is_409(self):
        self.requests.create.side_effect = ConflictException("request_pending")

        response = self.client.post(
            f"/v1/users/{self.user_id}/tenancy-requests",
            json={"tenancy_name": "ATTO", "reason": "Fluxes"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "request_pending"})

    def test_listing_and_withdrawing(self):
        self.requests.list_for_user.return_value = [_view(), _view(status="declined")]
        request_id = uuid4()

        listed = self.client.get(f"/v1/users/{self.user_id}/tenancy-requests")
        withdrawn = self.client.delete(
            f"/v1/users/{self.user_id}/tenancy-requests/{request_id}"
        )

        self.assertEqual([r["status"] for r in listed.json()], ["pending", "declined"])
        self.assertEqual(withdrawn.status_code, 204)
        self.requests.withdraw.assert_called_once_with(self.user_id, request_id)

    def test_withdrawing_someone_elses_is_404(self):
        self.requests.withdraw.side_effect = NotFoundException("request_not_found")

        response = self.client.delete(
            f"/v1/users/{self.user_id}/tenancy-requests/{uuid4()}"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "request_not_found"})

    def test_the_retired_membership_routes_are_gone(self):
        for method in ("post", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(f"/v1/users/{self.user_id}/tenancies")
                self.assertIn(response.status_code, (404, 405))
```

- [ ] **Step 2: Run them and see them fail**

```bash
$PY -m pytest app/service/tenancy_request_test.py app/controller/v1/user/tenancy_access_test.py -q -p no:cacheprovider
```

Expected: `ModuleNotFoundError: No module named 'app.repository.tenancy_request'` and `No module named 'app.service.tenancy_request'`.

- [ ] **Step 3: Implement the repository**

Create `app/repository/tenancy_request.py`:

```python
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exception.conflict import ConflictException
from app.exception.not_found import NotFoundException
from app.model.db.tenancy import Tenancy, TenancyRequest
from app.model.db.user import User
from app.model.tenancy import TenancyEventType, TenancyRequestStatus
from app.repository.tenancy_event import add_event
from app.repository.tenancy_membership import insert_membership
from app.repository.user import user_matches

CLOSED = (TenancyRequestStatus.APPROVED, TenancyRequestStatus.DECLINED)


class TenancyRequestRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def create(self, user_id: UUID, requested_name: str, reason: str) -> TenancyRequest:
        try:
            with self._session_factory() as session:
                request = TenancyRequest(
                    id=uuid4(),
                    user_id=user_id,
                    requested_name=requested_name,
                    reason=reason,
                    status=TenancyRequestStatus.PENDING,
                    created_tenancy=False,
                )
                session.add(request)
                session.flush()
                add_event(
                    session,
                    tenancy=None,
                    event_type=TenancyEventType.REQUEST_CREATED,
                    user_id=user_id,
                    actor_id=user_id,
                    request_id=request.id,
                )
                session.commit()
                session.refresh(request)
                return request
        except IntegrityError:
            raise ConflictException("request_pending")

    def fetch(self, request_id: UUID) -> TenancyRequest | None:
        with self._session_factory() as session:
            return session.query(TenancyRequest).filter_by(id=request_id).first()

    def pending_for(self, user_id: UUID) -> TenancyRequest | None:
        with self._session_factory() as session:
            return (
                session.query(TenancyRequest)
                .filter_by(user_id=user_id, status=TenancyRequestStatus.PENDING)
                .first()
            )

    def count_since(self, user_id: UUID, since: datetime) -> int:
        with self._session_factory() as session:
            return (
                session.query(func.count(TenancyRequest.id))
                .filter(
                    TenancyRequest.user_id == user_id,
                    TenancyRequest.created_at >= since,
                )
                .scalar()
            )

    def latest_for(self, user_id: UUID, limit: int) -> list[TenancyRequest]:
        with self._session_factory() as session:
            return (
                session.query(TenancyRequest)
                .filter_by(user_id=user_id)
                .order_by(TenancyRequest.created_at.desc())
                .limit(limit)
                .all()
            )

    def withdraw(self, request_id: UUID, user_id: UUID) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(TenancyRequest)
                .filter(
                    TenancyRequest.id == request_id,
                    TenancyRequest.user_id == user_id,
                    TenancyRequest.status == TenancyRequestStatus.PENDING,
                )
                .update(
                    {TenancyRequest.status: TenancyRequestStatus.WITHDRAWN},
                    synchronize_session=False,
                )
            )
            if updated == 0:
                session.rollback()
                return False
            add_event(
                session,
                tenancy=None,
                event_type=TenancyEventType.REQUEST_WITHDRAWN,
                user_id=user_id,
                actor_id=user_id,
                request_id=request_id,
            )
            session.commit()
            return True

    def _queue(self, session: Session, term: str | None, statuses) -> object:
        query = (
            session.query(TenancyRequest)
            .join(User, User.id == TenancyRequest.user_id)
            .filter(TenancyRequest.status.in_(statuses))
        )
        if term:
            query = query.filter(user_matches(term))
        return query

    def list_pending(self, term: str | None) -> list[TenancyRequest]:
        with self._session_factory() as session:
            return (
                self._queue(session, term, [TenancyRequestStatus.PENDING])
                .order_by(TenancyRequest.created_at.asc())
                .all()
            )

    def list_closed(
        self, term: str | None, limit: int, offset: int
    ) -> tuple[list[TenancyRequest], int]:
        with self._session_factory() as session:
            query = self._queue(session, term, CLOSED)
            total = query.count()
            rows = (
                query.order_by(
                    TenancyRequest.decided_at.desc().nullslast(),
                    TenancyRequest.created_at.desc(),
                )
                .limit(limit)
                .offset(offset)
                .all()
            )
            return rows, total

    def count_closed(self) -> int:
        with self._session_factory() as session:
            return (
                session.query(func.count(TenancyRequest.id))
                .filter(TenancyRequest.status.in_(CLOSED))
                .scalar()
            )

    def _locked_pending(self, session: Session, request_id: UUID) -> TenancyRequest:
        request = (
            session.query(TenancyRequest)
            .filter_by(id=request_id)
            .with_for_update()
            .first()
        )
        if request is None or request.status == TenancyRequestStatus.WITHDRAWN:
            raise NotFoundException("request_not_found")
        if request.status != TenancyRequestStatus.PENDING:
            raise ConflictException("request_not_pending")
        return request

    def approve(
        self,
        request_id: UUID,
        decided_by: UUID,
        tenancy: str,
        display_name: str | None,
        now: datetime,
    ) -> tuple[TenancyRequest, UUID]:
        try:
            with self._session_factory() as session:
                request = self._locked_pending(session, request_id)
                if display_name is not None:
                    session.add(
                        Tenancy(name=tenancy, display_name=display_name, is_enabled=True)
                    )
                    session.flush()
                    add_event(
                        session,
                        tenancy=tenancy,
                        event_type=TenancyEventType.TENANCY_CREATED,
                        actor_id=decided_by,
                        request_id=request.id,
                    )
                if not insert_membership(session, request.user_id, tenancy):
                    raise ConflictException("already_member")
                member_added = add_event(
                    session,
                    tenancy=tenancy,
                    event_type=TenancyEventType.MEMBER_ADDED,
                    user_id=request.user_id,
                    actor_id=decided_by,
                    request_id=request.id,
                )
                event_id = member_added.id
                request.status = TenancyRequestStatus.APPROVED
                request.tenancy = tenancy
                request.created_tenancy = display_name is not None
                request.decided_by = decided_by
                request.decided_at = now
                add_event(
                    session,
                    tenancy=tenancy,
                    event_type=TenancyEventType.REQUEST_APPROVED,
                    user_id=request.user_id,
                    actor_id=decided_by,
                    request_id=request.id,
                )
                session.commit()
                session.refresh(request)
                return request, event_id
        except IntegrityError:
            raise ConflictException("tenancy_exists")

    def decline(
        self,
        request_id: UUID,
        decided_by: UUID,
        message: str | None,
        now: datetime,
    ) -> TenancyRequest:
        with self._session_factory() as session:
            request = self._locked_pending(session, request_id)
            request.status = TenancyRequestStatus.DECLINED
            request.decision_message = message
            request.decided_by = decided_by
            request.decided_at = now
            add_event(
                session,
                tenancy=None,
                event_type=TenancyEventType.REQUEST_DECLINED,
                user_id=request.user_id,
                actor_id=decided_by,
                request_id=request.id,
            )
            session.commit()
            session.refresh(request)
            return request
```

- [ ] **Step 4: Implement the service (user side)**

Create `app/service/tenancy_request.py`:

```python
from datetime import datetime, timedelta
from typing import Callable
from uuid import UUID

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.too_many_requests import TooManyRequestsException
from app.model.dataset_access import utcnow
from app.model.tenancy import (
    REASON_MAX_LENGTH,
    TENANCY_NAME_MAX_LENGTH,
    TenancyRequestStatus,
    trimmed_within,
)
from app.model.tenancy_access import TenancyRequestView
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.tenancy_request import TenancyRequestRepository
from app.repository.user import UserRepository
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_notifier import TenancyNotifier

DAILY_LIMIT = 3
WINDOW = timedelta(hours=24)
LATEST = 5


class TenancyRequestService:
    def __init__(
        self,
        requests: TenancyRequestRepository,
        tenancies: TenancyRepository,
        memberships: TenancyMembershipRepository,
        membership_service: TenancyMembershipService,
        users: UserRepository,
        notifier: TenancyNotifier,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._requests = requests
        self._tenancies = tenancies
        self._memberships = memberships
        self._membership_service = membership_service
        self._users = users
        self._notifier = notifier
        self._clock = clock

    def list_for_user(self, user_id: UUID) -> list[TenancyRequestView]:
        return [self._user_view(r) for r in self._requests.latest_for(user_id, LATEST)]

    def create(self, user_id: UUID, tenancy_name: str, reason: str) -> TenancyRequestView:
        name = trimmed_within(tenancy_name, 1, TENANCY_NAME_MAX_LENGTH)
        if name is None:
            raise IllegalStateException("tenancy_name_invalid")
        why = trimmed_within(reason, 1, REASON_MAX_LENGTH)
        if why is None:
            raise IllegalStateException("reason_invalid")
        if self._requests.pending_for(user_id) is not None:
            raise ConflictException("request_pending")
        if self._requests.count_since(user_id, self._clock() - WINDOW) >= DAILY_LIMIT:
            raise TooManyRequestsException("too_many_requests")
        request = self._requests.create(user_id, name, why)
        requester = self._users.fetch_any_by_id(user_id)
        if requester is not None:
            self._notifier.request_received(request, requester)
        return self._user_view(request)

    def withdraw(self, user_id: UUID, request_id: UUID) -> None:
        if not self._requests.withdraw(request_id, user_id):
            raise NotFoundException("request_not_found")

    def _user_view(self, request) -> TenancyRequestView:
        return TenancyRequestView(
            id=request.id,
            requested_name=request.requested_name,
            reason=request.reason,
            status=TenancyRequestStatus(request.status).value,
            tenancy=self._membership_service.summary(request.tenancy)
            if request.tenancy
            else None,
            created_tenancy=bool(request.created_tenancy),
            decision_message=request.decision_message,
            created_at=request.created_at,
            decided_at=request.decided_at,
        )
```

- [ ] **Step 5: Implement the self routes**

Create `app/controller/v1/user/tenancy_access.py`:

```python
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize_self
from app.controller.v1.tenancy.access_resource import (
    TenancyRequestBody,
    TenancyRequestResponse,
    TenancySummaryResponse,
)
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_request import TenancyRequestService

router = APIRouter(
    prefix="/users",
    tags=["tenancy-access"],
    dependencies=[Depends(authenticate), Depends(authorize_self)],
)


@router.get("/{id}/tenancies", response_model=list[TenancySummaryResponse])
@inject
def my_tenancies(
    id: UUID,
    service: TenancyMembershipService = Depends(
        Provide[Container.tenancy_membership_service]
    ),
) -> list[TenancySummaryResponse]:
    return [TenancySummaryResponse.model_validate(s) for s in service.summaries_for(id)]


@router.get("/{id}/tenancy-requests", response_model=list[TenancyRequestResponse])
@inject
def my_requests(
    id: UUID,
    service: TenancyRequestService = Depends(Provide[Container.tenancy_request_service]),
) -> list[TenancyRequestResponse]:
    return [TenancyRequestResponse.model_validate(v) for v in service.list_for_user(id)]


@router.post(
    "/{id}/tenancy-requests", status_code=201, response_model=TenancyRequestResponse
)
@inject
def request_access(
    id: UUID,
    body: TenancyRequestBody,
    service: TenancyRequestService = Depends(Provide[Container.tenancy_request_service]),
) -> TenancyRequestResponse:
    return TenancyRequestResponse.model_validate(
        service.create(id, body.tenancy_name, body.reason)
    )


@router.delete("/{id}/tenancy-requests/{request_id}", status_code=204)
@inject
def withdraw_request(
    id: UUID,
    request_id: UUID,
    service: TenancyRequestService = Depends(Provide[Container.tenancy_request_service]),
) -> Response:
    service.withdraw(id, request_id)
    return Response(status_code=204)
```

In `app/container.py`, replace

```python
            "app.controller.v1.user.user",
```

with

```python
            "app.controller.v1.user.user",
            "app.controller.v1.user.tenancy_access",
```

replace

```python
from app.repository.tenancy_membership import TenancyMembershipRepository
```

with

```python
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.tenancy_request import TenancyRequestRepository
from app.service.tenancy_request import TenancyRequestService
```

and replace

```python
    auth_service = providers.Factory(
        AuthService,
```

with

```python
    tenancy_request_repository = providers.Factory(
        TenancyRequestRepository,
        session_factory=db.provided.session,
    )

    tenancy_request_service = providers.Factory(
        TenancyRequestService,
        requests=tenancy_request_repository,
        tenancies=tenancy_repository,
        memberships=tenancy_membership_repository,
        membership_service=tenancy_membership_service,
        users=user_repository,
        notifier=tenancy_notifier,
    )

    auth_service = providers.Factory(
        AuthService,
```

In `app/setup.py`, replace

```python
from app.controller.v1.user.user import router as user_router
```

with

```python
from app.controller.v1.user.user import router as user_router
from app.controller.v1.user.tenancy_access import router as tenancy_access_router
```

and replace

```python
    fastAPIApp.include_router(user_router, prefix="/v1")
```

with

```python
    fastAPIApp.include_router(user_router, prefix="/v1")
    fastAPIApp.include_router(tenancy_access_router, prefix="/v1")
```

- [ ] **Step 6: Run them and see them pass**

```bash
$PY -m pytest app/service/tenancy_request_test.py app/controller/v1/user app/controller/routes_security_test.py app/controller/interceptor -q -p no:cacheprovider
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
pwd && command git branch --show-current
command git add app/repository/tenancy_request.py app/service/tenancy_request.py app/service/tenancy_request_test.py app/controller/v1/user/tenancy_access.py app/controller/v1/user/tenancy_access_test.py app/container.py app/setup.py
command git commit -m "feat: users ask for a tenancy and see their tenancies and requests (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 11: The admin request queue — counts, list, detail, approve, decline

**Files:**
- Modify: `app/service/tenancy_request.py`, `app/service/tenancy_request_test.py`
- Create: `app/controller/v1/admin/tenancy.py`, `app/controller/v1/admin/tenancy_test.py`
- Modify: `app/container.py`, `app/setup.py`

**Interfaces:**
- Consumes: `TenancyRequestRepository` (Task 10), `TenancyMembershipService.require_open_for_members`, `check_new_tenancy`, `announce_access`, `summaries_for` (Task 8).
- Produces (`TenancyRequestService`, admin side):
  - `counts() -> RequestCounts` — `open` pending, `join` pending with a suggestion, `new = open - join`, `closed` approved + declined.
  - `queue(status, kind, q, limit, offset) -> Page[AdminTenancyRequestView]` — `status` `open` (oldest first, `kind` filters) or `closed` (newest decision first, `kind` ignored); `q` trimmed, blank means none; `1 <= limit <= 100`, `offset >= 0`, else `IllegalStateException("invalid_request")`.
  - `detail(request_id) -> AdminTenancyRequestDetailView`.
  - `approve(request_id, admin_id, tenancy: str | None, new_tenancy: NewTenancy | None) -> AdminTenancyRequestView`.
  - `decline(request_id, admin_id, message: str | None) -> AdminTenancyRequestView`.
  - The suggested tenancy: the enabled production tenancy, never public, whose resolved display name or namespace has the same `match_key` as `requested_name`. Withdrawn requests answer `request_not_found` everywhere here.
- Produces routes (admin, `authenticate` + `authorize`): `GET /v1/admin/tenancy-requests/counts`, `GET /v1/admin/tenancy-requests`, `GET /v1/admin/tenancy-requests/{request_id}`, `POST /v1/admin/tenancy-requests/{request_id}/approve`, `POST /v1/admin/tenancy-requests/{request_id}/decline`; the router `app/controller/v1/admin/tenancy.py` with prefix `/admin`, extended in Task 13.

- [ ] **Step 1: Write the failing tests**

Append to `app/service/tenancy_request_test.py`:

```python


class AdminQueueTestCase(RequestServiceTestCase):
    def setUp(self):
        super().setUp()
        self.admin = user_row(name="Luciana Rizzo")
        self.requester = user_row(orcid="0000-0002-1825-0097")
        people = {self.user.id: self.user, self.admin.id: self.admin, self.requester.id: self.requester}
        self.users.fetch_any_by_id.side_effect = people.get
        self.tenancies.list_all.return_value = [
            tenancy_row(ATTO, "ATTO"),
            tenancy_row(DEFAULT_TENANCY, "Public"),
            tenancy_row("datamap/production/cerrado-flux"),
            tenancy_row("datamap/production/off", "Off", is_enabled=False),
            tenancy_row("datamap/staging/lba", "LBA"),
        ]

    def pending(self, name: str):
        return request_row(self.requester.id, requested_name=name)


class TestSuggestionsAndCounts(AdminQueueTestCase):
    def test_join_when_a_tenancy_matches_new_otherwise(self):
        self.requests.list_pending.return_value = [
            self.pending("atto"),
            self.pending("Cerrado Flux"),
            self.pending("Public"),
            self.pending("Off"),
            self.pending("LBA"),
            self.pending("Brand new"),
        ]
        self.requests.count_closed.return_value = 7

        counts = self.service.counts()

        self.assertEqual((counts.open, counts.join, counts.new, counts.closed), (6, 2, 4, 7))

    def test_a_row_carries_the_requester_and_the_suggestion(self):
        self.requests.list_pending.return_value = [self.pending("cerrado-flux")]

        page = self.service.queue("open", None, None, 50, 0)

        (row,) = page.items
        self.assertEqual(row.kind, "join")
        self.assertEqual(row.suggested_tenancy.path, "datamap/production/cerrado-flux")
        self.assertEqual(row.suggested_tenancy.display_name, "Cerrado Flux")
        self.assertEqual(row.requester.orcid, "0000-0002-1825-0097")
        self.assertTrue(row.requester.email_verified)
        self.assertIsNone(row.decided_by)


class TestQueue(AdminQueueTestCase):
    def test_open_is_filtered_by_kind_and_paged_after_filtering(self):
        self.requests.list_pending.return_value = [
            self.pending("ATTO"),
            self.pending("New one"),
            self.pending("Another new"),
        ]

        page = self.service.queue("open", "new", "  ana ", 1, 1)

        self.requests.list_pending.assert_called_once_with("ana")
        self.assertEqual(page.total_count, 2)
        self.assertEqual([r.requested_name for r in page.items], ["Another new"])
        self.assertEqual((page.limit, page.offset), (1, 1))

    def test_closed_is_paged_by_the_repository_and_ignores_kind(self):
        decided = request_row(
            self.requester.id,
            status=TenancyRequestStatus.DECLINED,
            decided_by=self.admin.id,
            decided_at=NOW,
        )
        self.requests.list_closed.return_value = ([decided], 9)

        page = self.service.queue("closed", "join", "", 5, 0)

        self.requests.list_closed.assert_called_once_with(None, 5, 0)
        self.assertEqual(page.total_count, 9)
        self.assertEqual(page.items[0].decided_by.name, "Luciana Rizzo")

    def test_parameters_out_of_range_are_invalid_request(self):
        for args in (
            ("pending", None, None, 50, 0),
            ("open", "both", None, 50, 0),
            ("open", None, None, 0, 0),
            ("open", None, None, 101, 0),
            ("open", None, None, 50, -1),
        ):
            with self.subTest(args=args):
                with self.assertRaises(IllegalStateException) as raised:
                    self.service.queue(*args)
                self.assertEqual(str(raised.exception), "invalid_request")


class TestDetail(AdminQueueTestCase):
    def test_the_requesters_tenancies_and_the_suggestions_size(self):
        request = self.pending("ATTO")
        self.requests.fetch.return_value = request
        self.membership_service.summaries_for.return_value = [summary_of(DEFAULT_TENANCY, "Public")]
        self.memberships.count.return_value = 4

        detail = self.service.detail(request.id)

        self.assertEqual(detail.id, request.id)
        self.assertEqual(detail.requester_tenancies, [summary_of(DEFAULT_TENANCY, "Public")])
        self.assertEqual(detail.suggested_tenancy_members, 4)
        self.memberships.count.assert_called_once_with(ATTO)

    def test_without_a_suggestion_there_is_no_member_count(self):
        request = self.pending("Nothing like it")
        self.requests.fetch.return_value = request
        self.membership_service.summaries_for.return_value = []

        self.assertIsNone(self.service.detail(request.id).suggested_tenancy_members)

    def test_a_withdrawn_or_unknown_request_is_not_found(self):
        for found in (None, request_row(self.requester.id, status=TenancyRequestStatus.WITHDRAWN)):
            with self.subTest(found=found):
                self.requests.fetch.return_value = found
                with self.assertRaises(NotFoundException) as raised:
                    self.service.detail(uuid4())
                self.assertEqual(str(raised.exception), "request_not_found")


class TestApprove(AdminQueueTestCase):
    def setUp(self):
        super().setUp()
        self.request = self.pending("ATTO")
        self.requests.fetch.return_value = self.request
        self.memberships.is_member.return_value = False
        self.event_id = uuid4()
        self.requests.approve.side_effect = lambda request_id, admin_id, path, name, now: (
            request_row(
                self.requester.id,
                id=request_id,
                status=TenancyRequestStatus.APPROVED,
                tenancy=path,
                created_tenancy=name is not None,
                decided_by=admin_id,
                decided_at=now,
            ),
            self.event_id,
        )

    def code(self, tenancy=None, new_tenancy=None) -> str:
        with self.assertRaises(
            (IllegalStateException, ConflictException, NotFoundException)
        ) as raised:
            self.service.approve(self.request.id, self.admin.id, tenancy, new_tenancy)
        return str(raised.exception)

    def test_into_an_existing_tenancy(self):
        view = self.service.approve(self.request.id, self.admin.id, f" {ATTO} ", None)

        self.membership_service.require_open_for_members.assert_called_once_with(ATTO)
        self.requests.approve.assert_called_once_with(
            self.request.id, self.admin.id, ATTO, None, NOW
        )
        self.membership_service.announce_access.assert_called_once_with(
            self.requester.id, self.admin.id, ATTO, self.event_id
        )
        self.assertEqual(view.status, "approved")
        self.assertFalse(view.created_tenancy)
        self.assertEqual(view.decided_by.name, "Luciana Rizzo")

    def test_exactly_one_decision(self):
        self.assertEqual(self.code(), "invalid_request")
        self.assertEqual(
            self.code(ATTO, NewTenancy(display_name="X", namespace="x-1")), "invalid_request"
        )

    def test_a_second_decision_is_refused(self):
        self.request.status = TenancyRequestStatus.DECLINED

        self.assertEqual(self.code(ATTO), "request_not_pending")
        self.requests.approve.assert_not_called()

    def test_the_tenancy_rules_come_from_the_membership_service(self):
        self.membership_service.require_open_for_members.side_effect = ConflictException(
            "public_tenancy_locked"
        )

        self.assertEqual(self.code(DEFAULT_TENANCY), "public_tenancy_locked")

    def test_a_member_already_is_refused(self):
        self.memberships.is_member.return_value = True

        self.assertEqual(self.code(ATTO), "already_member")
        self.memberships.is_member.assert_called_once_with(self.requester.id, ATTO)

    def test_a_new_tenancy_needs_a_confirmed_email(self):
        self.membership_service.check_new_tenancy.return_value = (
            "datamap/production/atto-2",
            "ATTO 2",
        )
        self.requester.email_verified_at = None

        self.assertEqual(
            self.code(new_tenancy=NewTenancy(display_name="ATTO 2", namespace="atto-2")),
            "requester_email_unverified",
        )
        self.requests.approve.assert_not_called()

    def test_a_new_tenancy_is_created_with_the_approval(self):
        self.membership_service.check_new_tenancy.return_value = (
            "datamap/production/atto-2",
            "ATTO 2",
        )

        view = self.service.approve(
            self.request.id,
            self.admin.id,
            None,
            NewTenancy(display_name="ATTO 2", namespace="atto-2"),
        )

        self.membership_service.check_new_tenancy.assert_called_once_with("ATTO 2", "atto-2")
        self.requests.approve.assert_called_once_with(
            self.request.id, self.admin.id, "datamap/production/atto-2", "ATTO 2", NOW
        )
        self.assertTrue(view.created_tenancy)


class TestDecline(AdminQueueTestCase):
    def setUp(self):
        super().setUp()
        self.request = self.pending("ATTO")
        self.requests.fetch.return_value = self.request
        self.requests.decline.side_effect = lambda request_id, admin_id, message, now: request_row(
            self.requester.id,
            id=request_id,
            status=TenancyRequestStatus.DECLINED,
            decision_message=message,
            decided_by=admin_id,
            decided_at=now,
        )

    def test_the_message_is_trimmed_and_the_requester_told(self):
        view = self.service.decline(self.request.id, self.admin.id, "  Ask Alan  ")

        self.requests.decline.assert_called_once_with(
            self.request.id, self.admin.id, "Ask Alan", NOW
        )
        self.assertEqual(view.decision_message, "Ask Alan")
        (user, declined), _ = self.notifier.request_declined.call_args
        self.assertIs(user, self.requester)
        self.assertEqual(declined.decision_message, "Ask Alan")

    def test_an_empty_message_is_null(self):
        self.service.decline(self.request.id, self.admin.id, "   ")
        self.service.decline(self.request.id, self.admin.id, None)

        messages = [c.args[2] for c in self.requests.decline.call_args_list]
        self.assertEqual(messages, [None, None])

    def test_a_message_over_1000_characters_is_refused(self):
        with self.assertRaises(IllegalStateException) as raised:
            self.service.decline(self.request.id, self.admin.id, "x" * 1001)

        self.assertEqual(str(raised.exception), "message_invalid")

    def test_a_second_decision_is_refused(self):
        self.request.status = TenancyRequestStatus.APPROVED

        with self.assertRaises(ConflictException) as raised:
            self.service.decline(self.request.id, self.admin.id, None)

        self.assertEqual(str(raised.exception), "request_not_pending")
```

and in its imports replace

```python
from app.repository.user import UserRepository
```

with

```python
from app.model.tenancy_access import NewTenancy
from app.repository.user import UserRepository
```

Create `app/controller/v1/admin/tenancy_test.py`:

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
from app.controller.interceptor.authorization import authorize
from app.exception.conflict import ConflictException
from app.model.tenancy_access import (
    AdminTenancyRequestView,
    NewTenancy,
    Page,
    RequestCounts,
    Requester,
)
from app.service.tenancy_request import TenancyRequestService

AT = datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc)
ADMIN = uuid4()


def _row(**overrides) -> AdminTenancyRequestView:
    values = dict(
        id=uuid4(),
        requester=Requester(uuid4(), "Bruna", "b@usp.br", True, None),
        requested_name="ATTO",
        reason="r",
        status="pending",
        kind="new",
        suggested_tenancy=None,
        created_at=AT,
        tenancy=None,
        created_tenancy=False,
        decision_message=None,
        decided_by=None,
        decided_at=None,
    )
    values.update(overrides)
    return AdminTenancyRequestView(**values)


class AdminRoutesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = Container()
        app = FastAPI()
        setup.setup_routes(app)
        setup.setup_error_handlers(app)
        app.dependency_overrides[authenticate] = lambda: None
        app.dependency_overrides[authorize] = lambda: None
        cls.app = app
        cls.client = TestClient(app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls.container.unwire()

    def setUp(self):
        self.requests = Mock(spec=TenancyRequestService)
        self.container.tenancy_request_service.override(providers.Object(self.requests))
        self.headers = {"X-User-Id": str(ADMIN)}

    def tearDown(self):
        self.container.tenancy_request_service.reset_override()


class TestAdminGuard(AdminRoutesTestCase):
    def test_every_admin_tenancy_route_goes_through_casbin(self):
        for route in self.app.routes:
            path = getattr(route, "path", "")
            if path.startswith(("/v1/admin/tenanc", "/v1/admin/users")):
                with self.subTest(path=path, methods=route.methods):
                    calls = {d.call for d in route.dependant.dependencies}
                    self.assertIn(authenticate, calls)
                    self.assertIn(authorize, calls)


class TestRequestQueueRoutes(AdminRoutesTestCase):
    def test_counts(self):
        self.requests.counts.return_value = RequestCounts(open=3, join=1, new=2, closed=9)

        response = self.client.get("/v1/admin/tenancy-requests/counts", headers=self.headers)

        self.assertEqual(response.json(), {"open": 3, "join": 1, "new": 2, "closed": 9})

    def test_the_list_passes_the_query_through(self):
        self.requests.queue.return_value = Page(items=[_row()], total_count=1, limit=10, offset=0)

        response = self.client.get(
            "/v1/admin/tenancy-requests?status=open&kind=join&q=ana&limit=10&offset=0",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_count"], 1)
        self.assertEqual(response.json()["items"][0]["requester"]["name"], "Bruna")
        self.requests.queue.assert_called_once_with("open", "join", "ana", 10, 0)

    def test_the_defaults_are_open_50_0(self):
        self.requests.queue.return_value = Page(items=[], total_count=0, limit=50, offset=0)

        self.client.get("/v1/admin/tenancy-requests", headers=self.headers)

        self.requests.queue.assert_called_once_with("open", None, None, 50, 0)

    def test_a_limit_that_is_not_a_number_is_invalid_request(self):
        response = self.client.get(
            "/v1/admin/tenancy-requests?limit=many", headers=self.headers
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "invalid_request"})

    def test_approve_into_an_existing_tenancy_as_the_caller(self):
        request_id = uuid4()
        self.requests.approve.return_value = _row(id=request_id, status="approved")

        response = self.client.post(
            f"/v1/admin/tenancy-requests/{request_id}/approve",
            json={"tenancy": "datamap/production/atto"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "approved")
        self.requests.approve.assert_called_once_with(
            request_id, ADMIN, "datamap/production/atto", None
        )

    def test_approve_with_a_new_tenancy(self):
        request_id = uuid4()
        self.requests.approve.return_value = _row(id=request_id, status="approved")

        self.client.post(
            f"/v1/admin/tenancy-requests/{request_id}/approve",
            json={"new_tenancy": {"display_name": "ATTO", "namespace": "atto"}},
            headers=self.headers,
        )

        self.requests.approve.assert_called_once_with(
            request_id, ADMIN, None, NewTenancy(display_name="ATTO", namespace="atto")
        )

    def test_decline_with_and_without_a_body(self):
        request_id = uuid4()
        self.requests.decline.return_value = _row(id=request_id, status="declined")

        with_message = self.client.post(
            f"/v1/admin/tenancy-requests/{request_id}/decline",
            json={"message": "Ask Alan"},
            headers=self.headers,
        )
        without = self.client.post(
            f"/v1/admin/tenancy-requests/{request_id}/decline", headers=self.headers
        )

        self.assertEqual(with_message.status_code, 200)
        self.assertEqual(without.status_code, 200)
        self.assertEqual(
            [c.args for c in self.requests.decline.call_args_list],
            [(request_id, ADMIN, "Ask Alan"), (request_id, ADMIN, None)],
        )

    def test_a_conflict_keeps_its_code(self):
        self.requests.decline.side_effect = ConflictException("request_not_pending")

        response = self.client.post(
            f"/v1/admin/tenancy-requests/{uuid4()}/decline", json={}, headers=self.headers
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "request_not_pending"})
```

- [ ] **Step 2: Run them and see them fail**

```bash
$PY -m pytest app/service/tenancy_request_test.py app/controller/v1/admin/tenancy_test.py -q -p no:cacheprovider
```

Expected: `AttributeError: 'TenancyRequestService' object has no attribute 'counts'` (and `queue`, `detail`, `approve`, `decline`) in the service tests; `ModuleNotFoundError`-free collection but `404` on every admin route in the controller tests.

- [ ] **Step 3: Implement the service methods**

In `app/service/tenancy_request.py`, replace

```python
from datetime import datetime, timedelta
from typing import Callable
from uuid import UUID
```

with

```python
import dataclasses
from datetime import datetime, timedelta
from typing import Callable
from uuid import UUID
```

replace

```python
from app.model.tenancy import (
    REASON_MAX_LENGTH,
    TENANCY_NAME_MAX_LENGTH,
    TenancyRequestStatus,
    trimmed_within,
)
from app.model.tenancy_access import TenancyRequestView
```

with

```python
from app.model.tenancy import (
    MESSAGE_MAX_LENGTH,
    REASON_MAX_LENGTH,
    TENANCY_NAME_MAX_LENGTH,
    TenancyRequestStatus,
    TenancySummary,
    is_default,
    is_production,
    match_key,
    namespace_of,
    summary_of,
    trimmed_within,
)
from app.model.tenancy_access import (
    AdminTenancyRequestDetailView,
    AdminTenancyRequestView,
    NewTenancy,
    Page,
    RequestCounts,
    Requester,
    TenancyRequestView,
    UserRef,
)
```

replace

```python
DAILY_LIMIT = 3
WINDOW = timedelta(hours=24)
LATEST = 5
```

with

```python
DAILY_LIMIT = 3
WINDOW = timedelta(hours=24)
LATEST = 5
MAX_PAGE = 100
```

and replace

```python
    def _user_view(self, request) -> TenancyRequestView:
```

with

```python
    def counts(self) -> RequestCounts:
        index = self._suggestion_index()
        pending = self._requests.list_pending(None)
        join = sum(1 for r in pending if match_key(r.requested_name) in index)
        return RequestCounts(
            open=len(pending),
            join=join,
            new=len(pending) - join,
            closed=self._requests.count_closed(),
        )

    def queue(
        self, status: str, kind: str | None, q: str | None, limit: int, offset: int
    ) -> Page[AdminTenancyRequestView]:
        if (
            status not in ("open", "closed")
            or kind not in (None, "join", "new")
            or not 1 <= limit <= MAX_PAGE
            or offset < 0
        ):
            raise IllegalStateException("invalid_request")
        term = (q or "").strip() or None
        index = self._suggestion_index()
        if status == "closed":
            rows, total = self._requests.list_closed(term, limit, offset)
            return Page(
                items=[self._admin_view(r, index) for r in rows],
                total_count=total,
                limit=limit,
                offset=offset,
            )
        views = [self._admin_view(r, index) for r in self._requests.list_pending(term)]
        if kind is not None:
            views = [v for v in views if v.kind == kind]
        return Page(
            items=views[offset : offset + limit],
            total_count=len(views),
            limit=limit,
            offset=offset,
        )

    def detail(self, request_id: UUID) -> AdminTenancyRequestDetailView:
        request = self._visible(request_id)
        view = self._admin_view(request, self._suggestion_index())
        suggested = view.suggested_tenancy
        return AdminTenancyRequestDetailView(
            **{
                f.name: getattr(view, f.name)
                for f in dataclasses.fields(AdminTenancyRequestView)
            },
            requester_tenancies=self._membership_service.summaries_for(request.user_id),
            suggested_tenancy_members=self._memberships.count(suggested.path)
            if suggested
            else None,
        )

    def approve(
        self,
        request_id: UUID,
        admin_id: UUID,
        tenancy: str | None,
        new_tenancy: NewTenancy | None,
    ) -> AdminTenancyRequestView:
        if (tenancy is None) == (new_tenancy is None):
            raise IllegalStateException("invalid_request")
        request = self._pending(request_id)
        if tenancy is not None:
            path, display_name = tenancy.strip(), None
            self._membership_service.require_open_for_members(path)
            if self._memberships.is_member(request.user_id, path):
                raise ConflictException("already_member")
        else:
            path, display_name = self._membership_service.check_new_tenancy(
                new_tenancy.display_name, new_tenancy.namespace
            )
            requester = self._users.fetch_any_by_id(request.user_id)
            if requester is None or requester.email_verified_at is None:
                raise ConflictException("requester_email_unverified")
        approved, event_id = self._requests.approve(
            request_id, admin_id, path, display_name, self._clock()
        )
        self._membership_service.announce_access(
            approved.user_id, admin_id, path, event_id
        )
        return self._admin_view(approved, self._suggestion_index())

    def decline(
        self, request_id: UUID, admin_id: UUID, message: str | None
    ) -> AdminTenancyRequestView:
        text = trimmed_within(message, 0, MESSAGE_MAX_LENGTH)
        if text is None:
            raise IllegalStateException("message_invalid")
        self._pending(request_id)
        declined = self._requests.decline(request_id, admin_id, text or None, self._clock())
        user = self._users.fetch_any_by_id(declined.user_id)
        if user is not None:
            self._notifier.request_declined(user, declined)
        return self._admin_view(declined, self._suggestion_index())

    def _visible(self, request_id: UUID):
        request = self._requests.fetch(request_id)
        if (
            request is None
            or TenancyRequestStatus(request.status) == TenancyRequestStatus.WITHDRAWN
        ):
            raise NotFoundException("request_not_found")
        return request

    def _pending(self, request_id: UUID):
        request = self._visible(request_id)
        if TenancyRequestStatus(request.status) != TenancyRequestStatus.PENDING:
            raise ConflictException("request_not_pending")
        return request

    def _suggestion_index(self) -> dict[str, TenancySummary]:
        index: dict[str, TenancySummary] = {}
        for row in sorted(self._tenancies.list_all(), key=lambda r: r.name):
            if not row.is_enabled or not is_production(row.name) or is_default(row.name):
                continue
            summary = summary_of(row.name, row.display_name)
            index.setdefault(match_key(summary.display_name), summary)
            index.setdefault(match_key(namespace_of(row.name)), summary)
        return index

    def _admin_view(self, request, index: dict[str, TenancySummary]) -> AdminTenancyRequestView:
        suggestion = index.get(match_key(request.requested_name))
        return AdminTenancyRequestView(
            id=request.id,
            requester=self._requester(request.user_id),
            requested_name=request.requested_name,
            reason=request.reason,
            status=TenancyRequestStatus(request.status).value,
            kind="join" if suggestion else "new",
            suggested_tenancy=suggestion,
            created_at=request.created_at,
            tenancy=self._membership_service.summary(request.tenancy)
            if request.tenancy
            else None,
            created_tenancy=bool(request.created_tenancy),
            decision_message=request.decision_message,
            decided_by=self._user_ref(request.decided_by),
            decided_at=request.decided_at,
        )

    def _requester(self, user_id: UUID) -> Requester:
        user = self._users.fetch_any_by_id(user_id)
        if user is None:
            return Requester(
                id=user_id, name="Deleted account", email=None, email_verified=False, orcid=None
            )
        orcid = next((p.reference for p in user.providers if p.name == "orcid"), None)
        return Requester(
            id=user.id,
            name=user.name,
            email=user.email,
            email_verified=user.email_verified_at is not None,
            orcid=orcid,
        )

    def _user_ref(self, user_id: UUID | None) -> UserRef | None:
        if user_id is None:
            return None
        user = self._users.fetch_any_by_id(user_id)
        return UserRef(id=user.id, name=user.name) if user else None

    def _user_view(self, request) -> TenancyRequestView:
```

- [ ] **Step 4: Implement the admin routes**

Create `app/controller/v1/admin/tenancy.py`:

```python
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.tenancy.access_resource import (
    AdminTenancyRequestDetailResponse,
    AdminTenancyRequestPage,
    AdminTenancyRequestResponse,
    ApproveBody,
    DeclineBody,
    RequestCountsResponse,
)
from app.model.tenancy_access import NewTenancy
from app.service.tenancy_request import TenancyRequestService

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


@router.get("/tenancy-requests/counts", response_model=RequestCountsResponse)
@inject
def request_counts(
    service: TenancyRequestService = Depends(Provide[Container.tenancy_request_service]),
) -> RequestCountsResponse:
    return RequestCountsResponse.model_validate(service.counts())


@router.get("/tenancy-requests", response_model=AdminTenancyRequestPage)
@inject
def list_requests(
    status: str = "open",
    kind: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    service: TenancyRequestService = Depends(Provide[Container.tenancy_request_service]),
) -> AdminTenancyRequestPage:
    return AdminTenancyRequestPage.model_validate(
        service.queue(status, kind, q, limit, offset)
    )


@router.get(
    "/tenancy-requests/{request_id}", response_model=AdminTenancyRequestDetailResponse
)
@inject
def request_detail(
    request_id: UUID,
    service: TenancyRequestService = Depends(Provide[Container.tenancy_request_service]),
) -> AdminTenancyRequestDetailResponse:
    return AdminTenancyRequestDetailResponse.model_validate(service.detail(request_id))


@router.post(
    "/tenancy-requests/{request_id}/approve", response_model=AdminTenancyRequestResponse
)
@inject
def approve_request(
    request_id: UUID,
    body: ApproveBody,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyRequestService = Depends(Provide[Container.tenancy_request_service]),
) -> AdminTenancyRequestResponse:
    new_tenancy = (
        NewTenancy(
            display_name=body.new_tenancy.display_name,
            namespace=body.new_tenancy.namespace,
        )
        if body.new_tenancy is not None
        else None
    )
    return AdminTenancyRequestResponse.model_validate(
        service.approve(request_id, user_id, body.tenancy, new_tenancy)
    )


@router.post(
    "/tenancy-requests/{request_id}/decline", response_model=AdminTenancyRequestResponse
)
@inject
def decline_request(
    request_id: UUID,
    body: DeclineBody | None = None,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyRequestService = Depends(Provide[Container.tenancy_request_service]),
) -> AdminTenancyRequestResponse:
    return AdminTenancyRequestResponse.model_validate(
        service.decline(request_id, user_id, body.message if body else None)
    )
```

In `app/container.py`, replace

```python
            "app.controller.v1.admin.email",
```

with

```python
            "app.controller.v1.admin.email",
            "app.controller.v1.admin.tenancy",
```

In `app/setup.py`, replace

```python
from app.controller.v1.admin.email import router as admin_email_router
```

with

```python
from app.controller.v1.admin.email import router as admin_email_router
from app.controller.v1.admin.tenancy import router as admin_tenancy_router
```

and replace

```python
    fastAPIApp.include_router(admin_email_router, prefix="/v1")
```

with

```python
    fastAPIApp.include_router(admin_email_router, prefix="/v1")
    fastAPIApp.include_router(admin_tenancy_router, prefix="/v1")
```

- [ ] **Step 5: Run them and see them pass**

```bash
$PY -m pytest app/service/tenancy_request_test.py app/controller/v1/admin app/controller/routes_security_test.py -q -p no:cacheprovider
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
pwd && command git branch --show-current
command git add app/service/tenancy_request.py app/service/tenancy_request_test.py app/controller/v1/admin/tenancy.py app/controller/v1/admin/tenancy_test.py app/container.py app/setup.py
command git commit -m "feat: admins see, approve and decline tenancy requests (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 12: Tenancy invitations — invite from a dataset, lookup, accept, decline, withdraw; share state

**Files:**
- Create: `app/repository/tenancy_invitation.py`
- Create: `app/service/tenancy_invitation.py`, `app/service/tenancy_invitation_test.py`
- Modify: `app/service/share.py`, `app/service/share_test.py`
- Modify: `app/model/sharing.py`, `app/controller/v1/dataset/share_resource.py`
- Create: `app/controller/v1/dataset/tenancy_invitation.py`, `app/controller/v1/dataset/tenancy_invitation_test.py`
- Modify: `app/controller/v1/user/tenancy_access.py`, `app/controller/v1/user/tenancy_access_test.py`
- Modify: `app/controller/v1/admin/tenancy.py`, `app/controller/v1/admin/tenancy_test.py`
- Modify: `app/container.py`, `app/setup.py`

**Interfaces:**
- Consumes: `DatasetService.fetch_authorized` (returns `(dataset, allowed, level)`; `404` when the caller cannot see it, `403` when `WRITE` is not allowed), `TenancyMembershipService` (Task 8), `TenancyNotifier` (Task 7), `normalise_email`/`normalise_orcid` (`app/service/share_identity.py`).
- Produces (`TenancyInvitationRepository`): `create(tenancy, user_id, invited_by, dataset_id) -> TenancyInvitation` (writes `invitation_created`; `ConflictException("invitation_pending")` on the partial unique index), `fetch(invitation_id)`, `has_pending(tenancy, user_id) -> bool`, `pending_for_user(user_id)`, `pending_for_dataset(dataset_id)`, `pending_for_tenancy(tenancy)` (each newest first), `dataset_names(dataset_ids) -> dict[UUID, str]`, `close(invitation_id, status, closed_by, event_type) -> bool` (pending only), `accept(invitation_id, user_id) -> bool` (pending and the invitee's only; adds the membership; writes `invitation_accepted` and, when the membership is new, `member_added` with the invitation id).
- Produces (`TenancyInvitationService`): `lookup(dataset_id, user_id, value) -> ShareLookupView`, `may_invite(dataset, level, user_id) -> bool`, `invite(dataset_id, user_id, invitee_id) -> DatasetTenancyInvitationView`, `withdraw(dataset_id, user_id, invitation_id) -> None`, `withdraw_as_admin(invitation_id, admin_id) -> None`, `share_additions(dataset, level, user_id) -> tuple[list[DatasetTenancyInvitationView], bool]`, `pending_for_user(user_id) -> list[TenancyInvitationView]`, `accept(user_id, invitation_id) -> TenancySummary`, `decline(user_id, invitation_id) -> None`.
  - **May invite:** level `owner` or `write` (RFC 003 permission; a member editing only through *members can edit* has level `tenancy` and may not) **and** a member of the dataset's tenancy; the tenancy enabled, production, not public. Otherwise `invite` answers `403 forbidden`, then `409 public_tenancy_locked` / `legacy_tenancy_read_only` / `tenancy_disabled`, then `404 no_account`, `409 already_member`, `409 invitation_pending`.
  - **Lookup:** open to the callers of RFC 003's grant (`WRITE` on the dataset); value with `@` is an email, otherwise an ORCID iD; malformed → `400 invalid_request`; unknown or disabled → `404 no_account`.
- Produces: `ShareService(..., tenancy_repository, membership_service, tenancy_invitations, clock=...)`; `candidates` returns `[]` for a dataset in public; `state` fills `TenancyAccess.name` with the resolved display name, `is_default`, `is_legacy`, `datasets`, and `ShareState.tenancy_invitations`, `can_invite_to_tenancy`.
- Produces routes: `GET /v1/datasets/{dataset_id}/share/lookup?value=` → `200 ShareLookup`; `POST /v1/datasets/{dataset_id}/tenancy-invitations` `{user_id}` → `201 DatasetTenancyInvitation`; `DELETE /v1/datasets/{dataset_id}/tenancy-invitations/{invitation_id}` → `204`; `GET /v1/users/{id}/tenancy-invitations` → `200 TenancyInvitation[]`; `POST /v1/users/{id}/tenancy-invitations/{invitation_id}/accept` → `200 {tenancy}`; `POST /v1/users/{id}/tenancy-invitations/{invitation_id}/decline` → `204`; `DELETE /v1/admin/tenancy-invitations/{invitation_id}` → `204`.

- [ ] **Step 1: Write the failing tests**

Create `app/service/tenancy_invitation_test.py`:

```python
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.exception.conflict import ConflictException
from app.exception.forbidden import ForbiddenException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.model.dataset_access import AccessLevel, DatasetAction
from app.model.tenancy import (
    DEFAULT_TENANCY,
    TenancyEventType,
    TenancyInvitationStatus,
    summary_of,
)
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_invitation import TenancyInvitationRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.user import UserRepository
from app.service.dataset import DatasetService
from app.service.tenancy_invitation import TenancyInvitationService
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_notifier import TenancyNotifier

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
ATTO = "datamap/production/atto"
CALLER = uuid4()


def person(name="Bruna Costa", email="bruna@usp.br"):
    return SimpleNamespace(id=uuid4(), name=name, email=email)


def invitation_row(**overrides):
    values = dict(
        id=uuid4(),
        tenancy=ATTO,
        user_id=uuid4(),
        invited_by=CALLER,
        dataset_id=uuid4(),
        status=TenancyInvitationStatus.PENDING,
        created_at=NOW,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class InvitationServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.datasets = Mock(spec=DatasetService)
        self.invitations = Mock(spec=TenancyInvitationRepository)
        self.memberships = Mock(spec=TenancyMembershipRepository)
        self.membership_service = Mock(spec=TenancyMembershipService)
        self.membership_service.summary.side_effect = lambda path: summary_of(path, "ATTO")
        self.tenancies = Mock(spec=TenancyRepository)
        self.tenancies.fetch_any.side_effect = lambda path: SimpleNamespace(
            name=path, display_name=None, is_enabled=True
        )
        self.tenancies.count_datasets.return_value = 12
        self.users = Mock(spec=UserRepository)
        self.notifier = Mock(spec=TenancyNotifier)
        self.caller = SimpleNamespace(id=CALLER, name="Alan Calheiros", email="alan@usp.br")
        self.invitee = person()
        self.people = {CALLER: self.caller, self.invitee.id: self.invitee}
        self.users.fetch_any_by_id.side_effect = self.people.get
        self.users.fetch_by_id.side_effect = lambda id, is_enabled=True: self.people.get(id)
        self.dataset = SimpleNamespace(id=uuid4(), name="Ozone at ATTO", tenancy=ATTO)
        self.level = AccessLevel.OWNER
        self.datasets.fetch_authorized.side_effect = lambda **kwargs: (
            self.dataset,
            [ATTO],
            self.level,
        )
        self.members = {(CALLER, ATTO)}
        self.memberships.is_member.side_effect = lambda user_id, tenancy: (
            (user_id, tenancy) in self.members
        )
        self.invitations.has_pending.return_value = False
        self.invitations.create.side_effect = lambda tenancy, user_id, invited_by, dataset_id: invitation_row(
            tenancy=tenancy, user_id=user_id, invited_by=invited_by, dataset_id=dataset_id
        )
        self.service = TenancyInvitationService(
            dataset_service=self.datasets,
            invitations=self.invitations,
            memberships=self.memberships,
            membership_service=self.membership_service,
            tenancies=self.tenancies,
            users=self.users,
            notifier=self.notifier,
        )


class TestWhoMayInvite(InvitationServiceTestCase):
    def invite(self):
        return self.service.invite(self.dataset.id, CALLER, self.invitee.id)

    def test_the_owner_who_is_a_member_invites(self):
        view = self.invite()

        self.invitations.create.assert_called_once_with(
            ATTO, self.invitee.id, CALLER, self.dataset.id
        )
        self.assertEqual(view.user.name, "Bruna Costa")
        self.assertEqual(view.invited_by.name, "Alan Calheiros")
        self.assertTrue(view.can_withdraw)
        self.assertEqual(
            self.datasets.fetch_authorized.call_args.kwargs["action"], DatasetAction.WRITE
        )

    def test_a_write_collaborator_who_is_a_member_invites(self):
        self.level = AccessLevel.WRITE

        self.invite()

        self.invitations.create.assert_called_once()

    def test_a_member_who_edits_only_because_members_can_edit_may_not(self):
        self.level = AccessLevel.TENANCY

        with self.assertRaises(ForbiddenException):
            self.invite()

    def test_a_write_collaborator_outside_the_tenancy_may_not(self):
        self.level = AccessLevel.WRITE
        self.members = set()

        with self.assertRaises(ForbiddenException):
            self.invite()
        self.invitations.create.assert_not_called()

    def test_a_reader_may_not(self):
        self.datasets.fetch_authorized.side_effect = ForbiddenException("forbidden")

        with self.assertRaises(ForbiddenException):
            self.invite()


class TestInviteRules(InvitationServiceTestCase):
    def code(self) -> str:
        with self.assertRaises((ConflictException, NotFoundException)) as raised:
            self.service.invite(self.dataset.id, CALLER, self.invitee.id)
        return str(raised.exception)

    def test_the_tenancy_must_be_open_for_members(self):
        self.membership_service.require_open_for_members.side_effect = ConflictException(
            "legacy_tenancy_read_only"
        )

        self.assertEqual(self.code(), "legacy_tenancy_read_only")
        self.membership_service.require_open_for_members.assert_called_once_with(ATTO)

    def test_an_unknown_or_disabled_invitee_has_no_account(self):
        self.people.pop(self.invitee.id)

        self.assertEqual(self.code(), "no_account")

    def test_a_member_is_already_in(self):
        self.members.add((self.invitee.id, ATTO))

        self.assertEqual(self.code(), "already_member")

    def test_one_pending_invitation_per_person_and_tenancy(self):
        self.invitations.has_pending.return_value = True

        self.assertEqual(self.code(), "invitation_pending")

    def test_the_invitee_and_the_admins_are_told(self):
        view = self.service.invite(self.dataset.id, CALLER, self.invitee.id)

        self.notifier.invitation.assert_called_once_with(
            self.invitee, "Alan Calheiros", summary_of(ATTO, "ATTO"), "Ozone at ATTO", view.id
        )
        self.notifier.invitation_notice.assert_called_once_with(
            self.invitee, "Alan Calheiros", summary_of(ATTO, "ATTO"), "Ozone at ATTO", view.id
        )


class TestLookup(InvitationServiceTestCase):
    def test_an_exact_email_outside_the_tenancy_can_be_invited(self):
        self.users.fetch_by_email_insensitive.return_value = self.invitee

        found = self.service.lookup(self.dataset.id, CALLER, "  Bruna@USP.br ")

        self.users.fetch_by_email_insensitive.assert_called_once_with("bruna@usp.br")
        self.assertEqual(found.user.email, "bruna@usp.br")
        self.assertFalse(found.tenancy_member)
        self.assertFalse(found.invitation_pending)
        self.assertTrue(found.can_invite)

    def test_an_orcid_is_looked_up_as_a_provider(self):
        self.users.fetch_by_provider.return_value = self.invitee

        self.service.lookup(self.dataset.id, CALLER, "https://orcid.org/0000-0002-1825-0097")

        self.users.fetch_by_provider.assert_called_once_with(
            provider_name="orcid", reference="0000-0002-1825-0097"
        )

    def test_a_member_or_a_pending_invitee_cannot_be_invited_again(self):
        self.users.fetch_by_email_insensitive.return_value = self.invitee
        self.invitations.has_pending.return_value = True

        found = self.service.lookup(self.dataset.id, CALLER, "bruna@usp.br")

        self.assertTrue(found.invitation_pending)
        self.assertFalse(found.can_invite)

    def test_in_public_nobody_can_be_invited(self):
        self.dataset.tenancy = DEFAULT_TENANCY
        self.members.add((CALLER, DEFAULT_TENANCY))
        self.users.fetch_by_email_insensitive.return_value = self.invitee

        self.assertFalse(self.service.lookup(self.dataset.id, CALLER, "bruna@usp.br").can_invite)

    def test_a_malformed_value_is_invalid_request(self):
        for value in ("not an address", "0000-0002-1825-0098", ""):
            with self.subTest(value=value):
                with self.assertRaises(IllegalStateException) as raised:
                    self.service.lookup(self.dataset.id, CALLER, value)
                self.assertEqual(str(raised.exception), "invalid_request")

    def test_nobody_found_is_no_account(self):
        self.users.fetch_by_email_insensitive.return_value = None

        with self.assertRaises(NotFoundException) as raised:
            self.service.lookup(self.dataset.id, CALLER, "ghost@usp.br")

        self.assertEqual(str(raised.exception), "no_account")


class TestWithdraw(InvitationServiceTestCase):
    def test_the_inviter_withdraws_through_the_dataset(self):
        invitation = invitation_row(dataset_id=self.dataset.id)
        self.invitations.fetch.return_value = invitation
        self.invitations.close.return_value = True

        self.service.withdraw(self.dataset.id, CALLER, invitation.id)

        self.invitations.close.assert_called_once_with(
            invitation.id,
            TenancyInvitationStatus.WITHDRAWN,
            CALLER,
            TenancyEventType.INVITATION_WITHDRAWN,
        )

    def test_another_editor_is_forbidden(self):
        self.invitations.fetch.return_value = invitation_row(
            dataset_id=self.dataset.id, invited_by=uuid4()
        )

        with self.assertRaises(ForbiddenException):
            self.service.withdraw(self.dataset.id, CALLER, uuid4())

    def test_an_invitation_of_another_dataset_or_not_pending_is_not_found(self):
        for row in (
            invitation_row(),
            invitation_row(dataset_id=self.dataset.id, status=TenancyInvitationStatus.ACCEPTED),
            None,
        ):
            with self.subTest(row=row):
                self.invitations.fetch.return_value = row
                with self.assertRaises(NotFoundException) as raised:
                    self.service.withdraw(self.dataset.id, CALLER, uuid4())
                self.assertEqual(str(raised.exception), "invitation_not_found")

    def test_an_admin_withdraws_any_pending_one(self):
        self.invitations.close.return_value = True
        admin, invitation_id = uuid4(), uuid4()

        self.service.withdraw_as_admin(invitation_id, admin)

        self.invitations.close.assert_called_once_with(
            invitation_id,
            TenancyInvitationStatus.WITHDRAWN,
            admin,
            TenancyEventType.INVITATION_WITHDRAWN,
        )

    def test_an_admin_withdrawing_a_closed_one_is_not_found(self):
        self.invitations.close.return_value = False

        with self.assertRaises(NotFoundException):
            self.service.withdraw_as_admin(uuid4(), uuid4())


class TestInviteeSide(InvitationServiceTestCase):
    def test_pending_invitations_say_who_from_where_and_how_many_datasets(self):
        invitation = invitation_row(user_id=self.invitee.id)
        self.invitations.pending_for_user.return_value = [invitation]
        self.invitations.dataset_names.return_value = {invitation.dataset_id: "Ozone at ATTO"}

        (view,) = self.service.pending_for_user(self.invitee.id)

        self.assertEqual(view.tenancy, summary_of(ATTO, "ATTO"))
        self.assertEqual(view.invited_by.name, "Alan Calheiros")
        self.assertEqual(view.dataset.name, "Ozone at ATTO")
        self.assertEqual(view.datasets, 12)

    def test_a_dataset_that_is_gone_is_null(self):
        invitation = invitation_row(user_id=self.invitee.id, dataset_id=None)
        self.invitations.pending_for_user.return_value = [invitation]
        self.invitations.dataset_names.return_value = {}

        self.assertIsNone(self.service.pending_for_user(self.invitee.id)[0].dataset)

    def test_accepting_joins_the_tenancy(self):
        invitation = invitation_row(user_id=self.invitee.id)
        self.invitations.fetch.return_value = invitation
        self.invitations.accept.return_value = True

        summary = self.service.accept(self.invitee.id, invitation.id)

        self.invitations.accept.assert_called_once_with(invitation.id, self.invitee.id)
        self.assertEqual(summary, summary_of(ATTO, "ATTO"))

    def test_only_the_invitee_accepts_a_pending_one(self):
        for row in (
            invitation_row(),
            invitation_row(user_id=self.invitee.id, status=TenancyInvitationStatus.WITHDRAWN),
            None,
        ):
            with self.subTest(row=row):
                self.invitations.fetch.return_value = row
                with self.assertRaises(NotFoundException) as raised:
                    self.service.accept(self.invitee.id, uuid4())
                self.assertEqual(str(raised.exception), "invitation_not_found")

    def test_a_disabled_tenancy_cannot_be_joined(self):
        self.invitations.fetch.return_value = invitation_row(user_id=self.invitee.id)
        self.tenancies.fetch_any.side_effect = lambda path: SimpleNamespace(
            name=path, display_name=None, is_enabled=False
        )

        with self.assertRaises(ConflictException) as raised:
            self.service.accept(self.invitee.id, uuid4())

        self.assertEqual(str(raised.exception), "tenancy_disabled")
        self.invitations.accept.assert_not_called()

    def test_declining(self):
        invitation = invitation_row(user_id=self.invitee.id)
        self.invitations.fetch.return_value = invitation
        self.invitations.close.return_value = True

        self.service.decline(self.invitee.id, invitation.id)

        self.invitations.close.assert_called_once_with(
            invitation.id,
            TenancyInvitationStatus.DECLINED,
            self.invitee.id,
            TenancyEventType.INVITATION_DECLINED,
        )


class TestShareAdditions(InvitationServiceTestCase):
    def test_pending_invitations_of_the_dataset_and_whether_the_caller_may_invite(self):
        mine = invitation_row(user_id=self.invitee.id, dataset_id=self.dataset.id)
        theirs = invitation_row(
            user_id=self.invitee.id, dataset_id=self.dataset.id, invited_by=None
        )
        self.invitations.pending_for_dataset.return_value = [mine, theirs]

        views, can_invite = self.service.share_additions(self.dataset, AccessLevel.OWNER, CALLER)

        self.assertEqual([v.can_withdraw for v in views], [True, False])
        self.assertIsNone(views[1].invited_by)
        self.assertTrue(can_invite)

    def test_a_staging_or_disabled_tenancy_cannot_be_invited_to(self):
        self.dataset.tenancy = "datamap/staging/data-amazon"
        self.members.add((CALLER, self.dataset.tenancy))

        self.assertFalse(self.service.may_invite(self.dataset, AccessLevel.OWNER, CALLER))
```

Append to `app/service/share_test.py`:

```python


class TestTenancyInShareState(ShareServiceTestCase):
    def setUp(self):
        super().setUp()
        self.invitations.list_for_dataset.return_value = []
        self.anonymous_links.list_with_views.return_value = []
        self.users.count_in_tenancy.return_value = 3
        self.dataset.embargo_until = None

    def test_candidates_are_off_in_public(self):
        self.dataset.tenancy = DEFAULT_TENANCY

        self.assertEqual(self.service.candidates(self.dataset.id, CALLER, "ana"), [])
        self.users.search_share_candidates.assert_not_called()

    def test_the_tenancy_row_names_public_and_never_lets_members_edit(self):
        self.dataset.tenancy = DEFAULT_TENANCY
        self.dataset.members_can_edit = True
        self.tenancy_repository.count_datasets.return_value = 40

        tenancy = self.service.state(self.dataset.id, OWNER).tenancy

        self.assertEqual(tenancy.name, "Public")
        self.assertTrue(tenancy.is_default)
        self.assertFalse(tenancy.is_legacy)
        self.assertEqual(tenancy.datasets, 40)
        self.assertFalse(tenancy.members_can_edit)

    def test_pending_tenancy_invitations_and_whether_the_caller_may_invite(self):
        view = DatasetTenancyInvitationView(
            id=uuid4(),
            user=UserBrief(id=uuid4(), name="Bruna"),
            invited_by=None,
            created_at=NOW,
            can_withdraw=True,
        )
        self.tenancy_invitations.share_additions.return_value = ([view], True)

        state = self.service.state(self.dataset.id, OWNER)

        self.assertEqual(state.tenancy_invitations, [view])
        self.assertTrue(state.can_invite_to_tenancy)
        self.tenancy_invitations.share_additions.assert_called_once_with(
            self.dataset, AccessLevel.OWNER, OWNER
        )
```

In `app/service/share_test.py`, replace

```python
from app.service.user import UserService

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
```

with

```python
from app.service.user import UserService
from app.model.tenancy import DEFAULT_TENANCY, summary_of
from app.model.tenancy_access import DatasetTenancyInvitationView, UserBrief
from app.repository.tenancy import TenancyRepository
from app.service.tenancy_invitation import TenancyInvitationService
from app.service.tenancy_membership import TenancyMembershipService

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
```

and replace

```python
        self.service = ShareService(
            dataset_service=self.datasets,
            dataset_repository=self.dataset_repository,
            permission_repository=self.permissions,
            permission_service=self.permission_service,
            invitation_repository=self.invitations,
            anonymous_link_repository=self.anonymous_links,
            user_repository=self.users,
            user_service=self.user_service,
            audit=self.audit,
            email_service=self.email,
            public_base_url="https://datamap.pcs.usp.br",
            clock=lambda: NOW,
        )
```

with

```python
        self.tenancy_repository = Mock(spec=TenancyRepository)
        self.tenancy_repository.count_datasets.return_value = 0
        self.membership_service = Mock(spec=TenancyMembershipService)
        self.membership_service.summary.side_effect = lambda path: summary_of(path, None)
        self.tenancy_invitations = Mock(spec=TenancyInvitationService)
        self.tenancy_invitations.share_additions.return_value = ([], False)
        self.service = ShareService(
            dataset_service=self.datasets,
            dataset_repository=self.dataset_repository,
            permission_repository=self.permissions,
            permission_service=self.permission_service,
            invitation_repository=self.invitations,
            anonymous_link_repository=self.anonymous_links,
            user_repository=self.users,
            user_service=self.user_service,
            audit=self.audit,
            email_service=self.email,
            public_base_url="https://datamap.pcs.usp.br",
            tenancy_repository=self.tenancy_repository,
            membership_service=self.membership_service,
            tenancy_invitations=self.tenancy_invitations,
            clock=lambda: NOW,
        )
```

`share_preview_test.py` builds on `ShareServiceTestCase` and needs no change: its tenancy row still reads `Data Amazon` from the derived name.

Create `app/controller/v1/dataset/tenancy_invitation_test.py`:

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
from app.controller.interceptor.authorization import authorize
from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.model.tenancy_access import (
    DatasetTenancyInvitationView,
    ShareLookupView,
    UserBrief,
)
from app.service.tenancy_invitation import TenancyInvitationService

AT = datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc)
CALLER = uuid4()


class DatasetInvitationRoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = Container()
        app = FastAPI()
        setup.setup_routes(app)
        setup.setup_error_handlers(app)
        app.dependency_overrides[authenticate] = lambda: None
        app.dependency_overrides[authorize] = lambda: None
        cls.client = TestClient(app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls.container.unwire()

    def setUp(self):
        self.service = Mock(spec=TenancyInvitationService)
        self.container.tenancy_invitation_service.override(providers.Object(self.service))
        self.headers = {"X-User-Id": str(CALLER)}
        self.dataset_id = uuid4()

    def tearDown(self):
        self.container.tenancy_invitation_service.reset_override()

    def test_lookup(self):
        self.service.lookup.return_value = ShareLookupView(
            user=UserBrief(id=uuid4(), name="Bruna", email="b@usp.br"),
            tenancy_member=False,
            invitation_pending=False,
            can_invite=True,
        )

        response = self.client.get(
            f"/v1/datasets/{self.dataset_id}/share/lookup?value=b@usp.br",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["can_invite"], True)
        self.service.lookup.assert_called_once_with(self.dataset_id, CALLER, "b@usp.br")

    def test_lookup_without_a_value_or_with_a_bad_one_is_invalid_request(self):
        self.service.lookup.side_effect = IllegalStateException("invalid_request")

        missing = self.client.get(
            f"/v1/datasets/{self.dataset_id}/share/lookup", headers=self.headers
        )
        bad = self.client.get(
            f"/v1/datasets/{self.dataset_id}/share/lookup?value=nope", headers=self.headers
        )

        for response in (missing, bad):
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), {"detail": "invalid_request"})

    def test_invite_answers_201_with_the_invitation_unwrapped(self):
        invitee = uuid4()
        self.service.invite.return_value = DatasetTenancyInvitationView(
            id=uuid4(),
            user=UserBrief(id=invitee, name="Bruna", email="b@usp.br"),
            invited_by=UserBrief(id=CALLER, name="Alan", email=None),
            created_at=AT,
            can_withdraw=True,
        )

        response = self.client.post(
            f"/v1/datasets/{self.dataset_id}/tenancy-invitations",
            json={"user_id": str(invitee)},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user"]["id"], str(invitee))
        self.assertTrue(response.json()["can_withdraw"])
        self.service.invite.assert_called_once_with(self.dataset_id, CALLER, invitee)

    def test_invite_keeps_the_conflict_code(self):
        self.service.invite.side_effect = ConflictException("invitation_pending")

        response = self.client.post(
            f"/v1/datasets/{self.dataset_id}/tenancy-invitations",
            json={"user_id": str(uuid4())},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "invitation_pending"})

    def test_withdraw(self):
        invitation_id = uuid4()

        response = self.client.delete(
            f"/v1/datasets/{self.dataset_id}/tenancy-invitations/{invitation_id}",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 204)
        self.service.withdraw.assert_called_once_with(self.dataset_id, CALLER, invitation_id)
```

Append to `app/controller/v1/user/tenancy_access_test.py`:

```python


class TestInvitationRoutes(SelfRoutesTestCase):
    def setUp(self):
        super().setUp()
        self.invitations = Mock(spec=TenancyInvitationService)
        self.container.tenancy_invitation_service.override(providers.Object(self.invitations))

    def tearDown(self):
        self.container.tenancy_invitation_service.reset_override()
        super().tearDown()

    def test_pending_invitations(self):
        self.invitations.pending_for_user.return_value = [
            TenancyInvitationView(
                id=uuid4(),
                tenancy=summary_of("datamap/production/atto", "ATTO"),
                invited_by=UserRef(id=uuid4(), name="Alan"),
                dataset=DatasetRef(id=uuid4(), name="Ozone"),
                datasets=12,
                created_at=AT,
            )
        ]

        response = self.client.get(f"/v1/users/{self.user_id}/tenancy-invitations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["datasets"], 12)
        self.assertEqual(response.json()[0]["tenancy"]["display_name"], "ATTO")

    def test_accept_answers_the_tenancy(self):
        invitation_id = uuid4()
        self.invitations.accept.return_value = summary_of("datamap/production/atto", "ATTO")

        response = self.client.post(
            f"/v1/users/{self.user_id}/tenancy-invitations/{invitation_id}/accept"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tenancy"]["path"], "datamap/production/atto")
        self.invitations.accept.assert_called_once_with(self.user_id, invitation_id)

    def test_decline_answers_204(self):
        invitation_id = uuid4()

        response = self.client.post(
            f"/v1/users/{self.user_id}/tenancy-invitations/{invitation_id}/decline"
        )

        self.assertEqual(response.status_code, 204)
        self.invitations.decline.assert_called_once_with(self.user_id, invitation_id)

    def test_an_invitation_that_is_not_theirs_is_404(self):
        self.invitations.accept.side_effect = NotFoundException("invitation_not_found")

        response = self.client.post(
            f"/v1/users/{self.user_id}/tenancy-invitations/{uuid4()}/accept"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "invitation_not_found"})
```

and in its imports replace

```python
from app.model.tenancy_access import TenancyRequestView
from app.service.tenancy_membership import TenancyMembershipService
```

with

```python
from app.model.tenancy_access import (
    DatasetRef,
    TenancyInvitationView,
    TenancyRequestView,
    UserRef,
)
from app.service.tenancy_invitation import TenancyInvitationService
from app.service.tenancy_membership import TenancyMembershipService
```

Append to `app/controller/v1/admin/tenancy_test.py`:

```python


class TestAdminInvitationRoutes(AdminRoutesTestCase):
    def setUp(self):
        super().setUp()
        self.invitations = Mock(spec=TenancyInvitationService)
        self.container.tenancy_invitation_service.override(providers.Object(self.invitations))

    def tearDown(self):
        self.container.tenancy_invitation_service.reset_override()
        super().tearDown()

    def test_an_admin_withdraws_an_invitation(self):
        invitation_id = uuid4()

        response = self.client.delete(
            f"/v1/admin/tenancy-invitations/{invitation_id}", headers=self.headers
        )

        self.assertEqual(response.status_code, 204)
        self.invitations.withdraw_as_admin.assert_called_once_with(invitation_id, ADMIN)
```

and in its imports replace

```python
from app.service.tenancy_request import TenancyRequestService
```

with

```python
from app.service.tenancy_invitation import TenancyInvitationService
from app.service.tenancy_request import TenancyRequestService
```

- [ ] **Step 2: Run them and see them fail**

```bash
$PY -m pytest app/service/tenancy_invitation_test.py app/service/share_test.py app/service/share_preview_test.py app/controller/v1/dataset/tenancy_invitation_test.py app/controller/v1/user/tenancy_access_test.py app/controller/v1/admin/tenancy_test.py -q -p no:cacheprovider
```

Expected: `ModuleNotFoundError: No module named 'app.repository.tenancy_invitation'` / `'app.service.tenancy_invitation'` across the files.

- [ ] **Step 3: Implement the repository**

Create `app/repository/tenancy_invitation.py`:

```python
from contextlib import AbstractContextManager
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exception.conflict import ConflictException
from app.model.db.dataset import Dataset
from app.model.db.tenancy import TenancyInvitation
from app.model.tenancy import TenancyEventType, TenancyInvitationStatus
from app.repository.tenancy_event import add_event
from app.repository.tenancy_membership import insert_membership

PENDING = TenancyInvitationStatus.PENDING


class TenancyInvitationRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def create(
        self, tenancy: str, user_id: UUID, invited_by: UUID, dataset_id: UUID | None
    ) -> TenancyInvitation:
        try:
            with self._session_factory() as session:
                invitation = TenancyInvitation(
                    id=uuid4(),
                    tenancy=tenancy,
                    user_id=user_id,
                    invited_by=invited_by,
                    dataset_id=dataset_id,
                    status=PENDING,
                )
                session.add(invitation)
                session.flush()
                add_event(
                    session,
                    tenancy=tenancy,
                    event_type=TenancyEventType.INVITATION_CREATED,
                    user_id=user_id,
                    actor_id=invited_by,
                    invitation_id=invitation.id,
                )
                session.commit()
                session.refresh(invitation)
                return invitation
        except IntegrityError:
            raise ConflictException("invitation_pending")

    def fetch(self, invitation_id: UUID) -> TenancyInvitation | None:
        with self._session_factory() as session:
            return session.query(TenancyInvitation).filter_by(id=invitation_id).first()

    def has_pending(self, tenancy: str, user_id: UUID) -> bool:
        with self._session_factory() as session:
            return (
                session.query(TenancyInvitation.id)
                .filter_by(tenancy=tenancy, user_id=user_id, status=PENDING)
                .first()
                is not None
            )

    def _pending(self, **filters) -> list[TenancyInvitation]:
        with self._session_factory() as session:
            return (
                session.query(TenancyInvitation)
                .filter_by(status=PENDING, **filters)
                .order_by(TenancyInvitation.created_at.desc())
                .all()
            )

    def pending_for_user(self, user_id: UUID) -> list[TenancyInvitation]:
        return self._pending(user_id=user_id)

    def pending_for_dataset(self, dataset_id: UUID) -> list[TenancyInvitation]:
        return self._pending(dataset_id=dataset_id)

    def pending_for_tenancy(self, tenancy: str) -> list[TenancyInvitation]:
        return self._pending(tenancy=tenancy)

    def dataset_names(self, dataset_ids: list[UUID | None]) -> dict[UUID, str]:
        ids = [dataset_id for dataset_id in dataset_ids if dataset_id is not None]
        if not ids:
            return {}
        with self._session_factory() as session:
            rows = session.query(Dataset.id, Dataset.name).filter(Dataset.id.in_(ids)).all()
            return {dataset_id: name for dataset_id, name in rows}

    def close(
        self,
        invitation_id: UUID,
        status: TenancyInvitationStatus,
        closed_by: UUID,
        event_type: TenancyEventType,
    ) -> bool:
        with self._session_factory() as session:
            invitation = (
                session.query(TenancyInvitation)
                .filter_by(id=invitation_id, status=PENDING)
                .with_for_update()
                .first()
            )
            if invitation is None:
                return False
            invitation.status = status
            invitation.closed_by = closed_by
            invitation.closed_at = func.now()
            add_event(
                session,
                tenancy=invitation.tenancy,
                event_type=event_type,
                user_id=invitation.user_id,
                actor_id=closed_by,
                invitation_id=invitation.id,
            )
            session.commit()
            return True

    def accept(self, invitation_id: UUID, user_id: UUID) -> bool:
        with self._session_factory() as session:
            invitation = (
                session.query(TenancyInvitation)
                .filter_by(id=invitation_id, user_id=user_id, status=PENDING)
                .with_for_update()
                .first()
            )
            if invitation is None:
                return False
            invitation.status = TenancyInvitationStatus.ACCEPTED
            invitation.closed_by = user_id
            invitation.closed_at = func.now()
            add_event(
                session,
                tenancy=invitation.tenancy,
                event_type=TenancyEventType.INVITATION_ACCEPTED,
                user_id=user_id,
                actor_id=user_id,
                invitation_id=invitation.id,
            )
            if insert_membership(session, user_id, invitation.tenancy):
                add_event(
                    session,
                    tenancy=invitation.tenancy,
                    event_type=TenancyEventType.MEMBER_ADDED,
                    user_id=user_id,
                    actor_id=user_id,
                    invitation_id=invitation.id,
                )
            session.commit()
            return True
```

- [ ] **Step 4: Implement the service**

Create `app/service/tenancy_invitation.py`:

```python
from uuid import UUID

from app.exception.bad_request import BadRequestException
from app.exception.conflict import ConflictException
from app.exception.forbidden import ForbiddenException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.model.dataset_access import AccessLevel, DatasetAction
from app.model.tenancy import (
    TenancyEventType,
    TenancyInvitationStatus,
    TenancySummary,
    is_default,
    is_legacy,
    is_production,
)
from app.model.tenancy_access import (
    DatasetRef,
    DatasetTenancyInvitationView,
    ShareLookupView,
    TenancyInvitationView,
    UserBrief,
    UserRef,
)
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_invitation import TenancyInvitationRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.user import UserRepository
from app.service.dataset import DatasetService
from app.service.share_identity import normalise_email, normalise_orcid
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_notifier import TenancyNotifier

EDITORS = (AccessLevel.OWNER, AccessLevel.WRITE)
PENDING = TenancyInvitationStatus.PENDING


class TenancyInvitationService:
    def __init__(
        self,
        dataset_service: DatasetService,
        invitations: TenancyInvitationRepository,
        memberships: TenancyMembershipRepository,
        membership_service: TenancyMembershipService,
        tenancies: TenancyRepository,
        users: UserRepository,
        notifier: TenancyNotifier,
    ) -> None:
        self._datasets = dataset_service
        self._invitations = invitations
        self._memberships = memberships
        self._membership_service = membership_service
        self._tenancies = tenancies
        self._users = users
        self._notifier = notifier

    def lookup(self, dataset_id: UUID, user_id: UUID, value: str) -> ShareLookupView:
        dataset, level = self._authorized(dataset_id, user_id)
        target = self._resolve(value)
        tenancy = dataset.tenancy
        member = bool(tenancy) and self._memberships.is_member(target.id, tenancy)
        pending = bool(tenancy) and self._invitations.has_pending(tenancy, target.id)
        return ShareLookupView(
            user=UserBrief(id=target.id, name=target.name, email=target.email),
            tenancy_member=member,
            invitation_pending=pending,
            can_invite=not member
            and not pending
            and self.may_invite(dataset, level, user_id),
        )

    def may_invite(self, dataset, level: AccessLevel, user_id: UUID) -> bool:
        tenancy = dataset.tenancy
        if (
            level not in EDITORS
            or not tenancy
            or is_default(tenancy)
            or is_legacy(tenancy)
            or not is_production(tenancy)
        ):
            return False
        row = self._tenancies.fetch_any(tenancy)
        return (
            row is not None
            and row.is_enabled
            and self._memberships.is_member(user_id, tenancy)
        )

    def invite(
        self, dataset_id: UUID, user_id: UUID, invitee_id: UUID
    ) -> DatasetTenancyInvitationView:
        dataset, level = self._authorized(dataset_id, user_id)
        tenancy = dataset.tenancy
        if (
            level not in EDITORS
            or not tenancy
            or not self._memberships.is_member(user_id, tenancy)
        ):
            raise ForbiddenException(f"forbidden: invite to {tenancy} by {user_id}")
        self._membership_service.require_open_for_members(tenancy)
        invitee = self._users.fetch_by_id(id=invitee_id, is_enabled=True)
        if invitee is None:
            raise NotFoundException("no_account")
        if self._memberships.is_member(invitee.id, tenancy):
            raise ConflictException("already_member")
        if self._invitations.has_pending(tenancy, invitee.id):
            raise ConflictException("invitation_pending")
        invitation = self._invitations.create(tenancy, invitee.id, user_id, dataset.id)
        inviter = self._users.fetch_any_by_id(user_id)
        inviter_name = inviter.name if inviter else "A DataMap user"
        summary = self._membership_service.summary(tenancy)
        self._notifier.invitation(invitee, inviter_name, summary, dataset.name, invitation.id)
        self._notifier.invitation_notice(
            invitee, inviter_name, summary, dataset.name, invitation.id
        )
        return self._dataset_view(invitation, user_id)

    def withdraw(self, dataset_id: UUID, user_id: UUID, invitation_id: UUID) -> None:
        dataset, _ = self._authorized(dataset_id, user_id)
        invitation = self._invitations.fetch(invitation_id)
        if (
            invitation is None
            or invitation.dataset_id != dataset.id
            or TenancyInvitationStatus(invitation.status) != PENDING
        ):
            raise NotFoundException("invitation_not_found")
        if invitation.invited_by != user_id:
            raise ForbiddenException(f"forbidden: withdraw {invitation_id} by {user_id}")
        self._close(invitation.id, TenancyInvitationStatus.WITHDRAWN, user_id)

    def withdraw_as_admin(self, invitation_id: UUID, admin_id: UUID) -> None:
        self._close(invitation_id, TenancyInvitationStatus.WITHDRAWN, admin_id)

    def share_additions(
        self, dataset, level: AccessLevel, user_id: UUID
    ) -> tuple[list[DatasetTenancyInvitationView], bool]:
        views = [
            self._dataset_view(invitation, user_id)
            for invitation in self._invitations.pending_for_dataset(dataset.id)
        ]
        return views, self.may_invite(dataset, level, user_id)

    def pending_for_user(self, user_id: UUID) -> list[TenancyInvitationView]:
        invitations = self._invitations.pending_for_user(user_id)
        names = self._invitations.dataset_names([i.dataset_id for i in invitations])
        return [
            TenancyInvitationView(
                id=invitation.id,
                tenancy=self._membership_service.summary(invitation.tenancy),
                invited_by=self._ref(invitation.invited_by),
                dataset=DatasetRef(
                    id=invitation.dataset_id, name=names[invitation.dataset_id]
                )
                if invitation.dataset_id in names
                else None,
                datasets=self._tenancies.count_datasets(invitation.tenancy),
                created_at=invitation.created_at,
            )
            for invitation in invitations
        ]

    def accept(self, user_id: UUID, invitation_id: UUID) -> TenancySummary:
        invitation = self._theirs(user_id, invitation_id)
        row = self._tenancies.fetch_any(invitation.tenancy)
        if row is None or not row.is_enabled:
            raise ConflictException("tenancy_disabled")
        if not self._invitations.accept(invitation.id, user_id):
            raise NotFoundException("invitation_not_found")
        return self._membership_service.summary(invitation.tenancy)

    def decline(self, user_id: UUID, invitation_id: UUID) -> None:
        invitation = self._theirs(user_id, invitation_id)
        self._close(invitation.id, TenancyInvitationStatus.DECLINED, user_id)

    def _theirs(self, user_id: UUID, invitation_id: UUID):
        invitation = self._invitations.fetch(invitation_id)
        if (
            invitation is None
            or invitation.user_id != user_id
            or TenancyInvitationStatus(invitation.status) != PENDING
        ):
            raise NotFoundException("invitation_not_found")
        return invitation

    def _close(
        self, invitation_id: UUID, status: TenancyInvitationStatus, actor_id: UUID
    ) -> None:
        event_type = {
            TenancyInvitationStatus.WITHDRAWN: TenancyEventType.INVITATION_WITHDRAWN,
            TenancyInvitationStatus.DECLINED: TenancyEventType.INVITATION_DECLINED,
        }[status]
        if not self._invitations.close(invitation_id, status, actor_id, event_type):
            raise NotFoundException("invitation_not_found")

    def _authorized(self, dataset_id: UUID, user_id: UUID):
        dataset, _, level = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=None,
            action=DatasetAction.WRITE,
        )
        return dataset, level

    def _resolve(self, value: str):
        text = (value or "").strip()
        try:
            if "@" in text:
                user = self._users.fetch_by_email_insensitive(normalise_email(text))
            else:
                user = self._users.fetch_by_provider(
                    provider_name="orcid", reference=normalise_orcid(text)
                )
        except BadRequestException:
            raise IllegalStateException("invalid_request")
        if user is None:
            raise NotFoundException("no_account")
        return user

    def _dataset_view(self, invitation, user_id: UUID) -> DatasetTenancyInvitationView:
        return DatasetTenancyInvitationView(
            id=invitation.id,
            user=self._brief(invitation.user_id),
            invited_by=self._brief(invitation.invited_by)
            if invitation.invited_by
            else None,
            created_at=invitation.created_at,
            can_withdraw=invitation.invited_by == user_id,
        )

    def _brief(self, user_id: UUID) -> UserBrief:
        user = self._users.fetch_any_by_id(user_id)
        if user is None:
            return UserBrief(id=user_id, name="Deleted account", email=None)
        return UserBrief(id=user.id, name=user.name, email=user.email)

    def _ref(self, user_id: UUID | None) -> UserRef | None:
        if user_id is None:
            return None
        user = self._users.fetch_any_by_id(user_id)
        return UserRef(id=user.id, name=user.name) if user else None
```

- [ ] **Step 5: Share service and share state**

In `app/model/sharing.py`, replace

```python
@dataclass
class TenancyAccess:
    name: str
    path: str
    members: int
    members_can_edit: bool = True
```

with

```python
@dataclass
class TenancyAccess:
    name: str
    path: str
    members: int
    members_can_edit: bool = False
    is_default: bool = False
    is_legacy: bool = False
    datasets: int = 0
```

and replace

```python
    anonymous_links: list[AnonymousLinkView] = field(default_factory=list)
    tenancy: TenancyAccess | None = None
```

with

```python
    anonymous_links: list[AnonymousLinkView] = field(default_factory=list)
    tenancy: TenancyAccess | None = None
    tenancy_invitations: list = field(default_factory=list)
    can_invite_to_tenancy: bool = False
```

In `app/service/share.py`, replace

```python
from app.service.email_format import long_date, tenancy_display_name
```

with

```python
from app.service.email_format import long_date
```

replace

```python
from app.service.user import UserService

PLACEHOLDER_EMAIL_DOMAIN = "@fake.mail.com"
```

with

```python
from app.service.user import UserService
from app.model.tenancy import is_default
from app.repository.tenancy import TenancyRepository
from app.service.tenancy_invitation import TenancyInvitationService
from app.service.tenancy_membership import TenancyMembershipService

PLACEHOLDER_EMAIL_DOMAIN = "@fake.mail.com"
```

replace

```python
        email_service: EmailService,
        public_base_url: str,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
```

with

```python
        email_service: EmailService,
        public_base_url: str,
        tenancy_repository: TenancyRepository,
        membership_service: TenancyMembershipService,
        tenancy_invitations: TenancyInvitationService,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
```

replace

```python
        self._clock = clock
        self._logger = logging.getLogger("service:ShareService")
```

with

```python
        self._clock = clock
        self._tenancies = tenancy_repository
        self._membership_service = membership_service
        self._tenancy_invitations = tenancy_invitations
        self._logger = logging.getLogger("service:ShareService")
```

replace

```python
        if len((term or "").strip()) < 2 or not dataset.tenancy:
            return []
```

with

```python
        if (
            len((term or "").strip()) < 2
            or not dataset.tenancy
            or is_default(dataset.tenancy)
        ):
            return []
```

replace

```python
    def state(self, dataset_id: UUID, user_id: UUID) -> ShareState:
        dataset = self._authorized(dataset_id, user_id)
```

with

```python
    def state(self, dataset_id: UUID, user_id: UUID) -> ShareState:
        dataset, _, level = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=None,
            action=DatasetAction.WRITE,
        )
```

replace

```python
        tenancy = None
        if dataset.tenancy and not embargoed:
            tenancy = TenancyAccess(
                name=tenancy_display_name(dataset.tenancy),
                path=dataset.tenancy,
                members=self._users.count_in_tenancy(dataset.tenancy),
                members_can_edit=allows_member_edits(dataset),
            )
        return ShareState(
```

with

```python
        tenancy = None
        if dataset.tenancy and not embargoed:
            summary = self._membership_service.summary(dataset.tenancy)
            tenancy = TenancyAccess(
                name=summary.display_name,
                path=dataset.tenancy,
                members=self._users.count_in_tenancy(dataset.tenancy),
                members_can_edit=allows_member_edits(dataset),
                is_default=summary.is_default,
                is_legacy=summary.is_legacy,
                datasets=self._tenancies.count_datasets(dataset.tenancy),
            )
        tenancy_invitations, can_invite = self._tenancy_invitations.share_additions(
            dataset, level, user_id
        )
        return ShareState(
```

and replace

```python
            tenancy=tenancy,
        )

    def grant(
```

with

```python
            tenancy=tenancy,
            tenancy_invitations=tenancy_invitations,
            can_invite_to_tenancy=can_invite,
        )

    def grant(
```

In `app/controller/v1/dataset/share_resource.py`, replace

```python
from pydantic import BaseModel, Field, StringConstraints

```

with

```python
from pydantic import BaseModel, Field, StringConstraints

from app.controller.v1.tenancy.access_resource import DatasetTenancyInvitationResponse
```

replace

```python
class TenancyAccessResponse(BaseModel):
    name: str
    path: str
    members: int
    members_can_edit: bool = True
```

with

```python
class TenancyAccessResponse(BaseModel):
    name: str
    path: str
    members: int
    members_can_edit: bool = False
    is_default: bool = False
    is_legacy: bool = False
    datasets: int = 0
```

replace

```python
    anonymous_links: list[AnonymousLinkResponse]
    tenancy: TenancyAccessResponse | None = None
```

with

```python
    anonymous_links: list[AnonymousLinkResponse]
    tenancy: TenancyAccessResponse | None = None
    tenancy_invitations: list[DatasetTenancyInvitationResponse] = []
    can_invite_to_tenancy: bool = False
```

and replace

```python
            members=state.tenancy.members,
            members_can_edit=state.tenancy.members_can_edit,
        )
        if state.tenancy
        else None,
    )
```

with

```python
            members=state.tenancy.members,
            members_can_edit=state.tenancy.members_can_edit,
            is_default=state.tenancy.is_default,
            is_legacy=state.tenancy.is_legacy,
            datasets=state.tenancy.datasets,
        )
        if state.tenancy
        else None,
        tenancy_invitations=[
            DatasetTenancyInvitationResponse.model_validate(view)
            for view in state.tenancy_invitations
        ],
        can_invite_to_tenancy=state.can_invite_to_tenancy,
    )
```

- [ ] **Step 6: Routes and wiring**

Create `app/controller/v1/dataset/tenancy_invitation.py`:

```python
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.tenancy.access_resource import (
    DatasetTenancyInvitationResponse,
    ShareLookupResponse,
    UserIdBody,
)
from app.service.tenancy_invitation import TenancyInvitationService

router = APIRouter(
    prefix="/datasets",
    tags=["tenancy-invitations"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


@router.get("/{dataset_id}/share/lookup", response_model=ShareLookupResponse)
@inject
def share_lookup(
    dataset_id: UUID,
    value: str,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> ShareLookupResponse:
    return ShareLookupResponse.model_validate(service.lookup(dataset_id, user_id, value))


@router.post(
    "/{dataset_id}/tenancy-invitations",
    status_code=201,
    response_model=DatasetTenancyInvitationResponse,
)
@inject
def invite_to_tenancy(
    dataset_id: UUID,
    body: UserIdBody,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> DatasetTenancyInvitationResponse:
    return DatasetTenancyInvitationResponse.model_validate(
        service.invite(dataset_id, user_id, body.user_id)
    )


@router.delete("/{dataset_id}/tenancy-invitations/{invitation_id}", status_code=204)
@inject
def withdraw_tenancy_invitation(
    dataset_id: UUID,
    invitation_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> Response:
    service.withdraw(dataset_id, user_id, invitation_id)
    return Response(status_code=204)
```

In `app/controller/v1/user/tenancy_access.py`, replace

```python
from app.controller.v1.tenancy.access_resource import (
    TenancyRequestBody,
    TenancyRequestResponse,
    TenancySummaryResponse,
)
from app.service.tenancy_membership import TenancyMembershipService
```

with

```python
from app.controller.v1.tenancy.access_resource import (
    AcceptedInvitationResponse,
    TenancyInvitationResponse,
    TenancyRequestBody,
    TenancyRequestResponse,
    TenancySummaryResponse,
)
from app.service.tenancy_invitation import TenancyInvitationService
from app.service.tenancy_membership import TenancyMembershipService
```

and replace

```python
    service.withdraw(id, request_id)
    return Response(status_code=204)
```

with

```python
    service.withdraw(id, request_id)
    return Response(status_code=204)


@router.get("/{id}/tenancy-invitations", response_model=list[TenancyInvitationResponse])
@inject
def my_invitations(
    id: UUID,
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> list[TenancyInvitationResponse]:
    return [
        TenancyInvitationResponse.model_validate(v) for v in service.pending_for_user(id)
    ]


@router.post(
    "/{id}/tenancy-invitations/{invitation_id}/accept",
    response_model=AcceptedInvitationResponse,
)
@inject
def accept_invitation(
    id: UUID,
    invitation_id: UUID,
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> AcceptedInvitationResponse:
    return AcceptedInvitationResponse(
        tenancy=TenancySummaryResponse.model_validate(service.accept(id, invitation_id))
    )


@router.post("/{id}/tenancy-invitations/{invitation_id}/decline", status_code=204)
@inject
def decline_invitation(
    id: UUID,
    invitation_id: UUID,
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> Response:
    service.decline(id, invitation_id)
    return Response(status_code=204)
```

In `app/controller/v1/admin/tenancy.py`, replace

```python
from fastapi import APIRouter, Depends
```

with

```python
from fastapi import APIRouter, Depends, Response
```

replace

```python
from app.service.tenancy_request import TenancyRequestService
```

with

```python
from app.service.tenancy_invitation import TenancyInvitationService
from app.service.tenancy_request import TenancyRequestService
```

and replace

```python
        service.decline(request_id, user_id, body.message if body else None)
    )
```

with

```python
        service.decline(request_id, user_id, body.message if body else None)
    )


@router.delete("/tenancy-invitations/{invitation_id}", status_code=204)
@inject
def withdraw_invitation(
    invitation_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyInvitationService = Depends(
        Provide[Container.tenancy_invitation_service]
    ),
) -> Response:
    service.withdraw_as_admin(invitation_id, user_id)
    return Response(status_code=204)
```

In `app/container.py`, replace

```python
            "app.controller.v1.dataset.share",
```

with

```python
            "app.controller.v1.dataset.share",
            "app.controller.v1.dataset.tenancy_invitation",
```

replace

```python
from app.repository.tenancy_request import TenancyRequestRepository
```

with

```python
from app.repository.tenancy_request import TenancyRequestRepository
from app.repository.tenancy_invitation import TenancyInvitationRepository
from app.service.tenancy_invitation import TenancyInvitationService
```

replace

```python
    share_service = providers.Factory(
        ShareService,
```

with

```python
    tenancy_invitation_repository = providers.Factory(
        TenancyInvitationRepository,
        session_factory=db.provided.session,
    )

    tenancy_invitation_service = providers.Factory(
        TenancyInvitationService,
        dataset_service=dataset_service,
        invitations=tenancy_invitation_repository,
        memberships=tenancy_membership_repository,
        membership_service=tenancy_membership_service,
        tenancies=tenancy_repository,
        users=user_repository,
        notifier=tenancy_notifier,
    )

    share_service = providers.Factory(
        ShareService,
```

and replace

```python
        audit=dataset_access_audit,
        email_service=email_service,
        public_base_url=config.PUBLIC_BASE_URL,
    )

    anonymous_link_service = providers.Factory(
```

with

```python
        audit=dataset_access_audit,
        email_service=email_service,
        public_base_url=config.PUBLIC_BASE_URL,
        tenancy_repository=tenancy_repository,
        membership_service=tenancy_membership_service,
        tenancy_invitations=tenancy_invitation_service,
    )

    anonymous_link_service = providers.Factory(
```

In `app/setup.py`, replace

```python
from app.controller.v1.dataset.share import router as share_router
```

with

```python
from app.controller.v1.dataset.share import router as share_router
from app.controller.v1.dataset.tenancy_invitation import (
    router as tenancy_invitation_router,
)
```

and replace

```python
    fastAPIApp.include_router(share_router, prefix="/v1")
```

with

```python
    fastAPIApp.include_router(share_router, prefix="/v1")
    fastAPIApp.include_router(tenancy_invitation_router, prefix="/v1")
```

- [ ] **Step 7: Run them and see them pass**

```bash
$PY -m pytest app/service/tenancy_invitation_test.py app/service/share_test.py app/service/share_preview_test.py app/service/share_accept_test.py app/controller/v1/dataset app/controller/v1/user app/controller/v1/admin app/controller/routes_security_test.py -q -p no:cacheprovider
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
pwd && command git branch --show-current
command git add app/repository/tenancy_invitation.py app/service/tenancy_invitation.py app/service/tenancy_invitation_test.py app/service/share.py app/service/share_test.py app/model/sharing.py app/controller/v1/dataset/share_resource.py app/controller/v1/dataset/tenancy_invitation.py app/controller/v1/dataset/tenancy_invitation_test.py app/controller/v1/user/tenancy_access.py app/controller/v1/user/tenancy_access_test.py app/controller/v1/admin/tenancy.py app/controller/v1/admin/tenancy_test.py app/container.py app/setup.py
command git commit -m "feat: owners and editors invite colleagues into their tenancy; share lookup and state (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 13: Admin tenancies — list, create, members, removal impact, add, remove, user search

**Files:**
- Create: `app/service/tenancy_admin.py`, `app/service/tenancy_admin_test.py`
- Modify: `app/controller/v1/admin/tenancy.py`, `app/controller/v1/admin/tenancy_test.py`
- Modify: `app/container.py`

**Interfaces:**
- Consumes: `TenancyRepository` (Task 8), `TenancyMembershipRepository` (Task 8), `TenancyMembershipService` (Task 8), `TenancyInvitationRepository` (Task 12), `UserRepository.search_admin`, `fetch_any_by_id`, `fetch_by_id`.
- Produces (`TenancyAdminService(tenancies, memberships, membership_service, invitations, users, clock=utcnow)`):
  - `list() -> list[AdminTenancyView]` — every tenancy, disabled included, shared order.
  - `create(admin_id, display_name, namespace) -> AdminTenancyView` — `check_new_tenancy`, then `create_with_event`.
  - `members(path, limit, offset) -> TenancyMembersView` — `404 tenancy_not_found`; `1 <= limit <= 100`, `offset >= 0` else `400 invalid_request`; `since` = latest `member_added` event, else the account's `created_at`; `invited_by` from the latest accepted invitation; `invitations` pending, always `[]` for public and legacy.
  - `removal_impact(path, user_id) -> RemovalImpactView` — `404 tenancy_not_found`, `404 member_not_found`.
  - `add(path, user_id, admin_id) -> TenancyMemberView` — `require_open_for_members`, `404 no_account` (unknown or disabled), `409 already_member`; emails `tenancy_access_granted`.
  - `remove(path, user_id, admin_id) -> None` — `404 tenancy_not_found`, `409 public_tenancy_locked`, `409 legacy_tenancy_read_only`, `404 member_not_found`; no email.
  - `search_users(q) -> list[UserBrief]` — `q` trimmed, at least 2 characters else `400 invalid_request`; at most 10 enabled accounts by name, email or ORCID iD.
- Produces routes (admin): `GET /v1/admin/tenancies`, `POST /v1/admin/tenancies` (201), `GET /v1/admin/tenancies/{path:path}/members`, `GET /v1/admin/tenancies/{path:path}/members/{user_id}`, `POST /v1/admin/tenancies/{path:path}/members` (201 `TenancyMember`), `DELETE /v1/admin/tenancies/{path:path}/members/{user_id}` (204), `GET /v1/admin/users?q=`.

- [ ] **Step 1: Write the failing tests**

Create `app/service/tenancy_admin_test.py`:

```python
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.model.tenancy import DEFAULT_TENANCY, TenancyInvitationStatus
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_invitation import TenancyInvitationRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.user import UserRepository
from app.service.tenancy_admin import TenancyAdminService
from app.service.tenancy_membership import TenancyMembershipService

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
ATTO = "datamap/production/atto"
LEGACY = "datamap/staging/data-amazon"


def tenancy_row(name, display_name=None, is_enabled=True):
    return SimpleNamespace(name=name, display_name=display_name, is_enabled=is_enabled)


def user_row(name="Ana Lima", email="ana@usp.br"):
    return SimpleNamespace(
        id=uuid4(), name=name, email=email, created_at=NOW - timedelta(days=90)
    )


class AdminServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.tenancies = Mock(spec=TenancyRepository)
        self.memberships = Mock(spec=TenancyMembershipRepository)
        self.membership_service = Mock(spec=TenancyMembershipService)
        self.invitations = Mock(spec=TenancyInvitationRepository)
        self.users = Mock(spec=UserRepository)
        self.rows = {
            DEFAULT_TENANCY: tenancy_row(DEFAULT_TENANCY, "Public"),
            ATTO: tenancy_row(ATTO, "ATTO"),
            "datamap/production/beta": tenancy_row("datamap/production/beta", None, False),
            LEGACY: tenancy_row(LEGACY),
        }
        self.tenancies.fetch_any.side_effect = self.rows.get
        self.tenancies.list_all.return_value = [
            self.rows[LEGACY],
            self.rows["datamap/production/beta"],
            self.rows[ATTO],
            self.rows[DEFAULT_TENANCY],
        ]
        self.admin = user_row(name="Luciana Rizzo")
        self.member = user_row()
        self.people = {self.admin.id: self.admin, self.member.id: self.member}
        self.users.fetch_any_by_id.side_effect = self.people.get
        self.users.fetch_by_id.side_effect = lambda id, is_enabled=True: self.people.get(id)
        self.service = TenancyAdminService(
            tenancies=self.tenancies,
            memberships=self.memberships,
            membership_service=self.membership_service,
            invitations=self.invitations,
            users=self.users,
            clock=lambda: NOW,
        )


class TestList(AdminServiceTestCase):
    def test_every_tenancy_with_counts_in_the_shared_order(self):
        self.tenancies.member_counts.return_value = {DEFAULT_TENANCY: 120, ATTO: 4}
        self.tenancies.dataset_counts.return_value = {ATTO: 9}

        views = self.service.list()

        self.assertEqual(
            [v.path for v in views],
            [DEFAULT_TENANCY, ATTO, "datamap/production/beta", LEGACY],
        )
        public, atto, beta, legacy = views
        self.assertEqual((public.members, public.datasets, public.is_default), (120, 0, True))
        self.assertEqual((atto.members, atto.datasets, atto.display_name), (4, 9, "ATTO"))
        self.assertEqual((beta.display_name, beta.is_enabled), ("Beta", False))
        self.assertTrue(legacy.is_legacy)


class TestCreate(AdminServiceTestCase):
    def test_a_new_tenancy_is_validated_then_created_with_its_event(self):
        self.membership_service.check_new_tenancy.return_value = (
            "datamap/production/cerrado-flux",
            "Cerrado Flux",
        )

        view = self.service.create(self.admin.id, "Cerrado Flux", "cerrado-flux")

        self.tenancies.create_with_event.assert_called_once_with(
            "datamap/production/cerrado-flux", "Cerrado Flux", self.admin.id
        )
        self.assertEqual(view.path, "datamap/production/cerrado-flux")
        self.assertEqual((view.members, view.datasets, view.is_enabled), (0, 0, True))

    def test_the_validation_codes_pass_through(self):
        self.membership_service.check_new_tenancy.side_effect = ConflictException(
            "display_name_taken"
        )

        with self.assertRaises(ConflictException):
            self.service.create(self.admin.id, "ATTO", "atto-2")
        self.tenancies.create_with_event.assert_not_called()


class TestMembers(AdminServiceTestCase):
    def test_members_with_since_and_who_invited_them(self):
        other = user_row(name="Bruno")
        self.people[other.id] = other
        self.memberships.list_members.return_value = ([self.member, other], 2)
        added = NOW - timedelta(days=3)
        self.memberships.added_at.return_value = {self.member.id: added}
        self.memberships.inviters.return_value = {other.id: self.admin.id}
        self.invitations.pending_for_tenancy.return_value = []

        view = self.service.members(ATTO, 50, 0)

        first, second = view.members.items
        self.assertEqual(first.since, added)
        self.assertIsNone(first.invited_by)
        self.assertEqual(second.since, other.created_at)
        self.assertEqual(second.invited_by.name, "Luciana Rizzo")
        self.assertEqual(view.members.total_count, 2)
        self.memberships.list_members.assert_called_once_with(ATTO, 50, 0)

    def test_pending_invitations_come_with_them_except_in_public_and_legacy(self):
        self.memberships.list_members.return_value = ([], 0)
        self.memberships.added_at.return_value = {}
        self.memberships.inviters.return_value = {}
        invitation = SimpleNamespace(
            id=uuid4(),
            user_id=self.member.id,
            invited_by=self.admin.id,
            dataset_id=uuid4(),
            status=TenancyInvitationStatus.PENDING,
            created_at=NOW,
        )
        self.invitations.pending_for_tenancy.return_value = [invitation]
        self.invitations.dataset_names.return_value = {invitation.dataset_id: "Ozone"}

        atto = self.service.members(ATTO, 50, 0)
        public = self.service.members(DEFAULT_TENANCY, 50, 0)
        legacy = self.service.members(LEGACY, 50, 0)

        (pending,) = atto.invitations
        self.assertEqual(pending.user.email, "ana@usp.br")
        self.assertEqual(pending.invited_by.name, "Luciana Rizzo")
        self.assertEqual(pending.dataset.name, "Ozone")
        self.assertEqual(public.invitations, [])
        self.assertEqual(legacy.invitations, [])

    def test_an_unknown_tenancy_or_bad_paging(self):
        with self.assertRaises(NotFoundException) as raised:
            self.service.members("datamap/production/none", 50, 0)
        self.assertEqual(str(raised.exception), "tenancy_not_found")
        for limit, offset in ((0, 0), (101, 0), (50, -1)):
            with self.subTest(limit=limit, offset=offset):
                with self.assertRaises(IllegalStateException):
                    self.service.members(ATTO, limit, offset)


class TestRemovalImpact(AdminServiceTestCase):
    def test_what_removing_a_member_changes(self):
        self.memberships.is_member.return_value = True
        self.memberships.added_at.return_value = {}
        self.memberships.removal_counts.return_value = (9, 2, 1)

        impact = self.service.removal_impact(ATTO, self.member.id)

        self.assertEqual(impact.member_since, self.member.created_at)
        self.assertEqual(
            (impact.datasets_in_tenancy, impact.shared_with_user, impact.owned_by_user),
            (9, 2, 1),
        )

    def test_someone_who_is_not_a_member(self):
        self.memberships.is_member.return_value = False

        with self.assertRaises(NotFoundException) as raised:
            self.service.removal_impact(ATTO, self.member.id)

        self.assertEqual(str(raised.exception), "member_not_found")


class TestAddAndRemove(AdminServiceTestCase):
    def test_adding_a_member_records_and_announces_it(self):
        self.memberships.is_member.return_value = False
        event_id = uuid4()
        self.memberships.add.return_value = event_id

        view = self.service.add(ATTO, self.member.id, self.admin.id)

        self.membership_service.require_open_for_members.assert_called_once_with(ATTO)
        self.memberships.add.assert_called_once_with(ATTO, self.member.id, self.admin.id)
        self.membership_service.announce_access.assert_called_once_with(
            self.member.id, self.admin.id, ATTO, event_id
        )
        self.assertEqual((view.id, view.since, view.invited_by), (self.member.id, NOW, None))

    def test_adding_refusals(self):
        self.membership_service.require_open_for_members.side_effect = ConflictException(
            "public_tenancy_locked"
        )
        with self.assertRaises(ConflictException):
            self.service.add(DEFAULT_TENANCY, self.member.id, self.admin.id)

        self.membership_service.require_open_for_members.side_effect = None
        with self.assertRaises(NotFoundException) as raised:
            self.service.add(ATTO, uuid4(), self.admin.id)
        self.assertEqual(str(raised.exception), "no_account")

        self.memberships.is_member.return_value = True
        with self.assertRaises(ConflictException) as raised:
            self.service.add(ATTO, self.member.id, self.admin.id)
        self.assertEqual(str(raised.exception), "already_member")
        self.memberships.add.assert_not_called()

    def test_removing(self):
        self.memberships.remove.return_value = True

        self.service.remove(ATTO, self.member.id, self.admin.id)

        self.memberships.remove.assert_called_once_with(ATTO, self.member.id, self.admin.id)

    def test_removal_refusals_in_order(self):
        cases = (
            ("datamap/production/none", NotFoundException, "tenancy_not_found"),
            (DEFAULT_TENANCY, ConflictException, "public_tenancy_locked"),
            (LEGACY, ConflictException, "legacy_tenancy_read_only"),
        )
        for path, exception, code in cases:
            with self.subTest(path=path):
                with self.assertRaises(exception) as raised:
                    self.service.remove(path, self.member.id, self.admin.id)
                self.assertEqual(str(raised.exception), code)
        self.memberships.remove.assert_not_called()

        self.memberships.remove.return_value = False
        with self.assertRaises(NotFoundException) as raised:
            self.service.remove(ATTO, self.member.id, self.admin.id)
        self.assertEqual(str(raised.exception), "member_not_found")


class TestUserSearch(AdminServiceTestCase):
    def test_at_least_two_characters(self):
        for q in (None, "", " a "):
            with self.subTest(q=q):
                with self.assertRaises(IllegalStateException) as raised:
                    self.service.search_users(q)
                self.assertEqual(str(raised.exception), "invalid_request")

    def test_hits_are_id_name_and_email(self):
        self.users.search_admin.return_value = [self.member]

        (hit,) = self.service.search_users("  an ")

        self.users.search_admin.assert_called_once_with("an", 10)
        self.assertEqual((hit.id, hit.name, hit.email), (self.member.id, "Ana Lima", "ana@usp.br"))
```

Append to `app/controller/v1/admin/tenancy_test.py`:

```python


class TestAdminTenancyRoutes(AdminRoutesTestCase):
    def setUp(self):
        super().setUp()
        self.admin_service = Mock(spec=TenancyAdminService)
        self.container.tenancy_admin_service.override(providers.Object(self.admin_service))

    def tearDown(self):
        self.container.tenancy_admin_service.reset_override()
        super().tearDown()

    def test_list_and_create(self):
        view = AdminTenancyView(
            path="datamap/production/atto",
            display_name="ATTO",
            members=4,
            datasets=9,
            is_default=False,
            is_legacy=False,
            is_enabled=True,
        )
        self.admin_service.list.return_value = [view]
        self.admin_service.create.return_value = view

        listed = self.client.get("/v1/admin/tenancies", headers=self.headers)
        created = self.client.post(
            "/v1/admin/tenancies",
            json={"display_name": "ATTO", "namespace": "atto"},
            headers=self.headers,
        )

        self.assertEqual(listed.json()[0]["members"], 4)
        self.assertEqual(created.status_code, 201)
        self.admin_service.create.assert_called_once_with(ADMIN, "ATTO", "atto")

    def test_the_tenancy_path_travels_unencoded(self):
        self.admin_service.members.return_value = TenancyMembersView(
            members=Page(items=[], total_count=0, limit=50, offset=0), invitations=[]
        )
        user_id = uuid4()
        self.admin_service.removal_impact.return_value = RemovalImpactView(
            member_since=AT, datasets_in_tenancy=1, shared_with_user=0, owned_by_user=0
        )

        members = self.client.get(
            "/v1/admin/tenancies/datamap/production/atto/members?limit=50&offset=0",
            headers=self.headers,
        )
        impact = self.client.get(
            f"/v1/admin/tenancies/datamap/production/atto/members/{user_id}",
            headers=self.headers,
        )
        removed = self.client.delete(
            f"/v1/admin/tenancies/datamap/production/atto/members/{user_id}",
            headers=self.headers,
        )

        self.assertEqual(members.status_code, 200)
        self.admin_service.members.assert_called_once_with("datamap/production/atto", 50, 0)
        self.assertEqual(impact.json()["datasets_in_tenancy"], 1)
        self.admin_service.removal_impact.assert_called_once_with(
            "datamap/production/atto", user_id
        )
        self.assertEqual(removed.status_code, 204)
        self.admin_service.remove.assert_called_once_with(
            "datamap/production/atto", user_id, ADMIN
        )

    def test_adding_a_member_answers_201_with_the_member(self):
        user_id = uuid4()
        self.admin_service.add.return_value = TenancyMemberView(
            id=user_id, name="Ana", email="a@usp.br", since=AT, invited_by=None
        )

        response = self.client.post(
            "/v1/admin/tenancies/datamap/production/atto/members",
            json={"user_id": str(user_id)},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], str(user_id))
        self.admin_service.add.assert_called_once_with(
            "datamap/production/atto", user_id, ADMIN
        )

    def test_user_search(self):
        self.admin_service.search_users.return_value = [
            UserBrief(id=uuid4(), name="Ana", email="a@usp.br")
        ]

        response = self.client.get("/v1/admin/users?q=an", headers=self.headers)

        self.assertEqual(response.json()[0]["name"], "Ana")
        self.admin_service.search_users.assert_called_once_with("an")
```

and in its imports replace

```python
from app.model.tenancy_access import (
    AdminTenancyRequestView,
    NewTenancy,
    Page,
    RequestCounts,
    Requester,
)
from app.service.tenancy_invitation import TenancyInvitationService
```

with

```python
from app.model.tenancy_access import (
    AdminTenancyRequestView,
    AdminTenancyView,
    NewTenancy,
    Page,
    RemovalImpactView,
    RequestCounts,
    Requester,
    TenancyMembersView,
    TenancyMemberView,
    UserBrief,
)
from app.service.tenancy_admin import TenancyAdminService
from app.service.tenancy_invitation import TenancyInvitationService
```

- [ ] **Step 2: Run them and see them fail**

```bash
$PY -m pytest app/service/tenancy_admin_test.py app/controller/v1/admin/tenancy_test.py -q -p no:cacheprovider
```

Expected: `ModuleNotFoundError: No module named 'app.service.tenancy_admin'`.

- [ ] **Step 3: Implement the service**

Create `app/service/tenancy_admin.py`:

```python
from datetime import datetime
from typing import Callable
from uuid import UUID

from app.exception.conflict import ConflictException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.model.dataset_access import utcnow
from app.model.tenancy import (
    display_name_of,
    is_default,
    is_legacy,
    tenancy_order,
)
from app.model.tenancy_access import (
    AdminTenancyInvitationView,
    AdminTenancyView,
    DatasetRef,
    Page,
    RemovalImpactView,
    TenancyMembersView,
    TenancyMemberView,
    UserBrief,
    UserRef,
)
from app.repository.tenancy import TenancyRepository
from app.repository.tenancy_invitation import TenancyInvitationRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.user import UserRepository
from app.service.tenancy_membership import TenancyMembershipService

MAX_PAGE = 100
SEARCH_LIMIT = 10
SEARCH_MIN_LENGTH = 2


class TenancyAdminService:
    def __init__(
        self,
        tenancies: TenancyRepository,
        memberships: TenancyMembershipRepository,
        membership_service: TenancyMembershipService,
        invitations: TenancyInvitationRepository,
        users: UserRepository,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._tenancies = tenancies
        self._memberships = memberships
        self._membership_service = membership_service
        self._invitations = invitations
        self._users = users
        self._clock = clock

    def list(self) -> list[AdminTenancyView]:
        members = self._tenancies.member_counts()
        datasets = self._tenancies.dataset_counts()
        views = [
            AdminTenancyView(
                path=row.name,
                display_name=display_name_of(row.name, row.display_name),
                members=members.get(row.name, 0),
                datasets=datasets.get(row.name, 0),
                is_default=is_default(row.name),
                is_legacy=is_legacy(row.name),
                is_enabled=row.is_enabled,
            )
            for row in self._tenancies.list_all()
        ]
        return sorted(views, key=lambda v: tenancy_order(v.path, v.display_name))

    def create(self, admin_id: UUID, display_name: str, namespace: str) -> AdminTenancyView:
        path, name = self._membership_service.check_new_tenancy(display_name, namespace)
        self._tenancies.create_with_event(path, name, admin_id)
        return AdminTenancyView(
            path=path,
            display_name=name,
            members=0,
            datasets=0,
            is_default=False,
            is_legacy=False,
            is_enabled=True,
        )

    def members(self, path: str, limit: int, offset: int) -> TenancyMembersView:
        self._existing(path)
        if not 1 <= limit <= MAX_PAGE or offset < 0:
            raise IllegalStateException("invalid_request")
        users, total = self._memberships.list_members(path, limit, offset)
        ids = [user.id for user in users]
        since = self._memberships.added_at(path, ids)
        inviters = self._memberships.inviters(path, ids)
        items = [
            TenancyMemberView(
                id=user.id,
                name=user.name,
                email=user.email,
                since=since.get(user.id, user.created_at),
                invited_by=self._ref(inviters.get(user.id)),
            )
            for user in users
        ]
        return TenancyMembersView(
            members=Page(items=items, total_count=total, limit=limit, offset=offset),
            invitations=[]
            if is_default(path) or is_legacy(path)
            else self._pending_invitations(path),
        )

    def removal_impact(self, path: str, user_id: UUID) -> RemovalImpactView:
        self._existing(path)
        user = self._users.fetch_any_by_id(user_id)
        if user is None or not self._memberships.is_member(user_id, path):
            raise NotFoundException("member_not_found")
        in_tenancy, shared, owned = self._memberships.removal_counts(path, user_id)
        return RemovalImpactView(
            member_since=self._memberships.added_at(path, [user_id]).get(
                user_id, user.created_at
            ),
            datasets_in_tenancy=in_tenancy,
            shared_with_user=shared,
            owned_by_user=owned,
        )

    def add(self, path: str, user_id: UUID, admin_id: UUID) -> TenancyMemberView:
        self._membership_service.require_open_for_members(path)
        user = self._users.fetch_by_id(id=user_id, is_enabled=True)
        if user is None:
            raise NotFoundException("no_account")
        if self._memberships.is_member(user_id, path):
            raise ConflictException("already_member")
        event_id = self._memberships.add(path, user_id, admin_id)
        if event_id is None:
            raise ConflictException("already_member")
        self._membership_service.announce_access(user_id, admin_id, path, event_id)
        return TenancyMemberView(
            id=user.id, name=user.name, email=user.email, since=self._clock(), invited_by=None
        )

    def remove(self, path: str, user_id: UUID, admin_id: UUID) -> None:
        self._existing(path)
        if is_default(path):
            raise ConflictException("public_tenancy_locked")
        if is_legacy(path):
            raise ConflictException("legacy_tenancy_read_only")
        if not self._memberships.remove(path, user_id, admin_id):
            raise NotFoundException("member_not_found")

    def search_users(self, q: str | None) -> list[UserBrief]:
        term = (q or "").strip()
        if len(term) < SEARCH_MIN_LENGTH:
            raise IllegalStateException("invalid_request")
        return [
            UserBrief(id=user.id, name=user.name, email=user.email)
            for user in self._users.search_admin(term, SEARCH_LIMIT)
        ]

    def _existing(self, path: str) -> None:
        if self._tenancies.fetch_any(path) is None:
            raise NotFoundException("tenancy_not_found")

    def _pending_invitations(self, path: str) -> list[AdminTenancyInvitationView]:
        invitations = self._invitations.pending_for_tenancy(path)
        names = self._invitations.dataset_names([i.dataset_id for i in invitations])
        return [
            AdminTenancyInvitationView(
                id=invitation.id,
                user=self._brief(invitation.user_id),
                invited_by=self._ref(invitation.invited_by),
                dataset=DatasetRef(id=invitation.dataset_id, name=names[invitation.dataset_id])
                if invitation.dataset_id in names
                else None,
                created_at=invitation.created_at,
            )
            for invitation in invitations
        ]

    def _brief(self, user_id: UUID) -> UserBrief:
        user = self._users.fetch_any_by_id(user_id)
        if user is None:
            return UserBrief(id=user_id, name="Deleted account", email=None)
        return UserBrief(id=user.id, name=user.name, email=user.email)

    def _ref(self, user_id: UUID | None) -> UserRef | None:
        if user_id is None:
            return None
        user = self._users.fetch_any_by_id(user_id)
        return UserRef(id=user.id, name=user.name) if user else None
```

- [ ] **Step 4: Implement the routes**

In `app/controller/v1/admin/tenancy.py`, replace

```python
from app.controller.v1.tenancy.access_resource import (
    AdminTenancyRequestDetailResponse,
    AdminTenancyRequestPage,
    AdminTenancyRequestResponse,
    ApproveBody,
    DeclineBody,
    RequestCountsResponse,
)
```

with

```python
from app.controller.v1.tenancy.access_resource import (
    AdminTenancyRequestDetailResponse,
    AdminTenancyRequestPage,
    AdminTenancyRequestResponse,
    AdminTenancyResponse,
    ApproveBody,
    DeclineBody,
    RemovalImpactResponse,
    RequestCountsResponse,
    TenancyCreateBody,
    TenancyMemberResponse,
    TenancyMembersResponse,
    UserBriefResponse,
    UserIdBody,
)
from app.service.tenancy_admin import TenancyAdminService
```

and append to the end of the file:

```python


@router.get("/tenancies", response_model=list[AdminTenancyResponse])
@inject
def list_tenancies(
    service: TenancyAdminService = Depends(Provide[Container.tenancy_admin_service]),
) -> list[AdminTenancyResponse]:
    return [AdminTenancyResponse.model_validate(v) for v in service.list()]


@router.post("/tenancies", status_code=201, response_model=AdminTenancyResponse)
@inject
def create_tenancy(
    body: TenancyCreateBody,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyAdminService = Depends(Provide[Container.tenancy_admin_service]),
) -> AdminTenancyResponse:
    return AdminTenancyResponse.model_validate(
        service.create(user_id, body.display_name, body.namespace)
    )


@router.get(
    "/tenancies/{path:path}/members/{member_id}", response_model=RemovalImpactResponse
)
@inject
def removal_impact(
    path: str,
    member_id: UUID,
    service: TenancyAdminService = Depends(Provide[Container.tenancy_admin_service]),
) -> RemovalImpactResponse:
    return RemovalImpactResponse.model_validate(service.removal_impact(path, member_id))


@router.delete("/tenancies/{path:path}/members/{member_id}", status_code=204)
@inject
def remove_member(
    path: str,
    member_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyAdminService = Depends(Provide[Container.tenancy_admin_service]),
) -> Response:
    service.remove(path, member_id, user_id)
    return Response(status_code=204)


@router.get("/tenancies/{path:path}/members", response_model=TenancyMembersResponse)
@inject
def list_members(
    path: str,
    limit: int = 50,
    offset: int = 0,
    service: TenancyAdminService = Depends(Provide[Container.tenancy_admin_service]),
) -> TenancyMembersResponse:
    return TenancyMembersResponse.model_validate(service.members(path, limit, offset))


@router.post(
    "/tenancies/{path:path}/members",
    status_code=201,
    response_model=TenancyMemberResponse,
)
@inject
def add_member(
    path: str,
    body: UserIdBody,
    user_id: UUID = Depends(parse_user_header),
    service: TenancyAdminService = Depends(Provide[Container.tenancy_admin_service]),
) -> TenancyMemberResponse:
    return TenancyMemberResponse.model_validate(service.add(path, body.user_id, user_id))


@router.get("/users", response_model=list[UserBriefResponse])
@inject
def search_users(
    q: str = "",
    service: TenancyAdminService = Depends(Provide[Container.tenancy_admin_service]),
) -> list[UserBriefResponse]:
    return [UserBriefResponse.model_validate(hit) for hit in service.search_users(q)]
```

The member's id is `member_id` in the function so that `user_id` stays the caller from `X-User-Id`, as everywhere else in the codebase; the URL is unchanged.

In `app/container.py`, replace

```python
from app.service.tenancy_invitation import TenancyInvitationService
```

with

```python
from app.service.tenancy_invitation import TenancyInvitationService
from app.service.tenancy_admin import TenancyAdminService
```

and replace

```python
    share_service = providers.Factory(
        ShareService,
```

with

```python
    tenancy_admin_service = providers.Factory(
        TenancyAdminService,
        tenancies=tenancy_repository,
        memberships=tenancy_membership_repository,
        membership_service=tenancy_membership_service,
        invitations=tenancy_invitation_repository,
        users=user_repository,
    )

    share_service = providers.Factory(
        ShareService,
```

- [ ] **Step 5: Run them and see them pass**

```bash
$PY -m pytest app/service/tenancy_admin_test.py app/controller -q -p no:cacheprovider
$PY -m pytest -q -p no:cacheprovider 2>&1 | tail -3
```

Expected: all pass; the full unit run has no `failed`.

- [ ] **Step 6: Commit**

```bash
pwd && command git branch --show-current
command git add app/service/tenancy_admin.py app/service/tenancy_admin_test.py app/controller/v1/admin/tenancy.py app/controller/v1/admin/tenancy_test.py app/container.py
command git commit -m "feat: admins list, create and manage the members of tenancies (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 14: Integration — every account in public, new accounts work at once, datasets closed, share candidates and lookup

**Files:**
- Create: `tests/integration/fixtures/tenancy.py`
- Create: `tests/integration/test_public_tenancy_api.py`

**Interfaces:**
- Produces (`tests/integration/fixtures/tenancy.py`): `PUBLIC`, `LEGACY`, `ADMIN_ID`; `admin() -> dict`, `as_user(user_id, tenancy=None) -> dict`, `unique(prefix) -> str`, `new_account(http_client, name="Bruna Costa", confirmed=False, providers=None) -> dict` (`id`, `email`, `name`), `set_roles(http_client, user_id, add=(), remove=())`, `join(user_id, tenancy)`, `new_tenancy(display_name=None, enabled=True) -> str`, `display_name(path) -> str`, `create_dataset(http_client, user_id, tenancy) -> dict`, `update_dataset(http_client, user_id, dataset, tenancy=None) -> Response`, `members_access(http_client, user_id, dataset, value) -> Response`, `upload(http_client, user_id, dataset) -> Response`, `events(where) -> list[dict]`, `event_types(where) -> list[str]`, `roles_of(user_id) -> list[str]`, `tenancies_of(http_client, user_id) -> list[str]`, `request_access(http_client, user_id, name="ATTO", reason=...) -> Response`.

Memberships and tenancies are arranged with SQL (`join`, `new_tenancy`): they are read from the database on every call, so no reload is needed. Roles are changed only through `PUT`/`DELETE /users/{id}/roles`, which update the in-process enforcer at once; a role inserted with SQL would wait for Casbin's 5-second reload.

- [ ] **Step 1: Write the fixtures**

Create `tests/integration/fixtures/tenancy.py`:

```python
import uuid

import requests

from tests.integration.config import config
from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.embargo import headers_for
from tests.integration.fixtures.tus_auth import create_tus_payload
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.http_client import HttpClient

PUBLIC = "datamap/production/public"
LEGACY = "datamap/staging/data-amazon"
ADMIN_ID = config.user_id
EVENT_COLUMNS = ("event_type", "tenancy", "user_id", "actor_id", "request_id", "invitation_id")


def admin() -> dict:
    return headers_for(ADMIN_ID, None)


def as_user(user_id: str, tenancy: str | None = None) -> dict:
    return headers_for(user_id, tenancy)


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def new_account(
    http_client: HttpClient,
    name: str = "Bruna Costa",
    confirmed: bool = False,
    providers: list[dict] | None = None,
) -> dict:
    email = f"{unique('tenancy')}@example.com"
    response = http_client.post(
        "/users/",
        json={"name": name, "email": email, "providers": providers or [], "roles": []},
        headers=AuthFixture.valid_headers(),
    )
    assert_status_code(response, 200)
    user_id = response.json()["id"]
    if confirmed:
        execute(f"UPDATE users SET email_verified_at = now() WHERE id = '{user_id}'")
    return {"id": user_id, "email": email, "name": name}


def set_roles(
    http_client: HttpClient, user_id: str, add: tuple = (), remove: tuple = ()
) -> None:
    if remove:
        response = http_client.delete(
            f"/users/{user_id}/roles", json=list(remove), headers=AuthFixture.valid_headers()
        )
        assert_status_code(response, 200)
    if add:
        response = http_client.put(
            f"/users/{user_id}/roles", json=list(add), headers=AuthFixture.valid_headers()
        )
        assert_status_code(response, 200)


def join(user_id: str, tenancy: str) -> None:
    execute(
        "INSERT INTO users_tenancies (user_id, tenancy) "
        f"VALUES ('{user_id}', '{tenancy}') ON CONFLICT DO NOTHING"
    )


def new_tenancy(display_name: str | None = None, enabled: bool = True) -> str:
    path = f"datamap/production/{unique('t')}"
    name = "NULL" if display_name is None else f"'{display_name}'"
    execute(
        "INSERT INTO tenancies (name, display_name, is_enabled, created_at, updated_at) "
        f"VALUES ('{path}', {name}, {str(enabled).lower()}, now(), now())"
    )
    return path


def display_name(path: str) -> str:
    return execute(f"SELECT display_name FROM tenancies WHERE name = '{path}'")


def create_dataset(http_client: HttpClient, user_id: str, tenancy: str) -> dict:
    response = http_client.post(
        "/datasets",
        json={
            "name": unique("Tenancy dataset"),
            "data": {
                "description": "tenancy",
                "authors": [{"name": "A"}],
                "institution": "Test Institution",
            },
            "tenancy": tenancy,
        },
        headers=as_user(user_id, tenancy),
    )
    assert_status_code(response, 201)
    return response.json()


def update_dataset(
    http_client: HttpClient, user_id: str, dataset: dict, tenancy: str | None = None
) -> requests.Response:
    return http_client.put(
        f"/datasets/{dataset['id']}",
        json={"name": "edited", "data": {}, "tenancy": dataset["tenancy"]},
        headers=as_user(user_id, tenancy or dataset["tenancy"]),
    )


def members_access(
    http_client: HttpClient, user_id: str, dataset: dict, value: bool
) -> requests.Response:
    return http_client.put(
        f"/datasets/{dataset['id']}/members-access",
        json={"members_can_edit": value},
        headers=as_user(user_id, dataset["tenancy"]),
    )


def upload(http_client: HttpClient, user_id: str, dataset: dict) -> requests.Response:
    payload = create_tus_payload(
        user_id=user_id,
        dataset_id=dataset["id"],
        filename="data.nc",
        file_size=10,
        file_type="application/x-netcdf",
    )
    return http_client.post("/tus/hooks", json=payload, headers=AuthFixture.valid_headers())


def events(where: str) -> list[dict]:
    output = execute(
        "SELECT event_type, coalesce(tenancy, ''), coalesce(user_id::text, ''), "
        "coalesce(actor_id::text, ''), coalesce(request_id::text, ''), "
        "coalesce(invitation_id::text, '') "
        f"FROM tenancy_events WHERE {where} ORDER BY created_at, event_type"
    )
    return [dict(zip(EVENT_COLUMNS, line.split("|"))) for line in output.splitlines() if line]


def event_types(where: str) -> list[str]:
    return sorted(event["event_type"] for event in events(where))


def roles_of(user_id: str) -> list[str]:
    return execute(
        f"SELECT v1 FROM casbin_rule WHERE ptype = 'g' AND v0 = '{user_id}' ORDER BY v1"
    ).split()


def tenancies_of(http_client: HttpClient, user_id: str) -> list[str]:
    response = http_client.get(f"/users/{user_id}/tenancies", headers=as_user(user_id))
    assert_status_code(response, 200)
    return [tenancy["path"] for tenancy in response.json()]


def request_access(
    http_client: HttpClient,
    user_id: str,
    name: str = "ATTO",
    reason: str = "I process the ATTO tower fluxes.",
) -> requests.Response:
    return http_client.post(
        f"/users/{user_id}/tenancy-requests",
        json={"tenancy_name": name, "reason": reason},
        headers=as_user(user_id),
    )
```

- [ ] **Step 2: Write the tests**

Create `tests/integration/test_public_tenancy_api.py`:

```python
import pytest

from tests.integration.fixtures.account import (
    confirm_email_verification,
    newest_code,
    outbox,
    password_account,
    request_email_verification,
    unique_email,
)
from tests.integration.fixtures.embargo import grant
from tests.integration.fixtures.sharing import random_orcid
from tests.integration.fixtures.tenancy import (
    PUBLIC,
    as_user,
    create_dataset,
    events,
    join,
    members_access,
    new_account,
    new_tenancy,
    roles_of,
    set_roles,
    tenancies_of,
    unique,
    update_dataset,
    upload,
)
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.mailpit import Mailpit


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


def _lands_in_public_with_datasets_write(http_client, user_id: str) -> None:
    assert PUBLIC in tenancies_of(http_client, user_id)
    assert roles_of(user_id) == ["datasets_write"]
    assert outbox(http_client, related_id=user_id, template="new_account_pending")["items"] == []
    (added,) = events(f"user_id = '{user_id}' AND tenancy = '{PUBLIC}'")
    assert added["event_type"] == "member_added"
    assert added["actor_id"] == ""


class TestEveryCreationPath:
    def test_post_users(self, http_client):
        account = new_account(http_client)

        _lands_in_public_with_datasets_write(http_client, account["id"])

    def test_password_sign_up(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        _lands_in_public_with_datasets_write(http_client, account["id"])

    def test_orcid_email_verification(self, http_client, mailpit):
        orcid, email = random_orcid(), unique_email()
        started = request_email_verification(http_client, orcid, email)
        assert_status_code(started, 202)
        code = newest_code(http_client, mailpit, email)
        confirmed = confirm_email_verification(
            http_client, started.json()["challenge_id"], code
        )
        assert_status_code(confirmed, 200)

        _lands_in_public_with_datasets_write(http_client, confirmed.json()["user_id"])


class TestANewAccountWorksAtOnce:
    def test_it_creates_a_dataset_in_public_uploads_and_edits(self, http_client):
        account = new_account(http_client)

        dataset = create_dataset(http_client, account["id"], PUBLIC)
        uploaded = upload(http_client, account["id"], dataset)
        edited = update_dataset(http_client, account["id"], dataset)
        detail = http_client.get(
            f"/datasets/{dataset['id']}", headers=as_user(account["id"], PUBLIC)
        )

        assert_status_code(uploaded, 200)
        assert uploaded.json().get("RejectUpload") is not True
        assert_status_code(edited, 200)
        assert detail.json()["name"] == "edited"
        assert len(detail.json()["current_version"]["files_in"]) == 1
        assert detail.json()["access"]["level"] == "owner"


class TestNewDatasetsAreClosed:
    @pytest.mark.parametrize("in_public", [True, False])
    def test_members_can_edit_is_false_when_the_request_omits_it(
        self, http_client, in_public
    ):
        owner = new_account(http_client)
        tenancy = PUBLIC if in_public else new_tenancy()
        join(owner["id"], tenancy)

        dataset = create_dataset(http_client, owner["id"], tenancy)
        detail = http_client.get(
            f"/datasets/{dataset['id']}", headers=as_user(owner["id"], tenancy)
        )

        assert detail.json()["members_can_edit"] is False
        assert execute(
            f"SELECT members_can_edit FROM datasets WHERE id = '{dataset['id']}'"
        ) == "f"


@pytest.fixture
def published(http_client):
    owner = new_account(http_client, name="Public Owner")
    dataset = create_dataset(http_client, owner["id"], PUBLIC)
    assert_status_code(upload(http_client, owner["id"], dataset), 200)
    return owner, dataset


class TestPublicIsReadOnlyForMembers:
    def test_another_member_reads_metadata_and_files_but_cannot_change_them(
        self, http_client, published
    ):
        _, dataset = published
        reader = new_account(http_client, name="Public Reader")
        headers = as_user(reader["id"], PUBLIC)

        detail = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        version = detail.json()["current_version"]
        download = http_client.get(
            f"/datasets/{dataset['id']}/versions/{version['name']}/files/{version['files_in'][0]['id']}",
            headers=headers,
        )
        update = update_dataset(http_client, reader["id"], dataset)
        delete = http_client.delete(f"/datasets/{dataset['id']}", headers=headers)

        assert_status_code(detail, 200)
        assert detail.json()["access"]["level"] == "tenancy"
        assert detail.json()["access"]["can_edit"] is False
        assert detail.json()["members_can_edit"] is False
        assert_status_code(download, 200)
        assert_status_code(update, 403)
        assert update.json() == {"detail": "forbidden"}
        assert_status_code(delete, 401)

    def test_a_member_whose_role_deletes_is_refused_by_the_access_rule(
        self, http_client, published
    ):
        _, dataset = published
        deleter = new_account(http_client, name="Public Deleter")
        set_roles(http_client, deleter["id"], add=("datasets_admin",))

        delete = http_client.delete(
            f"/datasets/{dataset['id']}", headers=as_user(deleter["id"], PUBLIC)
        )

        assert_status_code(delete, 403)

    def test_the_owner_and_a_write_collaborator_edit(self, http_client, published):
        owner, dataset = published
        collaborator = new_account(http_client, name="Public Collaborator")
        grant(http_client, dataset["id"], collaborator["id"], "write")

        assert_status_code(update_dataset(http_client, owner["id"], dataset), 200)
        assert_status_code(update_dataset(http_client, collaborator["id"], dataset), 200)

    def test_opening_a_public_dataset_to_members_is_refused(self, http_client, published):
        owner, dataset = published

        opened = members_access(http_client, owner["id"], dataset, True)
        closed = members_access(http_client, owner["id"], dataset, False)

        assert_status_code(opened, 400)
        assert opened.json() == {"detail": "public_members_cannot_edit"}
        assert_status_code(closed, 200)
        assert closed.json()["members_can_edit"] is False

    def test_a_public_dataset_whose_column_says_true_is_still_closed(
        self, http_client, published
    ):
        _, dataset = published
        execute(f"UPDATE datasets SET members_can_edit = true WHERE id = '{dataset['id']}'")
        reader = new_account(http_client, name="Public Reader")

        update = update_dataset(http_client, reader["id"], dataset)
        detail = http_client.get(
            f"/datasets/{dataset['id']}", headers=as_user(reader["id"], PUBLIC)
        )

        assert_status_code(update, 403)
        assert detail.json()["members_can_edit"] is False

    def test_moving_a_dataset_into_public_closes_it(self, http_client):
        owner = new_account(http_client)
        tenancy = new_tenancy()
        join(owner["id"], tenancy)
        dataset = create_dataset(http_client, owner["id"], tenancy)
        assert_status_code(members_access(http_client, owner["id"], dataset, True), 200)

        moved = http_client.put(
            f"/datasets/{dataset['id']}",
            json={"name": "moved", "data": {}, "tenancy": PUBLIC},
            headers=as_user(owner["id"], tenancy),
        )

        assert_status_code(moved, 200)
        assert execute(
            f"SELECT members_can_edit, tenancy FROM datasets WHERE id = '{dataset['id']}'"
        ) == f"f|{PUBLIC}"


class TestOutsidePublic:
    def test_a_member_edits_only_after_the_owner_opens_the_dataset(self, http_client):
        tenancy = new_tenancy()
        owner, member = new_account(http_client), new_account(http_client)
        join(owner["id"], tenancy)
        join(member["id"], tenancy)
        dataset = create_dataset(http_client, owner["id"], tenancy)

        before = update_dataset(http_client, member["id"], dataset)
        opened = members_access(http_client, owner["id"], dataset, True)
        after = update_dataset(http_client, member["id"], dataset)

        assert_status_code(before, 403)
        assert_status_code(opened, 200)
        assert_status_code(after, 200)


class TestShareCandidatesAndLookup:
    def test_candidates_are_empty_for_a_dataset_in_public(self, http_client):
        owner = new_account(http_client)
        dataset = create_dataset(http_client, owner["id"], PUBLIC)
        name = unique("Zelda")
        new_account(http_client, name=name)

        response = http_client.get(
            f"/datasets/{dataset['id']}/share/candidates",
            params={"q": name},
            headers=as_user(owner["id"], PUBLIC),
        )

        assert_status_code(response, 200)
        assert response.json() == []

    def test_candidates_still_come_from_another_tenancy(self, http_client):
        tenancy = new_tenancy()
        owner = new_account(http_client)
        member = new_account(http_client, name=unique("Zelda"))
        join(owner["id"], tenancy)
        join(member["id"], tenancy)
        dataset = create_dataset(http_client, owner["id"], tenancy)

        response = http_client.get(
            f"/datasets/{dataset['id']}/share/candidates",
            params={"q": member["name"]},
            headers=as_user(owner["id"], tenancy),
        )

        assert [user["id"] for user in response.json()] == [member["id"]]

    def test_lookup_by_exact_email_orcid_and_unknown(self, http_client):
        tenancy = new_tenancy()
        owner = new_account(http_client)
        join(owner["id"], tenancy)
        dataset = create_dataset(http_client, owner["id"], tenancy)
        target = new_account(http_client)
        orcid = random_orcid()
        holder = new_account(
            http_client, providers=[{"name": "orcid", "reference": orcid}]
        )
        headers = as_user(owner["id"], tenancy)
        path = f"/datasets/{dataset['id']}/share/lookup"

        by_email = http_client.get(path, params={"value": target["email"].upper()}, headers=headers)
        by_orcid = http_client.get(path, params={"value": orcid}, headers=headers)
        unknown = http_client.get(path, params={"value": "ghost@example.com"}, headers=headers)
        malformed = http_client.get(path, params={"value": "not an address"}, headers=headers)

        assert_status_code(by_email, 200)
        assert by_email.json() == {
            "user": {"id": target["id"], "name": "Bruna Costa", "email": target["email"]},
            "tenancy_member": False,
            "invitation_pending": False,
            "can_invite": True,
        }
        assert by_orcid.json()["user"]["id"] == holder["id"]
        assert_status_code(unknown, 404)
        assert unknown.json() == {"detail": "no_account"}
        assert_status_code(malformed, 400)
        assert malformed.json() == {"detail": "invalid_request"}
```

- [ ] **Step 3: Make it fail first, against the base branch**

A test that passes before the feature exists tests nothing (CLAUDE.md). Build the stack from `docs/rfc-009-tenancies` with the two new files copied in:

```bash
G=/Users/caio.maia/workspace/datamap/gatekeeper
B=$G/.claude/worktrees/rfc-009-baseline
command git -C "$G" worktree add --detach "$B" docs/rfc-009-tenancies
cp tests/integration/fixtures/tenancy.py "$B/tests/integration/fixtures/tenancy.py"
cp tests/integration/test_public_tenancy_api.py "$B/tests/integration/test_public_tenancy_api.py"
```

Then, from `$B` instead of W, follow *Running the integration suite* (same `dc` function, same `ENV_FILE_PATH`, `cd "$B"` first), seed, wait for `/clients/` → 200, and run:

```bash
cd "$B" && $PY -m pytest tests/integration/test_public_tenancy_api.py -q -p no:cacheprovider
```

Expected: every test fails (no public tenancy, roles `[]`, `404` on `/users/{id}/tenancies`, `members_can_edit` `true`, missing `/share/lookup`), 0 passed. A test that passes here is wrong: fix it before going on. `dc down -v`. Keep `$B` for Tasks 15–17.

- [ ] **Step 4: Run it against this branch**

From W, follow *Running the integration suite* (stack up, seeded, `/clients/` → 200), then:

```bash
$PY -m pytest tests/integration/test_public_tenancy_api.py -q -p no:cacheprovider
```

Expected: `16 passed`, 0 failed, 0 skipped. `dc down`.

- [ ] **Step 5: Commit**

```bash
pwd && command git branch --show-current
command git add tests/integration/fixtures/tenancy.py tests/integration/test_public_tenancy_api.py
command git commit -m "test: every account in public, closed datasets, share candidates and lookup (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 15: Integration — tenancy requests and the admin queue

**Files:**
- Create: `tests/integration/test_tenancy_requests_api.py`

**Interfaces:**
- Consumes: `tests/integration/fixtures/tenancy.py` (Task 14), `ADMIN_ADDRESS`, `outbox`, `newest_text` (`tests/integration/fixtures/account.py`), `random_orcid`.

- [ ] **Step 1: Write the tests**

Create `tests/integration/test_tenancy_requests_api.py`:

```python
import pytest

from tests.integration.fixtures.account import ADMIN_ADDRESS, newest_text, outbox
from tests.integration.fixtures.sharing import random_orcid
from tests.integration.fixtures.tenancy import (
    ADMIN_ID,
    LEGACY,
    PUBLIC,
    admin,
    as_user,
    create_dataset,
    display_name,
    event_types,
    events,
    join,
    new_account,
    new_tenancy,
    request_access,
    tenancies_of,
    unique,
)
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.mailpit import Mailpit


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


def _refused(response, status: int, detail: str) -> None:
    assert_status_code(response, status)
    assert response.json() == {"detail": detail}, response.json()


def _withdraw(http_client, user_id: str, request_id: str):
    return http_client.delete(
        f"/users/{user_id}/tenancy-requests/{request_id}", headers=as_user(user_id)
    )


def _approve(http_client, request_id: str, body: dict):
    return http_client.post(
        f"/admin/tenancy-requests/{request_id}/approve", json=body, headers=admin()
    )


def _decline(http_client, request_id: str, body: dict | None = None):
    return http_client.post(
        f"/admin/tenancy-requests/{request_id}/decline", json=body, headers=admin()
    )


def _queue(http_client, **params) -> dict:
    response = http_client.get("/admin/tenancy-requests", params=params, headers=admin())
    assert_status_code(response, 200)
    return response.json()


def _counts(http_client) -> dict:
    response = http_client.get("/admin/tenancy-requests/counts", headers=admin())
    assert_status_code(response, 200)
    return response.json()


class TestAsking:
    def test_a_request_is_stored_trimmed_and_every_admin_is_told(self, http_client):
        account = new_account(http_client)

        response = request_access(http_client, account["id"], name="  ATTO  ")

        assert_status_code(response, 201)
        body = response.json()
        assert (body["status"], body["requested_name"], body["tenancy"]) == ("pending", "ATTO", None)
        items = outbox(http_client, template="tenancy_request_received", related_id=body["id"])["items"]
        assert [item["recipient"] for item in items] == [ADMIN_ADDRESS]
        assert items[0]["subject"] == "Tenancy request from Bruna Costa"
        assert events(f"request_id = '{body['id']}'") == [
            {
                "event_type": "request_created",
                "tenancy": "",
                "user_id": account["id"],
                "actor_id": account["id"],
                "request_id": body["id"],
                "invitation_id": "",
            }
        ]

    def test_one_pending_request_and_three_a_day_withdrawn_included(self, http_client):
        account = new_account(http_client)
        first = request_access(http_client, account["id"])
        assert_status_code(first, 201)
        _refused(request_access(http_client, account["id"]), 409, "request_pending")

        current = first.json()["id"]
        for _ in range(2):
            assert_status_code(_withdraw(http_client, account["id"], current), 204)
            again = request_access(http_client, account["id"])
            assert_status_code(again, 201)
            current = again.json()["id"]
        assert_status_code(_withdraw(http_client, account["id"], current), 204)

        _refused(request_access(http_client, account["id"]), 429, "too_many_requests")

    def test_what_is_asked_is_checked(self, http_client):
        account = new_account(http_client)

        _refused(request_access(http_client, account["id"], name="   "), 400, "tenancy_name_invalid")
        _refused(request_access(http_client, account["id"], reason="x" * 1001), 400, "reason_invalid")
        missing = http_client.post(
            f"/users/{account['id']}/tenancy-requests",
            json={"tenancy_name": "ATTO"},
            headers=as_user(account["id"]),
        )
        _refused(missing, 400, "invalid_request")

    def test_the_latest_requests_and_withdrawing(self, http_client):
        account = new_account(http_client)
        created = request_access(http_client, account["id"]).json()

        withdrawn = _withdraw(http_client, account["id"], created["id"])
        listed = http_client.get(
            f"/users/{account['id']}/tenancy-requests", headers=as_user(account["id"])
        )

        assert_status_code(withdrawn, 204)
        assert [(r["id"], r["status"]) for r in listed.json()] == [(created["id"], "withdrawn")]
        _refused(_withdraw(http_client, account["id"], created["id"]), 404, "request_not_found")
        assert event_types(f"request_id = '{created['id']}'") == [
            "request_created",
            "request_withdrawn",
        ]
        _refused(
            http_client.get(f"/admin/tenancy-requests/{created['id']}", headers=admin()),
            404,
            "request_not_found",
        )

    def test_the_routes_are_self_only_even_for_an_admin(self, http_client):
        account, other = new_account(http_client), new_account(http_client)

        as_other = http_client.get(
            f"/users/{account['id']}/tenancy-requests", headers=as_user(other["id"])
        )
        as_admin = http_client.post(
            f"/users/{account['id']}/tenancy-requests",
            json={"tenancy_name": "ATTO", "reason": "r"},
            headers=admin(),
        )
        tenancies = http_client.get(f"/users/{account['id']}/tenancies", headers=admin())

        for response in (as_other, as_admin, tenancies):
            assert_status_code(response, 401)


class TestTheQueue:
    def test_counts_join_or_new_and_search_by_name_email_and_orcid(self, http_client):
        tenancy = new_tenancy(display_name=unique("Queue Join"))
        joiner = new_account(http_client, name=unique("Joiner"))
        orcid = random_orcid()
        newcomer = new_account(
            http_client,
            name=unique("Newcomer"),
            providers=[{"name": "orcid", "reference": orcid}],
        )
        before = _counts(http_client)

        assert_status_code(
            request_access(http_client, joiner["id"], name=display_name(tenancy).upper()), 201
        )
        assert_status_code(
            request_access(http_client, newcomer["id"], name=unique("Brand new")), 201
        )
        after = _counts(http_client)

        assert after["open"] == before["open"] + 2
        assert after["join"] == before["join"] + 1
        assert after["new"] == before["new"] + 1
        assert after["open"] == after["join"] + after["new"]
        (joined,) = _queue(http_client, q=joiner["name"])["items"]
        assert joined["kind"] == "join"
        assert joined["suggested_tenancy"]["path"] == tenancy
        assert joined["requester"]["email_verified"] is False
        (by_email,) = _queue(http_client, q=newcomer["email"])["items"]
        assert (by_email["kind"], by_email["suggested_tenancy"]) == ("new", None)
        (by_orcid,) = _queue(http_client, q=orcid)["items"]
        assert by_orcid["requester"]["orcid"] == orcid
        assert len(_queue(http_client, kind="join", q=joiner["name"])["items"]) == 1
        assert _queue(http_client, kind="new", q=joiner["name"])["items"] == []

    def test_the_detail_lists_the_requesters_tenancies_and_the_suggestions_size(
        self, http_client
    ):
        tenancy = new_tenancy(display_name=unique("Detail"))
        member = new_account(http_client)
        join(member["id"], tenancy)
        account = new_account(http_client)
        request = request_access(http_client, account["id"], name=display_name(tenancy)).json()

        detail = http_client.get(f"/admin/tenancy-requests/{request['id']}", headers=admin())

        assert_status_code(detail, 200)
        assert [t["path"] for t in detail.json()["requester_tenancies"]] == [PUBLIC]
        assert detail.json()["suggested_tenancy_members"] == 1

    def test_bad_paging_is_invalid_request(self, http_client):
        for params in ({"limit": 0}, {"limit": 101}, {"status": "everything"}, {"limit": "x"}):
            response = http_client.get("/admin/tenancy-requests", params=params, headers=admin())
            _refused(response, 400, "invalid_request")


class TestApproving:
    def test_into_an_existing_tenancy(self, http_client, mailpit):
        tenancy = new_tenancy(display_name=unique("Approved"))
        owner = new_account(http_client)
        join(owner["id"], tenancy)
        dataset = create_dataset(http_client, owner["id"], tenancy)
        account = new_account(http_client)
        request = request_access(http_client, account["id"], name=display_name(tenancy)).json()

        approved = _approve(http_client, request["id"], {"tenancy": tenancy})

        assert_status_code(approved, 200)
        body = approved.json()
        assert (body["status"], body["created_tenancy"]) == ("approved", False)
        assert body["tenancy"]["path"] == tenancy
        assert body["decided_by"]["id"] == ADMIN_ID
        assert tenancy in tenancies_of(http_client, account["id"])
        readable = http_client.get(
            f"/datasets/{dataset['id']}", headers=as_user(account["id"], tenancy)
        )
        assert_status_code(readable, 200)
        text = newest_text(http_client, mailpit, account["email"])
        assert f"gave you access to {display_name(tenancy)} on DataMap." in text
        assert event_types(f"request_id = '{request['id']}'") == [
            "member_added",
            "request_approved",
            "request_created",
        ]
        (added,) = events(f"request_id = '{request['id']}' AND event_type = 'member_added'")
        assert (added["actor_id"], added["tenancy"]) == (ADMIN_ID, tenancy)
        mine = http_client.get(
            f"/users/{account['id']}/tenancy-requests", headers=as_user(account["id"])
        ).json()
        assert (mine[0]["status"], mine[0]["tenancy"]["path"]) == ("approved", tenancy)
        _refused(_approve(http_client, request["id"], {"tenancy": tenancy}), 409, "request_not_pending")
        _refused(_decline(http_client, request["id"]), 409, "request_not_pending")

    def test_into_a_new_tenancy(self, http_client):
        account = new_account(http_client, confirmed=True)
        request = request_access(http_client, account["id"], name="Cerrado Flux").json()
        namespace, name = unique("cerrado"), unique("Cerrado Flux")

        approved = _approve(
            http_client,
            request["id"],
            {"new_tenancy": {"display_name": name, "namespace": namespace}},
        )

        assert_status_code(approved, 200)
        path = f"datamap/production/{namespace}"
        assert approved.json()["created_tenancy"] is True
        assert approved.json()["tenancy"] == {
            "path": path,
            "display_name": name,
            "is_default": False,
            "is_legacy": False,
        }
        assert execute(f"SELECT is_enabled, display_name FROM tenancies WHERE name = '{path}'") == f"t|{name}"
        assert path in tenancies_of(http_client, account["id"])
        assert event_types(f"request_id = '{request['id']}'") == [
            "member_added",
            "request_approved",
            "request_created",
            "tenancy_created",
        ]

    def test_every_refusal(self, http_client):
        existing = new_tenancy(display_name=unique("Taken"))
        member = new_account(http_client, confirmed=True)
        join(member["id"], existing)
        request = request_access(http_client, member["id"]).json()["id"]
        fresh = {"display_name": unique("Fresh"), "namespace": unique("fresh")}

        _refused(_approve(http_client, request, {"tenancy": existing}), 409, "already_member")
        _refused(
            _approve(http_client, request, {"new_tenancy": {**fresh, "namespace": existing.rsplit("/", 1)[1]}}),
            409,
            "tenancy_exists",
        )
        _refused(
            _approve(http_client, request, {"new_tenancy": {**fresh, "display_name": display_name(existing).lower()}}),
            409,
            "display_name_taken",
        )
        _refused(
            _approve(http_client, request, {"new_tenancy": {**fresh, "namespace": "Not Valid"}}),
            400,
            "namespace_invalid",
        )
        _refused(
            _approve(http_client, request, {"new_tenancy": {**fresh, "namespace": "public"}}),
            400,
            "namespace_invalid",
        )
        _refused(_approve(http_client, request, {"tenancy": PUBLIC}), 409, "public_tenancy_locked")
        _refused(_approve(http_client, request, {"tenancy": LEGACY}), 409, "legacy_tenancy_read_only")
        _refused(
            _approve(http_client, request, {"tenancy": new_tenancy(enabled=False)}),
            409,
            "tenancy_disabled",
        )
        _refused(
            _approve(http_client, request, {"tenancy": f"datamap/production/{unique('none')}"}),
            404,
            "tenancy_not_found",
        )
        _refused(_approve(http_client, request, {}), 400, "invalid_request")
        _refused(_approve(http_client, request, {"tenancy": existing, "new_tenancy": fresh}), 400, "invalid_request")

        unverified = new_account(http_client)
        other = request_access(http_client, unverified["id"]).json()["id"]
        _refused(
            _approve(http_client, other, {"new_tenancy": fresh}), 409, "requester_email_unverified"
        )
        assert event_types(f"request_id = '{request}'") == ["request_created"]


class TestDeclining:
    def test_with_a_message_and_only_once(self, http_client, mailpit):
        account = new_account(http_client)
        request = request_access(http_client, account["id"]).json()

        declined = _decline(http_client, request["id"], {"message": "  Ask Alan to invite you.  "})

        assert_status_code(declined, 200)
        assert declined.json()["status"] == "declined"
        assert declined.json()["decision_message"] == "Ask Alan to invite you."
        text = newest_text(http_client, mailpit, account["email"])
        assert "An administrator could not give you access to ATTO." in text
        assert "Ask Alan to invite you." in text
        _refused(_decline(http_client, request["id"]), 409, "request_not_pending")
        (declined_event,) = events(f"request_id = '{request['id']}' AND event_type = 'request_declined'")
        assert declined_event["actor_id"] == ADMIN_ID

    def test_a_long_message_is_refused(self, http_client):
        account = new_account(http_client)
        request = request_access(http_client, account["id"]).json()

        _refused(_decline(http_client, request["id"], {"message": "x" * 1001}), 400, "message_invalid")

    def test_closed_requests_show_the_decision(self, http_client):
        account = new_account(http_client, name=unique("Closed"))
        request = request_access(http_client, account["id"]).json()
        assert_status_code(_decline(http_client, request["id"]), 200)

        (row,) = _queue(http_client, status="closed", q=account["name"])["items"]

        assert row["status"] == "declined"
        assert row["decision_message"] is None
        assert row["decided_by"]["id"] == ADMIN_ID
        assert _queue(http_client, status="open", q=account["name"])["items"] == []
```

- [ ] **Step 2: Make it fail first, against the base branch**

```bash
B=/Users/caio.maia/workspace/datamap/gatekeeper/.claude/worktrees/rfc-009-baseline
cp tests/integration/test_tenancy_requests_api.py "$B/tests/integration/test_tenancy_requests_api.py"
```

From `$B`, follow *Running the integration suite* (up, seed, `/clients/` → 200), then:

```bash
cd "$B" && $PY -m pytest tests/integration/test_tenancy_requests_api.py -q -p no:cacheprovider
```

Expected: every test fails (`404` on every new route), 0 passed. `dc down -v`.

- [ ] **Step 3: Run it against this branch**

From W: *Running the integration suite* (up, seed, `/clients/` → 200), then:

```bash
$PY -m pytest tests/integration/test_tenancy_requests_api.py -q -p no:cacheprovider
```

Expected: `14 passed`, 0 failed, 0 skipped. `dc down`.

- [ ] **Step 4: Commit**

```bash
pwd && command git branch --show-current
command git add tests/integration/test_tenancy_requests_api.py
command git commit -m "test: tenancy requests, the admin queue, approval and decline (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 16: Integration — tenancy invitations

**Files:**
- Create: `tests/integration/test_tenancy_invitations_api.py`

**Interfaces:**
- Consumes: `tests/integration/fixtures/tenancy.py` (Task 14), `grant` (`tests/integration/fixtures/embargo.py`: SQL permission row plus the `datasets_shared` role, as RFC 003's grant does), `ADMIN_ADDRESS`, `outbox`, `newest_text`.

**Known gap, pinned by a test (reported, not fixed here):** `DELETE /v1/datasets/{id}/tenancy-invitations/{invitation_id}` keeps the contract's `authorize` guard, and the seeded `datasets_write` policy allows only `(GET|POST|PUT)`. An inviter whose only role is `datasets_write` — every owner created after this PR — is refused by Casbin with `401` before the service runs. `datasets_shared` (given with any RFC 003 share) allows `DELETE` on concrete dataset ids. The RFC rules out new `p` rows, so this plan does not add one; `test_an_inviter_with_only_datasets_write_is_stopped_by_casbin` pins today's behaviour and must be inverted when the owner decides (a `p` row `datasets_write`, `/api/v1/datasets/[0-9a-f-]{36}/tenancy-invitations/[0-9a-f-]{36}$`, `DELETE`, `allow`, or a service-checked route). The same policy already blocks RFC 003's `DELETE /share/...` routes for such owners.

- [ ] **Step 1: Write the tests**

Create `tests/integration/test_tenancy_invitations_api.py`:

```python
from types import SimpleNamespace

import pytest

from tests.integration.fixtures.account import ADMIN_ADDRESS, newest_text, outbox
from tests.integration.fixtures.embargo import grant
from tests.integration.fixtures.tenancy import (
    ADMIN_ID,
    LEGACY,
    PUBLIC,
    admin,
    as_user,
    create_dataset,
    display_name,
    event_types,
    events,
    join,
    members_access,
    new_account,
    new_tenancy,
    tenancies_of,
    unique,
)
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.mailpit import Mailpit


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


@pytest.fixture
def world(http_client):
    tenancy = new_tenancy(display_name=unique("Invites"))
    owner = new_account(http_client, name=unique("Owner"))
    join(owner["id"], tenancy)
    dataset = create_dataset(http_client, owner["id"], tenancy)
    invitee = new_account(http_client, name=unique("Invitee"))
    return SimpleNamespace(tenancy=tenancy, owner=owner, dataset=dataset, invitee=invitee)


def _refused(response, status: int, detail: str) -> None:
    assert_status_code(response, status)
    assert response.json() == {"detail": detail}, response.json()


def _invite(http_client, inviter_id: str, dataset: dict, invitee_id: str):
    return http_client.post(
        f"/datasets/{dataset['id']}/tenancy-invitations",
        json={"user_id": invitee_id},
        headers=as_user(inviter_id, dataset["tenancy"]),
    )


def _withdraw(http_client, user_id: str, dataset: dict, invitation_id: str):
    return http_client.delete(
        f"/datasets/{dataset['id']}/tenancy-invitations/{invitation_id}",
        headers=as_user(user_id, dataset["tenancy"]),
    )


def _status(invitation_id: str) -> str:
    return execute(f"SELECT status FROM tenancy_invitations WHERE id = '{invitation_id}'")


def _editor(http_client, world, name: str) -> dict:
    editor = new_account(http_client, name=unique(name))
    join(editor["id"], world.tenancy)
    grant(http_client, world.dataset["id"], editor["id"], "write")
    return editor


class TestWhoMayInvite:
    def test_the_owner_invites_and_the_invitee_and_admins_are_told(
        self, http_client, mailpit, world
    ):
        response = _invite(http_client, world.owner["id"], world.dataset, world.invitee["id"])

        assert_status_code(response, 201)
        body = response.json()
        assert body["user"]["id"] == world.invitee["id"]
        assert body["invited_by"]["id"] == world.owner["id"]
        assert body["can_withdraw"] is True
        text = newest_text(http_client, mailpit, world.invitee["email"])
        assert f"invited you to join {display_name(world.tenancy)} on DataMap" in text
        assert "This email cannot accept for you." in text
        notices = outbox(http_client, template="tenancy_invitation_notice", related_id=body["id"])["items"]
        assert [n["recipient"] for n in notices] == [ADMIN_ADDRESS]
        (created,) = events(f"invitation_id = '{body['id']}'")
        assert (created["event_type"], created["actor_id"]) == ("invitation_created", world.owner["id"])

    def test_a_write_collaborator_who_is_a_member_invites(self, http_client, world):
        editor = _editor(http_client, world, "Editor")

        response = _invite(http_client, editor["id"], world.dataset, world.invitee["id"])

        assert_status_code(response, 201)

    def test_a_reader_a_members_can_edit_member_and_an_outside_collaborator_may_not(
        self, http_client, world
    ):
        reader = new_account(http_client)
        join(reader["id"], world.tenancy)
        grant(http_client, world.dataset["id"], reader["id"], "read")
        member = new_account(http_client)
        join(member["id"], world.tenancy)
        assert_status_code(members_access(http_client, world.owner["id"], world.dataset, True), 200)
        outsider = new_account(http_client)
        grant(http_client, world.dataset["id"], outsider["id"], "write")

        for inviter in (reader, member, outsider):
            _refused(
                _invite(http_client, inviter["id"], world.dataset, world.invitee["id"]),
                403,
                "forbidden",
            )

    def test_public_and_staging_cannot_be_invited_to(self, http_client):
        owner, invitee = new_account(http_client), new_account(http_client)
        join(owner["id"], LEGACY)
        in_public = create_dataset(http_client, owner["id"], PUBLIC)
        in_staging = create_dataset(http_client, owner["id"], LEGACY)

        _refused(_invite(http_client, owner["id"], in_public, invitee["id"]), 409, "public_tenancy_locked")
        _refused(_invite(http_client, owner["id"], in_staging, invitee["id"]), 409, "legacy_tenancy_read_only")

    def test_members_unknown_accounts_and_a_second_invitation(self, http_client, world):
        member = new_account(http_client)
        join(member["id"], world.tenancy)
        assert_status_code(
            _invite(http_client, world.owner["id"], world.dataset, world.invitee["id"]), 201
        )

        _refused(_invite(http_client, world.owner["id"], world.dataset, member["id"]), 409, "already_member")
        _refused(
            _invite(http_client, world.owner["id"], world.dataset, world.invitee["id"]),
            409,
            "invitation_pending",
        )
        _refused(
            _invite(http_client, world.owner["id"], world.dataset, "00000000-0000-0000-0000-000000000000"),
            404,
            "no_account",
        )


class TestTheInvitee:
    def test_sees_accepts_and_joins(self, http_client, world):
        invitation = _invite(
            http_client, world.owner["id"], world.dataset, world.invitee["id"]
        ).json()
        mine = as_user(world.invitee["id"])

        listed = http_client.get(f"/users/{world.invitee['id']}/tenancy-invitations", headers=mine)
        accepted = http_client.post(
            f"/users/{world.invitee['id']}/tenancy-invitations/{invitation['id']}/accept",
            headers=mine,
        )

        (pending,) = listed.json()
        assert pending["tenancy"]["path"] == world.tenancy
        assert pending["invited_by"]["id"] == world.owner["id"]
        assert pending["dataset"] == {"id": world.dataset["id"], "name": world.dataset["name"]}
        assert pending["datasets"] == 1
        assert_status_code(accepted, 200)
        assert accepted.json()["tenancy"]["path"] == world.tenancy
        assert world.tenancy in tenancies_of(http_client, world.invitee["id"])
        assert _status(invitation["id"]) == "accepted"
        assert event_types(f"invitation_id = '{invitation['id']}'") == [
            "invitation_accepted",
            "invitation_created",
            "member_added",
        ]
        read = http_client.get(
            f"/datasets/{world.dataset['id']}",
            headers=as_user(world.invitee["id"], world.tenancy),
        )
        assert_status_code(read, 200)
        _refused(
            http_client.post(
                f"/users/{world.invitee['id']}/tenancy-invitations/{invitation['id']}/accept",
                headers=mine,
            ),
            404,
            "invitation_not_found",
        )

    def test_only_the_invitee_accepts(self, http_client, world):
        invitation = _invite(
            http_client, world.owner["id"], world.dataset, world.invitee["id"]
        ).json()
        other = new_account(http_client)

        someone_else = http_client.post(
            f"/users/{world.invitee['id']}/tenancy-invitations/{invitation['id']}/accept",
            headers=as_user(other["id"]),
        )
        on_their_own_id = http_client.post(
            f"/users/{other['id']}/tenancy-invitations/{invitation['id']}/accept",
            headers=as_user(other["id"]),
        )

        assert_status_code(someone_else, 401)
        _refused(on_their_own_id, 404, "invitation_not_found")

    def test_declines(self, http_client, world):
        invitation = _invite(
            http_client, world.owner["id"], world.dataset, world.invitee["id"]
        ).json()

        declined = http_client.post(
            f"/users/{world.invitee['id']}/tenancy-invitations/{invitation['id']}/decline",
            headers=as_user(world.invitee["id"]),
        )

        assert_status_code(declined, 204)
        assert _status(invitation["id"]) == "declined"
        assert world.tenancy not in tenancies_of(http_client, world.invitee["id"])


class TestWithdrawing:
    def test_the_inviter_withdraws_and_another_editor_may_not(self, http_client, world):
        inviter = _editor(http_client, world, "Inviter")
        other_editor = _editor(http_client, world, "Other editor")
        invitation = _invite(http_client, inviter["id"], world.dataset, world.invitee["id"]).json()

        refused = _withdraw(http_client, other_editor["id"], world.dataset, invitation["id"])
        withdrawn = _withdraw(http_client, inviter["id"], world.dataset, invitation["id"])

        _refused(refused, 403, "forbidden")
        assert_status_code(withdrawn, 204)
        assert _status(invitation["id"]) == "withdrawn"
        _refused(
            _withdraw(http_client, inviter["id"], world.dataset, invitation["id"]),
            404,
            "invitation_not_found",
        )

    def test_an_inviter_with_only_datasets_write_is_stopped_by_casbin(self, http_client, world):
        invitation = _invite(
            http_client, world.owner["id"], world.dataset, world.invitee["id"]
        ).json()

        response = _withdraw(http_client, world.owner["id"], world.dataset, invitation["id"])

        assert_status_code(response, 401)
        assert _status(invitation["id"]) == "pending"

    def test_an_admin_withdraws(self, http_client, world):
        invitation = _invite(
            http_client, world.owner["id"], world.dataset, world.invitee["id"]
        ).json()

        withdrawn = http_client.delete(
            f"/admin/tenancy-invitations/{invitation['id']}", headers=admin()
        )

        assert_status_code(withdrawn, 204)
        assert _status(invitation["id"]) == "withdrawn"
        (event,) = events(
            f"invitation_id = '{invitation['id']}' AND event_type = 'invitation_withdrawn'"
        )
        assert event["actor_id"] == ADMIN_ID
        _refused(
            http_client.delete(f"/admin/tenancy-invitations/{invitation['id']}", headers=admin()),
            404,
            "invitation_not_found",
        )


class TestTheShareDialog:
    def test_the_share_state_carries_pending_invitations_and_whether_one_may_invite(
        self, http_client, world
    ):
        invitation = _invite(
            http_client, world.owner["id"], world.dataset, world.invitee["id"]
        ).json()

        state = http_client.get(
            f"/datasets/{world.dataset['id']}/share",
            headers=as_user(world.owner["id"], world.tenancy),
        )

        assert_status_code(state, 200)
        body = state.json()
        assert body["can_invite_to_tenancy"] is True
        assert [i["id"] for i in body["tenancy_invitations"]] == [invitation["id"]]
        assert body["tenancy"]["name"] == display_name(world.tenancy)
        assert (body["tenancy"]["is_default"], body["tenancy"]["is_legacy"]) == (False, False)
        assert body["tenancy"]["datasets"] == 1

    def test_the_lookup_says_when_someone_was_already_invited(self, http_client, world):
        path = f"/datasets/{world.dataset['id']}/share/lookup"
        headers = as_user(world.owner["id"], world.tenancy)

        before = http_client.get(path, params={"value": world.invitee["email"]}, headers=headers)
        _invite(http_client, world.owner["id"], world.dataset, world.invitee["id"])
        after = http_client.get(path, params={"value": world.invitee["email"]}, headers=headers)

        assert (before.json()["can_invite"], before.json()["invitation_pending"]) == (True, False)
        assert (after.json()["can_invite"], after.json()["invitation_pending"]) == (False, True)
```

- [ ] **Step 2: Make it fail first, against the base branch**

```bash
B=/Users/caio.maia/workspace/datamap/gatekeeper/.claude/worktrees/rfc-009-baseline
cp tests/integration/test_tenancy_invitations_api.py "$B/tests/integration/test_tenancy_invitations_api.py"
```

From `$B`: *Running the integration suite* (up, seed, `/clients/` → 200), then:

```bash
cd "$B" && $PY -m pytest tests/integration/test_tenancy_invitations_api.py -q -p no:cacheprovider
```

Expected: every test fails, 0 passed (`test_an_inviter_with_only_datasets_write_is_stopped_by_casbin` fails at `_invite` returning `404`, not at the assertion it pins). `dc down -v`.

- [ ] **Step 3: Run it against this branch**

From W: *Running the integration suite*, then:

```bash
$PY -m pytest tests/integration/test_tenancy_invitations_api.py -q -p no:cacheprovider
```

Expected: `13 passed`, 0 failed, 0 skipped. `dc down`.

- [ ] **Step 4: Commit**

```bash
pwd && command git branch --show-current
command git add tests/integration/test_tenancy_invitations_api.py
command git commit -m "test: tenancy invitations from the share dialog (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 17: Integration — admin tenancies, the `/admin` refusal, retired routes, and the migration

**Files:**
- Create: `tests/integration/test_admin_tenancies_api.py`
- Create: `tests/integration/test_tenancy_migration.py`

**Interfaces:**
- Consumes: `tests/integration/fixtures/tenancy.py` (Task 14), `grant`, `newest_text`, `random_orcid`, `disable` (`tests/integration/fixtures/account.py`).

- [ ] **Step 1: Write the admin tests**

Create `tests/integration/test_admin_tenancies_api.py`:

```python
import uuid

import pytest

from tests.integration.fixtures.account import disable, newest_text
from tests.integration.fixtures.embargo import grant
from tests.integration.fixtures.sharing import random_orcid
from tests.integration.fixtures.tenancy import (
    ADMIN_ID,
    LEGACY,
    PUBLIC,
    admin,
    as_user,
    create_dataset,
    display_name,
    events,
    join,
    new_account,
    new_tenancy,
    set_roles,
    tenancies_of,
    unique,
)
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.mailpit import Mailpit

SOMEONE = str(uuid.uuid4())


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


def _refused(response, status: int, detail: str) -> None:
    assert_status_code(response, status)
    assert response.json() == {"detail": detail}, response.json()


def _members_path(tenancy: str) -> str:
    return f"/admin/tenancies/{tenancy}/members"


def _add(http_client, tenancy: str, user_id: str):
    return http_client.post(_members_path(tenancy), json={"user_id": user_id}, headers=admin())


def _remove(http_client, tenancy: str, user_id: str):
    return http_client.delete(f"{_members_path(tenancy)}/{user_id}", headers=admin())


def _create(http_client, display: str, namespace: str):
    return http_client.post(
        "/admin/tenancies",
        json={"display_name": display, "namespace": namespace},
        headers=admin(),
    )


class TestOnlyAdmins:
    ROUTES = (
        ("get", "/admin/tenancy-requests/counts", None),
        ("get", "/admin/tenancy-requests", None),
        ("get", f"/admin/tenancy-requests/{SOMEONE}", None),
        ("post", f"/admin/tenancy-requests/{SOMEONE}/approve", {"tenancy": PUBLIC}),
        ("post", f"/admin/tenancy-requests/{SOMEONE}/decline", {}),
        ("get", "/admin/tenancies", None),
        ("post", "/admin/tenancies", {"display_name": "X", "namespace": "x-1"}),
        ("get", f"/admin/tenancies/{PUBLIC}/members", None),
        ("get", f"/admin/tenancies/{PUBLIC}/members/{SOMEONE}", None),
        ("post", f"/admin/tenancies/{PUBLIC}/members", {"user_id": SOMEONE}),
        ("delete", f"/admin/tenancies/{PUBLIC}/members/{SOMEONE}", None),
        ("delete", f"/admin/tenancy-invitations/{SOMEONE}", None),
        ("get", "/admin/users?q=ana", None),
    )

    def test_a_users_write_account_gets_401_on_every_admin_route(self, http_client):
        account = new_account(http_client)
        set_roles(http_client, account["id"], add=("users_write",))
        headers = as_user(account["id"])

        for method, path, body in self.ROUTES:
            response = getattr(http_client, method)(path, json=body, headers=headers)
            assert response.status_code == 401, f"{method.upper()} {path}: {response.status_code}"

    def test_the_retired_membership_routes_are_gone_even_for_an_admin(self, http_client):
        account = new_account(http_client)
        body = {"tenancies": ["datamap/production/data-amazon"]}

        added = http_client.post(f"/users/{account['id']}/tenancies", json=body, headers=admin())
        removed = http_client.delete(f"/users/{account['id']}/tenancies", json=body, headers=admin())

        assert added.status_code in (404, 405)
        assert removed.status_code in (404, 405)
        assert tenancies_of(http_client, account["id"]) == [PUBLIC]

    def test_tenancies_routes_lock_public(self, http_client):
        renamed = http_client.put(
            f"/tenancies/{PUBLIC}", json={"name": "x", "is_enabled": False}, headers=admin()
        )
        disabled = http_client.delete(f"/tenancies/{PUBLIC}", headers=admin())

        _refused(renamed, 409, "public_tenancy_locked")
        _refused(disabled, 409, "public_tenancy_locked")


class TestTheList:
    def test_public_first_legacy_last_with_counts(self, http_client):
        created = new_tenancy(display_name=unique("Listed"))
        response = http_client.get("/admin/tenancies", headers=admin())

        assert_status_code(response, 200)
        rows = response.json()
        paths = [row["path"] for row in rows]
        assert paths[0] == PUBLIC
        assert rows[0]["is_default"] is True
        assert rows[0]["members"] >= 1
        legacy_start = min(i for i, row in enumerate(rows) if row["is_legacy"])
        assert all(row["is_legacy"] for row in rows[legacy_start:])
        assert LEGACY in paths[legacy_start:]
        assert created in paths[1:legacy_start]
        (row,) = [r for r in rows if r["path"] == created]
        assert row == {
            "path": created,
            "display_name": display_name(created),
            "members": 0,
            "datasets": 0,
            "is_default": False,
            "is_legacy": False,
            "is_enabled": True,
        }


class TestCreating:
    def test_a_tenancy_is_created_once_with_its_event(self, http_client):
        namespace, display = unique("atto"), unique("ATTO")

        created = _create(http_client, display, namespace)

        assert_status_code(created, 201)
        path = f"datamap/production/{namespace}"
        assert created.json()["path"] == path
        assert created.json()["is_enabled"] is True
        (event,) = events(f"tenancy = '{path}'")
        assert (event["event_type"], event["actor_id"]) == ("tenancy_created", ADMIN_ID)
        _refused(_create(http_client, unique("Other"), namespace), 409, "tenancy_exists")
        _refused(_create(http_client, display.lower(), unique("other")), 409, "display_name_taken")
        _refused(_create(http_client, "Fine", "Bad NS"), 400, "namespace_invalid")
        _refused(_create(http_client, "Fine", "public"), 400, "namespace_invalid")
        _refused(_create(http_client, "   ", unique("fine")), 400, "display_name_invalid")


class TestMembers:
    def test_adding_a_member_emails_them_and_lists_them(self, http_client, mailpit):
        tenancy = new_tenancy(display_name=unique("Members"))
        account = new_account(http_client)

        added = _add(http_client, tenancy, account["id"])

        assert_status_code(added, 201)
        assert added.json()["id"] == account["id"]
        assert added.json()["invited_by"] is None
        assert tenancy in tenancies_of(http_client, account["id"])
        text = newest_text(http_client, mailpit, account["email"])
        assert f"gave you access to {display_name(tenancy)} on DataMap." in text
        (event,) = events(f"tenancy = '{tenancy}' AND user_id = '{account['id']}'")
        assert (event["event_type"], event["actor_id"]) == ("member_added", ADMIN_ID)
        listed = http_client.get(_members_path(tenancy), headers=admin()).json()
        assert listed["members"]["total_count"] == 1
        assert listed["members"]["items"][0]["id"] == account["id"]
        assert listed["invitations"] == []

    def test_adding_refusals(self, http_client):
        tenancy = new_tenancy()
        account = new_account(http_client)
        assert_status_code(_add(http_client, tenancy, account["id"]), 201)

        _refused(_add(http_client, tenancy, account["id"]), 409, "already_member")
        _refused(_add(http_client, PUBLIC, account["id"]), 409, "public_tenancy_locked")
        _refused(_add(http_client, LEGACY, account["id"]), 409, "legacy_tenancy_read_only")
        _refused(_add(http_client, new_tenancy(enabled=False), account["id"]), 409, "tenancy_disabled")
        _refused(
            _add(http_client, f"datamap/production/{unique('none')}", account["id"]),
            404,
            "tenancy_not_found",
        )
        _refused(_add(http_client, tenancy, SOMEONE), 404, "no_account")

    def test_paging_members(self, http_client):
        tenancy = new_tenancy()
        for _ in range(3):
            join(new_account(http_client)["id"], tenancy)

        page = http_client.get(
            _members_path(tenancy), params={"limit": 2, "offset": 2}, headers=admin()
        ).json()["members"]

        assert (page["total_count"], len(page["items"]), page["limit"], page["offset"]) == (3, 1, 2, 2)


class TestRemoving:
    def test_impact_removal_and_what_the_member_keeps(self, http_client):
        tenancy = new_tenancy()
        owner, member = new_account(http_client), new_account(http_client)
        join(owner["id"], tenancy)
        assert_status_code(_add(http_client, tenancy, member["id"]), 201)
        theirs = create_dataset(http_client, member["id"], tenancy)
        shared = create_dataset(http_client, owner["id"], tenancy)
        grant(http_client, shared["id"], member["id"], "read")

        impact = http_client.get(f"{_members_path(tenancy)}/{member['id']}", headers=admin())
        removed = _remove(http_client, tenancy, member["id"])
        next_call = http_client.get(
            f"/datasets/{shared['id']}", headers=as_user(member["id"], tenancy)
        )
        still_theirs = http_client.get(
            f"/datasets/{theirs['id']}", headers=as_user(member["id"])
        )

        assert_status_code(impact, 200)
        assert impact.json()["datasets_in_tenancy"] == 2
        assert impact.json()["shared_with_user"] == 1
        assert impact.json()["owned_by_user"] == 1
        assert impact.json()["member_since"]
        assert_status_code(removed, 204)
        assert_status_code(next_call, 401)
        assert next_call.json()["detail"].startswith("unauthorized_tenancy")
        assert_status_code(still_theirs, 200)
        assert tenancy not in tenancies_of(http_client, member["id"])
        (event,) = events(f"tenancy = '{tenancy}' AND event_type = 'member_removed'")
        assert (event["user_id"], event["actor_id"]) == (member["id"], ADMIN_ID)
        _refused(_remove(http_client, tenancy, member["id"]), 404, "member_not_found")
        _refused(
            http_client.get(f"{_members_path(tenancy)}/{member['id']}", headers=admin()),
            404,
            "member_not_found",
        )

    def test_public_and_legacy_are_locked_and_unknown_is_not_found(self, http_client):
        account = new_account(http_client)

        _refused(_remove(http_client, PUBLIC, account["id"]), 409, "public_tenancy_locked")
        _refused(_remove(http_client, LEGACY, ADMIN_ID), 409, "legacy_tenancy_read_only")
        _refused(
            _remove(http_client, f"datamap/production/{unique('none')}", account["id"]),
            404,
            "tenancy_not_found",
        )

    def test_removing_someone_who_joined_by_invitation_revokes_it(self, http_client):
        tenancy = new_tenancy()
        owner, invitee = new_account(http_client, name=unique("Owner")), new_account(http_client)
        join(owner["id"], tenancy)
        dataset = create_dataset(http_client, owner["id"], tenancy)
        invitation = http_client.post(
            f"/datasets/{dataset['id']}/tenancy-invitations",
            json={"user_id": invitee["id"]},
            headers=as_user(owner["id"], tenancy),
        ).json()
        pending = http_client.get(_members_path(tenancy), headers=admin()).json()["invitations"]
        assert_status_code(
            http_client.post(
                f"/users/{invitee['id']}/tenancy-invitations/{invitation['id']}/accept",
                headers=as_user(invitee["id"]),
            ),
            200,
        )
        listed = http_client.get(_members_path(tenancy), headers=admin()).json()

        removed = _remove(http_client, tenancy, invitee["id"])

        assert [i["id"] for i in pending] == [invitation["id"]]
        (joined,) = [m for m in listed["members"]["items"] if m["id"] == invitee["id"]]
        assert joined["invited_by"]["name"] == owner["name"]
        assert_status_code(removed, 204)
        assert execute(
            f"SELECT status FROM tenancy_invitations WHERE id = '{invitation['id']}'"
        ) == "revoked"


class TestUserSearch:
    def test_by_name_email_and_orcid_enabled_only(self, http_client):
        orcid = random_orcid()
        found = new_account(
            http_client, name=unique("Searchable"), providers=[{"name": "orcid", "reference": orcid}]
        )
        gone = new_account(http_client, name=unique("Searchable"))
        disable(http_client, gone["id"])

        by_name = http_client.get("/admin/users", params={"q": found["name"]}, headers=admin())
        by_email = http_client.get("/admin/users", params={"q": found["email"]}, headers=admin())
        by_orcid = http_client.get("/admin/users", params={"q": orcid}, headers=admin())
        not_disabled = http_client.get("/admin/users", params={"q": gone["name"]}, headers=admin())

        expected = [{"id": found["id"], "name": found["name"], "email": found["email"]}]
        assert by_name.json() == expected
        assert by_email.json() == expected
        assert by_orcid.json() == expected
        assert not_disabled.json() == []
        _refused(
            http_client.get("/admin/users", params={"q": " a "}, headers=admin()),
            400,
            "invalid_request",
        )
```

- [ ] **Step 2: Write the migration test**

Create `tests/integration/test_tenancy_migration.py`:

```python
import subprocess
import uuid

from tests.integration.utils.database import execute

GATEKEEPER_CONTAINER = "datamap_gatekeeper_test_integration"
PUBLIC = "datamap/production/public"
DATA_AMAZON = "datamap/production/data-amazon"


def _alembic(*args: str) -> str:
    completed = subprocess.run(
        ["docker", "exec", GATEKEEPER_CONTAINER, "python3", "-m", "alembic", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout + completed.stderr


def _user(name: str) -> str:
    user_id = str(uuid.uuid4())
    execute(
        "INSERT INTO users (id, name, email, is_enabled, created_at, updated_at) "
        f"VALUES ('{user_id}', '{name}', '{user_id}@example.com', true, now(), now())"
    )
    return user_id


def _dataset(tenancy: str) -> str:
    dataset_id = str(uuid.uuid4())
    execute(
        "INSERT INTO datasets (id, name, data, is_enabled, tenancy, members_can_edit, created_at, updated_at) "
        f"VALUES ('{dataset_id}', 'migration', '{{}}'::jsonb, true, '{tenancy}', true, now(), now())"
    )
    return dataset_id


def _roles(user_id: str) -> list[str]:
    return execute(
        f"SELECT v1 FROM casbin_rule WHERE ptype = 'g' AND v0 = '{user_id}' ORDER BY v1"
    ).split()


class TestTheMigration:
    def test_it_backfills_public_roles_and_defaults_and_survives_a_round_trip(self):
        plain = _user("Plain Account")
        reader = _user("Read Only")
        boss = _user("Admin Only")
        execute(
            "INSERT INTO casbin_rule (ptype, v0, v1) VALUES "
            f"('g', '{reader}', 'datasets_read'), ('g', '{boss}', 'admin')"
        )
        outside = _dataset(DATA_AMAZON)
        inside = _dataset(PUBLIC)

        down = _alembic("downgrade", "-1")
        up = _alembic("upgrade", "head")

        assert "c3d4e5f6a7b8 -> b1c2d3e4f5a6" in down
        assert "b1c2d3e4f5a6 -> c3d4e5f6a7b8" in up
        assert execute("SELECT version_num FROM alembic_version") == "c3d4e5f6a7b8"
        assert execute(
            f"SELECT display_name, is_enabled FROM tenancies WHERE name = '{PUBLIC}'"
        ) == "Public|t"
        for user_id in (plain, reader, boss):
            assert execute(
                f"SELECT count(*) FROM users_tenancies WHERE user_id = '{user_id}' AND tenancy = '{PUBLIC}'"
            ) == "1"
            assert execute(
                f"SELECT count(*) FROM tenancy_events WHERE user_id = '{user_id}' "
                f"AND tenancy = '{PUBLIC}' AND event_type = 'member_added' AND actor_id IS NULL"
            ) == "1"
        assert _roles(plain) == ["datasets_write"]
        assert _roles(reader) == ["datasets_read"]
        assert _roles(boss) == ["admin"]
        assert execute(f"SELECT members_can_edit FROM datasets WHERE id = '{outside}'") == "t"
        assert execute(f"SELECT members_can_edit FROM datasets WHERE id = '{inside}'") == "f"
        assert execute(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'datasets' AND column_name = 'members_can_edit'"
        ) == "false"

    def test_running_the_upgrade_twice_changes_nothing(self):
        before = execute(
            "SELECT (SELECT count(*) FROM users_tenancies), (SELECT count(*) FROM casbin_rule), "
            "(SELECT count(*) FROM tenancy_events)"
        )

        _alembic("downgrade", "-1")
        _alembic("upgrade", "head")
        after = execute(
            "SELECT (SELECT count(*) FROM users_tenancies), (SELECT count(*) FROM casbin_rule), "
            "(SELECT count(*) FROM tenancy_events)"
        )

        users, rules, _ = before.split("|")
        assert after.split("|")[:2] == [users, rules]
```

The round trip drops `tenancy_requests`, `tenancy_invitations` and `tenancy_events`, and with them the rows earlier files wrote; the second test therefore compares only memberships and Casbin rows, which the downgrade keeps, and the backfill must not duplicate. Pytest runs the files alphabetically, so this file runs after the other tenancy files; nothing later reads those rows.

- [ ] **Step 3: Make them fail first, against the base branch**

```bash
B=/Users/caio.maia/workspace/datamap/gatekeeper/.claude/worktrees/rfc-009-baseline
cp tests/integration/test_admin_tenancies_api.py tests/integration/test_tenancy_migration.py "$B/tests/integration/"
```

From `$B`: *Running the integration suite* (up, seed, `/clients/` → 200), then:

```bash
cd "$B" && $PY -m pytest tests/integration/test_admin_tenancies_api.py tests/integration/test_tenancy_migration.py -q -p no:cacheprovider
```

Expected: every test fails, 0 passed. Two caveats to check by reading the failures, not by trusting the count: `test_the_retired_membership_routes_are_gone_even_for_an_admin` fails because `POST /users/{id}/tenancies` answers `200` on the base, and `test_a_users_write_account_gets_401_on_every_admin_route` fails because the base has no public tenancy for `new_account`'s check, or because some admin routes answer `404` where `401` is expected — both are real failures. `dc down -v`, then remove the baseline worktree:

```bash
command git -C /Users/caio.maia/workspace/datamap/gatekeeper worktree remove --force "$B"
```

- [ ] **Step 4: Run them against this branch**

From W: *Running the integration suite*, then:

```bash
$PY -m pytest tests/integration/test_admin_tenancies_api.py tests/integration/test_tenancy_migration.py -q -p no:cacheprovider
```

Expected: `14 passed`, 0 failed, 0 skipped. `dc down`.

- [ ] **Step 5: Commit**

```bash
pwd && command git branch --show-current
command git add tests/integration/test_admin_tenancies_api.py tests/integration/test_tenancy_migration.py
command git commit -m "test: admin tenancies, the /admin refusal, retired routes and the migration (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 18: Validation loop, push, pull request

**Files:** whatever `ruff check --fix` and `ruff format` touch.

**Interfaces:** none new.

- [ ] **Step 1: Unit tests**

```bash
cd /Users/caio.maia/workspace/datamap/gatekeeper/.claude/worktrees/rfc-009-gatekeeper
$PY -m pytest -q -p no:cacheprovider 2>&1 | tail -3
```

Expected: no `failed`, no `error`; the passed count is at least Task 1's baseline minus the deleted tests (`TestNewAccountNotification`, `TestAdminAddresses` moved, the two `remove_tenancies` tests, `test_the_admin_notification_lists_the_account`) plus every test this plan added.

- [ ] **Step 2: The whole integration suite (controller only)**

Follow *Running the integration suite* in full (other projects down, clock resync, `dc down -v`, bucket directory, build, up, health 200, seed, `/clients/` 200), then:

```bash
$PY -m pytest tests/integration/ -q -p no:cacheprovider
```

Expected: `0 failed`, no `skipped` from `verify_services_running`, and the five new files collected (`test_public_tenancy_api.py`, `test_tenancy_requests_api.py`, `test_tenancy_invitations_api.py`, `test_admin_tenancies_api.py`, `test_tenancy_migration.py`). Read the summary line yourself. A batch of `401`s in the first files is Casbin's reload after the seed: re-run the `/clients/` poll and the suite. If a test fails, do not re-run the whole suite before reading the failure and `docker logs datamap_gatekeeper_test_integration 2>&1 | tail -200`.

Also run the Makefile's full cycle once, as CLAUDE.md requires, and read its summary (it swallows failures, and its `timeout` does not exist on macOS):

```bash
dc down -v
mkdir -p "$(grep STORAGE_DOCKER_VOLUME integration-test.env | cut -d= -f2)_test_integration/datamap"
make ENV_FILE_PATH=integration-test.env integration-test-full
```

While it runs, after `Integration test containers ready`, confirm `curl -s -m 3 -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/` prints `200`. Note: the Makefile uses the default compose project (the directory name), not `rfc-009`; it starts and stops its own stack. A batch of 401s at the start of its run is Casbin's reload (it seeds and runs at once); the run in this step's first half is the authority.

- [ ] **Step 3: Lint and format**

```bash
ruff check
ruff check --fix
ruff format
command git status --short
```

Expected: `ruff check` ends with `All checks passed!` (after `--fix`); `git status` lists only files this plan touched. Re-run `$PY -m pytest -q -p no:cacheprovider 2>&1 | tail -3` if formatting changed anything.

- [ ] **Step 4: Commit the formatting, push, open the pull request**

```bash
pwd && command git branch --show-current
command git add -A app tests migrations
command git diff --cached --stat
command git commit -m "style: ruff format (RFC 009)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" || true
command git push -u origin feat/rfc-009-gatekeeper
gh pr create --base main --head feat/rfc-009-gatekeeper --title "feat: tenancies for everyone, requests, invitations and the admin API (RFC 009, PR A)" --body "$(cat <<'EOF'
## Summary
- Every account is in `datamap/production/public` and holds `datasets_write`, by every creation path; the migration backfills existing accounts (only those with no dataset or admin role get `datasets_write`).
- New datasets start with `members_can_edit = false`; public is never member-editable (`400 public_members_cannot_edit`).
- Users request tenancies; admins approve (existing or new tenancy) or decline under `/v1/admin/*`; owners and `write` editors invite existing accounts into their tenancy from the share dialog.
- `tenancy_events` records every membership change; five emails go through the outbox; `new_account_pending` and `POST/DELETE /users/{id}/tenancies` are gone.

Spec: `docs/rfcs/009-tenancies-and-admin.md`. Contract: `docs/superpowers/plans/2026-10-05-rfc-009-contract.md`.

## Before deploying
- `ADMIN_NOTIFICATION_EMAILS` lists people who will act on requests.
- Give `datasets_read` beforehand to any account with no dataset role that must stay read-only.
- Known gap: an inviter whose only role is `datasets_write` cannot `DELETE /datasets/{id}/tenancy-invitations/{id}` (Casbin has no `DELETE` for that role); pinned by `test_an_inviter_with_only_datasets_write_is_stopped_by_casbin`.

## Test plan
- [ ] `pytest`
- [ ] Integration suite: 0 failed, new files collected
- [ ] `ruff check`, `ruff format`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: the push succeeds and `gh` prints the pull request URL.

---

## Self-review: RFC 009 PR A requirements → tasks

| Requirement (RFC / contract) | Task |
|---|---|
| `tenancies.display_name` (nullable, 64), resolved everywhere, never `null` | 2, 3, 8 (`summary`), 12 (share state), 7 (emails) |
| Migration: public tenancy (`ON CONFLICT … COALESCE`) | 3, verified 17 |
| Migration: every user into public | 3, verified 17 |
| Migration: `datasets_write` only for users with no `admin`/`datasets_read`/`datasets_write`/`datasets_admin` | 3, verified 17 |
| Migration: `members_can_edit` server default `false`, public rows set `false`, others kept | 3, verified 17 |
| Migration: three enums, three tables, indexes; downgrade leaves data | 3, verified 3 (round trip) and 17 |
| `DEFAULT_TENANCY` constant in `app/model/tenancy.py` | 2 |
| `UserService.create`: public + `datasets_write` + `member_added` with no actor; no `new_account_pending` | 5, verified 14 (three creation paths) |
| `new_account_pending` template and its integration test removed | 5 |
| `members_can_edit` default `false` (column, model, create) | 3, 4, verified 14 |
| `allows_member_edits` false in public whatever the column | 4, verified 14 |
| Moving into public stores `false` | 4, verified 14 |
| `PUT /members-access` `true` on public → `400 public_members_cannot_edit`; `false` no-op | 4, verified 14 |
| Public lock: `PUT`/`DELETE /tenancies/{public}`, admin member routes, approvals, invitations → `409 public_tenancy_locked` | 8, 11, 12, 13, verified 15–17 |
| Legacy staging read-only (`409 legacy_tenancy_read_only`), listed after production, no invitations | 8, 13, verified 15–17 |
| `authorize_self` (self routes; Casbin not consulted; admins refused) | 9, 10, verified 15 |
| `GET /users/{id}/tenancies` | 10, verified 14–17 |
| Requests: create, latest 5, withdraw; validation; one pending; 3 per 24 h | 10, verified 15 |
| Admin queue: counts, list (status/kind/q/limit/offset), detail, suggestion (join/new), search by name/email/ORCID | 11, verified 15 |
| Approve existing / new tenancy, all error codes, atomic, events, email | 10 (repository), 11, verified 15 |
| Decline with optional message, email | 10, 11, verified 15 |
| Invitations: who may invite, rules, emails to invitee and admins | 12, verified 16 |
| Accept / decline (self-only), withdraw by inviter, `403` for another editor, admin withdraw | 12, verified 16 |
| `GET /datasets/{id}/share` gains `tenancy_invitations`, `can_invite_to_tenancy`, tenancy `is_default`/`is_legacy`/`datasets` | 12, verified 16 |
| Share lookup by exact email / ORCID; `no_account`; `invalid_request` | 12, verified 14 and 16 |
| Share candidates `[]` in public | 12, verified 14 |
| Admin tenancies: list, create, members (paged, `since`, `invited_by`, pending invitations), removal impact, add (email), remove (revokes accepted invitation, no email) | 13, verified 17 |
| Removed member's next dataset call → `401 unauthorized_tenancy…` | existing `_determine_tenancies`, verified 17 |
| `GET /admin/users?q=` (≥ 2 chars, ≤ 10, enabled) | 13, verified 17 |
| `POST`/`DELETE /users/{id}/tenancies` removed | 5, verified 10 and 17 |
| No new Casbin `p` rows; `users_write` gets `401` on every `/admin` route | 11, 13, verified 17 |
| Five emails (contexts, dedup keys, admin per address, empty list sends nothing, placeholder skipped) | 7, verified 15–17 (`outbox`, Mailpit); empty list in unit tests (7) |
| `tenancy_events` for every flow | 5, 8, 10, 12, 13, verified 14–17 |
| Quiet `400 invalid_request` on every new route | 9, verified 10–13 and 15 |
| Admin dataset access unchanged (no bypass) | nothing added; the admin seeded user is never used to read others' datasets in the new tests |
| Unit: `allows_member_edits` public, namespace validation, request matching, display-name fallback | 4, 2, 11, 2 |
