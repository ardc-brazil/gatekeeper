# RFC 003: Dataset Embargo

| Status | Draft |
|--------|----------|
| Author | DataMap Team |
| Created | 2026-09-09 |
| Updated | 2026-09-30 |

> **Scope revised on 2026-09-30.** The feature was on hold from 2026-09-11 while
> product reshaped it. The revision brings into scope an anonymous reviewer link
> that shows metadata only, email delivery for invitations and embargo
> reminders, and a share dialog in place of the plain allowlist form. Nothing
> below has been built yet. The questions still open are listed at the end.

## Summary

Researchers need a citable identifier for a dataset while the article that describes it is still under review, without exposing the data itself. This RFC proposes **embargo**: a per-dataset, per-person access restriction with an end date, under which the files are reachable only by the dataset owner and by people the owner names — not by other members of the same tenancy, and not by the public.

Three decisions shape the design:

1. **Visibility during the embargo is the author's choice**, not a platform-wide rule. In *open mode* the dataset appears in its tenancy's listings carrying an embargo badge; in *hidden mode* it does not appear at all for anyone outside the allowlist. In neither mode is there a public page with metadata: outside the platform, the DOI leads only to a notice that the dataset is under embargo, and the only view of the dataset itself is a reviewer link, if the author creates one. The choice is made when the dataset is created, so it never surfaces before the author decides, and can be changed later.
2. **The embargo state is derived from a date**, not stored as a flag, and is evaluated at read time. No job decides access; the only scheduled work is sending email.
3. **Reviewers see the metadata, not the authors and not the files.** A reviewer link lets a venue's reviewers read the dataset's description without an account. Every field that could identify the authors is shown as redacted rather than removed, and nothing can be downloaded.

## Motivation

### Problem statement

Today the platform has no way to express "this dataset exists, is citable, but its data is not available yet". Access is decided by tenancy: whoever belongs to the tenancy sees the dataset and can download from it. That is too coarse for the AmazonFace data policy, which requires that data under embargo reach only the responsible researcher, the people they authorise, and the Data Team.

The same period is when the article is under review at a venue. Double-blind venues ask for the data to be described to reviewers without revealing who produced it, and today the only way to show a dataset is to show it with its authors.

### Why the current authorization model cannot express it

Casbin is configured over request path and HTTP verb:

```
m = g(r.sub, p.sub) && regexMatch(r.obj, p.obj) && regexMatch(r.act, p.act)
```

`obj` is the URL path. The model answers "may this subject call `GET /datasets`", never "may this subject see *this* dataset". Embargo needs the second question, and there is nowhere in the current model to put it.

### Goals

- Restrict file access to a named list of people, independent of tenancy.
- Keep the dataset citable while embargoed.
- Let the author decide whether the dataset is discoverable during the embargo.
- Give a venue's reviewers anonymous access to the metadata, with authorship redacted, and tell the author how the link is being used.
- Make granting access as easy as sharing a document: pick a colleague, or type an email or ORCID.
- Tell people by email when they are invited, and remind authors before their embargo ends.
- Record every embargo decision, so the data policy has evidence rather than recollection.

### Non-goals

- File access for reviewers.
- Automatic promotion of the DOI when the embargo ends.
- Redacting authorship from free text (see *Reviewer link*).
- An embargo at the storage level. The embargo is a feature of the application: the gatekeeper enforces it on every route, and whoever operates the infrastructure with storage credentials is outside it.

## Technical design

### Database changes

The embargo is derived: a dataset is under embargo when `embargo_until` is not null and still in the future. There is no boolean to drift out of sync with the date.

```sql
ALTER TABLE datasets
  ADD COLUMN embargo_until            timestamptz NULL,
  ADD COLUMN embargo_metadata_visible boolean     NOT NULL DEFAULT false,
  ADD COLUMN embargo_note             text        NULL;
```

`embargo_metadata_visible` defaults to `false` on purpose: the dataset must not appear in any listing between being created and the author choosing a mode.

```sql
CREATE TABLE dataset_permissions (
  dataset_id uuid        NOT NULL REFERENCES datasets(id),
  user_id    uuid        NOT NULL REFERENCES users(id),
  level      varchar(16) NOT NULL,               -- read | write
  granted_by uuid        NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (dataset_id, user_id)
);

CREATE TABLE dataset_invitations (
  id          uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id  uuid         NOT NULL REFERENCES datasets(id),
  email       varchar(256) NULL,                 -- email or orcid,
  orcid       varchar(32)  NULL,                 -- at least one of the two
  level       varchar(16)  NOT NULL,
  token_hash  varchar(64)  NOT NULL UNIQUE,      -- sha256 of the token in the link
  invited_by  uuid         NULL REFERENCES users(id),
  accepted_at timestamptz  NULL,
  accepted_by uuid         NULL REFERENCES users(id),
  revoked_at  timestamptz  NULL,
  created_at  timestamptz  NOT NULL DEFAULT now(),
  CHECK (email IS NOT NULL OR orcid IS NOT NULL)
);

CREATE INDEX idx_dataset_invitations_email ON dataset_invitations (lower(email));
CREATE INDEX idx_dataset_invitations_orcid ON dataset_invitations (orcid);

CREATE TABLE dataset_review_links (
  id          uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id  uuid         NOT NULL REFERENCES datasets(id),
  token_hash  varchar(64)  NOT NULL UNIQUE,      -- sha256 of the token in the link
  label       varchar(256) NOT NULL,             -- e.g. "JGR Atmospheres, round 1"; owner-only
  revoked_at  timestamptz  NULL,
  created_by  uuid         NULL REFERENCES users(id),
  created_at  timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX idx_dataset_review_links_dataset ON dataset_review_links (dataset_id);

-- One row per page view. No IP address, no user agent: the reviewer is anonymous
-- to the author, and must stay anonymous to us.
CREATE TABLE dataset_review_link_views (
  id          bigserial   PRIMARY KEY,
  link_id     uuid        NOT NULL REFERENCES dataset_review_links(id),
  outcome     varchar(16) NOT NULL,              -- shown | redirected
  viewed_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_dataset_review_link_views_link
  ON dataset_review_link_views (link_id, viewed_at DESC);

-- Append-only audit trail. Rows are never updated or deleted.
CREATE TABLE dataset_embargo_events (
  id          bigserial   PRIMARY KEY,
  dataset_id  uuid        NOT NULL REFERENCES datasets(id),
  event_type  varchar(32) NOT NULL,   -- created | extended | ended_early | expired
                                      -- | metadata_mode_changed
                                      -- | permission_granted | permission_revoked
                                      -- | invitation_created | invitation_revoked
                                      -- | review_link_created | review_link_revoked
  old_value   jsonb       NULL,
  new_value   jsonb       NULL,
  changed_by  uuid        NULL REFERENCES users(id),
  note        text        NULL,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_dataset_embargo_events_dataset
  ON dataset_embargo_events (dataset_id, occurred_at DESC);
```

The email tables are in *Notifications*.

Invitation and review-link tokens are stored as hashes: both grant access on their own, so a leaked database dump must not be a leaked set of links. The consequence is that a link is shown once, when it is created; an author who loses it creates another and revokes the first.

The migration needs no manual cleanup. `migrations/env.py` excludes `casbin_rule` from autogenerate through `EXTERNALLY_MANAGED_TABLES`, so the generated revision contains only the tables above.

### Access rule

One decision point in `DatasetService`, so there is a single place to read when someone asks why a given person cannot download:

```python
def _can_access_data(self, user_id, dataset) -> bool:
    if not self._is_under_embargo(dataset):   # embargo_until null or past
        return True
    if dataset.owner_id == user_id:
        return True
    return self._permission_repo.exists(dataset.id, user_id)
```

Reviewer access does not pass through this function. A reviewer has no `user_id`, never reaches the files, and is served by routes of their own (see *Reviewer link*).

**An embargoed dataset is embargoed on every route**, not only where files are read. Each route of `/datasets/{id}/...` loads the dataset and checks the caller before doing anything else, so an editor in the tenancy cannot change, version or delete a dataset they cannot see:

| Action | Who may, during the embargo |
|---|---|
| Read the dataset, its versions, its files; download | owner, `read`, `write` |
| Update metadata, create or enable versions, upload files, reserve or change a DOI, manage sharing and reviewer links | owner, `write` |
| Extend the embargo | owner; or, when the owner's account is disabled, anyone with a permission |
| Delete the dataset or a version; set or end the embargo; switch its mode | owner |

Anyone else gets **404**, on every route alike, in either mode: a 403 on a write would confirm the dataset exists. The TUS upload hooks count as routes: an upload token is issued only to someone who may upload.

How the reads behave:

| Where | Behaviour |
|-------|-----------|
| Search (`repository/dataset.py`) | The clause goes into the SQL, not into Python, or the total count and pagination start lying. With `embargo_metadata_visible = false` the row is excluded for anyone outside the allowlist, **including other members of the tenancy**. |
| Dataset read | Open mode answers normally with the badge; only the file name list is withheld, since a file name leaks content. File count and total size stay. Hidden mode answers **404, not 403** — a 403 confirms the dataset exists. |
| Download (`service/dataset.py`) | Checked before the link is generated. The pre-signed URL TTL drops from 7 days to 1 hour while under embargo: a 7-day link outlives a revocation. |

File access is identical in both modes. The mode governs only who knows the dataset exists.

### Public snapshots during the embargo

A snapshot is the JSON published to object storage that backs the public pages `/datasets/{id}` and `/doi/datasets/{id}/versions/{version}`. It carries the full metadata, authors included, and is written by `publish_dataset_version`, by creating a DOI in manual mode, and by moving a DOI to `findable`.

**No snapshot is generated while a dataset is under embargo, in either mode.** The check sits in `_publish_dataset_snapshot`, the one function all three paths go through, so no caller can forget it:

- `publish_dataset_version` answers `400 embargo_active`.
- Creating a DOI in manual mode still reserves the DOI, as a draft, and skips the snapshot. Reserving the identifier is the point of the embargo; failing it would defeat the feature.
- Moving a DOI to `registered` is allowed; moving it to `findable` answers `400 embargo_active`. Promotion is the step taken after the embargo, never during it.

**The DOI during the embargo.** The author reserves the DOI and moves it to `registered` while the embargo lasts. DataCite treats that state as resolvable but not indexed: `doi.org` redirects to the DOI's URL, and the metadata do not appear in DataCite Commons or its public API. The identifier the author writes into the submitted article therefore works — and, with no snapshot, the page it lands on must not depend on one.

That page, `/doi/datasets/{id}/versions/{version}`, is answered live while the embargo lasts, in either mode, and shows only this: the dataset is under embargo until a date. No name, no metadata, no authors. It says less than the DOI itself, whose number is already public, and it is served by a gatekeeper route that reads `embargo_until` and nothing else. Once the embargo ends and a snapshot exists, the same URL shows the snapshot as it does today.

When the embargo ends nothing is published on its own. The author publishes the version, which writes the first snapshot, and then promotes the DOI; the end-of-embargo email walks them through both.

### Who sees what

| During the embargo | Metadata, open mode | Metadata, hidden mode | File list | Download |
|---|---|---|---|---|
| Dataset owner | yes | yes | yes | yes |
| Person authorised by the owner | yes | yes | yes | yes |
| Reviewer holding a valid link | redacted | redacted | no — count and size only | no |
| Another member of the same tenancy | badge only | does not know it exists | no | no |
| Administrator | same as a tenancy member | same as a tenancy member | no | no |
| External user, no account | nothing | nothing | no | no |

**The embargo binds administrators too.** Only the owner and the people the owner authorised reach the files. The Data Team gets access the way anyone else does: by the owner granting it. An administrator's role still passes Casbin on the route, and the service then refuses, because `_can_access_data` does not look at roles.

### Lifecycle

- **Start.** An embargo can be set only on a dataset that has never been published, that is, one with no snapshot. Once a public page with the authors has existed, an embargo cannot take it back. The same rule allows an embargo that ended without the dataset being published to be set again.
- **End date.** File access opens on its own once `embargo_until` passes; the check is at read time. The owner may end an embargo early; an administrator may not, since ending it early is the same as reaching past it.
- **Owner gone.** When the owner's account is disabled, anyone with a permission may extend the embargo, within the same 90-day cap, so that a dataset still under review does not open because its owner left. Ending it early, switching its mode and deleting the dataset stay with the owner alone. Extension by someone other than the owner is recorded in `dataset_embargo_events` like any other.
- **Duration.** An embargo is set for at most 90 days, and each extension reaches at most 90 days from the day it is made. Extensions are unlimited in number. There is no total ceiling, but no embargo drifts for years without someone deciding so again each quarter. The cap is a hard limit, not a warning.
- **DOI.** Reserved while embargoed and promoted to `findable` **manually by the author** once it ends. The end-of-embargo email says so explicitly (see *Notifications*).

The 90-day cap is validated in the service, on creation and on every extension alike, rather than by a `CHECK` constraint, because the comparison is against `now()`, which is not immutable:

```python
MAX_EMBARGO_PERIOD = timedelta(days=90)

def _validate_embargo_until(self, new_until):
    if new_until > datetime.now(timezone.utc) + MAX_EMBARGO_PERIOD:
        raise BadRequestException(errors=[ErrorDetails(code="embargo_too_long")])

# set_embargo and extend_embargo both call it, then persist and append a
# dataset_embargo_events row ('created' or 'extended')
```

### Audit

Every embargo transition appends a row to `dataset_embargo_events`: creation with the chosen end date, each extension with the previous and new dates, each switch between open and hidden mode, each early termination, each grant or revocation of access, and each invitation or reviewer link created or revoked.

This is what gives the 90-day cap its meaning. Without the trail an extension is a date nobody remembers choosing; with it, an extension is an act attributed to a person at a time.

### Granting access: the share dialog

Access is granted from a single dialog on the dataset page, modelled on the share window of Google Docs. It has three parts: an input to add people, the list of who already has access, and the reviewer links.

**Adding people.** One input field serves two purposes:

- **Typing a name or email** searches the users of the dataset's tenancy and suggests matches as the author types. Selecting one grants the permission immediately.
- **Typing a full email or ORCID** that matches nobody in the tenancy is recognised by its shape and offered as "invite \<value\>". An ORCID is accepted bare (`0000-0002-1825-0097`) or as a URL (`https://orcid.org/0000-0002-1825-0097`), and is rejected if its check digit (ISO 7064 mod 11-2) does not match — a mistyped ORCID would otherwise wait forever for a sign-up that never comes.

The search deliberately covers only the tenancy. Searching every user of the platform would let any author enumerate who has an account. Someone outside the tenancy is reached by typing their exact email or ORCID, which reveals nothing the author did not already know.

When the author submits an email or ORCID, the backend resolves it:

| Input | Matched against | If a user is found | If not |
|---|---|---|---|
| Email | `users.email`, case-insensitive | permission granted now, *Access granted* email | pending invitation, *Invitation* email |
| ORCID | `providers` where `name = 'orcid'`, bare form in `reference` | permission granted now, *Access granted* email | pending invitation, link to copy |

An invitation by ORCID alone has no address to send to, so the dialog shows its link for the author to send through their own channels. Like every token here, the link is shown once; an author who needs it again generates a new one, which invalidates the old.

**Accepting.** The link is the invitation. Whoever opens it, logged in with any account, accepts it: the permission goes to that account, whatever its email or ORCID. The token works once; after that it answers that the invitation was already accepted. Requiring the account to match the email or ORCID invited would refuse the common case of a researcher who signs up with another address or provider, and buys little, since the author already trusted the channel the link went through. What protects the author instead is visibility: the dialog shows which account accepted each invitation, and a permission that went to the wrong person is revoked like any other.

Matching still helps where it can: when someone logs in with an email or ORCID that a pending invitation names, that invitation is accepted for them without the link.

**Who has access** lists the owner, each person with a permission and their level, each pending invitation marked as such, and for each accepted invitation the account that accepted it. The author can change a level, revoke a permission, or revoke an invitation from the same list.

**Reviewer links** are listed in their own section of the dialog (see below).

New endpoints, each needing a route-level Casbin policy in the seed data:

| Route | Purpose |
|---|---|
| `GET /datasets/{id}/share/candidates?q=` | Tenancy users matching `q` (at least 2 characters, at most 10 results, already-authorised users excluded). Returns id, name and email only. |
| `GET /datasets/{id}/share` | Owner, permissions, pending invitations, reviewer links with their view statistics. |
| `POST /datasets/{id}/share` | Grant by user id, email or ORCID. Answers with a permission, or with an invitation and its one-time link. |
| `PUT /datasets/{id}/share/permissions/{user_id}` | Change level. |
| `DELETE /datasets/{id}/share/permissions/{user_id}` | Revoke. |
| `DELETE /datasets/{id}/share/invitations/{id}` | Revoke an invitation. |

Only the owner and users with `write` permission may call the mutating routes; that check is in the service, since Casbin cannot see the dataset.

### Reviewer link

A reviewer link lets the reviewers of a venue read the dataset's metadata without an account and without learning who produced it. The typical case is an article submitted to a journal or conference under double-blind review: the author creates a link, pastes it into the submission's data-availability statement, and revokes it if the review ends before the embargo does.

**Creating a link.** From the share dialog the author gives the link a label only they will see — the venue and round, say. A dataset may have several links at once, one per venue or round, each revoked independently. The link is shown once, when created.

**Lifetime.** A link has no expiry of its own: it lives exactly as long as the embargo. Extending the embargo extends every link with it, which is what the author wants when the review is the reason for the extension.

| State | `/review/{token}` answers |
|---|---|
| Embargo active, link not revoked | the redacted metadata page |
| Embargo ended, link not revoked | a redirect to the public page `/datasets/{id}` once the author has published a snapshot; until then, a page saying the embargo has ended and the dataset has not been published yet |
| Link revoked, or token unknown | **404**, like a dataset the caller cannot see |

The redirect ends the anonymity: the public page shows the authors. By then the embargo is over by the author's own decision, and a reviewer who still needs the anonymised view is served by an extension.

**What the reviewer gets.** A page at `/review/{token}` served by the webapp without login. It shows the dataset's metadata with authorship redacted, and the number and total size of its files. It shows no file names, offers no download, and exposes no route that would produce a pre-signed URL. The link works in both open and hidden mode.

**Redaction.** Fields that identify authorship stay in the response with their shape intact and their value replaced by `"[redacted]"`, so the reviewer sees that the dataset has three authors without seeing who they are:

| Field | Treatment |
|---|---|
| `data.owner`, `data.authors[]`, `data.contacts[]`, `data.colaborators[]` | every value redacted, list length kept |
| `data.institution`, `data.project` | redacted |
| `data.reference[]`, `data.references`, `data.citation.doi` | redacted — prior work and the DOI both resolve to the authors |
| `owner_id`, `tenancy`, `created_by` on versions and files | omitted from the review response |

Redaction happens in the gatekeeper, in one function, driven by an **allowlist** of fields that are known to be safe: a metadata field added in the future is redacted until someone decides otherwise. Doing it in the webapp would leave the authors in the JSON the browser receives.

Free text such as `description` and `additional_information` cannot be redacted automatically. The dialog says so when a link is created.

**Usage.** Each page view appends a row to `dataset_review_link_views`. The share dialog shows, per link, the number of views, the first and the last. The table records nothing that identifies the reviewer — no IP address, no user agent, no cookie — so the author learns *whether* the venue opened the dataset, never *who* did. The web server's access logs are outside this promise; they are not visible to DataMap users. Page views are the only event, since the page offers nothing else to do.

The same event feeds a Prometheus counter, following RFC 005:

| Metric | Type | Labels |
|---|---|---|
| `datamap_review_link_views_total` | counter | `tenancy`, `outcome` (`shown`, `redirected`, `not_found`) |
| `datamap_review_links_created_total` | counter | `tenancy` |

`dataset_id` and `link_id` are forbidden labels under RFC 005; per-link numbers come from the table, not from Prometheus. The *Business / Platform usage* dashboard gains a panel with both counters. `not_found` is the one to watch: a steady rate of unknown tokens is someone guessing.

**Routes.** The reviewer routes are called by the BFF with its client credentials and carry no user. The token is the authorization:

| Route | Purpose |
|---|---|
| `GET /review/{token}` | Redacted metadata, file count and size, or the post-embargo redirect. Records the view. |
| `POST /datasets/{id}/review-links` | Create a link (owner or `write`). |
| `DELETE /datasets/{id}/review-links/{link_id}` | Revoke a link. |

### Notifications

Email is sent in this phase. The mechanism is deliberately small: the gatekeeper renders and sends every message over SMTP, and a table of messages makes sending independent of the request that caused it and keeps a record of everything sent.

#### What is sent

| Notification | Recipient | Trigger |
|---|---|---|
| Invitation | invitee (by email) | pending invitation created |
| Access granted | the added user | permission granted to an existing account |
| Embargo ending in 15, 10, 5 and 1 days | owner and everyone with a permission | `embargo_until` minus each offset |
| Embargo ended | owner and everyone with a permission | `embargo_until` passed, or ended early by the owner |

Everyone with access is told, not only the owner, so that if the owner is gone the others know the embargo is ending and the dataset still has to be published. Each reminder says how many days remain and that the files will become available to the tenancy when the embargo ends. Every copy says the embargo can be extended by up to 90 days at a time. Those who can extend it — the owner, or everyone with a permission when the owner's account is disabled — get a button to the dataset page; the others' copy names the owner as the person who can. Pending invitations are not people with access yet, and get nothing.

The owner's *Embargo ended* message must say, in terms a researcher who has never heard of DataCite will understand:

- the files are now available on DataMap to the members of the dataset's tenancy;
- nothing has been made public: to publish the dataset page, the author publishes the version on the dataset page;
- its DOI is **registered but not findable**: it resolves, but it is not indexed by DataCite, so the dataset will not appear in DataCite search or in the services that harvest from it;
- making it findable is a manual step the author takes after publishing, and nothing will do it for them.

The same message appears as a persistent banner on the dataset page for the owner, from the day the embargo ends until the DOI is promoted. Email is a nudge; the banner is what cannot be missed.

#### Email delivery and audit, for the whole platform

Nothing in this subsection is specific to embargo. It is the platform's way of sending email, and the embargo notifications are its first users; any later feature that sends a message uses the same path and gets the same record.

Every message is a row, written before it is sent and kept after:

```sql
CREATE TABLE email_messages (
  id               uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  template         varchar(64)  NOT NULL,         -- embargo_reminder, invitation, ...
  template_version varchar(64)  NOT NULL,         -- commit the gatekeeper was built from
  recipient        varchar(256) NOT NULL,
  subject          text         NOT NULL,         -- as rendered
  body_text        text         NOT NULL,         -- plain-text part, as rendered
  context          jsonb        NOT NULL,         -- template inputs
  related_type     varchar(32)  NULL,             -- dataset, user, ...
  related_id       uuid         NULL,
  triggered_by     uuid         NULL REFERENCES users(id),  -- null when the system sent it
  dedup_key        varchar(256) NULL UNIQUE,      -- e.g. embargo_reminder:<dataset>:<until>:15
  status           varchar(16)  NOT NULL DEFAULT 'pending',  -- pending | sending | sent | failed
  attempts         int          NOT NULL DEFAULT 0,
  next_attempt_at  timestamptz  NOT NULL DEFAULT now(),
  smtp_message_id  varchar(256) NULL,             -- Message-ID header, to find it in the mailbox
  sent_at          timestamptz  NULL,
  created_at       timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX idx_email_messages_due     ON email_messages (next_attempt_at) WHERE status = 'pending';
CREATE INDEX idx_email_messages_related ON email_messages (related_type, related_id, created_at DESC);
CREATE INDEX idx_email_messages_recipient ON email_messages (lower(recipient), created_at DESC);

-- Append-only. One row per thing that happened to a message.
CREATE TABLE email_events (
  id          bigserial   PRIMARY KEY,
  message_id  uuid        NOT NULL REFERENCES email_messages(id),
  event       varchar(16) NOT NULL,   -- queued | attempt_failed | sent | failed
  detail      text        NULL,       -- SMTP reply code and text, or the exception
  occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_email_events_message ON email_events (message_id, occurred_at);
```

Together they answer the questions asked when something goes wrong: *when* (`created_at`, `sent_at`, and every attempt in `email_events`), *what* (`subject` and `body_text` exactly as rendered, plus the template and the build that rendered it), *to whom* (`recipient`), *why* (`related_type`/`related_id` and `triggered_by`), and *what the server said* (`detail`). `smtp_message_id` finds the same message in the sending mailbox.

**Secrets in messages.** An invitation carries a link whose token grants access, and the database stores only its hash (see *Database changes*). The template marks such fields as secret. They are held in `context` only until the message leaves: when it is marked `sent` or `failed`, each secret is replaced by a mask, in `context` and in `body_text` alike. The record still shows that a link was sent and to where, not the token. A failed invitation is therefore not resent as it was; the author creates a new one.

**Consulting the record.** Two administrator routes, behind the existing admin role in Casbin:

| Route | Purpose |
|---|---|
| `GET /admin/emails?recipient=&related_id=&template=&status=` | Messages, newest first, paginated. |
| `GET /admin/emails/{id}` | One message with its events. |

A message about an embargoed dataset contains the dataset's name and dates, never its data, so this view does not reach past the embargo.

**How a message moves.**

1. **Enqueue.** The service that causes a message — granting a permission, creating an invitation — inserts the `email_messages` row and its `queued` event after its own write has committed. The two are not one transaction, since each repository commits its own session: the rare failure between them leaves an access without its email, which is logged, and never an email announcing an access that does not exist. If the SMTP server is down, the grant still succeeds and the email goes out later.
2. **Reminders.** A due-reminder query finds datasets whose `embargo_until` minus an offset has passed and inserts the reminder with `dedup_key = embargo_reminder:<dataset_id>:<embargo_until>:<offset>`. The unique key makes the insert idempotent, and because `embargo_until` is part of it, an extension starts a fresh sequence instead of repeating the old one. A reminder whose moment has already passed when the embargo is created or extended — an embargo set for 3 days has no 15-day reminder — is not sent. The same pass, finding an embargo whose date has passed, appends its `expired` row to `dataset_embargo_events` and queues the *Embargo ended* messages; `dedup_key` makes both happen once.
3. **Dispatch.** Due rows are claimed with `SELECT ... FOR UPDATE SKIP LOCKED` and moved to `sending` in their own committed transaction before anything is sent, so two gatekeeper instances never pick the same row. Success records `sent`, the Message-ID and the time.

**No message is ever sent twice.** That is a requirement, and it has a price: when it is not known whether a message left, it is not retried. A retry happens only when the server certainly did not accept the message — the connection failed, or it answered an error before accepting the content. A row left in `sending` by a crash, or a send whose outcome is unknown (a timeout after the content was written), becomes `failed` with that reason, visible in the record, for someone to look at. Losing an email in that rare case is preferred to delivering it twice. Definite failures retry with backoff; after 5 attempts the row is `failed`.

Steps 2 and 3 run from `POST /internal/notifications/dispatch`, which the Archivist calls every 5 minutes from its existing APScheduler, through the gatekeeper client it already has. The Archivist triggers; the gatekeeper owns the data, the templates and the SMTP connection. A reminder can therefore be up to 5 minutes late, which does not matter at a granularity of days.

Logs carry `email_id`, `template` and `outcome` as fields, never the recipient or the body; the table is where those live.

Metrics, under RFC 005:

| Metric | Type | Labels |
|---|---|---|
| `datamap_emails_total` | counter | `template`, `outcome` (`sent`, `retried`, `failed`) |
| `datamap_email_pending` | gauge | — |

A growing `pending` gauge means the SMTP server is unreachable; any `failed` is an email a person did not get.

#### Configuration

Pydantic settings, in the encrypted environment for production:

| Variable | Meaning |
|---|---|
| `EMAIL_ENABLED` | `false` keeps messages pending without sending. Default `false`. |
| `EMAIL_FROM_NAME`, `EMAIL_FROM_ADDRESS` | Sender, as two values: the env file is read by `make`'s `include`, which keeps quotes literally, so a single `"DataMap <...>"` value would reach the app with its quotes |
| `EMAIL_REPLY_TO` | Where replies go, if not the sender |
| `SMTP_HOST`, `SMTP_PORT` | Server |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Credentials |
| `SMTP_STARTTLS` | `true` for port 587 |
| `PUBLIC_BASE_URL` | Origin used to build links in the messages |

**First sender: a Gmail account of the project's own.** The first deployment sends through `smtp.gmail.com:587` with STARTTLS, authenticated as `datamap.pcs@gmail.com` with an app password. No DNS change and no request to USP's IT is needed, and Gmail signs the messages itself, so they are not treated as spam.

- Gmail sends as the authenticated account, whatever `EMAIL_FROM_ADDRESS` says. The sender shows as `DataMap <datamap.pcs@gmail.com>`: the display name is free, the address is not. `EMAIL_REPLY_TO` can point replies at a person.
- A copy of every message lands in the account's *Sent* folder, which is a second audit trail at no cost, and `smtp_message_id` finds it there.
- The limit of about 500 messages a day is far above this feature's volume.
- The account belongs to the project, not to a person, and its password lives in the encrypted environment like any other credential. If it stops working, the `pending` gauge is what reveals it.

A USP sender was tried first and is not available without IT: USP's Workspace does not allow 2-step verification, so a `@usp.br` account cannot have an app password, and the institutional relay `smtp.usp.br` answers the production host but refuses it (`Sender address rejected: Access denied`). Moving to an institutional sender later changes only the environment. The ways to get one, from the least to the most bureaucratic:

- a transactional provider (Brevo, Resend, SES) sending as `@datamap.pcs.usp.br`, which needs SPF and DKIM records from whoever manages the `pcs.usp.br` zone;
- USP's IT allowing `143.107.102.162` on `smtp.usp.br`, or on the Google Workspace SMTP relay (`smtp-relay.gmail.com`, which the host already reaches);
- USP's IT enabling 2-step verification, or creating a service account such as `datamap@usp.br`.

Local development and the integration suite run [Mailpit](https://mailpit.axllent.org/) as a compose service. It accepts any message on port 1025 and exposes what it received over an HTTP API, so an integration test can assert that an invitation produced exactly one email, to the right address, containing a working link — and that its `email_messages` row has the token masked afterwards.

#### Templates

HTML and plain-text versions of every message, rendered with Jinja2 from `app/templates/email/`. One base layout carries the DataMap identity — logo, border, footer — and each notification fills in its content block. The layout follows a design made in Claude Design, adapted to what email clients render:

- table-based layout, 600 px wide, all CSS inline;
- the logo as a PNG served from `PUBLIC_BASE_URL`, not SVG, which Gmail does not display;
- system fonts only, and legible in the dark mode that mail clients force;
- every message has a plain-text part that says the same thing.

## Alternatives considered

### Per-resource Casbin policies

Insert rows such as `p, <user_uuid>, /datasets/<ds_uuid>/versions/.*/files/.*, GET` into `casbin_rule`.

Rejected. The matcher is `regexMatch` over the request path, so a UUID that is not escaped correctly becomes a wildcard. The policy set is reloaded every 5 seconds and would grow by several rows per authorised person per dataset. Answering "who has access to dataset X?" would mean parsing strings rather than querying a table.

### One tenancy per embargoed dataset

Reuse the existing tenancy mechanism by minting a tenancy per embargoed dataset.

Rejected. `datasets.tenancy` is a single-valued column, so a dataset cannot belong to both its real tenancy and an embargo tenancy. Users would have to switch tenancy in the selector to see the dataset, and the selector would become unreadable. It also overloads a concept that means "organisational group" with something that means "access exception".

### Reviewer accounts instead of a link

Create a guest account per reviewer and grant it a permission.

Rejected. The venue, not the author, knows who the reviewers are, and a double-blind reviewer must not have to reveal their identity to the author to get access. A link the author hands to the venue is the only shape that works in both directions.

### Sending email inside the request

Call SMTP directly from the service that grants the permission.

Rejected. A slow or unavailable SMTP server would slow or fail the grant, a retry would need its own mechanism, and reminders need a scheduled sender anyway. The messages table serves both with one path, and is the audit record besides.

### A dedicated permissions table

Accepted. It is queryable, auditable, testable, and independent of the request path. Casbin remains responsible for routes only.

## Out of scope

| Item | Reason |
|------|--------|
| Automatic DOI promotion | Deliberately manual. The known risk is that authors forget and leave the DOI in `registered` or `draft`; the mitigation is the end-of-embargo email and a persistent banner. Revisit after the first real embargo expires. |
| File access for reviewers | Reviewers read the metadata only. |
| Redacting free text | Names in a description cannot be found reliably. The author is warned when creating a reviewer link. |
| Email preferences and unsubscribe | Every message in this RFC is transactional and tied to an action the recipient's dataset depends on. |
| Linking metadata co-authors to real users | `Person` is `{ name: string }` inside the metadata JSONB, with no foreign key to `users`, and the `colaborators[].permission` field is not read by any authorization check. The allowlist therefore cannot be derived from the metadata and must be built explicitly. |
| Public browsable catalogue | Direct-link access satisfies the data policy. A public search would need a new anonymous endpoint and a new page. |

## Open questions

Resolved on 2026-09-30:

- Whether metadata stay public during an embargo: the author's choice, open or hidden mode, and in neither mode is there a public page.
- Whether snapshots may be generated during an embargo: no, in either mode.
- Whether the reviewer link is in scope: yes, metadata only, with authorship redacted and usage reported to the author.
- How long a reviewer link lives: as long as the embargo, then it redirects to the public page once one exists.
- Whether the 90-day extension cap is a limit or a reminder: a limit.
- Whether a manual DOI promotion is acceptable: yes, with the end-of-embargo email explaining that the DOI is registered but not findable.
- Whether email is sent in this phase: yes, over SMTP, with every message recorded, for the whole platform.
- The first SMTP sender: `datamap.pcs@gmail.com`, since a USP account cannot have an app password.
- Where the DOI points during the embargo: it is `registered`, which DataCite resolves but does not index, so it lands on a minimal embargo page.
- How long email records are kept: no limit for now.
- How long an embargo may be set for: 90 days at most, on creation as on each extension.
- Which routes the embargo covers: all of them, reads and writes.
- When an embargo can be set: only on a dataset that has never been published.
- What an invitation link proves: nothing about identity. It is single-use and accepted by whoever opens it; the author sees who did.
- Who is told the embargo is ending: everyone with access, so the dataset is still published if the owner is gone.
- Who may extend when the owner's account is disabled: anyone with a permission, within the same cap.
- Whether email may be duplicated: never. A message whose delivery is uncertain is marked failed rather than retried.
- Who reaches the files during an embargo: the owner and the people the owner authorised. Not the tenancy, not administrators, and not the Data Team unless the owner grants it.

Still open:

- **An institutional sender.** Not blocking: see *Configuration* for the ways
  to get one.
