# RFC 011: Scoped API clients and user identity assertion

| Status | Draft |
|--------|-------|
| Author | DataMap Team |
| Created | 2026-10-05 |
| Updated | 2026-10-05 |

## Summary

The gatekeeper authenticates *clients* and then believes whatever user they name.
A client proves itself with `X-Api-Key`/`X-Api-Secret`; the user is a bare
`X-User-Id` header that nothing checks. Casbin then authorizes that user's
roles. Any holder of any client secret can therefore act as any user, admins
included, on every route, and the gatekeeper is reachable from the internet.

This RFC closes that hole in two layers:

1. **Every client gets a scope.** A client is a Casbin subject,
   `client:{key}`, with route policies of its own. The archivist reaches
   `/internal/*` and nothing else; the BFF reaches everything except
   `/internal/*` and `/tus/*`. A client outside its scope is refused before
   any user is looked at.
2. **A user is asserted, not named.** A client flagged `acts_as_users` sends a
   short-lived ES256 JWT, `X-User-Assertion`, signed with a private key only
   it holds, carrying `sub`, `aud`, `iat`, `exp`, `jti` and the method and path
   of the request it belongs to. The gatekeeper verifies it against the
   client's registered public key and derives the user from it. `X-User-Id` is
   no longer trusted.
3. **Only the BFF acts as users.** The archivist, the zipper and any future
   machine client cannot assert anyone, whatever secrets leak.
4. **The gatekeeper stores public keys only.** A leaked database or gatekeeper
   environment cannot mint an assertion, and adding a key is a row, not a
   deploy of two repositories.
5. **Rollout is observe, then enforce.** A setting moves the gatekeeper from
   `observe` (accept bare `X-User-Id`, count it) to `enforce` (refuse it). We
   switch when the counter has been at zero for a week.
6. **The residual risk is stated, not hidden.** The BFF mints assertions for
   whoever it believes is signed in, so a compromised BFF host still acts as
   any user. What changes is that every *other* secret — the archivist's, the
   zipper's, a test client's, one pasted into a log — stops being a skeleton
   key.

RFC 009's PR A makes `POST /users` ignore the `roles` in its payload, which
removes the most direct escalation (create yourself as `admin`). That is the
narrow fix. This RFC is the general one.

## Motivation

### Problem statement

A request reaches a user route through three checks, and only the first two
verify anything:

1. `authenticate` (`app/controller/interceptor/authentication.py:17-32`) calls
   `AuthService.authorize_client` (`app/service/auth.py:24-51`), which checks the
   key and the peppered secret hash and returns the client. It records the
   client's name for metrics and **discards everything else**: no scope, no
   capability, no link to the user.
2. `parse_user_header` (`app/controller/interceptor/user_parser.py:9-13`) reads
   `X-User-Id` and returns it as a UUID. It is not signed, not bound to the
   client and not checked against anything.
3. `authorize` (`app/controller/interceptor/authorization.py:20-33`) asks Casbin
   whether *that* user may use the path and verb.

So `X-Api-Key` + `X-Api-Secret` of *any* enabled client, plus the UUID of an
admin, is admin. The gatekeeper is published at
`https://datamap.pcs.usp.br/api/v1` (`infrastructure/nginx/datamap.conf:38-46`),
so the attacker does not need to be inside the network — only to hold one
secret. User UUIDs are not secret: they appear in the access log
(`app/setup.py:193`), in URLs the webapp builds, and one client-only call
(`GET /users/providers/orcid/{orcid}`, `app/controller/v1/user/user.py:211`)
turns a public ORCID iD into a user record with its roles.

Some routes do not even need the user to be an admin:

- `POST /users/{user_id}/invitations/claim`
  (`app/controller/v1/invitation/invitation.py:41-50`) has only `authenticate`
  and takes the user from the path: any client can claim any user's pending
  invitations for them.
- `POST /invitations/accept` (`invitation.py:30-38`) accepts a token as whoever
  `X-User-Id` names.
- `POST /users` (`user.py:84-98`) is client-only and, on `main` at 1ec58f7,
  still forwards `roles=payload.roles` (`user.py:95`). RFC 009 PR A drops it.

### What exists today

#### Who holds a client secret

| Holder | Where its secret lives | Routes it calls | Acts as a user? |
|---|---|---|---|
| **Webapp BFF** | `DATAMAP_API_KEY`/`DATAMAP_API_SECRET` in `datamap-webapp/secrets/production/frontend.env.sops`; one axios instance sends them on every call (`datamap-webapp/lib/rpc.ts:6-18`) | Everything a screen needs: `/datasets/**`, `/users/**`, `/tenancies`, `/invitations/**`, `/anonymous/{token}`, `/auth/*`, `/datasets/{id}/embargo-status` | **Yes**, on most calls: `buildHeaders` sets `X-User-Id` from the NextAuth session (`lib/rpc.ts:77-86`); three calls set it by hand (`lib/account.ts:34`, `lib/share.ts:70`, `lib/share.ts:75`). **As itself** for sign-in and public pages: `/auth/*` (`lib/account.ts:3-50`), `POST /users` (`lib/users.ts:109`), `GET /users/providers/...` (`lib/users.ts:127`), invitation preview, anonymous pages, embargo status |
| **Archivist** | `GATEKEEPER_API_KEY`/`GATEKEEPER_API_SECRET` in `archivist/secrets/production/archivist.env.sops`; `archivist/app/client/gatekeeper_client.py:17-21` | `GET /internal/datasets/collocation/pending` (`:31`), `GET /internal/datasets/{id}/files` (`:56`), `PUT /internal/datasets/{id}/files/{file_id}` (`:80`), `PUT /internal/datasets/{id}/collocation-status` (`:104-106`), `POST /internal/notifications/dispatch` (`:129`) | **Never.** No call sends `X-User-Id` |
| **Zipper** | `gatekeeper.api_key`/`api_secret` in the tracked `zipper/local_config.yml` and `zipper/staging_config.yml`; `zipper/app/gateways/gatekeeper.py:12-16` | One callback, `POST /v1/internal/datasets/{id}/versions/{v}/files/zip/{id}` (`gatekeeper.py:19`), **which does not exist in the gatekeeper**. The zipper is not deployed (`infrastructure/prometheus/prometheus.yml:30`) | **Never** |
| **TUSd** | **None.** It holds no client secret | `POST /tus/hooks`, guarded by `authorize_tus` only (`app/controller/v1/tus/tus.py:16`), with no `authenticate` | The user comes from the hook payload; see below |
| **Integration test client** | Seeded by `tests/integration/fixtures/seed_clients.sql:38-50`; defaults in `tests/integration/config.py:13-20` | Every route, as the seeded user, which holds `admin` and `clients_admin` (`seed_clients.sql:75-76`) | **Yes**, `X-User-Id` from config (`tests/integration/fixtures/auth.py:11-19`) |

Whether the BFF and the archivist are two client rows in production or share
one is not visible from the repositories; see *Open questions*.

#### Client records

`clients(key UUID PK, secret, name, is_enabled, created_at, updated_at)`
(`app/model/db/client.py:10-28`). The secret is stored as
`hmac-sha256$` + HMAC-SHA256 under `AUTH_CLIENT_SECRET_PEPPER`
(`app/service/secret.py:39-49`); legacy bcrypt hashes are upgraded on use
(`auth.py:48-49`). Clients are created and rotated through `/clients`
(`app/controller/v1/client/client.py:23-102`), which is authorized by the
*user's* Casbin roles (`clients_*`, `seed_clients.sql:33-35`) — so a client is
created by a user acting through another client. **A client has no scope, no
flag and no key material other than its secret.** The secret is stored as a
one-way hash, so the gatekeeper could not use it as an HMAC key for an
assertion even if we wanted to.

#### Signed user tokens the platform already has

- **NextAuth session.** A JWT encrypted with `NEXTAUTH_SECRET`, held in the
  browser's cookie and read by the BFF (`lib/appLocalContext.ts:35-44`), which
  requires `uid` and the current `TOKEN_VERSION` (`lib/middlewareChain.ts:24-31`).
  The gatekeeper never sees it.
- **`TOKEN_SECRET`** appears in `.env.local.template:6` but no code reads it and
  production does not set it. It is not a mechanism we can build on.
- **The upload token** is the one user-bound token the gatekeeper verifies today.
  `pages/api/auth/token.ts:23-34` signs HS256 with
  `AUTH_FILE_UPLOAD_TOKEN_SECRET`, claims `iss=datamap_bff`, `aud=file_upload`,
  `sub=<user>`, `file=<dataset>`, valid **one day**, and hands it to the browser,
  which sends it to tusd with `X-User-Id` (`components/base/UppyUploader.tsx:76-77`).
  tusd forwards the headers in the hook payload. `authorize_tus`
  (`authorization.py:68-98`) verifies the signature and audience
  (`auth.py:61-81`), requires `sub == X-User-Id` and `file == dataset_id`, then
  runs Casbin for that user. It is the precedent this RFC follows, with three
  differences: the assertion is per client, per request and lives seconds, not
  a day; and it is asymmetric.

#### Machine-only routes

| Route | Guard today | Caller |
|---|---|---|
| `GET /internal/datasets/collocation/pending` | `authenticate` (`app/controller/v1/internal/dataset_collocation.py:24-27`) | archivist |
| `GET /internal/datasets/{id}/files` | `authenticate` (`:59-62`) | archivist |
| `PUT /internal/datasets/{id}/files/{file_id}` | `authenticate` (`:93-96`) | archivist |
| `PUT /internal/datasets/{id}/collocation-status` | `authenticate` (`:114-117`) | archivist |
| `POST /internal/notifications/dispatch` | `authenticate` (`app/controller/v1/internal/notification.py:23-27`) | archivist |
| `POST /tus/hooks` | `authorize_tus`, no client | tusd |

Today the BFF secret reaches all five `/internal` routes: it can rewrite any
file's `storage_path` or trigger an email dispatch.

### Goals

- A client secret, alone, cannot act as any user.
- A machine client reaches only the routes it exists for.
- The user the gatekeeper authorizes is the user the BFF's session holds, and
  the gatekeeper can tell when it is not.
- No downtime and no flag day across four repositories.

### Non-goals

- Protecting against a compromised BFF host. It holds the private key and the
  session secret; it can be anyone. See *Residual risk*.
- Replacing NextAuth sessions with gatekeeper-issued sessions (see
  *Alternatives considered*).
- Changing how users authenticate (RFC 008).
- The admin screen for clients (RFC 010).
- Hardening the TUS hook path beyond what is noted in *Out of scope*.

## Options

### Option A: per-client route scopes

Clients become Casbin subjects with policies of their own; `authenticate`
enforces them.

- **Gains:** the archivist's and zipper's secrets stop reaching user routes and
  each other's routes; the BFF's secret stops reaching `/internal`. Cheap: one
  migration of policy rows, one enforce call, no change in any client.
- **Leaves:** the BFF secret still acts as any user, because the BFF genuinely
  needs every user route. The most valuable secret is exactly as dangerous as
  today. It also does nothing for the test client, which is the BFF's shape.

### Option B: cryptographic user assertion

The BFF signs a short-lived JWT per request; the gatekeeper derives the user
from it and stops reading `X-User-Id`.

- **Gains:** the client secret alone no longer names a user; an assertion seen
  in a log or on the wire is good for one method and path for a minute; only
  clients registered to act as users can do so.
- **Leaves:** a machine secret still reaches every route that does *not* need a
  user — `/internal/*`, `POST /users`, `/users/providers/...`, the invitation
  claim — which is a lot of what matters.

### Option C: both (recommended)

Scopes decide *which routes* a client may call; the assertion decides *who* the
user is. Each covers what the other leaves:

| Secret leaked | Today | A only | B only | **C** |
|---|---|---|---|---|
| archivist | any user, any route | `/internal/*` only | any client-only route, `/internal/*` | **`/internal/*` only** |
| zipper | any user, any route | its callback only | any client-only route | **its callback only** |
| BFF secret, without its signing key | any user, any route | any user, every non-internal route | client-only routes | **client-only, non-internal routes** |
| BFF secret *and* signing key (host compromise) | any user | any user | any user | **any user** |

The last row is the honest one: C does not help there, and nothing short of
moving session issuance into the gatekeeper does.

## Technical design

### Database changes

`clients` gains one column:

| Column | Type | Meaning |
|---|---|---|
| `acts_as_users` | `Boolean`, not null, default `false` | may send `X-User-Assertion` |

A new table holds each client's verification keys:

```
client_assertion_keys
  kid          String(64) primary key   -- chosen by the operator, e.g. "bff-2026-10"
  client_key   UUID, FK clients.key ON DELETE CASCADE
  public_key   Text                     -- PEM, EC P-256
  created_at   DateTime(tz)
  revoked_at   DateTime(tz), nullable   -- null means usable
```

At most a handful of rows; a client has two only while a rotation is in
progress. The private key never reaches the gatekeeper.

### Client scopes

Clients become Casbin subjects named `client:{key}`. User subjects are UUIDs —
`parse_user_header` rejects anything else — so the two namespaces cannot meet,
and the prefix makes a client row in `casbin_rule` obvious to a reader.

Scope roles, seeded by the migration:

| Role | Policy (`v1`, `v2`) | Holders |
|---|---|---|
| `scope_internal` | `^/api/v1/internal/` , `.*` | archivist, zipper |
| `scope_bff` | `^/api/v1/(?!internal/\|tus/)` , `.*` | BFF, integration test client |

The matcher's `regexMatch` (`app/resources/casbin_model.conf`) is pycasbin's
`re.match`: anchored at the start, open at the end. The patterns are prefixes,
so that is what we want; the explicit `^` is for the reader. The negative
lookahead in `scope_bff` is what keeps it from being `/*`. No client is ever
granted `admin`, whose `/*` would cover everything; a test asserts it.

`authenticate` enforces the scope right after the secret check:

```
enforce("client:{key}", request.url.path, request.method)  → else 403 client_out_of_scope
```

The policy reloads every five seconds like every other Casbin rule, so
narrowing a client takes effect without a deploy. A client with no scope role
reaches nothing; the migration grants a role to every existing client, so this
is never the state on the day it ships (see *Migration and seed*).

### The user assertion

Header: `X-User-Assertion: <compact JWS>`.

```
header   { "alg": "ES256", "typ": "JWT", "kid": "bff-2026-10" }
payload  {
  "iss": "<client key>",         // must equal the authenticated X-Api-Key
  "aud": "datamap-gatekeeper",
  "sub": "<user UUID>",
  "iat": 1791216000,
  "exp": 1791216060,             // iat + 60 s
  "jti": "<uuid4>",
  "htm": "PUT",
  "htu": "/v1/datasets/7d1c.../embargo"
}
```

- **ES256**, because both libraries already in use sign and verify it —
  `jsonwebtoken` in the webapp and PyJWT in the gatekeeper (with `cryptography`,
  which becomes an explicit dependency). An asymmetric key is what lets the
  gatekeeper store only public material (decision 4).
- **`htm` and `htu`** bind the assertion to one request, the way DPoP does. Both
  sides normalize the path the same way: percent-decode, drop the query string
  and any trailing slash, and keep it from the `/v1/` segment on. The BFF
  computes it from `axios.getUri(config)` in a request interceptor, so the
  call in `gateways/GatekeeperAPI.ts:54-58` that omits the leading slash is
  covered without touching it.
- **One assertion per request.** ES256 signing costs well under a millisecond in
  Node; the BFF makes a handful of calls per page.
- **No tenancy claim.** `X-Datamap-Tenancies` stays a header: the gatekeeper
  already checks it against the user's database memberships on every dataset
  call, so once the user is verified the tenancy is too.

### Verification

`authenticate` becomes the single place that decides who is calling. It returns
a `Principal(client, user_id, user_id_source)` and stores it on
`request.state`. In order:

1. Client secret, as today (`401 Unauthorized`).
2. Scope, as above (`403 client_out_of_scope`).
3. If `X-User-Assertion` is present:
   - the client must have `acts_as_users` (`401 assertion_not_allowed`);
   - `kid` must name an unrevoked key **of this client** (`401 assertion_invalid`);
   - signature, `alg == ES256` (never taken from a list the token chooses),
     `aud`, `iss == client key` (`401 assertion_invalid`);
   - `iat`/`exp` within the skew rules below (`401 assertion_expired`);
   - `htm`/`htu` equal to this request (`401 assertion_invalid`);
   - `sub` is a UUID; if `X-User-Id` is also sent it must equal `sub`
     (`401 user_id_mismatch`).
   The user is `sub`; the source is `assertion`.
4. Else, if `X-User-Id` is present: in `observe` mode the user is the header and
   the source is `bare_header`; in `enforce` mode `401 assertion_required`.
5. Else there is no user. Routes that need one fail in `parse_user_header`, as
   today.

`parse_user_header` stops reading the header. It depends on `authenticate` and
returns the principal's user, so the order of a route's `dependencies` list
stops mattering and FastAPI's per-request dependency cache runs `authenticate`
once. `authorize`, `authorize_self_or_policy` and every route that takes
`user_id: UUID = Depends(parse_user_header)` change nowhere else.

All `401`s keep the existing body; the specific reason goes to the metric and
the log, not to the caller, as `auth_failure` does today.

### Routes that change

| Route | Change |
|---|---|
| `POST /users/{user_id}/invitations/claim` | the path `user_id` must equal the asserted user (`401` otherwise). The BFF already calls it with that user right after sign-in (`lib/share.ts:75`) |
| `GET /users/providers/{provider}/{reference}`, `POST /users`, `/auth/*` | unchanged: they are how the BFF finds out who is signing in, before any assertion can exist. Reachable only with `scope_bff` |
| `/internal/*` | unchanged code; now `scope_internal` only |
| `/clients/*` | `acts_as_users` and key management are added in RFC 010's admin screen; until then they are set by migration and SQL |

### Webapp

- `lib/rpc.ts` gains a request interceptor: when the request carries a user
  (today: an `X-User-Id` header set by `buildHeaders` or by hand), it signs an
  assertion for that user, method and path, sets `X-User-Assertion`, and keeps
  `X-User-Id` during `observe` so the gatekeeper can compare them. Doing it in
  the interceptor covers the three hand-written headers (`lib/account.ts:34`,
  `lib/share.ts:70`, `lib/share.ts:75`) without editing them; a later cleanup
  replaces them with `buildHeaders`.
- The interceptor never signs for `context.uid ?? ""` — an empty user sends no
  assertion and no header, which the gatekeeper treats as "no user".
- New settings: `DATAMAP_USER_ASSERTION_KEY` (PKCS#8 PEM, base64 in the env
  file) and `DATAMAP_USER_ASSERTION_KID`, in `frontend.env.sops`.
- Calls made before a session exists — the NextAuth `jwt` callback's
  `getUserByUID` (`pages/api/auth/[...nextauth].ts:128`) included — sign for the
  user id the gatekeeper just returned from `/auth/login`, sign-up confirmation
  or the provider lookup. That is the BFF trusting the gatekeeper's answer, which
  is correct; it is also why a compromised BFF can assert anyone.

### Archivist and zipper

No code change. The archivist's client gets `scope_internal`; it never sent a
user and never will. The zipper's callback route does not exist, and its tracked
config carries a client key; whether that key is enabled in any environment is
an open question, and the answer decides whether it is rotated or deleted. When
the zipper is deployed it gets its own client, `scope_internal`, and a real
route.

### Rollout

`AUTH_USER_ASSERTION_MODE`: `observe` | `enforce`. Default `observe`.

| Step | What ships | Who notices |
|---|---|---|
| 1 | Gatekeeper: migration, scopes, assertion verification, `observe`, metrics | No one. Every existing call still passes; the BFF client has `scope_bff`, the archivist `scope_internal` |
| 2 | Webapp: signs every user call | No one. `datamap_user_identity_total{source="assertion"}` rises, `bare_header` falls to zero for the BFF |
| 3 | Integration suite signs; seed registers its key | CI |
| 4 | After a week with `bare_header` at zero for every client: `AUTH_USER_ASSERTION_MODE=enforce` | Anyone still sending a bare header gets `401` and appears on the counter |

Step 4 is an environment change and a rolling restart of the two gatekeeper
instances — no window. Rolling back is setting `observe` again.

Scopes ship enforced in step 1, not observed: the migration grants every
existing client the scope matching its known routes, and a client that is
refused shows up as `client_out_of_scope` within minutes — the archivist
dispatches email every minute, the BFF calls constantly. If the BFF and the archivist turn
out to share one client row, step 1 waits until they are split (see *Open
questions*).

### Key rotation

Overlap, as the runbook already does for client secrets
(`docs/runbooks/credential-rotation.md`, step 5):

1. Generate a P-256 pair offline. Insert the public key under a new `kid` for
   the BFF client.
2. Put the private key and the new `kid` in `frontend.env.sops`; deploy the
   webapp. Both keys verify meanwhile.
3. When the log shows no assertion with the old `kid` for ten minutes (the
   longest-lived assertion is two), set `revoked_at` on the old row.

**Emergency** (private key leaked): set `revoked_at` first. Every user call from
the BFF then fails with `401` until step 2 is done — an outage of user pages,
traded for closing the hole at once. The runbook gains a section 8 for this.

Client *secret* rotation is unchanged. Rotating one does not require rotating
the other.

### Clock skew

The BFF and both gatekeeper instances run on the same host today (nginx proxies
to both locally), so skew is near zero; the rules are for the day they do not.

- `exp` is accepted up to 30 s after it passes (PyJWT `leeway=30`).
- `iat` more than 30 s in the future is refused.
- `exp - iat` above 120 s is refused, whatever the BFF signed, so a
  misconfigured or compromised signer cannot issue long-lived assertions.

A refusal logs the observed `now - iat` so a drifting clock reads as skew, not
as an attack.

### Replay

An assertion is valid for one method, one path and at most about a minute and a
half. To replay one, an attacker must have seen it — in transit between the
BFF and the gatekeeper, or in a log — *and* hold the BFF's client secret, which
travels in the same request. The assertion is redacted from every log (below).

We do **not** keep a `jti` store in the first version. Two gatekeeper instances
would need it in PostgreSQL, one insert per request, plus cleanup; it would turn
"repeat this exact request within a minute" into "nothing". The `jti` is logged
on every verified request, so the store can be added later without a format
change. See *Open questions*.

### Integration test client

- The seed registers a test key pair: the public key in
  `client_assertion_keys`, `acts_as_users = true`, `scope_bff`. The private key
  lives in `tests/integration/config.py` with a name that says it is a test key;
  it is generated for the suite and matches nothing in any environment.
- `HttpClient._make_request` (`tests/integration/utils/http_client.py:36-57`) is
  the one place every request passes through. It turns an `X-User-Id` in the
  headers into an `X-User-Assertion` for that method and path, so the more than
  500 uses of `AuthFixture` stay as they are.
- A `raw=True` argument skips the signing, for the tests that must send a bare
  header, a forged assertion or someone else's `kid`.
- The suite runs in `enforce` mode, so a code path that still reads the bare
  header fails in CI. `observe` is covered by unit tests of the principal.
- A second seeded client with `scope_internal` and no `acts_as_users` stands in
  for the archivist, so the scope tests do not depend on the archivist
  repository.

### Metrics and logging

Metrics:

| Metric | Labels | Purpose |
|---|---|---|
| `datamap_user_identity_total` | `client`, `source` = `assertion` \| `bare_header` \| `none` | the rollout gate; `bare_header` must reach zero |
| `datamap_auth_failures_total` (existing, `app/metrics.py:209-214`) | new `reason` values: `client_out_of_scope`, `assertion_not_allowed`, `assertion_invalid`, `assertion_expired`, `assertion_required`, `user_id_mismatch` | added to `AUTH_REASONS` (`app/metrics.py:34`), or they collapse into `other` |

`client` is the client's name, already a label on `datamap_requests_total`; a
handful of values. `kid` and `jti` are never labels.

Logging, following the rules in `CLAUDE.md`:

- `assertion` joins `_SECRET_WORDS` (`app/logging_config.py:15`), so a header or
  field carrying one is redacted by the filter. The code never logs it in the
  first place.
- Refusals log named fields through `fields()`: `client`, `route`,
  `reason`, `kid`, `jti`, `iat_skew_s`, `request_id`. Never the token, never the
  whole header set.
- The access log's `user_id` (`app/setup.py:193`) today records the *claimed*
  header. It records the principal's user instead, plus `user_id_source`, so
  the log says who was authorized and how we know.
- `bare_header` requests in `observe` log one warning per request with
  `client` and `route`, which is what finds the last caller.

### Configuration

| Setting | Where | Notes |
|---|---|---|
| `AUTH_USER_ASSERTION_MODE` | gatekeeper | `observe` \| `enforce`; default `observe` |
| `DATAMAP_USER_ASSERTION_KEY` | webapp | PKCS#8 PEM, base64; private |
| `DATAMAP_USER_ASSERTION_KID` | webapp | must name an unrevoked row of the BFF client |

The gatekeeper gains no secret.

### Migration and seed

One Alembic revision:

- adds `clients.acts_as_users` and `client_assertion_keys`;
- inserts the `scope_internal` and `scope_bff` policies;
- grants scopes to existing clients **by name**, from a mapping in the
  migration (the production names are confirmed before it is written; see *Open
  questions*). A client it cannot classify gets `scope_bff`, which is exactly
  what every client can do today minus `/internal` — so the migration narrows
  access and never widens it — and is logged so an operator decides;
- does not set `acts_as_users` or insert keys: those are production values and
  are set by an operator, with a runbook entry, between steps 1 and 2.

`tests/integration/fixtures/seed_clients.sql` gains the two scope grants, the
test key, `acts_as_users` on the test client and the internal-only client.
Casbin reloads every five seconds, so the suite waits for the seeded rows the
way `CLAUDE.md` describes — poll `/api/v1/clients/` until it answers `200` —
and that poll now also proves the test client's scope is loaded.

### Security notes

| Threat | Defence |
|---|---|
| A leaked machine secret (archivist, zipper) acting as a user | `acts_as_users` is false; assertions refused; `X-User-Id` refused in `enforce` |
| A leaked machine secret reaching user routes or client-only routes | scope: `/internal/*` only |
| A leaked BFF secret acting as a user | no signing key, no assertion; `X-User-Id` refused in `enforce` |
| A leaked BFF secret reaching `/internal/*` | `scope_bff` excludes it |
| A captured assertion | bound to `iss`, method and path; about a minute; redacted from logs |
| One client's key used with another client's secret | `kid` must belong to the authenticated client; `iss` must equal its key |
| A long-lived assertion from a misconfigured signer | `exp - iat` capped at 120 s by the verifier |
| Algorithm confusion | the verifier fixes `ES256`; the header's `alg` is not trusted |
| A leaked gatekeeper database or environment | holds public keys and secret hashes only; cannot mint assertions |
| Claiming another user's invitations | claim requires path user = asserted user |

#### Residual risk

- **A compromised BFF host** holds the private key, the client secret and
  `NEXTAUTH_SECRET`. It can assert any user, admins included. This RFC does not
  change that. Narrowing it means the gatekeeper issuing user sessions itself,
  which is in *Alternatives considered*.
- **The BFF is also the sign-in authority for ORCID.** It decides which ORCID iD
  signed in and asks the gatekeeper for that user, so even gatekeeper-issued
  sessions would trust the BFF for ORCID sign-in.
- **Replay within a minute** of an exact request, by someone who already sees
  the BFF-to-gatekeeper traffic, until a `jti` store exists.
- **Client-only routes stay reachable with the BFF secret alone:** `POST
  /users`, the provider lookup, `/auth/*`, previews. The provider lookup still
  returns a user's roles to a holder of that secret, and `POST /users` still
  creates accounts. RFC 009 PR A removes the roles from creation; rate limits
  and a narrower lookup response are follow-ups.

## Testing

**Integration (gatekeeper),** in `enforce` mode unless stated:

- the BFF-shaped client with a valid assertion reaches user routes as `sub`;
- the same request with only `X-User-Id` answers `401` (`assertion_required`);
- a forged signature, a wrong `aud`, another client's `kid`, a revoked `kid`, an
  expired assertion, `exp - iat` of 300 s, an assertion for another path or
  method: each `401`, each counted under its reason;
- `X-User-Id` different from `sub`: `401` `user_id_mismatch`;
- the internal-only client: `/internal/*` works; a user route and `POST /users`
  answer `403 client_out_of_scope`; an assertion from it answers
  `assertion_not_allowed`;
- the BFF-shaped client on `/internal/notifications/dispatch`: `403`;
- the invitation claim for another user: `401`;
- the access log line carries the asserted user and `user_id_source`, and no
  assertion text;
- `datamap_user_identity_total` moves with each source.

Each of these is written to fail first against today's code, which accepts all
of them.

**Unit (gatekeeper):** path normalization (trailing slash, query string,
percent-encoding, `{name:path}` tenancy routes); skew boundaries; the principal
in `observe` and `enforce`; `parse_user_header` reads the principal, not the
header; the migration's name mapping never grants `admin`.

**Webapp (Jest):** the interceptor signs with method and normalized path; no
assertion for an empty user; the three hand-set headers get one; a verification
round-trip against the public key with `jsonwebtoken`.

## Delivery

| PR | Repository | Content |
|---|---|---|
| 1 | gatekeeper | Migration, scopes, `Principal`, assertion verification, `observe`/`enforce`, claim route check, access-log user, metrics and reasons, redaction, seed, integration tests, `cryptography` dependency, runbook section 8 |
| 2 | webapp | Assertion interceptor in `lib/rpc.ts`, settings, Jest tests |
| 3 | gatekeeper | Integration suite signs in `HttpClient`; suite switched to `enforce` |
| 4 | gatekeeper | Production `AUTH_USER_ASSERTION_MODE=enforce` |
| 5 | zipper | Own client, real callback route, credentials out of tracked config — when the zipper is deployed |

The archivist needs no PR. 1 is safe alone: it narrows `/internal` for the BFF
and changes nothing else that any client does. 2 depends on 1 and on an
operator having inserted the BFF's public key. 3 can merge with 1. 4 waits for
the counter.

### Before shipping PR 1

- The production client rows are listed (names and keys only) and each is
  mapped to a scope.
- If the BFF and the archivist share a client, a second client is created and
  the archivist moved to it first.
- The zipper's tracked key is checked against every environment's `clients`
  table.

### Before PR 4

- `datamap_user_identity_total{source="bare_header"}` at zero for seven days.
- Runbook section 8 rehearsed once in staging or locally.

## Alternatives considered

### Symmetric assertions (HS256 per client)

What the upload token does, and no new dependency. But the gatekeeper must hold
every client's key in a form it can use — in its environment, so adding a key
is a deploy of two repositories in lockstep (the runbook's step 6, which is the
expensive kind), or in the database, encrypted under yet another pepper. Either
way the gatekeeper's environment can then mint assertions. ES256 costs one
dependency and removes both.

### Reusing `AUTH_FILE_UPLOAD_TOKEN_SECRET` or the upload token

One secret for two purposes with different lifetimes and audiences, shared with
a token the browser holds for a day. Rejected.

### Forwarding the NextAuth session to the gatekeeper

The gatekeeper would decrypt the session cookie with `NEXTAUTH_SECRET`. It ties
the gatekeeper to NextAuth's token format and version, puts the session secret
in a second service, and a stolen cookie becomes a gatekeeper credential for
the session's lifetime. The BFF would still need to act as itself for sign-in.

### Gatekeeper-issued user sessions

The gatekeeper issues a session token at `/auth/login` and email verification,
and the BFF can only forward it. This is the only option that stops a
compromised BFF from asserting an arbitrary user — for password sign-in. For
ORCID the BFF still tells the gatekeeper which iD signed in, unless the
gatekeeper runs the OAuth exchange itself. It moves session lifetime,
revocation and refresh into the gatekeeper and rewrites RFC 008's webapp half.
Out of proportion to the hole being closed; worth revisiting if the BFF ever
runs somewhere less trusted than the gatekeeper.

### Mutual TLS between services

Authenticates the BFF's host, not the user; it replaces the client secret, not
`X-User-Id`. The services share a Docker network and a host today, so it adds
certificate management for little.

### Network isolation of `/internal`

An nginx `deny` for `/api/v1/internal` would keep the internet out, and is
worth doing anyway. It does nothing about a leaked BFF secret used from inside,
and nothing about user impersonation.

## Out of scope

- The admin screen for clients, scopes and keys (RFC 010).
- A `jti` replay store.
- Rate limits on `POST /users` and `/users/providers/...`, and trimming the
  lookup's response.
- **TUS hooks.** `/api/v1/tus/hooks` is reachable through the public
  `/api/v1` location, has no client authentication, and trusts the upload
  token the browser holds for a day. Anyone can post a hook *as themselves*
  with their own token. It does not let them act as another user, so it is
  not this RFC's hole, but it deserves its own: an nginx `deny` for the path
  from outside, and a shared secret or client for tusd.
- An nginx `deny` for `/api/v1/internal`.
- Replacing the remaining hand-written `X-User-Id` headers in the webapp with
  `buildHeaders`.

## Open questions

- **Which client rows exist in production, and do the BFF and the archivist
  share one?** The scope migration maps clients by name; if they share a row it
  cannot scope either without splitting them first.
- **Is the zipper's tracked client key enabled anywhere?** It is in
  `zipper/local_config.yml` and `zipper/staging_config.yml`. If it matches a
  production client, that client is disabled before this ships.
- **`/health-check/dependencies`** is protected by `authorize`, so an operator
  reaches it with a client and a user id. In `enforce` they would need an
  assertion. Should it move to a client scope (`scope_ops`) instead of a user
  role?
- **Does the BFF reach the gatekeeper through the internal network or through
  the public `/api/v1`?** It changes who could capture an assertion in transit,
  and so how much a `jti` store is worth.
- **Do we want the `jti` store in PR 1** rather than later? One insert per user
  request against the cost of a one-minute replay window.
- **Should `GET /users/providers/...` and `POST /users` move under `/auth`**
  so that "client-only, pre-session" routes have one prefix that a scope can
  name?
