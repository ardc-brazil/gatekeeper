# RFC 011: Scoped API clients, user identity assertion and personal access tokens

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

This RFC closes that hole and gives people who call the API directly a
credential of their own:

1. **Every client gets a scope.** A client is a Casbin subject,
   `client:{key}`, with route policies of its own. The archivist reaches
   `/internal/*` and nothing else; the BFF reaches everything except
   `/internal/*` and `/tus/*`. A client outside its scope is refused before
   any user is looked at.
2. **A user is asserted, not named.** A client flagged `acts_as_users` sends a
   short-lived ES256 JWT, `X-User-Assertion`, signed with a private key only
   it holds, carrying `sub`, `aud`, `iat`, `exp`, `jti` and the method and path
   of the request it belongs to. The gatekeeper verifies it against the
   client's registered public key and derives the user from it.
3. **Only the BFF acts as users through a client.** The archivist, the zipper
   and any future machine client cannot assert anyone, whatever secrets leak.
4. **The gatekeeper stores public keys only.** A leaked database or gatekeeper
   environment cannot mint an assertion, and adding a key is a row, not a
   deploy of two repositories.
5. <!--c:8v0c8-->**One ordered hard deploy, and `X-User-Id` is gone.** The webapp ships
   first, signing assertions while still sending `X-User-Id`; the gatekeeper
   ships next, requiring the assertion. From then on the gatekeeper reads no
   user identity from `X-User-Id` anywhere — not from clients, not from the TUS
   hook, not in the access log. There is no observe mode.<!--/c:8v0c8-->
6. **People who use the API directly get personal access tokens.** A
   signed-in user creates a token in the webapp profile and sends it as
   `Authorization: Bearer dm_pat_…`, alone — from a script or from the Swagger
   UI. It acts as that user with their current roles — admin routes included,
   for an admin's token — and can be read-only, expiring and revoked. OAuth is
   deferred.
7. **The residual risk is stated, not hidden.** The BFF mints assertions for
   whoever it believes is signed in, so a compromised BFF host still acts as
   any user. What changes is that every *other* secret — the archivist's, the
   zipper's, a test client's, one pasted into a log — stops being a skeleton
   key.
<!--co:8v0c8 by:Caio at:2026-10-05T21:44:05.755Z status:open quote:"**Rollout is observe, then enforce.** A setting moves the gatekeeper from `observe` (accept bare `X-User-Id`, count it) to `enforce` (refuse it). We switch when the counter has been at zero for a week."
Caio (2026-10-05T21:44:05.755Z): Let's just hard deploy this once it's done. No need to check for a week.
Caio (2026-10-05T21:44:24.995Z): Just make sure we are not using x-user-id anymore for non-related use cases.
Claude (2026-10-05T21:57:32.000Z): Done. The observe/enforce setting, the week at zero and the bare-header counter are gone. *Rollout* is now one ordered deploy inside the usual downtime: the webapp first (signs, still sends X-User-Id, which today's gatekeeper keeps using), then the gatekeeper (requires the assertion, never reads X-User-Id), then the webapp's API-tokens screen and cleanup. Refusals stay counted by reason. The new table "Every use of X-User-Id today" lists each use with file:line in all four repositories and what happens to it: BFF calls and the three hand-set headers → assertion, then the header stops leaving the BFF; TUS hook → user taken from the upload token's sub, header ignored; access log → the authorized user; unit and integration tests → principal/assertion; Swagger's X-User-Id scheme → bearer PAT. The archivist and the zipper never send it. Outside API users who send it today move to personal access tokens and must be told before the deploy (open question: who are they?).
-->

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
  still forwards `roles=payload.roles` (`user.py:95`). RFC 009 PR A
  (`feat/rfc-009-gatekeeper`, commit 1773ad2) ignores it: every new account
  gets exactly `datasets_write`, and roles change only through
  `PUT /users/{id}/roles`.

The same header is also how people outside the webapp use the API. The Swagger
UI the gatekeeper serves at `/api/docs` (`infrastructure/nginx/datamap.conf:97-104`)
offers `X-User-Id` as an "Authorize" field (`user_parser.py:6`), so anyone with
a client key and secret types in a user id — any user id. Those callers cannot
hold a signing key, so closing the hole for them needs a different credential.

### What exists today

#### Who holds a client secret

| Holder | Where its secret lives | Routes it calls | Acts as a user? |
|---|---|---|---|
| **Webapp BFF** | `DATAMAP_API_KEY`/`DATAMAP_API_SECRET` in `datamap-webapp/secrets/production/frontend.env.sops`; one axios instance sends them on every call (`datamap-webapp/lib/rpc.ts:6-18`) | Everything a screen needs: `/datasets/**`, `/users/**`, `/tenancies`, `/invitations/**`, `/anonymous/{token}`, `/auth/*`, `/datasets/{id}/embargo-status` | **Yes**, on most calls: `buildHeaders` sets `X-User-Id` from the NextAuth session (`lib/rpc.ts:77-86`); three calls set it by hand (`lib/account.ts:34`, `lib/share.ts:70`, `lib/share.ts:75`). **As itself** for sign-in and public pages: `/auth/*` (`lib/account.ts:3-50`), `POST /users` (`lib/users.ts:109`), `GET /users/providers/...` (`lib/users.ts:127`), invitation preview, anonymous pages, embargo status |
| **Archivist** | `GATEKEEPER_API_KEY`/`GATEKEEPER_API_SECRET` in `archivist/secrets/production/archivist.env.sops`; `archivist/app/client/gatekeeper_client.py:17-21` | `GET /internal/datasets/collocation/pending` (`:31`), `GET /internal/datasets/{id}/files` (`:56`), `PUT /internal/datasets/{id}/files/{file_id}` (`:80`), `PUT /internal/datasets/{id}/collocation-status` (`:104-106`), `POST /internal/notifications/dispatch` (`:129`) | **Never.** No call sends `X-User-Id` |
| **Zipper** | `gatekeeper.api_key`/`api_secret` in the tracked `zipper/local_config.yml` and `zipper/staging_config.yml`; `zipper/app/gateways/gatekeeper.py:12-16` | One callback, `POST /v1/internal/datasets/{id}/versions/{v}/files/zip/{id}` (`gatekeeper.py:19`), **which does not exist in the gatekeeper**. The zipper is not deployed (`infrastructure/prometheus/prometheus.yml:30`) | **Never** |
| **TUSd** | **None.** It holds no client secret | `POST /tus/hooks`, guarded by `authorize_tus` only (`app/controller/v1/tus/tus.py:16`), with no `authenticate` | The user comes from the hook payload; see below |
| **Integration test client** | Seeded by `tests/integration/fixtures/seed_clients.sql:38-50`; defaults in `tests/integration/config.py:13-20` | Every route, as the seeded user, which holds `admin` and `clients_admin` (`seed_clients.sql:75-76`) | **Yes**, `X-User-Id` from config (`tests/integration/fixtures/auth.py:11-19`) |
| **Direct API users** (scripts, the Swagger UI) | A client key and secret issued through `/clients` and handed to a person | Whatever they need | **Yes**, an `X-User-Id` of their choosing. The production rows and who holds each are listed in *Existing direct API clients* |

The BFF and the archivist are two separate client rows in production,
confirmed in *Existing direct API clients*; the scope migration maps them —
and every other row — by name.

#### Every use of `X-User-Id` today

Searched in `gatekeeper`, `datamap-webapp`, `archivist` and `zipper` (`main`,
and the zipper's `zip-async`), excluding RFCs and old plans. After this RFC the
gatekeeper reads **no user identity from `X-User-Id` anywhere**.

| Where | What it does | After this RFC |
|---|---|---|
| **Gatekeeper** | | |
| `app/controller/interceptor/user_parser.py:6` | declares `X-User-Id` as an `APIKeyHeader`, which makes it an "Authorize" field in Swagger | removed; Swagger offers a bearer field for a PAT (*Swagger UI*) |
| `user_parser.py:9-13`, `parse_user_header` | the user of every user route; used by `authorize`, `authorize_self_or_policy` (`authorization.py:21-23`, `:44-46`) and 46 uses across eight controller modules | returns the principal's user; never reads a header |
| `user_parser.py:16-22`, `parse_tus_user_id` | reads `X-User-Id` from the TUS hook payload | removed. `authorize_tus` (`authorization.py:68-98`) takes the user from the upload token's `sub`; the `sub == X-User-Id` check (`:81-82`) goes with it. The token already carries the user and is signed; the header added nothing but a second place to disagree |
| `app/setup.py:193` | access log `user_id` is the *claimed* header | the principal's user, plus `user_id_source` (`assertion` \| `pat` \| `upload_token`) |
| `app/controller/interceptor/authorization_test.py:44-83`, `app/controller/v1/user/user_test.py:134,184`, `app/controller/v1/dataset/share_test.py:51` | unit tests set the user through the header | set the principal through a test helper that overrides `authenticate` |
| `tests/integration/fixtures/auth.py:16,32,43`, `tests/integration/fixtures/embargo.py:25` | the integration suite names its user | the header becomes an input to `HttpClient`, which turns it into an assertion and does not send it (*Integration test client*) |
| `tests/integration/test_request_body_logging.py:176,188` | asserts the access log's user equals the header | asserts it equals the asserted user and `user_id_source` |
| `tests/integration/fixtures/tus_auth.py:72,94,122`, `tests/integration/test_tus_api.py:106,145,220-233` | TUS hook payloads carry it; one test requires a mismatch to be refused | payloads drop it; the mismatch test becomes "a header naming someone else is ignored and the upload belongs to the token's `sub`" |
| **Webapp** | | |
| `lib/rpc.ts:80`, `buildHeaders` | every user call from the BFF | signed into an assertion by a request interceptor; the header keeps being sent until the gatekeeper ships, then stops leaving the BFF |
| `lib/account.ts:34` (`changePassword`), `lib/share.ts:70` (`acceptInvitation`), `lib/share.ts:75` (claim invitations) | the three calls that set the header by hand, as the user acting on themselves | same as `buildHeaders`, through the interceptor; the cleanup passes the user as a config field instead of a header |
| `components/base/UppyUploader.tsx:76` | the browser sends it to tusd, which forwards it in the hook payload | ignored by the gatekeeper; removed in the cleanup. `X-User-Token` (`:77`) stays |
| `lib/__tests__/rpc.test.ts:23,36`, `account.test.ts:73`, `share.test.ts:27,108,115`, `dataset.test.ts:135-155`, `doi.test.ts:6`, `embargo.test.ts:11` | Jest expectations on the header | updated with the cleanup |
| `docs/frontnend-rpc.plantuml:43`, `docs/frontnend-rpc-datafetch.plantuml:39` | diagrams list it | updated with the cleanup |
| **Archivist** | none. `tests/unit/test_logging_config.py:67` is `X-User-Token`, unrelated | — |
| **Zipper** | none | — |
| **Infrastructure** (nginx, Alloy, Prometheus) | none | — |
| **Direct API users and Swagger** | key and secret plus a chosen `X-User-Id` | personal access tokens; a request that still carries `X-User-Id` without an assertion answers `401` with a message that says so |

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
- After this RFC the gatekeeper reads no user identity from `X-User-Id`
  anywhere.
- A person who uses the API directly — a script, the Swagger UI — acts as
  themselves with a credential that is theirs, limited in time and revocable,
  without holding a client secret.
- One ordered deploy, inside the downtime every deploy already has. No mode to
  switch later.

### Non-goals

- Protecting against a compromised BFF host. It holds the private key and the
  session secret; it can be anyone. See *Residual risk*.
- Replacing NextAuth sessions with gatekeeper-issued sessions (see
  *Alternatives considered*).
- Third-party applications acting for *other* users (OAuth). See
  *Alternatives considered*.
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

### Option C: both (recommended for clients)

Scopes decide *which routes* a client may call; the assertion decides *who* the
user is. Each covers what the other leaves:

| Secret leaked | Today | A only | B only | **C** |
|---|---|---|---|---|
| archivist | any user, any route | `/internal/*` only | any client-only route, `/internal/*` | **`/internal/*` only** |
| zipper | any user, any route | its callback only | any client-only route | **its callback only** |
| BFF secret, without its signing key | any user, any route | any user, every non-internal route | client-only routes | **client-only, non-internal routes** |
| BFF secret *and* signing key (host compromise) | any user | any user | any user | **any user** |
| a direct API user's client secret | any user, any route | any user, its scope | client-only routes | **client-only routes of its scope; and the client is retired for PATs** |
| a user's PAT (with D, below) | — | — | — | **that user, non-admin routes, until it expires or is revoked** |

The fourth row is the honest one: C does not help there, and nothing short of
moving session issuance into the gatekeeper does.

### Direct API access: who can a script or Swagger act as?

C needs a signing key, which a person at a terminal or in Swagger cannot hold.

- **D1: keep key/secret + `X-User-Id` for them.** Leaves the hole open for
  exactly the callers we know least about. Rejected.
- **D2: personal access tokens (recommended).** A user creates a token in the
  webapp and sends it as a bearer credential. The token *is* the user; no
  client secret is involved. GitHub-like UX, one table, one more branch in
  `authenticate`.
- **D3: OAuth 2.0** (authorization code with PKCE, access and refresh tokens,
  client registration). Needed only for third-party apps acting for users who
  are not their author. Deferred; see *Alternatives considered*.

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

A third table holds personal access tokens:

```
personal_access_tokens
  id            UUID primary key
  user_id       UUID, FK users.id ON DELETE CASCADE, indexed
  name          String(100)               -- "laptop notebook", chosen by the user
  token_hash    String(64), unique        -- hex SHA-256 of the whole token
  display       String(20)                -- "dm_pat_…a1b2", prefix and last 4
  read_only     Boolean, not null
  created_at    DateTime(tz)
  expires_at    DateTime(tz), not null
  last_used_at  DateTime(tz), nullable
  revoked_at    DateTime(tz), nullable
  revoked_by    UUID, nullable            -- the user or the admin who revoked it
```

### Client scopes

Clients become Casbin subjects named `client:{key}`. User subjects are UUIDs —
`parse_user_header` rejects anything else — so the two namespaces cannot meet,
and the prefix makes a client row in `casbin_rule` obvious to a reader.

Scope roles, seeded by the migration:

| Role | Policy (`v1`, `v2`) | Holders |
|---|---|---|
| `scope_internal` | `^/api/v1/internal/` , `.*` | archivist, zipper |
| `scope_bff` | `^/api/v1/(?!internal/\|tus/)` , `.*` | both BFF deployments (DataMap, DataAmazon), integration test client |
| `scope_pat` | `^/api/v1/(?!internal/\|tus/\|auth/\|clients\|users/[^/]+/tokens\|users/providers/\|users/?$\|tokens)` , `.*` | the subject `pat`, which every PAT request is checked as |

The matcher's `regexMatch` (`app/resources/casbin_model.conf`) is pycasbin's
`re.match`: anchored at the start, open at the end. The patterns are prefixes,
so that is what we want; the explicit `^` is for the reader. The negative
lookahead in `scope_bff` is what keeps it from being `/*`. No client is ever
granted `admin`, whose `/*` would cover everything; a test asserts it.
`scope_pat` additionally keeps a token away from the routes that create
accounts, manage clients, or manage tokens — **not** the admin area or role
changes, which stay gated by the route's own `authorize`, so an admin's token
reaches them exactly as an admin's session does — see *Personal access
tokens*.

`authenticate` enforces the scope right after the secret check:

```
enforce("client:{key}", request.url.path, request.method)  → else 403 client_out_of_scope
```

The policy reloads every five seconds like every other Casbin rule, so
narrowing a client takes effect without a deploy. A client with no scope role
reaches nothing; the migration grants a role to every existing client, so this
is never the state on the day it ships (see *Migration and seed*).

### <!--c:hul67-->The user assertion<!--/c:hul67-->
<!--co:hul67 by:Caio at:2026-10-05T21:49:52.800Z status:open quote:"The user assertion"
Caio (2026-10-05T21:49:52.800Z): How is this generated in the frontend? We store the private key, sign the footer and check against the public key in gatekeeper?
Claude (2026-10-05T21:57:32.000Z): Almost. Only the Next.js server signs — the axios request interceptor in lib/rpc.ts, the same place that adds X-Api-Key/X-Api-Secret today; the browser never sees the key or the assertion. The private key is an ES256 (P-256) key in frontend.env.sops as DATAMAP_USER_ASSERTION_KEY, with DATAMAP_USER_ASSERTION_KID naming it; the gatekeeper stores only the public key, in client_assertion_keys under that kid. There is no footer: it is a compact JWS, header.payload.signature, and the signature covers both header and payload (footers are PASETO's). The gatekeeper looks up the public key by kid, verifies the signature, then checks iss, aud, exp/iat, method and path, and takes sub as the user. Asymmetric so a leaked gatekeeper database or env cannot mint assertions. New subsection "How the BFF signs" below, with a jose sketch.
-->

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

- **ES256**, signed with `jose` in the webapp (a new, dependency-free package)
  and verified with PyJWT in the gatekeeper (with `cryptography`, which becomes
  an explicit dependency). An asymmetric key is what lets the gatekeeper store
  only public material (decision 4).
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

#### How the BFF signs

- **Only on the server.** The signer is the axios request interceptor in
  `lib/rpc.ts`, which runs in the Next.js BFF (`pages/api/*`,
  `getServerSideProps`, the NextAuth callbacks). The browser never holds the
  key and never sees an assertion; it talks to the BFF with its session cookie
  as today.
- **The key.** An ES256 (P-256) private key, PKCS#8 PEM, base64-encoded in
  `DATAMAP_USER_ASSERTION_KEY` in `frontend.env.sops`, with
  `DATAMAP_USER_ASSERTION_KID` naming it. The gatekeeper stores only the public
  half, in `client_assertion_keys` under that `kid`.
- **The token.** A compact JWS: `base64url(header).base64url(payload).base64url(signature)`,
  with the signature over the first two parts. There is no footer — that is
  PASETO's term; a JWS has none. The claims are the ones above.
- **The code.** A few lines:

  ```ts
  import { SignJWT, importPKCS8 } from "jose";
  import { randomUUID } from "crypto";

  const pem = Buffer.from(process.env.DATAMAP_USER_ASSERTION_KEY!, "base64").toString();
  const key = importPKCS8(pem, "ES256");           // once per process
  const kid = process.env.DATAMAP_USER_ASSERTION_KID!;

  axiosInterceptorInstance.interceptors.request.use(async (config) => {
    const uid = userOf(config);                    // today: the X-User-Id header
    if (!uid) return config;
    config.headers["X-User-Assertion"] = await new SignJWT({
      htm: config.method!.toUpperCase(),
      htu: normalizedPath(axiosInterceptorInstance.getUri(config)),
    })
      .setProtectedHeader({ alg: "ES256", typ: "JWT", kid })
      .setIssuer(apiKey!).setAudience("datamap-gatekeeper").setSubject(uid)
      .setIssuedAt().setExpirationTime("60s").setJti(randomUUID())
      .sign(await key);
    return config;
  });
  ```

- **What the gatekeeper checks, in order:** `kid` → an unrevoked public key of
  the authenticated client; the signature, with `ES256` fixed by the verifier;
  `iss` equals the authenticated client's key; `aud`; `exp` and `iat` within
  the skew rules; `htm` and `htu` equal this request; then `sub` becomes the
  user. Details and reasons are in *Verification*.
- **Why not HMAC.** With a shared secret the gatekeeper would hold a key that
  signs as well as verifies, so a leaked gatekeeper database or environment
  could mint an assertion for any user. With ES256 it holds only public keys.

### Personal access tokens

For people who call the API themselves — a notebook, a script, the Swagger UI.
The BFF never uses them.

**Creating one.** The webapp profile gains an *API tokens* section. A
signed-in user gives a name, picks an expiry — 30, 90 (default) or 365 days;
`AUTH_PAT_MAX_DAYS`, 365, is the ceiling the gatekeeper enforces — and may tick
*read-only*. The BFF calls `POST /users/{id}/tokens` with an assertion for that
user. The token is shown once, with a copy button and the line "you will not
see this again"; afterwards the list shows name, `display`, created, expires,
last used and read-only, with a *Revoke* button.

**Format.** `dm_pat_` followed by 43 base62 characters (32 random bytes from
`secrets.token_bytes`). The fixed prefix lets GitHub's and other secret
scanners match a token pasted into a repository, and lets the gatekeeper tell
a PAT from any future bearer format without a lookup.

**Storage.** Only `sha256(token)` is stored, and a request finds its row by
that hash through the unique index. A fast hash is right here and wrong for
passwords: a password has little entropy, so an attacker with the hash guesses
candidates and a slow hash is what makes each guess expensive; a 256-bit random
token has nothing to guess, so the hash only has to be one-way. A leaked table
yields no usable token.

**Using one.** `Authorization: Bearer dm_pat_…`, and nothing else — no
`X-Api-Key`, no `X-Api-Secret`, no `X-User-Id`. The token is the credential. A
request is identified by the token's id: in the log (`pat_id`, never the
token) and in `last_used_at` (written at most once a minute per token, not per
request). There is no rate limit on a PAT (see *Out of scope*).

**What it can do.** Everything the user can do *now*, intersected with
`scope_pat`, and with `GET` only if the token is read-only:

1. `enforce("pat", path, method)` — `scope_pat` keeps every PAT off
   `/internal`, `/tus`, `/auth`, `/clients`, `POST /users`, the provider lookup
   and the token routes themselves (`403 pat_out_of_scope`);
2. read-only and the method is not `GET`/`HEAD` → `403 pat_read_only`;
3. the route's own `authorize` as today, with the token's user — so a role
   removed from the user takes effect on their tokens within the five-second
   policy reload, and so an admin's token reaches `/admin/*` and
   `/users/{id}/roles` exactly as an admin's session does.

**Admins are admins.** A token carries the user's live roles with no exclusion
beyond what any admin session already has, so there is nothing left for
`scope_pat` to add on the admin area or on role changes. What stays excluded
for every PAT, admin included, is not about privilege:

- `/internal` and `/tus` — no session, admin or not, ever reaches them as a
  bearer user; one is machine-only, the other takes its user from a signed
  upload token.
- `/auth/*`, the provider lookup and `POST /users` — how someone gets a
  session in the first place, which a PAT already presupposes.
- `/clients` and the token routes (`/users/{id}/tokens`, `/tokens`) — letting a
  leaked bearer credential mint another standing credential, client or token,
  is a bigger blast radius than anything the user's own roles allow. A token
  cannot create, list or revoke tokens or clients, so a stolen one cannot
  extend itself.

**Revocation.** The user revokes from the profile
(`DELETE /users/{id}/tokens/{token_id}`); an admin lists and revokes any token
(`GET /tokens`, `DELETE /tokens/{token_id}`, under a `tokens_admin` policy that
`admin` already covers). Verification refuses a token whose user is disabled
(`users.is_enabled`), so disabling an account stops its tokens at once and
re-enabling it restores them unless they were revoked; deleting the user
deletes them. Activity (RFC 010) records `pat_created` and `pat_revoked` with
who did it, and `pat_used` once a day per token.

**Routes.**

| Route | Who | Notes |
|---|---|---|
| `POST /users/{id}/tokens` | the asserted user, `{id}` = self | body `{name, expires_in_days, read_only}`; answers the token once |
| `GET /users/{id}/tokens` | the asserted user, self | never returns the token or its hash |
| `DELETE /users/{id}/tokens/{token_id}` | the asserted user, self | `204`; idempotent |
| `GET /tokens`, `DELETE /tokens/{token_id}` | `tokens_admin` (admins) | through the BFF with an assertion |

All five require an assertion: they are refused to a PAT by `scope_pat` and to
a machine client by its scope.

### Verification

`authenticate` becomes the single place that decides who is calling. It returns
a `Principal(kind, client, user_id, user_id_source, pat_id, read_only)` and
stores it on `request.state`. It tries three paths, in order:

1. **Bearer PAT.** `Authorization: Bearer …` is present.
   - `X-Api-Key` also present → `401 ambiguous_credentials`; a request is one
     caller or the other.
   - not `dm_pat_…`, no row for its hash, revoked, expired, or the user
     disabled → `401 pat_invalid` (`pat_expired` and `pat_revoked` are
     separate reasons in the metric, not in the body).
   - `scope_pat` and read-only as above → `403`.
   The user is the token's user; the source is `pat`.
2. **Client key and secret.**
   1. Client secret, as today (`401 Unauthorized`).
   2. Scope, as above (`403 client_out_of_scope`).
   3. If `X-User-Assertion` is present:
      - the client must have `acts_as_users` (`401 assertion_not_allowed`);
      - `kid` must name an unrevoked key **of this client** (`401 assertion_invalid`);
      - signature, `alg == ES256` (never taken from a list the token chooses),
        `aud`, `iss == client key` (`401 assertion_invalid`);
      - `iat`/`exp` within the skew rules below (`401 assertion_expired`);
      - `htm`/`htu` equal to this request (`401 assertion_invalid`);
      - `sub` is a UUID.
      The user is `sub`; the source is `assertion`. An `X-User-Id` sent
      alongside is ignored, which is what lets the webapp ship first.
   4. Else, if `X-User-Id` is present: `401 user_id_header_rejected`, with a
      body that says the header is no longer accepted and points to personal
      access tokens. This is the one refusal that explains itself: it is what
      an outside script will hit after the deploy, and it reveals nothing.
   5. Else the client is a machine caller with no user. Routes that need one
      fail in `parse_user_header`, as today.
3. **Neither** → `401 Unauthorized`.

`parse_user_header` stops reading the header. It depends on `authenticate` and
returns the principal's user, so the order of a route's `dependencies` list
stops mattering and FastAPI's per-request dependency cache runs `authenticate`
once. `authorize`, `authorize_self_or_policy` and every route that takes
`user_id: UUID = Depends(parse_user_header)` change nowhere else.

All other `401`s keep the existing body; the specific reason goes to the metric
and the log, not to the caller, as `auth_failure` does today.

### TUS hooks

`authorize_tus` takes the user from the verified upload token's `sub` and stops
reading `X-User-Id` from the hook payload: `parse_tus_user_id`
(`user_parser.py:16-22`) and the `sub == X-User-Id` comparison
(`authorization.py:81-82`) are removed. The `file == dataset_id` check and
Casbin for that user stay. The uploader keeps sending the header until the
webapp cleanup; it is ignored either way. The source in the access log is
`upload_token`.

### Swagger UI

`/api/docs` is the other direct user of the API.

- The `X-User-Id` `APIKeyHeader` (`user_parser.py:6`) is removed, so its
  "Authorize" field disappears.
- An `HTTPBearer(auto_error=False, scheme_name="Personal access token")` is
  added to `authenticate`, with a description that says where to create one.
  "Authorize" then takes a PAT, and every "Try it out" call carries it.
- `X-Api-Key`/`X-Api-Secret` stay as schemes for machine clients.
  `X-User-Assertion` is read from the request, not declared as a scheme, so
  Swagger does not offer a field nobody can fill in.

### Routes that change

| Route | Change |
|---|---|
| `POST /users/{user_id}/invitations/claim` | the path `user_id` must equal the asserted user (`401` otherwise). The BFF already calls it with that user right after sign-in (`lib/share.ts:75`) |
| `GET /users/providers/{provider}/{reference}`, `POST /users`, `/auth/*` | unchanged, and **not** moved under `/auth/*` for a shared prefix: `scope_pat` and `scope_bff` already name them explicitly (*Client scopes*), so renaming the paths would be churn across both BFF deployments for no security gain. Reachable only with `scope_bff` |
| `/internal/*` | unchanged code; now `scope_internal` only |
| `POST /tus/hooks` | the user is the upload token's `sub` |
| `/users/{id}/tokens`, `/tokens` | new |
| `/clients/*` | `acts_as_users` and key management are added in RFC 010's admin screen; until then they are set by migration and SQL |
| `GET /health-check/dependencies` | unchanged: `authorize` gates it to `admin` today, since no other role is granted it. An admin's PAT now reaches it, the same way an admin's session already does. No `scope_ops` and no machine client for it now; if an external uptime monitor ever needs this route, give it a machine client scoped to just this path then |

### Webapp

- `lib/rpc.ts` gains the request interceptor above: when the request carries a
  user (today: an `X-User-Id` header set by `buildHeaders` or by hand), it signs
  an assertion for that user, method and path and sets `X-User-Assertion`.
  Doing it in the interceptor covers the three hand-written headers
  (`lib/account.ts:34`, `lib/share.ts:70`, `lib/share.ts:75`) without editing
  them. **It keeps sending `X-User-Id`**, because it ships before the
  gatekeeper, which until then still needs the header.
- The interceptor never signs for `context.uid ?? ""` — an empty user sends no
  assertion and no header, which the gatekeeper treats as "no user".
- New settings: `DATAMAP_USER_ASSERTION_KEY` (PKCS#8 PEM, base64 in the env
  file) and `DATAMAP_USER_ASSERTION_KID`, in `frontend.env.sops`.
- **DataAmazon is the same codebase, deployed separately.** `DataAmazon BFF -
  PROD` is this same webapp deployed with its own configuration, not a second
  repository. PR 4 covers both: each deployment generates its own key pair and
  gets its own `kid`, carried in its own `frontend.env.sops` (DataMap's and
  DataAmazon's), so one deployment's key never verifies the other's
  assertions.
- Calls made before a session exists — the NextAuth `jwt` callback's
  `getUserByUID` (`pages/api/auth/[...nextauth].ts:128`) included — sign for the
  user id the gatekeeper just returned from `/auth/login`, sign-up confirmation
  or the provider lookup. That is the BFF trusting the gatekeeper's answer, which
  is correct; it is also why a compromised BFF can assert anyone.
- **API tokens** in the profile: list, create (shown once), revoke, through
  `BFFAPI` and BFF routes under `pages/api/users/tokens`, a Formik form, SWR for
  the list.
- **Cleanup, after the gatekeeper ships:** `buildHeaders` and the three
  hand-written calls pass the user as an axios config field the interceptor
  consumes, so no request leaving the BFF carries `X-User-Id`; the uploader
  stops sending it to tusd; the Jest tests and the two diagrams in the audit
  table follow.

### Archivist

No code change. The archivist's client (`archivist 2026-09`) gets
`scope_internal`; it never sent a user and never will.

The zipper is out of scope for this RFC entirely; see *Out of scope*.

### Existing direct API clients

The production `clients` table has eleven rows. Names and truncated ids only —
no secrets, no full UUIDs:

| Name | Classification | Action at deploy |
|---|---|---|
| DataMap BFF - PROD 2026-09 | BFF, acts as users | `scope_bff`, `acts_as_users = true`; its own key pair and `kid` |
| DataAmazon BFF - PROD | BFF, acts as users | `scope_bff`, `acts_as_users = true`; its own key pair and `kid`, in its own `frontend.env.sops` (*Webapp*) |
| archivist 2026-09 | Machine | `scope_internal` |
| Caio Maia - API Credentials | Personal API access | told beforehand, then disabled once a PAT replaces it |
| Danielle S. Monteiro - 5726dcb3-… - API access | Personal API access | told beforehand, then disabled once a PAT replaces it |
| Adriano Almeida - API | Personal API access | told beforehand, then disabled once a PAT replaces it |
| Jeaneth Machicao - b2c91e37-… - API access | Personal API access | told beforehand, then disabled once a PAT replaces it |
| Workshop on Data Science - Oct/24 | Likely stale | `scope_bff` (migration default) until the owner confirms it unused, then disabled |
| 3B93A51A-ACE0-4D40-B5AA-C203B6CE3F0E | Likely stale (bare UUID) | `scope_bff` (migration default) until the owner confirms it unused, then disabled |
| archivist | Likely stale (older duplicate of "archivist 2026-09") | `scope_bff` (migration default) until the owner confirms it unused, then disabled |
| DataAmazon BFF | Likely stale (older duplicate of "DataAmazon BFF - PROD") | `scope_bff` (migration default) until the owner confirms it unused, then disabled |

The BFF and the archivist are never one row; the scope migration maps every
row above **by name** (*Migration and seed*).

**The two BFF rows** are the same `datamap-webapp` codebase, deployed twice
with different configuration — `DataAmazon BFF - PROD` is not a second
repository. Each deployment keeps acting as users through the assertion, with
its own key pair and `kid` in its own environment; the webapp PR covers both
(*Delivery*).

**The machine row** (`archivist 2026-09`) gets `scope_internal` and nothing
else changes.

**Personal API access** — the four named people and Caio Maia — move to
personal access tokens. Each is told before the deploy: the date, that their
client secret stops acting as a user, and how to create a token. Their client
rows are disabled once they confirm the move.

**Likely stale** — the two undated duplicates, the bare-UUID row and the
workshop row — are proposed for disabling at the deploy. The `clients` table
has no `last_used` column (`app/model/db/client.py:10-28`), so staleness is
checked in the access log and `datamap_requests_total` by client name, not a
column; the owner confirms each one is actually unused before it is disabled,
not after.

A client row used by a person or an outside script with `X-User-Id` stops
working as a user at the deploy regardless of its classification above: it
does not get `acts_as_users`, and a bare `X-User-Id` answers `401
user_id_header_rejected`.

### Rollout

One ordered deploy. Deployments already cause downtime (the README says so), so
the gatekeeper step happens inside that window and there is no compatibility
mode to remove later.

| Step | What ships | Effect |
|---|---|---|
| 0 | Before the window: both deployments' key pairs are generated, each private key and `kid` goes into its own `frontend.env.sops` (DataMap's and DataAmazon's), the five personal-API-access holders have been told the date | — |
| 1 | **Webapp** (PR 4), deployed to both the DataMap and DataAmazon environments: signs every user call, still sends `X-User-Id` | None visible. Today's gatekeeper ignores `X-User-Assertion` |
| 2 | **Gatekeeper** (PRs 1–3), in the downtime window: the migration runs at startup; the operator then sets `acts_as_users` and inserts both deployments' public keys (runbook) before traffic is let back in | Assertions required; `X-User-Id` refused or ignored; scopes enforced; PAT routes and the Swagger bearer field live |
| 3 | **Webapp** (PRs 5–6), straight after: API tokens in the profile, `X-User-Id` no longer leaves the BFF | External users can create tokens |

Between 2 and 3 external users have no way in; that gap is minutes and inside
the announced window.

Scopes ship enforced with the gatekeeper: the migration grants every existing
client the scope matching its known routes, and a client that is refused shows
up as `client_out_of_scope` within minutes — the archivist dispatches email
every minute, each BFF calls constantly. The BFF and the archivist do not
share a row (*Existing direct API clients*), so the deploy does not wait on
that.

**Watching it.** `datamap_auth_failures_total` by `reason` for the hour after
the deploy: `assertion_*` points at the BFF or its key, `client_out_of_scope`
at a misclassified client, `user_id_header_rejected` at an external user who
did not move.

**Rolling back** is redeploying the previous gatekeeper image. The migration
only adds a column and tables, which the old code ignores, so no downgrade is
needed; the step-1 webapp works against both. Step 3's cleanup is the one
that cannot run against the old gatekeeper, which is why it waits for step 2.

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

Each deployment rotates independently — DataMap's and DataAmazon's keys are
different rows under different client keys; rotating one never touches the
other.

Client *secret* rotation is unchanged. Rotating one does not require rotating
the other. PATs are not rotated by operators: they expire, and their users make
new ones.

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
half. To replay one, an attacker must have seen it — in transit between a BFF
and the gatekeeper, or in a log — *and* hold that BFF's client secret, which
travels in the same request. The assertion is redacted from every log (below).

Today every BFF reaches the gatekeeper over the internal network — the same
host, as *Clock skew* notes — not the public `/api/v1`. The 60-second lifetime
and the method/path binding are what stands between a captured assertion and
a replay; nothing about today's network path does that job, and nothing here
assumes it always will. If a BFF is ever moved to reach the gatekeeper over
the public network, revisit whether a `jti` store is still deferrable.

We do **not** keep a `jti` store in this version, and that is settled, not
open: two gatekeeper instances would need it in PostgreSQL, one insert per
request, plus cleanup, to turn "repeat this exact request within a minute"
into "nothing". The `jti` claim stays in the assertion only because it is
logged on every verified request (*Metrics and logging*); if that logging
ever stops, drop the claim too. See *Out of scope*.

A PAT is a bearer credential and is replayable by design until it expires or is
revoked; that is what its expiry, read-only flag, scope and revocation are for.

### Integration test client

**It signs assertions with a test key; it does not use PATs.** The suite acts
as many users — `AuthFixture.custom_headers(user_id=…)`, `headers_for(user_id)`
in `fixtures/embargo.py:21-30`, users created mid-test — and its traffic should
look like the BFF's, which is how every screen reaches the gatekeeper. PATs
would need a token minted per user before each test, through a route that
itself needs an assertion, and would test the less-used path everywhere.

- The seed registers a test key pair: the public key in
  `client_assertion_keys`, `acts_as_users = true`, `scope_bff`. The private key
  lives in `tests/integration/config.py` with a name that says it is a test key;
  it is generated for the suite and matches nothing in any environment.
- `HttpClient._make_request` (`tests/integration/utils/http_client.py:36-57`) is
  the one place every request passes through. It takes the `X-User-Id` out of
  the headers, signs an `X-User-Assertion` for that user, method and path, and
  sends the assertion only, so the more than 500 uses of `AuthFixture` stay as
  they are and no test passes because the header slipped through.
- A `raw=True` argument skips the signing, for the tests that must send a bare
  header, a forged assertion or someone else's `kid`.
- PATs get their own module: tokens are created through the token routes with
  an assertion, then used alone.
- The seed also inserts one PAT for the seeded user, with a fixed test value,
  so the shell readiness poll in `CLAUDE.md` stays a one-line `curl`: it polls
  `GET /api/v1/datasets` with that token (`/clients` is out of a PAT's scope)
  until `200`, which also proves the Casbin rows, `scope_pat` included, are
  loaded. `CLAUDE.md` is updated with it.
- A second seeded client with `scope_internal` and no `acts_as_users` stands in
  for the archivist, so the scope tests do not depend on the archivist
  repository.

### Metrics and logging

Metrics:

| Metric | Labels | Purpose |
|---|---|---|
| `datamap_auth_failures_total` (existing, `app/metrics.py:209-214`) | new `reason` values: `client_out_of_scope`, `assertion_not_allowed`, `assertion_invalid`, `assertion_expired`, `user_id_header_rejected`, `ambiguous_credentials`, `pat_invalid`, `pat_expired`, `pat_revoked`, `pat_out_of_scope`, `pat_read_only` | added to `AUTH_REASONS` (`app/metrics.py:34`), or they collapse into `other`. This is what the deploy is watched by |
| `datamap_requests_total` (existing) | `client` = the client's name, or `pat` for every PAT request | how much direct API traffic there is. Never a token id: unbounded |

`kid`, `jti` and `pat_id` are never labels. Abuse is visible without a rate
limiter: `last_used_at` per token and `pat_id` on every access-log line and
every refusal let an operator single out one token making far more requests
than its name suggests, without a Prometheus label carrying an identifier.

Logging, following the rules in `CLAUDE.md`:

- `assertion` joins `_SECRET_WORDS` (`app/logging_config.py:15`), so a header or
  field carrying one is redacted by the filter. `authorization` is already
  there, which covers the bearer header. The code never logs either in the
  first place.
- Refusals log named fields through `fields()`: `client`, `route`,
  `reason`, `kid`, `jti`, `pat_id`, `iat_skew_s`, `request_id`. Never the token,
  never the whole header set.
- The access log's `user_id` (`app/setup.py:193`) today records the *claimed*
  header. It records the principal's user instead, plus `user_id_source`
  (`assertion`, `pat`, `upload_token`) and `pat_id` when there is one, so the
  log says who was authorized and how we know.

### Configuration

| Setting | Where | Notes |
|---|---|---|
| `DATAMAP_USER_ASSERTION_KEY` | webapp | PKCS#8 PEM, base64; private |
| `DATAMAP_USER_ASSERTION_KID` | webapp | must name an unrevoked row of the BFF client |
| `AUTH_PAT_MAX_DAYS` | gatekeeper | default 365, the ceiling. No rate-limit setting exists (see *Out of scope*) |

The gatekeeper gains no secret.

### Migration and seed

One Alembic revision:

- adds `clients.acts_as_users`, `client_assertion_keys` and
  `personal_access_tokens`;
- inserts the `scope_internal`, `scope_bff`, `scope_pat` and `tokens_admin`
  policies, and the grouping that gives the subject `pat` `scope_pat`;
- grants scopes to existing clients **by name**, from the mapping in
  *Existing direct API clients*: `scope_internal` for the archivist,
  `scope_bff` for both BFF deployments and, until the owner confirms otherwise,
  for the four likely-stale rows. It grants nothing to the five
  personal-access rows, which are disabled once each owner has been told and a
  PAT replaces the client. A row the mapping does not name gets `scope_bff`,
  which is exactly what every client can do today minus `/internal` — so the
  migration narrows access and never widens it — and is logged so an operator
  decides;
- does not set `acts_as_users` or insert keys: those are production values,
  set by the operator from the runbook during the deploy window (*Rollout*,
  step 2).

`tests/integration/fixtures/seed_clients.sql` gains the scope grants, the test
key, `acts_as_users` on the test client, the internal-only client and the
seeded PAT. Casbin reloads every five seconds, so the suite waits for the
seeded rows as `CLAUDE.md` describes, with the PAT poll above.

### Security notes

| Threat | Defence |
|---|---|
| A leaked machine secret (archivist, zipper) acting as a user | `acts_as_users` is false; assertions refused; `X-User-Id` refused |
| A leaked machine secret reaching user routes or client-only routes | scope: `/internal/*` only |
| A leaked BFF secret acting as a user | no signing key, no assertion; `X-User-Id` refused |
| A leaked BFF secret reaching `/internal/*` | `scope_bff` excludes it |
| A captured assertion | bound to `iss`, method and path; about a minute; redacted from logs |
| One client's key used with another client's secret | `kid` must belong to the authenticated client; `iss` must equal its key |
| A long-lived assertion from a misconfigured signer | `exp - iat` capped at 120 s by the verifier |
| Algorithm confusion | the verifier fixes `ES256`; the header's `alg` is not trusted |
| A leaked gatekeeper database or environment | holds public keys, secret hashes and PAT hashes only; cannot mint assertions or recover a token |
| Claiming another user's invitations | claim requires path user = asserted user |
| A TUS hook naming another user | the user is the signed upload token's `sub`; the header is ignored |
| A leaked PAT | that user only, `GET` only if read-only, until expiry (at most 365 days) or revocation; the prefix lets secret scanners flag it; `last_used_at` and Activity show its use |
| A leaked PAT belonging to an admin | the same blast radius as a leaked admin session: every admin route. `/internal`, `/tus`, `/auth`, `/clients` and the token routes stay out of reach regardless of role — see *Personal access tokens* |
| A PAT used to mint or extend tokens | token routes are outside `scope_pat` |
| A PAT of a demoted or disabled user | roles are read live; `is_enabled` is checked on every request |
| A PAT guessed or brute-forced | 256 random bits — nothing short enough to guess; no rate limit backs this up (see *Out of scope*) |
| A PAT sent with a client secret to borrow the client's scope | `401 ambiguous_credentials` |

#### Residual risk

- **A compromised BFF host** — DataMap's or DataAmazon's deployment — holds its
  private key, its client secret and `NEXTAUTH_SECRET`. It can assert any
  user, admins included. This RFC does not change that, and does not make one
  deployment's compromise reach the other: each holds a different key pair
  and a different client row. Narrowing it further means the gatekeeper
  issuing user sessions itself, which is in *Alternatives considered*.
- **The BFF is also the sign-in authority for ORCID.** It decides which ORCID iD
  signed in and asks the gatekeeper for that user, so even gatekeeper-issued
  sessions would trust the BFF for ORCID sign-in.
- **Replay within a minute** of an exact request, by someone who already sees
  the BFF-to-gatekeeper traffic, until a `jti` store exists.
- **A PAT is a bearer credential.** Whoever holds it is the user until it
  expires or is revoked; it is not bound to a machine or an address.
- **Client-only routes stay reachable with either BFF deployment's secret
  alone:** `POST /users`, the provider lookup, `/auth/*`, previews. The provider lookup still
  returns a user's roles to a holder of that secret, and `POST /users` still
  creates accounts. RFC 009 PR A removes the roles from creation; rate limits
  and a narrower lookup response are follow-ups.

## Testing

**Integration (gatekeeper):**

- the BFF-shaped client with a valid assertion reaches user routes as `sub`;
- the same request with only `X-User-Id` answers `401`
  (`user_id_header_rejected`) with the explanatory body;
- an assertion plus an `X-User-Id` naming someone else acts as `sub`;
- a forged signature, a wrong `aud`, another client's `kid`, a revoked `kid`, an
  expired assertion, `exp - iat` of 300 s, an assertion for another path or
  method: each `401`, each counted under its reason;
- the internal-only client: `/internal/*` works; a user route and `POST /users`
  answer `403 client_out_of_scope`; an assertion from it answers
  `assertion_not_allowed`;
- the BFF-shaped client on `/internal/notifications/dispatch`: `403`;
- the invitation claim for another user: `401`;
- a TUS hook whose `X-User-Id` names someone else is authorized as the token's
  `sub`; one with no `X-User-Id` at all succeeds;
- PATs: create (returned once, absent from the list), use alone on a user
  route, list, revoke then `401`; expired `401`; a read-only token on `PUT`
  `403`; a token on `/clients`, `/users/{id}/tokens` and `/internal/*` `403`
  regardless of role; a non-admin's token on `/admin/*` and
  `/users/{id}/roles` `403` from the route's own `authorize`, not from scope;
  an admin's token reaches both; a role removed from the user is refused
  within the reload; a disabled user's token `401`; a PAT plus `X-Api-Key`
  `401`; an admin revokes another user's token;
- `/api/openapi.json` declares the bearer scheme and no `X-User-Id` scheme;
- the access log line carries the authorized user, `user_id_source` and
  `pat_id`, and no assertion or token text.

Each of these is written to fail first against today's code, which accepts all
of the bare-header cases and has no token routes.

**Unit (gatekeeper):** path normalization (trailing slash, query string,
percent-encoding, `{name:path}` tenancy routes); skew boundaries; the principal
for each of the three paths; `parse_user_header` reads the principal, not the
header; PAT format, hashing and the `last_used_at` throttle; the migration's
name mapping never grants `admin`; `scope_pat` matches exactly the routes
listed in *Personal access tokens* — `/admin/*` and `/users/{id}/roles` are
not among them, so a non-admin's PAT on either is refused by `authorize`, not
by scope, and an admin's PAT passes both.

**Webapp (Jest):** the interceptor signs with method and normalized path; no
assertion for an empty user; the three hand-set headers get one; a verification
round-trip against the public key with `jose`'s `jwtVerify`. The token screen:
the token is shown once and cleared on close; the expiry choices; revoke.

## Delivery

| PR | Repository | Content |
|---|---|---|
| 1 | gatekeeper | Migration (clients, keys, scopes), `Principal`, assertion verification, `X-User-Id` removed from `parse_user_header`, the TUS hook and the access log, claim route check, metrics and reasons, redaction, seed, integration suite signing in `HttpClient`, unit tests moved to the principal, `cryptography` dependency, runbook section 8 and the deploy SQL |
| 2 | gatekeeper | Personal access tokens: table, bearer path in `authenticate`, `scope_pat`, token routes, Activity events, seeded PAT and `CLAUDE.md` poll, integration tests |
| 3 | gatekeeper | Swagger: bearer scheme, `X-User-Id` scheme removed |
| 4 | webapp | Assertion interceptor in `lib/rpc.ts` (still sends `X-User-Id`), `jose`, settings, Jest tests. Deployed twice — to the DataMap and DataAmazon environments — with a key pair and `kid` of its own per deployment |
| 5 | webapp | API tokens section in the profile |
| 6 | webapp | Cleanup: `X-User-Id` no longer leaves the BFF or the uploader; tests and diagrams |

The archivist needs no PR; the zipper is out of scope (see *Out of scope*). PR
4 is deployed before PRs 1–3 reach production; 1–3 deploy together; 5 and 6
deploy right after (*Rollout*). PRs 1–3 can be reviewed and merged in any
order as long as they are not deployed before 4.

### Before the deploy

- The production client rows are mapped to a scope, per *Existing direct API
  clients*; the owner has confirmed each likely-stale row is actually unused
  and signed off on disabling it.
- The five personal-API-access holders — the four named people and Caio Maia —
  have been told the date, that their client secret stops acting as a user,
  and how to create a token.
- Both deployments' key pairs exist: each private key is in its own
  `frontend.env.sops` and PR 4 is deployed to both the DataMap and DataAmazon
  environments; the public-key SQL for both is ready in the runbook.
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

### An observe mode before enforcing

A setting that accepts and counts bare `X-User-Id` for a week before refusing
it. It finds unknown callers without breaking them, at the price of a second
deploy and a week in which the hole stays open. Deploys already take the system
down, the known callers are all in the audit table, and the unknown ones are
outside users who are told in advance. Dropped at the owner's review.

### Per-person clients with `X-User-Id` bound to one user

Give each outside user their own client, scoped to themselves. It keeps two
secrets where one would do, the client screens are admin-only so a user cannot
make one, and nothing marks it read-only or expires it. PATs are the same idea
done properly.

### OAuth 2.0 for direct API access

Authorization code with PKCE, access and refresh tokens, client registration
and consent. It needs an authorization server — an authorize endpoint, a
consent screen, registered redirect URIs, refresh-token rotation and its reuse
detection — and only pays off when a third-party application acts for users
*other than its author*, which nobody does today. A researcher's own scripts
and the Swagger UI are served by a PAT with GitHub-like UX: make it on a page,
paste it, done. OAuth stays open: its access tokens would arrive as
`Authorization: Bearer` too, and the bearer branch in `authenticate` dispatches
on the token's prefix, so an OAuth layer adds a branch rather than a second
path. For a command-line tool, the device authorization grant (RFC 8628) is
the natural first OAuth flow: the CLI shows a code, the user approves it in
the webapp, and no token is ever pasted.

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
- **The zipper.** It is not deployed and this RFC changes nothing about it.
  Its tracked config (`zipper/local_config.yml`, `zipper/staging_config.yml`)
  commits a client key and secret; that key must never be enabled in any
  environment, and it is not one of the eleven rows in *Existing direct API
  clients* — none of them is the zipper's. When the zipper is deployed it
  gets its own client, `scope_internal`, and a real callback route, as its
  own change.
- A `jti` replay store (see *Replay*).
- Rate limiting personal access tokens, per-token or otherwise. `last_used_at`
  and the `pat_id` on every access-log line and refusal already make heavy use
  of a single token visible (*Metrics and logging*); a limiter is a follow-up
  if that turns out not to be enough. The 365-day maximum expiry stays.
- Rate limits on `POST /users` and `/users/providers/...`, and trimming the
  lookup's response.
- **The rest of the TUS hook path.** The user now comes from the upload token
  alone, but `/api/v1/tus/hooks` is still reachable through the public
  `/api/v1` location, has no client authentication, and trusts a token the
  browser holds for a day. Anyone can post a hook *as themselves* with their
  own token. It deserves its own change: an nginx `deny` for the path from
  outside, and a shared secret or client for tusd.
- An nginx `deny` for `/api/v1/internal`.
- OAuth, including the device flow (see *Alternatives considered*).
- PAT scopes finer than read-only (per route or per dataset).

## Open questions

- **Are the four likely-stale client rows actually unused?** The proposal in
  *Existing direct API clients* is to disable them at the deploy. The
  `clients` table has no `last_used` column, so this is checked in the access
  log and `datamap_requests_total` by name, not a column; the owner confirms
  each row individually before it is disabled, not after.
