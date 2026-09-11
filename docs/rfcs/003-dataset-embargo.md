# RFC 003: Dataset Embargo

| Status | On hold |
|--------|----------|
| Author | DataMap Team |
| Created | 2026-09-09 |
| Updated | 2026-09-11 |

> **On hold as of 2026-09-11.** The product manager wants to reshape the feature,
> and a meeting is pending. Nothing below has been built. Treat the decisions
> here as the state of the discussion before that meeting, not as settled: the
> access model in particular was derived from a reading of the data policy that
> is now up for revision.

## Summary

Researchers need a citable identifier for a dataset while the article that describes it is still under review, without exposing the data itself. This RFC proposes **embargo**: a per-dataset, per-person access restriction with an end date, under which the files are reachable only by the dataset owner and by people the owner names — not by other members of the same tenancy, and not by the public.

Two decisions shape the design:

1. **Visibility during the embargo is the author's choice**, not a platform-wide rule. In *open mode* the dataset has a public page carrying an embargo badge; in *hidden mode* the dataset does not appear at all for anyone outside the allowlist. The choice is made when the dataset is created, so it never surfaces before the author decides, and can be changed later.
2. **The embargo state is derived from a date**, not stored as a flag, and is evaluated at read time. There is no scheduled job.

## Motivation

### Problem statement

Today the platform has no way to express "this dataset exists, is citable, but its data is not available yet". Access is decided by tenancy: whoever belongs to the tenancy sees the dataset and can download from it. That is too coarse for the AmazonFace data policy, which requires that data under embargo reach only the responsible researcher, the people they authorise, and the Data Team.

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
- Record every embargo decision, so the data policy has evidence rather than recollection.

### Non-goals

- Anonymous reviewer links (see *Out of scope*).
- Email notification of any kind.
- Automatic promotion of the DOI when the embargo ends.

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
  token       varchar(64)  NOT NULL UNIQUE,
  invited_by  uuid         NULL REFERENCES users(id),
  accepted_at timestamptz  NULL,
  created_at  timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX idx_dataset_invitations_email ON dataset_invitations (lower(email));

-- Append-only audit trail. Rows are never updated or deleted.
CREATE TABLE dataset_embargo_events (
  id          bigserial   PRIMARY KEY,
  dataset_id  uuid        NOT NULL REFERENCES datasets(id),
  event_type  varchar(32) NOT NULL,   -- created | extended | ended_early | expired
                                      -- | metadata_mode_changed
                                      -- | permission_granted | permission_revoked
  old_value   jsonb       NULL,
  new_value   jsonb       NULL,
  changed_by  uuid        NULL REFERENCES users(id),
  note        text        NULL,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_dataset_embargo_events_dataset
  ON dataset_embargo_events (dataset_id, occurred_at DESC);
```

> When generating the migration, check it for unintended `casbin_rule` operations and remove them from both `upgrade()` and `downgrade()`, as the project guidelines require.

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

Applied in three places:

| Where | Behaviour |
|-------|-----------|
| Search (`repository/dataset.py`) | The clause goes into the SQL, not into Python, or the total count and pagination start lying. With `embargo_metadata_visible = false` the row is excluded for anyone outside the allowlist, **including other members of the tenancy**. |
| Dataset read | Open mode answers normally with the badge; only the file name list is withheld, since a file name leaks content. File count and total size stay. Hidden mode answers **404, not 403** — a 403 confirms the dataset exists. |
| Download (`service/dataset.py`) | Checked before the link is generated. The pre-signed URL TTL drops from 7 days to 1 hour while under embargo: a 7-day link outlives a revocation. |

File access is identical in both modes. The mode governs only who knows the dataset exists.

### Who sees what

| During the embargo | Metadata, open mode | Metadata, hidden mode | File list | Download |
|---|---|---|---|---|
| Dataset owner | yes | yes | yes | yes |
| Person authorised by the owner | yes | yes | yes | yes |
| Another member of the same tenancy | badge only | does not know it exists | no | no |
| External user, no account | badge only | does not know it exists | no | no |

### Lifecycle

- **End date.** File access opens on its own once `embargo_until` passes; the check is at read time. An administrator may end an embargo early.
- **Extension.** Unlimited in number, capped at 90 days per extension. There is no total ceiling, but no embargo drifts for years without someone deciding so again each quarter.
- **DOI.** Reserved while embargoed and promoted to `findable` **manually by the author** once it ends. See *Out of scope*.

The 90-day cap is validated in the service rather than by a `CHECK` constraint, because the comparison is against `now()`, which is not immutable:

```python
MAX_EMBARGO_EXTENSION = timedelta(days=90)

def extend_embargo(self, dataset_id, new_until, user_id):
    if new_until > datetime.now(timezone.utc) + MAX_EMBARGO_EXTENSION:
        raise BadRequestException(errors=[ErrorDetails(code="embargo_extension_too_long")])
    # ... persist, then append a dataset_embargo_events row with event_type='extended'
```

### Audit

Every embargo transition appends a row to `dataset_embargo_events`: creation with the chosen end date, each extension with the previous and new dates, each switch between open and hidden mode, each early termination, and each grant or revocation of access.

This is what gives the 90-day cap its meaning. Without the trail an extension is a date nobody remembers choosing; with it, an extension is an act attributed to a person at a time.

### Granting access

The author adds someone by email or ORCID. If that person already has an account the permission takes effect immediately. If not, a pending invitation is stored and the interface produces a link the author sends through their own channels — the same email thread where the article is already being discussed. When the person signs up, the invitation is matched by email or ORCID and becomes a permission.

The workaround exists because the platform has no email infrastructure of any kind. When notification infrastructure arrives, only the delivery changes; the data model is already in place.

## Alternatives considered

### Per-resource Casbin policies

Insert rows such as `p, <user_uuid>, /datasets/<ds_uuid>/versions/.*/files/.*, GET` into `casbin_rule`.

Rejected. The matcher is `regexMatch` over the request path, so a UUID that is not escaped correctly becomes a wildcard. The policy set is reloaded every 5 seconds and would grow by several rows per authorised person per dataset. Answering "who has access to dataset X?" would mean parsing strings rather than querying a table.

### One tenancy per embargoed dataset

Reuse the existing tenancy mechanism by minting a tenancy per embargoed dataset.

Rejected. `datasets.tenancy` is a single-valued column, so a dataset cannot belong to both its real tenancy and an embargo tenancy. Users would have to switch tenancy in the selector to see the dataset, and the selector would become unreadable. It also overloads a concept that means "organisational group" with something that means "access exception".

### A dedicated permissions table

Accepted. It is queryable, auditable, testable, and independent of the request path. Casbin remains responsible for routes only.

## Out of scope

| Item | Reason |
|------|--------|
| Automatic DOI promotion | Deliberately manual. The known risk is that authors forget and leave the DOI in `registered` or `draft`; the mitigation is a persistent banner after the embargo ends. Revisit after the first real embargo expires. |
| Email delivery | No SMTP, provider, template or job exists in any service. Invitations work by copyable link and reminders by in-app banner. |
| Anonymous reviewer link | Needs a public token, expiry and anonymisation — a feature of its own. The invitation model here is its natural foundation. |
| Linking metadata co-authors to real users | `Person` is `{ name: string }` inside the metadata JSONB, with no foreign key to `users`, and the `colaborators[].permission` field is not read by any authorization check. The allowlist therefore cannot be derived from the metadata and must be built explicitly. |
| Public browsable catalogue | Direct-link access satisfies the data policy. A public search would need a new anonymous endpoint and a new page. |

## Open questions

The one that was open — whether metadata stay public during an embargo — was
resolved by making it the author's choice rather than a platform-wide rule.

Everything else is now pending the product review. Worth putting on the agenda,
because each would change the design here:

- Does the reviewer link come back into scope? It was cut, and the invitation
  model in §"Granting access" is its natural foundation if it returns.
- Does the 90-day extension cap survive contact with how researchers actually
  work, or does it become a reminder rather than a limit?
- Is a manual DOI promotion still acceptable, given the expectation that authors
  will leave identifiers in `registered` indefinitely?
