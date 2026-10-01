# Dataset Embargo: Cross-Service Contracts

Spec: `docs/rfcs/003-dataset-embargo.md`. This file fixes the interfaces the gatekeeper, the webapp (BFF and pages) and the Archivist share, so each plan can be implemented in parallel against it. When a plan and this file disagree, this file wins; change it first, then the plans.

## Plans

| # | Plan | Repo | Depends on |
|---|---|---|---|
| 01 | `2026-09-30-embargo-01-gatekeeper-email.md` | gatekeeper | — |
| 02 | `2026-09-30-embargo-02-gatekeeper-embargo-access.md` | gatekeeper | — |
| 03 | `2026-09-30-embargo-03-gatekeeper-sharing-review.md` | gatekeeper | 01, 02 |
| 04 | `2026-09-30-embargo-04-archivist-dispatch.md` | archivist | this file (route only) |
| 05 | `2026-09-30-embargo-05-webapp.md` | datamap-webapp | this file; merges after 02 and 03 |

01, 02 and 04 start together. 05 starts together too, against this file, with the gatekeeper mocked in its tests. 03 starts when 01 and 02 are merged into the feature branch.

Migrations form one chain and merge in this order, never re-pointed: 01 `d4e5f6a7b8c9` (revises the current head `c3h4i5j6k7l8`) → 02 `e5f6a7b8c9d0` → 03 `f6a7b8c9d0e1`. Plans 01, 02 and 03 merge into the gatekeeper in that order.

Deploy order: gatekeeper (01+02+03) → archivist (04) → webapp (05) → nginx change for `/doi/` (last task of 05, file in the gatekeeper repo). `EMAIL_ENABLED` is switched on only after all of it is verified in production.

## Conventions

- Gatekeeper routes are mounted under `/api/v1`. Paths below omit that prefix.
- **User routes** carry `X-Api-Key`, `X-Api-Secret`, `X-User-Id`, `X-Datamap-Tenancies` and use `Depends(authenticate), Depends(authorize)`.
- `X-Datamap-Tenancies` may be missing or empty on any user route: that means the caller's own tenancies, possibly none (`_determine_tenancies` falls back to `user.tenancies`). The webapp omits it for an account with no tenancy. Such a caller reaches, through a permission, every dataset route: fetch, version, search (`shared=true` and default), download and writes.
- **Client-only routes** carry `X-Api-Key`, `X-Api-Secret` (and `X-User-Id` where noted) and use `Depends(authenticate)` only. No Casbin.
- Timestamps are ISO 8601 with timezone (`2026-12-29T23:59:59+00:00`). UUIDs are strings.
- Errors keep the existing handlers: `BadRequestException(errors=[ErrorDetails(code=...)])` → `400 {"details": "Invalid client input", "errors": [{"code": ..., "field": null}]}`; `NotFoundException` → `404 {"detail": ...}`; `ConflictException` → `409`.
- A caller who may not see a dataset gets **404** on every dataset route, reads and writes alike.

## Shared enums and constants

```python
# app/model/embargo.py (gatekeeper)
class PermissionLevel(str, enum.Enum):
    READ = "read"
    WRITE = "write"

class AccessLevel(str, enum.Enum):     # what the caller holds on a dataset
    OWNER = "owner"
    WRITE = "write"
    READ = "read"
    TENANCY = "tenancy"                 # access through tenancy membership only

MAX_EMBARGO_PERIOD = timedelta(days=90)
REMINDER_OFFSETS_DAYS = (15, 10, 5, 1)
REDACTED = "[redacted]"
```

```ts
// datamap-webapp types/GatekeeperAPI.ts
export type PermissionLevel = "read" | "write";
export type AccessLevel = "owner" | "write" | "read" | "tenancy";
```

## Dataset payload additions

Every dataset object returned by `GET /datasets/{id}`, `GET /datasets/` (items, **including `minimal=true` items**, which the webapp's list badge reads), `GET /datasets/{id}/versions/{v}` gains two fields:

```json
"embargo": {
  "until": "2026-12-29T23:59:59+00:00",
  "active": true,
  "metadata_visible": false,
  "note": "Under review at JGR Atmospheres"
},
"access": {
  "level": "owner",
  "can_edit": true,
  "can_share": true,
  "can_manage_embargo": true,
  "can_extend_embargo": true,
  "can_delete": true
}
```

- `embargo` is `null` when `embargo_until` is null. `active` is `until > now()`.
- `access.level` is an `AccessLevel`. `can_edit` and `can_share`: owner or `write`, or tenancy member when no active embargo and the user's role allows writes (unchanged behaviour). `can_manage_embargo`: owner only. `can_delete` follows the access rule: the owner always; during an active embargo, nobody else; with no active embargo, a tenancy member whose role allows `DELETE`, as today (a permission never grants delete). `can_extend_embargo`: owner, or any permission holder when the owner's account is disabled; false when no active embargo.
- When the embargo is active and the caller's level is `tenancy` (open mode), every version's file list is returned empty and the version gains `"files_withheld": true` with `"files_summary": {"count": N, "total_size_bytes": B}`. Otherwise `files_withheld` is `false` and `files_summary` is still present.

`GET /datasets/` accepts `shared=true`: only datasets the caller holds a permission on, in any tenancy. Items have the same shape.

## Embargo (plan 02)

All user routes. All answer 404 to callers who may not see the dataset.

| Verb | Path | Body | Who | Success | Error codes (400) |
|---|---|---|---|---|---|
| PUT | `/datasets/{id}/embargo` | `{"until": ts, "metadata_visible": bool, "note": str\|null}` | owner | `200` embargo object | `embargo_too_long`, `embargo_until_in_past`, `embargo_dataset_published`, `embargo_already_active`, `embargo_manual_doi` |
| POST | `/datasets/{id}/embargo/extend` | `{"until": ts}` | owner; permission holder if owner disabled | `200` embargo object | `embargo_too_long`, `embargo_not_active`, `embargo_until_not_later` |
| POST | `/datasets/{id}/embargo/end` | — | owner | `200` embargo object (`active: false`) | `embargo_not_active` |
| PUT | `/datasets/{id}/embargo/mode` | `{"metadata_visible": bool}` | owner | `200` embargo object | `embargo_not_active` |

A caller who can see the dataset but lacks the role for the action gets `403 {"detail": "forbidden"}` — they already know it exists.

Client-only, no user:

| Verb | Path | Success |
|---|---|---|
| GET | `/datasets/{id}/embargo-status` | `200 {"embargoed": bool, "until": ts\|null}` — unknown id answers `{"embargoed": false, "until": null}` |

Snapshot-writing paths: DOI to `findable` under embargo answers `400 embargo_active`.

Manual DOI (`POST /datasets/{id}/versions/{v}/doi` with `mode: MANUAL`) gains an optional body field `"end_embargo": bool` (default false):

- dataset under embargo, `end_embargo` false or absent → `400 embargo_manual_doi_ends_embargo`;
- dataset under embargo, `end_embargo: true`, caller not owner → `403`;
- dataset under embargo, `end_embargo: true`, owner → DOI created, then embargo ended (`embargo_until` set to now, `ended_early` with note `"manual DOI"`), then snapshot published; the *Embargo ended* emails come from plan 03's next dispatch pass;
- no embargo → unchanged.

`PUT /datasets/{id}/embargo` answers `400 embargo_manual_doi` when any version has a DOI in manual mode, checked independently of `embargo_dataset_published`.

`access` gains no field for this; the webapp knows a DOI is manual from the existing DOI payload.

## Sharing (plan 03)

User routes.

| Verb | Path | Body | Success |
|---|---|---|---|
| GET | `/datasets/{id}/share/candidates?q=` | — | `200 [{"id","name","email"}]` (q ≥ 2 chars, ≤ 10 results, same tenancy, already-authorised excluded) |
| GET | `/datasets/{id}/share` | — | `200 ShareState` |
| POST | `/datasets/{id}/share` | `{"user_id"?: uuid, "email"?: str, "orcid"?: str, "level": "read"\|"write"}` exactly one target | `201 GrantResult` |
| PUT | `/datasets/{id}/share/permissions/{user_id}` | `{"level"}` | `200 Permission` |
| DELETE | `/datasets/{id}/share/permissions/{user_id}` | — | `204` |
| DELETE | `/datasets/{id}/share/invitations/{invitation_id}` | — | `204` |
| POST | `/datasets/{id}/share/invitations/{invitation_id}/link` | — | `200 {"link": url}` (old token invalidated) |

Error codes (400): `share_target_required`, `share_target_ambiguous`, `invalid_email`, `invalid_orcid`, `already_has_access`, `cannot_share_with_owner`, `invalid_level`, `unknown_user` (a `user_id` that names no enabled account).

```json
// ShareState
{
  "owner": {"id": "…", "name": "…", "email": "…"},
  "permissions": [{"user": {"id","name","email"}, "level": "read", "granted_at": ts, "granted_by": "…"}],
  "invitations": [{"id": "…", "email": "…"|null, "orcid": "…"|null, "level": "read",
                   "created_at": ts, "accepted_at": ts|null,
                   "accepted_by": {"id","name","email"}|null, "revoked_at": ts|null}],
  "review_links": [ReviewLink]
}
// GrantResult
{"kind": "permission", "permission": Permission}
{"kind": "invitation", "invitation": Invitation, "link": "https://datamap.pcs.usp.br/invitations/<token>"}
```

Client-only, with `X-User-Id`:

| Verb | Path | Body | Success | Errors |
|---|---|---|---|---|
| POST | `/invitations/accept` | `{"token": str}` | `200 {"dataset_id", "level"}` | `404` unknown or revoked; `409 {"detail": "invitation_already_accepted"}` |
| POST | `/users/{user_id}/invitations/claim` | — | `200 {"accepted": [{"dataset_id","level"}]}` | — |

The webapp calls `claim` right after sign-in (NextAuth `jwt` callback, `trigger == "signIn"`), and `accept` from the invitation page. Granting a permission or accepting an invitation adds the Casbin grouping `g, <user_id>, datasets_shared` when the user lacks it.

Links are built by the gatekeeper from `PUBLIC_BASE_URL`:

- invitation: `{PUBLIC_BASE_URL}/invitations/{token}`
- reviewer: `{PUBLIC_BASE_URL}/review/{token}`

Tokens: `secrets.token_urlsafe(32)`; stored as `sha256(token).hexdigest()`.

## Reviewer links (plan 03)

User routes:

| Verb | Path | Body | Success | Errors |
|---|---|---|---|---|
| POST | `/datasets/{id}/review-links` | `{"label": str}` (1–256 chars) | `201 ReviewLink + "link": url` | `400 embargo_not_active` |
| DELETE | `/datasets/{id}/review-links/{link_id}` | — | `204` | — |

```json
// ReviewLink
{"id": "…", "label": "JGR Atmospheres, round 1", "created_at": ts, "revoked_at": ts|null,
 "views": {"count": 12, "first_at": ts|null, "last_at": ts|null}}
```

Client-only, no user:

| Verb | Path | Success | Errors |
|---|---|---|---|
| GET | `/review/{token}` | `200 ReviewPage` | `404` unknown or revoked |

```json
// ReviewPage, embargo active
{"state": "active", "embargo_until": ts,
 "dataset": {"name": "…", "data": { …redacted… },
             "versions": [{"name": "1", "created_at": ts,
                           "files_summary": {"count": 42, "total_size_bytes": 1234}}]}}
// ReviewPage, embargo over
{"state": "ended", "dataset_id": "…", "published": true}
```

`published` is `visibility == PUBLIC`. The webapp redirects to `/datasets/{dataset_id}` when `published`, else shows "the embargo has ended and the dataset has not been published yet".

Redaction (gatekeeper, one function `redact_metadata(data: dict) -> dict`): keys in the allowlist pass through unchanged; any other key has every string inside it (recursively, through lists and dicts) replaced by `"[redacted]"`, keeping list lengths and dict keys. Allowlist:

```python
SAFE_METADATA_KEYS = frozenset({
    "description", "tags", "level", "realm", "source", "license", "category",
    "database", "start_date", "end_date", "creation_date", "location",
    "data_type", "grid_type", "variables", "resolution", "source_instrument",
    "additional_information", "is_enabled",
})
```

`owner`, `authors`, `contacts`, `colaborators`, `institution`, `project`, `reference`, `references`, `citation`, and any key not listed, are redacted.

## Notifications (plans 01, 03, 04)

Client-only (Archivist credentials):

| Verb | Path | Success |
|---|---|---|
| POST | `/internal/notifications/dispatch` | `200 {"queued": int, "sent": int, "failed": int, "skipped": int, "retried": int}` |

Admin user routes (`authorize`; the `admin` role's `/*` policy covers them):

| Verb | Path | Success |
|---|---|---|
| GET | `/admin/emails?recipient=&related_id=&template=&status=&page=&page_size=` | `200 {"items": [EmailSummary], "total_count", "page", "page_size"}` |
| GET | `/admin/emails/{id}` | `200 EmailDetail` (message + `events[]`) |
| POST | `/admin/emails/test` | `202 {"id"}` — body `{"recipient": str}`; a test message through the normal queue, to check SMTP in production |

Plan 01 details the other plans rely on:

- `email_messages` also has `secret_fields jsonb` (fields masked once sent) and `claimed_at timestamptz` (when the row entered `sending`, to find rows a crash left there).
- `template_version` is the `BUILD_COMMIT` config field (default `"unknown"`), passed as a Docker build arg by the Makefile.
- The email logo is served by the webapp at `{PUBLIC_BASE_URL}/images/email/datamap-logo.png` (file `public/images/email/datamap-logo.png`, plan 05).
- Gatekeeper code runs on Python 3.10 in production (`python:3.10.14-alpine`): no syntax newer than 3.10.

Templates (names are the `template` column and metric label): `invitation`, `access_granted`, `embargo_reminder`, `embargo_ended`.

Gatekeeper email API used by plan 03 (plan 01 builds it):

```python
# app/service/email.py
class EmailService:
    def enqueue(self, *, template: str, recipient: str, context: dict,
                secret_fields: frozenset[str] = frozenset(),
                related_type: str | None = None, related_id: UUID | None = None,
                triggered_by: UUID | None = None, dedup_key: str | None = None) -> UUID | None:
        """Render and store one message. Returns its id, or None when dedup_key already exists."""

    def dispatch_due(self, limit: int = 50) -> DispatchResult: ...
```

```python
# app/service/notification.py (plan 03), called by the dispatch route before dispatch_due
class EmbargoNotificationService:
    def queue_due(self, now: datetime) -> int: ...
```

The dispatch route calls `embargo_notifications.queue_due(now)` then `email_service.dispatch_due()`. Plan 01 ships the route calling only `dispatch_due`; plan 03 adds the `queue_due` call.

## Gatekeeper internal interfaces (plans 01–03)

Plan 03 builds on these exactly; the provider names are the `app/container.py` attributes.

```python
# plan 02 — app/model/embargo.py
class DatasetAction(enum.Enum):
    READ_METADATA, READ_FILES, WRITE, DELETE, EXTEND_EMBARGO, MANAGE_EMBARGO
class EmbargoEventType(str, enum.Enum):
    CREATED, EXTENDED, ENDED_EARLY, EXPIRED, METADATA_MODE_CHANGED, PERMISSION_GRANTED,
    PERMISSION_REVOKED, INVITATION_CREATED, INVITATION_REVOKED, REVIEW_LINK_CREATED, REVIEW_LINK_REVOKED
@dataclass class Embargo: until, active, metadata_visible, note=None
@dataclass class DatasetAccess: level, can_edit, can_share, can_manage_embargo, can_extend_embargo, can_delete
@dataclass class DatasetPermission: dataset_id, user_id, level: PermissionLevel, granted_by=None, created_at=None
SHARED_ROLE = "datasets_shared"
def utcnow() -> datetime
def embargo_active(until: datetime | None, now: datetime) -> bool

# plan 02 — app/exception/forbidden.py: ForbiddenException -> 403 {"detail": "forbidden"}

# plan 02 — app/repository/permission.py                      provider: permission_repository
class PermissionRepository:
    def fetch(self, dataset_id, user_id) -> DatasetPermissionDBModel | None
    def upsert(self, dataset_id, user_id, level: str, granted_by) -> DatasetPermissionDBModel
    def delete(self, dataset_id, user_id) -> bool
    def list_for_dataset(self, dataset_id) -> list[DatasetPermissionDBModel]

# plan 02 — app/repository/embargo_event.py                   provider: embargo_event_repository
class EmbargoEventRepository:
    def append(self, dataset_id, event_type: str, changed_by, old_value, new_value, note) -> None
    def list_for_dataset(self, dataset_id) -> list[DatasetEmbargoEvent]

# plan 02 — app/service/embargo_audit.py                      provider: embargo_audit
class EmbargoAudit:   # the only writer of dataset_embargo_events outside tests; also counts datamap_embargo_events_total
    def record(self, dataset_id, event_type: EmbargoEventType, changed_by: UUID | None,
               old_value: dict | None = None, new_value: dict | None = None, note: str | None = None) -> None

# plan 02 — app/service/dataset_access.py                     provider: dataset_access_service
class DatasetAccessService:
    def embargo_active(self, dataset, now=None) -> bool
    def embargo_of(self, dataset, now=None) -> Embargo | None
    def level_of(self, user_id, dataset, tenancies: list[str], now=None) -> AccessLevel | None
    def permits(self, user_id, dataset, tenancies, action: DatasetAction, now=None) -> bool
    def require(self, user_id, dataset, tenancies, action: DatasetAction, now=None) -> AccessLevel
        # NotFoundException when invisible, ForbiddenException when visible but not allowed
    def access_flags(self, user_id, dataset, tenancies, level: AccessLevel, now=None) -> DatasetAccess
    def owner_disabled(self, dataset) -> bool

# plan 02 — app/service/dataset.py                            provider: dataset_service
DatasetService.fetch_authorized(dataset_id, user_id, tenancies: list[str] | None, action: DatasetAction,
    is_enabled=True, latest_version=False, version_design_state=None, version_is_enabled=True)
    -> tuple[DatasetDBModel, list[str], AccessLevel]      # the entry point for any per-dataset service

# plan 02 — app/service/embargo_termination.py                provider: embargo_termination
EmbargoTermination.end(dataset, ended_by: UUID | None, now: datetime, note: str | None = None) -> None
    # sets embargo_until = now, upserts, records ended_early; notifies nobody

# plan 02 — app/service/permission.py                         provider: permission_service
class PermissionService:
    def grant(self, dataset_id, user_id, level: PermissionLevel, granted_by: UUID | None) -> DatasetPermission
        # NotFoundException for a missing or disabled user; upserts; adds datasets_shared when missing; records permission_granted
    def revoke(self, dataset_id, user_id, revoked_by: UUID | None) -> bool   # records permission_revoked; keeps the role
    def list_for_dataset(self, dataset_id) -> list[DatasetPermission]

# plan 02 — app/service/embargo.py                            provider: embargo_service
EmbargoService.set_embargo / extend / end / set_mode / status

# plan 01 — app/service/email.py                              providers: email_service, email_renderer
EmailService.enqueue(...) / dispatch_due(limit=50) -> DispatchResult(queued, sent, failed, skipped, retried)

# plan 03                                                       providers: dataset_invitation_repository,
#   dataset_review_link_repository, share_service, review_link_service,
#   embargo_notification_repository, embargo_notification_service
```

**One mechanism announces the end of an embargo.** Nothing is sent when an embargo ends: the owner's early end and the manual DOI both set `embargo_until` to now through `EmbargoTermination.end`, and a natural expiry needs no write at all. Plan 03's dispatch pass (`EmbargoNotificationService.queue_due`) finds every enabled dataset whose `embargo_until` has passed with no `expired` event since, records `expired` through `EmbargoAudit` (`changed_by` null) and queues the *Embargo ended* messages, reading the latest `ended_early` event to say whether and why it ended early.

## Metrics (RFC 005 names)

| Metric | Type | Labels | Plan |
|---|---|---|---|
| `datamap_emails_total` | counter | `template`, `outcome` (`sent`, `retried`, `failed`, `skipped`) | 01 |
| `datamap_email_pending` | gauge | — | 01 |
| `datamap_review_link_views_total` | counter | `tenancy`, `outcome` (`shown`, `redirected`, `not_found`) | 03 |
| `datamap_review_links_created_total` | counter | `tenancy` | 03 |
| `datamap_embargo_events_total` | counter | `event` (the `dataset_embargo_events.event_type` values) | 02 |

Webapp telemetry: add pages `/review/[token]`, `/doi/datasets/[datasetId]/versions/[versionName]`, `/invitations/[token]`, `/app/datasets/shared` to `PAGES`; add UI events `embargo_set`, `embargo_extended`, `dataset_shared`, `review_link_created` to `UI_EVENTS`.

## Casbin seed additions (plan 02)

Added to `app/resources/casbin_seed_policies.sql`, `app/resources/rbac_data.sql` and `tests/integration/fixtures/seed_clients.sql`:

```sql
('p', 'datasets_shared', '/api/v1/datasets/?$', 'GET', 'allow', NULL, NULL),
('p', 'datasets_shared', '/api/v1/datasets/[0-9a-f-]{36}(/.*)?$', '(GET|POST|PUT|DELETE)', 'allow', NULL, NULL),
('p', 'datasets_shared', '/api/v1/tus', 'POST', 'allow', NULL, NULL)
```

Production: the same three rows are inserted by hand, as the README describes for seed policies, before the gatekeeper with plan 02 is deployed.

## Webapp routes (plan 05)

| Page | Auth | Calls |
|---|---|---|
| `/app/datasets/shared` | logged in, tenancy not required | `GET /api/datasets?shared=true` |
| `/app/datasets/[datasetId]` (existing) | logged in, tenancy not required | adds embargo section, share dialog, badges from `embargo`/`access` |
| `/app/datasets/new` (existing) | logged in | embargo choice in the form; sent with `PUT /datasets/{id}/embargo` after the dataset update |
| DOI form (existing, `DatasetCitation.tsx`) | logged in | manual mode on an embargoed dataset → confirmation dialog, then `end_embargo: true`; manual mode on a dataset without embargo → notice that it can no longer be embargoed, confirmed before sending |
| `/review/[token]` | public | `GET /review/{token}` server-side |
| `/doi/datasets/[datasetId]/versions/[versionName]` | public | `GET /datasets/{id}/embargo-status` server-side; redirects to `/app/datasets/{id}/versions/{v}` when not embargoed |
| `/invitations/[token]` | logged in (redirect to login with callback) | `POST /invitations/accept`, then redirect to the dataset |

nginx (`infrastructure/nginx/datamap.conf` in the gatekeeper repo): the `location ~ ^/doi/datasets/...` block stops rewriting and proxies to the webapp, after the webapp page is deployed.
