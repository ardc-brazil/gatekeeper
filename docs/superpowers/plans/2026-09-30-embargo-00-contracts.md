# Dataset Embargo: Cross-Service Contracts

Spec: `docs/rfcs/003-dataset-embargo.md`. This file fixes the interfaces the gatekeeper, the webapp (BFF and pages) and the Archivist share, so each plan can be implemented in parallel against it. When a plan and this file disagree, this file wins; change it first, then the plans.

## Plans

| # | Plan | Repo | Depends on |
|---|---|---|---|
| 01 | `2026-09-30-embargo-01-gatekeeper-email.md` | gatekeeper | — |
| 02 | `2026-09-30-embargo-02-gatekeeper-embargo-access.md` | gatekeeper | — |
| 03 | `2026-09-30-embargo-03-gatekeeper-sharing-anonymous-links.md` | gatekeeper | 01, 02 |
| 04 | `2026-09-30-embargo-04-archivist-dispatch.md` | archivist | this file (route only) |
| 05 | `2026-09-30-embargo-05-webapp.md` | datamap-webapp | this file; merges after 02 and 03 |
| 06 | `2026-10-02-embargo-06-members-access.md` | gatekeeper, datamap-webapp | 02, 03, 05 |

01, 02 and 04 start together. 05 starts together too, against this file, with the gatekeeper mocked in its tests. 03 starts when 01 and 02 are merged into the feature branch. 06 starts when 03 is merged into the gatekeeper feature branch and 05 into the webapp's; its gatekeeper tasks merge before its webapp tasks.

Migrations form one chain and merge in this order, never re-pointed: 01 `d4e5f6a7b8c9` (revises the current head `c3h4i5j6k7l8`) → 02 `e5f6a7b8c9d0` → 03 `f6a7b8c9d0e1` → 06 `a7b8c9d0e1f2`. Plans 01, 02, 03 and 06 merge into the gatekeeper in that order.

Deploy order: gatekeeper (01+02+03, then 06) → archivist (04) → webapp (05, then 06) → nginx change for `/doi/` (last task of 05, file in the gatekeeper repo). `EMAIL_ENABLED` is switched on only after all of it is verified in production.

## Conventions

- Gatekeeper routes are mounted under `/api/v1`. Paths below omit that prefix.
- **User routes** carry `X-Api-Key`, `X-Api-Secret`, `X-User-Id`, `X-Datamap-Tenancies` and use `Depends(authenticate), Depends(authorize)`.
- `X-Datamap-Tenancies` may be missing or empty on any user route: that means the caller's own tenancies, possibly none (`_determine_tenancies` falls back to `user.tenancies`). The webapp omits it for an account with no tenancy. Such a caller reaches, through a permission, every dataset route: fetch, version, search (`shared=true` and default), download and writes.
- **Client-only routes** carry `X-Api-Key`, `X-Api-Secret` (and `X-User-Id` where noted) and use `Depends(authenticate)` only. No Casbin.
- Timestamps are ISO 8601 with timezone (`2026-12-29T23:59:59+00:00`). UUIDs are strings.
- Errors keep the existing handlers: `BadRequestException(errors=[ErrorDetails(code=...)])` → `400 {"details": "Invalid client input", "errors": [{"code": ..., "field": null}]}`; `NotFoundException` → `404 {"detail": ...}`; `ConflictException` → `409`.
- A caller who may not see a dataset gets **404** on every dataset route, reads and writes alike.

## Shared enums and constants

Sharing and access are a dataset feature of their own, used on any dataset, embargoed or not; the embargo is a layer on top. The gatekeeper model keeps them apart, and nothing in `dataset_access` depends on `embargo`.

```python
# app/model/dataset_access.py (gatekeeper)
class PermissionLevel(str, enum.Enum):
    READ = "read"
    WRITE = "write"

class AccessLevel(str, enum.Enum):     # what the caller holds on a dataset
    OWNER = "owner"
    WRITE = "write"
    READ = "read"
    TENANCY = "tenancy"                 # access through tenancy membership only

# app/model/embargo.py (gatekeeper)
MAX_EMBARGO_PERIOD = timedelta(days=90)
REMINDER_OFFSETS_DAYS = (15, 10, 5, 1)

# app/service/redaction.py (gatekeeper, anonymous links)
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

The default `GET /datasets/` (no `shared`) lists the datasets the caller owns or holds a permission on in any tenancy, not only in the selected one, plus those of the selected tenancies that the embargo leaves visible (plan 02 Task 8).

The detail payloads (`GET /datasets/{id}`, `GET /datasets/{id}/versions/{v}`; not list items) also carry the owner, whose name the dataset page shows to members and collaborators (design §1e) — plan 03, Task 13:

```json
"owner": {"id": "…", "name": "Luciana Rizzo"}
```

`owner` is `null` when the dataset has no owner or the owner's account cannot be read.

## Embargo (plan 02)

All user routes. All answer 404 to callers who may not see the dataset.

| Verb | Path | Body | Who | Success | Error codes (400) |
|---|---|---|---|---|---|
| PUT | `/datasets/{id}/embargo` | `{"until": ts, "metadata_visible": bool, "note": str\|null}` | owner | `200` embargo object | `embargo_too_long`, `embargo_until_in_past`, `embargo_dataset_published`, `embargo_already_active`, `embargo_manual_doi` |
| POST | `/datasets/{id}/embargo/extend` | `{"until": ts, "reason": str\|null}` (`reason` ≤ 500 chars, recorded as the event's note; plan 03 Task 13) | owner; permission holder if owner disabled | `200` embargo object | `embargo_too_long`, `embargo_not_active`, `embargo_until_not_later` |
| POST | `/datasets/{id}/embargo/end` | — | owner | `200` embargo object (`active: false`) | `embargo_not_active` |
| PUT | `/datasets/{id}/embargo/mode` | `{"metadata_visible": bool}` | owner | `200` embargo object | `embargo_not_active` |
| PUT | `/datasets/{id}/embargo/note` | `{"note": str\|null}` (≤ 2000 chars; plan 03 Task 13) | owner | `200` embargo object; records `note_changed` when it changes | `embargo_not_active` |
| GET | `/datasets/{id}/access-events` | — (plan 03 Task 13) | owner, `write` | `200 {"items": [AccessHistoryEntry]}`, newest first, at most 100 | — |

```json
// AccessHistoryEntry — the Settings tab's History (design §1g)
{"event_type": "extended", "occurred_at": ts,
 "actor": {"id": "…", "name": "Luciana Rizzo"}|null,      // null for the system ("expired")
 "subject": "Caio Maia"|"JGR Atmospheres, round 1"|"ORCID 0000-…"|null,  // whom or what the event was about
 "old_value": {…}|null, "new_value": {…}|null, "note": "Second review round requested"|null}
```

`event_type` is one of the `AccessEventType` values, now including `note_changed`. The webapp words each entry from these fields.

A caller who can see the dataset but lacks the role for the action gets `403 {"detail": "forbidden"}` — they already know it exists.

Client-only, no user:

| Verb | Path | Success |
|---|---|---|
| GET | `/datasets/{id}/embargo-status?version={name}` | `200 {"embargoed": bool, "until": ts\|null, "doi": str\|null}` — `doi` is that version's identifier, only while embargoed (plan 03 Task 13; the embargo page shows it, design §1i); unknown id answers `{"embargoed": false, "until": null, "doi": null}` |

Snapshot-writing paths: DOI to `findable` under embargo answers `400 embargo_active`.

Manual DOI (`POST /datasets/{id}/versions/{v}/doi` with `mode: MANUAL`) gains an optional body field `"end_embargo": bool` (default false):

- dataset under embargo, `end_embargo` false or absent → `400 embargo_manual_doi_ends_embargo`;
- dataset under embargo, `end_embargo: true`, caller not owner → `403`;
- dataset under embargo, `end_embargo: true`, owner → DOI created, then embargo ended (`embargo_until` set to now, `ended_early` with note `"manual DOI"`), then snapshot published; the *Embargo ended* emails come from plan 03's next dispatch pass;
- no embargo → unchanged.

`PUT /datasets/{id}/embargo` answers `400 embargo_manual_doi` when any version has a DOI in manual mode, checked independently of `embargo_dataset_published`.

`access` gains no field for this; the webapp knows a DOI is manual from the existing DOI payload.

## Sharing (plan 03)

Sharing works on **any dataset, embargoed or not** — for example, giving a dataset's contributors read/write access in the system while it is not embargoed. No sharing route checks the embargo, and none of the share UI is conditional on it. The embargo only removes the tenancy's default access and adds anonymous links.

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
  "permissions": [{"user": {"id","name","email"}, "level": "read", "granted_at": ts, "granted_by": "…",
                   "invited_as": "fernanda@inpe.br"|"ORCID 0000-…"|null}],   // the invitation it came from
  "invitations": [{"id": "…", "email": "…"|null, "orcid": "…"|null, "level": "read",
                   "created_at": ts, "accepted_at": ts|null,
                   "accepted_by": {"id","name","email"}|null, "revoked_at": ts|null}],
  "anonymous_links": [AnonymousLink],
  "tenancy": {"name": "Data Amazon", "path": "datamap/production/data-amazon", "members": 14}|null
}
// tenancy: the "Members of Data Amazon · 14 people · workspace default" row of the share
// dialog (design §1c); null while an embargo is active, when the tenancy has no default access.
// invited_as, tenancy: plan 03 Task 12.
// GrantResult
{"kind": "permission", "permission": Permission}
{"kind": "invitation", "invitation": Invitation, "link": "https://datamap.pcs.usp.br/invitations/<token>"}
```

Client-only, with `X-User-Id`:

| Verb | Path | Body | Success | Errors |
|---|---|---|---|---|
| GET | `/invitations/{token}` | — (no `X-User-Id` needed; plan 03 Task 12) | `200 InvitationPreview` | `404` unknown or revoked |
| POST | `/invitations/accept` | `{"token": str}` | `200 {"dataset_id", "level"}` | `404` unknown or revoked; `409 {"detail": "invitation_already_accepted"}` |
| POST | `/users/{user_id}/invitations/claim` | — | `200 {"accepted": [{"dataset_id","level"}]}` | — |

```json
// InvitationPreview — the invitation page before and after it is used (design §1i)
{"state": "pending"|"accepted", "dataset_name": "…", "inviter_name": "Luciana Rizzo",
 "owner_name": "Luciana Rizzo", "level": "read", "invited_as": "fernanda@inpe.br"|"ORCID 0000-…",
 "embargo_until": ts|null, "accepted_at": ts|null,
 "dataset_id": "…"|null}
// dataset_id: present when state is "accepted", so the used-invitation page can link to the
// dataset; null while pending. Asked for by the plan 05 review; plan 03 Task 12 builds the
// preview, and this file wins over that task's code, which predates the field.
```

The webapp calls `claim` right after sign-in (NextAuth `jwt` callback, `trigger == "signIn"`), and `accept` from the invitation page. Granting a permission or accepting an invitation adds the Casbin grouping `g, <user_id>, datasets_shared` when the user lacks it.

Links are built by the gatekeeper from `PUBLIC_BASE_URL`:

- invitation: `{PUBLIC_BASE_URL}/invitations/{token}`
- anonymous: `{PUBLIC_BASE_URL}/anonymous/{token}`

Tokens: `secrets.token_urlsafe(32)`; stored as `sha256(token).hexdigest()`.

## Anonymous links (plan 03)

User routes:

| Verb | Path | Body | Success | Errors |
|---|---|---|---|---|
| POST | `/datasets/{id}/anonymous-links` | `{"label": str}` (1–256 chars) | `201 AnonymousLink + "link": url` | `400 embargo_not_active` |
| DELETE | `/datasets/{id}/anonymous-links/{link_id}` | — | `204` | — |

```json
// AnonymousLink
{"id": "…", "label": "JGR Atmospheres, round 1", "token_hint": "9f2c…a71e"|null,
 "created_at": ts, "revoked_at": ts|null,
 "views": {"count": 12, "first_at": ts|null, "last_at": ts|null}}
// token_hint: the first and last four characters of the token, kept at creation so the
// share dialog can tell links apart (design §1c); plan 03 Task 11.
```

Client-only, no user:

| Verb | Path | Success | Errors |
|---|---|---|---|
| GET | `/anonymous/{token}` | `200 AnonymousPage` | `404` unknown or revoked |

```json
// AnonymousPage, embargo active
{"state": "active", "embargo_until": ts,
 "dataset": {"name": "…", "data": { …redacted… },
             "versions": [{"name": "1", "created_at": ts,
                           "files_summary": {"count": 42, "total_size_bytes": 1234,
                                             "extensions": [{"extension": ".nc"|null, "count": 9,
                                                             "total_size_bytes": 1000}]}}]}}
// extensions: largest first; never file names (design §1i "Anonymous view"); plan 03 Task 11.
// AnonymousPage, embargo over, dataset not published yet
{"state": "ended", "embargo_ended_at": ts,
 "dataset": {"name": "…", "data": { …redacted… }, "versions": [ …as above… ]}}
// AnonymousPage, dataset published
{"state": "published", "dataset_id": "…"}
```

Published means `visibility == PUBLIC`. Until then the link keeps serving the same redacted page, with a notice that the embargo has ended (`embargo_ended_at` is the dataset's `embargo_until`). Once published, the webapp redirects to `/datasets/{dataset_id}`; the anonymity ends there, since the public page shows the authors. The link never dead-ends.

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
- Every message is rendered by the existing `EmailTemplateRenderer` (`app/service/email_template.py`, #121) from `app/resources/email_templates/`, with `site_url = PUBLIC_BASE_URL`. Its images load from `{PUBLIC_BASE_URL}/img/email/` (`datamap-tile-36.png`, `datamap-tile-22.png`), which the webapp already serves from `public/img/email/`; no other logo is needed. Plan 01 adds the plain-text part (`RenderedEmail.text`, `<name>.txt` siblings, `base.txt`) and builds on the `fix/email-footer-links` PR, after which the renderer no longer supplies `preferences_url` or `unsubscribe_url`. No template mentions preferences, unsubscribing, snoozing or any feature DataMap does not have.
- Gatekeeper code runs on Python 3.10 in production (`python:3.10.14-alpine`): no syntax newer than 3.10.

Templates (names are `EmailTemplate` values, stored in the `template` column and used as the metric label). The new ones reproduce the Claude Design emails vendored in `docs/design/rfc-003-embargo/emails/`; the owner and collaborator variants of each design are branches of one template, so the label keeps these values:

| Message | `EmailTemplate` | Plan |
|---|---|---|
| Admin test message | `notification` (existing) | 01 |
| Access granted | `notification` (existing) | 03 |
| Invitation | `dataset_invitation` (new; design `embargo-invitation.html`) | 03 |
| Embargo ending in 15/10/5/1 days | `embargo_reminder` (new; designs `embargo-reminder-owner.html`, `embargo-reminder-collaborator.html`) | 03 |
| Embargo ended | `embargo_ended` (new; designs `embargo-ended-owner.html`, `embargo-ended-collaborator.html`) | 03 |

The three new templates use a transactional footer (`_transactional.html`: no About/Support/Data Policy/Datasets row, a sentence saying the message goes to everyone the dataset depends on), as the designs do.

The existing `invitation` (a workspace invitation with a role and an expiry) is not used.

Gatekeeper email API used by plan 03 (plan 01 builds it):

```python
# app/service/email.py
class EmailService:
    def enqueue(self, *, template: str, recipient: str, context: dict,   # template: an EmailTemplate value
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
# plan 02 — app/model/dataset_access.py (sharing and access; no embargo import)
class PermissionLevel(str, enum.Enum): READ, WRITE
class AccessLevel(str, enum.Enum): OWNER, WRITE, READ, TENANCY
class DatasetAction(enum.Enum):
    READ_METADATA, READ_FILES, WRITE, DELETE, EXTEND_EMBARGO, MANAGE_EMBARGO
class AccessEventType(str, enum.Enum):
    CREATED, EXTENDED, ENDED_EARLY, EXPIRED, METADATA_MODE_CHANGED, PERMISSION_GRANTED,
    PERMISSION_REVOKED, INVITATION_CREATED, INVITATION_REVOKED, ANONYMOUS_LINK_CREATED, ANONYMOUS_LINK_REVOKED
@dataclass class DatasetAccess: level, can_edit, can_share, can_manage_embargo, can_extend_embargo, can_delete
@dataclass class DatasetPermission: dataset_id, user_id, level: PermissionLevel, granted_by=None, created_at=None
SHARED_ROLE = "datasets_shared"
def utcnow() -> datetime

# plan 02 — app/model/embargo.py (embargo only)
MAX_EMBARGO_PERIOD, REMINDER_OFFSETS_DAYS
@dataclass class Embargo: until, active, metadata_visible, note=None
def embargo_active(until: datetime | None, now: datetime) -> bool

# plan 02 — app/exception/forbidden.py: ForbiddenException -> 403 {"detail": "forbidden"}

# plan 02 — app/repository/permission.py                      provider: permission_repository
class PermissionRepository:
    def fetch(self, dataset_id, user_id) -> DatasetPermissionDBModel | None
    def upsert(self, dataset_id, user_id, level: str, granted_by) -> DatasetPermissionDBModel
    def delete(self, dataset_id, user_id) -> bool
    def list_for_dataset(self, dataset_id) -> list[DatasetPermissionDBModel]

# plan 02 — app/repository/access_event.py                   provider: access_event_repository
class AccessEventRepository:
    def append(self, dataset_id, event_type: str, changed_by, old_value, new_value, note) -> None
    def list_for_dataset(self, dataset_id) -> list[DatasetAccessEvent]

# plan 02 — app/service/dataset_access_audit.py                      provider: dataset_access_audit
class DatasetAccessAudit:   # the only writer of dataset_access_events outside tests; also counts datamap_dataset_access_events_total
    def record(self, dataset_id, event_type: AccessEventType, changed_by: UUID | None,
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
#   dataset_anonymous_link_repository, share_service, anonymous_link_service,
#   embargo_notification_repository, embargo_notification_service
```

**One mechanism announces the end of an embargo.** Nothing is sent when an embargo ends: the owner's early end and the manual DOI both set `embargo_until` to now through `EmbargoTermination.end`, and a natural expiry needs no write at all. Plan 03's dispatch pass (`EmbargoNotificationService.queue_due`) finds every enabled dataset whose `embargo_until` has passed with no `expired` event since, records `expired` through `DatasetAccessAudit` (`changed_by` null) and queues the *Embargo ended* messages, reading the latest `ended_early` event to say whether and why it ended early.

## Metrics (RFC 005 names)

| Metric | Type | Labels | Plan |
|---|---|---|---|
| `datamap_emails_total` | counter | `template` (`notification`, `dataset_invitation`, `embargo_reminder`, `embargo_ended`), `outcome` (`sent`, `retried`, `failed`, `skipped`) | 01 |
| `datamap_email_pending` | gauge | — | 01 |
| `datamap_anonymous_link_views_total` | counter | `tenancy`, `outcome` (`shown`, `shown_after_embargo`, `redirected`, `not_found`) | 03 |
| `datamap_anonymous_links_created_total` | counter | `tenancy` | 03 |
| `datamap_dataset_access_events_total` | counter | `event` (the `dataset_access_events.event_type` values) | 02 |

Webapp telemetry: add pages `/anonymous/[token]`, `/doi/datasets/[datasetId]/versions/[versionName]`, `/invitations/[token]`, `/app/datasets/shared` to `PAGES`; add UI events `embargo_set`, `embargo_extended`, `dataset_shared`, `anonymous_link_created` to `UI_EVENTS`.

## Casbin seed additions (plan 02)

Added to `app/resources/casbin_seed_policies.sql`, `app/resources/rbac_data.sql` and `tests/integration/fixtures/seed_clients.sql`:

```sql
('p', 'datasets_shared', '/api/v1/datasets/?$', 'GET', 'allow', NULL, NULL),
('p', 'datasets_shared', '/api/v1/datasets/[0-9a-f-]{36}(/.*)?$', '(GET|POST|PUT|DELETE)', 'allow', NULL, NULL),
('p', 'datasets_shared', '/api/v1/tus', 'POST', 'allow', NULL, NULL)
```

Production: the same three rows are inserted by hand, as the README describes for seed policies, before the gatekeeper with plan 02 is deployed.

## Webapp routes (plan 05)

Every screen follows the Claude Design canvas vendored at `docs/design/rfc-003-embargo/Embargo Feature.dc.html` (sections §1a–§1i); plan 05 cites the section for each task.

| Page | Auth | Calls |
|---|---|---|
| `/app/datasets/shared` | logged in, tenancy not required | `GET /api/datasets?shared=true`; rendered as the "Shared with me" **tab** of the datasets list (design §1f), not a sidebar entry; for an account with no tenancy it is the only tab and "New dataset" is absent |
| `/app/datasets/[datasetId]` (existing) | logged in, tenancy not required | adds the embargo badge and card, the Share button and dialog, the Settings rows and the History (§1b, §1c, §1d, §1e, §1g, §1h); reads `embargo`, `access`, `owner`, `GET /share` and `GET /access-events` |
| `/app/datasets/new` (existing) | logged in | the "Who can see it" choice (§1a); the embargo is sent with `PUT /datasets/{id}/embargo` before the files are uploaded, so they never sit in an unembargoed dataset |
| DOI form (existing, `DatasetCitation.tsx`) | logged in | manual mode on an embargoed dataset → confirmation dialog, then `end_embargo: true`; manual mode on a dataset without embargo → notice that it can no longer be embargoed, confirmed before sending |
| `/anonymous/[token]` | public | `GET /anonymous/{token}` server-side |
| `/doi/datasets/[datasetId]/versions/[versionName]` | public | `GET /datasets/{id}/embargo-status?version={v}` server-side; shows the notice and the DOI (§1i); redirects to `/app/datasets/{id}/versions/{v}` when not embargoed |
| `/invitations/[token]` | logged in (redirect to login with callback) | `GET /invitations/{token}` to show the invitation, or that it was used (§1i); `POST /invitations/accept` on "Accept", then redirect to the dataset |

nginx (`infrastructure/nginx/datamap.conf` in the gatekeeper repo): the `location ~ ^/doi/datasets/...` block stops rewriting and proxies to the webapp, after the webapp page is deployed.

## Members' access (plan 06)

A per-dataset setting, the owner's alone: whether the members of the dataset's tenancy may only read it, or read and edit it as their workspace role allows. It changes what a member may do when no embargo is active; reads never change. During an active embargo it is inert, since the embargo already removes the members' access (plan 02), and it decides what they get back when the embargo ends. Permissions given through Share are untouched by it.

| `members_can_edit` | Member of the tenancy, no active embargo | Member of the tenancy, active embargo |
|---|---|---|
| `true` (default, today's behaviour) | the role decides reading, downloading, writing and deleting | as plan 02: badge only (open mode) or 404 (hidden mode) |
| `false` | the role decides reading and downloading; no write, no delete | same as `true` |

"Write" is every route checked as `DatasetAction.WRITE`: metadata, versions, uploads (the TUS hook), DOIs, sharing and anonymous links (`can_share` follows `can_edit`), the access history. "Delete" is `DatasetAction.DELETE`. With `false`, writes stay with the owner and `write` permission holders, delete with the owner. A member who also holds a `read` permission is a member for this purpose: the permission gives no write, and the role gives none either. Search is unchanged.

Storage: `datasets.members_can_edit boolean NOT NULL DEFAULT true`, migration `a7b8c9d0e1f2` (revises `a8b9c0d1e2f3`, plan 03's token hint).

The rule, in `DatasetAccessService._permits`, last branch (tenancy member, no active embargo):

```python
if action in (DatasetAction.WRITE, DatasetAction.DELETE) and not allows_member_edits(dataset):
    return False
return self._role_allows(user_id, _ROLE_METHOD[action])
```

`access.can_edit`, `can_share` and `can_delete` follow the rule: for a caller whose level is `tenancy` they are all `false` while `members_can_edit` is `false`. For the owner and permission holders nothing changes.

Payloads. Every dataset object of §Dataset payload additions (`GET /datasets/{id}`, `GET /datasets/{id}/versions/{v}`, `GET /datasets/` items including `minimal=true`) gains:

```json
"members_can_edit": true
```

`ShareState.tenancy` (plan 03 Task 12) gains the same field, and is still `null` while an embargo is active:

```json
"tenancy": {"name": "Data Amazon", "path": "datamap/production/data-amazon", "members": 14, "members_can_edit": true}|null
```

User route:

| Verb | Path | Body | Who | Success | Errors |
|---|---|---|---|---|---|
| PUT | `/datasets/{id}/members-access` | `{"members_can_edit": bool}` (strict boolean) | owner | `200 {"members_can_edit": bool, "access": {…}}` — `access` as in §Dataset payload additions, for the caller | `404` who may not see the dataset; `403 {"detail": "forbidden"}` who sees it and is not the owner; `422` a body without a boolean |

It answers the same with or without an active embargo. A change appends one `dataset_access_events` row through `DatasetAccessAudit`; setting the value it already has appends nothing:

```json
{"event_type": "members_access_changed", "old_value": {"members_can_edit": true},
 "new_value": {"members_can_edit": false}, "changed_by": "<owner>", "note": null}
```

`GET /datasets/{id}/access-events` returns it like any other entry, with `subject: null`; `datamap_dataset_access_events_total{event="members_access_changed"}` counts it. The route sits under `/api/v1/datasets/<uuid>/…`, which the `datasets_write` and `datasets_shared` policies already cover: no seed change.

Gatekeeper internal interface:

```python
# plan 06 — app/model/dataset_access.py
class DatasetAction(enum.Enum): ..., MANAGE_MEMBERS_ACCESS = "manage_members_access"   # owner only
class AccessEventType(str, enum.Enum): ..., MEMBERS_ACCESS_CHANGED = "members_access_changed"
@dataclass class MembersAccess: members_can_edit: bool; access: DatasetAccess

# plan 06 — app/model/db/dataset.py: Dataset.members_can_edit; app/model/dataset.py: Dataset.members_can_edit: bool = True

# plan 06 — app/service/dataset_access.py
def allows_member_edits(dataset) -> bool   # the column; None (a row not yet flushed) reads as the default, true

# plan 06 — app/service/members_access.py                     provider: members_access_service
class MembersAccessService:
    def set(self, dataset_id: UUID, user_id: UUID, tenancies: list[str] | None,
            members_can_edit: bool) -> MembersAccess
        # fetch_authorized(action=MANAGE_MEMBERS_ACCESS); upserts and records only on a change
```

Emails (plan 03's templates). `embargo_reminder` and `embargo_ended` take a required context key `members_can_edit` (bool), which `EmbargoNotificationService` reads from the dataset. Each message gains one sentence, in the owner's and the collaborators' copy alike (`{T}` is `tenancy_name`, `{O}` is `owner_name`):

| Message | `members_can_edit` | Owner's copy | Collaborator's copy |
|---|---|---|---|
| Reminder | true | When the embargo ends, members of {T} can read and edit this dataset again; the people you shared it with keep their access. | When the embargo ends, members of {T} can read and edit this dataset again; the people {O} shared it with keep their access. |
| Reminder | false | When the embargo ends, members of {T} can read this dataset; editing stays with the people you shared it with. | When the embargo ends, members of {T} can read this dataset; editing stays with {O} and the people they shared it with. |
| Ended (every variant, the manual DOI included) | true | Members of {T} can read and edit this dataset again; the people you shared it with keep their access. | Members of {T} can read and edit this dataset again; the people {O} shared it with keep their access. |
| Ended | false | Members of {T} can read this dataset; editing stays with the people you shared it with. | Members of {T} can read this dataset; editing stays with {O} and the people they shared it with. |

Webapp:

| Piece | Contract |
|---|---|
| Types | `MembersAccessRequest {members_can_edit: boolean}`, `MembersAccessResponse {members_can_edit: boolean, access: DatasetAccess}`; `members_can_edit` on `ShareTenancy`, `GetDatasetDetailsResponse` and the minimal list item |
| Server call | `lib/share.ts` `setMembersAccess(context, datasetId, request)` → `PUT /datasets/{id}/members-access` |
| BFF route | `PUT /api/datasets/[datasetId]/members-access` (`pages/api/datasets/[datasetId]/members-access.ts`, `bffRoute`, no tenancy required) |
| Browser | `BFFAPI.setMembersAccess(datasetId, request)`, which emits the UI event `members_access_changed` (added to `UI_EVENTS`) |
| Edit rights | unchanged: `canEditDataset` reads `access.can_edit` |
