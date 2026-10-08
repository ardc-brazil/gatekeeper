# RFC 010: Personal Access Tokens

| Status | Draft |
|--------|-------|
| Author | DataMap Team |
| Created | 2026-10-04 |
| Updated | 2026-10-04 |

## Summary

The `datamap` library (RFC 007) runs inside a notebook session with a token
the gatekeeper minted for that session. Outside a session — a Colab notebook,
a laptop, a script on a cluster — there is no credential a person can hold,
because the gatekeeper authenticates applications, not people. This RFC adds
**personal access tokens**: a read-only credential a signed-in user creates on
their profile page, pastes once into `datamap.login()`, and revokes when they
want. With it the same library lists a dataset and downloads its files to
wherever the code runs.

Three decisions:

1. **Same library, different credential.** The SDK's mode is decided by where
   the token came from, not by a second package. Inside a session the files
   are on `/data`; outside, `ds.download()` puts them in a workspace directory
   and the rest of the API is identical.
2. **A download needs an account and a tenancy, public dataset or not.** The
   token carries no rights of its own: every request is authorized as the user
   who owns it, with that user's tenancies and permissions at the time of the
   call. A dataset the user cannot open on the site cannot be opened with the
   token either, and a public dataset is not reachable without an account.
   Since RFC 009 every account belongs to the public tenancy, so in practice
   the requirement is an account; the rule is stated in full because it is
   what the data policy asks for.
3. **Paste, not a browser flow.** The token is shown once, at creation, and
   pasted into the SDK — what Zenodo, Kaggle and Hugging Face do. A
   device-code flow is nicer and is not worth its two extra endpoints yet.

## Motivation

The first thing a researcher asked for, when shown the notebook first cell,
was to run it in Colab. Colab has GPUs, no seat limit and a habit; DataMap's
sessions have the data on disk and a 20 GB ceiling. Both are right for
different work, and the only thing standing between them is a credential.

Today the gatekeeper has two ways in: a client key, issued to applications
(webapp, archivist, hub) and trusted to assert `X-User-Id`; and, from RFC 007,
a session token bound to one notebook session for at most twelve hours.
Neither can be handed to a person: the first impersonates anyone, the second
dies with the session.

### Goals

- A read-only credential a user creates, sees once, and revokes.
- The SDK works unchanged outside a session once the token is set.
- Every token request is authorized exactly as the site would authorize that
  user, including tenancy membership, sharing and embargo.
- A leaked token is bounded: read only, expiring, revocable, visible in the
  profile with when it was last used.

### Non-goals

- Anonymous access to public datasets. Decided against: downloads require an
  account and a tenancy, as on the site.
- Write access (uploads, saving notebooks) through a token.
- OAuth, device-code or browser-based login from the SDK.
- Service accounts for other institutions' pipelines. A person's token used by
  a script is allowed; a token without a person behind it is not.

## Design

### The token

`dmp_<lookup>.<secret>`: `lookup` is 12 characters from `secrets.token_urlsafe`
and indexes the row; `secret` is 32 random bytes, base64url. The prefix lets
the bearer resolver tell a personal token from a session JWT without parsing,
and lets secret scanners recognise it.

```sql
CREATE TABLE user_tokens (
  id           uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name         varchar(128) NOT NULL,
  lookup       varchar(16)  NOT NULL UNIQUE,
  secret_hash  varchar(256) NOT NULL,
  scope        varchar(16)  NOT NULL,            -- read
  created_at   timestamptz  NOT NULL DEFAULT now(),
  expires_at   timestamptz  NOT NULL,
  last_used_at timestamptz  NULL,
  revoked_at   timestamptz  NULL
);
CREATE INDEX idx_user_tokens_user ON user_tokens (user_id);
```

`secret_hash` uses `hash_secret` / `verify_secret` from `app/service/secret.py`
with `AUTH_CLIENT_SECRET_PEPPER`, the same scheme the client secrets use, so
there is nothing new to rotate or back up. The plaintext is returned once, by
the creating request, and never stored.

Lifetime: 90 days by default, one year at most, chosen at creation. A user
holds at most 10 unrevoked tokens. `last_used_at` is written at most once a
minute per token, so a tight loop of requests does not become a tight loop of
writes.

### Routes

User routes, authenticated as every other (`X-Api-Key`, `X-User-Id`), so only
the signed-in person manages their tokens:

| Route | Does |
|---|---|
| `GET /users/me/tokens` | the caller's tokens: `id`, `name`, `scope`, `created_at`, `expires_at`, `last_used_at`, `revoked_at`; never the secret |
| `POST /users/me/tokens` | `{"name", "expires_in_days"?}` → 201 with the full token, once; 400 `too_many_tokens` at ten; 400 `expiry_too_long` past a year |
| `DELETE /users/me/tokens/{id}` | sets `revoked_at`; 204; a revoked token fails on the next request |

Bearer routes, reachable with a personal token: `GET /users/me` (who am I),
`GET /datasets/` (search), `GET /datasets/{id}`, `GET /datasets/{id}/versions/{v}`,
`GET /datasets/{id}/versions/{v}/files/{file_id}` (the pre-signed download
URL). Nothing else.

### Authentication

RFC 007's bearer path becomes a resolver with two branches:

```
Authorization: Bearer dmp_...   → user_tokens by lookup; verify_secret; not revoked;
                                  not expired → subject personal_token, user = row.user_id
Authorization: Bearer <jwt>     → session token, as RFC 007
```

The resolver sets `request.state.session_claims` with the user id and the
user's **current** tenancies (read from the user at that moment, not stored
in the token), so `parse_user_header`, `parse_tenancy_header` and every
service downstream behave exactly as for a webapp request on behalf of that
user. Casbin enforces with the subject `personal_token`, which has policies
for the five bearer routes above and nothing else.

Policy rows, inserted by the migration as RFC 007's are:

```
p, personal_token, /api/v1/users/me$, GET, allow
p, personal_token, /api/v1/datasets/?$, GET, allow
p, personal_token, /api/v1/datasets/[0-9a-f-]{36}$, GET, allow
p, personal_token, /api/v1/datasets/[0-9a-f-]{36}/versions/[^/]+$, GET, allow
p, personal_token, /api/v1/datasets/[0-9a-f-]{36}/versions/[^/]+/files/[0-9a-f-]{36}$, GET, allow
```

A failed token is counted as `datamap_auth_failures_total{kind="personal",
reason}` with reasons `invalid_token`, `expired`, `revoked`. Requests made
with a token carry the `client="personal_token"` label on the HTTP metrics,
so their share of the traffic is one query.

### What a token can and cannot do

| | Site, signed in | Session token | Personal token |
|---|---|---|---|
| Read a dataset the user may see | yes | yes | yes |
| Download its files | yes | yes (manifest) | yes (pre-signed URL) |
| A dataset outside every tenancy of the user, not shared | no | no | no |
| Under embargo without access | no | no | no |
| Search | yes | no | yes |
| Upload, edit, share, save a notebook | yes | no | no |
| Manage tokens | yes | no | no |
| Lifetime | session | 12 h | up to a year, revocable |

Pre-signed URLs keep their TTL (one hour under embargo, seven days otherwise,
RFC 003). A token that downloads an embargoed dataset the user has access to
gets the one-hour link, as the site does.

### Profile page

A section *API tokens* in `/app/profile`: the list with name, created,
expires, last used; *New token* with name and expiry; the created token shown
once in a copy field with the sentence "Copy it now; it will not be shown
again"; *Revoke* per row with a confirmation. The section follows the Share
dialog's row style. Strings go through next-intl (RFC 006).

### SDK

Credential resolution in `datamap.open()`, in order: explicit `token=` and
`api_url=`; `DATAMAP_SESSION_TOKEN` (inside a session); `DATAMAP_TOKEN` in
the environment; `~/.datamap/credentials` written by `datamap.login()`
(mode `0600`, `api_url` and `token`). No credential → `NotInSession` with the
sentence that names `datamap.login()`.

```python
datamap.login()                                   # prompts with getpass; saves the file
datamap.login(token="dmp_...", api_url="https://datamap.pcs.usp.br/api/v1")
ds = datamap.open("3f9c1e", version="2")
ds.download()                                     # every file → ./datamap/3f9c1e/2/
ds.download("t3_smps_*.nc", to="/content/data")  # a pattern, elsewhere
ds.open_mfdataset("*.nc")                         # local now, as in a session
datamap.search("aerosol T3")                      # GET /datasets/?full_text=
datamap.whoami()                                  # GET /users/me
```

`download()` asks the gatekeeper for each file's pre-signed URL and streams
it to `DATAMAP_WORKSPACE` (default `./datamap`) under `{dataset_id}/{version}/`,
skipping a file that is already there with the same size. After it, `ds.files`
marks those files `local` with their paths, so the rest of the API does not
know which mode it is in. Inside a session `download()` works too, into
`/outputs/datamap/` — which is how a file outside the mounted selection can
still be fetched, counted against the 2 GB quota.

The R package gets `datamap::login()` and `ds$download()` with the same
behaviour.

### Colab

The dataset page gets *Use elsewhere* in the download menu: a dialog with the
three cells (`pip install datamap`, `datamap.login()`, `datamap.open(...)` +
`download()`) filled in for that dataset and version, with a copy button. In
Colab the token goes in its *Secrets* panel as `DATAMAP_TOKEN`, which the SDK
reads from the environment after `from google.colab import userdata;
os.environ["DATAMAP_TOKEN"] = userdata.get("DATAMAP_TOKEN")` — the dialog
shows that line too. A generated notebook file would be nicer; it needs a
place to host it that Colab can open, and the three cells are enough.

## Alternatives considered

- **Device-code login** (`datamap login` prints a URL and a code; the user
  approves in the browser; the SDK polls). Better for people who will never
  find the profile page. Costs an approval page, a pending-authorisation
  table and a polling endpoint. Deferred until the paste flow has been seen
  to fail someone.
- **Long-lived session tokens.** Reusing RFC 007's JWT with a long expiry
  would avoid a table, and lose revocation and the "last used" view, which
  are the two things a leaked credential needs.
- **Anonymous download of public datasets.** Would make the Colab story
  one cell shorter. Rejected by decision: downloads require an account and a
  tenancy, public or not, so usage is attributable and the data policy holds.
- **A separate "external" SDK.** Two packages, two docs, two first cells that
  look alike and diverge. The only real difference is where the credential
  comes from and where the files land, which is one function each.

## Rollout

The gatekeeper and SDK halves ship first: a token can be created through
Swagger before the profile page exists, which is how the first external users
(the Data Team) try it. The profile section follows. No gate: anyone with an
account can create a token, because a token can do nothing the account cannot.

## Out of scope

- Scopes beyond `read`. The column exists so `write` can be added without a
  migration, and the Casbin role for it would be a separate decision.
- Rate limiting per token. The platform has none per client either; if a
  script becomes a problem, the token's `last_used_at` says whose, and revoking
  it is the limit.
- Notifying the user by email when a token is created or used from somewhere
  new.

## Open questions

- **Whether to show the token's last-used origin** (an IP or a user agent).
  Useful to spot a leak, and a new column the privacy policy would have to
  mention. Not in the first version.
- **Whether `datamap.search()` should exist in the session mode too.** The
  session subject cannot search today, on purpose; a notebook that lists the
  catalogue is a reasonable ask and a one-line Casbin change.
