# Dataset Embargo — Webapp Implementation Plan (05)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Where the code goes.** This plan lives in the gatekeeper repo with the other embargo plans, but every file it changes is in the **webapp repo, `/Users/caio.maia/workspace/datamap/datamap-webapp`**, except Task 18, which changes `infrastructure/nginx/datamap.conf` in the **gatekeeper repo**. All paths below are relative to the webapp repo root unless a task says otherwise. Work in a git worktree of the webapp repo on branch `feat/dataset-embargo`, created from `origin/main`; never in the main checkout.

**Verified against:** webapp `main` at `8c6f761` (#101, the new DataMap identity), then re-checked at `9afeb5a` (#102–#104). Since then `LoggedLayout` redirects with `Router.replace`, `lib/rpc.ts` retries idempotent requests, and `lib/authRoutes.ts` adds `loginUrlFor`, which Tasks 12 and 13 use. None of those changes affects a step here. If `main` has moved again, diff the files in *File Structure* against it before starting.

**Design:** `docs/design/rfc-003-embargo/Embargo Feature.dc.html` (gatekeeper repo), vendored from Claude Design; its README maps each section to a task. Every UI task cites the artboard it reproduces (§1a–§1i) and ends with a step comparing the running page with it. Where the design and a decision in the RFC or the contracts disagree, the decision wins, and the task says so where it happens.

**Goal:** Give the webapp everything RFC 003 asks of the user interface: embargo at creation and on the dataset page, the share dialog, anonymous links, the anonymous page, the DOI embargo notice, invitation acceptance, a *Shared with me* list that works for an account with no tenancy, and the post-embargo banner.

**Architecture:** Server-side calls to the gatekeeper live in `lib/embargo.ts` and `lib/share.ts` (axiosInstance + buildHeaders); browser mutations go through new `BFFAPI` methods to new `pages/api` routes built on one helper, `lib/bffRoute.ts`, whose chain authenticates but does not require a tenancy. UI is split into small components under `components/Embargo`, `components/Share`, `components/Anonymous` and `components/Invitation`, each with a jsdom test; the public pages are thin and keep their decisions in tested `lib/*` functions.

**Tech Stack:** Next.js 14 (pages router), React 18, TypeScript, next-connect, axios, SWR, Formik, TailwindCSS, react-material-symbols, Jest + Testing Library.

## Global Constraints

- Contracts: `docs/superpowers/plans/2026-09-30-embargo-00-contracts.md` (gatekeeper repo). Payload shapes, routes and error codes are copied from it verbatim; if this plan disagrees with it, the contracts file wins.
- Maximum embargo period: **90 days**, on creation and on each extension. The UI offers dates up to today + 89 days so that the end of the chosen day never exceeds the server's `now() + 90 days`.
- `until` is sent as the end of the chosen UTC day: `YYYY-MM-DDT23:59:59+00:00`.
- Redaction marker: `"[redacted]"`.
- Mutations go through `gateways/BFFAPI.ts`, which emits `trackUiEvent` after success and throws `httpErrorHandler(error)` on failure. Reads use SWR with `lib/fetcher.js`. Forms use Formik.
- Constants live in `contants/{Category}Constants.ts` (the directory is spelled `contants`).
- Visual language: the DataMap identity of webapp #101 (`8c6f761`). Near-black `primary-900` on `primary-50` ground; white cards `rounded-lg border border-primary-200 bg-primary-0`; section `h2` at `m-0 text-lg leading-snug tracking-[-0.01em]` with a `text-sm text-primary-600` subtitle; form fields from `contants/EditFormConstants.ts`; card footers `border-t border-primary-200 bg-primary-50 px-5 py-3 rounded-b-lg`; notices in the mint tint `bg-secondary-500`; pills `px-2.5 py-[3px] rounded-full text-xs leading-[18px] font-semibold`; dialogs through `components/base/PopupModal.tsx` (with `destructive` and `maxWidthClassName`). Do not use the pre-#101 patterns (`border-t-4` callouts, `h6` section titles, `font-extrabold` page titles).
- Material Symbols: `<MaterialSymbol ... grade={-25} weight={400} />`, size 14–28, as #101 uses them; the embargo lock is filled (`fill`).
- Amber (`embargo-*`, Task 1) means "under embargo" and nothing else: the badge, the embargo card, the withheld-files lock, the creation notice, the anonymous banner while the embargo lasts, the DOI page's lock. Once the embargo has ended the same places turn neutral or mint. Red (`danger-*`) is for *End early*, *Remove access* and *Revoke* only.
- Component tests start with `/** @jest-environment jsdom */`, live in `__tests__` next to the component, and import components by relative path (Jest does not map `@/`). Components that a test imports must not import `react-markdown` (ESM, not transformed by Jest).
- Every new page must be listed in `PAGES` (`contants/TelemetryConstants.ts`), or `contants/__tests__/TelemetryConstants.test.ts` fails.
- Comments: none narrating code. One line only where a reader would otherwise undo something on purpose.
- Every task ends green on `npx jest <the task's tests>`; Task 17 runs the whole suite and `npm run build`.

## File Structure

| File | Responsibility |
|---|---|
| `types/GatekeeperAPI.ts` (modify) | Wire shapes of the new gatekeeper payloads |
| `types/BffAPI.ts` (modify) | `embargo`/`access`/`files_withheld` on existing dataset responses |
| `types/APIError.ts`, `lib/rpc.ts` (modify) | 403 and 409 become typed errors instead of 500 |
| `contants/EmbargoConstants.ts` (create) | Limits, the redaction marker, error-code → message |
| `contants/InternalRoutesConstants.ts`, `contants/TelemetryConstants.ts` (modify) | New routes, pages and UI events |
| `lib/shareTarget.ts` (create) | Email / ORCID recognition, ORCID checksum |
| `lib/embargoDates.ts` (create) | Date limits, validation, request building |
| `lib/embargoState.ts` (create) | Derived UI decisions from `embargo` + `access` |
| `lib/anonymousMetadata.ts` (create) | Turns redacted metadata into displayable rows, counts authors, names extensions |
| `lib/embargoDisplay.ts` (create) | The design's wording: short dates, days left, tenancy name, initials, link stats, history lines |
| `lib/anonymousPage.ts`, `lib/doiLanding.ts`, `lib/invitationPage.ts` (create) | `getServerSideProps` decisions of the three new pages |
| `lib/embargo.ts`, `lib/share.ts` (create), `lib/dataset.ts` (modify) | Server calls to the gatekeeper |
| `lib/middlewareChain.ts` (modify), `lib/bffRoute.ts` (create) | Tenancy-optional chain and the route helper |
| `lib/requestErrorHandler.ts` (modify) | 404 renders Next's not-found page instead of crashing |
| `lib/users.ts` (modify) | `canEditDataset` honours the dataset's `access` |
| `pages/api/datasets/[datasetId]/{embargo,share,anonymous-links}/…`, `pages/api/datasets/[datasetId]/access-events.ts`, `pages/api/datasets/shared.ts`, `pages/api/invitations/accept.ts` (create) | BFF routes |
| `gateways/BFFAPI.ts` (modify) | Browser methods for the new routes |
| `hooks/UseDebouncedValue.ts` (create) | Debounce for the search-as-you-type |
| `components/Embargo/*` (create) | Badge; the embargo and access cards; Extend, End early, mode and note dialogs; `EmbargoFields` and `SetEmbargoDialog`; the Settings blocks (embargo rows, access summary, history); withheld notice and locked Download; ended banner; choice at creation; the DOI page notice; manual-DOI prompts |
| `components/Datasets/DatasetsTabs.tsx` (create) | *Datasets* / *Shared with me* tabs |
| `components/Public/BareLayout.tsx` (create) | Header of the pages reached without signing in (§1i) |
| `components/Share/*` (create) | Share button and dialog, input, access list, anonymous links, one-time link |
| `components/Anonymous/*` (create) | Banner, files card with extension chips, redacted metadata rows |
| `components/Invitation/InvitationCard.tsx` (create) | Shows the invitation, accepts it on request, explains a used one |
| `components/base/PopupModal.tsx` (modify) | `hideCancel` for the one-button "I've copied it" |
| `components/LoggedLayout.tsx`, `components/DatasetDetailsPage.tsx`, `components/DatasetDetails/TabPanelSettings.tsx`, `components/DatasetDetails/DataCard/TabPanelDataCard.tsx`, `components/DatasetDetails/DataCard/DataExplorer.tsx`, `components/Search/ListItem.tsx`, `components/Tenancy/AccessPending.tsx`, `pages/app/datasets/new.tsx`, `types/new-dataset.d.ts`, `pages/api/auth/[...nextauth].ts` (modify) | Wiring |
| `pages/app/datasets/shared.tsx`, `pages/anonymous/[token].tsx`, `pages/doi/datasets/[datasetId]/versions/[versionName].tsx`, `pages/invitations/[token].tsx` (create) | New pages |
| `lib/doi.ts`, `components/DatasetDetails/DatasetCitation.tsx` (modify), `components/Embargo/ManualDoiConfirmation.tsx` (create) | A manual DOI ends the embargo only after confirmation |
| `components/DatasetDetails/DatasetColaboratorsForm.tsx` (modify) | Contributors are credit only: no permission field, a line pointing to Share |
| `lib/__tests__/emailImages.test.ts` (create) | Keeps `public/img/email/datamap-tile-{36,22}.png`, which the gatekeeper's email templates load, from being deleted |
| `contants/ShareConstants.ts`, `components/Share/PersonInitial.tsx` (create) | Share dialog row styles and the initial avatar |

## Task order and parallelism

| Task | Depends on | Can run in parallel with |
|---|---|---|
| 1 Types, error handling, palette | — | 2 |
| 2 Route and telemetry constants | — | 1, 3 |
| 3 Pure helpers (share target, dates, state, wording) | 1 (EmbargoConstants, types) | 2 |
| 4 Server calls (`lib/embargo.ts`, `lib/share.ts`) | 1 | 5 |
| 5 Tenancy-optional chain, route helper, 404 handling | 1 | 4 |
| 6 BFF routes and BFFAPI methods | 4, 5 | — |
| 7 Shared with me, layout, list badge (`EmbargoBadge`) | 2, 3, 6 | 10, 11 |
| 10 Share dialog | 3, 6 | 7, 11 |
| 8 Embargo on the dataset page | 3, 6, 7 (`EmbargoBadge`), 10 (`ShareDialog`) | 11, 12, 13 |
| 9 Embargo choice at creation | 8 (`EmbargoFields`) | 11–13, 15 |
| 11 Anonymous page (`BareLayout`) | 2, 3, 4 | 7, 8, 10 |
| 12 DOI landing page | 4, 11 (`BareLayout`) | 8, 9, 13 |
| 13 Invitation page and claim on sign-in | 4, 6, 11 (`BareLayout`) | 8, 9, 12 |
| 14 Manual DOI confirmation | 3, 8 (`SetEmbargoDialog`) | 9, 12, 13, 15 |
| 15 Contributors are credit only | 8 (`canEditDataset(user, dataset)`), 10 (the Share button it points to) | 9, 12–14 |
| 16 Guard on the email images | — | everything |
| 17 Full verification | all | — |
| 18 nginx (gatekeeper repo) | 12 deployed | — |

Tasks are numbered as they were first planned; run them in the order of this table (10 before 8).

---|---|---|
| 1 Types and error handling | — | 2, 3 |
| 2 Route and telemetry constants | — | 1, 3 |
| 3 Pure helpers (share target, dates) | 1 (EmbargoConstants) | 2 |
| 4 Server calls (`lib/embargo.ts`, `lib/share.ts`) | 1 | 5 |
| 5 Tenancy-optional chain, route helper, 404 handling | 1 | 4 |
| 6 BFF routes and BFFAPI methods | 4, 5 | — |
| 7 Shared with me, layout, list badge | 2, 6, 8's `EmbargoBadge` (create it here if 8 has not run) | 11, 12 |
| 8 Embargo on the dataset page | 3, 6 | 10, 11, 12 |
| 9 Embargo choice at creation | 3, 6, 8 (`EmbargoBadge` not needed; `EmbargoChoice` is created here) | 10, 11, 12 |
| 10 Share dialog | 3, 6 | 8, 9, 11, 12 |
| 11 Anonymous page | 2, 4 | 7, 8, 9, 10, 12 |
| 12 DOI landing page | 2, 4 | 7–11 |
| 13 Invitation page and claim on sign-in | 2, 4, 6 | 7–12 |
| 14 Manual DOI confirmation | 1, 3 | 7–13, 15, 16 |
| 15 Contributors are credit only | 8 (`canEditDataset(user, dataset)`), 10 (the Share button it points to) | 11–14, 16 |
| 16 Guard on the email images | — | everything |
| 17 Full verification | all | — |
| 18 nginx (gatekeeper repo) | 12 deployed | — |

---

### Task 1: Types and error handling

**Files:**
- Modify: `types/GatekeeperAPI.ts` (append)
- Modify: `types/BffAPI.ts:29-52` (`GetDatasetDetailsResponse`, `GetDatasetDetailsVersionResponse`), `types/BffAPI.ts:184-202` (`GetMinimalDatasetsDetasetDetailsResponse`)
- Modify: `types/APIError.ts:1`
- Modify: `lib/rpc.ts` (`httpErrorHandler`)
- Create: `contants/EmbargoConstants.ts`
- Modify: `tailwind.config.js` (the embargo amber and the danger red of the design)
- Test: `lib/__tests__/rpc.test.ts` (append), `contants/__tests__/EmbargoConstants.test.ts`

**Interfaces:**
- Produces (TypeScript, `types/GatekeeperAPI.ts`): `PermissionLevel`, `AccessLevel`, `DatasetEmbargo`, `DatasetAccess`, `DatasetOwner`, `FilesSummary`, `FileExtensionSummary`, `SetEmbargoRequest`, `ExtendEmbargoRequest`, `EmbargoModeRequest`, `EmbargoNoteRequest`, `EmbargoStatusResponse`, `ShareUser`, `SharePermission`, `ShareInvitation`, `ShareTenancy`, `AnonymousLinkViews`, `AnonymousLink`, `CreatedAnonymousLink`, `ShareState`, `GrantRequest`, `GrantResult`, `AnonymousPageVersion`, `AnonymousPageActive`, `AnonymousPageEnded`, `AnonymousPageResponse`, `AcceptInvitationResponse`, `ClaimInvitationsResponse`, `InvitationPreview`, `AccessHistoryEntry`, `AccessHistoryResponse`.
- Produces (Tailwind): `embargo-50`, `embargo-100`, `embargo-200`, `embargo-800` and `danger-50`, `danger-200`, `danger-700`, `danger-800` — the one new colour the design introduces (amber marks "under embargo", and nothing else uses it) and the red of its destructive text actions and error boxes.
- Produces (`contants/EmbargoConstants.ts`): `MAX_EMBARGO_DAYS = 90`, `REDACTED = "[redacted]"`, `ANONYMOUS_LINK_LABEL_MAX = 256`, `EMBARGO_ERROR_MESSAGES`, `GENERIC_ERROR_MESSAGE`, `messageForApiError(error: unknown): string`.
- Produces (`lib/rpc.ts`): `httpErrorHandler` returns `APIError` with `name: "FORBIDDEN", httpCode: 403` and `name: "CONFLICT", httpCode: 409`.

- [ ] **Step 1: Write the failing tests**

Append to `lib/__tests__/rpc.test.ts`:

```ts
import { AxiosError, AxiosHeaders } from "axios";
import { httpErrorHandler } from "../rpc";

function axiosErrorWith(status: number, data: unknown) {
    return new AxiosError("request failed", "ERR_BAD_REQUEST", undefined, {}, {
        status,
        data,
        statusText: "",
        headers: {},
        config: { headers: new AxiosHeaders() },
    } as any);
}

describe('httpErrorHandler', () => {
    test('a 403 is forbidden, not an internal error', () => {
        const e = httpErrorHandler(axiosErrorWith(403, { detail: "forbidden" }));
        expect(e.httpCode).toBe(403);
        expect(e.name).toBe("FORBIDDEN");
    })

    test('a 409 keeps the gatekeeper detail', () => {
        const e = httpErrorHandler(axiosErrorWith(409, { detail: "invitation_already_accepted" }));
        expect(e.httpCode).toBe(409);
        expect(e.name).toBe("CONFLICT");
        expect(e.message).toBe("invitation_already_accepted");
    })

    test('a 400 keeps the error codes', () => {
        const e = httpErrorHandler(axiosErrorWith(400, {
            details: "Invalid client input",
            errors: [{ code: "embargo_too_long", field: null }],
        }));
        expect(e.httpCode).toBe(400);
        expect(e.errors).toEqual([{ code: "embargo_too_long", field: null }]);
    })
})
```

Create `contants/__tests__/EmbargoConstants.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import { APIError } from "../../types/APIError";
import { EMBARGO_ERROR_MESSAGES, GENERIC_ERROR_MESSAGE, messageForApiError } from "../EmbargoConstants";

describe('messageForApiError', () => {
    test('a known error code becomes its message', () => {
        const error = new APIError("BAD_REQUEST", 400, "Invalid client input", true, [{ code: "embargo_too_long" }]);
        expect(messageForApiError(error)).toBe(EMBARGO_ERROR_MESSAGES.embargo_too_long);
    })

    test('a 403 says the action is not allowed', () => {
        const error = new APIError("FORBIDDEN", 403, "forbidden", true);
        expect(messageForApiError(error)).toBe("You are not allowed to do this on this dataset.");
    })

    test('a 404 says the dataset is gone or out of reach', () => {
        const error = new APIError("NOT_FOUND", 404, "Resource does not exists", true);
        expect(messageForApiError(error)).toBe("This dataset no longer exists, or you no longer have access to it.");
    })

    test('anything else is the generic message', () => {
        expect(messageForApiError(new Error("boom"))).toBe(GENERIC_ERROR_MESSAGE);
        expect(messageForApiError(undefined)).toBe(GENERIC_ERROR_MESSAGE);
    })

    test('every contract error code has a message', () => {
        const codes = [
            "embargo_too_long", "embargo_until_in_past", "embargo_dataset_published", "embargo_already_active",
            "embargo_not_active", "embargo_until_not_later", "embargo_active",
            "share_target_required", "share_target_ambiguous", "invalid_email", "invalid_orcid",
            "already_has_access", "cannot_share_with_owner", "invalid_level",
            "embargo_manual_doi", "embargo_manual_doi_ends_embargo",
        ];
        expect(codes.filter((code) => !EMBARGO_ERROR_MESSAGES[code])).toEqual([]);
    })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest lib/__tests__/rpc.test.ts contants/__tests__/EmbargoConstants.test.ts`
Expected: FAIL — `Cannot find module '../EmbargoConstants'`, and the 403/409 tests fail with `httpCode` 500.

- [ ] **Step 3: Implement**

`types/APIError.ts`, line 1:

```ts
export type HttpCode = 200 | 300 | 400 | 401 | 403 | 404 | 409 | 500;
```

`lib/rpc.ts`, inside `httpErrorHandler`, extend the status chain after the `statusCode === 400` branch:

```ts
      } else if (statusCode === 403) {
        handledError = new APIError(
          "FORBIDDEN",
          HttpStatusCode.Forbidden,
          "user not allowed to perform the operation",
          true
        )
      } else if (statusCode === 409) {
        handledError = new APIError(
          "CONFLICT",
          HttpStatusCode.Conflict,
          response?.data?.detail,
          true
        )
      }
```

Create `contants/EmbargoConstants.ts`:

```ts
import { APIError } from "../types/APIError";

export const MAX_EMBARGO_DAYS = 90;

export const REDACTED = "[redacted]";

export const ANONYMOUS_LINK_LABEL_MAX = 256;

export const GENERIC_ERROR_MESSAGE = "Something went wrong. Please try again.";

export const EMBARGO_ERROR_MESSAGES: Record<string, string> = {
    embargo_too_long: "An embargo can last at most 90 days from today.",
    embargo_until_in_past: "Choose a date in the future.",
    embargo_dataset_published: "This dataset has already been published, so it cannot be embargoed.",
    embargo_already_active: "This dataset is already under embargo.",
    embargo_not_active: "This dataset is not under embargo.",
    embargo_until_not_later: "The new date must be later than the current end of the embargo.",
    embargo_active: "This cannot be done while the dataset is under embargo.",
    share_target_required: "Choose a person, or type an email or ORCID.",
    share_target_ambiguous: "Type only one email or ORCID.",
    invalid_email: "This email address is not valid.",
    invalid_orcid: "This ORCID is not valid. Check the last digit.",
    already_has_access: "This person already has access.",
    cannot_share_with_owner: "The owner already has access.",
    invalid_level: "Choose a valid access level.",
    embargo_manual_doi: "This dataset has a manual DOI, so it can no longer be put under embargo.",
    embargo_manual_doi_ends_embargo: "Registering a manual DOI ends the embargo. Confirm it, or use a DOI generated by DataMap.",
};

export function messageForApiError(error: unknown): string {
    const apiError = error as APIError;
    const code = apiError?.errors?.[0]?.code;

    if (code && EMBARGO_ERROR_MESSAGES[code]) {
        return EMBARGO_ERROR_MESSAGES[code];
    }
    if (apiError?.httpCode === 403) {
        return "You are not allowed to do this on this dataset.";
    }
    if (apiError?.httpCode === 404) {
        return "This dataset no longer exists, or you no longer have access to it.";
    }
    return GENERIC_ERROR_MESSAGE;
}
```

Append to `types/GatekeeperAPI.ts`:

```ts
/**
 * Contracts: docs/superpowers/plans/2026-09-30-embargo-00-contracts.md (gatekeeper repo).
 */
export type PermissionLevel = "read" | "write";

export type AccessLevel = "owner" | "write" | "read" | "tenancy";

/** @interface */
export interface DatasetEmbargo {
    until: string
    active: boolean
    metadata_visible: boolean
    note: string | null
}

/** @interface */
export interface DatasetAccess {
    level: AccessLevel
    can_edit: boolean
    can_share: boolean
    can_manage_embargo: boolean
    can_extend_embargo: boolean
    can_delete: boolean
}

/** @interface */
export interface FilesSummary {
    count: number
    total_size_bytes: number
}

/** @interface */
export interface SetEmbargoRequest {
    until: string
    metadata_visible: boolean
    note: string | null
}

/** @interface */
export interface ExtendEmbargoRequest {
    until: string
    reason?: string | null
}

/** @interface */
export interface EmbargoNoteRequest {
    note: string | null
}

/** @interface */
export interface DatasetOwner {
    id: string
    name: string
}

/** @interface */
export interface EmbargoModeRequest {
    metadata_visible: boolean
}

/** @interface */
export interface EmbargoStatusResponse {
    embargoed: boolean
    until: string | null
    doi: string | null
}

/** @interface */
export interface ShareUser {
    id: string
    name: string
    email: string
}

/** @interface */
export interface SharePermission {
    user: ShareUser
    level: PermissionLevel
    granted_at: string
    granted_by: string
    invited_as: string | null
}

/** @interface */
export interface ShareInvitation {
    id: string
    email: string | null
    orcid: string | null
    level: PermissionLevel
    created_at: string
    accepted_at: string | null
    accepted_by: ShareUser | null
    revoked_at: string | null
}

/** @interface */
export interface AnonymousLinkViews {
    count: number
    first_at: string | null
    last_at: string | null
}

/** @interface */
export interface AnonymousLink {
    id: string
    label: string
    token_hint: string | null
    created_at: string
    revoked_at: string | null
    views: AnonymousLinkViews
}

/** @interface */
export interface CreatedAnonymousLink extends AnonymousLink {
    link: string
}

/** @interface */
export interface ShareTenancy {
    name: string
    path: string
    members: number
}

/** @interface */
export interface ShareState {
    owner: ShareUser
    permissions: SharePermission[]
    invitations: ShareInvitation[]
    anonymous_links: AnonymousLink[]
    tenancy: ShareTenancy | null
}

/** Exactly one of user_id, email, orcid. */
export interface GrantRequest {
    user_id?: string
    email?: string
    orcid?: string
    level: PermissionLevel
}

export type GrantResult =
    | { kind: "permission", permission: SharePermission }
    | { kind: "invitation", invitation: ShareInvitation, link: string };

/** @interface */
export interface FileExtensionSummary {
    extension: string | null
    count: number
    total_size_bytes: number
}

/** @interface */
export interface AnonymousPageVersion {
    name: string
    created_at: string
    files_summary: FilesSummary & { extensions: FileExtensionSummary[] }
}

/** @interface */
export interface AnonymousPageActive {
    state: "active"
    embargo_until: string
    dataset: {
        name: string
        data: Record<string, unknown>
        versions: AnonymousPageVersion[]
    }
}

/** @interface */
export interface AnonymousPageEnded {
    state: "ended"
    embargo_ended_at: string
    dataset: AnonymousPageActive["dataset"]
}

/** @interface */
export interface AnonymousPagePublished {
    state: "published"
    dataset_id: string
}

export type AnonymousPageResponse = AnonymousPageActive | AnonymousPageEnded | AnonymousPagePublished;

/** @interface */
export interface AcceptInvitationResponse {
    dataset_id: string
    level: PermissionLevel
}

/** @interface */
export interface ClaimInvitationsResponse {
    accepted: AcceptInvitationResponse[]
}

/** @interface */
export interface InvitationPreview {
    state: "pending" | "accepted"
    dataset_name: string
    inviter_name: string
    owner_name: string
    level: PermissionLevel
    invited_as: string
    embargo_until: string | null
    accepted_at: string | null
}

/** @interface */
export interface AccessHistoryEntry {
    event_type: string
    occurred_at: string
    actor: { id: string, name: string } | null
    subject: string | null
    old_value: Record<string, unknown> | null
    new_value: Record<string, unknown> | null
    note: string | null
}

/** @interface */
export interface AccessHistoryResponse {
    items: AccessHistoryEntry[]
}
```

In `types/BffAPI.ts`, add the import at the top of the file (merge with the existing `GatekeeperAPI` import if present):

```ts
import { DatasetAccess, DatasetEmbargo, DatasetOwner, FilesSummary } from "./GatekeeperAPI";
```

Then add these fields:

```ts
export interface GetDatasetDetailsResponse {
    id: string
    name: string
    data: DatasetInfo
    tenancy: string
    is_enabled: boolean
    created_at: Date
    updated_at: Date
    versions: GetDatasetDetailsVersionResponse[]
    current_version: GetDatasetDetailsVersionResponse
    embargo?: DatasetEmbargo | null
    access?: DatasetAccess
    owner?: DatasetOwner | null
}

export interface GetDatasetDetailsVersionResponse {
    id: string
    name: string
    // TODO: convert design_state to Enum
    design_state: string
    is_enabled: boolean
    files_in: GetDatasetDetailsVersionFileResponse[]
    doi: GetDatasetDetailsDOIResponse
    created_by: string
    created_at: Date
    updated_at: Date
    files_withheld?: boolean
    files_summary?: FilesSummary
}
```

and, in `GetMinimalDatasetsDetasetDetailsResponse`, after `current_version: {...}`:

```ts
    embargo?: DatasetEmbargo | null
    access?: DatasetAccess
```

`tailwind.config.js` — the palette is set in `theme.colors`, which replaces Tailwind's defaults, so there is no `amber-*` to use. Add, after `success: {…}`, the design's colours (`docs/design/rfc-003-embargo/Embargo Feature.dc.html`: badge `#fef3c7`/`#92400e`, card `#fffbeb`/`#fde68a`; destructive text `#b91c1c`, error box `#fef2f2`/`#fecaca`/`#991b1b`):

```js
			embargo: {
				'50': '#fffbeb',
				'100': '#fef3c7',
				'200': '#fde68a',
				'800': '#92400e'
			},
			danger: {
				'50': '#fef2f2',
				'200': '#fecaca',
				'700': '#b91c1c',
				'800': '#991b1b'
			}
```

Amber is reserved for "under embargo" — badge, card, notice — as the design states; nothing else uses `embargo-*`. Confirm buttons of destructive dialogs keep `PopupModal`'s existing `destructive` style; `danger-700` is for text actions ("End early", "Revoke", "Remove access") and the ORCID error box.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/rpc.test.ts contants/__tests__/EmbargoConstants.test.ts`
Expected: PASS (all tests in both files).

- [ ] **Step 5: Type-check**

Run: `npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E "types/(GatekeeperAPI|BffAPI|APIError)|lib/rpc|EmbargoConstants" || echo "no new type errors"`
Expected: `no new type errors`

- [ ] **Step 6: Commit**

```bash
git add types/GatekeeperAPI.ts types/BffAPI.ts types/APIError.ts lib/rpc.ts lib/__tests__/rpc.test.ts contants/EmbargoConstants.ts contants/__tests__/EmbargoConstants.test.ts tailwind.config.js
git commit -m "feat: types, error messages and the embargo colour"
```

---

### Task 2: Route and telemetry constants

**Files:**
- Modify: `contants/InternalRoutesConstants.ts`
- Modify: `contants/TelemetryConstants.ts:5-42`
- Test: `contants/__tests__/InternalRoutesConstants_test.ts` (append), `contants/__tests__/TelemetryConstants.test.ts` (append)

**Interfaces:**
- Produces: `ROUTE_PAGE_DATASETS_SHARED: string`, `ROUTE_PAGE_ANONYMOUS(params: { token }): string`, `ROUTE_PAGE_INVITATION(params: { token }): string`, `ROUTE_PAGE_DOI_LANDING(params: { id, versionName }): string`; UI events `embargo_set`, `embargo_extended`, `dataset_shared`, `anonymous_link_created`.

- [ ] **Step 1: Write the failing tests**

Append to `contants/__tests__/InternalRoutesConstants_test.ts`:

```ts
import {
    ROUTE_PAGE_DATASETS_SHARED,
    ROUTE_PAGE_DOI_LANDING,
    ROUTE_PAGE_INVITATION,
    ROUTE_PAGE_ANONYMOUS,
} from "../InternalRoutesConstants";

test('Shared with me route', () => {
    expect(ROUTE_PAGE_DATASETS_SHARED).toBe("/app/datasets/shared")
})

test('Anonymous route', () => {
    expect(ROUTE_PAGE_ANONYMOUS({ token: "abc" })).toBe("/anonymous/abc")
})

test('Invitation route', () => {
    expect(ROUTE_PAGE_INVITATION({ token: "xyz" })).toBe("/invitations/xyz")
})

test('DOI landing route', () => {
    expect(ROUTE_PAGE_DOI_LANDING({ id: "d1", versionName: "2" })).toBe("/doi/datasets/d1/versions/2")
})
```

Append to `contants/__tests__/TelemetryConstants.test.ts`:

```ts
describe("the embargo telemetry", () => {
  it("knows the new pages", () => {
    for (const page of [
      "/app/datasets/shared",
      "/anonymous/[token]",
      "/invitations/[token]",
      "/doi/datasets/[datasetId]/versions/[versionName]",
    ]) {
      expect(pageLabel(page)).toBe(page);
    }
  });

  it("accepts the new ui events", () => {
    for (const event of ["embargo_set", "embargo_extended", "dataset_shared", "anonymous_link_created"]) {
      expect(uiEventLabel(event)).toBe(event);
    }
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest contants/__tests__`
Expected: FAIL — the new route exports are undefined; `pageLabel("/anonymous/[token]")` returns `"other"`.

- [ ] **Step 3: Implement**

In `contants/InternalRoutesConstants.ts`, after `ROUTE_PAGE_DATASETS_NEW`:

```ts
/**
 * Route to the datasets shared with the user.
 * @constant
 */
export const ROUTE_PAGE_DATASETS_SHARED = ROUTE_PAGE_DATASETS + "/shared";

/**
 * Route to the anonymous page.
 * @constant
 */
export const ROUTE_PAGE_ANONYMOUS = (params) => replaceIt('/anonymous/:token', params);

/**
 * Route to the invitation acceptance page.
 * @constant
 */
export const ROUTE_PAGE_INVITATION = (params) => replaceIt('/invitations/:token', params);

/**
 * Route a DOI resolves to.
 * @constant
 */
export const ROUTE_PAGE_DOI_LANDING = (params) => replaceIt('/doi/datasets/:id/versions/:versionName', params);
```

In `contants/TelemetryConstants.ts`, `PAGES` becomes:

```ts
export const PAGES: readonly string[] = [
  "/",
  "/404",
  "/500",
  "/account/login",
  "/app/datasets",
  "/app/datasets/[datasetId]",
  "/app/datasets/[datasetId]/versions/[versionName]",
  "/app/datasets/new",
  "/app/datasets/shared",
  "/app/error",
  "/app/home",
  "/app/notebooks",
  "/app/profile",
  "/app/tenancy",
  "/datasets/[datasetId]",
  "/design-system",
  "/doi/datasets/[datasetId]/versions/[versionName]",
  "/invitations/[token]",
  "/orcid-oauth-callback",
  "/project/about",
  "/project/data-policy",
  "/project/partners-and-supporters",
  "/project/research-group",
  "/project/support",
  "/anonymous/[token]",
  "/tools",
];
```

and `UI_EVENTS` becomes:

```ts
export const UI_EVENTS = [
  "search",
  "filter_applied",
  "download_clicked",
  "upload_started",
  "upload_completed",
  "upload_failed",
  "dataset_created",
  "version_created",
  "version_published",
  "doi_created",
  "tenancy_switched",
  "embargo_set",
  "embargo_extended",
  "dataset_shared",
  "anonymous_link_created",
] as const;
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest contants/__tests__`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add contants/InternalRoutesConstants.ts contants/TelemetryConstants.ts contants/__tests__/
git commit -m "feat: routes and telemetry names for the embargo pages"
```

---

### Task 3: Pure helpers — share target and embargo dates

**Files:**
- Create: `lib/shareTarget.ts`, `lib/embargoDates.ts`, `lib/embargoState.ts`, `lib/embargoDisplay.ts`
- Test: `lib/__tests__/shareTarget.test.ts`, `lib/__tests__/embargoDates.test.ts`, `lib/__tests__/embargoState.test.ts`, `lib/__tests__/embargoDisplay.test.ts`

**Interfaces:**
- Consumes: `MAX_EMBARGO_DAYS` (Task 1), `GetDatasetDetailsResponse`, `GetDatasetDetailsDOIResponseState` (`types/BffAPI.ts`), `SetEmbargoRequest` (Task 1).
- Produces:
  - `type ShareTarget = { kind: "email" | "orcid" | "invalid_orcid" | "text", value: string }`
  - `isValidOrcidChecksum(orcid: string): boolean`, `classifyShareInput(raw: string): ShareTarget`
  - `toDateInputValue(date: Date): string`, `minEmbargoDate(now: Date): string`, `maxEmbargoDate(now: Date): string`, `minExtensionDate(currentUntil: string, now: Date): string`, `toEmbargoUntil(dateInput: string): string`, `validateEmbargoDate(dateInput: string, now: Date, min?: string): string | undefined`, `formatEmbargoDate(iso: string): string`, `embargoRequestFrom(values: { embargoMode?: EmbargoMode, embargoUntil?: string }): SetEmbargoRequest | null`, `type EmbargoMode = "none" | "open" | "hidden"`
  - `isFilesWithheld(dataset): boolean`, `shouldShowEmbargoEndedBanner(dataset): boolean`, `canSeeSettings(dataset, canEdit: boolean): boolean`
  - `type ManualDoiGate = "ends_embargo" | "owner_only" | "blocks_future_embargo"`, `manualDoiGate(dataset): ManualDoiGate`, `hasManualDoi(dataset): boolean`
  - `lib/embargoDisplay.ts` — the wording the design uses (`docs/design/rfc-003-embargo/Embargo Feature.dc.html`): `formatShortDate(iso, withYear = true)` ("Dec 15, 2026" / "Dec 15"), `formatHistoryWhen(iso)` ("Sep 26, 2026 14:02"), `daysLeft(iso, now)`, `daysFromToday(dateInput, now)`, `tenancyDisplayName(path)` ("datamap/production/data-amazon" → "Data Amazon"), `initialsOf(name)`, `describeLinkStats(link, now)` ("Created Sep 14 · first opened Sep 16 · last opened yesterday"), `describeAccessEvent(entry): { icon, who, what, detail }` (the History rows of §1g)

- [ ] **Step 1: Write the failing tests**

`lib/__tests__/shareTarget.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import { classifyShareInput, isValidOrcidChecksum } from "../shareTarget";

describe('isValidOrcidChecksum', () => {
    test.each([
        "0000-0002-1825-0097",
        "0000-0001-5109-3700",
        "0000-0002-6356-145X",
        "0000-0002-1694-233X",
    ])('%s is valid', (orcid) => {
        expect(isValidOrcidChecksum(orcid)).toBe(true);
    });

    test('a wrong check digit is invalid', () => {
        expect(isValidOrcidChecksum("0000-0002-1825-0098")).toBe(false);
    });

    test('anything that is not 16 characters of digits is invalid', () => {
        expect(isValidOrcidChecksum("0000-0002-1825")).toBe(false);
    });
});

describe('classifyShareInput', () => {
    test('a bare ORCID', () => {
        expect(classifyShareInput("0000-0002-1825-0097")).toEqual({ kind: "orcid", value: "0000-0002-1825-0097" });
    });

    test('an ORCID URL becomes the bare form', () => {
        expect(classifyShareInput(" https://orcid.org/0000-0002-6356-145x ")).toEqual({ kind: "orcid", value: "0000-0002-6356-145X" });
    });

    test('a mistyped ORCID is recognised as an invalid ORCID, not as text', () => {
        expect(classifyShareInput("0000-0002-1825-0098")).toEqual({ kind: "invalid_orcid", value: "0000-0002-1825-0098" });
    });

    test('an email', () => {
        expect(classifyShareInput("Ana.Souza@USP.br")).toEqual({ kind: "email", value: "ana.souza@usp.br" });
    });

    test('anything else is text to search with', () => {
        expect(classifyShareInput("ana sou")).toEqual({ kind: "text", value: "ana sou" });
        expect(classifyShareInput("ana@")).toEqual({ kind: "text", value: "ana@" });
    });
});
```

`lib/__tests__/embargoDates.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import {
    embargoRequestFrom,
    formatEmbargoDate,
    maxEmbargoDate,
    minEmbargoDate,
    minExtensionDate,
    toEmbargoUntil,
    validateEmbargoDate,
} from "../embargoDates";

const NOW = new Date("2026-09-30T10:00:00Z");

describe('embargo dates', () => {
    test('the earliest date is tomorrow', () => {
        expect(minEmbargoDate(NOW)).toBe("2026-10-01");
    });

    test('the latest date ends before now plus 90 days, so the server never refuses it', () => {
        const max = maxEmbargoDate(NOW);
        expect(max).toBe("2026-12-28");
        const endOfMax = new Date(toEmbargoUntil(max)).getTime();
        expect(endOfMax).toBeLessThanOrEqual(NOW.getTime() + 90 * 24 * 60 * 60 * 1000);
    });

    test('the latest date holds just before midnight too', () => {
        const lateNow = new Date("2026-09-30T23:59:59Z");
        const endOfMax = new Date(toEmbargoUntil(maxEmbargoDate(lateNow))).getTime();
        expect(endOfMax).toBeLessThanOrEqual(lateNow.getTime() + 90 * 24 * 60 * 60 * 1000);
    });

    test('until is the end of the chosen UTC day', () => {
        expect(toEmbargoUntil("2026-12-01")).toBe("2026-12-01T23:59:59+00:00");
    });

    test('an extension starts the day after the current end', () => {
        expect(minExtensionDate("2026-10-10T23:59:59+00:00", NOW)).toBe("2026-10-11");
    });

    test('an extension never starts before tomorrow', () => {
        expect(minExtensionDate("2026-09-01T23:59:59+00:00", NOW)).toBe("2026-10-01");
    });

    test.each([
        ["", "Required"],
        ["2026-09-30", "Choose a date after today."],
        ["2026-12-29", "An embargo can last at most 90 days."],
    ])('%s is refused with "%s"', (date, message) => {
        expect(validateEmbargoDate(date, NOW)).toBe(message);
    });

    test('a date inside the window is accepted', () => {
        expect(validateEmbargoDate("2026-12-28", NOW)).toBeUndefined();
    });

    test('a custom minimum is honoured', () => {
        expect(validateEmbargoDate("2026-10-05", NOW, "2026-10-11")).toBe("Choose a date after the current end of the embargo.");
    });

    test('dates are shown as a day, in UTC', () => {
        expect(formatEmbargoDate("2026-12-28T23:59:59+00:00")).toBe("December 28, 2026");
    });
});

describe('embargoRequestFrom', () => {
    test('no embargo builds no request', () => {
        expect(embargoRequestFrom({ embargoMode: "none", embargoUntil: "2026-12-01" })).toBeNull();
        expect(embargoRequestFrom({})).toBeNull();
    });

    test('open mode makes the metadata visible', () => {
        expect(embargoRequestFrom({ embargoMode: "open", embargoUntil: "2026-12-01" })).toEqual({
            until: "2026-12-01T23:59:59+00:00",
            metadata_visible: true,
            note: null,
        });
    });

    test('hidden mode keeps the metadata hidden', () => {
        expect(embargoRequestFrom({ embargoMode: "hidden", embargoUntil: "2026-12-01" })?.metadata_visible).toBe(false);
    });
});
```

`lib/__tests__/embargoState.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import { canSeeSettings, hasManualDoi, isFilesWithheld, manualDoiGate, shouldShowEmbargoEndedBanner } from "../embargoState";

function dataset(overrides: any = {}): any {
    return {
        id: "d1",
        embargo: { until: "2026-09-01T23:59:59+00:00", active: false, metadata_visible: false, note: null },
        access: { level: "owner", can_edit: true, can_share: true, can_manage_embargo: true, can_extend_embargo: false, can_delete: true },
        current_version: { name: "1", doi: { state: "REGISTERED" }, files_withheld: false },
        ...overrides,
    };
}

describe('shouldShowEmbargoEndedBanner', () => {
    test('the owner sees it after the embargo while the DOI is not findable', () => {
        expect(shouldShowEmbargoEndedBanner(dataset())).toBe(true);
    });

    test('not once the DOI is findable', () => {
        expect(shouldShowEmbargoEndedBanner(dataset({ current_version: { doi: { state: "FINDABLE" } } }))).toBe(false);
    });

    test('not while the embargo lasts', () => {
        expect(shouldShowEmbargoEndedBanner(dataset({ embargo: { until: "2026-12-01T23:59:59+00:00", active: true } }))).toBe(false);
    });

    test('not for someone other than the owner', () => {
        expect(shouldShowEmbargoEndedBanner(dataset({ access: { level: "write" } }))).toBe(false);
    });

    test('not for a dataset that never had an embargo', () => {
        expect(shouldShowEmbargoEndedBanner(dataset({ embargo: null }))).toBe(false);
    });
});

describe('isFilesWithheld', () => {
    test('true when the current version withholds its files', () => {
        expect(isFilesWithheld(dataset({ current_version: { files_withheld: true } }))).toBe(true);
    });

    test('false otherwise', () => {
        expect(isFilesWithheld(dataset())).toBe(false);
    });
});

describe('canSeeSettings', () => {
    test('an editor sees settings', () => {
        expect(canSeeSettings(dataset({ access: undefined }), true)).toBe(true);
    });

    test('someone who can only extend still sees settings', () => {
        expect(canSeeSettings(dataset({ access: { can_extend_embargo: true, can_manage_embargo: false } }), false)).toBe(true);
    });

    test('a reader does not', () => {
        expect(canSeeSettings(dataset({ access: { can_extend_embargo: false, can_manage_embargo: false } }), false)).toBe(false);
    });
});

describe('manual DOI', () => {
    const active = { until: "2026-12-01T23:59:59+00:00", active: true, metadata_visible: false, note: null };

    test('under embargo, the owner may end it by registering one', () => {
        expect(manualDoiGate(dataset({ embargo: active }))).toBe("ends_embargo");
    });

    test('under embargo, anyone else is told only the owner can', () => {
        expect(manualDoiGate(dataset({ embargo: active, access: { level: "write", can_manage_embargo: false } }))).toBe("owner_only");
        expect(manualDoiGate(dataset({ embargo: active, access: undefined }))).toBe("owner_only");
    });

    test('without an embargo, registering one rules out a future embargo', () => {
        expect(manualDoiGate(dataset({ embargo: null }))).toBe("blocks_future_embargo");
        expect(manualDoiGate(dataset())).toBe("blocks_future_embargo");
    });

    test('a manual DOI on any version counts', () => {
        expect(hasManualDoi(dataset({ versions: [{ doi: null }, { doi: { mode: "MANUAL" } }] }))).toBe(true);
        expect(hasManualDoi(dataset({ versions: [{ doi: { mode: "AUTO" } }] }))).toBe(false);
        expect(hasManualDoi(dataset({ versions: undefined }))).toBe(false);
    });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest lib/__tests__/shareTarget.test.ts lib/__tests__/embargoDates.test.ts lib/__tests__/embargoState.test.ts`
Expected: FAIL — `Cannot find module '../shareTarget'` (and the other two).

- [ ] **Step 3: Implement**

`lib/shareTarget.ts`:

```ts
export type ShareTarget =
    | { kind: "email", value: string }
    | { kind: "orcid", value: string }
    | { kind: "invalid_orcid", value: string }
    | { kind: "text", value: string };

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const ORCID = /^(?:https?:\/\/orcid\.org\/)?(\d{4}-\d{4}-\d{4}-\d{3}[\dXx])$/;

// ISO 7064 mod 11-2, the same check the gatekeeper applies.
export function isValidOrcidChecksum(orcid: string): boolean {
    const digits = orcid.replace(/-/g, "").toUpperCase();
    if (!/^\d{15}[\dX]$/.test(digits)) {
        return false;
    }
    let total = 0;
    for (const c of digits.slice(0, 15)) {
        total = (total + Number(c)) * 2;
    }
    const result = (12 - (total % 11)) % 11;
    return digits[15] === (result === 10 ? "X" : String(result));
}

export function classifyShareInput(raw: string): ShareTarget {
    const value = raw.trim();
    const orcid = ORCID.exec(value);
    if (orcid) {
        const bare = orcid[1].toUpperCase();
        return isValidOrcidChecksum(bare)
            ? { kind: "orcid", value: bare }
            : { kind: "invalid_orcid", value: bare };
    }
    if (EMAIL.test(value)) {
        return { kind: "email", value: value.toLowerCase() };
    }
    return { kind: "text", value };
}
```

`lib/embargoDates.ts`:

```ts
import { MAX_EMBARGO_DAYS } from "../contants/EmbargoConstants";
import { SetEmbargoRequest } from "../types/GatekeeperAPI";

export type EmbargoMode = "none" | "open" | "hidden";

const DAY_MS = 24 * 60 * 60 * 1000;

export function toDateInputValue(date: Date): string {
    return date.toISOString().slice(0, 10);
}

export function minEmbargoDate(now: Date): string {
    return toDateInputValue(new Date(now.getTime() + DAY_MS));
}

// 89, not 90: the chosen day ends at 23:59:59, which must stay within now + 90 days.
export function maxEmbargoDate(now: Date): string {
    return toDateInputValue(new Date(now.getTime() + (MAX_EMBARGO_DAYS - 1) * DAY_MS));
}

export function minExtensionDate(currentUntil: string, now: Date): string {
    const dayAfterCurrent = toDateInputValue(new Date(new Date(currentUntil).getTime() + DAY_MS));
    const tomorrow = minEmbargoDate(now);
    return dayAfterCurrent > tomorrow ? dayAfterCurrent : tomorrow;
}

export function toEmbargoUntil(dateInput: string): string {
    return `${dateInput}T23:59:59+00:00`;
}

export function validateEmbargoDate(dateInput: string, now: Date, min?: string): string | undefined {
    if (!dateInput) {
        return "Required";
    }
    if (min && dateInput < min) {
        return "Choose a date after the current end of the embargo.";
    }
    if (dateInput < minEmbargoDate(now)) {
        return "Choose a date after today.";
    }
    if (dateInput > maxEmbargoDate(now)) {
        return `An embargo can last at most ${MAX_EMBARGO_DAYS} days.`;
    }
    return undefined;
}

export function formatEmbargoDate(iso: string): string {
    return new Date(iso).toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
        timeZone: "UTC",
    });
}

export function embargoRequestFrom(values: { embargoMode?: EmbargoMode, embargoUntil?: string }): SetEmbargoRequest | null {
    if (!values.embargoMode || values.embargoMode === "none") {
        return null;
    }
    return {
        until: toEmbargoUntil(values.embargoUntil),
        metadata_visible: values.embargoMode === "open",
        note: null,
    };
}
```

`lib/embargoState.ts`:

```ts
import { GetDatasetDetailsDOIResponseRegisterMode, GetDatasetDetailsDOIResponseState, GetDatasetDetailsResponse } from "../types/BffAPI";

export type ManualDoiGate = "ends_embargo" | "owner_only" | "blocks_future_embargo";

export function isFilesWithheld(dataset: GetDatasetDetailsResponse): boolean {
    return dataset?.current_version?.files_withheld === true;
}

export function shouldShowEmbargoEndedBanner(dataset: GetDatasetDetailsResponse): boolean {
    return dataset?.access?.level === "owner"
        && !!dataset.embargo
        && !dataset.embargo.active
        && dataset.current_version?.doi?.state !== GetDatasetDetailsDOIResponseState.FINDABLE;
}

export function canSeeSettings(dataset: GetDatasetDetailsResponse, canEdit: boolean): boolean {
    return canEdit
        || dataset?.access?.can_extend_embargo === true
        || dataset?.access?.can_manage_embargo === true;
}

export function manualDoiGate(dataset: GetDatasetDetailsResponse): ManualDoiGate {
    if (dataset?.embargo?.active) {
        return dataset.access?.can_manage_embargo ? "ends_embargo" : "owner_only";
    }
    return "blocks_future_embargo";
}

export function hasManualDoi(dataset: GetDatasetDetailsResponse): boolean {
    return (dataset?.versions ?? []).some((version) => version?.doi?.mode === GetDatasetDetailsDOIResponseRegisterMode.MANUAL);
}
```

- [ ] **Step 4: The wording of the design**

The screens write dates short ("Dec 15, 2026", and "Dec 15" in a list badge), count days ("75 days left"), name the tenancy as people say it ("Data Amazon"), and word each history entry and link (§1b, §1c, §1f, §1g). One file holds that wording so every component says it the same way.

`lib/__tests__/embargoDisplay.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import {
    daysFromToday,
    daysLeft,
    describeAccessEvent,
    describeLinkStats,
    formatHistoryWhen,
    formatShortDate,
    initialsOf,
    tenancyDisplayName,
} from "../embargoDisplay";

const NOW = new Date("2026-10-01T10:00:00Z");

function entry(overrides: any): any {
    return { event_type: "created", occurred_at: "2026-09-09T17:28:00Z", actor: { id: "u", name: "Luciana Rizzo" }, subject: null, old_value: null, new_value: null, note: null, ...overrides };
}

describe("dates and counts", () => {
    test("short dates, with and without the year", () => {
        expect(formatShortDate("2026-12-15T23:59:59+00:00")).toBe("Dec 15, 2026");
        expect(formatShortDate("2026-12-15T23:59:59+00:00", false)).toBe("Dec 15");
    });

    test("the history's moment, in UTC", () => {
        expect(formatHistoryWhen("2026-09-26T14:02:00Z")).toBe("Sep 26, 2026 14:02");
    });

    test("days left round up and never go below zero", () => {
        expect(daysLeft("2026-12-15T23:59:59+00:00", NOW)).toBe(76);
        expect(daysLeft("2026-09-01T23:59:59+00:00", NOW)).toBe(0);
    });

    test("days from today to a chosen date", () => {
        expect(daysFromToday("2026-12-15", NOW)).toBe(75);
    });
});

describe("names", () => {
    test("a tenancy is named by its last segment", () => {
        expect(tenancyDisplayName("datamap/production/data-amazon")).toBe("Data Amazon");
        expect(tenancyDisplayName(undefined)).toBe("the workspace");
    });

    test("initials of a name", () => {
        expect(initialsOf("Luciana Varanda Rizzo")).toBe("LR");
        expect(initialsOf("ana")).toBe("A");
        expect(initialsOf("")).toBe("?");
    });
});

describe("anonymous link stats", () => {
    test("a link never opened", () => {
        expect(describeLinkStats({ created_at: "2026-09-26T10:00:00Z", views: { count: 0, first_at: null, last_at: null } } as any, NOW))
            .toBe("Created Sep 26 · not opened yet");
    });

    test("a link opened yesterday", () => {
        expect(describeLinkStats({ created_at: "2026-09-14T10:00:00Z", views: { count: 12, first_at: "2026-09-16T10:00:00Z", last_at: "2026-09-30T09:00:00Z" } } as any, NOW))
            .toBe("Created Sep 14 · first opened Sep 16 · last opened yesterday");
    });
});

describe("describeAccessEvent", () => {
    test("setting an embargo", () => {
        expect(describeAccessEvent(entry({ new_value: { until: "2026-11-30T23:59:59+00:00", metadata_visible: false }, note: "Under review at JGR Atmospheres" })))
            .toEqual({ icon: "lock", who: "Luciana Rizzo", what: "set an embargo until Nov 30, 2026", detail: "hidden from members · \"Under review at JGR Atmospheres\"" });
    });

    test("an extension says what it was and why", () => {
        expect(describeAccessEvent(entry({ event_type: "extended", old_value: { until: "2026-11-30T23:59:59+00:00" }, new_value: { until: "2026-12-15T23:59:59+00:00" }, note: "Second review round requested" })))
            .toEqual({ icon: "update", who: "Luciana Rizzo", what: "extended the embargo to Dec 15, 2026", detail: "was Nov 30, 2026 · \"Second review round requested\"" });
    });

    test("a grant names the person", () => {
        expect(describeAccessEvent(entry({ event_type: "permission_granted", actor: { id: "a", name: "Alan Calheiros" }, subject: "Caio Maia", new_value: { level: "read" } })))
            .toEqual({ icon: "person_add", who: "Alan Calheiros", what: "granted read access to Caio Maia", detail: "" });
    });

    test("a mode change says which way", () => {
        expect(describeAccessEvent(entry({ event_type: "metadata_mode_changed", old_value: { metadata_visible: false }, new_value: { metadata_visible: true } })).what)
            .toBe("made the dataset visible to members");
    });

    test("an anonymous link shows its label as the detail", () => {
        expect(describeAccessEvent(entry({ event_type: "anonymous_link_created", subject: "AGU Fall Meeting abstract" })))
            .toEqual({ icon: "link", who: "Luciana Rizzo", what: "created anonymous link", detail: "AGU Fall Meeting abstract" });
    });

    test("the system's own events are signed by DataMap", () => {
        expect(describeAccessEvent(entry({ event_type: "expired", actor: null })).who).toBe("DataMap");
    });

    test("an early end by an external DOI says so", () => {
        expect(describeAccessEvent(entry({ event_type: "ended_early", note: "manual DOI" })).detail).toBe("by registering an external DOI");
    });
});
```

`lib/embargoDisplay.ts`:

```ts
import { AccessHistoryEntry, AnonymousLink } from "../types/GatekeeperAPI";

const DAY_MS = 24 * 60 * 60 * 1000;

export function formatShortDate(iso: string, withYear = true): string {
    return new Date(iso).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        ...(withYear ? { year: "numeric" } : {}),
        timeZone: "UTC",
    });
}

export function formatHistoryWhen(iso: string): string {
    const date = new Date(iso);
    const time = `${String(date.getUTCHours()).padStart(2, "0")}:${String(date.getUTCMinutes()).padStart(2, "0")}`;
    return `${formatShortDate(iso)} ${time}`;
}

export function daysLeft(iso: string, now: Date): number {
    return Math.max(0, Math.ceil((new Date(iso).getTime() - now.getTime()) / DAY_MS));
}

export function daysFromToday(dateInput: string, now: Date): number {
    const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    return Math.round((new Date(`${dateInput}T00:00:00Z`).getTime() - today) / DAY_MS);
}

export function tenancyDisplayName(path?: string | null): string {
    if (!path) {
        return "the workspace";
    }
    const last = path.replace(/\/+$/, "").split("/").pop() ?? path;
    return last.split(/[-_]/).filter(Boolean).map((word) => word[0].toUpperCase() + word.slice(1)).join(" ");
}

export function initialsOf(name: string): string {
    const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
    if (words.length === 0) {
        return "?";
    }
    const first = words[0][0];
    const last = words.length > 1 ? words[words.length - 1][0] : "";
    return (first + last).toUpperCase();
}

function relativeDay(iso: string, now: Date): string {
    const days = daysFromToday(new Date(iso).toISOString().slice(0, 10), now);
    if (days === 0) {
        return "today";
    }
    if (days === -1) {
        return "yesterday";
    }
    return formatShortDate(iso, false);
}

export function describeLinkStats(link: AnonymousLink, now: Date): string {
    const created = `Created ${formatShortDate(link.created_at, false)}`;
    if (!link.views?.count || !link.views.first_at || !link.views.last_at) {
        return `${created} · not opened yet`;
    }
    return `${created} · first opened ${formatShortDate(link.views.first_at, false)} · last opened ${relativeDay(link.views.last_at, now)}`;
}

function quoted(text: string | null | undefined): string {
    return text ? `"${text}"` : "";
}

function joined(...parts: string[]): string {
    return parts.filter(Boolean).join(" · ");
}

export function describeAccessEvent(entry: AccessHistoryEntry): { icon: string, who: string, what: string, detail: string } {
    const who = entry.actor?.name ?? "DataMap";
    const before = (entry.old_value ?? {}) as Record<string, any>;
    const after = (entry.new_value ?? {}) as Record<string, any>;
    const subject = entry.subject ?? "someone";

    switch (entry.event_type) {
        case "created":
            return { icon: "lock", who, what: `set an embargo until ${formatShortDate(after.until)}`, detail: joined(after.metadata_visible ? "visible to members" : "hidden from members", quoted(entry.note)) };
        case "extended":
            return { icon: "update", who, what: `extended the embargo to ${formatShortDate(after.until)}`, detail: joined(before.until ? `was ${formatShortDate(before.until)}` : "", quoted(entry.note)) };
        case "ended_early":
            return { icon: "lock_open", who, what: "ended the embargo early", detail: entry.note === "manual DOI" ? "by registering an external DOI" : "" };
        case "expired":
            return { icon: "lock_open", who, what: "the embargo ended", detail: "" };
        case "metadata_mode_changed":
            return after.metadata_visible
                ? { icon: "visibility", who, what: "made the dataset visible to members", detail: "was hidden" }
                : { icon: "visibility_off", who, what: "hid the dataset from members", detail: "was visible" };
        case "note_changed":
            return { icon: "edit_note", who, what: after.note ? "changed the note" : "removed the note", detail: quoted(after.note) };
        case "permission_granted":
            return entry.old_value
                ? { icon: "manage_accounts", who, what: `changed ${subject}'s access to ${after.level}`, detail: "" }
                : { icon: "person_add", who, what: `granted ${after.level} access to ${subject}`, detail: "" };
        case "permission_revoked":
            return { icon: "person_remove", who, what: `removed ${subject}'s access`, detail: "" };
        case "invitation_created":
            return { icon: "mail", who, what: `invited ${subject}`, detail: "" };
        case "invitation_revoked":
            return { icon: "cancel_schedule_send", who, what: `revoked the invitation to ${subject}`, detail: "" };
        case "anonymous_link_created":
            return { icon: "link", who, what: "created anonymous link", detail: entry.subject ?? "" };
        case "anonymous_link_revoked":
            return { icon: "link_off", who, what: "revoked anonymous link", detail: entry.subject ?? "" };
        default:
            return { icon: "history", who, what: entry.event_type.replace(/_/g, " "), detail: "" };
    }
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/shareTarget.test.ts lib/__tests__/embargoDates.test.ts lib/__tests__/embargoState.test.ts lib/__tests__/embargoDisplay.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add lib/shareTarget.ts lib/embargoDates.ts lib/embargoState.ts lib/embargoDisplay.ts lib/__tests__/shareTarget.test.ts lib/__tests__/embargoDates.test.ts lib/__tests__/embargoState.test.ts lib/__tests__/embargoDisplay.test.ts
git commit -m "feat: recognise emails and ORCIDs, the embargo date limits and the design's wording"
```

---

### Task 4: Server calls to the gatekeeper

**Files:**
- Create: `lib/embargo.ts`, `lib/share.ts`
- Modify: `lib/dataset.ts` (add `getSharedDatasets`)
- Test: `lib/__tests__/embargo.test.ts`, `lib/__tests__/share.test.ts`, `lib/__tests__/dataset.test.ts` (append)

**Interfaces:**
- Consumes: Task 1 types; `AppLocalContext`, `axiosInstance`, `buildHeaders` (`lib/rpc.ts`).
- Produces:
  - `setEmbargo(context, datasetId, request: SetEmbargoRequest): Promise<DatasetEmbargo>`
  - `extendEmbargo(context, datasetId, request: ExtendEmbargoRequest): Promise<DatasetEmbargo>`
  - `endEmbargo(context, datasetId): Promise<DatasetEmbargo>`
  - `setEmbargoMode(context, datasetId, request: EmbargoModeRequest): Promise<DatasetEmbargo>`
  - `getEmbargoStatus(datasetId, versionName?): Promise<EmbargoStatusResponse>`
  - `setEmbargoNote(context, datasetId, request: EmbargoNoteRequest): Promise<DatasetEmbargo>` (design §1g)
  - `getAccessEvents(context, datasetId): Promise<AccessHistoryResponse>` (design §1g History)
  - `getInvitationPreview(token): Promise<InvitationPreview>` (design §1i Accept invitation)
  - `searchShareCandidates(context, datasetId, q): Promise<ShareUser[]>`
  - `getShareState(context, datasetId): Promise<ShareState>`
  - `grantAccess(context, datasetId, request: GrantRequest): Promise<GrantResult>`
  - `changePermissionLevel(context, datasetId, userId, level: PermissionLevel): Promise<SharePermission>`
  - `revokePermission(context, datasetId, userId): Promise<void>`
  - `revokeInvitation(context, datasetId, invitationId): Promise<void>`
  - `regenerateInvitationLink(context, datasetId, invitationId): Promise<{ link: string }>`
  - `createAnonymousLink(context, datasetId, label): Promise<CreatedAnonymousLink>`
  - `revokeAnonymousLink(context, datasetId, linkId): Promise<void>`
  - `getAnonymousPage(token): Promise<AnonymousPageResponse>`
  - `acceptInvitation(context, token): Promise<AcceptInvitationResponse>`
  - `claimInvitations(uid): Promise<ClaimInvitationsResponse>`
  - `getSharedDatasets(context, query: { [key: string]: string | string[] }): Promise<GetDatasetsResponse>`

- [ ] **Step 1: Write the failing tests**

`lib/__tests__/embargo.test.ts`:

```ts
import { endEmbargo, extendEmbargo, getEmbargoStatus, setEmbargo, setEmbargoMode } from "../embargo";
import axiosInstance, { buildHeaders } from "../rpc";

jest.mock("../rpc")
const mockGet = jest.mocked(axiosInstance.get)
const mockPut = jest.mocked(axiosInstance.put)
const mockPost = jest.mocked(axiosInstance.post)
const mockBuildHeaders = jest.mocked(buildHeaders)

const context = { uid: "u1", tenancy: "datamap/production/data-amazon" };
const headers = { headers: { "X-User-Id": "u1" } };
const embargo = { until: "2026-12-01T23:59:59+00:00", active: true, metadata_visible: false, note: null };

beforeEach(() => {
    mockBuildHeaders.mockReturnValue(headers as any);
});

describe("embargo calls", () => {
    test("set", async () => {
        mockPut.mockResolvedValue({ data: embargo });
        const request = { until: embargo.until, metadata_visible: false, note: null };

        expect(await setEmbargo(context, "d1", request)).toEqual(embargo);
        expect(mockPut).toHaveBeenCalledWith("/datasets/d1/embargo", request, headers);
    });

    test("extend", async () => {
        mockPost.mockResolvedValue({ data: embargo });

        await extendEmbargo(context, "d1", { until: embargo.until });
        expect(mockPost).toHaveBeenCalledWith("/datasets/d1/embargo/extend", { until: embargo.until }, headers);
    });

    test("end", async () => {
        mockPost.mockResolvedValue({ data: { ...embargo, active: false } });

        expect((await endEmbargo(context, "d1")).active).toBe(false);
        expect(mockPost).toHaveBeenCalledWith("/datasets/d1/embargo/end", {}, headers);
    });

    test("mode", async () => {
        mockPut.mockResolvedValue({ data: { ...embargo, metadata_visible: true } });

        await setEmbargoMode(context, "d1", { metadata_visible: true });
        expect(mockPut).toHaveBeenCalledWith("/datasets/d1/embargo/mode", { metadata_visible: true }, headers);
    });

    test("status is asked without a user", async () => {
        mockGet.mockResolvedValue({ data: { embargoed: true, until: embargo.until } });

        expect(await getEmbargoStatus("d1")).toEqual({ embargoed: true, until: embargo.until });
        expect(mockGet).toHaveBeenCalledWith("/datasets/d1/embargo-status");
    });
});
```

`lib/__tests__/share.test.ts`:

```ts
import {
    acceptInvitation,
    changePermissionLevel,
    claimInvitations,
    createAnonymousLink,
    getAnonymousPage,
    getShareState,
    grantAccess,
    regenerateInvitationLink,
    revokeInvitation,
    revokePermission,
    revokeAnonymousLink,
    searchShareCandidates,
} from "../share";
import axiosInstance, { buildHeaders } from "../rpc";

jest.mock("../rpc")
const mockGet = jest.mocked(axiosInstance.get)
const mockPut = jest.mocked(axiosInstance.put)
const mockPost = jest.mocked(axiosInstance.post)
const mockDelete = jest.mocked(axiosInstance.delete)
const mockBuildHeaders = jest.mocked(buildHeaders)

const context = { uid: "u1", tenancy: "datamap/production/data-amazon" };
const headers = { headers: { "X-User-Id": "u1" } };

beforeEach(() => {
    mockBuildHeaders.mockReturnValue(headers as any);
});

describe("share calls", () => {
    test("candidates carry the query as a parameter", async () => {
        mockGet.mockResolvedValue({ data: [{ id: "u2", name: "Ana", email: "ana@usp.br" }] });

        expect(await searchShareCandidates(context, "d1", "an")).toHaveLength(1);
        expect(mockGet).toHaveBeenCalledWith("/datasets/d1/share/candidates", { ...headers, params: { q: "an" } });
    });

    test("state", async () => {
        mockGet.mockResolvedValue({ data: { owner: {}, permissions: [], invitations: [], anonymous_links: [] } });

        await getShareState(context, "d1");
        expect(mockGet).toHaveBeenCalledWith("/datasets/d1/share", headers);
    });

    test("grant", async () => {
        mockPost.mockResolvedValue({ data: { kind: "invitation", invitation: {}, link: "https://x/invitations/t" } });

        expect((await grantAccess(context, "d1", { email: "a@b.co", level: "read" })).kind).toBe("invitation");
        expect(mockPost).toHaveBeenCalledWith("/datasets/d1/share", { email: "a@b.co", level: "read" }, headers);
    });

    test("change level", async () => {
        mockPut.mockResolvedValue({ data: {} });

        await changePermissionLevel(context, "d1", "u2", "write");
        expect(mockPut).toHaveBeenCalledWith("/datasets/d1/share/permissions/u2", { level: "write" }, headers);
    });

    test("revoke permission", async () => {
        mockDelete.mockResolvedValue({ status: 204 });

        await revokePermission(context, "d1", "u2");
        expect(mockDelete).toHaveBeenCalledWith("/datasets/d1/share/permissions/u2", headers);
    });

    test("revoke invitation", async () => {
        mockDelete.mockResolvedValue({ status: 204 });

        await revokeInvitation(context, "d1", "i1");
        expect(mockDelete).toHaveBeenCalledWith("/datasets/d1/share/invitations/i1", headers);
    });

    test("regenerate an invitation link", async () => {
        mockPost.mockResolvedValue({ data: { link: "https://x/invitations/new" } });

        expect(await regenerateInvitationLink(context, "d1", "i1")).toEqual({ link: "https://x/invitations/new" });
        expect(mockPost).toHaveBeenCalledWith("/datasets/d1/share/invitations/i1/link", {}, headers);
    });

    test("create an anonymous link", async () => {
        mockPost.mockResolvedValue({ data: { id: "r1", link: "https://x/anonymous/t" } });

        await createAnonymousLink(context, "d1", "JGR, round 1");
        expect(mockPost).toHaveBeenCalledWith("/datasets/d1/anonymous-links", { label: "JGR, round 1" }, headers);
    });

    test("revoke an anonymous link", async () => {
        mockDelete.mockResolvedValue({ status: 204 });

        await revokeAnonymousLink(context, "d1", "r1");
        expect(mockDelete).toHaveBeenCalledWith("/datasets/d1/anonymous-links/r1", headers);
    });

    test("the anonymous page is asked without a user", async () => {
        mockGet.mockResolvedValue({ data: { state: "published", dataset_id: "d1" } });

        await getAnonymousPage("a/b");
        expect(mockGet).toHaveBeenCalledWith("/anonymous/a%2Fb");
    });

    test("accept sends the user and the token", async () => {
        mockPost.mockResolvedValue({ data: { dataset_id: "d1", level: "read" } });

        await acceptInvitation(context, "tok");
        expect(mockPost).toHaveBeenCalledWith("/invitations/accept", { token: "tok" }, { headers: { "X-User-Id": "u1" } });
    });

    test("claim sends the user", async () => {
        mockPost.mockResolvedValue({ data: { accepted: [] } });

        await claimInvitations("u1");
        expect(mockPost).toHaveBeenCalledWith("/users/u1/invitations/claim", {}, { headers: { "X-User-Id": "u1" } });
    });
});
```

Append to `lib/__tests__/dataset.test.ts` (add `getSharedDatasets` to the existing import from `"../dataset"` and `buildHeaders` to the import from `"../rpc"`):

```ts
describe("shared datasets", () => {
    test("asks for the shared list, minimal, keeping the caller's paging", async () => {
        jest.mocked(buildHeaders).mockReturnValue({ headers: { "X-User-Id": "u1" } } as any);
        mockAxiosGet.mockResolvedValue({ data: { content: [], total_count: 0 } });
        const context = { uid: "u1", tenancy: undefined };

        await getSharedDatasets(context, { page: "2", page_size: "20" });

        expect(mockAxiosGet).toHaveBeenCalledWith("/datasets/", {
            headers: { "X-User-Id": "u1" },
            params: { page: "2", page_size: "20", minimal: "true", shared: "true" },
        });
    });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest lib/__tests__/embargo.test.ts lib/__tests__/share.test.ts lib/__tests__/dataset.test.ts`
Expected: FAIL — `Cannot find module '../embargo'`, `Cannot find module '../share'`, `getSharedDatasets is not a function`.

- [ ] **Step 3: Implement**

`lib/embargo.ts`:

```ts
import { DatasetEmbargo, EmbargoModeRequest, EmbargoStatusResponse, ExtendEmbargoRequest, SetEmbargoRequest } from "../types/GatekeeperAPI";
import { AppLocalContext } from "./appLocalContext";
import axiosInstance, { buildHeaders } from "./rpc";

export async function setEmbargo(context: AppLocalContext, datasetId: string, request: SetEmbargoRequest): Promise<DatasetEmbargo> {
    const response = await axiosInstance.put(`/datasets/${datasetId}/embargo`, request, buildHeaders(context));
    return response.data as DatasetEmbargo;
}

export async function extendEmbargo(context: AppLocalContext, datasetId: string, request: ExtendEmbargoRequest): Promise<DatasetEmbargo> {
    const response = await axiosInstance.post(`/datasets/${datasetId}/embargo/extend`, request, buildHeaders(context));
    return response.data as DatasetEmbargo;
}

export async function endEmbargo(context: AppLocalContext, datasetId: string): Promise<DatasetEmbargo> {
    const response = await axiosInstance.post(`/datasets/${datasetId}/embargo/end`, {}, buildHeaders(context));
    return response.data as DatasetEmbargo;
}

export async function setEmbargoMode(context: AppLocalContext, datasetId: string, request: EmbargoModeRequest): Promise<DatasetEmbargo> {
    const response = await axiosInstance.put(`/datasets/${datasetId}/embargo/mode`, request, buildHeaders(context));
    return response.data as DatasetEmbargo;
}

export async function getEmbargoStatus(datasetId: string): Promise<EmbargoStatusResponse> {
    const response = await axiosInstance.get(`/datasets/${encodeURIComponent(datasetId)}/embargo-status`);
    return response.data as EmbargoStatusResponse;
}
```

`lib/share.ts`:

```ts
import {
    AcceptInvitationResponse,
    ClaimInvitationsResponse,
    CreatedAnonymousLink,
    GrantRequest,
    GrantResult,
    PermissionLevel,
    AnonymousPageResponse,
    SharePermission,
    ShareState,
    ShareUser,
} from "../types/GatekeeperAPI";
import { AppLocalContext } from "./appLocalContext";
import axiosInstance, { buildHeaders } from "./rpc";

export async function searchShareCandidates(context: AppLocalContext, datasetId: string, q: string): Promise<ShareUser[]> {
    const response = await axiosInstance.get(`/datasets/${datasetId}/share/candidates`, {
        ...buildHeaders(context),
        params: { q },
    });
    return response.data as ShareUser[];
}

export async function getShareState(context: AppLocalContext, datasetId: string): Promise<ShareState> {
    const response = await axiosInstance.get(`/datasets/${datasetId}/share`, buildHeaders(context));
    return response.data as ShareState;
}

export async function grantAccess(context: AppLocalContext, datasetId: string, request: GrantRequest): Promise<GrantResult> {
    const response = await axiosInstance.post(`/datasets/${datasetId}/share`, request, buildHeaders(context));
    return response.data as GrantResult;
}

export async function changePermissionLevel(context: AppLocalContext, datasetId: string, userId: string, level: PermissionLevel): Promise<SharePermission> {
    const response = await axiosInstance.put(`/datasets/${datasetId}/share/permissions/${userId}`, { level }, buildHeaders(context));
    return response.data as SharePermission;
}

export async function revokePermission(context: AppLocalContext, datasetId: string, userId: string): Promise<void> {
    await axiosInstance.delete(`/datasets/${datasetId}/share/permissions/${userId}`, buildHeaders(context));
}

export async function revokeInvitation(context: AppLocalContext, datasetId: string, invitationId: string): Promise<void> {
    await axiosInstance.delete(`/datasets/${datasetId}/share/invitations/${invitationId}`, buildHeaders(context));
}

export async function regenerateInvitationLink(context: AppLocalContext, datasetId: string, invitationId: string): Promise<{ link: string }> {
    const response = await axiosInstance.post(`/datasets/${datasetId}/share/invitations/${invitationId}/link`, {}, buildHeaders(context));
    return response.data as { link: string };
}

export async function createAnonymousLink(context: AppLocalContext, datasetId: string, label: string): Promise<CreatedAnonymousLink> {
    const response = await axiosInstance.post(`/datasets/${datasetId}/anonymous-links`, { label }, buildHeaders(context));
    return response.data as CreatedAnonymousLink;
}

export async function revokeAnonymousLink(context: AppLocalContext, datasetId: string, linkId: string): Promise<void> {
    await axiosInstance.delete(`/datasets/${datasetId}/anonymous-links/${linkId}`, buildHeaders(context));
}

export async function getAnonymousPage(token: string): Promise<AnonymousPageResponse> {
    const response = await axiosInstance.get(`/anonymous/${encodeURIComponent(token)}`);
    return response.data as AnonymousPageResponse;
}

export async function acceptInvitation(context: AppLocalContext, token: string): Promise<AcceptInvitationResponse> {
    const response = await axiosInstance.post("/invitations/accept", { token }, { headers: { "X-User-Id": context.uid } });
    return response.data as AcceptInvitationResponse;
}

export async function claimInvitations(uid: string): Promise<ClaimInvitationsResponse> {
    const response = await axiosInstance.post(`/users/${uid}/invitations/claim`, {}, { headers: { "X-User-Id": uid } });
    return response.data as ClaimInvitationsResponse;
}
```

Append to `lib/dataset.ts`:

```ts
/**
 * Datasets the user holds a permission on, in any tenancy.
 */
export async function getSharedDatasets(context: AppLocalContext, query: { [key: string]: string | string[] }): Promise<GetDatasetsResponse> {
    const response = await axiosInstance.get("/datasets/", {
        ...buildHeaders(context),
        params: { ...query, minimal: "true", shared: "true" },
    });
    return response.data as GetDatasetsResponse;
}
```

- [ ] **Step 4: The calls the design adds**

The Settings tab edits the note and shows the history (`docs/design/rfc-003-embargo/Embargo Feature.dc.html` §1g), the invitation page shows the invitation before it is accepted (§1i), and the DOI page shows the DOI (§1i) — contracts §Embargo and §Sharing, from plan 03's Tasks 12 and 13.

Append to `lib/__tests__/embargo.test.ts`:

```ts
describe("what the design adds", () => {
    test("the status of a version carries its DOI", async () => {
        mockGet.mockResolvedValue({ data: { embargoed: true, until: embargo.until, doi: "10.5281/datamap.3f9c1e" } });

        expect((await getEmbargoStatus("d1", "2")).doi).toBe("10.5281/datamap.3f9c1e");
        expect(mockGet).toHaveBeenCalledWith("/datasets/d1/embargo-status", { params: { version: "2" } });
    });

    test("the note is set by itself", async () => {
        mockPut.mockResolvedValue({ data: { ...embargo, note: "Accepted" } });

        expect((await setEmbargoNote(context, "d1", { note: "Accepted" })).note).toBe("Accepted");
        expect(mockPut).toHaveBeenCalledWith("/datasets/d1/embargo/note", { note: "Accepted" }, headers);
    });

    test("the history is read with the user's headers", async () => {
        mockGet.mockResolvedValue({ data: { items: [] } });

        expect(await getAccessEvents(context, "d1")).toEqual({ items: [] });
        expect(mockGet).toHaveBeenCalledWith("/datasets/d1/access-events", headers);
    });
});
```

and add `getAccessEvents, setEmbargoNote` to its import from `"../embargo"`. Append to `lib/__tests__/share.test.ts`:

```ts
describe("invitation preview", () => {
    test("is read without a user", async () => {
        const preview = { state: "pending", dataset_name: "Ozone", inviter_name: "Ana", owner_name: "Ana", level: "read", invited_as: "x@y.org", embargo_until: null, accepted_at: null };
        jest.mocked(axiosInstance.get).mockResolvedValue({ data: preview });

        expect(await getInvitationPreview("tok/1")).toEqual(preview);
        expect(axiosInstance.get).toHaveBeenCalledWith("/invitations/tok%2F1");
    });
});
```

and add `getInvitationPreview` to its import from `"../share"`.

In `lib/embargo.ts`, add `AccessHistoryResponse, EmbargoNoteRequest` to the `GatekeeperAPI` import, replace `getEmbargoStatus`, and add the two calls:

```ts
export async function getEmbargoStatus(datasetId: string, versionName?: string): Promise<EmbargoStatusResponse> {
    const url = `/datasets/${encodeURIComponent(datasetId)}/embargo-status`;
    const response = versionName
        ? await axiosInstance.get(url, { params: { version: versionName } })
        : await axiosInstance.get(url);
    return response.data as EmbargoStatusResponse;
}

export async function setEmbargoNote(context: AppLocalContext, datasetId: string, request: EmbargoNoteRequest): Promise<DatasetEmbargo> {
    const response = await axiosInstance.put(`/datasets/${datasetId}/embargo/note`, request, buildHeaders(context));
    return response.data as DatasetEmbargo;
}

export async function getAccessEvents(context: AppLocalContext, datasetId: string): Promise<AccessHistoryResponse> {
    const response = await axiosInstance.get(`/datasets/${datasetId}/access-events`, buildHeaders(context));
    return response.data as AccessHistoryResponse;
}
```

In `lib/share.ts`, add `InvitationPreview` to the `GatekeeperAPI` import and:

```ts
export async function getInvitationPreview(token: string): Promise<InvitationPreview> {
    const response = await axiosInstance.get(`/invitations/${encodeURIComponent(token)}`);
    return response.data as InvitationPreview;
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/embargo.test.ts lib/__tests__/share.test.ts lib/__tests__/dataset.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add lib/embargo.ts lib/share.ts lib/dataset.ts lib/__tests__/embargo.test.ts lib/__tests__/share.test.ts lib/__tests__/dataset.test.ts
git commit -m "feat: server calls for embargo, sharing and anonymous links"
```

---

### Task 5: Tenancy-optional chain, route helper, 404 handling

**Files:**
- Modify: `lib/middlewareChain.ts`
- Create: `lib/bffRoute.ts`
- Modify: `lib/requestErrorHandler.ts`
- Modify (chain swap): `pages/api/user.ts`, `pages/api/auth/token.ts`, `pages/api/datasets/[datasetId].ts`, `pages/api/filesdownload/index.ts`, `pages/api/versions/index.ts`, `pages/api/versions/[versionName].ts`, `pages/api/dois/index.ts`
- Test: `lib/__tests__/middlewareChain.test.ts`, `lib/__tests__/requestErrorHandler.test.ts`

**Interfaces:**
- Produces: `authOnlyChain` (named export of `lib/middlewareChain.ts`); `bffRouter(): NodeRouter<NextApiRequest, NextApiResponse>` and `bffHandler(router)` (`lib/bffRoute.ts`); `handleDatasetRequestErrors` now returns `{ notFound: true }` on 404.

- [ ] **Step 1: Write the failing tests**

`lib/__tests__/middlewareChain.test.ts`:

```ts
jest.mock("next-auth/jwt", () => ({ getToken: jest.fn() }));

import { getToken } from "next-auth/jwt";
import { createRouter } from "next-connect";
import middlewareChain, { authOnlyChain } from "../middlewareChain";
import { TENANCY_STORAGE_NAME } from "../../types/TenancyStore";

const mockGetToken = jest.mocked(getToken);

function fakeRes() {
    const res: any = { statusCode: 200, headers: {} };
    res.setHeader = jest.fn((key: string, value: string) => (res.headers[key] = value));
    res.getHeader = jest.fn((key: string) => res.headers[key]);
    res.status = jest.fn((code: number) => {
        res.statusCode = code;
        return res;
    });
    res.end = jest.fn(() => res);
    res.json = jest.fn(() => res);
    return res;
}

async function call(chain: any, cookies: Record<string, string> = {}) {
    const res = fakeRes();
    const original = process.stdout.write;
    // @ts-ignore
    process.stdout.write = () => true;
    try {
        const handler = createRouter<any, any>()
            .use(chain)
            .get((req, r) => r.status(200).end("ok"))
            .handler();
        await handler({ method: "GET", url: "/api/x", headers: {}, cookies, query: {} } as any, res);
    } finally {
        process.stdout.write = original;
    }
    return res;
}

describe("the BFF chains", () => {
    test("the dataset chain lets a signed-in account with no tenancy through", async () => {
        mockGetToken.mockResolvedValue({ uid: "u1" } as any);

        expect((await call(authOnlyChain)).statusCode).toBe(200);
    });

    test("the default chain still requires a tenancy", async () => {
        mockGetToken.mockResolvedValue({ uid: "u1" } as any);

        expect((await call(middlewareChain)).statusCode).toBe(400);
    });

    test("the default chain passes with a tenancy cookie", async () => {
        mockGetToken.mockResolvedValue({ uid: "u1" } as any);

        expect((await call(middlewareChain, { [TENANCY_STORAGE_NAME]: "{}" })).statusCode).toBe(200);
    });

    test("neither lets an anonymous request through", async () => {
        mockGetToken.mockResolvedValue(null);

        expect((await call(authOnlyChain)).statusCode).toBe(401);
        expect((await call(middlewareChain)).statusCode).toBe(401);
    });
});
```

`lib/__tests__/requestErrorHandler.test.ts`:

```ts
import { handleDatasetRequestErrors } from "../requestErrorHandler";

const req = { headers: { host: "datamap.pcs.usp.br" } };

describe("handleDatasetRequestErrors", () => {
    test("a dataset the user cannot see renders the not-found page", () => {
        expect(handleDatasetRequestErrors({ response: { status: 404 } }, req, "d1")).toEqual({ notFound: true });
        expect(handleDatasetRequestErrors({ status: 404 }, req, "d1")).toEqual({ notFound: true });
    });

    test("a 401 still redirects to login", () => {
        const result: any = handleDatasetRequestErrors({ status: 401 }, req, "d1");
        expect(result.redirect.destination).toContain("/account/login");
    });

    test("anything else propagates", () => {
        expect(() => handleDatasetRequestErrors({ status: 500 }, req, "d1")).toThrow();
    });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest lib/__tests__/middlewareChain.test.ts lib/__tests__/requestErrorHandler.test.ts`
Expected: FAIL — `authOnlyChain` is undefined; a 404 is thrown instead of returning `{ notFound: true }`.

- [ ] **Step 3: Implement**

`lib/middlewareChain.ts`, after `const middlewareChain = router.use(requestLogging, auth, tenancyChecker)`:

```ts
// Dataset routes: the gatekeeper decides access per dataset, and an account invited from outside every tenancy has none to select.
export const authOnlyChain = createRouter<NextApiRequest, NextApiResponse>().use(requestLogging, auth);
```

`lib/bffRoute.ts`:

```ts
import type { NextApiRequest, NextApiResponse } from "next";
import { createRouter } from "next-connect";
import { ResponseError } from "../types/ResponseError";
import { authOnlyChain } from "./middlewareChain";
import { httpErrorHandler } from "./rpc";

export function bffRouter() {
    return createRouter<NextApiRequest, NextApiResponse>().use(authOnlyChain);
}

export function bffHandler(router: ReturnType<typeof bffRouter>) {
    return router.handler({
        onError: (err: ResponseError, req, res) => {
            const e = httpErrorHandler(err);
            res.status(e.httpCode).json(e);
        },
    });
}
```

`lib/requestErrorHandler.ts`, at the top of `handleDatasetRequestErrors`, before the 401 check:

```ts
    const status = error?.status ?? error?.statusCode ?? error?.response?.status;

    if (status === 404) {
        return { notFound: true as const };
    }
```

and change the 401 condition to `if (status === 401) {`.

Chain swap — in each file below, replace the default import of `middlewareChain` with the named `authOnlyChain` and `.use(middlewareChain)` with `.use(authOnlyChain)`:

| File | Import line becomes |
|---|---|
| `pages/api/user.ts` | `import { authOnlyChain } from "../../lib/middlewareChain";` |
| `pages/api/auth/token.ts` | `import { authOnlyChain } from "../../../lib/middlewareChain";` |
| `pages/api/datasets/[datasetId].ts` | `import { authOnlyChain } from "../../../lib/middlewareChain";` |
| `pages/api/filesdownload/index.ts` | `import { authOnlyChain } from "../../../lib/middlewareChain";` |
| `pages/api/versions/index.ts` | `import { authOnlyChain } from "../../../lib/middlewareChain";` |
| `pages/api/versions/[versionName].ts` | `import { authOnlyChain } from "../../../lib/middlewareChain";` |
| `pages/api/dois/index.ts` | `import { authOnlyChain } from "../../../lib/middlewareChain";` |

Commands:

```bash
for f in pages/api/user.ts pages/api/auth/token.ts "pages/api/datasets/[datasetId].ts" pages/api/filesdownload/index.ts pages/api/versions/index.ts "pages/api/versions/[versionName].ts" pages/api/dois/index.ts; do
  sed -i '' -e 's/^import middlewareChain from \(.*\)lib\/middlewareChain";/import { authOnlyChain } from \1lib\/middlewareChain";/' -e 's/\.use(middlewareChain)/.use(authOnlyChain)/' "$f"
done
grep -n "middlewareChain\|authOnlyChain" pages/api/user.ts pages/api/auth/token.ts "pages/api/datasets/[datasetId].ts" pages/api/filesdownload/index.ts pages/api/versions/index.ts "pages/api/versions/[versionName].ts" pages/api/dois/index.ts
```

Expected: every file shows `import { authOnlyChain } from "…lib/middlewareChain";` and `.use(authOnlyChain)`. `pages/api/datasets/index.ts` (list and create) and the snapshot routes keep `middlewareChain`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/middlewareChain.test.ts lib/__tests__/requestErrorHandler.test.ts lib/__tests__/requestLogging.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/middlewareChain.ts lib/bffRoute.ts lib/requestErrorHandler.ts lib/__tests__/middlewareChain.test.ts lib/__tests__/requestErrorHandler.test.ts pages/api/user.ts pages/api/auth/token.ts "pages/api/datasets/[datasetId].ts" pages/api/filesdownload/index.ts pages/api/versions/index.ts "pages/api/versions/[versionName].ts" pages/api/dois/index.ts
git commit -m "feat: dataset routes no longer require a selected tenancy"
```

---

### Task 6: BFF routes and BFFAPI methods

**Files:**
- Create:
  - `pages/api/datasets/[datasetId]/embargo/index.ts` (PUT)
  - `pages/api/datasets/[datasetId]/embargo/extend.ts` (POST)
  - `pages/api/datasets/[datasetId]/embargo/end.ts` (POST)
  - `pages/api/datasets/[datasetId]/embargo/mode.ts` (PUT)
  - `pages/api/datasets/[datasetId]/embargo/note.ts` (PUT; design §1g)
  - `pages/api/datasets/[datasetId]/access-events.ts` (GET; design §1g History)
  - `pages/api/datasets/[datasetId]/share/index.ts` (GET, POST)
  - `pages/api/datasets/[datasetId]/share/candidates.ts` (GET)
  - `pages/api/datasets/[datasetId]/share/permissions/[userId].ts` (PUT, DELETE)
  - `pages/api/datasets/[datasetId]/share/invitations/[invitationId]/index.ts` (DELETE)
  - `pages/api/datasets/[datasetId]/share/invitations/[invitationId]/link.ts` (POST)
  - `pages/api/datasets/[datasetId]/anonymous-links/index.ts` (POST)
  - `pages/api/datasets/[datasetId]/anonymous-links/[linkId].ts` (DELETE)
  - `pages/api/datasets/shared.ts` (GET)
  - `pages/api/invitations/accept.ts` (POST)
- Modify: `gateways/BFFAPI.ts`
- Test: `lib/__tests__/shareRoutes.test.ts`, `lib/__tests__/embargoRoutes.test.ts`, `gateways/__tests__/BFFAPI.embargo.test.ts`

**Interfaces:**
- Consumes: Task 4 functions; Task 5 `bffRouter`, `bffHandler`.
- Produces (browser, `BFFAPI`):
  - `setEmbargo(datasetId, request: SetEmbargoRequest): Promise<DatasetEmbargo>` (event `embargo_set`)
  - `extendEmbargo(datasetId, request: ExtendEmbargoRequest): Promise<DatasetEmbargo>` (event `embargo_extended`)
  - `endEmbargo(datasetId): Promise<DatasetEmbargo>`
  - `setEmbargoMode(datasetId, request: EmbargoModeRequest): Promise<DatasetEmbargo>`
  - `setEmbargoNote(datasetId, request: EmbargoNoteRequest): Promise<DatasetEmbargo>`
  - `searchShareCandidates(datasetId, q): Promise<ShareUser[]>`
  - `grantAccess(datasetId, request: GrantRequest): Promise<GrantResult>` (event `dataset_shared`)
  - `changePermissionLevel(datasetId, userId, level): Promise<SharePermission>`
  - `revokePermission(datasetId, userId): Promise<void>`
  - `revokeInvitation(datasetId, invitationId): Promise<void>`
  - `regenerateInvitationLink(datasetId, invitationId): Promise<{ link: string }>`
  - `createAnonymousLink(datasetId, label): Promise<CreatedAnonymousLink>` (event `anonymous_link_created`)
  - `revokeAnonymousLink(datasetId, linkId): Promise<void>`
  - `acceptInvitation(token): Promise<AcceptInvitationResponse>`
- Produces (BFF): `GET /api/datasets/{id}/share` is the SWR key used by the share dialog and by the dataset page's access card; `GET /api/datasets/{id}/access-events` by the Settings tab's History; `GET /api/datasets/shared?page=&page_size=` by the Shared tab.

- [ ] **Step 1: Write the failing tests**

`lib/__tests__/shareRoutes.test.ts`:

```ts
jest.mock("next-auth/jwt", () => ({ getToken: jest.fn(async () => ({ uid: "u1" })) }));
jest.mock("../share");

import { AxiosError, AxiosHeaders } from "axios";
import shareHandler from "../../pages/api/datasets/[datasetId]/share/index";
import permissionHandler from "../../pages/api/datasets/[datasetId]/share/permissions/[userId]";
import acceptHandler from "../../pages/api/invitations/accept";
import { acceptInvitation, getShareState, grantAccess, revokePermission } from "../share";

function fakeRes() {
    const res: any = { statusCode: 200, headers: {} };
    res.setHeader = jest.fn((key: string, value: string) => (res.headers[key] = value));
    res.getHeader = jest.fn((key: string) => res.headers[key]);
    res.status = jest.fn((code: number) => {
        res.statusCode = code;
        return res;
    });
    res.end = jest.fn(() => res);
    res.json = jest.fn(() => res);
    return res;
}

async function send(handler: any, method: string, query: Record<string, string>, body: unknown = undefined) {
    const res = fakeRes();
    const original = process.stdout.write;
    // @ts-ignore
    process.stdout.write = () => true;
    try {
        await handler({ method, url: "/api/x", headers: {}, cookies: {}, query, body } as any, res);
    } finally {
        process.stdout.write = original;
    }
    return res;
}

describe("the share BFF routes", () => {
    test("GET answers the share state, without a tenancy", async () => {
        jest.mocked(getShareState).mockResolvedValue({ owner: { id: "o" }, permissions: [], invitations: [], anonymous_links: [] } as any);

        const res = await send(shareHandler, "GET", { datasetId: "d1" });

        expect(res.statusCode).toBe(200);
        expect(res.json).toHaveBeenCalledWith(expect.objectContaining({ owner: { id: "o" } }));
        expect(getShareState).toHaveBeenCalledWith(expect.objectContaining({ uid: "u1" }), "d1");
    });

    test("POST grants and answers 201", async () => {
        jest.mocked(grantAccess).mockResolvedValue({ kind: "permission", permission: {} } as any);

        const res = await send(shareHandler, "POST", { datasetId: "d1" }, { user_id: "u2", level: "read" });

        expect(res.statusCode).toBe(201);
        expect(grantAccess).toHaveBeenCalledWith(expect.anything(), "d1", { user_id: "u2", level: "read" });
    });

    test("a gatekeeper 400 keeps its error code", async () => {
        jest.mocked(grantAccess).mockRejectedValue(new AxiosError("bad", "ERR", undefined, {}, {
            status: 400, data: { details: "Invalid client input", errors: [{ code: "invalid_orcid" }] },
            statusText: "", headers: {}, config: { headers: new AxiosHeaders() },
        } as any));

        const res = await send(shareHandler, "POST", { datasetId: "d1" }, { orcid: "0000", level: "read" });

        expect(res.statusCode).toBe(400);
        expect(res.json).toHaveBeenCalledWith(expect.objectContaining({ errors: [{ code: "invalid_orcid" }] }));
    });

    test("DELETE on a permission answers 204", async () => {
        jest.mocked(revokePermission).mockResolvedValue(undefined);

        const res = await send(permissionHandler, "DELETE", { datasetId: "d1", userId: "u2" });

        expect(res.statusCode).toBe(204);
        expect(revokePermission).toHaveBeenCalledWith(expect.anything(), "d1", "u2");
    });

    test("accepting an invitation already accepted is a 409", async () => {
        jest.mocked(acceptInvitation).mockRejectedValue(new AxiosError("conflict", "ERR", undefined, {}, {
            status: 409, data: { detail: "invitation_already_accepted" },
            statusText: "", headers: {}, config: { headers: new AxiosHeaders() },
        } as any));

        const res = await send(acceptHandler, "POST", {}, { token: "t" });

        expect(res.statusCode).toBe(409);
    });
});
```

`lib/__tests__/embargoRoutes.test.ts`:

```ts
jest.mock("next-auth/jwt", () => ({ getToken: jest.fn(async () => ({ uid: "u1" })) }));
jest.mock("../embargo");
jest.mock("../dataset");

import embargoHandler from "../../pages/api/datasets/[datasetId]/embargo/index";
import extendHandler from "../../pages/api/datasets/[datasetId]/embargo/extend";
import sharedHandler from "../../pages/api/datasets/shared";
import { getSharedDatasets } from "../dataset";
import { extendEmbargo, setEmbargo } from "../embargo";

function fakeRes() {
    const res: any = { statusCode: 200, headers: {} };
    res.setHeader = jest.fn((key: string, value: string) => (res.headers[key] = value));
    res.getHeader = jest.fn((key: string) => res.headers[key]);
    res.status = jest.fn((code: number) => {
        res.statusCode = code;
        return res;
    });
    res.end = jest.fn(() => res);
    res.json = jest.fn(() => res);
    return res;
}

async function send(handler: any, method: string, query: Record<string, string>, body: unknown = undefined) {
    const res = fakeRes();
    const original = process.stdout.write;
    // @ts-ignore
    process.stdout.write = () => true;
    try {
        await handler({ method, url: "/api/x", headers: {}, cookies: {}, query, body } as any, res);
    } finally {
        process.stdout.write = original;
    }
    return res;
}

describe("the embargo BFF routes", () => {
    test("PUT sets the embargo", async () => {
        jest.mocked(setEmbargo).mockResolvedValue({ active: true } as any);
        const body = { until: "2026-12-01T23:59:59+00:00", metadata_visible: false, note: null };

        const res = await send(embargoHandler, "PUT", { datasetId: "d1" }, body);

        expect(res.statusCode).toBe(200);
        expect(setEmbargo).toHaveBeenCalledWith(expect.anything(), "d1", body);
    });

    test("POST extend", async () => {
        jest.mocked(extendEmbargo).mockResolvedValue({ active: true } as any);

        await send(extendHandler, "POST", { datasetId: "d1" }, { until: "2026-12-20T23:59:59+00:00" });

        expect(extendEmbargo).toHaveBeenCalledWith(expect.anything(), "d1", { until: "2026-12-20T23:59:59+00:00" });
    });

    test("the shared list passes the paging through", async () => {
        jest.mocked(getSharedDatasets).mockResolvedValue({ content: [] } as any);

        const res = await send(sharedHandler, "GET", { page: "1", page_size: "20" });

        expect(res.statusCode).toBe(200);
        expect(getSharedDatasets).toHaveBeenCalledWith(expect.anything(), { page: "1", page_size: "20" });
    });
});
```

`gateways/__tests__/BFFAPI.embargo.test.ts`:

```ts
jest.mock("../../lib/telemetryClient", () => ({ trackUiEvent: jest.fn() }));
jest.mock("axios", () => {
    const actual = jest.requireActual("axios");
    return {
        __esModule: true,
        ...actual,
        default: {
            ...actual.default,
            get: jest.fn(),
            post: jest.fn(),
            put: jest.fn(),
            delete: jest.fn(),
            isAxiosError: actual.default.isAxiosError,
        },
    };
});

import axios, { AxiosError, AxiosHeaders } from "axios";
import { trackUiEvent } from "../../lib/telemetryClient";
import { BFFAPI } from "../BFFAPI";

const bff = new BFFAPI();

describe("BFFAPI embargo and sharing", () => {
    test("setting an embargo calls the BFF and records the event", async () => {
        jest.mocked(axios.put).mockResolvedValue({ status: 200, data: { active: true } });
        const request = { until: "2026-12-01T23:59:59+00:00", metadata_visible: true, note: null };

        expect(await bff.setEmbargo("d1", request)).toEqual({ active: true });
        expect(axios.put).toHaveBeenCalledWith("/api/datasets/d1/embargo", request);
        expect(trackUiEvent).toHaveBeenCalledWith("embargo_set");
    });

    test("a refused grant throws the API error with its code, and records nothing", async () => {
        jest.mocked(axios.post).mockRejectedValue(new AxiosError("bad", "ERR", undefined, {}, {
            status: 400, data: { errors: [{ code: "already_has_access" }] },
            statusText: "", headers: {}, config: { headers: new AxiosHeaders() },
        } as any));

        await expect(bff.grantAccess("d1", { email: "a@b.co", level: "read" }))
            .rejects.toMatchObject({ httpCode: 400, errors: [{ code: "already_has_access" }] });
        expect(trackUiEvent).not.toHaveBeenCalled();
    });

    test("candidates are searched with the query encoded", async () => {
        jest.mocked(axios.get).mockResolvedValue({ status: 200, data: [] });

        await bff.searchShareCandidates("d1", "ana souza");

        expect(axios.get).toHaveBeenCalledWith("/api/datasets/d1/share/candidates?q=ana%20souza");
    });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest lib/__tests__/shareRoutes.test.ts lib/__tests__/embargoRoutes.test.ts gateways/__tests__/BFFAPI.embargo.test.ts`
Expected: FAIL — the route modules do not exist; `bff.setEmbargo is not a function`.

- [ ] **Step 3: Implement the routes**

`pages/api/datasets/[datasetId]/embargo/index.ts`:

```ts
import { NewContext } from "../../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../../lib/bffRoute";
import { setEmbargo } from "../../../../../lib/embargo";

const router = bffRouter()
    .put(async (req, res) => {
        const context = await NewContext(req);
        res.json(await setEmbargo(context, req.query.datasetId as string, req.body));
    });

export default bffHandler(router);
```

`pages/api/datasets/[datasetId]/embargo/extend.ts`:

```ts
import { NewContext } from "../../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../../lib/bffRoute";
import { extendEmbargo } from "../../../../../lib/embargo";

const router = bffRouter()
    .post(async (req, res) => {
        const context = await NewContext(req);
        res.json(await extendEmbargo(context, req.query.datasetId as string, req.body));
    });

export default bffHandler(router);
```

`pages/api/datasets/[datasetId]/embargo/end.ts`:

```ts
import { NewContext } from "../../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../../lib/bffRoute";
import { endEmbargo } from "../../../../../lib/embargo";

const router = bffRouter()
    .post(async (req, res) => {
        const context = await NewContext(req);
        res.json(await endEmbargo(context, req.query.datasetId as string));
    });

export default bffHandler(router);
```

`pages/api/datasets/[datasetId]/embargo/mode.ts`:

```ts
import { NewContext } from "../../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../../lib/bffRoute";
import { setEmbargoMode } from "../../../../../lib/embargo";

const router = bffRouter()
    .put(async (req, res) => {
        const context = await NewContext(req);
        res.json(await setEmbargoMode(context, req.query.datasetId as string, req.body));
    });

export default bffHandler(router);
```

`pages/api/datasets/[datasetId]/share/index.ts`:

```ts
import { NewContext } from "../../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../../lib/bffRoute";
import { getShareState, grantAccess } from "../../../../../lib/share";

const router = bffRouter()
    .get(async (req, res) => {
        const context = await NewContext(req);
        res.json(await getShareState(context, req.query.datasetId as string));
    })
    .post(async (req, res) => {
        const context = await NewContext(req);
        res.status(201).json(await grantAccess(context, req.query.datasetId as string, req.body));
    });

export default bffHandler(router);
```

`pages/api/datasets/[datasetId]/share/candidates.ts`:

```ts
import { NewContext } from "../../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../../lib/bffRoute";
import { searchShareCandidates } from "../../../../../lib/share";

const router = bffRouter()
    .get(async (req, res) => {
        const context = await NewContext(req);
        res.json(await searchShareCandidates(context, req.query.datasetId as string, (req.query.q as string) ?? ""));
    });

export default bffHandler(router);
```

`pages/api/datasets/[datasetId]/share/permissions/[userId].ts`:

```ts
import { NewContext } from "../../../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../../../lib/bffRoute";
import { changePermissionLevel, revokePermission } from "../../../../../../lib/share";

const router = bffRouter()
    .put(async (req, res) => {
        const context = await NewContext(req);
        res.json(await changePermissionLevel(context, req.query.datasetId as string, req.query.userId as string, req.body?.level));
    })
    .delete(async (req, res) => {
        const context = await NewContext(req);
        await revokePermission(context, req.query.datasetId as string, req.query.userId as string);
        res.status(204).end();
    });

export default bffHandler(router);
```

`pages/api/datasets/[datasetId]/share/invitations/[invitationId]/index.ts`:

```ts
import { NewContext } from "../../../../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../../../../lib/bffRoute";
import { revokeInvitation } from "../../../../../../../lib/share";

const router = bffRouter()
    .delete(async (req, res) => {
        const context = await NewContext(req);
        await revokeInvitation(context, req.query.datasetId as string, req.query.invitationId as string);
        res.status(204).end();
    });

export default bffHandler(router);
```

`pages/api/datasets/[datasetId]/share/invitations/[invitationId]/link.ts`:

```ts
import { NewContext } from "../../../../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../../../../lib/bffRoute";
import { regenerateInvitationLink } from "../../../../../../../lib/share";

const router = bffRouter()
    .post(async (req, res) => {
        const context = await NewContext(req);
        res.json(await regenerateInvitationLink(context, req.query.datasetId as string, req.query.invitationId as string));
    });

export default bffHandler(router);
```

`pages/api/datasets/[datasetId]/anonymous-links/index.ts`:

```ts
import { NewContext } from "../../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../../lib/bffRoute";
import { createAnonymousLink } from "../../../../../lib/share";

const router = bffRouter()
    .post(async (req, res) => {
        const context = await NewContext(req);
        res.status(201).json(await createAnonymousLink(context, req.query.datasetId as string, req.body?.label));
    });

export default bffHandler(router);
```

`pages/api/datasets/[datasetId]/anonymous-links/[linkId].ts`:

```ts
import { NewContext } from "../../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../../lib/bffRoute";
import { revokeAnonymousLink } from "../../../../../lib/share";

const router = bffRouter()
    .delete(async (req, res) => {
        const context = await NewContext(req);
        await revokeAnonymousLink(context, req.query.datasetId as string, req.query.linkId as string);
        res.status(204).end();
    });

export default bffHandler(router);
```

`pages/api/datasets/shared.ts`:

```ts
import { NewContext } from "../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../lib/bffRoute";
import { getSharedDatasets } from "../../../lib/dataset";

const router = bffRouter()
    .get(async (req, res) => {
        const context = await NewContext(req);
        res.json(await getSharedDatasets(context, req.query as { [key: string]: string | string[] }));
    });

export default bffHandler(router);
```

`pages/api/invitations/accept.ts`:

```ts
import { NewContext } from "../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../lib/bffRoute";
import { acceptInvitation } from "../../../lib/share";

const router = bffRouter()
    .post(async (req, res) => {
        const context = await NewContext(req);
        res.json(await acceptInvitation(context, req.body?.token));
    });

export default bffHandler(router);
```

- [ ] **Step 4: Implement the BFFAPI methods**

In `gateways/BFFAPI.ts`, add to the imports:

```ts
import {
    AcceptInvitationResponse,
    CreatedAnonymousLink,
    DatasetEmbargo,
    EmbargoModeRequest,
    ExtendEmbargoRequest,
    GrantRequest,
    GrantResult,
    PermissionLevel,
    SetEmbargoRequest,
    SharePermission,
    ShareUser,
} from "../types/GatekeeperAPI";
```

and append these methods inside `class BFFAPI`, after `createNewDraftDatasetVersion`:

```ts
    async setEmbargo(datasetId: string, request: SetEmbargoRequest): Promise<DatasetEmbargo> {
        try {
            const response = await axios.put(`/api/datasets/${datasetId}/embargo`, request);
            trackUiEvent("embargo_set");
            return response.data as DatasetEmbargo;
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async extendEmbargo(datasetId: string, request: ExtendEmbargoRequest): Promise<DatasetEmbargo> {
        try {
            const response = await axios.post(`/api/datasets/${datasetId}/embargo/extend`, request);
            trackUiEvent("embargo_extended");
            return response.data as DatasetEmbargo;
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async endEmbargo(datasetId: string): Promise<DatasetEmbargo> {
        try {
            const response = await axios.post(`/api/datasets/${datasetId}/embargo/end`, {});
            return response.data as DatasetEmbargo;
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async setEmbargoMode(datasetId: string, request: EmbargoModeRequest): Promise<DatasetEmbargo> {
        try {
            const response = await axios.put(`/api/datasets/${datasetId}/embargo/mode`, request);
            return response.data as DatasetEmbargo;
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async searchShareCandidates(datasetId: string, q: string): Promise<ShareUser[]> {
        try {
            const response = await axios.get(`/api/datasets/${datasetId}/share/candidates?q=${encodeURIComponent(q)}`);
            return response.data as ShareUser[];
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async grantAccess(datasetId: string, request: GrantRequest): Promise<GrantResult> {
        try {
            const response = await axios.post(`/api/datasets/${datasetId}/share`, request);
            trackUiEvent("dataset_shared");
            return response.data as GrantResult;
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async changePermissionLevel(datasetId: string, userId: string, level: PermissionLevel): Promise<SharePermission> {
        try {
            const response = await axios.put(`/api/datasets/${datasetId}/share/permissions/${userId}`, { level });
            return response.data as SharePermission;
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async revokePermission(datasetId: string, userId: string): Promise<void> {
        try {
            await axios.delete(`/api/datasets/${datasetId}/share/permissions/${userId}`);
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async revokeInvitation(datasetId: string, invitationId: string): Promise<void> {
        try {
            await axios.delete(`/api/datasets/${datasetId}/share/invitations/${invitationId}`);
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async regenerateInvitationLink(datasetId: string, invitationId: string): Promise<{ link: string }> {
        try {
            const response = await axios.post(`/api/datasets/${datasetId}/share/invitations/${invitationId}/link`, {});
            return response.data as { link: string };
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async createAnonymousLink(datasetId: string, label: string): Promise<CreatedAnonymousLink> {
        try {
            const response = await axios.post(`/api/datasets/${datasetId}/anonymous-links`, { label });
            trackUiEvent("anonymous_link_created");
            return response.data as CreatedAnonymousLink;
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async revokeAnonymousLink(datasetId: string, linkId: string): Promise<void> {
        try {
            await axios.delete(`/api/datasets/${datasetId}/anonymous-links/${linkId}`);
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async acceptInvitation(token: string): Promise<AcceptInvitationResponse> {
        try {
            const response = await axios.post(`/api/invitations/accept`, { token });
            return response.data as AcceptInvitationResponse;
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }
```

- [ ] **Step 5: The routes the design adds**

In `lib/__tests__/embargoRoutes.test.ts`, add next to the other handler imports:

```ts
import noteHandler from "../../pages/api/datasets/[datasetId]/embargo/note";
import eventsHandler from "../../pages/api/datasets/[datasetId]/access-events";
```

add `getAccessEvents, setEmbargoNote` to the `"../embargo"` import, and append:

```ts
describe("the routes the design adds", () => {
    test("PUT note", async () => {
        jest.mocked(setEmbargoNote).mockResolvedValue({ note: "Accepted" } as any);

        const res = await send(noteHandler, "PUT", { datasetId: "d1" }, { note: "Accepted" });

        expect(res.statusCode).toBe(200);
        expect(setEmbargoNote).toHaveBeenCalledWith(expect.anything(), "d1", { note: "Accepted" });
    });

    test("GET access events", async () => {
        jest.mocked(getAccessEvents).mockResolvedValue({ items: [] });

        const res = await send(eventsHandler, "GET", { datasetId: "d1" });

        expect(res.statusCode).toBe(200);
        expect(res.json).toHaveBeenCalledWith({ items: [] });
    });
});
```

`pages/api/datasets/[datasetId]/embargo/note.ts`:

```ts
import { NewContext } from "../../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../../lib/bffRoute";
import { setEmbargoNote } from "../../../../../lib/embargo";

const router = bffRouter()
    .put(async (req, res) => {
        const context = await NewContext(req);
        res.json(await setEmbargoNote(context, req.query.datasetId as string, req.body));
    });

export default bffHandler(router);
```

`pages/api/datasets/[datasetId]/access-events.ts`:

```ts
import { NewContext } from "../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../lib/bffRoute";
import { getAccessEvents } from "../../../../lib/embargo";

const router = bffRouter()
    .get(async (req, res) => {
        const context = await NewContext(req);
        res.json(await getAccessEvents(context, req.query.datasetId as string));
    });

export default bffHandler(router);
```

In `gateways/BFFAPI.ts`, add `EmbargoNoteRequest` to the `GatekeeperAPI` import and, after `setEmbargoMode`:

```ts
    async setEmbargoNote(datasetId: string, request: EmbargoNoteRequest): Promise<DatasetEmbargo> {
        try {
            const response = await axios.put(`/api/datasets/${datasetId}/embargo/note`, request);
            return response.data as DatasetEmbargo;
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }
```

`extendEmbargo` already sends whatever `ExtendEmbargoRequest` holds, so the extension's `reason` (Task 1) reaches the gatekeeper with no route change.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/shareRoutes.test.ts lib/__tests__/embargoRoutes.test.ts gateways/__tests__/BFFAPI.embargo.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pages/api/datasets/ pages/api/invitations/ gateways/BFFAPI.ts gateways/__tests__/ lib/__tests__/shareRoutes.test.ts lib/__tests__/embargoRoutes.test.ts
git commit -m "feat: BFF routes for embargo, sharing, anonymous links and invitations"
```

---

### Task 7: Shared with me, layout and list badge

`Embargo Feature.dc.html` §1f ("List with badge"): the Datasets page gains two tabs, the workspace ("Data Amazon 108") and **Shared with me** ("2"), and an embargoed row carries an amber "Embargoed until Dec 15" badge in place of its state pill. "Shared with me" is a tab, not a menu entry: it lists the datasets the account holds a permission on, from any tenancy; for an account with no tenancy it is the only tab, and neither "Create" nor "+ New dataset" is offered (`datasets_shared` cannot create). Amber marks "under embargo" and nothing else (Task 1's `embargo-*` colours).

**Files:**
- Create: `components/Embargo/EmbargoBadge.tsx`, `components/Datasets/DatasetsTabs.tsx`, `pages/app/datasets/shared.tsx`
- Modify: `components/LoggedLayout.tsx`, `pages/app/datasets/index.tsx`, `components/Search/ListItem.tsx`, `components/Tenancy/AccessPending.tsx`
- Test: `components/Embargo/__tests__/EmbargoBadge.test.tsx`, `components/Datasets/__tests__/DatasetsTabs.test.tsx`, `components/Tenancy/__tests__/AccessPending.test.tsx` (append)

**Interfaces:**
- Consumes: `ROUTE_PAGE_DATASETS`, `ROUTE_PAGE_DATASETS_SHARED` (Task 2), `formatShortDate`, `tenancyDisplayName` (Task 3), `/api/datasets/shared` (Task 6).
- Produces: `LoggedLayout` prop `tenancyOptional?: boolean`; `EmbargoBadge({ embargo, compact? })` — Task 8 uses it in the dataset header; `DatasetsTabs({ active, tenancyName, tenancyCount, sharedCount })`.

- [ ] **Step 1: Write the failing tests**

`components/Embargo/__tests__/EmbargoBadge.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { EmbargoBadge } from "../EmbargoBadge";

const active = { until: "2026-12-15T23:59:59+00:00", active: true, metadata_visible: false, note: null };

describe("EmbargoBadge", () => {
    test("on the dataset page it carries the full date", () => {
        render(<EmbargoBadge embargo={active} />);

        expect(screen.getByTestId("embargo-badge").textContent).toContain("Embargoed until Dec 15, 2026");
    });

    test("in a list it drops the year", () => {
        render(<EmbargoBadge embargo={active} compact />);

        expect(screen.getByTestId("embargo-badge").textContent).toContain("Embargoed until Dec 15");
        expect(screen.getByTestId("embargo-badge").textContent).not.toContain("2026");
    });

    test("it is amber, the colour that means under embargo", () => {
        render(<EmbargoBadge embargo={active} />);

        expect(screen.getByTestId("embargo-badge").className).toContain("bg-embargo-100");
        expect(screen.getByTestId("embargo-badge").className).toContain("text-embargo-800");
    });

    test("nothing once the embargo is over, or without one", () => {
        const { rerender } = render(<EmbargoBadge embargo={{ ...active, active: false }} />);
        expect(screen.queryByTestId("embargo-badge")).toBeNull();

        rerender(<EmbargoBadge embargo={null} />);
        expect(screen.queryByTestId("embargo-badge")).toBeNull();
    });
});
```

`components/Datasets/__tests__/DatasetsTabs.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { DatasetsTabs } from "../DatasetsTabs";

describe("DatasetsTabs", () => {
    test("the workspace tab and Shared with me, each with its count", () => {
        render(<DatasetsTabs active="tenancy" tenancyName="Data Amazon" tenancyCount={108} sharedCount={2} />);

        expect(screen.getByRole("link", { name: "Data Amazon 108" }).getAttribute("aria-current")).toBe("page");
        expect(screen.getByRole("link", { name: "Shared with me 2" }).getAttribute("href")).toBe("/app/datasets/shared");
    });

    test("an account with no tenancy has only Shared with me", () => {
        render(<DatasetsTabs active="shared" tenancyName={null} sharedCount={2} />);

        expect(screen.queryByRole("link", { name: /Data Amazon/ })).toBeNull();
        expect(screen.getByRole("link", { name: "Shared with me 2" }).getAttribute("aria-current")).toBe("page");
    });
});
```

Append to `components/Tenancy/__tests__/AccessPending.test.tsx` (it already mocks `next-auth/react` and `next/router`):

```tsx
test("points to the datasets shared with the user", () => {
    render(<AccessPending />);

    expect(screen.getByRole("link", { name: "Shared with me" }).getAttribute("href")).toBe("/app/datasets/shared");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest components/Embargo/__tests__/EmbargoBadge.test.tsx components/Datasets/__tests__/DatasetsTabs.test.tsx components/Tenancy/__tests__/AccessPending.test.tsx`
Expected: FAIL — `Cannot find module '../EmbargoBadge'` and `'../DatasetsTabs'`; no link named "Shared with me".

- [ ] **Step 3: Implement**

`components/Embargo/EmbargoBadge.tsx` — the design's badge: amber, a filled lock, "Embargoed until …":

```tsx
import { MaterialSymbol } from "react-material-symbols";
import { formatShortDate } from "../../lib/embargoDisplay";
import { DatasetEmbargo } from "../../types/GatekeeperAPI";

interface Props {
    embargo?: DatasetEmbargo | null
    compact?: boolean
}

export function EmbargoBadge(props: Props) {
    if (!props.embargo?.active) {
        return null;
    }

    return (
        <span
            data-testid="embargo-badge"
            className="inline-flex items-center gap-1.5 px-2.5 py-[3px] text-xs leading-[18px] font-semibold rounded-full bg-embargo-100 text-embargo-800 whitespace-nowrap"
        >
            <MaterialSymbol icon="lock" size={14} grade={-25} weight={400} fill aria-hidden="true" />
            Embargoed until {formatShortDate(props.embargo.until, !props.compact)}
        </span>
    );
}
```

`components/Datasets/DatasetsTabs.tsx` — the underline tabs of §1f, in the style the dataset page's tabs use since #101:

```tsx
import Link from "next/link";
import { ROUTE_PAGE_DATASETS, ROUTE_PAGE_DATASETS_SHARED } from "../../contants/InternalRoutesConstants";

interface Props {
    active: "tenancy" | "shared"
    tenancyName?: string | null
    tenancyCount?: number
    sharedCount?: number
}

function Tab(props: { href: string, label: string, count?: number, active: boolean }) {
    return (
        <Link
            href={props.href}
            aria-current={props.active ? "page" : undefined}
            className={`pb-3 text-sm font-medium border-b-2 hover:text-primary-900 ${props.active ? "border-primary-900 text-primary-900" : "border-transparent text-primary-500"}`}
        >
            {props.label}{props.count !== undefined && <span className={`ml-1.5 font-normal ${props.active ? "text-primary-500" : "text-primary-400"}`}>{props.count}</span>}
        </Link>
    );
}

export function DatasetsTabs(props: Props) {
    return (
        <nav className="flex gap-6 border-b border-primary-200" aria-label="Datasets">
            {props.tenancyName &&
                <Tab href={ROUTE_PAGE_DATASETS} label={props.tenancyName} count={props.tenancyCount} active={props.active === "tenancy"} />
            }
            <Tab href={ROUTE_PAGE_DATASETS_SHARED} label="Shared with me" count={props.sharedCount} active={props.active === "shared"} />
        </nav>
    );
}
```

`components/Tenancy/AccessPending.tsx` — add `import Link from "next/link";` and `import { ROUTE_PAGE_DATASETS_SHARED } from "../../contants/InternalRoutesConstants";`, and after the second `<p>` (the one ending "there is no need to sign out and back in."):

```tsx
            <p className="text-sm text-primary-700 mt-2 mb-0">
                If a researcher shared a dataset with you, it is already in{" "}
                <Link href={ROUTE_PAGE_DATASETS_SHARED} className="text-sm font-semibold underline underline-offset-2">Shared with me</Link>.
            </p>
```

`components/LoggedLayout.tsx`:

1. Add `tenancyOptional?: boolean;` to `interface Props`.
2. The redirect becomes:

```tsx
  if (!props.tenancyOptional && !isTenancySelected()) {
    Router.replace(ROUTE_PAGE_TENANCY_SELECTOR);
  }
```

3. Wrap both forms of the Create control — the collapsed `{menuClosed && <Link … aria-label="Create">+</Link>}` and the expanded `{!menuClosed && (<div className="relative inline-block w-full">…</div>)}` — in `{isTenancySelected() && (<>…</>)}`: an account without a tenancy cannot create (§1f).
4. In `MenuItem`, `active` becomes "this page or one below it", so *Datasets* stays lit on `/app/datasets/shared` (a tab of Datasets) and on a dataset's own pages:

```tsx
  function active(href: string) {
    return router.pathname === href || router.pathname.startsWith(href + "/");
  }
```

The sidebar gets no new entry.

`pages/app/datasets/shared.tsx` — the Datasets page with the second tab active:

```tsx
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { DatasetsTabs } from "../../../components/Datasets/DatasetsTabs";
import LoggedLayout from "../../../components/LoggedLayout";
import { EmptySearch } from "../../../components/Search/EmptySearch";
import { ListDataset } from "../../../components/Search/ListDataset";
import { useTenancyStore } from "../../../components/TenancyStore";
import { ROUTE_PAGE_DATASETS_NEW } from "../../../contants/InternalRoutesConstants";
import { tenancyDisplayName } from "../../../lib/embargoDisplay";
import { SWRRetry, fetcher } from "../../../lib/fetcher";
import { GetDatasetsResponse } from "../../../types/BffAPI";

export default function SharedDatasetsPage() {
    const [currentPage, setCurrentPage] = useState(1);
    const [pageSize, setPageSize] = useState(10);
    const tenancySelected = useTenancyStore((state) => state.tenancySelected);

    const { data, error, isLoading } = useSWR(
        `/api/datasets/shared?page=${currentPage}&page_size=${pageSize}`,
        fetcher,
        { onErrorRetry: SWRRetry }
    );
    const datasets = data as GetDatasetsResponse;

    return (
        <LoggedLayout tenancyOptional>
            <div className="w-full max-w-5xl mx-auto flex flex-col gap-6">
                <div className="flex flex-wrap justify-between items-end gap-6">
                    <div>
                        <h2 className="m-0 text-3xl leading-tight">Datasets</h2>
                        <p className="mt-2 mb-0 text-[15px] leading-[23px] text-primary-600">Explore, analyze, and share quality data.</p>
                    </div>
                    {tenancySelected &&
                        <Link href={ROUTE_PAGE_DATASETS_NEW} className="btn-primary m-0 flex-none hover:text-primary-50">+ New dataset</Link>
                    }
                </div>

                <DatasetsTabs
                    active="shared"
                    tenancyName={tenancySelected ? tenancyDisplayName(tenancySelected) : null}
                    sharedCount={datasets?.total_count}
                />

                <div>
                    {isLoading && <EmptySearch>Loading datasets...</EmptySearch>}
                    {error && <EmptySearch>The shared datasets could not be loaded.</EmptySearch>}
                    {datasets && datasets.content.length === 0 &&
                        <EmptySearch>Nothing has been shared with you yet.</EmptySearch>
                    }
                    {datasets && datasets.content.length > 0 &&
                        <ListDataset
                            data={datasets.content}
                            requestedAt={Date.now()}
                            currentPage={datasets.page}
                            totalPages={datasets.total_pages}
                            totalCount={datasets.total_count}
                            hasNext={datasets.has_next}
                            hasPrevious={datasets.has_previous}
                            onPageChange={setCurrentPage}
                            pageSize={pageSize}
                            onPageSizeChange={(size) => {
                                setPageSize(size);
                                setCurrentPage(1);
                            }}
                        />
                    }
                </div>
            </div>
        </LoggedLayout>
    );
}

SharedDatasetsPage.auth = {
    role: "user",
    loading: <div>loading...</div>,
};
```

`pages/app/datasets/index.tsx` (as on main at 8c6f761):

1. Imports: `import { DatasetsTabs } from "../../../components/Datasets/DatasetsTabs";`, `import { useTenancyStore } from "../../../components/TenancyStore";`, `import { tenancyDisplayName } from "../../../lib/embargoDisplay";`.
2. In `ListDatasetPage`, after `useDatasetSearch(...)`:

```tsx
  const tenancySelected = useTenancyStore((state) => state.tenancySelected)
  const { data: shared } = useSWR(`/api/datasets/shared?page=1&page_size=1`, fetcher)
```

3. The header subtitle becomes the design's "Explore, analyze, and share quality data." and, between the header block (`flex flex-wrap justify-between items-end gap-6`) and the search block (`mt-7 mb-4`), insert:

```tsx
        <div className="mt-6">
          <DatasetsTabs
            active="tenancy"
            tenancyName={tenancyDisplayName(tenancySelected)}
            tenancyCount={datasets?.total_count}
            sharedCount={(shared as GetDatasetsResponse)?.total_count}
          />
        </div>
```

Hidden-mode datasets are not in the tenancy's count: the gatekeeper's search leaves them out for members (contracts §Dataset payload additions), which is what the design's "the count of 108 excludes them" asks.

`components/Search/ListItem.tsx` — add `import { EmbargoBadge } from "../Embargo/EmbargoBadge";`; the last column (`<div className="self-start"><DesignStatePill … /></div>`) becomes one badge per row, as in §1f:

```tsx
        <div className="self-start">
          {props.dataset.embargo?.active
            ? <EmbargoBadge embargo={props.dataset.embargo} compact />
            : <DesignStatePill state={props.dataset.current_version.design_state} />}
        </div>
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest components/Embargo/__tests__/EmbargoBadge.test.tsx components/Datasets/__tests__/DatasetsTabs.test.tsx components/Tenancy/__tests__/AccessPending.test.tsx contants/__tests__/TelemetryConstants.test.ts`
Expected: PASS (the telemetry test finds `/app/datasets/shared` in `PAGES`).

- [ ] **Step 5: Commit**

```bash
git add components/Embargo/EmbargoBadge.tsx components/Embargo/__tests__/EmbargoBadge.test.tsx components/Datasets/ components/LoggedLayout.tsx components/Search/ListItem.tsx components/Tenancy/AccessPending.tsx components/Tenancy/__tests__/AccessPending.test.tsx pages/app/datasets/index.tsx pages/app/datasets/shared.tsx
git commit -m "feat: Shared with me as a tab of Datasets, and the embargo badge in the list"
```

---

### Task 8: Embargo on the dataset page

The dataset page as `Embargo Feature.dc.html` draws it (`docs/design/rfc-003-embargo/`):

- §1b "Owner under embargo": the amber badge in the header, an amber **Embargo** card at the top of the Data card's sidebar ("75 days left · Ends Dec 15, 2026 · files open to Data Amazon", the mode with *Change*, the note, *Extend* and a red *End early*), a **Who has access** card (avatars, "You and 3 people · 1 pending invitation", anonymous links and their views), and a files table that says links expire after an hour.
- §1e "Member open mode": the same page with less in it — no Share, no Settings, no New version; *Download* present but disabled with a lock; the Files section replaced by an amber empty state with the count, the size, the date and whom to ask; the sidebar's facts gain "Files available" and "Owner". Hidden mode has no screen: the member gets the 404 (Task 5).
- §1d prompts: *Extend* (new date, optional reason), *End embargo now?* (its consequences), *Hide from members?* / *Show to members?*.
- §1g Settings: an **Embargo** block of rows (Status, Ends, Other members, Note, Reminders, each with its action), **Access** (a one-line summary and *Open share dialog*), **History** (from `GET /access-events`).
- §1h after the embargo: a neutral card with a checklist, *Make DOI findable*, "Shown until you do", no dismiss.

**Files:**
- Modify: `lib/users.ts:127-130` (`canEditDataset`) and its 8 call sites
- Create: `components/Embargo/EmbargoDialogs.tsx`, `components/Embargo/EmbargoCard.tsx`, `components/Embargo/AccessCard.tsx`, `components/Embargo/FilesWithheldNotice.tsx`, `components/Embargo/LockedDownloadButton.tsx`, `components/Embargo/EmbargoFields.tsx`, `components/Embargo/SetEmbargoDialog.tsx`, `components/Embargo/EmbargoSettingsSection.tsx`, `components/Embargo/AccessSummary.tsx`, `components/Embargo/AccessHistory.tsx`, `components/Embargo/EmbargoEndedBanner.tsx`
- Modify: `components/DatasetDetailsPage.tsx`, `components/DatasetDetails/TabPanelSettings.tsx`, `components/DatasetDetails/DataCard/TabPanelDataCard.tsx`, `components/DatasetDetails/DataCard/DataExplorer.tsx`
- Test: `lib/__tests__/users.test.ts`, `components/Embargo/__tests__/EmbargoCard.test.tsx`, `components/Embargo/__tests__/EmbargoDialogs.test.tsx`, `components/Embargo/__tests__/FilesWithheldNotice.test.tsx`, `components/Embargo/__tests__/EmbargoSettingsSection.test.tsx`, `components/Embargo/__tests__/AccessHistory.test.tsx`, `components/Embargo/__tests__/EmbargoEndedBanner.test.tsx`

**Interfaces:**
- Consumes: Task 3 (`minExtensionDate`, `maxEmbargoDate`, `minEmbargoDate`, `toEmbargoUntil`, `validateEmbargoDate`, `isFilesWithheld`, `shouldShowEmbargoEndedBanner`, `canSeeSettings`, `hasManualDoi`, and from `lib/embargoDisplay.ts` `formatShortDate`, `formatHistoryWhen`, `daysLeft`, `daysFromToday`, `tenancyDisplayName`, `initialsOf`, `describeAccessEvent`); Task 6 BFFAPI (`extendEmbargo`, `endEmbargo`, `setEmbargoMode`, `setEmbargoNote`, `setEmbargo`) and the existing `navigateDOIStatus`; Task 7 `EmbargoBadge`; Task 10 `ShareDialog`, `ShareButton`; `messageForApiError` (Task 1); `dataset.owner` (Task 1); SWR keys `/api/datasets/{id}/share` and `/api/datasets/{id}/access-events`.
- Produces: `canEditDataset(user, dataset?)`; `EmbargoFields({ tenancyName })` — Formik fields `embargoMode` (`"open" | "hidden"`), `embargoUntil`, `embargoNote`, used again by Task 9; the components above.

- [ ] **Step 1: Write the failing tests**

`lib/__tests__/users.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import { canEditDataset } from "../users";

const editor: any = { roles: ["datasets_write"] };
const reader: any = { roles: ["datasets_read"] };

describe("canEditDataset", () => {
    test("without access flags, the role decides", () => {
        expect(canEditDataset(editor)).toBe(true);
        expect(canEditDataset(reader)).toBe(false);
    });

    test("the dataset's access flags win over the role", () => {
        expect(canEditDataset(editor, { access: { can_edit: false } } as any)).toBe(false);
        expect(canEditDataset(reader, { access: { can_edit: true } } as any)).toBe(true);
    });
});
```

`components/Embargo/__tests__/EmbargoCard.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { beforeEach, describe, expect, jest, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';

jest.mock("next/router", () => ({ useRouter: () => ({ reload: jest.fn() }) }));
jest.mock("swr", () => ({ __esModule: true, default: () => ({ data: undefined }) }));
jest.mock("../../../gateways/BFFAPI", () => ({ BFFAPI: jest.fn().mockImplementation(() => ({})) }));

import { EmbargoCard } from "../EmbargoCard";

const owner = { level: "owner", can_edit: true, can_share: true, can_manage_embargo: true, can_extend_embargo: true, can_delete: true };

function dataset(overrides: any = {}): any {
    return {
        id: "d1",
        tenancy: "datamap/production/data-amazon",
        embargo: { until: "2026-12-15T23:59:59+00:00", active: true, metadata_visible: true, note: "Under review at JGR Atmospheres" },
        access: owner,
        ...overrides,
    };
}

beforeEach(() => {
    jest.useFakeTimers({ now: new Date("2026-10-01T10:00:00Z") });
});

describe("EmbargoCard", () => {
    test("says how long, who knows, and what the owner can do", () => {
        render(<EmbargoCard dataset={dataset()} />);

        expect(screen.getByText("76 days left")).toBeTruthy();
        expect(screen.getByText("Ends Dec 15, 2026 · files open to Data Amazon")).toBeTruthy();
        expect(screen.getByText(/Members can see it exists\./)).toBeTruthy();
        expect(screen.getByText("“Under review at JGR Atmospheres”")).toBeTruthy();
        expect(screen.getByRole("button", { name: "Change" })).toBeTruthy();
        expect(screen.getByRole("button", { name: "Extend" })).toBeTruthy();
        expect(screen.getByRole("button", { name: "End early" })).toBeTruthy();
    });

    test("someone who may only read sees the facts and no action", () => {
        render(<EmbargoCard dataset={dataset({ access: { ...owner, level: "read", can_manage_embargo: false, can_extend_embargo: false } })} />);

        expect(screen.getByText(/Hidden from members|Members can see it exists/)).toBeTruthy();
        expect(screen.queryByRole("button", { name: "Extend" })).toBeNull();
        expect(screen.queryByRole("button", { name: "End early" })).toBeNull();
    });

    test("a member of the tenancy gets no card: the files section tells them instead", () => {
        render(<EmbargoCard dataset={dataset({ access: { ...owner, level: "tenancy" } })} />);

        expect(screen.queryByText(/days left/)).toBeNull();
    });
});
```

`components/Embargo/__tests__/EmbargoDialogs.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { beforeEach, describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const extendEmbargo = jest.fn() as any;
const endEmbargo = jest.fn() as any;
const setEmbargoMode = jest.fn() as any;
const reload = jest.fn();

jest.mock("next/router", () => ({ useRouter: () => ({ reload }) }));
jest.mock("swr", () => ({
    __esModule: true,
    default: () => ({ data: { permissions: [{}, {}, {}], invitations: [], anonymous_links: [] } }),
}));
jest.mock("../../../gateways/BFFAPI", () => ({
    BFFAPI: jest.fn().mockImplementation(() => ({ extendEmbargo, endEmbargo, setEmbargoMode })),
}));

import { EmbargoModeDialog, EndEmbargoDialog, ExtendEmbargoDialog } from "../EmbargoDialogs";

const dataset: any = {
    id: "d1",
    tenancy: "datamap/production/data-amazon",
    embargo: { until: "2026-12-15T23:59:59+00:00", active: true, metadata_visible: true, note: null },
};

beforeEach(() => {
    jest.useFakeTimers({ now: new Date("2026-10-01T10:00:00Z"), doNotFake: ["setTimeout", "setInterval", "queueMicrotask", "nextTick"] });
});

describe("ExtendEmbargoDialog", () => {
    test("sends the new date with the reason", async () => {
        extendEmbargo.mockResolvedValue({ active: true });
        render(<ExtendEmbargoDialog dataset={dataset} show onClose={jest.fn()} />);

        expect(screen.getByText("Ends Dec 15, 2026")).toBeTruthy();
        fireEvent.change(screen.getByLabelText("New end date"), { target: { value: "2026-12-28" } });
        fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: "Second review round requested" } });
        fireEvent.click(screen.getByRole("button", { name: "Extend to Dec 28" }));

        await waitFor(() => expect(extendEmbargo).toHaveBeenCalledWith("d1", {
            until: "2026-12-28T23:59:59+00:00", reason: "Second review round requested",
        }));
        expect(reload).toHaveBeenCalled();
    });

    test("a date beyond 90 days is refused before it is sent", async () => {
        render(<ExtendEmbargoDialog dataset={dataset} show onClose={jest.fn()} />);

        fireEvent.change(screen.getByLabelText("New end date"), { target: { value: "2027-01-15" } });
        fireEvent.click(screen.getByRole("button", { name: /Extend/ }));

        expect(await screen.findByText("An embargo can last at most 90 days.")).toBeTruthy();
        expect(extendEmbargo).not.toHaveBeenCalled();
    });
});

describe("EndEmbargoDialog", () => {
    test("states what ending early does, then ends it", async () => {
        endEmbargo.mockResolvedValue({ active: false });
        render(<EndEmbargoDialog dataset={dataset} show onClose={jest.fn()} />);

        expect(screen.getByText("Set to end Dec 15, 2026 · can't be undone")).toBeTruthy();
        expect(screen.getByText("Files open to Data Amazon members now")).toBeTruthy();
        expect(screen.getByText("Nothing becomes public until the DOI is promoted")).toBeTruthy();
        expect(screen.getByText("Anonymous links keep showing the redacted page until you publish")).toBeTruthy();
        expect(screen.getByText("3 people with access are emailed")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "End embargo" }));

        await waitFor(() => expect(endEmbargo).toHaveBeenCalledWith("d1"));
    });
});

describe("EmbargoModeDialog", () => {
    test("hiding says who stops seeing it", async () => {
        setEmbargoMode.mockResolvedValue({});
        render(<EmbargoModeDialog dataset={dataset} show onClose={jest.fn()} />);

        expect(screen.getByText("Hide from members?")).toBeTruthy();
        expect(screen.getByText("Administrators included")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Hide dataset" }));

        await waitFor(() => expect(setEmbargoMode).toHaveBeenCalledWith("d1", { metadata_visible: false }));
    });
});
```

`components/Embargo/__tests__/FilesWithheldNotice.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { FilesWithheldNotice } from "../FilesWithheldNotice";

const dataset: any = {
    tenancy: "datamap/production/data-amazon",
    owner: { id: "o", name: "Luciana Rizzo" },
    embargo: { until: "2026-12-15T23:59:59+00:00", active: true, metadata_visible: true, note: null },
};

describe("FilesWithheldNotice", () => {
    test("count, size, date and whom to ask", () => {
        render(<FilesWithheldNotice dataset={dataset} version={{ files_withheld: true, files_summary: { count: 14, total_size_bytes: 2469606195 } } as any} />);

        const notice = screen.getByTestId("files-withheld");
        expect(notice.textContent).toContain("14 files · 2.3 GB, under embargo");
        expect(notice.textContent).toContain("File names and downloads become available to Data Amazon members on Dec 15, 2026.");
        expect(notice.textContent).toContain("You can cite the dataset now.");
        expect(notice.textContent).toContain("Need it earlier? Ask the owner, Luciana Rizzo, to share it with you.");
    });

    test("nothing when the files are visible", () => {
        render(<FilesWithheldNotice dataset={dataset} version={{ files_withheld: false } as any} />);

        expect(screen.queryByTestId("files-withheld")).toBeNull();
    });
});
```

`components/Embargo/__tests__/EmbargoSettingsSection.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { beforeEach, describe, expect, jest, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';

jest.mock("next/router", () => ({ useRouter: () => ({ reload: jest.fn() }) }));
jest.mock("swr", () => ({ __esModule: true, default: () => ({ data: undefined }) }));
jest.mock("../../../gateways/BFFAPI", () => ({ BFFAPI: jest.fn().mockImplementation(() => ({})) }));

import { EmbargoSettingsSection } from "../EmbargoSettingsSection";

const owner = { level: "owner", can_edit: true, can_share: true, can_manage_embargo: true, can_extend_embargo: true, can_delete: true };

beforeEach(() => {
    jest.useFakeTimers({ now: new Date("2026-10-01T10:00:00Z") });
});

describe("EmbargoSettingsSection", () => {
    test("under embargo: one row per fact, each with its action", () => {
        render(<EmbargoSettingsSection dataset={{
            id: "d1", tenancy: "t", access: owner, versions: [],
            embargo: { until: "2026-12-15T23:59:59+00:00", active: true, metadata_visible: true, note: "Under review at JGR Atmospheres" },
        } as any} />);

        expect(screen.getByText("Under embargo")).toBeTruthy();
        expect(screen.getByText("76 days left")).toBeTruthy();
        expect(screen.getByText("Dec 15, 2026")).toBeTruthy();
        expect(screen.getByText("Visible to members")).toBeTruthy();
        expect(screen.getByText("Under review at JGR Atmospheres")).toBeTruthy();
        expect(screen.getByText("15, 10, 5 and 1 day before the end")).toBeTruthy();
        for (const action of ["End early", "Extend", "Hide", "Edit"]) {
            expect(screen.getByRole("button", { name: action })).toBeTruthy();
        }
    });

    test("before an embargo: Set embargo", () => {
        render(<EmbargoSettingsSection dataset={{ id: "d1", tenancy: "t", access: owner, versions: [], embargo: null } as any} />);

        expect(screen.getByText("Not under embargo")).toBeTruthy();
        expect(screen.getByRole("button", { name: "Set embargo" })).toBeTruthy();
    });

    test("with an external DOI, it says why an embargo is not possible", () => {
        render(<EmbargoSettingsSection dataset={{ id: "d1", tenancy: "t", access: owner, versions: [{ doi: { mode: "MANUAL" } }], embargo: null } as any} />);

        expect(screen.queryByRole("button", { name: "Set embargo" })).toBeNull();
        expect(screen.getByText("This dataset has a manual DOI, so it can no longer be put under embargo.")).toBeTruthy();
    });

    test("someone who may only extend sees only Extend", () => {
        render(<EmbargoSettingsSection dataset={{
            id: "d1", tenancy: "t", versions: [],
            access: { ...owner, level: "write", can_manage_embargo: false },
            embargo: { until: "2026-12-15T23:59:59+00:00", active: true, metadata_visible: false, note: null },
        } as any} />);

        expect(screen.getByRole("button", { name: "Extend" })).toBeTruthy();
        expect(screen.queryByRole("button", { name: "End early" })).toBeNull();
        expect(screen.queryByRole("button", { name: "Show" })).toBeNull();
    });
});
```

`components/Embargo/__tests__/AccessHistory.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';

jest.mock("swr", () => ({
    __esModule: true,
    default: () => ({
        data: {
            items: [
                { event_type: "extended", occurred_at: "2026-09-24T09:41:00Z", actor: { id: "o", name: "Luciana Rizzo" }, subject: null,
                  old_value: { until: "2026-11-30T23:59:59+00:00" }, new_value: { until: "2026-12-15T23:59:59+00:00" }, note: "Second review round requested" },
                { event_type: "permission_granted", occurred_at: "2026-09-12T16:05:00Z", actor: { id: "a", name: "Alan Calheiros" }, subject: "Caio Maia",
                  old_value: null, new_value: { level: "read" }, note: null },
            ],
        },
    }),
}));

import { AccessHistory } from "../AccessHistory";

describe("AccessHistory", () => {
    test("a person, a date and a reason for every decision", () => {
        render(<AccessHistory datasetId="d1" />);

        expect(screen.getByText("Luciana Rizzo")).toBeTruthy();
        expect(screen.getByText("extended the embargo to Dec 15, 2026")).toBeTruthy();
        expect(screen.getByText("was Nov 30, 2026 · \"Second review round requested\"")).toBeTruthy();
        expect(screen.getByText("Sep 24, 2026 09:41")).toBeTruthy();
        expect(screen.getByText("granted read access to Caio Maia")).toBeTruthy();
    });
});
```

`components/Embargo/__tests__/EmbargoEndedBanner.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const navigateDOIStatus = jest.fn() as any;
const reload = jest.fn();
jest.mock("next/router", () => ({ useRouter: () => ({ reload }) }));
jest.mock("../../../gateways/BFFAPI", () => ({ BFFAPI: jest.fn().mockImplementation(() => ({ navigateDOIStatus })) }));

import { EmbargoEndedBanner } from "../EmbargoEndedBanner";

const dataset: any = {
    id: "d1",
    tenancy: "datamap/production/data-amazon",
    embargo: { until: "2026-12-15T23:59:59+00:00", active: false, metadata_visible: false, note: null },
    current_version: { name: "2", doi: { identifier: "10.5281/datamap.3f9c1e", state: "REGISTERED" } },
};

describe("EmbargoEndedBanner", () => {
    test("the checklist the owner cannot miss", () => {
        render(<EmbargoEndedBanner dataset={dataset} />);

        const banner = screen.getByRole("status");
        expect(banner.textContent).toContain("The embargo ended on Dec 15. One step left to publish.");
        expect(banner.textContent).toContain("Files are available to every member of Data Amazon.");
        expect(banner.textContent).toContain("registered but not findable");
        expect(banner.textContent).toContain("Shown until you do");
    });

    test("making the DOI findable asks first, then promotes it", async () => {
        navigateDOIStatus.mockResolvedValue({});
        render(<EmbargoEndedBanner dataset={dataset} />);

        fireEvent.click(screen.getByRole("button", { name: "Make DOI findable" }));
        fireEvent.click(screen.getByRole("button", { name: "Make it findable" }));

        await waitFor(() => expect(navigateDOIStatus).toHaveBeenCalledWith({ datasetId: "d1", versionName: "2", state: "FINDABLE" }));
    });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest lib/__tests__/users.test.ts components/Embargo/__tests__`
Expected: FAIL — `canEditDataset(editor, { access: { can_edit: false } })` returns true; the component modules do not exist.

- [ ] **Step 3: Implement `canEditDataset`**

`lib/users.ts` — add `import { DatasetAccess } from "../types/GatekeeperAPI";` and replace the function:

```ts
export function canEditDataset(user: UserDetailsResponse, dataset?: { access?: DatasetAccess }): boolean {
    if (dataset?.access) {
        return dataset.access.can_edit;
    }
    return user.roles.indexOf("datasets_write") >= 0
        || user.roles.indexOf("admin") >= 0;
}
```

Update the call sites:

```bash
sed -i '' 's/canEditDataset(props\.user)/canEditDataset(props.user, props.dataset)/' \
  components/DatasetDetailsPage.tsx \
  components/DatasetDetails/DatasetCoverageForm.tsx \
  components/DatasetDetails/DatasetProvenance.tsx \
  components/DatasetDetails/DatasetInstitution.tsx \
  components/DatasetDetails/DatasetColaboratorsForm.tsx \
  components/DatasetDetails/DatasetAuthorsForm.tsx \
  components/DatasetDetails/DatasetLicenseForm.tsx \
  components/DatasetDetails/DataCard/DatasetDescription.tsx
grep -rn "canEditDataset(props.user)" components || echo "all call sites pass the dataset"
```

Expected: `all call sites pass the dataset`.

- [ ] **Step 4: Implement the components**

Amber (`embargo-*`, Task 1) is for "under embargo" only; the ended banner is the neutral card, since the embargo is over and what is left is an unfinished step (§1h). Card labels are the sidebar's uppercase 11 px (`SideCardLabel` in `TabPanelDataCard.tsx`); text actions are `text-[13px] font-medium`, red (`text-danger-700`) only for *End early*. Confirmations use `PopupModal`, its `destructive` style for *End embargo*.

`components/Embargo/EmbargoDialogs.tsx` — §1d:

```tsx
import { useRouter } from "next/router";
import { useState } from "react";
import useSWR from "swr";
import { EDIT_FORM_ERROR_CLASS, EDIT_FORM_INPUT_CLASS } from "../../contants/EditFormConstants";
import { messageForApiError } from "../../contants/EmbargoConstants";
import { BFFAPI } from "../../gateways/BFFAPI";
import { maxEmbargoDate, minExtensionDate, toEmbargoUntil, validateEmbargoDate } from "../../lib/embargoDates";
import { formatShortDate, tenancyDisplayName } from "../../lib/embargoDisplay";
import { fetcher } from "../../lib/fetcher";
import { GetDatasetDetailsResponse } from "../../types/BffAPI";
import { ShareState } from "../../types/GatekeeperAPI";
import Modal from "../base/PopupModal";

interface DialogProps {
    dataset: GetDatasetDetailsResponse
    show: boolean
    onClose(): void
}

function Consequences(props: { items: string[] }) {
    return (
        <ul className="m-0 p-0 list-none flex flex-col gap-2.5 text-sm leading-[21px] text-primary-700">
            {props.items.map((item) => (
                <li key={item} className="flex gap-2.5"><span className="text-primary-400">—</span><span>{item}</span></li>
            ))}
        </ul>
    );
}

function useAction(onClose: () => void) {
    const router = useRouter();
    const [error, setError] = useState<string | null>(null);

    async function run(action: () => Promise<unknown>) {
        setError(null);
        try {
            await action();
            onClose();
            router.reload();
        } catch (e) {
            setError(messageForApiError(e));
        }
    }

    return { error, setError, run };
}

export function ExtendEmbargoDialog(props: DialogProps) {
    const [bffGateway] = useState(() => new BFFAPI());
    const [date, setDate] = useState("");
    const [reason, setReason] = useState("");
    const { error, setError, run } = useAction(props.onClose);
    const now = new Date();
    const embargo = props.dataset.embargo;
    if (!embargo) {
        return null;
    }
    const min = minExtensionDate(embargo.until, now);
    const max = maxEmbargoDate(now);

    function confirm() {
        const message = validateEmbargoDate(date, now, min);
        if (message) {
            setError(message);
            return;
        }
        run(() => bffGateway.extendEmbargo(props.dataset.id, { until: toEmbargoUntil(date), reason: reason.trim() || null }));
    }

    return (
        <Modal
            title="Extend embargo"
            show={props.show}
            confimButtonText={date ? `Extend to ${formatShortDate(toEmbargoUntil(date), false)}` : "Extend"}
            cancelButtonText="Cancel"
            cancel={props.onClose}
            confim={confirm}
            maxWidthClassName="max-w-[440px]"
        >
            <div className="flex flex-col gap-4">
                <p className="m-0 text-[13px] text-primary-500">Ends {formatShortDate(embargo.until)}</p>
                <div className="flex flex-col gap-1.5">
                    <label htmlFor="extend-until" className="m-0 text-[13px] font-semibold text-primary-900">New end date</label>
                    <input id="extend-until" type="date" min={min} max={max} value={date} onChange={(e) => setDate(e.target.value)} className={EDIT_FORM_INPUT_CLASS} />
                    <span className="text-xs text-primary-500">Up to 90 days from today · {formatShortDate(toEmbargoUntil(max))}</span>
                </div>
                <div className="flex flex-col gap-1.5">
                    <label htmlFor="extend-reason" className="m-0 text-[13px] font-semibold text-primary-900">Reason <span className="font-normal text-primary-400">optional</span></label>
                    <input id="extend-reason" type="text" maxLength={500} placeholder="Second review round requested" value={reason} onChange={(e) => setReason(e.target.value)} className={EDIT_FORM_INPUT_CLASS} />
                </div>
                {error && <p role="alert" className={EDIT_FORM_ERROR_CLASS}>{error}</p>}
            </div>
        </Modal>
    );
}

export function EndEmbargoDialog(props: DialogProps) {
    const [bffGateway] = useState(() => new BFFAPI());
    const { error, run } = useAction(props.onClose);
    const { data } = useSWR(props.show ? `/api/datasets/${props.dataset.id}/share` : null, fetcher);
    const people = (data as ShareState)?.permissions?.length ?? 0;
    const tenancy = tenancyDisplayName(props.dataset.tenancy);
    const emailed = people === 0
        ? "Nobody else has access; only you are emailed"
        : `${people} ${people === 1 ? "person" : "people"} with access ${people === 1 ? "is" : "are"} emailed`;

    return (
        <Modal
            title="End embargo now?"
            show={props.show}
            confimButtonText="End embargo"
            cancelButtonText="Keep embargo"
            destructive
            cancel={props.onClose}
            confim={() => run(() => bffGateway.endEmbargo(props.dataset.id))}
            maxWidthClassName="max-w-[440px]"
        >
            <div className="flex flex-col gap-4">
                <p className="m-0 text-[13px] text-primary-500">Set to end {formatShortDate(props.dataset.embargo?.until ?? "")} · can&apos;t be undone</p>
                <Consequences items={[
                    `Files open to ${tenancy} members now`,
                    "Nothing becomes public until the DOI is promoted",
                    "Anonymous links keep showing the redacted page until you publish",
                    emailed,
                ]} />
                {error && <p role="alert" className={EDIT_FORM_ERROR_CLASS}>{error}</p>}
            </div>
        </Modal>
    );
}

export function EmbargoModeDialog(props: DialogProps) {
    const [bffGateway] = useState(() => new BFFAPI());
    const { error, run } = useAction(props.onClose);
    const visible = props.dataset.embargo?.metadata_visible === true;
    const tenancy = tenancyDisplayName(props.dataset.tenancy);

    return (
        <Modal
            title={visible ? "Hide from members?" : "Show to members?"}
            show={props.show}
            confimButtonText={visible ? "Hide dataset" : "Show dataset"}
            cancelButtonText="Cancel"
            cancel={props.onClose}
            confim={() => run(() => bffGateway.setEmbargoMode(props.dataset.id, { metadata_visible: !visible }))}
            maxWidthClassName="max-w-[440px]"
        >
            <div className="flex flex-col gap-4">
                <p className="m-0 text-[13px] text-primary-500">
                    {visible ? "Currently listed with an \"Embargoed\" badge" : `Currently hidden from members of ${tenancy}`}
                </p>
                <Consequences items={visible
                    ? ["Removed from listings and search for everyone without access", "Administrators included", "File access unchanged"]
                    : [`Listed for members of ${tenancy} with an "Embargoed" badge`, "Title, description and authors readable; file names and downloads withheld", "File access unchanged"]} />
                {error && <p role="alert" className={EDIT_FORM_ERROR_CLASS}>{error}</p>}
            </div>
        </Modal>
    );
}

export function EmbargoNoteDialog(props: DialogProps) {
    const [bffGateway] = useState(() => new BFFAPI());
    const [note, setNote] = useState(props.dataset.embargo?.note ?? "");
    const { error, run } = useAction(props.onClose);

    return (
        <Modal
            title="Edit note"
            show={props.show}
            confimButtonText="Save note"
            cancelButtonText="Cancel"
            cancel={props.onClose}
            confim={() => run(() => bffGateway.setEmbargoNote(props.dataset.id, { note: note.trim() || null }))}
            maxWidthClassName="max-w-[440px]"
        >
            <div className="flex flex-col gap-1.5">
                <label htmlFor="embargo-note" className="m-0 text-[13px] font-semibold text-primary-900">Note</label>
                <input id="embargo-note" type="text" maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} className={EDIT_FORM_INPUT_CLASS} />
                <span className="text-xs text-primary-500">Visible to you and the people with access.</span>
                {error && <p role="alert" className={EDIT_FORM_ERROR_CLASS}>{error}</p>}
            </div>
        </Modal>
    );
}
```

The design's "3 people with access are emailed" counts the permission holders; with none, the dialog says only the owner is emailed rather than "0 people".

`components/Embargo/EmbargoCard.tsx` — §1b, the only amber surface on the page:

```tsx
import { useState } from "react";
import { MaterialSymbol } from "react-material-symbols";
import { daysLeft, formatShortDate, tenancyDisplayName } from "../../lib/embargoDisplay";
import { GetDatasetDetailsResponse } from "../../types/BffAPI";
import { EmbargoModeDialog, EndEmbargoDialog, ExtendEmbargoDialog } from "./EmbargoDialogs";

export function EmbargoCard(props: { dataset: GetDatasetDetailsResponse }) {
    const [open, setOpen] = useState<"extend" | "end" | "mode" | null>(null);
    const embargo = props.dataset.embargo;
    const access = props.dataset.access;

    if (!embargo?.active || !access || access.level === "tenancy") {
        return null;
    }

    const days = daysLeft(embargo.until, new Date());
    const action = "border border-primary-300 bg-primary-0 rounded-md px-2.5 py-[7px] text-[13px] font-semibold";

    return (
        <div className="flex flex-col gap-3 rounded-lg border border-embargo-200 bg-embargo-50 p-4">
            <div className="flex justify-between items-center">
                <span className="text-[11px] tracking-[0.08em] uppercase font-semibold text-embargo-800">Embargo</span>
                <MaterialSymbol icon="lock" size={18} grade={-25} weight={400} fill className="text-embargo-800" aria-hidden="true" />
            </div>
            <div className="flex flex-col gap-0.5">
                <span className="text-[22px] font-semibold tracking-[-0.02em] text-primary-900">{days} {days === 1 ? "day" : "days"} left</span>
                <span className="text-[13px] text-primary-600">Ends {formatShortDate(embargo.until)} · files open to {tenancyDisplayName(props.dataset.tenancy)}</span>
            </div>
            <p className="m-0 text-[13px] leading-[19px] text-primary-600">
                {embargo.metadata_visible ? "Members can see it exists." : "Hidden from members."}
                {access.can_manage_embargo && <> <button type="button" className="font-medium text-primary-900 hover:underline" onClick={() => setOpen("mode")}>Change</button></>}
            </p>
            {embargo.note && <p className="m-0 text-[13px] leading-[19px] italic text-primary-600">“{embargo.note}”</p>}
            {(access.can_extend_embargo || access.can_manage_embargo) &&
                <div className="flex gap-2 mt-1">
                    {access.can_extend_embargo && <button type="button" className={`flex-1 text-primary-900 ${action}`} onClick={() => setOpen("extend")}>Extend</button>}
                    {access.can_manage_embargo && <button type="button" className={`flex-1 text-danger-700 ${action}`} onClick={() => setOpen("end")}>End early</button>}
                </div>
            }
            <ExtendEmbargoDialog dataset={props.dataset} show={open === "extend"} onClose={() => setOpen(null)} />
            <EndEmbargoDialog dataset={props.dataset} show={open === "end"} onClose={() => setOpen(null)} />
            <EmbargoModeDialog dataset={props.dataset} show={open === "mode"} onClose={() => setOpen(null)} />
        </div>
    );
}
```

`components/Embargo/AccessCard.tsx` — §1b "Who has access":

```tsx
import { useSession } from "next-auth/react";
import { useState } from "react";
import { MaterialSymbol } from "react-material-symbols";
import useSWR from "swr";
import { initialsOf } from "../../lib/embargoDisplay";
import { fetcher } from "../../lib/fetcher";
import { GetDatasetDetailsResponse } from "../../types/BffAPI";
import { ShareState } from "../../types/GatekeeperAPI";
import { ShareDialog } from "../Share/ShareDialog";

export function AccessCard(props: { dataset: GetDatasetDetailsResponse }) {
    const [show, setShow] = useState(false);
    const session = useSession();
    const canShare = props.dataset.access?.can_share === true;
    const { data } = useSWR(canShare ? `/api/datasets/${props.dataset.id}/share` : null, fetcher);
    const state = data as ShareState;

    if (!canShare || !state) {
        return null;
    }

    const me = (session?.data?.user as any)?.uid;
    const people = [state.owner, ...state.permissions.map((permission) => permission.user)];
    const others = people.filter((person) => person.id !== me).length;
    const pending = state.invitations.filter((invitation) => !invitation.accepted_at && !invitation.revoked_at).length;
    const links = state.anonymous_links.filter((link) => !link.revoked_at);
    const views = links.reduce((total, link) => total + link.views.count, 0);
    const shown = people.slice(0, 4);

    return (
        <div className="flex flex-col gap-2.5 rounded-lg border border-primary-200 bg-primary-0 p-4">
            <div className="flex justify-between items-baseline">
                <span className="text-[11px] tracking-[0.08em] uppercase font-semibold text-primary-500">Who has access</span>
                <button type="button" className="text-[13px] font-medium text-primary-600 hover:text-primary-900" onClick={() => setShow(true)}>Manage</button>
            </div>
            <div className="flex items-center">
                {shown.map((person, index) => (
                    <span key={person.id} className={`flex items-center justify-center h-7 w-7 rounded-full border-2 border-primary-0 text-[11px] font-semibold ${index === 0 ? "bg-primary-900 text-primary-50" : "-ml-2 bg-secondary-900 text-primary-900"}`}>
                        {initialsOf(person.name)}
                    </span>
                ))}
                {people.length + pending > shown.length &&
                    <span className="-ml-1.5 flex items-center justify-center h-7 w-7 rounded-full border border-dashed border-primary-400 bg-primary-0 text-[11px] font-semibold text-primary-500">
                        +{people.length + pending - shown.length}
                    </span>
                }
            </div>
            <span className="text-[13px] leading-[19px] text-primary-600">
                {me && people.some((person) => person.id === me) ? `You and ${others} ${others === 1 ? "person" : "people"}` : `${people.length} people`}
                {pending > 0 && ` · ${pending} pending invitation${pending === 1 ? "" : "s"}`}
            </span>
            {props.dataset.embargo?.active &&
                <>
                    <div className="h-px bg-primary-100"></div>
                    <div className="flex justify-between text-[13px]">
                        <span className="text-primary-600">Anonymous links</span>
                        <span className="font-medium text-primary-900">{links.length} · {views} views</span>
                    </div>
                    <button type="button" aria-label="New anonymous link" className="self-start inline-flex items-center gap-1.5 rounded-md border border-primary-300 bg-primary-0 px-2.5 py-1.5 text-[13px] font-semibold text-primary-900" onClick={() => setShow(true)}>
                        <MaterialSymbol icon="add_link" size={16} grade={-25} weight={400} aria-hidden="true" /> New anonymous link
                    </button>
                </>
            }
            <ShareDialog dataset={props.dataset} show={show} onClose={() => setShow(false)} />
        </div>
    );
}
```

`components/Embargo/FilesWithheldNotice.tsx` — §1e, replacing the file list for a member of the tenancy:

```tsx
import { MaterialSymbol } from "react-material-symbols";
import { formatShortDate, tenancyDisplayName } from "../../lib/embargoDisplay";
import { bytesToSize } from "../../lib/file";
import { GetDatasetDetailsResponse, GetDatasetDetailsVersionResponse } from "../../types/BffAPI";

interface Props {
    dataset: GetDatasetDetailsResponse
    version?: GetDatasetDetailsVersionResponse
}

export function FilesWithheldNotice(props: Props) {
    if (!props.version?.files_withheld) {
        return null;
    }

    const summary = props.version.files_summary;
    const tenancy = tenancyDisplayName(props.dataset.tenancy);
    const owner = props.dataset.owner?.name;

    return (
        <div data-testid="files-withheld" className="flex flex-col items-center gap-3 rounded-lg border border-primary-200 bg-primary-0 px-8 py-9 text-center">
            <span aria-hidden="true" className="flex items-center justify-center h-11 w-11 rounded-full bg-embargo-100 text-embargo-800">
                <MaterialSymbol icon="lock" size={22} grade={-25} weight={400} fill />
            </span>
            <span className="text-base font-semibold text-primary-900">
                {summary?.count ?? 0} files · {bytesToSize(summary?.total_size_bytes ?? 0)}, under embargo
            </span>
            <span className="max-w-[460px] text-sm leading-[21px] text-primary-600">
                File names and downloads become available to {tenancy} members on{" "}
                <strong className="font-semibold text-primary-900">{formatShortDate(props.dataset.embargo?.until ?? "")}</strong>.
                Until then only the owner and the people they&apos;ve shared it with can reach them. You can cite the dataset now.
            </span>
            {owner && <span className="mt-1 text-[13px] text-primary-500">Need it earlier? Ask the owner, {owner}, to share it with you.</span>}
        </div>
    );
}
```

`lib/file.ts`'s `bytesToSize` writes `2.3 GB` for 2 469 606 195 bytes, as the test expects; if it writes another format on `main`, change the test's expected size to its output, not the function.

`components/Embargo/LockedDownloadButton.tsx` — §1e, present but disabled, so the member learns why rather than wonders where it went:

```tsx
import { MaterialSymbol } from "react-material-symbols";

export function LockedDownloadButton() {
    return (
        <button
            type="button"
            disabled
            title="The files are under embargo"
            className="inline-flex items-center gap-2 h-[38px] px-3.5 rounded-md border border-primary-200 bg-primary-100 text-primary-400 text-sm font-semibold cursor-not-allowed"
        >
            <MaterialSymbol icon="lock" size={18} grade={-25} weight={400} aria-hidden="true" /> Download
        </button>
    );
}
```

`components/Embargo/EmbargoFields.tsx` — the embargo half of §1a's "Under embargo" panel, shared with Settings' *Set embargo*:

```tsx
import { ErrorMessage, Field, useFormikContext } from "formik";
import { MaterialSymbol } from "react-material-symbols";
import { EDIT_FORM_ERROR_CLASS, EDIT_FORM_INPUT_CLASS } from "../../contants/EditFormConstants";
import { maxEmbargoDate, minEmbargoDate, toEmbargoUntil } from "../../lib/embargoDates";
import { daysFromToday, formatShortDate } from "../../lib/embargoDisplay";

interface Values {
    embargoMode: string
    embargoUntil: string
    embargoNote: string
}

const MEMBER_OPTIONS = [
    { value: "open", label: "See that it exists", hint: "Listed with an \"Embargoed\" badge. Title, description and authors readable; file names and downloads withheld." },
    { value: "hidden", label: "Don't see it at all", hint: "Hidden from every listing and search. Only you and the people you share it with know it exists." },
];

export function EmbargoFields(props: { tenancyName: string }) {
    const { values, setFieldValue } = useFormikContext<Values>();
    const now = new Date();
    const max = maxEmbargoDate(now);
    const days = values.embargoUntil ? daysFromToday(values.embargoUntil, now) : null;
    const until = values.embargoUntil ? formatShortDate(toEmbargoUntil(values.embargoUntil)) : null;

    return (
        <div className="flex flex-col gap-5">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                    <label htmlFor="embargoUntil" className="m-0 text-[13px] font-semibold text-primary-900">Embargo ends</label>
                    <Field type="date" id="embargoUntil" name="embargoUntil" min={minEmbargoDate(now)} max={max} className={EDIT_FORM_INPUT_CLASS} />
                    <span className="text-xs leading-[17px] text-primary-500">
                        {days !== null ? `${days} days. ` : ""}Up to 90 days ({formatShortDate(toEmbargoUntil(max))}); you can extend it later, 90 days at a time.
                    </span>
                    <ErrorMessage name="embargoUntil" component="div" className={EDIT_FORM_ERROR_CLASS} />
                </div>
                <div className="flex flex-col gap-1.5">
                    <label htmlFor="embargoNote" className="m-0 text-[13px] font-semibold text-primary-900">Note <span className="font-normal text-primary-400">optional</span></label>
                    <Field type="text" id="embargoNote" name="embargoNote" maxLength={2000} placeholder="Under review at JGR Atmospheres" className={EDIT_FORM_INPUT_CLASS} />
                    <span className="text-xs leading-[17px] text-primary-500">Visible to you and the people with access.</span>
                </div>
            </div>
            <fieldset className="flex flex-col gap-2 m-0 p-0 border-0">
                <legend className="mb-2 text-[13px] font-semibold text-primary-900">While embargoed, other members of {props.tenancyName}</legend>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {MEMBER_OPTIONS.map((option) => {
                        const selected = values.embargoMode === option.value;
                        return (
                            <label key={option.value} className={`flex flex-col gap-1 m-0 rounded-md bg-primary-0 px-3.5 py-3 cursor-pointer ${selected ? "border-[1.5px] border-primary-900" : "border border-primary-200"}`}>
                                <span className="flex items-center gap-2 text-[13px] font-semibold text-primary-900">
                                    <input type="radio" name="embargoMode" value={option.value} checked={selected} onChange={() => setFieldValue("embargoMode", option.value)} className="h-3.5 w-3.5 p-0 accent-primary-900" />
                                    {option.label}
                                </span>
                                <span className="pl-[22px] text-xs leading-[17px] text-primary-600">{option.hint}</span>
                            </label>
                        );
                    })}
                </div>
            </fieldset>
            <div className="flex gap-2.5 items-start rounded-md bg-embargo-100 px-3 py-2.5 text-xs leading-[18px] text-embargo-800">
                <MaterialSymbol icon="info" size={18} grade={-25} weight={400} className="flex-none" aria-hidden="true" />
                <span>
                    In either case there is no public page. Outside DataMap the DOI only says the dataset is under embargo
                    {until ? ` until ${until}` : ""}. Reviewers can read the metadata, with authors redacted, through a link you create after saving.
                </span>
            </div>
        </div>
    );
}
```

`components/Embargo/SetEmbargoDialog.tsx` — *Set embargo* from Settings, on a dataset that has none yet:

```tsx
import { FormikProvider, useFormik } from "formik";
import { useRouter } from "next/router";
import { useState } from "react";
import { EDIT_FORM_ERROR_CLASS } from "../../contants/EditFormConstants";
import { messageForApiError } from "../../contants/EmbargoConstants";
import { BFFAPI } from "../../gateways/BFFAPI";
import { embargoRequestFrom, validateEmbargoDate } from "../../lib/embargoDates";
import { tenancyDisplayName } from "../../lib/embargoDisplay";
import { GetDatasetDetailsResponse } from "../../types/BffAPI";
import Modal from "../base/PopupModal";
import { EmbargoFields } from "./EmbargoFields";

export function SetEmbargoDialog(props: { dataset: GetDatasetDetailsResponse, show: boolean, onClose(): void }) {
    const [bffGateway] = useState(() => new BFFAPI());
    const router = useRouter();
    const [error, setError] = useState<string | null>(null);
    const formik = useFormik({
        initialValues: { embargoMode: "hidden", embargoUntil: "", embargoNote: "" },
        validate: (values) => {
            const message = validateEmbargoDate(values.embargoUntil, new Date());
            return message ? { embargoUntil: message } : {};
        },
        onSubmit: async (values) => {
            setError(null);
            try {
                const request = embargoRequestFrom(values as any);
                await bffGateway.setEmbargo(props.dataset.id, { ...request, note: values.embargoNote.trim() || null });
                props.onClose();
                router.reload();
            } catch (e) {
                setError(messageForApiError(e));
            }
        },
    });

    return (
        <Modal
            title="Put under embargo"
            show={props.show}
            confimButtonText="Set embargo"
            cancelButtonText="Cancel"
            cancel={props.onClose}
            confim={() => formik.submitForm()}
            maxWidthClassName="max-w-2xl"
        >
            <FormikProvider value={formik}>
                <div className="flex flex-col gap-3">
                    <p className="m-0 text-[13px] text-primary-500">Only you and the people you share it with reach the files until the date you choose.</p>
                    <EmbargoFields tenancyName={tenancyDisplayName(props.dataset.tenancy)} />
                    {error && <p role="alert" className={EDIT_FORM_ERROR_CLASS}>{error}</p>}
                </div>
            </FormikProvider>
        </Modal>
    );
}
```

`components/Embargo/EmbargoSettingsSection.tsx` — §1g "Embargo":

```tsx
import { useState } from "react";
import { MaterialSymbol } from "react-material-symbols";
import { EMBARGO_ERROR_MESSAGES } from "../../contants/EmbargoConstants";
import { daysLeft, formatShortDate } from "../../lib/embargoDisplay";
import { hasManualDoi } from "../../lib/embargoState";
import { GetDatasetDetailsResponse } from "../../types/BffAPI";
import { EmbargoModeDialog, EmbargoNoteDialog, EndEmbargoDialog, ExtendEmbargoDialog } from "./EmbargoDialogs";
import { SetEmbargoDialog } from "./SetEmbargoDialog";

export function SettingsBlock(props: { title: string, danger?: boolean, children: React.ReactNode }) {
    return (
        <div className="grid grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)] gap-x-10 gap-y-3 items-start">
            <span className={`text-[15px] font-semibold ${props.danger ? "text-danger-700" : "text-primary-900"}`}>{props.title}</span>
            {props.children}
        </div>
    );
}

function Row(props: { label: string, children: React.ReactNode, action?: React.ReactNode }) {
    return (
        <div className="grid grid-cols-[180px_minmax(0,1fr)_auto] gap-x-3 items-center px-4 py-3.5 border-b border-primary-100 last:border-b-0 text-sm">
            <span className="text-primary-500">{props.label}</span>
            <span className="min-w-0 text-primary-900">{props.children}</span>
            <span>{props.action}</span>
        </div>
    );
}

function Action(props: { label: string, danger?: boolean, onClick(): void }) {
    return (
        <button type="button" onClick={props.onClick} className={`text-[13px] font-medium hover:underline underline-offset-2 ${props.danger ? "text-danger-700" : "text-primary-600"}`}>
            {props.label}
        </button>
    );
}

export function EmbargoSettingsSection(props: { dataset: GetDatasetDetailsResponse }) {
    const [open, setOpen] = useState<"set" | "extend" | "end" | "mode" | "note" | null>(null);
    const embargo = props.dataset.embargo;
    const access = props.dataset.access;
    const manage = access?.can_manage_embargo === true;
    const close = () => setOpen(null);

    if (!access || (!manage && !access.can_extend_embargo && !embargo?.active)) {
        return null;
    }

    return (
        <SettingsBlock title="Embargo">
            <div className="rounded-lg border border-primary-200 bg-primary-0">
                {embargo?.active
                    ? <>
                        <Row label="Status" action={manage && <Action label="End early" danger onClick={() => setOpen("end")} />}>
                            <span className="flex items-center gap-2">
                                <span className="inline-flex items-center gap-1.5 rounded-full bg-embargo-100 px-2.5 py-[3px] text-xs font-semibold text-embargo-800">
                                    <MaterialSymbol icon="lock" size={14} grade={-25} weight={400} fill aria-hidden="true" />
                                    Under embargo
                                </span>
                                <span className="text-primary-600">{daysLeft(embargo.until, new Date())} days left</span>
                            </span>
                        </Row>
                        <Row label="Ends" action={access.can_extend_embargo && <Action label="Extend" onClick={() => setOpen("extend")} />}>
                            {formatShortDate(embargo.until)}
                        </Row>
                        <Row label="Other members" action={manage && <Action label={embargo.metadata_visible ? "Hide" : "Show"} onClick={() => setOpen("mode")} />}>
                            {embargo.metadata_visible ? "Visible to members" : "Hidden from members"}
                        </Row>
                        <Row label="Note" action={manage && <Action label="Edit" onClick={() => setOpen("note")} />}>
                            <span className="text-primary-700">{embargo.note ?? "No note"}</span>
                        </Row>
                        <Row label="Reminders"><span className="text-primary-700">15, 10, 5 and 1 day before the end</span></Row>
                    </>
                    : <Row label="Status" action={manage && !hasManualDoi(props.dataset) && <Action label="Set embargo" onClick={() => setOpen("set")} />}>
                        <span className="flex flex-col gap-0.5">
                            <span>Not under embargo</span>
                            {manage && hasManualDoi(props.dataset) && <span className="text-[13px] text-primary-500">{EMBARGO_ERROR_MESSAGES.embargo_manual_doi}</span>}
                        </span>
                    </Row>
                }
            </div>
            <SetEmbargoDialog dataset={props.dataset} show={open === "set"} onClose={close} />
            <ExtendEmbargoDialog dataset={props.dataset} show={open === "extend"} onClose={close} />
            <EndEmbargoDialog dataset={props.dataset} show={open === "end"} onClose={close} />
            <EmbargoModeDialog dataset={props.dataset} show={open === "mode"} onClose={close} />
            <EmbargoNoteDialog dataset={props.dataset} show={open === "note"} onClose={close} />
        </SettingsBlock>
    );
}
```

A published dataset shows *Set embargo* too; the gatekeeper refuses it with `embargo_dataset_published` and the dialog shows that message, since the BFF payload does not say whether a public page exists.

`components/Embargo/AccessSummary.tsx` — §1g "Access":

```tsx
import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "../../lib/fetcher";
import { GetDatasetDetailsResponse } from "../../types/BffAPI";
import { ShareState } from "../../types/GatekeeperAPI";
import { ShareDialog } from "../Share/ShareDialog";
import { SettingsBlock } from "./EmbargoSettingsSection";

export function AccessSummary(props: { dataset: GetDatasetDetailsResponse }) {
    const [show, setShow] = useState(false);
    const canShare = props.dataset.access?.can_share === true;
    const { data } = useSWR(canShare ? `/api/datasets/${props.dataset.id}/share` : null, fetcher);
    const state = data as ShareState;

    if (!canShare || !state) {
        return null;
    }

    const names = [state.owner.name, ...state.permissions.map((p) => p.level === "write" ? `${p.user.name} (write)` : p.user.name)];
    const pending = state.invitations.filter((i) => !i.accepted_at && !i.revoked_at).length;
    const links = state.anonymous_links.filter((l) => !l.revoked_at).length;
    const parts = [names.join(", "), pending ? `${pending} pending` : "", links ? `${links} anonymous link${links === 1 ? "" : "s"}` : ""].filter(Boolean);

    return (
        <SettingsBlock title="Access">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-lg border border-primary-200 bg-primary-0 px-4 py-3.5 text-sm">
                <span className="min-w-0 text-primary-900">{parts.join(" · ")}</span>
                <button type="button" className="text-[13px] font-medium text-primary-600 hover:underline underline-offset-2" onClick={() => setShow(true)}>Open share dialog</button>
            </div>
            <ShareDialog dataset={props.dataset} show={show} onClose={() => setShow(false)} />
        </SettingsBlock>
    );
}
```

`components/Embargo/AccessHistory.tsx` — §1g "History", read from the audit trail:

```tsx
import { MaterialSymbol } from "react-material-symbols";
import useSWR from "swr";
import { describeAccessEvent, formatHistoryWhen } from "../../lib/embargoDisplay";
import { fetcher } from "../../lib/fetcher";
import { AccessHistoryResponse } from "../../types/GatekeeperAPI";
import { SettingsBlock } from "./EmbargoSettingsSection";

export function AccessHistory(props: { datasetId: string }) {
    const { data } = useSWR(`/api/datasets/${props.datasetId}/access-events`, fetcher);
    const items = (data as AccessHistoryResponse)?.items ?? [];

    if (items.length === 0) {
        return null;
    }

    return (
        <SettingsBlock title="History">
            <ul className="m-0 p-0 list-none rounded-lg border border-primary-200 bg-primary-0">
                {items.map((entry, index) => {
                    const row = describeAccessEvent(entry);
                    return (
                        <li key={index} className="grid grid-cols-[28px_minmax(0,1fr)_150px] gap-3 items-start px-4 py-3 border-b border-primary-100 last:border-b-0 text-sm leading-5">
                            <MaterialSymbol icon={row.icon as any} size={18} grade={-25} weight={400} className="pt-px text-primary-500" aria-hidden="true" />
                            <span className="min-w-0">
                                <strong className="font-semibold text-primary-900">{row.who}</strong> <span className="text-primary-700">{row.what}</span>
                                {row.detail && <span className="block text-xs text-primary-500">{row.detail}</span>}
                            </span>
                            <span className="text-right font-mono text-xs text-primary-500">{formatHistoryWhen(entry.occurred_at)}</span>
                        </li>
                    );
                })}
            </ul>
        </SettingsBlock>
    );
}
```

`components/Embargo/EmbargoEndedBanner.tsx` — §1h, the neutral card with a checklist and no dismiss:

```tsx
import { useRouter } from "next/router";
import { useState } from "react";
import { MaterialSymbol } from "react-material-symbols";
import { messageForApiError } from "../../contants/EmbargoConstants";
import { BFFAPI } from "../../gateways/BFFAPI";
import { formatShortDate, tenancyDisplayName } from "../../lib/embargoDisplay";
import { GetDatasetDetailsDOIResponseState, GetDatasetDetailsResponse } from "../../types/BffAPI";
import Modal from "../base/PopupModal";

export function EmbargoEndedBanner(props: { dataset: GetDatasetDetailsResponse }) {
    const [bffGateway] = useState(() => new BFFAPI());
    const router = useRouter();
    const [confirming, setConfirming] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const doi = props.dataset.current_version?.doi;
    const registered = doi?.state === GetDatasetDetailsDOIResponseState.REGISTERED;
    const tenancy = tenancyDisplayName(props.dataset.tenancy);

    async function promote() {
        setError(null);
        try {
            await bffGateway.navigateDOIStatus({
                datasetId: props.dataset.id,
                versionName: props.dataset.current_version.name,
                state: GetDatasetDetailsDOIResponseState.FINDABLE,
            });
            setConfirming(false);
            router.reload();
        } catch (e) {
            setError(messageForApiError(e));
        }
    }

    return (
        <div role="status" className="grid grid-cols-[40px_minmax(0,1fr)] md:grid-cols-[40px_minmax(0,1fr)_auto] gap-4 items-start rounded-lg border border-primary-200 bg-primary-0 px-6 py-5">
            <span aria-hidden="true" className="flex items-center justify-center h-10 w-10 rounded-full bg-secondary-500 text-primary-900">
                <MaterialSymbol icon="lock_open" size={22} grade={-25} weight={400} />
            </span>
            <div className="flex flex-col gap-2">
                <span className="text-base font-semibold text-primary-900">
                    The embargo ended on {formatShortDate(props.dataset.embargo?.until ?? "", false)}. One step left to publish.
                </span>
                <div className="flex flex-col gap-1.5 text-sm leading-[21px] text-primary-700">
                    <div className="flex gap-2.5">
                        <MaterialSymbol icon="check_circle" size={18} grade={-25} weight={400} fill className="flex-none text-success-500" aria-hidden="true" />
                        <span>Files are available to every member of {tenancy}.</span>
                    </div>
                    <div className="flex gap-2.5">
                        <MaterialSymbol icon="radio_button_unchecked" size={18} grade={-25} weight={400} className="flex-none text-primary-400" aria-hidden="true" />
                        {registered
                            ? <span>Nothing is public yet. The DOI <span className="font-mono text-[13px]">{doi.identifier}</span> is <strong className="font-semibold">registered but not findable</strong>: it resolves, but DataCite doesn&apos;t index it, so the dataset won&apos;t appear in DataCite search or in services that harvest from it, and there&apos;s no public page.</span>
                            : <span>Nothing is public yet. The dataset has no DOI to promote: create one in the Citation section, then make it findable.</span>}
                    </div>
                </div>
                <span className="text-[13px] text-primary-500">Promoting it publishes the public page with the authors; anonymous links then lead there. Nothing does this for you.</span>
                {error && <p role="alert" className="m-0 text-sm text-danger-700">{error}</p>}
            </div>
            {registered &&
                <div className="flex flex-col items-start md:items-end gap-2">
                    <button type="button" onClick={() => setConfirming(true)} className="h-10 px-3.5 rounded-md bg-primary-900 text-primary-50 text-sm font-semibold whitespace-nowrap hover:bg-primary-800">Make DOI findable</button>
                    <span className="text-xs text-primary-400">Shown until you do</span>
                </div>
            }
            <Modal
                title="Make the DOI findable?"
                show={confirming}
                confimButtonText="Make it findable"
                cancelButtonText="Not yet"
                cancel={() => setConfirming(false)}
                confim={promote}
                maxWidthClassName="max-w-[440px]"
            >
                <ul className="m-0 p-0 list-none flex flex-col gap-2.5 text-sm leading-[21px] text-primary-700">
                    <li className="flex gap-2.5"><span className="text-primary-400">—</span><span>The public page is published, with the authors</span></li>
                    <li className="flex gap-2.5"><span className="text-primary-400">—</span><span>DataCite indexes the DOI</span></li>
                    <li className="flex gap-2.5"><span className="text-primary-400">—</span><span>Anonymous links lead to the public page</span></li>
                </ul>
            </Modal>
        </div>
    );
}
```

- [ ] **Step 5: Wire the dataset page**

`components/DatasetDetailsPage.tsx` (as on main since #101: `StatusPill`, `max-w-5xl` column, actions in `flex flex-none items-center gap-2`) — imports:

```tsx
import { EmbargoBadge } from "./Embargo/EmbargoBadge";
import { EmbargoEndedBanner } from "./Embargo/EmbargoEndedBanner";
import { LockedDownloadButton } from "./Embargo/LockedDownloadButton";
import { canSeeSettings, isFilesWithheld, shouldShowEmbargoEndedBanner } from "../lib/embargoState";
import { bytesToSize } from "../lib/file";
```

`totalDatasetVersionFilesSize` stays imported from `../lib/file`. Replace the `filesCount` line with:

```tsx
  const filesWithheld = selectedVersion?.files_withheld ?? false;
  const filesCount = filesWithheld
    ? selectedVersion?.files_summary?.count ?? 0
    : selectedVersion?.files_in?.length ?? 0;
  const filesSize = filesWithheld
    ? bytesToSize(selectedVersion?.files_summary?.total_size_bytes ?? 0)
    : totalDatasetVersionFilesSize(selectedVersion);
```

and in the mono line use `{filesSize}` instead of `{totalDatasetVersionFilesSize(selectedVersion)}`.

`<LoggedLayout>` becomes `<LoggedLayout tenancyOptional>`. In the pill row, after `<StatusPill designState={selectedVersion?.design_state} />`:

```tsx
                <EmbargoBadge embargo={props.dataset.embargo} />
```

The actions block becomes (Task 10 adds the Share button as its first child):

```tsx
            <div className="flex flex-none items-center gap-2">
              {isFilesWithheld(props.dataset) ? <LockedDownloadButton /> : <DownloadDatafilesButton dataset={props.dataset} />}
              {(props.dataset.access?.can_delete ?? true) && <DatasetMoreSettingsButton dataset={props.dataset} />}
            </div>
```

Between the header block (the `md:flex-row` div) and `<Tabs className="pt-7">`:

```tsx
          {shouldShowEmbargoEndedBanner(props.dataset) && <EmbargoEndedBanner dataset={props.dataset} />}
```

and the settings tab condition:

```tsx
            {canSeeSettings(props.dataset, canEditDataset(props.user, props.dataset)) &&
              <TabPanelSettings title="Settings" dataset={props.dataset} user={props.user} />
            }
```

`components/DatasetDetails/DataCard/TabPanelDataCard.tsx` — import `EmbargoCard`, `AccessCard` from `../../Embargo/…`, `formatShortDate` from `../../../lib/embargoDisplay`. At the top of the `<aside className="flex flex-col gap-4">`:

```tsx
          <EmbargoCard dataset={props.dataset} />
          <AccessCard dataset={props.dataset} />
```

and inside the first sidebar card (the one with `DatasetUsability`), before `<DatasetUsability …>`, the member's facts of §1e:

```tsx
            {selectedVersion?.files_withheld && props.dataset.embargo &&
              <>
                <FactRow label="Files available">{formatShortDate(props.dataset.embargo.until)}</FactRow>
                {props.dataset.owner && <FactRow label="Owner">{props.dataset.owner.name}</FactRow>}
              </>
            }
```

`components/DatasetDetails/DataCard/DataExplorer.tsx` — add `import { FilesWithheldNotice } from "../../Embargo/FilesWithheldNotice";` and `import { bytesToSize } from "../../../lib/file";`. The count in the header (`{getVersionByName(...)?.files_in?.length ?? 0} files · {totalDatasetVersionFilesSize(selectedDatasetVersion)}`) becomes:

```tsx
            {selectedDatasetVersion?.files_withheld
              ? <>{selectedDatasetVersion.files_summary?.count ?? 0} files · {bytesToSize(selectedDatasetVersion.files_summary?.total_size_bytes ?? 0)}</>
              : <>{getVersionByName(props.selectedVersionName, props.dataset.versions, props.dataset)?.files_in?.length ?? 0} files · {totalDatasetVersionFilesSize(selectedDatasetVersion)}</>
            }
```

`NewVersionButton` is shown only to whoever may edit: `{props.dataset.access?.can_edit !== false && <NewVersionButton onClick={() => setShowUploadDataModal(true)} />}`. The file list becomes:

```tsx
      {selectedDatasetVersion?.files_withheld
        ? <FilesWithheldNotice dataset={props.dataset} version={selectedDatasetVersion} />
        : <>
            <DatasetFilesList … />
            {props.dataset.embargo?.active &&
              <p className="m-0 mt-2 text-[13px] text-primary-500">Download links expire after 1 hour while embargoed.</p>
            }
          </>
      }
```

keeping the existing `<DatasetFilesList …>` element and its props as they are where `…` stands.

`components/DatasetDetails/TabPanelSettings.tsx` — §1g: the tab becomes a column of 220 px-labelled blocks. Add the imports `EmbargoSettingsSection`, `SettingsBlock` (from `../Embargo/EmbargoSettingsSection`), `AccessSummary`, `AccessHistory` and `canEditDataset` (`../../lib/users`). Keep the existing *General* `section` and its `Formik` unchanged, rendered only when `canEditDataset(props.user, props.dataset)`, and replace the outer grid with:

```tsx
      <div className="flex flex-col gap-7 pt-2">
        {canEditDataset(props.user, props.dataset) &&
          <SettingsBlock title="General">
            {/* the existing <Formik …>…</Formik> for name and institution, unchanged */}
          </SettingsBlock>
        }
        <EmbargoSettingsSection dataset={props.dataset} />
        <AccessSummary dataset={props.dataset} />
        {canEditDataset(props.user, props.dataset) && <AccessHistory datasetId={props.dataset.id} />}
      </div>
```

Move the existing `<Formik …>…</Formik>` into the *General* block without changing it, and drop its old `h2`/subtitle and the "About settings" `aside` (the block's label replaces them). Both dataset pages already route errors through `handleDatasetRequestErrors`, which renders not-found on 404 (Task 5).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/users.test.ts components/Embargo/__tests__`
Expected: PASS.

- [ ] **Step 7: Compare with the design**

`npm run dev`; open a dataset you own under embargo, then the same dataset as a member of its tenancy (open mode), then one whose embargo ended with a registered DOI. Next to `Embargo Feature.dc.html` §1b, §1d, §1e, §1g and §1h, check the badge, the two sidebar cards, the files section for the member and the locked Download, the Settings rows and History, the dialogs, and the banner.

- [ ] **Step 8: Commit**

```bash
git add lib/users.ts lib/__tests__/users.test.ts components/Embargo/ components/DatasetDetailsPage.tsx components/DatasetDetails/
git commit -m "feat: the embargo on the dataset page, its settings and history, as designed"
```

---

### Task 9: Embargo choice at creation

The "Who can see it" block of `Embargo Feature.dc.html` §1a, "Create a dataset" (`docs/design/rfc-003-embargo/`): two cards, *Open to the workspace* and *Under embargo*; choosing the second unfolds the panel Task 8 built as `EmbargoFields` (end date, note, what other members see, the amber DOI notice); the footer adds "· embargo until Dec 15, 2026" to the file count. The members' choice starts on *Don't see it at all*, because `embargo_metadata_visible` defaults to false (§1a "Why here").

**Files:**
- Create: `components/Embargo/EmbargoChoice.tsx`
- Modify: `types/new-dataset.d.ts` (`FormValues`), `pages/app/datasets/new.tsx`
- Test: `components/Embargo/__tests__/EmbargoChoice.test.tsx`

**Interfaces:**
- Consumes: `EmbargoFields` (Task 8); `embargoRequestFrom`, `validateEmbargoDate`, `toEmbargoUntil` (Task 3); `formatShortDate`, `tenancyDisplayName` (Task 3); `BFFAPI.setEmbargo` (Task 6); `useTenancyStore` (main).
- Produces: `EmbargoChoice({ tenancyName })` — Formik fields `embargoMode` (`"none" | "open" | "hidden"`), `embargoUntil`, `embargoNote` (must be rendered inside a `<Formik>`).

- [ ] **Step 1: Write the failing test**

`components/Embargo/__tests__/EmbargoChoice.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react';
import { Form, Formik } from "formik";
import { EmbargoChoice } from "../EmbargoChoice";

function renderChoice() {
    render(
        <Formik initialValues={{ embargoMode: "none", embargoUntil: "", embargoNote: "" }} onSubmit={() => undefined}>
            <Form><EmbargoChoice tenancyName="Data Amazon" /></Form>
        </Formik>
    );
}

describe("EmbargoChoice", () => {
    test("open to the workspace by default, and no date asked", () => {
        renderChoice();

        expect((screen.getByRole("radio", { name: /Open to the workspace/ }) as HTMLInputElement).checked).toBe(true);
        expect(screen.getByText("Every member of Data Amazon can read and download the files.")).toBeTruthy();
        expect(screen.queryByLabelText("Embargo ends")).toBeNull();
    });

    test("under embargo asks for the date, and members don't see it until the author says so", () => {
        renderChoice();

        fireEvent.click(screen.getByRole("radio", { name: /Under embargo/ }));

        const date = screen.getByLabelText("Embargo ends") as HTMLInputElement;
        expect(date.min).not.toBe("");
        expect(date.max).not.toBe("");
        expect(screen.getByText("While embargoed, other members of Data Amazon")).toBeTruthy();
        expect((screen.getByRole("radio", { name: /Don't see it at all/ }) as HTMLInputElement).checked).toBe(true);
    });

    test("members may be told it exists", () => {
        renderChoice();

        fireEvent.click(screen.getByRole("radio", { name: /Under embargo/ }));
        fireEvent.click(screen.getByRole("radio", { name: /See that it exists/ }));

        expect((screen.getByRole("radio", { name: /See that it exists/ }) as HTMLInputElement).checked).toBe(true);
        expect((screen.getByRole("radio", { name: /Under embargo/ }) as HTMLInputElement).checked).toBe(true);
    });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx jest components/Embargo/__tests__/EmbargoChoice.test.tsx`
Expected: FAIL — `Cannot find module '../EmbargoChoice'`.

- [ ] **Step 3: Implement**

`components/Embargo/EmbargoChoice.tsx` — the label and hint follow the *Title* and *Data files* blocks of `pages/app/datasets/new.tsx` (`text-sm font-semibold`, `text-[13px]` hint); the cards are the same as the members' choice in `EmbargoFields`:

```tsx
import { useFormikContext } from "formik";
import { EmbargoFields } from "./EmbargoFields";

interface Values {
    embargoMode: string
    embargoUntil: string
    embargoNote: string
}

export function EmbargoChoice(props: { tenancyName: string }) {
    const { values, setFieldValue } = useFormikContext<Values>();
    const embargoed = values.embargoMode !== "none";
    const options = [
        { embargo: false, label: "Open to the workspace", hint: `Every member of ${props.tenancyName} can read and download the files.` },
        { embargo: true, label: "Under embargo", hint: "Only you and the people you share it with reach the files. The dataset stays citable: you can reserve a DOI and give reviewers a read-only link." },
    ];

    return (
        <div className="flex flex-col gap-2">
            <span className="text-sm font-semibold text-primary-900">Who can see it</span>
            <span className="text-[13px] leading-[19px] text-primary-500">You can change this later, as long as the dataset hasn&apos;t been published.</span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
                {options.map((option) => {
                    const selected = embargoed === option.embargo;
                    return (
                        <label key={option.label} className={`flex flex-col gap-1 m-0 rounded-md bg-primary-0 px-3.5 py-3 cursor-pointer ${selected ? "border-[1.5px] border-primary-900" : "border border-primary-200"}`}>
                            <span className="flex items-center gap-2 text-sm font-semibold text-primary-900">
                                <input
                                    type="radio"
                                    name="visibility"
                                    checked={selected}
                                    onChange={() => setFieldValue("embargoMode", option.embargo ? "hidden" : "none")}
                                    className="h-3.5 w-3.5 p-0 accent-primary-900"
                                />
                                {option.label}
                            </span>
                            <span className="pl-[22px] text-[13px] leading-[19px] text-primary-600">{option.hint}</span>
                        </label>
                    );
                })}
            </div>
            {embargoed &&
                <div className="mt-2 rounded-lg border border-primary-200 bg-primary-0 p-5">
                    <EmbargoFields tenancyName={props.tenancyName} />
                </div>
            }
        </div>
    );
}
```

`types/new-dataset.d.ts` — `FormValues` becomes:

```ts
interface FormValues {
    datasetTitle?: string,
    urls?: DatafilePath[]
    uploadedDataFiles?: Datafile[],
    remoteFilesCount: number
    embargoMode?: "none" | "open" | "hidden"
    embargoUntil?: string
    embargoNote?: string
}
```

`pages/app/datasets/new.tsx` (as on main since #101):

1. Imports:

```tsx
import { EmbargoChoice } from "../../../components/Embargo/EmbargoChoice";
import { useTenancyStore } from "../../../components/TenancyStore";
import { embargoRequestFrom, toEmbargoUntil, validateEmbargoDate } from "../../../lib/embargoDates";
import { formatShortDate, tenancyDisplayName } from "../../../lib/embargoDisplay";
```

2. In `NewPage`, after `const { data: session } = useSession();`: `const tenancySelected = useTenancyStore((state) => state.tenancySelected);`.
3. `initialValues` gains `embargoMode: 'none', embargoUntil: '', embargoNote: ''`.
4. In `handleValidateForm`, before `return errors;`:

```ts
    if (values.embargoMode && values.embargoMode !== "none") {
      const message = validateEmbargoDate(values.embargoUntil, new Date());
      if (message) {
        errors.embargoUntil = message;
      }
    }
```

5. In `handleSubmitForm`, the chain starts with the embargo, so no file is uploaded to a dataset the tenancy can still read. Replace the first two links (`uploadFiles()` and `.then(() => updateDataset(datasetUpdateRequest))`) with:

```ts
    const embargoRequest = embargoRequestFrom(values);
    const datasetId = datasetPrototyping.createDatasetResponseV2.id;

    (embargoRequest
      ? bffGateway.setEmbargo(datasetId, { ...embargoRequest, note: values.embargoNote?.trim() || null })
      : Promise.resolve(null))
      .then(() => uploadFiles())
      .then(() => updateDataset(datasetUpdateRequest))
```

The rest of the chain (`.then(() => { … publishDatasetVersion … })` onward) is unchanged.

6. Render `<EmbargoChoice tenancyName={tenancyDisplayName(tenancySelected)} />` after the *Data files* block (the `flex flex-col gap-2` div that starts with `<span className="text-sm font-semibold text-primary-900">Data files</span>` and ends with `<UppyUploader … />`), as the last child of the `flex flex-col gap-10` column — §1a orders Title, Data files, Who can see it.
7. The footer's count (`{values.remoteFilesCount} {values.remoteFilesCount === 1 ? "file" : "files"}`) gains the embargo:

```tsx
                  {values.remoteFilesCount} {values.remoteFilesCount === 1 ? "file" : "files"}
                  {values.embargoMode !== "none" && values.embargoUntil && ` · embargo until ${formatShortDate(toEmbargoUntil(values.embargoUntil))}`}
```

The design's footer also shows the total size ("2 files · 339 MB"); main's footer counts files only, and this task does not add the size.

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx jest components/Embargo/__tests__/EmbargoChoice.test.tsx lib/__tests__/embargoDates.test.ts`
Expected: PASS.

- [ ] **Step 5: Compare with the design**

`npm run dev`, open `/app/datasets/new`, choose *Under embargo*, and set a date and a note. Next to §1a, check the two cards, the unfolded panel, the amber notice and the footer.

- [ ] **Step 6: Commit**

```bash
git add components/Embargo/EmbargoChoice.tsx components/Embargo/__tests__/EmbargoChoice.test.tsx types/new-dataset.d.ts pages/app/datasets/new.tsx
git commit -m "feat: choose who can see a dataset when creating it"
```

---

### Task 10: Share dialog

The dialog is `Embargo Feature.dc.html` §1c (`docs/design/rfc-003-embargo/`): the screens "Share dialog" (under embargo), "Share without embargo", "Share typing", "New anonymous link" and "Link created once", and from §1d the "Revoke access" prompt. It works on **any** dataset; the anonymous-links section and its footnote appear only under embargo, and the first row names the tenancy only without one (contracts §Sharing).

**Files:**
- Create: `hooks/UseDebouncedValue.ts`
- Create: `contants/ShareConstants.ts`, `components/Share/PersonInitial.tsx`, `components/Share/ShareInput.tsx`, `components/Share/OneTimeLinkDialog.tsx`, `components/Share/RemoveAccessDialog.tsx`, `components/Share/NewAnonymousLinkDialog.tsx`, `components/Share/AccessList.tsx`, `components/Share/AnonymousLinksSection.tsx`, `components/Share/ShareDialog.tsx`, `components/Share/ShareButton.tsx`
- Modify: `components/DatasetDetailsPage.tsx`, `components/base/PopupModal.tsx` (`hideCancel`)
- Test: `components/Share/__tests__/ShareInput.test.tsx`, `components/Share/__tests__/AccessList.test.tsx`, `components/Share/__tests__/AnonymousLinksSection.test.tsx`, `components/Share/__tests__/ShareDialog.test.tsx`

**Interfaces:**
- Consumes: `classifyShareInput` (Task 3); `initialsOf`, `formatShortDate`, `describeLinkStats`, `tenancyDisplayName` (Task 3, `lib/embargoDisplay.ts`); BFFAPI methods (Task 6); `messageForApiError`, `ANONYMOUS_LINK_LABEL_MAX` (Task 1); `ShareState` with `tenancy` and `invited_as`, `AnonymousLink.token_hint` (Task 1); SWR key `/api/datasets/{id}/share`; `components/base/PopupModal.tsx`.
- Produces:
  - `useDebouncedValue<T>(value: T, delayMs: number): T`
  - `ShareInput({ datasetId, tenancyName, onGrant(request: GrantRequest): Promise<void> })`
  - `AccessList({ state, embargoActive, onChangeLevel(userId, level), onRemove(permission), onRevokeInvitation(id) })`
  - `AnonymousLinksSection({ links, onNew(), onRevoke(id) })`
  - `NewAnonymousLinkDialog({ show, onCreate(label): Promise<void>, onCancel })`, `OneTimeLinkDialog({ link, kind: "anonymous" | "invitation", onDone })`, `RemoveAccessDialog({ permission, embargoActive, onConfirm, onCancel })`
  - `ShareDialog({ dataset, show, onClose })`, `ShareButton({ dataset })` — the button shows how many people have access, as the design's "Share 4"

- [ ] **Step 1: Write the failing tests**

`components/Share/__tests__/ShareInput.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { beforeEach, describe, expect, jest, test } from '@jest/globals';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

const searchShareCandidates = jest.fn() as any;
jest.mock("../../../gateways/BFFAPI", () => ({
    BFFAPI: jest.fn().mockImplementation(() => ({ searchShareCandidates })),
}));

import { ShareInput } from "../ShareInput";

beforeEach(() => {
    jest.useFakeTimers();
    searchShareCandidates.mockResolvedValue([{ id: "u2", name: "Marcia Yamasoe", email: "marcia.yamasoe@iag.usp.br" }]);
});

function type(text: string) {
    fireEvent.change(screen.getByLabelText("Add people by name, email or ORCID"), { target: { value: text } });
}

async function settle() {
    await act(async () => { jest.advanceTimersByTime(300); });
    await act(async () => { await Promise.resolve(); });
}

describe("ShareInput", () => {
    test("searches the workspace once the typing settles, and says how to reach others", async () => {
        render(<ShareInput datasetId="d1" tenancyName="Data Amazon" onGrant={jest.fn() as any} />);

        type("ma");
        type("mar");
        expect(searchShareCandidates).not.toHaveBeenCalled();
        await settle();

        await waitFor(() => expect(searchShareCandidates).toHaveBeenCalledTimes(1));
        expect(searchShareCandidates).toHaveBeenCalledWith("d1", "mar");
        expect(await screen.findByRole("button", { name: /Marcia Yamasoe/ })).toBeTruthy();
        expect(screen.getByText("Someone outside Data Amazon? Type their full email or ORCID.")).toBeTruthy();
    });

    test("picking a suggestion grants to that user at the chosen level", async () => {
        const onGrant = jest.fn().mockResolvedValue(undefined) as any;
        render(<ShareInput datasetId="d1" tenancyName="Data Amazon" onGrant={onGrant} />);

        fireEvent.change(screen.getByLabelText("Access level"), { target: { value: "write" } });
        type("mar");
        await settle();
        fireEvent.click(await screen.findByRole("button", { name: /Marcia Yamasoe/ }));

        await waitFor(() => expect(onGrant).toHaveBeenCalledWith({ user_id: "u2", level: "write" }));
    });

    test("a full email is offered as an invitation, without searching", async () => {
        const onGrant = jest.fn().mockResolvedValue(undefined) as any;
        render(<ShareInput datasetId="d1" tenancyName="Data Amazon" onGrant={onGrant} />);

        type("joao.silva@inpe.br");
        await settle();
        fireEvent.click(screen.getByRole("button", { name: /Invite joao.silva@inpe.br/ }));

        await waitFor(() => expect(onGrant).toHaveBeenCalledWith({ email: "joao.silva@inpe.br", level: "read" }));
        expect(searchShareCandidates).not.toHaveBeenCalled();
    });

    test("an ORCID URL is offered as an invitation by ORCID", async () => {
        const onGrant = jest.fn().mockResolvedValue(undefined) as any;
        render(<ShareInput datasetId="d1" tenancyName="Data Amazon" onGrant={onGrant} />);

        type("https://orcid.org/0000-0002-1825-0097");
        fireEvent.click(screen.getByRole("button", { name: /Invite ORCID 0000-0002-1825-0097/ }));

        await waitFor(() => expect(onGrant).toHaveBeenCalledWith({ orcid: "0000-0002-1825-0097", level: "read" }));
    });

    test("a mistyped ORCID is refused on the spot, in the design's words", () => {
        render(<ShareInput datasetId="d1" tenancyName="Data Amazon" onGrant={jest.fn() as any} />);

        type("0000-0002-1825-0098");

        expect(screen.getByText("0000-0002-1825-0098 isn't a valid ORCID")).toBeTruthy();
        expect(screen.getByText("The last digit doesn't check out. Compare it with the person's ORCID page.")).toBeTruthy();
        expect(screen.queryByRole("button", { name: /Invite/ })).toBeNull();
    });
});
```

`components/Share/__tests__/AccessList.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react';
import { AccessList } from "../AccessList";

const state: any = {
    owner: { id: "o", name: "Luciana Rizzo", email: "luciana.rizzo@usp.br" },
    permissions: [
        { user: { id: "u2", name: "Alan Calheiros", email: "alan.calheiros@inpe.br" }, level: "write", granted_at: "2026-09-09T10:00:00+00:00", granted_by: "o", invited_as: null },
        { user: { id: "u3", name: "Fernanda Lima", email: "fernanda.lima@gmail.com" }, level: "read", granted_at: "2026-09-29T10:00:00+00:00", granted_by: "o", invited_as: "fernanda@inpe.br" },
    ],
    invitations: [
        { id: "i1", email: "maria.oliveira@inpe.br", orcid: null, level: "read", created_at: "2026-09-28T10:00:00+00:00", accepted_at: null, accepted_by: null, revoked_at: null },
        { id: "i2", email: null, orcid: "0000-0002-1825-0097", level: "read", created_at: "2026-09-30T10:00:00+00:00", accepted_at: null, accepted_by: null, revoked_at: null },
        { id: "i3", email: "fernanda@inpe.br", orcid: null, level: "read", created_at: "2026-09-27T10:00:00+00:00", accepted_at: "2026-09-29T10:00:00+00:00", accepted_by: { id: "u3", name: "Fernanda Lima", email: "fernanda.lima@gmail.com" }, revoked_at: null },
        { id: "i4", email: "gone@uni.edu", orcid: null, level: "read", created_at: "2026-09-26T10:00:00+00:00", accepted_at: null, accepted_by: null, revoked_at: "2026-09-27T10:00:00+00:00" },
    ],
    anonymous_links: [],
    tenancy: null,
};

function renderList(overrides: any = {}, handlers: any = {}) {
    render(<AccessList
        state={{ ...state, ...overrides }}
        embargoActive
        onChangeLevel={handlers.onChangeLevel ?? jest.fn()}
        onRemove={handlers.onRemove ?? jest.fn()}
        onRevokeInvitation={handlers.onRevokeInvitation ?? jest.fn()}
    />);
}

describe("AccessList", () => {
    test("the owner, then each person with when they were added", () => {
        renderList();

        expect(screen.getByText("Luciana Rizzo")).toBeTruthy();
        expect(screen.getByText("Owner")).toBeTruthy();
        expect(screen.getByText("alan.calheiros@inpe.br · added Sep 9")).toBeTruthy();
    });

    test("someone who came through an invitation says which address it was sent to", () => {
        renderList();

        expect(screen.getByText("fernanda.lima@gmail.com · accepted the invitation sent to fernanda@inpe.br")).toBeTruthy();
    });

    test("pending invitations say whether DataMap sent them", () => {
        renderList();

        expect(screen.getByText("Invited Sep 28 · pending · email sent")).toBeTruthy();
        expect(screen.getByText("ORCID 0000-0002-1825-0097")).toBeTruthy();
        expect(screen.getByText("Invited Sep 30 · pending · link shown once, not sent by DataMap")).toBeTruthy();
    });

    test("accepted and revoked invitations are not listed again", () => {
        renderList();

        expect(screen.queryByText("gone@uni.edu")).toBeNull();
        expect(screen.queryByText("fernanda@inpe.br")).toBeNull();
    });

    test("the level menu changes a level and removes access", () => {
        const onChangeLevel = jest.fn();
        const onRemove = jest.fn();
        renderList({}, { onChangeLevel, onRemove });

        fireEvent.change(screen.getByLabelText("Access for Alan Calheiros"), { target: { value: "read" } });
        fireEvent.change(screen.getByLabelText("Access for Fernanda Lima"), { target: { value: "remove" } });

        expect(onChangeLevel).toHaveBeenCalledWith("u2", "read");
        expect(onRemove).toHaveBeenCalledWith(state.permissions[1]);
    });

    test("a pending invitation is revoked", () => {
        const onRevokeInvitation = jest.fn();
        renderList({}, { onRevokeInvitation });

        fireEvent.click(screen.getByRole("button", { name: "Revoke invitation for maria.oliveira@inpe.br" }));

        expect(onRevokeInvitation).toHaveBeenCalledWith("i1");
    });

    test("without an embargo the workspace is the first row", () => {
        renderList({ tenancy: { name: "Data Amazon", path: "datamap/production/data-amazon", members: 14 } });

        expect(screen.getByText("Members of Data Amazon")).toBeTruthy();
        expect(screen.getByText("14 people · workspace default")).toBeTruthy();
    });
});
```

`components/Share/__tests__/AnonymousLinksSection.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { beforeEach, describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react';
import { AnonymousLinksSection } from "../AnonymousLinksSection";

const links: any = [
    { id: "r1", label: "JGR Atmospheres, round 1", token_hint: "9f2c…a71e", created_at: "2026-09-14T10:00:00+00:00", revoked_at: null, views: { count: 12, first_at: "2026-09-16T10:00:00+00:00", last_at: "2026-09-30T10:00:00+00:00" } },
    { id: "r2", label: "AGU Fall Meeting abstract", token_hint: "b04d…c3e8", created_at: "2026-09-26T10:00:00+00:00", revoked_at: null, views: { count: 0, first_at: null, last_at: null } },
    { id: "r3", label: "Old", token_hint: null, created_at: "2026-09-01T10:00:00+00:00", revoked_at: "2026-09-02T10:00:00+00:00", views: { count: 1, first_at: null, last_at: null } },
];

beforeEach(() => {
    jest.useFakeTimers({ now: new Date("2026-10-01T10:00:00Z") });
});

describe("AnonymousLinksSection", () => {
    test("each link shows its label, a hint of its URL, its use and its views", () => {
        render(<AnonymousLinksSection links={links} onNew={jest.fn()} onRevoke={jest.fn()} />);

        expect(screen.getByText("JGR Atmospheres, round 1")).toBeTruthy();
        expect(screen.getByText("/anonymous/9f2c…a71e")).toBeTruthy();
        expect(screen.getByText("Created Sep 14 · first opened Sep 16 · last opened yesterday")).toBeTruthy();
        expect(screen.getByText("Created Sep 26 · not opened yet")).toBeTruthy();
        expect(screen.getByLabelText("12 views")).toBeTruthy();
        expect(screen.queryByText("Old")).toBeNull();
    });

    test("states what an anonymous link is", () => {
        render(<AnonymousLinksSection links={[]} onNew={jest.fn()} onRevoke={jest.fn()} />);

        expect(screen.getByText("Metadata only, authors redacted · anyone with the link, no account · works until the dataset is published · the full URL is shown once, at creation")).toBeTruthy();
    });

    test("new and revoke", () => {
        const onNew = jest.fn();
        const onRevoke = jest.fn();
        render(<AnonymousLinksSection links={links} onNew={onNew} onRevoke={onRevoke} />);

        fireEvent.click(screen.getByRole("button", { name: "New anonymous link" }));
        fireEvent.click(screen.getByRole("button", { name: "Revoke JGR Atmospheres, round 1" }));

        expect(onNew).toHaveBeenCalled();
        expect(onRevoke).toHaveBeenCalledWith("r1");
    });
});
```

`components/Share/__tests__/ShareDialog.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const grantAccess = jest.fn() as any;
const createAnonymousLink = jest.fn() as any;
const revokePermission = jest.fn() as any;
const searchShareCandidates = jest.fn() as any;
const mutate = jest.fn();
let shareState: any;

jest.mock("../../../gateways/BFFAPI", () => ({
    BFFAPI: jest.fn().mockImplementation(() => ({ grantAccess, createAnonymousLink, revokePermission, searchShareCandidates })),
}));
jest.mock("swr", () => ({
    __esModule: true,
    default: () => ({ data: shareState, error: undefined, mutate }),
}));
jest.mock("next-auth/react", () => ({ useSession: () => ({ data: null }) }));

import { ShareDialog } from "../ShareDialog";

const embargoed: any = { id: "d1", name: "GoAmazon 2014/5", tenancy: "datamap/production/data-amazon", embargo: { active: true, until: "2026-12-15T23:59:59+00:00" } };
const open: any = { id: "d2", name: "Manaus Radar Reflectivity 2023", tenancy: "datamap/production/data-amazon", embargo: null };

function stateWith(overrides: any = {}) {
    return {
        owner: { id: "o", name: "Luciana Rizzo", email: "luciana.rizzo@usp.br" },
        permissions: [{ user: { id: "u2", name: "Alan Calheiros", email: "alan@inpe.br" }, level: "write", granted_at: "2026-09-09T10:00:00+00:00", granted_by: "o", invited_as: null }],
        invitations: [],
        anonymous_links: [],
        tenancy: null,
        ...overrides,
    };
}

describe("ShareDialog", () => {
    test("under embargo: anonymous links, and the footer says access continues", () => {
        shareState = stateWith();
        render(<ShareDialog dataset={embargoed} show onClose={jest.fn()} />);

        expect(screen.getByRole("dialog", { name: "Share" })).toBeTruthy();
        expect(screen.getByText("GoAmazon 2014/5")).toBeTruthy();
        expect(screen.getByText("Anonymous links")).toBeTruthy();
        expect(screen.getByText("Access continues after the embargo ends")).toBeTruthy();
    });

    test("without an embargo: no anonymous links, and the footer says when they exist", () => {
        shareState = stateWith({ tenancy: { name: "Data Amazon", path: "x", members: 14 } });
        render(<ShareDialog dataset={open} show onClose={jest.fn()} />);

        expect(screen.getByText("Manaus Radar Reflectivity 2023 · not under embargo")).toBeTruthy();
        expect(screen.queryByText("Anonymous links")).toBeNull();
        expect(screen.getByText("Anonymous links are available under embargo")).toBeTruthy();
    });

    test("an ORCID invitation shows its link once", async () => {
        shareState = stateWith();
        grantAccess.mockResolvedValue({ kind: "invitation", invitation: { id: "i1", email: null }, link: "https://datamap.pcs.usp.br/invitations/tok" });
        render(<ShareDialog dataset={embargoed} show onClose={jest.fn()} />);

        fireEvent.change(screen.getByLabelText("Add people by name, email or ORCID"), { target: { value: "0000-0002-1825-0097" } });
        fireEvent.click(screen.getByRole("button", { name: /Invite ORCID/ }));

        expect(await screen.findByText("Copy the link now")).toBeTruthy();
        expect(screen.getByDisplayValue("https://datamap.pcs.usp.br/invitations/tok")).toBeTruthy();
        await waitFor(() => expect(mutate).toHaveBeenCalled());
    });

    test("an emailed invitation needs no link to copy", async () => {
        shareState = stateWith();
        grantAccess.mockResolvedValue({ kind: "invitation", invitation: { id: "i1", email: "joao@inpe.br" }, link: "https://datamap.pcs.usp.br/invitations/tok" });
        render(<ShareDialog dataset={embargoed} show onClose={jest.fn()} />);

        fireEvent.change(screen.getByLabelText("Add people by name, email or ORCID"), { target: { value: "joao@inpe.br" } });
        fireEvent.click(screen.getByRole("button", { name: /Invite joao@inpe.br/ }));

        await waitFor(() => expect(mutate).toHaveBeenCalled());
        expect(screen.queryByText("Copy the link now")).toBeNull();
    });

    test("a new anonymous link warns about free text, then is shown once", async () => {
        shareState = stateWith();
        createAnonymousLink.mockResolvedValue({ id: "r1", link: "https://datamap.pcs.usp.br/anonymous/tok" });
        render(<ShareDialog dataset={embargoed} show onClose={jest.fn()} />);

        fireEvent.click(screen.getByRole("button", { name: "New anonymous link" }));
        expect(screen.getByText("Free text isn't redacted — check the description for names.")).toBeTruthy();
        fireEvent.change(screen.getByLabelText(/Label/), { target: { value: "JGR Atmospheres, round 2" } });
        fireEvent.click(screen.getByRole("button", { name: "Create link" }));

        await waitFor(() => expect(createAnonymousLink).toHaveBeenCalledWith("d1", "JGR Atmospheres, round 2"));
        expect(await screen.findByDisplayValue("https://datamap.pcs.usp.br/anonymous/tok")).toBeTruthy();
        expect(screen.getByText("Works until the dataset is published, then leads to the public page · view count shown in Share, viewers stay anonymous")).toBeTruthy();
    });

    test("removing access asks first and says what happens", async () => {
        shareState = stateWith();
        revokePermission.mockResolvedValue(undefined);
        render(<ShareDialog dataset={embargoed} show onClose={jest.fn()} />);

        fireEvent.change(screen.getByLabelText("Access for Alan Calheiros"), { target: { value: "remove" } });
        expect(screen.getByText("Existing download links expire within 1 hour")).toBeTruthy();
        expect(screen.getByText("No notification is sent")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Remove access" }));

        await waitFor(() => expect(revokePermission).toHaveBeenCalledWith("d1", "u2"));
    });

    test("a refusal is shown in words", async () => {
        shareState = stateWith();
        grantAccess.mockRejectedValue({ httpCode: 400, errors: [{ code: "already_has_access" }] });
        render(<ShareDialog dataset={embargoed} show onClose={jest.fn()} />);

        fireEvent.change(screen.getByLabelText("Add people by name, email or ORCID"), { target: { value: "joao@inpe.br" } });
        fireEvent.click(screen.getByRole("button", { name: /Invite joao@inpe.br/ }));

        expect(await screen.findByText("This person already has access.")).toBeTruthy();
    });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest components/Share/__tests__`
Expected: FAIL — the component modules do not exist.

- [ ] **Step 3: Implement**

`MaterialSymbol` renders its icon name as text, which would become part of a button's accessible name ("add_link New anonymous link"); every button that carries an icon therefore has an `aria-label`. Rows are `grid-cols-[32px_minmax(0,1fr)_auto]` with a 32 px avatar, as in the design; the owner's avatar is near-black, everyone else's the mint `secondary-900` (#d7e4e3), a pending invitation's a dashed outline. The level is a borderless select reading "Can read" / "Can write", whose last option removes access — the design shows no separate remove control. The dialog has its own frame rather than `PopupModal`, because the design puts the dataset name under the title and a sentence beside the Done button; the confirmations (§1d) and the two link dialogs (§1c) do use `PopupModal`.

`hooks/UseDebouncedValue.ts`:

```ts
import { useEffect, useState } from "react";

export function useDebouncedValue<T>(value: T, delayMs: number): T {
    const [debounced, setDebounced] = useState(value);

    useEffect(() => {
        const id = setTimeout(() => setDebounced(value), delayMs);
        return () => clearTimeout(id);
    }, [value, delayMs]);

    return debounced;
}
```

`contants/ShareConstants.ts`:

```ts
export const SHARE_SECTION_LABEL_CLASS = "m-0 text-[11px] leading-4 font-semibold uppercase tracking-[0.08em] text-primary-500";

export const SHARE_ROW_CLASS = "grid grid-cols-[32px_minmax(0,1fr)_auto] gap-3 items-center py-2";

export const SHARE_PERSON_NAME_CLASS = "text-sm font-medium text-primary-900 truncate";

export const SHARE_PERSON_DETAIL_CLASS = "text-xs text-primary-500 truncate";

export const SHARE_DANGER_ACTION_CLASS = "text-[13px] font-medium text-danger-700 hover:underline underline-offset-2";

export const SHARE_LEVEL_LABELS: Record<string, string> = { read: "Can read", write: "Can write" };
```

`components/Share/PersonInitial.tsx`:

```tsx
import { MaterialSymbol } from "react-material-symbols";
import { initialsOf } from "../../lib/embargoDisplay";

interface Props {
    name?: string | null
    owner?: boolean
    pendingIcon?: "mail" | "badge"
}

export function PersonInitial(props: Props) {
    if (props.pendingIcon) {
        return (
            <span aria-hidden="true" className="flex flex-none items-center justify-center h-8 w-8 rounded-full border border-dashed border-primary-400 bg-primary-0 text-primary-500">
                <MaterialSymbol icon={props.pendingIcon} size={16} grade={-25} weight={400} />
            </span>
        );
    }
    const colours = props.owner ? "bg-primary-900 text-primary-50" : "bg-secondary-900 text-primary-900";
    return (
        <span aria-hidden="true" className={`flex flex-none items-center justify-center h-8 w-8 rounded-full text-xs font-semibold ${colours}`}>
            {initialsOf(props.name ?? "")}
        </span>
    );
}
```

`components/Share/ShareInput.tsx` — §1c "Share typing":

```tsx
import { useEffect, useState } from "react";
import { MaterialSymbol } from "react-material-symbols";
import { SHARE_PERSON_DETAIL_CLASS, SHARE_PERSON_NAME_CLASS } from "../../contants/ShareConstants";
import { BFFAPI } from "../../gateways/BFFAPI";
import { useDebouncedValue } from "../../hooks/UseDebouncedValue";
import { classifyShareInput } from "../../lib/shareTarget";
import { GrantRequest, PermissionLevel, ShareUser } from "../../types/GatekeeperAPI";
import { PersonInitial } from "./PersonInitial";

interface Props {
    datasetId: string
    tenancyName: string
    onGrant(request: GrantRequest): Promise<void>
}

function Highlighted(props: { name: string, typed: string }) {
    const start = props.name.toLowerCase().indexOf(props.typed.toLowerCase());
    if (start < 0 || !props.typed) {
        return <>{props.name}</>;
    }
    const end = start + props.typed.length;
    return <>{props.name.slice(0, start)}<strong className="font-bold">{props.name.slice(start, end)}</strong>{props.name.slice(end)}</>;
}

export function ShareInput(props: Props) {
    const [bffGateway] = useState(() => new BFFAPI());
    const [text, setText] = useState("");
    const [level, setLevel] = useState<PermissionLevel>("read");
    const [suggestions, setSuggestions] = useState<ShareUser[]>([]);
    const debounced = useDebouncedValue(text, 300);
    const target = classifyShareInput(text);

    useEffect(() => {
        const settled = classifyShareInput(debounced);
        if (settled.kind !== "text" || settled.value.length < 2) {
            setSuggestions([]);
            return;
        }
        let cancelled = false;
        bffGateway.searchShareCandidates(props.datasetId, settled.value)
            .then((users) => { if (!cancelled) setSuggestions(users); })
            .catch(() => { if (!cancelled) setSuggestions([]); });
        return () => { cancelled = true; };
    }, [debounced, props.datasetId, bffGateway]);

    async function grant(request: GrantRequest) {
        await props.onGrant(request);
        setText("");
        setSuggestions([]);
    }

    const panel = "mt-1.5 w-full max-w-[460px] rounded-lg border border-primary-200 bg-primary-0 shadow-lg shadow-primary-900/10 overflow-hidden";
    const option = "grid grid-cols-[32px_minmax(0,1fr)] gap-3 items-center w-full px-3.5 py-2.5 text-left hover:bg-primary-100";

    return (
        <div className="relative">
            <div className="flex gap-2">
                <div className={`flex flex-1 items-center gap-2.5 h-11 px-3.5 rounded-md border bg-primary-0 ${text ? "border-primary-900" : "border-primary-300"}`}>
                    <MaterialSymbol icon="person_add" size={20} grade={-25} weight={400} className="text-primary-400" />
                    <input
                        aria-label="Add people by name, email or ORCID"
                        type="text"
                        autoComplete="off"
                        className="w-full h-full p-0 border-0 bg-transparent text-sm text-primary-900 placeholder:text-primary-400 focus:outline-none focus:ring-0"
                        placeholder="Add people by name, email or ORCID"
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                    />
                </div>
                <select
                    aria-label="Access level"
                    className="h-11 w-auto flex-none rounded-md border border-primary-300 bg-primary-0 pl-3 pr-8 text-sm font-medium text-primary-900"
                    value={level}
                    onChange={(e) => setLevel(e.target.value as PermissionLevel)}
                >
                    <option value="read">Can read</option>
                    <option value="write">Can write</option>
                </select>
            </div>

            {target.kind === "invalid_orcid" &&
                <div role="alert" className="mt-1.5 grid grid-cols-[32px_minmax(0,1fr)] gap-3 items-center max-w-[460px] rounded-lg border border-danger-200 bg-danger-50 px-3.5 py-2.5">
                    <MaterialSymbol icon="error" size={18} grade={-25} weight={400} className="justify-self-center text-danger-700" />
                    <span className="flex flex-col">
                        <span className="text-sm font-medium text-danger-700">{target.value} isn&apos;t a valid ORCID</span>
                        <span className="text-xs text-danger-800">The last digit doesn&apos;t check out. Compare it with the person&apos;s ORCID page.</span>
                    </span>
                </div>
            }

            {(target.kind === "email" || target.kind === "orcid") &&
                <div className={panel}>
                    <button
                        type="button"
                        className={option}
                        onClick={() => grant(target.kind === "email" ? { email: target.value, level } : { orcid: target.value, level })}
                    >
                        <PersonInitial pendingIcon={target.kind === "email" ? "mail" : "badge"} />
                        <span className="flex flex-col min-w-0">
                            <span className={SHARE_PERSON_NAME_CLASS}>Invite {target.kind === "email" ? target.value : `ORCID ${target.value}`}</span>
                            <span className={SHARE_PERSON_DETAIL_CLASS}>
                                {target.kind === "email"
                                    ? "If they have no account yet, they'll get an email with a link"
                                    : "If no account has this ORCID, you'll get a link to send them"}
                            </span>
                        </span>
                    </button>
                </div>
            }

            {target.kind === "text" && suggestions.length > 0 &&
                <div className={panel}>
                    <ul className="m-0 p-0 list-none">
                        {suggestions.map((user) => (
                            <li key={user.id}>
                                <button type="button" aria-label={`${user.name} ${user.email}`} className={option} onClick={() => grant({ user_id: user.id, level })}>
                                    <PersonInitial name={user.name} />
                                    <span className="flex flex-col min-w-0">
                                        <span className={SHARE_PERSON_NAME_CLASS}><Highlighted name={user.name} typed={text.trim()} /></span>
                                        <span className={SHARE_PERSON_DETAIL_CLASS}>{user.email}</span>
                                    </span>
                                </button>
                            </li>
                        ))}
                    </ul>
                    <p className="m-0 px-3.5 py-2 border-t border-primary-100 text-xs text-primary-500">
                        Someone outside {props.tenancyName}? Type their full email or ORCID.
                    </p>
                </div>
            }
        </div>
    );
}
```

The invite rows say "If they have no account yet…" where the design says "No account yet": whether the address has an account is known only after the gatekeeper answers (a permission or an invitation), and searching outside the tenancy is deliberately not offered (RFC §Sharing).

`components/Share/AccessList.tsx` — §1c "Who has access":

```tsx
import { MaterialSymbol } from "react-material-symbols";
import {
    SHARE_DANGER_ACTION_CLASS,
    SHARE_LEVEL_LABELS,
    SHARE_PERSON_DETAIL_CLASS,
    SHARE_PERSON_NAME_CLASS,
    SHARE_ROW_CLASS,
    SHARE_SECTION_LABEL_CLASS,
} from "../../contants/ShareConstants";
import { formatShortDate } from "../../lib/embargoDisplay";
import { PermissionLevel, SharePermission, ShareState } from "../../types/GatekeeperAPI";
import { PersonInitial } from "./PersonInitial";

interface Props {
    state: ShareState
    embargoActive: boolean
    me?: string
    onChangeLevel(userId: string, level: PermissionLevel): void
    onRemove(permission: SharePermission): void
    onRevokeInvitation(invitationId: string): void
}

function permissionDetail(permission: SharePermission): string {
    if (permission.invited_as && permission.invited_as !== permission.user.email) {
        return `${permission.user.email} · accepted the invitation sent to ${permission.invited_as}`;
    }
    return `${permission.user.email} · added ${formatShortDate(permission.granted_at, false)}`;
}

export function AccessList(props: Props) {
    const pending = props.state.invitations.filter((invitation) => !invitation.revoked_at && !invitation.accepted_at);
    const owner = props.state.owner;

    return (
        <section className="flex flex-col gap-1" aria-labelledby="access-list-title">
            <h4 id="access-list-title" className={`${SHARE_SECTION_LABEL_CLASS} pb-1.5`}>Who has access</h4>
            <ul className="m-0 p-0 list-none">
                {props.state.tenancy &&
                    <li className={SHARE_ROW_CLASS}>
                        <span aria-hidden="true" className="flex items-center justify-center h-8 w-8 rounded-full bg-secondary-500 text-primary-900">
                            <MaterialSymbol icon="groups" size={18} grade={-25} weight={400} />
                        </span>
                        <span className="flex flex-col min-w-0">
                            <span className={SHARE_PERSON_NAME_CLASS}>Members of {props.state.tenancy.name}</span>
                            <span className={SHARE_PERSON_DETAIL_CLASS}>{props.state.tenancy.members} people · workspace default</span>
                        </span>
                        <span className="text-[13px] font-medium text-primary-500">Can read</span>
                    </li>
                }

                <li className={SHARE_ROW_CLASS}>
                    <PersonInitial name={owner.name} owner />
                    <span className="flex flex-col min-w-0">
                        <span className={SHARE_PERSON_NAME_CLASS}>{owner.name}{props.me === owner.id ? " (you)" : ""}</span>
                        <span className={SHARE_PERSON_DETAIL_CLASS}>{owner.email}</span>
                    </span>
                    <span className="text-[13px] font-medium text-primary-500">Owner</span>
                </li>

                {props.state.permissions.map((permission) => (
                    <li key={permission.user.id} className={SHARE_ROW_CLASS}>
                        <PersonInitial name={permission.user.name} />
                        <span className="flex flex-col min-w-0">
                            <span className={SHARE_PERSON_NAME_CLASS}>{permission.user.name}{props.me === permission.user.id ? " (you)" : ""}</span>
                            <span className={SHARE_PERSON_DETAIL_CLASS}>{permissionDetail(permission)}</span>
                        </span>
                        <select
                            aria-label={`Access for ${permission.user.name}`}
                            className="w-auto h-8 border-0 bg-transparent pl-1 pr-7 text-[13px] font-medium text-primary-900 focus:ring-0"
                            value={permission.level}
                            onChange={(e) => e.target.value === "remove"
                                ? props.onRemove(permission)
                                : props.onChangeLevel(permission.user.id, e.target.value as PermissionLevel)}
                        >
                            <option value="read">{SHARE_LEVEL_LABELS.read}</option>
                            <option value="write">{SHARE_LEVEL_LABELS.write}</option>
                            <option value="remove">Remove access</option>
                        </select>
                    </li>
                ))}

                {pending.map((invitation) => {
                    const who = invitation.email ?? `ORCID ${invitation.orcid}`;
                    const how = invitation.email ? "email sent" : "link shown once, not sent by DataMap";
                    return (
                        <li key={invitation.id} className={SHARE_ROW_CLASS}>
                            <PersonInitial pendingIcon={invitation.email ? "mail" : "badge"} />
                            <span className="flex flex-col min-w-0">
                                <span className={SHARE_PERSON_NAME_CLASS}>{who}</span>
                                <span className={SHARE_PERSON_DETAIL_CLASS}>Invited {formatShortDate(invitation.created_at, false)} · pending · {how}</span>
                            </span>
                            <button
                                type="button"
                                aria-label={`Revoke invitation for ${who}`}
                                className={SHARE_DANGER_ACTION_CLASS}
                                onClick={() => props.onRevokeInvitation(invitation.id)}
                            >
                                Revoke
                            </button>
                        </li>
                    );
                })}
            </ul>
        </section>
    );
}
```

`components/Share/AnonymousLinksSection.tsx` — §1c "Anonymous links":

```tsx
import { MaterialSymbol } from "react-material-symbols";
import { SHARE_DANGER_ACTION_CLASS, SHARE_PERSON_DETAIL_CLASS, SHARE_ROW_CLASS, SHARE_SECTION_LABEL_CLASS } from "../../contants/ShareConstants";
import { describeLinkStats } from "../../lib/embargoDisplay";
import { AnonymousLink } from "../../types/GatekeeperAPI";

interface Props {
    links: AnonymousLink[]
    onNew(): void
    onRevoke(linkId: string): void
}

export function AnonymousLinksSection(props: Props) {
    const now = new Date();
    const links = props.links.filter((link) => !link.revoked_at);

    return (
        <section className="flex flex-col gap-1" aria-labelledby="anonymous-links-title">
            <div className="flex justify-between items-center pb-2">
                <h4 id="anonymous-links-title" className={SHARE_SECTION_LABEL_CLASS}>Anonymous links</h4>
                <button
                    type="button"
                    aria-label="New anonymous link"
                    className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border border-primary-300 bg-primary-0 text-[13px] font-semibold text-primary-900 hover:bg-primary-100"
                    onClick={props.onNew}
                >
                    <MaterialSymbol icon="add_link" size={16} grade={-25} weight={400} /> New anonymous link
                </button>
            </div>
            <ul className="m-0 p-0 list-none">
                {links.map((link) => (
                    <li key={link.id} className={SHARE_ROW_CLASS}>
                        <span aria-hidden="true" className="flex items-center justify-center h-8 w-8 rounded-lg bg-embargo-100 text-embargo-800">
                            <MaterialSymbol icon="visibility_off" size={18} grade={-25} weight={400} />
                        </span>
                        <span className="flex flex-col min-w-0">
                            <span className="flex items-center gap-2 text-sm font-medium text-primary-900 min-w-0">
                                <span className="truncate">{link.label}</span>
                                {link.token_hint && <span className="font-mono text-[11px] font-normal text-primary-400 whitespace-nowrap">/anonymous/{link.token_hint}</span>}
                            </span>
                            <span className={SHARE_PERSON_DETAIL_CLASS}>{describeLinkStats(link, now)}</span>
                        </span>
                        <span className="flex items-center gap-3.5">
                            <span aria-label={`${link.views.count} views`} className="flex items-center gap-1 text-[13px] font-medium text-primary-900">
                                <MaterialSymbol icon="visibility" size={16} grade={-25} weight={400} className="text-primary-500" />
                                {link.views.count}
                            </span>
                            <button type="button" aria-label={`Revoke ${link.label}`} className={SHARE_DANGER_ACTION_CLASS} onClick={() => props.onRevoke(link.id)}>
                                Revoke
                            </button>
                        </span>
                    </li>
                ))}
            </ul>
            <p className="m-0 pt-1 text-xs leading-[18px] text-primary-500">
                Metadata only, authors redacted · anyone with the link, no account · works until the dataset is published · the full URL is shown once, at creation
            </p>
        </section>
    );
}
```

`components/Share/NewAnonymousLinkDialog.tsx` — §1c "New anonymous link":

```tsx
import { useState } from "react";
import { MaterialSymbol } from "react-material-symbols";
import { EDIT_FORM_INPUT_CLASS } from "../../contants/EditFormConstants";
import { ANONYMOUS_LINK_LABEL_MAX } from "../../contants/EmbargoConstants";
import Modal from "../base/PopupModal";

interface Props {
    show: boolean
    onCreate(label: string): Promise<void>
    onCancel(): void
}

export function NewAnonymousLinkDialog(props: Props) {
    const [label, setLabel] = useState("");

    return (
        <Modal
            title="New anonymous link"
            show={props.show}
            confimButtonText="Create link"
            cancelButtonText="Cancel"
            cancel={() => { setLabel(""); props.onCancel(); }}
            confim={async () => {
                if (label.trim()) {
                    await props.onCreate(label.trim());
                    setLabel("");
                }
            }}
            maxWidthClassName="max-w-[520px]"
        >
            <div className="flex flex-col gap-4">
                <p className="m-0 text-[13px] leading-[19px] text-primary-500">
                    Metadata only · authors, institution, references and DOI redacted. Can be used to share with publication reviewers.
                </p>
                <div className="flex flex-col gap-1.5">
                    <label htmlFor="anonymous-link-label" className="m-0 text-[13px] font-semibold text-primary-900">
                        Label <span className="font-normal text-primary-400">only you see it</span>
                    </label>
                    <input
                        id="anonymous-link-label"
                        type="text"
                        className={EDIT_FORM_INPUT_CLASS}
                        maxLength={ANONYMOUS_LINK_LABEL_MAX}
                        placeholder="JGR Atmospheres, round 2"
                        value={label}
                        onChange={(e) => setLabel(e.target.value)}
                    />
                </div>
                <div className="flex gap-2.5 items-start rounded-md bg-embargo-100 px-3 py-2.5 text-xs leading-[18px] text-embargo-800">
                    <MaterialSymbol icon="warning" size={18} grade={-25} weight={400} className="flex-none" />
                    <span>Free text isn&apos;t redacted — check the description for names.</span>
                </div>
            </div>
        </Modal>
    );
}
```

`components/Share/OneTimeLinkDialog.tsx` — §1c "Link created once", also used for an ORCID invitation's link, which DataMap cannot email:

```tsx
import { useState } from "react";
import { MaterialSymbol } from "react-material-symbols";
import Modal from "../base/PopupModal";

interface Props {
    link: string | null
    kind: "anonymous" | "invitation"
    onDone(): void
}

export function OneTimeLinkDialog(props: Props) {
    const [copied, setCopied] = useState(false);

    async function copy() {
        await navigator.clipboard?.writeText(props.link ?? "");
        setCopied(true);
    }

    return (
        <Modal
            title="Copy the link now"
            show={!!props.link}
            confimButtonText="I've copied it"
            hideCancel
            cancel={() => { setCopied(false); props.onDone(); }}
            confim={() => { setCopied(false); props.onDone(); }}
            maxWidthClassName="max-w-[520px]"
        >
            <div className="flex flex-col gap-3">
                <p className="m-0 text-[13px] leading-[19px] text-primary-500">
                    {props.kind === "anonymous"
                        ? "Shown once. If lost, create a new link and revoke this one."
                        : "Shown once. Send it to them yourself; if lost, revoke the invitation and invite them again."}
                </p>
                <div className="flex items-center rounded-md border border-primary-300">
                    <input
                        aria-label="Link"
                        readOnly
                        value={props.link ?? ""}
                        onFocus={(e) => e.target.select()}
                        className="flex-1 h-11 px-3 border-0 bg-transparent font-mono text-xs text-primary-700 truncate focus:ring-0"
                    />
                    <button type="button" aria-label="Copy" onClick={copy} className="flex items-center gap-1.5 h-11 px-3.5 border-l border-primary-300 text-[13px] font-semibold text-primary-900">
                        <MaterialSymbol icon="content_copy" size={16} grade={-25} weight={400} /> {copied ? "Copied" : "Copy"}
                    </button>
                </div>
                <p className="m-0 text-[13px] leading-[19px] text-primary-500">
                    {props.kind === "anonymous"
                        ? "Works until the dataset is published, then leads to the public page · view count shown in Share, viewers stay anonymous"
                        : "It works once, for whoever opens it; you will see which account accepted."}
                </p>
            </div>
        </Modal>
    );
}
```

`PopupModal` on `main` (8c6f761) always renders its Close/Cancel button. The design shows a single "I've copied it", so `PopupModal` gains an optional `hideCancel` — add `hideCancel?: boolean` to `ModalProps` and wrap the cancel `<button …>` in `{!props.hideCancel && (…)}`. Every existing caller leaves it unset and renders as before.

`components/Share/RemoveAccessDialog.tsx` — §1d "Revoke access":

```tsx
import Modal from "../base/PopupModal";
import { SharePermission } from "../../types/GatekeeperAPI";

interface Props {
    permission: SharePermission | null
    embargoActive: boolean
    onConfirm(permission: SharePermission): void
    onCancel(): void
}

export function RemoveAccessDialog(props: Props) {
    const permission = props.permission;

    return (
        <Modal
            title="Remove access?"
            show={!!permission}
            confimButtonText="Remove access"
            cancelButtonText="Cancel"
            destructive
            cancel={props.onCancel}
            confim={() => permission && props.onConfirm(permission)}
            maxWidthClassName="max-w-[440px]"
        >
            {permission &&
                <div className="flex flex-col gap-3">
                    <p className="m-0 text-[13px] text-primary-500">{permission.user.name} · {permission.user.email}</p>
                    <ul className="m-0 p-0 list-none flex flex-col gap-2.5 text-sm leading-[21px] text-primary-700">
                        <li className="flex gap-2.5"><span className="text-primary-400">—</span>
                            <span>{props.embargoActive ? "Existing download links expire within 1 hour" : "Download links already given out stay valid for up to 7 days"}</span>
                        </li>
                        <li className="flex gap-2.5"><span className="text-primary-400">—</span><span>No notification is sent</span></li>
                    </ul>
                </div>
            }
        </Modal>
    );
}
```

The design's "Existing download links expire within 1 hour" holds only under embargo, when links last one hour (RFC §Access rule); without one they last seven days, and the dialog says so.

`components/Share/ShareDialog.tsx` — §1c "Share dialog" and "Share without embargo":

```tsx
import { useState } from "react";
import { useSession } from "next-auth/react";
import { MaterialSymbol } from "react-material-symbols";
import useSWR from "swr";
import { messageForApiError } from "../../contants/EmbargoConstants";
import { BFFAPI } from "../../gateways/BFFAPI";
import { tenancyDisplayName } from "../../lib/embargoDisplay";
import { fetcher } from "../../lib/fetcher";
import { GetDatasetDetailsResponse } from "../../types/BffAPI";
import { GrantRequest, PermissionLevel, SharePermission, ShareState } from "../../types/GatekeeperAPI";
import { AccessList } from "./AccessList";
import { AnonymousLinksSection } from "./AnonymousLinksSection";
import { NewAnonymousLinkDialog } from "./NewAnonymousLinkDialog";
import { OneTimeLinkDialog } from "./OneTimeLinkDialog";
import { RemoveAccessDialog } from "./RemoveAccessDialog";
import { ShareInput } from "./ShareInput";

interface Props {
    dataset: GetDatasetDetailsResponse
    show: boolean
    onClose(): void
}

export function ShareDialog(props: Props) {
    const [bffGateway] = useState(() => new BFFAPI());
    const session = useSession();
    const [error, setError] = useState<string | null>(null);
    const [oneTime, setOneTime] = useState<{ link: string, kind: "anonymous" | "invitation" } | null>(null);
    const [newLink, setNewLink] = useState(false);
    const [removing, setRemoving] = useState<SharePermission | null>(null);
    const datasetId = props.dataset.id;
    const embargoActive = props.dataset.embargo?.active === true;

    const { data, error: loadError, mutate } = useSWR(props.show ? `/api/datasets/${datasetId}/share` : null, fetcher);
    const state = data as ShareState;

    if (!props.show) {
        return null;
    }

    async function run<T>(action: () => Promise<T>): Promise<T | undefined> {
        setError(null);
        try {
            const result = await action();
            await mutate();
            return result;
        } catch (e) {
            setError(messageForApiError(e));
            return undefined;
        }
    }

    async function onGrant(request: GrantRequest) {
        const result = await run(() => bffGateway.grantAccess(datasetId, request));
        if (result?.kind === "invitation" && !result.invitation.email) {
            setOneTime({ link: result.link, kind: "invitation" });
        }
    }

    return (
        <>
            <div className="fixed inset-0 z-40 bg-primary-900/40" aria-hidden="true"></div>
            <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto p-4">
                <div role="dialog" aria-modal="true" aria-labelledby="share-dialog-title" className="flex flex-col w-full max-w-[640px] max-h-[calc(100vh-2rem)] bg-primary-0 border border-primary-300 rounded-xl shadow-xl shadow-primary-900/20">
                    <div className="flex justify-between items-start gap-4 px-6 pt-5 pb-4">
                        <div className="flex flex-col gap-0.5 min-w-0">
                            <h3 id="share-dialog-title" className="m-0 text-lg font-semibold tracking-[-0.01em] text-primary-900">Share</h3>
                            <span className="text-[13px] text-primary-500 truncate">{props.dataset.name}{embargoActive ? "" : " · not under embargo"}</span>
                        </div>
                        <button type="button" aria-label="Close" onClick={props.onClose} className="text-primary-500 hover:text-primary-900">
                            <MaterialSymbol icon="close" size={20} grade={-25} weight={400} />
                        </button>
                    </div>

                    <div className="flex flex-col gap-4 px-6 pb-5 overflow-y-auto">
                        <ShareInput datasetId={datasetId} tenancyName={tenancyDisplayName(props.dataset.tenancy)} onGrant={onGrant} />
                        {error && <p role="alert" className="m-0 text-sm text-danger-700">{error}</p>}
                        {loadError && <p className="m-0 text-sm text-danger-700">The people with access could not be loaded.</p>}
                        {state &&
                            <AccessList
                                state={state}
                                embargoActive={embargoActive}
                                me={(session?.data?.user as any)?.uid}
                                onChangeLevel={(userId, level: PermissionLevel) => run(() => bffGateway.changePermissionLevel(datasetId, userId, level))}
                                onRemove={(permission) => setRemoving(permission)}
                                onRevokeInvitation={(id) => run(() => bffGateway.revokeInvitation(datasetId, id))}
                            />
                        }
                        {state && embargoActive &&
                            <div className="border-t border-primary-200 pt-4">
                                <AnonymousLinksSection
                                    links={state.anonymous_links}
                                    onNew={() => setNewLink(true)}
                                    onRevoke={(id) => run(() => bffGateway.revokeAnonymousLink(datasetId, id))}
                                />
                            </div>
                        }
                    </div>

                    <div className="flex justify-between items-center gap-4 px-6 py-3.5 border-t border-primary-200 bg-primary-50 rounded-b-xl">
                        <span className="text-xs leading-[17px] text-primary-500">
                            {embargoActive ? "Access continues after the embargo ends" : "Anonymous links are available under embargo"}
                        </span>
                        <button type="button" onClick={props.onClose} className="h-9 px-4 rounded-md bg-primary-900 text-primary-50 text-sm font-semibold hover:bg-primary-800">Done</button>
                    </div>
                </div>
            </div>

            <NewAnonymousLinkDialog
                show={newLink}
                onCancel={() => setNewLink(false)}
                onCreate={async (label) => {
                    const result = await run(() => bffGateway.createAnonymousLink(datasetId, label));
                    setNewLink(false);
                    if (result) setOneTime({ link: result.link, kind: "anonymous" });
                }}
            />
            <OneTimeLinkDialog link={oneTime?.link ?? null} kind={oneTime?.kind ?? "anonymous"} onDone={() => setOneTime(null)} />
            <RemoveAccessDialog
                permission={removing}
                embargoActive={embargoActive}
                onCancel={() => setRemoving(null)}
                onConfirm={(permission) => {
                    setRemoving(null);
                    run(() => bffGateway.revokePermission(datasetId, permission.user.id));
                }}
            />
        </>
    );
}
```

An emailed invitation's link reaches the invitee by email, so the dialog does not show it; an ORCID invitation has no address, so its link is shown once to copy (RFC §Sharing). Regenerating an invitation's link (contracts) stays available in the API; the design's list offers only Revoke, after which the author invites again.

`components/Share/ShareButton.tsx` — §1b "Share 4", the count being the people with access (owner and permissions, not pending invitations):

```tsx
import { useState } from "react";
import { MaterialSymbol } from "react-material-symbols";
import useSWR from "swr";
import { fetcher } from "../../lib/fetcher";
import { GetDatasetDetailsResponse } from "../../types/BffAPI";
import { ShareState } from "../../types/GatekeeperAPI";
import { ShareDialog } from "./ShareDialog";

export function ShareButton(props: { dataset: GetDatasetDetailsResponse }) {
    const [show, setShow] = useState(false);
    const { data } = useSWR(`/api/datasets/${props.dataset.id}/share`, fetcher);
    const people = data ? 1 + (data as ShareState).permissions.length : null;

    return (
        <>
            <button
                type="button"
                aria-label="Share"
                className="inline-flex items-center gap-2 h-[38px] px-3.5 rounded-md border border-primary-300 bg-primary-0 text-primary-900 text-sm font-semibold whitespace-nowrap hover:bg-primary-100 transition-colors"
                onClick={() => setShow(true)}
            >
                <MaterialSymbol icon="group" size={18} grade={-25} weight={400} /> Share
                {people !== null && <span className="rounded-full bg-primary-200 px-[7px] py-px text-[11px] text-primary-700">{people}</span>}
            </button>
            <ShareDialog dataset={props.dataset} show={show} onClose={() => setShow(false)} />
        </>
    );
}
```

`components/DatasetDetailsPage.tsx` — add `import { ShareButton } from "./Share/ShareButton";` and make it the first child of the header actions (`<div className="flex flex-none items-center gap-2">`, as changed in Task 8):

```tsx
              {props.dataset.access?.can_share && <ShareButton dataset={props.dataset} />}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest components/Share/__tests__`
Expected: PASS.

- [ ] **Step 5: Compare with the design**

Run `npm run dev`, open a dataset you own under embargo, then one without, and open Share. Next to `docs/design/rfc-003-embargo/Embargo Feature.dc.html` §1c (open it in a browser beside `support.js`), check: the header and footer sentences, the order of rows, the dashed avatars of pending invitations, the anonymous-link rows with their URL hint and views, the typing panel, the two link dialogs and the remove prompt.

- [ ] **Step 6: Commit**

```bash
git add hooks/UseDebouncedValue.ts contants/ShareConstants.ts components/Share/ components/DatasetDetailsPage.tsx
git commit -m "feat: share dialog with workspace search, invitations and anonymous links, as designed"
```

---

### Task 11: Anonymous page

The page is `Embargo Feature.dc.html` §1i, "Anonymous view" and "Anonymous after embargo" (`docs/design/rfc-003-embargo/`). It uses a header with only the logo and an **Anonymous view** label, with no navigation or *Sign in*. A full-width banner sits under the header: amber while the embargo lasts, mint once it has ended. A single 720 px column holds:

- the version line: `v2 · 14 files · 2.3 GB`;
- the title;
- the redaction as a visible shape: a grey `[redacted]` chip and "· 2 authors";
- *About*;
- *Files*: a count and size, "Names and downloads not available", and one chip per extension;
- *Metadata*: rows of 170 px labels, with redacted values in grey monospace.

Revoked or unknown tokens get the standard 404 (§1i note). A published dataset redirects to its public page.

**Files:**
- Create: `components/Public/BareLayout.tsx`, `lib/anonymousMetadata.ts`, `lib/anonymousPage.ts`, `components/Anonymous/AnonymousBanner.tsx`, `components/Anonymous/AnonymousFilesCard.tsx`, `components/Anonymous/AnonymousMetadataList.tsx`, `pages/anonymous/[token].tsx`
- Test: `lib/__tests__/anonymousMetadata.test.ts`, `lib/__tests__/anonymousPage.test.ts`, `components/Anonymous/__tests__/AnonymousMetadataList.test.tsx`, `components/Anonymous/__tests__/AnonymousBanner.test.tsx`, `components/Anonymous/__tests__/AnonymousFilesCard.test.tsx`

**Interfaces:**
- Consumes: `getAnonymousPage` (Task 4); `REDACTED` (Task 1); `AnonymousPageResponse`, `AnonymousPageVersion`, `FileExtensionSummary` (Task 1); `formatShortDate` (Task 3); `bytesToSize` (main, `lib/file.ts`); `Logo` (main, `components/Brand/Logo.tsx`); `ROUTE_PAGE_DATASETS_SNAPSHOTS_DETAILS` (existing).
- Produces:
  - `BareLayout({ right?, children })`: the header the pages without login share, also used by Tasks 12 and 13.
  - `displayValue(value)`, `anonymousMetadataEntries(data)`, `authorCount(data)`, `latestVersion(versions)`, `extensionLabel(extension)`.
  - `anonymousPageProps(page)`.
  - `AnonymousBanner({ page })`, `AnonymousFilesCard({ version })`, `AnonymousMetadataList({ data })`.

- [ ] **Step 1: Write the failing tests**

`lib/__tests__/anonymousMetadata.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import { anonymousMetadataEntries, authorCount, displayValue, extensionLabel, latestVersion } from "../anonymousMetadata";

describe("displayValue", () => {
    test("a redacted list keeps its length", () => {
        expect(displayValue([{ name: "[redacted]" }, { name: "[redacted]" }, { name: "[redacted]" }]))
            .toBe("[redacted] · [redacted] · [redacted]");
    });

    test("empty values read as a dash", () => {
        expect(displayValue("")).toBe("—");
        expect(displayValue(null)).toBe("—");
        expect(displayValue([])).toBe("—");
    });

    test("objects join their values", () => {
        expect(displayValue({ temporal: "1h", spatial: "1km" })).toBe("1h · 1km");
    });
});

describe("anonymousMetadataEntries", () => {
    test("in the design's order, marks redacted rows, skips the description", () => {
        const entries = anonymousMetadataEntries({
            grid_type: "regular",
            license: "CC-BY-4.0",
            description: "long text",
            institution: "[redacted]",
            authors: [{ name: "[redacted]" }, { name: "[redacted]" }],
        });

        expect(entries).toEqual([
            { key: "authors", label: "Authors", value: "[redacted] · [redacted]", redacted: true },
            { key: "institution", label: "Institution", value: "[redacted]", redacted: true },
            { key: "license", label: "License", value: "CC-BY-4.0", redacted: false },
            { key: "grid_type", label: "Grid type", value: "regular", redacted: false },
        ]);
    });
});

describe("the shape of what is hidden", () => {
    test("counts the authors without naming them", () => {
        expect(authorCount({ authors: [{ name: "[redacted]" }, { name: "[redacted]" }] })).toBe(2);
        expect(authorCount({})).toBe(0);
    });

    test("the latest version is the one with the newest creation", () => {
        const versions: any = [
            { name: "1", created_at: "2026-08-01T00:00:00Z" },
            { name: "2", created_at: "2026-09-01T00:00:00Z" },
        ];
        expect(latestVersion(versions).name).toBe("2");
        expect(latestVersion([])).toBeUndefined();
    });

    test("files without an extension are named so", () => {
        expect(extensionLabel(".nc")).toBe(".nc");
        expect(extensionLabel(null)).toBe("no extension");
    });
});
```

`lib/__tests__/anonymousPage.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import { anonymousPageProps } from "../anonymousPage";

describe("anonymousPageProps", () => {
    test("an active embargo renders the page", () => {
        const page: any = { state: "active", embargo_until: "2026-12-01T23:59:59+00:00", dataset: { name: "x", data: {}, versions: [] } };

        expect(anonymousPageProps(page)).toEqual({ props: { page } });
    });

    test("after the embargo, an unpublished dataset keeps its anonymous page", () => {
        const page: any = { state: "ended", embargo_ended_at: "2026-12-01T23:59:59+00:00", dataset: { name: "x", data: {}, versions: [] } };

        expect(anonymousPageProps(page)).toEqual({ props: { page } });
    });

    test("a published dataset redirects to its public page", () => {
        expect(anonymousPageProps({ state: "published", dataset_id: "d1" }))
            .toEqual({ redirect: { destination: "/datasets/d1", permanent: false } });
    });
});
```

`components/Anonymous/__tests__/AnonymousMetadataList.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { AnonymousMetadataList } from "../AnonymousMetadataList";

describe("AnonymousMetadataList", () => {
    test("redacted fields keep their place, in grey monospace", () => {
        render(<AnonymousMetadataList data={{ authors: [{ name: "[redacted]" }, { name: "[redacted]" }], license: "CC-BY-4.0" }} />);

        expect(screen.getByText("Authors")).toBeTruthy();
        expect(screen.getByText("[redacted] · [redacted]").className).toContain("font-mono");
        expect(screen.getByText("CC-BY-4.0").className).not.toContain("font-mono");
    });
});
```

`components/Anonymous/__tests__/AnonymousBanner.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { AnonymousBanner } from "../AnonymousBanner";

const dataset: any = { name: "x", data: {}, versions: [] };

describe("AnonymousBanner", () => {
    test("under embargo: who is reading, what is hidden, until when", () => {
        render(<AnonymousBanner page={{ state: "active", embargo_until: "2026-12-15T23:59:59+00:00", dataset }} />);

        const banner = screen.getByRole("note");
        expect(banner.textContent).toContain("You're reading this dataset as an anonymous reviewer. Authorship is redacted and the files aren't available. The dataset is under embargo until Dec 15, 2026.");
        expect(banner.className).toContain("bg-embargo-100");
    });

    test("after the embargo: where the link will lead", () => {
        render(<AnonymousBanner page={{ state: "ended", embargo_ended_at: "2026-12-15T23:59:59+00:00", dataset }} />);

        const banner = screen.getByRole("note");
        expect(banner.textContent).toContain("Anonymous view · authorship redacted, files not available. The embargo ended on Dec 15, 2026; the dataset hasn't been published yet. This link leads to the public page once it is.");
        expect(banner.className).not.toContain("embargo");
    });
});
```

`components/Anonymous/__tests__/AnonymousFilesCard.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { AnonymousFilesCard } from "../AnonymousFilesCard";

describe("AnonymousFilesCard", () => {
    test("counts and kinds, never a file name", () => {
        render(<AnonymousFilesCard version={{
            name: "2", created_at: "2026-09-01T00:00:00Z",
            files_summary: {
                count: 14, total_size_bytes: 2469606195,
                extensions: [
                    { extension: ".nc", count: 9, total_size_bytes: 2254857830 },
                    { extension: null, count: 1, total_size_bytes: 12288 },
                ],
            },
        }} />);

        expect(screen.getByText("14 files · 2.3 GB")).toBeTruthy();
        expect(screen.getByText("Names and downloads not available")).toBeTruthy();
        expect(screen.getByText(".nc")).toBeTruthy();
        expect(screen.getByText("9 · 2.1 GB")).toBeTruthy();
        expect(screen.getByText("no extension")).toBeTruthy();
        expect(screen.getByText("1 · 12.0 KB")).toBeTruthy();
    });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest lib/__tests__/anonymousMetadata.test.ts lib/__tests__/anonymousPage.test.ts components/Anonymous/__tests__`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement**

`components/Public/BareLayout.tsx` — the header of the pages a visitor reaches from a link (§1i): logo on the left, one item on the right, nothing else to wander into:

```tsx
import Head from "next/head";
import Link from "next/link";
import { ReactNode } from "react";
import { Logo } from "../Brand/Logo";

interface Props {
    right?: ReactNode
    children: ReactNode
}

export function BareLayout(props: Props) {
    return (
        <div className="min-h-screen bg-primary-50">
            <Head>
                <title>DataMap</title>
                <meta name="robots" content="noindex, nofollow" />
            </Head>
            <header className="h-16 px-4 md:px-8 flex items-center justify-between border-b border-primary-200">
                <Link href="/" className="flex items-center"><Logo size="md" /></Link>
                {props.right}
            </header>
            <main>{props.children}</main>
        </div>
    );
}
```

`lib/anonymousMetadata.ts` — the labels are listed in the order of the design's Metadata card (authors, institution, project, license, category, coverage, references); other keys follow alphabetically:

```ts
import { REDACTED } from "../contants/EmbargoConstants";
import { AnonymousPageVersion } from "../types/GatekeeperAPI";

const LABELS: Record<string, string> = {
    authors: "Authors",
    institution: "Institution",
    project: "Project",
    license: "License",
    category: "Category",
    start_date: "Start date",
    end_date: "End date",
    location: "Location",
    reference: "References",
    references: "References",
    additional_information: "Additional information",
    citation: "Citation",
    colaborators: "Collaborators",
    contacts: "Contacts",
    creation_date: "Created",
    data_type: "Data type",
    database: "Database",
    grid_type: "Grid type",
    level: "Level",
    owner: "Owner",
    realm: "Realm",
    resolution: "Resolution",
    source: "Source",
    source_instrument: "Source instrument",
    tags: "Tags",
    variables: "Variables",
};

const ORDER = Object.keys(LABELS);
const NOT_LISTED = new Set(["description", "is_enabled", "id", "name", "version"]);

export function displayValue(value: unknown): string {
    if (value === null || value === undefined || value === "") {
        return "—";
    }
    if (Array.isArray(value)) {
        return value.length === 0 ? "—" : value.map(displayValue).join(" · ");
    }
    if (typeof value === "object") {
        const parts = Object.values(value as Record<string, unknown>).map(displayValue).filter((part) => part !== "—");
        return parts.length ? parts.join(" · ") : "—";
    }
    return String(value);
}

function rank(key: string): number {
    const index = ORDER.indexOf(key);
    return index < 0 ? ORDER.length : index;
}

export function anonymousMetadataEntries(data: Record<string, unknown>): { key: string, label: string, value: string, redacted: boolean }[] {
    return Object.keys(data)
        .filter((key) => !NOT_LISTED.has(key))
        .sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
        .map((key) => {
            const value = displayValue(data[key]);
            return { key, label: LABELS[key] ?? key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()), value, redacted: value.includes(REDACTED) };
        });
}

export function authorCount(data: Record<string, unknown>): number {
    return Array.isArray(data?.authors) ? data.authors.length : 0;
}

export function latestVersion(versions: AnonymousPageVersion[]): AnonymousPageVersion | undefined {
    return [...(versions ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
}

export function extensionLabel(extension: string | null): string {
    return extension ?? "no extension";
}
```

`lib/anonymousPage.ts`:

```ts
import { ROUTE_PAGE_DATASETS_SNAPSHOTS_DETAILS } from "../contants/InternalRoutesConstants";
import { AnonymousPageResponse } from "../types/GatekeeperAPI";

export function anonymousPageProps(page: AnonymousPageResponse) {
    if (page.state === "published") {
        return { redirect: { destination: ROUTE_PAGE_DATASETS_SNAPSHOTS_DETAILS({ id: page.dataset_id }), permanent: false } };
    }
    return { props: { page } };
}
```

`components/Anonymous/AnonymousBanner.tsx` — amber is for "under embargo" only, so after the embargo the banner turns to the mint tint (`secondary-500`):

```tsx
import { MaterialSymbol } from "react-material-symbols";
import { formatShortDate } from "../../lib/embargoDisplay";
import { AnonymousPageActive, AnonymousPageEnded } from "../../types/GatekeeperAPI";

export function AnonymousBanner(props: { page: AnonymousPageActive | AnonymousPageEnded }) {
    const active = props.page.state === "active";

    return (
        <div role="note" className={`flex gap-2.5 items-start px-4 md:px-8 py-3 text-[13px] leading-[19px] ${active ? "bg-embargo-100 text-embargo-800" : "bg-secondary-500 text-primary-900"}`}>
            <MaterialSymbol icon="visibility_off" size={18} grade={-25} weight={400} className="flex-none" aria-hidden="true" />
            <span>
                {props.page.state === "active"
                    ? `You're reading this dataset as an anonymous reviewer. Authorship is redacted and the files aren't available. The dataset is under embargo until ${formatShortDate(props.page.embargo_until)}.`
                    : `Anonymous view · authorship redacted, files not available. The embargo ended on ${formatShortDate(props.page.embargo_ended_at)}; the dataset hasn't been published yet. This link leads to the public page once it is.`}
            </span>
        </div>
    );
}
```

`components/Anonymous/AnonymousFilesCard.tsx`:

```tsx
import { MaterialSymbol } from "react-material-symbols";
import { extensionLabel } from "../../lib/anonymousMetadata";
import { bytesToSize } from "../../lib/file";
import { AnonymousPageVersion } from "../../types/GatekeeperAPI";

export function AnonymousFilesCard(props: { version?: AnonymousPageVersion }) {
    const summary = props.version?.files_summary;

    return (
        <div className="rounded-lg border border-primary-200 bg-primary-0">
            <div className="flex gap-3 items-center px-4 py-3.5 border-b border-primary-100 text-sm text-primary-900">
                <MaterialSymbol icon="folder" size={20} grade={-25} weight={400} className="text-primary-500" aria-hidden="true" />
                <span className="font-semibold">{summary?.count ?? 0} files · {bytesToSize(summary?.total_size_bytes ?? 0)}</span>
                <span className="ml-auto text-xs text-primary-400">Names and downloads not available</span>
            </div>
            {(summary?.extensions ?? []).length > 0 &&
                <div className="flex flex-wrap gap-1.5 px-4 py-3">
                    {summary.extensions.map((kind) => (
                        <span key={kind.extension ?? ""} className="inline-flex items-center gap-1.5 rounded-full border border-primary-200 bg-primary-50 px-2.5 py-1 text-xs text-primary-700">
                            <span className="font-mono font-semibold">{extensionLabel(kind.extension)}</span>
                            <span className="text-primary-500">{kind.count} · {bytesToSize(kind.total_size_bytes)}</span>
                        </span>
                    ))}
                </div>
            }
        </div>
    );
}
```

`components/Anonymous/AnonymousMetadataList.tsx`:

```tsx
import { anonymousMetadataEntries } from "../../lib/anonymousMetadata";

export function AnonymousMetadataList(props: { data: Record<string, unknown> }) {
    return (
        <div className="rounded-lg border border-primary-200 bg-primary-0">
            {anonymousMetadataEntries(props.data).map((entry) => (
                <div key={entry.key} className="grid grid-cols-[120px_minmax(0,1fr)] sm:grid-cols-[170px_minmax(0,1fr)] items-center px-4 py-3 border-b border-primary-100 last:border-b-0 text-sm">
                    <span className="text-primary-500">{entry.label}</span>
                    <span className={entry.redacted ? "font-mono text-xs text-primary-700" : "text-primary-900"}>{entry.value}</span>
                </div>
            ))}
        </div>
    );
}
```

`pages/anonymous/[token].tsx`:

```tsx
import { ReactMarkdown } from "react-markdown/lib/react-markdown";
import remarkGfm from "remark-gfm";
import { AnonymousBanner } from "../../components/Anonymous/AnonymousBanner";
import { AnonymousFilesCard } from "../../components/Anonymous/AnonymousFilesCard";
import { AnonymousMetadataList } from "../../components/Anonymous/AnonymousMetadataList";
import { BareLayout } from "../../components/Public/BareLayout";
import { REDACTED } from "../../contants/EmbargoConstants";
import { authorCount, latestVersion } from "../../lib/anonymousMetadata";
import { anonymousPageProps } from "../../lib/anonymousPage";
import { bytesToSize } from "../../lib/file";
import { getAnonymousPage } from "../../lib/share";
import { AnonymousPageActive, AnonymousPageEnded } from "../../types/GatekeeperAPI";

interface Props {
    page: AnonymousPageActive | AnonymousPageEnded
}

export default function AnonymousPage(props: Props) {
    const dataset = props.page.dataset;
    const version = latestVersion(dataset.versions);
    const authors = authorCount(dataset.data);
    const description = String(dataset.data.description ?? "");

    return (
        <BareLayout right={<span className="text-xs font-semibold uppercase tracking-[0.08em] text-primary-500">Anonymous view</span>}>
            <AnonymousBanner page={props.page} />
            <div className="mx-auto w-full max-w-[720px] px-4 md:px-8 pt-8 pb-24 flex flex-col gap-7">
                <div className="flex flex-col gap-2.5">
                    {version &&
                        <span className="font-mono text-xs text-primary-500">
                            v{version.name} · {version.files_summary.count} files · {bytesToSize(version.files_summary.total_size_bytes)}
                        </span>
                    }
                    <h1 className="m-0 text-[26px] leading-[1.2] font-semibold tracking-[-0.02em] text-primary-900 [text-wrap:balance]">{dataset.name}</h1>
                    {authors > 0 &&
                        <div className="flex gap-1.5 items-center text-sm text-primary-600">
                            <span className="inline-flex px-2 py-px rounded bg-primary-200 font-mono text-xs text-primary-700">{REDACTED}</span>
                            · {authors} {authors === 1 ? "author" : "authors"}
                        </div>
                    }
                </div>

                {description &&
                    <section className="flex flex-col gap-2.5">
                        <h2 className="m-0 text-base font-semibold text-primary-900">About</h2>
                        <article className="prose max-w-none text-[15px] leading-6 text-primary-700">
                            <ReactMarkdown children={description} remarkPlugins={[remarkGfm]} />
                        </article>
                    </section>
                }

                <section className="flex flex-col gap-2.5">
                    <h2 className="m-0 text-base font-semibold text-primary-900">Files</h2>
                    <AnonymousFilesCard version={version} />
                </section>

                <section className="flex flex-col gap-2.5">
                    <h2 className="m-0 text-base font-semibold text-primary-900">Metadata</h2>
                    <AnonymousMetadataList data={dataset.data} />
                </section>
            </div>
        </BareLayout>
    );
}

export async function getServerSideProps({ query }) {
    try {
        return anonymousPageProps(await getAnonymousPage(query.token as string));
    } catch (error) {
        if (error?.response?.status === 404) {
            return { notFound: true };
        }
        throw error;
    }
}
```

The design draws the ended page with "Files and metadata as in the anonymous view above", so both states render the same sections. Only the banner differs.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/anonymousMetadata.test.ts lib/__tests__/anonymousPage.test.ts components/Anonymous/__tests__ contants/__tests__/TelemetryConstants.test.ts`
Expected: PASS.

- [ ] **Step 5: Compare with the design**

Create an anonymous link on an embargoed dataset (Task 10), open it in a private window, then end the embargo and open it again. Compare each view with §1i's "Anonymous view" and "Anonymous after embargo".

- [ ] **Step 6: Commit**

```bash
git add components/Public/ lib/anonymousMetadata.ts lib/anonymousPage.ts lib/__tests__/anonymousMetadata.test.ts lib/__tests__/anonymousPage.test.ts components/Anonymous/ "pages/anonymous/[token].tsx"
git commit -m "feat: the anonymous view, redaction shown as a shape"
```

---

### Task 12: DOI landing page

The page is `Embargo Feature.dc.html` §1i "DOI landing" (`docs/design/rfc-003-embargo/`). It uses the bare header with *Sign in* and a centred column: an amber lock in a 56 px circle, "This dataset is under embargo", the date written out in bold, the reserved identifier in monospace, and one line about DataMap with *Learn more*. "What the DOI page says is less than the DOI itself — no title, no authors, only a date." The status is read for the version the DOI names (`?version`, plan 03 Task 13), so the identifier shown is that version's own.

**Files:**
- Create: `lib/doiLanding.ts`, `components/Embargo/EmbargoNotice.tsx`, `pages/doi/datasets/[datasetId]/versions/[versionName].tsx`
- Test: `lib/__tests__/doiLanding.test.ts`, `components/Embargo/__tests__/EmbargoNotice.test.tsx`

**Interfaces:**
- Consumes: `getEmbargoStatus(datasetId, versionName)` (Task 4); `EmbargoStatusResponse` with `doi` (Task 1); `formatEmbargoDate` (Task 3); `BareLayout` (Task 11); `ROUTE_PAGE_DATASETS_VERSION_DETAILS` (existing); `loginUrlFor` (main, `lib/authRoutes.ts`).
- Produces: `doiLandingProps(status, datasetId, versionName)` → `{ props: { until, doi } } | { redirect }`; `EmbargoNotice({ until, doi })`.

- [ ] **Step 1: Write the failing tests**

`lib/__tests__/doiLanding.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import { doiLandingProps } from "../doiLanding";

describe("doiLandingProps", () => {
    test("under embargo, only the date and the identifier are shown", () => {
        expect(doiLandingProps({ embargoed: true, until: "2026-12-15T23:59:59+00:00", doi: "10.5281/datamap.3f9c1e" }, "d1", "2"))
            .toEqual({ props: { until: "2026-12-15T23:59:59+00:00", doi: "10.5281/datamap.3f9c1e" } });
    });

    test("otherwise it goes where the DOI has always led", () => {
        expect(doiLandingProps({ embargoed: false, until: null, doi: null }, "d1", "2"))
            .toEqual({ redirect: { destination: "/app/datasets/d1/versions/2", permanent: false } });
    });

    test("when the status cannot be read, it goes there too, and that page enforces access", () => {
        expect(doiLandingProps(null, "d1", "2"))
            .toEqual({ redirect: { destination: "/app/datasets/d1/versions/2", permanent: false } });
    });
});
```

`components/Embargo/__tests__/EmbargoNotice.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { EmbargoNotice } from "../EmbargoNotice";

describe("EmbargoNotice", () => {
    test("a date, a reserved identifier, and nothing about the dataset", () => {
        render(<EmbargoNotice until="2026-12-15T23:59:59+00:00" doi="10.5281/datamap.3f9c1e" />);

        const notice = screen.getByRole("status");
        expect(screen.getByRole("heading", { name: "This dataset is under embargo" })).toBeTruthy();
        expect(notice.textContent).toContain("It will become available on DataMap on December 15, 2026. The identifier below is reserved and will lead to the dataset once it is published.");
        expect(screen.getByText("doi:10.5281/datamap.3f9c1e")).toBeTruthy();
        expect(screen.getByRole("link", { name: "Learn more" }).getAttribute("href")).toBe("/project/about");
    });

    test("without an identifier, no identifier line", () => {
        render(<EmbargoNotice until="2026-12-15T23:59:59+00:00" doi={null} />);

        expect(screen.queryByText(/^doi:/)).toBeNull();
    });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest lib/__tests__/doiLanding.test.ts components/Embargo/__tests__/EmbargoNotice.test.tsx`
Expected: FAIL — `Cannot find module '../doiLanding'`, `Cannot find module '../EmbargoNotice'`.

- [ ] **Step 3: Implement**

`lib/doiLanding.ts`:

```ts
import { ROUTE_PAGE_DATASETS_VERSION_DETAILS } from "../contants/InternalRoutesConstants";
import { EmbargoStatusResponse } from "../types/GatekeeperAPI";

export function doiLandingProps(status: EmbargoStatusResponse | null, datasetId: string, versionName: string) {
    if (status?.embargoed && status.until) {
        return { props: { until: status.until, doi: status.doi ?? null } };
    }
    return {
        redirect: {
            destination: ROUTE_PAGE_DATASETS_VERSION_DETAILS({ id: datasetId, versionName }),
            permanent: false,
        },
    };
}
```

`components/Embargo/EmbargoNotice.tsx`:

```tsx
import Link from "next/link";
import { MaterialSymbol } from "react-material-symbols";
import { formatEmbargoDate } from "../../lib/embargoDates";

export function EmbargoNotice(props: { until: string, doi: string | null }) {
    return (
        <div role="status" className="mx-auto max-w-[560px] px-4 md:px-8 pt-24 pb-28 flex flex-col items-center gap-4 text-center">
            <span aria-hidden="true" className="flex items-center justify-center h-14 w-14 rounded-full bg-embargo-100 text-embargo-800">
                <MaterialSymbol icon="lock" size={28} grade={-25} weight={400} fill />
            </span>
            <h1 className="m-0 mt-2 text-[28px] leading-[1.2] font-semibold tracking-[-0.02em] text-primary-900">This dataset is under embargo</h1>
            <p className="m-0 max-w-[440px] text-base leading-[25px] text-primary-700 [text-wrap:pretty]">
                It will become available on DataMap on <strong className="font-semibold text-primary-900">{formatEmbargoDate(props.until)}</strong>.
                {" "}The identifier below is reserved and will lead to the dataset once it is published.
            </p>
            {props.doi && <span className="mt-2 font-mono text-[13px] text-primary-500">doi:{props.doi}</span>}
            <span className="mt-6 text-[13px] text-primary-400">
                DataMap is a data platform for atmospheric big data and data science research in Brazil.{" "}
                <Link href="/project/about" className="font-medium text-primary-600 hover:text-primary-900">Learn more</Link>
            </span>
        </div>
    );
}
```

The design reads "DataMap is data platform"; the page says "is a data platform".

`pages/doi/datasets/[datasetId]/versions/[versionName].tsx`:

```tsx
import Link from "next/link";
import { EmbargoNotice } from "../../../../../components/Embargo/EmbargoNotice";
import { ROUTE_PAGE_DATASETS_VERSION_DETAILS } from "../../../../../contants/InternalRoutesConstants";
import { BareLayout } from "../../../../../components/Public/BareLayout";
import { loginUrlFor } from "../../../../../lib/authRoutes";
import { doiLandingProps } from "../../../../../lib/doiLanding";
import { getEmbargoStatus } from "../../../../../lib/embargo";
import { logError } from "../../../../../lib/logging";

interface Props {
    until: string
    doi: string | null
    returnTo: string
}

export default function DoiLandingPage(props: Props) {
    return (
        <BareLayout right={<Link href={loginUrlFor(props.returnTo)} className="text-sm font-semibold text-primary-900">Sign in</Link>}>
            <EmbargoNotice until={props.until} doi={props.doi} />
        </BareLayout>
    );
}

export async function getServerSideProps({ query }) {
    const datasetId = query.datasetId as string;
    const versionName = query.versionName as string;

    let status = null;
    try {
        status = await getEmbargoStatus(datasetId, versionName);
    } catch (error) {
        logError("reading the embargo status failed", error);
    }
    const result = doiLandingProps(status, datasetId, versionName);
    if ("props" in result) {
        return { props: { ...result.props, returnTo: ROUTE_PAGE_DATASETS_VERSION_DETAILS({ id: datasetId, versionName }) } };
    }
    return result;
}
```

*Sign in* returns to the version's own page, not here: the status is read with the client's credentials, so this page would show the notice again to someone who has access. That page shows the dataset to whoever may read it and answers 404 to anyone else (Task 5).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/doiLanding.test.ts components/Embargo/__tests__/EmbargoNotice.test.tsx contants/__tests__/TelemetryConstants.test.ts`
Expected: PASS.

- [ ] **Step 5: Compare with the design**

Open `/doi/datasets/<id>/versions/<name>` for an embargoed dataset in a private window, next to §1i "DOI landing".

- [ ] **Step 6: Commit**

```bash
git add lib/doiLanding.ts lib/__tests__/doiLanding.test.ts components/Embargo/EmbargoNotice.tsx components/Embargo/__tests__/EmbargoNotice.test.tsx "pages/doi/datasets/[datasetId]/versions/[versionName].tsx"
git commit -m "feat: the DOI lands on an embargo notice while the embargo lasts"
```

---

### Task 13: Invitation page and claim on sign-in

The page is `Embargo Feature.dc.html` §1i, "Accept invitation" and "Invitation already used" (`docs/design/rfc-003-embargo/`). The invitation is shown before anything happens:

- the heading is "{inviter} shared a dataset with you", followed by what accepting does;
- rows *Dataset*, *Access* and *Invited as*;
- one button, **Accept as {the signed-in account}**;
- "Not you? Use another account. The link works once; the owner sees which account accepted."

A used link says when it was accepted and whom to ask. A revoked or unknown token gets the standard 404. The page reads the invitation through `GET /invitations/{token}` (plan 03 Task 12), with the client's credentials, so an invitation already used can be explained without signing in.

**Files:**
- Create: `lib/invitationPage.ts`, `components/Invitation/InvitationCard.tsx`, `pages/invitations/[token].tsx`
- Modify: `pages/api/auth/[...nextauth].ts`
- Test: `lib/__tests__/invitationPage.test.ts`, `components/Invitation/__tests__/InvitationCard.test.tsx`, `pages/api/auth/__tests__/[...nextauth].test.ts` (append)

**Interfaces:**
- Consumes:
  - `getInvitationPreview` (Task 4) and `InvitationPreview` (Task 1);
  - `BFFAPI.acceptInvitation` (Task 6) and `claimInvitations` (Task 4);
  - `formatShortDate` (Task 3) and `BareLayout` (Task 11);
  - `loginUrlFor` (main, `lib/authRoutes.ts`);
  - `ROUTE_PAGE_INVITATION` (Task 2) and `ROUTE_PAGE_DATASETS_DETAILS`.
- Produces: `invitationPageProps(preview, token, account)`, `InvitationCard({ token, preview, account })`, `claimPendingInvitations(uid)` (exported from `[...nextauth].ts`).

- [ ] **Step 1: Write the failing tests**

`lib/__tests__/invitationPage.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import { invitationPageProps } from "../invitationPage";

const pending: any = { state: "pending", dataset_name: "GoAmazon", inviter_name: "Luciana Rizzo", owner_name: "Luciana Rizzo", level: "read", invited_as: "fernanda@inpe.br", embargo_until: null, accepted_at: null };

describe("invitationPageProps", () => {
    test("a signed-in account sees the invitation", () => {
        expect(invitationPageProps(pending, "tok", "fernanda.lima@gmail.com"))
            .toEqual({ props: { token: "tok", preview: pending, account: "fernanda.lima@gmail.com" } });
    });

    test("anyone else signs in first and comes back to the same invitation", () => {
        const result: any = invitationPageProps(pending, "tok", null);

        expect(result.redirect.permanent).toBe(false);
        expect(result.redirect.destination).toBe("/account/login?phase=sign-in&callbackUrl=%2Finvitations%2Ftok");
    });

    test("a used invitation is explained without signing in", () => {
        const used = { ...pending, state: "accepted", accepted_at: "2026-09-29T10:00:00Z" };

        expect(invitationPageProps(used, "tok", null)).toEqual({ props: { token: "tok", preview: used, account: null } });
    });

    test("a revoked or unknown invitation is not found", () => {
        expect(invitationPageProps(null, "tok", "x@y.z")).toEqual({ notFound: true });
    });
});
```

`components/Invitation/__tests__/InvitationCard.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const acceptInvitation = jest.fn() as any;
const replace = jest.fn();

jest.mock("next-auth/react", () => ({ signOut: jest.fn() }));
jest.mock("../../../gateways/BFFAPI", () => ({
    BFFAPI: jest.fn().mockImplementation(() => ({ acceptInvitation })),
}));
jest.mock("next/router", () => ({ __esModule: true, default: { replace: (url: string) => replace(url) } }));

import { InvitationCard } from "../InvitationCard";

const pending: any = {
    state: "pending", dataset_name: "GoAmazon 2014/5 — Aerosol size distribution, T3 site",
    inviter_name: "Luciana Rizzo", owner_name: "Luciana Rizzo", level: "read",
    invited_as: "fernanda@inpe.br", embargo_until: "2026-12-15T23:59:59+00:00", accepted_at: null,
};

describe("InvitationCard", () => {
    test("shows the invitation, and accepts it only when asked", async () => {
        acceptInvitation.mockResolvedValue({ dataset_id: "d1", level: "read" });
        render(<InvitationCard token="tok" preview={pending} account="fernanda.lima@gmail.com" />);

        expect(screen.getByRole("heading", { name: "Luciana Rizzo shared a dataset with you" })).toBeTruthy();
        expect(screen.getByText("Accepting gives this account read access, now and after the embargo.")).toBeTruthy();
        expect(screen.getByText("Can read and download")).toBeTruthy();
        expect(screen.getByText("fernanda@inpe.br")).toBeTruthy();
        expect(acceptInvitation).not.toHaveBeenCalled();

        fireEvent.click(screen.getByRole("button", { name: "Accept as fernanda.lima@gmail.com" }));

        await waitFor(() => expect(replace).toHaveBeenCalledWith("/app/datasets/d1"));
        expect(acceptInvitation).toHaveBeenCalledWith("tok");
    });

    test("without an embargo, the access is simply granted", () => {
        render(<InvitationCard token="tok" preview={{ ...pending, embargo_until: null, level: "write" }} account="a@b.c" />);

        expect(screen.getByText("Accepting gives this account write access.")).toBeTruthy();
        expect(screen.getByText("Can edit and download")).toBeTruthy();
    });

    test("used: when, and whom to ask", () => {
        render(<InvitationCard token="tok" preview={{ ...pending, state: "accepted", accepted_at: "2026-09-29T10:00:00Z" }} account={null} />);

        expect(screen.getByRole("heading", { name: "This invitation was already used" })).toBeTruthy();
        expect(screen.getByRole("status").textContent).toContain("It was accepted on Sep 29, 2026. If that was you, sign in to open the dataset. If it wasn't, ask Luciana Rizzo to revoke it and send a new one.");
    });

    test("accepted by someone else meanwhile: the used message", async () => {
        acceptInvitation.mockRejectedValue({ httpCode: 409 });
        render(<InvitationCard token="tok" preview={pending} account="a@b.c" />);

        fireEvent.click(screen.getByRole("button", { name: "Accept as a@b.c" }));

        expect(await screen.findByRole("alert")).toBeTruthy();
        expect(screen.getByRole("alert").textContent).toContain("already used");
    });
});
```

Append to `pages/api/auth/__tests__/[...nextauth].test.ts` (put the `jest.mock` call at the top of the file, before the existing import; Jest hoists it anyway):

```ts
jest.mock("../../../../lib/share", () => ({ claimInvitations: jest.fn() }));

import { claimPendingInvitations } from "../[...nextauth]";
import { claimInvitations } from "../../../../lib/share";

describe('claiming pending invitations at sign-in', () => {
    test('claims for the user who signed in', async () => {
        jest.mocked(claimInvitations).mockResolvedValue({ accepted: [] });

        await claimPendingInvitations("u1");

        expect(claimInvitations).toHaveBeenCalledWith("u1");
    });

    test('a failure never blocks the sign-in', async () => {
        jest.mocked(claimInvitations).mockRejectedValue(new Error("gatekeeper down"));
        const original = process.stdout.write;
        // @ts-ignore
        process.stdout.write = () => true;
        try {
            await expect(claimPendingInvitations("u1")).resolves.toBeUndefined();
        } finally {
            process.stdout.write = original;
        }
    });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest lib/__tests__/invitationPage.test.ts components/Invitation/__tests__ "pages/api/auth/__tests__"`
Expected: FAIL — modules missing; `claimPendingInvitations` is not exported.

- [ ] **Step 3: Implement**

`lib/invitationPage.ts`:

```ts
import { ROUTE_PAGE_INVITATION } from "../contants/InternalRoutesConstants";
import { InvitationPreview } from "../types/GatekeeperAPI";
import { loginUrlFor } from "./authRoutes";

export function invitationPageProps(preview: InvitationPreview | null, token: string, account: string | null) {
    if (!preview) {
        return { notFound: true as const };
    }
    if (preview.state === "pending" && !account) {
        return { redirect: { destination: loginUrlFor(ROUTE_PAGE_INVITATION({ token })), permanent: false } };
    }
    return { props: { token, preview, account } };
}
```

`components/Invitation/InvitationCard.tsx`:

```tsx
import { signOut } from "next-auth/react";
import Link from "next/link";
import Router from "next/router";
import { useState } from "react";
import { GENERIC_ERROR_MESSAGE } from "../../contants/EmbargoConstants";
import { ROUTE_PAGE_DATASETS, ROUTE_PAGE_DATASETS_DETAILS, ROUTE_PAGE_INVITATION } from "../../contants/InternalRoutesConstants";
import { BFFAPI } from "../../gateways/BFFAPI";
import { loginUrlFor } from "../../lib/authRoutes";
import { formatShortDate } from "../../lib/embargoDisplay";
import { InvitationPreview } from "../../types/GatekeeperAPI";

interface Props {
    token: string
    preview: InvitationPreview
    account: string | null
}

const ACCESS = { read: "Can read and download", write: "Can edit and download" };

function Row(props: { label: string, children: React.ReactNode }) {
    return (
        <div className="grid grid-cols-[110px_minmax(0,1fr)] gap-3 px-4 py-3 border-b border-primary-100 last:border-b-0 text-sm">
            <span className="text-primary-500">{props.label}</span>
            <span className="text-primary-900 font-medium">{props.children}</span>
        </div>
    );
}

export function InvitationCard(props: Props) {
    const [accepting, setAccepting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const preview = props.preview;
    const here = ROUTE_PAGE_INVITATION({ token: props.token });

    if (preview.state === "accepted") {
        return (
            <div role="status" className="flex flex-col gap-3 text-center items-center">
                <h1 className="m-0 text-[26px] leading-[1.2] font-semibold tracking-[-0.02em] text-primary-900">This invitation was already used</h1>
                <p className="m-0 max-w-[440px] text-[15px] leading-6 text-primary-700">
                    It was accepted on {formatShortDate(preview.accepted_at)}. If that was you,{" "}
                    <Link href={loginUrlFor(ROUTE_PAGE_DATASETS)} className="font-medium text-primary-900 underline underline-offset-2">sign in</Link>
                    {" "}to open the dataset. If it wasn&apos;t, ask {preview.owner_name} to revoke it and send a new one.
                </p>
            </div>
        );
    }

    async function accept() {
        setAccepting(true);
        setError(null);
        try {
            const result = await new BFFAPI().acceptInvitation(props.token);
            Router.replace(ROUTE_PAGE_DATASETS_DETAILS({ id: result.dataset_id }));
        } catch (e) {
            setAccepting(false);
            if (e?.httpCode === 409) {
                setError(`This invitation was already used. If it wasn't by you, ask ${preview.owner_name} to revoke it and send a new one.`);
            } else if (e?.httpCode === 404) {
                setError(`This invitation is no longer valid. Ask ${preview.inviter_name} for a new one.`);
            } else {
                setError(GENERIC_ERROR_MESSAGE);
            }
        }
    }

    return (
        <div className="flex flex-col gap-5">
            <div className="flex flex-col gap-2">
                <h1 className="m-0 text-[26px] leading-[1.2] font-semibold tracking-[-0.02em] text-primary-900">{preview.inviter_name} shared a dataset with you</h1>
                <p className="m-0 text-[15px] leading-6 text-primary-600">
                    {preview.embargo_until
                        ? `Accepting gives this account ${preview.level} access, now and after the embargo.`
                        : `Accepting gives this account ${preview.level} access.`}
                </p>
            </div>
            <div className="rounded-lg border border-primary-200 bg-primary-0">
                <Row label="Dataset">{preview.dataset_name}</Row>
                <Row label="Access">{ACCESS[preview.level] ?? preview.level}</Row>
                <Row label="Invited as"><span className="font-mono text-[13px] font-normal">{preview.invited_as}</span></Row>
            </div>
            {error && <p role="alert" className="m-0 text-sm text-danger-700">{error}</p>}
            <button type="button" disabled={accepting} onClick={accept} className="btn-primary m-0 self-start disabled:opacity-60">
                Accept as {props.account}
            </button>
            <p className="m-0 text-[13px] leading-5 text-primary-500">
                Not you?{" "}
                <button type="button" className="font-medium text-primary-900 underline underline-offset-2" onClick={() => signOut({ callbackUrl: loginUrlFor(here) })}>Use another account.</button>
                {" "}The link works once; the owner sees which account accepted.
            </p>
        </div>
    );
}
```

The *sign in* link of a used invitation goes to the dataset list: the page does not learn the dataset's id before the visitor proves who they are.

`pages/invitations/[token].tsx`:

```tsx
import { getToken } from "next-auth/jwt";
import { InvitationCard } from "../../components/Invitation/InvitationCard";
import { BareLayout } from "../../components/Public/BareLayout";
import { invitationPageProps } from "../../lib/invitationPage";
import { getInvitationPreview } from "../../lib/share";
import { InvitationPreview } from "../../types/GatekeeperAPI";

interface Props {
    token: string
    preview: InvitationPreview
    account: string | null
}

export default function InvitationPage(props: Props) {
    return (
        <BareLayout>
            <div className="mx-auto w-full max-w-[560px] px-4 md:px-8 pt-20 pb-24">
                <InvitationCard token={props.token} preview={props.preview} account={props.account} />
            </div>
        </BareLayout>
    );
}

export async function getServerSideProps({ req, query }) {
    const token = query.token as string;
    let preview: InvitationPreview | null = null;
    try {
        preview = await getInvitationPreview(token);
    } catch (error) {
        if (error?.response?.status !== 404) {
            throw error;
        }
    }
    const session = await getToken({ req });
    const account = session?.uid ? ((session.email ?? session.name) as string) ?? null : null;
    return invitationPageProps(preview, token, account);
}
```

`pages/api/auth/[...nextauth].ts`:

1. Add `import { claimInvitations } from "../../../lib/share";`.
2. In the `jwt` callback, the `signIn` branch becomes:

```ts
      if (trigger == "signIn") {
        const user = await getUserByProviderAuthentication(account, token);
        token = hydrateWithUserInfo(token, user);
        await claimPendingInvitations(user.id);
      } else if (trigger == "update" && token.uid) {
```

3. After `hydrateWithUserInfo`, add:

```ts
export async function claimPendingInvitations(uid: string): Promise<void> {
  try {
    await claimInvitations(uid);
  } catch (error) {
    // A failed claim must not block the sign-in; the invitation link still works.
    logError("claiming pending invitations failed", error);
  }
}
```

An account signed in with ORCID has no e-mail in its token, so the button names it by its name (`session.email ?? session.name`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/invitationPage.test.ts components/Invitation/__tests__ "pages/api/auth/__tests__" contants/__tests__/TelemetryConstants.test.ts`
Expected: PASS.

- [ ] **Step 5: Compare with the design**

Invite an e-mail address you can sign in with (Task 10). Open the link signed out: it should lead to sign-in and back. Accept, then open the link again. Compare with §1i's "Accept invitation" and "Invitation already used".

- [ ] **Step 6: Commit**

```bash
git add lib/invitationPage.ts lib/__tests__/invitationPage.test.ts components/Invitation/ "pages/invitations/[token].tsx" "pages/api/auth/[...nextauth].ts" "pages/api/auth/__tests__/[...nextauth].test.ts"
git commit -m "feat: an invitation is shown before it is accepted, and claimed at sign-in"
```

---

### Task 14: A manual DOI ends the embargo, and only with consent

A manual DOI is managed outside DataMap and is usually already public at DataCite, so the gatekeeper refuses one on an embargoed dataset unless the request says `end_embargo: true` (contracts, *Embargo*). This task makes the DOI form ask first, with the two prompts of `Embargo Feature.dc.html` §1d (`docs/design/rfc-003-embargo/`): "External DOI ends the embargo" and "Register external DOI?".

**Files:**
- Modify: `types/GatekeeperAPI.ts` (`DOICreationRequest`), `types/BffAPI.ts` (`CreateDOIRequest`)
- Modify: `lib/doi.ts` (`createDOI`)
- Create: `components/Embargo/ManualDoiConfirmation.tsx`
- Modify: `components/DatasetDetails/DatasetCitation.tsx` (`CitationManualDOIForm`, `DOIManagementAlert.errorCodeMapping`)
- Test: `lib/__tests__/doi.test.ts`, `components/Embargo/__tests__/ManualDoiConfirmation.test.tsx`

**Interfaces:**
- Consumes: `manualDoiGate`, `ManualDoiGate` (Task 3); `tenancyDisplayName` (Task 3); `EMBARGO_ERROR_MESSAGES` with `embargo_manual_doi`, `embargo_manual_doi_ends_embargo` (Task 1); `SetEmbargoDialog` (Task 8).
- Produces: `CreateDOIRequest.endEmbargo?: boolean`; `DOICreationRequest.end_embargo?: boolean`; `ManualDoiConfirmation({ gate, identifier, tenancyName, show, onConfirm, onCancel, onSetEmbargo? })`.

- [ ] **Step 1: Write the failing tests**

`lib/__tests__/doi.test.ts`:

```ts
import { createDOI } from "../doi";
import axiosInstance, { buildHeaders } from "../rpc";

jest.mock("../rpc")
const mockPost = jest.mocked(axiosInstance.post)
const headers = { headers: { "X-User-Id": "u1" } };

beforeEach(() => {
    jest.mocked(buildHeaders).mockReturnValue(headers as any);
    mockPost.mockResolvedValue({ data: { identifier: "10.1000/182", mode: "manual", state: "findable" } });
});

const context = { uid: "u1", tenancy: "datamap/production/data-amazon" };

describe("createDOI", () => {
    test("a manual DOI that ends the embargo says so", async () => {
        await createDOI(context, { datasetId: "d1", versionName: "1", identifier: "10.1000/182", mode: "MANUAL", endEmbargo: true });

        expect(mockPost).toHaveBeenCalledWith("/datasets/d1/versions/1/doi", {
            mode: "MANUAL",
            identifier: "10.1000/182",
            tenancy: "datamap/production/data-amazon",
            end_embargo: true,
        }, headers);
    });

    test("otherwise the request is as before", async () => {
        await createDOI(context, { datasetId: "d1", versionName: "1", mode: "AUTO" });

        expect(mockPost).toHaveBeenCalledWith("/datasets/d1/versions/1/doi", {
            mode: "AUTO",
            identifier: undefined,
            tenancy: "datamap/production/data-amazon",
        }, headers);
    });
});
```

`components/Embargo/__tests__/ManualDoiConfirmation.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react';
import { ManualDoiConfirmation } from "../ManualDoiConfirmation";

const base = { identifier: "10.1029/2026JD041877", tenancyName: "Data Amazon", show: true };

describe("ManualDoiConfirmation", () => {
    test("under embargo, the owner is told what ends and confirms it", () => {
        const onConfirm = jest.fn();
        render(<ManualDoiConfirmation {...base} gate="ends_embargo" onConfirm={onConfirm} onCancel={jest.fn()} />);

        expect(screen.getByText("External DOI ends the embargo")).toBeTruthy();
        expect(screen.getByText("10.1029/2026JD041877 · minted outside DataMap")).toBeTruthy();
        for (const line of ["Embargo ends · can't be undone", "Files open to Data Amazon members now", "Public page published, with authors", "Anonymous links redirect to it"]) {
            expect(screen.getByText(line)).toBeTruthy();
        }
        expect(screen.getByText("To keep the embargo, generate the DOI with DataMap instead.")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "End embargo and register DOI" }));

        expect(onConfirm).toHaveBeenCalled();
    });

    test("under embargo, anyone else gets an explanation and nothing to confirm", () => {
        render(<ManualDoiConfirmation {...base} gate="owner_only" onConfirm={jest.fn()} onCancel={jest.fn()} />);

        expect(screen.getByText(/Only the owner of this dataset can end its embargo/)).toBeTruthy();
        expect(screen.queryByRole("button", { name: "End embargo and register DOI" })).toBeNull();
        expect(screen.queryByRole("button", { name: "Register DOI" })).toBeNull();
    });

    test("without an embargo, the user learns it can no longer be embargoed, and may set one first", () => {
        const onConfirm = jest.fn();
        const onSetEmbargo = jest.fn();
        render(<ManualDoiConfirmation {...base} gate="blocks_future_embargo" onConfirm={onConfirm} onCancel={jest.fn()} onSetEmbargo={onSetEmbargo} />);

        expect(screen.getByText("Register external DOI?")).toBeTruthy();
        expect(screen.getByText("After this, the dataset can no longer be put under embargo.")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Set an embargo first" }));
        expect(onSetEmbargo).toHaveBeenCalled();

        fireEvent.click(screen.getByRole("button", { name: "Register DOI" }));
        expect(onConfirm).toHaveBeenCalled();
    });

    test("someone who may not set an embargo just cancels", () => {
        const onCancel = jest.fn();
        render(<ManualDoiConfirmation {...base} gate="blocks_future_embargo" onConfirm={jest.fn()} onCancel={onCancel} />);

        expect(screen.queryByRole("button", { name: "Set an embargo first" })).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        expect(onCancel).toHaveBeenCalled();
    });

    test("cancel sends nothing", () => {
        const onConfirm = jest.fn();
        const onCancel = jest.fn();
        render(<ManualDoiConfirmation {...base} gate="ends_embargo" onConfirm={onConfirm} onCancel={onCancel} />);

        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

        expect(onCancel).toHaveBeenCalled();
        expect(onConfirm).not.toHaveBeenCalled();
    });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest lib/__tests__/doi.test.ts components/Embargo/__tests__/ManualDoiConfirmation.test.tsx`
Expected: FAIL — `end_embargo` is not sent; `Cannot find module '../ManualDoiConfirmation'`.

- [ ] **Step 3: Implement the request**

`types/GatekeeperAPI.ts`, `DOICreationRequest` becomes:

```ts
export interface DOICreationRequest {
    mode: string
    tenancy: string
    identifier?: string
    end_embargo?: boolean
}
```

`types/BffAPI.ts`, `CreateDOIRequest` becomes:

```ts
export interface CreateDOIRequest {
    datasetId: string
    versionName: string
    identifier?: string
    mode: string
    endEmbargo?: boolean
}
```

`lib/doi.ts`, in `createDOI`, the request becomes:

```ts
    const request = {
        mode: req.mode,
        identifier: req.identifier,
        tenancy: context.tenancy,
        ...(req.endEmbargo ? { end_embargo: true } : {}),
    } as DOICreationRequest;
```

`pages/api/dois/index.ts` passes `req.body` to `createDOI` unchanged, so it needs no edit.

- [ ] **Step 4: Implement the confirmation**

`components/Embargo/ManualDoiConfirmation.tsx` — the consequences are the dash list of Task 8's dialogs:

```tsx
import Modal from "../base/PopupModal";
import { ManualDoiGate } from "../../lib/embargoState";

interface Props {
    gate: ManualDoiGate
    identifier: string
    tenancyName: string
    show: boolean
    onConfirm(): void
    onCancel(): void
    onSetEmbargo?(): void
}

function Consequences(props: { items: string[] }) {
    return (
        <ul className="m-0 p-0 list-none flex flex-col gap-2.5 text-sm leading-[21px] text-primary-700">
            {props.items.map((item) => (
                <li key={item} className="flex gap-2.5"><span className="text-primary-400">—</span><span>{item}</span></li>
            ))}
        </ul>
    );
}

export function ManualDoiConfirmation(props: Props) {
    if (props.gate === "owner_only") {
        return (
            <Modal title="Only the owner can do this" show={props.show} confimButtonText="" cancelButtonText="Close" cancel={props.onCancel} maxWidthClassName="max-w-[440px]">
                <p className="m-0 text-sm leading-[21px] text-primary-700">
                    A DOI minted outside DataMap ends the embargo. Only the owner of this dataset can end its embargo.
                    To keep the embargo, generate the DOI with DataMap instead.
                </p>
            </Modal>
        );
    }

    if (props.gate === "ends_embargo") {
        return (
            <Modal
                title="External DOI ends the embargo"
                show={props.show}
                confimButtonText="End embargo and register DOI"
                cancelButtonText="Cancel"
                destructive
                cancel={props.onCancel}
                confim={props.onConfirm}
                maxWidthClassName="max-w-[440px]"
            >
                <div className="flex flex-col gap-4">
                    <p className="m-0 font-mono text-[13px] text-primary-500">{props.identifier} · minted outside DataMap</p>
                    <Consequences items={[
                        "Embargo ends · can't be undone",
                        `Files open to ${props.tenancyName} members now`,
                        "Public page published, with authors",
                        "Anonymous links redirect to it",
                    ]} />
                    <p className="m-0 text-[13px] text-primary-500">To keep the embargo, generate the DOI with DataMap instead.</p>
                </div>
            </Modal>
        );
    }

    return (
        <Modal
            title="Register external DOI?"
            show={props.show}
            confimButtonText="Register DOI"
            cancelButtonText={props.onSetEmbargo ? "Set an embargo first" : "Cancel"}
            cancel={props.onSetEmbargo ?? props.onCancel}
            confim={props.onConfirm}
            maxWidthClassName="max-w-[440px]"
        >
            <div className="flex flex-col gap-3">
                <p className="m-0 font-mono text-[13px] text-primary-500">{props.identifier}</p>
                <p className="m-0 text-sm leading-[21px] text-primary-700">After this, the dataset can no longer be put under embargo.</p>
            </div>
        </Modal>
    );
}
```

The design's second prompt has no plain *Cancel*: its secondary button is *Set an embargo first*. That button needs someone who may set an embargo (`access.can_manage_embargo`). Anyone else gets *Cancel* in its place. `PopupModal`'s close control still dismisses the prompt for everyone.

- [ ] **Step 5: Wire the DOI form**

`components/DatasetDetails/DatasetCitation.tsx`:

1. Imports: add `import Router from "next/router";`, `import { EMBARGO_ERROR_MESSAGES } from "../../contants/EmbargoConstants";`, `import { manualDoiGate } from "../../lib/embargoState";`, `import { tenancyDisplayName } from "../../lib/embargoDisplay";`, `import { ManualDoiConfirmation } from "../Embargo/ManualDoiConfirmation";`, `import { SetEmbargoDialog } from "../Embargo/SetEmbargoDialog";`.

2. In `CitationManualDOIForm`, replace the `async function onSubmit(values, { setSubmitting }) { … }` block with:

```tsx
    const gate = manualDoiGate(props.dataset);
    const [pendingIdentifier, setPendingIdentifier] = useState<string | null>(null);
    const [sending, setSending] = useState(false);
    const [settingEmbargo, setSettingEmbargo] = useState(false);

    function onSubmit(values, { setSubmitting }) {
        setSubmitting(false);
        setPendingIdentifier(values.doi.text);
    }

    async function send(identifier: string) {
        setSending(true);
        try {
            const createDOIRequest = {
                datasetId: props.dataset.id,
                versionName: getVersionByName(props.selectedVersionName, props.dataset.versions, props.dataset)?.name,
                identifier: identifier,
                mode: GetDatasetDetailsDOIResponseRegisterMode.MANUAL,
                endEmbargo: gate === "ends_embargo",
            } as CreateDOIRequest;

            const result = await bffGateway.createDOI(createDOIRequest)
            props.onManualDOICreatedWithSuccess({
                identifier: result.identifier,
                state: result.state,
                mode: result.mode,
            } as GetDatasetDetailsDOIResponse);

            if (gate === "ends_embargo") {
                Router.reload();
            }
        } catch (error) {
            props.onManualDOICreatedWithError(error);
        } finally {
            setSending(false);
            setPendingIdentifier(null);
        }
    }
```

3. Since #101 the form ends in `<EditFormActions onCancel={props.onManualDOIFormEditionCancel} isSubmitting={isSubmitting} />`; it becomes:

```tsx
                        <EditFormActions onCancel={props.onManualDOIFormEditionCancel} isSubmitting={isSubmitting || sending} />
```

4. After the closing `</Formik>` and before the closing `</div>` of `CitationManualDOIForm`'s return:

```tsx
            <ManualDoiConfirmation
                gate={gate}
                identifier={pendingIdentifier ?? ""}
                tenancyName={tenancyDisplayName(props.dataset.tenancy)}
                show={pendingIdentifier !== null}
                onConfirm={() => send(pendingIdentifier)}
                onCancel={() => setPendingIdentifier(null)}
                onSetEmbargo={props.dataset.access?.can_manage_embargo ? () => { setPendingIdentifier(null); setSettingEmbargo(true); } : undefined}
            />
            <SetEmbargoDialog dataset={props.dataset} show={settingEmbargo} onClose={() => setSettingEmbargo(false)} />
```

5. In `DOIManagementAlert.errorCodeMapping`, the `default` case becomes:

```ts
            default: return EMBARGO_ERROR_MESSAGES[code] ?? code;
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/doi.test.ts components/Embargo/__tests__ lib/__tests__/embargoState.test.ts`
Expected: PASS.

- [ ] **Step 7: Type-check the form**

Run: `npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E "DatasetCitation|ManualDoiConfirmation|lib/doi" || echo "no new type errors"`
Expected: `no new type errors`

- [ ] **Step 8: Commit**

```bash
git add types/GatekeeperAPI.ts types/BffAPI.ts lib/doi.ts lib/__tests__/doi.test.ts components/Embargo/ManualDoiConfirmation.tsx components/Embargo/__tests__/ManualDoiConfirmation.test.tsx components/DatasetDetails/DatasetCitation.tsx
git commit -m "feat: a manual DOI ends the embargo only after the owner confirms"
```

---

### Task 15: Contributors are credit only

The contributors in a dataset's metadata (`data.colaborators[]`) carried a `permission` — owner, can view, can edit — that nothing ever enforced. Under the embargo it would contradict the real access granted in the share dialog: someone listed as "Editor" would get a 404. Contributors become credit only: the form stops asking for a permission and stops showing it, and points to Share for access. Existing `permission` values stay in the JSON untouched; nothing reads them, so there is no migration.

Verified against webapp main `8c6f761` (`components/DatasetDetails/DatasetColaboratorsForm.tsx`, 185 lines).

**Files:**
- Modify: `components/DatasetDetails/DatasetColaboratorsForm.tsx`
- Test: `components/DatasetDetails/__tests__/DatasetColaboratorsForm.test.tsx`

**Interfaces:**
- Consumes: `canEditDataset(user, dataset)` (Task 8), the Share button (Task 10) that the new line points to.
- Produces: `CONTRIBUTORS_ACCESS_NOTE` exported from the form module, the sentence the form shows.

- [ ] **Step 1: Write the failing test**

`components/DatasetDetails/__tests__/DatasetColaboratorsForm.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { beforeEach, describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const updateDataset = jest.fn() as any;
jest.mock("../../../gateways/BFFAPI", () => ({
    BFFAPI: jest.fn().mockImplementation(() => ({ updateDataset })),
}));
jest.mock("../../../lib/users", () => ({ canEditDataset: () => true }));

import DatasetColaboratorsForm, { CONTRIBUTORS_ACCESS_NOTE } from "../DatasetColaboratorsForm";

function dataset(colaborators: any[]): any {
    return { id: "d1", name: "Ozone", tenancy: "t", is_enabled: true, data: { colaborators } };
}

describe("DatasetColaboratorsForm", () => {
    beforeEach(() => updateDataset.mockResolvedValue({}));

    test("lists contributors by name only, whatever permission the JSON still holds", () => {
        render(<DatasetColaboratorsForm dataset={dataset([{ name: "Ana", permission: "can_edit" }])} user={{} as any} />);

        expect(screen.getByText("Ana")).toBeTruthy();
        expect(screen.queryByText(/Editor|Viewer|Owner/)).toBeNull();
    });

    test("the form asks for a name, not a permission, and points to Share for access", () => {
        render(<DatasetColaboratorsForm dataset={dataset([{ name: "Ana" }])} user={{} as any} alwaysEdition />);

        expect(screen.getByLabelText("Name")).toBeTruthy();
        expect(screen.queryByLabelText("Permission")).toBeNull();
        expect(screen.getByText(CONTRIBUTORS_ACCESS_NOTE)).toBeTruthy();
    });

    test("a contributor with only a name is saved, and stored permissions are kept", async () => {
        const data = dataset([{ name: "Ana", permission: "owner" }]);
        render(<DatasetColaboratorsForm dataset={data} user={{} as any} alwaysEdition />);

        fireEvent.click(screen.getByText("+ Add collaborator"));
        fireEvent.change(screen.getAllByLabelText("Name")[1], { target: { value: "Bruno" } });
        fireEvent.submit(screen.getAllByLabelText("Name")[1].closest("form") as HTMLFormElement);

        await waitFor(() => expect(updateDataset).toHaveBeenCalledTimes(1));
        expect(updateDataset.mock.calls[0][0].data.colaborators).toEqual([
            { name: "Ana", permission: "owner" },
            { name: "Bruno" },
        ]);
    });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx jest components/DatasetDetails/__tests__/DatasetColaboratorsForm.test.tsx`
Expected: FAIL — `CONTRIBUTORS_ACCESS_NOTE` is undefined, the read mode shows `(Editor)`, the form has a `Permission` select, and the second contributor fails validation with `Select one`.

- [ ] **Step 3: Make contributors credit only**

In `components/DatasetDetails/DatasetColaboratorsForm.tsx`:

1. Drop `EDIT_FORM_SELECT_CLASS` from the `EditFormConstants` import, and export the note after the imports:

```tsx
import { EDIT_FORM_ERROR_CLASS, EDIT_FORM_HINT_CLASS, EDIT_FORM_INPUT_CLASS, EDIT_FORM_LABEL_CLASS, EMPTY_VALUE_CLASS } from "../../contants/EditFormConstants";
```

```tsx
export const CONTRIBUTORS_ACCESS_NOTE = "Listing someone here credits them; it does not give them access. To give someone access to this dataset, use Share.";
```

2. The schema validates the name only:

```tsx
    const schema = Yup.object().shape({
        colaborators: Yup.array()
            .of(
                Yup.object().shape({
                    name: Yup.string()
                        .max(255, "Name should be less than 255 characters")
                        .required("Name is required."),
                })
            )
    });
```

3. Delete `getPermissionDescription` entirely.

4. In the edit form, show the note under the hint:

```tsx
                                        <p className={EDIT_FORM_HINT_CLASS}>
                                            {infoText}
                                        </p>
                                        <p className={EDIT_FORM_HINT_CLASS}>
                                            {CONTRIBUTORS_ACCESS_NOTE}
                                        </p>
```

and replace each row (the `<div className="flex items-start gap-2" key={index}>` block) with the name field and the remove button only:

```tsx
                                                        <div className="flex items-start gap-2" key={index}>
                                                            <div className="min-w-0 flex-1">
                                                                <label htmlFor={`colaborators.${index}.name`} className={EDIT_FORM_LABEL_CLASS}>Name</label>
                                                                <Field
                                                                    id={`colaborators.${index}.name`}
                                                                    name={`colaborators.${index}.name`}
                                                                    className={EDIT_FORM_INPUT_CLASS}
                                                                    placeholder="Name of a contributor"
                                                                />
                                                                <ErrorMessage
                                                                    name={`colaborators.${index}.name`}
                                                                    component="div"
                                                                    className={EDIT_FORM_ERROR_CLASS}
                                                                />
                                                            </div>
                                                            <div className="pt-[26px]">
                                                                <CloseButton label="Remove collaborator" onClick={() => arrayHelpers.remove(index)} />
                                                            </div>
                                                        </div>
```

5. Read mode lists names only:

```tsx
                {props?.dataset?.data?.colaborators?.map((person, index) =>
                    <li key={index}>
                        {person.name}
                    </li>)}
```

The `permission` key of entries already stored is left in `values.colaborators` as it came, so saving the form never rewrites it.

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx jest components/DatasetDetails/__tests__/DatasetColaboratorsForm.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add components/DatasetDetails/DatasetColaboratorsForm.tsx components/DatasetDetails/__tests__/DatasetColaboratorsForm.test.tsx
git commit -m "feat: contributors are credit only; access is given through Share"
```

---

### Task 16: The images the emails show stay where they are served

The gatekeeper's email templates (`app/resources/email_templates/base.html`, gatekeeper #121) load `{site_url}/img/email/datamap-tile-36.png` in the header and `{site_url}/img/email/datamap-tile-22.png` in the footer. Webapp #101 already ships both under `public/img/email/` (72×72 and 44×44: twice the size they are shown at). Nothing in this repo refers to them, so nothing stops a later clean-up from deleting them and every email from losing its logo. This task adds that guard; it creates no image.

**Files:**
- Test: `lib/__tests__/emailImages.test.ts`

**Interfaces:**
- Produces: nothing at runtime; a test that fails if either file goes missing or changes format.

- [ ] **Step 1: Write the test**

`lib/__tests__/emailImages.test.ts`:

```ts
import { readFileSync } from "fs";
import { join } from "path";

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function png(name: string): Buffer {
    return readFileSync(join(__dirname, "..", "..", "public", "img", "email", name));
}

describe("the images the gatekeeper's emails load from the webapp", () => {
    test.each([
        ["datamap-tile-36.png", 72],
        ["datamap-tile-22.png", 44],
    ])("%s is a %ipx square PNG under public/img/email", (name, size) => {
        const bytes = png(name);

        expect(bytes.subarray(0, 8)).toEqual(PNG_SIGNATURE);
        expect(bytes.readUInt32BE(16)).toBe(size);
        expect(bytes.readUInt32BE(20)).toBe(size);
    });
});
```

- [ ] **Step 2: Run it, then prove it can fail**

Run: `npx jest lib/__tests__/emailImages.test.ts`
Expected: PASS (both files exist on main since 8c6f761).

Then make it fail once, so it is known to test something:

```bash
mv public/img/email/datamap-tile-22.png /tmp/datamap-tile-22.png
npx jest lib/__tests__/emailImages.test.ts; echo "exit=$?"
mv /tmp/datamap-tile-22.png public/img/email/datamap-tile-22.png
```

Expected: `ENOENT` for `datamap-tile-22.png` and `exit=1`; after moving it back, `git status --short public/` prints nothing.

- [ ] **Step 3: Commit**

```bash
git add lib/__tests__/emailImages.test.ts
git commit -m "test: keep the images the emails load where the webapp serves them"
```

---

### Task 17: Full verification

**Files:** none changed unless a check fails.

- [ ] **Step 1: Whole test suite**

Run: `npm run test 2>&1 | tail -30`
Expected: `Tests:` line with `0 failed`; `Test Suites:` all passed. Read the exit status separately: `npm run test >/dev/null 2>&1; echo "exit=$?"` → `exit=0`.

- [ ] **Step 2: Type-check and production build**

Run: `npm run build; echo "exit=$?"`
Expected: `exit=0`; the route list includes `/app/datasets/shared`, `/anonymous/[token]`, `/invitations/[token]`, `/doi/datasets/[datasetId]/versions/[versionName]` and the new `/api/...` routes.

- [ ] **Step 3: The images the emails load are served**

Run: `npm run start & sleep 5; for f in datamap-tile-36.png datamap-tile-22.png; do curl -s -o /dev/null -w "$f %{http_code} %{content_type}\n" http://localhost:3000/img/email/$f; done; kill %1`
Expected: `datamap-tile-36.png 200 image/png` and `datamap-tile-22.png 200 image/png`

- [ ] **Step 4: Lint**

Run: `npx next lint; echo "exit=$?"`
Expected: `exit=0` with no errors in the files this plan touched (pre-existing warnings elsewhere are acceptable; do not fix unrelated files).

- [ ] **Step 5: Manual check against a gatekeeper with plans 02 and 03**

With the gatekeeper integration stack up (`make ENV_FILE_PATH=integration-test.env integration-test-up` in the gatekeeper repo) and the webapp's `.env.local` pointing `DATAMAP_BASE_URL` at it, run `npm run dev` and walk through:

1. Create a dataset *Under embargo*, members *Don't see it at all*, a date 30 days ahead and a note → the header shows the badge; the sidebar shows the embargo card with the note (§1a, §1b).
2. Share → type a colleague's name from the tenancy → pick → they appear in the dialog and in *Who has access*.
3. Share → type an unknown email → *Invite* → the one-time link appears once.
4. Create an anonymous link → open it in a private window → the amber banner, `[redacted] · N authors`, extension chips, no file names, no download (§1i).
5. Open `/doi/datasets/<id>/versions/1` in a private window → embargo notice with the date and the identifier, no dataset name.
6. Sign in as a second account with no tenancy → *Shared with me* lists nothing; open the invitation link → the preview → *Accept as …* → redirected to the dataset. Open the link again → "This invitation was already used".
7. Extend with a reason, switch the mode, edit the note → Settings › History lists each with who and when (§1g).
8. As a tenancy member in open mode → the files section shows the withheld notice; Download is locked (§1e).
9. End early → the neutral ended banner with its checklist; the anonymous link now shows the mint banner (§1h, §1i).
10. On an embargoed dataset, register a manual DOI → "External DOI ends the embargo"; Cancel sends nothing. As a `write` collaborator, the dialog says only the owner can. Without an embargo → "Register external DOI?" with *Set an embargo first* (§1d).

Record anything that differs from the contracts in the PR description; do not change the contracts from this plan.

- [ ] **Step 6: Commit any fixes**

```bash
git status --short
git add -A && git commit -m "fix: issues found in the embargo webapp verification"
```

(Skip the commit if `git status --short` is empty.)

---

### Task 18: nginx — the DOI lands on the webapp page (gatekeeper repo)

**Deploy order:** merge and deploy the webapp with Task 12 first. Until the page exists, this change would send DOI visitors to a 404. The gatekeeper with plans 02 and 03 must be deployed too, or the page cannot read the embargo status (it then redirects as today, which is safe).

**Files (gatekeeper repo, `/Users/caio.maia/workspace/datamap/gatekeeper`, in a worktree on branch `feat/doi-landing-nginx`):**
- Modify: `infrastructure/nginx/datamap.conf:189-196`

- [ ] **Step 1: Write the check that fails today**

Create `/tmp/doi-landing-check.sh` (scratch, not committed):

```bash
#!/bin/sh
set -eu
grep -n -A6 'location ~ ^/doi/datasets/' infrastructure/nginx/datamap.conf | grep -q 'rewrite' && { echo "FAIL: /doi/ still rewritten to /app"; exit 1; }
grep -n -A6 'location ~ ^/doi/datasets/' infrastructure/nginx/datamap.conf | grep -q 'proxy_pass http://localhost:3000;' && echo "OK: /doi/ proxied to the webapp"
```

Run: `sh /tmp/doi-landing-check.sh`
Expected: `FAIL: /doi/ still rewritten to /app`

- [ ] **Step 2: Change the block**

Replace lines 189–196 of `infrastructure/nginx/datamap.conf`:

```nginx
    # doi redirection
    location ~ ^/doi/datasets/([^/]+)/versions/([^/]+) {
        rewrite ^/doi/datasets/([^/]+)/versions/([^/]+) /app/datasets/$1/versions/$2 permanent;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_pass http://localhost:3000;
    }
```

with:

```nginx
    # doi landing: a public webapp page shows the embargo notice, or redirects to /app as before
    location ~ ^/doi/datasets/([^/]+)/versions/([^/]+) {
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_pass http://localhost:3000;
    }
```

- [ ] **Step 3: Run the check and validate the syntax**

Run: `sh /tmp/doi-landing-check.sh`
Expected: `OK: /doi/ proxied to the webapp`

Validate with nginx itself, using throwaway certificates at the paths the file names:

```bash
D=$(mktemp -d)
mkdir -p "$D/live/datamap.pcs.usp.br"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=test" \
  -keyout "$D/live/datamap.pcs.usp.br/privkey.pem" -out "$D/live/datamap.pcs.usp.br/fullchain.pem" 2>/dev/null
docker run --rm \
  -v "$PWD/infrastructure/nginx/datamap.conf:/etc/nginx/conf.d/default.conf:ro" \
  -v "$D:/etc/letsencrypt:ro" \
  nginx:1.27 nginx -t
rm -rf "$D"
```

Expected: `nginx: configuration file /etc/nginx/nginx.conf test is successful`

- [ ] **Step 4: Commit**

```bash
git add infrastructure/nginx/datamap.conf
git commit -m "feat: the DOI lands on the webapp, which shows the embargo notice"
```

- [ ] **Step 5: Apply on the host (operator with sudo; the deploy user has none)**

```bash
sudo cp infrastructure/nginx/datamap.conf /etc/nginx/sites-available/datamap.conf
sudo nginx -t && sudo systemctl reload nginx
```

Verify, for a dataset without an embargo:

```bash
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" https://datamap.pcs.usp.br/doi/datasets/<dataset-id>/versions/1
```

Expected: `307 https://datamap.pcs.usp.br/app/datasets/<dataset-id>/versions/1`. For an embargoed dataset: `200`, and the body contains `This dataset is under embargo`.

---

## Self-review against the spec

| RFC / contracts / design requirement | Task |
|---|---|
| Embargo choice at creation: *Open to the workspace* / *Under embargo*, date ≤ 90 days, note, members' visibility defaulting to hidden (§1a) | 8 (`EmbargoFields`), 9 |
| Badge in the header and the list, *Shared with me* tab (§1b, §1f) | 7 |
| Embargo card: days left, end date, mode with *Change*, note, *Extend*, *End early*, per access flags (§1b) | 8 |
| Extension by permission holders when the owner is disabled | 8 (`can_extend_embargo`) |
| Extend with optional reason, End early with its consequences, Hide/Show, Note (§1d) | 8 |
| Member view: files withheld with count, size, date and whom to ask; Download locked; no New version, Settings or Share (§1e) | 8 |
| Settings: embargo rows, access summary, history from the audit trail, *Set embargo* or why not (§1g) | 8 |
| Share dialog: tenancy search, email/ORCID detection with checksum, levels, list, revoke (§1c) | 3, 10 |
| Invitation link shown once, accepted-by shown | 10 |
| Anonymous links: label, one-time link, token hint, views count/first/last, revoke (§1c) | 10 |
| Anonymous page: redaction as a shape, extension chips, never file names; after the embargo the mint banner until published, then the redirect (§1i) | 11 |
| DOI landing: date and reserved identifier only; redirect otherwise (§1i) | 12, 18 |
| Invitation page: preview before accepting, *Accept as*, *Use another account*, used state, 404 for revoked (§1i) | 13 |
| Claim pending invitations at sign-in, never blocking | 13 |
| Accounts with no tenancy: Shared with me, dataset pages, dataset BFF routes | 5, 7, 8 |
| Post-embargo banner: checklist, registered but not findable, *Make DOI findable* after confirming (§1h) | 3, 8 |
| Telemetry pages and events | 2, 6 |
| Manual DOI under embargo: the §1d prompts, `end_embargo: true`, owner only; no embargo after a manual DOI | 1, 3, 8, 14 |
| Email images at `{PUBLIC_BASE_URL}/img/email/datamap-tile-{36,22}.png` (shipped by #101; guarded here) | 16, 17 |
| Contributors are credit only; access goes through Share | 15 |
| Sharing on any dataset, embargoed or not (the Share button follows `access.can_share`, never the embargo) | 10 |

Not built, although the design draws them: the *Cite* button of §1e, the *Not published* pill of §1h, and *Delete dataset* inside Settings (§1g). The dataset page keeps main's citation section and its delete in the *More* menu. None of them is part of RFC 003.
