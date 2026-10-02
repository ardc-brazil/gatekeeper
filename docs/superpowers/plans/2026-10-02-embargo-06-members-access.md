# Dataset Embargo — Members' Access Implementation Plan (06)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a dataset's owner choose whether the members of its tenancy may read and edit it, as their workspace role allows (the default, today's behaviour), or only read it; show and change that choice where the design shows the members' row, and say in the embargo emails and the ended banner what members get when the embargo ends.

**Architecture:** One boolean column, `datasets.members_can_edit`, read in exactly one place: the last branch of `DatasetAccessService._permits`, where a tenancy member without an active embargo is let through by role. The access flags, the 404/403 answers and every route follow from that rule, as they already do for the embargo. An owner-only `MembersAccessService.set` behind `PUT /datasets/{id}/members-access` changes it and records it through `DatasetAccessAudit`. The webapp reads the value from the dataset payload, changes it through one BFF route and one dialog, and words it in one helper module.

**Tech Stack:** Gatekeeper: Python 3.10 (production image `python:3.10.14-alpine`), FastAPI 0.111, SQLAlchemy 1.4.23, Alembic, dependency-injector, Jinja2, pytest + `unittest.mock`, integration tests against Docker (PostgreSQL, MinIO, WireMock, Mailpit). Webapp: Next.js 14 (pages router), React 18, TypeScript, next-connect, axios, SWR, Formik, TailwindCSS, react-material-symbols, Jest + Testing Library.

**Spec:** the maintainer's decision of 2026-10-02 (members' access), on top of `docs/rfcs/003-dataset-embargo.md` (§Sharing: Access rule; §Embargo: Every route, Lifecycle; §Notifications). **Contracts:** `docs/superpowers/plans/2026-09-30-embargo-00-contracts.md`, section *Members' access (plan 06)*, which wins over this plan on any interface. **Design:** `docs/design/rfc-003-embargo/Embargo Feature.dc.html` §1a (creation), §1c (share dialog), §1d (dialogs), §1g (Settings), §1h (ended banner).

**Where the code goes.** Tasks 1–5 change the **gatekeeper** (`/Users/caio.maia/workspace/datamap/gatekeeper`); work in a worktree on `feat/embargo-06-members-access`, branched from the gatekeeper feature branch that already contains plans 01, 02 and 03. Tasks 6–11 change the **webapp** (`/Users/caio.maia/workspace/datamap/datamap-webapp`); work in a worktree on `feat/embargo-06-members-access`, branched from the branch that contains plan 05 (`feat/embargo-05-webapp` until it merges). Task 12 validates both. Paths are relative to the repo the task names.

**Verified against:** gatekeeper `feat/embargo-02-access` at `b73e10a` (plan 02 as built, on plan 01; `level_of` there already asks the role for `GET` through `reads_tenancy`) and plan 03 as written (`2026-09-30-embargo-03-gatekeeper-sharing-anonymous-links.md`, Tasks 8, 9, 12 and 13; not built when this plan was written); webapp `feat/embargo-05-webapp` at `9a3957c` (the branch was still taking review fixes; if it has moved, diff the files in *File Structure* against it before starting). Plan 03's code is quoted from its tasks: if its implementation named something differently, follow the implementation and keep this plan's behaviour.

## Global Constraints

- Migration revision id `a7b8c9d0e1f2`, `down_revision = "a8b9c0d1e2f3"` (plan 03's token hint, which followed its `f6a7b8c9d0e1`). The chain is 01 `d4e5f6a7b8c9` → 02 `e5f6a7b8c9d0` → 03 `f6a7b8c9d0e1` → `a8b9c0d1e2f3` → 06 `a7b8c9d0e1f2`; never re-point it.
- Column: `datasets.members_can_edit boolean NOT NULL DEFAULT true`. `true` is today's behaviour, so every existing dataset keeps it.
- The rule lives only in `DatasetAccessService._permits`: a tenancy member with no active embargo gets `READ_METADATA` and `READ_FILES` by role as today, and `WRITE` and `DELETE` by role only when `members_can_edit` is true. Nothing else reads the column to decide access. Search (`app/repository/dataset.py`) is unchanged.
- The setting is inert while an embargo is active and decides what members get back when it ends. It never touches permissions given through Share: `write` holders keep writing, the owner keeps everything, delete stays with the owner (and, in the default mode only, with a tenancy role that allows `DELETE`).
- Only the owner changes it: `DatasetAction.MANAGE_MEMBERS_ACCESS`. A caller who cannot see the dataset gets **404**; one who sees it and is not the owner gets **403** `{"detail": "forbidden"}`.
- Event type `members_access_changed`, `old_value {"members_can_edit": <before>}`, `new_value {"members_can_edit": <after>}`, written only through `DatasetAccessAudit.record`, only when the value changes.
- Casbin: no seed change. `PUT /api/v1/datasets/<uuid>/members-access` is covered by `datasets_write` (`/api/v1/datasets`, `(GET|POST|PUT)`) and `datasets_shared` (`/api/v1/datasets/[0-9a-f-]{36}(/.*)?$`).
- Python 3.10 in production: no syntax newer than 3.10. Type hints everywhere; dataclasses for models.
- Comments (CLAUDE.md): none narrating code; one line only where a reader would otherwise undo something on purpose.
- Copy, verbatim. Webapp:
  - Share dialog and Settings row, no embargo: `{N} people · can read and edit` / `{N} people · can read · editing limited to the people above`; during an embargo: `No access during the embargo · afterwards: read and edit` / `No access during the embargo · afterwards: read only`; the action is a `Change` link, owner only.
  - Set-embargo dialog and creation: `When the embargo ends, members of {T} can read and edit again.` / `When the embargo ends, members of {T} can read but not edit.`, followed by `Change`.
  - Ended banner: `Members of {T} can read and edit this dataset again; the people you shared it with keep their access.` / `Members of {T} can read this dataset; editing stays with the people you shared it with.`
  - Dialog: title `What members of {T} can do`; options `Read and edit` (`Their workspace role decides, as on any dataset of {T}.`) and `Read only` (`They read and download. Editing, uploads and new versions stay with you and the people you share it with as Can write.`); under an embargo, `Members have no access while the embargo lasts. This decides what they get when it ends.`; buttons `Save`, `Cancel`.
  - History: `let members of the workspace edit the dataset` (detail `was read only`) / `made the dataset read only for members of the workspace` (detail `was read and edit`).
- Copy, verbatim. Emails: the four sentences of the contracts' table, owner and collaborator variants.
- Webapp telemetry: UI event `members_access_changed`, emitted by `BFFAPI.setMembersAccess` after success.
- Webapp conventions (plan 05): component tests start with `/** @jest-environment jsdom */`, live in `__tests__` next to the component and import by relative path; dialogs through `components/base/PopupModal.tsx`; constants in `contants/`; Material Symbols `grade={-25} weight={400}`; amber only for "under embargo".
- Validation: gatekeeper `pytest`, the full integration suite (read the run; never pipe `make` into `tail`/`grep`), `ruff check`, `ruff check --fix`, `ruff format`; webapp `npm run test`, `npx tsc --noEmit`, `npm run build`.

## File Structure

Gatekeeper:

| File | Status | Responsibility |
|---|---|---|
| `app/model/db/dataset.py` | modify | `Dataset.members_can_edit` column |
| `migrations/versions/2026_10_02_1200-a7b8c9d0e1f2_add_members_can_edit.py` | create | Schema |
| `app/model/dataset_access.py`, `app/model/dataset_access_test.py` | modify | `DatasetAction.MANAGE_MEMBERS_ACCESS`, `AccessEventType.MEMBERS_ACCESS_CHANGED`, `MembersAccess` |
| `app/service/dataset_access.py`, `app/service/dataset_access_test.py` | modify | `allows_member_edits()`; the rule; owner-only action |
| `app/service/members_access.py`, `app/service/members_access_test.py` | create | `MembersAccessService.set` — change and record |
| `app/controller/v1/dataset/members_access.py` | create | `PUT /datasets/{id}/members-access` |
| `app/controller/v1/dataset/resource.py` | modify | `MembersAccessRequest`, `MembersAccessResponse`; `members_can_edit` on the dataset responses |
| `app/controller/v1/dataset/dataset.py` | modify | The three dataset adapters pass `members_can_edit` |
| `app/model/dataset.py` | modify | Domain `Dataset.members_can_edit` |
| `app/service/dataset.py`, `app/service/dataset_test.py` | modify | `_view` sets `members_can_edit` |
| `app/model/sharing.py`, `app/service/share.py`, `app/controller/v1/dataset/share_resource.py`, `app/service/share_test.py`, `app/service/share_preview_test.py` (plan 03) | modify | `ShareState.tenancy.members_can_edit` |
| `app/container.py`, `app/setup.py` | modify | `members_access_service`; the router |
| `app/resources/email_templates/embargo_reminder.{html,txt}`, `embargo_ended.{html,txt}` (plan 03) | modify | The members' sentence |
| `app/service/email_template_test.py` (plan 03) | modify | Contexts gain `members_can_edit`; the copy's tests |
| `app/service/notification.py`, `app/service/notification_test.py` (plan 03) | modify | The context key, from the dataset |
| `tests/integration/test_dataset_members_access.py` | create | End-to-end behaviour, on plan 02's fixtures |

Webapp:

| File | Status | Responsibility |
|---|---|---|
| `types/GatekeeperAPI.ts`, `types/BffAPI.ts` | modify | `MembersAccessRequest`, `MembersAccessResponse`, `members_can_edit` on `ShareTenancy` and the dataset responses |
| `lib/share.ts`, `lib/__tests__/share.test.ts` | modify | `setMembersAccess` server call |
| `pages/api/datasets/[datasetId]/members-access.ts`, `lib/__tests__/membersAccessRoute.test.ts` | create | BFF route |
| `gateways/BFFAPI.ts`, `gateways/__tests__/BFFAPI.embargo.test.ts` | modify | `setMembersAccess`, with the UI event |
| `contants/TelemetryConstants.ts`, `contants/__tests__/TelemetryConstants.test.ts` | modify | `members_access_changed` |
| `lib/membersAccess.ts`, `lib/__tests__/membersAccess.test.ts` | create | Every wording and decision about the members' row |
| `components/Share/MembersAccessDialog.tsx`, `components/Share/__tests__/MembersAccessDialog.test.tsx` | create | The two-option dialog |
| `hooks/UseMembersAccess.ts` | create | Save, refresh the page's props, report the error |
| `components/Share/AccessList.tsx`, `components/Share/ShareDialog.tsx` and their tests | modify | The members' row with Change (§1c) |
| `components/Embargo/AccessSummary.tsx`, `components/Embargo/__tests__/AccessSummary.test.tsx` | modify / create | The same row in Settings → Access (§1g) |
| `components/Embargo/EmbargoFields.tsx`, `components/Embargo/SetEmbargoDialog.tsx`, `pages/app/datasets/new.tsx`, `types/new-dataset.d.ts` and tests | modify | The line under the mode choice; the value sent before the embargo (§1a, §1d) |
| `components/Embargo/EmbargoEndedBanner.tsx` and its test | modify | The outcome sentence (§1h) |
| `lib/embargoDisplay.ts`, `lib/__tests__/embargoDisplay.test.ts` | modify | History wording |

## Task order and parallelism

| Task | Repo | Depends on | Can run in parallel with |
|---|---|---|---|
| 1 Column, migration and the rule | gatekeeper | plans 01–03 merged | 6, 7 |
| 2 The owner's route and its audit | gatekeeper | 1 | 3, 4 |
| 3 Payloads: every dataset object and the share state | gatekeeper | 1 | 2, 4 |
| 4 The members' sentence in the embargo emails | gatekeeper | 1 | 2, 3 |
| 5 Integration tests | gatekeeper | 2, 3 | 6–11 |
| 6 Types, server call, BFF route, BFFAPI, telemetry | webapp | plan 05 merged | 1–5, 7 |
| 7 Wording, the members dialog and its hook | webapp | 6 | 1–5 |
| 8 Share dialog row | webapp | 7 | 9, 10, 11 |
| 9 Settings → Access row | webapp | 7 | 8, 10, 11 |
| 10 Set-embargo dialog and creation | webapp | 7 | 8, 9, 11 |
| 11 Ended banner and History | webapp | 7 | 8, 9, 10 |
| 12 Validation | both | all | — |

Tasks 8 and 9 both import `components/Share/ShareDialog.tsx` (9 renders it): if they share a worktree, run 9 after 8. The webapp works against mocks until Task 5's gatekeeper is up; Task 12's manual walk needs both.

---

### Task 1: Column, migration and the rule

**Repo:** gatekeeper.

The whole feature is one branch of the access rule. Everything that decides what a member may do — every route through `fetch_authorized`, the TUS hook, the access flags — already goes through `DatasetAccessService._permits`, so the rule changes there and nowhere else.

**Files:**
- Modify: `app/model/db/dataset.py` (`Dataset`, after `embargo_note`)
- Create: `migrations/versions/2026_10_02_1200-a7b8c9d0e1f2_add_members_can_edit.py`
- Modify: `app/service/dataset_access.py` (module function; the last branch of `_permits`)
- Test: `app/service/dataset_access_test.py` (the `_dataset` helper; append tests)

**Interfaces:**
- Consumes: plan 02's `DatasetAccessService`, `DatasetAction`, `AccessLevel`, `_ROLE_METHOD`; plan 03's migrations `f6a7b8c9d0e1` and `a8b9c0d1e2f3`.
- Produces: ORM `Dataset.members_can_edit: bool` (NOT NULL, default true); `allows_member_edits(dataset) -> bool` in `app/service/dataset_access.py`, which Tasks 2, 3 and 4 import.

- [ ] **Step 1: Write the failing tests**

In `app/service/dataset_access_test.py`, change the import of the service to:

```python
from app.service.dataset_access import DatasetAccessService, allows_member_edits
```

replace the `_dataset` helper with:

```python
def _dataset(
    owner_id=None, until=None, visible=False, tenancy=TENANCY, members_can_edit=True
):
    return DatasetDBModel(
        id=uuid4(),
        name="d",
        data={},
        owner_id=owner_id,
        tenancy=tenancy,
        embargo_until=until,
        embargo_metadata_visible=visible,
        embargo_note=None,
        members_can_edit=members_can_edit,
    )
```

and append to the end of the file:

```python
class TestMembersAccess(unittest.TestCase):
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

    def _permits(self, dataset, action, tenancies=(TENANCY,)):
        return self.access.permits(self.user_id, dataset, list(tenancies), action, NOW)

    def test_read_only_members_still_read_and_download(self):
        dataset = _dataset(owner_id=uuid4(), members_can_edit=False)

        self.assertTrue(self._permits(dataset, DatasetAction.READ_METADATA))
        self.assertTrue(self._permits(dataset, DatasetAction.READ_FILES))

    def test_read_only_members_neither_write_nor_delete_whatever_their_role(self):
        dataset = _dataset(owner_id=uuid4(), members_can_edit=False)

        self.assertFalse(self._permits(dataset, DatasetAction.WRITE))
        self.assertFalse(self._permits(dataset, DatasetAction.DELETE))
        asked = [call.kwargs["action"] for call in self.users.enforce.call_args_list]
        self.assertNotIn("PUT", asked)
        self.assertNotIn("DELETE", asked)

    def test_by_default_members_write_and_delete_as_their_role_allows(self):
        dataset = _dataset(owner_id=uuid4())

        self.assertTrue(self._permits(dataset, DatasetAction.WRITE))
        self.assertTrue(self._permits(dataset, DatasetAction.DELETE))

    def test_a_read_permission_does_not_borrow_the_roles_write_in_read_only_mode(self):
        self._grant("read")
        dataset = _dataset(owner_id=uuid4())
        self.assertTrue(self._permits(dataset, DatasetAction.WRITE))

        dataset.members_can_edit = False

        self.assertFalse(self._permits(dataset, DatasetAction.WRITE))
        self.assertTrue(self._permits(dataset, DatasetAction.READ_FILES))

    def test_a_write_permission_still_writes_in_read_only_mode(self):
        self._grant("write")
        dataset = _dataset(owner_id=uuid4(), members_can_edit=False)

        self.assertTrue(self._permits(dataset, DatasetAction.WRITE, tenancies=()))
        self.assertTrue(self._permits(dataset, DatasetAction.WRITE))
        self.assertFalse(self._permits(dataset, DatasetAction.DELETE))

    def test_the_owner_keeps_everything_in_read_only_mode(self):
        dataset = _dataset(owner_id=self.user_id, members_can_edit=False)

        flags = self.access.access_flags(
            self.user_id, dataset, [TENANCY], AccessLevel.OWNER, NOW
        )

        self.assertTrue(flags.can_edit)
        self.assertTrue(flags.can_share)
        self.assertTrue(flags.can_delete)

    def test_the_flags_of_a_read_only_member(self):
        dataset = _dataset(owner_id=uuid4(), members_can_edit=False)

        flags = self.access.access_flags(
            self.user_id, dataset, [TENANCY], AccessLevel.TENANCY, NOW
        )

        self.assertEqual(flags.level, AccessLevel.TENANCY)
        self.assertFalse(flags.can_edit)
        self.assertFalse(flags.can_share)
        self.assertFalse(flags.can_delete)
        self.assertFalse(flags.can_manage_embargo)

    def test_the_setting_is_inert_during_an_embargo(self):
        for members_can_edit in (True, False):
            with self.subTest(members_can_edit=members_can_edit):
                dataset = _dataset(
                    owner_id=uuid4(),
                    until=NOW + timedelta(days=5),
                    visible=True,
                    members_can_edit=members_can_edit,
                )

                self.assertTrue(self._permits(dataset, DatasetAction.READ_METADATA))
                self.assertFalse(self._permits(dataset, DatasetAction.READ_FILES))
                self.assertFalse(self._permits(dataset, DatasetAction.WRITE))

    def test_the_setting_decides_what_members_get_back_when_the_embargo_ends(self):
        ended = NOW - timedelta(seconds=1)
        read_only = _dataset(owner_id=uuid4(), until=ended, members_can_edit=False)
        editable = _dataset(owner_id=uuid4(), until=ended, members_can_edit=True)

        self.assertTrue(self._permits(read_only, DatasetAction.READ_FILES))
        self.assertFalse(self._permits(read_only, DatasetAction.WRITE))
        self.assertTrue(self._permits(editable, DatasetAction.WRITE))

    def test_a_row_not_yet_flushed_reads_as_the_default(self):
        dataset = _dataset(owner_id=uuid4())
        dataset.members_can_edit = None

        self.assertTrue(allows_member_edits(dataset))
        self.assertTrue(self._permits(dataset, DatasetAction.WRITE))
        self.assertFalse(allows_member_edits(_dataset(members_can_edit=False)))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest app/service/dataset_access_test.py -v`
Expected: collection error — `ImportError: cannot import name 'allows_member_edits' from 'app.service.dataset_access'`.

- [ ] **Step 3: Add the column** — `app/model/db/dataset.py`

In `Dataset`, after `embargo_note = Column(Text, nullable=True)`:

```python
    members_can_edit = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sqlalchemy.true(),
    )
```

- [ ] **Step 4: Write the rule** — `app/service/dataset_access.py`

Add, after the `_PERMISSION_ACTIONS` dictionary:

```python
def allows_member_edits(dataset: DatasetDBModel) -> bool:
    # None is a row not flushed yet, whose column default is true; `not None` would read it as read-only.
    return dataset.members_can_edit is not False
```

In `_permits`, the last line, `return self._role_allows(user_id, _ROLE_METHOD[action])`, becomes:

```python
        if action in (
            DatasetAction.WRITE,
            DatasetAction.DELETE,
        ) and not allows_member_edits(dataset):
            return False
        return self._role_allows(user_id, _ROLE_METHOD[action])
```

The branches above it are unchanged: the owner returns first, a permission's own actions return before the tenancy is looked at, and an active embargo returns before this line. That is what makes the setting inert during an embargo and leaves permissions alone.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest app/service/dataset_access_test.py -v`
Expected: PASS — plan 02's tests and the 10 in `TestMembersAccess`.

- [ ] **Step 6: Write the migration** — `migrations/versions/2026_10_02_1200-a7b8c9d0e1f2_add_members_can_edit.py`

```python
"""Members of a dataset's tenancy may edit it, or only read it

Revision ID: a7b8c9d0e1f2
Revises: a8b9c0d1e2f3
Create Date: 2026-10-02 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column(
            "members_can_edit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("datasets", "members_can_edit")
```

The server default fills every existing row with `true`, so no dataset changes behaviour on deploy.

- [ ] **Step 7: Verify the migration against a real database**

Run:
```bash
make ENV_FILE_PATH=local.env docker-run-db
make ENV_FILE_PATH=local.env db-upgrade
make ENV_FILE_PATH=local.env db-downgrade
make ENV_FILE_PATH=local.env db-upgrade
```
Expected: each command exits 0; the round trip shows `Running downgrade a7b8c9d0e1f2 -> a8b9c0d1e2f3` and `Running upgrade a8b9c0d1e2f3 -> a7b8c9d0e1f2`.

Then check autogenerate proposes nothing:
```bash
make ENV_FILE_PATH=local.env MESSAGE="check members access parity" db-create-migration
```
Expected: the generated file's `upgrade()` and `downgrade()` contain only `pass`. Delete that generated file.

- [ ] **Step 8: Run the unit suite**

Run: `python -m pytest`
Expected: PASS. Tests that build a `DatasetDBModel` without the new field get `None`, which `allows_member_edits` reads as the default.

- [ ] **Step 9: Commit**

```bash
git add app/model/db/dataset.py app/service/dataset_access.py app/service/dataset_access_test.py "migrations/versions/2026_10_02_1200-a7b8c9d0e1f2_add_members_can_edit.py"
git commit -m "feat: members of a dataset's tenancy can be limited to reading it"
```

---

### Task 2: The owner's route and its audit

**Repo:** gatekeeper.

**Files:**
- Modify: `app/model/dataset_access.py` (`DatasetAction`, `AccessEventType`, `MembersAccess`)
- Modify: `app/model/dataset_access_test.py` (append)
- Modify: `app/service/dataset_access.py` (owner-only actions in `_permits`)
- Modify: `app/service/dataset_access_test.py` (append to `TestMembersAccess`)
- Create: `app/service/members_access.py`, `app/service/members_access_test.py`
- Modify: `app/controller/v1/dataset/resource.py` (append two models)
- Create: `app/controller/v1/dataset/members_access.py`
- Modify: `app/container.py` (wiring module, provider), `app/setup.py` (router)

**Interfaces:**
- Consumes: Task 1's `allows_member_edits`; plan 02's `DatasetService.fetch_authorized`, `DatasetRepository.upsert(dataset=...)`, `DatasetAccessService.access_flags`, `DatasetAccessAudit.record`, `utcnow`, `ForbiddenException`, `parse_user_header`, `parse_tenancy_header`, `AccessResponse`.
- Produces:
  - `DatasetAction.MANAGE_MEMBERS_ACCESS = "manage_members_access"`, owner only.
  - `AccessEventType.MEMBERS_ACCESS_CHANGED = "members_access_changed"`.
  - `@dataclass MembersAccess(members_can_edit: bool, access: DatasetAccess)`.
  - `MembersAccessService.set(dataset_id: UUID, user_id: UUID, tenancies: list[str] | None, members_can_edit: bool) -> MembersAccess`; container provider `members_access_service`.
  - `PUT /api/v1/datasets/{dataset_id}/members-access`, body `MembersAccessRequest {members_can_edit: StrictBool}`, answer `MembersAccessResponse {members_can_edit: bool, access: AccessResponse}`.

- [ ] **Step 1: Write the failing tests**

Append to `app/model/dataset_access_test.py`, inside `TestAccessModel`:

```python
    def test_the_members_access_event_and_action_have_their_contract_values(self):
        from app.model.dataset_access import DatasetAction

        self.assertEqual(
            AccessEventType.MEMBERS_ACCESS_CHANGED.value, "members_access_changed"
        )
        self.assertEqual(
            DatasetAction.MANAGE_MEMBERS_ACCESS.value, "manage_members_access"
        )
```

Append to `TestMembersAccess` in `app/service/dataset_access_test.py`:

```python
    def test_only_the_owner_changes_what_members_can_do(self):
        dataset = _dataset(owner_id=self.user_id)
        self.assertTrue(
            self._permits(dataset, DatasetAction.MANAGE_MEMBERS_ACCESS)
        )

        self._grant("write")
        others = _dataset(owner_id=uuid4())

        self.assertFalse(self._permits(others, DatasetAction.MANAGE_MEMBERS_ACCESS))
        self.users.enforce.assert_not_called()
```

Create `app/service/members_access_test.py`:

```python
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

from app.exception.forbidden import ForbiddenException
from app.model.dataset import VisibilityStatus
from app.model.dataset_access import AccessEventType, AccessLevel, DatasetAction
from app.model.db.dataset import Dataset as DatasetDBModel
from app.repository.dataset import DatasetRepository
from app.service.dataset import DatasetService
from app.service.dataset_access import DatasetAccessService
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.members_access import MembersAccessService

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


class TestMembersAccessService(unittest.TestCase):
    def setUp(self):
        self.datasets = Mock(spec=DatasetService)
        self.repository = Mock(spec=DatasetRepository)
        self.audit = Mock(spec=DatasetAccessAudit)
        self.service = MembersAccessService(
            dataset_service=self.datasets,
            repository=self.repository,
            access_service=DatasetAccessService(
                permission_repository=Mock(), user_service=Mock()
            ),
            audit=self.audit,
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
            members_can_edit=True,
        )
        self.datasets.fetch_authorized.return_value = (
            self.dataset,
            ["t"],
            AccessLevel.OWNER,
        )
        for target in (
            "app.service.members_access.utcnow",
            "app.service.dataset_access.utcnow",
        ):
            patcher = patch(target, return_value=NOW)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _set(self, members_can_edit: bool):
        return self.service.set(
            dataset_id=self.dataset.id,
            user_id=self.user_id,
            tenancies=None,
            members_can_edit=members_can_edit,
        )

    def test_the_owner_makes_members_read_only_and_it_is_recorded(self):
        result = self._set(False)

        self.assertFalse(self.dataset.members_can_edit)
        self.repository.upsert.assert_called_once_with(dataset=self.dataset)
        self.audit.record.assert_called_once_with(
            dataset_id=self.dataset.id,
            event_type=AccessEventType.MEMBERS_ACCESS_CHANGED,
            changed_by=self.user_id,
            old_value={"members_can_edit": True},
            new_value={"members_can_edit": False},
        )
        self.assertFalse(result.members_can_edit)
        self.assertEqual(result.access.level, AccessLevel.OWNER)
        self.assertTrue(result.access.can_edit)

    def test_the_change_is_asked_of_the_access_rule_as_an_owner_action(self):
        self._set(False)

        self.assertEqual(
            self.datasets.fetch_authorized.call_args.kwargs["action"],
            DatasetAction.MANAGE_MEMBERS_ACCESS,
        )

    def test_setting_the_value_it_already_has_changes_and_records_nothing(self):
        result = self._set(True)

        self.repository.upsert.assert_not_called()
        self.audit.record.assert_not_called()
        self.assertTrue(result.members_can_edit)

    def test_it_can_be_changed_during_an_embargo(self):
        self.dataset.embargo_until = NOW + timedelta(days=30)

        result = self._set(False)

        self.assertFalse(result.members_can_edit)
        self.audit.record.assert_called_once()

    def test_a_caller_who_is_not_the_owner_is_refused_before_anything_changes(self):
        self.datasets.fetch_authorized.side_effect = ForbiddenException("forbidden")

        with self.assertRaises(ForbiddenException):
            self._set(False)

        self.assertTrue(self.dataset.members_can_edit)
        self.repository.upsert.assert_not_called()
        self.audit.record.assert_not_called()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest app/model/dataset_access_test.py app/service/dataset_access_test.py app/service/members_access_test.py -v`
Expected: FAIL — `AttributeError: MEMBERS_ACCESS_CHANGED`, `AttributeError: MANAGE_MEMBERS_ACCESS`, and `ModuleNotFoundError: No module named 'app.service.members_access'`.

- [ ] **Step 3: The model** — `app/model/dataset_access.py`

Add to `DatasetAction`, after `MANAGE_EMBARGO = "manage_embargo"`:

```python
    MANAGE_MEMBERS_ACCESS = "manage_members_access"
```

Add to `AccessEventType`, after the last member (plan 03 added `NOTE_CHANGED`):

```python
    MEMBERS_ACCESS_CHANGED = "members_access_changed"
```

Append at the end of the module:

```python
@dataclass
class MembersAccess:
    members_can_edit: bool
    access: DatasetAccess
```

- [ ] **Step 4: Only the owner** — `app/service/dataset_access.py`

Add, next to `_PERMISSION_ACTIONS`:

```python
_OWNER_ONLY_ACTIONS = frozenset(
    {DatasetAction.MANAGE_EMBARGO, DatasetAction.MANAGE_MEMBERS_ACCESS}
)
```

In `_permits`, the two lines

```python
        if action == DatasetAction.MANAGE_EMBARGO:
            return False
```

become:

```python
        if action in _OWNER_ONLY_ACTIONS:
            return False
```

They sit right after `if level == AccessLevel.OWNER: return True`, so the owner is let through and nobody else reaches the role check.

- [ ] **Step 5: The service** — `app/service/members_access.py`

```python
from uuid import UUID

from app.model.dataset_access import (
    AccessEventType,
    DatasetAction,
    MembersAccess,
    utcnow,
)
from app.repository.dataset import DatasetRepository
from app.service.dataset import DatasetService
from app.service.dataset_access import DatasetAccessService, allows_member_edits
from app.service.dataset_access_audit import DatasetAccessAudit


class MembersAccessService:
    def __init__(
        self,
        dataset_service: DatasetService,
        repository: DatasetRepository,
        access_service: DatasetAccessService,
        audit: DatasetAccessAudit,
    ) -> None:
        self._datasets = dataset_service
        self._repository = repository
        self._access = access_service
        self._audit = audit

    def set(
        self,
        dataset_id: UUID,
        user_id: UUID,
        tenancies: list[str] | None,
        members_can_edit: bool,
    ) -> MembersAccess:
        dataset, allowed, level = self._datasets.fetch_authorized(
            dataset_id=dataset_id,
            user_id=user_id,
            tenancies=tenancies,
            action=DatasetAction.MANAGE_MEMBERS_ACCESS,
        )
        before = allows_member_edits(dataset)
        if before != members_can_edit:
            dataset.members_can_edit = members_can_edit
            self._repository.upsert(dataset=dataset)
            self._audit.record(
                dataset_id=dataset.id,
                event_type=AccessEventType.MEMBERS_ACCESS_CHANGED,
                changed_by=user_id,
                old_value={"members_can_edit": before},
                new_value={"members_can_edit": members_can_edit},
            )
        return MembersAccess(
            members_can_edit=allows_member_edits(dataset),
            access=self._access.access_flags(
                user_id=user_id,
                dataset=dataset,
                tenancies=allowed,
                level=level,
                now=utcnow(),
            ),
        )
```

- [ ] **Step 6: Run the unit tests to verify they pass**

Run: `python -m pytest app/model/dataset_access_test.py app/service/dataset_access_test.py app/service/members_access_test.py -v`
Expected: PASS (5 tests in `TestMembersAccessService`, 11 in `TestMembersAccess`).

- [ ] **Step 7: Request and response** — append to `app/controller/v1/dataset/resource.py`

Add `StrictBool` to the pydantic import (`from pydantic import BaseModel, Field, StrictBool`), then append:

```python
class MembersAccessRequest(BaseModel):
    members_can_edit: StrictBool = Field(
        ..., title="Members of the tenancy may edit (true) or only read (false)"
    )


class MembersAccessResponse(BaseModel):
    members_can_edit: bool = Field(
        ..., title="Members of the tenancy may edit when no embargo is active"
    )
    access: AccessResponse = Field(..., title="What the caller may do")
```

`StrictBool` refuses `"false"`, `0` and `1`: a string that reads like a boolean would otherwise be coerced, and the wrong mode stored.

- [ ] **Step 8: The route** — `app/controller/v1/dataset/members_access.py`

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
    AccessResponse,
    MembersAccessRequest,
    MembersAccessResponse,
)
from app.service.members_access import MembersAccessService

router = APIRouter(
    prefix="/datasets",
    tags=["members-access"],
    dependencies=[Depends(authenticate), Depends(authorize)],
    responses={404: {"description": "Not found"}},
)


# PUT /datasets/{dataset_id}/members-access
@router.put("/{dataset_id}/members-access")
@inject
def set_members_access(
    dataset_id: UUID,
    request: MembersAccessRequest,
    user_id: UUID = Depends(parse_user_header),
    tenancies: list[str] = Depends(parse_tenancy_header),
    service: MembersAccessService = Depends(
        Provide[Container.members_access_service]
    ),
) -> MembersAccessResponse:
    result = service.set(
        dataset_id=dataset_id,
        user_id=user_id,
        tenancies=tenancies,
        members_can_edit=request.members_can_edit,
    )
    return MembersAccessResponse(
        members_can_edit=result.members_can_edit,
        access=AccessResponse(
            level=result.access.level.value,
            can_edit=result.access.can_edit,
            can_share=result.access.can_share,
            can_manage_embargo=result.access.can_manage_embargo,
            can_extend_embargo=result.access.can_extend_embargo,
            can_delete=result.access.can_delete,
        ),
    )
```

- [ ] **Step 9: Wiring** — `app/container.py` and `app/setup.py`

In `app/container.py`, add the import next to the other services:

```python
from app.service.members_access import MembersAccessService
```

add `"app.controller.v1.dataset.members_access",` to `wiring_config.modules`, right after `"app.controller.v1.dataset.embargo_status",`, and the provider after `embargo_service`:

```python
    members_access_service = providers.Factory(
        MembersAccessService,
        dataset_service=dataset_service,
        repository=dataset_repository,
        access_service=dataset_access_service,
        audit=dataset_access_audit,
    )
```

In `app/setup.py`, add the import after the `embargo_status_router` import:

```python
from app.controller.v1.dataset.members_access import router as members_access_router
```

and, after `fastAPIApp.include_router(embargo_status_router, prefix="/v1")`:

```python
    fastAPIApp.include_router(members_access_router, prefix="/v1")
```

- [ ] **Step 10: Check the route is guarded and the app starts**

Run: `python -m pytest app/controller/routes_security_test.py -v && python -c "from app.setup import setup_routes; from fastapi import FastAPI; app = FastAPI(); setup_routes(app); print(sorted(r.path for r in app.routes if 'members-access' in r.path))"`
Expected: PASS (the router carries `authenticate` and `authorize`), then `['/v1/datasets/{dataset_id}/members-access']`.

- [ ] **Step 11: Commit**

```bash
git add app/model/dataset_access.py app/model/dataset_access_test.py app/service/dataset_access.py app/service/dataset_access_test.py app/service/members_access.py app/service/members_access_test.py app/controller/v1/dataset/resource.py app/controller/v1/dataset/members_access.py app/container.py app/setup.py
git commit -m "feat: the owner decides whether members may edit, and the change is recorded"
```

---

### Task 3: Payloads: every dataset object and the share state

**Repo:** gatekeeper.

Every dataset object the webapp reads passes through `DatasetService._view` (plan 02), so the value is set there once, for detail, version and list items alike, minimal ones included. The share state's tenancy row (plan 03 Task 12) carries it too, for the dialog that already reads that row.

**Files:**
- Modify: `app/model/dataset.py` (`Dataset`)
- Modify: `app/service/dataset.py` (`_view`)
- Modify: `app/controller/v1/dataset/resource.py` (`DatasetGetResponse`, `DatasetVersionGetResponse`)
- Modify: `app/controller/v1/dataset/dataset.py` (`_adapt_dataset`, `_adapt_minimal_dataset`, `_adapt_dataset_specific_version`)
- Modify: `app/model/sharing.py` (`TenancyAccess`), `app/service/share.py` (`state`), `app/controller/v1/dataset/share_resource.py` (`TenancyAccessResponse`, `adapt_share_state`)
- Test: `app/service/dataset_test.py` (append), `app/service/share_test.py` (`ShareServiceTestCase`), `app/service/share_preview_test.py` (append)

**Interfaces:**
- Consumes: Task 1's `allows_member_edits`; plan 02's `_view`; plan 03 Task 12's `TenancyAccess`, `TenancyAccessResponse`, `ShareService.state`, `ShareServiceTestCase`.
- Produces: domain `Dataset.members_can_edit: bool = True`; `"members_can_edit": bool` on `GET /datasets/{id}`, `GET /datasets/{id}/versions/{v}` and every `GET /datasets/` item; `TenancyAccess.members_can_edit: bool`, `"tenancy": {..., "members_can_edit": bool}` on `GET /datasets/{id}/share`.

- [ ] **Step 1: Write the failing tests**

Append to `TestDatasetService` in `app/service/dataset_test.py`:

```python
    def test_every_item_says_whether_members_can_edit(self):
        self.user_service.fetch_by_id.return_value = self.mock_user([])
        read_only = Mock(spec=DatasetDBModel)
        read_only.versions = []
        read_only.members_can_edit = False
        editable = Mock(spec=DatasetDBModel)
        editable.versions = []
        editable.members_can_edit = True
        self.dataset_repository.search.return_value = PaginatedResult(
            items=[read_only, editable], total_count=2, page=1, page_size=10
        )

        with patch.object(
            self.dataset_service,
            "_adapt_minimal_dataset",
            side_effect=lambda dataset: SimpleNamespace(
                versions=[], current_version=None, version=None
            ),
        ):
            result = self.dataset_service.search_datasets(
                query=DatasetQuery(minimal=True), user_id=uuid4()
            )

        self.assertEqual(
            [item.members_can_edit for item in result.items], [False, True]
        )
```

In `app/service/share_test.py`, add `members_can_edit=True,` to the `SimpleNamespace` that `ShareServiceTestCase.setUp` assigns to `self.dataset` (after `embargo_note=...`). Then append to `TestStateExtras` in `app/service/share_preview_test.py`:

```python
    def test_the_tenancy_row_says_what_members_can_do(self):
        self.invitations.list_for_dataset.return_value = []
        self.anonymous_links.list_with_views.return_value = []
        self.users.count_in_tenancy.return_value = 14
        self.dataset.embargo_until = None

        self.assertTrue(self.service.state(self.dataset.id, OWNER).tenancy.members_can_edit)

        self.dataset.members_can_edit = False

        self.assertFalse(self.service.state(self.dataset.id, OWNER).tenancy.members_can_edit)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest app/service/dataset_test.py app/service/share_preview_test.py -k "members_can_edit or members_can_do" -v`
Expected: FAIL — `AttributeError: 'types.SimpleNamespace' object has no attribute 'members_can_edit'` (the view sets nothing yet) and `AttributeError: 'TenancyAccess' object has no attribute 'members_can_edit'`.

- [ ] **Step 3: The domain and the view**

In `app/model/dataset.py`, add to `Dataset` after its last field (plan 03 added `owner_name`):

```python
    members_can_edit: bool = True
```

In `app/service/dataset.py`, change the import of the access service to:

```python
from app.service.dataset_access import DatasetAccessService, allows_member_edits
```

and in `_view`, after `adapted.embargo = self._access.embargo_of(dataset_db, now)`:

```python
        adapted.members_can_edit = allows_member_edits(dataset_db)
```

- [ ] **Step 4: The share state**

In `app/model/sharing.py`, add to `TenancyAccess` after `members: int`:

```python
    members_can_edit: bool = True
```

In `app/service/share.py`, import `allows_member_edits` from `app.service.dataset_access`, and in `state` the `TenancyAccess(...)` call gains:

```python
                members_can_edit=allows_member_edits(dataset),
```

In `app/controller/v1/dataset/share_resource.py`, add to `TenancyAccessResponse` after `members: int`:

```python
    members_can_edit: bool = True
```

and in `adapt_share_state` the `TenancyAccessResponse(...)` call becomes:

```python
        tenancy=TenancyAccessResponse(
            name=state.tenancy.name,
            path=state.tenancy.path,
            members=state.tenancy.members,
            members_can_edit=state.tenancy.members_can_edit,
        )
        if state.tenancy
        else None,
```

- [ ] **Step 5: The responses**

In `app/controller/v1/dataset/resource.py`, add to `DatasetGetResponse` and to `DatasetVersionGetResponse`, after `access`:

```python
    members_can_edit: bool = Field(
        True, title="Members of the tenancy may edit when no embargo is active"
    )
```

In `app/controller/v1/dataset/dataset.py`, `_adapt_dataset`, `_adapt_minimal_dataset` and `_adapt_dataset_specific_version` each gain, after `access=_adapt_access(dataset.access),`:

```python
        members_can_edit=dataset.members_can_edit,
```

`_adapt_minimal_dataset` already answers with `DatasetGetResponse`, so the minimal list items carry the field with no model of their own. `DatasetCreateResponse` is left as it is: it carries neither `embargo` nor `access`, and the webapp reads the created dataset again before showing it.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest app/service/dataset_test.py app/service/share_test.py app/service/share_preview_test.py app/controller -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/model/dataset.py app/service/dataset.py app/service/dataset_test.py app/controller/v1/dataset/resource.py app/controller/v1/dataset/dataset.py app/model/sharing.py app/service/share.py app/controller/v1/dataset/share_resource.py app/service/share_test.py app/service/share_preview_test.py
git commit -m "feat: every dataset and the share dialog's members row say whether members can edit"
```

---

### Task 4: The members' sentence in the embargo emails

**Repo:** gatekeeper.

Plan 03's reminder and end-of-embargo messages say the files become available to every member of the tenancy. They now also say what those members may do with the dataset, which this setting decides. The sentence sits right after each message's first paragraph, in the owner's and the collaborators' copy, in HTML and in text. The key is required: `StrictUndefined` makes a context without it fail in the test suite rather than send a message that guesses.

**Files:**
- Modify: `app/resources/email_templates/embargo_reminder.html`, `embargo_reminder.txt`, `embargo_ended.html`, `embargo_ended.txt` (plan 03 Task 8)
- Modify: `app/service/email_template_test.py` (the two contexts; append a test class)
- Modify: `app/service/notification.py` (the context), `app/service/notification_test.py`

**Interfaces:**
- Consumes: Task 1's `allows_member_edits`; plan 03's templates, `EmailTemplateRenderer`, `CONTEXTS`, `REMINDER`, `COLLABORATOR_REMINDER`, `ENDED`, `COLLABORATOR_ENDED`, `SITE_URL`, `UndefinedError` in `email_template_test.py`; `EmbargoNotificationService._queue_for_people`.
- Produces: required context key `members_can_edit: bool` for `embargo_reminder` and `embargo_ended`; `EmbargoNotificationService` sets it from the dataset.

- [ ] **Step 1: Write the failing template tests**

In `app/service/email_template_test.py`, add `"members_can_edit": True,` to `CONTEXTS[EmailTemplate.EMBARGO_REMINDER]` and to `CONTEXTS[EmailTemplate.EMBARGO_ENDED]` (after `"tenancy_name": "Data Amazon",` in each). `REMINDER`, `COLLABORATOR_REMINDER`, `ENDED` and `COLLABORATOR_ENDED` are built from them and inherit it. Then append at the end of the file:

```python
class TestMembersSentence(unittest.TestCase):
    def setUp(self):
        self.renderer = EmailTemplateRenderer(site_url=SITE_URL)

    def render(self, template, context):
        return self.renderer.render(template, context)

    def assert_in_both(self, sentence, email):
        self.assertIn(sentence, email.html)
        self.assertIn(sentence, email.text)

    def test_the_owner_reminder_says_members_can_edit_again(self):
        email = self.render(EmailTemplate.EMBARGO_REMINDER, REMINDER)

        self.assert_in_both(
            "When the embargo ends, members of Data Amazon can read and edit this dataset again; "
            "the people you shared it with keep their access.",
            email,
        )

    def test_the_owner_reminder_says_editing_stays_with_the_people_shared_with(self):
        email = self.render(EmailTemplate.EMBARGO_REMINDER, {**REMINDER, "members_can_edit": False})

        self.assert_in_both(
            "When the embargo ends, members of Data Amazon can read this dataset; "
            "editing stays with the people you shared it with.",
            email,
        )
        self.assertNotIn("can read and edit", email.text)

    def test_the_collaborator_reminder_names_the_owner(self):
        editable = self.render(EmailTemplate.EMBARGO_REMINDER, COLLABORATOR_REMINDER)
        read_only = self.render(
            EmailTemplate.EMBARGO_REMINDER, {**COLLABORATOR_REMINDER, "members_can_edit": False}
        )

        self.assert_in_both(
            "When the embargo ends, members of Data Amazon can read and edit this dataset again; "
            "the people Luciana Rizzo shared it with keep their access.",
            editable,
        )
        self.assert_in_both(
            "When the embargo ends, members of Data Amazon can read this dataset; "
            "editing stays with Luciana Rizzo and the people they shared it with.",
            read_only,
        )

    def test_the_owner_end_notice_says_what_members_got_back(self):
        editable = self.render(EmailTemplate.EMBARGO_ENDED, ENDED)
        read_only = self.render(EmailTemplate.EMBARGO_ENDED, {**ENDED, "members_can_edit": False})

        self.assert_in_both(
            "Members of Data Amazon can read and edit this dataset again; "
            "the people you shared it with keep their access.",
            editable,
        )
        self.assert_in_both(
            "Members of Data Amazon can read this dataset; "
            "editing stays with the people you shared it with.",
            read_only,
        )

    def test_the_collaborator_end_notice_names_the_owner(self):
        email = self.render(
            EmailTemplate.EMBARGO_ENDED, {**COLLABORATOR_ENDED, "members_can_edit": False}
        )

        self.assert_in_both(
            "Members of Data Amazon can read this dataset; "
            "editing stays with Luciana Rizzo and the people they shared it with.",
            email,
        )

    def test_an_end_by_manual_doi_says_it_too(self):
        email = self.render(
            EmailTemplate.EMBARGO_ENDED,
            {**ENDED, "doi": "10.1029/2026JD041877", "ended_early": True, "ended_by_manual_doi": True},
        )

        self.assert_in_both(
            "Members of Data Amazon can read and edit this dataset again; "
            "the people you shared it with keep their access.",
            email,
        )

    def test_the_sentence_is_a_paragraph_of_its_own_in_the_text(self):
        reminder = self.render(EmailTemplate.EMBARGO_REMINDER, REMINDER).text
        ended = self.render(EmailTemplate.EMBARGO_ENDED, COLLABORATOR_ENDED).text

        self.assertIn("\n\nWhen the embargo ends, members of Data Amazon", reminder)
        self.assertIn("keep their access.\n\n", reminder)
        self.assertIn("\n\nMembers of Data Amazon can read and edit", ended)

    def test_a_context_without_the_setting_fails_here_not_in_an_inbox(self):
        for template, context in (
            (EmailTemplate.EMBARGO_REMINDER, REMINDER),
            (EmailTemplate.EMBARGO_ENDED, ENDED),
        ):
            with self.subTest(template=template):
                partial = {key: value for key, value in context.items() if key != "members_can_edit"}
                with self.assertRaises(UndefinedError):
                    self.render(template, partial)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest app/service/email_template_test.py -k TestMembersSentence -v`
Expected: FAIL — seven tests fail on `assertIn` (the sentence is not there), and `test_a_context_without_the_setting_fails_here_not_in_an_inbox` fails with `AssertionError: UndefinedError not raised`.

- [ ] **Step 3: The reminder** — `app/resources/email_templates/embargo_reminder.html`

After the first paragraph, the line that begins `{% call m.paragraph() %}On {{ m.strong(embargo_until_date) }} the files of the dataset below` and ends `{% endcall %}`, insert:

```html
{% call m.paragraph() %}{% if members_can_edit %}When the embargo ends, members of {{ tenancy_name }} can read and edit this dataset again; the people {{ "you" if is_owner else owner_name }} shared it with keep their access.{% elif is_owner %}When the embargo ends, members of {{ tenancy_name }} can read this dataset; editing stays with the people you shared it with.{% else %}When the embargo ends, members of {{ tenancy_name }} can read this dataset; editing stays with {{ owner_name }} and the people they shared it with.{% endif %}{% endcall %}
```

`app/resources/email_templates/embargo_reminder.txt`: the line that begins `On {{ embargo_until_date }} the files of the dataset below` ends with `{% endif %}` and is followed by two empty lines, then `Dataset: {{ dataset_name }}`. Insert, between those two empty lines and `Dataset:`, the sentence and two more empty lines, so that the passage reads:

```
On {{ embargo_until_date }} the files of the dataset below become available to every member of {{ tenancy_name }}.{% if is_owner %} Nothing becomes public: the public page only appears when you make the DOI findable.{% else %} Your own access doesn't change.{% endif %}


{% if members_can_edit %}When the embargo ends, members of {{ tenancy_name }} can read and edit this dataset again; the people {{ "you" if is_owner else owner_name }} shared it with keep their access.{% elif is_owner %}When the embargo ends, members of {{ tenancy_name }} can read this dataset; editing stays with the people you shared it with.{% else %}When the embargo ends, members of {{ tenancy_name }} can read this dataset; editing stays with {{ owner_name }} and the people they shared it with.{% endif %}


Dataset: {{ dataset_name }}
```

`trim_blocks` eats the newline after a closing `{% endif %}`, so two empty lines after a line that ends with a tag render as one: the sentence comes out as a paragraph of its own, as `test_the_sentence_is_a_paragraph_of_its_own_in_the_text` checks.

- [ ] **Step 4: The end notice** — `app/resources/email_templates/embargo_ended.html`

The sentence for this message, written once here and inserted three times below:

```html
{% call m.paragraph() %}{% if members_can_edit %}Members of {{ tenancy_name }} can read and edit this dataset again; the people {{ "you" if is_owner else owner_name }} shared it with keep their access.{% elif is_owner %}Members of {{ tenancy_name }} can read this dataset; editing stays with the people you shared it with.{% else %}Members of {{ tenancy_name }} can read this dataset; editing stays with {{ owner_name }} and the people they shared it with.{% endif %}{% endcall %}
```

Insert it on a line of its own after each branch's first paragraph:

1. In the `{% if ended_by_manual_doi %}` branch, after the line that begins `{% call m.paragraph() %}Registering the external DOI {{ m.strong(doi) }} ended the embargo` (ending `{% endcall %}`), before `{{ m.details([`.
2. In the `{% elif is_owner %}` branch, after the line `{% call m.paragraph() %}{% if ended_early %}You ended the embargo on the dataset below early, today, …{% endif %}{% endcall %}`, before `{{ m.details([`.
3. In the `{% else %}` branch, after the line that begins `{% call m.paragraph() %}{% if ended_early %}{{ owner_name }} ended the embargo on the dataset below early` (ending `Your own access doesn't change.{% endcall %}`), before `{% set rows = [`.

`app/resources/email_templates/embargo_ended.txt` — the text sentence:

```
{% if members_can_edit %}Members of {{ tenancy_name }} can read and edit this dataset again; the people {{ "you" if is_owner else owner_name }} shared it with keep their access.{% elif is_owner %}Members of {{ tenancy_name }} can read this dataset; editing stays with the people you shared it with.{% else %}Members of {{ tenancy_name }} can read this dataset; editing stays with {{ owner_name }} and the people they shared it with.{% endif %}
```

Insert it, followed by two empty lines, in the same three places:

1. After the line `Registering the external DOI {{ doi }} ended the embargo on the dataset below today, …{% if not is_owner %} Your own access doesn't change.{% endif %}` and the two empty lines that follow it, before `Dataset: {{ dataset_name }}`.
2. After the line `{% if ended_early %}You ended the embargo on the dataset below early, today, {{ ended_on_date }}.{% else %}…{% endif %}` and its two empty lines, before `Dataset: {{ dataset_name }}`.
3. After the line `{% if ended_early %}{{ owner_name }} ended the embargo … Your own access doesn't change.` and its two empty lines, before `Dataset: {{ dataset_name }}`. That line ends in text, not in a tag, so its newline is kept and the gap before the sentence stays as wide as the gap before `Dataset:` is today; the inserted sentence ends in `{% endif %}`, so the two empty lines after it render as one blank line.

- [ ] **Step 5: Run the template tests to verify they pass**

Run: `python -m pytest app/service/email_template_test.py -v`
Expected: PASS — plan 03's `TestEmbargoTemplates` (its contexts now carry the key) and the 8 tests of `TestMembersSentence`.

- [ ] **Step 6: Write the failing notification tests**

In `app/service/notification_test.py`, add `members_can_edit=True,` to the `SimpleNamespace` assigned to `self.dataset` in `TestQueueDue.setUp` and to the one returned by `ended()` (after `embargo_until=...` in each). Then append to `TestQueueDue`:

```python
    def test_the_reminder_says_what_members_get_when_the_embargo_ends(self):
        self.dataset.members_can_edit = False

        self.service.queue_due(NOW)

        contexts = [call.kwargs["context"] for call in self.email.enqueue.call_args_list]
        self.assertEqual(len(contexts), 2)
        self.assertEqual({context["members_can_edit"] for context in contexts}, {False})

    def test_the_end_notice_says_what_members_got_back(self):
        ended = self.ended()
        self.repository.datasets_with_reminders_due.return_value = []
        self.repository.datasets_expired_unannounced.return_value = [ended]

        self.service.queue_due(NOW)

        contexts = [call.kwargs["context"] for call in self.email.enqueue.call_args_list]
        self.assertEqual({context["members_can_edit"] for context in contexts}, {True})
```

- [ ] **Step 7: Run them to verify they fail**

Run: `python -m pytest app/service/notification_test.py -v`
Expected: the two new tests FAIL with `KeyError: 'members_can_edit'`; every other test still passes, because their `EmailService` is a mock that does not render.

- [ ] **Step 8: Pass the setting** — `app/service/notification.py`

Add the import:

```python
from app.service.dataset_access import allows_member_edits
```

and, in `_queue_for_people`, add to the `base` dictionary after `"tenancy_name": tenancy_display_name(dataset.tenancy),`:

```python
            "members_can_edit": allows_member_edits(dataset),
```

- [ ] **Step 9: Run them to verify they pass**

Run: `python -m pytest app/service/notification_test.py app/service/email_template_test.py -v`
Expected: PASS (13 tests in `notification_test.py`).

- [ ] **Step 10: Look at the messages**

Render the four cases plan 03 compares with the design, with each value of the setting, and read the sentence in place:

```bash
python - <<'PY'
from app.service.email_template import EmailTemplate, EmailTemplateRenderer
from app.service import email_template_test as t

renderer = EmailTemplateRenderer(site_url="https://datamap.pcs.usp.br")
for name, template, context in (
    ("reminder-owner", EmailTemplate.EMBARGO_REMINDER, t.REMINDER),
    ("reminder-collaborator", EmailTemplate.EMBARGO_REMINDER, t.COLLABORATOR_REMINDER),
    ("ended-owner", EmailTemplate.EMBARGO_ENDED, t.ENDED),
    ("ended-collaborator", EmailTemplate.EMBARGO_ENDED, t.COLLABORATOR_ENDED),
):
    for value in (True, False):
        text = renderer.render(template, {**context, "members_can_edit": value}).text
        line = next(line for line in text.splitlines() if "members of Data Amazon can read" in line.lower())
        print(f"{name} {value}: {line}")
PY
```

Expected: eight lines, each one of the four sentences of the contracts' table, owner wording for the `-owner` cases and `Luciana Rizzo` in the `-collaborator` ones.

- [ ] **Step 11: Commit**

```bash
git add app/resources/email_templates/embargo_reminder.html app/resources/email_templates/embargo_reminder.txt app/resources/email_templates/embargo_ended.html app/resources/email_templates/embargo_ended.txt app/service/email_template_test.py app/service/notification.py app/service/notification_test.py
git commit -m "feat: embargo emails say what the members get when the embargo ends"
```

---

### Task 5: Integration tests

**Repo:** gatekeeper.

Unit tests mock the repository and the routing; the rule only matters if every route, the TUS hook and the payloads really follow it. These tests use plan 02's fixtures (`tests/integration/fixtures/embargo.py`) as they are: `create_user` with real roles and tenancies, `grant` writing a real permission, `create_dataset` and `set_embargo` through the real routes.

**Files:**
- Create: `tests/integration/test_dataset_members_access.py`

**Interfaces:**
- Consumes: plan 02's fixtures `TENANCY`, `create_dataset`, `create_user`, `grant`, `headers_for`, `set_embargo`; `AuthFixture.valid_headers()` (the seeded admin, who owns the datasets it creates); `create_tus_payload`; `assert_status_code`; `config.user_id`; the routes of Tasks 2 and 3 and plan 03's `GET /share` and `GET /access-events`.
- Produces: nothing other tasks consume.

Roles in the seed (`tests/integration/fixtures/seed_clients.sql`): `datasets_write` allows `GET|POST|PUT` on `/api/v1/datasets…` and the TUS hook; `datasets_admin` adds `DELETE`. A member with `datasets_write` is the "editor", a member with `datasets_admin` the one whose role may delete.

- [ ] **Step 1: Confirm the routes exist as the tests address them**

With the integration stack up from a build of this branch (Step 4 shows how), run:

```bash
curl -s http://localhost:9094/api/openapi.json | python -c "import json,sys; print([p for p in json.load(sys.stdin)['paths'] if 'members-access' in p or p.endswith('/access-events') or p.endswith('/share')])"
```
Expected: `['/api/v1/datasets/{dataset_id}/members-access', '/api/v1/datasets/{dataset_id}/access-events', '/api/v1/datasets/{dataset_id}/share']` in some order (`/share` and `/access-events` are plan 03's).

- [ ] **Step 2: Write the tests** — `tests/integration/test_dataset_members_access.py`

```python
import pytest

from tests.integration.config import config
from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.embargo import (
    TENANCY,
    create_dataset,
    create_user,
    grant,
    headers_for,
    set_embargo,
)
from tests.integration.fixtures.tus_auth import create_tus_payload
from tests.integration.utils.assertions import assert_status_code


@pytest.fixture
def owner():
    return AuthFixture.valid_headers()


@pytest.fixture
def editor(http_client):
    user_id = create_user(http_client, ["datasets_write"], [TENANCY])
    return user_id, headers_for(user_id, TENANCY)


@pytest.fixture
def deleter(http_client):
    user_id = create_user(http_client, ["datasets_admin"], [TENANCY])
    return user_id, headers_for(user_id, TENANCY)


@pytest.fixture
def outsider(http_client):
    user_id = create_user(http_client, [], [])
    return user_id, headers_for(user_id, None)


def _members(http_client, dataset_id: str, headers: dict, can_edit: bool):
    return http_client.put(
        f"/datasets/{dataset_id}/members-access",
        json={"members_can_edit": can_edit},
        headers=headers,
    )


def _update(http_client, dataset_id: str, headers: dict):
    return http_client.put(
        f"/datasets/{dataset_id}",
        json={"name": "edited", "data": {}, "tenancy": TENANCY},
        headers=headers,
    )


def _tus(http_client, dataset_id: str, user_id: str):
    payload = create_tus_payload(
        user_id=user_id,
        dataset_id=dataset_id,
        filename="data.nc",
        file_size=10,
        file_type="application/x-netcdf",
    )
    return http_client.post(
        "/tus/hooks", json=payload, headers=AuthFixture.valid_headers()
    )


def _owner_file(http_client, dataset: dict, owner: dict) -> tuple[str, str]:
    assert_status_code(_tus(http_client, dataset["id"], config.user_id), 200)
    body = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()
    version = body["current_version"]
    return version["name"], version["files_in"][0]["id"]


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


class TestReadOnly:
    def test_the_owner_makes_members_read_only(self, http_client, owner):
        dataset = create_dataset(http_client, owner)

        response = _members(http_client, dataset["id"], owner, False)

        assert_status_code(response, 200)
        body = response.json()
        assert body["members_can_edit"] is False
        assert body["access"]["level"] == "owner"
        assert body["access"]["can_edit"] is True
        detail = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()
        assert detail["members_can_edit"] is False

    def test_members_read_and_download_but_change_nothing(
        self, http_client, owner, editor
    ):
        dataset = create_dataset(http_client, owner)
        version, file_id = _owner_file(http_client, dataset, owner)
        assert_status_code(_members(http_client, dataset["id"], owner, False), 200)
        user_id, headers = editor

        read = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        download = http_client.get(
            f"/datasets/{dataset['id']}/versions/{version}/files/{file_id}",
            headers=headers,
        )
        update = _update(http_client, dataset["id"], headers)
        new_version = http_client.post(
            f"/datasets/{dataset['id']}/versions",
            json={"datafilesPreviouslyUploaded": []},
            headers=headers,
        )
        upload = _tus(http_client, dataset["id"], user_id)

        assert_status_code(read, 200)
        body = read.json()
        assert body["access"]["level"] == "tenancy"
        assert body["access"]["can_edit"] is False
        assert body["access"]["can_share"] is False
        assert body["access"]["can_delete"] is False
        assert body["current_version"]["files_withheld"] is False
        assert len(body["current_version"]["files_in"]) == 1
        assert_status_code(download, 200)
        assert_status_code(update, 403)
        assert update.json() == {"detail": "forbidden"}
        assert_status_code(new_version, 403)
        assert upload.json().get("RejectUpload") is True
        assert upload.json()["HTTPResponse"]["StatusCode"] == 403

    def test_a_role_that_deletes_deletes_only_in_the_default_mode(
        self, http_client, owner, deleter
    ):
        _, headers = deleter
        read_only = create_dataset(http_client, owner)
        editable = create_dataset(http_client, owner)
        assert_status_code(_members(http_client, read_only["id"], owner, False), 200)

        refused = http_client.delete(f"/datasets/{read_only['id']}", headers=headers)
        allowed = http_client.delete(f"/datasets/{editable['id']}", headers=headers)

        assert_status_code(refused, 403)
        assert_status_code(
            http_client.get(f"/datasets/{read_only['id']}", headers=owner), 200
        )
        assert_status_code(allowed, 200)

    def test_a_write_permission_still_edits(self, http_client, owner, outsider):
        dataset = create_dataset(http_client, owner)
        assert_status_code(_members(http_client, dataset["id"], owner, False), 200)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "write")

        update = _update(http_client, dataset["id"], headers)

        assert_status_code(update, 200)

    def test_a_read_permission_does_not_borrow_the_roles_write(
        self, http_client, owner, editor
    ):
        dataset = create_dataset(http_client, owner)
        user_id, headers = editor
        grant(http_client, dataset["id"], user_id, "read")
        assert_status_code(_update(http_client, dataset["id"], headers), 200)

        assert_status_code(_members(http_client, dataset["id"], owner, False), 200)

        assert_status_code(_update(http_client, dataset["id"], headers), 403)

    def test_lists_and_versions_carry_the_setting(self, http_client, owner, outsider):
        dataset = create_dataset(http_client, owner)
        assert_status_code(_members(http_client, dataset["id"], owner, False), 200)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "read")
        version = dataset["current_version"]["name"]

        minimal = http_client.get("/datasets/?shared=true&minimal=true", headers=headers)
        full = http_client.get("/datasets/?shared=true", headers=headers)
        by_version = http_client.get(
            f"/datasets/{dataset['id']}/versions/{version}", headers=owner
        )

        for listing in (minimal, full):
            assert_status_code(listing, 200)
            item = next(i for i in listing.json()["content"] if i["id"] == dataset["id"])
            assert item["members_can_edit"] is False
        assert_status_code(by_version, 200)
        assert by_version.json()["members_can_edit"] is False


class TestWithAnEmbargo:
    def test_the_setting_is_inert_during_the_embargo_and_decides_afterwards(
        self, http_client, owner, editor
    ):
        dataset = create_dataset(http_client, owner)
        assert_status_code(_members(http_client, dataset["id"], owner, False), 200)
        assert_status_code(
            set_embargo(http_client, dataset["id"], owner, visible=False), 200
        )
        _, headers = editor

        during = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        ended = http_client.post(f"/datasets/{dataset['id']}/embargo/end", headers=owner)
        after = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        update = _update(http_client, dataset["id"], headers)

        assert_status_code(during, 404)
        assert_status_code(ended, 200)
        assert_status_code(after, 200)
        assert after.json()["access"]["can_edit"] is False
        assert after.json()["members_can_edit"] is False
        assert_status_code(update, 403)

    def test_by_default_members_edit_again_after_the_embargo(
        self, http_client, owner, editor
    ):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        http_client.post(f"/datasets/{dataset['id']}/embargo/end", headers=owner)
        _, headers = editor

        assert_status_code(_update(http_client, dataset["id"], headers), 200)

    def test_the_owner_changes_it_during_the_embargo(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)

        response = _members(http_client, dataset["id"], owner, False)

        assert_status_code(response, 200)
        assert response.json()["members_can_edit"] is False


class TestWhoMayChangeIt:
    def test_a_member_who_sees_the_dataset_is_forbidden(
        self, http_client, owner, editor
    ):
        dataset = create_dataset(http_client, owner)
        _, headers = editor

        response = _members(http_client, dataset["id"], headers, False)

        assert_status_code(response, 403)
        assert response.json() == {"detail": "forbidden"}

    def test_a_write_permission_is_forbidden(self, http_client, owner, outsider):
        dataset = create_dataset(http_client, owner)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "write")

        assert_status_code(_members(http_client, dataset["id"], headers, False), 403)

    def test_a_member_who_cannot_see_the_dataset_gets_404(
        self, http_client, owner, editor
    ):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        _, headers = editor

        assert_status_code(_members(http_client, dataset["id"], headers, False), 404)

    def test_a_body_without_a_boolean_is_refused(self, http_client, owner):
        dataset = create_dataset(http_client, owner)

        for body in ({}, {"members_can_edit": "false"}, {"members_can_edit": 0}):
            response = http_client.put(
                f"/datasets/{dataset['id']}/members-access", json=body, headers=owner
            )
            assert_status_code(response, 422)
        detail = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()
        assert detail["members_can_edit"] is True


class TestHistoryAndShareState:
    def test_each_change_is_in_the_history_once(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        _members(http_client, dataset["id"], owner, False)
        _members(http_client, dataset["id"], owner, False)

        history = http_client.get(f"/datasets/{dataset['id']}/access-events", headers=owner)

        assert_status_code(history, 200)
        changes = [
            item
            for item in history.json()["items"]
            if item["event_type"] == "members_access_changed"
        ]
        assert len(changes) == 1
        assert changes[0]["old_value"] == {"members_can_edit": True}
        assert changes[0]["new_value"] == {"members_can_edit": False}
        assert changes[0]["actor"]["id"] == config.user_id
        assert changes[0]["subject"] is None

    def test_the_share_state_says_what_members_can_do(self, http_client, owner):
        dataset = create_dataset(http_client, owner)

        before = http_client.get(f"/datasets/{dataset['id']}/share", headers=owner)
        _members(http_client, dataset["id"], owner, False)
        after = http_client.get(f"/datasets/{dataset['id']}/share", headers=owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        during = http_client.get(f"/datasets/{dataset['id']}/share", headers=owner)

        assert before.json()["tenancy"]["members_can_edit"] is True
        assert after.json()["tenancy"]["members_can_edit"] is False
        assert during.json()["tenancy"] is None
```

- [ ] **Step 3: Make sure they fail without the feature**

Build and run the stack from the commit before Task 1 (a worktree at the plan-03 head, with this test file copied in), then:

Run: `make ENV_FILE_PATH=integration-test.env integration-test-run-specific TEST_PATH=tests/integration/test_dataset_members_access.py`
Expected: FAIL — `PUT /datasets/{id}/members-access` answers 404 and `members_can_edit` is missing from every payload; only `test_a_new_dataset_lets_members_edit_as_today` fails on the missing key alone. That proves the tests address real routes and fields.

- [ ] **Step 4: Run them against this branch**

```bash
make ENV_FILE_PATH=integration-test.env integration-test-clean
mkdir -p "$(grep STORAGE_DOCKER_VOLUME integration-test.env | cut -d= -f2)_test_integration/datamap"
make ENV_FILE_PATH=integration-test.env integration-test-build
make ENV_FILE_PATH=integration-test.env integration-test-up
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/
```
Expected: `200`. If not, read `docker logs datamap_gatekeeper_test_integration`: the application applies the migrations at startup, and a failing `a7b8c9d0e1f2` keeps the container unhealthy.

Seed, and wait for Casbin's 5-second reload before running:

```bash
docker exec -i datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db < tests/integration/fixtures/seed_clients.sql
until [ "$(curl -s -o /dev/null -w '%{http_code}' -H 'X-Api-Key: 5060b1a2-9aaf-48db-871a-0839007fd478' -H 'X-Api-Secret: integration-test-not-a-real-secret' -H 'X-User-Id: cbb0a683-630f-4b86-8b45-91b90a6fce1c' http://localhost:9094/api/v1/clients/)" = 200 ]; do sleep 1; done
make ENV_FILE_PATH=integration-test.env integration-test-run-specific TEST_PATH=tests/integration/test_dataset_members_access.py
```
Expected: 16 passed.

- [ ] **Step 5: Run the whole integration suite**

Every dataset, DOI, TUS, sharing and embargo test goes through the changed rule; they must stay green with the default `true`.

Run: `make ENV_FILE_PATH=integration-test.env integration-test-run`
Expected: 0 failures. Read the summary line yourself; do not pipe `make` into `tail`.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_dataset_members_access.py
git commit -m "test: members' access end to end, from the tenancy, a permission and the owner"
```

---

### Task 6: Types, server call, BFF route, BFFAPI, telemetry

**Repo:** webapp.

**Files:**
- Modify: `types/GatekeeperAPI.ts` (`ShareTenancy`; append two interfaces)
- Modify: `types/BffAPI.ts` (`GetDatasetDetailsResponse`, `GetMinimalDatasetsDetasetDetailsResponse`)
- Modify: `lib/share.ts` (append), `lib/__tests__/share.test.ts` (append)
- Create: `pages/api/datasets/[datasetId]/members-access.ts`, `lib/__tests__/membersAccessRoute.test.ts`
- Modify: `gateways/BFFAPI.ts` (import; append a method), `gateways/__tests__/BFFAPI.embargo.test.ts` (append)
- Modify: `contants/TelemetryConstants.ts` (`UI_EVENTS`), `contants/__tests__/TelemetryConstants.test.ts` (append)

**Interfaces:**
- Consumes: plan 05's `bffRouter`, `bffHandler`, `NewContext`, `axiosInstance`, `buildHeaders`, `httpErrorHandler`, `trackUiEvent`, `DatasetAccess`.
- Produces:
  - `MembersAccessRequest { members_can_edit: boolean }`, `MembersAccessResponse { members_can_edit: boolean, access: DatasetAccess }`; `ShareTenancy.members_can_edit: boolean`; `GetDatasetDetailsResponse.members_can_edit?: boolean` and the same on the minimal list item.
  - `setMembersAccess(context: AppLocalContext, datasetId: string, request: MembersAccessRequest): Promise<MembersAccessResponse>` in `lib/share.ts`.
  - `PUT /api/datasets/[datasetId]/members-access`.
  - `BFFAPI.setMembersAccess(datasetId: string, request: MembersAccessRequest): Promise<MembersAccessResponse>`, emitting `members_access_changed`.

- [ ] **Step 1: Write the failing tests**

Append to `lib/__tests__/share.test.ts` (and add `setMembersAccess` to its import from `"../share"`):

```ts
describe("members' access", () => {
    test("is set with the user's headers", async () => {
        const answer = { members_can_edit: false, access: { level: "owner" } };
        mockPut.mockResolvedValue({ data: answer });

        expect(await setMembersAccess(context, "d1", { members_can_edit: false })).toEqual(answer);
        expect(mockPut).toHaveBeenCalledWith("/datasets/d1/members-access", { members_can_edit: false }, headers);
    });
});
```

Create `lib/__tests__/membersAccessRoute.test.ts`:

```ts
jest.mock("next-auth/jwt", () => ({ getToken: jest.fn(async () => ({ uid: "u1" })) }));
jest.mock("../share");

import { AxiosError, AxiosHeaders } from "axios";
import membersAccessHandler from "../../pages/api/datasets/[datasetId]/members-access";
import { setMembersAccess } from "../share";

function gatekeeperError(status: number, data: unknown) {
    return new AxiosError("gatekeeper", "ERR", undefined, {}, {
        status, data, statusText: "", headers: {}, config: { headers: new AxiosHeaders() },
    } as any);
}

function fakeRes() {
    const res: any = { statusCode: 200, headers: {} };
    res.setHeader = jest.fn((key: string, value: string) => (res.headers[key] = value));
    res.getHeader = jest.fn((key: string) => res.headers[key]);
    res.status = jest.fn((code: number) => {
        res.statusCode = code;
        return res;
    });
    res.end = jest.fn(() => res);
    res.json = jest.fn(() => res);
    return res;
}

async function send(handler: any, method: string, query: Record<string, string>, body: unknown = undefined) {
    const res = fakeRes();
    const original = process.stdout.write;
    // @ts-ignore
    process.stdout.write = () => true;
    try {
        await handler({ method, url: "/api/x", headers: {}, cookies: {}, query, body } as any, res);
    } finally {
        process.stdout.write = original;
    }
    return res;
}

describe("the members' access BFF route", () => {
    test("PUT passes the body through, without a tenancy", async () => {
        const answer = { members_can_edit: false, access: { level: "owner" } };
        jest.mocked(setMembersAccess).mockResolvedValue(answer as any);

        const res = await send(membersAccessHandler, "PUT", { datasetId: "d1" }, { members_can_edit: false });

        expect(res.statusCode).toBe(200);
        expect(setMembersAccess).toHaveBeenCalledWith(expect.anything(), "d1", { members_can_edit: false });
        expect(res.json).toHaveBeenCalledWith(answer);
    });

    test("a refusal keeps the gatekeeper's status", async () => {
        jest.mocked(setMembersAccess).mockRejectedValue(gatekeeperError(403, { detail: "forbidden" }));

        const res = await send(membersAccessHandler, "PUT", { datasetId: "d1" }, { members_can_edit: false });

        expect(res.statusCode).toBe(403);
    });

    test("only PUT is answered", async () => {
        const res = await send(membersAccessHandler, "GET", { datasetId: "d1" });

        expect(res.statusCode).toBe(405);
    });
});
```

Append to `gateways/__tests__/BFFAPI.embargo.test.ts`, inside `describe("BFFAPI embargo and sharing", ...)`:

```ts
    test("changing what members can do calls the BFF and records the event", async () => {
        const answer = { members_can_edit: false, access: { level: "owner" } };
        jest.mocked(axios.put).mockResolvedValue({ status: 200, data: answer });

        expect(await bff.setMembersAccess("d1", { members_can_edit: false })).toEqual(answer);
        expect(axios.put).toHaveBeenCalledWith("/api/datasets/d1/members-access", { members_can_edit: false });
        expect(trackUiEvent).toHaveBeenCalledWith("members_access_changed");
    });
```

Append to `contants/__tests__/TelemetryConstants.test.ts`:

```ts
describe("members' access", () => {
  it("accepts its ui event", () => {
    expect(uiEventLabel("members_access_changed")).toBe("members_access_changed");
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npx jest lib/__tests__/share.test.ts lib/__tests__/membersAccessRoute.test.ts gateways/__tests__/BFFAPI.embargo.test.ts contants/__tests__/TelemetryConstants.test.ts`
Expected: FAIL — `setMembersAccess is not a function`, `Cannot find module '../../pages/api/datasets/[datasetId]/members-access'`, `bff.setMembersAccess is not a function`, and `uiEventLabel("members_access_changed")` is `undefined`.

- [ ] **Step 3: The types**

In `types/GatekeeperAPI.ts`, `ShareTenancy` becomes:

```ts
/** @interface */
export interface ShareTenancy {
    name: string
    path: string
    members: number
    members_can_edit: boolean
}
```

and append:

```ts
/** @interface */
export interface MembersAccessRequest {
    members_can_edit: boolean
}

/** @interface */
export interface MembersAccessResponse {
    members_can_edit: boolean
    access: DatasetAccess
}
```

In `types/BffAPI.ts`, add to `GetDatasetDetailsResponse` after `owner?: DatasetOwner | null`, and to `GetMinimalDatasetsDetasetDetailsResponse` after `access?: DatasetAccess`:

```ts
    members_can_edit?: boolean
```

It is optional because a payload from a gatekeeper without plan 06 lacks it; every reader treats a missing value as `true`, the default.

- [ ] **Step 4: The server call** — append to `lib/share.ts`

Add `MembersAccessRequest` and `MembersAccessResponse` to its import from `"../types/GatekeeperAPI"`, then:

```ts
export async function setMembersAccess(context: AppLocalContext, datasetId: string, request: MembersAccessRequest): Promise<MembersAccessResponse> {
    const response = await axiosInstance.put(`/datasets/${datasetId}/members-access`, request, buildHeaders(context));
    return response.data as MembersAccessResponse;
}
```

- [ ] **Step 5: The BFF route** — `pages/api/datasets/[datasetId]/members-access.ts`

```ts
import { NewContext } from "../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../lib/bffRoute";
import { setMembersAccess } from "../../../../lib/share";

const router = bffRouter()
    .put(async (req, res) => {
        const context = await NewContext(req);
        res.json(await setMembersAccess(context, req.query.datasetId as string, req.body));
    });

export default bffHandler(router);
```

- [ ] **Step 6: The browser method** — `gateways/BFFAPI.ts`

Add `MembersAccessRequest` and `MembersAccessResponse` to the import from `"../types/GatekeeperAPI"`, and append to the class, after `setEmbargoNote`:

```ts
    async setMembersAccess(datasetId: string, request: MembersAccessRequest): Promise<MembersAccessResponse> {
        try {
            const response = await axios.put(`/api/datasets/${datasetId}/members-access`, request);
            trackUiEvent("members_access_changed");
            return response.data as MembersAccessResponse;
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }
```

- [ ] **Step 7: The UI event** — `contants/TelemetryConstants.ts`

In `UI_EVENTS`, after `"anonymous_link_created",`:

```ts
  "members_access_changed",
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/share.test.ts lib/__tests__/membersAccessRoute.test.ts gateways/__tests__/BFFAPI.embargo.test.ts contants/__tests__/TelemetryConstants.test.ts`
Expected: PASS.

- [ ] **Step 9: Type-check**

Run: `npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E "types/(GatekeeperAPI|BffAPI)|lib/share|members-access|gateways/BFFAPI|TelemetryConstants" || echo "no new type errors"`
Expected: `no new type errors`. Plan 05's test fixtures that build a `ShareTenancy` literal without `members_can_edit` are typed `any`, so the new required field breaks none of them.

- [ ] **Step 10: Commit**

```bash
git add types/GatekeeperAPI.ts types/BffAPI.ts lib/share.ts lib/__tests__/share.test.ts "pages/api/datasets/[datasetId]/members-access.ts" lib/__tests__/membersAccessRoute.test.ts gateways/BFFAPI.ts gateways/__tests__/BFFAPI.embargo.test.ts contants/TelemetryConstants.ts contants/__tests__/TelemetryConstants.test.ts
git commit -m "feat: the webapp can change what members of a dataset's tenancy may do"
```

---

### Task 7: Wording, the members dialog and its hook

**Repo:** webapp.

Every place that shows the setting — the share dialog, Settings, the embargo fields, the ended banner — takes its words and its decisions from one module, so the copy cannot drift between them. The dialog is the one control that changes it; the hook is what the two places on the dataset page use to save it.

After a save the hook asks Next for the page's props again (`router.replace(router.asPath)`): the dataset page reads the dataset in `getServerSideProps`, so this refreshes `members_can_edit` everywhere on the page at once, and keeps component state such as an open share dialog. A full `router.reload()`, which plan 05's embargo dialogs use, would close the share dialog under the owner's cursor.

**Files:**
- Create: `lib/membersAccess.ts`, `lib/__tests__/membersAccess.test.ts`
- Create: `components/Share/MembersAccessDialog.tsx`, `components/Share/__tests__/MembersAccessDialog.test.tsx`
- Create: `hooks/UseMembersAccess.ts`

**Interfaces:**
- Consumes: Task 6's `BFFAPI.setMembersAccess`; plan 05's `PopupModal`, `messageForApiError`, `GetDatasetDetailsResponse`, `ShareState`.
- Produces:
  - `membersCanEditOf(dataset: GetDatasetDetailsResponse, state?: ShareState | null): boolean`
  - `canChangeMembersAccess(dataset: GetDatasetDetailsResponse): boolean`
  - `membersAccessDetail(options: { membersCanEdit: boolean, embargoActive: boolean, members?: number | null }): string`
  - `membersAfterEmbargoLine(tenancyName: string, membersCanEdit: boolean): string`
  - `membersOutcomeSentence(tenancyName: string, membersCanEdit: boolean): string`
  - `<MembersAccessDialog show tenancyName membersCanEdit embargoActive busy? error? onCancel onSave(membersCanEdit: boolean) />`
  - `useMembersAccess(datasetId: string, afterSave?: () => Promise<unknown>): { editing: boolean, busy: boolean, error: string | null, open(): void, close(): void, save(membersCanEdit: boolean): Promise<void> }`

- [ ] **Step 1: Write the failing tests**

Create `lib/__tests__/membersAccess.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import {
    canChangeMembersAccess,
    membersAccessDetail,
    membersAfterEmbargoLine,
    membersCanEditOf,
    membersOutcomeSentence,
} from "../membersAccess";

describe("what members can do", () => {
    test("the share state's row wins, the dataset is the fallback, and missing means the default", () => {
        const dataset: any = { members_can_edit: false };

        expect(membersCanEditOf(dataset, { tenancy: { members_can_edit: true } } as any)).toBe(true);
        expect(membersCanEditOf(dataset, { tenancy: null } as any)).toBe(false);
        expect(membersCanEditOf(dataset)).toBe(false);
        expect(membersCanEditOf({} as any)).toBe(true);
    });

    test("only the owner changes it", () => {
        expect(canChangeMembersAccess({ access: { level: "owner" } } as any)).toBe(true);
        expect(canChangeMembersAccess({ access: { level: "write" } } as any)).toBe(false);
        expect(canChangeMembersAccess({} as any)).toBe(false);
    });

    test("the row, without an embargo", () => {
        expect(membersAccessDetail({ membersCanEdit: true, embargoActive: false, members: 14 }))
            .toBe("14 people · can read and edit");
        expect(membersAccessDetail({ membersCanEdit: false, embargoActive: false, members: 14 }))
            .toBe("14 people · can read · editing limited to the people above");
        expect(membersAccessDetail({ membersCanEdit: true, embargoActive: false, members: 1 }))
            .toBe("1 person · can read and edit");
    });

    test("the row, during an embargo, says what comes afterwards", () => {
        expect(membersAccessDetail({ membersCanEdit: true, embargoActive: true, members: 14 }))
            .toBe("No access during the embargo · afterwards: read and edit");
        expect(membersAccessDetail({ membersCanEdit: false, embargoActive: true }))
            .toBe("No access during the embargo · afterwards: read only");
    });

    test("the line under the embargo choice", () => {
        expect(membersAfterEmbargoLine("Data Amazon", true))
            .toBe("When the embargo ends, members of Data Amazon can read and edit again.");
        expect(membersAfterEmbargoLine("Data Amazon", false))
            .toBe("When the embargo ends, members of Data Amazon can read but not edit.");
    });

    test("the sentence of the ended banner", () => {
        expect(membersOutcomeSentence("Data Amazon", true))
            .toBe("Members of Data Amazon can read and edit this dataset again; the people you shared it with keep their access.");
        expect(membersOutcomeSentence("Data Amazon", false))
            .toBe("Members of Data Amazon can read this dataset; editing stays with the people you shared it with.");
    });
});
```

Create `components/Share/__tests__/MembersAccessDialog.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react';
import { MembersAccessDialog } from "../MembersAccessDialog";

function renderDialog(overrides: any = {}) {
    const onSave = jest.fn();
    const onCancel = jest.fn();
    render(<MembersAccessDialog show tenancyName="Data Amazon" membersCanEdit embargoActive={false} onCancel={onCancel} onSave={onSave} {...overrides} />);
    return { onSave, onCancel };
}

describe("MembersAccessDialog", () => {
    test("offers the two choices, the current one selected", () => {
        renderDialog();

        expect(screen.getByRole("dialog", { name: "What members of Data Amazon can do" })).toBeTruthy();
        expect((screen.getByRole("radio", { name: /Read and edit/ }) as HTMLInputElement).checked).toBe(true);
        expect(screen.getByText("Their workspace role decides, as on any dataset of Data Amazon.")).toBeTruthy();
        expect(screen.getByText("They read and download. Editing, uploads and new versions stay with you and the people you share it with as Can write.")).toBeTruthy();
    });

    test("saves the choice", () => {
        const { onSave } = renderDialog();

        fireEvent.click(screen.getByRole("radio", { name: /Read only/ }));
        fireEvent.click(screen.getByRole("button", { name: "Save" }));

        expect(onSave).toHaveBeenCalledWith(false);
    });

    test("cancel saves nothing", () => {
        const { onSave, onCancel } = renderDialog();

        fireEvent.click(screen.getByRole("radio", { name: /Read only/ }));
        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

        expect(onCancel).toHaveBeenCalled();
        expect(onSave).not.toHaveBeenCalled();
    });

    test("during an embargo it says the choice is for afterwards", () => {
        renderDialog({ embargoActive: true, membersCanEdit: false });

        expect((screen.getByRole("radio", { name: /Read only/ }) as HTMLInputElement).checked).toBe(true);
        expect(screen.getByText("Members have no access while the embargo lasts. This decides what they get when it ends.")).toBeTruthy();
    });

    test("an error is shown, and Save waits while busy", () => {
        renderDialog({ busy: true, error: "You are not allowed to do this on this dataset." });

        expect(screen.getByRole("alert").textContent).toBe("You are not allowed to do this on this dataset.");
        expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
    });

    test("nothing is rendered when hidden", () => {
        renderDialog({ show: false });

        expect(screen.queryByRole("dialog")).toBeNull();
    });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npx jest lib/__tests__/membersAccess.test.ts components/Share/__tests__/MembersAccessDialog.test.tsx`
Expected: FAIL — `Cannot find module '../membersAccess'` and `Cannot find module '../MembersAccessDialog'`.

- [ ] **Step 3: The wording** — `lib/membersAccess.ts`

```ts
import { GetDatasetDetailsResponse } from "../types/BffAPI";
import { ShareState } from "../types/GatekeeperAPI";

export function membersCanEditOf(dataset: GetDatasetDetailsResponse, state?: ShareState | null): boolean {
    if (state?.tenancy) {
        return state.tenancy.members_can_edit !== false;
    }
    return dataset?.members_can_edit !== false;
}

export function canChangeMembersAccess(dataset: GetDatasetDetailsResponse): boolean {
    return dataset?.access?.level === "owner";
}

export function membersAccessDetail(options: { membersCanEdit: boolean, embargoActive: boolean, members?: number | null }): string {
    if (options.embargoActive) {
        return `No access during the embargo · afterwards: ${options.membersCanEdit ? "read and edit" : "read only"}`;
    }
    const what = options.membersCanEdit ? "can read and edit" : "can read · editing limited to the people above";
    if (options.members === undefined || options.members === null) {
        return what;
    }
    return `${options.members} ${options.members === 1 ? "person" : "people"} · ${what}`;
}

export function membersAfterEmbargoLine(tenancyName: string, membersCanEdit: boolean): string {
    return membersCanEdit
        ? `When the embargo ends, members of ${tenancyName} can read and edit again.`
        : `When the embargo ends, members of ${tenancyName} can read but not edit.`;
}

export function membersOutcomeSentence(tenancyName: string, membersCanEdit: boolean): string {
    return membersCanEdit
        ? `Members of ${tenancyName} can read and edit this dataset again; the people you shared it with keep their access.`
        : `Members of ${tenancyName} can read this dataset; editing stays with the people you shared it with.`;
}
```

- [ ] **Step 4: The dialog** — `components/Share/MembersAccessDialog.tsx`

```tsx
import { useEffect, useState } from "react";
import Modal from "../base/PopupModal";

interface Props {
    show: boolean
    tenancyName: string
    membersCanEdit: boolean
    embargoActive: boolean
    busy?: boolean
    error?: string | null
    onCancel(): void
    onSave(membersCanEdit: boolean): void
}

export function MembersAccessDialog(props: Props) {
    const [choice, setChoice] = useState(props.membersCanEdit);

    useEffect(() => {
        if (props.show) {
            setChoice(props.membersCanEdit);
        }
    }, [props.show, props.membersCanEdit]);

    const options = [
        { value: true, label: "Read and edit", hint: `Their workspace role decides, as on any dataset of ${props.tenancyName}.` },
        { value: false, label: "Read only", hint: "They read and download. Editing, uploads and new versions stay with you and the people you share it with as Can write." },
    ];

    return (
        <Modal
            title={`What members of ${props.tenancyName} can do`}
            show={props.show}
            confimButtonText="Save"
            cancelButtonText="Cancel"
            cancel={props.onCancel}
            confim={() => props.onSave(choice)}
            confirmDisabled={props.busy}
            maxWidthClassName="max-w-[440px]"
        >
            <div className="flex flex-col gap-3">
                <fieldset className="flex flex-col gap-2.5 m-0 p-0 border-0">
                    <legend className="sr-only">What members can do</legend>
                    {options.map((option) => {
                        const selected = choice === option.value;
                        return (
                            <label key={option.label} className={`flex flex-col gap-1 m-0 rounded-md bg-primary-0 px-3.5 py-3 cursor-pointer ${selected ? "border-[1.5px] border-primary-900" : "border border-primary-200"}`}>
                                <span className="flex items-center gap-2 text-[13px] font-semibold text-primary-900">
                                    <input type="radio" name="membersAccess" checked={selected} onChange={() => setChoice(option.value)} className="h-3.5 w-3.5 p-0 accent-primary-900" />
                                    {option.label}
                                </span>
                                <span className="pl-[22px] text-xs leading-[17px] text-primary-600">{option.hint}</span>
                            </label>
                        );
                    })}
                </fieldset>
                {props.embargoActive && <p className="m-0 text-[13px] text-primary-500">Members have no access while the embargo lasts. This decides what they get when it ends.</p>}
                {props.error && <p role="alert" className="m-0 text-sm text-danger-700">{props.error}</p>}
            </div>
        </Modal>
    );
}
```

The option cards are the ones `EmbargoFields` uses for the members' visibility (§1a), so the two choices about members look alike.

- [ ] **Step 5: The hook** — `hooks/UseMembersAccess.ts`

```ts
import { useRouter } from "next/router";
import { useRef, useState } from "react";
import { messageForApiError } from "../contants/EmbargoConstants";
import { BFFAPI } from "../gateways/BFFAPI";

export function useMembersAccess(datasetId: string, afterSave?: () => Promise<unknown>) {
    const router = useRouter();
    const [bffGateway] = useState(() => new BFFAPI());
    const [editing, setEditing] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const busyRef = useRef(false);

    async function save(membersCanEdit: boolean) {
        if (busyRef.current) {
            return;
        }
        busyRef.current = true;
        setBusy(true);
        setError(null);
        try {
            await bffGateway.setMembersAccess(datasetId, { members_can_edit: membersCanEdit });
            await afterSave?.();
            await router.replace(router.asPath, undefined, { scroll: false });
            setEditing(false);
        } catch (e) {
            setError(messageForApiError(e));
        } finally {
            busyRef.current = false;
            setBusy(false);
        }
    }

    return {
        editing,
        busy,
        error,
        open: () => {
            setError(null);
            setEditing(true);
        },
        close: () => setEditing(false),
        save,
    };
}
```

The hook is exercised through the components that use it, in Tasks 8 and 9.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/membersAccess.test.ts components/Share/__tests__/MembersAccessDialog.test.tsx`
Expected: PASS (6 + 6 tests).

- [ ] **Step 7: Commit**

```bash
git add lib/membersAccess.ts lib/__tests__/membersAccess.test.ts components/Share/MembersAccessDialog.tsx components/Share/__tests__/MembersAccessDialog.test.tsx hooks/UseMembersAccess.ts
git commit -m "feat: one place for what members can do, the dialog that changes it, and its save"
```

---

### Task 8: Share dialog row

**Repo:** webapp. **Design:** §1c, the "Members of Data Amazon" row.

The row becomes the control. Without an embargo it reads `14 people · can read and edit`, or `14 people · can read · editing limited to the people above`; during an embargo, `No access during the embargo · afterwards: read and edit` (or `read only`). The owner sees a `Change` link that opens the dialog of Task 7; everyone else sees the text alone.

The design draws this row first. It moves to the end of *Who has access*, after the owner, the people and the pending invitations: the read-only wording says editing is "limited to the people above", which is true only below them. It is also shown during an embargo now, when `ShareState.tenancy` is `null`, because what members get afterwards is exactly what the owner may want to change then; the dataset payload carries the value.

**Files:**
- Modify: `components/Share/AccessList.tsx`
- Modify: `components/Share/ShareDialog.tsx`
- Test: `components/Share/__tests__/AccessList.test.tsx`, `components/Share/__tests__/ShareDialog.test.tsx`

**Interfaces:**
- Consumes: Task 7's `membersCanEditOf`, `canChangeMembersAccess`, `membersAccessDetail`, `MembersAccessDialog`, `useMembersAccess`; plan 05's `tenancyDisplayName`.
- Produces: `AccessList` props `members?: MembersRow | null` and `onChangeMembers?(): void`; `export interface MembersRow { tenancyName: string, detail: string, canChange: boolean }`. `AccessList` no longer reads `state.tenancy` itself.

- [ ] **Step 1: Write the failing tests**

In `components/Share/__tests__/AccessList.test.tsx`, replace the test `"without an embargo the workspace is the first row"` with:

```tsx
    test("the members row comes last, after the people it refers to", () => {
        render(<AccessList
            state={state}
            members={{ tenancyName: "Data Amazon", detail: "14 people · can read · editing limited to the people above", canChange: false }}
            onChangeLevel={jest.fn()}
            onRemove={jest.fn()}
            onRevokeInvitation={jest.fn()}
        />);

        const rows = screen.getAllByRole("listitem");
        expect(rows[rows.length - 1].textContent).toContain("Members of Data Amazon");
        expect(screen.getByText("14 people · can read · editing limited to the people above")).toBeTruthy();
        expect(screen.queryByRole("button", { name: /Change what members/ })).toBeNull();
    });

    test("the owner changes what members can do from the row", () => {
        const onChangeMembers = jest.fn();
        render(<AccessList
            state={state}
            members={{ tenancyName: "Data Amazon", detail: "14 people · can read and edit", canChange: true }}
            onChangeMembers={onChangeMembers}
            onChangeLevel={jest.fn()}
            onRemove={jest.fn()}
            onRevokeInvitation={jest.fn()}
        />);

        fireEvent.click(screen.getByRole("button", { name: "Change what members of Data Amazon can do" }));

        expect(onChangeMembers).toHaveBeenCalled();
    });

    test("without a members row, the state's tenancy is not shown on its own", () => {
        renderList({ tenancy: { name: "Data Amazon", path: "datamap/production/data-amazon", members: 14, members_can_edit: true } });

        expect(screen.queryByText("Members of Data Amazon")).toBeNull();
    });
```

In `components/Share/__tests__/ShareDialog.test.tsx`, add next to the other mocked functions at the top:

```tsx
const setMembersAccess = jest.fn() as any;
const replace = jest.fn(async () => true);
```

add `setMembersAccess` to the object the `BFFAPI` mock returns:

```tsx
jest.mock("../../../gateways/BFFAPI", () => ({
    BFFAPI: jest.fn().mockImplementation(() => ({ grantAccess, createAnonymousLink, revokePermission, revokeAnonymousLink, searchShareCandidates, setMembersAccess })),
}));
```

add, after the `next-auth/react` mock:

```tsx
jest.mock("next/router", () => ({ useRouter: () => ({ replace, asPath: "/app/datasets/d2" }) }));
```

and append inside `describe("ShareDialog", ...)`:

```tsx
    test("without an embargo the owner changes what members can do", async () => {
        shareState = stateWith({ tenancy: { name: "Data Amazon", path: "datamap/production/data-amazon", members: 14, members_can_edit: true } });
        setMembersAccess.mockResolvedValue({ members_can_edit: false, access: { level: "owner" } });
        render(<ShareDialog dataset={{ ...open, access: { level: "owner" }, members_can_edit: true }} show onClose={jest.fn()} />);

        expect(screen.getByText("14 people · can read and edit")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Change what members of Data Amazon can do" }));
        fireEvent.click(screen.getByRole("radio", { name: /Read only/ }));
        fireEvent.click(screen.getByRole("button", { name: "Save" }));

        await waitFor(() => expect(setMembersAccess).toHaveBeenCalledWith("d2", { members_can_edit: false }));
        await waitFor(() => expect(replace).toHaveBeenCalledWith("/app/datasets/d2", undefined, { scroll: false }));
        expect(mutate).toHaveBeenCalled();
        await waitFor(() => expect(screen.queryByRole("dialog", { name: "What members of Data Amazon can do" })).toBeNull());
        expect(screen.getByRole("dialog", { name: "Share" })).toBeTruthy();
    });

    test("during an embargo the row says what members get afterwards", () => {
        shareState = stateWith({ tenancy: null });
        render(<ShareDialog dataset={{ ...embargoed, access: { level: "owner" }, members_can_edit: false }} show onClose={jest.fn()} />);

        expect(screen.getByText("No access during the embargo · afterwards: read only")).toBeTruthy();
        expect(screen.getByRole("button", { name: "Change what members of Data Amazon can do" })).toBeTruthy();
    });

    test("someone who is not the owner reads the row and cannot change it", () => {
        shareState = stateWith({ tenancy: { name: "Data Amazon", path: "datamap/production/data-amazon", members: 14, members_can_edit: false } });
        render(<ShareDialog dataset={{ ...open, access: { level: "write" } }} show onClose={jest.fn()} />);

        expect(screen.getByText("14 people · can read · editing limited to the people above")).toBeTruthy();
        expect(screen.queryByRole("button", { name: /Change what members/ })).toBeNull();
    });

    test("a refused change is shown in the members dialog", async () => {
        shareState = stateWith({ tenancy: { name: "Data Amazon", path: "datamap/production/data-amazon", members: 14, members_can_edit: true } });
        setMembersAccess.mockRejectedValue({ httpCode: 403 });
        render(<ShareDialog dataset={{ ...open, access: { level: "owner" } }} show onClose={jest.fn()} />);

        fireEvent.click(screen.getByRole("button", { name: "Change what members of Data Amazon can do" }));
        fireEvent.click(screen.getByRole("button", { name: "Save" }));

        expect(await screen.findByText("You are not allowed to do this on this dataset.")).toBeTruthy();
    });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npx jest components/Share/__tests__/AccessList.test.tsx components/Share/__tests__/ShareDialog.test.tsx`
Expected: FAIL — the new `AccessList` tests find the members row first (or not at all) and no Change button; the new `ShareDialog` tests find neither `14 people · can read and edit` nor the Change button. The tests of plan 05 still pass.

- [ ] **Step 3: The row** — `components/Share/AccessList.tsx`

Replace the `Props` interface with:

```tsx
interface Props {
    state: ShareState
    me?: string
    busy?: boolean
    onChangeLevel(userId: string, level: PermissionLevel): void
    onRemove(permission: SharePermission): void
    onRevokeInvitation(invitationId: string): void
    members?: MembersRow | null
    onChangeMembers?(): void
}

export interface MembersRow {
    tenancyName: string
    detail: string
    canChange: boolean
}
```

Delete the first item of the list, the block that starts `{props.state.tenancy &&` and renders `Members of {props.state.tenancy.name}` with `{props.state.tenancy.members} people · workspace default` and `Can read`.

Then, right before the closing `</ul>`, after the `{pending.map(...)}` block, add:

```tsx
                {props.members &&
                    <li className={SHARE_ROW_CLASS}>
                        <span aria-hidden="true" className="flex items-center justify-center h-8 w-8 rounded-full bg-secondary-500 text-primary-900">
                            <MaterialSymbol icon="groups" size={18} grade={-25} weight={400} />
                        </span>
                        <span className="flex flex-col min-w-0">
                            <span className={SHARE_PERSON_NAME_CLASS}>Members of {props.members.tenancyName}</span>
                            <span className={SHARE_PERSON_DETAIL_CLASS}>{props.members.detail}</span>
                        </span>
                        {props.members.canChange
                            ? <button
                                type="button"
                                aria-label={`Change what members of ${props.members.tenancyName} can do`}
                                className="text-[13px] font-medium text-primary-600 hover:underline underline-offset-2 disabled:opacity-50 disabled:no-underline disabled:cursor-not-allowed"
                                disabled={props.busy}
                                onClick={() => props.onChangeMembers?.()}
                            >
                                Change
                            </button>
                            : <span></span>}
                    </li>
                }
```

The empty `<span>` keeps the row's third grid column, so the text lines up with the people above whether or not there is a link.

- [ ] **Step 4: The dialog wiring** — `components/Share/ShareDialog.tsx`

Add the imports:

```tsx
import { useMembersAccess } from "../../hooks/UseMembersAccess";
import { canChangeMembersAccess, membersAccessDetail, membersCanEditOf } from "../../lib/membersAccess";
import { MembersAccessDialog } from "./MembersAccessDialog";
```

Right after `const state = data as ShareState;` and before `if (!props.show) {`, so the hook runs on every render:

```tsx
    const membersAccess = useMembersAccess(datasetId, () => mutate());
```

After the `if (!props.show) { return null; }` block:

```tsx
    const tenancyName = tenancyDisplayName(props.dataset.tenancy);
    const membersCanEdit = membersCanEditOf(props.dataset, state);
    const membersRow = props.dataset.tenancy && (state?.tenancy || embargoActive)
        ? {
            tenancyName,
            canChange: canChangeMembersAccess(props.dataset),
            detail: membersAccessDetail({ membersCanEdit, embargoActive, members: state?.tenancy?.members ?? null }),
        }
        : null;
```

In the `<ShareInput ... />` element, `tenancyName={tenancyDisplayName(props.dataset.tenancy)}` becomes `tenancyName={tenancyName}`. In the `<AccessList ... />` element, add after `onRevokeInvitation={...}`:

```tsx
                                members={membersRow}
                                onChangeMembers={membersAccess.open}
```

And after the `<RemoveAccessDialog ... />` element, before the closing `</>`:

```tsx
            <MembersAccessDialog
                show={membersAccess.editing}
                tenancyName={tenancyName}
                membersCanEdit={membersCanEdit}
                embargoActive={embargoActive}
                busy={membersAccess.busy}
                error={membersAccess.error}
                onCancel={membersAccess.close}
                onSave={membersAccess.save}
            />
```

The share state is refetched (`mutate`) and the page's props replaced after a save, so the row reads the new value from either source; the share dialog stays open.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npx jest components/Share`
Expected: PASS, every test in `components/Share/__tests__`.

- [ ] **Step 6: Compare with the design**

Run `npm run dev` against a gatekeeper with Tasks 1–5, open a dataset you own, without an embargo, and open Share. Next to §1c of `docs/design/rfc-003-embargo/Embargo Feature.dc.html`: the members row has the same avatar, name and type sizes, now last in the list, with `Change` where the design has `Can read`. Change it to Read only: the row reads `… · can read · editing limited to the people above`, the dialog stays open. Set an embargo: the row reads `No access during the embargo · afterwards: read only`.

- [ ] **Step 7: Commit**

```bash
git add components/Share/AccessList.tsx components/Share/ShareDialog.tsx components/Share/__tests__/AccessList.test.tsx components/Share/__tests__/ShareDialog.test.tsx
git commit -m "feat: the share dialog's members row says what members can do, and the owner changes it there"
```

---

### Task 9: Settings → Access row

**Repo:** webapp. **Design:** §1g, the *Access* block of Settings.

The Access block gains a second row under the people: `Members of Data Amazon`, the same text as the share dialog's row, and `Change` for the owner. It shows wherever the block shows (owner and `write` holders, plan 05).

**Files:**
- Modify: `components/Embargo/AccessSummary.tsx`
- Create: `components/Embargo/__tests__/AccessSummary.test.tsx`

**Interfaces:**
- Consumes: Task 7's `membersCanEditOf`, `canChangeMembersAccess`, `membersAccessDetail`, `MembersAccessDialog`, `useMembersAccess`; plan 05's `SettingsBlock`, `ShareDialog`, `tenancyDisplayName`.
- Produces: nothing other tasks consume.

- [ ] **Step 1: Write the failing test** — `components/Embargo/__tests__/AccessSummary.test.tsx`

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const setMembersAccess = jest.fn() as any;
const replace = jest.fn(async () => true);
const mutate = jest.fn(async () => undefined);
let shareState: any;

jest.mock("../../../gateways/BFFAPI", () => ({ BFFAPI: jest.fn().mockImplementation(() => ({ setMembersAccess })) }));
jest.mock("swr", () => ({ __esModule: true, default: () => ({ data: shareState, error: undefined, mutate }) }));
jest.mock("next/router", () => ({ useRouter: () => ({ replace, asPath: "/app/datasets/d1" }) }));
jest.mock("next-auth/react", () => ({ useSession: () => ({ data: null }) }));
jest.mock("../../../lib/fetcher", () => ({ fetcher: jest.fn() }));

import { AccessSummary } from "../AccessSummary";

const owner = { level: "owner", can_edit: true, can_share: true, can_manage_embargo: true, can_extend_embargo: false, can_delete: true };

function stateWith(tenancy: any) {
    return {
        owner: { id: "o", name: "Luciana Rizzo", email: "l@usp.br" },
        permissions: [{ user: { id: "u2", name: "Alan Calheiros", email: "a@inpe.br" }, level: "write" }],
        invitations: [],
        anonymous_links: [],
        tenancy,
    };
}

describe("AccessSummary", () => {
    test("the people, then what members of the workspace can do", () => {
        shareState = stateWith({ name: "Data Amazon", path: "datamap/production/data-amazon", members: 14, members_can_edit: true });
        render(<AccessSummary dataset={{ id: "d1", tenancy: "datamap/production/data-amazon", access: owner, embargo: null, members_can_edit: true } as any} />);

        expect(screen.getByText("Luciana Rizzo, Alan Calheiros (write)")).toBeTruthy();
        expect(screen.getByText("Members of Data Amazon")).toBeTruthy();
        expect(screen.getByText("14 people · can read and edit")).toBeTruthy();
    });

    test("the owner changes it from Settings", async () => {
        shareState = stateWith({ name: "Data Amazon", path: "datamap/production/data-amazon", members: 14, members_can_edit: true });
        setMembersAccess.mockResolvedValue({ members_can_edit: false, access: owner });
        render(<AccessSummary dataset={{ id: "d1", tenancy: "datamap/production/data-amazon", access: owner, embargo: null, members_can_edit: true } as any} />);

        fireEvent.click(screen.getByRole("button", { name: "Change what members of Data Amazon can do" }));
        fireEvent.click(screen.getByRole("radio", { name: /Read only/ }));
        fireEvent.click(screen.getByRole("button", { name: "Save" }));

        await waitFor(() => expect(setMembersAccess).toHaveBeenCalledWith("d1", { members_can_edit: false }));
        await waitFor(() => expect(replace).toHaveBeenCalledWith("/app/datasets/d1", undefined, { scroll: false }));
        expect(mutate).toHaveBeenCalled();
    });

    test("during an embargo it says what members get afterwards", () => {
        shareState = stateWith(null);
        render(<AccessSummary dataset={{ id: "d1", tenancy: "datamap/production/data-amazon", access: owner, embargo: { active: true, until: "2026-12-15T23:59:59+00:00" }, members_can_edit: false } as any} />);

        expect(screen.getByText("No access during the embargo · afterwards: read only")).toBeTruthy();
    });

    test("a write holder reads it and cannot change it", () => {
        shareState = stateWith({ name: "Data Amazon", path: "datamap/production/data-amazon", members: 14, members_can_edit: false });
        render(<AccessSummary dataset={{ id: "d1", tenancy: "datamap/production/data-amazon", access: { ...owner, level: "write", can_manage_embargo: false }, embargo: null } as any} />);

        expect(screen.getByText("14 people · can read · editing limited to the people above")).toBeTruthy();
        expect(screen.queryByRole("button", { name: /Change what members/ })).toBeNull();
    });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx jest components/Embargo/__tests__/AccessSummary.test.tsx`
Expected: FAIL — `Unable to find an element with the text: Members of Data Amazon` (the first test passes its first assertion).

- [ ] **Step 3: Implement** — `components/Embargo/AccessSummary.tsx`

```tsx
import { useState } from "react";
import useSWR from "swr";
import { useMembersAccess } from "../../hooks/UseMembersAccess";
import { tenancyDisplayName } from "../../lib/embargoDisplay";
import { fetcher } from "../../lib/fetcher";
import { canChangeMembersAccess, membersAccessDetail, membersCanEditOf } from "../../lib/membersAccess";
import { GetDatasetDetailsResponse } from "../../types/BffAPI";
import { ShareState } from "../../types/GatekeeperAPI";
import { MembersAccessDialog } from "../Share/MembersAccessDialog";
import { ShareDialog } from "../Share/ShareDialog";
import { SettingsBlock } from "./EmbargoSettingsSection";

export function AccessSummary(props: { dataset: GetDatasetDetailsResponse }) {
    const [show, setShow] = useState(false);
    const canShare = props.dataset.access?.can_share === true;
    const { data, mutate } = useSWR(canShare ? `/api/datasets/${props.dataset.id}/share` : null, fetcher);
    const state = data as ShareState;
    const membersAccess = useMembersAccess(props.dataset.id, () => mutate());

    if (!canShare || !state) {
        return null;
    }

    const names = [state.owner.name, ...state.permissions.map((p) => p.level === "write" ? `${p.user.name} (write)` : p.user.name)];
    const pending = state.invitations.filter((i) => !i.accepted_at && !i.revoked_at).length;
    const links = state.anonymous_links.filter((l) => !l.revoked_at).length;
    const parts = [names.join(", "), pending ? `${pending} pending` : "", links ? `${links} anonymous link${links === 1 ? "" : "s"}` : ""].filter(Boolean);
    const embargoActive = props.dataset.embargo?.active === true;
    const tenancyName = tenancyDisplayName(props.dataset.tenancy);
    const membersCanEdit = membersCanEditOf(props.dataset, state);
    const showMembers = !!props.dataset.tenancy && (!!state.tenancy || embargoActive);

    return (
        <SettingsBlock title="Access">
            <div className="rounded-lg border border-primary-200 bg-primary-0 text-sm">
                <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-3.5 border-b border-primary-100 last:border-b-0">
                    <span className="min-w-0 text-primary-900">{parts.join(" · ")}</span>
                    <button type="button" className="text-[13px] font-medium text-primary-600 hover:underline underline-offset-2" onClick={() => setShow(true)}>Open share dialog</button>
                </div>
                {showMembers &&
                    <div className="grid grid-cols-[180px_minmax(0,1fr)_auto] gap-x-3 items-center px-4 py-3.5">
                        <span className="text-primary-500">Members of {tenancyName}</span>
                        <span className="min-w-0 text-primary-900">
                            {membersAccessDetail({ membersCanEdit, embargoActive, members: state.tenancy?.members ?? null })}
                        </span>
                        {canChangeMembersAccess(props.dataset)
                            ? <button
                                type="button"
                                aria-label={`Change what members of ${tenancyName} can do`}
                                className="text-[13px] font-medium text-primary-600 hover:underline underline-offset-2"
                                onClick={membersAccess.open}
                            >
                                Change
                            </button>
                            : <span></span>}
                    </div>
                }
            </div>
            <ShareDialog dataset={props.dataset} show={show} onClose={() => setShow(false)} />
            <MembersAccessDialog
                show={membersAccess.editing}
                tenancyName={tenancyName}
                membersCanEdit={membersCanEdit}
                embargoActive={embargoActive}
                busy={membersAccess.busy}
                error={membersAccess.error}
                onCancel={membersAccess.close}
                onSave={membersAccess.save}
            />
        </SettingsBlock>
    );
}
```

The members row uses the `180px` label column of the embargo block's rows above it in Settings (`EmbargoSettingsSection`'s `Row`), so the two blocks line up.

- [ ] **Step 4: Run it to verify it passes**

Run: `npx jest components/Embargo/__tests__/AccessSummary.test.tsx components/Share`
Expected: PASS.

- [ ] **Step 5: Compare with the design**

In the running app, open Settings on a dataset you own: next to §1g, the Access block keeps its people line and *Open share dialog*, and has the members row under it with the same label colour and spacing as the Embargo block's rows. Change it here, then open Share: the share dialog's row says the same.

- [ ] **Step 6: Commit**

```bash
git add components/Embargo/AccessSummary.tsx components/Embargo/__tests__/AccessSummary.test.tsx
git commit -m "feat: Settings shows and changes what members can do"
```

---

### Task 10: Set-embargo dialog and creation

**Repo:** webapp. **Design:** §1a (the embargo choice at creation) and §1d (*Put under embargo*), both built on `EmbargoFields`.

Under the choice of what members see during the embargo, one line says what they get after it: `When the embargo ends, members of Data Amazon can read and edit again. Change`. `Change` opens the dialog of Task 7; the choice is a form value, sent when the form is, so nothing is saved for a dataset the author then abandons. It is sent **before** the embargo: a failure between the two calls leaves at most the members' setting changed, which retrying the form repeats harmlessly, and never an embargo whose aftermath is the default against the author's choice. At creation, plan 05's `finishDatasetCreation` already retries the embargo step and tolerates `embargo_already_active`.

**Files:**
- Modify: `components/Embargo/EmbargoFields.tsx`
- Modify: `components/Embargo/SetEmbargoDialog.tsx`
- Modify: `pages/app/datasets/new.tsx`, `types/new-dataset.d.ts`
- Test: `components/Embargo/__tests__/EmbargoChoice.test.tsx` (append), `components/Embargo/__tests__/SetEmbargoDialog.test.tsx` (create)

**Interfaces:**
- Consumes: Task 6's `BFFAPI.setMembersAccess`; Task 7's `membersAfterEmbargoLine`, `MembersAccessDialog`; plan 05's `EmbargoFields`, `EmbargoChoice`, `embargoRequestFrom`, `finishDatasetCreation`.
- Produces: the Formik value `membersCanEdit: boolean` read by `EmbargoFields` (a missing value reads as `true`).

- [ ] **Step 1: Write the failing tests**

Append inside `describe("EmbargoChoice", ...)` in `components/Embargo/__tests__/EmbargoChoice.test.tsx` (add `fireEvent` to its `@testing-library/react` import):

```tsx
    test("a line under the members choice says what they get afterwards, and Change switches it", async () => {
        renderChoice();

        await clickRadio(/Under embargo/);

        expect(screen.getByText("When the embargo ends, members of Data Amazon can read and edit again.")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Change what members of Data Amazon can do" }));
        expect(screen.getByText("Members have no access while the embargo lasts. This decides what they get when it ends.")).toBeTruthy();
        await act(async () => {
            fireEvent.click(screen.getByRole("radio", { name: /Read only/ }));
            fireEvent.click(screen.getByRole("button", { name: "Save" }));
        });

        expect(screen.getByText("When the embargo ends, members of Data Amazon can read but not edit.")).toBeTruthy();
        expect(screen.queryByRole("dialog", { name: "What members of Data Amazon can do" })).toBeNull();
    });
```

Create `components/Embargo/__tests__/SetEmbargoDialog.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { beforeEach, describe, expect, jest, test } from '@jest/globals';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

const setEmbargo = jest.fn() as any;
const setMembersAccess = jest.fn() as any;
const reload = jest.fn();

jest.mock("next/router", () => ({ useRouter: () => ({ reload }) }));
jest.mock("../../../gateways/BFFAPI", () => ({
    BFFAPI: jest.fn().mockImplementation(() => ({ setEmbargo, setMembersAccess })),
}));

import { SetEmbargoDialog } from "../SetEmbargoDialog";

const dataset: any = { id: "d1", tenancy: "datamap/production/data-amazon", embargo: null, members_can_edit: true };

beforeEach(() => {
    jest.useFakeTimers({ now: new Date("2026-10-01T10:00:00Z"), doNotFake: ["setTimeout", "setInterval", "queueMicrotask", "nextTick"] });
    setEmbargo.mockReset();
    setMembersAccess.mockReset();
    setEmbargo.mockResolvedValue({ active: true });
    setMembersAccess.mockResolvedValue({ members_can_edit: false });
});

function pickDate() {
    fireEvent.change(screen.getByLabelText("Embargo ends"), { target: { value: "2026-11-15" } });
}

describe("SetEmbargoDialog", () => {
    test("a changed members' setting is sent first, then the embargo", async () => {
        render(<SetEmbargoDialog dataset={dataset} show onClose={jest.fn()} />);
        pickDate();

        fireEvent.click(screen.getByRole("button", { name: "Change what members of Data Amazon can do" }));
        await act(async () => {
            fireEvent.click(screen.getByRole("radio", { name: /Read only/ }));
            fireEvent.click(screen.getByRole("button", { name: "Save" }));
        });
        expect(screen.getByText("When the embargo ends, members of Data Amazon can read but not edit.")).toBeTruthy();
        await act(async () => {
            fireEvent.click(screen.getByRole("button", { name: "Set embargo" }));
        });

        await waitFor(() => expect(setEmbargo).toHaveBeenCalled());
        expect(setMembersAccess).toHaveBeenCalledWith("d1", { members_can_edit: false });
        expect(setMembersAccess.mock.invocationCallOrder[0]).toBeLessThan(setEmbargo.mock.invocationCallOrder[0]);
    });

    test("an unchanged setting sends only the embargo", async () => {
        render(<SetEmbargoDialog dataset={dataset} show onClose={jest.fn()} />);
        pickDate();

        await act(async () => {
            fireEvent.click(screen.getByRole("button", { name: "Set embargo" }));
        });

        await waitFor(() => expect(setEmbargo).toHaveBeenCalledWith("d1", {
            until: "2026-11-15T23:59:59+00:00",
            metadata_visible: false,
            note: null,
        }));
        expect(setMembersAccess).not.toHaveBeenCalled();
    });

    test("a dataset already read-only starts from read-only", () => {
        render(<SetEmbargoDialog dataset={{ ...dataset, members_can_edit: false }} show onClose={jest.fn()} />);

        expect(screen.getByText("When the embargo ends, members of Data Amazon can read but not edit.")).toBeTruthy();
    });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npx jest components/Embargo/__tests__/EmbargoChoice.test.tsx components/Embargo/__tests__/SetEmbargoDialog.test.tsx`
Expected: FAIL — `Unable to find an element with the text: When the embargo ends, members of Data Amazon can read and edit again.` (and `…can read but not edit.`); `an unchanged setting sends only the embargo` passes already.

- [ ] **Step 3: The line** — `components/Embargo/EmbargoFields.tsx`

Change the imports at the top to:

```tsx
import { ErrorMessage, Field, useFormikContext } from "formik";
import { useState } from "react";
import { MaterialSymbol } from "react-material-symbols";
import { EDIT_FORM_ERROR_CLASS, EDIT_FORM_INPUT_CLASS } from "../../contants/EditFormConstants";
import { maxEmbargoDate, minEmbargoDate, toEmbargoUntil } from "../../lib/embargoDates";
import { daysFromToday, formatShortDate } from "../../lib/embargoDisplay";
import { membersAfterEmbargoLine } from "../../lib/membersAccess";
import { MembersAccessDialog } from "../Share/MembersAccessDialog";
```

add to the `Values` interface:

```tsx
    membersCanEdit?: boolean
```

add, at the top of `EmbargoFields`, after `const { values, setFieldValue } = useFormikContext<Values>();`:

```tsx
    const [changingMembers, setChangingMembers] = useState(false);
    const membersCanEdit = values.membersCanEdit !== false;
```

and, right after the closing `</fieldset>` of the members' choice (before the amber `info` notice):

```tsx
            <p className="m-0 -mt-2 text-xs leading-[17px] text-primary-600">
                {membersAfterEmbargoLine(props.tenancyName, membersCanEdit)}{" "}
                <button
                    type="button"
                    aria-label={`Change what members of ${props.tenancyName} can do`}
                    disabled={props.disabled}
                    onClick={() => setChangingMembers(true)}
                    className="font-semibold text-primary-900 underline underline-offset-2 disabled:opacity-50 disabled:no-underline disabled:cursor-not-allowed"
                >
                    Change
                </button>
            </p>
            <MembersAccessDialog
                show={changingMembers}
                tenancyName={props.tenancyName}
                membersCanEdit={membersCanEdit}
                embargoActive
                onCancel={() => setChangingMembers(false)}
                onSave={(value) => {
                    setFieldValue("membersCanEdit", value);
                    setChangingMembers(false);
                }}
            />
```

`Change` follows the fields' `disabled` prop: at creation, once the embargo step has gone through, plan 05 locks the embargo fields, and the members' setting was sent with it. `embargoActive` is set because the dialog is opened while choosing an embargo: its note, that members have no access while it lasts and this decides what they get after, is exactly the situation.

- [ ] **Step 4: The dialog sends it** — `components/Embargo/SetEmbargoDialog.tsx`

Replace the `formik` declaration with:

```tsx
    const membersCanEdit = props.dataset.members_can_edit !== false;
    const formik = useFormik({
        initialValues: { embargoMode: "hidden", embargoUntil: "", embargoNote: "", membersCanEdit },
        validate: (values) => {
            const message = validateEmbargoDate(values.embargoUntil, new Date());
            return message ? { embargoUntil: message } : {};
        },
        onSubmit: async (values) => {
            setError(null);
            try {
                if (values.membersCanEdit !== membersCanEdit) {
                    await bffGateway.setMembersAccess(props.dataset.id, { members_can_edit: values.membersCanEdit });
                }
                const request = embargoRequestFrom(values as any);
                await bffGateway.setEmbargo(props.dataset.id, { ...request, note: values.embargoNote.trim() || null });
                props.onClose();
                router.reload();
            } catch (e) {
                setError(messageForApiError(e));
            }
        },
    });
```

- [ ] **Step 5: Creation sends it** — `pages/app/datasets/new.tsx` and `types/new-dataset.d.ts`

In `types/new-dataset.d.ts`, add to `FormValues` after `embargoNote?: string`:

```ts
    membersCanEdit?: boolean
```

In `pages/app/datasets/new.tsx`, `initialValues` gains, after `embargoNote: ''`:

```tsx
    membersCanEdit: true
```

(with a comma after `embargoNote: ''`), and the `setEmbargo` step passed to `finishDatasetCreation` becomes:

```tsx
      setEmbargo: embargoRequest
        ? async () => {
          if (values.membersCanEdit === false) {
            await bffGateway.setMembersAccess(datasetId, { members_can_edit: false });
          }
          return bffGateway.setEmbargo(datasetId, { ...embargoRequest, note: values.embargoNote?.trim() || null });
        }
        : null,
```

A new dataset starts with `members_can_edit: true`, so only `false` needs a call. An open dataset (no embargo chosen) never shows the line and sends nothing.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npx jest components/Embargo`
Expected: PASS, plan 05's `EmbargoChoice` tests included.

- [ ] **Step 7: Type-check**

Run: `npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E "EmbargoFields|SetEmbargoDialog|datasets/new|new-dataset" || echo "no new type errors"`
Expected: `no new type errors`

- [ ] **Step 8: Compare with the design**

In the running app, start a new dataset and choose *Under embargo*: next to §1a, the line sits under the two "other members" cards, in the cards' hint size, with `Change` underlined. Choose Read only in the dialog, create the dataset, and open its Settings: the Access block reads `No access during the embargo · afterwards: read only`. On a dataset without an embargo, *Set embargo* in Settings (§1d) shows the same line.

- [ ] **Step 9: Commit**

```bash
git add components/Embargo/EmbargoFields.tsx components/Embargo/SetEmbargoDialog.tsx pages/app/datasets/new.tsx types/new-dataset.d.ts components/Embargo/__tests__/EmbargoChoice.test.tsx components/Embargo/__tests__/SetEmbargoDialog.test.tsx
git commit -m "feat: setting an embargo says what members get when it ends, and lets the owner change it"
```

---

### Task 11: Ended banner and History

**Repo:** webapp. **Design:** §1h (the owner's banner after the embargo) and §1g (History).

The banner's checklist says the files are available to every member; a second ticked line says what those members may do: `Members of Data Amazon can read and edit this dataset again; the people you shared it with keep their access.` or `Members of Data Amazon can read this dataset; editing stays with the people you shared it with.` The banner is the owner's (plan 05's `shouldShowEmbargoEndedBanner`), so the sentence speaks to the owner. The History words the new event.

**Files:**
- Modify: `components/Embargo/EmbargoEndedBanner.tsx`, `components/Embargo/__tests__/EmbargoEndedBanner.test.tsx`
- Modify: `lib/embargoDisplay.ts` (`describeAccessEvent`), `lib/__tests__/embargoDisplay.test.ts`

**Interfaces:**
- Consumes: Task 7's `membersOutcomeSentence`; plan 05's `describeAccessEvent`, `AccessHistoryEntry`.
- Produces: `describeAccessEvent` handles `event_type: "members_access_changed"`.

- [ ] **Step 1: Write the failing tests**

Append inside `describe("EmbargoEndedBanner", ...)` in `components/Embargo/__tests__/EmbargoEndedBanner.test.tsx`:

```tsx
    test("it says what members got back, by default read and edit", () => {
        render(<EmbargoEndedBanner dataset={dataset} />);

        expect(screen.getByRole("status").textContent)
            .toContain("Members of Data Amazon can read and edit this dataset again; the people you shared it with keep their access.");
    });

    test("with members read-only, editing stays with the people shared with", () => {
        render(<EmbargoEndedBanner dataset={{ ...dataset, members_can_edit: false }} />);

        const banner = screen.getByRole("status");
        expect(banner.textContent)
            .toContain("Members of Data Amazon can read this dataset; editing stays with the people you shared it with.");
        expect(banner.textContent).not.toContain("can read and edit");
    });
```

Append inside `describe("describeAccessEvent", ...)` in `lib/__tests__/embargoDisplay.test.ts`:

```ts
    test("what members can do, either way", () => {
        expect(describeAccessEvent(entry({ event_type: "members_access_changed", old_value: { members_can_edit: true }, new_value: { members_can_edit: false } })))
            .toEqual({ icon: "edit_off", who: "Luciana Rizzo", what: "made the dataset read only for members of the workspace", detail: "was read and edit" });
        expect(describeAccessEvent(entry({ event_type: "members_access_changed", old_value: { members_can_edit: false }, new_value: { members_can_edit: true } })))
            .toEqual({ icon: "edit", who: "Luciana Rizzo", what: "let members of the workspace edit the dataset", detail: "was read only" });
    });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npx jest components/Embargo/__tests__/EmbargoEndedBanner.test.tsx lib/__tests__/embargoDisplay.test.ts`
Expected: FAIL — the banner lacks the sentence, and `describeAccessEvent` falls to its default and answers `{ icon: "history", what: "members access changed", … }`.

- [ ] **Step 3: The banner** — `components/Embargo/EmbargoEndedBanner.tsx`

Add the import:

```tsx
import { membersOutcomeSentence } from "../../lib/membersAccess";
```

and, right after the checklist's first item — the `<div className="flex gap-2.5">` whose text is `Files are available to every member of {tenancy}.` — add a second ticked item:

```tsx
                    <div className="flex gap-2.5">
                        <MaterialSymbol icon="check_circle" size={18} grade={-25} weight={400} fill className="flex-none text-success-500" aria-hidden="true" />
                        <span>{membersOutcomeSentence(tenancy, props.dataset.members_can_edit !== false)}</span>
                    </div>
```

- [ ] **Step 4: The History** — `lib/embargoDisplay.ts`

In `describeAccessEvent`, add before `case "permission_granted":`:

```ts
        case "members_access_changed":
            return after.members_can_edit
                ? { icon: "edit", who, what: "let members of the workspace edit the dataset", detail: "was read only" }
                : { icon: "edit_off", who, what: "made the dataset read only for members of the workspace", detail: "was read and edit" };
```

The entry carries no tenancy name (`subject` is `null` for this event), so it says "the workspace", as the embargo entries do with "members".

- [ ] **Step 5: Run them to verify they pass**

Run: `npx jest components/Embargo/__tests__/EmbargoEndedBanner.test.tsx lib/__tests__/embargoDisplay.test.ts`
Expected: PASS.

- [ ] **Step 6: Compare with the design**

In the running app, end an embargo early on a dataset you own whose members are read-only: next to §1h, the banner's checklist has the files line, then the members line with the same tick, then the DOI line. Open Settings › History: the change of the members' access is listed with your name, newest first.

- [ ] **Step 7: Commit**

```bash
git add components/Embargo/EmbargoEndedBanner.tsx components/Embargo/__tests__/EmbargoEndedBanner.test.tsx lib/embargoDisplay.ts lib/__tests__/embargoDisplay.test.ts
git commit -m "feat: the ended banner and the history say what members can do"
```

---

### Task 12: Validation

**Files:** none changed unless a check fails.

Gatekeeper, in its worktree:

- [ ] **Step 1: Unit tests**

Run: `python -m pytest`
Expected: PASS, 0 failures.

- [ ] **Step 2: Integration tests, full cycle**

Run: `make ENV_FILE_PATH=integration-test.env integration-test-full`
Then confirm it really ran: the output must show the pytest summary for `tests/integration/` with `0 failed`, `test_dataset_members_access.py` among the files collected, and before it the API answered:

Run, while the stack is up: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9094/api/v1/health-check/`
Expected: `200`. (`integration-test-full` swallows failures and its readiness wait uses `timeout`, absent on macOS: read the summary, do not trust the exit code. A container that never becomes healthy is a migration failing at startup; read `docker logs datamap_gatekeeper_test_integration` before blaming a test.)

- [ ] **Step 3: Lint and format**

Run: `ruff check && ruff check --fix && ruff format`
Expected: `All checks passed!`; `ruff format` reports files left unchanged or reformatted, and `ruff check` passes again after it.

- [ ] **Step 4: Commit any formatting changes**

```bash
git add -u
git commit -m "style: ruff format"
```
(Skip if `git status` shows nothing.)

Webapp, in its worktree:

- [ ] **Step 5: Whole test suite**

Run: `npm run test >/dev/null 2>&1; echo "exit=$?"`
Expected: `exit=0`. Then `npm run test 2>&1 | grep -E "^(Tests|Test Suites):"` for the counts: `0 failed` on both lines.

- [ ] **Step 6: Type-check**

Run: `npx tsc --noEmit -p tsconfig.json; echo "exit=$?"`
Expected: `exit=0`. If the base branch already reports type errors, run the same command in a worktree of the base branch and compare the two lists: this plan adds none.

- [ ] **Step 7: Production build**

Run: `npm run build; echo "exit=$?"`
Expected: `exit=0`; the route list includes `/api/datasets/[datasetId]/members-access`.

- [ ] **Step 8: Lint**

Run: `npx next lint; echo "exit=$?"`
Expected: `exit=0` with no errors in the files this plan touched (pre-existing warnings elsewhere are acceptable; do not fix unrelated files).

- [ ] **Step 9: Manual walk, both together**

With the gatekeeper integration stack up from this plan's branch and the webapp's `.env.local` pointing `DATAMAP_BASE_URL` at it (`npm run dev`), as the dataset's owner and as a second account that is a member of the same workspace with an editing role:

1. Create a dataset open to the workspace. As the member: Edit, New version and Upload are offered and work.
2. As the owner, Share → the last row reads `N people · can read and edit` → Change → Read only → Save. The row reads `… · can read · editing limited to the people above`; the dialog stayed open.
3. As the member, reload: the dataset reads and downloads; Edit, New version, Upload, Settings and Share are gone.
4. As the owner, Settings: the Access block shows the same row; History lists "made the dataset read only for members of the workspace".
5. Set an embargo from Settings: the dialog's line reads `When the embargo ends, members of <T> can read but not edit.`. The member gets the embargo's answers (404 in hidden mode). Share reads `No access during the embargo · afterwards: read only`.
6. End the embargo early: the owner's banner has `Members of <T> can read this dataset; editing stays with the people you shared it with.`; the member reads again and still cannot edit.
7. With `EMAIL_ENABLED=false`, the next dispatch (`POST /api/v1/internal/notifications/dispatch` with the Archivist's credentials) records the *Embargo ended* messages: `GET /api/v1/admin/emails/?template=embargo_ended` and the owner's `body_text` contains the same sentence.

Record anything that differs from the contracts in the PR description; change the contracts first if the difference is to stay.

- [ ] **Step 10: Commit any fixes**

```bash
git status --short
git add -A && git commit -m "fix: issues found in the members' access verification"
```

(In each repo; skip the commit where `git status --short` is empty.)

---

## Self-review against the spec

| Decision | Task |
|---|---|
| Per-dataset, owner-only setting; default read and edit (today's behaviour) | 1 (column default), 2 (`MANAGE_MEMBERS_ACCESS`, owner only) |
| Read only: no write, upload, new version or other write action for members; delete only with the owner (and a DELETE role in the default mode only) | 1 (`_permits`), 5 (update, version, TUS, delete end to end) |
| Reads never affected; role still governs reading and downloading | 1, 5 (read and download as a read-only member) |
| Inert during an embargo; decides what members get back when it ends | 1 (embargo branch returns first), 5 (`TestWithAnEmbargo`) |
| `datasets.members_can_edit` NOT NULL default true; migration `a7b8c9d0e1f2` after `f6a7b8c9d0e1` | 1 |
| `access_flags` follow (`can_edit`, `can_share`, `can_delete` false for a read-only member) | 1, 5 |
| Search unchanged | Global Constraints; no task touches `app/repository/dataset.py` |
| `members_can_edit` on every dataset object, list items and minimal included | 3, 5 |
| `ShareState.tenancy.members_can_edit`, still `null` during an embargo | 3, 5 |
| `PUT /datasets/{id}/members-access` → 200 `access` + `members_can_edit`; 404/403 as everywhere | 2, 5 |
| `members_access_changed` through `DatasetAccessAudit`, old/new values; listed by `GET /access-events` | 2, 5, 11 (wording) |
| Reminder and ended emails, owner and collaborator variants, one sentence each | 4 |
| Share dialog row: text, `Change` for the owner, the embargo wording | 7, 8 |
| Settings → Access row | 9 |
| Set-embargo dialog and creation line with `Change` | 10 |
| Ended banner sentence | 11 |
| History wording | 11 |
| `canEditDataset` unchanged (reads `access.can_edit`) | no task changes `lib/users.ts` |
| `BFFAPI.setMembersAccess`, BFF route, server call in `lib/share.ts`, telemetry `members_access_changed` | 6 |

Decisions this plan had to make, beyond the maintainer's:

- **The members row moves to the end of *Who has access*** (Task 8). The design (§1c) draws it first; the read-only copy says "editing limited to the people above", which is only true below the people. If the row must stay first, the copy changes instead (for example "… to the people listed here") and the move is dropped.
- **During an embargo the share dialog and Settings show the row**, reading `No access during the embargo · afterwards: …`, although `ShareState.tenancy` is `null`; the value comes from the dataset payload. The read-only variant of that line, `afterwards: read only`, and of the embargo-fields line, `can read but not edit`, are this plan's wording; the maintainer gave only the read-and-edit forms.
- **The collaborator variants of the emails** name the owner: "the people {owner} shared it with keep their access" and "editing stays with {owner} and the people they shared it with". The reminder's sentences open with "When the embargo ends,".
- **A no-op change records nothing**, as plan 02's mode switch does.
- **The body is a strict boolean** (`StrictBool`): `"false"` or `0` answer 422 rather than being coerced.
- **After a save the page's props are refetched** (`router.replace(router.asPath)`) instead of reloading the page, so the share dialog stays open.
- **At creation and in *Put under embargo*, the members' setting is sent before the embargo**, so a failure in between never leaves an embargo whose aftermath contradicts the author's choice.
- **`InvitationPreview.dataset_id`** (contracts, §Sharing) is not built here: it belongs to plan 03 Task 12's preview and plan 05's invitation page, and the contracts were amended with it in the same commit as this plan.
