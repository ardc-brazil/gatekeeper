# RFC 009: Tenancies and the admin area

| Status | Draft |
|--------|-------|
| Author | DataMap Team |
| Created | 2026-10-04 |
| Updated | 2026-10-04 |

## Summary

A new DataMap account today lands on "Your access is not set up yet" and waits
for someone to insert `users_tenancies` and `casbin_rule` rows by hand. This RFC
gives every account a workspace from its first sign-in, lets people ask for more
from inside the app, lets dataset owners bring colleagues into their tenancy,
and gives the DataMap admins a place to decide: the **Admin** area, whose shell
later RFCs fill with more pages.

The decisions that shape everything else:

1. **Everyone is in `datamap/production/public`.** The migration creates it and
   adds every existing account; every account created afterwards, by any path,
   is added at creation. Public is locked: it cannot be removed from anyone, and
   it has no member management. The access rule from RFC 003 does not change.
2. **New accounts can read at once.** Membership only means something with a
   dataset role, so every account gets the global `datasets_read` role at
   creation, and the migration gives it to every account that has no dataset
   role yet.
3. **The tenancy selector appears only with more than one tenancy.** With exactly
   one, it is selected and the user goes on. "Access pending" survives only for
   an account with zero tenancies, and points to requesting access.
4. **People ask in their own words; admins decide.** A request is a tenancy name
   and a reason in free text, never a path. One pending request per user. A
   DataMap admin (the global Casbin `admin` role) approves it by picking an
   existing tenancy or creating `datamap/production/{namespace}`, or declines it
   with an optional message. A new tenancy is never created for an account with
   an unconfirmed email.
5. **Owners and editors invite existing users into their tenancy without an
   admin.** From the share dialog, the owner or a `write` collaborator who is a
   member of the dataset's tenancy invites an existing account into it. The
   invitee accepts in the app; the email carries no token. Admins are told.
6. **Roles stay global.** There are no per-tenancy roles and no tenancy admins:
   members are members. The design's Reader / Contributor / Admin labels per
   membership are not built.
7. **Production only.** New tenancies are always `datamap/production/*`. Legacy
   `datamap/staging/*` tenancies are listed read-only.
8. **The Admin area ships as a shell with two working tabs.** Requests and
   Tenancies work; Users and Activity are present with an empty state and are
   filled by RFC 010.

## Motivation

### Problem statement

- **New accounts hit a dead end.** RFC 008 opened sign-up to anyone with an
  email, and every one of those accounts reaches `AccessPending` until the team
  edits the database. The only signal the team gets is the
  `new_account_pending` email.
- **Granting access is SQL.** `POST /users/{id}/tenancies` exists, but nothing
  calls it, it has two `TODO` comments about who may call it, and any account
  with `users_write` can reach it.
- **Researchers cannot bring a colleague in.** RFC 003 lets an owner share one
  dataset at a time. A group that adds a student has to ask the team to add them
  to the whole tenancy.
- **Admins have no screen.** Requests arrive by email, if at all, and decisions
  leave no trace.

### What exists today

- **Gatekeeper.** `tenancies(name PK, is_enabled)` and the
  `users_tenancies(user_id, tenancy)` association. `UserService.create`
  attaches the tenancies in its payload (none, for every RFC 008 path), grants
  the roles in its payload (none) and enqueues `new_account_pending` to
  `ADMIN_NOTIFICATION_EMAILS`. `DatasetService._determine_tenancies` checks the
  requested tenancy against the database membership on every call, so a
  membership removed in the database takes effect at once.
- **Access rule.** `DatasetAccessService.level_of` gives tenancy access only when
  the user is a member *and* a role allows `GET` on datasets
  (`reads_tenancy`). Membership without `datasets_read` or `datasets_write`
  grants nothing.
- **Casbin.** Global roles (`admin`, `users_*`, `datasets_*`, `tenancies_*`,
  `datasets_shared`) over path and verb; `admin` holds `/*` with `.*`.
- **Webapp.** `/app/tenancy` lists the session's tenancies or shows
  `AccessPending`; `RequireSession` selects the only tenancy when there is one;
  the session carries `uid` and `tenancies` and refreshes them on `update()`.
  The session does not carry roles.
- **Sharing (RFC 003).** The share dialog suggests members of the dataset's
  tenancy and resolves a typed email or ORCID to an account; the mutating share
  routes are for the owner and `write` collaborators, checked in the service.

### Goals

- Every account can use DataMap the moment it is created.
- Asking for a tenancy, and answering, happen in the app, with email on both
  sides.
- An owner can bring a known colleague into their tenancy without waiting.
- Admins see every open request, and every membership change is recorded.

### Non-goals

- Per-tenancy roles, tenancy administrators, Casbin domains.
- Environments other than production.
- Inviting people who have no account into a tenancy; RFC 003 invitations cover
  them at the dataset level.
- The Users and Activity pages, system-role toggles, disabling accounts, API
  clients (RFC 010).

## Technical design

### Data model

#### `tenancies`

Gains `display_name String(64), nullable`. `null` keeps today's derived name
(`tenancy_display_name`, the namespace title-cased). The column exists because
the design names tenancies the way their groups do — "ATTO", "LBA Legacy",
"Cerrado Flux" — and no title-casing of a slug produces those. It is set when
an admin creates a tenancy and is `Public` for the default one. Every API that
shows a tenancy name (share state, emails, the selector, admin) reads
`display_name` first. Display names are unique among enabled production
tenancies, case-insensitively, so a request can be matched to one.

#### `tenancy_requests`

```
tenancy_requests
  id               UUID primary key
  user_id          UUID, FK users ON DELETE CASCADE
  requested_name   String(128)        -- what the user typed in "Tenancy"
  reason           String(1000)       -- what the user typed in "Why"
  status           enum tenancy_request_status: pending | approved | declined | withdrawn
  tenancy          String(256), FK tenancies, nullable   -- set on approval
  created_tenancy  Boolean, default false               -- the approval created it
  decision_message String(1000), nullable               -- the decline message
  decided_by       UUID, FK users ON DELETE SET NULL, nullable
  decided_at       DateTime(tz), nullable
  created_at       DateTime(tz)
  updated_at       DateTime(tz)

  unique index uq_tenancy_requests_pending (user_id) WHERE status = 'pending'
  index ix_tenancy_requests_status_created (status, created_at)
```

The partial unique index is the "one pending request per user" rule; the
service checks first and answers `409 request_pending`, the index stops a race.

Whether a request is to *join* or to *create* is not stored: the user cannot
tell (the design's helper text says so) and neither is binding. The queue
computes a **suggested tenancy** when it lists requests: the enabled production
tenancy whose display name or namespace equals `requested_name`,
case-insensitively and ignoring spaces versus hyphens. A suggestion makes the
row a **Join**, its absence a **New**. The admin's decision is what is stored
(`tenancy`, `created_tenancy`).

#### `tenancy_invitations`

```
tenancy_invitations
  id           UUID primary key
  tenancy      String(256), FK tenancies
  user_id      UUID, FK users ON DELETE CASCADE        -- the invitee
  invited_by   UUID, FK users ON DELETE SET NULL, nullable
  dataset_id   UUID, FK datasets ON DELETE SET NULL, nullable   -- the share dialog it came from
  status       enum tenancy_invitation_status: pending | accepted | declined | withdrawn | revoked
  closed_by    UUID, FK users ON DELETE SET NULL, nullable
  closed_at    DateTime(tz), nullable
  created_at   DateTime(tz)
  updated_at   DateTime(tz)

  unique index uq_tenancy_invitations_pending (tenancy, user_id) WHERE status = 'pending'
  index ix_tenancy_invitations_user_status (user_id, status)
```

`revoked` is set when an admin removes from the tenancy a member who joined by
accepting an invitation; the removal is the revocation.

#### `tenancy_events`

Requests and invitations keep their own who and when, but direct additions and
removals by an admin leave no trace anywhere today. An append-only table records
every membership change now, so RFC 010's Activity page and user history have
the past to show:

```
tenancy_events
  id             UUID primary key
  tenancy        String(256)                -- not a FK: events outlive tenancies
  event_type     enum tenancy_event_type
  user_id        UUID, nullable             -- the subject
  actor_id       UUID, nullable             -- who did it; null for the migration and sign-up
  request_id     UUID, nullable
  invitation_id  UUID, nullable
  created_at     DateTime(tz)

  index ix_tenancy_events_created (created_at)
  index ix_tenancy_events_user (user_id, created_at)
```

`event_type`: `tenancy_created`, `member_added`, `member_removed`,
`request_created`, `request_approved`, `request_declined`,
`request_withdrawn`, `invitation_created`, `invitation_accepted`,
`invitation_declined`, `invitation_withdrawn`. `member_added` is written for
every way in (sign-up, approval, invitation, admin), distinguished by
`actor_id`, `request_id` and `invitation_id`. User ids are not foreign keys,
like `dataset_access_events`.

`users_tenancies` does not change.

### Migration

One revision on top of `b1c2d3e4f5a6`, every step safe to run against data that
already has part of it:

1. Add `tenancies.display_name`.
2. Create the default tenancy:
   `INSERT INTO tenancies (name, display_name, is_enabled) VALUES ('datamap/production/public', 'Public', true) ON CONFLICT (name) DO UPDATE SET is_enabled = true, display_name = COALESCE(tenancies.display_name, 'Public')`.
3. Add every user, enabled or not, to it:
   `INSERT INTO users_tenancies (user_id, tenancy) SELECT id, 'datamap/production/public' FROM users ON CONFLICT DO NOTHING`.
4. Give `datasets_read` to every user with no dataset role:
   insert `('g', user_id, 'datasets_read')` into `casbin_rule` for each user
   with no `g` row naming `admin`, `datasets_read`, `datasets_write` or
   `datasets_admin`. Casbin's five-second reload picks the rows up.
5. Create the three enums, the three tables and their indexes.

Downgrade drops the tables, enums and column. It leaves the public tenancy, its
memberships and the granted roles in place: they are data, and removing them
would take access away from people.

`DEFAULT_TENANCY = "datamap/production/public"` is a constant in
`app/model/tenancy.py`, not a setting: the migration and the code must agree.

### Account creation

`UserService.create` — the one place every creation path passes through
(`POST /users`, password sign-up, ORCID email verification) — now:

- appends `DEFAULT_TENANCY` to the tenancies in the payload;
- adds `datasets_read` to the roles in the payload;
- writes a `member_added` event with no actor;
- **no longer enqueues `new_account_pending`.** No account waits for a
  workspace any more, so the email would be wrong; admins hear about requests
  instead (see *Emails*). The template and its integration test are removed.
  `ADMIN_NOTIFICATION_EMAILS` keeps its meaning: the addresses told about
  things admins must act on.

### Public is locked

- Removing `DEFAULT_TENANCY` from a user answers `409 public_tenancy_locked`.
- `DELETE /tenancies/{public}` and `PUT /tenancies/{public}` answer the same.
- Admin routes that manage members refuse it with the same code.
- Invitations and request approvals into it answer `409 public_tenancy_locked`;
  everyone is already in.

**Share suggestions skip public.** RFC 003 limits the share dialog's
suggestions to the dataset's tenancy so that an author cannot enumerate the
platform's accounts. With everyone in public, that limit would be gone for every
dataset in public: `GET /datasets/{id}/share/candidates` returns `[]` when the
dataset's tenancy is `DEFAULT_TENANCY`. People are still reached by typing an
exact email or ORCID.

### Legacy staging tenancies

Existing `datamap/staging/*` tenancies keep working for their members. The
admin Tenancies list shows them in a separate group, **Legacy · staging**,
after the production ones, without an environment column: their path says it.
They are read-only: the member panel lists members, with no **+ Add**, no
remove, and no pending invitations. Requests cannot be approved into them and
invitations cannot target them (`409 legacy_tenancy_read_only`).

### Endpoints

All under `/api/v1`, all behind `authenticate` (client credentials). Three
kinds of user authorization:

- **self** — a new `authorize_self` interceptor: `{id}` must equal `X-User-Id`,
  else `401`. Casbin is not consulted, so an account without any role can
  reach its own requests and invitations; an admin acts on other people's
  through `/admin`, never through these.
- **admin** — plain `authorize`. Only the `admin` role's `/*` policy matches
  `/api/v1/admin/...`; no other seeded pattern does.
- **dataset** — `authorize` (Casbin allows the dataset routes to
  `datasets_write` and `datasets_shared`), then the service decides on the
  dataset, as RFC 003's share routes do.

#### User side

| Verb and path | Auth | Body / query | Response |
|---|---|---|---|
| `GET /users/{id}/tenancies` | self | — | `200 [{path, display_name, is_default, is_legacy}]` |
| `GET /users/{id}/tenancy-requests` | self | — | `200` the latest 5, newest first |
| `POST /users/{id}/tenancy-requests` | self | `{tenancy_name, reason}` | `201 {request}`; `409 request_pending`; `429 too_many_requests` |
| `DELETE /users/{id}/tenancy-requests/{request_id}` | self | — | `204` (withdrawn); `404` unless pending and theirs |
| `GET /users/{id}/tenancy-invitations` | self | — | `200` pending ones: tenancy display name, inviter name, dataset name, date, dataset count |
| `POST /users/{id}/tenancy-invitations/{invitation_id}/accept` | self | — | `200 {tenancy}`; `404 invitation_not_found` unless pending and theirs |
| `POST /users/{id}/tenancy-invitations/{invitation_id}/decline` | self | — | `204`; same `404` |

`tenancy_name` is 1–128 characters and `reason` 1–1000, both trimmed. At most
three requests per user in 24 hours, withdrawn ones included.

#### Dataset side (share dialog)

| Verb and path | Auth | Body / query | Response |
|---|---|---|---|
| `GET /datasets/{id}/share/lookup?value=` | dataset | exact email or ORCID | `200 {user: {id, name, email}, tenancy_member, invitation_pending, can_invite}`; `404 no_account` |
| `POST /datasets/{id}/tenancy-invitations` | dataset | `{user_id}` | `201 {invitation}` |
| `DELETE /datasets/{id}/tenancy-invitations/{invitation_id}` | dataset | — | `204` (withdrawn) |

`GET /datasets/{id}/share` gains `tenancy_invitations` (pending ones created
from this dataset, with invitee and inviter) and `can_invite_to_tenancy`.

**Who may invite:** the dataset's owner or a user with `write` permission on it
(RFC 003), who is also a member of the dataset's tenancy. Tenancy members who
can edit only through *members can edit* are not editors here. Otherwise
`403 forbidden`. The tenancy must be enabled, production and not public. The
invitee must be enabled and not already a member (`409 already_member`), with
no pending invitation to it (`409 invitation_pending`).

**Who may withdraw:** the inviter, through the dataset route; anyone else gets
`403`. Admins withdraw through `/admin`.

The lookup resolves only an exact email or ORCID, as RFC 003's grant already
does, so it reveals nothing the grant did not. It is open to the same callers
as the grant.

#### Admin

| Verb and path | Body / query | Response |
|---|---|---|
| `GET /admin/tenancy-requests/counts` | — | `{open, join, new, closed}` — the sidebar and tab badges |
| `GET /admin/tenancy-requests` | `status=open\|closed`, `kind=join\|new`, `q`, `limit`, `offset` | rows with requester (name, email, email confirmed, ORCID), request, suggested tenancy, created_at; closed rows add decision, tenancy, decided_by, decided_at |
| `GET /admin/tenancy-requests/{id}` | — | the row plus the requester's tenancies and global dataset role, and the suggested tenancy's member count |
| `POST /admin/tenancy-requests/{id}/approve` | `{tenancy}` or `{new_tenancy: {display_name, namespace}}` | `200 {request}` |
| `POST /admin/tenancy-requests/{id}/decline` | `{message?}` | `200 {request}` |
| `GET /admin/tenancies` | — | `[{path, display_name, members, datasets, is_default, is_legacy, is_enabled}]` |
| `POST /admin/tenancies` | `{display_name, namespace}` | `201 {tenancy}` |
| `GET /admin/tenancies/{path}/members` | `limit`, `offset` | members (id, name, email, since, invited_by) and pending invitations |
| `GET /admin/tenancies/{path}/members/{user_id}` | — | removal impact: `member_since`, `datasets_in_tenancy`, `shared_with_user`, `owned_by_user` |
| `POST /admin/tenancies/{path}/members` | `{user_id}` | `201` |
| `DELETE /admin/tenancies/{path}/members/{user_id}` | — | `204` |
| `DELETE /admin/tenancy-invitations/{id}` | — | `204` (withdrawn) |
| `GET /admin/users?q=` | at least 2 characters | at most 10 enabled users matching name, email or ORCID iD: id, name, email |

`q` on the queue matches the requester's name, email or ORCID iD. Closed means
approved or declined; withdrawn requests leave the queue and stay in the events.

**Approving.** Atomically: the request must be pending (`409 request_not_pending`),
the user is added, the request becomes `approved`, events are written, then the
email is enqueued.

- `{tenancy}`: an enabled production tenancy other than public, of which the
  requester is not a member (`409 already_member`).
- `{new_tenancy}`: `namespace` matches `^[a-z0-9-]+$`, 2–63 characters, not
  `public`; the path `datamap/production/{namespace}` must not exist, enabled or
  not (`409 tenancy_exists`); `display_name` is 1–64 characters and unique
  (`409 display_name_taken`); the requester's email must be confirmed
  (`409 requester_email_unverified`). The tenancy is created with
  `is_enabled = true` and a `tenancy_created` event.

Approval does not change roles. The review dialog shows the requester's global
dataset role so the admin can see that, for example, a requester with only
`datasets_read` will not be able to upload to the tenancy just created; granting
`datasets_write` stays on `PUT /users/{id}/roles` until RFC 010 puts the toggle
on the user page.

**Removing a member** answers `409 public_tenancy_locked` for public and
`409 legacy_tenancy_read_only` for staging. The user's datasets in the tenancy
stay theirs: the owner check comes first in the access rule. An accepted
invitation behind the membership becomes `revoked`. No email is sent.

#### Retired

`POST /users/{id}/tenancies` and `DELETE /users/{id}/tenancies` are removed.
Nothing calls them, they let `users_write` change memberships, and they bypass
the public lock and the events. `POST /users` keeps accepting `tenancies`,
with public always added.

### Casbin

No new `p` rows. The admin routes need none (`admin` already holds `/*`), and
the new dataset routes fall under the existing `/api/v1/datasets` patterns. A
`deny` row was considered for the retired membership routes and rejected: the
policy effect is `allow && !deny` across every role a subject holds, so a deny
on `users_write` would also block an admin who happens to hold it.

New `g` rows: `datasets_read` for every account, from the migration and from
`UserService.create`. An integration test asserts that a `users_write` account
gets `401` on `/api/v1/admin/tenancy-requests`, so a future seed row matching
`/admin` by accident is caught.

### Errors

Bodies are `{"detail": "<code>"}` like the rest of the API.

| Status | Codes |
|---|---|
| 400 | `invalid_request`, `tenancy_name_invalid`, `reason_invalid`, `namespace_invalid`, `display_name_invalid`, `message_invalid` |
| 403 | `forbidden` (not owner/editor, not a member of the tenancy, not the inviter) |
| 404 | `request_not_found`, `invitation_not_found`, `tenancy_not_found`, `no_account` |
| 409 | `request_pending`, `request_not_pending`, `already_member`, `invitation_pending`, `tenancy_exists`, `display_name_taken`, `requester_email_unverified`, `public_tenancy_locked`, `legacy_tenancy_read_only`, `tenancy_disabled` |
| 429 | `too_many_requests` |

### Emails

Through the outbox like every other email, in English, on the transactional
shell (`_transactional.html`) — the "same shell" of the design's 1g. None
carries a token, so `secret_fields` is empty for all of them. Admin messages
are one per address in `ADMIN_NOTIFICATION_EMAILS`, with
`dedup_key = {template}:{object_id}:{address hash}` as RFC 008 does; an empty
list sends nothing. Accounts with a placeholder address are skipped as today.

| Template | To | Sent when | Content |
|---|---|---|---|
| `tenancy_request_received` | admins | a request is created | Subject "Tenancy request from {name}". "{name} asked for access to a tenancy." Details: Name, Email (with "confirmed" / "not confirmed"), Tenancy asked for, Why, Requested. CTA "Review request" → `/app/admin/requests?request={id}`. Reason line: on the list of administrators. |
| `tenancy_access_granted` | the user | a request is approved, or an admin adds the user | Subject "You now have access to {tenancy}". "{admin} gave you access to {tenancy} on DataMap." Details: Tenancy (display name and path), Datasets (count). "Your datasets in Public stay where they are." CTA "Open DataMap" → `/app/tenancy`. |
| `tenancy_request_declined` | the user | a request is declined | Subject "Your request for {requested name}". "An administrator could not give you access to {requested name}." The admin's message, if any, quoted. "You can still work in Public and can send another request." CTA "Open DataMap". |
| `tenancy_invitation` | the invitee | an invitation is created | Subject "{inviter} invited you to {tenancy}". "{inviter} invited you to join {tenancy} on DataMap, from the dataset “{dataset}”." "Sign in to accept or decline. This email cannot accept for you." CTA "Open DataMap" → `/app/home`. |
| `tenancy_invitation_notice` | admins | an invitation is created | Subject "{inviter} invited {invitee} to {tenancy}". Details: Inviter, Invitee (name, email), Tenancy, Dataset. "No approval is needed. You can withdraw it, or remove {invitee} later, from Admin › Tenancies." CTA "Open tenancy" → `/app/admin/tenancies?tenancy={path}`. |

The CTA URLs are built from `PUBLIC_BASE_URL`. The template's `reason` block
explains why the recipient got it, as every existing template does.

### Webapp

#### Session

- `hydrateWithUserInfo` adds `token.admin = user.roles.includes("admin")`; the
  session exposes `session.user.admin`. Only the boolean, not the role list.
- After a change that alters the user's own tenancies the page calls
  `update()`, which re-reads them (the `jwt` callback already does this on
  `update`):
  - accepting an invitation: `update()`, then select the new tenancy and go to
    `/app/home` (the design: "the home switches to it");
  - an approved request: the home and profile panels read
    `GET /users/{id}/tenancy-requests` through SWR, revalidated on focus; when
    the latest request turns `approved` they call `update()` and offer
    "Switch to {tenancy}". The selector page reads the user server-side and
    calls `update()` when that list differs from the session's.
  - removal: a `401 unauthorized_tenancy` from a dataset route clears the
    selected tenancy, calls `update()` and sends the user to `/app/tenancy`.

#### Tenancy selection

- `/app/tenancy`:
  - **one tenancy:** select it and go to `/app/home`; no page.
  - **more than one:** the design's 1i. "Welcome, {first name}" / "Choose the
    tenancy you want to work in." Rows from `GET /users/{id}/tenancies` with
    display name and path; Public uses the `public` icon. A pending request is
    a row with the dashed `tenancy` icon, its requested name and "Requested
    {date} · waiting for an administrator" in amber, and **Withdraw**. A
    request declined in the last 30 days, with no newer one, shows
    "Declined {date}" and the admin's message. Footer: "+ Request access to
    another tenancy".
  - **zero tenancies:** `AccessPending`, rewritten: "You're not in any tenancy"
    / "Your account is not part of any tenancy, so there is nothing to work in
    yet. Ask for access to the group or project you work with; an
    administrator reviews it and you're emailed with the answer." Button
    **Request access**; the existing *Shared with me* link and "check again"
    stay.
- The avatar menu shows "Switch tenancy" only with more than one tenancy, and
  gains "Request access to a tenancy" next to it.
- The profile's Tenancies section lists display names, marks Public "Everyone
  is in public", and shows the pending or declined request with the same copy as
  the selector.

**Request access dialog** (the design's 1i, 520 px): title "Request access";
"Name the tenancy you need. An administrator reviews it; you're emailed with
the answer." Field **Tenancy**, helper "The name of the group or project. If it
exists, this is a request to join; if not, a request to create it. Only
administrators can tell which." Field **Why** (textarea). **Cancel** /
**Send request**. Formik and Yup with the limits above; `409 request_pending`
reads "You already have a request waiting. Withdraw it to send another."

#### Home

A panel at the top of `/app/home` (the design's 1j), one card per pending
invitation: `tenancy` icon, "{inviter} invited you to {tenancy}", and
"{n} datasets · from “{dataset}” · {date}"; **Decline** / **Accept**. The
design's "As Reader" is dropped (decision 6). Below the invitations, while a
request is pending: "Your request for {name} is waiting for an administrator ·
Withdraw".

#### Share dialog

When the dataset has a production tenancy other than public and
`can_invite_to_tenancy` is true, a typed value with the shape of an email or
ORCID is looked up (`/share/lookup`, debounced). If it is an account outside the
tenancy, the suggestion card of the design's 1j appears: avatar, name, "{email}
· not a member of {tenancy}", and two options:

- **Share this dataset only** (default) — "Can read · as today", the level
  chip's value; this is RFC 003's grant, unchanged.
- **Invite to {tenancy}** — "Member of the tenancy · sees its {n} datasets once
  they accept · administrators are notified".

Pending tenancy invitations appear in *Who has access* with the dashed icon,
"Invited to {tenancy} {date} · not accepted yet", and **Withdraw** for the
inviter. The footer reads "Owners and editors can invite to the tenancy" when
inviting is possible. The design's "Contributor is offered only to owners" is
not built: there is no role to offer.

#### Admin area

The design's shell, built so RFC 010 adds pages to it without touching it:

- **Sidebar.** For `session.user.admin`, a divider after Profile and an
  **Admin** item (`admin_panel_settings`, filled when active) with a black pill
  showing `open` from `/admin/tenancy-requests/counts` (SWR, revalidated on
  focus and every 60 s, hidden at zero). On admin pages the tenancy footer
  reads "All tenancies".
- **Layout.** `components/Admin/AdminLayout.tsx`: the app sidebar plus a 64 px
  header with tabs **Requests** (count badge) · **Users** · **Tenancies** ·
  **Activity**, active tab underlined, avatar right. Admin pages use
  `tenancyOptional`: they span every tenancy.
- **Gate.** Each page declares `auth = { admin: true }`; `RequireSession`
  renders the not-found page for a session without `admin`, so the area does
  not reveal itself. BFF routes under `pages/api/admin/` use a new
  `adminChain` (request logging, `auth`, the `admin` claim) and the gatekeeper's
  Casbin check is the authority.

| Route | Content |
|---|---|
| `/app/admin` | redirects to `/app/admin/requests` |
| `/app/admin/requests` | the design's 1a |
| `/app/admin/tenancies` | the design's 1d |
| `/app/admin/users` | empty state: "Users" / "Coming soon. Until then, add and remove people from Tenancies." |
| `/app/admin/activity` | empty state: "Activity" / "Coming soon: every admin action, who and when." |

**Requests (1a).** "Requests" / "{open} open · {join} for existing tenancies,
{new} for new ones". Filter pills **Open**, **Join existing**, **New tenancy**,
**Closed** with counts; search "Name, email or ORCID". Table **Account |
Request | Requested | Email | ·**: initials avatar, name and email; a **Join**
or **New** pill, the suggested tenancy's display name or the requested name,
and the reason truncated below; the date and "{n} days waiting", amber after 3
days; "verified" / "unverified" with the design's icons; **Review** and a
`more_horiz` menu holding "Decline…". Below, **Recently closed** (the last 5)
with "Activity →": "{who} · {tenancy} · Approved" or "· Approved · new tenancy"
in green, "· Declined" in red, "by {admin} · {when}".

**Review dialog (1c, 560 px).** Header "{requester} · {email} · requested
{relative}". A two-way switch, **Join existing** / **New tenancy**, starts on
the suggestion's side.

- *Join existing* — title "Join {tenancy}". A tenancy picker (production,
  enabled, not public, not already the requester's), prefilled with the
  suggestion. Info rows: **Tenancy** "{display name}" / `{path} · {n} members`;
  **Reason**; **Currently in** the requester's tenancy paths and their global
  dataset role in words ("can read datasets" / "can create and edit datasets").
  The design's Reader / Contributor cards are not built.
- *New tenancy* — title "New tenancy: {display name}". **Display name**
  prefilled with the requested name, **Namespace** prefilled with its slug,
  both editable; preview `datamap/production/{namespace} · requester becomes a
  member`. For an unconfirmed email the amber banner "Email not verified. A new
  tenancy can't be created for an unverified account." and **Create and
  approve** disabled.
- Notice: "{first name} is emailed either way." Footer: **Decline…** (red link)
  · **Cancel** · **Approve** / **Create and approve**.

**Decline dialog (1e, 440 px).** "Decline request?" / "{requester} · join
{tenancy}" or "· new tenancy {name}". **Message to {first name}** (optional),
placeholder "Ask a member of the tenancy to invite you from a dataset's Share
dialog". Bullet "— Stays in public · can request again". **Cancel** /
**Decline** (red).

**Tenancies (1d).** "Tenancies" / "{n} tenancies · root `datamap` · everyone is
in `public`"; **+ New tenancy** opens the design's create dialog without the
Environment field (Display name, Namespace, preview, **Cancel** / **Create**).
The list: Public first, with a `lock` and no chevron; then production tenancies
by display name; then **Legacy · staging**. Each row: icon, name, path, members,
datasets. No environment pill. The right panel for the selected tenancy: name,
path, "Members · {n}", **+ Add**; members with initials, name and email (no
role), "invited by {name}" when they came by invitation, a `close` button;
pending invitations below, dashed, with **Withdraw**; "Show {n} more" pages by
50. Public shows "Everyone · {n} accounts" and no list.

- **+ Add** — "Add to {tenancy}": search "Name, email or ORCID"
  (`/admin/users`), pick one, "{first name} is emailed." **Cancel** / **Add**.
- **Remove** — the design's prompt: "Remove from {tenancy}?" / "{name} · member
  since {date}"; "— Loses access to the {n} datasets of the tenancy",
  "— Keeps {n} datasets shared explicitly" (when there are any), "— Still owns
  {n} datasets of the tenancy" (when there are any), "— Stays in public".
  **Cancel** / **Remove** (red).

#### BFF

| Route | Proxies |
|---|---|
| `pages/api/tenancies/index.ts` | `GET /users/{uid}/tenancies` |
| `pages/api/tenancy-requests/index.ts`, `[requestId].ts` | the user's requests: list, create, withdraw |
| `pages/api/tenancy-invitations/index.ts`, `[invitationId]/accept.ts`, `[invitationId]/decline.ts` | the user's invitations |
| `pages/api/datasets/[datasetId]/share/lookup.ts` | `/share/lookup` |
| `pages/api/datasets/[datasetId]/tenancy-invitations/index.ts`, `[invitationId].ts` | invite, withdraw |
| `pages/api/admin/tenancy-requests/...` | `counts`, list, detail, `approve`, `decline` |
| `pages/api/admin/tenancies/...` | list, create, members, add, remove, removal impact |
| `pages/api/admin/tenancy-invitations/[invitationId].ts` | withdraw |
| `pages/api/admin/users.ts` | search |

The user routes take the user from the session, never from the request, and use
`authOnlyChain`: an account with zero tenancies must reach them. Matching
`BFFAPI` methods; routes in `InternalRoutesConstants.ts`; copy in
`TenancyConstants.ts` and `AdminConstants.ts`.

### Security notes

| Threat | Defence |
|---|---|
| A non-admin approving, adding or removing | admin routes pass Casbin only with `admin`; the BFF claim is a convenience, not the check; the old `/users/{id}/tenancies` routes are gone |
| Joining a tenancy by inviting oneself | invitations need owner or `write` on a dataset of that tenancy *and* membership of it; the invitee must be someone else's account, accepted only by them |
| An outside collaborator opening a tenancy | a `write` collaborator who is not a member cannot invite |
| Accepting for someone else | accept and decline are self-only routes; the email has no token |
| Enumerating tenancy names | a user sees only their own tenancies, their own requests' names and the tenancy of a dataset they can already open; the request form never lists tenancies, and the suggestion is computed for admins only |
| Enumerating accounts | share suggestions are off in public; the lookup takes only an exact email or ORCID, as RFC 003's grant does; global user search is admin-only |
| Request spam to admins | one pending request per user, three per day |
| Removing someone's last workspace | public cannot be removed |
| Stale membership in a session | the gatekeeper checks membership in the database on every dataset call |

Global roles mean that a member with `datasets_write` can create datasets in
every tenancy they belong to, public included, and a dataset in public is
visible to every account. That is today's rule applied to a tenancy that
contains everyone; the new-dataset form says so ("Visible to every DataMap
account") when public is selected.

## Testing

**Integration (gatekeeper)**, against Mailpit, new files
`test_tenancy_requests_api.py`, `test_tenancy_invitations_api.py`,
`test_admin_tenancies_api.py`:

- the migration: public exists, every seeded user is in it, users without a
  dataset role have `datasets_read`; a second `upgrade` after a `downgrade`
  succeeds;
- every creation path (`POST /users`, password sign-up, ORCID email
  verification) lands in public with `datasets_read` and sends no
  `new_account_pending`; the new account lists public datasets;
- requests: create, `409 request_pending`, the daily limit, withdraw, the
  admin email per address and none for an empty list; self-only (`401` for
  another user's id, even an admin's);
- approval into an existing tenancy and into a new one; `already_member`,
  `tenancy_exists`, `display_name_taken`, `namespace_invalid`,
  `requester_email_unverified`, `request_not_pending` on a second decision;
  approved and declined emails; the requester can read the tenancy's datasets
  right after;
- the queue's counts, filters, search by name, email and ORCID, and Join/New
  from the suggestion;
- invitations: owner and `write` collaborator can invite; a reader, a
  *members can edit* member and a non-member collaborator get `403`; public and
  staging refused; invitee email and admin notice; accept adds membership and
  is self-only; decline; withdraw by inviter, `403` for another editor, admin
  withdraw;
- admin tenancies: list counts, legacy group, create, add with email, remove
  with removal impact, `public_tenancy_locked` everywhere, revoked invitation
  on removal; a removed member's next dataset call answers `401`;
- a `users_write` account gets `401` on every `/admin` route; the retired
  `/users/{id}/tenancies` routes answer `404`/`405`;
- share candidates return `[]` for a dataset in public; `/share/lookup` for an
  exact email, an ORCID, and `no_account`;
- every `tenancy_events` row the flows above should write.

**Unit (gatekeeper):** namespace validation, request-to-tenancy matching,
display-name fallback.

**Webapp (Jest):** the selector's three cases; `hydrateWithUserInfo` setting
`admin`; `RequireSession` hiding admin pages; the request form; the home
invitation panel calling `update()` and selecting the tenancy; the share
suggestion card's two options; the review dialog's disabled state for an
unconfirmed email; the admin sidebar entry and badge.

## Delivery

| PR | Repository | Content |
|---|---|---|
| A | gatekeeper | Migration, default tenancy and `datasets_read` at creation, `new_account_pending` retired, user / dataset / admin routes, emails, events, public lock, share-candidate change, tests |
| B | webapp | Selector rules, `AccessPending` rewrite, request form, profile and avatar-menu entries, home invitation panel, share-dialog invitation, `update()` refresh |
| C | webapp | `admin` claim, Admin shell, Requests and Tenancies tabs, empty Users and Activity |

A ships first and is useful alone: every account lands in public and admins get
request emails as soon as B lets users send them. B and C are independent of
each other. Until C ships, requests are decided with the admin API.

### Before shipping A

- `ADMIN_NOTIFICATION_EMAILS` lists people who will act on requests.
- Decide whether any existing account must *not* gain `datasets_read`; the
  migration grants it to every account without a dataset role.

## Alternatives considered

### Public as an implicit membership

Treat every account as a member of public without rows. Every query that
joins `users_tenancies` — the access rule, member counts, the share dialog —
would need a special case, and the special case would be forgotten somewhere.
One row per account is cheap and makes public an ordinary tenancy with a lock.

### Per-tenancy roles (Casbin domains)

What the design draws: Reader, Contributor and Admin per membership. It changes
the Casbin model, every policy, the access rule and the role checks in the
webapp. Out of proportion to "let people in"; decision 6 keeps roles global.

### The user picks the tenancy from a list

Simpler to decide, but it shows every tenancy name to every account, and the
people asking often do not know what the group's tenancy is called. Free text
read by an admin costs the admin one click.

### Invitation links with a token

RFC 003 uses tokens because its invitees may not have an account. Here the
invitee always has one, so acceptance can be a signed-in action, and an email
that cannot accept anything is one less thing to leak.

### Keeping `new_account_pending`

It reported accounts waiting for a workspace; after this RFC no account waits.
Admins hear about what needs a decision — requests and invitations — instead.

### Requests answered by tenancy members

Spreads the decision to the people who know the requester, but needs tenancy
administrators, which decision 6 rules out. Members bring people in through
invitations instead.

## Out of scope

- **RFC 010:** the Users list and user detail (memberships, history, sign-in
  providers, API clients card), system-role toggles and the "can't remove your
  own administrator role" rule, disabling accounts, API clients (create, show
  secret once, rotate), and the Activity log and its filters, reading
  `tenancy_events`.
- Editing a tenancy's display name or namespace, disabling a tenancy from the
  admin area.
- Moving or deleting the legacy staging tenancies.
- An email when an admin removes someone from a tenancy.
- Inviting people without an account into a tenancy.
- Feature flags (present in the design's data, drawn on no screen).

## Open questions

- Should approving a request that **creates** a tenancy also grant the
  requester `datasets_write` when they lack it? Without it they cannot upload
  to their own tenancy until an admin grants the role through the API (or, after
  RFC 010, the toggle). The design assumed "requester becomes Contributor".
- Should the staging tenancies' members be moved to their production
  counterparts and the staging tenancies disabled, rather than kept read-only?
