# RFC 006: Internationalization (pt-BR and English)

| Status | Draft |
|--------|----------|
| Author | DataMap Team |
| Created | 2026-10-01 |
| Updated | 2026-10-08 (rewritten against RFC 003, 008 and 009 as built; terminology settled) |

## Summary

DataMap speaks only English: every page of datamap-webapp, every error the
gatekeeper returns, and every email the outbox sends. Most of its users are
Brazilian researchers. This RFC makes the platform available in **Brazilian
Portuguese and English**, with Portuguese as the default, and makes each
person's language a stored preference that the site, the emails and the
notebooks (RFC 007) all follow.

Six decisions shape it:

1. **Two locales, `pt-BR` and `en`, and `pt-BR` is the default.** It is used
   whenever nothing better is known.
2. **The language is not in the URL.** A link means the same page in every
   language, so dataset links, DOI landing pages, invitation and anonymous
   links are unaffected.
3. **The language is detected, then remembered.** A first visit follows the
   browser's `Accept-Language`. When an account is created, or the first time
   an existing account signs in after this ships, the detected language
   becomes the account's preference. The person can change it at any time.
4. **One cookie is what a page reads.** `NEXT_LOCALE` is set by the middleware
   on a first visit, overwritten with the account's preference at every
   sign-in, and written by the language switcher. Pages never consult the
   session or the gatekeeper to know the language.
5. **The webapp uses `next-intl`.** Messages live in JSON catalogs, one file
   per feature area per locale, so several people — or agents — can translate
   different areas at the same time without touching the same file.
6. **Every email is rendered in a locale chosen when it is enqueued and stored
   on its row**, with gettext catalogs compiled by Babel. Templates hold the
   sentences; callers pass data, not prose.

## Motivation

### Problem statement

The platform's audience is mostly the AmazonFace and USP research community,
and its interface is in a language many of them read slowly. The emails that
went live with RFC 003, 008 and 009 — embargo reminders, sign-up codes,
password resets, workspace access decisions, the message that explains what a
registered-but-not-findable DOI means — are exactly the texts that must be
understood on the first read, and they are in English.

### What exists today

**datamap-webapp** (`origin/main` at #114):

- Pages Router only, no i18n library. `pages/_document.tsx` hardcodes
  `<Html lang="en">`.
- 37 pages and 169 component files, with roughly **1,250 inline user-visible
  strings** plus about 130 more in `contants/AccountConstants.ts`,
  `AdminConstants.ts`, `EmbargoConstants.ts`, `TenancyConstants.ts`,
  `ShareConstants.ts` and in `lib/*Display.ts` helpers.
- Dates are formatted with `toLocale*` (7 calls, some with an explicit
  `timeZone: "UTC"` for embargo dates), with `react-moment` (5 files), and
  with hand-rolled relative time and plurals in `lib/adminDisplay.ts`.
- Yup validation messages in 22 components and `lib/accountValidation.ts`.
- **Backend error codes are already mapped to English in four places**:
  `ACCOUNT_ERROR_MESSAGES`, `ADMIN_ERROR_MESSAGES`, `EMBARGO_ERROR_MESSAGES`
  and `TENANCY_ERROR_MESSAGES`, each with its own fallback.
  `lib/datasetVersionCreation.ts` and `lib/requestErrorHandler.ts` still
  compose English sentences around a backend detail.
- 80 component test files make about 1,100 text-based queries
  (`getByText`, `getByRole({ name })`) against the English copy.
- `.eslintrc.json` exists, but there is no `lint` script and CI does not lint.
- The footer is rendered only by `components/Layout.tsx` (public pages). The
  signed-in app (`LoggedLayout`), the bare pages (`BareLayout`: account,
  invitations, anonymous links, DOI) and the login page have none.

**Sign-in and account creation** (RFC 008, 009):

- Sign-in is email and password or ORCID; GitHub and the credentials stub
  exist only in development. Neither production method gives a language, so
  the browser's `Accept-Language` is the only automatic signal.
- Accounts are created in three places: `POST /users/` (development GitHub),
  `AccountService.confirm_sign_up` and
  `AccountService.confirm_email_verification` (ORCID with a confirmed email).
  The last two read what to create from `auth_challenges.payload`, written
  before the account exists.
- NextAuth already uses the advanced initialization
  (`NextAuth(req, res, authOptionsFor({ req, res }))`), so the callbacks can
  read and write cookies. Users are hydrated in `hydratePasswordSignIn`,
  `finishOrcidSignIn`, `refreshPendingSignIn` and `hydrateWithUserInfo`.

**gatekeeper** (`origin/main` at #148):

- `users` has no language column. `Accept-Language` is not read anywhere.
- Self-service user routes follow `PUT /users/{id}/...` guarded by
  `authorize_self` or `authorize_self_or_policy`
  (`app/controller/interceptor/authorization.py`); `PUT /users/{id}/password`
  is the model.
- Most errors are codes, roughly sixty of them since RFC 003, 008 and 009.
  Five details are still English prose: `"Snapshot not found"`,
  `"Invalid snapshot data"` (`dataset_snapshot.py`), `"Invalid client input"`,
  `"Internal server error"` (`exception_handler.py`) and `"Unauthorized"`
  (`interceptor/authentication.py`). There is no list of codes.
- Server-made text reaches the UI in a few places: the invitation preview
  returns `inviter_name = "A DataMap user"` and `owner_name = "the owner"`
  (`share.py`), and the public tenancy's `display_name` is stored as
  `'Public'`.

**Email** (RFC 003's outbox, built in #131):

- 16 templates in `app/resources/email_templates/`, 12 with a `.txt` twin,
  on `base.html`/`base.txt` and `_transactional.{html,txt}`. `base.html` says
  `lang="en"`.
- `EmailService.enqueue` renders at enqueue and stores `subject` and
  `body_text`; dispatch **renders the HTML again** from the stored `context`
  (`email.py`, `_mime`). `context` is JSONB.
- Dates arrive in `context` already formatted in English by
  `app/service/email_format.py` (`long_date`/`short_date` use `%B`, which
  follows the process locale) and by `tenancy_notifier.py`
  (`"<date> at HH:MM UTC"`).
- Several sentences are written in Python and passed as context:
  `_access_granted_context` in `share.py` (title, message, reason, labels,
  button), the admin test message in `email.py`, `"A DataMap user"`,
  `"the owner"`, `["You"]` in `notification.py`. Plurals and list joins
  (`", "`, `" and "`) are inline in `embargo_reminder.{html,txt}`.
- Recipients are of four kinds: existing accounts; an address with no
  account yet (sign-up code, ORCID verification code, dataset invitation);
  addresses from `ADMIN_NOTIFICATION_EMAILS`, which may not be accounts; and
  existing accounts reached through an unauthenticated request (password
  reset, `sign_up_existing_account`).

**Already waiting on this RFC:** RFC 007 sends a `locale` when it starts a
notebook session and expects `messages/<locale>/notebooks.json`; RFC 010 puts
its profile section "through next-intl (RFC 006)". RFC 008 and 009 specify
their emails and screens "in English".

### Goals

- Every screen of the webapp, public and signed-in, in `pt-BR` and `en`.
- Every email in the recipient's language, with dates and plurals correct in
  that language.
- A language that is right on the first visit without asking, and a visible
  way to change it on every layout.
- One stored preference per account, read by the webapp, the emails and the
  notebooks.
- A catalog that cannot silently fall behind: a key present in one locale and
  missing in the other fails CI.

### Non-goals

- **User content.** Dataset titles, descriptions, metadata, DOI records,
  tenancy display names typed by admins, and audit notes are shown as written.
  RFC 001 already indexes metadata with the `simple` configuration because it
  arrives in both languages.
- **A third language.** The design does not prevent one, but nothing is built
  for it.
- **Localized URLs, `hreflang` and per-language SEO.**
- **archivist, zipper, Swagger.** No end-user text; the administrators use
  Swagger as it is.
- **Changing any English copy.** Extraction moves text into catalogs
  verbatim. Rewording is a separate change.

## Decisions

| Decision | Choice | Rejected |
|---|---|---|
| Locales | `pt-BR`, `en` (BCP 47 tags everywhere) | `pt`, `pt_BR` in the API |
| Default | `pt-BR` | `en` |
| Language in the URL | No | `/en/...`, `/pt-BR/...` prefixes (Next built-in i18n routing) |
| What a page reads | the `NEXT_LOCALE` cookie, kept in sync with the account | reading the session on every page |
| Webapp library | `next-intl` 4 (peer `next ^14`) | `next-i18next` (needs prefix or domain routing on the Pages Router); a home-grown dictionary (no plurals, no typed keys, no formatting) |
| Email catalogs | gettext `.po` via Babel, `jinja2.ext.i18n` | one template file per locale (layout and logic duplicated per language) |
| Email locale | resolved at enqueue, stored on the row, reused at dispatch | resolved at dispatch (a retry could change language) |
| Preference route | `PUT /users/{id}/locale` with `authorize_self` | `PUT /users/me/locale` (new route shape, needs a Casbin row for `datasets_write`) |
| Email to someone with no account | the locale the webapp detected for that request; for a dataset invitation, the inviter's | bilingual message; always the default |
| Normative text (Data Policy) | translated, then reviewed line by line by the maintainer before release | left in one language |

## Locale resolution

### In the browser

The webapp reads one thing: the `NEXT_LOCALE` cookie. What keeps it right:

| When | What writes `NEXT_LOCALE` |
|---|---|
| First request without the cookie | the middleware, from `Accept-Language`, else `pt-BR` |
| Every sign-in (password, ORCID, and the `update` re-hydration) | NextAuth, with the account's `locale` |
| The language switcher | the switcher; and, when signed in, the account is updated too |

Matching `Accept-Language` takes the first language range, by quality, whose
primary subtag is `pt` or `en`: `pt-PT` and `pt` map to `pt-BR`; `en-GB` maps
to `en`. Anything else falls through to the default.

**Filling the preference.** At sign-in, an account whose `locale` is `null`
gets the cookie's value. This is how existing accounts acquire a preference
without anyone being asked, and how a choice made before signing in is kept. A
non-null preference is never overwritten by detection; it wins, and the cookie
is reset to it.

A pending ORCID session (no account yet) has no `uid` to save to. Its locale
travels with the email-verification request instead, and is written when the
account is created.

### For an email

There is no browser at dispatch, so the locale is decided when the message is
enqueued, and stored on the row.

| Recipient | Locale |
|---|---|
| An existing account | its `users.locale`, else `pt-BR` |
| An existing account, reached by an unauthenticated request (`password_reset`, `sign_up_existing_account`) | its `users.locale`, else the request's locale, else `pt-BR` |
| An address with no account, answering the person's own request (`sign_up_code`, `email_verification_code`) | the request's locale, kept in the challenge payload for resends |
| An address with no account, invited by someone (`dataset_invitation`) | the inviter's `users.locale` (`triggered_by`), else `pt-BR` |
| An address in `ADMIN_NOTIFICATION_EMAILS` | the `users.locale` of the account with that email, else `pt-BR` |

"The request's locale" is an optional `locale` field the webapp sends from
`NEXT_LOCALE`; an absent or unsupported value is ignored, never rejected, so
an old client keeps working.

## Gatekeeper changes

### Schema

```sql
ALTER TABLE users ADD COLUMN locale varchar(8) NULL
  CHECK (locale IN ('pt-BR', 'en'));

ALTER TABLE email_messages ADD COLUMN locale varchar(8) NOT NULL DEFAULT 'en'
  CHECK (locale IN ('pt-BR', 'en'));
ALTER TABLE email_messages ALTER COLUMN locale DROP DEFAULT;
```

`users.locale` is nullable on purpose: `null` means *never chosen nor
detected*, which is what sign-in fills. `email_messages.locale` is backfilled
with `en`, the language every existing row was rendered in, and has no default
afterwards so the code must always set it.

The supported set is one `Locale` enum in `app/model/locale.py`, with
`DEFAULT_LOCALE = Locale.PT_BR` — a `str` subclass with explicit values, since
production runs Python 3.10 and `StrEnum` is 3.11. `Locale.parse(value)`
returns `None` for anything unsupported, which is what the "ignored, never
rejected" rule above uses.

### Users and accounts

| Route | Change |
|---|---|
| `GET /users/{id}`, `GET /users/providers/{provider}/{ref}` and every response built from `UserGetResponse` | include `locale` |
| `PUT /users/{id}/locale` | **New.** Body `{"locale": "en"}`, `204`. Dependencies `[authenticate, authorize_self]`, as `PUT /users/{id}/password`. An unsupported value is `400` with `ErrorDetails(code="unsupported_locale", field="locale")`. |
| `POST /users/` | optional `locale` (development GitHub sign-in) |
| `POST /auth/sign-up`, `POST /auth/email-verifications` | optional `locale`, stored in `auth_challenges.payload` and used for the code email and its resends; `confirm_sign_up` and `confirm_email_verification` write it to `users.locale` |
| `POST /auth/password-reset` | optional `locale`, used only when the account's own is `null` |

`authorize_self` needs no Casbin row, so the route works for an account holding
only `datasets_write`, the role every sign-up receives.

### Errors

The webapp translates by code. The gatekeeper's job is to return a code for
everything a person can see, and to keep a list of them:

- The five prose details become codes: `snapshot_not_found`,
  `invalid_snapshot_data`, `invalid_client_input`, `internal_error`,
  `unauthorized`. `"Invalid client input"` lives under `details`, next to the
  `errors[]` list; the key stays, only the value changes.
- Details that carry a value after a colon (`"not_found: <id>"`) keep their
  shape; the webapp translates the part before the colon.
- `docs/error-codes.md` lists every code a response can carry, with its status
  and one line of meaning. It is seeded from the four webapp maps and from the
  gatekeeper's raise sites. A gatekeeper test fails when a code raised in
  `app/` is missing from the list.
- The invitation preview returns `inviter_name` and `owner_name` as `null`
  when unknown, instead of English placeholders; the webapp renders its own.
- The public tenancy keeps `display_name = 'Public'` in the database; the
  webapp shows it through a message keyed on the public namespace, not the
  stored string.

The gatekeeper does **not** read `Accept-Language` and does not translate
responses. One place translates, and it is the one that knows the session.

### Email

**Locale on every message.** `EmailService.enqueue` takes a required
`locale: Locale`. It renders `subject` and `body_text` in it, stores it on the
row, and `_mime` passes `record.locale` when it re-renders the HTML at
dispatch, so a message is in one language from enqueue to inbox. Resolution
follows the table in *For an email*, in one helper,
`EmailLocaleResolver`, so callers do not each reinvent it.

**Rendering.** `EmailTemplateRenderer.render(template, context, locale)`,
locale required, no default.

- The Jinja2 environment loads `jinja2.ext.i18n` with `newstyle=True`
  gettext; each render installs the translations for its locale. Templates
  mark text with `{% trans %}` / `_()`, and plurals with
  `{% trans count=n %}...{% pluralize %}...{% endtrans %}`.
- `base.html` sets `<html lang="{{ locale }}">`. Footer labels, tagline and
  subjects are translated like any other text; the postal address is not.
- `.txt` twins are translated the same way; `html_to_text` is unaffected.
- Catalogs: `app/resources/locales/{pt_BR,en}/LC_MESSAGES/email.po`, extracted
  with `pybabel extract` (config in `babel.cfg`). `msgid`s are the English
  text. The `.mo` files are compiled in the Docker build and by a `make`
  target the tests depend on; they are not committed.
- Babel joins `requirements.txt` pinned, next to `Jinja2==3.1.6`.

**Data in, sentences out.** `context` is JSONB and is rendered twice, so it
carries values, never formatted text:

- Dates go in as ISO 8601 strings and are formatted in the template by
  filters bound to the render's locale: `{{ until | date_long }}`,
  `{{ at | datetime_utc }}`. They replace `email_format.long_date`,
  `short_date` and the `"at HH:MM UTC"` string in `tenancy_notifier.py`, and
  the `%B` dependency on the process locale goes with them. A value that is
  not an ISO date is printed as it is, so rows enqueued before the deploy
  still render.
- Lists of names are joined by a `join_names` filter that uses the locale's
  list pattern (`a, b e c` / `a, b and c`), replacing the inline joins in
  `embargo_reminder`.
- The sentences now built in Python move into the templates:
  `_access_granted_context` passes the dataset, level and actor, and the
  template words them; `"A DataMap user"`, `"the owner"` and `["You"]` become
  `None` or a flag the template turns into words; the admin test message
  becomes a template.

### Amendments to RFC 003, 008 and 009

Each gets a one-line pointer here. In substance:

- **003**: `email_messages` has a `locale` column; messages are rendered in
  it at enqueue and at dispatch.
- **008**: emails and screens are no longer "in English": they follow this
  RFC. `POST /auth/sign-up`, `/auth/email-verifications` and
  `/auth/password-reset` accept an optional `locale`.
- **009**: emails follow this RFC; admin notifications use the admin
  account's locale when the address belongs to one.

RFC 007 needs no amendment: the webapp sends the cookie's locale when it
starts a notebook session, which is the account's preference for a signed-in
user.

## Webapp changes

### Library and catalogs

`next-intl` 4. Catalogs live in `messages/<locale>/<namespace>.json`, merged at
load into one object keyed by namespace:

```
messages/
  en/     common errors datasetDetails public account workspace
          search embargo admin dataPolicy notebooks apiTokens   (.json)
  pt-BR/  (the same files)
```

Each namespace has one owner (see *Work breakdown*). `common` holds only what
every area uses — Save, Cancel, the user menu, the sidebar, the footer — and
is frozen after Phase 0 so parallel tracks never edit it together; a track
that needs a new shared string adds it to its own namespace, and it moves to
`common` in the cleanup phase. `notebooks` and `apiTokens` belong to RFC 007
and RFC 010: whichever lands after Phase 0 writes its strings there directly;
anything that landed before (RFC 007's interim `NOTEBOOK_TEXT`) moves in the
cleanup phase.

Keys are typed: a `global.d.ts` declares the message shape from
`messages/en/*.json`, so a key with a typo fails `tsc`. Messages use ICU syntax
for plurals and interpolation.

The catalog for one locale is loaded per request, with a dynamic
`import()` of that locale only. At ~1,400 strings it is tens of KB; splitting
by page is not worth its complexity.

### Plumbing

- **`middleware.ts`**: sets `NEXT_LOCALE` from `Accept-Language` when absent.
  The `/` → `/app/home` rewrite is unchanged.
- **`_app.tsx`**: gains `getInitialProps`, which reads `NEXT_LOCALE` (from the
  request on the server, from `document.cookie` on the client), loads that
  locale's catalog, and wraps the tree in `NextIntlClientProvider`. One place,
  so no page can forget it. This turns off automatic static optimization,
  which costs little: nearly every page is already server-rendered or behind
  sign-in.
- **The three `getStaticProps` pages** (`/`, `/project/about`,
  `/project/research-group`) move to `getServerSideProps`. They only read
  `public/data/researchers.json`; a static page is built once, in one
  language, which is what not having the language in the URL rules out.
- **`_document.tsx`**: `<Html lang={locale}>`.
- **NextAuth**, in `authOptionsFor({ req, res })`:
  - after hydrating a signed-in user (`hydratePasswordSignIn`,
    `finishOrcidSignIn`, `hydrateWithUserInfo`), if the account's `locale` is
    `null`, call `PUT /users/{uid}/locale` with the cookie's value; then set
    `NEXT_LOCALE` on `res` to the account's locale;
  - the `update` trigger does the same, so a change made on another device is
    picked up on the next refresh.
  - `authOptions` without a request is used only to read sessions, never to
    sign in, so it needs nothing.
- **Account forms** (`lib/account.ts`): sign-up, ORCID email verification and
  password reset send `locale` from the cookie.
- **Notebooks**: the session request sends the cookie's locale (RFC 007 already
  sends a `locale`).

### Switching language

A `LanguageSwitcher` with two entries, each labelled in its own language
("Português", "English"), on every layout:

- signed in: the user menu (`components/Profile/AvatarButton.tsx`), and a
  *Language* `ProfileSection` on `pages/app/profile`;
- public pages: the footer in `components/Layout.tsx`;
- bare pages and the login page: the `right` slot of the `BareLayout` header,
  and the same position on the login page.

Choosing a language:

1. writes `NEXT_LOCALE`;
2. if signed in, calls the BFF route `PUT /api/users/me/locale`, built with
   `bffRouter()` on `authOnlyChain` (it must not need a tenancy), which
   forwards to `PUT /users/{uid}/locale`;
3. reloads the current route with `router.replace(router.asPath)`.

If step 2 fails, the page still switches (the cookie is set) and a notice says
the preference was not saved, since the next sign-in would otherwise undo the
choice. A pending ORCID session skips step 2.

### Formatting

- Dates and numbers go through `next-intl`'s `useFormatter` (`dateTime`,
  `relativeTime`, `number`). The default time zone is `America/Sao_Paulo`.
  **Embargo dates keep `timeZone: "UTC"`**, passed explicitly at each call, as
  `lib/embargoDates.ts` and `lib/embargoDisplay.ts` do today; moving them to
  São Paulo would show every embargo ending a day early.
- `react-moment`, `toLocale*` and the relative time and plurals in
  `lib/adminDisplay.ts` are replaced by `useFormatter` and ICU plurals.
  `react-moment` and `moment` leave `package.json` in the cleanup phase.
- Yup schemas are built from a factory taking `t`, so their messages are
  translated. Module-level message constants (`PASSWORD_LENGTH_MESSAGE`) become
  keys.
- Constants files with UI text keep their structure (keys, order, values) and
  replace each label with a message key.
- `<title>DataMap</title>` is the brand and is not translated.

### Errors in the webapp

The four maps (`ACCOUNT_`, `ADMIN_`, `EMBARGO_`, `TENANCY_ERROR_MESSAGES`)
and their helpers become one: the `errors` namespace, one key per code in
`docs/error-codes.md`, and one function, `errorMessage(t, error)`, with one
fallback (`errors.unknown`, showing the raw code in small type for support).
Where an area today words the same code differently, the area keeps its
wording as a nested key (`errors.byArea.embargo.<code>`) rather than
changing copy in an extraction PR. `lib/datasetVersionCreation.ts` and
`lib/requestErrorHandler.ts` stop composing English: they pass the code on,
and the login page renders it through `errorMessage`.

### Guarding against regressions

- **Catalog parity**: a jest test loads every `messages/en/*.json` and its
  `pt-BR` twin and fails on any key present in one and not in the other, and on
  any empty string.
- **Error codes**: a jest test fails when a code in the gatekeeper's
  `docs/error-codes.md` (vendored as `contants/ErrorCodes.ts`) has no
  `errors.*` message.
- **Hardcoded text**: `npm run lint` is added, CI runs it, and
  `.eslintrc.json` gains `react/jsx-no-literals` (`noStrings: true`,
  allow-list for punctuation and symbols) under `overrides`, scoped to the
  directories already migrated. Each track adds its directories in its own PR;
  the cleanup phase applies it to all of `components/` and `pages/`.
- **Missing messages** throw in development and tests (`onError`), and fall
  back to the English message with a logged warning in production.
- **Component tests keep their English queries.** A shared
  `test/renderWithIntl.tsx` provides the real `en` catalog. Because the
  extraction is verbatim, the ~1,100 text queries keep passing unchanged; a
  query that breaks during a track means the copy was altered, which is a
  defect of the extraction, not a test to update. Each track wraps its
  tests' render helper and adds one test per area that renders in `pt-BR`.

## Terminology

Consistency across tracks matters more than any one choice. Every translating
track reads `datamap-webapp/messages/GLOSSARY.md`, created in Phase 0 and
shared with the email catalogs. Tracks propose additions in their PR
description; the cleanup phase merges them. Three product terms stay in
English in both locales, treated as names: **dataset**, **workspace** and
**snapshot**. They keep their English plural (`os datasets`) and take the
masculine article (`o dataset`, `o workspace`, `o snapshot`).


| English | pt-BR | Note |
|---|---|---|
| dataset | dataset | A name, never "conjunto de dados" |
| workspace / tenancy | workspace | The UI's word for a tenancy since RFC 009 |
| embargo | embargo | |
| findable / registered (DOI) | localizável / registrado | DataCite states, explained where shown |
| upload / download | enviar / baixar | |
| snapshot | snapshot | |
| sign in / sign out / sign up | entrar / sair / criar conta | |
| anonymous link | link anônimo | |
| share | compartilhar | |
| member | membro | |

## Work breakdown

The work is shaped for several agents working in parallel, each in its own
worktree and pull request, with one person reviewing. Two rules make parallel
tracks safe:

1. **Every file has one owner track.** A track edits only its directories, its
   own namespace files in both locales, and its tests.
2. **Contracts land first.** Nothing parallel starts until Phase 0 is merged.

### Phase 0 — foundation (serial)

| PR | Repository | Content |
|---|---|---|
| G0 | gatekeeper | `users.locale` and `email_messages.locale` migrations; `Locale`; `locale` in user responses; `PUT /users/{id}/locale`; optional `locale` on `POST /users/`, `/auth/sign-up`, `/auth/email-verifications`, `/auth/password-reset`, kept in the challenge payload and written at account creation; `EmailService.enqueue(locale=...)` with `EmailLocaleResolver`, every caller passing it, `_mime` using `record.locale` (templates still English, so behaviour is unchanged); `docs/error-codes.md` and its test. Unit and integration tests. Deployable alone. |
| W0 | datamap-webapp | `next-intl`, after confirming its 4.x Pages Router support with one migrated page (pin 3.x if it falls short); `messages/` skeleton with `common` and `errors`; `GLOSSARY.md`; middleware; `_app.getInitialProps`; `_document`; NextAuth cookie and fill-null; locale on account forms and notebook sessions; BFF locale route; `LanguageSwitcher` on every layout; profile section; parity test; `npm run lint` in CI with the override scaffold; `renderWithIntl`. Migrates `LoggedLayout`, `SidebarMenuItem`, `Navbar`, `AvatarButton`, `Footer` and `BareLayout` as the worked example the tracks copy. Depends on G0 being deployed. |

### Phase 1 — tracks (parallel)

| Track | Repository | Owns | Namespace |
|---|---|---|---|
| T1 Dataset editing | webapp | `components/DatasetDetails/**`, `components/base/**`, `components/DatasetDetailsPage.tsx`, `components/DownloadDatafilesButton.tsx`, `pages/app/datasets/[datasetId]/**`, `pages/app/datasets/new.tsx` | `datasetDetails` |
| T2 Public site | webapp | `pages/index.tsx`, `pages/project/*` **except** `data-policy`, `components/Home`, `components/Project`, `components/Public`, `ResearcherProfile.tsx`, `pages/404.tsx`, `pages/500.tsx` | `public` |
| T3 Account and sign-in | webapp | `components/Account/**`, `components/Auth/**`, `pages/account/**`, `pages/orcid-oauth-callback.tsx`, `pages/app/profile/**` (except the language section from W0), `contants/AccountConstants.ts`, `lib/accountValidation.ts` | `account` |
| T4 Workspace and members | webapp | `components/Tenancy/**`, `components/Workspace/**`, `components/Invitation/**`, `pages/app/{home,tenancy,members,error}/**`, `pages/invitations/**`, `contants/TenancyConstants.ts` | `workspace` |
| T5 Search and public dataset page | webapp | `components/Search/**`, `components/DatasetSnapshot/**`, `components/Anonymous/**`, `pages/datasets/**`, `pages/doi/**`, `pages/anonymous/**`, `pages/app/datasets/index*`, `lib/anonymousMetadata.ts` | `search` |
| T6 Embargo and sharing | webapp | `components/Embargo/**`, `components/Share/**`, `components/Datasets/**`, `pages/app/datasets/shared*`, `contants/{Embargo,Share}Constants.ts`, `lib/{embargoDisplay,embargoDates,membersAccess}.ts` | `embargo` |
| T7 Admin | webapp | `components/Admin/**`, `pages/app/admin/**`, `contants/AdminConstants.ts`, `lib/adminDisplay.ts` | `admin` |
| T8 Errors | both | gatekeeper prose details → codes, preview placeholders → `null`; webapp's four maps → `errors`, `errorMessage`, `lib/rpc.ts`, `lib/datasetVersionCreation.ts`, `lib/requestErrorHandler.ts`, error-code test | `errors` |
| T9 Email | gatekeeper | Babel, `jinja2.ext.i18n`, catalogs, filters, `email_format.py` removed, sentences moved from `share.py`, `notification.py`, `tenancy_notifier.py`, `email.py` into templates; all 16 templates and their `.txt` twins | — |
| T10 Data Policy | webapp | `pages/project/data-policy.tsx` | `dataPolicy` |

Anything not listed belongs to W0: the layouts, `components/{Navbar,Profile,ContextMenu,ui,Icons,Brand}`, `LayoutFullScreen.tsx`. `pages/app/notebooks` is left to RFC 007, which replaces it. `pages/design-system` and `pages/tools` are internal and stay in English.

T1, T4 and T6 are the largest (150 to 200 strings each). T8 touches the
four error maps that T3, T4, T6 and T7 import: those tracks call
`errorMessage` and do not edit the maps, so T8 can run alongside them.
**T10 is not merged without the maintainer's careful review of the Portuguese
text**, since the Data Policy has normative weight; the maintainer reviews
every track's translation, but this one line by line.

Each track's PR description lists the strings it could not translate with
confidence, so the review goes there first. There are ten tracks and one
reviewer; they can be merged in any order, so the reviewer sets the pace, not
the agents.

### Phase 2 — cleanup (serial)

ESLint rule over all of `components/` and `pages/`; shared strings promoted to
`common`; RFC 007's interim strings moved to `notebooks`; `react-moment` and
`moment` removed; glossary finalized.

### Deployment order

G0, then W0, because W0 calls the new route and sends the new fields. Every
later PR deploys independently. G0's migrations are additive, and
`email_messages.locale` is backfilled, so no step needs downtime beyond the
deploy's usual one.

## Testing

**Gatekeeper.**

- Unit: `Locale.parse`; account creation from both challenge kinds writes the
  payload's locale; `EmailLocaleResolver` for every row of the resolution
  table; `enqueue` stores the locale and `_mime` renders with it; the renderer
  produces Portuguese and English subjects, HTML and text for every template,
  formats a date differently in each, pluralizes `embargo_reminder` for 1 and
  many days, joins names per locale, and prints a non-ISO date unchanged;
  rendering without `locale` is a `TypeError`.
- A catalog test fails if any `msgid` in `email.po` has an empty `msgstr` in
  `pt_BR`.
- `docs/error-codes.md` covers every code raised in `app/`.
- Integration: `PUT /users/{id}/locale` changes the caller, refuses another
  user's id, answers 400 for `fr`, and works for an account with only
  `datasets_write`; sign-up with `locale: "en"` produces a Mailpit message in
  English and an account with `locale = 'en'`; sign-up without one produces
  Portuguese. Written to fail first.

**Webapp.**

- Parity and error-code tests, as above.
- Middleware: `Accept-Language: en-GB,en;q=0.9` → cookie `en`;
  `pt-PT` → `pt-BR`; `fr` → `pt-BR`; an existing cookie is not overwritten.
- NextAuth: a `null` locale is filled from the cookie; a stored locale is kept,
  wins, and resets the cookie.
- The existing component tests pass unchanged under `renderWithIntl`, plus one
  `pt-BR` render per track.

## Alternatives considered

### `PUT /users/me/locale`

Proposed in the first draft. A `me` route needs declaring before `/{id}`, and
it sits behind `authorize`, where `datasets_write` — the role every account
has — holds no `/api/v1/users` policy, so it would answer 401 to everyone.
`PUT /users/{id}/locale` with `authorize_self` follows `PUT /users/{id}/password`
and needs no policy.

### Rendering an email's language at dispatch

Look up the recipient's preference when the message leaves rather than when it
is queued. Rejected: the outbox already renders `subject` and `body_text` at
enqueue, so they would disagree with the HTML, and a retry could change
language after the person changed their preference.

### Reading the session on every page

Resolve the language from the session (or the gatekeeper) on each request
instead of from a cookie. Rejected: the session is not available on public
pages without extra work, and the cookie is already right by construction,
since sign-in and the switcher are the only ways the preference changes.

## Out of scope

| Item | Reason |
|------|--------|
| Translating user content or audit records | Written by people or by the system as a record, in the language it was written. |
| Language in the URL, `hreflang` | No per-language SEO need yet; prefixes would touch every link and the middleware. |
| A third locale | Nothing requested. Adding one is a catalog, a `CHECK`, and an enum value. |
| Email preferences beyond language | RFC 003 already excludes preferences and unsubscribe. |
| Rewording English copy | Extraction is verbatim, so tests and review stay mechanical. |

## Open questions

None. Settled in review: *dataset*, *workspace* and *snapshot* stay in English
in Portuguese text, and the maintainer reviews every translation, the Data
Policy included.
