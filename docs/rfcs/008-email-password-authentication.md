# RFC 008: Email and password authentication

| Status | Draft |
|--------|-------|
| Author | DataMap Team |
| Created | 2026-10-03 |
| Updated | 2026-10-03 |

## Summary

DataMap can only be signed into with ORCID. This RFC adds email and password as
a second way in, with the full account lifecycle around it: sign-up confirmed by
email, password reset, password change, and a notification to the DataMap
admins whenever an account is created and is waiting for a tenancy.

The decisions that shape everything else:

1. **One person, one account.** Every account carries a confirmed, unique email
   and that email is the identity. A sign-in method — password or ORCID — is
   attached to an account only by someone who proves they read that inbox.
2. **ORCID sign-in requires a confirmed email.** ORCID does not reliably give us
   one, so the person types it and confirms it. This also retires the
   `@fake.mail.com` placeholders: every existing account without a confirmed
   email confirms one on its next ORCID sign-in, and cannot continue until it
   does.
3. **Email confirmation is a 6-digit numeric code typed in the same screen that
   asked for it, not a link.** A link lets an attacker attach their ORCID, or
   their password, to a victim's email the moment the victim clicks without
   reading. A code proves the inbox and the browser belong to the same person.
4. **Passwords are hashed slowly, once, off the event loop.** bcrypt at cost 10
   over a peppered HMAC, run in a threadpool, and only at sign-in. Commit
   e417840 removed bcrypt from API secrets because it ran on every
   request and blocked the loop; neither is true here.
5. **The gatekeeper owns accounts; the webapp owns screens.** Hashes,
   challenges, email and rules live next to the user table. The webapp's
   NextAuth credentials provider becomes a thin call to the gatekeeper.
6. **Admins are a list in configuration.** `ADMIN_NOTIFICATION_EMAILS` receives
   a message for every new account, from any sign-in method.

## Motivation

### Problem statement

Researchers without an ORCID iD cannot use DataMap at all, and those who have
one but prefer not to use it have no alternative. Institutional collaborators,
students and reviewers are the people most often turned away.

Separately, a large share of existing accounts have no real email: ORCID keeps
email addresses private by default ("Only me"), so the webapp stored
`<orcid>@fake.mail.com`. Those people never receive invitations, embargo
reminders or any other email the platform now sends.

### What exists today

- **Webapp.** `pages/api/auth/[...nextauth].ts` registers a `credentials`
  provider whose `authorize()` accepts any address ending in
  `@local.datamap.com` with a password of six or more characters, without
  calling the gatekeeper. The login page shows its form only in development,
  but **the provider is registered in production**, so a direct POST to
  `/api/auth/callback/credentials` creates a real user and a session. The
  GitHub provider has the same shape. There are no sign-up, confirmation,
  forgot-password or reset pages.
- **Gatekeeper.** `users` has no password and no verification state. There is
  no login endpoint. The gatekeeper trusts `X-User-Id` from the webapp, which
  authenticates as a client with `X-Api-Key`/`X-Api-Secret`.
- **Reusable pieces.** The email outbox with Jinja2 templates and
  `secret_fields` masking (RFC 003, *Email delivery and audit*); opaque tokens
  stored as SHA-256 hashes (`app/service/share_token.py`); bcrypt helpers in
  `app/service/secret.py`; Mailpit in the integration suite.

### Can ORCID give us the email?

Not reliably. With the `/authenticate` scope we use, the API returns only emails
the person made public. The `/read-limited` scope also returns emails marked
"Trusted parties", but it exists only on the Member API and still depends on the
person having changed the default. ORCID's public email is used to pre-fill the
confirmation field and nothing more.

### Goals

- Sign up, sign in, reset and change a password, with every email confirmed.
- One account per person across both sign-in methods, with no duplicates and
  no account merges.
- Every account ends up with a confirmed, real email.
- The admins learn about every new account without having to look.

### Non-goals

- Other identity providers. GitHub stays development-only.
- Merging two accounts that already exist. Detected and refused; see
  *Collisions*.
- Revoking open sessions on password change. Sessions are NextAuth JWTs; see
  *Out of scope*.
- Two-factor authentication.

## Technical design

### Database changes

`users` gains four columns:

| Column               | Type                     | Meaning                                    |
| -------------------- | ------------------------ | ------------------------------------------ |
| `password_hash`      | `String(128)`, nullable  | `null` means the account has no password   |
| `email_verified_at`  | `DateTime(tz)`, nullable | `null` means the email was never confirmed |
| `failed_login_count` | `Integer`, default 0     | consecutive wrong passwords                |
| `locked_until`       | `DateTime(tz)`, nullable | sign-in by password refused until then     |

The password does **not** become a `providers` row. A `credentials` provider
referencing the email would go stale on the first email change; "has a
password" is `password_hash is not null`.

A new table holds every pending confirmation and reset:

```
auth_challenges
  id             UUID primary key
  kind           enum: sign_up | email_verification | password_reset
  email          String(256), lower-cased
  secret_hash    String(128), unique
  attempts       Integer, default 0
  issued_at      DateTime(tz)          -- last time a code was sent; drives the resend cooldown
  expires_at     DateTime(tz)
  consumed_at    DateTime(tz), nullable
  confirmed_at   DateTime(tz), nullable -- set only by a successful confirmation
  user_id        UUID, nullable, FK users ON DELETE CASCADE
  payload        JSONB      -- what is pending: name, password hash, ORCID iD
  created_at     DateTime(tz)
```

- Codes are 6 numeric digits, `000000`–`999999`, from `secrets.randbelow`.
  They are stored as `HMAC-SHA256(AUTH_CHALLENGE_PEPPER, challenge_id || code)`:
  a million candidates is nothing offline, so the pepper, which is not in the
  database, is what protects a leaked table.
- Reset tokens are `new_token()` and stored with `hash_token()`, as invitations
  are.
- Codes live 15 minutes and allow 5 attempts. Reset links live 1 hour. All are
  single-use; a new challenge of the same kind for the same email consumes the
  previous one.

Every existing user starts with `email_verified_at = null`.

### Password hashing

```
password_hash = bcrypt(cost=10, base64(HMAC-SHA256(AUTH_PASSWORD_PEPPER, password)))
```

- **bcrypt at cost 10** is about 40 ms on production hardware (151 ms measured
  at cost 12 in e417840, halving per step). A human password has little
  entropy; a fast hash would let a leaked table be tested at billions of
  candidates per second.
- **The pepper** carries over the property e417840 relied on: a leaked table is
  useless without the environment.
- **base64 of the HMAC** keeps the bcrypt input at 44 bytes, under its 72-byte
  truncation and free of NUL bytes.
- **The hash runs in a threadpool** (`run_in_threadpool`), so a sign-in never
  blocks other requests.

Password policy: 10 to 128 characters, no composition rules.

### Endpoints

All are mounted under `/v1/auth` and require client credentials
(`authenticate`), not a user (`authorize`), except the password change. Every
response that could reveal whether an email has an account is identical for
both cases.

| Verb and path | Body | Response |
|---|---|---|
| `POST /auth/sign-up` | `{name, email, password}` | `202 {challenge_id}`, always |
| `POST /auth/sign-up/{challenge_id}/confirm` | `{code}` | `200 {user_id}` |
| `POST /auth/email-verifications` | `{orcid, email, name}` | `202 {challenge_id}`, always |
| `POST /auth/email-verifications/{challenge_id}/confirm` | `{code}` | `200 {user_id}` or `409` |
| `POST /auth/challenges/{challenge_id}/resend` | — | `202` or `429` |
| `POST /auth/login` | `{email, password}` | `200 {user_id}` or `401` |
| `POST /auth/password-reset` | `{email}` | `202`, always |
| `POST /auth/password-reset/confirm` | `{token, password}` | `204` |
| `PUT /users/{id}/password` | `{current_password, new_password}` | `204` or `401`; self only |

Code errors on the confirm endpoints are `400` with `code_invalid`,
`code_expired` or `code_attempts_exceeded`; the last two consume the challenge,
and a resend revives it with a new code. Validation errors are `400` with
`invalid_email`, `invalid_name`, `invalid_password` or `invalid_orcid`, raised
as `IllegalStateException` so the body is `{"detail": "<code>"}` like every other
error here (the `BadRequestException` handler answers a different shape).

#### Self-access

A new account has no Casbin role, so `authorize` would refuse it its own user.
`GET /users/{id}` and `PUT /users/{id}/password` skip Casbin when `{id}` equals
`X-User-Id`, and go through Casbin otherwise. The password change answers `401`
for anyone but the account itself, whatever their roles.

#### Sign-up

`POST /auth/sign-up` hashes the password, stores it in the challenge payload and
emails a code. Confirming:

- **Email has no account:** creates the user with `password_hash` and
  `email_verified_at = now()`.
- **Email has an account:** sets `password_hash` on it and confirms the email.
  The person who typed the code owns the inbox, which is exactly what a password
  reset proves.

#### Email verification (ORCID sign-in)

Called by the webapp when an ORCID sign-in finds no ready account. Confirming:

| ORCID iD has an account? | Email has an account? | Result                                                           |
| ------------------------ | --------------------- | ---------------------------------------------------------------- |
| yes                      | no                    | set the email on the ORCID account, confirm it                   |
| yes                      | the same account      | confirm it                                                       |
| yes                      | a different account   | `409 email_belongs_to_another_account`                           |
| no                       | yes                   | attach the ORCID provider to that account, confirm it            |
| no                       | no                    | create the user with the ORCID provider and the email, confirmed |

A disabled account holding the email also answers the `409`; ORCID is never
attached to a disabled account.

Changing a user's email through `PUT /users/{id}` clears `email_verified_at`.

#### Collisions

The `409` is the only case where two accounts already exist for one person: an
ORCID account with a placeholder email and another account holding the real
one. It is refused, not merged; the screen tells the person to contact the
DataMap team. Today almost every account came from ORCID, so this should be
rare.

#### Sign-in

`POST /auth/login` returns `401 invalid_credentials` for an unknown email, a
wrong password, an account without a password, an unconfirmed email or a
disabled account. When the email is unknown it still runs bcrypt against a fixed
dummy hash, so timing does not reveal which emails exist.

Ten consecutive failures set `locked_until = now() + 15 min`; a lock answers
`401` too, so it reveals nothing. A success or a reset clears both counters.
Expiry does not: the count stays at ten, so the first wrong password after a
lock ends locks the account again. The failures are consecutive until a
success says otherwise.

#### Password reset

Sends the link `{PUBLIC_BASE_URL}/account/reset-password/{token}` only when the
account exists and its email is confirmed. Confirming consumes the link
atomically before anything else, so a double submit sets one password and the
second answers `token_invalid`; it then sets the password, clears the lock and
consumes every other open `password_reset` challenge of that user.

The request answers the same `202` for every address, but it does not burn
equal time: a known, confirmed address costs a few more database round trips
than an unknown one. Only sign-in carries the dummy-hash timing guarantee.

#### Rate limits

- Resend: once per 90 seconds per challenge, `429 resend_too_soon` otherwise.
  It works on any challenge not yet confirmed — expired, out of attempts or
  replaced — and issues a new code with fresh attempts and expiry. A confirmed
  challenge answers `404 challenge_not_found`.
- At most 5 code or link emails per address per hour, resends included,
  counted from the outbox. Past that the `202` is still returned and no email
  is sent.

### Delivery

Auth emails go through the outbox like every other email and leave on the
Archivist's dispatch, every minute in production. The 90-second resend cooldown
gives the first code a dispatch cycle to arrive before a resend replaces it,
and the code screen says the email can take up to a minute.

### Notifications

New templates in `app/resources/email_templates/`, in English like the existing
ones, with the code or token in `secret_fields`:

| Template | Sent to | Content |
|---|---|---|
| `sign_up_code` | the person | the code; "if this wasn't you, ignore it" |
| `email_verification_code` | the person | the code and the ORCID iD being linked |
| `password_reset` | the person | the link, valid 1 hour |
| `new_account_pending` | `ADMIN_NOTIFICATION_EMAILS` | name, email, sign-in method, creation time |

`new_account_pending` is enqueued from `UserService.create`, so it fires for
every path that creates a user — password, ORCID, or `POST /users` — one
message per admin, with `dedup_key = new_account_pending:{user_id}:{address hash}`
(the column is unique, so a key per user would reach only the first admin).

### Configuration

| Setting | Notes |
|---|---|
| `AUTH_PASSWORD_PEPPER` | at least 16 characters; changing it invalidates every password |
| `AUTH_CHALLENGE_PEPPER` | at least 16 characters |
| `ADMIN_NOTIFICATION_EMAILS` | comma-separated; empty disables the notification |

### Webapp

#### Session

- **Password.** The credentials provider's `authorize()` calls
  `POST /auth/login` and returns the gatekeeper `user_id`; the `jwt` callback
  hydrates with `getUserByUID`. The `@local.datamap.com` shortcut is removed;
  local development uses the real flow and reads codes from Mailpit.
- **ORCID.** On sign-in, if the ORCID iD has no account, or its account has no
  confirmed email, the token gets `pending: {orcid, name}` and **no `uid`**.
  `_app` sends a pending session to `/account/confirm-email`. After the code is
  confirmed the page calls `update()`, and the `jwt` callback looks the ORCID iD
  up again — the one already in the token, never one sent by the browser.
- **`middlewareChain` requires `uid`.** Today `auth` only checks that a token
  exists, so a pending token would reach the gatekeeper with no `X-User-Id`.
- **Token version.** Tokens carry a version claim. A token without it, issued
  before this change, is signed out, so open sessions cannot skip the
  confirmation.
- **GitHub and the credentials stub** are registered only when
  `NODE_ENV === "development"`. This ships first, on its own.

#### Screens

Public pages follow the invitation pages: `BareLayout`, a centred 560 px
column, Formik with Yup, `btn-primary`, inline errors with `role="alert"`,
English copy.

| Route | Content |
|---|---|
| `/account/login` | Tabs **Sign in** and **Create account**, selected by the existing and currently ignored `phase` parameter. Sign in: ORCID button, "or" divider, email and password, "Forgot password?". Create account: ORCID button, divider, name, email, password; on submit the tab shows the code step. |
| `/account/confirm-email` | For a pending ORCID session. Email field pre-filled from ORCID's public email or the account's current real one, then the code step. The `409` reads "This email belongs to another DataMap account. Contact the DataMap team." |
| `/account/forgot-password` | Email field; "If an account exists, we sent a link." |
| `/account/reset-password/[token]` | New password and confirmation, then to sign-in. |

**`CodeInput`** (`components/Account/CodeInput.tsx`) — six single-digit boxes,
no library:

- digits only; typing moves to the next box;
- Backspace on an empty box moves back; arrow keys move between boxes;
- pasting a code fills all six;
- `inputMode="numeric"`, and `autocomplete="one-time-code"` on the first box;
- submits when the sixth digit is entered;
- each box labelled "Digit n of 6".

**`VerificationCodeForm`** wraps it for sign-up and email verification, with
"Resend code" behind a 90-second countdown and the messages "Invalid code",
"Code expired, request a new one" and "Too many attempts".

**Profile, "Sign-in methods":**

- **Password:** "Change password" (dialog with the current and new password)
  when the account has one; otherwise "Set a password", which sends the reset
  link to the confirmed email — no new endpoint.
- **ORCID:** "Connect ORCID" when absent. It starts an ORCID sign-in, which
  lands on email verification and attaches the iD to this account because the
  email is already its own.

#### BFF

Routes under `pages/api/account/` proxy one-to-one to the endpoints above; all
are public except `password`, which uses `authOnlyChain`. Matching `BFFAPI`
methods, route constants in `InternalRoutesConstants.ts`, messages in
`AccountConstants.ts`.

### Security notes

| Threat | Defence |
|---|---|
| Account enumeration | identical `202`s; one `401` for every sign-in failure; dummy bcrypt |
| Linking an attacker's ORCID or password to a victim's email | codes typed in the initiating screen, not links |
| Online password guessing | 10-failure lock, 15 minutes |
| Code guessing | 5 attempts per code, 15-minute lifetime, 5 codes per email per hour |
| Leaked database | peppered bcrypt for passwords, peppered HMAC for codes, SHA-256 for reset tokens |
| Pending session reaching the API | `middlewareChain` requires `uid` |
| Codes or tokens in logs or the admin email view | `secret_fields` masking; log named fields only |

## Testing

**Integration (gatekeeper)**, against Mailpit:

- each flow end to end: sign-up for a new and an existing email, every row of
  the email-verification table, sign-in, reset, change;
- wrong, expired, exhausted and reused codes; resend cooldown; the per-email
  hourly cap;
- identical responses for existing and unknown emails;
- the lock after ten failures and its reset;
- `new_account_pending` on all three creation paths, and none when the list is
  empty.

**Unit (gatekeeper):** hashing round-trip and pepper dependence; code
generation range and format.

**Webapp (Jest):** `authorize()`; provider mapping and the `pending` state in
the `jwt` callback; the token version check; `middlewareChain` refusing a token
without `uid`; `CodeInput` typing, Backspace, paste and auto-submit;
the sign-up, confirm-email and reset forms.

## Delivery

| PR | Repository | Content |
|---|---|---|
| 0 | webapp | Register GitHub and credentials providers only in development |
| 1 | gatekeeper | Migration, `/v1/auth/*`, password change, templates, admin notification, tests |
| 2 | webapp | Password sign-in and sign-up, forgot and reset, `CodeInput`, change password |
| 3 | webapp | ORCID pending state, `/account/confirm-email`, `uid` in `middlewareChain`, token version, profile links |

PR 1 can ship before the webapp uses it; only the admin notification is
visible, and it starts with ORCID sign-ups. PR 3 is the one that changes the
experience of existing users.

### Before shipping PR 3

- Email must be enabled and delivering in production. Otherwise no ORCID user
  can finish signing in.
- `AUTH_PASSWORD_PEPPER`, `AUTH_CHALLENGE_PEPPER` and
  `ADMIN_NOTIFICATION_EMAILS` set in production.
- All three flows exercised in staging with real email.

## Alternatives considered

### Confirmation links instead of codes

The usual pattern, rejected for the reason in decision 3: a link attaches
whatever the requester chose to whoever clicks it. Reset keeps a link because
the new password is chosen at the moment of the click, by the clicker.

### A fast hash for passwords

Requested to avoid a repeat of the slow API-secret checks. The slowness there
came from hashing on every request inside `async def`; here it is once per
sign-in, in a threadpool. A fast hash over low-entropy input gives an attacker
with the table everything.

### Reading the email from ORCID

Covered in *Can ORCID give us the email?*. Used only to pre-fill.

### Signing in with the password to link ORCID

The first shape of the ORCID screen offered "I already have an account: sign in
to link". It excludes ORCID-only accounts with a real email and adds a second
credential check where a code already proves ownership.

### Admins from the Casbin `admin` role

Self-maintaining, but depends on admins having real emails — the problem this
RFC fixes — and on the role meaning "who grants tenancies" in production.

### NextAuth's email provider, or an external identity provider

The first duplicates the email outbox in the webapp and moves account rules
away from the user table. The second is another service to run and a migration
of providers and Casbin subjects, out of proportion to the problem.

## Out of scope

- Revoking sessions on password change or reset; would need a server-side
  session list or a per-user token version.
- Changing the email of an account from the profile.
- Merging two existing accounts.
- Two-factor authentication.
- An admin screen for granting tenancies; the notification links nowhere yet.

## Open questions

- Is DataMap's ORCID integration on the Member API? If so, `/read-limited`
  would pre-fill more emails. It does not change the flow.
