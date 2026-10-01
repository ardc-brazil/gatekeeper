# Embargo 03 — Gatekeeper: Sharing, Invitations, Reviewer Links and Embargo Notifications

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an author share a dataset with named people (tenancy search, email or ORCID), accept single-use invitations, give a venue an anonymous metadata-only reviewer link with usage counts, and email everyone with access before and when an embargo ends.

**Architecture:** Three new tables (`dataset_invitations`, `dataset_review_links`, `dataset_review_link_views`) behind three repositories. `ShareService` owns grants, invitations and acceptance; `ReviewLinkService` owns reviewer links and the redacted review page; `EmbargoNotificationService` decides which reminder and end-of-embargo messages are due and hands them to plan 01's `EmailService`. Every per-dataset decision goes through plan 02's `DatasetService.fetch_authorized`, which applies `DatasetAccessService`; every permission write goes through plan 02's `PermissionService` (which also grants the `datasets_shared` role and records the audit row); every other audit row goes through plan 02's `EmbargoAudit`. This plan never re-implements the access rule.

**Tech Stack:** Python 3.10 (production image `python:3.10.14-alpine`), FastAPI 0.111, SQLAlchemy 1.4, Alembic, dependency-injector, Casbin, Jinja2 (pinned by plan 01), prometheus-client, pytest + `unittest.mock`, black-box integration tests against the container on `localhost:9094`, Mailpit (added by plan 01).

**Spec:** `docs/rfcs/003-dataset-embargo.md`. **Contracts:** `docs/superpowers/plans/2026-09-30-embargo-00-contracts.md` — when this plan and the contracts disagree, the contracts win.

## Global Constraints

- Routes live under `/api/v1`; paths below omit it. User routes use `Depends(authenticate), Depends(authorize)`; client-only routes use `Depends(authenticate)` only.
- A caller who may not see a dataset gets **404** on every route; a caller who sees it but lacks the right gets **403** (plan 02's `ForbiddenException`).
- Error codes are exactly: `share_target_required`, `share_target_ambiguous`, `invalid_email`, `invalid_orcid`, `already_has_access`, `cannot_share_with_owner`, `invalid_level`, `unknown_user`, `embargo_not_active` (400, via `BadRequestException(errors=[ErrorDetails(code=...)])`); `invitation_already_accepted` (409, via `ConflictException`).
- Tokens: `secrets.token_urlsafe(32)`, stored as `hashlib.sha256(token.encode()).hexdigest()`. A token is returned once, in the response that creates it, and never logged.
- Links: `{PUBLIC_BASE_URL}/invitations/{token}` and `{PUBLIC_BASE_URL}/review/{token}`.
- Redaction allowlist is exactly `SAFE_METADATA_KEYS` from the contracts; everything else is redacted with `"[redacted]"` keeping shape.
- Reviewer views store no IP, user agent or cookie.
- Email is queued **after** the write it announces has committed; a failure to queue is logged and never undoes the write.
- Reminders: offsets `(15, 10, 5, 1)` days, to the owner (if enabled) and every enabled permission holder, `dedup_key = embargo_reminder:<dataset_id>:<embargo_until_iso>:<offset>:<user_id>`; an offset whose moment had already passed when the current `embargo_until` was set is never sent; when several are due at once only the nearest one is sent. End notice: `dedup_key = embargo_ended:<dataset_id>:<embargo_until_iso>:<user_id>`, plus one `expired` row in `dataset_embargo_events`.
- Metrics: `datamap_review_link_views_total{tenancy,outcome}` (`shown`, `redirected`, `not_found`), `datamap_review_links_created_total{tenancy}`. `dataset_id`/`link_id` are never labels.
- Python 3.10 in production: no syntax newer than 3.10.
- Placeholder addresses (`@fake.mail.com`) are passed to `EmailService.enqueue`, which records them as `skipped`; only a person with no email at all is left out.
- When an embargo ended early, the *Embargo ended* message says so, and says why when it was a manual DOI.
- Comments: none narrating code; one line only where a reader would otherwise undo something on purpose (CLAUDE.md).
- Validation loop after the last task: `pytest`, `make ENV_FILE_PATH=integration-test.env integration-test-full` (read the run, do not pipe it), `ruff check`, `ruff check --fix`, `ruff format`.

## Interfaces this plan consumes (from plans 01 and 02)

These names are what plans 01 and 02 must ship. If either plan names them differently, change this plan's imports, not the other plan.

```python
# plan 02 — app/model/embargo.py
class PermissionLevel(str, enum.Enum): READ = "read"; WRITE = "write"
class AccessLevel(str, enum.Enum): OWNER, WRITE, READ, TENANCY
class DatasetAction(enum.Enum): READ_METADATA, READ_FILES, WRITE, DELETE, EXTEND_EMBARGO, MANAGE_EMBARGO
class EmbargoEventType(str, enum.Enum): CREATED, EXTENDED, ENDED_EARLY, EXPIRED, METADATA_MODE_CHANGED,
    PERMISSION_GRANTED, PERMISSION_REVOKED, INVITATION_CREATED, INVITATION_REVOKED,
    REVIEW_LINK_CREATED, REVIEW_LINK_REVOKED
@dataclass class DatasetPermission: dataset_id, user_id, level: PermissionLevel, granted_by, created_at
REDACTED = "[redacted]"; REMINDER_OFFSETS_DAYS = (15, 10, 5, 1); SHARED_ROLE = "datasets_shared"

# plan 02 — app/model/db/embargo.py
class DatasetPermission(Base):        # dataset_permissions: dataset_id, user_id, level (str), granted_by, created_at
class DatasetEmbargoEvent(Base):      # dataset_embargo_events: id, dataset_id, event_type, old_value, new_value, changed_by, note, occurred_at
# plan 02 — app/model/db/dataset.py: Dataset.embargo_until, Dataset.embargo_metadata_visible, Dataset.embargo_note

# plan 02 — app/repository/permission.py (reads only here; writes go through PermissionService)
class PermissionRepository:
    def fetch(self, dataset_id: UUID, user_id: UUID) -> DatasetPermissionDBModel | None
    def list_for_dataset(self, dataset_id: UUID) -> list[DatasetPermissionDBModel]

# plan 02 — app/service/permission.py
class PermissionService:
    def grant(self, dataset_id: UUID, user_id: UUID, level: PermissionLevel, granted_by: UUID | None) -> DatasetPermission
        # upserts, adds the datasets_shared role when missing, records permission_granted (with old_value on a level change);
        # raises NotFoundException when the user does not exist or is disabled
    def revoke(self, dataset_id: UUID, user_id: UUID, revoked_by: UUID | None) -> bool   # False when there was none
    def list_for_dataset(self, dataset_id: UUID) -> list[DatasetPermission]

# plan 02 — app/service/embargo_audit.py
class EmbargoAudit:
    def record(self, dataset_id: UUID, event_type: EmbargoEventType, changed_by: UUID | None,
               old_value: dict | None = None, new_value: dict | None = None, note: str | None = None) -> None

# plan 02 — app/service/dataset.py
DatasetService.fetch_authorized(dataset_id: UUID, user_id: UUID, tenancies: list[str] | None, action: DatasetAction,
                                is_enabled=True, latest_version=False, version_design_state=None,
                                version_is_enabled=True) -> tuple[DatasetDBModel, list[str], AccessLevel]
    # NotFoundException when the caller may not see it; ForbiddenException (403) when they see it but may not do `action`
# Existing: DatasetRepository.fetch(dataset_id=..., restrict_by_tenancy=False) for lookups with no caller.

# plan 02 — ending an embargo early (EmbargoTermination.end, used by POST /embargo/end and by the manual DOI with
#           "end_embargo": true) sets embargo_until to the moment it ended and records ended_early (note "manual DOI"
#           on the DOI path). It notifies nobody: the "Embargo ended" emails and the `expired` row come from this
#           plan's dispatch pass, which also covers an embargo that simply runs out.

# plan 02 — container providers: dataset_service, dataset_repository, permission_repository, permission_service,
#           embargo_audit, user_repository, user_service

# plan 01 — app/service/email.py
class EmailService:
    def enqueue(self, *, template: str, recipient: str, context: dict, secret_fields: frozenset[str] = frozenset(),
                related_type: str | None = None, related_id: UUID | None = None,
                triggered_by: UUID | None = None, dedup_key: str | None = None) -> UUID | None
    def dispatch_due(self, limit: int = 50) -> DispatchResult   # DispatchResult(sent, failed, skipped, retried)
#   enqueue renders at once; a recipient ending in @fake.mail.com is stored with status `skipped` and never sent,
#   so callers pass placeholder addresses through rather than filtering them. DispatchResult(queued, sent, failed, skipped, retried).
# main (#121) + plan 01 — app/service/email_template.py: EmailTemplate (str enum), EmailTemplateRenderer(site_url)
#           .render(EmailTemplate, context) -> RenderedEmail(subject, html, text), StrictUndefined, site_url property.
#           Templates live in app/resources/email_templates/: NAME.html extends "base.html" and imports "_macros.html";
#           an optional NAME.txt extends plan 01's "base.txt" (blocks content, reason). EmailService.enqueue takes the
#           enum value as `template`.
# plan 01 — app/config.py: PUBLIC_BASE_URL, BUILD_COMMIT; container providers: email_service, email_renderer
# plan 01 — app/controller/v1/internal/notification.py: POST /internal/notifications/dispatch,
#           response model NotificationDispatchResponse in app/controller/v1/internal/resource.py
# plan 01 — tests/integration/utils/mailpit.py: Mailpit().messages_to(address) -> list[dict] (keys "ID", "Subject"),
#           Mailpit().wait_for(address, count, timeout) -> list[dict], Mailpit().message(message_id) -> dict (key "Text")
# plan 01 — GET /admin/emails/?recipient=… -> {"items": [...]}; GET /admin/emails/{id} -> {"body_text", "context", "status", ...}
# Production runs Python 3.10 (python:3.10.14-alpine): nothing newer than 3.10 syntax.
```

## File Structure

| File | Responsibility |
|---|---|
| `migrations/versions/2026_09_30_1300-f6a7b8c9d0e1_add_sharing_and_review_links.py` | the three tables |
| `migrations/env.py` | import the new model module |
| `app/model/db/sharing.py` | `DatasetInvitation`, `DatasetReviewLink`, `DatasetReviewLinkView` |
| `app/model/sharing.py` | domain dataclasses returned by services |
| `app/repository/dataset_invitation.py` | invitation persistence, atomic single-use accept |
| `app/repository/dataset_review_link.py` | link persistence, view recording, view aggregates |
| `app/repository/embargo_notification.py` | the two queries the notification pass needs |
| `app/repository/user.py` | `fetch_by_email_insensitive`, `search_share_candidates` |
| `app/service/share_identity.py` | email/ORCID normalisation and ORCID checksum |
| `app/service/share_token.py` | token generation and hashing |
| `app/service/redaction.py` | `SAFE_METADATA_KEYS`, `redact_metadata` |
| `app/service/share.py` | `ShareService` |
| `app/service/review_link.py` | `ReviewLinkService` |
| `app/service/notification.py` | `EmbargoNotificationService` |
| `app/metrics.py` | two reviewer-link counters |
| `app/resources/email_templates/{dataset_invitation,embargo_reminder,embargo_ended}.{html,txt}`, `app/service/email_template.py` | message content in the existing identity; access granted uses the existing `notification` |
| `app/controller/v1/dataset/share_resource.py` | Pydantic request/response models for share and review links |
| `app/controller/v1/dataset/share.py` | share routes |
| `app/controller/v1/dataset/review_link.py` | reviewer-link management routes |
| `app/controller/v1/invitation/invitation.py` | accept and claim (client-only) |
| `app/controller/v1/review/review.py` | `GET /review/{token}` (client-only) |
| `app/controller/v1/internal/notification.py` | call `queue_due` before `dispatch_due` |
| `app/container.py`, `app/setup.py` | wiring and routers |
| `infrastructure/grafana/dashboards/Business/platform-usage.json` | "Reviewer links" row and panel |
| `tests/integration/utils/database.py` | `psql` helper to backdate an event in the test database |
| `tests/integration/test_sharing_api.py`, `test_review_links_api.py`, `test_embargo_notifications.py` | integration tests |

## Task order and parallelism

- **Wave A (parallel):** Task 1, Task 2, Task 3.
- **Wave B (parallel, after A):** Task 4, Task 6, Task 8.
- **Wave C (after B):** Task 5 (after 4), Task 7 (after 6), Task 9 (after 4, 6, 8).
- **Wave D:** Task 10 (after 5, 7, 9), then Task 11 (integration), then Task 12 (validation loop).

---

### Task 1: Tables, models and repositories

**Files:**
- Create: `app/model/db/sharing.py`
- Create: `migrations/versions/2026_09_30_1300-f6a7b8c9d0e1_add_sharing_and_review_links.py`
- Modify: `migrations/env.py` (model imports block, lines 27-33)
- Create: `app/repository/dataset_invitation.py`
- Create: `app/repository/dataset_review_link.py`
- Test: `app/repository/sharing_models_test.py`

**Interfaces:**
- Consumes: `Base` from `app.database`; plan 02 revision `e5f6a7b8c9d0`.
- Produces:
  - `DatasetInvitation(id, dataset_id, email, orcid, level, token_hash, invited_by, accepted_at, accepted_by, revoked_at, created_at)`
  - `DatasetReviewLink(id, dataset_id, token_hash, label, revoked_at, created_by, created_at)`
  - `DatasetReviewLinkView(id, link_id, outcome, viewed_at)`
  - `DatasetInvitationRepository`: `create(invitation) -> DatasetInvitation`, `fetch(dataset_id, invitation_id) -> DatasetInvitation | None`, `fetch_by_token_hash(token_hash) -> DatasetInvitation | None`, `list_for_dataset(dataset_id) -> list[DatasetInvitation]`, `list_pending_for(email: str | None, orcid: str | None) -> list[DatasetInvitation]`, `find_pending(dataset_id, email, orcid) -> DatasetInvitation | None`, `mark_accepted(invitation_id, user_id, at) -> bool`, `revoke(invitation_id, at) -> bool`, `replace_token(invitation_id, token_hash) -> bool`
  - `DatasetReviewLinkRepository`: `create(link) -> DatasetReviewLink`, `fetch(dataset_id, link_id) -> DatasetReviewLink | None`, `fetch_by_token_hash(token_hash) -> DatasetReviewLink | None`, `list_with_views(dataset_id) -> list[tuple[DatasetReviewLink, int, datetime | None, datetime | None]]`, `revoke(link_id, at) -> bool`, `record_view(link_id, outcome) -> None`

- [ ] **Step 1: Write the failing test**

```python
# app/repository/sharing_models_test.py
import unittest

from app.model.db.sharing import (
    DatasetInvitation,
    DatasetReviewLink,
    DatasetReviewLinkView,
)


class TestSharingTables(unittest.TestCase):
    def test_invitation_table_has_the_columns_the_rfc_names(self):
        self.assertEqual(
            set(DatasetInvitation.__table__.columns.keys()),
            {
                "id", "dataset_id", "email", "orcid", "level", "token_hash",
                "invited_by", "accepted_at", "accepted_by", "revoked_at", "created_at",
            },
        )

    def test_review_link_tables_record_no_reviewer_identity(self):
        self.assertEqual(
            set(DatasetReviewLinkView.__table__.columns.keys()),
            {"id", "link_id", "outcome", "viewed_at"},
        )
        self.assertNotIn("expires_at", DatasetReviewLink.__table__.columns.keys())

    def test_tokens_are_unique(self):
        self.assertTrue(DatasetInvitation.__table__.c.token_hash.unique)
        self.assertTrue(DatasetReviewLink.__table__.c.token_hash.unique)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/repository/sharing_models_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.model.db.sharing'`

- [ ] **Step 3: Write the models**

```python
# app/model/db/sharing.py
import sqlalchemy
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class DatasetInvitation(Base):
    __tablename__ = "dataset_invitations"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False)
    email = Column(String(256), nullable=True)
    orcid = Column(String(32), nullable=True)
    level = Column(String(16), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    accepted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "email IS NOT NULL OR orcid IS NOT NULL",
            name="ck_dataset_invitations_target",
        ),
        Index("idx_dataset_invitations_dataset", "dataset_id"),
        Index("idx_dataset_invitations_orcid", "orcid"),
    )


class DatasetReviewLink(Base):
    __tablename__ = "dataset_review_links"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    label = Column(String(256), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_dataset_review_links_dataset", "dataset_id"),)


class DatasetReviewLinkView(Base):
    __tablename__ = "dataset_review_link_views"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    link_id = Column(
        UUID(as_uuid=True), ForeignKey("dataset_review_links.id"), nullable=False
    )
    outcome = Column(String(16), nullable=False)
    viewed_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_dataset_review_link_views_link", "link_id", "viewed_at"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest app/repository/sharing_models_test.py -v`
Expected: 3 passed

- [ ] **Step 5: Write the migration**

The `lower(email)` index is an expression index, which autogenerate skips; it lives only in the migration.

```python
# migrations/versions/2026_09_30_1300-f6a7b8c9d0e1_add_sharing_and_review_links.py
"""Add dataset invitations, reviewer links and their views

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-30 13:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dataset_invitations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datasets.id"),
            nullable=False,
        ),
        sa.Column("email", sa.String(256), nullable=True),
        sa.Column("orcid", sa.String(32), nullable=True),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "invited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "accepted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "email IS NOT NULL OR orcid IS NOT NULL",
            name="ck_dataset_invitations_target",
        ),
    )
    op.create_index(
        "idx_dataset_invitations_dataset", "dataset_invitations", ["dataset_id"]
    )
    op.create_index("idx_dataset_invitations_orcid", "dataset_invitations", ["orcid"])
    op.execute(
        "CREATE INDEX idx_dataset_invitations_email "
        "ON dataset_invitations (lower(email))"
    )

    op.create_table(
        "dataset_review_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datasets.id"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_dataset_review_links_dataset", "dataset_review_links", ["dataset_id"]
    )

    op.create_table(
        "dataset_review_link_views",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "link_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dataset_review_links.id"),
            nullable=False,
        ),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column(
            "viewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_dataset_review_link_views_link",
        "dataset_review_link_views",
        ["link_id", "viewed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_dataset_review_link_views_link", table_name="dataset_review_link_views"
    )
    op.drop_table("dataset_review_link_views")
    op.drop_index("idx_dataset_review_links_dataset", table_name="dataset_review_links")
    op.drop_table("dataset_review_links")
    op.execute("DROP INDEX IF EXISTS idx_dataset_invitations_email")
    op.drop_index("idx_dataset_invitations_orcid", table_name="dataset_invitations")
    op.drop_index("idx_dataset_invitations_dataset", table_name="dataset_invitations")
    op.drop_table("dataset_invitations")
```

Add to `migrations/env.py`, next to the other model imports:

```python
from app.model.db import sharing  # noqa: E402, F401
```

- [ ] **Step 6: Write the repositories**

```python
# app/repository/dataset_invitation.py
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.model.db.sharing import DatasetInvitation


class DatasetInvitationRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def create(self, invitation: DatasetInvitation) -> DatasetInvitation:
        with self._session_factory() as session:
            session.add(invitation)
            session.commit()
            session.refresh(invitation)
            return invitation

    def fetch(self, dataset_id: UUID, invitation_id: UUID) -> DatasetInvitation | None:
        with self._session_factory() as session:
            return (
                session.query(DatasetInvitation)
                .filter_by(id=invitation_id, dataset_id=dataset_id)
                .first()
            )

    def fetch_by_token_hash(self, token_hash: str) -> DatasetInvitation | None:
        with self._session_factory() as session:
            return (
                session.query(DatasetInvitation)
                .filter_by(token_hash=token_hash)
                .first()
            )

    def list_for_dataset(self, dataset_id: UUID) -> list[DatasetInvitation]:
        with self._session_factory() as session:
            return (
                session.query(DatasetInvitation)
                .filter_by(dataset_id=dataset_id)
                .order_by(DatasetInvitation.created_at.desc())
                .all()
            )

    def list_pending_for(
        self, email: str | None, orcid: str | None
    ) -> list[DatasetInvitation]:
        matches = []
        if email:
            matches.append(func.lower(DatasetInvitation.email) == email.lower())
        if orcid:
            matches.append(DatasetInvitation.orcid == orcid)
        if not matches:
            return []
        with self._session_factory() as session:
            return (
                session.query(DatasetInvitation)
                .filter(
                    DatasetInvitation.accepted_at.is_(None),
                    DatasetInvitation.revoked_at.is_(None),
                    or_(*matches),
                )
                .all()
            )

    def find_pending(
        self, dataset_id: UUID, email: str | None, orcid: str | None
    ) -> DatasetInvitation | None:
        return next(
            (
                invitation
                for invitation in self.list_pending_for(email, orcid)
                if invitation.dataset_id == dataset_id
            ),
            None,
        )

    def mark_accepted(self, invitation_id: UUID, user_id: UUID, at: datetime) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(DatasetInvitation)
                .filter(
                    DatasetInvitation.id == invitation_id,
                    DatasetInvitation.accepted_at.is_(None),
                    DatasetInvitation.revoked_at.is_(None),
                )
                .update(
                    {"accepted_at": at, "accepted_by": user_id},
                    synchronize_session=False,
                )
            )
            session.commit()
            return updated == 1

    def revoke(self, invitation_id: UUID, at: datetime) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(DatasetInvitation)
                .filter(
                    DatasetInvitation.id == invitation_id,
                    DatasetInvitation.revoked_at.is_(None),
                )
                .update({"revoked_at": at}, synchronize_session=False)
            )
            session.commit()
            return updated == 1

    def replace_token(self, invitation_id: UUID, token_hash: str) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(DatasetInvitation)
                .filter(
                    DatasetInvitation.id == invitation_id,
                    DatasetInvitation.accepted_at.is_(None),
                    DatasetInvitation.revoked_at.is_(None),
                )
                .update({"token_hash": token_hash}, synchronize_session=False)
            )
            session.commit()
            return updated == 1
```

```python
# app/repository/dataset_review_link.py
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.model.db.sharing import DatasetReviewLink, DatasetReviewLinkView


class DatasetReviewLinkRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def create(self, link: DatasetReviewLink) -> DatasetReviewLink:
        with self._session_factory() as session:
            session.add(link)
            session.commit()
            session.refresh(link)
            return link

    def fetch(self, dataset_id: UUID, link_id: UUID) -> DatasetReviewLink | None:
        with self._session_factory() as session:
            return (
                session.query(DatasetReviewLink)
                .filter_by(id=link_id, dataset_id=dataset_id)
                .first()
            )

    def fetch_by_token_hash(self, token_hash: str) -> DatasetReviewLink | None:
        with self._session_factory() as session:
            return (
                session.query(DatasetReviewLink)
                .filter_by(token_hash=token_hash)
                .first()
            )

    def list_with_views(
        self, dataset_id: UUID
    ) -> list[tuple[DatasetReviewLink, int, datetime | None, datetime | None]]:
        with self._session_factory() as session:
            rows = (
                session.query(
                    DatasetReviewLink,
                    func.count(DatasetReviewLinkView.id),
                    func.min(DatasetReviewLinkView.viewed_at),
                    func.max(DatasetReviewLinkView.viewed_at),
                )
                .outerjoin(
                    DatasetReviewLinkView,
                    DatasetReviewLinkView.link_id == DatasetReviewLink.id,
                )
                .filter(DatasetReviewLink.dataset_id == dataset_id)
                .group_by(DatasetReviewLink.id)
                .order_by(DatasetReviewLink.created_at.desc())
                .all()
            )
            return [(link, count, first, last) for link, count, first, last in rows]

    def revoke(self, link_id: UUID, at: datetime) -> bool:
        with self._session_factory() as session:
            updated = (
                session.query(DatasetReviewLink)
                .filter(
                    DatasetReviewLink.id == link_id,
                    DatasetReviewLink.revoked_at.is_(None),
                )
                .update({"revoked_at": at}, synchronize_session=False)
            )
            session.commit()
            return updated == 1

    def record_view(self, link_id: UUID, outcome: str) -> None:
        with self._session_factory() as session:
            session.add(DatasetReviewLinkView(link_id=link_id, outcome=outcome))
            session.commit()
```

- [ ] **Step 7: Verify the migration chain**

Run: `grep -n "down_revision" migrations/versions/2026_09_30_1300-f6a7b8c9d0e1_add_sharing_and_review_links.py && grep -rn "revision: str = \"e5f6a7b8c9d0\"" migrations/versions/`
Expected: the first line shows `"e5f6a7b8c9d0"`, the second finds plan 02's migration. If plan 02's head has another id, use it.

- [ ] **Step 8: Commit**

```bash
git add app/model/db/sharing.py app/repository/dataset_invitation.py app/repository/dataset_review_link.py app/repository/sharing_models_test.py migrations/env.py migrations/versions/2026_09_30_1300-f6a7b8c9d0e1_add_sharing_and_review_links.py
git commit -m "feat: tables for dataset invitations and reviewer links"
```

---

### Task 2: Identity parsing, tokens and redaction

**Files:**
- Create: `app/service/share_identity.py`, `app/service/share_token.py`, `app/service/redaction.py`
- Test: `app/service/share_identity_test.py`, `app/service/share_token_test.py`, `app/service/redaction_test.py`

**Interfaces:**
- Consumes: `BadRequestException`, `ErrorDetails` (`app/exception/bad_request.py`); `REDACTED` (plan 02).
- Produces: `normalise_email(value: str) -> str`, `normalise_orcid(value: str) -> str`, `orcid_checksum_ok(value: str) -> bool`; `new_token() -> str`, `hash_token(token: str) -> str`; `SAFE_METADATA_KEYS: frozenset[str]`, `redact_metadata(data: dict | None) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
# app/service/share_identity_test.py
import unittest

from app.exception.bad_request import BadRequestException
from app.service.share_identity import (
    normalise_email,
    normalise_orcid,
    orcid_checksum_ok,
)


class TestEmail(unittest.TestCase):
    def test_an_email_is_trimmed_and_lowercased(self):
        self.assertEqual(normalise_email("  Ana.Silva@USP.br "), "ana.silva@usp.br")

    def test_a_value_without_a_domain_is_refused(self):
        with self.assertRaises(BadRequestException) as caught:
            normalise_email("ana.silva")
        self.assertEqual(caught.exception.errors[0].code, "invalid_email")


class TestOrcid(unittest.TestCase):
    def test_the_bare_form_is_accepted(self):
        self.assertEqual(normalise_orcid("0000-0002-1825-0097"), "0000-0002-1825-0097")

    def test_the_url_form_is_reduced_to_the_bare_form(self):
        self.assertEqual(
            normalise_orcid("https://orcid.org/0000-0002-1825-0097"),
            "0000-0002-1825-0097",
        )

    def test_dashes_are_restored_and_a_lowercase_x_is_raised(self):
        self.assertEqual(normalise_orcid("000000021694233x"), "0000-0002-1694-233X")

    def test_a_wrong_check_digit_is_refused(self):
        with self.assertRaises(BadRequestException) as caught:
            normalise_orcid("0000-0002-1825-0098")
        self.assertEqual(caught.exception.errors[0].code, "invalid_orcid")

    def test_a_malformed_value_is_refused(self):
        with self.assertRaises(BadRequestException):
            normalise_orcid("orcid:1234")

    def test_checksum_examples(self):
        self.assertTrue(orcid_checksum_ok("0000-0001-5109-3700"))
        self.assertTrue(orcid_checksum_ok("0000-0002-1694-233X"))
        self.assertFalse(orcid_checksum_ok("0000-0001-5109-3701"))
```

```python
# app/service/share_token_test.py
import hashlib
import unittest

from app.service.share_token import hash_token, new_token


class TestShareToken(unittest.TestCase):
    def test_tokens_are_long_and_distinct(self):
        tokens = {new_token() for _ in range(50)}
        self.assertEqual(len(tokens), 50)
        self.assertTrue(all(len(token) >= 43 for token in tokens))

    def test_the_hash_is_sha256_hex(self):
        self.assertEqual(hash_token("abc"), hashlib.sha256(b"abc").hexdigest())
```

```python
# app/service/redaction_test.py
import unittest

from app.service.redaction import redact_metadata


class TestRedaction(unittest.TestCase):
    def test_authorship_is_redacted_and_keeps_its_shape(self):
        data = {
            "authors": [{"name": "Ana"}, {"name": "Bruno"}, {"name": "Carla"}],
            "owner": {"name": "Ana"},
            "institution": "USP",
            "citation": {"doi": "10.1234/abc"},
            "colaborators": [{"name": "Davi", "permission": "can_view"}],
        }

        redacted = redact_metadata(data)

        self.assertEqual(
            redacted["authors"],
            [{"name": "[redacted]"}, {"name": "[redacted]"}, {"name": "[redacted]"}],
        )
        self.assertEqual(redacted["owner"], {"name": "[redacted]"})
        self.assertEqual(redacted["institution"], "[redacted]")
        self.assertEqual(redacted["citation"], {"doi": "[redacted]"})
        self.assertEqual(
            redacted["colaborators"],
            [{"name": "[redacted]", "permission": "[redacted]"}],
        )

    def test_allowlisted_fields_pass_through(self):
        data = {"description": "Ozone at ATTO", "tags": ["ozone"], "is_enabled": True}
        self.assertEqual(redact_metadata(data), data)

    def test_an_unknown_field_is_redacted(self):
        self.assertEqual(redact_metadata({"pi_name": "Ana"}), {"pi_name": "[redacted]"})

    def test_non_strings_inside_a_redacted_field_are_kept(self):
        self.assertEqual(
            redact_metadata({"project": {"code": "AF", "year": 2026}}),
            {"project": {"code": "[redacted]", "year": 2026}},
        )

    def test_missing_metadata_is_an_empty_dict(self):
        self.assertEqual(redact_metadata(None), {})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/service/share_identity_test.py app/service/share_token_test.py app/service/redaction_test.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# app/service/share_identity.py
import re

from app.exception.bad_request import BadRequestException, ErrorDetails

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ORCID = re.compile(r"^(\d{4})-?(\d{4})-?(\d{4})-?(\d{3}[\dX])$")
_ORCID_PREFIXES = ("https://orcid.org/", "http://orcid.org/", "orcid.org/")


def normalise_email(value: str) -> str:
    email = (value or "").strip().lower()
    if not _EMAIL.match(email):
        raise BadRequestException(errors=[ErrorDetails(code="invalid_email")])
    return email


def orcid_checksum_ok(value: str) -> bool:
    digits = value.replace("-", "")
    total = 0
    for char in digits[:15]:
        total = (total + int(char)) * 2
    result = (12 - total % 11) % 11
    return digits[15] == ("X" if result == 10 else str(result))


def normalise_orcid(value: str) -> str:
    orcid = (value or "").strip()
    for prefix in _ORCID_PREFIXES:
        if orcid.lower().startswith(prefix):
            orcid = orcid[len(prefix) :]
            break
    match = _ORCID.match(orcid.upper())
    if match is None:
        raise BadRequestException(errors=[ErrorDetails(code="invalid_orcid")])
    orcid = "-".join(match.groups())
    if not orcid_checksum_ok(orcid):
        raise BadRequestException(errors=[ErrorDetails(code="invalid_orcid")])
    return orcid
```

```python
# app/service/share_token.py
import hashlib
import secrets


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
```

```python
# app/service/redaction.py
from typing import Any

from app.model.embargo import REDACTED

SAFE_METADATA_KEYS = frozenset(
    {
        "description",
        "tags",
        "level",
        "realm",
        "source",
        "license",
        "category",
        "database",
        "start_date",
        "end_date",
        "creation_date",
        "location",
        "data_type",
        "grid_type",
        "variables",
        "resolution",
        "source_instrument",
        "additional_information",
        "is_enabled",
    }
)


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return REDACTED
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    return value


def redact_metadata(data: dict | None) -> dict:
    if not data:
        return {}
    return {
        key: value if key in SAFE_METADATA_KEYS else _redact(value)
        for key, value in data.items()
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest app/service/share_identity_test.py app/service/share_token_test.py app/service/redaction_test.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add app/service/share_identity.py app/service/share_token.py app/service/redaction.py app/service/share_identity_test.py app/service/share_token_test.py app/service/redaction_test.py
git commit -m "feat: parse emails and ORCIDs, hash share tokens, redact authorship"
```

---

### Task 3: User queries for sharing

**Files:**
- Modify: `app/repository/user.py`
- Test: `app/repository/user_share_query_test.py`

**Interfaces:**
- Produces: `UserRepository.fetch_by_email_insensitive(email: str) -> User | None`; `UserRepository.search_share_candidates(tenancy: str, term: str, exclude_ids: list[UUID], limit: int = 10) -> list[User]`; module function `like_pattern(term: str) -> str`.

- [ ] **Step 1: Write the failing test**

The query itself is exercised by the integration suite (Task 11); the unit test pins the escaping, which is where a `%` typed into the search box would otherwise match everyone.

```python
# app/repository/user_share_query_test.py
import unittest

from app.repository.user import like_pattern


class TestLikePattern(unittest.TestCase):
    def test_the_term_is_wrapped_for_a_contains_match(self):
        self.assertEqual(like_pattern("ana"), "%ana%")

    def test_wildcards_typed_by_the_user_are_escaped(self):
        self.assertEqual(like_pattern("50%_a\\b"), "%50\\%\\_a\\\\b%")

    def test_surrounding_spaces_are_ignored(self):
        self.assertEqual(like_pattern("  ana "), "%ana%")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/repository/user_share_query_test.py -v`
Expected: FAIL with `ImportError: cannot import name 'like_pattern'`

- [ ] **Step 3: Write the implementation**

Add the imports at the top of `app/repository/user.py`:

```python
from sqlalchemy import func, or_
from app.model.db.user import user_tenancy_association
```

Add the module function above the class and the two methods inside `UserRepository`:

```python
def like_pattern(term: str) -> str:
    escaped = (
        term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"
```

```python
    def fetch_by_email_insensitive(self, email: str) -> User | None:
        with self._session_factory() as session:
            return (
                session.query(User)
                .filter(func.lower(User.email) == email.lower(), User.is_enabled == true())
                .first()
            )

    def search_share_candidates(
        self, tenancy: str, term: str, exclude_ids: list[UUID], limit: int = 10
    ) -> List[User]:
        pattern = like_pattern(term)
        with self._session_factory() as session:
            query = (
                session.query(User)
                .join(
                    user_tenancy_association,
                    user_tenancy_association.c.user_id == User.id,
                )
                .filter(
                    user_tenancy_association.c.tenancy == tenancy,
                    User.is_enabled == true(),
                    or_(
                        User.name.ilike(pattern, escape="\\"),
                        User.email.ilike(pattern, escape="\\"),
                    ),
                )
            )
            if exclude_ids:
                query = query.filter(User.id.notin_(exclude_ids))
            return query.order_by(User.name).limit(limit).all()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest app/repository/user_share_query_test.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/repository/user.py app/repository/user_share_query_test.py
git commit -m "feat: find share candidates within a tenancy, and users by email in any case"
```

---

### Task 4: ShareService — state, grants, invitations

**Files:**
- Create: `app/model/sharing.py`
- Create: `app/service/share.py`
- Test: `app/service/share_test.py`

**Interfaces:**
- Consumes: Tasks 1–3; plan 02 `DatasetService.fetch_authorized`, `DatasetAction`, `PermissionRepository` (reads), `PermissionService.grant/revoke`, `EmbargoAudit.record`, `EmbargoEventType`, `PermissionLevel`; `DatasetRepository.fetch`; plan 01 `EmailService.enqueue`.
- Produces (used by Tasks 5, 7):

```python
# app/model/sharing.py
@dataclass
class ShareUser: id: UUID; name: str; email: str | None
@dataclass
class PermissionView: user: ShareUser; level: str; granted_at: datetime; granted_by: UUID | None
@dataclass
class InvitationView: id: UUID; email: str | None; orcid: str | None; level: str; created_at: datetime;
                      accepted_at: datetime | None; accepted_by: ShareUser | None; revoked_at: datetime | None
@dataclass
class ReviewLinkViews: count: int; first_at: datetime | None; last_at: datetime | None
@dataclass
class ReviewLinkView: id: UUID; label: str; created_at: datetime; revoked_at: datetime | None; views: ReviewLinkViews
@dataclass
class ShareState: owner: ShareUser | None; permissions: list[PermissionView]; invitations: list[InvitationView]; review_links: list[ReviewLinkView]
@dataclass
class GrantRequest: level: str; user_id: UUID | None = None; email: str | None = None; orcid: str | None = None
@dataclass
class GrantResult: kind: str; permission: PermissionView | None = None; invitation: InvitationView | None = None; link: str | None = None
@dataclass
class AcceptResult: dataset_id: UUID; level: str
```

```python
# app/service/share.py
class ShareService:
    def candidates(self, dataset_id: UUID, user_id: UUID, term: str) -> list[ShareUser]
    def state(self, dataset_id: UUID, user_id: UUID) -> ShareState
    def grant(self, dataset_id: UUID, user_id: UUID, request: GrantRequest) -> GrantResult
    def update_permission(self, dataset_id: UUID, user_id: UUID, target_user_id: UUID, level: str) -> PermissionView
    def revoke_permission(self, dataset_id: UUID, user_id: UUID, target_user_id: UUID) -> None
    def revoke_invitation(self, dataset_id: UUID, user_id: UUID, invitation_id: UUID) -> None
    def regenerate_link(self, dataset_id: UUID, user_id: UUID, invitation_id: UUID) -> str
```

- [ ] **Step 1: Write the domain dataclasses**

```python
# app/model/sharing.py
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class ShareUser:
    id: UUID
    name: str
    email: str | None = None


@dataclass
class PermissionView:
    user: ShareUser
    level: str
    granted_at: datetime
    granted_by: UUID | None = None


@dataclass
class InvitationView:
    id: UUID
    email: str | None
    orcid: str | None
    level: str
    created_at: datetime
    accepted_at: datetime | None = None
    accepted_by: ShareUser | None = None
    revoked_at: datetime | None = None


@dataclass
class ReviewLinkViews:
    count: int = 0
    first_at: datetime | None = None
    last_at: datetime | None = None


@dataclass
class ReviewLinkView:
    id: UUID
    label: str
    created_at: datetime
    revoked_at: datetime | None = None
    views: ReviewLinkViews = field(default_factory=ReviewLinkViews)


@dataclass
class ShareState:
    owner: ShareUser | None
    permissions: list[PermissionView] = field(default_factory=list)
    invitations: list[InvitationView] = field(default_factory=list)
    review_links: list[ReviewLinkView] = field(default_factory=list)


@dataclass
class GrantRequest:
    level: str
    user_id: UUID | None = None
    email: str | None = None
    orcid: str | None = None


@dataclass
class GrantResult:
    kind: str
    permission: PermissionView | None = None
    invitation: InvitationView | None = None
    link: str | None = None


@dataclass
class AcceptResult:
    dataset_id: UUID
    level: str


@dataclass
class ReviewVersion:
    name: str
    created_at: datetime
    file_count: int
    total_size_bytes: int


@dataclass
class ReviewPage:
    state: str
    dataset_id: UUID
    embargo_until: datetime | None = None
    name: str | None = None
    data: dict = field(default_factory=dict)
    versions: list[ReviewVersion] = field(default_factory=list)
    published: bool = False
```

- [ ] **Step 2: Write the failing tests**

```python
# app/service/share_test.py
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.exception.bad_request import BadRequestException
from app.exception.not_found import NotFoundException
from app.model.embargo import AccessLevel, DatasetAction, EmbargoEventType, PermissionLevel
from app.model.sharing import GrantRequest
from app.repository.dataset import DatasetRepository
from app.repository.dataset_invitation import DatasetInvitationRepository
from app.repository.dataset_review_link import DatasetReviewLinkRepository
from app.repository.permission import PermissionRepository
from app.repository.user import UserRepository
from app.service.dataset import DatasetService
from app.service.email import EmailService
from app.service.embargo_audit import EmbargoAudit
from app.service.permission import PermissionService
from app.service.share import ShareService
from app.service.share_token import hash_token
from app.service.user import UserService

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
OWNER = uuid4()
CALLER = uuid4()


def user_row(user_id=None, name="Ana", email="ana@usp.br"):
    return SimpleNamespace(id=user_id or uuid4(), name=name, email=email, providers=[])


class ShareServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.datasets = Mock(spec=DatasetService)
        self.dataset_repository = Mock(spec=DatasetRepository)
        self.permissions = Mock(spec=PermissionRepository)
        self.permission_service = Mock(spec=PermissionService)
        self.invitations = Mock(spec=DatasetInvitationRepository)
        self.review_links = Mock(spec=DatasetReviewLinkRepository)
        self.users = Mock(spec=UserRepository)
        self.user_service = Mock(spec=UserService)
        self.audit = Mock(spec=EmbargoAudit)
        self.email = Mock(spec=EmailService)
        self.dataset = SimpleNamespace(
            id=uuid4(), name="Ozone at ATTO", owner_id=OWNER, tenancy="datamap/production/data-amazon"
        )
        self.datasets.fetch_authorized.return_value = (self.dataset, [], AccessLevel.OWNER)
        self.dataset_repository.fetch.return_value = self.dataset
        self.permissions.fetch.return_value = None
        self.permissions.list_for_dataset.return_value = []
        self.permission_service.grant.side_effect = (
            lambda dataset_id, user_id, level, granted_by: SimpleNamespace(
                user_id=user_id, level=level, created_at=NOW, granted_by=granted_by
            )
        )
        self.permission_service.revoke.return_value = False
        self.invitations.find_pending.return_value = None
        self.users.fetch_by_id.side_effect = lambda id, is_enabled=True: user_row(id, name="Caller")
        self.service = ShareService(
            dataset_service=self.datasets,
            dataset_repository=self.dataset_repository,
            permission_repository=self.permissions,
            permission_service=self.permission_service,
            invitation_repository=self.invitations,
            review_link_repository=self.review_links,
            user_repository=self.users,
            user_service=self.user_service,
            audit=self.audit,
            email_service=self.email,
            public_base_url="https://datamap.pcs.usp.br",
            clock=lambda: NOW,
        )


class TestGrantTargets(ShareServiceTestCase):
    def test_no_target_is_refused(self):
        with self.assertRaises(BadRequestException) as caught:
            self.service.grant(self.dataset.id, CALLER, GrantRequest(level="read"))
        self.assertEqual(caught.exception.errors[0].code, "share_target_required")

    def test_two_targets_are_refused(self):
        with self.assertRaises(BadRequestException) as caught:
            self.service.grant(
                self.dataset.id,
                CALLER,
                GrantRequest(level="read", email="a@b.co", orcid="0000-0002-1825-0097"),
            )
        self.assertEqual(caught.exception.errors[0].code, "share_target_ambiguous")

    def test_an_unknown_level_is_refused(self):
        with self.assertRaises(BadRequestException) as caught:
            self.service.grant(self.dataset.id, CALLER, GrantRequest(level="admin", email="a@b.co"))
        self.assertEqual(caught.exception.errors[0].code, "invalid_level")

    def test_the_caller_needs_write_access(self):
        self.datasets.fetch_authorized.side_effect = NotFoundException("not_found")
        with self.assertRaises(NotFoundException):
            self.service.grant(self.dataset.id, CALLER, GrantRequest(level="read", email="a@b.co"))
        self.datasets.fetch_authorized.assert_called_once_with(
            dataset_id=self.dataset.id, user_id=CALLER, tenancies=None, action=DatasetAction.WRITE
        )


class TestGrantToAnExistingAccount(ShareServiceTestCase):
    def test_an_email_that_matches_an_account_grants_now(self):
        target = user_row(name="Bruno", email="bruno@inpa.gov.br")
        self.users.fetch_by_email_insensitive.return_value = target

        result = self.service.grant(
            self.dataset.id, CALLER, GrantRequest(level="read", email="Bruno@INPA.gov.br")
        )

        self.assertEqual(result.kind, "permission")
        self.assertEqual(result.permission.level, "read")
        self.users.fetch_by_email_insensitive.assert_called_once_with("bruno@inpa.gov.br")
        self.permission_service.grant.assert_called_once_with(
            self.dataset.id, target.id, PermissionLevel.READ, CALLER
        )
        self.assertEqual(self.email.enqueue.call_args.kwargs["template"], "notification")
        self.assertEqual(
            self.email.enqueue.call_args.kwargs["context"]["cta_url"].rsplit("/", 2)[-2], "datasets"
        )
        self.assertEqual(self.email.enqueue.call_args.kwargs["recipient"], "bruno@inpa.gov.br")

    def test_an_orcid_is_matched_through_the_orcid_provider(self):
        target = user_row(name="Carla", email=None)
        self.users.fetch_by_provider.return_value = target

        self.service.grant(
            self.dataset.id,
            CALLER,
            GrantRequest(level="write", orcid="https://orcid.org/0000-0002-1825-0097"),
        )

        self.users.fetch_by_provider.assert_called_once_with(
            provider_name="orcid", reference="0000-0002-1825-0097"
        )
        self.email.enqueue.assert_not_called()

    def test_the_owner_cannot_be_granted(self):
        self.users.fetch_by_id.side_effect = None
        self.users.fetch_by_id.return_value = user_row(OWNER)
        with self.assertRaises(BadRequestException) as caught:
            self.service.grant(self.dataset.id, CALLER, GrantRequest(level="read", user_id=OWNER))
        self.assertEqual(caught.exception.errors[0].code, "cannot_share_with_owner")

    def test_someone_who_already_has_access_is_refused(self):
        target = user_row()
        self.users.fetch_by_email_insensitive.return_value = target
        self.permissions.fetch.return_value = SimpleNamespace(level="read")
        with self.assertRaises(BadRequestException) as caught:
            self.service.grant(self.dataset.id, CALLER, GrantRequest(level="read", email=target.email))
        self.assertEqual(caught.exception.errors[0].code, "already_has_access")

    def test_an_unknown_user_id_is_refused(self):
        self.users.fetch_by_id.side_effect = None
        self.users.fetch_by_id.return_value = None
        with self.assertRaises(BadRequestException) as caught:
            self.service.grant(self.dataset.id, CALLER, GrantRequest(level="read", user_id=uuid4()))
        self.assertEqual(caught.exception.errors[0].code, "unknown_user")

    def test_a_failure_to_queue_the_email_does_not_undo_the_grant(self):
        target = user_row()
        self.users.fetch_by_email_insensitive.return_value = target
        self.email.enqueue.side_effect = RuntimeError("database gone")

        result = self.service.grant(self.dataset.id, CALLER, GrantRequest(level="read", email=target.email))

        self.assertEqual(result.kind, "permission")


class TestInvitation(ShareServiceTestCase):
    def setUp(self):
        super().setUp()
        self.users.fetch_by_email_insensitive.return_value = None
        self.users.fetch_by_provider.return_value = None
        self.invitations.create.side_effect = lambda invitation: SimpleNamespace(
            id=uuid4(),
            email=invitation.email,
            orcid=invitation.orcid,
            level=invitation.level,
            token_hash=invitation.token_hash,
            created_at=NOW,
            accepted_at=None,
            accepted_by=None,
            revoked_at=None,
        )

    def test_an_unknown_email_becomes_an_invitation_with_a_link_and_an_email(self):
        result = self.service.grant(
            self.dataset.id, CALLER, GrantRequest(level="read", email="dora@ufam.edu.br")
        )

        self.assertEqual(result.kind, "invitation")
        self.assertTrue(result.link.startswith("https://datamap.pcs.usp.br/invitations/"))
        token = result.link.rsplit("/", 1)[1]
        stored = self.invitations.create.call_args.args[0]
        self.assertEqual(stored.token_hash, hash_token(token))
        enqueue = self.email.enqueue.call_args.kwargs
        self.assertEqual(enqueue["template"], "dataset_invitation")
        self.assertEqual(enqueue["recipient"], "dora@ufam.edu.br")
        self.assertEqual(enqueue["secret_fields"], frozenset({"link"}))
        self.assertEqual(enqueue["context"]["link"], result.link)
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"], EmbargoEventType.INVITATION_CREATED
        )

    def test_an_orcid_invitation_sends_no_email(self):
        result = self.service.grant(
            self.dataset.id, CALLER, GrantRequest(level="read", orcid="0000-0002-1825-0097")
        )
        self.assertEqual(result.kind, "invitation")
        self.email.enqueue.assert_not_called()

    def test_a_second_pending_invitation_for_the_same_person_is_refused(self):
        self.invitations.find_pending.return_value = SimpleNamespace(id=uuid4())
        with self.assertRaises(BadRequestException) as caught:
            self.service.grant(self.dataset.id, CALLER, GrantRequest(level="read", email="dora@ufam.edu.br"))
        self.assertEqual(caught.exception.errors[0].code, "already_has_access")


class TestManage(ShareServiceTestCase):
    def test_revoking_a_permission_goes_through_the_permission_service(self):
        self.permission_service.revoke.return_value = True
        target = uuid4()

        self.service.revoke_permission(self.dataset.id, CALLER, target)

        self.permission_service.revoke.assert_called_once_with(self.dataset.id, target, CALLER)

    def test_revoking_a_missing_permission_is_not_found(self):
        with self.assertRaises(NotFoundException):
            self.service.revoke_permission(self.dataset.id, CALLER, uuid4())

    def test_regenerating_a_link_replaces_the_token(self):
        invitation_id = uuid4()
        self.invitations.fetch.return_value = SimpleNamespace(
            id=invitation_id, accepted_at=None, revoked_at=None
        )
        self.invitations.replace_token.return_value = True

        link = self.service.regenerate_link(self.dataset.id, CALLER, invitation_id)

        token = link.rsplit("/", 1)[1]
        self.invitations.replace_token.assert_called_once_with(invitation_id, hash_token(token))

    def test_a_used_invitation_cannot_get_a_new_link(self):
        self.invitations.fetch.return_value = SimpleNamespace(
            id=uuid4(), accepted_at=NOW, revoked_at=None
        )
        with self.assertRaises(NotFoundException):
            self.service.regenerate_link(self.dataset.id, CALLER, uuid4())

    def test_candidates_need_two_characters(self):
        self.assertEqual(self.service.candidates(self.dataset.id, CALLER, "a"), [])
        self.users.search_share_candidates.assert_not_called()

    def test_candidates_exclude_the_owner_and_current_permissions(self):
        holder = uuid4()
        self.permissions.list_for_dataset.return_value = [SimpleNamespace(user_id=holder)]
        self.users.search_share_candidates.return_value = [user_row(name="Ana Lima")]

        found = self.service.candidates(self.dataset.id, CALLER, "ana")

        self.assertEqual([user.name for user in found], ["Ana Lima"])
        self.users.search_share_candidates.assert_called_once_with(
            tenancy=self.dataset.tenancy, term="ana", exclude_ids=[OWNER, holder]
        )
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest app/service/share_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.service.share'`

- [ ] **Step 4: Write the implementation**

```python
# app/service/share.py
import logging
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

from app.exception.bad_request import BadRequestException, ErrorDetails
from app.exception.not_found import NotFoundException
from app.logging_config import fields
from app.model.db.sharing import DatasetInvitation
from app.model.embargo import DatasetAction, EmbargoEventType, PermissionLevel
from app.model.sharing import (
    GrantRequest,
    GrantResult,
    InvitationView,
    PermissionView,
    ReviewLinkView,
    ReviewLinkViews,
    ShareState,
    ShareUser,
)
from app.repository.dataset import DatasetRepository
from app.repository.dataset_invitation import DatasetInvitationRepository
from app.repository.dataset_review_link import DatasetReviewLinkRepository
from app.repository.permission import PermissionRepository
from app.repository.user import UserRepository
from app.service.dataset import DatasetService
from app.service.email import EmailService
from app.service.email_template import EmailTemplate
from app.service.embargo_audit import EmbargoAudit
from app.service.permission import PermissionService
from app.service.share_identity import normalise_email, normalise_orcid
from app.service.share_token import hash_token, new_token
from app.service.user import UserService

PLACEHOLDER_EMAIL_DOMAIN = "@fake.mail.com"


def _bad(code: str) -> BadRequestException:
    return BadRequestException(errors=[ErrorDetails(code=code)])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def deliverable(email: str | None) -> bool:
    return bool(email) and not email.lower().endswith(PLACEHOLDER_EMAIL_DOMAIN)


class ShareService:
    def __init__(
        self,
        dataset_service: DatasetService,
        dataset_repository: DatasetRepository,
        permission_repository: PermissionRepository,
        permission_service: PermissionService,
        invitation_repository: DatasetInvitationRepository,
        review_link_repository: DatasetReviewLinkRepository,
        user_repository: UserRepository,
        user_service: UserService,
        audit: EmbargoAudit,
        email_service: EmailService,
        public_base_url: str,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._datasets = dataset_service
        self._dataset_repository = dataset_repository
        self._permissions = permission_repository
        self._permission_service = permission_service
        self._invitations = invitation_repository
        self._review_links = review_link_repository
        self._users = user_repository
        self._user_service = user_service
        self._audit = audit
        self._email = email_service
        self._base_url = public_base_url.rstrip("/")
        self._clock = clock
        self._logger = logging.getLogger("service:ShareService")

    def invitation_link(self, token: str) -> str:
        return f"{self._base_url}/invitations/{token}"

    def _authorized(self, dataset_id: UUID, user_id: UUID):
        dataset, _, _ = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=None,
            action=DatasetAction.WRITE,
        )
        return dataset

    def _share_user(self, user_id: UUID | None) -> ShareUser | None:
        if user_id is None:
            return None
        user = self._users.fetch_by_id(id=user_id, is_enabled=True)
        if user is None:
            user = self._users.fetch_by_id(id=user_id, is_enabled=False)
        if user is None:
            return None
        return ShareUser(id=user.id, name=user.name, email=user.email)

    def _permission_view(self, permission) -> PermissionView:
        return PermissionView(
            user=self._share_user(permission.user_id),
            level=PermissionLevel(permission.level).value,
            granted_at=permission.created_at,
            granted_by=permission.granted_by,
        )

    def _invitation_view(self, invitation) -> InvitationView:
        return InvitationView(
            id=invitation.id,
            email=invitation.email,
            orcid=invitation.orcid,
            level=invitation.level,
            created_at=invitation.created_at,
            accepted_at=invitation.accepted_at,
            accepted_by=self._share_user(invitation.accepted_by),
            revoked_at=invitation.revoked_at,
        )

    def _queue(self, **kwargs) -> None:
        try:
            self._email.enqueue(**kwargs)
        except Exception:
            self._logger.error(
                "email enqueue failed",
                exc_info=True,
                extra=fields(
                    template=kwargs.get("template"),
                    dataset_id=str(kwargs.get("related_id")),
                ),
            )

    def candidates(self, dataset_id: UUID, user_id: UUID, term: str) -> list[ShareUser]:
        dataset = self._authorized(dataset_id, user_id)
        if len((term or "").strip()) < 2 or not dataset.tenancy:
            return []
        excluded = [dataset.owner_id] + [
            permission.user_id
            for permission in self._permissions.list_for_dataset(dataset.id)
        ]
        users = self._users.search_share_candidates(
            tenancy=dataset.tenancy,
            term=term.strip(),
            exclude_ids=[user for user in excluded if user is not None],
        )
        return [ShareUser(id=user.id, name=user.name, email=user.email) for user in users]

    def state(self, dataset_id: UUID, user_id: UUID) -> ShareState:
        dataset = self._authorized(dataset_id, user_id)
        return ShareState(
            owner=self._share_user(dataset.owner_id),
            permissions=[
                self._permission_view(permission)
                for permission in self._permissions.list_for_dataset(dataset.id)
            ],
            invitations=[
                self._invitation_view(invitation)
                for invitation in self._invitations.list_for_dataset(dataset.id)
            ],
            review_links=[
                ReviewLinkView(
                    id=link.id,
                    label=link.label,
                    created_at=link.created_at,
                    revoked_at=link.revoked_at,
                    views=ReviewLinkViews(count=count, first_at=first, last_at=last),
                )
                for link, count, first, last in self._review_links.list_with_views(
                    dataset.id
                )
            ],
        )

    def grant(self, dataset_id: UUID, user_id: UUID, request: GrantRequest) -> GrantResult:
        targets = [
            value
            for value in (request.user_id, request.email, request.orcid)
            if value not in (None, "")
        ]
        if not targets:
            raise _bad("share_target_required")
        if len(targets) > 1:
            raise _bad("share_target_ambiguous")
        try:
            level = PermissionLevel(request.level)
        except ValueError:
            raise _bad("invalid_level")

        dataset = self._authorized(dataset_id, user_id)

        email = normalise_email(request.email) if request.email else None
        orcid = normalise_orcid(request.orcid) if request.orcid else None
        if request.user_id is not None:
            target = self._users.fetch_by_id(id=request.user_id, is_enabled=True)
            if target is None:
                raise _bad("unknown_user")
        elif email is not None:
            target = self._users.fetch_by_email_insensitive(email)
        else:
            target = self._users.fetch_by_provider(provider_name="orcid", reference=orcid)

        if target is not None:
            return self._grant_to_account(dataset, user_id, target, level)
        return self._invite(dataset, user_id, email, orcid, level)

    def _grant_to_account(self, dataset, user_id: UUID, target, level: PermissionLevel) -> GrantResult:
        if target.id == dataset.owner_id:
            raise _bad("cannot_share_with_owner")
        if self._permissions.fetch(dataset.id, target.id) is not None:
            raise _bad("already_has_access")

        permission = self._permission_service.grant(dataset.id, target.id, level, user_id)
        if target.email:
            granter = self._share_user(user_id)
            self._queue(
                template=EmailTemplate.NOTIFICATION.value,
                recipient=target.email,
                context=self._access_granted_context(
                    dataset, granter.name if granter else None, level
                ),
                related_type="dataset",
                related_id=dataset.id,
                triggered_by=user_id,
            )
        return GrantResult(kind="permission", permission=self._permission_view(permission))

    def _access_granted_context(self, dataset, granter_name: str | None, level: PermissionLevel) -> dict:
        access = "edit" if level is PermissionLevel.WRITE else "read"
        what = f"{access} access to the dataset “{dataset.name}” on DataMap"
        return {
            "title": f"You now have access to “{dataset.name}”",
            "preheader": f"You now have {what}.",
            "actor_name": granter_name or None,
            "message": f"gave you {what}." if granter_name else f"You were given {what}.",
            "details": [
                {"label": "Dataset", "value": dataset.name},
                {"label": "Access", "value": access.capitalize()},
            ],
            "cta_label": "Open dataset",
            "cta_url": f"{self._base_url}/app/datasets/{dataset.id}",
            "reason": "You received this email because someone gave you access to a dataset on DataMap.",
        }

    def _invite(self, dataset, user_id: UUID, email: str | None, orcid: str | None, level: PermissionLevel) -> GrantResult:
        if self._invitations.find_pending(dataset.id, email, orcid) is not None:
            raise _bad("already_has_access")

        token = new_token()
        invitation = self._invitations.create(
            DatasetInvitation(
                dataset_id=dataset.id,
                email=email,
                orcid=orcid,
                level=level.value,
                token_hash=hash_token(token),
                invited_by=user_id,
            )
        )
        link = self.invitation_link(token)
        self._audit.record(
            dataset_id=dataset.id,
            event_type=EmbargoEventType.INVITATION_CREATED,
            changed_by=user_id,
            new_value={"invitation_id": str(invitation.id), "level": level.value},
        )
        if email is not None:
            inviter = self._share_user(user_id)
            self._queue(
                template=EmailTemplate.DATASET_INVITATION.value,
                recipient=email,
                context={
                    "dataset_name": dataset.name,
                    "inviter_name": inviter.name if inviter and inviter.name else "A DataMap user",
                    "level": level.value,
                    "link": link,
                },
                secret_fields=frozenset({"link"}),
                related_type="dataset",
                related_id=dataset.id,
                triggered_by=user_id,
            )
        return GrantResult(
            kind="invitation", invitation=self._invitation_view(invitation), link=link
        )

    def update_permission(
        self, dataset_id: UUID, user_id: UUID, target_user_id: UUID, level: str
    ) -> PermissionView:
        try:
            new_level = PermissionLevel(level)
        except ValueError:
            raise _bad("invalid_level")
        dataset = self._authorized(dataset_id, user_id)
        current = self._permissions.fetch(dataset.id, target_user_id)
        if current is None:
            raise NotFoundException(f"not_found: {target_user_id}")
        permission = self._permission_service.grant(
            dataset.id, target_user_id, new_level, user_id
        )
        return self._permission_view(permission)

    def revoke_permission(self, dataset_id: UUID, user_id: UUID, target_user_id: UUID) -> None:
        dataset = self._authorized(dataset_id, user_id)
        if not self._permission_service.revoke(dataset.id, target_user_id, user_id):
            raise NotFoundException(f"not_found: {target_user_id}")

    def revoke_invitation(self, dataset_id: UUID, user_id: UUID, invitation_id: UUID) -> None:
        dataset = self._authorized(dataset_id, user_id)
        invitation = self._invitations.fetch(dataset.id, invitation_id)
        if invitation is None or invitation.revoked_at is not None:
            raise NotFoundException(f"not_found: {invitation_id}")
        self._invitations.revoke(invitation_id, self._clock())
        self._audit.record(
            dataset_id=dataset.id,
            event_type=EmbargoEventType.INVITATION_REVOKED,
            changed_by=user_id,
            old_value={"invitation_id": str(invitation_id)},
        )

    def regenerate_link(self, dataset_id: UUID, user_id: UUID, invitation_id: UUID) -> str:
        dataset = self._authorized(dataset_id, user_id)
        invitation = self._invitations.fetch(dataset.id, invitation_id)
        if (
            invitation is None
            or invitation.accepted_at is not None
            or invitation.revoked_at is not None
        ):
            raise NotFoundException(f"not_found: {invitation_id}")
        token = new_token()
        if not self._invitations.replace_token(invitation_id, hash_token(token)):
            raise NotFoundException(f"not_found: {invitation_id}")
        return self.invitation_link(token)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest app/service/share_test.py -v`
Expected: all passed (21 tests)

- [ ] **Step 6: Commit**

```bash
git add app/model/sharing.py app/service/share.py app/service/share_test.py
git commit -m "feat: share a dataset with an account, or invite by email or ORCID"
```

---

### Task 5: Accepting and claiming invitations

**Files:**
- Modify: `app/service/share.py` (add `accept`, `claim`, `_accept`)
- Test: `app/service/share_accept_test.py`

**Interfaces:**
- Consumes: Task 4's `ShareService`; `ConflictException`; `UserService.fetch_by_id` (returns domain `User` with `providers: list[UserProvider]`).
- Produces: `ShareService.accept(token: str, user_id: UUID) -> AcceptResult` (404 unknown/revoked, 409 `invitation_already_accepted`); `ShareService.claim(user_id: UUID) -> list[AcceptResult]`.

- [ ] **Step 1: Write the failing tests**

```python
# app/service/share_accept_test.py
from types import SimpleNamespace
from uuid import uuid4

from app.exception.conflict import ConflictException
from app.exception.not_found import NotFoundException
from app.model.embargo import PermissionLevel
from app.model.user import User, UserProvider
from app.service.share_token import hash_token
from app.service.share_test import NOW, OWNER, ShareServiceTestCase


def pending(dataset_id, level="read", email=None, orcid=None):
    return SimpleNamespace(
        id=uuid4(), dataset_id=dataset_id, level=level, email=email, orcid=orcid,
        accepted_at=None, revoked_at=None,
    )


class TestAccept(ShareServiceTestCase):
    def setUp(self):
        super().setUp()
        self.invitee = uuid4()
        self.user_service.fetch_by_id.return_value = User(
            id=self.invitee, name="Dora", email="dora@ufam.edu.br", providers=[]
        )
        self.invitation = pending(self.dataset.id, level="write")
        self.invitations.fetch_by_token_hash.return_value = self.invitation
        self.invitations.mark_accepted.return_value = True

    def test_any_account_that_opens_the_link_gets_the_permission(self):
        result = self.service.accept("the-token", self.invitee)

        self.invitations.fetch_by_token_hash.assert_called_once_with(hash_token("the-token"))
        self.invitations.mark_accepted.assert_called_once_with(self.invitation.id, self.invitee, NOW)
        self.permission_service.grant.assert_called_once_with(
            self.dataset.id, self.invitee, PermissionLevel.WRITE, None
        )
        self.assertEqual(result.dataset_id, self.dataset.id)
        self.assertEqual(result.level, "write")

    def test_an_unknown_token_is_not_found(self):
        self.invitations.fetch_by_token_hash.return_value = None
        with self.assertRaises(NotFoundException):
            self.service.accept("nope", self.invitee)

    def test_a_revoked_invitation_is_not_found(self):
        self.invitation.revoked_at = NOW
        with self.assertRaises(NotFoundException):
            self.service.accept("the-token", self.invitee)

    def test_a_used_invitation_is_a_conflict(self):
        self.invitation.accepted_at = NOW
        with self.assertRaises(ConflictException) as caught:
            self.service.accept("the-token", self.invitee)
        self.assertEqual(str(caught.exception), "invitation_already_accepted")

    def test_losing_the_race_to_accept_is_a_conflict(self):
        self.invitations.mark_accepted.return_value = False
        with self.assertRaises(ConflictException):
            self.service.accept("the-token", self.invitee)
        self.permission_service.grant.assert_not_called()

    def test_an_existing_higher_permission_is_not_lowered(self):
        self.invitation.level = "read"
        self.permissions.fetch.return_value = SimpleNamespace(level="write")

        result = self.service.accept("the-token", self.invitee)

        self.permission_service.grant.assert_not_called()
        self.assertEqual(result.level, "write")

    def test_the_owner_accepting_gets_nothing_new(self):
        self.user_service.fetch_by_id.return_value = User(id=OWNER, name="Owner", providers=[])
        result = self.service.accept("the-token", OWNER)
        self.permission_service.grant.assert_not_called()
        self.assertEqual(result.level, "owner")


class TestClaim(ShareServiceTestCase):
    def test_pending_invitations_matching_email_or_orcid_are_accepted(self):
        user_id = uuid4()
        self.user_service.fetch_by_id.return_value = User(
            id=user_id,
            name="Eva",
            email="Eva@USP.br",
            providers=[UserProvider(name="orcid", reference="0000-0002-1825-0097")],
        )
        first, second = pending(self.dataset.id), pending(self.dataset.id, level="write")
        self.invitations.list_pending_for.return_value = [first, second]
        self.invitations.mark_accepted.return_value = True

        accepted = self.service.claim(user_id)

        self.invitations.list_pending_for.assert_called_once_with(
            "eva@usp.br", "0000-0002-1825-0097"
        )
        self.assertEqual(len(accepted), 2)

    def test_a_placeholder_email_is_not_matched(self):
        user_id = uuid4()
        self.user_service.fetch_by_id.return_value = User(
            id=user_id, name="Eva", email="eva@fake.mail.com", providers=[]
        )
        self.invitations.list_pending_for.return_value = []

        self.assertEqual(self.service.claim(user_id), [])
        self.invitations.list_pending_for.assert_called_once_with(None, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/service/share_accept_test.py -v`
Expected: FAIL with `AttributeError: 'ShareService' object has no attribute 'accept'`

- [ ] **Step 3: Write the implementation**

Add to the imports of `app/service/share.py`:

```python
from app.exception.conflict import ConflictException
from app.model.sharing import AcceptResult
```

Add to `ShareService`:

```python
    def accept(self, token: str, user_id: UUID) -> AcceptResult:
        invitation = self._invitations.fetch_by_token_hash(hash_token(token))
        if invitation is None or invitation.revoked_at is not None:
            raise NotFoundException("invitation_not_found")
        if invitation.accepted_at is not None:
            raise ConflictException("invitation_already_accepted")
        user = self._user_service.fetch_by_id(user_id)
        result = self._accept(invitation, user.id)
        if result is None:
            raise ConflictException("invitation_already_accepted")
        return result

    def claim(self, user_id: UUID) -> list[AcceptResult]:
        user = self._user_service.fetch_by_id(user_id)
        email = user.email.lower() if deliverable(user.email) else None
        orcid = next(
            (
                provider.reference
                for provider in (user.providers or [])
                if provider.name == "orcid"
            ),
            None,
        )
        accepted = []
        for invitation in self._invitations.list_pending_for(email, orcid):
            result = self._accept(invitation, user.id)
            if result is not None:
                accepted.append(result)
        return accepted

    def _accept(self, invitation, user_id: UUID) -> AcceptResult | None:
        if not self._invitations.mark_accepted(invitation.id, user_id, self._clock()):
            return None
        dataset = self._dataset_repository.fetch(
            dataset_id=invitation.dataset_id, restrict_by_tenancy=False
        )
        if dataset is None:
            raise NotFoundException(f"not_found: {invitation.dataset_id}")
        if dataset.owner_id == user_id:
            return AcceptResult(dataset_id=invitation.dataset_id, level="owner")

        current = self._permissions.fetch(invitation.dataset_id, user_id)
        if current is not None and (
            current.level == PermissionLevel.WRITE.value
            or current.level == invitation.level
        ):
            return AcceptResult(dataset_id=invitation.dataset_id, level=current.level)

        self._permission_service.grant(
            invitation.dataset_id,
            user_id,
            PermissionLevel(invitation.level),
            getattr(invitation, "invited_by", None),
        )
        return AcceptResult(dataset_id=invitation.dataset_id, level=invitation.level)
```

`_accept` has no caller to check access against: the token is the authorization. It reads the dataset with `DatasetRepository.fetch(dataset_id=..., restrict_by_tenancy=False)` only to compare the owner, and the permission, the `datasets_shared` role and the `permission_granted` row all come from `PermissionService.grant`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest app/service/share_accept_test.py app/service/share_test.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add app/service/share.py app/service/share_accept_test.py app/service/share_test.py
git commit -m "feat: accept an invitation once, and claim pending ones on login"
```

---

### Task 6: ReviewLinkService and its metrics

**Files:**
- Create: `app/service/review_link.py`
- Modify: `app/metrics.py` (two counters in `Metrics.__init__`, two methods)
- Test: `app/service/review_link_test.py`, `app/metrics_test.py` (add a class)

**Interfaces:**
- Consumes: Tasks 1, 2, 4 (`ReviewPage`, `ReviewVersion`, `ReviewLinkView`); plan 02 `DatasetService.fetch_authorized`, `DatasetAction`, `EmbargoAudit.record`, `EmbargoEventType`; `DatasetRepository.fetch(dataset_id, restrict_by_tenancy=False)`; `VisibilityStatus`.
- Produces: `ReviewLinkService.create(dataset_id, user_id, label) -> tuple[ReviewLinkView, str]`, `ReviewLinkService.revoke(dataset_id, user_id, link_id) -> None`, `ReviewLinkService.view(token: str) -> ReviewPage`; `metrics.review_link_viewed(tenancy: str | None, outcome: str)`, `metrics.review_link_created(tenancy: str | None)`.

- [ ] **Step 1: Write the failing metrics test**

Append to `app/metrics_test.py`:

```python
class TestReviewLinks(MetricsTestCase):
    def test_views_are_counted_by_outcome_and_tenancy(self):
        self.metrics.review_link_viewed("datamap/production/data-amazon", "shown")
        self.metrics.review_link_viewed(None, "not_found")

        self.assertEqual(
            self.value(
                "datamap_review_link_views_total",
                tenancy="datamap/production/data-amazon",
                outcome="shown",
            ),
            1.0,
        )
        self.assertEqual(
            self.value("datamap_review_link_views_total", tenancy="none", outcome="not_found"),
            1.0,
        )

    def test_created_links_are_counted_by_tenancy(self):
        self.metrics.review_link_created("datamap/production/data-amazon")
        self.assertEqual(
            self.value(
                "datamap_review_links_created_total",
                tenancy="datamap/production/data-amazon",
            ),
            1.0,
        )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest app/metrics_test.py::TestReviewLinks -v`
Expected: FAIL with `AttributeError: 'Metrics' object has no attribute 'review_link_viewed'`

- [ ] **Step 3: Add the counters**

In `Metrics.__init__` of `app/metrics.py`, after `self._snapshots`:

```python
        self._review_link_views = Counter(
            "datamap_review_link_views_total",
            "Reviewer link pages served",
            ["tenancy", "outcome"],
            registry=self.registry,
        )
        self._review_links_created = Counter(
            "datamap_review_links_created_total",
            "Reviewer links created",
            ["tenancy"],
            registry=self.registry,
        )
```

After `snapshot_published`:

```python
    def review_link_viewed(self, tenancy: str | None, outcome: str) -> None:
        self._review_link_views.labels(tenancy=tenancy or "none", outcome=outcome).inc()

    def review_link_created(self, tenancy: str | None) -> None:
        self._review_links_created.labels(tenancy=tenancy or "none").inc()
```

Run: `pytest app/metrics_test.py::TestReviewLinks -v` — Expected: 2 passed

- [ ] **Step 4: Write the failing service tests**

```python
# app/service/review_link_test.py
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from prometheus_client import REGISTRY

from app.exception.bad_request import BadRequestException
from app.exception.not_found import NotFoundException
from app.model.dataset import VisibilityStatus
from app.model.embargo import AccessLevel, DatasetAction, EmbargoEventType
from app.repository.dataset import DatasetRepository
from app.repository.dataset_review_link import DatasetReviewLinkRepository
from app.service.dataset import DatasetService
from app.service.embargo_audit import EmbargoAudit
from app.service.review_link import ReviewLinkService
from app.service.share_token import hash_token

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
TENANCY = "datamap/production/data-amazon"


def _sample(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


def dataset(until=NOW + timedelta(days=30), visibility=VisibilityStatus.PRIVATE):
    files = [SimpleNamespace(size_bytes=10), SimpleNamespace(size_bytes=32)]
    return SimpleNamespace(
        id=uuid4(),
        name="Ozone at ATTO",
        tenancy=TENANCY,
        embargo_until=until,
        visibility=visibility,
        data={"description": "Ozone", "authors": [{"name": "Ana"}]},
        versions=[
            SimpleNamespace(name="1", created_at=NOW, is_enabled=True, files_in=files),
            SimpleNamespace(name="0", created_at=NOW, is_enabled=False, files_in=[]),
        ],
    )


class ReviewLinkTestCase(unittest.TestCase):
    def setUp(self):
        self.dataset_service = Mock(spec=DatasetService)
        self.links = Mock(spec=DatasetReviewLinkRepository)
        self.datasets = Mock(spec=DatasetRepository)
        self.audit = Mock(spec=EmbargoAudit)
        self.dataset = dataset()
        self.dataset_service.fetch_authorized.return_value = (self.dataset, [], AccessLevel.OWNER)
        self.datasets.fetch.return_value = self.dataset
        self.links.create.side_effect = lambda link: SimpleNamespace(
            id=uuid4(), label=link.label, created_at=NOW, revoked_at=None, token_hash=link.token_hash
        )
        self.service = ReviewLinkService(
            dataset_service=self.dataset_service,
            review_link_repository=self.links,
            dataset_repository=self.datasets,
            audit=self.audit,
            public_base_url="https://datamap.pcs.usp.br/",
            clock=lambda: NOW,
        )


class TestCreate(ReviewLinkTestCase):
    def test_a_link_is_created_while_the_embargo_lasts(self):
        before = _sample("datamap_review_links_created_total", tenancy=TENANCY)

        view, link = self.service.create(self.dataset.id, uuid4(), "JGR, round 1")

        self.assertEqual(
            self.dataset_service.fetch_authorized.call_args.kwargs["action"], DatasetAction.WRITE
        )
        self.assertTrue(link.startswith("https://datamap.pcs.usp.br/review/"))
        token = link.rsplit("/", 1)[1]
        self.assertEqual(self.links.create.call_args.args[0].token_hash, hash_token(token))
        self.assertEqual(view.label, "JGR, round 1")
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"], EmbargoEventType.REVIEW_LINK_CREATED
        )
        self.assertEqual(_sample("datamap_review_links_created_total", tenancy=TENANCY) - before, 1.0)

    def test_no_link_without_an_active_embargo(self):
        self.dataset_service.fetch_authorized.return_value = (
            dataset(until=NOW - timedelta(seconds=1)),
            [],
            AccessLevel.OWNER,
        )
        with self.assertRaises(BadRequestException) as caught:
            self.service.create(self.dataset.id, uuid4(), "JGR")
        self.assertEqual(caught.exception.errors[0].code, "embargo_not_active")


class TestView(ReviewLinkTestCase):
    def setUp(self):
        super().setUp()
        self.link = SimpleNamespace(id=uuid4(), dataset_id=self.dataset.id, revoked_at=None)
        self.links.fetch_by_token_hash.return_value = self.link

    def test_an_active_embargo_shows_redacted_metadata_and_counts_only(self):
        before = _sample("datamap_review_link_views_total", tenancy=TENANCY, outcome="shown")

        page = self.service.view("tok")

        self.links.fetch_by_token_hash.assert_called_once_with(hash_token("tok"))
        self.assertEqual(page.state, "active")
        self.assertEqual(page.data["authors"], [{"name": "[redacted]"}])
        self.assertEqual(page.data["description"], "Ozone")
        self.assertEqual(len(page.versions), 1)
        self.assertEqual(page.versions[0].file_count, 2)
        self.assertEqual(page.versions[0].total_size_bytes, 42)
        self.links.record_view.assert_called_once_with(self.link.id, "shown")
        self.assertEqual(
            _sample("datamap_review_link_views_total", tenancy=TENANCY, outcome="shown") - before, 1.0
        )

    def test_an_ended_embargo_reports_whether_the_dataset_was_published(self):
        self.datasets.fetch.return_value = dataset(
            until=NOW - timedelta(days=1), visibility=VisibilityStatus.PUBLIC
        )

        page = self.service.view("tok")

        self.assertEqual(page.state, "ended")
        self.assertTrue(page.published)
        self.assertEqual(page.data, {})
        self.links.record_view.assert_called_once_with(self.link.id, "redirected")

    def test_a_revoked_link_is_not_found(self):
        self.link.revoked_at = NOW
        before = _sample("datamap_review_link_views_total", tenancy="none", outcome="not_found")
        with self.assertRaises(NotFoundException):
            self.service.view("tok")
        self.links.record_view.assert_not_called()
        self.assertEqual(
            _sample("datamap_review_link_views_total", tenancy="none", outcome="not_found") - before, 1.0
        )

    def test_an_unknown_token_is_not_found(self):
        self.links.fetch_by_token_hash.return_value = None
        with self.assertRaises(NotFoundException):
            self.service.view("tok")


class TestRevoke(ReviewLinkTestCase):
    def test_revoking_records_the_event(self):
        link_id = uuid4()
        self.links.fetch.return_value = SimpleNamespace(id=link_id, revoked_at=None)

        self.service.revoke(self.dataset.id, uuid4(), link_id)

        self.links.revoke.assert_called_once_with(link_id, NOW)
        self.assertEqual(
            self.audit.record.call_args.kwargs["event_type"], EmbargoEventType.REVIEW_LINK_REVOKED
        )

    def test_revoking_an_unknown_link_is_not_found(self):
        self.links.fetch.return_value = None
        with self.assertRaises(NotFoundException):
            self.service.revoke(self.dataset.id, uuid4(), uuid4())
```

- [ ] **Step 5: Run them to verify they fail**

Run: `pytest app/service/review_link_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.service.review_link'`

- [ ] **Step 6: Write the implementation**

```python
# app/service/review_link.py
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

from app.exception.bad_request import BadRequestException, ErrorDetails
from app.exception.not_found import NotFoundException
from app.metrics import metrics
from app.model.dataset import VisibilityStatus
from app.model.db.sharing import DatasetReviewLink
from app.model.sharing import ReviewLinkView, ReviewPage, ReviewVersion
from app.model.embargo import DatasetAction, EmbargoEventType
from app.repository.dataset import DatasetRepository
from app.repository.dataset_review_link import DatasetReviewLinkRepository
from app.service.dataset import DatasetService
from app.service.embargo_audit import EmbargoAudit
from app.service.redaction import redact_metadata
from app.service.share_token import hash_token, new_token


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReviewLinkService:
    def __init__(
        self,
        dataset_service: DatasetService,
        review_link_repository: DatasetReviewLinkRepository,
        dataset_repository: DatasetRepository,
        audit: EmbargoAudit,
        public_base_url: str,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._dataset_service = dataset_service
        self._links = review_link_repository
        self._datasets = dataset_repository
        self._audit = audit
        self._base_url = public_base_url.rstrip("/")
        self._clock = clock

    def _embargo_active(self, dataset) -> bool:
        return dataset.embargo_until is not None and dataset.embargo_until > self._clock()

    def _authorized(self, dataset_id: UUID, user_id: UUID):
        dataset, _, _ = self._dataset_service.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=None,
            action=DatasetAction.WRITE,
        )
        return dataset

    def create(self, dataset_id: UUID, user_id: UUID, label: str) -> tuple[ReviewLinkView, str]:
        dataset = self._authorized(dataset_id, user_id)
        if not self._embargo_active(dataset):
            raise BadRequestException(errors=[ErrorDetails(code="embargo_not_active")])

        token = new_token()
        link = self._links.create(
            DatasetReviewLink(
                dataset_id=dataset.id,
                token_hash=hash_token(token),
                label=label.strip(),
                created_by=user_id,
            )
        )
        self._audit.record(
            dataset_id=dataset.id,
            event_type=EmbargoEventType.REVIEW_LINK_CREATED,
            changed_by=user_id,
            new_value={"link_id": str(link.id), "label": link.label},
        )
        metrics.review_link_created(dataset.tenancy)
        view = ReviewLinkView(
            id=link.id, label=link.label, created_at=link.created_at, revoked_at=None
        )
        return view, f"{self._base_url}/review/{token}"

    def revoke(self, dataset_id: UUID, user_id: UUID, link_id: UUID) -> None:
        dataset = self._authorized(dataset_id, user_id)
        link = self._links.fetch(dataset.id, link_id)
        if link is None or link.revoked_at is not None:
            raise NotFoundException(f"not_found: {link_id}")
        self._links.revoke(link_id, self._clock())
        self._audit.record(
            dataset_id=dataset.id,
            event_type=EmbargoEventType.REVIEW_LINK_REVOKED,
            changed_by=user_id,
            old_value={"link_id": str(link_id)},
        )

    def view(self, token: str) -> ReviewPage:
        link = self._links.fetch_by_token_hash(hash_token(token))
        dataset = None
        if link is not None and link.revoked_at is None:
            dataset = self._datasets.fetch(
                dataset_id=link.dataset_id, restrict_by_tenancy=False
            )
        if dataset is None:
            metrics.review_link_viewed(None, "not_found")
            raise NotFoundException("review_link_not_found")

        if not self._embargo_active(dataset):
            self._links.record_view(link.id, "redirected")
            metrics.review_link_viewed(dataset.tenancy, "redirected")
            return ReviewPage(
                state="ended",
                dataset_id=dataset.id,
                published=dataset.visibility == VisibilityStatus.PUBLIC,
            )

        self._links.record_view(link.id, "shown")
        metrics.review_link_viewed(dataset.tenancy, "shown")
        return ReviewPage(
            state="active",
            dataset_id=dataset.id,
            embargo_until=dataset.embargo_until,
            name=dataset.name,
            data=redact_metadata(dataset.data),
            versions=[
                ReviewVersion(
                    name=version.name,
                    created_at=version.created_at,
                    file_count=len(version.files_in),
                    total_size_bytes=sum(file.size_bytes or 0 for file in version.files_in),
                )
                for version in dataset.versions
                if version.is_enabled
            ],
        )
```

The dataset name is shown: a title describes the data, not who produced it. If a reviewer flags a title as identifying, that is a decision for the RFC, not for this code.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest app/service/review_link_test.py app/metrics_test.py -v`
Expected: all passed

- [ ] **Step 8: Commit**

```bash
git add app/service/review_link.py app/service/review_link_test.py app/metrics.py app/metrics_test.py
git commit -m "feat: reviewer links that show redacted metadata and count their views"
```

---

### Task 7: Routes, resources, wiring

**Files:**
- Create: `app/controller/v1/dataset/share_resource.py`
- Create: `app/controller/v1/dataset/share.py`
- Create: `app/controller/v1/dataset/review_link.py`
- Create: `app/controller/v1/invitation/__init__.py` (empty), `app/controller/v1/invitation/invitation.py`
- Create: `app/controller/v1/review/__init__.py` (empty), `app/controller/v1/review/review.py`
- Modify: `app/container.py` (imports, wiring list, providers), `app/setup.py` (imports, `setup_routes`)
- Test: `app/controller/v1/dataset/share_resource_test.py`; `app/controller/routes_security_test.py` stays green unchanged

**Interfaces:**
- Consumes: Tasks 4–6; plan 02's `parse_user_header` usage pattern and `ForbiddenException` handler; plan 01's `PUBLIC_BASE_URL`.
- Produces: the routes in the contracts' *Sharing* and *Reviewer links* sections, with exactly those JSON shapes.

- [ ] **Step 1: Write the failing adapter test**

```python
# app/controller/v1/dataset/share_resource_test.py
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.controller.v1.dataset.share_resource import (
    adapt_grant_result,
    adapt_review_page,
)
from app.model.sharing import (
    GrantResult,
    InvitationView,
    ReviewPage,
    ReviewVersion,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class TestAdapters(unittest.TestCase):
    def test_an_invitation_result_carries_its_link(self):
        invitation = InvitationView(
            id=uuid4(), email="dora@ufam.edu.br", orcid=None, level="read", created_at=NOW
        )
        body = adapt_grant_result(
            GrantResult(kind="invitation", invitation=invitation, link="https://x/invitations/t")
        ).model_dump(mode="json", exclude_none=True)

        self.assertEqual(body["kind"], "invitation")
        self.assertEqual(body["link"], "https://x/invitations/t")
        self.assertEqual(body["invitation"]["email"], "dora@ufam.edu.br")
        self.assertNotIn("permission", body)

    def test_an_active_review_page_has_versions_with_file_summaries(self):
        page = ReviewPage(
            state="active",
            dataset_id=uuid4(),
            embargo_until=NOW,
            name="Ozone",
            data={"authors": [{"name": "[redacted]"}]},
            versions=[ReviewVersion(name="1", created_at=NOW, file_count=2, total_size_bytes=42)],
        )
        body = adapt_review_page(page)

        self.assertEqual(body["state"], "active")
        self.assertEqual(body["dataset"]["name"], "Ozone")
        self.assertEqual(
            body["dataset"]["versions"][0]["files_summary"],
            {"count": 2, "total_size_bytes": 42},
        )
        self.assertNotIn("dataset_id", body)

    def test_an_ended_review_page_says_only_where_to_go(self):
        dataset_id = uuid4()
        body = adapt_review_page(ReviewPage(state="ended", dataset_id=dataset_id, published=True))
        self.assertEqual(body, {"state": "ended", "dataset_id": str(dataset_id), "published": True})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest app/controller/v1/dataset/share_resource_test.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the resources**

```python
# app/controller/v1/dataset/share_resource.py
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.model.sharing import (
    GrantResult,
    InvitationView,
    PermissionView,
    ReviewLinkView,
    ReviewPage,
    ShareState,
    ShareUser,
)


class ShareUserResponse(BaseModel):
    id: UUID
    name: str
    email: str | None = None


class PermissionResponse(BaseModel):
    user: ShareUserResponse | None
    level: str
    granted_at: datetime
    granted_by: UUID | None = None


class InvitationResponse(BaseModel):
    id: UUID
    email: str | None = None
    orcid: str | None = None
    level: str
    created_at: datetime
    accepted_at: datetime | None = None
    accepted_by: ShareUserResponse | None = None
    revoked_at: datetime | None = None


class ReviewLinkViewsResponse(BaseModel):
    count: int
    first_at: datetime | None = None
    last_at: datetime | None = None


class ReviewLinkResponse(BaseModel):
    id: UUID
    label: str
    created_at: datetime
    revoked_at: datetime | None = None
    views: ReviewLinkViewsResponse
    link: str | None = None


class ShareStateResponse(BaseModel):
    owner: ShareUserResponse | None
    permissions: list[PermissionResponse]
    invitations: list[InvitationResponse]
    review_links: list[ReviewLinkResponse]


class GrantRequestBody(BaseModel):
    level: str
    user_id: UUID | None = None
    email: str | None = None
    orcid: str | None = None


class GrantResultResponse(BaseModel):
    kind: Literal["permission", "invitation"]
    permission: PermissionResponse | None = None
    invitation: InvitationResponse | None = None
    link: str | None = None


class UpdatePermissionBody(BaseModel):
    level: str


class LinkResponse(BaseModel):
    link: str


class CreateReviewLinkBody(BaseModel):
    label: str = Field(..., min_length=1, max_length=256)


class AcceptInvitationBody(BaseModel):
    token: str = Field(..., min_length=1)


class AcceptResultResponse(BaseModel):
    dataset_id: UUID
    level: str


class ClaimResponse(BaseModel):
    accepted: list[AcceptResultResponse]


def adapt_user(user: ShareUser | None) -> ShareUserResponse | None:
    if user is None:
        return None
    return ShareUserResponse(id=user.id, name=user.name, email=user.email)


def adapt_permission(permission: PermissionView) -> PermissionResponse:
    return PermissionResponse(
        user=adapt_user(permission.user),
        level=permission.level,
        granted_at=permission.granted_at,
        granted_by=permission.granted_by,
    )


def adapt_invitation(invitation: InvitationView) -> InvitationResponse:
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        orcid=invitation.orcid,
        level=invitation.level,
        created_at=invitation.created_at,
        accepted_at=invitation.accepted_at,
        accepted_by=adapt_user(invitation.accepted_by),
        revoked_at=invitation.revoked_at,
    )


def adapt_review_link(link: ReviewLinkView, url: str | None = None) -> ReviewLinkResponse:
    return ReviewLinkResponse(
        id=link.id,
        label=link.label,
        created_at=link.created_at,
        revoked_at=link.revoked_at,
        views=ReviewLinkViewsResponse(
            count=link.views.count,
            first_at=link.views.first_at,
            last_at=link.views.last_at,
        ),
        link=url,
    )


def adapt_share_state(state: ShareState) -> ShareStateResponse:
    return ShareStateResponse(
        owner=adapt_user(state.owner),
        permissions=[adapt_permission(p) for p in state.permissions],
        invitations=[adapt_invitation(i) for i in state.invitations],
        review_links=[adapt_review_link(link) for link in state.review_links],
    )


def adapt_grant_result(result: GrantResult) -> GrantResultResponse:
    return GrantResultResponse(
        kind=result.kind,
        permission=adapt_permission(result.permission) if result.permission else None,
        invitation=adapt_invitation(result.invitation) if result.invitation else None,
        link=result.link,
    )


def adapt_review_page(page: ReviewPage) -> dict:
    if page.state == "ended":
        return {
            "state": "ended",
            "dataset_id": str(page.dataset_id),
            "published": page.published,
        }
    return {
        "state": "active",
        "embargo_until": page.embargo_until.isoformat() if page.embargo_until else None,
        "dataset": {
            "name": page.name,
            "data": page.data,
            "versions": [
                {
                    "name": version.name,
                    "created_at": version.created_at.isoformat(),
                    "files_summary": {
                        "count": version.file_count,
                        "total_size_bytes": version.total_size_bytes,
                    },
                }
                for version in page.versions
            ],
        },
    }
```

- [ ] **Step 4: Write the routers**

```python
# app/controller/v1/dataset/share.py
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.dataset.share_resource import (
    GrantRequestBody,
    GrantResultResponse,
    LinkResponse,
    PermissionResponse,
    ShareStateResponse,
    ShareUserResponse,
    UpdatePermissionBody,
    adapt_grant_result,
    adapt_permission,
    adapt_share_state,
    adapt_user,
)
from app.model.sharing import GrantRequest
from app.service.share import ShareService

router = APIRouter(
    prefix="/datasets",
    tags=["sharing"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


@router.get("/{dataset_id}/share/candidates", response_model=list[ShareUserResponse])
@inject
def share_candidates(
    dataset_id: UUID,
    q: str = "",
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> list[ShareUserResponse]:
    return [adapt_user(user) for user in service.candidates(dataset_id, user_id, q)]


@router.get("/{dataset_id}/share", response_model=ShareStateResponse)
@inject
def share_state(
    dataset_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> ShareStateResponse:
    return adapt_share_state(service.state(dataset_id, user_id))


@router.post(
    "/{dataset_id}/share",
    status_code=201,
    response_model=GrantResultResponse,
    response_model_exclude_none=True,
)
@inject
def grant(
    dataset_id: UUID,
    body: GrantRequestBody,
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> GrantResultResponse:
    result = service.grant(
        dataset_id,
        user_id,
        GrantRequest(
            level=body.level, user_id=body.user_id, email=body.email, orcid=body.orcid
        ),
    )
    return adapt_grant_result(result)


@router.put(
    "/{dataset_id}/share/permissions/{target_user_id}", response_model=PermissionResponse
)
@inject
def update_permission(
    dataset_id: UUID,
    target_user_id: UUID,
    body: UpdatePermissionBody,
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> PermissionResponse:
    return adapt_permission(
        service.update_permission(dataset_id, user_id, target_user_id, body.level)
    )


@router.delete("/{dataset_id}/share/permissions/{target_user_id}", status_code=204)
@inject
def revoke_permission(
    dataset_id: UUID,
    target_user_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> Response:
    service.revoke_permission(dataset_id, user_id, target_user_id)
    return Response(status_code=204)


@router.delete("/{dataset_id}/share/invitations/{invitation_id}", status_code=204)
@inject
def revoke_invitation(
    dataset_id: UUID,
    invitation_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> Response:
    service.revoke_invitation(dataset_id, user_id, invitation_id)
    return Response(status_code=204)


@router.post(
    "/{dataset_id}/share/invitations/{invitation_id}/link", response_model=LinkResponse
)
@inject
def regenerate_invitation_link(
    dataset_id: UUID,
    invitation_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> LinkResponse:
    return LinkResponse(link=service.regenerate_link(dataset_id, user_id, invitation_id))
```

```python
# app/controller/v1/dataset/review_link.py
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.dataset.share_resource import (
    CreateReviewLinkBody,
    ReviewLinkResponse,
    adapt_review_link,
)
from app.service.review_link import ReviewLinkService

router = APIRouter(
    prefix="/datasets",
    tags=["review-links"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


@router.post(
    "/{dataset_id}/review-links", status_code=201, response_model=ReviewLinkResponse
)
@inject
def create_review_link(
    dataset_id: UUID,
    body: CreateReviewLinkBody,
    user_id: UUID = Depends(parse_user_header),
    service: ReviewLinkService = Depends(Provide[Container.review_link_service]),
) -> ReviewLinkResponse:
    view, url = service.create(dataset_id, user_id, body.label)
    return adapt_review_link(view, url)


@router.delete("/{dataset_id}/review-links/{link_id}", status_code=204)
@inject
def revoke_review_link(
    dataset_id: UUID,
    link_id: UUID,
    user_id: UUID = Depends(parse_user_header),
    service: ReviewLinkService = Depends(Provide[Container.review_link_service]),
) -> Response:
    service.revoke(dataset_id, user_id, link_id)
    return Response(status_code=204)
```

```python
# app/controller/v1/invitation/invitation.py
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.user_parser import parse_user_header
from app.controller.v1.dataset.share_resource import (
    AcceptInvitationBody,
    AcceptResultResponse,
    ClaimResponse,
)
from app.service.share import ShareService

router = APIRouter(tags=["invitations"], dependencies=[Depends(authenticate)])


@router.post("/invitations/accept", response_model=AcceptResultResponse)
@inject
def accept_invitation(
    body: AcceptInvitationBody,
    user_id: UUID = Depends(parse_user_header),
    service: ShareService = Depends(Provide[Container.share_service]),
) -> AcceptResultResponse:
    result = service.accept(body.token, user_id)
    return AcceptResultResponse(dataset_id=result.dataset_id, level=result.level)


@router.post("/users/{user_id}/invitations/claim", response_model=ClaimResponse)
@inject
def claim_invitations(
    user_id: UUID,
    service: ShareService = Depends(Provide[Container.share_service]),
) -> ClaimResponse:
    return ClaimResponse(
        accepted=[
            AcceptResultResponse(dataset_id=result.dataset_id, level=result.level)
            for result in service.claim(user_id)
        ]
    )
```

```python
# app/controller/v1/review/review.py
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.v1.dataset.share_resource import adapt_review_page
from app.service.review_link import ReviewLinkService

router = APIRouter(prefix="/review", tags=["review"], dependencies=[Depends(authenticate)])


@router.get("/{token}")
@inject
def review_page(
    token: str,
    service: ReviewLinkService = Depends(Provide[Container.review_link_service]),
) -> dict:
    return adapt_review_page(service.view(token))
```

- [ ] **Step 5: Wire the container and the app**

In `app/container.py` add imports:

```python
from app.repository.dataset_invitation import DatasetInvitationRepository
from app.repository.dataset_review_link import DatasetReviewLinkRepository
from app.repository.embargo_notification import EmbargoNotificationRepository
from app.service.notification import EmbargoNotificationService
from app.service.review_link import ReviewLinkService
from app.service.share import ShareService
```

Add to `wiring_config.modules`:

```python
            "app.controller.v1.dataset.share",
            "app.controller.v1.dataset.review_link",
            "app.controller.v1.invitation.invitation",
            "app.controller.v1.review.review",
```

Add providers after `embargo_service` (plan 02's `dataset_service`, `dataset_repository`, `permission_repository`, `permission_service`, `embargo_audit` and plan 01's `email_service` must already be declared above):

```python
    dataset_invitation_repository = providers.Factory(
        DatasetInvitationRepository,
        session_factory=db.provided.session,
    )

    dataset_review_link_repository = providers.Factory(
        DatasetReviewLinkRepository,
        session_factory=db.provided.session,
    )

    share_service = providers.Factory(
        ShareService,
        dataset_service=dataset_service,
        dataset_repository=dataset_repository,
        permission_repository=permission_repository,
        permission_service=permission_service,
        invitation_repository=dataset_invitation_repository,
        review_link_repository=dataset_review_link_repository,
        user_repository=user_repository,
        user_service=user_service,
        audit=embargo_audit,
        email_service=email_service,
        public_base_url=config.PUBLIC_BASE_URL,
    )

    review_link_service = providers.Factory(
        ReviewLinkService,
        dataset_service=dataset_service,
        review_link_repository=dataset_review_link_repository,
        dataset_repository=dataset_repository,
        audit=embargo_audit,
        public_base_url=config.PUBLIC_BASE_URL,
    )
```

(`embargo_notification_repository` and `embargo_notification_service` are added in Task 9; leave those two imports out until then if Task 9 is not merged yet.)

In `app/setup.py` add imports:

```python
from app.controller.v1.dataset.share import router as share_router
from app.controller.v1.dataset.review_link import router as review_link_router
from app.controller.v1.invitation.invitation import router as invitation_router
from app.controller.v1.review.review import router as review_router
```

In `setup_routes`, after `dataset_router`:

```python
    fastAPIApp.include_router(share_router, prefix="/v1")
    fastAPIApp.include_router(review_link_router, prefix="/v1")
    fastAPIApp.include_router(invitation_router, prefix="/v1")
    fastAPIApp.include_router(review_router, prefix="/v1")
```

- [ ] **Step 6: Run the unit tests, including the route guard test**

Run: `pytest app/controller/v1/dataset/share_resource_test.py app/controller/routes_security_test.py -v`
Expected: all passed. Every new route has `authenticate`, so `PUBLIC_ROUTES` stays unchanged.

- [ ] **Step 7: Confirm the routes exist**

Run: `python -c "from fastapi import FastAPI; from app import setup; a=FastAPI(); setup.setup_routes(a); print(sorted(r.path for r in a.routes if 'share' in r.path or 'review' in r.path or 'invitation' in r.path))"`
Expected: the eleven paths of the contracts (`/v1/datasets/{dataset_id}/share`, `.../share/candidates`, `.../share/permissions/{target_user_id}`, `.../share/invitations/{invitation_id}`, `.../share/invitations/{invitation_id}/link`, `.../review-links`, `.../review-links/{link_id}`, `/v1/invitations/accept`, `/v1/users/{user_id}/invitations/claim`, `/v1/review/{token}`).

- [ ] **Step 8: Commit**

```bash
git add app/controller/v1/dataset/share_resource.py app/controller/v1/dataset/share_resource_test.py app/controller/v1/dataset/share.py app/controller/v1/dataset/review_link.py app/controller/v1/invitation app/controller/v1/review app/container.py app/setup.py
git commit -m "feat: routes to share datasets, accept invitations and read reviewer pages"
```

---

### Task 8: Email templates

Every message goes through the existing `EmailTemplateRenderer` and the templates in `app/resources/email_templates/` (#121), in the same identity: each new template extends `base.html`, imports `_macros.html`, and fills the blocks `title` (the subject), `preheader`, `label`, `content` and `reason` using only the macros. Each also has a `.txt` sibling extending plan 01's `base.txt`, so the plain-text part is written, not derived.

What each notification uses:

| Notification | Template | Why |
|---|---|---|
| Invitation | `dataset_invitation` (new) | The existing `invitation` is about joining a workspace, with a role and an expiry; ours is a dataset, a level, and no expiry. |
| Access granted | `notification` (existing) | Its fields — title, actor, message, details, button, reason — say everything this message needs. |
| Embargo ending | `embargo_reminder` (new) | Days remaining and the end date in the details panel; the extend button only for who can extend. |
| Embargo ended | `embargo_ended` (new) | The registered-but-not-findable explanation as a list, and the manual-DOI variant. |

No template mentions notification preferences, unsubscribing, snoozing or anything else DataMap does not have (see plan 01, Task 3, on the `fix/email-footer-links` PR).

**Files:**
- Modify: `app/service/email_template.py` (enum members, optional defaults)
- Create: `app/resources/email_templates/dataset_invitation.html`, `dataset_invitation.txt`
- Create: `app/resources/email_templates/embargo_reminder.html`, `embargo_reminder.txt`
- Create: `app/resources/email_templates/embargo_ended.html`, `embargo_ended.txt`
- Modify: `app/service/email_template_test.py` (import line, then append)

**Interfaces:**
- Consumes: plan 01's `EmailTemplateRenderer(site_url).render(EmailTemplate, context) -> RenderedEmail(subject, html, text)`, its `.txt` lookup and `base.txt` (blocks `content`, `reason`).
- Produces: `EmailTemplate.DATASET_INVITATION = "dataset_invitation"`, `EmailTemplate.EMBARGO_REMINDER = "embargo_reminder"`, `EmailTemplate.EMBARGO_ENDED = "embargo_ended"`, and their context keys:
  - `dataset_invitation`: `dataset_name`, `inviter_name`, `level` (`read` | `write`), `link` (secret)
  - `embargo_reminder`: `dataset_name`, `days_remaining`, `embargo_until_date`, `can_extend`, `owner_name`, `dataset_url`
  - `embargo_ended`: `dataset_name`, `is_owner`, `owner_name`, `dataset_url`; optional `ended_early`, `ended_by_manual_doi` (default `False`)
  - access granted uses `notification`: `title`, `preheader`, `message`, `cta_label`, `cta_url`, `reason`, optional `actor_name`, `details` (built in Task 4)

- [ ] **Step 1: Write the failing tests**

In `app/service/email_template_test.py`, change the import at the top to:

```python
from app.service.email_template import TEMPLATES_DIR, EmailTemplate, EmailTemplateRenderer
```

and append at the end of the file. The new `CONTEXTS` entries keep the existing `test_every_template_renders_with_its_context`, which loops over every `EmailTemplate`, green:

```python
CONTEXTS[EmailTemplate.DATASET_INVITATION] = {
    "dataset_name": "Ozone at ATTO",
    "inviter_name": "Ana Lima",
    "level": "read",
    "link": "https://datamap.example.org/invitations/tok",
}
CONTEXTS[EmailTemplate.EMBARGO_REMINDER] = {
    "dataset_name": "Ozone at ATTO",
    "days_remaining": 5,
    "embargo_until_date": "2026-12-29",
    "can_extend": True,
    "owner_name": "Ana Lima",
    "dataset_url": "https://datamap.example.org/app/datasets/1",
}
CONTEXTS[EmailTemplate.EMBARGO_ENDED] = {
    "dataset_name": "Ozone",
    "is_owner": True,
    "owner_name": "Ana",
    "dataset_url": "https://datamap.example.org/app/datasets/1",
}

REMINDER = {
    key: value
    for key, value in CONTEXTS[EmailTemplate.EMBARGO_REMINDER].items()
    if key != "can_extend"
}
ENDED = {
    key: value
    for key, value in CONTEXTS[EmailTemplate.EMBARGO_ENDED].items()
    if key != "is_owner"
}
NEW_TEMPLATES = (
    EmailTemplate.DATASET_INVITATION,
    EmailTemplate.EMBARGO_REMINDER,
    EmailTemplate.EMBARGO_ENDED,
)


class TestEmbargoTemplates(unittest.TestCase):
    def setUp(self):
        self.renderer = EmailTemplateRenderer(site_url=SITE_URL)

    def test_every_new_template_has_a_written_text_part(self):
        for template in NEW_TEMPLATES:
            with self.subTest(template=template):
                self.assertTrue((TEMPLATES_DIR / f"{template.value}.txt").is_file())

    def test_no_new_template_offers_what_datamap_does_not_have(self):
        for template in NEW_TEMPLATES:
            for suffix in (".html", ".txt"):
                body = (TEMPLATES_DIR / f"{template.value}{suffix}").read_text().lower()
                for word in ("unsubscribe", "preferences", "snooze"):
                    with self.subTest(template=template, suffix=suffix, word=word):
                        self.assertNotIn(word, body)

    def test_the_invitation_carries_its_link_in_both_parts(self):
        email = self.renderer.render(
            EmailTemplate.DATASET_INVITATION, CONTEXTS[EmailTemplate.DATASET_INVITATION]
        )

        self.assertIn("https://datamap.example.org/invitations/tok", email.html)
        self.assertIn("https://datamap.example.org/invitations/tok", email.text)
        self.assertEqual(email.subject, "Ana Lima shared “Ozone at ATTO” with you on DataMap")

    def test_a_reminder_offers_the_extend_button_only_to_who_can_extend(self):
        owner = self.renderer.render(EmailTemplate.EMBARGO_REMINDER, {**REMINDER, "can_extend": True})
        others = self.renderer.render(EmailTemplate.EMBARGO_REMINDER, {**REMINDER, "can_extend": False})

        self.assertIn("Extend the embargo", owner.html)
        self.assertNotIn("Extend the embargo", others.html)
        self.assertIn("Ana Lima", others.html)
        self.assertIn("Ana Lima can extend it", others.text)

    def test_the_reminder_subject_counts_the_days(self):
        five = self.renderer.render(EmailTemplate.EMBARGO_REMINDER, {**REMINDER, "can_extend": True})
        one = self.renderer.render(
            EmailTemplate.EMBARGO_REMINDER, {**REMINDER, "can_extend": True, "days_remaining": 1}
        )

        self.assertEqual(five.subject, "Embargo on “Ozone at ATTO” ends in 5 days")
        self.assertEqual(one.subject, "Embargo on “Ozone at ATTO” ends in 1 day")

    def test_the_end_notice_explains_registered_but_not_findable_to_the_owner(self):
        email = self.renderer.render(EmailTemplate.EMBARGO_ENDED, {**ENDED, "is_owner": True})

        self.assertIn("registered but not findable", email.text)
        self.assertIn("will not appear in DataCite search", email.text)
        self.assertIn("nothing will do it for you", email.text)
        self.assertIn("registered but not findable", email.html)

    def test_an_end_by_manual_doi_says_why_and_that_the_page_is_public(self):
        email = self.renderer.render(
            EmailTemplate.EMBARGO_ENDED,
            {**ENDED, "is_owner": False, "ended_early": True, "ended_by_manual_doi": True},
        )

        self.assertIn("registered a DOI for it in manual mode", email.text)
        self.assertIn("public page is now published", email.text)
        self.assertNotIn("registered but not findable", email.text)

    def test_an_early_end_by_the_owner_says_it_ended_early(self):
        email = self.renderer.render(
            EmailTemplate.EMBARGO_ENDED, {**ENDED, "is_owner": False, "ended_early": True}
        )

        self.assertIn("ended it early", email.text)
        self.assertIn("Publishing it is a manual step that Ana takes", email.text)

    def test_dataset_names_are_escaped_in_html_and_plain_in_the_subject(self):
        email = self.renderer.render(
            EmailTemplate.EMBARGO_REMINDER,
            {**REMINDER, "can_extend": False, "dataset_name": "<b>O3 & CO</b>"},
        )

        self.assertIn("&lt;b&gt;O3 &amp; CO&lt;/b&gt;", email.html)
        self.assertEqual(email.subject, "Embargo on “<b>O3 & CO</b>” ends in 5 days")

    def test_a_missing_owner_name_fails_here_not_in_an_inbox(self):
        context = {key: value for key, value in REMINDER.items() if key != "owner_name"}

        with self.assertRaises(UndefinedError):
            self.renderer.render(EmailTemplate.EMBARGO_REMINDER, {**context, "can_extend": False})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest app/service/email_template_test.py -v`
Expected: collection error, `AttributeError: DATASET_INVITATION` — the module-level `CONTEXTS` additions name members that do not exist yet.

- [ ] **Step 3: Add the enum members and optional defaults**

In `app/service/email_template.py`:

```python
class EmailTemplate(str, Enum):
    INVITATION = "invitation"
    ANNOUNCEMENT = "announcement"
    DATASET_REMINDER = "dataset_reminder"
    NOTIFICATION = "notification"
    DATASET_INVITATION = "dataset_invitation"
    EMBARGO_REMINDER = "embargo_reminder"
    EMBARGO_ENDED = "embargo_ended"


_OPTIONAL_DEFAULTS: dict[EmailTemplate, dict[str, Any]] = {
    EmailTemplate.ANNOUNCEMENT: {"image_url": None, "image_alt": "", "highlights": []},
    EmailTemplate.DATASET_REMINDER: {"missing_fields": []},
    EmailTemplate.NOTIFICATION: {"actor_name": None, "details": []},
    EmailTemplate.EMBARGO_ENDED: {"ended_early": False, "ended_by_manual_doi": False},
}
```

- [ ] **Step 4: Write the templates**

`app/resources/email_templates/dataset_invitation.html`

```html
{% extends "base.html" %}
{% import "_macros.html" as m %}
{% block title %}{{ inviter_name }} shared “{{ dataset_name }}” with you on DataMap{% endblock %}
{% block preheader %}{{ inviter_name }} gave you {{ "edit" if level == "write" else "read" }} access to a dataset under embargo.{% endblock %}
{% block label %}Invitation{% endblock %}
{% block content %}
{{ m.heading("You've been invited to a dataset") }}
{% call m.paragraph() %}{{ m.strong(inviter_name) }} gave you {{ "edit" if level == "write" else "read" }} access to the dataset {{ m.strong(dataset_name) }} on DataMap.{% endcall %}
{{ m.details([
  {"label": "Dataset", "value": dataset_name},
  {"label": "Access", "value": "Edit" if level == "write" else "Read"},
  {"label": "Invited by", "value": inviter_name},
]) }}
{% call m.paragraph() %}The dataset is under embargo: only the people its author names can see it. Accept the invitation and sign in, with any account, to open it.{% endcall %}
{{ m.button("Accept invitation", link) }}
{{ m.spacer(16) }}
{% call m.note(bottom=16) %}The link works once. If you weren't expecting this invitation, you can ignore this email.{% endcall %}
{{ m.link_fallback(link) }}
{% endblock %}
{% block reason %}You received this email because someone shared a DataMap dataset with this address.{% endblock %}
```

`app/resources/email_templates/dataset_invitation.txt`

```
{% extends "base.txt" %}
{% block content %}
{{ inviter_name }} gave you {{ "edit" if level == "write" else "read" }} access to the dataset “{{ dataset_name }}” on DataMap.

The dataset is under embargo: only the people its author names can see it. Open the link below and sign in, with any account, to accept:

{{ link }}

The link works once. If you weren't expecting this invitation, you can ignore this email.
{% endblock %}
{% block reason %}You received this email because someone shared a DataMap dataset with this address.{% endblock %}
```

`app/resources/email_templates/embargo_reminder.html`

```html
{% extends "base.html" %}
{% import "_macros.html" as m %}
{% block title %}Embargo on “{{ dataset_name }}” ends in {{ days_remaining }} day{{ "" if days_remaining == 1 else "s" }}{% endblock %}
{% block preheader %}On {{ embargo_until_date }} the files become available to the dataset's tenancy.{% endblock %}
{% block label %}Reminder{% endblock %}
{% block content %}
{{ m.heading("The embargo ends in " ~ days_remaining ~ (" day" if days_remaining == 1 else " days")) }}
{% call m.paragraph() %}The embargo on {{ m.strong(dataset_name) }} ends on {{ embargo_until_date }}. When it ends, the files become available to the members of the dataset's tenancy. Nothing is made public until the DOI is promoted.{% endcall %}
{{ m.details([
  {"label": "Dataset", "value": dataset_name},
  {"label": "Embargo ends", "value": embargo_until_date},
  {"label": "Days remaining", "value": days_remaining},
]) }}
{% if can_extend %}
{% call m.paragraph() %}If the article is still under review, the embargo can be extended by up to 90 days at a time.{% endcall %}
{{ m.button("Extend the embargo", dataset_url) }}
{{ m.spacer(16) }}
{{ m.link_fallback(dataset_url) }}
{% else %}
{% call m.note() %}If it needs more time, {{ m.strong(owner_name) }} can extend it by up to 90 days at a time.{% endcall %}
{% endif %}
{% endblock %}
{% block reason %}You received this email because you have access to a dataset under embargo on DataMap.{% endblock %}
```

`app/resources/email_templates/embargo_reminder.txt`

```
{% extends "base.txt" %}
{% block content %}
The embargo on “{{ dataset_name }}” ends in {{ days_remaining }} day{{ "" if days_remaining == 1 else "s" }}, on {{ embargo_until_date }}.

When it ends, the files become available to the members of the dataset's tenancy. Nothing is made public until the DOI is promoted.

{% if can_extend %}
If the article is still under review, the embargo can be extended by up to 90 days at a time: {{ dataset_url }}
{% else %}
If it needs more time, {{ owner_name }} can extend it by up to 90 days at a time.
{% endif %}
{% endblock %}
{% block reason %}You received this email because you have access to a dataset under embargo on DataMap.{% endblock %}
```

`app/resources/email_templates/embargo_ended.html`

```html
{% extends "base.html" %}
{% import "_macros.html" as m %}
{% block title %}The embargo on “{{ dataset_name }}” has ended{% endblock %}
{% block preheader %}{% if ended_by_manual_doi %}A DOI registered in manual mode ended the embargo, and the public page is published.{% else %}The files are available to the dataset's tenancy. Nothing is public yet.{% endif %}{% endblock %}
{% block label %}Embargo{% endblock %}
{% block content %}
{{ m.heading("The embargo has ended") }}
{% if ended_by_manual_doi %}
{% call m.paragraph() %}The embargo on {{ m.strong(dataset_name) }} ended early: {{ owner_name }} registered a DOI for it in manual mode, which requires the dataset to be public.{% endcall %}
{% call m.paragraph() %}The dataset's public page is now published, and its files are available on DataMap to the members of the dataset's tenancy.{% endcall %}
{% else %}
{% call m.paragraph() %}The embargo on {{ m.strong(dataset_name) }} has ended{% if ended_early %}: {{ owner_name }} ended it early{% endif %}.{% endcall %}
{{ m.bullets([
  "The files are now available on DataMap to the members of the dataset's tenancy.",
  "Nothing has been made public yet.",
  "The DOI is registered but not findable: it resolves, but DataCite does not index it, so the dataset will not appear in DataCite search or in the services that harvest from it.",
  "Promoting the DOI to findable publishes the dataset's public page and indexes the DOI. It is a manual step on the dataset page, and nothing will do it for you." if is_owner else "Publishing it is a manual step that " ~ owner_name ~ " takes on the dataset page.",
]) }}
{% endif %}
{{ m.spacer(8) }}
{{ m.button("Open dataset", dataset_url) }}
{% endblock %}
{% block reason %}You received this email because you have access to this dataset on DataMap.{% endblock %}
```

`app/resources/email_templates/embargo_ended.txt`

```
{% extends "base.txt" %}
{% block content %}
{% if ended_by_manual_doi %}
The embargo on “{{ dataset_name }}” ended early: {{ owner_name }} registered a DOI for it in manual mode, which requires the dataset to be public.

The dataset's public page is now published, and its files are available on DataMap to the members of the dataset's tenancy: {{ dataset_url }}
{% else %}
The embargo on “{{ dataset_name }}” has ended{% if ended_early %}: {{ owner_name }} ended it early{% endif %}.

- The files are now available on DataMap to the members of the dataset's tenancy.
- Nothing has been made public yet.
- The DOI is registered but not findable: it resolves, but DataCite does not index it, so the dataset will not appear in DataCite search or in the services that harvest from it.
{% if is_owner %}
- Promoting the DOI to findable publishes the dataset's public page and indexes the DOI. It is a manual step on the dataset page, and nothing will do it for you.
{% else %}
- Publishing it is a manual step that {{ owner_name }} takes on the dataset page.
{% endif %}

Open the dataset: {{ dataset_url }}
{% endif %}
{% endblock %}
{% block reason %}You received this email because you have access to this dataset on DataMap.{% endblock %}
```

`m.bullets` escapes its items, so the list in `embargo_ended.html` is plain strings; the owner's name is joined with `~` and escaped like the rest.

- [ ] **Step 5: Run them to verify they pass**

Run: `python -m pytest app/service/email_template_test.py -v`
Expected: PASS — the existing tests, plan 01's, and the 10 in `TestEmbargoTemplates` (`StrictUndefined` makes a missing key fail here rather than in someone's inbox).

- [ ] **Step 6: Commit**

```bash
git add app/service/email_template.py app/service/email_template_test.py app/resources/email_templates/dataset_invitation.html app/resources/email_templates/dataset_invitation.txt app/resources/email_templates/embargo_reminder.html app/resources/email_templates/embargo_reminder.txt app/resources/email_templates/embargo_ended.html app/resources/email_templates/embargo_ended.txt
git commit -m "feat: email templates for invitations and the end of an embargo"
```

---

### Task 9: EmbargoNotificationService and the dispatch route

**Files:**
- Create: `app/repository/embargo_notification.py`
- Create: `app/service/notification.py`
- Modify: `app/controller/v1/internal/notification.py` (plan 01)
- Modify: `app/container.py` (two providers)
- Test: `app/service/notification_test.py`

**Interfaces:**
- Consumes: plan 02 `DatasetEmbargoEvent`, `PermissionRepository.list_for_dataset`, `EmbargoAudit.record`, `EmbargoEventType`, `REMINDER_OFFSETS_DAYS`, and its early-termination path (the owner's `POST /datasets/{id}/embargo/end` and the manual DOI with `end_embargo: true`, both setting `embargo_until` to the moment it ended and appending `ended_early`, the DOI one with note `"manual DOI"`); plan 01 `EmailService.enqueue`, `EmailService.dispatch_due`; `UserRepository.fetch_by_id`.
- Produces:
  - `EmbargoNotificationRepository.datasets_with_reminders_due(now, horizon) -> list[Dataset]`, `.datasets_expired_unannounced(now) -> list[Dataset]`, `.embargo_set_at(dataset_id, until) -> datetime | None`, `.ending_event(dataset_id) -> DatasetEmbargoEvent | None` (the `ended_early` event when it is the latest of created/extended/ended_early)
  - `EmbargoNotificationService.queue_due(now: datetime) -> int`
  - module function `due_offset(until, set_at, now, offsets) -> int | None`

- [ ] **Step 1: Write the failing tests**

```python
# app/service/notification_test.py
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.model.embargo import EmbargoEventType
from app.repository.embargo_notification import EmbargoNotificationRepository
from app.repository.permission import PermissionRepository
from app.repository.user import UserRepository
from app.service.email import EmailService
from app.service.embargo_audit import EmbargoAudit
from app.service.notification import EmbargoNotificationService, due_offset

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
OFFSETS = (15, 10, 5, 1)


class TestDueOffset(unittest.TestCase):
    def test_nothing_is_due_before_fifteen_days(self):
        self.assertIsNone(due_offset(NOW + timedelta(days=16), NOW - timedelta(days=60), NOW, OFFSETS))

    def test_the_nearest_passed_offset_is_due(self):
        self.assertEqual(due_offset(NOW + timedelta(days=4), NOW - timedelta(days=60), NOW, OFFSETS), 5)

    def test_an_offset_already_past_when_the_date_was_set_is_never_due(self):
        set_at = NOW - timedelta(hours=1)
        self.assertIsNone(due_offset(NOW + timedelta(days=3), set_at, NOW, (15, 10)))
        self.assertEqual(due_offset(NOW + timedelta(days=3), set_at - timedelta(days=3), NOW, OFFSETS), 5)

    def test_an_unknown_set_time_allows_every_offset(self):
        self.assertEqual(due_offset(NOW + timedelta(hours=2), None, NOW, OFFSETS), 1)


class TestQueueDue(unittest.TestCase):
    def setUp(self):
        self.repository = Mock(spec=EmbargoNotificationRepository)
        self.permissions = Mock(spec=PermissionRepository)
        self.users = Mock(spec=UserRepository)
        self.audit = Mock(spec=EmbargoAudit)
        self.email = Mock(spec=EmailService)
        self.email.enqueue.return_value = uuid4()
        self.owner = SimpleNamespace(id=uuid4(), name="Ana", email="ana@usp.br", is_enabled=True)
        self.reader = SimpleNamespace(id=uuid4(), name="Bruno", email="bruno@inpa.gov.br", is_enabled=True)
        self.people = {self.owner.id: self.owner, self.reader.id: self.reader}
        self.users.fetch_by_id.side_effect = lambda id, is_enabled=True: (
            self.people.get(id) if self.people.get(id) and self.people[id].is_enabled == is_enabled else None
        )
        self.dataset = SimpleNamespace(
            id=uuid4(), name="Ozone", owner_id=self.owner.id, embargo_until=NOW + timedelta(days=4, hours=6)
        )
        self.permissions.list_for_dataset.return_value = [SimpleNamespace(user_id=self.reader.id)]
        self.repository.datasets_with_reminders_due.return_value = [self.dataset]
        self.repository.datasets_expired_unannounced.return_value = []
        self.repository.embargo_set_at.return_value = NOW - timedelta(days=60)
        self.repository.ending_event.return_value = None
        self.service = EmbargoNotificationService(
            notification_repository=self.repository,
            permission_repository=self.permissions,
            user_repository=self.users,
            audit=self.audit,
            email_service=self.email,
            public_base_url="https://datamap.pcs.usp.br",
        )

    def test_owner_and_permission_holders_each_get_the_reminder_once_keyed(self):
        queued = self.service.queue_due(NOW)

        self.assertEqual(queued, 2)
        calls = [call.kwargs for call in self.email.enqueue.call_args_list]
        self.assertEqual({call["recipient"] for call in calls}, {"ana@usp.br", "bruno@inpa.gov.br"})
        until = self.dataset.embargo_until.isoformat()
        self.assertEqual(
            {call["dedup_key"] for call in calls},
            {
                f"embargo_reminder:{self.dataset.id}:{until}:5:{self.owner.id}",
                f"embargo_reminder:{self.dataset.id}:{until}:5:{self.reader.id}",
            },
        )
        by_recipient = {call["recipient"]: call["context"] for call in calls}
        self.assertTrue(by_recipient["ana@usp.br"]["can_extend"])
        self.assertFalse(by_recipient["bruno@inpa.gov.br"]["can_extend"])
        self.assertEqual(by_recipient["ana@usp.br"]["days_remaining"], 5)

    def test_when_the_owner_is_disabled_the_others_can_extend(self):
        self.owner.is_enabled = False

        self.service.queue_due(NOW)

        calls = [call.kwargs for call in self.email.enqueue.call_args_list]
        self.assertEqual([call["recipient"] for call in calls], ["bruno@inpa.gov.br"])
        self.assertTrue(calls[0]["context"]["can_extend"])

    def test_a_person_without_an_email_is_left_out(self):
        self.reader.email = None
        self.assertEqual(self.service.queue_due(NOW), 1)

    def test_a_placeholder_address_is_passed_on_to_be_recorded_as_skipped(self):
        self.reader.email = "bruno@fake.mail.com"
        self.service.queue_due(NOW)
        recipients = [call.kwargs["recipient"] for call in self.email.enqueue.call_args_list]
        self.assertIn("bruno@fake.mail.com", recipients)

    def test_an_already_queued_reminder_is_not_counted(self):
        self.email.enqueue.return_value = None
        self.assertEqual(self.service.queue_due(NOW), 0)

    def test_an_ended_embargo_is_announced_and_marked_expired(self):
        ended = SimpleNamespace(
            id=uuid4(), name="Ozone", owner_id=self.owner.id, embargo_until=NOW - timedelta(minutes=3)
        )
        self.repository.datasets_with_reminders_due.return_value = []
        self.repository.datasets_expired_unannounced.return_value = [ended]

        self.service.queue_due(NOW)

        calls = [call.kwargs for call in self.email.enqueue.call_args_list]
        self.assertEqual({call["template"] for call in calls}, {"embargo_ended"})
        self.assertEqual(
            {call["dedup_key"] for call in calls},
            {
                f"embargo_ended:{ended.id}:{ended.embargo_until.isoformat()}:{self.owner.id}",
                f"embargo_ended:{ended.id}:{ended.embargo_until.isoformat()}:{self.reader.id}",
            },
        )
        self.audit.record.assert_called_once()
        self.assertEqual(self.audit.record.call_args.kwargs["event_type"], EmbargoEventType.EXPIRED)
        self.assertIsNone(self.audit.record.call_args.kwargs["changed_by"])
        self.assertFalse(calls[0]["context"]["ended_early"])

    def test_an_embargo_ended_by_a_manual_doi_says_so(self):
        ended = SimpleNamespace(
            id=uuid4(), name="Ozone", owner_id=self.owner.id, embargo_until=NOW - timedelta(minutes=3)
        )
        self.repository.datasets_with_reminders_due.return_value = []
        self.repository.datasets_expired_unannounced.return_value = [ended]
        self.repository.ending_event.return_value = SimpleNamespace(
            event_type="ended_early", note="manual DOI"
        )

        self.service.queue_due(NOW)

        context = self.email.enqueue.call_args_list[0].kwargs["context"]
        self.assertTrue(context["ended_early"])
        self.assertTrue(context["ended_by_manual_doi"])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest app/service/notification_test.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the repository**

```python
# app/repository/embargo_notification.py
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from typing import Callable
from uuid import UUID

from sqlalchemy import and_, exists
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import true

from app.model.db.dataset import Dataset
from app.model.db.embargo import DatasetEmbargoEvent


class EmbargoNotificationRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def datasets_with_reminders_due(self, now: datetime, horizon: timedelta) -> list[Dataset]:
        with self._session_factory() as session:
            return (
                session.query(Dataset)
                .filter(
                    Dataset.is_enabled == true(),
                    Dataset.embargo_until.isnot(None),
                    Dataset.embargo_until > now,
                    Dataset.embargo_until <= now + horizon,
                )
                .all()
            )

    def datasets_expired_unannounced(self, now: datetime) -> list[Dataset]:
        announced = exists().where(
            and_(
                DatasetEmbargoEvent.dataset_id == Dataset.id,
                DatasetEmbargoEvent.event_type == "expired",
                DatasetEmbargoEvent.occurred_at >= Dataset.embargo_until,
            )
        )
        with self._session_factory() as session:
            return (
                session.query(Dataset)
                .filter(
                    Dataset.is_enabled == true(),
                    Dataset.embargo_until.isnot(None),
                    Dataset.embargo_until <= now,
                    ~announced,
                )
                .all()
            )

    def ending_event(self, dataset_id: UUID) -> DatasetEmbargoEvent | None:
        with self._session_factory() as session:
            event = (
                session.query(DatasetEmbargoEvent)
                .filter(
                    DatasetEmbargoEvent.dataset_id == dataset_id,
                    DatasetEmbargoEvent.event_type.in_(
                        ("created", "extended", "ended_early")
                    ),
                )
                .order_by(DatasetEmbargoEvent.occurred_at.desc())
                .first()
            )
            if event is None or event.event_type != "ended_early":
                return None
            return event

    def embargo_set_at(self, dataset_id: UUID, until: datetime) -> datetime | None:
        with self._session_factory() as session:
            event = (
                session.query(DatasetEmbargoEvent)
                .filter(
                    DatasetEmbargoEvent.dataset_id == dataset_id,
                    DatasetEmbargoEvent.event_type.in_(("created", "extended")),
                )
                .order_by(DatasetEmbargoEvent.occurred_at.desc())
                .first()
            )
            return event.occurred_at if event is not None else None
```

- [ ] **Step 4: Write the service**

```python
# app/service/notification.py
import logging
from datetime import datetime, timedelta
from uuid import UUID

from app.logging_config import fields
from app.model.embargo import REMINDER_OFFSETS_DAYS, EmbargoEventType
from app.repository.embargo_notification import EmbargoNotificationRepository
from app.repository.permission import PermissionRepository
from app.repository.user import UserRepository
from app.service.email import EmailService
from app.service.embargo_audit import EmbargoAudit

MANUAL_DOI_NOTE = "manual DOI"


def due_offset(
    until: datetime, set_at: datetime | None, now: datetime, offsets: tuple[int, ...]
) -> int | None:
    due = [
        offset
        for offset in offsets
        if until - timedelta(days=offset) <= now
        and (set_at is None or until - timedelta(days=offset) >= set_at)
    ]
    return min(due) if due else None


class EmbargoNotificationService:
    def __init__(
        self,
        notification_repository: EmbargoNotificationRepository,
        permission_repository: PermissionRepository,
        user_repository: UserRepository,
        audit: EmbargoAudit,
        email_service: EmailService,
        public_base_url: str,
    ) -> None:
        self._repository = notification_repository
        self._permissions = permission_repository
        self._users = user_repository
        self._audit = audit
        self._email = email_service
        self._base_url = public_base_url.rstrip("/")
        self._logger = logging.getLogger("service:EmbargoNotificationService")

    def queue_due(self, now: datetime) -> int:
        queued = 0
        horizon = timedelta(days=max(REMINDER_OFFSETS_DAYS))
        for dataset in self._repository.datasets_with_reminders_due(now, horizon):
            set_at = self._repository.embargo_set_at(dataset.id, dataset.embargo_until)
            offset = due_offset(dataset.embargo_until, set_at, now, REMINDER_OFFSETS_DAYS)
            if offset is not None:
                queued += self._queue_for_people(dataset, "embargo_reminder", offset)
        for dataset in self._repository.datasets_expired_unannounced(now):
            ending = self._repository.ending_event(dataset.id)
            queued += self._queue_for_people(dataset, "embargo_ended", None, ending)
            self._audit.record(
                dataset_id=dataset.id,
                event_type=EmbargoEventType.EXPIRED,
                changed_by=None,
                new_value={"embargo_until": dataset.embargo_until.isoformat()},
            )
        return queued

    def _people(self, dataset) -> tuple[object | None, list]:
        owner = self._users.fetch_by_id(id=dataset.owner_id, is_enabled=True)
        holders = [
            user
            for user in (
                self._users.fetch_by_id(id=permission.user_id, is_enabled=True)
                for permission in self._permissions.list_for_dataset(dataset.id)
            )
            if user is not None
        ]
        return owner, holders

    def _queue_for_people(self, dataset, template: str, offset: int | None, ending=None) -> int:
        owner, holders = self._people(dataset)
        owner_name = owner.name if owner is not None else ""
        recipients = ([owner] if owner is not None else []) + holders
        until = dataset.embargo_until.isoformat()
        queued = 0
        for person in recipients:
            if not person.email:
                continue
            is_owner = owner is not None and person.id == owner.id
            context = {
                "dataset_name": dataset.name,
                "owner_name": owner_name,
                "dataset_url": f"{self._base_url}/app/datasets/{dataset.id}",
            }
            if template == "embargo_reminder":
                context.update(
                    days_remaining=offset,
                    embargo_until_date=dataset.embargo_until.date().isoformat(),
                    can_extend=is_owner or owner is None,
                )
                dedup_key = f"embargo_reminder:{dataset.id}:{until}:{offset}:{person.id}"
            else:
                context.update(
                    is_owner=is_owner,
                    ended_early=ending is not None,
                    ended_by_manual_doi=ending is not None
                    and (ending.note or "") == MANUAL_DOI_NOTE,
                )
                dedup_key = f"embargo_ended:{dataset.id}:{until}:{person.id}"
            queued += self._enqueue(template, person.email, context, dataset.id, dedup_key)
        return queued

    def _enqueue(self, template: str, recipient: str, context: dict, dataset_id: UUID, dedup_key: str) -> int:
        try:
            message_id = self._email.enqueue(
                template=template,
                recipient=recipient,
                context=context,
                related_type="dataset",
                related_id=dataset_id,
                dedup_key=dedup_key,
            )
        except Exception:
            self._logger.error(
                "email enqueue failed",
                exc_info=True,
                extra=fields(template=template, dataset_id=str(dataset_id)),
            )
            return 0
        return 1 if message_id is not None else 0
```

`owner is None` here means the owner's account is disabled (it was fetched with `is_enabled=True`), which is exactly when the RFC lets every permission holder extend.

Early termination, by the owner or by a manual DOI with `end_embargo: true`, reaches this same pass: plan 02 sets `embargo_until` to the moment it ended, so the dataset is "expired and unannounced" on the next dispatch, at most five minutes later, with the same `dedup_key` per dataset, `embargo_until` and recipient. `ending_event` is what lets the message say why.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest app/service/notification_test.py -v`
Expected: 11 passed

- [ ] **Step 6: Wire it into the container and the dispatch route**

In `app/container.py` (imports already added in Task 7):

```python
    embargo_notification_repository = providers.Factory(
        EmbargoNotificationRepository,
        session_factory=db.provided.session,
    )

    embargo_notification_service = providers.Factory(
        EmbargoNotificationService,
        notification_repository=embargo_notification_repository,
        permission_repository=permission_repository,
        user_repository=user_repository,
        audit=embargo_audit,
        email_service=email_service,
        public_base_url=config.PUBLIC_BASE_URL,
    )
```

In `app/controller/v1/internal/notification.py` (plan 01), replace the dispatch function with:

```python
@router.post(
    "/dispatch",
    dependencies=[Depends(authenticate)],
    response_model=NotificationDispatchResponse,
)
@inject
def dispatch(
    notifications: EmbargoNotificationService = Depends(
        Provide[Container.embargo_notification_service]
    ),
    email_service: EmailService = Depends(Provide[Container.email_service]),
) -> NotificationDispatchResponse:
    """Queue the embargo messages that are due, then send what is due. Called by the Archivist."""
    queued = notifications.queue_due(datetime.now(timezone.utc))
    result = email_service.dispatch_due()
    return NotificationDispatchResponse(
        queued=queued + result.queued,
        sent=result.sent,
        failed=result.failed,
        skipped=result.skipped,
        retried=result.retried,
    )
```

with the imports `from datetime import datetime, timezone` and `from app.service.notification import EmbargoNotificationService`. Keep plan 01's `router` prefix and `NotificationDispatchResponse` model as they are.

- [ ] **Step 7: Run plan 01's dispatch route test and this task's tests**

Run: `pytest app/service/notification_test.py app/controller -v`
Expected: all passed. If plan 01's route test mocks only `email_service`, add `embargo_notification_service` returning `0` to it.

- [ ] **Step 8: Commit**

```bash
git add app/repository/embargo_notification.py app/service/notification.py app/service/notification_test.py app/controller/v1/internal/notification.py app/container.py
git commit -m "feat: queue embargo reminders and the end notice for everyone with access"
```

---

### Task 10: Dashboard panel

**Files:**
- Modify: `infrastructure/grafana/dashboards/Business/platform-usage.json`
- Test: `app/grafana_dashboards_test.py` (unchanged; must stay green)

**Interfaces:**
- Consumes: Task 6's metric names.

- [ ] **Step 1: Append the row and the panel**

Append these two objects to the end of the `panels` array (after panel id 40; ids 41 and 42, row at y=96, panel at y=97):

```json
{
  "type": "row",
  "title": "Reviewer links",
  "collapsed": false,
  "panels": [],
  "id": 41,
  "gridPos": {"x": 0, "y": 96, "w": 24, "h": 1}
},
{
  "type": "timeseries",
  "title": "Reviewer link views",
  "description": "Pages served to reviewer links. A steady not_found rate is someone guessing tokens.",
  "datasource": {"type": "prometheus", "uid": "prometheus"},
  "targets": [
    {
      "refId": "A",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "expr": "sum by (outcome) (increase(datamap_review_link_views_total[$__interval]))",
      "legendFormat": "{{outcome}}",
      "range": true,
      "instant": false
    },
    {
      "refId": "B",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "expr": "sum(increase(datamap_review_links_created_total[$__interval]))",
      "legendFormat": "links created",
      "range": true,
      "instant": false
    }
  ],
  "fieldConfig": {
    "defaults": {
      "unit": "short",
      "custom": {
        "drawStyle": "bars",
        "lineWidth": 1,
        "fillOpacity": 80,
        "showPoints": "never",
        "spanNulls": true,
        "stacking": {"mode": "normal", "group": "A"}
      },
      "color": {"mode": "palette-classic"}
    },
    "overrides": []
  },
  "options": {
    "legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max", "lastNotNull"], "showLegend": true},
    "tooltip": {"mode": "multi", "sort": "desc"}
  },
  "id": 42,
  "gridPos": {"x": 0, "y": 97, "w": 24, "h": 8}
}
```

- [ ] **Step 2: Run the dashboard test**

Run: `pytest app/grafana_dashboards_test.py -v`
Expected: all passed (both metrics are declared in `app/metrics.py` by Task 6)

- [ ] **Step 3: Commit**

```bash
git add infrastructure/grafana/dashboards/Business/platform-usage.json
git commit -m "feat: reviewer link views on the platform usage dashboard"
```

---

### Task 11: Integration tests

**Files:**
- Create: `tests/integration/utils/database.py`
- Create: `tests/integration/test_sharing_api.py`
- Create: `tests/integration/test_review_links_api.py`
- Create: `tests/integration/test_embargo_notifications.py`

**Interfaces:**
- Consumes: everything above; plan 02's `PUT /datasets/{id}/embargo`; plan 01's Mailpit service, `tests/integration/utils/mailpit.py`, and `GET /admin/emails`.

Write each test, run it, and **watch it fail first** (CLAUDE.md: a test that passes on its first run tests nothing). The simplest way: run each file before wiring the route it covers is merged, or temporarily point one assertion at a wrong value and see it fail.

- [ ] **Step 1: Database helper**

```python
# tests/integration/utils/database.py
import subprocess

POSTGRES_CONTAINER = "datamap_postgres_test_integration"


def execute(sql: str) -> str:
    result = subprocess.run(
        [
            "docker", "exec", POSTGRES_CONTAINER,
            "psql", "-U", "gk_admin", "-d", "gatekeeper_db", "-tA", "-c", sql,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
```

- [ ] **Step 2: Sharing tests**

```python
# tests/integration/test_sharing_api.py
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.integration.config import config
from tests.integration.utils.assertions import assert_status_code


def headers(user_id: str, tenancy: str | None = None) -> dict:
    return {
        "X-Api-Key": config.api_key,
        "X-Api-Secret": config.api_secret,
        "X-User-Id": user_id,
        "X-Datamap-Tenancies": tenancy if tenancy is not None else "",
        "Content-Type": "application/json",
    }


def create_user(http_client, valid_headers, providers=None) -> dict:
    email = f"share_{uuid.uuid4().hex[:8]}@example.com"
    response = http_client.post(
        "/users/",
        json={"name": "Outside Researcher", "email": email, "providers": providers or [], "roles": []},
        headers=valid_headers,
    )
    assert_status_code(response, 200)
    return {"id": response.json()["id"], "email": email}


@pytest.fixture
def embargoed_dataset(dataset_fixture, http_client, valid_headers):
    dataset = dataset_fixture.create_test_dataset()
    until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    response = http_client.put(
        f"/datasets/{dataset['id']}/embargo",
        json={"until": until, "metadata_visible": False, "note": None},
        headers=valid_headers,
    )
    assert_status_code(response, 200)
    return dataset


class TestShareWithAnAccountOutsideTheTenancy:
    def test_a_user_with_no_tenancy_and_no_role_reads_the_dataset_once_shared(
        self, http_client, valid_headers, embargoed_dataset
    ):
        outsider = create_user(http_client, valid_headers)
        dataset_id = embargoed_dataset["id"]

        before = http_client.get(f"/datasets/{dataset_id}", headers=headers(outsider["id"]))
        assert before.status_code in (401, 404)

        grant = http_client.post(
            f"/datasets/{dataset_id}/share",
            json={"email": outsider["email"].upper(), "level": "read"},
            headers=valid_headers,
        )
        assert_status_code(grant, 201)
        assert grant.json()["kind"] == "permission"

        after = http_client.get(f"/datasets/{dataset_id}", headers=headers(outsider["id"]))
        assert_status_code(after, 200)
        assert after.json()["access"]["level"] == "read"

        shared = http_client.get("/datasets/?shared=true", headers=headers(outsider["id"]))
        assert_status_code(shared, 200)
        assert dataset_id in [item["id"] for item in shared.json()["content"]]

        cannot_edit = http_client.put(
            f"/datasets/{dataset_id}",
            json={"name": "x", "data": {}, "tenancy": embargoed_dataset["tenancy"]},
            headers=headers(outsider["id"]),
        )
        assert_status_code(cannot_edit, 403)

    def test_revoking_takes_the_access_away(self, http_client, valid_headers, embargoed_dataset):
        outsider = create_user(http_client, valid_headers)
        dataset_id = embargoed_dataset["id"]
        http_client.post(
            f"/datasets/{dataset_id}/share",
            json={"user_id": outsider["id"], "level": "read"},
            headers=valid_headers,
        )

        revoke = http_client.delete(
            f"/datasets/{dataset_id}/share/permissions/{outsider['id']}", headers=valid_headers
        )
        assert_status_code(revoke, 204)

        after = http_client.get(f"/datasets/{dataset_id}", headers=headers(outsider["id"]))
        assert_status_code(after, 404)

    def test_the_share_state_lists_permissions_and_invitations(
        self, http_client, valid_headers, embargoed_dataset
    ):
        dataset_id = embargoed_dataset["id"]
        http_client.post(
            f"/datasets/{dataset_id}/share",
            json={"email": f"nobody_{uuid.uuid4().hex[:6]}@example.org", "level": "read"},
            headers=valid_headers,
        )

        state = http_client.get(f"/datasets/{dataset_id}/share", headers=valid_headers)

        assert_status_code(state, 200)
        body = state.json()
        assert body["owner"]["id"] == config.user_id
        assert len(body["invitations"]) == 1
        assert body["invitations"][0]["accepted_at"] is None

    def test_an_invalid_orcid_is_refused(self, http_client, valid_headers, embargoed_dataset):
        response = http_client.post(
            f"/datasets/{embargoed_dataset['id']}/share",
            json={"orcid": "0000-0002-1825-0098", "level": "read"},
            headers=valid_headers,
        )
        assert_status_code(response, 400)
        assert response.json()["errors"][0]["code"] == "invalid_orcid"


class TestInvitations:
    def invite(self, http_client, valid_headers, dataset_id) -> str:
        response = http_client.post(
            f"/datasets/{dataset_id}/share",
            json={"email": f"invitee_{uuid.uuid4().hex[:6]}@example.org", "level": "write"},
            headers=valid_headers,
        )
        assert_status_code(response, 201)
        assert response.json()["kind"] == "invitation"
        return response.json()["link"].rsplit("/", 1)[1]

    def test_the_link_is_accepted_once_by_any_account(self, http_client, valid_headers, embargoed_dataset):
        token = self.invite(http_client, valid_headers, embargoed_dataset["id"])
        first = create_user(http_client, valid_headers)
        second = create_user(http_client, valid_headers)

        accepted = http_client.post(
            "/invitations/accept", json={"token": token}, headers=headers(first["id"])
        )
        assert_status_code(accepted, 200)
        assert accepted.json() == {"dataset_id": embargoed_dataset["id"], "level": "write"}

        again = http_client.post(
            "/invitations/accept", json={"token": token}, headers=headers(second["id"])
        )
        assert_status_code(again, 409)
        assert again.json()["detail"] == "invitation_already_accepted"

        state = http_client.get(f"/datasets/{embargoed_dataset['id']}/share", headers=valid_headers)
        assert state.json()["invitations"][0]["accepted_by"]["id"] == first["id"]

    def test_an_unknown_token_is_not_found(self, http_client, valid_headers):
        user = create_user(http_client, valid_headers)
        response = http_client.post(
            "/invitations/accept", json={"token": "not-a-token"}, headers=headers(user["id"])
        )
        assert_status_code(response, 404)

    def test_a_pending_invitation_is_claimed_when_its_orcid_signs_in(
        self, http_client, valid_headers, embargoed_dataset
    ):
        orcid = "0000-0002-1694-233X"
        invite = http_client.post(
            f"/datasets/{embargoed_dataset['id']}/share",
            json={"orcid": orcid, "level": "read"},
            headers=valid_headers,
        )
        assert_status_code(invite, 201)
        user = create_user(http_client, valid_headers, providers=[{"name": "orcid", "reference": orcid}])

        claim = http_client.post(f"/users/{user['id']}/invitations/claim", headers=headers(user["id"]))

        assert_status_code(claim, 200)
        assert claim.json()["accepted"] == [{"dataset_id": embargoed_dataset["id"], "level": "read"}]
```

The ORCID test reuses one fixed ORCID; the `providers` table may already hold it from an earlier run of the same database. Run against `integration-test-full`, which starts from an empty database, or pick the ORCID per run with a valid checksum computed by `app.service.share_identity.orcid_checksum_ok`.

- [ ] **Step 3: Reviewer link tests**

```python
# tests/integration/test_review_links_api.py
from tests.integration.test_sharing_api import embargoed_dataset  # noqa: F401
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute


def client_only(valid_headers) -> dict:
    return {key: value for key, value in valid_headers.items() if key in ("X-Api-Key", "X-Api-Secret", "Content-Type")}


def create_link(http_client, valid_headers, dataset_id) -> dict:
    response = http_client.post(
        f"/datasets/{dataset_id}/review-links", json={"label": "JGR, round 1"}, headers=valid_headers
    )
    assert_status_code(response, 201)
    return response.json()


class TestReviewLinks:
    def test_the_page_redacts_authorship_and_lists_no_files(
        self, http_client, valid_headers, embargoed_dataset
    ):
        link = create_link(http_client, valid_headers, embargoed_dataset["id"])
        token = link["link"].rsplit("/", 1)[1]

        page = http_client.get(f"/review/{token}", headers=client_only(valid_headers))

        assert_status_code(page, 200)
        body = page.json()
        assert body["state"] == "active"
        assert body["dataset"]["data"]["authors"] == [{"name": "[redacted]", "email": "[redacted]"}]
        assert body["dataset"]["data"]["institution"] == "[redacted]"
        assert body["dataset"]["data"]["description"] == "Dataset created for integration testing"
        assert "files_in" not in str(body)

        state = http_client.get(f"/datasets/{embargoed_dataset['id']}/share", headers=valid_headers)
        assert state.json()["review_links"][0]["views"]["count"] == 1

    def test_a_revoked_link_is_not_found(self, http_client, valid_headers, embargoed_dataset):
        link = create_link(http_client, valid_headers, embargoed_dataset["id"])
        token = link["link"].rsplit("/", 1)[1]

        revoke = http_client.delete(
            f"/datasets/{embargoed_dataset['id']}/review-links/{link['id']}", headers=valid_headers
        )
        assert_status_code(revoke, 204)

        page = http_client.get(f"/review/{token}", headers=client_only(valid_headers))
        assert_status_code(page, 404)

    def test_after_the_embargo_the_page_points_to_the_dataset(
        self, http_client, valid_headers, embargoed_dataset
    ):
        link = create_link(http_client, valid_headers, embargoed_dataset["id"])
        token = link["link"].rsplit("/", 1)[1]
        end = http_client.post(f"/datasets/{embargoed_dataset['id']}/embargo/end", headers=valid_headers)
        assert_status_code(end, 200)

        page = http_client.get(f"/review/{token}", headers=client_only(valid_headers))

        assert_status_code(page, 200)
        assert page.json() == {"state": "ended", "dataset_id": embargoed_dataset["id"], "published": False}

    def test_no_link_without_an_embargo(self, http_client, valid_headers, dataset_fixture):
        dataset = dataset_fixture.create_test_dataset()
        response = http_client.post(
            f"/datasets/{dataset['id']}/review-links", json={"label": "x"}, headers=valid_headers
        )
        assert_status_code(response, 400)
        assert response.json()["errors"][0]["code"] == "embargo_not_active"

    def test_the_page_needs_client_credentials(self, http_client, no_auth_headers):
        assert_status_code(http_client.get("/review/anything", headers=no_auth_headers), 401)

    def test_views_record_no_reviewer_identity(self):
        columns = execute(
            "SELECT string_agg(column_name, ',' ORDER BY column_name) FROM information_schema.columns "
            "WHERE table_name = 'dataset_review_link_views'"
        )
        assert columns == "id,link_id,outcome,viewed_at"
```

- [ ] **Step 4: Notification tests**

```python
# tests/integration/test_embargo_notifications.py
import time
import uuid
from datetime import datetime, timedelta, timezone

from tests.integration.test_sharing_api import create_user
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.mailpit import Mailpit


def dispatch(http_client, valid_headers) -> dict:
    client = {key: value for key, value in valid_headers.items() if key in ("X-Api-Key", "X-Api-Secret", "Content-Type")}
    response = http_client.post("/internal/notifications/dispatch", headers=client)
    assert_status_code(response, 200)
    return response.json()


def set_embargo(http_client, valid_headers, dataset_id, delta: timedelta) -> str:
    until = (datetime.now(timezone.utc) + delta).isoformat()
    response = http_client.put(
        f"/datasets/{dataset_id}/embargo",
        json={"until": until, "metadata_visible": False, "note": None},
        headers=valid_headers,
    )
    assert_status_code(response, 200)
    return until


class TestEmbargoNotifications:
    def test_a_reminder_reaches_each_person_exactly_once(self, http_client, valid_headers, dataset_fixture):
        dataset = dataset_fixture.create_test_dataset()
        reader = create_user(http_client, valid_headers)
        set_embargo(http_client, valid_headers, dataset["id"], timedelta(days=4, hours=12))
        http_client.post(
            f"/datasets/{dataset['id']}/share",
            json={"user_id": reader["id"], "level": "read"},
            headers=valid_headers,
        )
        execute(
            "UPDATE dataset_embargo_events SET occurred_at = occurred_at - interval '30 days' "
            f"WHERE dataset_id = '{dataset['id']}' AND event_type = 'created'"
        )

        dispatch(http_client, valid_headers)
        dispatch(http_client, valid_headers)

        Mailpit().wait_for(reader["email"], count=1)
        reminders = [
            message for message in Mailpit().messages_to(reader["email"]) if "ends in 5 days" in message["Subject"]
        ]
        assert len(reminders) == 1

    def test_the_end_notice_goes_out_once_and_the_invitation_token_is_masked(
        self, http_client, valid_headers, dataset_fixture
    ):
        dataset = dataset_fixture.create_test_dataset()
        invitee = f"masked_{uuid.uuid4().hex[:6]}@example.org"
        set_embargo(http_client, valid_headers, dataset["id"], timedelta(seconds=4))
        invite = http_client.post(
            f"/datasets/{dataset['id']}/share",
            json={"email": invitee, "level": "read"},
            headers=valid_headers,
        )
        token = invite.json()["link"].rsplit("/", 1)[1]
        time.sleep(5)

        dispatch(http_client, valid_headers)
        dispatch(http_client, valid_headers)

        messages = Mailpit().wait_for(invitee, count=1)
        assert len(messages) == 1
        assert token in Mailpit().message(messages[0]["ID"])["Text"]

        record = http_client.get(f"/admin/emails/?recipient={invitee}", headers=valid_headers)
        assert_status_code(record, 200)
        email_id = record.json()["items"][0]["id"]
        detail = http_client.get(f"/admin/emails/{email_id}", headers=valid_headers).json()
        assert detail["status"] == "sent"
        assert token not in detail["body_text"]
        assert token not in str(detail["context"])

        expired = execute(
            f"SELECT count(*) FROM dataset_embargo_events WHERE dataset_id = '{dataset['id']}' AND event_type = 'expired'"
        )
        assert expired == "1"

    def test_a_manual_doi_that_ends_the_embargo_tells_everyone_with_access_why(
        self, http_client, valid_headers, dataset_fixture
    ):
        dataset = dataset_fixture.create_dataset_with_version()
        version = dataset["current_version"]["name"]
        reader = create_user(http_client, valid_headers)
        set_embargo(http_client, valid_headers, dataset["id"], timedelta(days=30))
        http_client.post(
            f"/datasets/{dataset['id']}/share",
            json={"user_id": reader["id"], "level": "read"},
            headers=valid_headers,
        )

        doi = http_client.post(
            f"/datasets/{dataset['id']}/versions/{version}/doi",
            json={
                "identifier": f"10.82978/MANUAL{uuid.uuid4().hex[:8]}",
                "mode": "MANUAL",
                "end_embargo": True,
            },
            headers=valid_headers,
        )
        assert_status_code(doi, 201)

        dispatch(http_client, valid_headers)
        dispatch(http_client, valid_headers)

        messages = [
            message
            for message in Mailpit().wait_for(reader["email"], count=2)
            if "has ended" in message["Subject"]
        ]
        assert len(messages) == 1
        assert "registered a DOI for it in manual mode" in Mailpit().message(messages[0]["ID"])["Text"]
```

The owner of the integration user's datasets (`config.user_id`) has the seeded email; the end-notice assertions use the invitee's address so they do not depend on what else the shared user received in earlier tests.

- [ ] **Step 5: Run the integration suite**

Run: `make ENV_FILE_PATH=integration-test.env integration-test-full`
Then confirm the API actually answered during the run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:9094/api/v1/health-check/` (with the stack up via `integration-test-up`), and read the pytest summary in the make output — do not pipe `make` into `tail`/`grep`.
Expected: the three new files pass; no previously passing test fails. If the first run shows a batch of 401s, that is Casbin's 5-second reload after seeding (CLAUDE.md) — poll `/api/v1/clients/` until it answers 200 and rerun with `integration-test-run`.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/utils/database.py tests/integration/test_sharing_api.py tests/integration/test_review_links_api.py tests/integration/test_embargo_notifications.py
git commit -m "test: sharing, invitations, reviewer links and embargo emails end to end"
```

---

### Task 12: Validation loop

- [ ] **Step 1:** `pytest` — Expected: all unit tests pass.
- [ ] **Step 2:** `make ENV_FILE_PATH=integration-test.env integration-test-full` — read the output; confirm the health check answered and the pytest summary shows no failures.
- [ ] **Step 3:** `ruff check` — Expected: `All checks passed!`
- [ ] **Step 4:** `ruff check --fix` and `ruff format` — then `git diff --stat` to see what changed.
- [ ] **Step 5:** Commit any formatting changes:

```bash
git add -A app tests migrations infrastructure
git commit -m "chore: ruff format"
```

---

## Self-review notes

- **Spec coverage:** invitations by email/ORCID (Tasks 2, 4), tenancy search excluding owner and current holders (Tasks 3, 4), single-use accept by any account and 409 (Task 5), claim on login (Task 5), `datasets_shared` on grant and accept (Tasks 4, 5), reviewer links only while embargoed, redaction allowlist, no file names, views without identity, `ended`/`published` (Task 6), metrics and panel (Tasks 6, 10), audit events for invitations and links (Tasks 4–6), three new templates in the existing identity (`dataset_invitation`, `embargo_reminder`, `embargo_ended`, each with a written `.txt`) plus access granted through the existing `notification`, with the registered-but-not-findable text, the extend button only for who can extend, and the early and manual-DOI endings (Task 8), reminders to everyone with access, nearest offset only, never an offset past at set time, end notice and `expired` once (Task 9), dispatch wiring (Task 9), integration coverage for every route, repository and Casbin path (Task 11).
- **Not in this plan:** the access rule, `datasets_shared` seed rows, embargo routes and the `access` payload (plan 02); the email table, sender, the plain-text part of the renderer and `base.txt`, Mailpit and admin routes (plan 01); the base layout and macros (main, #121); the webapp (plan 05).
