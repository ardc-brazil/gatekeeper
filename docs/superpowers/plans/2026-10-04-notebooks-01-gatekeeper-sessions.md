# Notebooks — Gatekeeper Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the gatekeeper everything increment A of RFC 007 needs from it: notebook and session entities, the session token and the bearer authentication path, the routes the webapp, the hub, the container entrypoint and the archivist call, the seat and quota limits, and the metrics.

**Architecture:** Two services. `NotebookService` owns the notebook rows, the file selection against the 20 GB ceiling, the readability rule (reusing `DatasetService.fetch_authorized`, so embargo and sharing behave exactly as for a download) and the manifest the entrypoint copies from. `NotebookSessionService` owns the session lifecycle: the seat transaction, the quota check, the token, the hub stop call, the internal transitions and the purge listing. A session token is a JWT; `authenticate` learns to accept it as a bearer, the two header parsers read the user and tenancies from its claims, and `authorize` enforces Casbin with the `notebook_session` subject so a token can only reach read routes. The gatekeeper never writes to the notebooks volume: it reads it (quota, content, manifest's `notebook_exists`) through a read-only mount.

**Tech Stack:** Python 3.10 (production image `python:3.10.14-alpine`), FastAPI 0.111, SQLAlchemy 1.4.23, Alembic, dependency-injector 4.41, Casbin 1.23, PyJWT 2.8, prometheus-client, requests, pytest, unittest.mock, integration tests against Docker (PostgreSQL, MinIO, WireMock).

**Spec:** `docs/rfcs/007-notebooks.md` (§Session lifecycle, §Data in the session, §Session token and SDK authentication, §Data model, §Routes, §Limits, §Observability, §Testing). **Contracts:** `docs/superpowers/plans/2026-10-04-notebooks-00-contracts.md` (wins over this plan on any interface).

## Global Constraints

- Migration revision id `b8c9d0e1f2a3`, `down_revision = "c3d4e5f6a7b8"` (RFC 009's tenancy requests migration, the head of `main` on 2026-10-08; confirm with the head computation in Task 2 before writing the file). Never re-pointed. The migration also inserts the Casbin policy rows, guarded by `WHERE NOT EXISTS`.
- Settings and defaults exactly as the contracts list them: `AUTH_NOTEBOOK_SESSION_TOKEN_SECRET` (required), `NOTEBOOK_SEATS=4`, `NOTEBOOK_SESSION_MAX_HOURS=12`, `NOTEBOOK_DATA_MAX_BYTES=21474836480`, `NOTEBOOK_STORAGE_QUOTA_BYTES=2147483648`, `NOTEBOOK_STORAGE_PATH=/storage/notebooks`, `NOTEBOOK_OUTPUTS_RETENTION_HOURS=24`, `NOTEBOOK_HUB_URL=http://datamap_jupyterhub:8000/hub`, `NOTEBOOK_HUB_API_TOKEN=""`, `NOTEBOOK_HUB_TIMEOUT_SECONDS=5`.
- Error codes exactly: `version_not_published`, `name_taken`, `selection_too_large`, `file_not_in_version`, `session_running`, `session_elsewhere`, `storage_full`, `no_seats`, `hub_unavailable`, `content_not_written`. Status codes per the contracts table.
- Version names are strings. Mount path inside the container is `/data/{dataset_id}/{version_name}`.
- A bearer token reaches only: `GET /datasets/{id}`, `GET /datasets/{id}/versions/{v}`, `GET /datasets/{id}/versions/{v}/files/{file_id}`, `GET /notebooks/{id}/manifest`, `POST /notebooks/{id}/session/progress`. Everything else answers 401 to it.
- The gatekeeper never writes under `NOTEBOOK_STORAGE_PATH`. The mount is `:ro` in every compose file.
- Seat count is taken under `pg_advisory_xact_lock(4915624)` in the same transaction as the insert. (The RFC said a one-row table; the lock replaces it — Task 11 amends the RFC.)
- Stop reason derivation when the hub sends none: `stop_requested` on the row if set, else `max_age` when `now - started_at >= NOTEBOOK_SESSION_MAX_HOURS`, else `idle`.
- `notebook_sessions` is append-only: rows are never deleted; `notebook_id` is `ON DELETE SET NULL`; `dataset_id` has no FK.
- Metrics: `datamap_notebook_sessions_active{kernel}`, `datamap_notebook_session_requests_total{outcome}`, `datamap_notebook_session_duration_seconds{stop_reason}`.
- The production image is `python:3.10.14-alpine`: no syntax newer than 3.10. `X | None` annotations are fine.
- Code style (CLAUDE.md): no narrating comments; one-line comment only where a reader would otherwise undo something on purpose. Type hints everywhere. Dataclasses for domain models. Test files `module_test.py` next to the module.
- Integration tests are mandatory: this plan changes `app/controller/interceptor/`, `app/repository/`, route paths, status codes and Casbin seed data. Never pipe `make` into `tail`/`grep` and read the exit code. Confirm `curl -s -o /dev/null -w "%{http_code}" http://localhost:9094/api/v1/health-check/` answers 200 before trusting a run.
- Run from the worktree root. The `.venv` at `gatekeeper/.venv` works from a worktree: `../../../.venv/bin/python -m pytest`.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `app/model/notebook.py` (+ `notebook_test.py`) | create | Enums, constants, domain dataclasses, `slug_name`, `mount_path`, `lab_path` |
| `app/model/db/notebook.py` | create | `Notebook`, `NotebookDataset`, `NotebookSession` ORM models |
| `app/model/db/user.py` | modify | `notebook_storage_bytes` column |
| `migrations/versions/2026_10_04_1200-b8c9d0e1f2a3_add_notebooks.py` | create | Schema plus Casbin rows |
| `migrations/env.py` | modify | Import `app.model.db.notebook` |
| `app/exception/refused.py` | create | `RefusedException(status_code, code, **extra)` |
| `app/controller/interceptor/exception_handler.py`, `app/setup.py` | modify | Handler for `RefusedException`; register routers |
| `app/config.py`, `local.env.template`, `integration-test.env`, `app/config_email_test.py` | modify | Settings |
| `app/repository/notebook.py` | create | `NotebookRepository` |
| `app/repository/notebook_session.py` | create | `NotebookSessionRepository`, the seat transaction |
| `app/repository/user.py` | modify | `set_notebook_storage_bytes` |
| `app/service/notebook_token.py` (+ `_test.py`) | create | `NotebookTokenService.mint / verify` |
| `app/service/notebook_storage.py` (+ `_test.py`) | create | `NotebookStorage`: usage, exists, read, over the read-only mount |
| `app/gateway/jupyterhub/__init__.py`, `hub_client.py` (+ `_test.py`) | create | `HubClient.stop_server` |
| `app/service/notebook_session_auth.py` (+ `_test.py`) | create | `NotebookSessionAuth.authenticate(token) -> SessionClaims`, token plus live row |
| `app/controller/interceptor/authentication.py`, `user_parser.py` (+ `_test.py`), `tenancy_parser.py` (+ `_test.py`), `authorization.py` | modify | Bearer path |
| `app/service/dataset.py` | modify | `file_url(file, expires_in)` extracted from `get_file_download_url` |
| `app/service/notebook.py` (+ `_test.py`) | create | `NotebookService` |
| `app/service/notebook_session.py` (+ `_test.py`) | create | `NotebookSessionService` |
| `app/metrics.py`, `app/metrics_test.py` | modify | Three notebook metrics; `session_not_live` auth reason |
| `app/controller/v1/notebook/__init__.py`, `notebook.py`, `resource.py` | create | User and bearer routes |
| `app/controller/v1/internal/notebook_session.py`, `internal/resource.py` | create / modify | Hub and archivist routes |
| `app/container.py` | modify | Providers and wiring |
| `app/resources/casbin_seed_policies.sql` | modify | Policy rows, for reference; the migration is what inserts them |
| `docker-compose-integration-test.yaml` | modify | Read-only storage mount on the gatekeeper; `storage_helper_test_integration` |
| `tests/integration/wiremock/mappings/hub_stop_server.json` | create | Hub stub |
| `tests/integration/fixtures/notebooks.py`, `tests/integration/test_notebooks_api.py` | create | Integration tests |
| `docs/rfcs/007-notebooks.md` | modify | Amendments where execution diverged |

---

### Task 1: Settings, domain model and the refusal exception

**Files:**
- Modify: `app/config.py` (after `BUILD_COMMIT`)
- Modify: `local.env.template`, `integration-test.env`, `app/config_email_test.py`
- Create: `app/model/notebook.py`, `app/model/notebook_test.py`
- Create: `app/exception/refused.py`
- Modify: `app/controller/interceptor/exception_handler.py`, `app/setup.py`

**Interfaces:**
- Produces: `Kernel`, `SessionState`, `LIVE_STATES`, `StopReason`, `SESSION_ROLE`, `TOKEN_AUDIENCE`, `TOKEN_ISSUER`, `TOKEN_GRACE`, `MANIFEST_URL_TTL`, `PROGRESS_KEEP`, `PROGRESS_LINE_MAX`, `OUTPUTS_MOUNT`, `DATA_MOUNT`, `SEAT_LOCK_KEY`, `NAME_PATTERN`; dataclasses `NotebookDataset`, `NotebookSession`, `Notebook`, `SessionClaims`, `SessionStart`, `Capacity`, `ManifestFile`, `ManifestDataset`, `Manifest`, `Purgeable`; functions `slug_name(title) -> str`, `mount_path(dataset_id, version_name) -> str`, `lab_path(user_id, path) -> str`; `RefusedException(status_code, code, **extra)`; settings listed in Global Constraints.

- [ ] **Step 1: Write the failing model tests**

`app/model/notebook_test.py`:

```python
import unittest
from uuid import uuid4

from app.model.notebook import (
    LIVE_STATES,
    NAME_PATTERN,
    SessionState,
    lab_path,
    mount_path,
    slug_name,
)


class TestSlugName(unittest.TestCase):
    def test_lower_cases_and_replaces_runs_of_non_alphanumerics(self):
        self.assertEqual(
            slug_name("GoAmazon 2014/5 — Aerosol, T3 site"),
            "goamazon_2014_5_aerosol_t3_site",
        )

    def test_cuts_at_forty_characters(self):
        self.assertEqual(len(slug_name("a" * 100)), 40)

    def test_empty_title_falls_back_to_notebook(self):
        self.assertEqual(slug_name(""), "notebook")
        self.assertEqual(slug_name("—"), "notebook")

    def test_a_slug_satisfies_the_name_pattern(self):
        self.assertIsNotNone(NAME_PATTERN.match(slug_name("Ünïcode, title!")))


class TestPaths(unittest.TestCase):
    def test_mount_path_is_data_dataset_version(self):
        dataset_id = uuid4()
        self.assertEqual(mount_path(dataset_id, "2"), f"/data/{dataset_id}/2")

    def test_lab_path_opens_the_notebook_in_the_users_server(self):
        user_id = uuid4()
        self.assertEqual(
            lab_path(user_id, "x.ipynb"), f"/user/{user_id}/lab/tree/x.ipynb"
        )


class TestStates(unittest.TestCase):
    def test_live_states_are_starting_and_running(self):
        self.assertEqual(LIVE_STATES, (SessionState.STARTING, SessionState.RUNNING))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `../../../.venv/bin/python -m pytest app/model/notebook_test.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.model.notebook'`

- [ ] **Step 3: Write the domain model**

`app/model/notebook.py`:

```python
import enum
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID


class Kernel(str, enum.Enum):
    PYTHON = "python3"
    R = "ir"


class SessionState(str, enum.Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    ENDED = "ended"
    FAILED = "failed"


LIVE_STATES = (SessionState.STARTING, SessionState.RUNNING)


class StopReason(str, enum.Enum):
    IDLE = "idle"
    USER = "user"
    ADMIN = "admin"
    MAX_AGE = "max_age"
    SPAWN_ERROR = "spawn_error"


SESSION_ROLE = "notebook_session"
TOKEN_AUDIENCE = "notebook_session"
TOKEN_ISSUER = "gatekeeper"
TOKEN_GRACE = timedelta(minutes=10)
MANIFEST_URL_TTL = timedelta(hours=1)
PROGRESS_KEEP = 50
PROGRESS_LINE_MAX = 200
OUTPUTS_MOUNT = "/outputs"
DATA_MOUNT = "/data"
# Arbitrary but fixed, and distinct from MIGRATION_LOCK_KEY in app/database.py.
SEAT_LOCK_KEY = 4915624
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
NAME_MAX = 40


def slug_name(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", (title or "").lower()).strip("_")[:NAME_MAX]
    return base.strip("_") or "notebook"


def mount_path(dataset_id: UUID, version_name: str) -> str:
    return f"{DATA_MOUNT}/{dataset_id}/{version_name}"


def lab_path(user_id: UUID, path: str) -> str:
    return f"/user/{user_id}/lab/tree/{path}"


@dataclass
class NotebookDataset:
    dataset_id: UUID | None
    version_name: str | None
    file_ids: list[UUID] | None = None
    position: int = 0
    title: str | None = None
    source_deleted: bool = False
    mounted_files: int = 0
    mounted_bytes: int = 0


@dataclass
class NotebookSession:
    id: UUID
    notebook_id: UUID | None
    user_id: UUID
    tenancy: str
    kernel: Kernel
    state: SessionState
    dataset_id: UUID | None = None
    dataset_version: str | None = None
    mounted_files: int = 0
    mounted_bytes: int = 0
    requested_at: datetime | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    stop_reason: StopReason | None = None
    stop_requested: StopReason | None = None
    progress: list[str] = field(default_factory=list)


@dataclass
class Notebook:
    id: UUID
    owner_id: UUID
    name: str
    path: str
    kernel: Kernel
    size_bytes: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    datasets: list[NotebookDataset] = field(default_factory=list)
    session: NotebookSession | None = None

    @property
    def dataset(self) -> NotebookDataset | None:
        return self.datasets[0] if self.datasets else None

    @property
    def mounted_files(self) -> int:
        return sum(d.mounted_files for d in self.datasets)

    @property
    def mounted_bytes(self) -> int:
        return sum(d.mounted_bytes for d in self.datasets)


@dataclass
class SessionClaims:
    user_id: UUID
    tenancies: list[str]
    notebook_id: UUID
    session_id: UUID
    datasets: list[dict]
    kernel: Kernel
    locale: str


@dataclass
class SessionStart:
    session: NotebookSession
    token: str
    login_url: str
    lab_path: str
    resumed: bool


@dataclass
class Capacity:
    seats_taken: int
    seats_total: int
    storage_used_bytes: int
    storage_quota_bytes: int
    data_max_bytes: int


@dataclass
class ManifestFile:
    id: UUID
    name: str
    size_bytes: int
    relative_path: str
    url: str


@dataclass
class ManifestDataset:
    dataset_id: UUID
    dataset_title: str
    version_name: str
    mount_path: str
    file_count: int
    total_bytes: int
    files: list[ManifestFile]


@dataclass
class Manifest:
    notebook_id: UUID
    notebook_path: str
    notebook_exists: bool
    kernel: Kernel
    outputs_path: str
    datasets: list[ManifestDataset]


@dataclass
class Purgeable:
    sessions: list[dict]
    outputs: list[dict]
    notebooks: list[dict]
```

- [ ] **Step 4: Run the model tests**

Run: `../../../.venv/bin/python -m pytest app/model/notebook_test.py -q`
Expected: 7 passed

- [ ] **Step 5: Add the refusal exception and its handler**

`app/exception/refused.py`:

```python
class RefusedException(Exception):
    def __init__(self, status_code: int, code: str, **extra: object) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.extra = extra
```

In `app/controller/interceptor/exception_handler.py`, add the import and the handler after `bad_request_exception_handler`:

```python
from app.exception.refused import RefusedException
```

```python
async def refused_exception_handler(request: Request, exc: RefusedException):
    logger.info(f"Refused: {exc.code}")
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.code, **exc.extra}
    )
```

In `app/setup.py`, import `RefusedException` and `refused_exception_handler`, and in `setup_error_handlers` add before the generic one:

```python
    fastAPIApp.add_exception_handler(RefusedException, refused_exception_handler)
```

- [ ] **Step 6: Write the handler test**

Append to `app/controller/interceptor/exception_handler_test.py`:

```python
import json

from app.controller.interceptor.exception_handler import refused_exception_handler
from app.exception.refused import RefusedException


class TestRefusedHandler(unittest.IsolatedAsyncioTestCase):
    async def test_answers_the_status_and_the_code_with_the_extras(self):
        response = await refused_exception_handler(
            None, RefusedException(429, "no_seats", seats_total=4)
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(
            json.loads(response.body), {"detail": "no_seats", "seats_total": 4}
        )
```

(Keep the file's existing `import unittest`; add `import json` next to it if absent.)

Run: `../../../.venv/bin/python -m pytest app/controller/interceptor/exception_handler_test.py -q`
Expected: all passed, including the new one

- [ ] **Step 7: Add the settings**

In `app/config.py`, after `BUILD_COMMIT`:

```python
    AUTH_NOTEBOOK_SESSION_TOKEN_SECRET: str = Field(
        ..., description="HS256 key for notebook session tokens, shared with the hub"
    )
    NOTEBOOK_SEATS: int = Field(4, description="Concurrent live notebook sessions")
    NOTEBOOK_SESSION_MAX_HOURS: int = Field(12, description="Hard session limit")
    NOTEBOOK_DATA_MAX_BYTES: int = Field(
        20 * 1024**3, description="Largest file selection a session mounts"
    )
    NOTEBOOK_STORAGE_QUOTA_BYTES: int = Field(
        2 * 1024**3, description="Notebook storage per user"
    )
    NOTEBOOK_STORAGE_PATH: str = Field(
        "/storage/notebooks", description="Read-only mount of notebooks/"
    )
    NOTEBOOK_OUTPUTS_RETENTION_HOURS: int = Field(
        24, description="Outputs kept after the last session ends"
    )
    NOTEBOOK_HUB_URL: str = Field(
        "http://datamap_jupyterhub:8000/hub", description="JupyterHub, docker network"
    )
    NOTEBOOK_HUB_API_TOKEN: str = Field(
        "", description="Hub admin API token; empty makes stop calls fail closed"
    )
    NOTEBOOK_HUB_TIMEOUT_SECONDS: float = Field(
        5, description="Connect and read timeout for hub calls"
    )
```

Append to `local.env.template`:

```
# Notebooks (RFC 007)
AUTH_NOTEBOOK_SESSION_TOKEN_SECRET=local-notebook-session-secret
NOTEBOOK_HUB_API_TOKEN=
```

Append to `integration-test.env`:

```
# Notebooks (RFC 007)
AUTH_NOTEBOOK_SESSION_TOKEN_SECRET=notebook-session-fake-secret
NOTEBOOK_SEATS=2
NOTEBOOK_DATA_MAX_BYTES=4096
NOTEBOOK_STORAGE_QUOTA_BYTES=2097152
NOTEBOOK_STORAGE_PATH=/storage/notebooks
NOTEBOOK_HUB_URL=http://datamap_wiremock_test_integration:8080/hub
NOTEBOOK_HUB_API_TOKEN=integration-hub-token
```

In `app/config_email_test.py`, add to `REQUIRED`:

```python
    "AUTH_NOTEBOOK_SESSION_TOKEN_SECRET": "secret",
```

Add the same line to your own `local.env` (not committed).

- [ ] **Step 8: Run the whole unit suite**

Run: `../../../.venv/bin/python -m pytest -q`
Expected: all passed (the required setting is present in `local.env`, the template and the config test)

- [ ] **Step 9: Commit**

```bash
git add app/model/notebook.py app/model/notebook_test.py app/exception/refused.py \
  app/controller/interceptor/exception_handler.py app/controller/interceptor/exception_handler_test.py \
  app/setup.py app/config.py app/config_email_test.py local.env.template integration-test.env
git commit -m "feat(notebooks): settings, domain model and the refusal exception

RFC 007 increment A. The refusal exception carries the 413/429/503 answers
the notebook routes need and that no existing handler produces."
```

---

### Task 2: Database models and migration

**Files:**
- Create: `app/model/db/notebook.py`
- Modify: `app/model/db/user.py`
- Create: `migrations/versions/2026_10_04_1200-b8c9d0e1f2a3_add_notebooks.py`
- Modify: `migrations/env.py`
- Modify: `app/resources/casbin_seed_policies.sql`

**Interfaces:**
- Produces: ORM classes `Notebook`, `NotebookDataset`, `NotebookSession` in `app/model/db/notebook.py` with the columns below; `User.notebook_storage_bytes`.

- [ ] **Step 1: Write the ORM models**

`app/model/db/notebook.py`:

```python
import sqlalchemy
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Notebook(Base):
    __tablename__ = "notebooks"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(128), nullable=False)
    path = Column(String(512), nullable=False)
    kernel = Column(String(16), nullable=False)
    size_bytes = Column(BigInteger, nullable=False, default=0, server_default="0")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    file_purged_at = Column(DateTime(timezone=True), nullable=True)
    outputs_purged_at = Column(DateTime(timezone=True), nullable=True)

    datasets = relationship(
        "NotebookDataset",
        lazy="joined",
        order_by="NotebookDataset.position",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uc_notebooks_owner_name"),
        Index("idx_notebooks_owner", "owner_id"),
    )


class NotebookDataset(Base):
    __tablename__ = "notebook_datasets"
    notebook_id = Column(
        UUID(as_uuid=True),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    position = Column(SmallInteger, primary_key=True, default=0)
    dataset_id = Column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True
    )
    dataset_version = Column(String(256), nullable=True)
    file_ids = Column(JSONB, nullable=True)
    mounted_files = Column(Integer, nullable=False, default=0, server_default="0")
    mounted_bytes = Column(BigInteger, nullable=False, default=0, server_default="0")

    dataset = relationship("Dataset", lazy="joined")


class NotebookSession(Base):
    __tablename__ = "notebook_sessions"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    notebook_id = Column(
        UUID(as_uuid=True), ForeignKey("notebooks.id", ondelete="SET NULL"), nullable=True
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    tenancy = Column(String(256), nullable=False)
    dataset_id = Column(UUID(as_uuid=True), nullable=True)
    dataset_version = Column(String(256), nullable=True)
    kernel = Column(String(16), nullable=False)
    state = Column(String(16), nullable=False)
    mounted_files = Column(Integer, nullable=False, default=0, server_default="0")
    mounted_bytes = Column(BigInteger, nullable=False, default=0, server_default="0")
    requested_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    stopped_at = Column(DateTime(timezone=True), nullable=True)
    stop_reason = Column(String(32), nullable=True)
    stop_requested = Column(String(32), nullable=True)
    progress = Column(JSONB, nullable=True)
    data_purged_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "idx_notebook_sessions_live",
            "user_id",
            postgresql_where=sqlalchemy.text("state IN ('starting', 'running')"),
        ),
        Index(
            "idx_notebook_sessions_dataset",
            "dataset_id",
            sqlalchemy.text("requested_at DESC"),
        ),
        Index(
            "idx_notebook_sessions_notebook",
            "notebook_id",
            sqlalchemy.text("requested_at DESC"),
        ),
    )
```

In `app/model/db/user.py`, add `BigInteger` to the `sqlalchemy` import and, after `updated_at` on `User`:

```python
    notebook_storage_bytes = Column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
```

In `migrations/env.py`, after the `sharing` import:

```python
from app.model.db import notebook  # noqa: E402, F401
```

- [ ] **Step 2: Write the migration**

`migrations/versions/2026_10_04_1200-b8c9d0e1f2a3_add_notebooks.py`:

```python
"""Add notebooks

Revision ID: b8c9d0e1f2a3
Revises: c3d4e5f6a7b8
Create Date: 2026-10-04 12:00:00

"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None

POLICIES = [
    ("notebook_session", "/api/v1/datasets/[0-9a-f-]{36}$", "GET"),
    ("notebook_session", "/api/v1/datasets/[0-9a-f-]{36}/versions/[^/]+$", "GET"),
    (
        "notebook_session",
        "/api/v1/datasets/[0-9a-f-]{36}/versions/[^/]+/files/[0-9a-f-]{36}$",
        "GET",
    ),
    ("notebook_session", "/api/v1/notebooks/[0-9a-f-]{36}/manifest$", "GET"),
    ("notebook_session", "/api/v1/notebooks/[0-9a-f-]{36}/session/progress$", "POST"),
    ("notebooks_user", "/api/v1/notebooks(/.*)?$", "(GET|POST|PATCH|DELETE)"),
]

INSERT_POLICY = sa.text(
    "INSERT INTO casbin_rule (ptype, v0, v1, v2, v3) "
    "SELECT 'p', :subject, :object, :action, 'allow' "
    "WHERE NOT EXISTS (SELECT 1 FROM casbin_rule "
    "WHERE ptype = 'p' AND v0 = :subject AND v1 = :object AND v2 = :action)"
)

DELETE_POLICY = sa.text(
    "DELETE FROM casbin_rule "
    "WHERE ptype = 'p' AND v0 = :subject AND v1 = :object AND v2 = :action"
)


def upgrade() -> None:
    op.create_table(
        "notebooks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("kernel", sa.String(length=16), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outputs_purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uc_notebooks_owner_name"),
    )
    op.create_index("idx_notebooks_owner", "notebooks", ["owner_id"])

    op.create_table(
        "notebook_datasets",
        sa.Column("notebook_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dataset_version", sa.String(length=256), nullable=True),
        sa.Column("file_ids", postgresql.JSONB(), nullable=True),
        sa.Column("mounted_files", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "mounted_bytes", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebooks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("notebook_id", "position"),
    )

    op.create_table(
        "notebook_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("notebook_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenancy", sa.String(length=256), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dataset_version", sa.String(length=256), nullable=True),
        sa.Column("kernel", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("mounted_files", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "mounted_bytes", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_reason", sa.String(length=32), nullable=True),
        sa.Column("stop_requested", sa.String(length=32), nullable=True),
        sa.Column("progress", postgresql.JSONB(), nullable=True),
        sa.Column("data_purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebooks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_notebook_sessions_live",
        "notebook_sessions",
        ["user_id"],
        postgresql_where=sa.text("state IN ('starting', 'running')"),
    )
    op.create_index(
        "idx_notebook_sessions_dataset",
        "notebook_sessions",
        ["dataset_id", sa.text("requested_at DESC")],
    )
    op.create_index(
        "idx_notebook_sessions_notebook",
        "notebook_sessions",
        ["notebook_id", sa.text("requested_at DESC")],
    )

    op.add_column(
        "users",
        sa.Column(
            "notebook_storage_bytes", sa.BigInteger(), server_default="0", nullable=False
        ),
    )

    for subject, obj, action in POLICIES:
        op.execute(INSERT_POLICY.bindparams(subject=subject, object=obj, action=action))


def downgrade() -> None:
    for subject, obj, action in POLICIES:
        op.execute(DELETE_POLICY.bindparams(subject=subject, object=obj, action=action))
    op.drop_column("users", "notebook_storage_bytes")
    op.drop_index("idx_notebook_sessions_notebook", table_name="notebook_sessions")
    op.drop_index("idx_notebook_sessions_dataset", table_name="notebook_sessions")
    op.drop_index("idx_notebook_sessions_live", table_name="notebook_sessions")
    op.drop_table("notebook_sessions")
    op.drop_table("notebook_datasets")
    op.drop_index("idx_notebooks_owner", table_name="notebooks")
    op.drop_table("notebooks")
```

- [ ] **Step 3: Seed files**

Append to `app/resources/casbin_seed_policies.sql` (one line per policy, in the file's format):

```sql
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'notebook_session', '/api/v1/datasets/[0-9a-f-]{36}$', 'GET', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'notebook_session', '/api/v1/datasets/[0-9a-f-]{36}/versions/[^/]+$', 'GET', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'notebook_session', '/api/v1/datasets/[0-9a-f-]{36}/versions/[^/]+/files/[0-9a-f-]{36}$', 'GET', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'notebook_session', '/api/v1/notebooks/[0-9a-f-]{36}/manifest$', 'GET', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'notebook_session', '/api/v1/notebooks/[0-9a-f-]{36}/session/progress$', 'POST', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'notebooks_user', '/api/v1/notebooks(/.*)?$', '(GET|POST|PATCH|DELETE)', 'allow', NULL, NULL);
```

Leave `tests/integration/fixtures/seed_clients.sql` unchanged: the migration inserts these rows before the seed runs, and Task 9 checks that `SELECT count(*) FROM casbin_rule WHERE v0 = 'notebook_session'` is 5 after both.

- [ ] **Step 4: Verify the migration applies and the models match it**

Start the local database and apply:

```bash
make ENV_FILE_PATH=local.env docker-run-db
make ENV_FILE_PATH=local.env db-upgrade
```

Expected: `Running upgrade c3d4e5f6a7b8 -> b8c9d0e1f2a3, Add notebooks`.

Then check autogenerate proposes nothing:

```bash
make ENV_FILE_PATH=local.env MESSAGE="notebooks drift check" db-create-migration
```

Expected: the generated file's `upgrade()` contains only `pass`. Delete that generated file. If it contains operations, fix the ORM model (not the migration) until it is empty.

Downgrade and upgrade once to prove the pair:

```bash
make ENV_FILE_PATH=local.env db-downgrade
make ENV_FILE_PATH=local.env db-upgrade
```

- [ ] **Step 5: Run the unit suite**

Run: `../../../.venv/bin/python -m pytest -q`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add app/model/db/notebook.py app/model/db/user.py migrations/env.py \
  migrations/versions/2026_10_04_1200-b8c9d0e1f2a3_add_notebooks.py \
  app/resources/casbin_seed_policies.sql
git commit -m "feat(notebooks): notebook, dataset-link and session tables

notebook_sessions is append-only and outlives both the notebook and the
dataset: it is the usage record. notebook_datasets takes a list so a second
dataset later is a UI change, not a migration. The migration also inserts the
Casbin rows for the session subject and the notebooks_user role, guarded so a
re-run or the test seed cannot duplicate them."
```

---

### Task 3: Repositories

**Files:**
- Create: `app/repository/notebook.py`
- Create: `app/repository/notebook_session.py`
- Modify: `app/repository/user.py`

**Interfaces:**
- Consumes: ORM models from Task 2; `SEAT_LOCK_KEY`, `LIVE_STATES`, `PROGRESS_KEEP` from Task 1.
- Produces:
  - `NotebookRepository(session_factory)`: `insert(notebook) -> Notebook`, `fetch(id, include_deleted=False) -> Notebook | None`, `list_for_owner(owner_id, dataset_id=None) -> list[Notebook]`, `name_exists(owner_id, name) -> bool`, `save(notebook) -> Notebook`, `soft_delete(id) -> None`, `list_deleted_unpurged() -> list[Notebook]`, `list_outputs_purgeable(before: datetime) -> list[Notebook]`, `mark_file_purged(id)`, `mark_outputs_purged(id)`.
  - `NotebookSessionRepository(session_factory)`: `start_if_seat_available(session, seats_total) -> NotebookSession | None`, `fetch(id) -> NotebookSession | None`, `live_for_user(user_id) -> NotebookSession | None`, `latest_for_notebook(notebook_id) -> NotebookSession | None`, `count_live() -> int`, `live_count_by_kernel() -> dict[str, int]`, `set_state(id, state, started_at=None, stopped_at=None, stop_reason=None) -> NotebookSession | None`, `set_stop_requested(id, reason) -> None`, `append_progress(id, line) -> None`, `list_unpurged_not_live() -> list[NotebookSession]`, `mark_data_purged(id) -> None`.
  - `UserRepository.set_notebook_storage_bytes(user_id, size_bytes) -> None`.

Repositories here have no unit tests (they are SQL; the integration suite in Task 10 is what proves them), which is the existing convention for `tenancy.py`, `permission.py` and the rest.

- [ ] **Step 1: Write `NotebookRepository`**

`app/repository/notebook.py`:

```python
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable
from uuid import UUID

from sqlalchemy import and_, exists, func, or_
from sqlalchemy.orm import Session

from app.model.db.notebook import (
    Notebook as NotebookDBModel,
    NotebookDataset as NotebookDatasetDBModel,
    NotebookSession as NotebookSessionDBModel,
)
from app.model.notebook import LIVE_STATES


class NotebookRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def insert(self, notebook: NotebookDBModel) -> NotebookDBModel:
        with self._session_factory() as session:
            session.add(notebook)
            session.commit()
            session.refresh(notebook)
            return notebook

    def fetch(self, id: UUID, include_deleted: bool = False) -> NotebookDBModel | None:
        with self._session_factory() as session:
            query = session.query(NotebookDBModel).filter(NotebookDBModel.id == id)
            if not include_deleted:
                query = query.filter(NotebookDBModel.deleted_at.is_(None))
            return query.one_or_none()

    def list_for_owner(
        self, owner_id: UUID, dataset_id: UUID | None = None
    ) -> list[NotebookDBModel]:
        with self._session_factory() as session:
            query = session.query(NotebookDBModel).filter(
                NotebookDBModel.owner_id == owner_id,
                NotebookDBModel.deleted_at.is_(None),
            )
            if dataset_id is not None:
                query = query.filter(
                    exists().where(
                        and_(
                            NotebookDatasetDBModel.notebook_id == NotebookDBModel.id,
                            NotebookDatasetDBModel.dataset_id == dataset_id,
                        )
                    )
                )
            return query.order_by(NotebookDBModel.updated_at.desc()).all()

    def name_exists(self, owner_id: UUID, name: str) -> bool:
        with self._session_factory() as session:
            return session.query(
                exists().where(
                    and_(
                        NotebookDBModel.owner_id == owner_id,
                        NotebookDBModel.name == name,
                        NotebookDBModel.deleted_at.is_(None),
                    )
                )
            ).scalar()

    def save(self, notebook: NotebookDBModel) -> NotebookDBModel:
        with self._session_factory() as session:
            merged = session.merge(notebook)
            session.commit()
            session.refresh(merged)
            return merged

    def soft_delete(self, id: UUID) -> None:
        with self._session_factory() as session:
            session.query(NotebookDBModel).filter(
                NotebookDBModel.id == id, NotebookDBModel.deleted_at.is_(None)
            ).update({NotebookDBModel.deleted_at: func.now()})
            session.commit()

    def list_deleted_unpurged(self) -> list[NotebookDBModel]:
        with self._session_factory() as session:
            return (
                session.query(NotebookDBModel)
                .filter(
                    NotebookDBModel.deleted_at.isnot(None),
                    NotebookDBModel.file_purged_at.is_(None),
                )
                .all()
            )

    def list_outputs_purgeable(self, before: datetime) -> list[NotebookDBModel]:
        """Notebooks with no live session whose last session stopped before `before`
        and whose outputs were not purged since that stop."""
        with self._session_factory() as session:
            last_stop = (
                session.query(
                    NotebookSessionDBModel.notebook_id.label("notebook_id"),
                    func.max(NotebookSessionDBModel.stopped_at).label("stopped_at"),
                )
                .filter(NotebookSessionDBModel.stopped_at.isnot(None))
                .group_by(NotebookSessionDBModel.notebook_id)
                .subquery()
            )
            live = exists().where(
                and_(
                    NotebookSessionDBModel.notebook_id == NotebookDBModel.id,
                    NotebookSessionDBModel.state.in_([s.value for s in LIVE_STATES]),
                )
            )
            return (
                session.query(NotebookDBModel)
                .join(last_stop, last_stop.c.notebook_id == NotebookDBModel.id)
                .filter(
                    ~live,
                    last_stop.c.stopped_at < before,
                    or_(
                        NotebookDBModel.outputs_purged_at.is_(None),
                        NotebookDBModel.outputs_purged_at < last_stop.c.stopped_at,
                    ),
                )
                .all()
            )

    def mark_file_purged(self, id: UUID) -> None:
        with self._session_factory() as session:
            session.query(NotebookDBModel).filter(NotebookDBModel.id == id).update(
                {NotebookDBModel.file_purged_at: func.now()}
            )
            session.commit()

    def mark_outputs_purged(self, id: UUID) -> None:
        with self._session_factory() as session:
            session.query(NotebookDBModel).filter(NotebookDBModel.id == id).update(
                {NotebookDBModel.outputs_purged_at: func.now()}
            )
            session.commit()
```

- [ ] **Step 2: Write `NotebookSessionRepository`**

`app/repository/notebook_session.py`:

```python
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable
from uuid import UUID

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.model.db.notebook import NotebookSession as NotebookSessionDBModel
from app.model.notebook import (
    LIVE_STATES,
    PROGRESS_KEEP,
    PROGRESS_LINE_MAX,
    SEAT_LOCK_KEY,
    SessionState,
    StopReason,
)

LIVE_VALUES = [state.value for state in LIVE_STATES]


class NotebookSessionRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def start_if_seat_available(
        self, session: NotebookSessionDBModel, seats_total: int
    ) -> NotebookSessionDBModel | None:
        with self._session_factory() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SEAT_LOCK_KEY})
            live = (
                db.query(func.count(NotebookSessionDBModel.id))
                .filter(NotebookSessionDBModel.state.in_(LIVE_VALUES))
                .scalar()
            )
            if live >= seats_total:
                db.rollback()
                return None
            db.add(session)
            db.commit()
            db.refresh(session)
            return session

    def fetch(self, id: UUID) -> NotebookSessionDBModel | None:
        with self._session_factory() as db:
            return (
                db.query(NotebookSessionDBModel)
                .filter(NotebookSessionDBModel.id == id)
                .one_or_none()
            )

    def live_for_user(self, user_id: UUID) -> NotebookSessionDBModel | None:
        with self._session_factory() as db:
            return (
                db.query(NotebookSessionDBModel)
                .filter(
                    NotebookSessionDBModel.user_id == user_id,
                    NotebookSessionDBModel.state.in_(LIVE_VALUES),
                )
                .order_by(NotebookSessionDBModel.requested_at.desc())
                .first()
            )

    def latest_for_notebook(self, notebook_id: UUID) -> NotebookSessionDBModel | None:
        with self._session_factory() as db:
            return (
                db.query(NotebookSessionDBModel)
                .filter(NotebookSessionDBModel.notebook_id == notebook_id)
                .order_by(NotebookSessionDBModel.requested_at.desc())
                .first()
            )

    def count_live(self) -> int:
        with self._session_factory() as db:
            return (
                db.query(func.count(NotebookSessionDBModel.id))
                .filter(NotebookSessionDBModel.state.in_(LIVE_VALUES))
                .scalar()
            )

    def live_count_by_kernel(self) -> dict[str, int]:
        with self._session_factory() as db:
            rows = (
                db.query(
                    NotebookSessionDBModel.kernel,
                    func.count(NotebookSessionDBModel.id),
                )
                .filter(NotebookSessionDBModel.state.in_(LIVE_VALUES))
                .group_by(NotebookSessionDBModel.kernel)
                .all()
            )
            return {kernel: count for kernel, count in rows}

    def set_state(
        self,
        id: UUID,
        state: SessionState,
        started_at: datetime | None = None,
        stopped_at: datetime | None = None,
        stop_reason: StopReason | None = None,
    ) -> NotebookSessionDBModel | None:
        with self._session_factory() as db:
            row = (
                db.query(NotebookSessionDBModel)
                .filter(NotebookSessionDBModel.id == id)
                .one_or_none()
            )
            if row is None:
                return None
            row.state = state.value
            if started_at is not None:
                row.started_at = started_at
            if stopped_at is not None:
                row.stopped_at = stopped_at
            if stop_reason is not None:
                row.stop_reason = stop_reason.value
            db.commit()
            db.refresh(row)
            return row

    def set_stop_requested(self, id: UUID, reason: StopReason) -> None:
        with self._session_factory() as db:
            db.query(NotebookSessionDBModel).filter(
                NotebookSessionDBModel.id == id
            ).update({NotebookSessionDBModel.stop_requested: reason.value})
            db.commit()

    def append_progress(self, id: UUID, line: str) -> None:
        with self._session_factory() as db:
            row = (
                db.query(NotebookSessionDBModel)
                .filter(NotebookSessionDBModel.id == id)
                .with_for_update()
                .one_or_none()
            )
            if row is None:
                return
            lines = list(row.progress or [])
            lines.append(line[:PROGRESS_LINE_MAX])
            row.progress = lines[-PROGRESS_KEEP:]
            db.commit()

    def list_unpurged_not_live(self) -> list[NotebookSessionDBModel]:
        with self._session_factory() as db:
            return (
                db.query(NotebookSessionDBModel)
                .filter(
                    NotebookSessionDBModel.state.notin_(LIVE_VALUES),
                    NotebookSessionDBModel.data_purged_at.is_(None),
                )
                .all()
            )

    def mark_data_purged(self, id: UUID) -> None:
        with self._session_factory() as db:
            db.query(NotebookSessionDBModel).filter(
                NotebookSessionDBModel.id == id
            ).update({NotebookSessionDBModel.data_purged_at: func.now()})
            db.commit()
```

- [ ] **Step 3: Add the storage figure to `UserRepository`**

In `app/repository/user.py`, add a method to the class:

```python
    def set_notebook_storage_bytes(self, user_id: UUID, size_bytes: int) -> None:
        with self._session_factory() as session:
            session.query(User).filter(User.id == user_id).update(
                {User.notebook_storage_bytes: size_bytes}
            )
            session.commit()
```

(`User` is the ORM model the file already imports as `User`; check the existing import name at the top of the file and use it.)

- [ ] **Step 4: Import check and lint**

Run: `../../../.venv/bin/python -c "import app.repository.notebook, app.repository.notebook_session"` and `ruff check app/repository`
Expected: no output from either

- [ ] **Step 5: Commit**

```bash
git add app/repository/notebook.py app/repository/notebook_session.py app/repository/user.py
git commit -m "feat(notebooks): repositories, with the seat count under an advisory lock

start_if_seat_available counts live sessions and inserts in one transaction
under pg_advisory_xact_lock, so two requests cannot both see the last seat
free. The lock replaces the one-row capacity table the RFC sketched: same
guarantee, no table."
```

---

### Task 4: Session token and the read-only storage view

**Files:**
- Create: `app/service/notebook_token.py`, `app/service/notebook_token_test.py`
- Create: `app/service/notebook_storage.py`, `app/service/notebook_storage_test.py`

**Interfaces:**
- Consumes: `SessionClaims`, `Kernel`, `TOKEN_*` from Task 1; ORM `NotebookSession` from Task 2.
- Produces:
  - `NotebookTokenService(secret: str, max_hours: int)`: `mint(session, tenancies, datasets, locale, now=None) -> str`, `verify(token) -> SessionClaims` (raises `UnauthorizedException("expired" | "invalid_token")`).
  - `NotebookStorage(root: str)`: `user_dir(user_id) -> str`, `usage_bytes(user_id) -> int`, `notebook_exists(user_id, path) -> bool`, `read_notebook(user_id, path) -> bytes | None`.

- [ ] **Step 1: Write the failing token tests**

`app/service/notebook_token_test.py`:

```python
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt

from app.exception.unauthorized import UnauthorizedException
from app.model.notebook import Kernel, TOKEN_AUDIENCE
from app.service.notebook_token import NotebookTokenService

SECRET = "unit-test-secret"


def a_session(**overrides):
    values = dict(id=uuid4(), notebook_id=uuid4(), user_id=uuid4(), kernel="python3")
    values.update(overrides)
    return SimpleNamespace(**values)


class TestMintAndVerify(unittest.TestCase):
    def setUp(self):
        self.service = NotebookTokenService(secret=SECRET, max_hours=12)
        self.session = a_session()
        self.datasets = [{"id": str(uuid4()), "version": "2"}]

    def test_round_trip_carries_every_claim(self):
        token = self.service.mint(
            self.session, ["t/a"], self.datasets, "pt-BR"
        )

        claims = self.service.verify(token)

        self.assertEqual(claims.user_id, self.session.user_id)
        self.assertEqual(claims.tenancies, ["t/a"])
        self.assertEqual(claims.notebook_id, self.session.notebook_id)
        self.assertEqual(claims.session_id, self.session.id)
        self.assertEqual(claims.datasets, self.datasets)
        self.assertEqual(claims.kernel, Kernel.PYTHON)
        self.assertEqual(claims.locale, "pt-BR")

    def test_expiry_is_max_hours_plus_ten_minutes(self):
        now = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
        token = self.service.mint(self.session, [], self.datasets, "en", now=now)

        payload = jwt.decode(token, SECRET, algorithms=["HS256"], audience=TOKEN_AUDIENCE)

        self.assertEqual(payload["exp"] - payload["iat"], 12 * 3600 + 600)
        self.assertEqual(payload["iss"], "gatekeeper")

    def test_an_expired_token_is_refused_as_expired(self):
        long_ago = datetime.now(timezone.utc) - timedelta(days=2)
        token = self.service.mint(self.session, [], self.datasets, "en", now=long_ago)

        with self.assertRaises(UnauthorizedException) as raised:
            self.service.verify(token)
        self.assertEqual(str(raised.exception), "expired")

    def test_a_token_signed_with_another_key_is_invalid(self):
        other = NotebookTokenService(secret="other", max_hours=12)
        token = other.mint(self.session, [], self.datasets, "en")

        with self.assertRaises(UnauthorizedException) as raised:
            self.service.verify(token)
        self.assertEqual(str(raised.exception), "invalid_token")

    def test_an_upload_token_is_not_a_session_token(self):
        upload = jwt.encode(
            {"aud": "file_upload", "sub": str(uuid4()), "file": "x"},
            SECRET,
            algorithm="HS256",
        )

        with self.assertRaises(UnauthorizedException) as raised:
            self.service.verify(upload)
        self.assertEqual(str(raised.exception), "invalid_token")

    def test_garbage_is_invalid(self):
        with self.assertRaises(UnauthorizedException):
            self.service.verify("not.a.token")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `../../../.venv/bin/python -m pytest app/service/notebook_token_test.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the token service**

`app/service/notebook_token.py`:

```python
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from app.exception.unauthorized import UnauthorizedException
from app.model.notebook import (
    TOKEN_AUDIENCE,
    TOKEN_GRACE,
    TOKEN_ISSUER,
    Kernel,
    SessionClaims,
)


class NotebookTokenService:
    def __init__(self, secret: str, max_hours: int) -> None:
        self._secret = secret
        self._lifetime = timedelta(hours=max_hours) + TOKEN_GRACE
        self._logger = logging.getLogger("service:notebook_token")

    def mint(
        self,
        session,
        tenancies: list[str],
        datasets: list[dict],
        locale: str,
        now: datetime | None = None,
    ) -> str:
        issued = now or datetime.now(timezone.utc)
        payload = {
            "iss": TOKEN_ISSUER,
            "aud": TOKEN_AUDIENCE,
            "sub": str(session.user_id),
            "tenancies": list(tenancies),
            "notebook_id": str(session.notebook_id),
            "session_id": str(session.id),
            "datasets": datasets,
            "kernel": session.kernel,
            "locale": locale,
            "iat": int(issued.timestamp()),
            "exp": int((issued + self._lifetime).timestamp()),
        }
        return jwt.encode(payload, self._secret, algorithm="HS256")

    def verify(self, token: str) -> SessionClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience=TOKEN_AUDIENCE,
                issuer=TOKEN_ISSUER,
            )
        except jwt.ExpiredSignatureError:
            self._logger.warning("session token rejected: expired")
            raise UnauthorizedException("expired")
        except jwt.InvalidTokenError:
            self._logger.warning("session token rejected: invalid")
            raise UnauthorizedException("invalid_token")
        try:
            return SessionClaims(
                user_id=UUID(payload["sub"]),
                tenancies=list(payload.get("tenancies") or []),
                notebook_id=UUID(payload["notebook_id"]),
                session_id=UUID(payload["session_id"]),
                datasets=list(payload.get("datasets") or []),
                kernel=Kernel(payload["kernel"]),
                locale=str(payload.get("locale") or "pt-BR"),
            )
        except (KeyError, ValueError):
            raise UnauthorizedException("invalid_token")
```

- [ ] **Step 4: Run the token tests**

Run: `../../../.venv/bin/python -m pytest app/service/notebook_token_test.py -q`
Expected: 6 passed

- [ ] **Step 5: Write the failing storage tests**

`app/service/notebook_storage_test.py`:

```python
import os
import tempfile
import unittest
from uuid import uuid4

from app.service.notebook_storage import NotebookStorage


class TestNotebookStorage(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.storage = NotebookStorage(root=self.root)
        self.user_id = uuid4()

    def write(self, relative: str, size: int) -> None:
        path = os.path.join(self.root, str(self.user_id), relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"x" * size)

    def test_usage_of_a_user_with_no_directory_is_zero(self):
        self.assertEqual(self.storage.usage_bytes(self.user_id), 0)

    def test_usage_sums_every_file_including_outputs(self):
        self.write("a.ipynb", 100)
        self.write(".outputs/nb/result.nc", 250)

        self.assertEqual(self.storage.usage_bytes(self.user_id), 350)

    def test_notebook_exists_only_when_the_file_is_there(self):
        self.assertFalse(self.storage.notebook_exists(self.user_id, "a.ipynb"))
        self.write("a.ipynb", 1)
        self.assertTrue(self.storage.notebook_exists(self.user_id, "a.ipynb"))

    def test_read_notebook_returns_bytes_or_none(self):
        self.assertIsNone(self.storage.read_notebook(self.user_id, "a.ipynb"))
        self.write("a.ipynb", 3)
        self.assertEqual(self.storage.read_notebook(self.user_id, "a.ipynb"), b"xxx")

    def test_a_path_cannot_escape_the_users_directory(self):
        with self.assertRaises(ValueError):
            self.storage.notebook_exists(self.user_id, "../other.ipynb")
```

- [ ] **Step 6: Run to verify they fail, then write the storage view**

Run: `../../../.venv/bin/python -m pytest app/service/notebook_storage_test.py -q`
Expected: FAIL with `ModuleNotFoundError`

`app/service/notebook_storage.py`:

```python
import os
from uuid import UUID


class NotebookStorage:
    """The gatekeeper's read-only view of notebooks/. It never writes here."""

    def __init__(self, root: str) -> None:
        self._root = root

    def user_dir(self, user_id: UUID) -> str:
        return os.path.join(self._root, str(user_id))

    def usage_bytes(self, user_id: UUID) -> int:
        total = 0
        for directory, _, files in os.walk(self.user_dir(user_id)):
            for name in files:
                try:
                    total += os.lstat(os.path.join(directory, name)).st_size
                except OSError:
                    continue
        return total

    def notebook_exists(self, user_id: UUID, path: str) -> bool:
        return os.path.isfile(self._inside(user_id, path))

    def read_notebook(self, user_id: UUID, path: str) -> bytes | None:
        full = self._inside(user_id, path)
        if not os.path.isfile(full):
            return None
        with open(full, "rb") as handle:
            return handle.read()

    def _inside(self, user_id: UUID, path: str) -> str:
        base = os.path.realpath(self.user_dir(user_id))
        full = os.path.realpath(os.path.join(base, path))
        if full != base and not full.startswith(base + os.sep):
            raise ValueError("path escapes the user's directory")
        return full
```

- [ ] **Step 7: Run both test files**

Run: `../../../.venv/bin/python -m pytest app/service/notebook_token_test.py app/service/notebook_storage_test.py -q`
Expected: 11 passed

- [ ] **Step 8: Commit**

```bash
git add app/service/notebook_token.py app/service/notebook_token_test.py \
  app/service/notebook_storage.py app/service/notebook_storage_test.py
git commit -m "feat(notebooks): session token and the read-only view of notebook storage

The token is HS256 with its own audience and issuer, so an upload token
signed with a different secret and audience can never pass as one. The
storage view measures quota and reads a notebook; path traversal is refused
before any filesystem call."
```

---

### Task 5: Hub client, session authentication and the bearer path

**Files:**
- Create: `app/gateway/jupyterhub/__init__.py`, `app/gateway/jupyterhub/hub_client.py`, `app/gateway/jupyterhub/hub_client_test.py`
- Create: `app/service/notebook_session_auth.py`, `app/service/notebook_session_auth_test.py`
- Modify: `app/controller/interceptor/authentication.py`, `user_parser.py`, `user_parser_test.py`, `tenancy_parser.py`, `authorization.py`
- Create: `app/controller/interceptor/tenancy_parser_test.py`
- Modify: `app/metrics.py` (`AUTH_REASONS`)

**Interfaces:**
- Consumes: `NotebookTokenService.verify`, `NotebookSessionRepository.fetch`, `LIVE_STATES`, `SESSION_ROLE`, `RefusedException`.
- Produces:
  - `HubClient(base_url, api_token, timeout_seconds)`: `stop_server(username: str) -> None`, raises `RefusedException(503, "hub_unavailable")`.
  - `NotebookSessionAuth(token_service, session_repository)`: `authenticate(token: str) -> SessionClaims`, raises `UnauthorizedException("session_not_live")` when the row is not live.
  - `request.state.session_claims: SessionClaims` set by `authenticate` on a bearer request; `parse_user_header` and `parse_tenancy_header` read it; `authorize` enforces with subject `SESSION_ROLE` when it is set.

- [ ] **Step 1: Write the failing hub client tests**

`app/gateway/jupyterhub/hub_client_test.py`:

```python
import unittest
from unittest.mock import Mock, patch

import requests

from app.exception.refused import RefusedException
from app.gateway.jupyterhub.hub_client import HubClient


class TestStopServer(unittest.TestCase):
    def setUp(self):
        self.client = HubClient(
            base_url="http://hub:8000/hub", api_token="t", timeout_seconds=2
        )

    def response(self, status: int) -> Mock:
        response = Mock(spec=requests.Response)
        response.status_code = status
        return response

    @patch("app.gateway.jupyterhub.hub_client.requests.delete")
    def test_calls_the_users_server_route_with_the_token(self, delete):
        delete.return_value = self.response(204)

        self.client.stop_server("abc")

        delete.assert_called_once_with(
            "http://hub:8000/hub/api/users/abc/server",
            headers={"Authorization": "token t"},
            timeout=2,
        )

    @patch("app.gateway.jupyterhub.hub_client.requests.delete")
    def test_202_and_404_count_as_stopped(self, delete):
        for status in (202, 404):
            delete.return_value = self.response(status)
            self.client.stop_server("abc")

    @patch("app.gateway.jupyterhub.hub_client.requests.delete")
    def test_any_other_status_is_hub_unavailable(self, delete):
        delete.return_value = self.response(500)

        with self.assertRaises(RefusedException) as raised:
            self.client.stop_server("abc")
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.code, "hub_unavailable")

    @patch("app.gateway.jupyterhub.hub_client.requests.delete")
    def test_a_timeout_is_hub_unavailable(self, delete):
        delete.side_effect = requests.Timeout()

        with self.assertRaises(RefusedException):
            self.client.stop_server("abc")

    def test_an_empty_token_fails_closed_without_a_request(self):
        client = HubClient(base_url="http://hub", api_token="", timeout_seconds=2)
        with patch("app.gateway.jupyterhub.hub_client.requests.delete") as delete:
            with self.assertRaises(RefusedException):
                client.stop_server("abc")
            delete.assert_not_called()
```

- [ ] **Step 2: Run to verify they fail, then write the client**

Run: `../../../.venv/bin/python -m pytest app/gateway/jupyterhub/hub_client_test.py -q`
Expected: FAIL with `ModuleNotFoundError`

`app/gateway/jupyterhub/__init__.py`: empty.

`app/gateway/jupyterhub/hub_client.py`:

```python
import logging

import requests

from app.exception.refused import RefusedException
from app.logging_config import fields
from app.metrics import metrics

STOPPED_STATUSES = (202, 204, 404)


class HubClient:
    def __init__(self, base_url: str, api_token: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._timeout = timeout_seconds
        self._logger = logging.getLogger("gateway:jupyterhub")

    def stop_server(self, username: str) -> None:
        if not self._api_token:
            raise RefusedException(503, "hub_unavailable")
        url = f"{self._base_url}/api/users/{username}/server"
        with metrics.external_call("jupyterhub", "server.stop") as call:
            try:
                response = requests.delete(
                    url,
                    headers={"Authorization": f"token {self._api_token}"},
                    timeout=self._timeout,
                )
            except requests.RequestException as error:
                self._logger.warning(
                    "hub unreachable", extra=fields(username=username, error=str(error))
                )
                raise RefusedException(503, "hub_unavailable")
            call.status = response.status_code
        if response.status_code not in STOPPED_STATUSES:
            self._logger.warning(
                "hub refused to stop a server",
                extra=fields(username=username, status_code=response.status_code),
            )
            raise RefusedException(503, "hub_unavailable")
```

Run the tests again. Expected: 5 passed.

- [ ] **Step 3: Write the failing session-auth tests**

`app/service/notebook_session_auth_test.py`:

```python
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.exception.unauthorized import UnauthorizedException
from app.model.notebook import Kernel, SessionClaims
from app.repository.notebook_session import NotebookSessionRepository
from app.service.notebook_session_auth import NotebookSessionAuth
from app.service.notebook_token import NotebookTokenService


class TestAuthenticate(unittest.TestCase):
    def setUp(self):
        self.tokens = Mock(spec=NotebookTokenService)
        self.sessions = Mock(spec=NotebookSessionRepository)
        self.auth = NotebookSessionAuth(
            token_service=self.tokens, session_repository=self.sessions
        )
        self.claims = SessionClaims(
            user_id=uuid4(),
            tenancies=[],
            notebook_id=uuid4(),
            session_id=uuid4(),
            datasets=[],
            kernel=Kernel.PYTHON,
            locale="en",
        )
        self.tokens.verify.return_value = self.claims

    def test_a_live_session_authenticates(self):
        self.sessions.fetch.return_value = SimpleNamespace(state="running")

        self.assertIs(self.auth.authenticate("tok"), self.claims)
        self.sessions.fetch.assert_called_once_with(self.claims.session_id)

    def test_starting_counts_as_live(self):
        self.sessions.fetch.return_value = SimpleNamespace(state="starting")
        self.auth.authenticate("tok")

    def test_a_stopped_session_is_refused_as_not_live(self):
        self.sessions.fetch.return_value = SimpleNamespace(state="stopped")

        with self.assertRaises(UnauthorizedException) as raised:
            self.auth.authenticate("tok")
        self.assertEqual(str(raised.exception), "session_not_live")

    def test_an_unknown_session_is_refused_as_not_live(self):
        self.sessions.fetch.return_value = None

        with self.assertRaises(UnauthorizedException):
            self.auth.authenticate("tok")

    def test_token_errors_propagate(self):
        self.tokens.verify.side_effect = UnauthorizedException("expired")

        with self.assertRaises(UnauthorizedException) as raised:
            self.auth.authenticate("tok")
        self.assertEqual(str(raised.exception), "expired")
        self.sessions.fetch.assert_not_called()
```

- [ ] **Step 4: Run to verify they fail, then write the service**

`app/service/notebook_session_auth.py`:

```python
from app.exception.unauthorized import UnauthorizedException
from app.model.notebook import LIVE_STATES, SessionClaims
from app.repository.notebook_session import NotebookSessionRepository
from app.service.notebook_token import NotebookTokenService

LIVE_VALUES = {state.value for state in LIVE_STATES}


class NotebookSessionAuth:
    def __init__(
        self,
        token_service: NotebookTokenService,
        session_repository: NotebookSessionRepository,
    ) -> None:
        self._tokens = token_service
        self._sessions = session_repository

    def authenticate(self, token: str) -> SessionClaims:
        claims = self._tokens.verify(token)
        row = self._sessions.fetch(claims.session_id)
        if row is None or row.state not in LIVE_VALUES:
            raise UnauthorizedException("session_not_live")
        return claims
```

Run: `../../../.venv/bin/python -m pytest app/service/notebook_session_auth_test.py -q`
Expected: 5 passed

- [ ] **Step 5: The bearer path in the interceptors**

In `app/metrics.py`, add `"session_not_live"` to `AUTH_REASONS`.

`app/controller/interceptor/authentication.py` becomes:

```python
from dependency_injector.wiring import inject, Provide

from app.container import Container
from app.model.notebook import SESSION_ROLE
from app.service.auth import AuthService
from app.service.notebook_session_auth import NotebookSessionAuth
from app.exception.unauthorized import UnauthorizedException
from app.metrics import metrics
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader


api_key = APIKeyHeader(name="X-Api-Key", auto_error=False, scheme_name="X-Api-Key")
api_secret = APIKeyHeader(
    name="X-Api-Secret", auto_error=False, scheme_name="X-Api-Secret"
)
authorization = APIKeyHeader(
    name="Authorization", auto_error=False, scheme_name="Authorization"
)

BEARER = "Bearer "


@inject
def authenticate(
    request: Request,
    api_key: str = Depends(api_key),
    api_secret: str = Depends(api_secret),
    authorization: str = Depends(authorization),
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
    session_auth: NotebookSessionAuth = Depends(
        Provide[Container.notebook_session_auth]
    ),
):
    if api_key is None and authorization and authorization.startswith(BEARER):
        try:
            claims = session_auth.authenticate(authorization[len(BEARER) :])
        except UnauthorizedException as e:
            metrics.auth_failure("session", str(e))
            raise HTTPException(status_code=401, detail="Unauthorized")
        request.state.session_claims = claims
        request.state.client_name = SESSION_ROLE
        return

    try:
        client = auth_service.authorize_client(
            api_key=api_key, salted_api_secret=api_secret
        )
    except UnauthorizedException as e:
        metrics.auth_failure("authn", str(e))
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Read by the request middleware as the `client` metric label.
    request.state.client_name = client.name
```

In `app/controller/interceptor/user_parser.py`, `parse_user_header` becomes:

```python
async def parse_user_header(request: Request, user_id: str = Depends(user_id)) -> UUID:
    claims = getattr(getattr(request, "state", None), "session_claims", None)
    if claims is not None:
        return claims.user_id
    if not user_id:
        raise UnauthorizedException("user_id header not found")

    return UUID(user_id)
```

`app/controller/interceptor/tenancy_parser.py` becomes:

```python
from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

tenancies = APIKeyHeader(
    name="X-Datamap-Tenancies", auto_error=False, scheme_name="X-Datamap-Tenancies"
)


def parse_tenancy_header(
    request: Request, tenancies: str = Depends(tenancies)
) -> list[str]:
    claims = getattr(getattr(request, "state", None), "session_claims", None)
    if claims is not None:
        return list(claims.tenancies)
    if not tenancies:
        return []

    return [tenancy.strip() for tenancy in tenancies.split(";")]
```

In `app/controller/interceptor/authorization.py`, `authorize` becomes the function below; `authorize_self_or_policy`, `authorize_self` and `authorize_tus` (RFC 008 and 009 added the first two) stay as they are:

```python
@inject
def authorize(
    request: Request,
    user_id: UUID = Depends(parse_user_header),
    auth_service: AuthService = Depends(Provide[Container.auth_service]),
):
    resource = request.url.path
    action = request.method
    claims = getattr(request.state, "session_claims", None)
    subject = SESSION_ROLE if claims is not None else user_id

    try:
        auth_service.authorize_user(subject, resource, action)
    except UnauthorizedException as e:
        metrics.auth_failure("authz", str(e))
        raise
```

with `from app.model.notebook import SESSION_ROLE` added to its imports. `authorize_user` already does `str(user_id)`, so a string subject works unchanged.

- [ ] **Step 6: Parser tests**

Append to `app/controller/interceptor/user_parser_test.py`:

```python
from types import SimpleNamespace
from uuid import uuid4


class TestUserParserWithSessionClaims(unittest.IsolatedAsyncioTestCase):
    async def test_the_claims_win_over_the_header(self):
        user_id = uuid4()
        request = SimpleNamespace(state=SimpleNamespace(session_claims=SimpleNamespace(user_id=user_id)))

        self.assertEqual(await parse_user_header(request=request, user_id=None), user_id)
```

Create `app/controller/interceptor/tenancy_parser_test.py`:

```python
import unittest
from types import SimpleNamespace

from app.controller.interceptor.tenancy_parser import parse_tenancy_header


class TestTenancyParser(unittest.TestCase):
    def test_splits_the_header_on_semicolons(self):
        request = SimpleNamespace(state=SimpleNamespace())
        self.assertEqual(
            parse_tenancy_header(request=request, tenancies="a/b; c/d"), ["a/b", "c/d"]
        )

    def test_missing_header_is_an_empty_list(self):
        request = SimpleNamespace(state=SimpleNamespace())
        self.assertEqual(parse_tenancy_header(request=request, tenancies=None), [])

    def test_session_claims_win_over_the_header(self):
        claims = SimpleNamespace(tenancies=["t/x"])
        request = SimpleNamespace(state=SimpleNamespace(session_claims=claims))
        self.assertEqual(parse_tenancy_header(request=request, tenancies="a/b"), ["t/x"])
```

Run: `../../../.venv/bin/python -m pytest app/controller/interceptor -q`
Expected: all passed. (If the existing `user_parser_test.py` cases pass `request=None`, they still pass: `getattr(None, "state", None)` is `None`.)

- [ ] **Step 7: Run the whole unit suite and lint**

Run: `../../../.venv/bin/python -m pytest -q && ruff check && ruff format --check`
Expected: all passed; no lint findings. (`Container.notebook_session_auth` does not exist yet; the `@inject` reference resolves at wiring time, so the suite passes. Task 9 adds the provider, and until then the application will not boot — that is expected and is why Tasks 5–9 land on one branch.)

- [ ] **Step 8: Commit**

```bash
git add app/gateway/jupyterhub app/service/notebook_session_auth.py app/service/notebook_session_auth_test.py \
  app/controller/interceptor/authentication.py app/controller/interceptor/user_parser.py \
  app/controller/interceptor/user_parser_test.py app/controller/interceptor/tenancy_parser.py \
  app/controller/interceptor/tenancy_parser_test.py app/controller/interceptor/authorization.py app/metrics.py
git commit -m "feat(notebooks): bearer session tokens in the interceptors

A bearer request authenticates by token plus a live session row, carries the
user and tenancies from the claims, and is authorized as the notebook_session
subject, so the token reaches only the routes that subject has. Revocation is
the row state: a stopped session's token fails on the next request."
```

---

### Task 6: `NotebookService`

**Files:**
- Modify: `app/service/dataset.py` (`file_url`)
- Create: `app/service/notebook.py`, `app/service/notebook_test.py`

**Interfaces:**
- Consumes: `DatasetService.fetch_authorized(dataset_id, user_id, tenancies, action)`, `DatasetVersionRepository.fetch_version_by_name`, `NotebookRepository`, `NotebookSessionRepository.latest_for_notebook`, `NotebookStorage`, Task 1 model.
- Produces:
  - `DatasetService.file_url(file: DataFileDBModel, expires_in: timedelta) -> str`.
  - `NotebookService(repository, session_repository, dataset_service, version_repository, storage, data_max_bytes)`: `create(owner_id, tenancies, dataset_id, version_name, kernel, name=None, file_ids=None) -> Notebook`, `list(owner_id, dataset_id=None) -> list[Notebook]`, `fetch(id, owner_id) -> Notebook`, `fetch_row(id, owner_id) -> NotebookDBModel` (for the session service), `update(id, owner_id, name=None, file_ids=NOT_SET) -> Notebook`, `soft_delete(id, owner_id) -> None`, `content(id, owner_id) -> bytes`, `manifest(claims, notebook_id) -> Manifest`, `published_version(dataset_id, version_name, user_id, tenancies) -> tuple[DatasetDBModel, DatasetVersionDBModel]`, `select(version, file_ids) -> tuple[list[DataFileDBModel], int]`, `adapt(row, session_row=None) -> Notebook`.

- [ ] **Step 1: Extract `file_url` in `DatasetService`**

In `app/service/dataset.py`, add after `get_file_download_url`:

```python
    def file_url(self, file: DataFileDBModel, expires_in: timedelta) -> str:
        bucket_prefix = self._dataset_bucket + "/"
        object_name = (
            file.storage_path[len(bucket_prefix) :]
            if file.storage_path.startswith(bucket_prefix)
            else file.storage_path
        )
        return self._minio_gateway.get_pre_signed_url(
            bucket_name=self._dataset_bucket,
            object_name=object_name,
            original_file_name=file.name,
            expires_in=expires_in,
        )
```

and replace the `url = self._minio_gateway.get_pre_signed_url(...)` block inside `get_file_download_url` with:

```python
        url = self.file_url(
            file,
            EMBARGO_DOWNLOAD_TTL
            if self._access.embargo_active(dataset)
            else DEFAULT_DOWNLOAD_TTL,
        )
```

(`timedelta` is already imported in that module for the TTL constants; confirm with `grep -n "^from datetime" app/service/dataset.py`.)

Run: `../../../.venv/bin/python -m pytest app/service/dataset_test.py -q`
Expected: all passed

- [ ] **Step 2: Write the failing service tests**

`app/service/notebook_test.py`:

```python
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.exception.bad_request import BadRequestException
from app.exception.conflict import ConflictException
from app.exception.not_found import NotFoundException
from app.exception.refused import RefusedException
from app.model.dataset import DesignState
from app.model.dataset_access import DatasetAction
from app.model.notebook import Kernel, SessionClaims
from app.repository.dataset_version import DatasetVersionRepository
from app.repository.notebook import NotebookRepository
from app.repository.notebook_session import NotebookSessionRepository
from app.service.dataset import DatasetService
from app.service.notebook import NOT_SET, NotebookService
from app.service.notebook_storage import NotebookStorage


def a_file(size: int, name: str = "a.nc") -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), name=name, size_bytes=size, storage_path="datamap/x")


def a_version(files, published=True, name="2") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        files_in=list(files),
        design_state=DesignState.PUBLISHED if published else DesignState.DRAFT,
        is_enabled=True,
    )


def a_dataset(name="GoAmazon T3") -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), name=name, is_enabled=True)


class NotebookServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.notebooks = Mock(spec=NotebookRepository)
        self.sessions = Mock(spec=NotebookSessionRepository)
        self.datasets = Mock(spec=DatasetService)
        self.versions = Mock(spec=DatasetVersionRepository)
        self.storage = Mock(spec=NotebookStorage)
        self.service = NotebookService(
            repository=self.notebooks,
            session_repository=self.sessions,
            dataset_service=self.datasets,
            version_repository=self.versions,
            storage=self.storage,
            data_max_bytes=1000,
        )
        self.owner = uuid4()
        self.dataset = a_dataset()
        self.files = [a_file(400), a_file(500, "b.nc")]
        self.version = a_version(self.files)
        self.datasets.fetch_authorized.return_value = (self.dataset, [], None)
        self.versions.fetch_version_by_name.return_value = self.version
        self.notebooks.name_exists.return_value = False
        self.sessions.latest_for_notebook.return_value = None
        self.notebooks.insert.side_effect = lambda row: self._saved(row)

    def _saved(self, row):
        row.id = row.id or uuid4()
        return row


class TestCreate(NotebookServiceTestCase):
    def test_reads_the_dataset_with_the_files_action(self):
        self.service.create(self.owner, ["t"], self.dataset.id, "2", Kernel.PYTHON)

        self.datasets.fetch_authorized.assert_called_once_with(
            dataset_id=self.dataset.id,
            user_id=self.owner,
            tenancies=["t"],
            action=DatasetAction.READ_FILES,
        )

    def test_a_draft_version_is_refused(self):
        self.versions.fetch_version_by_name.return_value = a_version(self.files, published=False)

        with self.assertRaises(ConflictException) as raised:
            self.service.create(self.owner, [], self.dataset.id, "2", Kernel.PYTHON)
        self.assertEqual(str(raised.exception), "version_not_published")

    def test_an_unknown_version_is_not_found(self):
        self.versions.fetch_version_by_name.return_value = None

        with self.assertRaises(NotFoundException):
            self.service.create(self.owner, [], self.dataset.id, "9", Kernel.PYTHON)

    def test_the_whole_version_is_selected_by_default(self):
        notebook = self.service.create(self.owner, [], self.dataset.id, "2", Kernel.R)

        self.assertIsNone(notebook.dataset.file_ids)
        self.assertEqual(notebook.mounted_files, 2)
        self.assertEqual(notebook.mounted_bytes, 900)
        self.assertEqual(notebook.kernel, Kernel.R)

    def test_a_selection_over_the_ceiling_is_refused_with_the_numbers(self):
        self.versions.fetch_version_by_name.return_value = a_version([a_file(600), a_file(600)])

        with self.assertRaises(RefusedException) as raised:
            self.service.create(self.owner, [], self.dataset.id, "2", Kernel.PYTHON)
        self.assertEqual(raised.exception.status_code, 413)
        self.assertEqual(raised.exception.code, "selection_too_large")
        self.assertEqual(raised.exception.extra, {"max_bytes": 1000, "selected_bytes": 1200})

    def test_a_subset_under_the_ceiling_is_accepted(self):
        big = [a_file(600), a_file(600, "b.nc")]
        self.versions.fetch_version_by_name.return_value = a_version(big)

        notebook = self.service.create(
            self.owner, [], self.dataset.id, "2", Kernel.PYTHON, file_ids=[big[0].id]
        )

        self.assertEqual(notebook.dataset.file_ids, [big[0].id])
        self.assertEqual(notebook.mounted_bytes, 600)

    def test_a_file_from_elsewhere_is_a_bad_request(self):
        with self.assertRaises(BadRequestException) as raised:
            self.service.create(
                self.owner, [], self.dataset.id, "2", Kernel.PYTHON, file_ids=[uuid4()]
            )
        self.assertEqual(raised.exception.errors[0].code, "file_not_in_version")

    def test_the_name_comes_from_the_dataset_title_and_dodges_collisions(self):
        self.notebooks.name_exists.side_effect = [True, True, False]

        notebook = self.service.create(self.owner, [], self.dataset.id, "2", Kernel.PYTHON)

        self.assertEqual(notebook.name, "goamazon_t3_3")
        self.assertEqual(notebook.path, "goamazon_t3_3.ipynb")

    def test_an_explicit_name_that_exists_is_a_conflict(self):
        self.notebooks.name_exists.return_value = True

        with self.assertRaises(ConflictException) as raised:
            self.service.create(self.owner, [], self.dataset.id, "2", Kernel.PYTHON, name="x")
        self.assertEqual(str(raised.exception), "name_taken")

    def test_an_explicit_name_must_match_the_pattern(self):
        with self.assertRaises(BadRequestException):
            self.service.create(self.owner, [], self.dataset.id, "2", Kernel.PYTHON, name="bad name!")


class TestFetchAndUpdate(NotebookServiceTestCase):
    def a_row(self, owner=None, file_ids=None):
        link = SimpleNamespace(
            position=0, dataset_id=self.dataset.id, dataset_version="2",
            file_ids=file_ids, mounted_files=2, mounted_bytes=900, dataset=self.dataset,
        )
        return SimpleNamespace(
            id=uuid4(), owner_id=owner or self.owner, name="n", path="n.ipynb",
            kernel="python3", size_bytes=0, created_at=None, updated_at=None,
            deleted_at=None, datasets=[link],
        )

    def test_someone_elses_notebook_is_not_found(self):
        self.notebooks.fetch.return_value = self.a_row(owner=uuid4())

        with self.assertRaises(NotFoundException):
            self.service.fetch(uuid4(), self.owner)

    def test_a_deleted_source_is_reported(self):
        row = self.a_row()
        row.datasets[0].dataset_id = None
        row.datasets[0].dataset = None
        self.notebooks.fetch.return_value = row

        notebook = self.service.fetch(row.id, self.owner)

        self.assertTrue(notebook.dataset.source_deleted)

    def test_changing_the_selection_under_a_live_session_is_refused(self):
        row = self.a_row()
        self.notebooks.fetch.return_value = row
        self.sessions.latest_for_notebook.return_value = SimpleNamespace(state="running")

        with self.assertRaises(ConflictException) as raised:
            self.service.update(row.id, self.owner, file_ids=[self.files[0].id])
        self.assertEqual(str(raised.exception), "session_running")

    def test_renaming_does_not_need_the_session_stopped(self):
        row = self.a_row()
        self.notebooks.fetch.return_value = row
        self.notebooks.save.side_effect = lambda r: r
        self.sessions.latest_for_notebook.return_value = SimpleNamespace(state="running")

        notebook = self.service.update(row.id, self.owner, name="renamed")

        self.assertEqual(notebook.name, "renamed")
        self.assertEqual(notebook.path, "renamed.ipynb")

    def test_a_new_selection_is_re_measured(self):
        row = self.a_row()
        self.notebooks.fetch.return_value = row
        self.notebooks.save.side_effect = lambda r: r

        notebook = self.service.update(row.id, self.owner, file_ids=[self.files[1].id])

        self.assertEqual(notebook.mounted_files, 1)
        self.assertEqual(notebook.mounted_bytes, 500)

    def test_update_without_file_ids_keeps_the_selection(self):
        row = self.a_row(file_ids=[str(self.files[0].id)])
        self.notebooks.fetch.return_value = row
        self.notebooks.save.side_effect = lambda r: r

        notebook = self.service.update(row.id, self.owner, name="z")

        self.assertEqual(notebook.dataset.file_ids, [self.files[0].id])


class TestContentAndManifest(NotebookServiceTestCase):
    def setUp(self):
        super().setUp()
        self.row = SimpleNamespace(
            id=uuid4(), owner_id=self.owner, name="n", path="n.ipynb", kernel="python3",
            size_bytes=0, created_at=None, updated_at=None, deleted_at=None,
            datasets=[SimpleNamespace(
                position=0, dataset_id=self.dataset.id, dataset_version="2",
                file_ids=None, mounted_files=2, mounted_bytes=900, dataset=self.dataset,
            )],
        )
        self.notebooks.fetch.return_value = self.row
        self.claims = SessionClaims(
            user_id=self.owner, tenancies=["t"], notebook_id=self.row.id,
            session_id=uuid4(), datasets=[], kernel=Kernel.PYTHON, locale="en",
        )

    def test_content_not_written_yet_is_a_distinct_not_found(self):
        self.storage.read_notebook.return_value = None

        with self.assertRaises(NotFoundException) as raised:
            self.service.content(self.row.id, self.owner)
        self.assertEqual(str(raised.exception), "content_not_written")

    def test_manifest_lists_the_selection_with_urls_and_mount_path(self):
        self.storage.notebook_exists.return_value = False
        self.datasets.file_url.side_effect = lambda file, expires_in: f"url:{file.name}"

        manifest = self.service.manifest(self.claims, self.row.id)

        self.assertFalse(manifest.notebook_exists)
        self.assertEqual(manifest.outputs_path, "/outputs")
        dataset = manifest.datasets[0]
        self.assertEqual(dataset.mount_path, f"/data/{self.dataset.id}/2")
        self.assertEqual(dataset.file_count, 2)
        self.assertEqual(dataset.total_bytes, 900)
        self.assertEqual([f.url for f in dataset.files], ["url:a.nc", "url:b.nc"])
        self.assertEqual(dataset.files[0].relative_path, "a.nc")

    def test_manifest_of_another_notebook_is_not_found(self):
        with self.assertRaises(NotFoundException):
            self.service.manifest(self.claims, uuid4())

    def test_manifest_re_checks_readability_now(self):
        self.datasets.fetch_authorized.side_effect = NotFoundException("gone")

        with self.assertRaises(NotFoundException):
            self.service.manifest(self.claims, self.row.id)
```

- [ ] **Step 3: Run to verify they fail**

Run: `../../../.venv/bin/python -m pytest app/service/notebook_test.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.service.notebook'`

- [ ] **Step 4: Write the service**

`app/service/notebook.py`:

```python
from uuid import UUID

from app.exception.bad_request import BadRequestException, ErrorDetails
from app.exception.conflict import ConflictException
from app.exception.not_found import NotFoundException
from app.exception.refused import RefusedException
from app.model.dataset import DesignState
from app.model.dataset_access import DatasetAction
from app.model.db.dataset import (
    DataFile as DataFileDBModel,
    Dataset as DatasetDBModel,
    DatasetVersion as DatasetVersionDBModel,
)
from app.model.db.notebook import (
    Notebook as NotebookDBModel,
    NotebookDataset as NotebookDatasetDBModel,
)
from app.model.notebook import (
    MANIFEST_URL_TTL,
    NAME_PATTERN,
    OUTPUTS_MOUNT,
    Kernel,
    Manifest,
    ManifestDataset,
    ManifestFile,
    Notebook,
    NotebookDataset,
    NotebookSession,
    SessionClaims,
    SessionState,
    StopReason,
    mount_path,
    slug_name,
)
from app.repository.dataset_version import DatasetVersionRepository
from app.repository.notebook import NotebookRepository
from app.repository.notebook_session import NotebookSessionRepository
from app.service.dataset import DatasetService
from app.service.notebook_storage import NotebookStorage

NOT_SET = object()


class NotebookService:
    def __init__(
        self,
        repository: NotebookRepository,
        session_repository: NotebookSessionRepository,
        dataset_service: DatasetService,
        version_repository: DatasetVersionRepository,
        storage: NotebookStorage,
        data_max_bytes: int,
    ) -> None:
        self._repository = repository
        self._sessions = session_repository
        self._datasets = dataset_service
        self._versions = version_repository
        self._storage = storage
        self._data_max_bytes = data_max_bytes

    def create(
        self,
        owner_id: UUID,
        tenancies: list[str],
        dataset_id: UUID,
        version_name: str,
        kernel: Kernel,
        name: str | None = None,
        file_ids: list[UUID] | None = None,
    ) -> Notebook:
        dataset, version = self.published_version(
            dataset_id, version_name, owner_id, tenancies
        )
        files, total = self.select(version, file_ids)
        name = self._free_name(owner_id, name, dataset.name)
        row = NotebookDBModel(
            owner_id=owner_id, name=name, path=f"{name}.ipynb", kernel=kernel.value
        )
        row.datasets.append(
            NotebookDatasetDBModel(
                position=0,
                dataset_id=dataset.id,
                dataset_version=version.name,
                file_ids=[str(f.id) for f in files] if file_ids is not None else None,
                mounted_files=len(files),
                mounted_bytes=total,
            )
        )
        notebook = self.adapt(self._repository.insert(row))
        notebook.datasets[0].title = dataset.name
        notebook.datasets[0].source_deleted = False
        return notebook

    def list(self, owner_id: UUID, dataset_id: UUID | None = None) -> list[Notebook]:
        rows = self._repository.list_for_owner(owner_id, dataset_id=dataset_id)
        return [
            self.adapt(row, self._sessions.latest_for_notebook(row.id)) for row in rows
        ]

    def fetch_row(self, id: UUID, owner_id: UUID) -> NotebookDBModel:
        row = self._repository.fetch(id)
        if row is None or row.owner_id != owner_id:
            raise NotFoundException(f"not_found: {id}")
        return row

    def fetch(self, id: UUID, owner_id: UUID) -> Notebook:
        row = self.fetch_row(id, owner_id)
        return self.adapt(row, self._sessions.latest_for_notebook(row.id))

    def update(
        self,
        id: UUID,
        owner_id: UUID,
        name: str | None = None,
        file_ids=NOT_SET,
    ) -> Notebook:
        row = self.fetch_row(id, owner_id)
        if name is not None and name != row.name:
            self._check_name(name)
            if self._repository.name_exists(owner_id, name):
                raise ConflictException("name_taken")
            row.name = name
            row.path = f"{name}.ipynb"
        if file_ids is not NOT_SET:
            latest = self._sessions.latest_for_notebook(row.id)
            if latest is not None and latest.state in (
                SessionState.STARTING.value,
                SessionState.RUNNING.value,
            ):
                raise ConflictException("session_running")
            link = row.datasets[0]
            version = self._versions.fetch_version_by_name(
                dataset_id=link.dataset_id, version_name=link.dataset_version
            )
            if version is None:
                raise NotFoundException("not_found: source version")
            files, total = self.select(version, file_ids)
            link.file_ids = [str(f.id) for f in files] if file_ids is not None else None
            link.mounted_files = len(files)
            link.mounted_bytes = total
        saved = self._repository.save(row)
        return self.adapt(saved, self._sessions.latest_for_notebook(saved.id))

    def soft_delete(self, id: UUID, owner_id: UUID) -> None:
        self.fetch_row(id, owner_id)
        self._repository.soft_delete(id)

    def content(self, id: UUID, owner_id: UUID) -> bytes:
        row = self.fetch_row(id, owner_id)
        data = self._storage.read_notebook(owner_id, row.path)
        if data is None:
            raise NotFoundException("content_not_written")
        return data

    def manifest(self, claims: SessionClaims, notebook_id: UUID) -> Manifest:
        if claims.notebook_id != notebook_id:
            raise NotFoundException(f"not_found: {notebook_id}")
        row = self.fetch_row(notebook_id, claims.user_id)
        datasets = []
        for link in row.datasets:
            if link.dataset_id is None:
                raise NotFoundException("not_found: source deleted")
            dataset, version = self.published_version(
                link.dataset_id, link.dataset_version, claims.user_id, claims.tenancies
            )
            file_ids = [UUID(x) for x in link.file_ids] if link.file_ids else None
            files, total = self.select(version, file_ids)
            datasets.append(
                ManifestDataset(
                    dataset_id=dataset.id,
                    dataset_title=dataset.name,
                    version_name=version.name,
                    mount_path=mount_path(dataset.id, version.name),
                    file_count=len(files),
                    total_bytes=total,
                    files=[
                        ManifestFile(
                            id=f.id,
                            name=f.name,
                            size_bytes=f.size_bytes,
                            relative_path=f.name,
                            url=self._datasets.file_url(f, expires_in=MANIFEST_URL_TTL),
                        )
                        for f in files
                    ],
                )
            )
        return Manifest(
            notebook_id=row.id,
            notebook_path=row.path,
            notebook_exists=self._storage.notebook_exists(row.owner_id, row.path),
            kernel=Kernel(row.kernel),
            outputs_path=OUTPUTS_MOUNT,
            datasets=datasets,
        )

    def published_version(
        self,
        dataset_id: UUID,
        version_name: str,
        user_id: UUID,
        tenancies: list[str],
    ) -> tuple[DatasetDBModel, DatasetVersionDBModel]:
        dataset, _, _ = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.READ_FILES,
        )
        version = self._versions.fetch_version_by_name(
            dataset_id=dataset_id, version_name=version_name
        )
        if version is None:
            raise NotFoundException(f"not_found: {version_name} for dataset {dataset_id}")
        if version.design_state != DesignState.PUBLISHED or not version.is_enabled:
            raise ConflictException("version_not_published")
        return dataset, version

    def select(
        self, version: DatasetVersionDBModel, file_ids: list[UUID] | None
    ) -> tuple[list[DataFileDBModel], int]:
        if file_ids is None:
            files = list(version.files_in)
        else:
            by_id = {f.id: f for f in version.files_in}
            if any(i not in by_id for i in file_ids):
                raise BadRequestException(
                    errors=[ErrorDetails(code="file_not_in_version", field="file_ids")]
                )
            files = [by_id[i] for i in file_ids]
        total = sum(f.size_bytes for f in files)
        if total > self._data_max_bytes:
            raise RefusedException(
                413,
                "selection_too_large",
                max_bytes=self._data_max_bytes,
                selected_bytes=total,
            )
        return files, total

    def adapt(self, row: NotebookDBModel, session_row=None) -> Notebook:
        return Notebook(
            id=row.id,
            owner_id=row.owner_id,
            name=row.name,
            path=row.path,
            kernel=Kernel(row.kernel),
            size_bytes=row.size_bytes or 0,
            created_at=row.created_at,
            updated_at=row.updated_at,
            deleted_at=row.deleted_at,
            datasets=[self._adapt_link(link) for link in row.datasets],
            session=adapt_session(session_row) if session_row is not None else None,
        )

    def _adapt_link(self, link: NotebookDatasetDBModel) -> NotebookDataset:
        source = getattr(link, "dataset", None)
        return NotebookDataset(
            dataset_id=link.dataset_id,
            version_name=link.dataset_version,
            file_ids=[UUID(x) for x in link.file_ids] if link.file_ids else None,
            position=link.position,
            title=source.name if source is not None else None,
            source_deleted=link.dataset_id is None
            or (source is not None and not source.is_enabled),
            mounted_files=link.mounted_files or 0,
            mounted_bytes=link.mounted_bytes or 0,
        )

    def _free_name(self, owner_id: UUID, name: str | None, title: str) -> str:
        if name is not None:
            self._check_name(name)
            if self._repository.name_exists(owner_id, name):
                raise ConflictException("name_taken")
            return name
        base = slug_name(title)
        candidate, counter = base, 1
        while self._repository.name_exists(owner_id, candidate):
            counter += 1
            candidate = f"{base}_{counter}"
        return candidate

    @staticmethod
    def _check_name(name: str) -> None:
        if not NAME_PATTERN.match(name):
            raise BadRequestException(
                errors=[ErrorDetails(code="invalid_name", field="name")]
            )


def adapt_session(row) -> NotebookSession:
    return NotebookSession(
        id=row.id,
        notebook_id=row.notebook_id,
        user_id=row.user_id,
        tenancy=row.tenancy,
        kernel=Kernel(row.kernel),
        state=SessionState(row.state),
        dataset_id=row.dataset_id,
        dataset_version=row.dataset_version,
        mounted_files=row.mounted_files or 0,
        mounted_bytes=row.mounted_bytes or 0,
        requested_at=row.requested_at,
        started_at=row.started_at,
        stopped_at=row.stopped_at,
        stop_reason=StopReason(row.stop_reason) if row.stop_reason else None,
        stop_requested=StopReason(row.stop_requested) if row.stop_requested else None,
        progress=list(row.progress or []),
    )
```

- [ ] **Step 5: Run the service tests**

Run: `../../../.venv/bin/python -m pytest app/service/notebook_test.py -q`
Expected: 20 passed. (If `test_the_name_comes_from_the_dataset_title_and_dodges_collisions` fails on the slug, check `slug_name("GoAmazon T3")` is `goamazon_t3`.)

- [ ] **Step 6: Commit**

```bash
git add app/service/dataset.py app/service/notebook.py app/service/notebook_test.py
git commit -m "feat(notebooks): notebook service — selection, readability and the manifest

Readability is DatasetService.fetch_authorized with READ_FILES, the same call
a download makes, so embargo and sharing need no notebook-specific rule. The
manifest re-checks it at session start: an embargo that began after the
notebook was created stops the copy, not just the page."
```

---

### Task 7: `NotebookSessionService` and metrics

**Files:**
- Modify: `app/metrics.py`, `app/metrics_test.py`
- Create: `app/service/notebook_session.py`, `app/service/notebook_session_test.py`

**Interfaces:**
- Consumes: `NotebookService.fetch_row / published_version / select / adapt`, `adapt_session`, `NotebookRepository`, `NotebookSessionRepository`, `UserRepository.set_notebook_storage_bytes`, `NotebookStorage.usage_bytes`, `NotebookTokenService.mint`, `HubClient.stop_server`.
- Produces:
  - `metrics.notebook_sessions_active(counts: dict[str, int])`, `metrics.notebook_session_request(outcome: str)`, `metrics.notebook_session_ended(stop_reason: str, seconds: float)`.
  - `NotebookSessionService(notebook_service, notebook_repository, session_repository, user_repository, storage, token_service, hub_client, seats, quota_bytes, max_hours, outputs_retention_hours)`: `start(notebook_id, user_id, tenancies, locale) -> SessionStart`, `status(notebook_id, user_id) -> NotebookSession | None`, `stop(notebook_id, user_id, reason=StopReason.USER) -> None`, `delete_notebook(notebook_id, user_id) -> None`, `progress(claims, notebook_id, line) -> None`, `capacity(user_id) -> Capacity`, `mark_started(session_id) -> None`, `mark_stopped(session_id, reason: StopReason | None) -> None`, `purgeable() -> Purgeable`, `mark_session_purged(session_id)`, `mark_outputs_purged(notebook_id)`, `mark_notebook_purged(notebook_id)`.

- [ ] **Step 1: Metrics, test first**

Append to `app/metrics_test.py`:

```python
class TestNotebookSessions(MetricsTestCase):
    def test_active_gauge_is_set_per_kernel_and_zeroed_for_the_missing_one(self):
        self.metrics.notebook_sessions_active({"python3": 3})

        self.assertEqual(
            self.value("datamap_notebook_sessions_active", kernel="python3"), 3.0
        )
        self.assertEqual(self.value("datamap_notebook_sessions_active", kernel="ir"), 0.0)

    def test_requests_are_counted_by_outcome(self):
        self.metrics.notebook_session_request("no_seats")
        self.metrics.notebook_session_request("no_seats")
        self.metrics.notebook_session_request("started")

        self.assertEqual(
            self.value("datamap_notebook_session_requests_total", outcome="no_seats"), 2.0
        )

    def test_duration_is_observed_under_the_stop_reason(self):
        self.metrics.notebook_session_ended("idle", 90.0)

        self.assertEqual(
            self.value(
                "datamap_notebook_session_duration_seconds_count", stop_reason="idle"
            ),
            1.0,
        )
```

Run: `../../../.venv/bin/python -m pytest app/metrics_test.py -q`
Expected: 3 new failures with `AttributeError`

In `app/metrics.py`, inside `Metrics.__init__` after `_email_pending`:

```python
        self._notebook_active = Gauge(
            "datamap_notebook_sessions_active",
            "Notebook sessions starting or running",
            ["kernel"],
            registry=self.registry,
        )
        self._notebook_requests = Counter(
            "datamap_notebook_session_requests_total",
            "Session start requests by outcome",
            ["outcome"],
            registry=self.registry,
        )
        self._notebook_duration = Histogram(
            "datamap_notebook_session_duration_seconds",
            "Wall time from start to stop",
            ["stop_reason"],
            buckets=(60, 300, 900, 1800, 3600, 7200, 14400, 28800, 43200),
            registry=self.registry,
        )
```

and the methods, after `tus_hook`:

```python
    def notebook_sessions_active(self, counts: dict[str, int]) -> None:
        for kernel in NOTEBOOK_KERNELS:
            self._notebook_active.labels(kernel=kernel).set(counts.get(kernel, 0))

    def notebook_session_request(self, outcome: str) -> None:
        self._notebook_requests.labels(outcome=outcome).inc()

    def notebook_session_ended(self, stop_reason: str, seconds: float) -> None:
        self._notebook_duration.labels(stop_reason=stop_reason).observe(seconds)
```

with, at module level next to `AUTH_REASONS`:

```python
NOTEBOOK_KERNELS = ("python3", "ir")
```

Run the metrics tests again. Expected: all passed.

- [ ] **Step 2: Write the failing session service tests**

`app/service/notebook_session_test.py`:

```python
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from app.exception.conflict import ConflictException
from app.exception.not_found import NotFoundException
from app.exception.refused import RefusedException
from app.gateway.jupyterhub.hub_client import HubClient
from app.model.notebook import Kernel, SessionState, StopReason
from app.repository.notebook import NotebookRepository
from app.repository.notebook_session import NotebookSessionRepository
from app.repository.user import UserRepository
from app.service.notebook import NotebookService
from app.service.notebook_session import NotebookSessionService
from app.service.notebook_storage import NotebookStorage
from app.service.notebook_token import NotebookTokenService

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def session_row(**overrides):
    values = dict(
        id=uuid4(), notebook_id=uuid4(), user_id=uuid4(), tenancy="t", kernel="python3",
        state="starting", dataset_id=uuid4(), dataset_version="2", mounted_files=1,
        mounted_bytes=10, requested_at=NOW, started_at=None, stopped_at=None,
        stop_reason=None, stop_requested=None, progress=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class SessionServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.notebook_service = Mock(spec=NotebookService)
        self.notebooks = Mock(spec=NotebookRepository)
        self.sessions = Mock(spec=NotebookSessionRepository)
        self.users = Mock(spec=UserRepository)
        self.storage = Mock(spec=NotebookStorage)
        self.tokens = Mock(spec=NotebookTokenService)
        self.hub = Mock(spec=HubClient)
        self.service = NotebookSessionService(
            notebook_service=self.notebook_service,
            notebook_repository=self.notebooks,
            session_repository=self.sessions,
            user_repository=self.users,
            storage=self.storage,
            token_service=self.tokens,
            hub_client=self.hub,
            seats=4,
            quota_bytes=1000,
            max_hours=12,
            outputs_retention_hours=24,
            data_max_bytes=5000,
        )
        self.user = uuid4()
        self.dataset = SimpleNamespace(id=uuid4(), name="D", tenancy="t")
        self.version = SimpleNamespace(id=uuid4(), name="2", files_in=[])
        self.link = SimpleNamespace(
            position=0, dataset_id=self.dataset.id, dataset_version="2", file_ids=None,
            mounted_files=1, mounted_bytes=10, dataset=self.dataset,
        )
        self.row = SimpleNamespace(
            id=uuid4(), owner_id=self.user, name="n", path="n.ipynb", kernel="python3",
            size_bytes=0, created_at=NOW, updated_at=NOW, deleted_at=None, datasets=[self.link],
        )
        self.notebook_service.fetch_row.return_value = self.row
        self.notebook_service.published_version.return_value = (self.dataset, self.version)
        self.notebook_service.select.return_value = ([SimpleNamespace(size_bytes=10)], 10)
        self.sessions.live_for_user.return_value = None
        self.sessions.latest_for_notebook.return_value = None
        self.sessions.live_count_by_kernel.return_value = {}
        self.sessions.start_if_seat_available.side_effect = lambda row, seats: row
        self.storage.usage_bytes.return_value = 100
        self.tokens.mint.return_value = "tok"


class TestStart(SessionServiceTestCase):
    def test_a_new_session_is_starting_with_a_token_and_the_lab_path(self):
        start = self.service.start(self.row.id, self.user, ["t"], "pt-BR")

        self.assertEqual(start.session.state, SessionState.STARTING)
        self.assertEqual(start.token, "tok")
        self.assertEqual(start.login_url, "/hub/login")
        self.assertEqual(start.lab_path, f"/user/{self.user}/lab/tree/n.ipynb")
        self.assertFalse(start.resumed)
        inserted = self.sessions.start_if_seat_available.call_args.args[0]
        self.assertEqual(inserted.tenancy, "t")
        self.assertEqual(inserted.dataset_id, self.dataset.id)
        self.assertEqual(inserted.mounted_bytes, 10)
        self.tokens.mint.assert_called_once()
        self.assertEqual(
            self.tokens.mint.call_args.kwargs["datasets"],
            [{"id": str(self.dataset.id), "version": "2"}],
        )

    def test_the_quota_is_measured_and_stored_before_the_seat_is_taken(self):
        self.service.start(self.row.id, self.user, ["t"], "en")

        self.users.set_notebook_storage_bytes.assert_called_once_with(self.user, 100)

    def test_over_quota_is_refused_with_the_numbers(self):
        self.storage.usage_bytes.return_value = 1001

        with self.assertRaises(RefusedException) as raised:
            self.service.start(self.row.id, self.user, ["t"], "en")
        self.assertEqual(raised.exception.code, "storage_full")
        self.assertEqual(raised.exception.extra, {"quota_bytes": 1000, "used_bytes": 1001})
        self.sessions.start_if_seat_available.assert_not_called()

    def test_no_seat_is_refused_with_the_total(self):
        self.sessions.start_if_seat_available.side_effect = lambda row, seats: None

        with self.assertRaises(RefusedException) as raised:
            self.service.start(self.row.id, self.user, ["t"], "en")
        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.extra, {"seats_total": 4})

    def test_a_live_session_on_another_notebook_is_a_conflict(self):
        other = session_row(user_id=self.user, notebook_id=uuid4(), state="running")
        self.sessions.live_for_user.return_value = other

        with self.assertRaises(ConflictException) as raised:
            self.service.start(self.row.id, self.user, ["t"], "en")
        self.assertEqual(str(raised.exception), "session_elsewhere")

    def test_a_live_session_on_this_notebook_is_returned_with_a_fresh_token(self):
        live = session_row(user_id=self.user, notebook_id=self.row.id, state="running")
        self.sessions.live_for_user.return_value = live

        start = self.service.start(self.row.id, self.user, ["t"], "en")

        self.assertTrue(start.resumed)
        self.assertEqual(start.session.id, live.id)
        self.sessions.start_if_seat_available.assert_not_called()

    def test_an_unpublished_version_is_refused_before_anything_is_measured(self):
        self.notebook_service.published_version.side_effect = ConflictException(
            "version_not_published"
        )

        with self.assertRaises(ConflictException):
            self.service.start(self.row.id, self.user, ["t"], "en")
        self.storage.usage_bytes.assert_not_called()

    def test_a_deleted_source_is_not_found(self):
        self.link.dataset_id = None

        with self.assertRaises(NotFoundException):
            self.service.start(self.row.id, self.user, ["t"], "en")


class TestStopAndTransitions(SessionServiceTestCase):
    def test_stop_asks_the_hub_then_records_the_stop(self):
        live = session_row(user_id=self.user, notebook_id=self.row.id, state="running", started_at=NOW)
        self.sessions.latest_for_notebook.return_value = live
        self.sessions.set_state.return_value = live

        self.service.stop(self.row.id, self.user)

        self.sessions.set_stop_requested.assert_called_once_with(live.id, StopReason.USER)
        self.hub.stop_server.assert_called_once_with(str(self.user))
        self.assertEqual(
            self.sessions.set_state.call_args.kwargs["stop_reason"], StopReason.USER
        )

    def test_stop_with_no_live_session_is_a_no_op(self):
        self.sessions.latest_for_notebook.return_value = session_row(state="stopped")

        self.service.stop(self.row.id, self.user)

        self.hub.stop_server.assert_not_called()

    def test_a_hub_failure_leaves_the_row_untouched(self):
        self.sessions.latest_for_notebook.return_value = session_row(
            user_id=self.user, notebook_id=self.row.id, state="running"
        )
        self.hub.stop_server.side_effect = RefusedException(503, "hub_unavailable")

        with self.assertRaises(RefusedException):
            self.service.stop(self.row.id, self.user)
        self.sessions.set_state.assert_not_called()

    def test_mark_started_moves_starting_to_running(self):
        row = session_row(state="starting")
        self.sessions.fetch.return_value = row
        self.sessions.set_state.return_value = row

        self.service.mark_started(row.id)

        self.assertEqual(self.sessions.set_state.call_args.args[1], SessionState.RUNNING)

    def test_mark_started_on_a_stopped_row_does_nothing(self):
        self.sessions.fetch.return_value = session_row(state="stopped")

        self.service.mark_started(uuid4())

        self.sessions.set_state.assert_not_called()

    def test_mark_started_on_an_unknown_row_is_not_found(self):
        self.sessions.fetch.return_value = None

        with self.assertRaises(NotFoundException):
            self.service.mark_started(uuid4())

    @patch("app.service.notebook_session.utcnow", return_value=NOW)
    def test_stopped_without_a_reason_is_idle_when_young(self, _):
        row = session_row(state="running", started_at=NOW - timedelta(hours=1))
        self.sessions.fetch.return_value = row
        self.sessions.set_state.return_value = row

        self.service.mark_stopped(row.id, None)

        kwargs = self.sessions.set_state.call_args.kwargs
        self.assertEqual(self.sessions.set_state.call_args.args[1], SessionState.STOPPED)
        self.assertEqual(kwargs["stop_reason"], StopReason.IDLE)

    @patch("app.service.notebook_session.utcnow", return_value=NOW)
    def test_stopped_without_a_reason_is_max_age_after_twelve_hours(self, _):
        row = session_row(state="running", started_at=NOW - timedelta(hours=12, minutes=1))
        self.sessions.fetch.return_value = row
        self.sessions.set_state.return_value = row

        self.service.mark_stopped(row.id, None)

        self.assertEqual(self.sessions.set_state.call_args.args[1], SessionState.ENDED)
        self.assertEqual(
            self.sessions.set_state.call_args.kwargs["stop_reason"], StopReason.MAX_AGE
        )

    def test_stopped_without_a_reason_uses_the_recorded_request(self):
        row = session_row(state="running", started_at=NOW, stop_requested="admin")
        self.sessions.fetch.return_value = row
        self.sessions.set_state.return_value = row

        self.service.mark_stopped(row.id, None)

        self.assertEqual(
            self.sessions.set_state.call_args.kwargs["stop_reason"], StopReason.ADMIN
        )

    def test_spawn_error_is_failed(self):
        row = session_row(state="starting")
        self.sessions.fetch.return_value = row
        self.sessions.set_state.return_value = row

        self.service.mark_stopped(row.id, StopReason.SPAWN_ERROR)

        self.assertEqual(self.sessions.set_state.call_args.args[1], SessionState.FAILED)

    def test_stopped_twice_is_idempotent(self):
        self.sessions.fetch.return_value = session_row(state="stopped")

        self.service.mark_stopped(uuid4(), StopReason.IDLE)

        self.sessions.set_state.assert_not_called()


class TestProgressStatusCapacity(SessionServiceTestCase):
    def test_progress_appends_to_the_claims_session_only(self):
        claims = SimpleNamespace(notebook_id=self.row.id, session_id=uuid4(), user_id=self.user)

        self.service.progress(claims, self.row.id, "Mounting")

        self.sessions.append_progress.assert_called_once_with(claims.session_id, "Mounting")

    def test_progress_for_another_notebook_is_not_found(self):
        claims = SimpleNamespace(notebook_id=uuid4(), session_id=uuid4(), user_id=self.user)

        with self.assertRaises(NotFoundException):
            self.service.progress(claims, self.row.id, "x")

    def test_status_is_none_when_the_notebook_never_ran(self):
        self.assertIsNone(self.service.status(self.row.id, self.user))

    def test_capacity_reads_seats_and_the_users_storage(self):
        self.sessions.count_live.return_value = 3
        self.storage.usage_bytes.return_value = 5

        capacity = self.service.capacity(self.user)

        self.assertEqual((capacity.seats_taken, capacity.seats_total), (3, 4))
        self.assertEqual((capacity.storage_used_bytes, capacity.storage_quota_bytes), (5, 1000))
        self.assertEqual(capacity.data_max_bytes, 5000)


class TestPurgeable(SessionServiceTestCase):
    @patch("app.service.notebook_session.utcnow", return_value=NOW)
    def test_lists_sessions_outputs_and_deleted_notebooks(self, _):
        self.sessions.list_unpurged_not_live.return_value = [session_row(id=uuid4(), user_id=self.user)]
        self.notebooks.list_outputs_purgeable.return_value = [self.row]
        self.notebooks.list_deleted_unpurged.return_value = [self.row]

        purgeable = self.service.purgeable()

        self.notebooks.list_outputs_purgeable.assert_called_once_with(NOW - timedelta(hours=24))
        self.assertEqual(purgeable.sessions[0]["user_id"], str(self.user))
        self.assertEqual(purgeable.outputs[0]["notebook_id"], str(self.row.id))
        self.assertEqual(purgeable.notebooks[0]["path"], "n.ipynb")
```

- [ ] **Step 3: Run to verify they fail, then write the service**

Run: `../../../.venv/bin/python -m pytest app/service/notebook_session_test.py -q`
Expected: FAIL with `ModuleNotFoundError`

`app/service/notebook_session.py`:

```python
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.exception.conflict import ConflictException
from app.exception.not_found import NotFoundException
from app.exception.refused import RefusedException
from app.gateway.jupyterhub.hub_client import HubClient
from app.logging_config import fields
from app.metrics import metrics
from app.model.db.notebook import NotebookSession as NotebookSessionDBModel
from app.model.notebook import (
    LIVE_STATES,
    Capacity,
    NotebookSession,
    Purgeable,
    SessionClaims,
    SessionStart,
    SessionState,
    StopReason,
    lab_path,
)
from app.repository.notebook import NotebookRepository
from app.repository.notebook_session import NotebookSessionRepository
from app.repository.user import UserRepository
from app.service.notebook import NotebookService, adapt_session
from app.service.notebook_storage import NotebookStorage
from app.service.notebook_token import NotebookTokenService

LIVE_VALUES = {state.value for state in LIVE_STATES}
LOGIN_URL = "/hub/login"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NotebookSessionService:
    def __init__(
        self,
        notebook_service: NotebookService,
        notebook_repository: NotebookRepository,
        session_repository: NotebookSessionRepository,
        user_repository: UserRepository,
        storage: NotebookStorage,
        token_service: NotebookTokenService,
        hub_client: HubClient,
        seats: int,
        quota_bytes: int,
        max_hours: int,
        outputs_retention_hours: int,
        data_max_bytes: int,
    ) -> None:
        self._notebooks = notebook_service
        self._notebook_repository = notebook_repository
        self._sessions = session_repository
        self._users = user_repository
        self._storage = storage
        self._tokens = token_service
        self._hub = hub_client
        self._seats = seats
        self._quota = quota_bytes
        self._max_age = timedelta(hours=max_hours)
        self._outputs_retention = timedelta(hours=outputs_retention_hours)
        self._data_max_bytes = data_max_bytes
        self._logger = logging.getLogger("service:notebook_session")

    def start(
        self, notebook_id: UUID, user_id: UUID, tenancies: list[str], locale: str
    ) -> SessionStart:
        row = self._notebooks.fetch_row(notebook_id, user_id)
        link = row.datasets[0]
        if link.dataset_id is None:
            raise NotFoundException("not_found: source deleted")

        live = self._sessions.live_for_user(user_id)
        if live is not None and live.notebook_id == row.id:
            metrics.notebook_session_request("resumed")
            return self._start_result(row, live, tenancies, locale, resumed=True)
        if live is not None:
            metrics.notebook_session_request("elsewhere")
            raise ConflictException("session_elsewhere")

        dataset, version = self._notebooks.published_version(
            link.dataset_id, link.dataset_version, user_id, tenancies
        )
        file_ids = [UUID(x) for x in link.file_ids] if link.file_ids else None
        files, total = self._notebooks.select(version, file_ids)

        used = self._storage.usage_bytes(user_id)
        self._users.set_notebook_storage_bytes(user_id, used)
        if used > self._quota:
            metrics.notebook_session_request("storage_full")
            raise RefusedException(
                413, "storage_full", quota_bytes=self._quota, used_bytes=used
            )

        session = NotebookSessionDBModel(
            notebook_id=row.id,
            user_id=user_id,
            tenancy=dataset.tenancy or "",
            dataset_id=dataset.id,
            dataset_version=version.name,
            kernel=row.kernel,
            state=SessionState.STARTING.value,
            mounted_files=len(files),
            mounted_bytes=total,
            progress=[],
        )
        inserted = self._sessions.start_if_seat_available(session, self._seats)
        if inserted is None:
            metrics.notebook_session_request("no_seats")
            raise RefusedException(429, "no_seats", seats_total=self._seats)
        metrics.notebook_session_request("started")
        self._refresh_gauge()
        self._logger.info(
            "session requested",
            extra=fields(
                session_id=str(inserted.id),
                notebook_id=str(row.id),
                dataset_id=str(dataset.id),
                kernel=row.kernel,
                mounted_bytes=total,
            ),
        )
        return self._start_result(row, inserted, tenancies, locale, resumed=False)

    def _start_result(self, row, session_row, tenancies, locale, resumed) -> SessionStart:
        datasets = [
            {"id": str(link.dataset_id), "version": link.dataset_version}
            for link in row.datasets
        ]
        token = self._tokens.mint(
            session_row, tenancies=tenancies, datasets=datasets, locale=locale
        )
        return SessionStart(
            session=adapt_session(session_row),
            token=token,
            login_url=LOGIN_URL,
            lab_path=lab_path(row.owner_id, row.path),
            resumed=resumed,
        )

    def status(self, notebook_id: UUID, user_id: UUID) -> NotebookSession | None:
        row = self._notebooks.fetch_row(notebook_id, user_id)
        latest = self._sessions.latest_for_notebook(row.id)
        return adapt_session(latest) if latest is not None else None

    def stop(
        self, notebook_id: UUID, user_id: UUID, reason: StopReason = StopReason.USER
    ) -> None:
        row = self._notebooks.fetch_row(notebook_id, user_id)
        latest = self._sessions.latest_for_notebook(row.id)
        if latest is None or latest.state not in LIVE_VALUES:
            return
        self._sessions.set_stop_requested(latest.id, reason)
        self._hub.stop_server(str(latest.user_id))
        self._finish(latest, reason)

    def delete_notebook(self, notebook_id: UUID, user_id: UUID) -> None:
        self.stop(notebook_id, user_id)
        self._notebooks.soft_delete(notebook_id, user_id)

    def progress(self, claims: SessionClaims, notebook_id: UUID, line: str) -> None:
        if claims.notebook_id != notebook_id:
            raise NotFoundException(f"not_found: {notebook_id}")
        self._sessions.append_progress(claims.session_id, line)

    def capacity(self, user_id: UUID) -> Capacity:
        return Capacity(
            seats_taken=self._sessions.count_live(),
            seats_total=self._seats,
            storage_used_bytes=self._storage.usage_bytes(user_id),
            storage_quota_bytes=self._quota,
            data_max_bytes=self._data_max_bytes,
        )

    def mark_started(self, session_id: UUID) -> None:
        row = self._sessions.fetch(session_id)
        if row is None:
            raise NotFoundException(f"not_found: {session_id}")
        if row.state != SessionState.STARTING.value:
            return
        self._sessions.set_state(row.id, SessionState.RUNNING, started_at=utcnow())
        self._refresh_gauge()

    def mark_stopped(self, session_id: UUID, reason: StopReason | None) -> None:
        row = self._sessions.fetch(session_id)
        if row is None:
            raise NotFoundException(f"not_found: {session_id}")
        if row.state not in LIVE_VALUES:
            return
        self._finish(row, reason or self._derive_reason(row))

    def _derive_reason(self, row) -> StopReason:
        if row.stop_requested:
            return StopReason(row.stop_requested)
        if row.started_at is not None and utcnow() - row.started_at >= self._max_age:
            return StopReason.MAX_AGE
        return StopReason.IDLE

    def _finish(self, row, reason: StopReason) -> None:
        state = {
            StopReason.MAX_AGE: SessionState.ENDED,
            StopReason.SPAWN_ERROR: SessionState.FAILED,
        }.get(reason, SessionState.STOPPED)
        now = utcnow()
        self._sessions.set_state(row.id, state, stopped_at=now, stop_reason=reason)
        if row.started_at is not None:
            metrics.notebook_session_ended(
                reason.value, (now - row.started_at).total_seconds()
            )
        self._refresh_gauge()
        self._logger.info(
            "session finished",
            extra=fields(
                session_id=str(row.id),
                notebook_id=str(row.notebook_id),
                dataset_id=str(row.dataset_id),
                stop_reason=reason.value,
            ),
        )

    def _refresh_gauge(self) -> None:
        metrics.notebook_sessions_active(self._sessions.live_count_by_kernel())

    def purgeable(self) -> Purgeable:
        before = utcnow() - self._outputs_retention
        return Purgeable(
            sessions=[
                {"id": str(s.id), "user_id": str(s.user_id)}
                for s in self._sessions.list_unpurged_not_live()
            ],
            outputs=[
                {"notebook_id": str(n.id), "user_id": str(n.owner_id)}
                for n in self._notebook_repository.list_outputs_purgeable(before)
            ],
            notebooks=[
                {"notebook_id": str(n.id), "user_id": str(n.owner_id), "path": n.path}
                for n in self._notebook_repository.list_deleted_unpurged()
            ],
        )

    def mark_session_purged(self, session_id: UUID) -> None:
        self._sessions.mark_data_purged(session_id)

    def mark_outputs_purged(self, notebook_id: UUID) -> None:
        self._notebook_repository.mark_outputs_purged(notebook_id)

    def mark_notebook_purged(self, notebook_id: UUID) -> None:
        self._notebook_repository.mark_file_purged(notebook_id)
```

- [ ] **Step 4: Run the tests**

Run: `../../../.venv/bin/python -m pytest app/service/notebook_session_test.py app/metrics_test.py -q`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add app/metrics.py app/metrics_test.py app/service/notebook_session.py app/service/notebook_session_test.py
git commit -m "feat(notebooks): session lifecycle — seats, quota, token, hub stop, transitions

The seat is taken last, after readability and quota, so a refused request
never holds one. A stop reason the hub cannot name is derived here: the
recorded request, else max_age past twelve hours, else idle."
```

---

### Task 8: Routes, container wiring and the application

**Files:**
- Create: `app/controller/v1/notebook/__init__.py`, `app/controller/v1/notebook/resource.py`, `app/controller/v1/notebook/notebook.py`
- Create: `app/controller/v1/internal/notebook_session.py`; modify `app/controller/v1/internal/resource.py`
- Modify: `app/container.py`, `app/setup.py`

**Interfaces:**
- Consumes: everything from Tasks 1–7.
- Produces: the routes in the contracts; `Container.notebook_session_auth`, `Container.notebook_service`, `Container.notebook_session_service`.

- [ ] **Step 1: Response and request models**

`app/controller/v1/notebook/__init__.py`: empty.

`app/controller/v1/notebook/resource.py`:

```python
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.model.notebook import Kernel, SessionState, StopReason


class NotebookDatasetResponse(BaseModel):
    id: Optional[UUID] = Field(None, title="Dataset ID")
    title: Optional[str] = Field(None, title="Dataset title")
    version_name: Optional[str] = Field(None, title="Pinned version")
    source_deleted: bool = Field(False, title="The dataset is gone")


class SessionResponse(BaseModel):
    id: UUID
    state: SessionState
    stop_reason: Optional[StopReason] = None
    requested_at: datetime
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    mounted_files: int = 0
    mounted_bytes: int = 0
    progress: list[str] = Field(default_factory=list)
    max_hours: int


class NotebookResponse(BaseModel):
    id: UUID
    name: str
    path: str
    kernel: Kernel
    size_bytes: int
    created_at: datetime
    updated_at: datetime
    dataset: Optional[NotebookDatasetResponse] = None
    file_ids: Optional[list[UUID]] = None
    mounted_files: int
    mounted_bytes: int
    session: Optional[SessionResponse] = None


class NotebookListResponse(BaseModel):
    content: list[NotebookResponse]


class NotebookCreateRequest(BaseModel):
    dataset_id: UUID
    version_name: str = Field(..., min_length=1, max_length=256)
    kernel: Kernel
    name: Optional[str] = Field(None, max_length=128)
    file_ids: Optional[list[UUID]] = None


class NotebookUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    file_ids: Optional[list[UUID]] = None


class SessionStartRequest(BaseModel):
    locale: str = Field("pt-BR", max_length=16)


class SessionStartResponse(BaseModel):
    session: SessionResponse
    token: str
    login_url: str
    lab_path: str


class SessionStatusResponse(BaseModel):
    state: Optional[SessionState] = None
    id: Optional[UUID] = None
    stop_reason: Optional[StopReason] = None
    requested_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    mounted_files: int = 0
    mounted_bytes: int = 0
    progress: list[str] = Field(default_factory=list)
    max_hours: int


class CapacityResponse(BaseModel):
    seats_taken: int
    seats_total: int
    storage_used_bytes: int
    storage_quota_bytes: int
    data_max_bytes: int


class ProgressRequest(BaseModel):
    line: str = Field(..., min_length=1, max_length=200)


class ManifestFileResponse(BaseModel):
    id: UUID
    name: str
    size_bytes: int
    relative_path: str
    url: str


class ManifestDatasetResponse(BaseModel):
    dataset_id: UUID
    dataset_title: str
    version_name: str
    mount_path: str
    file_count: int
    total_bytes: int
    files: list[ManifestFileResponse]


class ManifestResponse(BaseModel):
    notebook_id: UUID
    notebook_path: str
    notebook_exists: bool
    kernel: Kernel
    outputs_path: str
    datasets: list[ManifestDatasetResponse]
```

Append to `app/controller/v1/internal/resource.py`:

```python
class NotebookSessionStoppedRequest(BaseModel):
    reason: Optional[str] = Field(
        None, title="idle | user | admin | max_age | spawn_error; derived when absent"
    )


class PurgeableResponse(BaseModel):
    sessions: list[dict] = Field(default_factory=list)
    outputs: list[dict] = Field(default_factory=list)
    notebooks: list[dict] = Field(default_factory=list)
```

- [ ] **Step 2: The user and bearer router**

`app/controller/v1/notebook/notebook.py`:

```python
from typing import Optional
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, Response

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.tenancy_parser import parse_tenancy_header
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.notebook.resource import (
    CapacityResponse,
    ManifestDatasetResponse,
    ManifestFileResponse,
    ManifestResponse,
    NotebookCreateRequest,
    NotebookDatasetResponse,
    NotebookListResponse,
    NotebookResponse,
    NotebookUpdateRequest,
    ProgressRequest,
    SessionResponse,
    SessionStartRequest,
    SessionStartResponse,
    SessionStatusResponse,
)
from app.exception.not_found import NotFoundException
from app.model.notebook import Manifest, Notebook, NotebookSession
from app.service.notebook import NOT_SET, NotebookService
from app.service.notebook_session import NotebookSessionService

router = APIRouter(
    prefix="/notebooks",
    tags=["notebooks"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


def _session(session: NotebookSession, max_hours: int) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        state=session.state,
        stop_reason=session.stop_reason,
        requested_at=session.requested_at,
        started_at=session.started_at,
        stopped_at=session.stopped_at,
        mounted_files=session.mounted_files,
        mounted_bytes=session.mounted_bytes,
        progress=session.progress,
        max_hours=max_hours,
    )


def _notebook(notebook: Notebook, max_hours: int) -> NotebookResponse:
    dataset = notebook.dataset
    return NotebookResponse(
        id=notebook.id,
        name=notebook.name,
        path=notebook.path,
        kernel=notebook.kernel,
        size_bytes=notebook.size_bytes,
        created_at=notebook.created_at,
        updated_at=notebook.updated_at,
        dataset=NotebookDatasetResponse(
            id=dataset.dataset_id,
            title=dataset.title,
            version_name=dataset.version_name,
            source_deleted=dataset.source_deleted,
        )
        if dataset is not None
        else None,
        file_ids=dataset.file_ids if dataset is not None else None,
        mounted_files=notebook.mounted_files,
        mounted_bytes=notebook.mounted_bytes,
        session=_session(notebook.session, max_hours) if notebook.session else None,
    )


def _manifest(manifest: Manifest) -> ManifestResponse:
    return ManifestResponse(
        notebook_id=manifest.notebook_id,
        notebook_path=manifest.notebook_path,
        notebook_exists=manifest.notebook_exists,
        kernel=manifest.kernel,
        outputs_path=manifest.outputs_path,
        datasets=[
            ManifestDatasetResponse(
                dataset_id=d.dataset_id,
                dataset_title=d.dataset_title,
                version_name=d.version_name,
                mount_path=d.mount_path,
                file_count=d.file_count,
                total_bytes=d.total_bytes,
                files=[
                    ManifestFileResponse(
                        id=f.id,
                        name=f.name,
                        size_bytes=f.size_bytes,
                        relative_path=f.relative_path,
                        url=f.url,
                    )
                    for f in d.files
                ],
            )
            for d in manifest.datasets
        ],
    )


def _claims(request: Request):
    claims = getattr(request.state, "session_claims", None)
    if claims is None:
        raise NotFoundException("not_found: bearer route")
    return claims


@router.get("/-/capacity", response_model=CapacityResponse)
@inject
def capacity(
    user_id: UUID = Depends(parse_user_header),
    service: NotebookSessionService = Depends(
        Provide[Container.notebook_session_service]
    ),
) -> CapacityResponse:
    capacity = service.capacity(user_id)
    return CapacityResponse(
        seats_taken=capacity.seats_taken,
        seats_total=capacity.seats_total,
        storage_used_bytes=capacity.storage_used_bytes,
        storage_quota_bytes=capacity.storage_quota_bytes,
        data_max_bytes=capacity.data_max_bytes,
    )


@router.get("/", response_model=NotebookListResponse)
@inject
def list_notebooks(
    dataset_id: Optional[UUID] = None,
    user_id: UUID = Depends(parse_user_header),
    service: NotebookService = Depends(Provide[Container.notebook_service]),
    max_hours: int = Depends(Provide[Container.config.NOTEBOOK_SESSION_MAX_HOURS]),
) -> NotebookListResponse:
    notebooks = service.list(user_id, dataset_id=dataset_id)
    return NotebookListResponse(content=[_notebook(n, max_hours) for n in notebooks])


@router.post("/", status_code=201, response_model=NotebookResponse)
@inject
def create_notebook(
    payload: NotebookCreateRequest,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: NotebookService = Depends(Provide[Container.notebook_service]),
    max_hours: int = Depends(Provide[Container.config.NOTEBOOK_SESSION_MAX_HOURS]),
) -> NotebookResponse:
    notebook = service.create(
        owner_id=user_id,
        tenancies=tenancies,
        dataset_id=payload.dataset_id,
        version_name=payload.version_name,
        kernel=payload.kernel,
        name=payload.name,
        file_ids=payload.file_ids,
    )
    return _notebook(notebook, max_hours)


@router.get("/{notebook_id}", response_model=NotebookResponse)
@inject
def get_notebook(
    notebook_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: NotebookService = Depends(Provide[Container.notebook_service]),
    max_hours: int = Depends(Provide[Container.config.NOTEBOOK_SESSION_MAX_HOURS]),
) -> NotebookResponse:
    return _notebook(service.fetch(notebook_id, user_id), max_hours)


@router.patch("/{notebook_id}", response_model=NotebookResponse)
@inject
def update_notebook(
    notebook_id: UUID,
    payload: NotebookUpdateRequest,
    user_id: UUID = Depends(parse_user_header),
    service: NotebookService = Depends(Provide[Container.notebook_service]),
    max_hours: int = Depends(Provide[Container.config.NOTEBOOK_SESSION_MAX_HOURS]),
) -> NotebookResponse:
    file_ids = payload.file_ids if "file_ids" in payload.model_fields_set else NOT_SET
    notebook = service.update(notebook_id, user_id, name=payload.name, file_ids=file_ids)
    return _notebook(notebook, max_hours)


@router.delete("/{notebook_id}", status_code=204)
@inject
def delete_notebook(
    notebook_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: NotebookSessionService = Depends(
        Provide[Container.notebook_session_service]
    ),
) -> Response:
    service.delete_notebook(notebook_id, user_id)
    return Response(status_code=204)


@router.get("/{notebook_id}/content")
@inject
def get_content(
    notebook_id: UUID,
    download: bool = False,
    user_id: UUID = Depends(parse_user_header),
    service: NotebookService = Depends(Provide[Container.notebook_service]),
) -> Response:
    data = service.content(notebook_id, user_id)
    notebook = service.fetch(notebook_id, user_id)
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{notebook.path}"'
    return Response(content=data, media_type="application/json", headers=headers)


@router.post("/{notebook_id}/sessions", response_model=SessionStartResponse)
@inject
def start_session(
    notebook_id: UUID,
    payload: SessionStartRequest,
    response: Response,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: NotebookSessionService = Depends(
        Provide[Container.notebook_session_service]
    ),
    max_hours: int = Depends(Provide[Container.config.NOTEBOOK_SESSION_MAX_HOURS]),
) -> SessionStartResponse:
    start = service.start(notebook_id, user_id, tenancies, payload.locale)
    response.status_code = 200 if start.resumed else 201
    return SessionStartResponse(
        session=_session(start.session, max_hours),
        token=start.token,
        login_url=start.login_url,
        lab_path=start.lab_path,
    )


@router.get("/{notebook_id}/session", response_model=SessionStatusResponse)
@inject
def session_status(
    notebook_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: NotebookSessionService = Depends(
        Provide[Container.notebook_session_service]
    ),
    max_hours: int = Depends(Provide[Container.config.NOTEBOOK_SESSION_MAX_HOURS]),
) -> SessionStatusResponse:
    session = service.status(notebook_id, user_id)
    if session is None:
        return SessionStatusResponse(max_hours=max_hours)
    return SessionStatusResponse(**_session(session, max_hours).model_dump())


@router.delete("/{notebook_id}/session", status_code=204)
@inject
def stop_session(
    notebook_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: NotebookSessionService = Depends(
        Provide[Container.notebook_session_service]
    ),
) -> Response:
    service.stop(notebook_id, user_id)
    return Response(status_code=204)


@router.get("/{notebook_id}/manifest", response_model=ManifestResponse)
@inject
def manifest(
    notebook_id: UUID,
    request: Request,
    service: NotebookService = Depends(Provide[Container.notebook_service]),
) -> ManifestResponse:
    return _manifest(service.manifest(_claims(request), notebook_id))


@router.post("/{notebook_id}/session/progress", status_code=204)
@inject
def report_progress(
    notebook_id: UUID,
    payload: ProgressRequest,
    request: Request,
    service: NotebookSessionService = Depends(
        Provide[Container.notebook_session_service]
    ),
) -> Response:
    service.progress(_claims(request), notebook_id, payload.line)
    return Response(status_code=204)
```

Route order matters: `/-/capacity` is declared before `/{notebook_id}` so FastAPI does not try to parse `-` as a UUID.

- [ ] **Step 3: The internal router**

`app/controller/v1/internal/notebook_session.py`:

```python
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.v1.internal.resource import (
    NotebookSessionStoppedRequest,
    PurgeableResponse,
)
from app.model.notebook import StopReason
from app.service.notebook_session import NotebookSessionService

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(authenticate)],
    responses={404: {"description": "Not found"}},
)


@router.post("/notebook-sessions/{session_id}/started", status_code=204)
@inject
def session_started(
    session_id: UUID,
    service: NotebookSessionService = Depends(
        Provide[Container.notebook_session_service]
    ),
) -> Response:
    service.mark_started(session_id)
    return Response(status_code=204)


@router.post("/notebook-sessions/{session_id}/stopped", status_code=204)
@inject
def session_stopped(
    session_id: UUID,
    payload: NotebookSessionStoppedRequest | None = None,
    service: NotebookSessionService = Depends(
        Provide[Container.notebook_session_service]
    ),
) -> Response:
    reason = StopReason(payload.reason) if payload and payload.reason else None
    service.mark_stopped(session_id, reason)
    return Response(status_code=204)


@router.get("/notebook-sessions/purgeable", response_model=PurgeableResponse)
@inject
def purgeable(
    service: NotebookSessionService = Depends(
        Provide[Container.notebook_session_service]
    ),
) -> PurgeableResponse:
    result = service.purgeable()
    return PurgeableResponse(
        sessions=result.sessions, outputs=result.outputs, notebooks=result.notebooks
    )


@router.post("/notebook-sessions/{session_id}/purged", status_code=204)
@inject
def session_purged(
    session_id: UUID,
    service: NotebookSessionService = Depends(
        Provide[Container.notebook_session_service]
    ),
) -> Response:
    service.mark_session_purged(session_id)
    return Response(status_code=204)


@router.post("/notebooks/{notebook_id}/outputs-purged", status_code=204)
@inject
def outputs_purged(
    notebook_id: UUID,
    service: NotebookSessionService = Depends(
        Provide[Container.notebook_session_service]
    ),
) -> Response:
    service.mark_outputs_purged(notebook_id)
    return Response(status_code=204)


@router.post("/notebooks/{notebook_id}/purged", status_code=204)
@inject
def notebook_purged(
    notebook_id: UUID,
    service: NotebookSessionService = Depends(
        Provide[Container.notebook_session_service]
    ),
) -> Response:
    service.mark_notebook_purged(notebook_id)
    return Response(status_code=204)
```

`/notebook-sessions/purgeable` is declared after `/{session_id}/started` and `/{session_id}/stopped`; those have a trailing segment, so `purgeable` cannot collide with them. Keep it before `/{session_id}/purged`? It cannot collide with that either (different trailing segment). Order is fine as written.

- [ ] **Step 4: Container and routes**

In `app/container.py`:

Imports:

```python
from app.gateway.jupyterhub.hub_client import HubClient
from app.repository.notebook import NotebookRepository
from app.repository.notebook_session import NotebookSessionRepository
from app.service.notebook import NotebookService
from app.service.notebook_session import NotebookSessionService
from app.service.notebook_session_auth import NotebookSessionAuth
from app.service.notebook_storage import NotebookStorage
from app.service.notebook_token import NotebookTokenService
```

`wiring_config.modules` gains:

```python
            "app.controller.v1.notebook.notebook",
            "app.controller.v1.internal.notebook_session",
```

Providers, after `embargo_notification_service`:

```python
    notebook_repository = providers.Factory(
        NotebookRepository,
        session_factory=db.provided.session,
    )

    notebook_session_repository = providers.Factory(
        NotebookSessionRepository,
        session_factory=db.provided.session,
    )

    notebook_token_service = providers.Singleton(
        NotebookTokenService,
        secret=config.AUTH_NOTEBOOK_SESSION_TOKEN_SECRET,
        max_hours=config.NOTEBOOK_SESSION_MAX_HOURS,
    )

    notebook_storage = providers.Singleton(
        NotebookStorage,
        root=config.NOTEBOOK_STORAGE_PATH,
    )

    hub_client = providers.Singleton(
        HubClient,
        base_url=config.NOTEBOOK_HUB_URL,
        api_token=config.NOTEBOOK_HUB_API_TOKEN,
        timeout_seconds=config.NOTEBOOK_HUB_TIMEOUT_SECONDS,
    )

    notebook_session_auth = providers.Factory(
        NotebookSessionAuth,
        token_service=notebook_token_service,
        session_repository=notebook_session_repository,
    )

    notebook_service = providers.Factory(
        NotebookService,
        repository=notebook_repository,
        session_repository=notebook_session_repository,
        dataset_service=dataset_service,
        version_repository=dataset_version_repository,
        storage=notebook_storage,
        data_max_bytes=config.NOTEBOOK_DATA_MAX_BYTES,
    )

    notebook_session_service = providers.Factory(
        NotebookSessionService,
        notebook_service=notebook_service,
        notebook_repository=notebook_repository,
        session_repository=notebook_session_repository,
        user_repository=user_repository,
        storage=notebook_storage,
        token_service=notebook_token_service,
        hub_client=hub_client,
        seats=config.NOTEBOOK_SEATS,
        quota_bytes=config.NOTEBOOK_STORAGE_QUOTA_BYTES,
        max_hours=config.NOTEBOOK_SESSION_MAX_HOURS,
        outputs_retention_hours=config.NOTEBOOK_OUTPUTS_RETENTION_HOURS,
        data_max_bytes=config.NOTEBOOK_DATA_MAX_BYTES,
    )
```

`config.from_dict(settings.model_dump())` gives every setting as a provider; `config.NOTEBOOK_SESSION_MAX_HOURS` is what the routes inject. If `Provide[Container.config.NOTEBOOK_SESSION_MAX_HOURS]` arrives as a string under `from_dict`, coerce in the route with `int(...)`; check once by calling `GET /notebooks/-/capacity` in Step 6.

In `app/setup.py`, import the two routers:

```python
from app.controller.v1.notebook.notebook import router as notebook_router
from app.controller.v1.internal.notebook_session import (
    router as internal_notebook_session_router,
)
```

and in `setup_routes`, after `internal_notification_router`:

```python
    fastAPIApp.include_router(notebook_router, prefix="/v1")
    fastAPIApp.include_router(internal_notebook_session_router, prefix="/v1")
```

- [ ] **Step 5: Boot the application locally**

```bash
make ENV_FILE_PATH=local.env python-run
```

Expected: uvicorn starts, the migration log shows `b8c9d0e1f2a3` applied (or already at head), no import error. Then, in another shell, with a local client key from your `local.env` or the admin bootstrap:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9092/api/v1/notebooks/-/capacity \
  -H "X-Api-Key: $KEY" -H "X-Api-Secret: $SECRET" -H "X-User-Id: $ADMIN_USER_ID"
```

Expected: `200`. With a made-up bearer token: `curl -s http://localhost:9092/api/v1/notebooks/ -H "Authorization: Bearer x"` → `401`.

- [ ] **Step 6: Unit suite and lint**

Run: `../../../.venv/bin/python -m pytest -q && ruff check && ruff format`
Expected: all passed; format leaves the tree clean (commit anything it touched)

- [ ] **Step 7: Commit**

```bash
git add app/controller/v1/notebook app/controller/v1/internal/notebook_session.py \
  app/controller/v1/internal/resource.py app/container.py app/setup.py
git commit -m "feat(notebooks): notebook, session, manifest and internal routes

User routes under /notebooks, bearer-only manifest and progress on the same
router (Casbin keeps the token on those two), hub and archivist routes under
/internal. The capacity route is declared before /{id} so '-' is never parsed
as a UUID."
```

---

### Task 9: Integration tests

**Files:**
- Modify: `docker-compose-integration-test.yaml`
- Create: `tests/integration/wiremock/mappings/hub_stop_server.json`
- Create: `tests/integration/fixtures/notebooks.py`
- Create: `tests/integration/test_notebooks_api.py`

The integration env from Task 1 sets `NOTEBOOK_SEATS=2`, `NOTEBOOK_DATA_MAX_BYTES=4096` and `NOTEBOOK_STORAGE_QUOTA_BYTES=2097152` so the limits can be hit with small fixtures.

- [ ] **Step 1: Compose changes**

In `docker-compose-integration-test.yaml`, on `gatekeeper_test_integration` add:

```yaml
    volumes:
      - storage_test_integration:/storage:ro
```

and add a helper that can write to the same volume (the gatekeeper's mount is read-only on purpose; the quota test needs to put bytes there):

```yaml
  storage_helper_test_integration:
    image: alpine:3.20
    container_name: datamap_storage_helper_test_integration
    command: ["sleep", "infinity"]
    volumes:
      - storage_test_integration:/storage
    networks:
      - gatekeeper_integration-test-network
    healthcheck:
      test: ["CMD", "true"]
      interval: 30s
```

(The CI step "Every container must report healthy" greps `test_integration` containers for `(healthy)`; a container without a healthcheck shows no status, so the trivial healthcheck above keeps that gate honest.)

- [ ] **Step 2: WireMock stub for the hub**

`tests/integration/wiremock/mappings/hub_stop_server.json`:

```json
{
  "request": {
    "method": "DELETE",
    "urlPathPattern": "/hub/api/users/[^/]+/server",
    "headers": {"Authorization": {"equalTo": "token integration-hub-token"}}
  },
  "response": {"status": 204}
}
```

- [ ] **Step 3: Fixtures**

`tests/integration/fixtures/notebooks.py`:

```python
import subprocess
import uuid

import jwt

from tests.integration.config import config
from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.embargo import create_user, headers_for
from tests.integration.fixtures.tus_auth import create_tus_payload
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.http_client import HttpClient

SESSION_TOKEN_SECRET = "notebook-session-fake-secret"
STORAGE_HELPER = "datamap_storage_helper_test_integration"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def admin_user(http_client: HttpClient) -> str:
    """A second administrator, in the test tenancy, so two people can hold seats."""
    return create_user(http_client, roles=["admin"], tenancies=[config.tenancy])


def published_dataset(
    http_client: HttpClient,
    dataset_fixture,
    file_sizes: list[int] = (1024,),
    headers: dict | None = None,
) -> dict:
    """A dataset with one published version holding one file per size.

    Returns {"id", "version_name", "file_ids"}.
    """
    headers = headers or AuthFixture.valid_headers()
    user_id = headers["X-User-Id"]
    response = http_client.post(
        "/datasets", json=dataset_fixture.get_basic_dataset_data(), headers=headers
    )
    assert_status_code(response, 201)
    dataset = response.json()
    dataset_id = dataset["id"]
    for index, size in enumerate(file_sizes):
        payload = create_tus_payload(
            user_id=user_id,
            dataset_id=dataset_id,
            filename=f"file_{index}.nc",
            file_size=size,
            file_type="application/x-netcdf",
        )
        hook = http_client.post("/tus/hooks", json=payload, headers=headers)
        assert_status_code(hook, 200)
    detail = http_client.get(f"/datasets/{dataset_id}", headers=headers)
    assert_status_code(detail, 200)
    version = detail.json()["current_version"]
    version_name = version["name"]
    enable = http_client.put(
        f"/datasets/{dataset_id}/versions/{version_name}/enable", headers=headers
    )
    assert_status_code(enable, 200)
    publish = http_client.put(
        f"/datasets/{dataset_id}/versions/{version_name}/publish", headers=headers
    )
    assert_status_code(publish, 200)
    detail = http_client.get(
        f"/datasets/{dataset_id}/versions/{version_name}", headers=headers
    )
    assert_status_code(detail, 200)
    file_ids = [f["id"] for f in detail.json()["version"]["files_in"]]
    assert len(file_ids) == len(file_sizes), detail.text
    return {"id": dataset_id, "version_name": version_name, "file_ids": file_ids}


def create_notebook(http_client: HttpClient, dataset: dict, headers: dict | None = None, **body):
    payload = {
        "dataset_id": dataset["id"],
        "version_name": dataset["version_name"],
        "kernel": "python3",
    }
    payload.update(body)
    return http_client.post("/notebooks/", json=payload, headers=headers or AuthFixture.valid_headers())


def start_session(http_client: HttpClient, notebook_id: str, headers: dict | None = None):
    return http_client.post(
        f"/notebooks/{notebook_id}/sessions",
        json={"locale": "en"},
        headers=headers or AuthFixture.valid_headers(),
    )


def internal(http_client: HttpClient, method: str, path: str, **kwargs):
    headers = {
        "X-Api-Key": config.api_key,
        "X-Api-Secret": config.api_secret,
        "Content-Type": "application/json",
    }
    return getattr(http_client, method)(path, headers=headers, **kwargs)


def forged_token(session_id: str, notebook_id: str, user_id: str, secret: str = SESSION_TOKEN_SECRET) -> str:
    return jwt.encode(
        {
            "iss": "gatekeeper",
            "aud": "notebook_session",
            "sub": user_id,
            "tenancies": [config.tenancy],
            "notebook_id": notebook_id,
            "session_id": session_id,
            "datasets": [],
            "kernel": "python3",
            "locale": "en",
            "iat": 1717453998,
            "exp": 1926260558,
        },
        secret,
        algorithm="HS256",
    )


def fill_storage(user_id: str, size_bytes: int) -> None:
    subprocess.run(
        [
            "docker", "exec", STORAGE_HELPER, "sh", "-c",
            f"mkdir -p /storage/notebooks/{user_id} && "
            f"head -c {size_bytes} /dev/zero > /storage/notebooks/{user_id}/filler.bin",
        ],
        check=True,
        capture_output=True,
    )


def write_notebook_file(user_id: str, path: str, content: str) -> None:
    subprocess.run(
        [
            "docker", "exec", STORAGE_HELPER, "sh", "-c",
            f"mkdir -p /storage/notebooks/{user_id} && "
            f"printf '%s' '{content}' > /storage/notebooks/{user_id}/{path}",
        ],
        check=True,
        capture_output=True,
    )


def new_user_headers(http_client: HttpClient) -> tuple[str, dict]:
    user_id = admin_user(http_client)
    return user_id, headers_for(user_id, config.tenancy)


def unique_name() -> str:
    return f"nb_{uuid.uuid4().hex[:8]}"
```

The `version` key in the detail response: confirm with `curl -s http://localhost:9094/api/openapi.json | python3 -c "import json,sys; print(json.load(sys.stdin)['components']['schemas']['DatasetVersionGetResponse']['properties'].keys())"` once the stack is up, and adjust `detail.json()["version"]["files_in"]` to the real shape before trusting the fixture.

- [ ] **Step 4: The tests**

`tests/integration/test_notebooks_api.py`:

```python
import uuid
from datetime import timedelta

from tests.integration.config import config
from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.embargo import create_user, grant, headers_for
from tests.integration.fixtures.notebooks import (
    bearer,
    create_notebook,
    fill_storage,
    forged_token,
    internal,
    new_user_headers,
    published_dataset,
    start_session,
    unique_name,
    write_notebook_file,
)
from tests.integration.fixtures.sharing import set_embargo
from tests.integration.utils.assertions import assert_status_code

import pytest


@pytest.fixture(autouse=True)
def release_the_default_users_seat(http_client):
    """Two seats in this env: a session left live by one test starves the next."""
    yield
    headers = AuthFixture.valid_headers()
    listed = http_client.get("/notebooks/", headers=headers)
    if listed.status_code != 200:
        return
    for notebook in listed.json()["content"]:
        session = notebook.get("session")
        if session and session["state"] in ("starting", "running"):
            http_client.delete(f"/notebooks/{notebook['id']}/session", headers=headers)


class TestCreate:
    def test_a_notebook_on_a_published_version_mounts_every_file(
        self, http_client, dataset_fixture
    ):
        dataset = published_dataset(http_client, dataset_fixture, [1000, 2000])

        response = create_notebook(http_client, dataset)

        assert_status_code(response, 201)
        body = response.json()
        assert body["kernel"] == "python3"
        assert body["path"] == body["name"] + ".ipynb"
        assert body["dataset"]["id"] == dataset["id"]
        assert body["dataset"]["version_name"] == dataset["version_name"]
        assert body["dataset"]["source_deleted"] is False
        assert body["file_ids"] is None
        assert body["mounted_files"] == 2
        assert body["mounted_bytes"] == 3000
        assert body["session"] is None

    def test_a_draft_version_is_refused(self, http_client, dataset_fixture):
        dataset = dataset_fixture.create_test_dataset()
        version_name = dataset["current_version"]["name"]

        response = create_notebook(
            http_client, {"id": dataset["id"], "version_name": version_name}
        )

        assert_status_code(response, 409)
        assert response.json()["detail"] == "version_not_published"

    def test_a_selection_over_the_ceiling_is_refused_with_the_numbers(
        self, http_client, dataset_fixture
    ):
        dataset = published_dataset(http_client, dataset_fixture, [3000, 3000])

        whole = create_notebook(http_client, dataset)
        assert_status_code(whole, 413)
        assert whole.json() == {
            "detail": "selection_too_large",
            "max_bytes": 4096,
            "selected_bytes": 6000,
        }

        subset = create_notebook(http_client, dataset, file_ids=[dataset["file_ids"][0]])
        assert_status_code(subset, 201)
        assert subset.json()["file_ids"] == [dataset["file_ids"][0]]
        assert subset.json()["mounted_bytes"] == 3000

    def test_a_file_from_elsewhere_is_a_bad_request(self, http_client, dataset_fixture):
        dataset = published_dataset(http_client, dataset_fixture)

        response = create_notebook(http_client, dataset, file_ids=[str(uuid.uuid4())])

        assert_status_code(response, 400)
        assert response.json()["errors"][0]["code"] == "file_not_in_version"

    def test_a_taken_name_is_a_conflict(self, http_client, dataset_fixture):
        dataset = published_dataset(http_client, dataset_fixture)
        name = unique_name()
        assert_status_code(create_notebook(http_client, dataset, name=name), 201)

        response = create_notebook(http_client, dataset, name=name)

        assert_status_code(response, 409)
        assert response.json()["detail"] == "name_taken"

    def test_someone_without_access_gets_404(self, http_client, dataset_fixture):
        dataset = published_dataset(http_client, dataset_fixture)
        outsider = create_user(http_client, roles=["admin"], tenancies=[])

        response = create_notebook(http_client, dataset, headers=headers_for(outsider, None))

        assert_status_code(response, 404)

    def test_a_bearer_token_cannot_create(self, http_client, dataset_fixture):
        dataset = published_dataset(http_client, dataset_fixture)
        token = forged_token(str(uuid.uuid4()), str(uuid.uuid4()), config.user_id)

        response = create_notebook(http_client, dataset, headers=bearer(token))

        assert_status_code(response, 401)


class TestListGetUpdateDelete:
    def test_round_trip(self, http_client, dataset_fixture, valid_headers):
        dataset = published_dataset(http_client, dataset_fixture, [100, 200])
        created = create_notebook(http_client, dataset).json()
        notebook_id = created["id"]

        listed = http_client.get("/notebooks/", headers=valid_headers)
        assert_status_code(listed, 200)
        assert notebook_id in [n["id"] for n in listed.json()["content"]]

        by_dataset = http_client.get(
            f"/notebooks/?dataset_id={dataset['id']}", headers=valid_headers
        )
        assert [n["id"] for n in by_dataset.json()["content"]] == [notebook_id]

        renamed = http_client.patch(
            f"/notebooks/{notebook_id}", json={"name": unique_name()}, headers=valid_headers
        )
        assert_status_code(renamed, 200)
        assert renamed.json()["path"].endswith(".ipynb")

        narrowed = http_client.patch(
            f"/notebooks/{notebook_id}",
            json={"file_ids": [dataset["file_ids"][1]]},
            headers=valid_headers,
        )
        assert_status_code(narrowed, 200)
        assert narrowed.json()["mounted_bytes"] == 200

        widened = http_client.patch(
            f"/notebooks/{notebook_id}", json={"file_ids": None}, headers=valid_headers
        )
        assert widened.json()["mounted_bytes"] == 300

        deleted = http_client.delete(f"/notebooks/{notebook_id}", headers=valid_headers)
        assert_status_code(deleted, 204)
        assert_status_code(http_client.get(f"/notebooks/{notebook_id}", headers=valid_headers), 404)
        listed = http_client.get("/notebooks/", headers=valid_headers)
        assert notebook_id not in [n["id"] for n in listed.json()["content"]]

    def test_content_before_the_first_session_is_not_written(
        self, http_client, dataset_fixture, valid_headers
    ):
        dataset = published_dataset(http_client, dataset_fixture)
        notebook_id = create_notebook(http_client, dataset).json()["id"]

        response = http_client.get(f"/notebooks/{notebook_id}/content", headers=valid_headers)

        assert_status_code(response, 404)
        assert response.json()["detail"] == "content_not_written"

    def test_content_is_served_and_downloadable_once_on_disk(
        self, http_client, dataset_fixture, valid_headers
    ):
        dataset = published_dataset(http_client, dataset_fixture)
        created = create_notebook(http_client, dataset).json()
        write_notebook_file(config.user_id, created["path"], '{"cells": []}')

        plain = http_client.get(f"/notebooks/{created['id']}/content", headers=valid_headers)
        assert_status_code(plain, 200)
        assert plain.json() == {"cells": []}

        download = http_client.get(
            f"/notebooks/{created['id']}/content?download=1", headers=valid_headers
        )
        assert download.headers["Content-Disposition"] == f'attachment; filename="{created["path"]}"'

    def test_someone_elses_notebook_is_not_found(self, http_client, dataset_fixture):
        dataset = published_dataset(http_client, dataset_fixture)
        notebook_id = create_notebook(http_client, dataset).json()["id"]
        _, other = new_user_headers(http_client)

        assert_status_code(http_client.get(f"/notebooks/{notebook_id}", headers=other), 404)


class TestSessions:
    def test_the_token_opens_exactly_the_read_routes(
        self, http_client, dataset_fixture, valid_headers
    ):
        dataset = published_dataset(http_client, dataset_fixture, [500])
        notebook_id = create_notebook(http_client, dataset).json()["id"]

        started = start_session(http_client, notebook_id)
        assert_status_code(started, 201)
        body = started.json()
        assert body["session"]["state"] == "starting"
        assert body["login_url"] == "/hub/login"
        assert body["lab_path"].startswith(f"/user/{config.user_id}/lab/tree/")
        token = body["token"]

        assert_status_code(http_client.get(f"/datasets/{dataset['id']}", headers=bearer(token)), 200)
        version = http_client.get(
            f"/datasets/{dataset['id']}/versions/{dataset['version_name']}", headers=bearer(token)
        )
        assert_status_code(version, 200)
        file_url = http_client.get(
            f"/datasets/{dataset['id']}/versions/{dataset['version_name']}/files/{dataset['file_ids'][0]}",
            headers=bearer(token),
        )
        assert_status_code(file_url, 200)

        manifest = http_client.get(f"/notebooks/{notebook_id}/manifest", headers=bearer(token))
        assert_status_code(manifest, 200)
        payload = manifest.json()
        assert payload["notebook_exists"] is False
        assert payload["outputs_path"] == "/outputs"
        mounted = payload["datasets"][0]
        assert mounted["mount_path"] == f"/data/{dataset['id']}/{dataset['version_name']}"
        assert mounted["file_count"] == 1
        assert mounted["files"][0]["url"].startswith("http")

        progress = http_client.post(
            f"/notebooks/{notebook_id}/session/progress",
            json={"line": "Mounting 1 file"},
            headers=bearer(token),
        )
        assert_status_code(progress, 204)
        status = http_client.get(f"/notebooks/{notebook_id}/session", headers=valid_headers)
        assert status.json()["progress"] == ["Mounting 1 file"]

        for method, path in (
            ("get", "/notebooks/"),
            ("get", f"/notebooks/{notebook_id}"),
            ("post", "/datasets/"),
            ("get", "/datasets/"),
            ("get", f"/notebooks/{uuid.uuid4()}/manifest"),
        ):
            refused = getattr(http_client, method)(path, headers=bearer(token), json={})
            assert refused.status_code in (401, 404), (method, path, refused.text)

    def test_a_second_start_on_the_same_notebook_returns_the_live_session(
        self, http_client, dataset_fixture
    ):
        dataset = published_dataset(http_client, dataset_fixture)
        notebook_id = create_notebook(http_client, dataset).json()["id"]
        first = start_session(http_client, notebook_id).json()

        second = start_session(http_client, notebook_id)

        assert_status_code(second, 200)
        assert second.json()["session"]["id"] == first["session"]["id"]
        assert second.json()["token"]

    def test_a_live_session_elsewhere_is_a_conflict(self, http_client, dataset_fixture):
        dataset = published_dataset(http_client, dataset_fixture)
        first_id = create_notebook(http_client, dataset).json()["id"]
        second_id = create_notebook(http_client, dataset).json()["id"]
        assert_status_code(start_session(http_client, first_id), 201)

        response = start_session(http_client, second_id)

        assert_status_code(response, 409)
        assert response.json()["detail"] == "session_elsewhere"

    def test_the_hub_reports_started_then_stopped_and_the_token_dies(
        self, http_client, dataset_fixture, valid_headers
    ):
        dataset = published_dataset(http_client, dataset_fixture)
        notebook_id = create_notebook(http_client, dataset).json()["id"]
        started = start_session(http_client, notebook_id).json()
        session_id, token = started["session"]["id"], started["token"]

        assert_status_code(internal(http_client, "post", f"/internal/notebook-sessions/{session_id}/started"), 204)
        status = http_client.get(f"/notebooks/{notebook_id}/session", headers=valid_headers).json()
        assert status["state"] == "running"
        assert status["started_at"] is not None

        assert_status_code(internal(http_client, "post", f"/internal/notebook-sessions/{session_id}/stopped", json={}), 204)
        status = http_client.get(f"/notebooks/{notebook_id}/session", headers=valid_headers).json()
        assert status["state"] == "stopped"
        assert status["stop_reason"] == "idle"

        assert_status_code(http_client.get(f"/datasets/{dataset['id']}", headers=bearer(token)), 401)

        assert_status_code(internal(http_client, "post", f"/internal/notebook-sessions/{session_id}/stopped", json={"reason": "user"}), 204)
        again = http_client.get(f"/notebooks/{notebook_id}/session", headers=valid_headers).json()
        assert again["stop_reason"] == "idle"

        resumed = start_session(http_client, notebook_id)
        assert_status_code(resumed, 201)
        assert resumed.json()["session"]["id"] != session_id

    def test_a_spawn_error_is_failed(self, http_client, dataset_fixture, valid_headers):
        dataset = published_dataset(http_client, dataset_fixture)
        notebook_id = create_notebook(http_client, dataset).json()["id"]
        session_id = start_session(http_client, notebook_id).json()["session"]["id"]

        internal(http_client, "post", f"/internal/notebook-sessions/{session_id}/stopped", json={"reason": "spawn_error"})

        status = http_client.get(f"/notebooks/{notebook_id}/session", headers=valid_headers).json()
        assert status["state"] == "failed"
        assert status["stop_reason"] == "spawn_error"

    def test_stopping_asks_the_hub_and_records_the_user(
        self, http_client, dataset_fixture, valid_headers
    ):
        dataset = published_dataset(http_client, dataset_fixture)
        notebook_id = create_notebook(http_client, dataset).json()["id"]
        start_session(http_client, notebook_id)

        stopped = http_client.delete(f"/notebooks/{notebook_id}/session", headers=valid_headers)

        assert_status_code(stopped, 204)
        status = http_client.get(f"/notebooks/{notebook_id}/session", headers=valid_headers).json()
        assert status["state"] == "stopped"
        assert status["stop_reason"] == "user"

    def test_deleting_a_notebook_stops_its_session(self, http_client, dataset_fixture, valid_headers):
        dataset = published_dataset(http_client, dataset_fixture)
        notebook_id = create_notebook(http_client, dataset).json()["id"]
        token = start_session(http_client, notebook_id).json()["token"]

        assert_status_code(http_client.delete(f"/notebooks/{notebook_id}", headers=valid_headers), 204)

        assert_status_code(http_client.get(f"/datasets/{dataset['id']}", headers=bearer(token)), 401)

    def test_a_forged_token_for_a_session_that_never_started_is_refused(
        self, http_client, dataset_fixture
    ):
        dataset = published_dataset(http_client, dataset_fixture)
        notebook_id = create_notebook(http_client, dataset).json()["id"]
        token = forged_token(str(uuid.uuid4()), notebook_id, config.user_id)

        assert_status_code(http_client.get(f"/notebooks/{notebook_id}/manifest", headers=bearer(token)), 401)

    def test_a_token_signed_with_another_secret_is_refused(self, http_client, dataset_fixture):
        dataset = published_dataset(http_client, dataset_fixture)
        notebook_id = create_notebook(http_client, dataset).json()["id"]
        session_id = start_session(http_client, notebook_id).json()["session"]["id"]
        token = forged_token(session_id, notebook_id, config.user_id, secret="wrong")

        assert_status_code(http_client.get(f"/notebooks/{notebook_id}/manifest", headers=bearer(token)), 401)


class TestSeatsAndQuota:
    def test_the_third_seat_is_refused_and_capacity_says_so(self, http_client, dataset_fixture):
        holders = [new_user_headers(http_client) for _ in range(3)]
        for user_id, headers in holders[:2]:
            dataset = published_dataset(http_client, dataset_fixture, headers=headers)
            notebook_id = create_notebook(http_client, dataset, headers=headers).json()["id"]
            assert_status_code(start_session(http_client, notebook_id, headers=headers), 201)

        third_id, third = holders[2]
        dataset = published_dataset(http_client, dataset_fixture, headers=third)
        notebook_id = create_notebook(http_client, dataset, headers=third).json()["id"]
        refused = start_session(http_client, notebook_id, headers=third)
        assert_status_code(refused, 429)
        assert refused.json() == {"detail": "no_seats", "seats_total": 2}

        capacity = http_client.get("/notebooks/-/capacity", headers=third)
        assert_status_code(capacity, 200)
        assert capacity.json()["seats_taken"] == 2
        assert capacity.json()["seats_total"] == 2
        assert capacity.json()["data_max_bytes"] == 4096

        for user_id, headers in holders[:2]:
            for notebook in http_client.get("/notebooks/", headers=headers).json()["content"]:
                http_client.delete(f"/notebooks/{notebook['id']}/session", headers=headers)

    def test_over_quota_is_refused_with_the_numbers(self, http_client, dataset_fixture):
        user_id, headers = new_user_headers(http_client)
        fill_storage(user_id, 3_000_000)
        dataset = published_dataset(http_client, dataset_fixture, headers=headers)
        notebook_id = create_notebook(http_client, dataset, headers=headers).json()["id"]

        response = start_session(http_client, notebook_id, headers=headers)

        assert_status_code(response, 413)
        assert response.json() == {
            "detail": "storage_full",
            "quota_bytes": 2097152,
            "used_bytes": 3_000_000,
        }
        capacity = http_client.get("/notebooks/-/capacity", headers=headers).json()
        assert capacity["storage_used_bytes"] == 3_000_000


class TestEmbargo:
    def test_the_dataset_rule_decides_who_can_open_a_notebook(self, http_client, dataset_fixture):
        dataset = published_dataset(http_client, dataset_fixture)
        set_embargo(http_client, dataset["id"], timedelta(days=30))
        outsider = create_user(http_client, roles=["admin"], tenancies=[config.tenancy])
        outsider_headers = headers_for(outsider, config.tenancy)

        assert_status_code(create_notebook(http_client, dataset, headers=outsider_headers), 404)
        assert_status_code(create_notebook(http_client, dataset), 201)

        grant(http_client, dataset["id"], outsider, "read")
        assert_status_code(create_notebook(http_client, dataset, headers=outsider_headers), 201)

    def test_an_embargo_that_starts_after_creation_stops_the_manifest(
        self, http_client, dataset_fixture
    ):
        dataset = published_dataset(http_client, dataset_fixture)
        member = create_user(http_client, roles=["admin"], tenancies=[config.tenancy])
        member_headers = headers_for(member, config.tenancy)
        notebook_id = create_notebook(http_client, dataset, headers=member_headers).json()["id"]
        token = start_session(http_client, notebook_id, headers=member_headers).json()["token"]
        assert_status_code(http_client.get(f"/notebooks/{notebook_id}/manifest", headers=bearer(token)), 200)

        set_embargo(http_client, dataset["id"], timedelta(days=30))

        assert_status_code(http_client.get(f"/notebooks/{notebook_id}/manifest", headers=bearer(token)), 404)
        http_client.delete(f"/notebooks/{notebook_id}/session", headers=member_headers)


class TestInternal:
    def test_purgeable_lists_a_stopped_session_until_it_is_reported(
        self, http_client, dataset_fixture, valid_headers
    ):
        dataset = published_dataset(http_client, dataset_fixture)
        notebook_id = create_notebook(http_client, dataset).json()["id"]
        session_id = start_session(http_client, notebook_id).json()["session"]["id"]
        http_client.delete(f"/notebooks/{notebook_id}/session", headers=valid_headers)

        listed = internal(http_client, "get", "/internal/notebook-sessions/purgeable")
        assert_status_code(listed, 200)
        assert session_id in [s["id"] for s in listed.json()["sessions"]]
        assert notebook_id not in [o["notebook_id"] for o in listed.json()["outputs"]]

        assert_status_code(internal(http_client, "post", f"/internal/notebook-sessions/{session_id}/purged"), 204)
        listed = internal(http_client, "get", "/internal/notebook-sessions/purgeable")
        assert session_id not in [s["id"] for s in listed.json()["sessions"]]

    def test_a_deleted_notebook_is_listed_for_file_removal(
        self, http_client, dataset_fixture, valid_headers
    ):
        dataset = published_dataset(http_client, dataset_fixture)
        created = create_notebook(http_client, dataset).json()
        http_client.delete(f"/notebooks/{created['id']}", headers=valid_headers)

        listed = internal(http_client, "get", "/internal/notebook-sessions/purgeable").json()
        entry = next(n for n in listed["notebooks"] if n["notebook_id"] == created["id"])
        assert entry == {"notebook_id": created["id"], "user_id": config.user_id, "path": created["path"]}

        assert_status_code(internal(http_client, "post", f"/internal/notebooks/{created['id']}/purged"), 204)
        listed = internal(http_client, "get", "/internal/notebook-sessions/purgeable").json()
        assert created["id"] not in [n["notebook_id"] for n in listed["notebooks"]]

    def test_internal_routes_need_a_client_key(self, http_client):
        response = http_client.get(
            "/internal/notebook-sessions/purgeable", headers=AuthFixture.invalid_headers()
        )
        assert_status_code(response, 401)

    def test_unknown_session_is_404(self, http_client):
        assert_status_code(
            internal(http_client, "post", f"/internal/notebook-sessions/{uuid.uuid4()}/started"), 404
        )
```

`grant` from `tests/integration/fixtures/embargo.py` has signature `grant(http_client, dataset_id, user_id, level)`; `set_embargo` from `sharing.py` needs the dataset owned by the default test user, which `published_dataset` with default headers gives. `create_user(http_client, roles, tenancies)` is the `embargo.py` one (returns the id).

- [ ] **Step 5: Make the suite fail first, then run it**

Before writing the tests' implementation side existed (it does, from Tasks 1–8), prove the suite tests something: temporarily change `"no_seats"` to `"no_seat"` in `app/service/notebook_session.py`, run only `TestSeatsAndQuota`, watch it fail, revert.

Full cycle:

```bash
mkdir -p ../../../data-storage_test_integration/datamap
docker ps --format "{{.Names}}\t{{.Ports}}" | grep 5433    # must be empty
make ENV_FILE_PATH=integration-test.env integration-test-full
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/
```

The `make` target swallows failures, so read the pytest summary line yourself, and run the file alone for a trustworthy exit code:

```bash
make ENV_FILE_PATH=integration-test.env integration-test-up
docker exec datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db -f /tmp/seed_clients.sql
sleep 6
pytest tests/integration/test_notebooks_api.py -q
echo "exit: $?"
docker exec datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db \
  -c "SELECT count(*) FROM casbin_rule WHERE v0 = 'notebook_session'"
```

Expected: every test passes; the count is `5` (the seed did not duplicate the migration's rows). Then the whole suite: `pytest tests/integration -q` with no new failures outside this file.

If `published_dataset` fails on the detail shape, fix the fixture against the OpenAPI document as described in Step 3, not the assertion.

- [ ] **Step 6: Lint and commit**

```bash
ruff check && ruff format
git add docker-compose-integration-test.yaml tests/integration/wiremock/mappings/hub_stop_server.json \
  tests/integration/fixtures/notebooks.py tests/integration/test_notebooks_api.py
git commit -m "test(notebooks): integration coverage for sessions, bearer scope, seats, quota and embargo

The gatekeeper mounts the storage volume read-only; an alpine helper on the
same volume is what the quota test writes with. Seats are two and the copy
ceiling is 4 KB in the integration env so the limits are reachable with
fixtures a few bytes long."
```

---

### Task 10: RFC amendments and the validation loop

**Files:**
- Modify: `docs/rfcs/007-notebooks.md`

- [ ] **Step 1: Record where execution diverged**

In `docs/rfcs/007-notebooks.md`:

1. Under *Data model*, replace the sentence about the one-row `notebook_capacity` table with: "The seat limit is a count over `idx_notebook_sessions_live`, taken inside the same transaction that inserts the `starting` row, under `pg_advisory_xact_lock`, so two requests cannot both see the last seat free. The hub's own `active_server_limit` is set to the same number as a second fence, not as the first."
2. Under *Routes*, change `POST /notebooks/` from "writes the first cell" to "records the notebook; the container entrypoint writes the first cell on the first start when the file does not exist yet, because the gatekeeper never writes to the volume". Change `DELETE /notebooks/{id}` to "soft delete; the archivist removes the file". Add `POST /notebooks/{id}/session/progress` (bearer) and note that `GET /notebooks/{id}/session` carries `progress` reported by the entrypoint, not proxied from the hub.
3. Under *Session lifecycle*, add after the transitions table: "The hub cannot name the reason a server stopped. The gatekeeper derives it: the reason it recorded when it asked for the stop, else `max_age` past twelve hours, else `idle`. The hub sends `spawn_error` explicitly."
4. Under *Session token*, replace "The webapp sends the browser to `/hub/login?token=<jwt>` once" with "The webapp posts the token to `/hub/login` as a form field, so it never appears in a URL or an access log".
5. Add `notebook_datasets` to the data model (one row today, list by design) in place of `dataset_id`/`dataset_version` columns on `notebooks`, and add `mounted_files`, `mounted_bytes`, `file_ids` there; add `stop_requested`, `progress`, `data_purged_at` to `notebook_sessions`; add `deleted_at`, `file_purged_at`, `outputs_purged_at` to `notebooks`.
6. Add the Casbin `notebooks_user` role to *Rollout*: gate 2 is a `g` row per user for `notebooks_user`.
7. Under *Session token*, add "`exp` is `iat` plus the 12 h limit plus 10 minutes" if missing, and the `iss`/`aud` claims.

Update the `Updated` date in the header table.

- [ ] **Step 2: The full validation loop**

```bash
../../../.venv/bin/python -m pytest -q
make ENV_FILE_PATH=integration-test.env integration-test-full
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/
ruff check
ruff check --fix
ruff format
```

Expected: unit suite green; integration summary line shows no failures and the API answered 200; ruff clean.

- [ ] **Step 3: Commit and open the pull request**

```bash
git add docs/rfcs/007-notebooks.md
git commit -m "docs(rfc-007): record where increment A diverged from the plan

Advisory lock instead of a capacity table, first cell written by the
entrypoint, progress reported over HTTP, stop reason derived, hub login by
form POST, and the columns the implementation needed."
git push -u origin docs/rfc-007-notebooks
gh pr create --title "feat(notebooks): gatekeeper side of RFC 007 increment A" --body "$(cat <<'EOF'
## Summary
- notebook, dataset-link and append-only session tables; Casbin rows for the session subject and the notebooks_user role
- session token as a bearer in the interceptors: token plus live row, authorized as `notebook_session`
- notebook routes, session routes, manifest and progress for the entrypoint, internal routes for the hub and the archivist
- seats under an advisory lock, storage quota over a read-only mount, hub stop through its REST API
- metrics per RFC 005; RFC 007 amended where execution diverged

Spec: docs/rfcs/007-notebooks.md. Contracts: docs/superpowers/plans/2026-10-04-notebooks-00-contracts.md.

## Test plan
- [ ] unit suite green
- [ ] integration suite green, API answered 200 before the run
- [ ] `SELECT count(*) FROM casbin_rule WHERE v0 = 'notebook_session'` is 5 after seed on top of migration

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Rewrite any subagent commit trailers to the session's own before pushing (see memory: subagent commit trailers).
