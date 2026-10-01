# Gatekeeper Email Delivery and Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the gatekeeper one way to send email, for the whole platform: every message is rendered from a template, recorded before it is sent, sent over SMTP at most once, and kept with its history afterwards.

**Architecture:** A service enqueues a message as a row in `email_messages` (with a `queued` row in `email_events`). A dispatch pass, triggered over `POST /api/v1/internal/notifications/dispatch` by the Archivist, claims due rows with `SELECT … FOR UPDATE SKIP LOCKED`, moves them to `sending` in their own commit, and hands each to a thin `smtplib` wrapper that tells a definite refusal apart from an uncertain outcome. Only definite refusals are retried; anything uncertain becomes `failed`, so no message is ever delivered twice. Secrets in a message (an invitation link, say) stay in the row only until it leaves, then are masked.

**Tech Stack:** FastAPI 0.111, SQLAlchemy 1.4.23, Alembic, dependency-injector 4.41, the existing `EmailTemplateRenderer` (Jinja2 3.1.6, already pinned), stdlib `smtplib`/`email`/`html.parser`, prometheus-client 0.20, pytest/unittest, Mailpit (integration only).

**Spec:** `docs/rfcs/003-dataset-embargo.md` §Notifications. **Contracts:** `docs/superpowers/plans/2026-09-30-embargo-00-contracts.md` §Notifications, §Metrics.

## Global Constraints

- Production image is `python:3.10.14-alpine` (`Dockerfile`): no syntax newer than 3.10 (no `except*`, no `typing.Self`, no PEP 695).
- Migration revision ids are fixed across plans: plan 01 = `d4e5f6a7b8c9` (revises current head `c3h4i5j6k7l8`), plan 02 = `e5f6a7b8c9d0` (revises `d4e5f6a7b8c9`), plan 03 = `f6a7b8c9d0e1` (revises `e5f6a7b8c9d0`).
- Status values: `pending | sending | sent | failed | skipped`. Event values: `queued | attempt_failed | sent | failed | skipped`.
- A message is never sent twice. Retry only on a definite refusal (could not connect, session refused, recipient/sender/data refused by the server). An outcome that is not known (connection dropped or timed out after the content was written; a row left in `sending`) is `failed`, never retried.
- Retries: at most 5 attempts in total; delays after attempts 1–4 are 1 min, 5 min, 15 min, 1 h.
- A recipient ending in `@fake.mail.com` is recorded as `skipped` with detail `placeholder address`, never sent.
- Metrics: `datamap_emails_total{template, outcome}` with outcome in `sent | retried | failed | skipped`; `datamap_email_pending` gauge, no labels.
- Logs carry `email_id`, `template`, `outcome` as `fields()` extras. Never the recipient, the subject or the body.
- Comments: only where a reader would otherwise undo something on purpose; one line (CLAUDE.md §Code Style). Empty `__init__.py` files have no comment.
- `EMAIL_ENABLED` defaults to `false`; with it off, messages are recorded and stay `pending`.
- Every config field added here has a default, so existing environments keep starting.
- Every message is rendered by the existing `EmailTemplateRenderer` (`app/service/email_template.py`) from `app/resources/email_templates/`, with `site_url = PUBLIC_BASE_URL`. This plan adds no layout and changes no existing `.html` template. The `template` column and the `template` metric label hold `EmailTemplate` values.

## File Structure

| Path | Responsibility |
|---|---|
| `app/config.py` (modify) | `EMAIL_*`, `SMTP_*`, `PUBLIC_BASE_URL`, `BUILD_COMMIT` settings |
| `app/config_email_test.py` (create) | Defaults of the new settings |
| `Dockerfile`, `docker-compose-infrastructure.yaml`, `docker-compose-integration-test.yaml`, `Makefile` (modify) | Pass the build commit into the image as `BUILD_COMMIT` |
| `local.env.template` (modify) | Document the new settings |
| `app/model/email.py` (create) | Domain enums and dataclasses: `EmailStatus`, `EmailEventType`, `EmailRecord`, `EmailEventRecord`, `EmailQuery`, `DispatchResult` |
| `app/model/db/email.py` (create) | SQLAlchemy models `EmailMessage`, `EmailEvent` |
| `migrations/versions/2026_09_30_1200-d4e5f6a7b8c9_add_email_messages.py` (create) | Schema |
| `migrations/env.py` (modify) | Import the email models for autogenerate |
| `app/repository/email.py` (create) | Persistence, claiming with `SKIP LOCKED`, search |
| `app/service/email_text.py` + `_test.py` (create) | HTML → plain text, for templates without a `.txt` |
| `app/service/email_template.py`, `email_template_test.py` (modify, additive) | `RenderedEmail.text`, `.txt` siblings, `site_url` property |
| `app/resources/email_templates/base.txt` (create) | Plain-text layout the `.txt` siblings extend |
| `app/gateway/email/__init__.py`, `smtp.py`, `smtp_test.py` (create) | SMTP wrapper and failure classification |
| `app/service/email_masking.py` + `_test.py` (create) | Masking of secret fields |
| `app/service/email.py` + `email_test.py` (create) | `EmailService.enqueue`, `dispatch_due`, `search`, `fetch`, `send_test_message` |
| `app/metrics.py`, `app/metrics_test.py` (modify) | `datamap_emails_total`, `datamap_email_pending` |
| `app/controller/v1/internal/notification.py`, `resource.py` (create/modify) | `POST /internal/notifications/dispatch` |
| `app/controller/v1/admin/__init__.py`, `email.py`, `resource.py` (create) | `GET /admin/emails`, `GET /admin/emails/{id}`, `POST /admin/emails/test` |
| `app/container.py`, `app/setup.py` (modify) | Wiring and router mounting |
| `docker-compose-integration-test.yaml`, `integration-test.env` (modify) | Mailpit service, SMTP settings pointing at it |
| `tests/integration/utils/mailpit.py` (create) | Mailpit HTTP API helper |
| `tests/integration/test_email_delivery.py` (create) | End-to-end delivery, exactly-once, masking, skipped |
| `infrastructure/grafana/dashboards/Business/platform-usage.json` (modify) | Email panel |

## Task Order and Parallelism

```
Task 1 (config, build commit)
   ├── Task 2 (models + migration)  ──► Task 4 (repository) ─┐
   ├── Task 3 (plain-text part) ─────────────────────────────┤
   └── Task 5 (SMTP gateway)        ─────────────────────────┤
                                                             ▼
                          Task 6 (masking, metrics, EmailService.enqueue)
                                                             ▼
                          Task 7 (EmailService.dispatch_due)
                                                             ▼
                          Task 8 (routes + wiring)
                                                             ▼
                          Task 9 (Mailpit + integration tests + dashboard + validation loop)
```

Tasks 2, 3 and 5 can run in parallel once Task 1 is merged. Everything else is sequential.

---

### Task 1: Settings and the build commit

**Files:**
- Modify: `app/config.py` (after `METRICS_PORT`, before the validator)
- Create: `app/config_email_test.py`
- Modify: `Dockerfile`, `docker-compose-infrastructure.yaml`, `docker-compose-integration-test.yaml`, `Makefile`, `local.env.template`

**Interfaces:**
- Produces: `settings.EMAIL_ENABLED: bool`, `EMAIL_FROM_NAME: str`, `EMAIL_FROM_ADDRESS: str`, `EMAIL_REPLY_TO: Optional[str]`, `SMTP_HOST: str`, `SMTP_PORT: int`, `SMTP_USERNAME: Optional[str]`, `SMTP_PASSWORD: Optional[str]`, `SMTP_STARTTLS: bool`, `SMTP_TIMEOUT_SECONDS: float`, `PUBLIC_BASE_URL: str`, `BUILD_COMMIT: str`. Container reads them as `config.<NAME>`.

- [ ] **Step 1: Write the failing test**

`app/config_email_test.py`:

```python
import os
import unittest
from unittest.mock import patch

from app.config import Config

REQUIRED = {
    "LOG_LEVEL": "INFO",
    "ENVIRONMENT": "test",
    "POSTGRES_HOST": "db",
    "POSTGRES_PORT": "5432",
    "POSTGRES_USER": "user",
    "POSTGRES_PASSWORD": "password",
    "POSTGRES_DB": "db",
    "AUTH_FILE_UPLOAD_TOKEN_SECRET": "secret",
    "AUTH_CLIENT_SECRET_PEPPER": "pepper-of-sixteen-chars",
    "CASBIN_MODEL_FILE": "app/resources/casbin_model.conf",
    "DOI_BASE_URL": "http://doi",
    "DOI_PREFIX": "10.0",
    "DOI_LOGIN": "login",
    "DOI_PASSWORD": "password",
    "MINIO_URL": "minio:9000",
    "MINIO_ACCESS_KEY": "key",
    "MINIO_SECRET_KEY": "secret",
    "MINIO_DATASET_BUCKET": "datamap",
    "MINIO_DEFAULT_REGION_ID": "us-east-1",
    "MINIO_USE_SSL": "False",
}


class TestEmailSettings(unittest.TestCase):
    def build(self, **overrides) -> Config:
        with patch.dict(os.environ, {**REQUIRED, **overrides}, clear=True):
            return Config(_env_file=None)

    def test_an_environment_without_email_settings_still_starts_with_sending_off(self):
        config = self.build()

        self.assertFalse(config.EMAIL_ENABLED)
        self.assertEqual(config.EMAIL_FROM_NAME, "DataMap")
        self.assertEqual(config.SMTP_PORT, 587)
        self.assertTrue(config.SMTP_STARTTLS)
        self.assertIsNone(config.SMTP_USERNAME)
        self.assertEqual(config.PUBLIC_BASE_URL, "https://datamap.pcs.usp.br")
        self.assertEqual(config.BUILD_COMMIT, "unknown")

    def test_the_production_values_are_read_as_written(self):
        config = self.build(
            EMAIL_ENABLED="true",
            EMAIL_FROM_NAME="DataMap",
            EMAIL_FROM_ADDRESS="datamap.pcs@gmail.com",
            SMTP_HOST="smtp.gmail.com",
            SMTP_PORT="587",
            SMTP_STARTTLS="true",
            SMTP_USERNAME="datamap.pcs@gmail.com",
            SMTP_PASSWORD="abcdabcdabcdabcd",
        )

        self.assertTrue(config.EMAIL_ENABLED)
        self.assertEqual(config.EMAIL_FROM_ADDRESS, "datamap.pcs@gmail.com")
        self.assertEqual(config.SMTP_HOST, "smtp.gmail.com")
        self.assertEqual(config.SMTP_PASSWORD, "abcdabcdabcdabcd")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest app/config_email_test.py -v`
Expected: FAIL with `AttributeError: 'Config' object has no attribute 'EMAIL_ENABLED'`

- [ ] **Step 3: Add the settings**

In `app/config.py`, after the `METRICS_PORT` field:

```python
    EMAIL_ENABLED: bool = Field(
        False, description="Send queued email; when false it stays pending"
    )
    EMAIL_FROM_NAME: str = Field("DataMap", description="Sender display name")
    EMAIL_FROM_ADDRESS: str = Field(
        "no-reply@datamap.pcs.usp.br", description="Sender address"
    )
    EMAIL_REPLY_TO: Optional[str] = Field(None, description="Reply-To address")
    SMTP_HOST: str = Field("localhost", description="SMTP server host")
    SMTP_PORT: int = Field(587, description="SMTP server port")
    SMTP_USERNAME: Optional[str] = Field(None, description="SMTP user")
    SMTP_PASSWORD: Optional[str] = Field(None, description="SMTP password")
    SMTP_STARTTLS: bool = Field(True, description="Upgrade the connection with STARTTLS")
    SMTP_TIMEOUT_SECONDS: float = Field(30, description="SMTP socket timeout")
    PUBLIC_BASE_URL: str = Field(
        "https://datamap.pcs.usp.br", description="Origin of links in messages"
    )
    BUILD_COMMIT: str = Field("unknown", description="Commit the image was built from")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest app/config_email_test.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Pass the build commit into the image**

`Dockerfile` — in the final stage, before `CMD`:

```dockerfile
ARG BUILD_COMMIT=unknown
ENV BUILD_COMMIT=$BUILD_COMMIT
```

`docker-compose-infrastructure.yaml` — replace `build: .` of the `gatekeeper` service:

```yaml
    build:
      context: .
      args:
        BUILD_COMMIT: ${BUILD_COMMIT:-unknown}
```

`docker-compose-integration-test.yaml` — the same replacement for `gatekeeper_test_integration`.

`Makefile` — after the `export $(shell sed 's/=.*//' ${ENV_FILE_PATH})` line:

```make
export BUILD_COMMIT ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
```

`local.env.template` — append:

```
# Email (RFC 003). Off by default: messages are recorded and stay pending.
EMAIL_ENABLED=False
EMAIL_FROM_NAME=DataMap
EMAIL_FROM_ADDRESS=no-reply@datamap.pcs.usp.br
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_STARTTLS=False
SMTP_USERNAME=
SMTP_PASSWORD=
PUBLIC_BASE_URL=http://localhost:3000
```

- [ ] **Step 6: Verify the image still builds and reads the commit**

Run:
```bash
docker build --build-arg BUILD_COMMIT=$(git rev-parse --short HEAD) -t gatekeeper-email-check .
docker run --rm gatekeeper-email-check python3 -c "import os; print(os.environ['BUILD_COMMIT'])"
```
Expected: the short commit hash.

- [ ] **Step 7: Commit**

```bash
git add app/config.py app/config_email_test.py Dockerfile docker-compose-infrastructure.yaml docker-compose-integration-test.yaml Makefile local.env.template
git commit -m "feat: email and SMTP settings, off by default"
```

---

### Task 2: Email tables and domain model

**Files:**
- Create: `app/model/email.py`, `app/model/db/email.py`, `app/model/email_test.py`
- Create: `migrations/versions/2026_09_30_1200-d4e5f6a7b8c9_add_email_messages.py`
- Modify: `migrations/env.py:27-33`

**Interfaces:**
- Produces (domain, `app/model/email.py`):

```python
class EmailStatus(str, enum.Enum): PENDING, SENDING, SENT, FAILED, SKIPPED   # values lower-case
class EmailEventType(str, enum.Enum): QUEUED, ATTEMPT_FAILED, SENT, FAILED, SKIPPED
@dataclass EmailRecord(id, template, template_version, recipient, subject, body_text, context: dict,
                       secret_fields: list[str], related_type, related_id, triggered_by, dedup_key,
                       status: EmailStatus, attempts: int, next_attempt_at, smtp_message_id, sent_at, created_at)
@dataclass EmailEventRecord(id: int, event: EmailEventType, detail: str | None, occurred_at: datetime)
@dataclass EmailQuery(recipient=None, related_id=None, template=None, status: EmailStatus | None = None, page=1, page_size=20)
@dataclass DispatchResult(queued=0, sent=0, failed=0, skipped=0, retried=0)
```

- Produces (DB, `app/model/db/email.py`): `EmailMessage` (table `email_messages`), `EmailEvent` (table `email_events`).

Two columns go beyond the RFC's table and are needed by the mechanism: `secret_fields` (which context keys to mask once the message leaves) and `claimed_at` (when a row entered `sending`, to find rows left there by a crash).

- [ ] **Step 1: Write the failing test**

`app/model/email_test.py`:

```python
import unittest

from app.model.db.email import EmailEvent, EmailMessage
from app.model.email import DispatchResult, EmailEventType, EmailStatus


class TestEmailModel(unittest.TestCase):
    def test_status_and_event_values_are_the_ones_stored(self):
        self.assertEqual(
            [status.value for status in EmailStatus],
            ["pending", "sending", "sent", "failed", "skipped"],
        )
        self.assertEqual(
            [event.value for event in EmailEventType],
            ["queued", "attempt_failed", "sent", "failed", "skipped"],
        )

    def test_the_tables_carry_what_the_audit_needs(self):
        columns = set(EmailMessage.__table__.columns.keys())

        self.assertTrue(
            {
                "template", "template_version", "recipient", "subject", "body_text",
                "context", "secret_fields", "related_type", "related_id",
                "triggered_by", "dedup_key", "status", "attempts", "next_attempt_at",
                "claimed_at", "smtp_message_id", "sent_at", "created_at",
            }.issubset(columns)
        )  # fmt: skip
        self.assertTrue(EmailMessage.__table__.columns["dedup_key"].unique)
        self.assertEqual(
            set(EmailEvent.__table__.columns.keys()),
            {"id", "message_id", "event", "detail", "occurred_at"},
        )

    def test_a_dispatch_result_starts_at_zero(self):
        self.assertEqual(DispatchResult(), DispatchResult(0, 0, 0, 0, 0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest app/model/email_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.model.db.email'`

- [ ] **Step 3: Write the domain model**

`app/model/email.py`:

```python
from dataclasses import dataclass
from datetime import datetime
import enum
from uuid import UUID


class EmailStatus(str, enum.Enum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class EmailEventType(str, enum.Enum):
    QUEUED = "queued"
    ATTEMPT_FAILED = "attempt_failed"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class EmailRecord:
    id: UUID
    template: str
    template_version: str
    recipient: str
    subject: str
    body_text: str
    context: dict
    secret_fields: list[str]
    related_type: str | None
    related_id: UUID | None
    triggered_by: UUID | None
    dedup_key: str | None
    status: EmailStatus
    attempts: int
    next_attempt_at: datetime
    smtp_message_id: str | None
    sent_at: datetime | None
    created_at: datetime


@dataclass
class EmailEventRecord:
    id: int
    event: EmailEventType
    detail: str | None
    occurred_at: datetime


@dataclass
class EmailQuery:
    recipient: str | None = None
    related_id: UUID | None = None
    template: str | None = None
    status: EmailStatus | None = None
    page: int = 1
    page_size: int = 20


@dataclass
class DispatchResult:
    queued: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    retried: int = 0
```

- [ ] **Step 4: Write the DB models**

`app/model/db/email.py`:

```python
import sqlalchemy
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


class EmailMessage(Base):
    __tablename__ = "email_messages"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    template = Column(String(64), nullable=False)
    template_version = Column(String(64), nullable=False)
    recipient = Column(String(256), nullable=False)
    subject = Column(Text, nullable=False)
    body_text = Column(Text, nullable=False)
    context = Column(JSONB, nullable=False)
    secret_fields = Column(JSONB, nullable=False, server_default=sqlalchemy.text("'[]'::jsonb"))
    related_type = Column(String(32), nullable=True)
    related_id = Column(UUID(as_uuid=True), nullable=True)
    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    dedup_key = Column(String(256), nullable=True, unique=True)
    status = Column(String(16), nullable=False, server_default="pending")
    attempts = Column(Integer, nullable=False, server_default="0")
    next_attempt_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    smtp_message_id = Column(String(256), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "idx_email_messages_due",
            "next_attempt_at",
            postgresql_where=sqlalchemy.text("status = 'pending'"),
        ),
        Index("idx_email_messages_related", "related_type", "related_id", "created_at"),
    )


class EmailEvent(Base):
    __tablename__ = "email_events"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    message_id = Column(
        UUID(as_uuid=True), ForeignKey("email_messages.id"), nullable=False
    )
    event = Column(String(16), nullable=False)
    detail = Column(Text, nullable=True)
    occurred_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_email_events_message", "message_id", "occurred_at"),)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest app/model/email_test.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Write the migration**

`migrations/versions/2026_09_30_1200-d4e5f6a7b8c9_add_email_messages.py`:

```python
"""Add email_messages and email_events

Revision ID: d4e5f6a7b8c9
Revises: c3h4i5j6k7l8
Create Date: 2026-09-30 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3h4i5j6k7l8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("template", sa.String(length=64), nullable=False),
        sa.Column("template_version", sa.String(length=64), nullable=False),
        sa.Column("recipient", sa.String(length=256), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False),
        sa.Column(
            "secret_fields",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("related_type", sa.String(length=32), nullable=True),
        sa.Column("related_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dedup_key", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("smtp_message_id", sa.String(length=256), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["triggered_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_key"),
    )
    op.create_index(
        "idx_email_messages_due",
        "email_messages",
        ["next_attempt_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "idx_email_messages_related",
        "email_messages",
        ["related_type", "related_id", "created_at"],
    )
    op.execute(
        "CREATE INDEX idx_email_messages_recipient "
        "ON email_messages (lower(recipient), created_at DESC)"
    )

    op.create_table(
        "email_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["message_id"], ["email_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_email_events_message", "email_events", ["message_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_email_events_message", table_name="email_events")
    op.drop_table("email_events")
    op.execute("DROP INDEX IF EXISTS idx_email_messages_recipient")
    op.drop_index("idx_email_messages_related", table_name="email_messages")
    op.drop_index("idx_email_messages_due", table_name="email_messages")
    op.drop_table("email_messages")
```

In `migrations/env.py`, after `from app.model.db import doi  # noqa: E402, F401`:

```python
from app.model.db import email  # noqa: E402, F401
```

- [ ] **Step 7: Run the migration up and down against the local database**

Run:
```bash
make ENV_FILE_PATH=local.env docker-run-db
make ENV_FILE_PATH=local.env db-upgrade
make ENV_FILE_PATH=local.env db-downgrade
make ENV_FILE_PATH=local.env db-upgrade
```
Expected: each command ends without a traceback; `db-upgrade` logs `Running upgrade c3h4i5j6k7l8 -> d4e5f6a7b8c9`.

Then check autogenerate proposes nothing for these tables:

Run: `make ENV_FILE_PATH=local.env MESSAGE="check email drift" db-create-migration`
Expected: the generated file's `upgrade()` contains only `pass` (index `idx_email_messages_recipient` is expression-based and skipped by reflection). Delete that generated file.

- [ ] **Step 8: Commit**

```bash
git add app/model/email.py app/model/email_test.py app/model/db/email.py migrations/env.py migrations/versions/2026_09_30_1200-d4e5f6a7b8c9_add_email_messages.py
git commit -m "feat: tables for every email the platform sends"
```

---

### Task 3: A plain-text part for the existing email templates

The templates and their renderer already exist (`app/resources/email_templates/`, `app/service/email_template.py`, merged in #121). This plan sends every message through them and adds nothing to their HTML. What they lack is the plain-text part RFC 003 requires, which is also what `email_messages.body_text` records. This task adds it, additively: existing callers and tests keep working.

It builds on the `fix/email-footer-links` PR, which merges first: that PR removes the *Notification preferences* and *Unsubscribe* links from `base.html`, points the footer's *Datasets* link at `{site_url}/app/datasets`, and stops the renderer from supplying `preferences_url` and `unsubscribe_url`. Nothing in this plan uses or tests those two variables, and no template added by this plan or plan 03 mentions preferences, unsubscribing, snoozing or any other feature DataMap does not have.

**Files:**
- Create: `app/service/email_text.py`, `app/service/email_text_test.py`
- Modify: `app/service/email_template.py`, `app/service/email_template_test.py` (append only)
- Create: `app/resources/email_templates/base.txt`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:

```python
# app/service/email_text.py
def html_to_text(html: str) -> str: ...

# app/service/email_template.py (additions)
@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str = ""              # new; always filled by render()

class EmailTemplateRenderer:
    @property
    def site_url(self) -> str: ...      # new; the origin without a trailing slash
    def render(self, template: EmailTemplate, context: dict[str, Any]) -> RenderedEmail: ...
```

`render` also unescapes the subject: it comes from the `title` block of an `.html` template, which autoescaping turns into `Ozone &amp; CO2` — fine in HTML, wrong in a `Subject:` header. And it looks for `<template>.txt` beside `<template>.html`. When it exists it is rendered with the same variables; `select_autoescape(["html"])` already leaves `.txt` unescaped, and `StrictUndefined` still applies. When it does not, the text is derived from the rendered HTML by `html_to_text`. The four templates from #121 have no `.txt`, so they get derived text; templates added later (plan 03) ship a `.txt` that extends `base.txt`.

- [ ] **Step 1: Write the failing converter tests**

`app/service/email_text_test.py`:

```python
import unittest

from app.service.email_text import html_to_text


class TestHtmlToText(unittest.TestCase):
    def test_a_link_keeps_its_address(self):
        text = html_to_text('<p>Open <a href="https://d.example/x">the dataset</a> now.</p>')

        self.assertEqual(text, "Open the dataset (https://d.example/x) now.")

    def test_a_link_whose_label_is_its_address_is_written_once(self):
        text = html_to_text('<a href="https://d.example/x">https://d.example/x</a>')

        self.assertEqual(text, "https://d.example/x")

    def test_rows_and_breaks_become_lines_and_whitespace_collapses(self):
        html = "<table><tr><td>  First   line </td></tr><tr><td>Second<br>Third</td></tr></table>"

        self.assertEqual(html_to_text(html), "First line\nSecond\nThird")

    def test_head_style_and_hidden_preheader_are_left_out(self):
        html = (
            "<html><head><title>Subject</title><meta charset=\"utf-8\"><style>a{color:red}</style></head>"
            '<body><span style="display:none!important;">preheader &#8199;&#847;</span>'
            "<p>Body</p></body></html>"
        )

        self.assertEqual(html_to_text(html), "Body")

    def test_entities_are_decoded(self):
        self.assertEqual(html_to_text("<p>A&nbsp;&amp;&nbsp;B &middot; C</p>"), "A & B · C")

    def test_blank_lines_never_pile_up(self):
        html = "<p>One</p><p></p><p></p><p>Two</p>"

        self.assertEqual(html_to_text(html), "One\n\nTwo")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest app/service/email_text_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.service.email_text'`

- [ ] **Step 3: Write the converter**

`app/service/email_text.py`:

```python
import re
from html.parser import HTMLParser

_SKIPPED = {"head", "title", "style", "script"}
_BLOCKS = {"div", "tr", "table", "br", "li", "ul", "ol"}
_PARAGRAPHS = {"p", "h1", "h2", "h3", "h4", "h5", "h6"}


class _Converter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skipped: list[str] = []
        self._hidden_tag: str | None = None
        self._hidden_depth = 0
        self._link_href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self._skipped:
            if tag in _SKIPPED:
                self._skipped.append(tag)
            return
        if tag in _SKIPPED:
            self._skipped.append(tag)
            return
        if self._hidden_tag is not None:
            if tag == self._hidden_tag:
                self._hidden_depth += 1
            return
        attributes = dict(attrs)
        if "display:none" in (attributes.get("style") or "").replace(" ", "").lower():
            self._hidden_tag, self._hidden_depth = tag, 1
            return
        if tag == "a":
            self._link_href = attributes.get("href")
            self._link_text = []
        elif tag in _PARAGRAPHS:
            self._parts.append("\n\n")
        elif tag in _BLOCKS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if self._skipped:
            if tag == self._skipped[-1]:
                self._skipped.pop()
            return
        if self._hidden_tag is not None:
            if tag == self._hidden_tag:
                self._hidden_depth -= 1
                if self._hidden_depth == 0:
                    self._hidden_tag = None
            return
        if tag == "a" and self._link_href is not None:
            label = " ".join("".join(self._link_text).split())
            href = self._link_href
            self._parts.append(href if not label or label == href else f"{label} ({href})")
            self._link_href = None
        elif tag in _PARAGRAPHS:
            self._parts.append("\n\n")

    def handle_data(self, data):
        if self._skipped or self._hidden_tag is not None:
            return
        if self._link_href is not None:
            self._link_text.append(data)
        else:
            self._parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self._parts).replace("\xa0", " ").split("\n")]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def html_to_text(html: str) -> str:
    converter = _Converter()
    converter.feed(html)
    converter.close()
    return converter.text()
```

- [ ] **Step 4: Run them to verify they pass**

Run: `python -m pytest app/service/email_text_test.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Write the failing renderer tests**

Append to `app/service/email_template_test.py` (the existing tests stay as they are):

```python
import tempfile
from pathlib import Path


class TestPlainTextPart(unittest.TestCase):
    def setUp(self):
        self.renderer = EmailTemplateRenderer(site_url=SITE_URL)

    def test_a_template_without_a_text_file_gets_text_derived_from_its_html(self):
        email = self.renderer.render(
            EmailTemplate.NOTIFICATION, CONTEXTS[EmailTemplate.NOTIFICATION]
        )

        self.assertIn("André Maia approved your request.", email.text)
        self.assertIn("Open dataset (https://datamap.example.org/datasets/7b21d4)", email.text)
        self.assertNotIn("<", email.text)
        self.assertNotIn("You now have access to Manaus", email.text)

    def test_a_text_file_beside_the_html_is_used_unescaped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notification.html").write_text(
                "{% block title %}{{ title }}{% endblock %}<p>{{ title }}</p>"
            )
            (root / "notification.txt").write_text("Plain: {{ title }} at {{ site_url }}")
            renderer = EmailTemplateRenderer(site_url=SITE_URL, templates_dir=root)

            email = renderer.render(EmailTemplate.NOTIFICATION, {"title": "A & B"})

        self.assertEqual(email.text, "Plain: A & B at https://datamap.example.org")
        self.assertIn("A &amp; B", email.html)

    def test_a_missing_variable_in_the_text_file_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notification.html").write_text("{% block title %}t{% endblock %}")
            (root / "notification.txt").write_text("{{ nowhere }}")
            renderer = EmailTemplateRenderer(site_url=SITE_URL, templates_dir=root)

            with self.assertRaises(UndefinedError):
                renderer.render(EmailTemplate.NOTIFICATION, {})

    def test_the_site_url_is_exposed_without_a_trailing_slash(self):
        self.assertEqual(self.renderer.site_url, "https://datamap.example.org")

    def test_the_subject_is_plain_text_not_html(self):
        context = {**CONTEXTS[EmailTemplate.NOTIFICATION], "title": "Ozone & CO2 — Ana's data"}

        email = self.renderer.render(EmailTemplate.NOTIFICATION, context)

        self.assertEqual(email.subject, "Ozone & CO2 — Ana's data")
        self.assertIn("Ozone &amp; CO2", email.html)
```

- [ ] **Step 6: Run them to verify they fail**

Run: `python -m pytest app/service/email_template_test.py -v`
Expected: the existing tests PASS; the five new ones FAIL with `AttributeError: 'RenderedEmail' object has no attribute 'text'`, `AttributeError: 'EmailTemplateRenderer' object has no attribute 'site_url'`, and `'Ozone &amp; CO2 …' != 'Ozone & CO2 …'` — the subject comes from the `title` block of an `.html` template, so it is escaped today.

- [ ] **Step 7: Extend the renderer**

In `app/service/email_template.py`, add the imports:

```python
import html as html_entities

from app.service.email_text import html_to_text
```

Replace the `RenderedEmail` dataclass:

```python
@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str = ""
```

In `EmailTemplateRenderer`, add after `__init__`:

```python
    @property
    def site_url(self) -> str:
        return self._site_url
```

and replace the `return RenderedEmail(...)` at the end of `render` with:

```python
        html = jinja_template.render(variables)
        return RenderedEmail(
            subject=html_entities.unescape(subject.strip()),
            html=html,
            text=self._text(template, variables, html),
        )

    def _text(self, template: EmailTemplate, variables: dict[str, Any], html: str) -> str:
        name = f"{template.value}.txt"
        if name not in self._env.list_templates():
            return html_to_text(html)
        return self._env.get_template(name).render(variables).strip()
```

The presence check uses `list_templates()` rather than catching `TemplateNotFound`, so a `.txt` that extends a missing parent still fails loudly.

- [ ] **Step 8: Add the text layout the new templates extend**

`app/resources/email_templates/base.txt`:

```
{% block content %}{% endblock %}

--
DataMap — a data platform for atmospheric big data and data science research in Brazil.
{{ site_url }}/

{% block reason %}{% endblock %}


University of São Paulo · Escola Politécnica, PCS
Av. Prof. Luciano Gualberto, 158 · São Paulo, SP 05508-010 · Brazil
```

`trim_blocks` eats the newline after `{% endblock %}`, hence the two empty lines before the address. Nothing renders `base.txt` on its own; it exists for the `.txt` siblings plan 03 adds (`{% extends "base.txt" %}`).

- [ ] **Step 9: Run the renderer and converter tests**

Run: `python -m pytest app/service/email_template_test.py app/service/email_text_test.py -v`
Expected: PASS (all existing renderer tests plus 5 + 6 new)

- [ ] **Step 10: Commit**

```bash
git add app/service/email_text.py app/service/email_text_test.py app/service/email_template.py app/service/email_template_test.py app/resources/email_templates/base.txt
git commit -m "feat: a plain-text part for every email template"
```

---

### Task 4: Email repository

**Files:**
- Create: `app/repository/email.py`

**Interfaces:**
- Consumes: `EmailMessage`, `EmailEvent` (Task 2); `EmailRecord`, `EmailEventRecord`, `EmailEventType`, `EmailQuery`, `EmailStatus`; `PaginatedResult` from `app/model/dataset.py`.
- Produces:

```python
class EmailRepository:
    def __init__(self, session_factory: Callable[..., AbstractContextManager[Session]]): ...
    def add(self, message: EmailMessage, event: EmailEventType, detail: str | None = None) -> EmailRecord | None: ...
    def claim_due(self, now: datetime, limit: int) -> list[EmailRecord]: ...
    def claim_stale_sending(self, claimed_before: datetime) -> list[EmailRecord]: ...
    def mark_sent(self, message_id: UUID, smtp_message_id: str, sent_at: datetime, context: dict, body_text: str) -> None: ...
    def mark_retry(self, message_id: UUID, attempts: int, next_attempt_at: datetime, detail: str) -> None: ...
    def mark_failed(self, message_id: UUID, attempts: int, detail: str, context: dict, body_text: str) -> None: ...
    def count_pending(self) -> int: ...
    def search(self, query: EmailQuery) -> PaginatedResult: ...
    def fetch(self, message_id: UUID) -> tuple[EmailRecord, list[EmailEventRecord]] | None: ...
```

`add` returns `None` only when the insert collided on `dedup_key`; any other integrity error propagates. `claim_due` and `claim_stale_sending` lock with `FOR UPDATE SKIP LOCKED` and commit the state change before returning, so two gatekeeper instances never hold the same row.

Repositories in this codebase are not unit-tested (they are mocked in service tests); this one is exercised end to end by Task 9. This task's check is a type and lint pass plus an import.

- [ ] **Step 1: Write the repository**

`app/repository/email.py`:

```python
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.model.dataset import PaginatedResult
from app.model.db.email import EmailEvent, EmailMessage
from app.model.email import (
    EmailEventRecord,
    EmailEventType,
    EmailQuery,
    EmailRecord,
    EmailStatus,
)

MAX_PAGE_SIZE = 100


def _record(row: EmailMessage) -> EmailRecord:
    return EmailRecord(
        id=row.id,
        template=row.template,
        template_version=row.template_version,
        recipient=row.recipient,
        subject=row.subject,
        body_text=row.body_text,
        context=dict(row.context or {}),
        secret_fields=list(row.secret_fields or []),
        related_type=row.related_type,
        related_id=row.related_id,
        triggered_by=row.triggered_by,
        dedup_key=row.dedup_key,
        status=EmailStatus(row.status),
        attempts=row.attempts or 0,
        next_attempt_at=row.next_attempt_at,
        smtp_message_id=row.smtp_message_id,
        sent_at=row.sent_at,
        created_at=row.created_at,
    )


class EmailRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def add(
        self, message: EmailMessage, event: EmailEventType, detail: str | None = None
    ) -> EmailRecord | None:
        dedup_key = message.dedup_key
        with self._session_factory() as session:
            try:
                session.add(message)
                session.flush()
                session.add(
                    EmailEvent(message_id=message.id, event=event.value, detail=detail)
                )
                session.commit()
            except IntegrityError:
                session.rollback()
                if dedup_key is not None and self._dedup_exists(session, dedup_key):
                    return None
                raise
            session.refresh(message)
            return _record(message)

    def claim_due(self, now: datetime, limit: int) -> list[EmailRecord]:
        with self._session_factory() as session:
            rows = (
                session.query(EmailMessage)
                .filter(
                    EmailMessage.status == EmailStatus.PENDING.value,
                    EmailMessage.next_attempt_at <= now,
                )
                .order_by(EmailMessage.next_attempt_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
                .all()
            )
            for row in rows:
                row.status = EmailStatus.SENDING.value
                row.claimed_at = now
            claimed = [_record(row) for row in rows]
            session.commit()
            return claimed

    def claim_stale_sending(self, claimed_before: datetime) -> list[EmailRecord]:
        with self._session_factory() as session:
            rows = (
                session.query(EmailMessage)
                .filter(
                    EmailMessage.status == EmailStatus.SENDING.value,
                    EmailMessage.claimed_at < claimed_before,
                )
                .with_for_update(skip_locked=True)
                .all()
            )
            for row in rows:
                row.status = EmailStatus.FAILED.value
            stale = [_record(row) for row in rows]
            session.commit()
            return stale

    def mark_sent(
        self,
        message_id: UUID,
        smtp_message_id: str,
        sent_at: datetime,
        context: dict,
        body_text: str,
    ) -> None:
        self._apply(
            message_id,
            {
                "status": EmailStatus.SENT.value,
                "smtp_message_id": smtp_message_id,
                "sent_at": sent_at,
                "context": context,
                "body_text": body_text,
            },
            EmailEventType.SENT,
            None,
        )

    def mark_retry(
        self, message_id: UUID, attempts: int, next_attempt_at: datetime, detail: str
    ) -> None:
        self._apply(
            message_id,
            {
                "status": EmailStatus.PENDING.value,
                "attempts": attempts,
                "next_attempt_at": next_attempt_at,
                "claimed_at": None,
            },
            EmailEventType.ATTEMPT_FAILED,
            detail,
        )

    def mark_failed(
        self,
        message_id: UUID,
        attempts: int,
        detail: str,
        context: dict,
        body_text: str,
    ) -> None:
        self._apply(
            message_id,
            {
                "status": EmailStatus.FAILED.value,
                "attempts": attempts,
                "context": context,
                "body_text": body_text,
            },
            EmailEventType.FAILED,
            detail,
        )

    def count_pending(self) -> int:
        with self._session_factory() as session:
            return (
                session.query(func.count(EmailMessage.id))
                .filter(EmailMessage.status == EmailStatus.PENDING.value)
                .scalar()
                or 0
            )

    def search(self, query: EmailQuery) -> PaginatedResult:
        with self._session_factory() as session:
            rows = session.query(EmailMessage)
            if query.recipient:
                rows = rows.filter(
                    func.lower(EmailMessage.recipient) == query.recipient.lower()
                )
            if query.related_id:
                rows = rows.filter(EmailMessage.related_id == query.related_id)
            if query.template:
                rows = rows.filter(EmailMessage.template == query.template)
            if query.status:
                rows = rows.filter(EmailMessage.status == query.status.value)
            rows = rows.order_by(EmailMessage.created_at.desc())

            total_count = rows.count()
            page = max(1, query.page)
            page_size = max(1, min(MAX_PAGE_SIZE, query.page_size))
            items = [
                _record(row)
                for row in rows.offset((page - 1) * page_size).limit(page_size).all()
            ]
            return PaginatedResult(
                items=items, total_count=total_count, page=page, page_size=page_size
            )

    def fetch(
        self, message_id: UUID
    ) -> tuple[EmailRecord, list[EmailEventRecord]] | None:
        with self._session_factory() as session:
            row = session.query(EmailMessage).filter_by(id=message_id).first()
            if row is None:
                return None
            events = (
                session.query(EmailEvent)
                .filter_by(message_id=message_id)
                .order_by(EmailEvent.occurred_at, EmailEvent.id)
                .all()
            )
            return _record(row), [
                EmailEventRecord(
                    id=event.id,
                    event=EmailEventType(event.event),
                    detail=event.detail,
                    occurred_at=event.occurred_at,
                )
                for event in events
            ]

    def _apply(
        self,
        message_id: UUID,
        values: dict,
        event: EmailEventType,
        detail: str | None,
    ) -> None:
        with self._session_factory() as session:
            session.query(EmailMessage).filter(EmailMessage.id == message_id).update(
                values, synchronize_session=False
            )
            session.add(EmailEvent(message_id=message_id, event=event.value, detail=detail))
            session.commit()

    @staticmethod
    def _dedup_exists(session: Session, dedup_key: str) -> bool:
        return (
            session.query(EmailMessage.id).filter_by(dedup_key=dedup_key).first()
            is not None
        )
```

- [ ] **Step 2: Check it imports and lints**

Run:
```bash
python -c "import app.repository.email"
ruff check app/repository/email.py && ruff format --check app/repository/email.py
```
Expected: no output from the import; `All checks passed!` and `1 file already formatted` (run `ruff format app/repository/email.py` first if it reports a reformat).

- [ ] **Step 3: Commit**

```bash
git add app/repository/email.py
git commit -m "feat: email repository that claims due messages with SKIP LOCKED"
```

---

### Task 5: SMTP gateway

**Files:**
- Create: `app/gateway/email/__init__.py` (empty), `app/gateway/email/smtp.py`, `app/gateway/email/smtp_test.py`

**Interfaces:**
- Produces:

```python
class DefiniteSendFailure(Exception): ...    # the server certainly did not accept the message
class UncertainSendFailure(Exception): ...   # it may have; never retry
class SmtpSender:
    def __init__(self, host: str, port: int, username: str | None, password: str | None,
                 starttls: bool, timeout_seconds: float = 30.0, smtp_factory=smtplib.SMTP): ...
    def send(self, message: email.message.EmailMessage) -> None: ...
```

Classification, which is what makes "never twice" hold:

| Where it fails | Exception | Class |
|---|---|---|
| Opening the connection | any `OSError` / `smtplib.SMTPException` | Definite |
| `STARTTLS`, `login` | any `OSError` / `smtplib.SMTPException` | Definite |
| `send_message` | `SMTPRecipientsRefused`, `SMTPSenderRefused`, `SMTPDataError` (the server answered no) | Definite |
| `send_message` | anything else (`SMTPServerDisconnected`, timeout, `OSError`) | Uncertain |
| `quit` after a successful send | anything | ignored — the message was accepted |

- [ ] **Step 1: Write the failing test**

`app/gateway/email/smtp_test.py`:

```python
import smtplib
import socket
import unittest
from email.message import EmailMessage
from unittest.mock import MagicMock, Mock

from app.gateway.email.smtp import (
    DefiniteSendFailure,
    SmtpSender,
    UncertainSendFailure,
)


def _message() -> EmailMessage:
    message = EmailMessage()
    message["From"] = "DataMap <datamap@example.com>"
    message["To"] = "someone@example.com"
    message["Subject"] = "Hello"
    message.set_content("Hi")
    return message


class TestSmtpSender(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.factory = Mock(return_value=self.connection)

    def sender(self, **overrides) -> SmtpSender:
        options = dict(
            host="smtp.example.com",
            port=587,
            username="datamap@example.com",
            password="app-password",
            starttls=True,
            timeout_seconds=7,
            smtp_factory=self.factory,
        )
        options.update(overrides)
        return SmtpSender(**options)

    def test_it_upgrades_logs_in_sends_and_quits(self):
        message = _message()

        self.sender().send(message)

        self.factory.assert_called_once_with("smtp.example.com", 587, timeout=7)
        self.connection.starttls.assert_called_once()
        self.connection.login.assert_called_once_with(
            "datamap@example.com", "app-password"
        )
        self.connection.send_message.assert_called_once_with(message)
        self.connection.quit.assert_called_once()

    def test_without_credentials_it_does_not_log_in(self):
        self.sender(username=None, password=None, starttls=False).send(_message())

        self.connection.starttls.assert_not_called()
        self.connection.login.assert_not_called()

    def test_a_refused_connection_is_definite(self):
        self.factory.side_effect = ConnectionRefusedError("refused")

        with self.assertRaises(DefiniteSendFailure):
            self.sender().send(_message())

    def test_wrong_credentials_are_definite(self):
        self.connection.login.side_effect = smtplib.SMTPAuthenticationError(
            535, b"5.7.8 Username and Password not accepted"
        )

        with self.assertRaises(DefiniteSendFailure):
            self.sender().send(_message())

    def test_a_recipient_the_server_refuses_is_definite(self):
        self.connection.send_message.side_effect = smtplib.SMTPRecipientsRefused(
            {"someone@example.com": (550, b"no such user")}
        )

        with self.assertRaises(DefiniteSendFailure):
            self.sender().send(_message())

    def test_content_the_server_refuses_is_definite(self):
        self.connection.send_message.side_effect = smtplib.SMTPDataError(
            552, b"message too big"
        )

        with self.assertRaises(DefiniteSendFailure):
            self.sender().send(_message())

    def test_a_disconnect_while_sending_is_uncertain(self):
        self.connection.send_message.side_effect = smtplib.SMTPServerDisconnected(
            "Connection unexpectedly closed"
        )

        with self.assertRaises(UncertainSendFailure):
            self.sender().send(_message())

    def test_a_timeout_while_sending_is_uncertain(self):
        self.connection.send_message.side_effect = socket.timeout("timed out")

        with self.assertRaises(UncertainSendFailure):
            self.sender().send(_message())

    def test_a_failing_quit_after_a_send_is_not_a_failure(self):
        self.connection.quit.side_effect = smtplib.SMTPServerDisconnected("gone")

        self.sender().send(_message())

        self.connection.send_message.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest app/gateway/email/smtp_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.gateway.email'`

- [ ] **Step 3: Write the gateway**

`app/gateway/email/__init__.py`: empty file.

`app/gateway/email/smtp.py`:

```python
import smtplib
import ssl
from email.message import EmailMessage

from app.metrics import metrics

_REFUSED_BY_SERVER = (
    smtplib.SMTPRecipientsRefused,
    smtplib.SMTPSenderRefused,
    smtplib.SMTPDataError,
)


class DefiniteSendFailure(Exception):
    """The server certainly did not accept the message; it may be retried."""


class UncertainSendFailure(Exception):
    """The message may have been accepted; retrying could deliver it twice."""


class SmtpSender:
    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        starttls: bool,
        timeout_seconds: float = 30.0,
        smtp_factory=smtplib.SMTP,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username or None
        self._password = password or None
        self._starttls = starttls
        self._timeout = timeout_seconds
        self._smtp_factory = smtp_factory

    def send(self, message: EmailMessage) -> None:
        with metrics.external_call("smtp", "send"):
            self._send(message)

    def _send(self, message: EmailMessage) -> None:
        try:
            connection = self._smtp_factory(self._host, self._port, timeout=self._timeout)
        except (OSError, smtplib.SMTPException) as e:
            raise DefiniteSendFailure(f"connect: {e}") from e

        try:
            try:
                if self._starttls:
                    connection.starttls(context=ssl.create_default_context())
                if self._username:
                    connection.login(self._username, self._password or "")
            except (OSError, smtplib.SMTPException) as e:
                raise DefiniteSendFailure(f"session: {e}") from e

            try:
                connection.send_message(message)
            except _REFUSED_BY_SERVER as e:
                raise DefiniteSendFailure(f"refused: {e}") from e
            except (OSError, smtplib.SMTPException) as e:
                raise UncertainSendFailure(f"during send: {e}") from e
        finally:
            try:
                connection.quit()
            except (OSError, smtplib.SMTPException):
                pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest app/gateway/email/smtp_test.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add app/gateway/email
git commit -m "feat: SMTP sender that tells a refusal from an unknown outcome"
```

---

### Task 6: Masking, metrics and `EmailService.enqueue`

**Files:**
- Create: `app/service/email_masking.py`, `app/service/email_masking_test.py`
- Modify: `app/metrics.py` (declare in `Metrics.__init__`, methods next to `snapshot_published`), `app/metrics_test.py`
- Create: `app/service/email.py`, `app/service/email_test.py`

**Interfaces:**
- Consumes: `EmailRepository` (Task 4), `EmailTemplate`/`EmailTemplateRenderer` (`app/service/email_template.py`, extended in Task 3), `SmtpSender` (Task 5, only as a constructor argument here).
- Produces:

```python
MASK = "[masked]"
def mask_secrets(context: dict, body_text: str, secret_fields: Iterable[str]) -> tuple[dict, str]: ...

metrics.email_outcome(template: str, outcome: str) -> None     # outcome: sent | retried | failed | skipped
metrics.email_pending(count: int) -> None

class EmailService:
    def __init__(self, repository: EmailRepository, renderer: EmailTemplateRenderer, sender: SmtpSender,
                 enabled: bool, from_name: str, from_address: str, reply_to: str | None,
                 template_version: str, clock: Callable[[], datetime] = _utcnow): ...
    def enqueue(self, *, template: str, recipient: str, context: dict,
                secret_fields: frozenset[str] = frozenset(), related_type: str | None = None,
                related_id: UUID | None = None, triggered_by: UUID | None = None,
                dedup_key: str | None = None) -> UUID | None: ...
```

`enqueue` renders immediately, so a broken template fails in the request that caused it, not minutes later in the dispatcher. `template` is an `EmailTemplate` value; an unknown name raises `ValueError` there too. It returns the message id, or `None` when `dedup_key` already exists. A placeholder recipient is stored as `skipped`, masked at once, and counted.

- [ ] **Step 1: Write the failing masking test**

`app/service/email_masking_test.py`:

```python
import unittest

from app.service.email_masking import MASK, mask_secrets


class TestMaskSecrets(unittest.TestCase):
    def test_a_secret_is_masked_in_the_context_and_wherever_the_body_shows_it(self):
        link = "https://datamap.example/invitations/abc123"
        context = {"link": link, "dataset_name": "Rain"}
        body = f"Open {link} to accept. Again: {link}"

        masked_context, masked_body = mask_secrets(context, body, ["link"])

        self.assertEqual(masked_context, {"link": MASK, "dataset_name": "Rain"})
        self.assertEqual(masked_body, f"Open {MASK} to accept. Again: {MASK}")
        self.assertEqual(context["link"], link)

    def test_fields_that_are_not_secret_are_untouched(self):
        context = {"dataset_name": "Rain"}

        self.assertEqual(mask_secrets(context, "Rain", []), (context, "Rain"))

    def test_an_absent_or_empty_secret_masks_nothing_in_the_body(self):
        masked_context, masked_body = mask_secrets({"code": ""}, "body", ["code", "x"])

        self.assertEqual(masked_context, {"code": MASK})
        self.assertEqual(masked_body, "body")

    def test_a_secret_repeated_inside_other_fields_is_masked_there_too(self):
        context = {
            "code": "c0ffee12",
            "message": "Verification code: c0ffee12",
            "details": [{"label": "Code", "value": "c0ffee12"}],
            "count": 3,
        }

        masked_context, _ = mask_secrets(context, "", ["code"])

        self.assertEqual(
            masked_context,
            {
                "code": MASK,
                "message": f"Verification code: {MASK}",
                "details": [{"label": "Code", "value": MASK}],
                "count": 3,
            },
        )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest app/service/email_masking_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.service.email_masking'`

- [ ] **Step 3: Write the masking helper**

`app/service/email_masking.py`:

```python
from typing import Any, Iterable

MASK = "[masked]"


def _replace(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, MASK)
        return value
    if isinstance(value, list):
        return [_replace(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, secrets) for key, item in value.items()}
    return value


def mask_secrets(
    context: dict, body_text: str, secret_fields: Iterable[str]
) -> tuple[dict, str]:
    names = set(secret_fields)
    secrets = [
        context[name]
        for name in names
        if isinstance(context.get(name), str) and context[name]
    ]
    masked = {
        key: MASK if key in names else _replace(value, secrets)
        for key, value in context.items()
    }
    for secret in secrets:
        body_text = body_text.replace(secret, MASK)
    return masked, body_text
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python -m pytest app/service/email_masking_test.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Write the failing metrics test**

Append to `app/metrics_test.py`:

```python
class TestEmail(MetricsTestCase):
    def test_each_outcome_is_counted_per_template(self):
        self.metrics.email_outcome("invitation", "sent")
        self.metrics.email_outcome("invitation", "sent")
        self.metrics.email_outcome("invitation", "failed")

        self.assertEqual(
            self.value("datamap_emails_total", template="invitation", outcome="sent"),
            2.0,
        )
        self.assertEqual(
            self.value("datamap_emails_total", template="invitation", outcome="failed"),
            1.0,
        )

    def test_the_pending_gauge_shows_the_last_count(self):
        self.metrics.email_pending(7)
        self.metrics.email_pending(3)

        self.assertEqual(self.value("datamap_email_pending"), 3.0)
```

Run: `python -m pytest app/metrics_test.py::TestEmail -v`
Expected: FAIL with `AttributeError: 'Metrics' object has no attribute 'email_outcome'`

- [ ] **Step 6: Add the metrics**

In `app/metrics.py`, inside `Metrics.__init__`, after `self._collocation_pending = Gauge(...)`:

```python
        self._emails = Counter(
            "datamap_emails_total",
            "Email messages by what became of them",
            ["template", "outcome"],
            registry=self.registry,
        )
        self._email_pending = Gauge(
            "datamap_email_pending",
            "Email messages waiting to be sent",
            registry=self.registry,
        )
```

After the `collocation_pending` method:

```python
    def email_outcome(self, template: str, outcome: str) -> None:
        self._emails.labels(template=template, outcome=outcome).inc()

    def email_pending(self, count: int) -> None:
        self._email_pending.set(count)
```

Run: `python -m pytest app/metrics_test.py -v`
Expected: PASS (all, including `TestEmail`)

- [ ] **Step 7: Write the failing `enqueue` tests**

`app/service/email_test.py`:

```python
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import UUID, uuid4

from prometheus_client import REGISTRY

from app.gateway.email.smtp import SmtpSender
from app.model.db.email import EmailMessage
from app.model.email import EmailEventType, EmailRecord, EmailStatus
from app.repository.email import EmailRepository
from app.service.email import EmailService
from app.service.email_masking import MASK
from app.service.email_template import EmailTemplateRenderer

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

CODE = "c0ffee12"
TEST_CONTEXT = {
    "title": "DataMap test message",
    "preheader": "A test message from DataMap.",
    "message": f"If this reached your inbox, the platform can send email. Verification code: {CODE}",
    "cta_label": "Open DataMap",
    "cta_url": "https://datamap.example",
    "reason": "You received this email because a DataMap administrator sent a test message to this address.",
    "code": CODE,
}


def _sample(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def _record(**overrides) -> EmailRecord:
    values = dict(
        id=uuid4(),
        template="notification",
        template_version="abc1234",
        recipient="someone@example.com",
        subject="DataMap test message",
        body_text="Verification code: c0ffee12",
        context=dict(TEST_CONTEXT),
        secret_fields=["code"],
        related_type=None,
        related_id=None,
        triggered_by=None,
        dedup_key=None,
        status=EmailStatus.SENDING,
        attempts=0,
        next_attempt_at=NOW,
        smtp_message_id=None,
        sent_at=None,
        created_at=NOW,
    )
    values.update(overrides)
    return EmailRecord(**values)


class EmailServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.repository = Mock(spec=EmailRepository)
        self.sender = Mock(spec=SmtpSender)
        self.renderer = EmailTemplateRenderer(site_url="https://datamap.example")
        self.service = self.build(enabled=True)

    def build(self, enabled: bool) -> EmailService:
        return EmailService(
            repository=self.repository,
            renderer=self.renderer,
            sender=self.sender,
            enabled=enabled,
            from_name="DataMap",
            from_address="datamap.pcs@gmail.com",
            reply_to=None,
            template_version="abc1234",
            clock=lambda: NOW,
        )

    def stored(self) -> tuple[EmailMessage, EmailEventType, str | None]:
        args, kwargs = self.repository.add.call_args
        message = kwargs.get("message", args[0] if args else None)
        event = kwargs.get("event", args[1] if len(args) > 1 else None)
        detail = kwargs.get("detail", args[2] if len(args) > 2 else None)
        return message, event, detail


class TestEnqueue(EmailServiceTestCase):
    def test_a_message_is_rendered_and_stored_pending_with_a_queued_event(self):
        self.repository.add.side_effect = lambda message, event, detail=None: _record(
            id=message.id, status=EmailStatus.PENDING
        )
        related = uuid4()

        message_id = self.service.enqueue(
            template="notification",
            recipient="someone@example.com",
            context=TEST_CONTEXT,
            secret_fields=frozenset({"code"}),
            related_type="dataset",
            related_id=related,
            dedup_key="test:1",
        )

        message, event, _ = self.stored()
        self.assertIsInstance(message_id, UUID)
        self.assertEqual(message.id, message_id)
        self.assertEqual(message.status, EmailStatus.PENDING.value)
        self.assertEqual(event, EmailEventType.QUEUED)
        self.assertEqual(message.subject, "DataMap test message")
        self.assertIn("c0ffee12", message.body_text)
        self.assertEqual(message.context, TEST_CONTEXT)
        self.assertEqual(message.secret_fields, ["code"])
        self.assertEqual(message.template_version, "abc1234")
        self.assertEqual((message.related_type, message.related_id), ("dataset", related))
        self.assertEqual(message.dedup_key, "test:1")

    def test_a_duplicate_dedup_key_returns_none(self):
        self.repository.add.return_value = None

        self.assertIsNone(
            self.service.enqueue(
                template="notification",
                recipient="someone@example.com",
                context=TEST_CONTEXT,
                dedup_key="test:1",
            )
        )

    def test_a_placeholder_address_is_recorded_as_skipped_and_masked(self):
        self.repository.add.side_effect = lambda message, event, detail=None: _record(
            id=message.id, status=EmailStatus.SKIPPED
        )
        before = _sample("datamap_emails_total", template="notification", outcome="skipped")

        self.service.enqueue(
            template="notification",
            recipient="0000-0002-1825-0097@fake.mail.com",
            context=TEST_CONTEXT,
            secret_fields=frozenset({"code"}),
        )

        message, event, detail = self.stored()
        self.assertEqual(message.status, EmailStatus.SKIPPED.value)
        self.assertEqual(event, EmailEventType.SKIPPED)
        self.assertEqual(detail, "placeholder address")
        self.assertEqual(message.context["code"], MASK)
        self.assertNotIn(CODE, str(message.context))
        self.assertNotIn(CODE, message.body_text)
        self.assertEqual(
            _sample("datamap_emails_total", template="notification", outcome="skipped"),
            before + 1,
        )
        self.sender.send.assert_not_called()

    def test_a_template_that_cannot_render_fails_where_it_was_asked_for(self):
        with self.assertRaises(Exception):
            self.service.enqueue(
                template="notification", recipient="a@example.com", context={}
            )

        self.repository.add.assert_not_called()
```

- [ ] **Step 8: Run them to verify they fail**

Run: `python -m pytest app/service/email_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.service.email'`

- [ ] **Step 9: Write `EmailService` with `enqueue`**

`app/service/email.py`:

```python
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
```

- [ ] **Step 10: Run them to verify they pass**

Run: `python -m pytest app/service/email_test.py app/service/email_masking_test.py app/metrics_test.py -v`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add app/service/email.py app/service/email_test.py app/service/email_masking.py app/service/email_masking_test.py app/metrics.py app/metrics_test.py
git commit -m "feat: queue email with its secrets, skipping placeholder addresses"
```

---

### Task 7: `EmailService.dispatch_due`, `search`, `fetch`, `send_test_message`

**Files:**
- Modify: `app/service/email.py`
- Modify: `app/service/email_test.py`

**Interfaces:**
- Consumes: Tasks 4–6.
- Produces:

```python
MAX_ATTEMPTS = 5
RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15), timedelta(hours=1))
STALE_SENDING_AFTER = timedelta(minutes=10)

class EmailService:
    def dispatch_due(self, limit: int = 50) -> DispatchResult: ...
    def search(self, query: EmailQuery) -> PaginatedResult: ...
    def fetch(self, message_id: UUID) -> tuple[EmailRecord, list[EmailEventRecord]]: ...   # NotFoundException
    def send_test_message(self, recipient: str, triggered_by: UUID | None) -> UUID: ...
```

`dispatch_due`, in order:

1. Rows in `sending` claimed more than 10 minutes ago: `failed`, masked, detail `delivery uncertain: left in sending`, counted `failed`.
2. With `EMAIL_ENABLED` off: set the pending gauge and return.
3. Claim up to `limit` due rows (now `sending`, committed).
4. For each: build the MIME message (re-render HTML from the stored context; a render error → `failed`), send.
   - success → `sent`, Message-ID, `sent_at`, secrets masked; counted `sent`.
   - `DefiniteSendFailure` → attempts + 1; if < 5, back to `pending` at `now + RETRY_DELAYS[attempts - 1]`, counted `retried`; else `failed`, masked, counted `failed`.
   - `UncertainSendFailure` → `failed`, masked, detail `delivery uncertain: …`, counted `failed`. Never retried.
5. Set the pending gauge.

- [ ] **Step 1: Write the failing tests**

Append to `app/service/email_test.py`:

```python
from datetime import timedelta

from app.exception.not_found import NotFoundException
from app.gateway.email.smtp import DefiniteSendFailure, UncertainSendFailure
from app.service.email import MAX_ATTEMPTS, RETRY_DELAYS


class TestDispatch(EmailServiceTestCase):
    def setUp(self):
        super().setUp()
        self.repository.claim_stale_sending.return_value = []
        self.repository.count_pending.return_value = 0

    def test_a_due_message_is_sent_once_and_its_secret_masked_afterwards(self):
        record = _record()
        self.repository.claim_due.return_value = [record]

        result = self.service.dispatch_due()

        self.assertEqual(result.sent, 1)
        sent = self.sender.send.call_args.args[0]
        self.assertEqual(sent["To"], "someone@example.com")
        self.assertEqual(sent["From"], "DataMap <datamap.pcs@gmail.com>")
        self.assertEqual(sent["Subject"], "DataMap test message")
        self.assertTrue(sent["Message-ID"].endswith("@gmail.com>"))
        self.assertIn("c0ffee12", sent.get_body(("plain",)).get_content())
        self.assertIn("c0ffee12", sent.get_body(("html",)).get_content())

        kwargs = self.repository.mark_sent.call_args.kwargs
        self.assertEqual(kwargs["message_id"], record.id)
        self.assertEqual(kwargs["smtp_message_id"], sent["Message-ID"])
        self.assertEqual(kwargs["sent_at"], NOW)
        self.assertEqual(kwargs["context"]["code"], MASK)
        self.assertNotIn(CODE, str(kwargs["context"]))
        self.assertNotIn(CODE, kwargs["body_text"])

    def test_a_definite_refusal_is_retried_later(self):
        self.repository.claim_due.return_value = [_record(attempts=0)]
        self.sender.send.side_effect = DefiniteSendFailure("connect: refused")

        result = self.service.dispatch_due()

        self.assertEqual(result.retried, 1)
        kwargs = self.repository.mark_retry.call_args.kwargs
        self.assertEqual(kwargs["attempts"], 1)
        self.assertEqual(kwargs["next_attempt_at"], NOW + RETRY_DELAYS[0])
        self.assertIn("connect: refused", kwargs["detail"])
        self.repository.mark_failed.assert_not_called()

    def test_the_fifth_definite_refusal_is_final(self):
        self.repository.claim_due.return_value = [_record(attempts=MAX_ATTEMPTS - 1)]
        self.sender.send.side_effect = DefiniteSendFailure("refused: 550")

        result = self.service.dispatch_due()

        self.assertEqual(result.failed, 1)
        kwargs = self.repository.mark_failed.call_args.kwargs
        self.assertEqual(kwargs["attempts"], MAX_ATTEMPTS)
        self.assertEqual(kwargs["context"]["code"], MASK)
        self.repository.mark_retry.assert_not_called()

    def test_an_uncertain_outcome_is_never_retried(self):
        self.repository.claim_due.return_value = [_record(attempts=0)]
        self.sender.send.side_effect = UncertainSendFailure("during send: timed out")

        result = self.service.dispatch_due()

        self.assertEqual(result.failed, 1)
        kwargs = self.repository.mark_failed.call_args.kwargs
        self.assertTrue(kwargs["detail"].startswith("delivery uncertain"))
        self.assertEqual(kwargs["attempts"], 1)
        self.repository.mark_retry.assert_not_called()

    def test_a_message_left_in_sending_becomes_failed_not_sent_again(self):
        self.repository.claim_stale_sending.return_value = [_record()]
        self.repository.claim_due.return_value = []

        result = self.service.dispatch_due()

        self.repository.claim_stale_sending.assert_called_once_with(
            NOW - timedelta(minutes=10)
        )
        self.assertEqual(result.failed, 1)
        self.assertTrue(
            self.repository.mark_failed.call_args.kwargs["detail"].startswith(
                "delivery uncertain"
            )
        )
        self.sender.send.assert_not_called()

    def test_with_sending_off_nothing_is_claimed(self):
        self.service = self.build(enabled=False)
        self.repository.count_pending.return_value = 4

        result = self.service.dispatch_due()

        self.repository.claim_due.assert_not_called()
        self.sender.send.assert_not_called()
        self.assertEqual(result.sent, 0)
        self.assertEqual(_sample("datamap_email_pending"), 4.0)

    def test_outcomes_are_counted(self):
        before = _sample("datamap_emails_total", template="notification", outcome="sent")
        self.repository.claim_due.return_value = [_record(), _record()]

        self.service.dispatch_due()

        self.assertEqual(
            _sample("datamap_emails_total", template="notification", outcome="sent"),
            before + 2,
        )

    def test_a_template_that_no_longer_renders_fails_without_sending(self):
        self.repository.claim_due.return_value = [_record(context={})]

        result = self.service.dispatch_due()

        self.assertEqual(result.failed, 1)
        self.sender.send.assert_not_called()

    def test_reply_to_is_set_when_configured(self):
        service = EmailService(
            repository=self.repository,
            renderer=self.renderer,
            sender=self.sender,
            enabled=True,
            from_name="DataMap",
            from_address="datamap.pcs@gmail.com",
            reply_to="caio.maia@usp.br",
            template_version="abc1234",
            clock=lambda: NOW,
        )
        self.repository.claim_due.return_value = [_record()]

        service.dispatch_due()

        self.assertEqual(self.sender.send.call_args.args[0]["Reply-To"], "caio.maia@usp.br")


class TestReading(EmailServiceTestCase):
    def test_an_unknown_message_is_not_found(self):
        self.repository.fetch.return_value = None

        with self.assertRaises(NotFoundException):
            self.service.fetch(uuid4())

    def test_the_test_message_carries_a_masked_code(self):
        self.repository.add.side_effect = lambda message, event, detail=None: _record(
            id=message.id, status=EmailStatus.PENDING
        )
        admin = uuid4()

        self.service.send_test_message("ops@example.com", triggered_by=admin)

        message, _, _ = self.stored()
        self.assertEqual(message.template, "notification")
        self.assertEqual(message.secret_fields, ["code"])
        self.assertEqual(len(message.context["code"]), 8)
        self.assertIn(message.context["code"], message.context["message"])
        self.assertEqual(message.subject, "DataMap test message")
        self.assertEqual(message.triggered_by, admin)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest app/service/email_test.py -v`
Expected: FAIL with `ImportError: cannot import name 'MAX_ATTEMPTS' from 'app.service.email'`

- [ ] **Step 3: Implement dispatch, reading and the test message**

Add to the imports of `app/service/email.py`:

```python
import secrets
from datetime import timedelta
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, make_msgid

from app.exception.not_found import NotFoundException
from app.gateway.email.smtp import DefiniteSendFailure, UncertainSendFailure
from app.model.dataset import PaginatedResult
from app.model.email import DispatchResult, EmailEventRecord, EmailQuery, EmailRecord
```

Add module constants after `PLACEHOLDER_DOMAIN`:

```python
MAX_ATTEMPTS = 5
RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
)
STALE_SENDING_AFTER = timedelta(minutes=10)
```

Add these methods to `EmailService`:

```python
    def dispatch_due(self, limit: int = 50) -> DispatchResult:
        result = DispatchResult()
        now = self._clock()

        for stale in self._repository.claim_stale_sending(now - STALE_SENDING_AFTER):
            self._fail(stale, stale.attempts, "delivery uncertain: left in sending", result)

        if self._enabled:
            for record in self._repository.claim_due(now, limit):
                self._deliver(record, now, result)

        metrics.email_pending(self._repository.count_pending())
        return result

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

    def _deliver(self, record: EmailRecord, now: datetime, result: DispatchResult) -> None:
        attempts = record.attempts + 1
        try:
            message = self._mime(record)
        except Exception as e:
            self._fail(record, attempts, f"render: {e}", result)
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
            extra=fields(email_id=str(record.id), template=record.template, outcome=outcome),
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
```

- [ ] **Step 4: Run them to verify they pass**

Run: `python -m pytest app/service/email_test.py -v`
Expected: PASS (all `TestEnqueue`, `TestDispatch`, `TestReading`)

- [ ] **Step 5: Commit**

```bash
git add app/service/email.py app/service/email_test.py
git commit -m "feat: dispatch email at most once, retrying only definite refusals"
```

---

### Task 8: Dispatch and admin routes, wiring

**Files:**
- Create: `app/controller/v1/internal/notification.py`
- Modify: `app/controller/v1/internal/resource.py` (append)
- Create: `app/controller/v1/admin/__init__.py` (empty), `app/controller/v1/admin/email.py`, `app/controller/v1/admin/resource.py`
- Modify: `app/container.py`, `app/setup.py`
- Test: `app/controller/routes_security_test.py` (existing, must keep passing); `app/controller/v1/admin/email_test.py` (create)

**Interfaces:**
- Consumes: `EmailService` (Tasks 6–7).
- Produces: `Container.email_service`, `Container.email_renderer` (plan 03 reuses both); routes per contracts §Notifications plus `POST /admin/emails/test`.

| Verb | Path | Guards | Body | Response |
|---|---|---|---|---|
| POST | `/v1/internal/notifications/dispatch` | `authenticate` | — | `200 {"queued","sent","failed","skipped","retried"}` |
| GET | `/v1/admin/emails/` | `authenticate`, `authorize` | query `recipient, related_id, template, status, page, page_size` | `200 {"items":[EmailSummary],"total_count","page","page_size"}` |
| GET | `/v1/admin/emails/{email_id}` | `authenticate`, `authorize` | — | `200 EmailDetail` |
| POST | `/v1/admin/emails/test` | `authenticate`, `authorize` | `{"recipient": str}` | `202 {"id": uuid}` |

`POST /admin/emails/test` is an addition to the contracts: it is how an operator checks a new SMTP credential in production without touching the database.

- [ ] **Step 1: Write the failing route test**

`app/controller/v1/admin/email_test.py`:

```python
import unittest

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app import setup
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize


class TestEmailRoutes(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        setup.setup_routes(app)
        self.routes = {
            (route.path, method): route
            for route in app.routes
            if isinstance(route, APIRoute)
            for method in route.methods
        }

    def guards(self, path: str, method: str) -> set:
        return {
            dependency.call
            for dependency in self.routes[(path, method)].dependant.dependencies
        }

    def test_the_archivist_dispatch_route_takes_client_credentials_only(self):
        guards = self.guards("/v1/internal/notifications/dispatch", "POST")

        self.assertIn(authenticate, guards)
        self.assertNotIn(authorize, guards)

    def test_the_email_record_is_behind_casbin(self):
        for key in [
            ("/v1/admin/emails/", "GET"),
            ("/v1/admin/emails/{email_id}", "GET"),
            ("/v1/admin/emails/test", "POST"),
        ]:
            self.assertTrue({authenticate, authorize} <= self.guards(*key), key)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest app/controller/v1/admin/email_test.py -v`
Expected: FAIL with `KeyError: ('/v1/internal/notifications/dispatch', 'POST')` (or `ModuleNotFoundError` for `app.controller.v1.admin`)

- [ ] **Step 3: Write the internal dispatch route**

Append to `app/controller/v1/internal/resource.py`:

```python
class NotificationDispatchResponse(BaseModel):
    queued: int = Field(..., description="Messages queued by this pass")
    sent: int = Field(..., description="Messages accepted by the SMTP server")
    failed: int = Field(..., description="Messages that will not be sent")
    skipped: int = Field(..., description="Messages recorded and not sent")
    retried: int = Field(..., description="Messages refused and scheduled again")
```

(Add `from pydantic import BaseModel, Field` to that file's imports if absent.)

`app/controller/v1/internal/notification.py`:

```python
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.v1.internal.resource import NotificationDispatchResponse
from app.service.email import EmailService

router = APIRouter(
    prefix="/internal/notifications",
    tags=["internal"],
    responses={404: {"description": "Not found"}},
)


@router.post(
    "/dispatch",
    dependencies=[Depends(authenticate)],
    response_model=NotificationDispatchResponse,
)
@inject
def dispatch(
    email_service: EmailService = Depends(Provide[Container.email_service]),
) -> NotificationDispatchResponse:
    """Send the email that is due. Called by the Archivist every few minutes."""
    result = email_service.dispatch_due()
    return NotificationDispatchResponse(
        queued=result.queued,
        sent=result.sent,
        failed=result.failed,
        skipped=result.skipped,
        retried=result.retried,
    )
```

- [ ] **Step 4: Write the admin routes**

`app/controller/v1/admin/__init__.py`: empty file.

`app/controller/v1/admin/resource.py`:

```python
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EmailSummaryResponse(BaseModel):
    id: UUID
    template: str
    recipient: str
    subject: str
    status: str
    attempts: int
    related_type: Optional[str]
    related_id: Optional[UUID]
    triggered_by: Optional[UUID]
    created_at: datetime
    sent_at: Optional[datetime]


class EmailListResponse(BaseModel):
    items: list[EmailSummaryResponse]
    total_count: int
    page: int
    page_size: int


class EmailEventResponse(BaseModel):
    event: str
    detail: Optional[str]
    occurred_at: datetime


class EmailDetailResponse(EmailSummaryResponse):
    template_version: str
    body_text: str
    context: dict
    smtp_message_id: Optional[str]
    next_attempt_at: datetime
    events: list[EmailEventResponse]


class TestEmailRequest(BaseModel):
    recipient: str = Field(..., min_length=3, max_length=256, description="Address")


class TestEmailResponse(BaseModel):
    id: UUID
```

`app/controller/v1/admin/email.py`:

```python
from typing import Optional
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.admin.resource import (
    EmailDetailResponse,
    EmailEventResponse,
    EmailListResponse,
    EmailSummaryResponse,
    TestEmailRequest,
    TestEmailResponse,
)
from app.model.email import EmailQuery, EmailRecord, EmailStatus
from app.service.email import EmailService

router = APIRouter(
    prefix="/admin/emails",
    tags=["admin"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


def _summary(record: EmailRecord) -> dict:
    return dict(
        id=record.id,
        template=record.template,
        recipient=record.recipient,
        subject=record.subject,
        status=record.status.value,
        attempts=record.attempts,
        related_type=record.related_type,
        related_id=record.related_id,
        triggered_by=record.triggered_by,
        created_at=record.created_at,
        sent_at=record.sent_at,
    )


@router.get("/", response_model=EmailListResponse)
@inject
def search(
    recipient: Optional[str] = None,
    related_id: Optional[UUID] = None,
    template: Optional[str] = None,
    status: Optional[EmailStatus] = None,
    page: int = 1,
    page_size: int = 20,
    service: EmailService = Depends(Provide[Container.email_service]),
) -> EmailListResponse:
    result = service.search(
        EmailQuery(
            recipient=recipient,
            related_id=related_id,
            template=template,
            status=status,
            page=page,
            page_size=page_size,
        )
    )
    return EmailListResponse(
        items=[EmailSummaryResponse(**_summary(item)) for item in result.items],
        total_count=result.total_count,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{email_id}", response_model=EmailDetailResponse)
@inject
def fetch(
    email_id: UUID,
    service: EmailService = Depends(Provide[Container.email_service]),
) -> EmailDetailResponse:
    record, events = service.fetch(email_id)
    return EmailDetailResponse(
        **_summary(record),
        template_version=record.template_version,
        body_text=record.body_text,
        context=record.context,
        smtp_message_id=record.smtp_message_id,
        next_attempt_at=record.next_attempt_at,
        events=[
            EmailEventResponse(
                event=event.event.value,
                detail=event.detail,
                occurred_at=event.occurred_at,
            )
            for event in events
        ],
    )


@router.post("/test", status_code=202, response_model=TestEmailResponse)
@inject
def send_test(
    request: TestEmailRequest,
    user_id: UUID = Depends(parse_user_header),
    service: EmailService = Depends(Provide[Container.email_service]),
) -> TestEmailResponse:
    return TestEmailResponse(
        id=service.send_test_message(request.recipient, triggered_by=user_id)
    )
```

- [ ] **Step 5: Wire the container and mount the routers**

In `app/container.py`, add imports:

```python
from app.gateway.email.smtp import SmtpSender
from app.repository.email import EmailRepository
from app.service.email import EmailService
from app.service.email_template import EmailTemplateRenderer
```

Add to `wiring_config.modules`:

```python
            "app.controller.v1.internal.notification",
            "app.controller.v1.admin.email",
```

Add providers after `tus_service`:

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

In `app/setup.py`, add imports next to the other routers:

```python
from app.controller.v1.admin.email import router as admin_email_router
from app.controller.v1.internal.notification import (
    router as internal_notification_router,
)
```

and in `setup_routes`, after `internal_dataset_collocation_router`:

```python
    fastAPIApp.include_router(internal_notification_router, prefix="/v1")
    fastAPIApp.include_router(admin_email_router, prefix="/v1")
```

- [ ] **Step 6: Run the route tests and the whole unit suite**

Run:
```bash
python -m pytest app/controller/v1/admin/email_test.py app/controller/routes_security_test.py -v
python -m pytest
```
Expected: PASS; the full suite has no new failures.

- [ ] **Step 7: Commit**

```bash
git add app/controller/v1/internal app/controller/v1/admin app/container.py app/setup.py
git commit -m "feat: dispatch route for the Archivist and an email record for admins"
```

---

### Task 9: Mailpit, integration tests, dashboard, validation loop

**Files:**
- Modify: `docker-compose-integration-test.yaml`, `integration-test.env`
- Create: `tests/integration/utils/mailpit.py`, `tests/integration/test_email_delivery.py`
- Modify: `infrastructure/grafana/dashboards/Business/platform-usage.json`

**Interfaces:**
- Consumes: the routes of Task 8.
- Produces: `Mailpit` helper (`messages_to(address) -> list[dict]`, `message(id) -> dict`) for plan 03's integration tests.

- [ ] **Step 1: Add Mailpit to the integration stack**

`docker-compose-integration-test.yaml` — new service (and add `mailpit_test_integration` to `depends_on` of `gatekeeper_test_integration`):

```yaml
  mailpit_test_integration:
    image: axllent/mailpit:v1.20
    container_name: datamap_mailpit_test_integration
    restart: always
    ports:
      - "8025:8025"
      - "1025:1025"
    networks:
      - gatekeeper_integration-test-network
    healthcheck:
      test: ["CMD", "/mailpit", "readyz"]
      interval: 5s
      timeout: 5s
      retries: 5
```

`integration-test.env` — append:

```
# Email - Mailpit (Internal container communication)
EMAIL_ENABLED=True
EMAIL_FROM_NAME=DataMap
EMAIL_FROM_ADDRESS=no-reply@datamap.test
SMTP_HOST=datamap_mailpit_test_integration
SMTP_PORT=1025
SMTP_STARTTLS=False
SMTP_USERNAME=
SMTP_PASSWORD=
PUBLIC_BASE_URL=http://localhost:3000

# Mailpit HTTP API (External access)
MAILPIT_URL=http://localhost:8025
```

Check the healthcheck inside the container before trusting it (CLAUDE.md: a healthcheck that never passes is worse than none):

Run:
```bash
make ENV_FILE_PATH=integration-test.env integration-test-up
docker exec datamap_mailpit_test_integration /mailpit readyz; echo "exit=$?"
docker inspect --format '{{.State.Health.Status}}' datamap_mailpit_test_integration
```
Expected: `exit=0` and `healthy`.

- [ ] **Step 2: Write the Mailpit helper**

`tests/integration/utils/mailpit.py`:

```python
"""Reads what the gatekeeper sent, from Mailpit's HTTP API."""

import os
import time

import requests

MAILPIT_URL = os.getenv("MAILPIT_URL", "http://localhost:8025")


class Mailpit:
    def __init__(self, base_url: str = MAILPIT_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def messages_to(self, address: str) -> list[dict]:
        response = requests.get(
            f"{self.base_url}/api/v1/search",
            params={"query": f'to:"{address}"'},
            timeout=5,
        )
        response.raise_for_status()
        return response.json().get("messages", [])

    def wait_for(self, address: str, count: int = 1, timeout: float = 10.0) -> list[dict]:
        deadline = time.monotonic() + timeout
        while True:
            found = self.messages_to(address)
            if len(found) >= count or time.monotonic() >= deadline:
                return found
            time.sleep(0.2)

    def message(self, message_id: str) -> dict:
        response = requests.get(f"{self.base_url}/api/v1/message/{message_id}", timeout=5)
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 3: Write the failing integration tests**

`tests/integration/test_email_delivery.py`:

```python
import json
import uuid

import pytest

from tests.integration.test_metrics import _sample, _scrape
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.mailpit import Mailpit


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


@pytest.fixture
def client_headers(valid_headers):
    return {
        "X-Api-Key": valid_headers["X-Api-Key"],
        "X-Api-Secret": valid_headers["X-Api-Secret"],
        "Content-Type": "application/json",
    }


def _recipient() -> str:
    return f"email_test_{uuid.uuid4().hex[:12]}@example.com"


def _queue_test_message(http_client, headers, recipient: str) -> str:
    response = http_client.post(
        "/admin/emails/test", headers=headers, json={"recipient": recipient}
    )
    assert_status_code(response, 202)
    return response.json()["id"]


def _dispatch(http_client, client_headers) -> dict:
    response = http_client.post(
        "/internal/notifications/dispatch", headers=client_headers
    )
    assert_status_code(response, 200)
    return response.json()


class TestEmailDelivery:
    def test_a_queued_message_is_delivered_exactly_once(
        self, http_client, valid_headers, client_headers, mailpit
    ):
        recipient = _recipient()
        _queue_test_message(http_client, valid_headers, recipient)

        first = _dispatch(http_client, client_headers)
        delivered = mailpit.wait_for(recipient)
        _dispatch(http_client, client_headers)

        assert first["sent"] >= 1, first
        assert len(delivered) == 1, delivered
        assert len(mailpit.messages_to(recipient)) == 1
        assert delivered[0]["Subject"] == "DataMap test message"

    def test_the_record_keeps_what_was_sent_but_not_the_secret(
        self, http_client, valid_headers, client_headers, mailpit
    ):
        recipient = _recipient()
        email_id = _queue_test_message(http_client, valid_headers, recipient)

        _dispatch(http_client, client_headers)
        delivered = mailpit.wait_for(recipient)
        body = mailpit.message(delivered[0]["ID"])["Text"]
        record = http_client.get(f"/admin/emails/{email_id}", headers=valid_headers)

        assert_status_code(record, 200)
        detail = record.json()
        code = body.split("Verification code: ")[1].split()[0]
        assert detail["status"] == "sent"
        assert detail["recipient"] == recipient
        assert detail["context"]["code"] == "[masked]"
        assert code not in json.dumps(detail["context"])
        assert code not in detail["body_text"]
        assert "[masked]" in detail["body_text"]
        assert detail["smtp_message_id"].strip("<>") == delivered[0]["MessageID"]
        assert [event["event"] for event in detail["events"]] == ["queued", "sent"]

    def test_a_placeholder_address_is_recorded_and_never_sent(
        self, http_client, valid_headers, client_headers, mailpit
    ):
        recipient = f"orcid_{uuid.uuid4().hex[:12]}@fake.mail.com"
        email_id = _queue_test_message(http_client, valid_headers, recipient)

        _dispatch(http_client, client_headers)
        record = http_client.get(f"/admin/emails/{email_id}", headers=valid_headers)

        assert record.json()["status"] == "skipped"
        assert mailpit.messages_to(recipient) == []

    def test_the_record_can_be_searched_by_recipient(
        self, http_client, valid_headers, client_headers
    ):
        recipient = _recipient()
        email_id = _queue_test_message(http_client, valid_headers, recipient)

        response = http_client.get(
            "/admin/emails/", headers=valid_headers, params={"recipient": recipient.upper()}
        )

        assert_status_code(response, 200)
        assert [item["id"] for item in response.json()["items"]] == [email_id]

    def test_sending_is_counted(self, http_client, valid_headers, client_headers):
        before = _sample(
            _scrape(), "datamap_emails_total", template="notification", outcome="sent"
        )
        _queue_test_message(http_client, valid_headers, _recipient())

        _dispatch(http_client, client_headers)

        after = _sample(
            _scrape(), "datamap_emails_total", template="notification", outcome="sent"
        )
        assert after == before + 1

    def test_the_dispatch_route_refuses_a_caller_without_client_credentials(
        self, http_client
    ):
        response = http_client.post(
            "/internal/notifications/dispatch", headers={"Content-Type": "application/json"}
        )

        assert_status_code(response, 401)
```

- [ ] **Step 4: Make each test fail first**

Before the stack has this branch's image, run against the previous build to see them fail; otherwise temporarily set `EMAIL_ENABLED=False` in `integration-test.env`:

Run: `make ENV_FILE_PATH=integration-test.env integration-test-full` with `EMAIL_ENABLED=False`
Expected: `test_a_queued_message_is_delivered_exactly_once`, `test_the_record_keeps_what_was_sent_but_not_the_secret` and `test_sending_is_counted` FAIL (nothing is sent); `test_a_placeholder_address_is_recorded_and_never_sent` PASSES — skipping does not depend on sending. Restore `EMAIL_ENABLED=True`.

- [ ] **Step 5: Run the full integration suite for real**

Run:
```bash
make ENV_FILE_PATH=integration-test.env integration-test-full
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/
```
`integration-test-full` swallows failures (CLAUDE.md §Verify the run actually ran): read the pytest summary line itself, never a piped exit code. Before the final `down`, confirm the API answered. If Casbin answers 401 right after seeding, poll `GET /api/v1/clients/` with the seeded credentials until it answers 200, then rerun with `make ENV_FILE_PATH=integration-test.env integration-test-run`.
Expected: `tests/integration/test_email_delivery.py` 6 passed; no new failures elsewhere; health check `200`.

- [ ] **Step 6: Add the email panel to the business dashboard**

In `infrastructure/grafana/dashboards/Business/platform-usage.json`, append a row and two panels after the "DOIs" row (next free `id`s; `gridPos.y` below the last panel). Panel targets:

```json
{
  "datasource": {"type": "prometheus", "uid": "prometheus"},
  "expr": "sum by (template, outcome) (increase(datamap_emails_total[$__interval]))",
  "legendFormat": "{{template}} {{outcome}}"
}
```

```json
{
  "datasource": {"type": "prometheus", "uid": "prometheus"},
  "expr": "max(datamap_email_pending)",
  "legendFormat": "pending"
}
```

Use a `timeseries` panel (stacked bars, like panel 39) titled "Email by outcome" and a `stat` panel titled "Email waiting to be sent".

Run: `python -m pytest app/grafana_dashboards_test.py -v`
Expected: PASS (both metrics are declared by `Metrics`).

- [ ] **Step 7: Validation loop (CLAUDE.md)**

Run, in order:
```bash
python -m pytest
make ENV_FILE_PATH=integration-test.env integration-test-full
ruff check
ruff check --fix
ruff format
```
Expected: unit suite passes; integration summary shows no failures; ruff reports `All checks passed!`. Commit any formatting changes.

- [ ] **Step 8: Commit**

```bash
git add docker-compose-integration-test.yaml integration-test.env tests/integration/utils/mailpit.py tests/integration/test_email_delivery.py infrastructure/grafana/dashboards/Business/platform-usage.json
git commit -m "test: email is delivered once, recorded, and masked, against Mailpit"
```

---

## Self-Review

- **Spec coverage:** settings (T1); tables with every audit column and the append-only events (T2); render at enqueue with subject/body as rendered and template version (T1 build commit, T6); secrets masked once the message leaves, in context and body (T6, T7); dedup returning `None` (T4, T6); placeholder `@fake.mail.com` skipped (T6); SMTP with STARTTLS/login (T5); at-most-once — claim in own commit with `SKIP LOCKED`, retry only definite refusals up to 5, uncertain and stale `sending` to `failed` (T4, T5, T7); metrics (T6, T7) and dashboard (T9); logs with `email_id`/`template`/`outcome` only (T6, T7); dispatch route under `/api/v1/internal` with client credentials (T8); admin record routes and the test message, rendered with the existing `notification` template (T7, T8); Mailpit and integration assertions of exactly-once and masking (T9); every message rendered by the existing `EmailTemplateRenderer` and templates from #121, with the plain-text part the RFC requires added to it (T3). Reminders and the embargo templates are plan 03.
- **Deviations from the RFC table, deliberate:** `secret_fields` and `claimed_at` columns; `POST /admin/emails/test`; `BUILD_COMMIT` as the template version source. Recorded in this plan; the RFC can absorb them when plan 03 updates it.
