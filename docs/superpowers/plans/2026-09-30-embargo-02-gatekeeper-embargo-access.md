# Dataset Embargo — Gatekeeper Embargo and Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a dataset's embargo real in the gatekeeper: the embargo columns, per-dataset permissions, one access rule applied on every dataset route, no snapshot while embargoed, the embargo routes, and access for people outside the tenancy.

**Architecture:** A `DatasetAccessService` holds the single access rule (`level_of`, `permits`, `require`). `DatasetService` stops filtering by tenancy in SQL for single-dataset routes: it fetches by id (`restrict_by_tenancy=False`) through one method, `fetch_authorized`, which then asks the access service. Search keeps the filter in SQL, extended with owner and permission clauses. An `EmbargoService` owns set/extend/end/mode, and an `EmbargoAudit` writes the append-only trail and counts it. Permission holders get the `datasets_shared` Casbin role, so a permission is sufficient on its own.

**Tech Stack:** Python 3.10 (production image `python:3.10.14-alpine`), FastAPI 0.111, SQLAlchemy 1.4.23, Alembic, dependency-injector, Casbin 1.23, prometheus-client, pytest, unittest.mock, integration tests against Docker (PostgreSQL, MinIO, WireMock).

**Spec:** `docs/rfcs/003-dataset-embargo.md` (§Database changes, §Access rule, §People from outside the tenancy, §Public snapshots during the embargo, §Who sees what, §Lifecycle, §Audit). **Contracts:** `docs/superpowers/plans/2026-09-30-embargo-00-contracts.md` (wins over this plan on any interface).

## Global Constraints

- Migration revision id `e5f6a7b8c9d0`, `down_revision = "d4e5f6a7b8c9"` (plan 01's email migration). The chain is fixed: 01 `d4e5f6a7b8c9` → 02 `e5f6a7b8c9d0` → 03 `f6a7b8c9d0e1`, and the plans merge in that order. Develop on a branch that already contains plan 01's migration; never re-point `down_revision`.
- 90-day cap: `MAX_EMBARGO_PERIOD = timedelta(days=90)`, validated on create and on every extension, against `now()` in the service. Error codes exactly: `embargo_too_long`, `embargo_until_in_past`, `embargo_dataset_published`, `embargo_already_active`, `embargo_not_active`, `embargo_until_not_later`, `embargo_active`.
- "Published" means `datasets.visibility == PUBLIC`.
- A caller who may not see a dataset gets **404** on every dataset route; a caller who can see it but may not perform the action gets **403** `{"detail": "forbidden"}`.
- Administrators get no exception from the embargo. The access rule never looks at roles except to keep today's tenancy-role behaviour for tenancy members.
- Download URL TTL: 1 hour while the embargo is active, 7 days otherwise.
- A manual DOI and an embargo never coexist. `POST .../doi` with `mode: MANUAL` on an embargoed dataset answers `400 embargo_manual_doi_ends_embargo` unless the body carries `"end_embargo": true`; with it, a non-owner gets 403 and the owner's request ends the embargo (`ended_early`, note `"manual DOI"`), creates the DOI and publishes the snapshot as today. `PUT /embargo` answers `400 embargo_manual_doi` when any version has a manual DOI, checked before and independently of `embargo_dataset_published`.
- Ending an embargo, by route or by manual DOI, goes through one seam, `EmbargoTermination.end`: it sets `embargo_until` to the moment it ended and records `ended_early`. It notifies nobody. Plan 03's dispatch pass finds every embargo whose date has passed, ended early or run out alike, writes `expired` and queues the *Embargo ended* emails; one mechanism covers both, since no request triggers a natural expiry.
- A missing or empty `X-Datamap-Tenancies` header is valid on every user route: it means the caller's own tenancies, possibly none. A caller with no tenancy reaches, through a permission, the dataset routes, search (`shared=true` and default), downloads and writes.
- The production image is `python:3.10.14-alpine`: no syntax newer than Python 3.10 (no `except*`, no `typing.Self`, no PEP 695 generics). `X | None` annotations are fine.
- Casbin role name: `datasets_shared`.
- Metric: `datamap_embargo_events_total{event}`.
- Code style (CLAUDE.md): no narrating comments; one-line comment only where a reader would otherwise undo something on purpose. Type hints everywhere. Dataclasses for models.
- Integration tests are mandatory for this plan: it changes `app/repository/`, route paths, status codes and Casbin seed data.
- Never pipe `make` into `tail`/`grep` and read the exit code. Confirm the API answered before trusting an integration run.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `app/model/embargo.py` | create | Enums (`PermissionLevel`, `AccessLevel`, `DatasetAction`, `EmbargoEventType`), constants, `Embargo`, `DatasetAccess`, `DatasetPermission`, `embargo_active()`, `utcnow()` |
| `app/model/embargo_test.py` | create | Unit tests for the pure helpers |
| `app/model/db/embargo.py` | create | `DatasetPermission`, `DatasetEmbargoEvent` ORM models |
| `app/model/db/dataset.py` | modify | Three embargo columns on `Dataset` |
| `app/model/dataset.py` | modify | `Dataset.embargo`, `Dataset.access`, `DatasetVersion.files_withheld`, `DatasetQuery.shared` |
| `migrations/versions/2026_09_30_1210-e5f6a7b8c9d0_add_dataset_embargo.py` | create | Schema |
| `migrations/env.py` | modify | Import `app.model.db.embargo` for autogenerate |
| `app/exception/forbidden.py` | create | `ForbiddenException` |
| `app/controller/interceptor/exception_handler.py`, `app/setup.py` | modify | 403 handler; register new routers |
| `app/controller/interceptor/exception_handler_test.py` | create | Handler test |
| `app/repository/permission.py` | create | `PermissionRepository` |
| `app/repository/embargo_event.py` | create | `EmbargoEventRepository` |
| `app/metrics.py`, `app/metrics_test.py` | modify | `datamap_embargo_events_total` |
| `app/service/embargo_audit.py` (+ `_test.py`) | create | `EmbargoAudit.record()` — append event + metric |
| `app/service/embargo_termination.py` (+ `_test.py`) | create | `EmbargoTermination.end()` — the one way an embargo ends early |
| `app/service/dataset_access.py` (+ `_test.py`) | create | `DatasetAccessService` — the access rule |
| `app/service/permission.py` (+ `_test.py`) | create | `PermissionService.grant/revoke/list_for_dataset` (plan 03 calls `grant`) |
| `app/service/dataset.py`, `app/service/dataset_test.py` | modify | `fetch_authorized`; every method authorized; owner fix; snapshot block; TTL; files withheld; embargo/access on views |
| `app/repository/dataset.py` | modify | Search: owner / permission / tenancy-with-embargo clause; `shared` |
| `app/service/embargo.py` (+ `_test.py`) | create | `EmbargoService` — set, extend, end, mode, status |
| `app/controller/v1/dataset/resource.py` | modify | Embargo/access response and request models; `DOICreateRequest.end_embargo` |
| `app/controller/v1/dataset/dataset.py` | modify | Adapters; `shared` query param; `user_id` on delete/enable |
| `app/controller/v1/dataset/embargo.py` | create | `PUT /embargo`, `POST /embargo/extend`, `POST /embargo/end`, `PUT /embargo/mode` |
| `app/controller/v1/dataset/embargo_status.py` | create | `GET /datasets/{id}/embargo-status` (client-only) |
| `app/container.py` | modify | New providers and wiring |
| `app/service/tus.py`, `app/service/tus_test.py` | modify/create | Refuse uploads the access rule forbids |
| `app/resources/casbin_seed_policies.sql`, `app/resources/rbac_data.sql`, `tests/integration/fixtures/seed_clients.sql` | modify | `datasets_shared` policies |
| `tests/integration/fixtures/embargo.py` | create | Users, grants, embargo helpers |
| `tests/integration/test_dataset_embargo.py` | create | End-to-end behaviour |

## Task Graph

```
T1 model+migration ─┬─ T2 repositories ─┬─ T4 access service ─┬─ T6 DatasetService authorization ── T7 embargo views/snapshots/TTL ─┐
T3 403 exception ───┘   T5 audit+metric ┘                    ├─ T8 search SQL                                                       ├─ T12 integration ── T13 validation
                                                             ├─ T9 permission service                                               │
                                                             └─ T10 embargo service + routes ──────────────────────────────────────┤
T5 also builds EmbargoTermination, which T6 injects and T7/T10 use.
T11 Casbin seeds (independent) ────────────────────────────────────────────────────────────────────────────────────────────────────┘
TUS refusal is part of T6.
```

Parallelizable: {T1, T3, T11}; then {T2, T5}; then T4; then {T6, T8, T9, T10} (T6 and T8 both touch `app/service/dataset.py`: run T8 after T6 if they share a worktree); T7 after T6; T12 after all; T13 last.

---

### Task 1: Domain model, ORM models and migration

**Files:**
- Create: `app/model/embargo.py`, `app/model/embargo_test.py`, `app/model/db/embargo.py`, `migrations/versions/2026_09_30_1210-e5f6a7b8c9d0_add_dataset_embargo.py`
- Modify: `app/model/db/dataset.py:3-15,58-70`, `app/model/dataset.py:52-104`, `migrations/env.py:27-33`

**Interfaces:**
- Produces: everything in `app/model/embargo.py` (names used by every later task and by plan 03); ORM `DatasetPermission`, `DatasetEmbargoEvent`; `Dataset.embargo_until`, `Dataset.embargo_metadata_visible`, `Dataset.embargo_note`; domain `Dataset.embargo: Embargo | None`, `Dataset.access: DatasetAccess | None`, `DatasetVersion.files_withheld: bool`, `DatasetQuery.shared: bool`.

- [ ] **Step 1: Write the failing test** — `app/model/embargo_test.py`

```python
import unittest
from datetime import datetime, timedelta, timezone

from app.model.embargo import (
    MAX_EMBARGO_PERIOD,
    AccessLevel,
    EmbargoEventType,
    PermissionLevel,
    embargo_active,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class TestEmbargoActive(unittest.TestCase):
    def test_no_date_is_no_embargo(self):
        self.assertFalse(embargo_active(None, NOW))

    def test_a_future_date_is_an_active_embargo(self):
        self.assertTrue(embargo_active(NOW + timedelta(seconds=1), NOW))

    def test_a_date_that_has_passed_is_no_longer_an_embargo(self):
        self.assertFalse(embargo_active(NOW, NOW))
        self.assertFalse(embargo_active(NOW - timedelta(days=1), NOW))


class TestConstants(unittest.TestCase):
    def test_the_cap_is_ninety_days(self):
        self.assertEqual(MAX_EMBARGO_PERIOD, timedelta(days=90))

    def test_levels_serialise_to_the_contract_values(self):
        self.assertEqual(
            [level.value for level in AccessLevel],
            ["owner", "write", "read", "tenancy"],
        )
        self.assertEqual([level.value for level in PermissionLevel], ["read", "write"])

    def test_event_types_fit_the_column(self):
        for event in EmbargoEventType:
            self.assertLessEqual(len(event.value), 32)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest app/model/embargo_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.model.embargo'`

- [ ] **Step 3: Write `app/model/embargo.py`**

```python
import enum
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

MAX_EMBARGO_PERIOD = timedelta(days=90)
REMINDER_OFFSETS_DAYS = (15, 10, 5, 1)
REDACTED = "[redacted]"
SHARED_ROLE = "datasets_shared"


class PermissionLevel(str, enum.Enum):
    READ = "read"
    WRITE = "write"


class AccessLevel(str, enum.Enum):
    OWNER = "owner"
    WRITE = "write"
    READ = "read"
    TENANCY = "tenancy"


class DatasetAction(enum.Enum):
    READ_METADATA = "read_metadata"
    READ_FILES = "read_files"
    WRITE = "write"
    DELETE = "delete"
    EXTEND_EMBARGO = "extend_embargo"
    MANAGE_EMBARGO = "manage_embargo"


class EmbargoEventType(str, enum.Enum):
    CREATED = "created"
    EXTENDED = "extended"
    ENDED_EARLY = "ended_early"
    EXPIRED = "expired"
    METADATA_MODE_CHANGED = "metadata_mode_changed"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"
    INVITATION_CREATED = "invitation_created"
    INVITATION_REVOKED = "invitation_revoked"
    REVIEW_LINK_CREATED = "review_link_created"
    REVIEW_LINK_REVOKED = "review_link_revoked"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def embargo_active(until: datetime | None, now: datetime) -> bool:
    return until is not None and until > now


@dataclass
class Embargo:
    until: datetime
    active: bool
    metadata_visible: bool
    note: str | None = None


@dataclass
class DatasetAccess:
    level: AccessLevel
    can_edit: bool
    can_share: bool
    can_manage_embargo: bool
    can_extend_embargo: bool
    can_delete: bool


@dataclass
class DatasetPermission:
    dataset_id: UUID
    user_id: UUID
    level: PermissionLevel
    granted_by: UUID | None = None
    created_at: datetime | None = None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest app/model/embargo_test.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Add the ORM models** — `app/model/db/embargo.py`

```python
import sqlalchemy
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


class DatasetPermission(Base):
    __tablename__ = "dataset_permissions"
    dataset_id = Column(
        UUID(as_uuid=True), ForeignKey("datasets.id"), primary_key=True
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    level = Column(String(16), nullable=False)
    granted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("level IN ('read', 'write')", name="ck_dataset_permissions_level"),
        Index("idx_dataset_permissions_user", "user_id"),
    )


class DatasetEmbargoEvent(Base):
    __tablename__ = "dataset_embargo_events"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False)
    event_type = Column(String(32), nullable=False)
    old_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=True)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    note = Column(Text, nullable=True)
    occurred_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sqlalchemy.text("now()"),
    )

    __table_args__ = (
        Index(
            "idx_dataset_embargo_events_dataset",
            "dataset_id",
            sqlalchemy.text("occurred_at DESC"),
        ),
    )
```

- [ ] **Step 6: Add the embargo columns** — `app/model/db/dataset.py`

Add `Text` to the `from sqlalchemy import (...)` list (lines 3-14), then after `search_vector = Column(String, nullable=True)` (line 70):

```python
    embargo_until = Column(DateTime(timezone=True), nullable=True)
    embargo_metadata_visible = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sqlalchemy.false(),
    )
    embargo_note = Column(Text, nullable=True)
```

- [ ] **Step 7: Extend the domain dataclasses** — `app/model/dataset.py`

Add the import at the top (after `from app.model.doi import DOI`):

```python
from app.model.embargo import DatasetAccess, Embargo
```

In `DatasetVersion`, after `doi: DOI = None`:

```python
    files_withheld: bool = False
```

In `Dataset`, after `file_count: int = None`:

```python
    embargo: Embargo | None = None
    access: DatasetAccess | None = None
```

In `DatasetQuery`, after `minimal: bool = False`:

```python
    shared: bool = False
```

- [ ] **Step 8: Write the migration** — `migrations/versions/2026_09_30_1210-e5f6a7b8c9d0_add_dataset_embargo.py`

```python
"""Add dataset embargo, per-dataset permissions and the embargo audit trail

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-30 12:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column("embargo_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "datasets",
        sa.Column(
            "embargo_metadata_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("datasets", sa.Column("embargo_note", sa.Text(), nullable=True))

    op.create_table(
        "dataset_permissions",
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datasets.id"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            primary_key=True,
        ),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column(
            "granted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "level IN ('read', 'write')", name="ck_dataset_permissions_level"
        ),
    )
    op.create_index(
        "idx_dataset_permissions_user", "dataset_permissions", ["user_id"]
    )

    op.create_table(
        "dataset_embargo_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datasets.id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column(
            "changed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_dataset_embargo_events_dataset",
        "dataset_embargo_events",
        ["dataset_id", sa.text("occurred_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_dataset_embargo_events_dataset", table_name="dataset_embargo_events"
    )
    op.drop_table("dataset_embargo_events")
    op.drop_index("idx_dataset_permissions_user", table_name="dataset_permissions")
    op.drop_table("dataset_permissions")
    op.drop_column("datasets", "embargo_note")
    op.drop_column("datasets", "embargo_metadata_visible")
    op.drop_column("datasets", "embargo_until")
```

- [ ] **Step 9: Register the models for autogenerate** — `migrations/env.py`, after `from app.model.db import doi  # noqa: E402, F401`:

```python
from app.model.db import embargo  # noqa: E402, F401
```

- [ ] **Step 10: Verify the migration against a real database**

Run:
```bash
make ENV_FILE_PATH=local.env docker-run-db
make ENV_FILE_PATH=local.env db-upgrade
make ENV_FILE_PATH=local.env db-downgrade
make ENV_FILE_PATH=local.env db-upgrade
```
Expected: each command exits 0; the downgrade/upgrade round trip shows `Running downgrade e5f6a7b8c9d0 -> d4e5f6a7b8c9` and `Running upgrade d4e5f6a7b8c9 -> e5f6a7b8c9d0`.

Then check autogenerate proposes nothing:
```bash
make ENV_FILE_PATH=local.env MESSAGE="check embargo parity" db-create-migration
```
Expected: the generated file's `upgrade()` and `downgrade()` contain only `pass`. Delete that generated file.

- [ ] **Step 11: Run the unit suite**

Run: `pytest`
Expected: PASS (no test touches the new columns yet)

- [ ] **Step 12: Commit**

```bash
git add app/model/embargo.py app/model/embargo_test.py app/model/db/embargo.py app/model/db/dataset.py app/model/dataset.py migrations/env.py "migrations/versions/2026_09_30_1210-e5f6a7b8c9d0_add_dataset_embargo.py"
git commit -m "feat: embargo columns, dataset permissions and the embargo audit table"
```

---

### Task 2: Repositories for permissions and embargo events

**Files:**
- Create: `app/repository/permission.py`, `app/repository/embargo_event.py`

**Interfaces:**
- Consumes: ORM `DatasetPermission`, `DatasetEmbargoEvent` (Task 1).
- Produces:
  - `PermissionRepository.fetch(dataset_id: UUID, user_id: UUID) -> DatasetPermission | None`
  - `PermissionRepository.upsert(dataset_id: UUID, user_id: UUID, level: str, granted_by: UUID | None) -> DatasetPermission`
  - `PermissionRepository.delete(dataset_id: UUID, user_id: UUID) -> bool`
  - `PermissionRepository.list_for_dataset(dataset_id: UUID) -> list[DatasetPermission]`
  - `EmbargoEventRepository.append(dataset_id: UUID, event_type: str, changed_by: UUID | None, old_value: dict | None, new_value: dict | None, note: str | None) -> None`
  - `EmbargoEventRepository.list_for_dataset(dataset_id: UUID) -> list[DatasetEmbargoEvent]`

Repositories follow the existing pattern and have no unit tests in this codebase; their SQL is exercised by Task 12's integration suite (CLAUDE.md: unit tests mock the repository and cannot see SQL).

- [ ] **Step 1: Write `app/repository/permission.py`**

```python
from contextlib import AbstractContextManager
from typing import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.model.db.embargo import DatasetPermission


class PermissionRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def fetch(self, dataset_id: UUID, user_id: UUID) -> DatasetPermission | None:
        with self._session_factory() as session:
            return (
                session.query(DatasetPermission)
                .filter_by(dataset_id=dataset_id, user_id=user_id)
                .first()
            )

    def upsert(
        self, dataset_id: UUID, user_id: UUID, level: str, granted_by: UUID | None
    ) -> DatasetPermission:
        with self._session_factory() as session:
            permission = (
                session.query(DatasetPermission)
                .filter_by(dataset_id=dataset_id, user_id=user_id)
                .first()
            )
            if permission is None:
                permission = DatasetPermission(
                    dataset_id=dataset_id,
                    user_id=user_id,
                    level=level,
                    granted_by=granted_by,
                )
                session.add(permission)
            else:
                permission.level = level
                permission.granted_by = granted_by
            session.commit()
            session.refresh(permission)
            return permission

    def delete(self, dataset_id: UUID, user_id: UUID) -> bool:
        with self._session_factory() as session:
            deleted = (
                session.query(DatasetPermission)
                .filter_by(dataset_id=dataset_id, user_id=user_id)
                .delete()
            )
            session.commit()
            return deleted > 0

    def list_for_dataset(self, dataset_id: UUID) -> list[DatasetPermission]:
        with self._session_factory() as session:
            return (
                session.query(DatasetPermission)
                .filter_by(dataset_id=dataset_id)
                .order_by(DatasetPermission.created_at.asc())
                .all()
            )
```

- [ ] **Step 2: Write `app/repository/embargo_event.py`**

```python
from contextlib import AbstractContextManager
from typing import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.model.db.embargo import DatasetEmbargoEvent


class EmbargoEventRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def append(
        self,
        dataset_id: UUID,
        event_type: str,
        changed_by: UUID | None,
        old_value: dict | None,
        new_value: dict | None,
        note: str | None,
    ) -> None:
        with self._session_factory() as session:
            session.add(
                DatasetEmbargoEvent(
                    dataset_id=dataset_id,
                    event_type=event_type,
                    changed_by=changed_by,
                    old_value=old_value,
                    new_value=new_value,
                    note=note,
                )
            )
            session.commit()

    def list_for_dataset(self, dataset_id: UUID) -> list[DatasetEmbargoEvent]:
        with self._session_factory() as session:
            return (
                session.query(DatasetEmbargoEvent)
                .filter_by(dataset_id=dataset_id)
                .order_by(DatasetEmbargoEvent.occurred_at.desc())
                .all()
            )
```

- [ ] **Step 3: Check they import and lint**

Run: `python -c "import app.repository.permission, app.repository.embargo_event" && ruff check app/repository/permission.py app/repository/embargo_event.py`
Expected: no output from Python; `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add app/repository/permission.py app/repository/embargo_event.py
git commit -m "feat: repositories for dataset permissions and embargo events"
```

---

### Task 3: A 403 for callers who can see a dataset but may not act on it

**Files:**
- Create: `app/exception/forbidden.py`, `app/controller/interceptor/exception_handler_test.py`
- Modify: `app/controller/interceptor/exception_handler.py`, `app/setup.py:191-201`

**Interfaces:**
- Produces: `ForbiddenException(Exception)`; HTTP `403 {"detail": "forbidden"}`.

- [ ] **Step 1: Write the failing test** — `app/controller/interceptor/exception_handler_test.py`

```python
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import setup
from app.exception.forbidden import ForbiddenException


class TestForbiddenHandler(unittest.TestCase):
    def test_a_forbidden_action_answers_403_without_the_exception_text(self):
        app = FastAPI()
        setup.setup_error_handlers(app)

        @app.get("/boom")
        def boom():
            raise ForbiddenException("user x may not delete dataset y")

        response = TestClient(app, raise_server_exceptions=False).get("/boom")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "forbidden"})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest app/controller/interceptor/exception_handler_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.exception.forbidden'`

- [ ] **Step 3: Implement**

`app/exception/forbidden.py`:

```python
class ForbiddenException(Exception):
    pass
```

`app/controller/interceptor/exception_handler.py` — add the import next to the other exception imports and the handler after `unauthorized_exception_handler`:

```python
from app.exception.forbidden import ForbiddenException
```

```python
async def forbidden_exception_handler(request: Request, exc: ForbiddenException):
    logger.info(f"Forbidden exception: {exc}")
    return JSONResponse(status_code=403, content={"detail": "forbidden"})
```

`app/setup.py` — import `forbidden_exception_handler` and `ForbiddenException` where the other handlers are imported, and in `setup_error_handlers`, after the `UnauthorizedException` registration:

```python
    fastAPIApp.add_exception_handler(ForbiddenException, forbidden_exception_handler)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest app/controller/interceptor/exception_handler_test.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/exception/forbidden.py app/controller/interceptor/exception_handler.py app/controller/interceptor/exception_handler_test.py app/setup.py
git commit -m "feat: answer 403 when a visible dataset forbids the action"
```

---

### Task 4: The access rule — `DatasetAccessService`

**Files:**
- Create: `app/service/dataset_access.py`, `app/service/dataset_access_test.py`

**Interfaces:**
- Consumes: `PermissionRepository.fetch` (Task 2); `UserService.fetch_by_id(id)`, `UserService.enforce(user_id, resource, action)` (existing); `ForbiddenException` (Task 3); `app.model.embargo` (Task 1).
- Produces (used by Tasks 6–10 and plan 03):
  - `embargo_active(dataset, now: datetime | None = None) -> bool`
  - `embargo_of(dataset, now: datetime | None = None) -> Embargo | None`
  - `level_of(user_id: UUID | None, dataset, tenancies: list[str], now: datetime | None = None) -> AccessLevel | None`
  - `permits(user_id: UUID, dataset, tenancies: list[str], action: DatasetAction, now: datetime | None = None) -> bool`
  - `require(user_id: UUID, dataset, tenancies: list[str], action: DatasetAction, now: datetime | None = None) -> AccessLevel` — raises `NotFoundException` when invisible, `ForbiddenException` when visible but not allowed
  - `access_flags(user_id: UUID, dataset, tenancies: list[str], level: AccessLevel, now: datetime | None = None) -> DatasetAccess`
  - `owner_disabled(dataset) -> bool`

Rule (RFC §Access rule, contracts §Dataset payload additions):

| Level | Actions while embargo active | Actions with no active embargo |
|---|---|---|
| owner | all | all |
| write permission | read metadata, read files, write; extend if owner disabled | read metadata, read files, write; plus tenancy rules if in the tenancy |
| read permission | read metadata, read files; extend if owner disabled | read metadata, read files; plus tenancy rules if in the tenancy |
| tenancy (open mode only) | read metadata, if the user's tenancy role allows `GET` | each action allowed iff the user's tenancy role allows its method (`GET`/`PUT`/`DELETE`) — today's behaviour |
| none | nothing (404) | nothing (404) |

`MANAGE_EMBARGO` is owner-only. The tenancy role check enforces against `/api/v1/datasets/tenancy-scope`, a path that tenancy roles' policies match (`/api/v1/datasets` prefix, `/*` for admin) and `datasets_shared`'s policies do not (`/api/v1/datasets/?$`, `/api/v1/datasets/<uuid>...`); otherwise the shared role would leak tenancy-wide write access.

- [ ] **Step 1: Write the failing tests** — `app/service/dataset_access_test.py`

```python
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

from app.exception.forbidden import ForbiddenException
from app.exception.not_found import NotFoundException
from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.db.embargo import DatasetPermission as DatasetPermissionDBModel
from app.model.embargo import AccessLevel, DatasetAction
from app.repository.permission import PermissionRepository
from app.service.dataset_access import DatasetAccessService
from app.service.user import UserService

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
TENANCY = "datamap/production/data-amazon"


def _dataset(owner_id=None, until=None, visible=False, tenancy=TENANCY):
    return DatasetDBModel(
        id=uuid4(),
        name="d",
        data={},
        owner_id=owner_id,
        tenancy=tenancy,
        embargo_until=until,
        embargo_metadata_visible=visible,
        embargo_note=None,
    )


class TestDatasetAccessService(unittest.TestCase):
    def setUp(self):
        self.permissions = Mock(spec=PermissionRepository)
        self.permissions.fetch.return_value = None
        self.users = Mock(spec=UserService)
        self.users.enforce.return_value = True
        self.access = DatasetAccessService(
            permission_repository=self.permissions, user_service=self.users
        )
        self.user_id = uuid4()

    def _grant(self, level: str):
        self.permissions.fetch.return_value = DatasetPermissionDBModel(
            dataset_id=uuid4(), user_id=self.user_id, level=level
        )

    def test_the_owner_is_owner_whatever_the_embargo(self):
        dataset = _dataset(owner_id=self.user_id, until=NOW + timedelta(days=5))
        self.assertEqual(
            self.access.level_of(self.user_id, dataset, [], NOW), AccessLevel.OWNER
        )

    def test_a_permission_counts_without_the_tenancy(self):
        self._grant("read")
        dataset = _dataset(until=NOW + timedelta(days=5))
        self.assertEqual(
            self.access.level_of(self.user_id, dataset, [], NOW), AccessLevel.READ
        )

    def test_a_tenancy_member_sees_a_dataset_without_embargo(self):
        dataset = _dataset()
        self.assertEqual(
            self.access.level_of(self.user_id, dataset, [TENANCY], NOW),
            AccessLevel.TENANCY,
        )

    def test_a_tenancy_member_does_not_see_a_hidden_embargo(self):
        dataset = _dataset(until=NOW + timedelta(days=5), visible=False)
        self.assertIsNone(self.access.level_of(self.user_id, dataset, [TENANCY], NOW))

    def test_a_tenancy_member_sees_an_open_embargo_but_not_its_files(self):
        dataset = _dataset(until=NOW + timedelta(days=5), visible=True)
        self.assertTrue(
            self.access.permits(
                self.user_id, dataset, [TENANCY], DatasetAction.READ_METADATA, NOW
            )
        )
        self.assertFalse(
            self.access.permits(
                self.user_id, dataset, [TENANCY], DatasetAction.READ_FILES, NOW
            )
        )
        self.assertFalse(
            self.access.permits(self.user_id, dataset, [TENANCY], DatasetAction.WRITE, NOW)
        )

    def test_an_expired_embargo_gives_the_tenancy_back_its_access(self):
        dataset = _dataset(until=NOW - timedelta(seconds=1))
        self.assertTrue(
            self.access.permits(
                self.user_id, dataset, [TENANCY], DatasetAction.READ_FILES, NOW
            )
        )

    def test_tenancy_writes_still_follow_the_role(self):
        dataset = _dataset()
        self.users.enforce.side_effect = lambda user_id, resource, action: (
            action == "GET"
        )
        self.assertTrue(
            self.access.permits(
                self.user_id, dataset, [TENANCY], DatasetAction.READ_FILES, NOW
            )
        )
        self.assertFalse(
            self.access.permits(self.user_id, dataset, [TENANCY], DatasetAction.WRITE, NOW)
        )
        self.users.enforce.assert_any_call(
            user_id=self.user_id,
            resource="/api/v1/datasets/tenancy-scope",
            action="PUT",
        )

    def test_a_read_permission_cannot_write(self):
        self._grant("read")
        dataset = _dataset(until=NOW + timedelta(days=5))
        self.assertTrue(
            self.access.permits(self.user_id, dataset, [], DatasetAction.READ_FILES, NOW)
        )
        self.assertFalse(
            self.access.permits(self.user_id, dataset, [], DatasetAction.WRITE, NOW)
        )

    def test_a_write_permission_can_write_but_not_delete(self):
        self._grant("write")
        dataset = _dataset(until=NOW + timedelta(days=5))
        self.assertTrue(
            self.access.permits(self.user_id, dataset, [], DatasetAction.WRITE, NOW)
        )
        self.assertFalse(
            self.access.permits(self.user_id, dataset, [], DatasetAction.DELETE, NOW)
        )

    def test_only_the_owner_manages_the_embargo(self):
        self._grant("write")
        dataset = _dataset(owner_id=uuid4(), until=NOW + timedelta(days=5))
        self.assertFalse(
            self.access.permits(
                self.user_id, dataset, [], DatasetAction.MANAGE_EMBARGO, NOW
            )
        )

    def test_a_permission_holder_extends_only_when_the_owner_is_disabled(self):
        self._grant("read")
        dataset = _dataset(owner_id=uuid4(), until=NOW + timedelta(days=5))
        self.assertFalse(
            self.access.permits(
                self.user_id, dataset, [], DatasetAction.EXTEND_EMBARGO, NOW
            )
        )
        self.users.fetch_by_id.side_effect = NotFoundException("disabled")
        self.assertTrue(
            self.access.permits(
                self.user_id, dataset, [], DatasetAction.EXTEND_EMBARGO, NOW
            )
        )

    def test_require_hides_what_the_caller_cannot_see(self):
        dataset = _dataset(until=NOW + timedelta(days=5), visible=False)
        with self.assertRaises(NotFoundException):
            self.access.require(
                self.user_id, dataset, [TENANCY], DatasetAction.WRITE, NOW
            )

    def test_require_forbids_what_the_caller_can_see_but_not_do(self):
        dataset = _dataset(until=NOW + timedelta(days=5), visible=True)
        with self.assertRaises(ForbiddenException):
            self.access.require(
                self.user_id, dataset, [TENANCY], DatasetAction.WRITE, NOW
            )

    def test_flags_for_the_owner(self):
        dataset = _dataset(owner_id=self.user_id, until=NOW + timedelta(days=5))
        flags = self.access.access_flags(
            self.user_id, dataset, [], AccessLevel.OWNER, NOW
        )
        self.assertEqual(flags.level, AccessLevel.OWNER)
        self.assertTrue(flags.can_edit)
        self.assertTrue(flags.can_share)
        self.assertTrue(flags.can_manage_embargo)
        self.assertTrue(flags.can_extend_embargo)
        self.assertTrue(flags.can_delete)

    def test_nobody_can_extend_an_embargo_that_is_not_active(self):
        dataset = _dataset(owner_id=self.user_id)
        flags = self.access.access_flags(
            self.user_id, dataset, [], AccessLevel.OWNER, NOW
        )
        self.assertFalse(flags.can_extend_embargo)

    def test_embargo_of_a_dataset_without_one_is_none(self):
        self.assertIsNone(self.access.embargo_of(_dataset(), NOW))

    def test_embargo_of_reports_the_state(self):
        until = NOW + timedelta(days=5)
        embargo = self.access.embargo_of(_dataset(until=until, visible=True), NOW)
        self.assertEqual(embargo.until, until)
        self.assertTrue(embargo.active)
        self.assertTrue(embargo.metadata_visible)

    def test_a_dataset_with_no_owner_counts_as_owner_disabled(self):
        self.assertTrue(self.access.owner_disabled(_dataset(owner_id=None)))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest app/service/dataset_access_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.service.dataset_access'`

- [ ] **Step 3: Implement** — `app/service/dataset_access.py`

```python
from datetime import datetime
from uuid import UUID

from app.exception.forbidden import ForbiddenException
from app.exception.not_found import NotFoundException
from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.embargo import (
    AccessLevel,
    DatasetAccess,
    DatasetAction,
    Embargo,
    embargo_active,
    utcnow,
)
from app.repository.permission import PermissionRepository
from app.service.user import UserService

# Matched by the tenancy roles' policies and not by datasets_shared's, which name concrete ids.
TENANCY_ROLE_RESOURCE = "/api/v1/datasets/tenancy-scope"

_ROLE_METHOD = {
    DatasetAction.READ_METADATA: "GET",
    DatasetAction.READ_FILES: "GET",
    DatasetAction.WRITE: "PUT",
    DatasetAction.DELETE: "DELETE",
}

_PERMISSION_ACTIONS = {
    AccessLevel.WRITE: frozenset(
        {DatasetAction.READ_METADATA, DatasetAction.READ_FILES, DatasetAction.WRITE}
    ),
    AccessLevel.READ: frozenset(
        {DatasetAction.READ_METADATA, DatasetAction.READ_FILES}
    ),
}


class DatasetAccessService:
    def __init__(
        self, permission_repository: PermissionRepository, user_service: UserService
    ) -> None:
        self._permissions = permission_repository
        self._user_service = user_service

    def embargo_active(
        self, dataset: DatasetDBModel, now: datetime | None = None
    ) -> bool:
        return embargo_active(dataset.embargo_until, now or utcnow())

    def embargo_of(
        self, dataset: DatasetDBModel, now: datetime | None = None
    ) -> Embargo | None:
        if dataset.embargo_until is None:
            return None
        return Embargo(
            until=dataset.embargo_until,
            active=self.embargo_active(dataset, now),
            metadata_visible=bool(dataset.embargo_metadata_visible),
            note=dataset.embargo_note,
        )

    def level_of(
        self,
        user_id: UUID | None,
        dataset: DatasetDBModel,
        tenancies: list[str],
        now: datetime | None = None,
    ) -> AccessLevel | None:
        if user_id is not None and dataset.owner_id == user_id:
            return AccessLevel.OWNER
        if user_id is not None:
            permission = self._permissions.fetch(dataset_id=dataset.id, user_id=user_id)
            if permission is not None:
                return AccessLevel(permission.level)
        if dataset.tenancy in tenancies and (
            not self.embargo_active(dataset, now) or dataset.embargo_metadata_visible
        ):
            return AccessLevel.TENANCY
        return None

    def permits(
        self,
        user_id: UUID,
        dataset: DatasetDBModel,
        tenancies: list[str],
        action: DatasetAction,
        now: datetime | None = None,
    ) -> bool:
        now = now or utcnow()
        level = self.level_of(user_id, dataset, tenancies, now)
        return self._permits(user_id, dataset, tenancies, level, action, now)

    def require(
        self,
        user_id: UUID,
        dataset: DatasetDBModel,
        tenancies: list[str],
        action: DatasetAction,
        now: datetime | None = None,
    ) -> AccessLevel:
        now = now or utcnow()
        level = self.level_of(user_id, dataset, tenancies, now)
        if level is None:
            raise NotFoundException(f"not_found: {dataset.id}")
        if not self._permits(user_id, dataset, tenancies, level, action, now):
            raise ForbiddenException(
                f"forbidden: {action.value} on {dataset.id} for {user_id}"
            )
        return level

    def access_flags(
        self,
        user_id: UUID,
        dataset: DatasetDBModel,
        tenancies: list[str],
        level: AccessLevel,
        now: datetime | None = None,
    ) -> DatasetAccess:
        now = now or utcnow()

        def can(action: DatasetAction) -> bool:
            return self._permits(user_id, dataset, tenancies, level, action, now)

        can_edit = can(DatasetAction.WRITE)
        return DatasetAccess(
            level=level,
            can_edit=can_edit,
            can_share=can_edit,
            can_manage_embargo=level == AccessLevel.OWNER,
            can_extend_embargo=self.embargo_active(dataset, now)
            and can(DatasetAction.EXTEND_EMBARGO),
            can_delete=can(DatasetAction.DELETE),
        )

    def owner_disabled(self, dataset: DatasetDBModel) -> bool:
        if dataset.owner_id is None:
            return True
        try:
            self._user_service.fetch_by_id(id=dataset.owner_id)
        except NotFoundException:
            return True
        return False

    def _permits(
        self,
        user_id: UUID,
        dataset: DatasetDBModel,
        tenancies: list[str],
        level: AccessLevel | None,
        action: DatasetAction,
        now: datetime,
    ) -> bool:
        if level is None:
            return False
        if level == AccessLevel.OWNER:
            return True
        if action == DatasetAction.MANAGE_EMBARGO:
            return False
        active = self.embargo_active(dataset, now)
        if action == DatasetAction.EXTEND_EMBARGO:
            return (
                active
                and level in _PERMISSION_ACTIONS
                and self.owner_disabled(dataset)
            )
        if action in _PERMISSION_ACTIONS.get(level, frozenset()):
            return True
        if dataset.tenancy not in tenancies:
            return False
        if active:
            return (
                action == DatasetAction.READ_METADATA
                and bool(dataset.embargo_metadata_visible)
                and self._role_allows(user_id, "GET")
            )
        return self._role_allows(user_id, _ROLE_METHOD[action])

    def _role_allows(self, user_id: UUID, method: str) -> bool:
        return self._user_service.enforce(
            user_id=user_id, resource=TENANCY_ROLE_RESOURCE, action=method
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest app/service/dataset_access_test.py -v`
Expected: PASS (18 tests)

- [ ] **Step 5: Commit**

```bash
git add app/service/dataset_access.py app/service/dataset_access_test.py
git commit -m "feat: one access rule for datasets, embargo and permissions included"
```

---

### Task 5: Audit trail, its metric, and the one way an embargo ends early — `EmbargoAudit`, `EmbargoTermination`

**Files:**
- Create: `app/service/embargo_audit.py`, `app/service/embargo_audit_test.py`, `app/service/embargo_termination.py`, `app/service/embargo_termination_test.py`
- Modify: `app/metrics.py` (declarations in `Metrics.__init__`, method next to `snapshot_published`), `app/metrics_test.py`

**Interfaces:**
- Consumes: `EmbargoEventRepository.append` (Task 2), `EmbargoEventType` (Task 1), `DatasetRepository.upsert` (existing).
- Produces:
  - `Metrics.embargo_event(event: str) -> None`
  - `EmbargoAudit.record(dataset_id: UUID, event_type: EmbargoEventType, changed_by: UUID | None, old_value: dict | None = None, new_value: dict | None = None, note: str | None = None) -> None` (plan 03 records invitation and review-link events through it)
  - `embargo_state(dataset) -> dict` — `{"until": iso | None, "metadata_visible": bool}`, the audit payload shape
  - `EmbargoTermination.end(dataset, ended_by: UUID | None, now: datetime, note: str | None = None) -> None` — sets `embargo_until = now`, upserts, records `ended_early` with `note`. `EmbargoService.end` (Task 10) and the manual-DOI path (Task 7) both end embargoes only through it. It sends nothing: plan 03's dispatch pass announces every embargo whose date has passed.

- [ ] **Step 1: Write the failing tests**

Append to `app/metrics_test.py`:

```python
class TestEmbargoEvents(MetricsTestCase):
    def test_each_event_is_counted_by_its_type(self):
        self.metrics.embargo_event("created")
        self.metrics.embargo_event("created")
        self.metrics.embargo_event("extended")

        self.assertEqual(
            self.value("datamap_embargo_events_total", event="created"), 2.0
        )
        self.assertEqual(
            self.value("datamap_embargo_events_total", event="extended"), 1.0
        )
```

`app/service/embargo_audit_test.py`:

```python
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from app.model.embargo import EmbargoEventType
from app.repository.embargo_event import EmbargoEventRepository
from app.service.embargo_audit import EmbargoAudit


class TestEmbargoAudit(unittest.TestCase):
    def test_an_event_is_appended_and_counted(self):
        events = Mock(spec=EmbargoEventRepository)
        audit = EmbargoAudit(event_repository=events)
        dataset_id, user_id = uuid4(), uuid4()

        with patch("app.service.embargo_audit.metrics") as metrics:
            audit.record(
                dataset_id=dataset_id,
                event_type=EmbargoEventType.EXTENDED,
                changed_by=user_id,
                old_value={"until": "a"},
                new_value={"until": "b"},
                note="review round 2",
            )

        events.append.assert_called_once_with(
            dataset_id=dataset_id,
            event_type="extended",
            changed_by=user_id,
            old_value={"until": "a"},
            new_value={"until": "b"},
            note="review round 2",
        )
        metrics.embargo_event.assert_called_once_with("extended")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest app/metrics_test.py::TestEmbargoEvents app/service/embargo_audit_test.py -v`
Expected: FAIL — `AttributeError: 'Metrics' object has no attribute 'embargo_event'` and `ModuleNotFoundError: No module named 'app.service.embargo_audit'`

- [ ] **Step 3: Implement**

`app/metrics.py`, in `Metrics.__init__` after `self._snapshots = Counter(...)`:

```python
        self._embargo_events = Counter(
            "datamap_embargo_events_total",
            "Embargo decisions recorded in the audit trail",
            ["event"],
            registry=self.registry,
        )
```

and after `def snapshot_published(...)`:

```python
    def embargo_event(self, event: str) -> None:
        self._embargo_events.labels(event=event).inc()
```

`app/service/embargo_audit.py`:

```python
from uuid import UUID

from app.metrics import metrics
from app.model.embargo import EmbargoEventType
from app.repository.embargo_event import EmbargoEventRepository


class EmbargoAudit:
    def __init__(self, event_repository: EmbargoEventRepository) -> None:
        self._events = event_repository

    def record(
        self,
        dataset_id: UUID,
        event_type: EmbargoEventType,
        changed_by: UUID | None,
        old_value: dict | None = None,
        new_value: dict | None = None,
        note: str | None = None,
    ) -> None:
        self._events.append(
            dataset_id=dataset_id,
            event_type=event_type.value,
            changed_by=changed_by,
            old_value=old_value,
            new_value=new_value,
            note=note,
        )
        metrics.embargo_event(event_type.value)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest app/metrics_test.py app/service/embargo_audit_test.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing test for the termination seam** — `app/service/embargo_termination_test.py`

```python
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.embargo import EmbargoEventType
from app.repository.dataset import DatasetRepository
from app.service.embargo_audit import EmbargoAudit
from app.service.embargo_termination import EmbargoTermination

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class TestEmbargoTermination(unittest.TestCase):
    def test_ending_moves_the_date_to_now_and_records_it(self):
        repository = Mock(spec=DatasetRepository)
        audit = Mock(spec=EmbargoAudit)
        termination = EmbargoTermination(repository=repository, audit=audit)
        user_id = uuid4()
        dataset = DatasetDBModel(
            id=uuid4(),
            name="d",
            embargo_until=NOW + timedelta(days=3),
            embargo_metadata_visible=True,
        )

        termination.end(dataset=dataset, ended_by=user_id, now=NOW, note="manual DOI")

        self.assertEqual(dataset.embargo_until, NOW)
        repository.upsert.assert_called_once_with(dataset=dataset)
        audit.record.assert_called_once_with(
            dataset_id=dataset.id,
            event_type=EmbargoEventType.ENDED_EARLY,
            changed_by=user_id,
            old_value={
                "until": (NOW + timedelta(days=3)).isoformat(),
                "metadata_visible": True,
            },
            new_value={"until": NOW.isoformat(), "metadata_visible": True},
            note="manual DOI",
        )
```

- [ ] **Step 6: Run it to verify it fails**

Run: `pytest app/service/embargo_termination_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.service.embargo_termination'`

- [ ] **Step 7: Implement** — `app/service/embargo_termination.py`

```python
from datetime import datetime
from uuid import UUID

from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.embargo import EmbargoEventType
from app.repository.dataset import DatasetRepository
from app.service.embargo_audit import EmbargoAudit


def embargo_state(dataset: DatasetDBModel) -> dict:
    return {
        "until": dataset.embargo_until.isoformat() if dataset.embargo_until else None,
        "metadata_visible": bool(dataset.embargo_metadata_visible),
    }


class EmbargoTermination:
    def __init__(self, repository: DatasetRepository, audit: EmbargoAudit) -> None:
        self._repository = repository
        self._audit = audit

    def end(
        self,
        dataset: DatasetDBModel,
        ended_by: UUID | None,
        now: datetime,
        note: str | None = None,
    ) -> None:
        before = embargo_state(dataset)
        dataset.embargo_until = now
        self._repository.upsert(dataset=dataset)
        self._audit.record(
            dataset_id=dataset.id,
            event_type=EmbargoEventType.ENDED_EARLY,
            changed_by=ended_by,
            old_value=before,
            new_value=embargo_state(dataset),
            note=note,
        )
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `pytest app/service/embargo_termination_test.py app/service/embargo_audit_test.py app/metrics_test.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add app/metrics.py app/metrics_test.py app/service/embargo_audit.py app/service/embargo_audit_test.py app/service/embargo_termination.py app/service/embargo_termination_test.py
git commit -m "feat: record every embargo decision, and end an embargo through one seam"
```

---

### Task 6: Authorize every dataset route through the access rule

**Files:**
- Modify: `app/service/dataset.py` (constructor `:47-66`; every public method listed below; `_publish_dataset_snapshot` `:1013-1090`), `app/service/dataset_test.py`, `app/controller/v1/dataset/dataset.py:283-333`, `app/service/tus.py`, `app/container.py`
- Create: `app/service/tus_test.py`

**Interfaces:**
- Consumes: `DatasetAccessService` (Task 4), `ForbiddenException` (Task 3), `DatasetAction`, `AccessLevel` (Task 1).
- Produces:
  - `DatasetService.__init__(..., tenancy_service, access_service: DatasetAccessService, embargo_termination: EmbargoTermination, dataset_bucket: str)` — `access_service` and `embargo_termination` are new keyword arguments before `dataset_bucket` (Task 7 uses the second).
  - Container provider `embargo_termination`.
  - `DatasetService.fetch_authorized(dataset_id: UUID, user_id: UUID, tenancies: list[str] | None, action: DatasetAction, is_enabled: bool = True, latest_version: bool = False, version_design_state: DesignState = None, version_is_enabled: bool = True) -> tuple[DatasetDBModel, list[str], AccessLevel]` — public; `EmbargoService` (Task 10) and plan 03 use it.
  - `DatasetService.disable_dataset(dataset_id: UUID, user_id: UUID, tenancies: list[str] = None)` and `enable_dataset(dataset_id: UUID, user_id: UUID, tenancies: list[str] = None)` gain `user_id`.
  - `DatasetService._publish_dataset_snapshot(dataset_id: UUID, version_name: str, doi_state: str = None)` loses `user_id` and `tenancies` (callers have authorized already).

Method-by-method (every public method of `DatasetService`):

| Method | Action | Change |
|---|---|---|
| `fetch_dataset` | `READ_METADATA` | returns `None` on `NotFoundException` from `fetch_authorized` (controller already answers 404 on `None`) |
| `update_dataset` | `WRITE` | **stops setting `owner_id`**; sets `tenancy` only when the request carries one and the level is `OWNER` or `TENANCY` |
| `create_dataset` | — | unchanged (Casbin role + tenancy, as today) |
| `disable_dataset` | `DELETE` | gains `user_id`; was unscoped by user |
| `enable_dataset` | `DELETE` | gains `user_id`; fetch with `is_enabled=False` |
| `enable_dataset_version` | `WRITE` | fetch with `version_is_enabled=False` |
| `disable_dataset_version` | `DELETE` | — |
| `fetch_available_filters` | — | unchanged |
| `search_datasets` | — | Task 8 |
| `create_data_file` | `WRITE` | TUS uploads are refused when not allowed |
| `publish_dataset_version` | `WRITE` | — |
| `create_doi` | `WRITE` | Task 7 adds the embargo skip |
| `change_doi_state` | `WRITE` | Task 7 adds `embargo_active` |
| `get_doi` | `READ_METADATA` | — |
| `delete_doi` | `WRITE` | — |
| `get_file_download_url` | `READ_FILES` | Task 7 adds the TTL |
| `create_new_version` | `WRITE` | fetch with `version_is_enabled=False` |
| `fetch_dataset_version` | `READ_METADATA` | Task 7 withholds files |
| `get_dataset_latest_snapshot`, `get_dataset_version_snapshot` | — | unchanged, public |

- [ ] **Step 1: Write the failing tests** — add to `app/service/dataset_test.py`

Add imports at the top:

```python
from app.exception.forbidden import ForbiddenException
from app.model.embargo import AccessLevel, DatasetAccess, DatasetAction
from app.service.dataset_access import DatasetAccessService
from app.service.embargo_termination import EmbargoTermination
```

Replace `setUp` with:

```python
    def setUp(self):
        self.dataset_repository = Mock(spec=DatasetRepository)
        self.dataset_version_repository = Mock(spec=DatasetVersionRepository)
        self.data_file_repository = Mock(spec=DataFileRepository)
        self.user_service = Mock(spec=UserService)
        self.doi_service = Mock(spec=DOIService)
        self.minio_gateway = Mock(spec=ObjectStorageGateway)
        self.tenancy_service = Mock(spec=TenancyService)
        self.dataset_access = Mock(spec=DatasetAccessService)
        self.dataset_access.require.return_value = AccessLevel.TENANCY
        self.dataset_access.level_of.return_value = AccessLevel.TENANCY
        self.dataset_access.permits.return_value = True
        self.dataset_access.embargo_active.return_value = False
        self.dataset_access.embargo_of.return_value = None
        self.dataset_access.access_flags.return_value = DatasetAccess(
            level=AccessLevel.TENANCY,
            can_edit=True,
            can_share=True,
            can_manage_embargo=False,
            can_extend_embargo=False,
            can_delete=True,
        )
        self.embargo_termination = Mock(spec=EmbargoTermination)
        self.dataset_service = DatasetService(
            repository=self.dataset_repository,
            version_repository=self.dataset_version_repository,
            data_file_repository=self.data_file_repository,
            user_service=self.user_service,
            doi_service=self.doi_service,
            minio_gateway=self.minio_gateway,
            tenancy_service=self.tenancy_service,
            access_service=self.dataset_access,
            embargo_termination=self.embargo_termination,
            dataset_bucket="dataset_bucket",
        )
```

Add this test class at the end of the file:

```python
class TestDatasetServiceAuthorization(TestDatasetService):
    def _fetched(self, **overrides):
        dataset = Mock(spec=DatasetDBModel)
        dataset.id = uuid4()
        dataset.versions = []
        for key, value in overrides.items():
            setattr(dataset, key, value)
        self.dataset_repository.fetch.return_value = dataset
        self.user_service.fetch_by_id.return_value = self.mock_user([])
        return dataset

    def test_fetch_authorized_looks_the_dataset_up_by_id_and_asks_the_rule(self):
        dataset = self._fetched()
        user_id = uuid4()

        found, tenancies, level = self.dataset_service.fetch_authorized(
            dataset_id=dataset.id,
            user_id=user_id,
            tenancies=None,
            action=DatasetAction.WRITE,
        )

        self.assertIs(found, dataset)
        self.assertEqual(tenancies, [])
        self.assertEqual(level, AccessLevel.TENANCY)
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset.id,
            is_enabled=True,
            tenancies=[],
            latest_version=False,
            version_design_state=None,
            version_is_enabled=True,
            restrict_by_tenancy=False,
        )
        self.dataset_access.require.assert_called_once_with(
            user_id=user_id, dataset=dataset, tenancies=[], action=DatasetAction.WRITE
        )

    def test_fetch_authorized_hides_a_missing_dataset(self):
        self.user_service.fetch_by_id.return_value = self.mock_user([])
        self.dataset_repository.fetch.return_value = None

        with self.assertRaises(NotFoundException):
            self.dataset_service.fetch_authorized(
                dataset_id=uuid4(),
                user_id=uuid4(),
                tenancies=None,
                action=DatasetAction.READ_METADATA,
            )

    def test_fetch_dataset_answers_none_to_a_caller_who_cannot_see_it(self):
        self._fetched()
        self.dataset_access.require.side_effect = NotFoundException("hidden")

        self.assertIsNone(
            self.dataset_service.fetch_dataset(dataset_id=uuid4(), user_id=uuid4())
        )

    def test_update_does_not_change_the_owner(self):
        owner = uuid4()
        dataset = self._fetched(owner_id=owner, tenancy="t1", data={})
        self.dataset_service._should_create_new_version = Mock(return_value=False)

        self.dataset_service.update_dataset(
            dataset_id=dataset.id,
            dataset_request=Dataset(id=dataset.id, name="n", data={}, tenancy="t1"),
            user_id=uuid4(),
        )

        self.assertEqual(dataset.owner_id, owner)

    def test_a_permission_holder_cannot_move_the_dataset_to_another_tenancy(self):
        self.dataset_access.require.return_value = AccessLevel.WRITE
        dataset = self._fetched(owner_id=uuid4(), tenancy="t1", data={})
        self.dataset_service._should_create_new_version = Mock(return_value=False)

        self.dataset_service.update_dataset(
            dataset_id=dataset.id,
            dataset_request=Dataset(id=dataset.id, name="n", data={}, tenancy="t2"),
            user_id=uuid4(),
        )

        self.assertEqual(dataset.tenancy, "t1")

    def test_writes_are_refused_when_the_rule_forbids_them(self):
        self._fetched()
        self.dataset_access.require.side_effect = ForbiddenException("no")

        with self.assertRaises(ForbiddenException):
            self.dataset_service.publish_dataset_version(
                dataset_id=uuid4(), user_id=uuid4(), version_name="1"
            )

    def test_deleting_asks_for_the_delete_action(self):
        self._fetched()
        user_id = uuid4()

        self.dataset_service.disable_dataset(dataset_id=uuid4(), user_id=user_id)

        self.assertEqual(
            self.dataset_access.require.call_args.kwargs["action"],
            DatasetAction.DELETE,
        )
```

Add `app/service/tus_test.py`:

```python
import unittest
from unittest.mock import Mock
from uuid import uuid4

from app.exception.forbidden import ForbiddenException
from app.service.dataset import DatasetService
from app.service.tus import TusService


def _payload(dataset_id) -> dict:
    return {
        "Type": "post-finish",
        "Event": {
            "Upload": {
                "Size": 10,
                "MetaData": {
                    "dataset_id": str(dataset_id),
                    "filename": "a.nc",
                    "filetype": "application/x-netcdf",
                },
                "Storage": {"Bucket": "datamap", "Key": "staged/abc"},
            }
        },
    }


class TestTusService(unittest.TestCase):
    def test_an_upload_the_access_rule_forbids_is_rejected(self):
        datasets = Mock(spec=DatasetService)
        datasets.create_data_file.side_effect = ForbiddenException("no")

        result = TusService(dataset_service=datasets).handle(
            payload=_payload(uuid4()), user_id=uuid4()
        )

        self.assertEqual(result.status_code, 403)
        self.assertTrue(result.reject_upload)
        self.assertEqual(result.body_msg, "upload_not_allowed")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest app/service/dataset_test.py::TestDatasetServiceAuthorization app/service/tus_test.py -v`
Expected: FAIL — `TypeError: DatasetService.__init__() got an unexpected keyword argument 'access_service'`, and the TUS test returns `500` instead of `403`.

- [ ] **Step 3: Implement in `app/service/dataset.py`**

Imports, after the existing ones:

```python
from app.exception.forbidden import ForbiddenException
from app.model.embargo import AccessLevel, DatasetAction, utcnow
from app.service.dataset_access import DatasetAccessService
from app.service.embargo_termination import EmbargoTermination
```

Constructor: add the parameters `access_service: DatasetAccessService,` and `embargo_termination: EmbargoTermination,` between `tenancy_service` and `dataset_bucket`, and `self._access = access_service` and `self._embargo_termination = embargo_termination` in the body.

Add, right after `_determine_tenancies`:

```python
    def fetch_authorized(
        self,
        dataset_id: UUID,
        user_id: UUID,
        tenancies: list[str] | None,
        action: DatasetAction,
        is_enabled: bool = True,
        latest_version: bool = False,
        version_design_state: DesignState = None,
        version_is_enabled: bool = True,
    ) -> tuple[DatasetDBModel, list[str], AccessLevel]:
        allowed = self._determine_tenancies(user_id=user_id, tenancies=tenancies or [])
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id,
            is_enabled=is_enabled,
            tenancies=allowed,
            latest_version=latest_version,
            version_design_state=version_design_state,
            version_is_enabled=version_is_enabled,
            restrict_by_tenancy=False,
        )
        if dataset is None:
            raise NotFoundException(f"not_found: {dataset_id}")
        level = self._access.require(
            user_id=user_id, dataset=dataset, tenancies=allowed, action=action
        )
        return dataset, allowed, level
```

Replace each method's opening lookup (`if tenancies is None: ...`, `self._repository.fetch(...)`, `if dataset is None: raise NotFoundException(...)`) with one call to `fetch_authorized`. Full new bodies:

```python
    def fetch_dataset(
        self,
        dataset_id: UUID,
        is_enabled: bool = True,
        user_id: UUID = None,
        tenancies: list[str] = None,
        latest_version: bool = False,
        version_design_state: DesignState = None,
        version_is_enabled: bool = True,
    ) -> Dataset | None:
        try:
            dataset, allowed, level = self.fetch_authorized(
                dataset_id=dataset_id,
                user_id=user_id,
                tenancies=tenancies,
                action=DatasetAction.READ_METADATA,
                is_enabled=is_enabled,
                latest_version=latest_version,
                version_design_state=version_design_state,
                version_is_enabled=version_is_enabled,
            )
        except NotFoundException:
            return None

        return self._view(
            self._adapt_dataset(dataset=dataset), dataset, user_id, allowed, level
        )

    def update_dataset(
        self,
        dataset_id: UUID,
        dataset_request: Dataset,
        user_id: UUID,
        tenancies: list[str] = None,
    ) -> None:
        dataset_db, _, level = self.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.WRITE,
        )

        dataset_db.name = dataset_request.name
        dataset_db.data = dataset_request.data
        if dataset_request.tenancy and level in (AccessLevel.OWNER, AccessLevel.TENANCY):
            dataset_db.tenancy = dataset_request.tenancy

        # (the rest of the method — new version or DOI metadata update, upsert, metric — is unchanged)
```

Keep the remainder of `update_dataset` from `if self._should_create_new_version(...)` to `metrics.dataset_event("updated")` exactly as it is, and delete the line `dataset_db.owner_id = user_id`. Do not keep the parenthesised line above; it marks where the unchanged code continues.

```python
    def disable_dataset(
        self, dataset_id: UUID, user_id: UUID, tenancies: list[str] = None
    ) -> None:
        dataset, _, _ = self.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.DELETE,
        )
        dataset.is_enabled = False
        self._repository.upsert(dataset=dataset)
        metrics.dataset_event("deleted")

    def enable_dataset(
        self, dataset_id: UUID, user_id: UUID, tenancies: list[str] = None
    ) -> None:
        dataset, _, _ = self.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.DELETE,
            is_enabled=False,
        )
        dataset.is_enabled = True
        self._repository.upsert(dataset=dataset)
        metrics.dataset_event("enabled")
```

For `enable_dataset_version`, `disable_dataset_version`, `publish_dataset_version`, `create_doi`, `change_doi_state`, `get_doi`, `delete_doi`, `create_new_version`, replace the opening lookup with (actions and `version_is_enabled` per the table above):

```python
        dataset, _, _ = self.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.WRITE,
        )
```

— with `action=DatasetAction.DELETE` in `disable_dataset_version`, `action=DatasetAction.READ_METADATA` in `get_doi`, and `version_is_enabled=False` added in `enable_dataset_version` and `create_new_version`. The rest of each method is unchanged.

`create_data_file`:

```python
    def create_data_file(self, file: DataFile, dataset_id: UUID, user_id: UUID) -> None:
        dataset_db, _, _ = self.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=None,
            action=DatasetAction.WRITE,
        )

        # (unchanged from `version: DatasetVersionDBModel = self._version_repository.fetch_draft_version(` to the end)
```

`get_file_download_url` opening lookup:

```python
        dataset, _, _ = self.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.READ_FILES,
        )
```

`fetch_dataset_version` opening lookup:

```python
        dataset, allowed, level = self.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.READ_METADATA,
        )
```

and its return becomes:

```python
        return self._view(
            self._adapt_dataset_version(dataset=dataset, dataset_version=version),
            dataset,
            user_id,
            allowed,
            level,
        )
```

`_publish_dataset_snapshot`: change the signature to `(self, dataset_id: UUID, version_name: str, doi_state: str = None)` and its lookup to:

```python
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id, restrict_by_tenancy=False
        )
```

Update its two callers (`create_doi`, `change_doi_state`) to pass only `dataset_id`, `version_name` and (in `change_doi_state`) `doi_state`.

Add the view helper next to the other adapters (Task 7 fills in the embargo parts; here it carries the access flags):

```python
    def _view(
        self,
        adapted: Dataset,
        dataset_db: DatasetDBModel,
        user_id: UUID,
        tenancies: list[str],
        level: AccessLevel,
    ) -> Dataset:
        now = utcnow()
        adapted.owner_id = dataset_db.owner_id
        adapted.embargo = self._access.embargo_of(dataset_db, now)
        adapted.access = self._access.access_flags(
            user_id=user_id,
            dataset=dataset_db,
            tenancies=tenancies,
            level=level,
            now=now,
        )
        return adapted
```

`create_dataset`: return `self._view(self._adapt_dataset(dataset=created), created, user_id, [created.tenancy], AccessLevel.OWNER)` instead of the bare adapter.

`app/service/tus.py` — in `handle_post_finish`, wrap the `create_data_file` call:

```python
            try:
                self._dataset_service.create_data_file(
                    file=file, dataset_id=dataset_id, user_id=user_id
                )
            except ForbiddenException:
                self._logger.warning(
                    "upload refused", extra=fields(dataset_id=str(dataset_id))
                )
                return TusResult(
                    status_code=403, body_msg="upload_not_allowed", reject_upload=True
                )
```

with `from app.exception.forbidden import ForbiddenException` at the top. A `NotFoundException` keeps today's path (500 with `reject_upload`), which `tests/integration/test_tus_api.py::test_post_finish_hook_invalid_dataset_id_500` pins.

`app/controller/v1/dataset/dataset.py` — `delete_dataset` and `enable_dataset` take the user:

```python
# DELETE /datasets/{id}
@router.delete("/{id}")
@inject
def delete_dataset(
    id: str,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> None:
    service.disable_dataset(dataset_id=id, user_id=user_id, tenancies=tenancies)
    return {}
```

```python
# PUT /datasets/:dataset_id/enable
@router.put("/{id}/enable")
@inject
def enable_dataset(
    id: str,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: DatasetService = Depends(Provide[Container.dataset_service]),
) -> None:
    service.enable_dataset(dataset_id=id, user_id=user_id, tenancies=tenancies)
    return {}
```

`app/container.py` — imports and providers (place `permission_repository` with the other repositories, `dataset_access_service` before `dataset_service`):

```python
from app.repository.embargo_event import EmbargoEventRepository
from app.repository.permission import PermissionRepository
from app.service.dataset_access import DatasetAccessService
from app.service.embargo_audit import EmbargoAudit
from app.service.embargo_termination import EmbargoTermination
```

```python
    permission_repository = providers.Factory(
        PermissionRepository,
        session_factory=db.provided.session,
    )

    dataset_access_service = providers.Factory(
        DatasetAccessService,
        permission_repository=permission_repository,
        user_service=user_service,
    )

    embargo_event_repository = providers.Factory(
        EmbargoEventRepository,
        session_factory=db.provided.session,
    )

    embargo_audit = providers.Factory(
        EmbargoAudit,
        event_repository=embargo_event_repository,
    )

    embargo_termination = providers.Factory(
        EmbargoTermination,
        repository=dataset_repository,
        audit=embargo_audit,
    )
```

(`embargo_termination` goes after `dataset_repository` is declared.) In `dataset_service = providers.Factory(DatasetService, ...)` add `access_service=dataset_access_service,` and `embargo_termination=embargo_termination,` before `dataset_bucket=`.

- [ ] **Step 4: Update the existing unit tests that pinned the old lookup**

Every `self.dataset_repository.fetch.assert_called_once_with(...)` in `app/service/dataset_test.py` must now expect the `fetch_authorized` call shape. Find them:

Run: `grep -n "dataset_repository.fetch.assert_called" app/service/dataset_test.py`

Replace each with the full form, filling in that test's own `dataset_id`, tenancies and flags:

```python
        self.dataset_repository.fetch.assert_called_once_with(
            dataset_id=dataset_id,
            is_enabled=True,
            tenancies=["tenancy1"],
            latest_version=False,
            version_design_state=None,
            version_is_enabled=True,
            restrict_by_tenancy=False,
        )
```

Then:
- `test_disable_dataset_not_found` / `test_enable_dataset_not_found`: call with `user_id=uuid4()` and set `self.user_service.fetch_by_id.return_value = self.mock_user([])`.
- Tests that call `_publish_dataset_snapshot(...)` directly (around lines 2250, 2294, 2317) or assert `mock_publish.assert_called_once_with(...)` (around 2355 and the patched blocks after it): drop `user_id=` and `tenancies=` from those calls and expectations; for direct calls, assert `self.dataset_repository.fetch.assert_called_once_with(dataset_id=dataset_id, restrict_by_tenancy=False)`.
- `test_update_dataset`: remove any assertion that `owner_id` equals the caller.

Run: `pytest app/service/dataset_test.py app/service/tus_test.py -v`
Expected: PASS (all, including the 7 new authorization tests and the TUS test)

- [ ] **Step 5: Run the whole unit suite**

Run: `pytest`
Expected: PASS. `app/controller/routes_security_test.py` still passes (no route lost its guard).

- [ ] **Step 6: Commit**

```bash
git add app/service/dataset.py app/service/dataset_test.py app/service/tus.py app/service/tus_test.py app/controller/v1/dataset/dataset.py app/container.py
git commit -m "feat: every dataset route asks the access rule; updating no longer changes the owner"
```

---

### Task 7: Embargo on the dataset views, snapshots, DOI and downloads

**Files:**
- Modify: `app/service/dataset.py` (`_view`, `create_doi`, `change_doi_state`, `_publish_dataset_snapshot`, `get_file_download_url`), `app/service/dataset_test.py`, `app/controller/v1/dataset/resource.py`, `app/controller/v1/dataset/dataset.py` (adapters `:50-163`)

**Interfaces:**
- Consumes: `fetch_authorized`, `_view` (Task 6); `DatasetAccessService.embargo_active/permits/embargo_of` (Task 4).
- Produces: response fields `embargo`, `access` on `DatasetGetResponse` and `DatasetVersionGetResponse`; `files_withheld`, `files_summary` on `DatasetVersionResponse` (contract shapes); `400 embargo_active` from `PUT .../doi` to `findable`; `DatasetService.create_doi(..., end_embargo: bool = False)` and `DOICreateRequest.end_embargo` — manual DOI under embargo answers `400 embargo_manual_doi_ends_embargo` without it, 403 for a non-owner with it, and for the owner ends the embargo through `EmbargoTermination.end(note="manual DOI")` and publishes the snapshot; `get_pre_signed_url(..., expires_in=timedelta(hours=1))` under embargo.
- Consumes also: `EmbargoTermination` (Task 5), injected in Task 6.

- [ ] **Step 1: Write the failing tests** — append to `TestDatasetServiceAuthorization` in `app/service/dataset_test.py` (add `from datetime import timedelta` to the imports)

```python
    def test_files_are_withheld_when_the_rule_says_so(self):
        dataset = self._fetched()
        version = Mock(spec=DatasetVersionDBModel)
        file = Mock(spec=DataFileDBModel)
        file.size_bytes = 7
        version.files = [file]
        version.files_in = [file]
        version.doi = None
        version.design_state = DesignState.DRAFT
        version.created_at = datetime.datetime(2026, 1, 1)
        dataset.versions = [version]
        self.dataset_access.permits.return_value = False

        result = self.dataset_service.fetch_dataset(
            dataset_id=dataset.id, user_id=uuid4()
        )

        self.assertEqual(result.versions[0].files_in, [])
        self.assertTrue(result.versions[0].files_withheld)
        self.assertEqual(result.versions[0].files_count, 1)
        self.assertEqual(result.versions[0].files_size_in_bytes, 7)

    def test_promoting_a_doi_to_findable_is_refused_under_embargo(self):
        dataset = self._fetched()
        self.dataset_access.embargo_active.return_value = True
        version = Mock(spec=DatasetVersionDBModel)
        version.doi = Mock()
        self.dataset_version_repository.fetch_version_by_name.return_value = version

        with self.assertRaises(BadRequestException) as raised:
            self.dataset_service.change_doi_state(
                dataset_id=dataset.id,
                version_name="1",
                new_state=DOIState.FINDABLE,
                user_id=uuid4(),
            )

        self.assertEqual(raised.exception.errors[0].code, "embargo_active")
        self.doi_service.change_state.assert_not_called()
        self.minio_gateway.put_file.assert_not_called()

    def test_registering_a_doi_is_allowed_under_embargo(self):
        dataset = self._fetched()
        self.dataset_access.embargo_active.return_value = True
        version = Mock(spec=DatasetVersionDBModel)
        version.doi = Mock()
        self.dataset_version_repository.fetch_version_by_name.return_value = version

        self.dataset_service.change_doi_state(
            dataset_id=dataset.id,
            version_name="1",
            new_state=DOIState.REGISTERED,
            user_id=uuid4(),
        )

        self.doi_service.change_state.assert_called_once()

    def _manual_doi(self, embargoed: bool, level: AccessLevel):
        dataset = self._fetched()
        self.dataset_access.embargo_active.return_value = embargoed
        self.dataset_access.require.return_value = level
        version = Mock(spec=DatasetVersionDBModel)
        version.doi = None
        self.dataset_version_repository.fetch_version_by_name.return_value = version
        self.dataset_service._create_doi_model = Mock(
            return_value=DOI(mode=DOIMode.MANUAL, identifier="10.1/x")
        )
        return dataset

    def _create_manual(self, dataset, end_embargo: bool, user_id=None):
        return self.dataset_service.create_doi(
            dataset_id=dataset.id,
            version_name="1",
            doi=DOI(mode=DOIMode.MANUAL, identifier="10.1/x"),
            user_id=user_id or uuid4(),
            end_embargo=end_embargo,
        )

    def test_a_manual_doi_under_embargo_needs_the_embargo_to_end(self):
        dataset = self._manual_doi(embargoed=True, level=AccessLevel.OWNER)

        with self.assertRaises(BadRequestException) as raised:
            self._create_manual(dataset, end_embargo=False)

        self.assertEqual(
            raised.exception.errors[0].code, "embargo_manual_doi_ends_embargo"
        )
        self.doi_service.create.assert_not_called()
        self.embargo_termination.end.assert_not_called()

    def test_only_the_owner_may_end_the_embargo_with_a_manual_doi(self):
        dataset = self._manual_doi(embargoed=True, level=AccessLevel.WRITE)

        with self.assertRaises(ForbiddenException):
            self._create_manual(dataset, end_embargo=True)

        self.doi_service.create.assert_not_called()
        self.embargo_termination.end.assert_not_called()

    def test_the_owner_ends_the_embargo_then_the_snapshot_is_published(self):
        dataset = self._manual_doi(embargoed=True, level=AccessLevel.OWNER)
        user_id = uuid4()
        order = []
        self.doi_service.create.side_effect = lambda doi: order.append("doi") or doi
        self.embargo_termination.end.side_effect = lambda **kwargs: order.append("end")

        with patch.object(
            self.dataset_service,
            "_publish_dataset_snapshot",
            side_effect=lambda **kwargs: order.append("snapshot"),
        ):
            self._create_manual(dataset, end_embargo=True, user_id=user_id)

        self.assertEqual(order, ["doi", "end", "snapshot"])
        kwargs = self.embargo_termination.end.call_args.kwargs
        self.assertIs(kwargs["dataset"], dataset)
        self.assertEqual(kwargs["ended_by"], user_id)
        self.assertEqual(kwargs["note"], "manual DOI")

    def test_a_manual_doi_without_embargo_is_unchanged(self):
        dataset = self._manual_doi(embargoed=False, level=AccessLevel.TENANCY)

        with patch.object(
            self.dataset_service, "_publish_dataset_snapshot"
        ) as publish:
            self._create_manual(dataset, end_embargo=False)

        self.doi_service.create.assert_called_once()
        publish.assert_called_once()
        self.embargo_termination.end.assert_not_called()

    def test_the_snapshot_writer_itself_refuses_an_embargoed_dataset(self):
        self._fetched()
        self.dataset_access.embargo_active.return_value = True

        with self.assertRaises(BadRequestException) as raised:
            self.dataset_service._publish_dataset_snapshot(
                dataset_id=uuid4(), version_name="1"
            )

        self.assertEqual(raised.exception.errors[0].code, "embargo_active")
        self.minio_gateway.put_file.assert_not_called()

    def test_a_download_link_under_embargo_lives_one_hour(self):
        dataset = self._fetched(tenancy="t1")
        self.dataset_access.embargo_active.return_value = True
        file = Mock(spec=DataFileDBModel)
        file.id = uuid4()
        file.name = "a.nc"
        file.storage_path = "datamap/a"
        file.extension = "nc"
        file.size_bytes = 1
        version = Mock(spec=DatasetVersionDBModel)
        version.files_in = [file]
        self.dataset_version_repository.fetch_version_by_name.return_value = version
        self.minio_gateway.get_pre_signed_url.return_value = "https://x"

        self.dataset_service.get_file_download_url(
            dataset_id=dataset.id, version_name="1", file_id=file.id, user_id=uuid4()
        )

        self.assertEqual(
            self.minio_gateway.get_pre_signed_url.call_args.kwargs["expires_in"],
            timedelta(hours=1),
        )
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest app/service/dataset_test.py::TestDatasetServiceAuthorization -v`
Expected: the new tests FAIL (files not withheld; no `embargo_active` error; `create_doi() got an unexpected keyword argument 'end_embargo'`; `KeyError: 'expires_in'`).

- [ ] **Step 3: Implement in `app/service/dataset.py`**

Add `from datetime import timedelta` to the imports, and module constants under `_mode_of`:

```python
EMBARGO_DOWNLOAD_TTL = timedelta(hours=1)
DEFAULT_DOWNLOAD_TTL = timedelta(days=7)
```

`_view` — append before `return adapted`:

```python
        if not self._access.permits(
            user_id=user_id,
            dataset=dataset_db,
            tenancies=tenancies,
            action=DatasetAction.READ_FILES,
            now=now,
        ):
            for version in (*adapted.versions, adapted.current_version, adapted.version):
                if version is not None:
                    version.files = []
                    version.files_in = []
                    version.files_withheld = True
```

`create_doi` — add the parameter `end_embargo: bool = False` after `tenancies`, take the level from the lookup (`dataset, _, level = self.fetch_authorized(...)`), and right after the `if version.doi: raise BadRequestException(...already_exists...)` check:

```python
        ends_embargo = doi.mode == DOIMode.MANUAL and self._access.embargo_active(
            dataset
        )
        if ends_embargo and not end_embargo:
            raise BadRequestException(
                errors=[ErrorDetails(code="embargo_manual_doi_ends_embargo")]
            )
        if ends_embargo and level != AccessLevel.OWNER:
            raise ForbiddenException(
                f"forbidden: only the owner ends the embargo of {dataset_id}"
            )
```

and replace the block `if doi.mode == DOIMode.MANUAL: self._publish_dataset_snapshot(...)` at the end with:

```python
        if ends_embargo:
            self._embargo_termination.end(
                dataset=dataset, ended_by=user_id, now=utcnow(), note="manual DOI"
            )

        if doi.mode == DOIMode.MANUAL:
            self._publish_dataset_snapshot(
                dataset_id=dataset_id, version_name=version_name
            )
```

The DOI is created before the embargo ends, so a failed registration leaves the embargo in place; the snapshot comes last, once `_publish_dataset_snapshot` re-reads a dataset whose embargo has ended.

`app/controller/v1/dataset/resource.py` — `DOICreateRequest` gains:

```python
    end_embargo: bool = Field(
        False, title="Confirm that a manual DOI ends the dataset's embargo"
    )
```

`app/controller/v1/dataset/dataset.py` — `create_doi` passes it: add `end_embargo=create_doi_request.end_embargo,` to the `service.create_doi(...)` call.

`change_doi_state` — before the `# Before the state change...` comment:

```python
        if new_state == DOIState.FINDABLE and self._access.embargo_active(dataset):
            raise BadRequestException(errors=[ErrorDetails(code="embargo_active")])
```

`_publish_dataset_snapshot` — after `if dataset is None: raise NotFoundException(...)`:

```python
        if self._access.embargo_active(dataset):
            raise BadRequestException(errors=[ErrorDetails(code="embargo_active")])
```

`get_file_download_url` — the gateway call becomes:

```python
        url = self._minio_gateway.get_pre_signed_url(
            bucket_name=self._dataset_bucket,
            object_name=file.storage_path[len(self._dataset_bucket) + 1 :]
            if file.storage_path.startswith(self._dataset_bucket + "/")
            else file.storage_path,
            original_file_name=file.name,
            expires_in=EMBARGO_DOWNLOAD_TTL
            if self._access.embargo_active(dataset)
            else DEFAULT_DOWNLOAD_TTL,
        )
```

- [ ] **Step 4: Response models** — `app/controller/v1/dataset/resource.py`, after `DOIResponse`:

```python
class VersionFilesSummaryResponse(BaseModel):
    count: int = Field(..., title="Number of files")
    total_size_bytes: int = Field(..., title="Total size of the files in bytes")


class EmbargoResponse(BaseModel):
    until: datetime = Field(..., title="Embargo end")
    active: bool = Field(..., title="Whether the embargo is in force now")
    metadata_visible: bool = Field(..., title="Open mode (true) or hidden mode")
    note: Optional[str] = Field(None, title="Note")


class AccessResponse(BaseModel):
    level: str = Field(..., title="owner, write, read or tenancy")
    can_edit: bool = Field(..., title="May change the dataset")
    can_share: bool = Field(..., title="May manage sharing and reviewer links")
    can_manage_embargo: bool = Field(..., title="May set, end or switch the embargo")
    can_extend_embargo: bool = Field(..., title="May extend the embargo")
    can_delete: bool = Field(..., title="May delete the dataset")
```

In `DatasetVersionResponse` add:

```python
    files_withheld: bool = Field(False, title="File list withheld by the embargo")
    files_summary: Optional[VersionFilesSummaryResponse] = Field(
        None, title="File count and size"
    )
```

In `DatasetGetResponse` and `DatasetVersionGetResponse` add:

```python
    embargo: Optional[EmbargoResponse] = Field(None, title="Embargo")
    access: Optional[AccessResponse] = Field(None, title="What the caller may do")
```

- [ ] **Step 5: Adapters** — `app/controller/v1/dataset/dataset.py`

Import the three new response classes and `Embargo`, `DatasetAccess` from `app.model.embargo`. Add:

```python
def _adapt_embargo(embargo: Embargo | None) -> EmbargoResponse | None:
    if embargo is None:
        return None
    return EmbargoResponse(
        until=embargo.until,
        active=embargo.active,
        metadata_visible=embargo.metadata_visible,
        note=embargo.note,
    )


def _adapt_access(access: DatasetAccess | None) -> AccessResponse | None:
    if access is None:
        return None
    return AccessResponse(
        level=access.level.value,
        can_edit=access.can_edit,
        can_share=access.can_share,
        can_manage_embargo=access.can_manage_embargo,
        can_extend_embargo=access.can_extend_embargo,
        can_delete=access.can_delete,
    )


def _files_summary(version: DatasetVersion) -> VersionFilesSummaryResponse:
    return VersionFilesSummaryResponse(
        count=version.files_count or 0,
        total_size_bytes=version.files_size_in_bytes or 0,
    )
```

Add to the `DatasetVersionResponse(...)` construction in both `_adapt_dataset_version` and `_adapt_minimal_dataset_version`:

```python
        files_withheld=version.files_withheld,
        files_summary=_files_summary(version),
```

and to `DatasetGetResponse(...)` in `_adapt_dataset` and `_adapt_minimal_dataset`, and `DatasetVersionGetResponse(...)` in `_adapt_dataset_specific_version`:

```python
        embargo=_adapt_embargo(dataset.embargo),
        access=_adapt_access(dataset.access),
```

- [ ] **Step 6: Run the tests**

Run: `pytest app/service/dataset_test.py app/controller -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/service/dataset.py app/service/dataset_test.py app/controller/v1/dataset/resource.py app/controller/v1/dataset/dataset.py
git commit -m "feat: no snapshot or findable DOI under embargo, short download links, files withheld from the tenancy"
```

---

### Task 8: Search that knows owners, permissions and embargoes

**Files:**
- Modify: `app/repository/dataset.py:82-180`, `app/service/dataset.py` (`search_datasets`), `app/service/dataset_test.py` (`test_search_datasets`), `app/controller/v1/dataset/dataset.py` (`get_datasets`)

**Interfaces:**
- Consumes: ORM `DatasetPermission` (Task 1), `_view` and `DatasetAccessService.level_of` (Tasks 4, 6), `DatasetQuery.shared` (Task 1).
- Produces: `DatasetRepository.search(query_params: DatasetQuery, tenancies: list[str] = None, user_id: UUID | None = None) -> PaginatedResult`; `GET /datasets/?shared=true`.

The clause lives in SQL so `total_count` and the page agree (RFC §Access rule). It mirrors `level_of`: owner, or permission, or tenancy member and (no active embargo or open mode). With `shared=true`, only datasets the caller holds a permission on.

- [ ] **Step 1: Write the failing test** — replace `test_search_datasets` in `app/service/dataset_test.py`

```python
    def test_search_datasets(self):
        user_id = uuid4()
        self.user_service.fetch_by_id.return_value = self.mock_user(["tenancy1"])
        self.tenancy_service.fetch.side_effect = lambda name: self.mock_tenancy(
            name, is_enabled=True
        )
        query = DatasetQuery(shared=True)
        self.dataset_repository.search.return_value = PaginatedResult(
            items=[], total_count=0, page=1, page_size=10
        )

        self.dataset_service.search_datasets(query=query, user_id=user_id)

        self.dataset_repository.search.assert_called_once_with(
            query_params=query, tenancies=["tenancy1"], user_id=user_id
        )

    def test_search_skips_an_item_the_rule_does_not_show(self):
        self.user_service.fetch_by_id.return_value = self.mock_user([])
        hidden = Mock(spec=DatasetDBModel)
        hidden.versions = []
        self.dataset_repository.search.return_value = PaginatedResult(
            items=[hidden], total_count=1, page=1, page_size=10
        )
        self.dataset_access.level_of.return_value = None

        result = self.dataset_service.search_datasets(
            query=DatasetQuery(), user_id=uuid4()
        )

        self.assertEqual(result.items, [])

    def test_a_caller_with_no_tenancy_and_no_header_still_searches(self):
        user_id = uuid4()
        self.user_service.fetch_by_id.return_value = self.mock_user([])
        self.dataset_repository.search.return_value = PaginatedResult(
            items=[], total_count=0, page=1, page_size=10
        )

        self.dataset_service.search_datasets(
            query=DatasetQuery(), user_id=user_id, tenancies=[]
        )

        self.dataset_repository.search.assert_called_once_with(
            query_params=DatasetQuery(), tenancies=[], user_id=user_id
        )

    def test_minimal_items_carry_embargo_and_access(self):
        self.user_service.fetch_by_id.return_value = self.mock_user([])
        shared = Mock(spec=DatasetDBModel)
        shared.versions = []
        self.dataset_repository.search.return_value = PaginatedResult(
            items=[shared], total_count=1, page=1, page_size=10
        )
        self.dataset_access.level_of.return_value = AccessLevel.READ
        embargo = Embargo(
            until=datetime.datetime(2026, 12, 1, tzinfo=datetime.timezone.utc),
            active=True,
            metadata_visible=False,
        )
        self.dataset_access.embargo_of.return_value = embargo
        adapted = SimpleNamespace(versions=[], current_version=None, version=None)

        with patch.object(
            self.dataset_service, "_adapt_minimal_dataset", return_value=adapted
        ):
            result = self.dataset_service.search_datasets(
                query=DatasetQuery(minimal=True), user_id=uuid4()
            )

        self.assertIs(result.items[0].embargo, embargo)
        self.assertIs(
            result.items[0].access, self.dataset_access.access_flags.return_value
        )
```

(`dataset_test.py` already imports `datetime` as a module; add `from types import SimpleNamespace`, `from unittest.mock import patch` if absent, and `Embargo` to the `app.model.embargo` import.)

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest app/service/dataset_test.py -k search -v`
Expected: FAIL — `search` called without `user_id`; the hidden item is returned.

- [ ] **Step 3: Repository** — `app/repository/dataset.py`

Imports: change `from sqlalchemy import and_, or_, func, text` to `from sqlalchemy import and_, or_, func, text, not_, select`, and add `from app.model.db.embargo import DatasetPermission`.

Signature: `def search(self, query_params: DatasetQuery, tenancies: list[str] = None, user_id: UUID | None = None) -> PaginatedResult:`

Replace the line `query = query.filter(Dataset.tenancy.in_(tenancies))` with:

```python
            permitted = select(DatasetPermission.dataset_id).where(
                DatasetPermission.user_id == user_id
            )
            if query_params.shared:
                query = query.filter(Dataset.id.in_(permitted))
            else:
                under_embargo = and_(
                    Dataset.embargo_until.isnot(None),
                    Dataset.embargo_until > func.now(),
                )
                visible_to_tenancy = and_(
                    Dataset.tenancy.in_(tenancies),
                    or_(
                        not_(under_embargo),
                        Dataset.embargo_metadata_visible.is_(True),
                    ),
                )
                query = query.filter(
                    or_(
                        Dataset.owner_id == user_id,
                        Dataset.id.in_(permitted),
                        visible_to_tenancy,
                    )
                )
```

- [ ] **Step 4: Service** — `search_datasets` in `app/service/dataset.py`

```python
    def search_datasets(
        self, query: DatasetQuery, user_id: UUID, tenancies: list[str] = None
    ) -> PaginatedResult:
        allowed = self._determine_tenancies(user_id=user_id, tenancies=tenancies or [])
        result: PaginatedResult = self._repository.search(
            query_params=query, tenancies=allowed, user_id=user_id
        )
        metrics.search(
            has_text=bool(query.full_text),
            has_filters=any(
                (
                    query.categories,
                    query.level,
                    query.data_types,
                    query.date_from,
                    query.date_to,
                )
            ),
            found=result.total_count if result is not None else 0,
        )

        if result is None or result.items is None:
            return PaginatedResult(
                items=[], total_count=0, page=query.page, page_size=query.page_size
            )

        adapt = self._adapt_minimal_dataset if query.minimal else self._adapt_dataset
        items = []
        for dataset in result.items:
            level = self._access.level_of(
                user_id=user_id, dataset=dataset, tenancies=allowed
            )
            if level is None:
                continue
            items.append(
                self._view(adapt(dataset=dataset), dataset, user_id, allowed, level)
            )

        return PaginatedResult(
            items=items,
            total_count=result.total_count,
            page=result.page,
            page_size=result.page_size,
        )
```

- [ ] **Step 5: Controller** — `get_datasets` in `app/controller/v1/dataset/dataset.py`: add the query parameter `shared: bool = False,` after `minimal: bool = False,` and pass `shared=shared,` into `DatasetQuery(...)`. The minimal adapter `_adapt_minimal_dataset` carries `embargo` and `access` (Task 7 Step 5); the webapp's list badge reads them from `GET /datasets/?minimal=true`.

- [ ] **Step 6: Run the tests**

Run: `pytest app/service/dataset_test.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/repository/dataset.py app/service/dataset.py app/service/dataset_test.py app/controller/v1/dataset/dataset.py
git commit -m "feat: search lists owned and shared datasets and hides embargoed ones in SQL"
```

---

### Task 9: `PermissionService` — the grant plan 03 builds on

**Files:**
- Create: `app/service/permission.py`, `app/service/permission_test.py`
- Modify: `app/container.py`

**Interfaces:**
- Consumes: `PermissionRepository` (Task 2), `EmbargoAudit` (Task 5), `UserService.fetch_by_id/add_roles` (existing), `SHARED_ROLE` (Task 1).
- Produces (plan 03 calls these; no route here):
  - `PermissionService.grant(dataset_id: UUID, user_id: UUID, level: PermissionLevel, granted_by: UUID | None) -> DatasetPermission` — upserts, adds `g, <user_id>, datasets_shared` if missing, records `permission_granted`.
  - `PermissionService.revoke(dataset_id: UUID, user_id: UUID, revoked_by: UUID | None) -> bool` — deletes, records `permission_revoked`; leaves the role (it grants nothing alone).
  - `PermissionService.list_for_dataset(dataset_id: UUID) -> list[DatasetPermission]`
  - Container provider `permission_service`.

- [ ] **Step 1: Write the failing tests** — `app/service/permission_test.py`

```python
import unittest
from unittest.mock import Mock
from uuid import uuid4

from app.exception.not_found import NotFoundException
from app.model.db.embargo import DatasetPermission as DatasetPermissionDBModel
from app.model.embargo import EmbargoEventType, PermissionLevel
from app.model.user import User
from app.repository.permission import PermissionRepository
from app.service.embargo_audit import EmbargoAudit
from app.service.permission import PermissionService
from app.service.user import UserService


class TestPermissionService(unittest.TestCase):
    def setUp(self):
        self.permissions = Mock(spec=PermissionRepository)
        self.users = Mock(spec=UserService)
        self.audit = Mock(spec=EmbargoAudit)
        self.service = PermissionService(
            permission_repository=self.permissions,
            user_service=self.users,
            audit=self.audit,
        )
        self.dataset_id, self.user_id, self.by = uuid4(), uuid4(), uuid4()
        self.permissions.fetch.return_value = None
        self.permissions.upsert.return_value = DatasetPermissionDBModel(
            dataset_id=self.dataset_id, user_id=self.user_id, level="read"
        )

    def test_granting_gives_the_shared_role_once(self):
        self.users.fetch_by_id.return_value = User(id=self.user_id, roles=[])

        permission = self.service.grant(
            self.dataset_id, self.user_id, PermissionLevel.READ, self.by
        )

        self.assertEqual(permission.level, PermissionLevel.READ)
        self.users.add_roles.assert_called_once_with(
            id=self.user_id, roles=["datasets_shared"]
        )
        self.audit.record.assert_called_once_with(
            dataset_id=self.dataset_id,
            event_type=EmbargoEventType.PERMISSION_GRANTED,
            changed_by=self.by,
            old_value=None,
            new_value={"user_id": str(self.user_id), "level": "read"},
        )

    def test_a_user_who_has_the_role_is_not_given_it_again(self):
        self.users.fetch_by_id.return_value = User(
            id=self.user_id, roles=["datasets_shared"]
        )

        self.service.grant(self.dataset_id, self.user_id, PermissionLevel.READ, self.by)

        self.users.add_roles.assert_not_called()

    def test_granting_to_a_missing_user_fails_before_writing(self):
        self.users.fetch_by_id.side_effect = NotFoundException("missing")

        with self.assertRaises(NotFoundException):
            self.service.grant(
                self.dataset_id, self.user_id, PermissionLevel.READ, self.by
            )

        self.permissions.upsert.assert_not_called()

    def test_revoking_a_permission_records_it(self):
        self.permissions.fetch.return_value = DatasetPermissionDBModel(
            dataset_id=self.dataset_id, user_id=self.user_id, level="write"
        )

        self.assertTrue(self.service.revoke(self.dataset_id, self.user_id, self.by))

        self.permissions.delete.assert_called_once_with(
            dataset_id=self.dataset_id, user_id=self.user_id
        )
        self.audit.record.assert_called_once_with(
            dataset_id=self.dataset_id,
            event_type=EmbargoEventType.PERMISSION_REVOKED,
            changed_by=self.by,
            old_value={"user_id": str(self.user_id), "level": "write"},
        )

    def test_revoking_nothing_is_not_an_event(self):
        self.assertFalse(self.service.revoke(self.dataset_id, self.user_id, self.by))
        self.audit.record.assert_not_called()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest app/service/permission_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.service.permission'`

- [ ] **Step 3: Implement** — `app/service/permission.py`

```python
from uuid import UUID

from app.model.db.embargo import DatasetPermission as DatasetPermissionDBModel
from app.model.embargo import (
    SHARED_ROLE,
    DatasetPermission,
    EmbargoEventType,
    PermissionLevel,
)
from app.repository.permission import PermissionRepository
from app.service.embargo_audit import EmbargoAudit
from app.service.user import UserService


def _adapt(permission: DatasetPermissionDBModel) -> DatasetPermission:
    return DatasetPermission(
        dataset_id=permission.dataset_id,
        user_id=permission.user_id,
        level=PermissionLevel(permission.level),
        granted_by=permission.granted_by,
        created_at=permission.created_at,
    )


class PermissionService:
    def __init__(
        self,
        permission_repository: PermissionRepository,
        user_service: UserService,
        audit: EmbargoAudit,
    ) -> None:
        self._permissions = permission_repository
        self._user_service = user_service
        self._audit = audit

    def grant(
        self,
        dataset_id: UUID,
        user_id: UUID,
        level: PermissionLevel,
        granted_by: UUID | None,
    ) -> DatasetPermission:
        user = self._user_service.fetch_by_id(id=user_id)
        previous = self._permissions.fetch(dataset_id=dataset_id, user_id=user_id)
        saved = self._permissions.upsert(
            dataset_id=dataset_id,
            user_id=user_id,
            level=level.value,
            granted_by=granted_by,
        )
        if SHARED_ROLE not in (user.roles or []):
            self._user_service.add_roles(id=user_id, roles=[SHARED_ROLE])
        self._audit.record(
            dataset_id=dataset_id,
            event_type=EmbargoEventType.PERMISSION_GRANTED,
            changed_by=granted_by,
            old_value={"user_id": str(user_id), "level": previous.level}
            if previous is not None
            else None,
            new_value={"user_id": str(user_id), "level": level.value},
        )
        return _adapt(saved)

    def revoke(self, dataset_id: UUID, user_id: UUID, revoked_by: UUID | None) -> bool:
        previous = self._permissions.fetch(dataset_id=dataset_id, user_id=user_id)
        if previous is None:
            return False
        self._permissions.delete(dataset_id=dataset_id, user_id=user_id)
        self._audit.record(
            dataset_id=dataset_id,
            event_type=EmbargoEventType.PERMISSION_REVOKED,
            changed_by=revoked_by,
            old_value={"user_id": str(user_id), "level": previous.level},
        )
        return True

    def list_for_dataset(self, dataset_id: UUID) -> list[DatasetPermission]:
        return [
            _adapt(permission)
            for permission in self._permissions.list_for_dataset(dataset_id=dataset_id)
        ]
```

- [ ] **Step 4: Container** — `app/container.py`

```python
from app.service.permission import PermissionService
```

(`embargo_event_repository` and `embargo_audit` were declared in Task 6.)

```python
    permission_service = providers.Factory(
        PermissionService,
        permission_repository=permission_repository,
        user_service=user_service,
        audit=embargo_audit,
    )
```

- [ ] **Step 5: Run the tests**

Run: `pytest app/service/permission_test.py -v && python -c "from app.container import Container; Container()"`
Expected: PASS (5 tests); the container builds without error.

- [ ] **Step 6: Commit**

```bash
git add app/service/permission.py app/service/permission_test.py app/container.py
git commit -m "feat: granting a permission gives the shared role and leaves a trail"
```

---

### Task 10: `EmbargoService` and the embargo routes

**Files:**
- Create: `app/service/embargo.py`, `app/service/embargo_test.py`, `app/controller/v1/dataset/embargo.py`, `app/controller/v1/dataset/embargo_status.py`
- Modify: `app/controller/v1/dataset/resource.py`, `app/container.py` (providers + `wiring_config`), `app/setup.py` (`setup_routes`)

**Interfaces:**
- Consumes: `DatasetService.fetch_authorized` (Task 6), `DatasetRepository.fetch/upsert`, `DatasetAccessService` (Task 4), `EmbargoAudit`, `EmbargoTermination`, `embargo_state` (Task 5).
- Produces:
  - `EmbargoService.set_embargo(dataset_id, user_id, tenancies, until: datetime, metadata_visible: bool, note: str | None) -> Embargo` — refuses `embargo_manual_doi` when any version has a manual DOI, checked before `embargo_dataset_published`
  - `EmbargoService.extend(dataset_id, user_id, tenancies, until: datetime) -> Embargo`
  - `EmbargoService.end(dataset_id, user_id, tenancies) -> Embargo`
  - `EmbargoService.set_mode(dataset_id, user_id, tenancies, metadata_visible: bool) -> Embargo`
  - `EmbargoService.status(dataset_id: UUID) -> tuple[bool, datetime | None]`
  - Routes per contracts §Embargo; `GET /datasets/{id}/embargo-status` with `authenticate` only.

- [ ] **Step 1: Write the failing tests** — `app/service/embargo_test.py`

```python
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

from app.exception.bad_request import BadRequestException
from app.exception.forbidden import ForbiddenException
from app.model.dataset import VisibilityStatus
from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.db.dataset import DatasetVersion as DatasetVersionDBModel
from app.model.db.doi import DOI as DOIDBModel
from app.model.embargo import AccessLevel, DatasetAction, EmbargoEventType
from app.repository.dataset import DatasetRepository
from app.service.dataset import DatasetService
from app.service.dataset_access import DatasetAccessService
from app.service.embargo import EmbargoService
from app.service.embargo_audit import EmbargoAudit
from app.service.embargo_termination import EmbargoTermination

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class TestEmbargoService(unittest.TestCase):
    def setUp(self):
        self.datasets = Mock(spec=DatasetService)
        self.repository = Mock(spec=DatasetRepository)
        self.audit = Mock(spec=EmbargoAudit)
        self.access = DatasetAccessService(
            permission_repository=Mock(), user_service=Mock()
        )
        self.service = EmbargoService(
            dataset_service=self.datasets,
            repository=self.repository,
            access_service=self.access,
            audit=self.audit,
            termination=EmbargoTermination(repository=self.repository, audit=self.audit),
        )
        self.user_id = uuid4()
        self.dataset = DatasetDBModel(
            id=uuid4(),
            name="d",
            data={},
            owner_id=self.user_id,
            tenancy="t",
            visibility=VisibilityStatus.PRIVATE,
            embargo_until=None,
            embargo_metadata_visible=False,
        )
        self.datasets.fetch_authorized.return_value = (
            self.dataset,
            ["t"],
            AccessLevel.OWNER,
        )
        patcher = patch("app.service.embargo.utcnow", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)
        patch_access = patch("app.service.dataset_access.utcnow", return_value=NOW)
        patch_access.start()
        self.addCleanup(patch_access.stop)

    def _code(self, call) -> str:
        with self.assertRaises(BadRequestException) as raised:
            call()
        return raised.exception.errors[0].code

    def _set(self, until, visible=False):
        return self.service.set_embargo(
            dataset_id=self.dataset.id,
            user_id=self.user_id,
            tenancies=None,
            until=until,
            metadata_visible=visible,
            note="under review",
        )

    def test_setting_an_embargo(self):
        embargo = self._set(NOW + timedelta(days=30), visible=True)

        self.assertTrue(embargo.active)
        self.assertTrue(embargo.metadata_visible)
        self.assertEqual(self.dataset.embargo_until, NOW + timedelta(days=30))
        self.repository.upsert.assert_called_once_with(dataset=self.dataset)
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"], EmbargoEventType.CREATED
        )
        self.assertEqual(
            self.datasets.fetch_authorized.call_args.kwargs["action"],
            DatasetAction.MANAGE_EMBARGO,
        )

    def test_the_cap_applies_on_creation(self):
        self.assertEqual(
            self._code(lambda: self._set(NOW + timedelta(days=90, seconds=1))),
            "embargo_too_long",
        )

    def test_ninety_days_exactly_is_allowed(self):
        self.assertTrue(self._set(NOW + timedelta(days=90)).active)

    def test_a_date_in_the_past_is_refused(self):
        self.assertEqual(
            self._code(lambda: self._set(NOW - timedelta(minutes=1))),
            "embargo_until_in_past",
        )

    def test_a_published_dataset_cannot_be_embargoed(self):
        self.dataset.visibility = VisibilityStatus.PUBLIC
        self.assertEqual(
            self._code(lambda: self._set(NOW + timedelta(days=1))),
            "embargo_dataset_published",
        )

    def _with_manual_doi(self):
        self.dataset.versions = [
            DatasetVersionDBModel(
                name="1",
                doi=DOIDBModel(mode="MANUAL", state="FINDABLE", doi={}),
            )
        ]

    def test_a_dataset_with_a_manual_doi_cannot_be_embargoed(self):
        self._with_manual_doi()
        self.assertEqual(
            self._code(lambda: self._set(NOW + timedelta(days=1))),
            "embargo_manual_doi",
        )

    def test_the_manual_doi_check_does_not_rely_on_the_snapshot(self):
        self._with_manual_doi()
        self.dataset.visibility = VisibilityStatus.PUBLIC
        self.assertEqual(
            self._code(lambda: self._set(NOW + timedelta(days=1))),
            "embargo_manual_doi",
        )

    def test_a_datamap_doi_does_not_prevent_an_embargo(self):
        self.dataset.versions = [
            DatasetVersionDBModel(
                name="1", doi=DOIDBModel(mode="AUTO", state="DRAFT", doi={})
            )
        ]
        self.assertTrue(self._set(NOW + timedelta(days=1)).active)

    def test_an_active_embargo_cannot_be_set_again(self):
        self.dataset.embargo_until = NOW + timedelta(days=1)
        self.assertEqual(
            self._code(lambda: self._set(NOW + timedelta(days=2))),
            "embargo_already_active",
        )

    def test_an_embargo_that_ended_unpublished_can_be_set_again(self):
        self.dataset.embargo_until = NOW - timedelta(days=1)
        self.assertTrue(self._set(NOW + timedelta(days=2)).active)

    def test_a_naive_date_is_read_as_utc(self):
        naive = (NOW + timedelta(days=3)).replace(tzinfo=None)
        self.assertEqual(self._set(naive).until, NOW + timedelta(days=3))

    def _extend(self, until):
        return self.service.extend(
            dataset_id=self.dataset.id,
            user_id=self.user_id,
            tenancies=None,
            until=until,
        )

    def test_extending(self):
        self.dataset.embargo_until = NOW + timedelta(days=10)
        embargo = self._extend(NOW + timedelta(days=80))
        self.assertEqual(embargo.until, NOW + timedelta(days=80))
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"],
            EmbargoEventType.EXTENDED,
        )

    def test_the_cap_applies_on_every_extension(self):
        self.dataset.embargo_until = NOW + timedelta(days=10)
        self.assertEqual(
            self._code(lambda: self._extend(NOW + timedelta(days=91))),
            "embargo_too_long",
        )

    def test_an_extension_must_move_the_date_forward(self):
        self.dataset.embargo_until = NOW + timedelta(days=10)
        self.assertEqual(
            self._code(lambda: self._extend(NOW + timedelta(days=10))),
            "embargo_until_not_later",
        )

    def test_there_is_nothing_to_extend_without_an_active_embargo(self):
        self.assertEqual(
            self._code(lambda: self._extend(NOW + timedelta(days=10))),
            "embargo_not_active",
        )

    def test_a_reader_cannot_extend_while_the_owner_is_active(self):
        self.dataset.embargo_until = NOW + timedelta(days=10)
        self.dataset.owner_id = uuid4()
        self.datasets.fetch_authorized.return_value = (
            self.dataset,
            [],
            AccessLevel.READ,
        )
        self.access._permissions.fetch.return_value = Mock(level="read")
        with self.assertRaises(ForbiddenException):
            self._extend(NOW + timedelta(days=20))

    def test_ending_early(self):
        self.dataset.embargo_until = NOW + timedelta(days=10)
        embargo = self.service.end(
            dataset_id=self.dataset.id, user_id=self.user_id, tenancies=None
        )
        self.assertFalse(embargo.active)
        self.assertEqual(self.dataset.embargo_until, NOW)
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"],
            EmbargoEventType.ENDED_EARLY,
        )

    def test_switching_mode(self):
        self.dataset.embargo_until = NOW + timedelta(days=10)
        embargo = self.service.set_mode(
            dataset_id=self.dataset.id,
            user_id=self.user_id,
            tenancies=None,
            metadata_visible=True,
        )
        self.assertTrue(embargo.metadata_visible)
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"],
            EmbargoEventType.METADATA_MODE_CHANGED,
        )

    def test_status_of_an_unknown_dataset_reveals_nothing(self):
        self.repository.fetch.return_value = None
        self.assertEqual(self.service.status(uuid4()), (False, None))

    def test_status_of_an_embargoed_dataset(self):
        self.dataset.embargo_until = NOW + timedelta(days=10)
        self.repository.fetch.return_value = self.dataset
        self.assertEqual(
            self.service.status(self.dataset.id), (True, NOW + timedelta(days=10))
        )
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest app/service/embargo_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.service.embargo'`

- [ ] **Step 3: Implement** — `app/service/embargo.py`

```python
from datetime import datetime, timezone
from uuid import UUID

from app.exception.bad_request import BadRequestException, ErrorDetails
from app.exception.forbidden import ForbiddenException
from app.model.dataset import VisibilityStatus
from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.doi import Mode as DOIMode
from app.model.embargo import (
    MAX_EMBARGO_PERIOD,
    DatasetAction,
    Embargo,
    EmbargoEventType,
    utcnow,
)
from app.repository.dataset import DatasetRepository
from app.service.dataset import DatasetService
from app.service.dataset_access import DatasetAccessService
from app.service.embargo_audit import EmbargoAudit
from app.service.embargo_termination import EmbargoTermination, embargo_state


def _bad(code: str) -> BadRequestException:
    return BadRequestException(errors=[ErrorDetails(code=code)])


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _has_manual_doi(dataset: DatasetDBModel) -> bool:
    return any(
        version.doi is not None and version.doi.mode == DOIMode.MANUAL.name
        for version in dataset.versions
    )


def _validate_until(until: datetime, now: datetime) -> None:
    if until <= now:
        raise _bad("embargo_until_in_past")
    if until > now + MAX_EMBARGO_PERIOD:
        raise _bad("embargo_too_long")


class EmbargoService:
    def __init__(
        self,
        dataset_service: DatasetService,
        repository: DatasetRepository,
        access_service: DatasetAccessService,
        audit: EmbargoAudit,
        termination: EmbargoTermination,
    ) -> None:
        self._datasets = dataset_service
        self._repository = repository
        self._access = access_service
        self._audit = audit
        self._termination = termination

    def set_embargo(
        self,
        dataset_id: UUID,
        user_id: UUID,
        tenancies: list[str] | None,
        until: datetime,
        metadata_visible: bool,
        note: str | None,
    ) -> Embargo:
        dataset, _, _ = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.MANAGE_EMBARGO,
        )
        now = utcnow()
        until = _aware(until)
        if self._access.embargo_active(dataset, now):
            raise _bad("embargo_already_active")
        if _has_manual_doi(dataset):
            raise _bad("embargo_manual_doi")
        if dataset.visibility == VisibilityStatus.PUBLIC:
            raise _bad("embargo_dataset_published")
        _validate_until(until, now)

        before = embargo_state(dataset)
        dataset.embargo_until = until
        dataset.embargo_metadata_visible = metadata_visible
        dataset.embargo_note = note
        self._repository.upsert(dataset=dataset)
        self._audit.record(
            dataset_id=dataset.id,
            event_type=EmbargoEventType.CREATED,
            changed_by=user_id,
            old_value=before,
            new_value=embargo_state(dataset),
            note=note,
        )
        return self._access.embargo_of(dataset, now)

    def extend(
        self,
        dataset_id: UUID,
        user_id: UUID,
        tenancies: list[str] | None,
        until: datetime,
    ) -> Embargo:
        dataset, allowed, _ = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.READ_METADATA,
        )
        now = utcnow()
        until = _aware(until)
        if not self._access.embargo_active(dataset, now):
            raise _bad("embargo_not_active")
        if not self._access.permits(
            user_id=user_id,
            dataset=dataset,
            tenancies=allowed,
            action=DatasetAction.EXTEND_EMBARGO,
            now=now,
        ):
            raise ForbiddenException(f"forbidden: extend {dataset.id} for {user_id}")
        if until <= dataset.embargo_until:
            raise _bad("embargo_until_not_later")
        _validate_until(until, now)

        before = embargo_state(dataset)
        dataset.embargo_until = until
        self._repository.upsert(dataset=dataset)
        self._audit.record(
            dataset_id=dataset.id,
            event_type=EmbargoEventType.EXTENDED,
            changed_by=user_id,
            old_value=before,
            new_value=embargo_state(dataset),
        )
        return self._access.embargo_of(dataset, now)

    def end(
        self, dataset_id: UUID, user_id: UUID, tenancies: list[str] | None
    ) -> Embargo:
        dataset, _, _ = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.MANAGE_EMBARGO,
        )
        now = utcnow()
        if not self._access.embargo_active(dataset, now):
            raise _bad("embargo_not_active")

        self._termination.end(dataset=dataset, ended_by=user_id, now=now)
        return self._access.embargo_of(dataset, now)

    def set_mode(
        self,
        dataset_id: UUID,
        user_id: UUID,
        tenancies: list[str] | None,
        metadata_visible: bool,
    ) -> Embargo:
        dataset, _, _ = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.MANAGE_EMBARGO,
        )
        now = utcnow()
        if not self._access.embargo_active(dataset, now):
            raise _bad("embargo_not_active")

        if bool(dataset.embargo_metadata_visible) != metadata_visible:
            before = embargo_state(dataset)
            dataset.embargo_metadata_visible = metadata_visible
            self._repository.upsert(dataset=dataset)
            self._audit.record(
                dataset_id=dataset.id,
                event_type=EmbargoEventType.METADATA_MODE_CHANGED,
                changed_by=user_id,
                old_value=before,
                new_value=embargo_state(dataset),
            )
        return self._access.embargo_of(dataset, now)

    def status(self, dataset_id: UUID) -> tuple[bool, datetime | None]:
        dataset = self._repository.fetch(
            dataset_id=dataset_id, version_is_enabled=False, restrict_by_tenancy=False
        )
        if dataset is None or not self._access.embargo_active(dataset):
            return False, None
        return True, dataset.embargo_until
```

- [ ] **Step 4: Run the service tests**

Run: `pytest app/service/embargo_test.py -v`
Expected: PASS (20 tests)

- [ ] **Step 5: Request/response models** — append to `app/controller/v1/dataset/resource.py`

```python
class EmbargoSetRequest(BaseModel):
    until: datetime = Field(..., title="Embargo end, at most 90 days ahead")
    metadata_visible: bool = Field(False, title="Open mode (true) or hidden mode")
    note: Optional[str] = Field(None, title="Note", max_length=2000)


class EmbargoExtendRequest(BaseModel):
    until: datetime = Field(..., title="New embargo end, at most 90 days ahead")


class EmbargoModeRequest(BaseModel):
    metadata_visible: bool = Field(..., title="Open mode (true) or hidden mode")


class EmbargoStatusResponse(BaseModel):
    embargoed: bool = Field(..., title="Whether the dataset is under embargo now")
    until: Optional[datetime] = Field(None, title="Embargo end")
```

- [ ] **Step 6: Routes** — `app/controller/v1/dataset/embargo.py`

```python
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.tenancy_parser import parse_tenancy_header
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.dataset.resource import (
    EmbargoExtendRequest,
    EmbargoModeRequest,
    EmbargoResponse,
    EmbargoSetRequest,
)
from app.model.embargo import Embargo
from app.service.embargo import EmbargoService

router = APIRouter(
    prefix="/datasets",
    tags=["embargo"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


def _adapt(embargo: Embargo) -> EmbargoResponse:
    return EmbargoResponse(
        until=embargo.until,
        active=embargo.active,
        metadata_visible=embargo.metadata_visible,
        note=embargo.note,
    )


# PUT /datasets/{dataset_id}/embargo
@router.put("/{dataset_id}/embargo")
@inject
def set_embargo(
    dataset_id: UUID,
    request: EmbargoSetRequest,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: EmbargoService = Depends(Provide[Container.embargo_service]),
) -> EmbargoResponse:
    return _adapt(
        service.set_embargo(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            until=request.until,
            metadata_visible=request.metadata_visible,
            note=request.note,
        )
    )


# POST /datasets/{dataset_id}/embargo/extend
@router.post("/{dataset_id}/embargo/extend")
@inject
def extend_embargo(
    dataset_id: UUID,
    request: EmbargoExtendRequest,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: EmbargoService = Depends(Provide[Container.embargo_service]),
) -> EmbargoResponse:
    return _adapt(
        service.extend(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            until=request.until,
        )
    )


# POST /datasets/{dataset_id}/embargo/end
@router.post("/{dataset_id}/embargo/end")
@inject
def end_embargo(
    dataset_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: EmbargoService = Depends(Provide[Container.embargo_service]),
) -> EmbargoResponse:
    return _adapt(
        service.end(dataset_id=dataset_id, user_id=user_id, tenancies=tenancies)
    )


# PUT /datasets/{dataset_id}/embargo/mode
@router.put("/{dataset_id}/embargo/mode")
@inject
def set_embargo_mode(
    dataset_id: UUID,
    request: EmbargoModeRequest,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: EmbargoService = Depends(Provide[Container.embargo_service]),
) -> EmbargoResponse:
    return _adapt(
        service.set_mode(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            metadata_visible=request.metadata_visible,
        )
    )
```

`app/controller/v1/dataset/embargo_status.py`:

```python
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.v1.dataset.resource import EmbargoStatusResponse
from app.service.embargo import EmbargoService

router = APIRouter(prefix="/datasets", tags=["embargo"])


# GET /datasets/{dataset_id}/embargo-status
@router.get("/{dataset_id}/embargo-status", dependencies=[Depends(authenticate)])
@inject
def get_embargo_status(
    dataset_id: UUID,
    service: EmbargoService = Depends(Provide[Container.embargo_service]),
) -> EmbargoStatusResponse:
    embargoed, until = service.status(dataset_id=dataset_id)
    return EmbargoStatusResponse(embargoed=embargoed, until=until)
```

- [ ] **Step 7: Wire them** — `app/container.py`: import `EmbargoService`; add `"app.controller.v1.dataset.embargo"` and `"app.controller.v1.dataset.embargo_status"` to `wiring_config.modules`; add the provider after `dataset_service`:

```python
    embargo_service = providers.Factory(
        EmbargoService,
        dataset_service=dataset_service,
        repository=dataset_repository,
        access_service=dataset_access_service,
        audit=embargo_audit,
        termination=embargo_termination,
    )
```

`app/setup.py`: import both routers (`from app.controller.v1.dataset.embargo import router as embargo_router`, `from app.controller.v1.dataset.embargo_status import router as embargo_status_router`) and in `setup_routes`, after the `dataset_snapshot_router` line:

```python
    fastAPIApp.include_router(embargo_router, prefix="/v1")
    fastAPIApp.include_router(embargo_status_router, prefix="/v1")
```

- [ ] **Step 8: Run the route security test and the whole suite**

Run: `pytest app/controller/routes_security_test.py -v && pytest`
Expected: PASS. `embargo-status` passes the security test without being listed in `PUBLIC_ROUTES`, since it carries `authenticate`.

- [ ] **Step 9: Commit**

```bash
git add app/service/embargo.py app/service/embargo_test.py app/controller/v1/dataset/embargo.py app/controller/v1/dataset/embargo_status.py app/controller/v1/dataset/resource.py app/container.py app/setup.py
git commit -m "feat: routes to set, extend, end and switch an embargo, and its public status"
```

---

### Task 11: Casbin policies for `datasets_shared`

**Files:**
- Modify: `app/resources/casbin_seed_policies.sql`, `app/resources/rbac_data.sql`, `tests/integration/fixtures/seed_clients.sql:23`

**Interfaces:**
- Produces: the role `datasets_shared` with exactly the three policies of contracts §Casbin seed additions.

- [ ] **Step 1: Append to `app/resources/casbin_seed_policies.sql`**

```sql
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_shared', '/api/v1/datasets/?$', 'GET', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_shared', '/api/v1/datasets/[0-9a-f-]{36}(/.*)?$', '(GET|POST|PUT|DELETE)', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_shared', '/api/v1/tus', 'POST', 'allow', NULL, NULL);
```

- [ ] **Step 2: Append to `app/resources/rbac_data.sql`**

```sql
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_shared', '/api/v1/datasets/?$', 'GET', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_shared', '/api/v1/datasets/[0-9a-f-]{36}(/.*)?$', '(GET|POST|PUT|DELETE)', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_shared', '/api/v1/tus', 'POST', 'allow', NULL, NULL);
```

- [ ] **Step 3: Insert into `tests/integration/fixtures/seed_clients.sql`**, right after the `datasets_filters` policy (line 23), the same three lines as Step 2.

- [ ] **Step 4: Check the regexes behave as intended with Casbin's own matcher**

Run:
```bash
python - <<'EOF'
from casbin.util.builtin_operators import regex_match
uuid = "0b7e2a2e-1c1e-4b6e-9a55-3f1a2b3c4d5e"
assert regex_match("/api/v1/datasets", "/api/v1/datasets/?$")
assert regex_match("/api/v1/datasets/", "/api/v1/datasets/?$")
assert not regex_match("/api/v1/datasets/filters", "/api/v1/datasets/?$")
assert regex_match(f"/api/v1/datasets/{uuid}", "/api/v1/datasets/[0-9a-f-]{36}(/.*)?$")
assert regex_match(f"/api/v1/datasets/{uuid}/embargo/extend", "/api/v1/datasets/[0-9a-f-]{36}(/.*)?$")
assert not regex_match("/api/v1/datasets/filters", "/api/v1/datasets/[0-9a-f-]{36}(/.*)?$")
assert not regex_match("/api/v1/datasets/tenancy-scope", "/api/v1/datasets/[0-9a-f-]{36}(/.*)?$")
assert not regex_match("/api/v1/datasets/tenancy-scope", "/api/v1/datasets/?$")
assert regex_match("/api/v1/datasets/tenancy-scope", "/api/v1/datasets")
print("ok")
EOF
```
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add app/resources/casbin_seed_policies.sql app/resources/rbac_data.sql tests/integration/fixtures/seed_clients.sql
git commit -m "feat: the datasets_shared role reaches named datasets and nothing else"
```

Production note for the PR description: the three `casbin_seed_policies.sql` rows are inserted by hand on the production database before this gatekeeper is deployed (README, seed policies).

---

### Task 12: Integration tests

**Files:**
- Create: `tests/integration/fixtures/embargo.py`, `tests/integration/test_dataset_embargo.py`

**Interfaces:**
- Consumes: every route of Tasks 6–10, the seed of Task 11, `POST /users/`, `PUT /users/{id}/roles`, `POST /users/{id}/tenancies`, `DELETE /users/{id}` (existing).

Permissions are granted directly in PostgreSQL here, since the share routes arrive with plan 03; the role is added through the users API, exactly as `PermissionService.grant` would.

- [ ] **Step 1: Write the fixture** — `tests/integration/fixtures/embargo.py`

```python
import subprocess
import uuid
from datetime import datetime, timedelta, timezone

from tests.integration.config import config
from tests.integration.fixtures.auth import AuthFixture

POSTGRES_CONTAINER = "datamap_postgres_test_integration"
TENANCY = config.tenancy


def until(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def headers_for(user_id: str, tenancy: str | None) -> dict:
    headers = {
        "X-Api-Key": config.api_key,
        "X-Api-Secret": config.api_secret,
        "X-User-Id": user_id,
        "Content-Type": "application/json",
    }
    if tenancy:
        headers["X-Datamap-Tenancies"] = tenancy
    return headers


def client_headers() -> dict:
    return {
        "X-Api-Key": config.api_key,
        "X-Api-Secret": config.api_secret,
        "Content-Type": "application/json",
    }


def create_user(http_client, roles: list[str], tenancies: list[str]) -> str:
    admin = AuthFixture.valid_headers()
    response = http_client.post(
        "/users/",
        json={
            "name": "Embargo Test User",
            "email": f"embargo_{uuid.uuid4().hex[:10]}@example.com",
            "providers": [],
            "roles": [],
        },
        headers=admin,
    )
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


def grant(http_client, dataset_id: str, user_id: str, level: str) -> None:
    sql = (
        "INSERT INTO dataset_permissions (dataset_id, user_id, level) "
        f"VALUES ('{dataset_id}', '{user_id}', '{level}') "
        "ON CONFLICT (dataset_id, user_id) DO UPDATE SET level = EXCLUDED.level"
    )
    subprocess.run(
        [
            "docker", "exec", POSTGRES_CONTAINER,
            "psql", "-U", "gk_admin", "-d", "gatekeeper_db",
            "-v", "ON_ERROR_STOP=1", "-c", sql,
        ],
        check=True,
        capture_output=True,
    )
    response = http_client.put(
        f"/users/{user_id}/roles",
        json=["datasets_shared"],
        headers=AuthFixture.valid_headers(),
    )
    assert response.status_code == 200, response.text


def create_dataset(http_client, headers: dict) -> dict:
    response = http_client.post(
        "/datasets",
        json={
            "name": f"Embargo Test {uuid.uuid4().hex[:8]}",
            "data": {"description": "embargo", "authors": [{"name": "A"}]},
            "tenancy": TENANCY,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def set_embargo(http_client, dataset_id: str, headers: dict, visible: bool, days: int = 30):
    return http_client.put(
        f"/datasets/{dataset_id}/embargo",
        json={"until": until(days), "metadata_visible": visible, "note": "review"},
        headers=headers,
    )


def manual_doi(http_client, dataset: dict, headers: dict, end_embargo: bool | None = None):
    body = {"identifier": f"10.82978/MANUAL{uuid.uuid4().hex[:8]}", "mode": "MANUAL"}
    if end_embargo is not None:
        body["end_embargo"] = end_embargo
    version = dataset["current_version"]["name"]
    return http_client.post(
        f"/datasets/{dataset['id']}/versions/{version}/doi", json=body, headers=headers
    )


def auto_doi(http_client, dataset: dict, headers: dict):
    version = dataset["current_version"]["name"]
    return http_client.post(
        f"/datasets/{dataset['id']}/versions/{version}/doi",
        json={"mode": "AUTO"},
        headers=headers,
    )


def make_findable(http_client, dataset: dict, headers: dict):
    version = dataset["current_version"]["name"]
    return http_client.put(
        f"/datasets/{dataset['id']}/versions/{version}/doi",
        json={"state": "FINDABLE"},
        headers=headers,
    )
```

- [ ] **Step 2: Write the tests** — `tests/integration/test_dataset_embargo.py`

```python
import uuid

import pytest

from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.embargo import (
    TENANCY,
    auto_doi,
    client_headers,
    create_dataset,
    create_user,
    grant,
    headers_for,
    make_findable,
    manual_doi,
    set_embargo,
    until,
)
from tests.integration.fixtures.tus_auth import create_tus_payload
from tests.integration.utils.assertions import assert_status_code


@pytest.fixture
def owner():
    return AuthFixture.valid_headers()


@pytest.fixture
def member(http_client):
    user_id = create_user(http_client, ["datasets_write"], [TENANCY])
    return user_id, headers_for(user_id, TENANCY)


@pytest.fixture
def outsider(http_client):
    user_id = create_user(http_client, [], [])
    return user_id, headers_for(user_id, None)


def _ids(response) -> list[str]:
    return [item["id"] for item in response.json()["content"]]


class TestHiddenEmbargo:
    def test_a_tenancy_member_does_not_know_it_exists(self, http_client, owner, member):
        dataset = create_dataset(http_client, owner)
        assert_status_code(set_embargo(http_client, dataset["id"], owner, visible=False), 200)

        _, headers = member
        assert_status_code(http_client.get(f"/datasets/{dataset['id']}", headers=headers), 404)
        listing = http_client.get("/datasets/?page_size=20", headers=headers)
        assert_status_code(listing, 200)
        assert dataset["id"] not in _ids(listing)

    def test_every_write_answers_404(self, http_client, owner, member):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        _, headers = member

        update = http_client.put(
            f"/datasets/{dataset['id']}",
            json={"name": "x", "data": {}, "tenancy": TENANCY},
            headers=headers,
        )
        version = http_client.post(
            f"/datasets/{dataset['id']}/versions",
            json={"datafilesPreviouslyUploaded": []},
            headers=headers,
        )
        assert_status_code(update, 404)
        assert_status_code(version, 404)

    def test_an_upload_from_the_tenancy_is_rejected(self, http_client, owner, member):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        user_id, _ = member

        payload = create_tus_payload(
            user_id=user_id,
            dataset_id=dataset["id"],
            filename="a.nc",
            file_size=10,
            file_type="application/x-netcdf",
        )
        response = http_client.post("/tus/hooks", json=payload, headers=AuthFixture.valid_headers())

        assert response.json().get("RejectUpload") is True


class TestOpenEmbargo:
    def test_a_tenancy_member_sees_the_badge_but_not_the_files(self, http_client, owner, member):
        dataset = create_dataset(http_client, owner)
        assert_status_code(set_embargo(http_client, dataset["id"], owner, visible=True), 200)
        _, headers = member

        response = http_client.get(f"/datasets/{dataset['id']}", headers=headers)

        assert_status_code(response, 200)
        body = response.json()
        assert body["embargo"]["active"] is True
        assert body["embargo"]["metadata_visible"] is True
        assert body["access"]["level"] == "tenancy"
        assert body["access"]["can_edit"] is False
        for version in body["versions"]:
            assert version["files_withheld"] is True
            assert version["files_in"] == []
            assert "count" in version["files_summary"]

    def test_a_write_is_forbidden_not_hidden(self, http_client, owner, member):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=True)
        _, headers = member

        response = http_client.put(
            f"/datasets/{dataset['id']}",
            json={"name": "x", "data": {}, "tenancy": TENANCY},
            headers=headers,
        )

        assert_status_code(response, 403)
        assert response.json() == {"detail": "forbidden"}


class TestOwnerAndPermissions:
    def test_the_owner_sees_everything(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)

        body = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()

        assert body["access"]["level"] == "owner"
        assert body["access"]["can_manage_embargo"] is True
        assert all(v["files_withheld"] is False for v in body["versions"])

    def test_someone_with_no_tenancy_and_a_read_permission_reads_it(self, http_client, owner, outsider):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "read")

        response = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        shared = http_client.get("/datasets/?shared=true", headers=headers)
        update = http_client.put(
            f"/datasets/{dataset['id']}",
            json={"name": "x", "data": {}, "tenancy": TENANCY},
            headers=headers,
        )

        assert_status_code(response, 200)
        assert response.json()["access"]["level"] == "read"
        assert dataset["id"] in _ids(shared)
        assert_status_code(update, 403)

    def test_someone_with_no_tenancy_finds_it_in_every_listing(self, http_client, owner, outsider):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "read")
        version = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()["versions"][0]["name"]

        listing = http_client.get("/datasets/", headers=headers)
        minimal = http_client.get("/datasets/?minimal=true", headers=headers)
        by_version = http_client.get(f"/datasets/{dataset['id']}/versions/{version}", headers=headers)

        assert_status_code(listing, 200)
        assert dataset["id"] in _ids(listing)
        item = next(i for i in minimal.json()["content"] if i["id"] == dataset["id"])
        assert item["embargo"]["active"] is True
        assert item["access"]["level"] == "read"
        assert_status_code(by_version, 200)

    def test_a_write_permission_can_edit_and_does_not_take_ownership(self, http_client, owner, outsider):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "write")

        update = http_client.put(
            f"/datasets/{dataset['id']}",
            json={"name": "edited by collaborator", "data": {}, "tenancy": ""},
            headers=headers,
        )
        as_owner = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()

        assert_status_code(update, 200)
        assert as_owner["name"] == "edited by collaborator"
        assert as_owner["access"]["level"] == "owner"
        assert as_owner["tenancy"] == TENANCY

    def test_a_permission_holder_extends_only_when_the_owner_is_disabled(self, http_client):
        owner_id = create_user(http_client, ["datasets_write"], [TENANCY])
        owner_headers = headers_for(owner_id, TENANCY)
        dataset = create_dataset(http_client, owner_headers)
        set_embargo(http_client, dataset["id"], owner_headers, visible=False, days=10)
        reader_id = create_user(http_client, [], [])
        grant(http_client, dataset["id"], reader_id, "read")
        reader = headers_for(reader_id, None)
        body = {"until": until(60)}

        refused = http_client.post(f"/datasets/{dataset['id']}/embargo/extend", json=body, headers=reader)
        http_client.delete(f"/users/{owner_id}", headers=AuthFixture.valid_headers())
        allowed = http_client.post(f"/datasets/{dataset['id']}/embargo/extend", json=body, headers=reader)

        assert_status_code(refused, 403)
        assert_status_code(allowed, 200)


class TestEmbargoRules:
    def _error(self, response) -> str:
        assert_status_code(response, 400)
        return response.json()["errors"][0]["code"]

    def test_the_cap_applies_on_creation_and_extension(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        assert self._error(set_embargo(http_client, dataset["id"], owner, visible=False, days=91)) == "embargo_too_long"

        set_embargo(http_client, dataset["id"], owner, visible=False, days=10)
        response = http_client.post(
            f"/datasets/{dataset['id']}/embargo/extend",
            json={"until": until(91)},
            headers=owner,
        )
        assert self._error(response) == "embargo_too_long"

    def test_a_date_in_the_past_is_refused(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        response = http_client.put(
            f"/datasets/{dataset['id']}/embargo",
            json={"until": until(-1), "metadata_visible": False},
            headers=owner,
        )
        assert self._error(response) == "embargo_until_in_past"

    def test_a_published_dataset_cannot_be_embargoed(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        assert auto_doi(http_client, dataset, owner).status_code in (200, 201)
        assert_status_code(make_findable(http_client, dataset, owner), 200)

        response = set_embargo(http_client, dataset["id"], owner, visible=False)

        assert self._error(response) == "embargo_dataset_published"

    def test_a_dataset_with_a_manual_doi_cannot_be_embargoed(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        assert manual_doi(http_client, dataset, owner).status_code in (200, 201)

        response = set_embargo(http_client, dataset["id"], owner, visible=False)

        assert self._error(response) == "embargo_manual_doi"

    def test_a_datamap_doi_keeps_the_embargo_and_writes_no_snapshot(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)

        doi = auto_doi(http_client, dataset, owner)
        findable = make_findable(http_client, dataset, owner)
        snapshot = http_client.get(f"/datasets/{dataset['id']}/snapshot")
        body = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()

        assert doi.status_code in (200, 201), doi.text
        assert self._error(findable) == "embargo_active"
        assert_status_code(snapshot, 404)
        assert body["embargo"]["active"] is True


class TestManualDoiUnderEmbargo:
    def _error(self, response) -> str:
        assert_status_code(response, 400)
        return response.json()["errors"][0]["code"]

    def test_it_is_refused_without_confirmation(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)

        response = manual_doi(http_client, dataset, owner)
        snapshot = http_client.get(f"/datasets/{dataset['id']}/snapshot")
        body = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()

        assert self._error(response) == "embargo_manual_doi_ends_embargo"
        assert_status_code(snapshot, 404)
        assert body["embargo"]["active"] is True
        assert body["current_version"]["doi"] is None

    def test_a_write_holder_cannot_end_the_owners_embargo(self, http_client, owner, outsider):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "write")

        response = manual_doi(http_client, dataset, headers, end_embargo=True)
        body = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()

        assert_status_code(response, 403)
        assert body["embargo"]["active"] is True

    def test_the_owner_confirms_and_the_embargo_ends_with_the_snapshot_published(self, http_client, owner, member):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        _, member_headers = member

        response = manual_doi(http_client, dataset, owner, end_embargo=True)
        snapshot = http_client.get(f"/datasets/{dataset['id']}/snapshot")
        body = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()
        as_member = http_client.get(f"/datasets/{dataset['id']}", headers=member_headers)

        assert response.status_code in (200, 201), response.text
        assert_status_code(snapshot, 200)
        assert body["embargo"]["active"] is False
        assert_status_code(as_member, 200)

    def test_ending_early_gives_the_tenancy_its_access_back(self, http_client, owner, member):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        _, headers = member

        ended = http_client.post(f"/datasets/{dataset['id']}/embargo/end", headers=owner)

        assert_status_code(ended, 200)
        assert ended.json()["active"] is False
        assert_status_code(http_client.get(f"/datasets/{dataset['id']}", headers=headers), 200)

    def test_only_the_owner_sets_an_embargo(self, http_client, owner, member):
        dataset = create_dataset(http_client, owner)
        _, headers = member

        assert_status_code(set_embargo(http_client, dataset["id"], headers, visible=False), 403)


class TestEmbargoStatus:
    def test_it_answers_the_client_without_a_user(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)

        response = http_client.get(f"/datasets/{dataset['id']}/embargo-status", headers=client_headers())

        assert_status_code(response, 200)
        assert response.json()["embargoed"] is True
        assert response.json()["until"] is not None

    def test_an_unknown_dataset_reveals_nothing(self, http_client):
        response = http_client.get(f"/datasets/{uuid.uuid4()}/embargo-status", headers=client_headers())

        assert_status_code(response, 200)
        assert response.json() == {"embargoed": False, "until": None}

    def test_it_needs_client_credentials(self, http_client):
        response = http_client.get(f"/datasets/{uuid.uuid4()}/embargo-status")

        assert_status_code(response, 401)
```

- [ ] **Step 3: Make sure the tests fail without the feature**

Run the suite against `origin/main`'s gatekeeper first (stash nothing; build from a checkout of `main` in another worktree, or simply run before Task 6 is merged in your branch):

Run: `make ENV_FILE_PATH=integration-test.env integration-test-run-specific TEST_PATH=tests/integration/test_dataset_embargo.py`
Expected (on main): FAIL — `PUT /datasets/{id}/embargo` answers 404/405. This proves the tests address real routes.

- [ ] **Step 4: Run them against this branch**

```bash
make ENV_FILE_PATH=integration-test.env integration-test-clean
mkdir -p "$(grep STORAGE_DOCKER_VOLUME integration-test.env | cut -d= -f2)_test_integration/datamap"
make ENV_FILE_PATH=integration-test.env integration-test-build
make ENV_FILE_PATH=integration-test.env integration-test-up
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/
```
Expected: `200`. If not, read `docker logs datamap_gatekeeper_test_integration` — a failing migration keeps the container unhealthy.

Seed and wait for Casbin's 5-second reload before running:

```bash
docker exec -i datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db < tests/integration/fixtures/seed_clients.sql
until [ "$(curl -s -o /dev/null -w '%{http_code}' -H 'X-Api-Key: 5060b1a2-9aaf-48db-871a-0839007fd478' -H 'X-Api-Secret: integration-test-not-a-real-secret' -H 'X-User-Id: cbb0a683-630f-4b86-8b45-91b90a6fce1c' http://localhost:9094/api/v1/clients/)" = 200 ]; do sleep 1; done
make ENV_FILE_PATH=integration-test.env integration-test-run-specific TEST_PATH=tests/integration/test_dataset_embargo.py
```
Expected: all tests in `test_dataset_embargo.py` PASS.

- [ ] **Step 5: Run the whole integration suite** (other suites must stay green — dataset, DOI, TUS and snapshot tests all go through the changed lookups)

Run: `make ENV_FILE_PATH=integration-test.env integration-test-run`
Expected: 0 failures. Read the summary line yourself; do not pipe `make` into `tail`.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/fixtures/embargo.py tests/integration/test_dataset_embargo.py
git commit -m "test: embargo access end to end, from tenancy, owner, permission and client"
```

---

### Task 13: Validation loop

- [ ] **Step 1: Unit tests**

Run: `pytest`
Expected: PASS, 0 failures.

- [ ] **Step 2: Integration tests, full cycle**

Run: `make ENV_FILE_PATH=integration-test.env integration-test-full`
Then confirm it really ran: the output must show the pytest summary for `tests/integration/` with `0 failed`, and before it the API answered:

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/` while the stack is up.
Expected: `200`. (`integration-test-full` swallows failures and its readiness wait uses `timeout`, absent on macOS: read the summary, do not trust the exit code.)

- [ ] **Step 3: Lint and format**

Run: `ruff check && ruff check --fix && ruff format`
Expected: `All checks passed!`; `ruff format` reports files left unchanged or reformatted, and `ruff check` passes again after it.

- [ ] **Step 4: Commit any formatting changes**

```bash
git add -u
git commit -m "style: ruff format"
```
(Skip if `git status` shows nothing.)

---

## Self-Review Notes

- Spec coverage: columns/permissions/events (T1), access rule incl. every route (T4, T6), outside-the-tenancy access (T4 role scope, T6 `restrict_by_tenancy=False`, T8 search, T9 role grant, T11 policies), snapshots/DOI (T7), manual DOI ends the embargo only with confirmation and only by the owner (T7), no embargo on a dataset with a manual DOI (T10), download TTL (T7), files withheld (T7), lifecycle/cap/owner-gone extension (T10), audit + metric (T5, T9, T10), the termination seam plan 03 hooks into (T5, used by T7 and T10), embargo-status (T10), owner fix (T6), TUS refusal (T6). Invitations, review links, share routes and notifications are plan 03.
- Natural expiry (`expired` event and its email) is not here: it has no request to hang on, so plan 03's dispatch pass records it.
- Contract delta to raise: `access.can_delete` is computed by the rule (owner; or tenancy member with the delete role when no embargo is active), not "owner only", so today's tenancy deletion keeps working for unembargoed datasets.
