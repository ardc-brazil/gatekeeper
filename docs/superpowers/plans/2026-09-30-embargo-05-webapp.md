# Dataset Embargo — Webapp Implementation Plan (05)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Where the code goes.** This plan lives in the gatekeeper repo with the other embargo plans, but every file it changes is in the **webapp repo, `/Users/caio.maia/workspace/datamap/datamap-webapp`**, except Task 17, which changes `infrastructure/nginx/datamap.conf` in the **gatekeeper repo**. All paths below are relative to the webapp repo root unless a task says otherwise. Work in a git worktree of the webapp repo on branch `feat/dataset-embargo`, created from `origin/main`; never in the main checkout.

**Verified against:** webapp `main` at `8c6f761` (#101, the new DataMap identity; #100, the encrypted environment, touches nothing here). Every file this plan modifies was compared with that commit. If `main` has moved, diff the files in *File Structure* against it before starting.

**Goal:** Give the webapp everything RFC 003 asks of the user interface: embargo at creation and on the dataset page, the share dialog, reviewer links, the anonymous review page, the DOI embargo notice, invitation acceptance, a *Shared with me* list that works for an account with no tenancy, and the post-embargo banner.

**Architecture:** Server-side calls to the gatekeeper live in `lib/embargo.ts` and `lib/share.ts` (axiosInstance + buildHeaders); browser mutations go through new `BFFAPI` methods to new `pages/api` routes built on one helper, `lib/bffRoute.ts`, whose chain authenticates but does not require a tenancy. UI is split into small components under `components/Embargo`, `components/Share`, `components/Review` and `components/Invitation`, each with a jsdom test; the public pages are thin and keep their decisions in tested `lib/*` functions.

**Tech Stack:** Next.js 14 (pages router), React 18, TypeScript, next-connect, axios, SWR, Formik, TailwindCSS, react-material-symbols, Jest + Testing Library.

## Global Constraints

- Contracts: `docs/superpowers/plans/2026-09-30-embargo-00-contracts.md` (gatekeeper repo). Payload shapes, routes and error codes are copied from it verbatim; if this plan disagrees with it, the contracts file wins.
- Maximum embargo period: **90 days**, on creation and on each extension. The UI offers dates up to today + 89 days so that the end of the chosen day never exceeds the server's `now() + 90 days`.
- `until` is sent as the end of the chosen UTC day: `YYYY-MM-DDT23:59:59+00:00`.
- Redaction marker: `"[redacted]"`.
- Mutations go through `gateways/BFFAPI.ts`, which emits `trackUiEvent` after success and throws `httpErrorHandler(error)` on failure. Reads use SWR with `lib/fetcher.js`. Forms use Formik.
- Constants live in `contants/{Category}Constants.ts` (the directory is spelled `contants`).
- Visual language: the DataMap identity of webapp #101 (`8c6f761`). Near-black `primary-900` on `primary-50` ground; white cards `rounded-lg border border-primary-200 bg-primary-0`; section `h2` at `m-0 text-lg leading-snug tracking-[-0.01em]` with a `text-sm text-primary-600` subtitle; form fields from `contants/EditFormConstants.ts`; card footers `border-t border-primary-200 bg-primary-50 px-5 py-3 rounded-b-lg`; notices in the mint tint `bg-secondary-500`; pills `px-2.5 py-[3px] rounded-full text-xs leading-[18px] font-semibold`; dialogs through `components/base/PopupModal.tsx` (with `destructive` and `maxWidthClassName`). Do not use the pre-#101 patterns (`border-t-4` callouts, `h6` section titles, `font-extrabold` page titles).
- Material Symbols: `<MaterialSymbol ... grade={-25} weight={400} />`, size 14–22, as #101 uses them.
- Component tests start with `/** @jest-environment jsdom */`, live in `__tests__` next to the component, and import components by relative path (Jest does not map `@/`). Components that a test imports must not import `react-markdown` (ESM, not transformed by Jest).
- Every new page must be listed in `PAGES` (`contants/TelemetryConstants.ts`), or `contants/__tests__/TelemetryConstants.test.ts` fails.
- Comments: none narrating code. One line only where a reader would otherwise undo something on purpose.
- Every task ends green on `npx jest <the task's tests>`; Task 16 runs the whole suite and `npm run build`.

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
| `lib/reviewMetadata.ts` (create) | Turns redacted metadata into displayable rows |
| `lib/reviewPage.ts`, `lib/doiLanding.ts`, `lib/invitationPage.ts` (create) | `getServerSideProps` decisions of the three new pages |
| `lib/embargo.ts`, `lib/share.ts` (create), `lib/dataset.ts` (modify) | Server calls to the gatekeeper |
| `lib/middlewareChain.ts` (modify), `lib/bffRoute.ts` (create) | Tenancy-optional chain and the route helper |
| `lib/requestErrorHandler.ts` (modify) | 404 renders Next's not-found page instead of crashing |
| `lib/users.ts` (modify) | `canEditDataset` honours the dataset's `access` |
| `pages/api/datasets/[datasetId]/{embargo,share,review-links}/…`, `pages/api/datasets/shared.ts`, `pages/api/invitations/accept.ts` (create) | BFF routes |
| `gateways/BFFAPI.ts` (modify) | Browser methods for the new routes |
| `hooks/UseDebouncedValue.ts` (create) | Debounce for the search-as-you-type |
| `components/Embargo/*` (create) | Badge, settings, choice at creation, withheld notice, ended banner |
| `components/Share/*` (create) | Share button and dialog, input, access list, reviewer links, one-time link |
| `components/Review/ReviewMetadataList.tsx` (create) | Redacted metadata table |
| `components/Invitation/AcceptInvitation.tsx` (create) | Accepts and redirects |
| `components/LoggedLayout.tsx`, `components/DatasetDetailsPage.tsx`, `components/DatasetDetails/TabPanelSettings.tsx`, `components/DatasetDetails/DataCard/DataExplorer.tsx`, `components/Search/ListItem.tsx`, `components/Tenancy/AccessPending.tsx`, `pages/app/datasets/new.tsx`, `types/new-dataset.d.ts`, `pages/api/auth/[...nextauth].ts` (modify) | Wiring |
| `pages/app/datasets/shared.tsx`, `pages/review/[token].tsx`, `pages/doi/datasets/[datasetId]/versions/[versionName].tsx`, `pages/invitations/[token].tsx` (create) | New pages |
| `lib/doi.ts`, `components/DatasetDetails/DatasetCitation.tsx` (modify), `components/Embargo/ManualDoiConfirmation.tsx` (create) | A manual DOI ends the embargo only after confirmation |
| `lib/__tests__/emailImages.test.ts` (create) | Keeps `public/img/email/datamap-tile-{36,22}.png`, which the gatekeeper's email templates load, from being deleted |
| `contants/ShareConstants.ts`, `components/Share/PersonInitial.tsx` (create) | Share dialog row styles and the initial avatar |

## Task order and parallelism

| Task | Depends on | Can run in parallel with |
|---|---|---|
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
| 11 Review page | 2, 4 | 7, 8, 9, 10, 12 |
| 12 DOI landing page | 2, 4 | 7–11 |
| 13 Invitation page and claim on sign-in | 2, 4, 6 | 7–12 |
| 14 Manual DOI confirmation | 1, 3 | 7–13, 15 |
| 15 Guard on the email images | — | everything |
| 16 Full verification | all | — |
| 17 nginx (gatekeeper repo) | 12 deployed | — |

---

### Task 1: Types and error handling

**Files:**
- Modify: `types/GatekeeperAPI.ts` (append)
- Modify: `types/BffAPI.ts:29-52` (`GetDatasetDetailsResponse`, `GetDatasetDetailsVersionResponse`), `types/BffAPI.ts:184-202` (`GetMinimalDatasetsDetasetDetailsResponse`)
- Modify: `types/APIError.ts:1`
- Modify: `lib/rpc.ts` (`httpErrorHandler`)
- Create: `contants/EmbargoConstants.ts`
- Test: `lib/__tests__/rpc.test.ts` (append), `contants/__tests__/EmbargoConstants.test.ts`

**Interfaces:**
- Produces (TypeScript, `types/GatekeeperAPI.ts`): `PermissionLevel`, `AccessLevel`, `DatasetEmbargo`, `DatasetAccess`, `FilesSummary`, `SetEmbargoRequest`, `ExtendEmbargoRequest`, `EmbargoModeRequest`, `EmbargoStatusResponse`, `ShareUser`, `SharePermission`, `ShareInvitation`, `ReviewLinkViews`, `ReviewLink`, `CreatedReviewLink`, `ShareState`, `GrantRequest`, `GrantResult`, `ReviewPageVersion`, `ReviewPageActive`, `ReviewPageEnded`, `ReviewPageResponse`, `AcceptInvitationResponse`, `ClaimInvitationsResponse`.
- Produces (`contants/EmbargoConstants.ts`): `MAX_EMBARGO_DAYS = 90`, `REDACTED = "[redacted]"`, `REVIEW_LINK_LABEL_MAX = 256`, `EMBARGO_ERROR_MESSAGES`, `GENERIC_ERROR_MESSAGE`, `messageForApiError(error: unknown): string`.
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

export const REVIEW_LINK_LABEL_MAX = 256;

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
}

/** @interface */
export interface EmbargoModeRequest {
    metadata_visible: boolean
}

/** @interface */
export interface EmbargoStatusResponse {
    embargoed: boolean
    until: string | null
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
export interface ReviewLinkViews {
    count: number
    first_at: string | null
    last_at: string | null
}

/** @interface */
export interface ReviewLink {
    id: string
    label: string
    created_at: string
    revoked_at: string | null
    views: ReviewLinkViews
}

/** @interface */
export interface CreatedReviewLink extends ReviewLink {
    link: string
}

/** @interface */
export interface ShareState {
    owner: ShareUser
    permissions: SharePermission[]
    invitations: ShareInvitation[]
    review_links: ReviewLink[]
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
export interface ReviewPageVersion {
    name: string
    created_at: string
    files_summary: FilesSummary
}

/** @interface */
export interface ReviewPageActive {
    state: "active"
    embargo_until: string
    dataset: {
        name: string
        data: Record<string, unknown>
        versions: ReviewPageVersion[]
    }
}

/** @interface */
export interface ReviewPageEnded {
    state: "ended"
    dataset_id: string
    published: boolean
}

export type ReviewPageResponse = ReviewPageActive | ReviewPageEnded;

/** @interface */
export interface AcceptInvitationResponse {
    dataset_id: string
    level: PermissionLevel
}

/** @interface */
export interface ClaimInvitationsResponse {
    accepted: AcceptInvitationResponse[]
}
```

In `types/BffAPI.ts`, add the import at the top of the file (merge with the existing `GatekeeperAPI` import if present):

```ts
import { DatasetAccess, DatasetEmbargo, FilesSummary } from "./GatekeeperAPI";
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

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/rpc.test.ts contants/__tests__/EmbargoConstants.test.ts`
Expected: PASS (all tests in both files).

- [ ] **Step 5: Type-check**

Run: `npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E "types/(GatekeeperAPI|BffAPI|APIError)|lib/rpc|EmbargoConstants" || echo "no new type errors"`
Expected: `no new type errors`

- [ ] **Step 6: Commit**

```bash
git add types/GatekeeperAPI.ts types/BffAPI.ts types/APIError.ts lib/rpc.ts lib/__tests__/rpc.test.ts contants/EmbargoConstants.ts contants/__tests__/EmbargoConstants.test.ts
git commit -m "feat: types and error messages for the dataset embargo"
```

---

### Task 2: Route and telemetry constants

**Files:**
- Modify: `contants/InternalRoutesConstants.ts`
- Modify: `contants/TelemetryConstants.ts:5-42`
- Test: `contants/__tests__/InternalRoutesConstants_test.ts` (append), `contants/__tests__/TelemetryConstants.test.ts` (append)

**Interfaces:**
- Produces: `ROUTE_PAGE_DATASETS_SHARED: string`, `ROUTE_PAGE_REVIEW(params: { token }): string`, `ROUTE_PAGE_INVITATION(params: { token }): string`, `ROUTE_PAGE_DOI_LANDING(params: { id, versionName }): string`; UI events `embargo_set`, `embargo_extended`, `dataset_shared`, `review_link_created`.

- [ ] **Step 1: Write the failing tests**

Append to `contants/__tests__/InternalRoutesConstants_test.ts`:

```ts
import {
    ROUTE_PAGE_DATASETS_SHARED,
    ROUTE_PAGE_DOI_LANDING,
    ROUTE_PAGE_INVITATION,
    ROUTE_PAGE_REVIEW,
} from "../InternalRoutesConstants";

test('Shared with me route', () => {
    expect(ROUTE_PAGE_DATASETS_SHARED).toBe("/app/datasets/shared")
})

test('Review route', () => {
    expect(ROUTE_PAGE_REVIEW({ token: "abc" })).toBe("/review/abc")
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
      "/review/[token]",
      "/invitations/[token]",
      "/doi/datasets/[datasetId]/versions/[versionName]",
    ]) {
      expect(pageLabel(page)).toBe(page);
    }
  });

  it("accepts the new ui events", () => {
    for (const event of ["embargo_set", "embargo_extended", "dataset_shared", "review_link_created"]) {
      expect(uiEventLabel(event)).toBe(event);
    }
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest contants/__tests__`
Expected: FAIL — the new route exports are undefined; `pageLabel("/review/[token]")` returns `"other"`.

- [ ] **Step 3: Implement**

In `contants/InternalRoutesConstants.ts`, after `ROUTE_PAGE_DATASETS_NEW`:

```ts
/**
 * Route to the datasets shared with the user.
 * @constant
 */
export const ROUTE_PAGE_DATASETS_SHARED = ROUTE_PAGE_DATASETS + "/shared";

/**
 * Route to the anonymous reviewer page.
 * @constant
 */
export const ROUTE_PAGE_REVIEW = (params) => replaceIt('/review/:token', params);

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
  "/review/[token]",
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
  "review_link_created",
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
- Create: `lib/shareTarget.ts`, `lib/embargoDates.ts`, `lib/embargoState.ts`
- Test: `lib/__tests__/shareTarget.test.ts`, `lib/__tests__/embargoDates.test.ts`, `lib/__tests__/embargoState.test.ts`

**Interfaces:**
- Consumes: `MAX_EMBARGO_DAYS` (Task 1), `GetDatasetDetailsResponse`, `GetDatasetDetailsDOIResponseState` (`types/BffAPI.ts`), `SetEmbargoRequest` (Task 1).
- Produces:
  - `type ShareTarget = { kind: "email" | "orcid" | "invalid_orcid" | "text", value: string }`
  - `isValidOrcidChecksum(orcid: string): boolean`, `classifyShareInput(raw: string): ShareTarget`
  - `toDateInputValue(date: Date): string`, `minEmbargoDate(now: Date): string`, `maxEmbargoDate(now: Date): string`, `minExtensionDate(currentUntil: string, now: Date): string`, `toEmbargoUntil(dateInput: string): string`, `validateEmbargoDate(dateInput: string, now: Date, min?: string): string | undefined`, `formatEmbargoDate(iso: string): string`, `embargoRequestFrom(values: { embargoMode?: EmbargoMode, embargoUntil?: string }): SetEmbargoRequest | null`, `type EmbargoMode = "none" | "open" | "hidden"`
  - `isFilesWithheld(dataset): boolean`, `shouldShowEmbargoEndedBanner(dataset): boolean`, `canSeeSettings(dataset, canEdit: boolean): boolean`
  - `type ManualDoiGate = "ends_embargo" | "owner_only" | "blocks_future_embargo"`, `manualDoiGate(dataset): ManualDoiGate`, `hasManualDoi(dataset): boolean`

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

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/shareTarget.test.ts lib/__tests__/embargoDates.test.ts lib/__tests__/embargoState.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/shareTarget.ts lib/embargoDates.ts lib/embargoState.ts lib/__tests__/shareTarget.test.ts lib/__tests__/embargoDates.test.ts lib/__tests__/embargoState.test.ts
git commit -m "feat: recognise emails and ORCIDs, and the embargo date limits"
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
  - `getEmbargoStatus(datasetId): Promise<EmbargoStatusResponse>`
  - `searchShareCandidates(context, datasetId, q): Promise<ShareUser[]>`
  - `getShareState(context, datasetId): Promise<ShareState>`
  - `grantAccess(context, datasetId, request: GrantRequest): Promise<GrantResult>`
  - `changePermissionLevel(context, datasetId, userId, level: PermissionLevel): Promise<SharePermission>`
  - `revokePermission(context, datasetId, userId): Promise<void>`
  - `revokeInvitation(context, datasetId, invitationId): Promise<void>`
  - `regenerateInvitationLink(context, datasetId, invitationId): Promise<{ link: string }>`
  - `createReviewLink(context, datasetId, label): Promise<CreatedReviewLink>`
  - `revokeReviewLink(context, datasetId, linkId): Promise<void>`
  - `getReviewPage(token): Promise<ReviewPageResponse>`
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
    createReviewLink,
    getReviewPage,
    getShareState,
    grantAccess,
    regenerateInvitationLink,
    revokeInvitation,
    revokePermission,
    revokeReviewLink,
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
        mockGet.mockResolvedValue({ data: { owner: {}, permissions: [], invitations: [], review_links: [] } });

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

    test("create a reviewer link", async () => {
        mockPost.mockResolvedValue({ data: { id: "r1", link: "https://x/review/t" } });

        await createReviewLink(context, "d1", "JGR, round 1");
        expect(mockPost).toHaveBeenCalledWith("/datasets/d1/review-links", { label: "JGR, round 1" }, headers);
    });

    test("revoke a reviewer link", async () => {
        mockDelete.mockResolvedValue({ status: 204 });

        await revokeReviewLink(context, "d1", "r1");
        expect(mockDelete).toHaveBeenCalledWith("/datasets/d1/review-links/r1", headers);
    });

    test("the review page is asked without a user", async () => {
        mockGet.mockResolvedValue({ data: { state: "ended", dataset_id: "d1", published: false } });

        await getReviewPage("a/b");
        expect(mockGet).toHaveBeenCalledWith("/review/a%2Fb");
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
    CreatedReviewLink,
    GrantRequest,
    GrantResult,
    PermissionLevel,
    ReviewPageResponse,
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

export async function createReviewLink(context: AppLocalContext, datasetId: string, label: string): Promise<CreatedReviewLink> {
    const response = await axiosInstance.post(`/datasets/${datasetId}/review-links`, { label }, buildHeaders(context));
    return response.data as CreatedReviewLink;
}

export async function revokeReviewLink(context: AppLocalContext, datasetId: string, linkId: string): Promise<void> {
    await axiosInstance.delete(`/datasets/${datasetId}/review-links/${linkId}`, buildHeaders(context));
}

export async function getReviewPage(token: string): Promise<ReviewPageResponse> {
    const response = await axiosInstance.get(`/review/${encodeURIComponent(token)}`);
    return response.data as ReviewPageResponse;
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

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/embargo.test.ts lib/__tests__/share.test.ts lib/__tests__/dataset.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/embargo.ts lib/share.ts lib/dataset.ts lib/__tests__/embargo.test.ts lib/__tests__/share.test.ts lib/__tests__/dataset.test.ts
git commit -m "feat: server calls for embargo, sharing and reviewer links"
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
  - `pages/api/datasets/[datasetId]/share/index.ts` (GET, POST)
  - `pages/api/datasets/[datasetId]/share/candidates.ts` (GET)
  - `pages/api/datasets/[datasetId]/share/permissions/[userId].ts` (PUT, DELETE)
  - `pages/api/datasets/[datasetId]/share/invitations/[invitationId]/index.ts` (DELETE)
  - `pages/api/datasets/[datasetId]/share/invitations/[invitationId]/link.ts` (POST)
  - `pages/api/datasets/[datasetId]/review-links/index.ts` (POST)
  - `pages/api/datasets/[datasetId]/review-links/[linkId].ts` (DELETE)
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
  - `searchShareCandidates(datasetId, q): Promise<ShareUser[]>`
  - `grantAccess(datasetId, request: GrantRequest): Promise<GrantResult>` (event `dataset_shared`)
  - `changePermissionLevel(datasetId, userId, level): Promise<SharePermission>`
  - `revokePermission(datasetId, userId): Promise<void>`
  - `revokeInvitation(datasetId, invitationId): Promise<void>`
  - `regenerateInvitationLink(datasetId, invitationId): Promise<{ link: string }>`
  - `createReviewLink(datasetId, label): Promise<CreatedReviewLink>` (event `review_link_created`)
  - `revokeReviewLink(datasetId, linkId): Promise<void>`
  - `acceptInvitation(token): Promise<AcceptInvitationResponse>`
- Produces (BFF): `GET /api/datasets/{id}/share` is the SWR key used by the share dialog; `GET /api/datasets/shared?page=&page_size=` by the Shared page.

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
        jest.mocked(getShareState).mockResolvedValue({ owner: { id: "o" }, permissions: [], invitations: [], review_links: [] } as any);

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

`pages/api/datasets/[datasetId]/review-links/index.ts`:

```ts
import { NewContext } from "../../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../../lib/bffRoute";
import { createReviewLink } from "../../../../../lib/share";

const router = bffRouter()
    .post(async (req, res) => {
        const context = await NewContext(req);
        res.status(201).json(await createReviewLink(context, req.query.datasetId as string, req.body?.label));
    });

export default bffHandler(router);
```

`pages/api/datasets/[datasetId]/review-links/[linkId].ts`:

```ts
import { NewContext } from "../../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../../lib/bffRoute";
import { revokeReviewLink } from "../../../../../lib/share";

const router = bffRouter()
    .delete(async (req, res) => {
        const context = await NewContext(req);
        await revokeReviewLink(context, req.query.datasetId as string, req.query.linkId as string);
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
    CreatedReviewLink,
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

    async createReviewLink(datasetId: string, label: string): Promise<CreatedReviewLink> {
        try {
            const response = await axios.post(`/api/datasets/${datasetId}/review-links`, { label });
            trackUiEvent("review_link_created");
            return response.data as CreatedReviewLink;
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async revokeReviewLink(datasetId: string, linkId: string): Promise<void> {
        try {
            await axios.delete(`/api/datasets/${datasetId}/review-links/${linkId}`);
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

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/shareRoutes.test.ts lib/__tests__/embargoRoutes.test.ts gateways/__tests__/BFFAPI.embargo.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pages/api/datasets/ pages/api/invitations/ gateways/BFFAPI.ts gateways/__tests__/ lib/__tests__/shareRoutes.test.ts lib/__tests__/embargoRoutes.test.ts
git commit -m "feat: BFF routes for embargo, sharing, reviewer links and invitations"
```

---

### Task 7: Shared with me, layout and list badge

**Files:**
- Modify: `components/LoggedLayout.tsx`
- Create: `components/Embargo/EmbargoBadge.tsx` (skip if Task 8 already created it; the content is identical)
- Create: `pages/app/datasets/shared.tsx`
- Modify: `components/Search/ListItem.tsx`, `components/Tenancy/AccessPending.tsx`
- Test: `components/Embargo/__tests__/EmbargoBadge.test.tsx`, `components/Tenancy/__tests__/AccessPending.test.tsx` (append)

**Interfaces:**
- Consumes: `ROUTE_PAGE_DATASETS_SHARED` (Task 2), `formatEmbargoDate` (Task 3), `/api/datasets/shared` (Task 6).
- Produces: `LoggedLayout` prop `tenancyOptional?: boolean`; `EmbargoBadge(props: { embargo?: DatasetEmbargo | null })`.

- [ ] **Step 1: Write the failing tests**

`components/Embargo/__tests__/EmbargoBadge.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { EmbargoBadge } from "../EmbargoBadge";

describe("EmbargoBadge", () => {
    test("shows the end date of an active embargo", () => {
        render(<EmbargoBadge embargo={{ until: "2026-12-28T23:59:59+00:00", active: true, metadata_visible: false, note: null }} />);

        expect(screen.getByTestId("embargo-badge").textContent).toContain("Under embargo until December 28, 2026");
    });

    test("shows nothing once the embargo is over", () => {
        render(<EmbargoBadge embargo={{ until: "2026-09-01T23:59:59+00:00", active: false, metadata_visible: false, note: null }} />);

        expect(screen.queryByTestId("embargo-badge")).toBeNull();
    });

    test("shows nothing without an embargo", () => {
        render(<EmbargoBadge embargo={null} />);

        expect(screen.queryByTestId("embargo-badge")).toBeNull();
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

Run: `npx jest components/Embargo/__tests__/EmbargoBadge.test.tsx components/Tenancy/__tests__/AccessPending.test.tsx`
Expected: FAIL — `Cannot find module '../EmbargoBadge'`; no link named "Shared with me".

- [ ] **Step 3: Implement**

`components/Embargo/EmbargoBadge.tsx`:

```tsx
import { MaterialSymbol } from "react-material-symbols";
import { formatEmbargoDate } from "../../lib/embargoDates";
import { DatasetEmbargo } from "../../types/GatekeeperAPI";

interface Props {
    embargo?: DatasetEmbargo | null
}

export function EmbargoBadge(props: Props) {
    if (!props.embargo?.active) {
        return null;
    }

    return (
        <span
            data-testid="embargo-badge"
            className="inline-flex items-center gap-1 px-2.5 py-[3px] text-xs leading-[18px] font-semibold rounded-full text-primary-900 bg-secondary-500 whitespace-nowrap"
        >
            <MaterialSymbol icon="lock_clock" size={14} grade={-25} weight={400} />
            Under embargo until {formatEmbargoDate(props.embargo.until)}
        </span>
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
2. Change the redirect to:

```tsx
  // If no tenancy selected, request to select one
  if (!props.tenancyOptional && !isTenancySelected()) {
    Router.push(ROUTE_PAGE_TENANCY_SELECTOR);
  }
```

3. Add `ROUTE_PAGE_DATASETS_SHARED` to the `InternalRoutesConstants` import (`MaterialSymbol` is already imported), and after the `Datasets` `MenuItem`:

```tsx
            <MenuItem href={ROUTE_PAGE_DATASETS_SHARED} text="Shared with me" icon="folder_shared" collapsed={menuClosed} />
```

4. In `MenuItem`, `active` becomes an exact match. The current `href.indexOf(browserPath) >= 0` lights *Shared with me* on `/app/datasets`, because `/app/datasets/shared` contains `/app/datasets`:

```tsx
  function active(href: string) {
    return href === router.pathname;
  }
```

`isActive` and the rest of `MenuItem` stay as they are.

5. The tenancy line at the bottom of the sidebar (`{!menuClosed && tenancySelected && (...)}`) already renders nothing without a tenancy; leave it.

`pages/app/datasets/shared.tsx`:

```tsx
import { useState } from "react";
import useSWR from "swr";
import LoggedLayout from "../../../components/LoggedLayout";
import { EmptySearch } from "../../../components/Search/EmptySearch";
import { ListDataset } from "../../../components/Search/ListDataset";
import { SWRRetry, fetcher } from "../../../lib/fetcher";
import { GetDatasetsResponse } from "../../../types/BffAPI";

export default function SharedDatasetsPage() {
    const [currentPage, setCurrentPage] = useState(1);
    const [pageSize, setPageSize] = useState(20);

    const { data, error, isLoading } = useSWR(
        `/api/datasets/shared?page=${currentPage}&page_size=${pageSize}`,
        fetcher,
        { onErrorRetry: SWRRetry }
    );
    const datasets = data as GetDatasetsResponse;

    return (
        <LoggedLayout tenancyOptional>
            <div className="w-full max-w-5xl mx-auto">
                <h2 className="m-0 text-3xl leading-tight">Shared with me</h2>
                <p className="mt-2 mb-0 text-[15px] leading-[23px] text-primary-600">
                    Datasets other researchers gave you access to, in any namespace.
                </p>

                <div className="mt-7">
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

`components/Search/ListItem.tsx` — add `import { EmbargoBadge } from "../Embargo/EmbargoBadge";` and replace the last column (`<div className="self-start"><DesignStatePill ... /></div>`) with:

```tsx
        <div className="self-start flex flex-col items-end gap-1.5">
          <DesignStatePill state={props.dataset.current_version.design_state} />
          <EmbargoBadge embargo={props.dataset.embargo} />
        </div>
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest components/Embargo/__tests__/EmbargoBadge.test.tsx components/Tenancy/__tests__/AccessPending.test.tsx contants/__tests__/TelemetryConstants.test.ts`
Expected: PASS (the telemetry test now finds `/app/datasets/shared` in `PAGES`).

- [ ] **Step 5: Commit**

```bash
git add components/Embargo/EmbargoBadge.tsx components/Embargo/__tests__/EmbargoBadge.test.tsx components/LoggedLayout.tsx components/Search/ListItem.tsx components/Tenancy/AccessPending.tsx components/Tenancy/__tests__/AccessPending.test.tsx pages/app/datasets/shared.tsx
git commit -m "feat: Shared with me, open to accounts with no namespace"
```

---

### Task 8: Embargo on the dataset page

**Files:**
- Modify: `lib/users.ts:127-130` (`canEditDataset`) and its 8 call sites
- Create: `components/Embargo/EmbargoSettings.tsx`, `components/Embargo/FilesWithheldNotice.tsx`, `components/Embargo/EmbargoEndedBanner.tsx`
- Create (if Task 7 has not): `components/Embargo/EmbargoBadge.tsx` (content in Task 7)
- Modify: `components/DatasetDetailsPage.tsx`, `components/DatasetDetails/TabPanelSettings.tsx`, `components/DatasetDetails/DataCard/DataExplorer.tsx`, `pages/app/datasets/[datasetId]/index.tsx`, `pages/app/datasets/[datasetId]/versions/[versionName]/index.tsx`
- Test: `lib/__tests__/users.test.ts`, `components/Embargo/__tests__/EmbargoSettings.test.tsx`, `components/Embargo/__tests__/FilesWithheldNotice.test.tsx`, `components/Embargo/__tests__/EmbargoEndedBanner.test.tsx`

**Interfaces:**
- Consumes: Task 3 (`minEmbargoDate`, `maxEmbargoDate`, `minExtensionDate`, `validateEmbargoDate`, `toEmbargoUntil`, `formatEmbargoDate`, `isFilesWithheld`, `shouldShowEmbargoEndedBanner`, `canSeeSettings`, `hasManualDoi`), Task 6 BFFAPI methods, `messageForApiError` (Task 1).
- Produces: `canEditDataset(user, dataset?)`; components `EmbargoSettings({ dataset })`, `FilesWithheldNotice({ version })`, `EmbargoEndedBanner({ dataset })`.

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

`components/Embargo/__tests__/FilesWithheldNotice.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { FilesWithheldNotice } from "../FilesWithheldNotice";

describe("FilesWithheldNotice", () => {
    test("says the list is hidden, with the count and size", () => {
        render(<FilesWithheldNotice version={{ files_withheld: true, files_summary: { count: 42, total_size_bytes: 2048 } } as any} />);

        const notice = screen.getByTestId("files-withheld");
        expect(notice.textContent).toContain("42 files");
        expect(notice.textContent).toContain("hidden while this dataset is under embargo");
    });

    test("renders nothing when the files are visible", () => {
        render(<FilesWithheldNotice version={{ files_withheld: false } as any} />);

        expect(screen.queryByTestId("files-withheld")).toBeNull();
    });
});
```

`components/Embargo/__tests__/EmbargoEndedBanner.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { EmbargoEndedBanner } from "../EmbargoEndedBanner";

describe("EmbargoEndedBanner", () => {
    test("explains that nothing is public and the DOI is registered but not findable", () => {
        render(<EmbargoEndedBanner dataset={{ embargo: { until: "2026-09-01T23:59:59+00:00", active: false } } as any} />);

        const banner = screen.getByRole("status");
        expect(banner.textContent).toContain("ended on September 1, 2026");
        expect(banner.textContent).toContain("Nothing has been made public");
        expect(banner.textContent).toContain("registered but not findable");
        expect(banner.textContent).toContain("Findable");
    });
});
```

`components/Embargo/__tests__/EmbargoSettings.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { beforeEach, describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const setEmbargo = jest.fn() as any;
const extendEmbargo = jest.fn() as any;
const endEmbargo = jest.fn() as any;
const setEmbargoMode = jest.fn() as any;
const reload = jest.fn();

jest.mock("../../../gateways/BFFAPI", () => ({
    BFFAPI: jest.fn().mockImplementation(() => ({ setEmbargo, extendEmbargo, endEmbargo, setEmbargoMode })),
}));
jest.mock("next/router", () => ({ __esModule: true, default: { reload: () => reload() }, useRouter: () => ({ reload }) }));

import { EmbargoSettings } from "../EmbargoSettings";

const owner = { level: "owner", can_edit: true, can_share: true, can_manage_embargo: true, can_extend_embargo: true, can_delete: true };

function datasetWith(embargo: any, access: any = owner, versions: any[] = []): any {
    return { id: "d1", embargo, access, versions };
}

beforeEach(() => {
    jest.useFakeTimers({ now: new Date("2026-09-30T10:00:00Z"), doNotFake: ["setTimeout", "setInterval", "queueMicrotask", "nextTick"] });
});

describe("EmbargoSettings", () => {
    test("the owner sets an embargo on a dataset without one", async () => {
        setEmbargo.mockResolvedValue({ active: true });
        render(<EmbargoSettings dataset={datasetWith(null)} />);

        fireEvent.click(screen.getByLabelText("Hidden"));
        fireEvent.change(screen.getByLabelText("Embargo until"), { target: { value: "2026-12-01" } });
        fireEvent.click(screen.getByRole("button", { name: "Set embargo" }));

        await waitFor(() => expect(setEmbargo).toHaveBeenCalledWith("d1", {
            until: "2026-12-01T23:59:59+00:00", metadata_visible: false, note: null,
        }));
        await waitFor(() => expect(reload).toHaveBeenCalled());
    });

    test("an extension beyond 90 days is refused before it is sent", async () => {
        render(<EmbargoSettings dataset={datasetWith({ until: "2026-10-10T23:59:59+00:00", active: true, metadata_visible: false, note: null })} />);

        fireEvent.change(screen.getByLabelText("New end date"), { target: { value: "2027-01-15" } });
        fireEvent.click(screen.getByRole("button", { name: "Extend" }));

        expect(await screen.findByText("An embargo can last at most 90 days.")).toBeTruthy();
        expect(extendEmbargo).not.toHaveBeenCalled();
    });

    test("a server refusal is shown in words", async () => {
        extendEmbargo.mockRejectedValue({ httpCode: 400, errors: [{ code: "embargo_until_not_later" }] });
        render(<EmbargoSettings dataset={datasetWith({ until: "2026-10-10T23:59:59+00:00", active: true, metadata_visible: false, note: null })} />);

        fireEvent.change(screen.getByLabelText("New end date"), { target: { value: "2026-11-01" } });
        fireEvent.click(screen.getByRole("button", { name: "Extend" }));

        expect(await screen.findByText("The new date must be later than the current end of the embargo.")).toBeTruthy();
    });

    test("someone who may only extend sees neither the mode nor the end button", () => {
        render(<EmbargoSettings dataset={datasetWith(
            { until: "2026-10-10T23:59:59+00:00", active: true, metadata_visible: false, note: null },
            { ...owner, level: "write", can_manage_embargo: false },
        )} />);

        expect(screen.getByRole("button", { name: "Extend" })).toBeTruthy();
        expect(screen.queryByRole("button", { name: "End embargo now" })).toBeNull();
        expect(screen.queryByRole("button", { name: "Save visibility" })).toBeNull();
    });

    test("a dataset with a manual DOI cannot be put under embargo", () => {
        render(<EmbargoSettings dataset={datasetWith(null, owner, [{ doi: { mode: "MANUAL" } }])} />);

        expect(screen.queryByRole("button", { name: "Set embargo" })).toBeNull();
        expect(screen.getByText("This dataset has a manual DOI, so it can no longer be put under embargo.")).toBeTruthy();
    });

    test("ending early asks for confirmation", async () => {
        endEmbargo.mockResolvedValue({ active: false });
        render(<EmbargoSettings dataset={datasetWith({ until: "2026-10-10T23:59:59+00:00", active: true, metadata_visible: true, note: null })} />);

        fireEvent.click(screen.getByRole("button", { name: "End embargo now" }));
        fireEvent.click(screen.getByRole("button", { name: "End embargo" }));

        await waitFor(() => expect(endEmbargo).toHaveBeenCalledWith("d1"));
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

They follow the identity introduced by webapp #101: sections are white cards (`rounded-lg border border-primary-200 bg-primary-0`) with an `h2` at `text-lg`, form fields use the classes in `contants/EditFormConstants.ts`, notices use the mint tint `bg-secondary-500`, and icons are `MaterialSymbol` at weight 400, grade -25.

`components/Embargo/FilesWithheldNotice.tsx`:

```tsx
import { MaterialSymbol } from "react-material-symbols";
import { bytesToSize } from "../../lib/file";
import { GetDatasetDetailsVersionResponse } from "../../types/BffAPI";

interface Props {
    version?: GetDatasetDetailsVersionResponse
}

export function FilesWithheldNotice(props: Props) {
    if (!props.version?.files_withheld) {
        return null;
    }

    const summary = props.version.files_summary;

    return (
        <div data-testid="files-withheld" className="flex gap-3 items-start rounded-lg border border-primary-200 bg-secondary-500 px-4 py-3">
            <MaterialSymbol icon="lock" size={18} grade={-25} weight={400} className="mt-0.5 text-primary-700" />
            <p className="m-0 text-sm leading-5 text-primary-700">
                The file list is hidden while this dataset is under embargo.
                {summary && <> It holds {summary.count} files, {bytesToSize(summary.total_size_bytes)} in total.</>}
            </p>
        </div>
    );
}
```

`components/Embargo/EmbargoEndedBanner.tsx`:

```tsx
import { MaterialSymbol } from "react-material-symbols";
import { formatEmbargoDate } from "../../lib/embargoDates";
import { GetDatasetDetailsResponse } from "../../types/BffAPI";

interface Props {
    dataset: GetDatasetDetailsResponse
}

export function EmbargoEndedBanner(props: Props) {
    return (
        <div role="status" className="flex gap-3 items-start rounded-lg border border-primary-200 bg-secondary-500 p-4">
            <MaterialSymbol icon="lock_open" size={20} grade={-25} weight={400} className="mt-0.5 text-primary-900" />
            <div className="flex flex-col gap-1.5 text-sm leading-5 text-primary-700">
                <p className="m-0 font-semibold text-primary-900">The embargo on this dataset ended on {formatEmbargoDate(props.dataset.embargo.until)}.</p>
                <p className="m-0">Its files are now available to the members of its namespace. Nothing has been made public.</p>
                <p className="m-0">
                    Its DOI is registered but not findable: it resolves, but DataCite does not index it, so the dataset
                    does not appear in DataCite search. To publish the dataset page and index the DOI, move the DOI to
                    Findable in the Citation section. Nothing will do it for you.
                </p>
            </div>
        </div>
    );
}
```

`components/Embargo/EmbargoSettings.tsx`:

```tsx
import { ErrorMessage, Field, Form, Formik } from "formik";
import { useRouter } from "next/router";
import { useState } from "react";
import {
    EDIT_FORM_ERROR_CLASS,
    EDIT_FORM_HINT_CLASS,
    EDIT_FORM_INPUT_CLASS,
    EDIT_FORM_LABEL_CLASS,
} from "../../contants/EditFormConstants";
import { EMBARGO_ERROR_MESSAGES, messageForApiError } from "../../contants/EmbargoConstants";
import { BFFAPI } from "../../gateways/BFFAPI";
import {
    embargoRequestFrom,
    EmbargoMode,
    formatEmbargoDate,
    maxEmbargoDate,
    minEmbargoDate,
    minExtensionDate,
    toEmbargoUntil,
    validateEmbargoDate,
} from "../../lib/embargoDates";
import { hasManualDoi } from "../../lib/embargoState";
import { GetDatasetDetailsResponse } from "../../types/BffAPI";
import Modal from "../base/PopupModal";

interface Props {
    dataset: GetDatasetDetailsResponse
}

export function EmbargoSettings(props: Props) {
    const bffGateway = new BFFAPI();
    const router = useRouter();
    const [serverError, setServerError] = useState<string | null>(null);
    const [confirmEnd, setConfirmEnd] = useState(false);

    const embargo = props.dataset.embargo;
    const access = props.dataset.access;
    const now = new Date();

    async function run(action: () => Promise<unknown>) {
        setServerError(null);
        try {
            await action();
            router.reload();
        } catch (error) {
            setServerError(messageForApiError(error));
        }
    }

    const manualDoi = hasManualDoi(props.dataset);
    const showSet = access?.can_manage_embargo && !embargo?.active && !manualDoi;
    const showManualDoiNote = access?.can_manage_embargo && !embargo?.active && manualDoi;
    const showExtend = access?.can_extend_embargo && embargo?.active;
    const showManage = access?.can_manage_embargo && embargo?.active;

    if (!showSet && !showManualDoiNote && !showExtend && !showManage) {
        return null;
    }

    return (
        <section className="flex flex-col gap-3 min-w-0" aria-labelledby="embargo-settings-title">
            <div>
                <h2 id="embargo-settings-title" className="m-0 text-lg leading-snug tracking-[-0.01em]">Embargo</h2>
                <p className="m-0 mt-1 text-sm text-primary-600">
                    {embargo?.active
                        ? <>Under embargo until {formatEmbargoDate(embargo.until)}, {embargo.metadata_visible
                            ? "visible to the namespace with an embargo badge"
                            : "hidden from everyone without access"}. Only the owner and the people the owner authorised reach the files.</>
                        : "Keep the files closed while the article that describes them is under review."}
                </p>
            </div>

            {serverError && <p role="alert" className="m-0 text-sm text-error-600">{serverError}</p>}

            {showManualDoiNote &&
                <div className="rounded-lg border border-primary-200 bg-primary-0 p-5">
                    <p className="m-0 text-sm text-primary-700">{EMBARGO_ERROR_MESSAGES.embargo_manual_doi}</p>
                </div>
            }

            {showSet &&
                <Formik
                    initialValues={{ embargoMode: "hidden" as EmbargoMode, embargoUntil: "" }}
                    validate={(values) => {
                        const message = validateEmbargoDate(values.embargoUntil, now);
                        return message ? { embargoUntil: message } : {};
                    }}
                    onSubmit={(values) => run(() => bffGateway.setEmbargo(props.dataset.id, embargoRequestFrom(values)))}
                >
                    {({ isSubmitting }) => (
                        <Form className="rounded-lg border border-primary-200 bg-primary-0">
                            <div className="flex flex-col gap-5 p-5">
                                <EmbargoModeFields />
                                <div>
                                    <label htmlFor="embargoUntil" className={EDIT_FORM_LABEL_CLASS}>Embargo until</label>
                                    <Field type="date" id="embargoUntil" name="embargoUntil" min={minEmbargoDate(now)} max={maxEmbargoDate(now)} className={EDIT_FORM_INPUT_CLASS} />
                                    <ErrorMessage name="embargoUntil" component="div" className={EDIT_FORM_ERROR_CLASS} />
                                </div>
                            </div>
                            <div className="flex items-center justify-end gap-2 border-t border-primary-200 bg-primary-50 px-5 py-3 rounded-b-lg">
                                <button type="submit" className="btn-primary m-0" disabled={isSubmitting}>Set embargo</button>
                            </div>
                        </Form>
                    )}
                </Formik>
            }

            {showExtend &&
                <Formik
                    initialValues={{ until: "" }}
                    validate={(values) => {
                        const min = minExtensionDate(embargo.until, now);
                        const message = validateEmbargoDate(values.until, now, min);
                        return message ? { until: message } : {};
                    }}
                    onSubmit={(values) => run(() => bffGateway.extendEmbargo(props.dataset.id, { until: toEmbargoUntil(values.until) }))}
                >
                    {({ isSubmitting }) => (
                        <Form className="rounded-lg border border-primary-200 bg-primary-0">
                            <div className="flex flex-col gap-1.5 p-5">
                                <label htmlFor="extendUntil" className={EDIT_FORM_LABEL_CLASS}>New end date</label>
                                <Field type="date" id="extendUntil" name="until" min={minExtensionDate(embargo.until, now)} max={maxEmbargoDate(now)} className={EDIT_FORM_INPUT_CLASS} />
                                <ErrorMessage name="until" component="div" className={EDIT_FORM_ERROR_CLASS} />
                                <p className={EDIT_FORM_HINT_CLASS}>Each extension reaches at most 90 days from today.</p>
                            </div>
                            <div className="flex items-center justify-end gap-2 border-t border-primary-200 bg-primary-50 px-5 py-3 rounded-b-lg">
                                <button type="submit" className="btn-primary-outline m-0" disabled={isSubmitting}>Extend</button>
                            </div>
                        </Form>
                    )}
                </Formik>
            }

            {showManage &&
                <>
                    <Formik
                        initialValues={{ embargoMode: (embargo.metadata_visible ? "open" : "hidden") as EmbargoMode }}
                        onSubmit={(values) => run(() => bffGateway.setEmbargoMode(props.dataset.id, { metadata_visible: values.embargoMode === "open" }))}
                    >
                        {({ isSubmitting }) => (
                            <Form className="rounded-lg border border-primary-200 bg-primary-0">
                                <div className="p-5">
                                    <EmbargoModeFields />
                                </div>
                                <div className="flex items-center justify-between gap-2 border-t border-primary-200 bg-primary-50 px-5 py-3 rounded-b-lg">
                                    <button type="button" className="btn-primary-outline m-0" onClick={() => setConfirmEnd(true)}>End embargo now</button>
                                    <button type="submit" className="btn-primary m-0" disabled={isSubmitting}>Save visibility</button>
                                </div>
                            </Form>
                        )}
                    </Formik>

                    <Modal
                        title="End the embargo"
                        show={confirmEnd}
                        confimButtonText="End embargo"
                        cancelButtonText="Cancel"
                        destructive
                        cancel={() => setConfirmEnd(false)}
                        confim={() => {
                            setConfirmEnd(false);
                            run(() => bffGateway.endEmbargo(props.dataset.id));
                        }}
                    >
                        <p className="m-0">The files become available to the members of the namespace now. This cannot be undone.</p>
                    </Modal>
                </>
            }
        </section>
    );
}

function EmbargoModeFields() {
    return (
        <fieldset className="flex flex-col gap-3 m-0 p-0 border-0">
            <legend className={EDIT_FORM_LABEL_CLASS}>While under embargo, the dataset is</legend>
            <div>
                <label className="flex gap-2 items-center m-0 text-sm font-medium text-primary-900">
                    <Field type="radio" name="embargoMode" value="hidden" className="h-4 w-4 accent-primary-900" /> Hidden
                </label>
                <p className={`${EDIT_FORM_HINT_CLASS} pl-6`}>Nobody without access knows it exists.</p>
            </div>
            <div>
                <label className="flex gap-2 items-center m-0 text-sm font-medium text-primary-900">
                    <Field type="radio" name="embargoMode" value="open" className="h-4 w-4 accent-primary-900" /> Visible with a badge
                </label>
                <p className={`${EDIT_FORM_HINT_CLASS} pl-6`}>The namespace sees it in listings; files stay closed.</p>
            </div>
        </fieldset>
    );
}
```

The radio labels must match the test: `getByLabelText("Hidden")` finds the radio by its wrapping label text "Hidden". Keep the label text exactly `Hidden` and `Visible with a badge`. `globals.css` styles every bare `input` with `w-full p-2.5`; the explicit `h-4 w-4` on the radios overrides it.

- [ ] **Step 5: Wire the dataset page**

`components/DatasetDetailsPage.tsx` (as on main since #101: `StatusPill`, `max-w-5xl` column, actions in `flex flex-none items-center gap-2`) — imports:

```tsx
import { EmbargoBadge } from "./Embargo/EmbargoBadge";
import { EmbargoEndedBanner } from "./Embargo/EmbargoEndedBanner";
import { canSeeSettings, isFilesWithheld, shouldShowEmbargoEndedBanner } from "../lib/embargoState";
import { bytesToSize } from "../lib/file";
```

`totalDatasetVersionFilesSize` stays imported from `../lib/file` too. Replace the `filesCount` line with:

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

The actions block becomes:

```tsx
            <div className="flex flex-none items-center gap-2">
              {!isFilesWithheld(props.dataset) && <DownloadDatafilesButton dataset={props.dataset} />}
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

`components/DatasetDetails/TabPanelSettings.tsx` — add `import { EmbargoSettings } from "../Embargo/EmbargoSettings";` and `import { canEditDataset } from "../../lib/users";`. The left column (`<section className="flex flex-col gap-3 min-w-0">` holding *General*) becomes a column of sections:

```tsx
        <div className="flex flex-col gap-10 min-w-0">
          {canEditDataset(props.user, props.dataset) &&
            <section className="flex flex-col gap-3 min-w-0">
              {/* the existing General heading and Formik, unchanged */}
            </section>
          }
          <EmbargoSettings dataset={props.dataset} />
        </div>
```

Move the existing `<div><h2 …>General</h2>…</div>` and `<Formik …>…</Formik>` into that `section` without changing them; the `<aside>` stays where it is, as the grid's second column.

`components/DatasetDetails/DataCard/DataExplorer.tsx` — add `import { FilesWithheldNotice } from "../../Embargo/FilesWithheldNotice";` and `import { bytesToSize } from "../../../lib/file";`. The count in the header (`{getVersionByName(...)?.files_in?.length ?? 0} files · {totalDatasetVersionFilesSize(selectedDatasetVersion)}`) becomes:

```tsx
            {selectedDatasetVersion?.files_withheld
              ? <>{selectedDatasetVersion.files_summary?.count ?? 0} files · {bytesToSize(selectedDatasetVersion.files_summary?.total_size_bytes ?? 0)}</>
              : <>{getVersionByName(props.selectedVersionName, props.dataset.versions, props.dataset)?.files_in?.length ?? 0} files · {totalDatasetVersionFilesSize(selectedDatasetVersion)}</>
            }
```

`NewVersionButton` is shown only to whoever may edit: `{props.dataset.access?.can_edit !== false && <NewVersionButton onClick={() => setShowUploadDataModal(true)} />}`. Directly above `<DatasetFilesList`:

```tsx
      <FilesWithheldNotice version={selectedDatasetVersion} />
```

Both dataset pages (`pages/app/datasets/[datasetId]/index.tsx`, `pages/app/datasets/[datasetId]/versions/[versionName]/index.tsx`) already route errors through `handleDatasetRequestErrors`, which now renders not-found on 404 (Task 5); no change needed beyond that.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/users.test.ts components/Embargo/__tests__`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add lib/users.ts lib/__tests__/users.test.ts components/Embargo/ components/DatasetDetailsPage.tsx components/DatasetDetails/
git commit -m "feat: embargo status and settings on the dataset page"
```

---

### Task 9: Embargo choice at creation

**Files:**
- Create: `components/Embargo/EmbargoChoice.tsx`
- Modify: `types/new-dataset.d.ts` (`FormValues`), `pages/app/datasets/new.tsx`
- Test: `components/Embargo/__tests__/EmbargoChoice.test.tsx`

**Interfaces:**
- Consumes: `embargoRequestFrom`, `validateEmbargoDate`, `minEmbargoDate`, `maxEmbargoDate`, `EmbargoMode` (Task 3); `BFFAPI.setEmbargo` (Task 6).
- Produces: `EmbargoChoice` — Formik fields `embargoMode` and `embargoUntil` (must be rendered inside a `<Formik>`).

- [ ] **Step 1: Write the failing test**

`components/Embargo/__tests__/EmbargoChoice.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react';
import { Form, Formik } from "formik";
import { EmbargoChoice } from "../EmbargoChoice";

function renderChoice() {
    const values: any = {};
    render(
        <Formik initialValues={{ embargoMode: "none", embargoUntil: "" }} onSubmit={() => undefined}>
            {(formik) => {
                Object.assign(values, formik.values);
                return <Form><EmbargoChoice /></Form>;
            }}
        </Formik>
    );
    return values;
}

describe("EmbargoChoice", () => {
    test("no embargo by default, and no date asked", () => {
        renderChoice();

        expect((screen.getByLabelText("No embargo") as HTMLInputElement).checked).toBe(true);
        expect(screen.queryByLabelText("Embargo until")).toBeNull();
    });

    test("choosing an embargo asks for a date within 90 days", () => {
        renderChoice();

        fireEvent.click(screen.getByLabelText("Embargo, hidden"));

        const date = screen.getByLabelText("Embargo until") as HTMLInputElement;
        expect(date.max).not.toBe("");
        expect(date.min).not.toBe("");
    });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx jest components/Embargo/__tests__/EmbargoChoice.test.tsx`
Expected: FAIL — `Cannot find module '../EmbargoChoice'`.

- [ ] **Step 3: Implement**

`components/Embargo/EmbargoChoice.tsx` — styled like the blocks of `pages/app/datasets/new.tsx` since #101 (`flex flex-col gap-2`, `text-sm font-semibold` label, `text-[13px]` hint), with each option a bordered row:

```tsx
import { ErrorMessage, Field, useFormikContext } from "formik";
import { EDIT_FORM_ERROR_CLASS, EDIT_FORM_INPUT_CLASS } from "../../contants/EditFormConstants";
import { maxEmbargoDate, minEmbargoDate } from "../../lib/embargoDates";

const OPTIONS = [
    { value: "none", label: "No embargo", hint: "The namespace reaches the files as soon as they are uploaded." },
    { value: "hidden", label: "Embargo, hidden", hint: "Nobody without access knows the dataset exists." },
    { value: "open", label: "Embargo, visible with a badge", hint: "The namespace sees it in listings; files stay closed." },
];

export function EmbargoChoice() {
    const { values } = useFormikContext<{ embargoMode: string, embargoUntil: string }>();
    const now = new Date();

    return (
        <div className="flex flex-col gap-2">
            <span className="text-sm font-semibold text-primary-900">Embargo</span>
            <span className="text-[13px] leading-[19px] text-primary-500">
                Under embargo, only you and the people you authorise reach the files, for up to 90 days,
                extendable. Use it while the article that describes the data is under review.
            </span>
            <fieldset className="flex flex-col gap-2 m-0 p-0 border-0">
                {OPTIONS.map(option => (
                    <div key={option.value} className={`rounded-md border px-3.5 py-3 ${values.embargoMode === option.value ? "border-primary-900 bg-primary-0" : "border-primary-300 bg-primary-0"}`}>
                        <label className="flex gap-2.5 items-center m-0 text-sm font-medium text-primary-900 cursor-pointer">
                            <Field type="radio" name="embargoMode" value={option.value} className="h-4 w-4 p-0 accent-primary-900" /> {option.label}
                        </label>
                        <p className="m-0 mt-0.5 pl-[26px] text-[13px] leading-[19px] text-primary-500">{option.hint}</p>
                    </div>
                ))}
            </fieldset>
            {values.embargoMode !== "none" &&
                <div className="flex flex-col gap-1.5 pt-1">
                    <label htmlFor="embargoUntil" className="m-0 text-sm font-semibold text-primary-900">Embargo until</label>
                    <Field type="date" id="embargoUntil" name="embargoUntil" min={minEmbargoDate(now)} max={maxEmbargoDate(now)} className={EDIT_FORM_INPUT_CLASS} />
                    <ErrorMessage name="embargoUntil" component="div" className={EDIT_FORM_ERROR_CLASS} />
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
}
```

`pages/app/datasets/new.tsx` (as on main since #101):

1. Imports: `import { EmbargoChoice } from "../../../components/Embargo/EmbargoChoice";` and `import { embargoRequestFrom, validateEmbargoDate } from "../../../lib/embargoDates";`.
2. `initialValues` gains `embargoMode: 'none', embargoUntil: ''`.
3. In `handleValidateForm`, before `return errors;`:

```ts
    if (values.embargoMode && values.embargoMode !== "none") {
      const message = validateEmbargoDate(values.embargoUntil, new Date());
      if (message) {
        errors.embargoUntil = message;
      }
    }
```

4. In `handleSubmitForm`, the chain starts with the embargo, so no file is uploaded to a dataset the tenancy can still read. Replace the first two links (`uploadFiles()` and `.then(() => updateDataset(datasetUpdateRequest))`) with:

```ts
    const embargoRequest = embargoRequestFrom(values);
    const datasetId = datasetPrototyping.createDatasetResponseV2.id;

    (embargoRequest ? bffGateway.setEmbargo(datasetId, embargoRequest) : Promise.resolve(null))
      .then(() => uploadFiles())
      .then(() => updateDataset(datasetUpdateRequest))
```

The rest of the chain (`.then(() => { … publishDatasetVersion … })` onward) is unchanged.

5. Render `<EmbargoChoice />` between the *Title* block (the `flex flex-col gap-2` div that ends with the `text-[13px]` hint "Give a unique name for your dataset…") and the *Data files* block (the `flex flex-col gap-2` div that starts with `<span className="text-sm font-semibold text-primary-900">Data files</span>`). Both are children of the `flex flex-col gap-10` column, so the spacing comes from it.

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx jest components/Embargo/__tests__/EmbargoChoice.test.tsx lib/__tests__/embargoDates.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add components/Embargo/EmbargoChoice.tsx components/Embargo/__tests__/EmbargoChoice.test.tsx types/new-dataset.d.ts pages/app/datasets/new.tsx
git commit -m "feat: choose an embargo when creating a dataset"
```

---

### Task 10: Share dialog

**Files:**
- Create: `hooks/UseDebouncedValue.ts`
- Create: `contants/ShareConstants.ts`, `components/Share/PersonInitial.tsx`, `components/Share/ShareInput.tsx`, `components/Share/OneTimeLink.tsx`, `components/Share/AccessList.tsx`, `components/Share/ReviewLinksSection.tsx`, `components/Share/ShareDialog.tsx`, `components/Share/ShareButton.tsx`
- Modify: `components/DatasetDetailsPage.tsx`
- Test: `components/Share/__tests__/ShareInput.test.tsx`, `components/Share/__tests__/AccessList.test.tsx`, `components/Share/__tests__/ReviewLinksSection.test.tsx`, `components/Share/__tests__/ShareDialog.test.tsx`

**Interfaces:**
- Consumes: `classifyShareInput` (Task 3); BFFAPI methods (Task 6); `messageForApiError`, `EMBARGO_ERROR_MESSAGES`, `REVIEW_LINK_LABEL_MAX` (Task 1); `formatEmbargoDate` (Task 3); SWR key `/api/datasets/{id}/share`.
- Produces:
  - `useDebouncedValue<T>(value: T, delayMs: number): T`
  - `ShareInput({ datasetId, onGrant(request: GrantRequest): Promise<void> })`
  - `OneTimeLink({ link, onDismiss })`
  - `AccessList({ state, onChangeLevel(userId, level), onRevokePermission(userId), onRevokeInvitation(id), onRegenerateLink(id) })`
  - `ReviewLinksSection({ links, embargoActive, onCreate(label): Promise<void>, onRevoke(id) })`
  - `ShareDialog({ dataset, show, onClose })`, `ShareButton({ dataset })`

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
    searchShareCandidates.mockResolvedValue([{ id: "u2", name: "Ana Souza", email: "ana@usp.br" }]);
});

function type(text: string) {
    fireEvent.change(screen.getByLabelText("Add people"), { target: { value: text } });
}

describe("ShareInput", () => {
    test("searches the namespace once the typing settles", async () => {
        render(<ShareInput datasetId="d1" onGrant={jest.fn() as any} />);

        type("an");
        type("ana");
        expect(searchShareCandidates).not.toHaveBeenCalled();
        act(() => { jest.advanceTimersByTime(300); });

        await waitFor(() => expect(searchShareCandidates).toHaveBeenCalledTimes(1));
        expect(searchShareCandidates).toHaveBeenCalledWith("d1", "ana");
        expect(await screen.findByRole("button", { name: /Ana Souza/ })).toBeTruthy();
    });

    test("picking a suggestion grants to that user at the chosen level", async () => {
        const onGrant = jest.fn().mockResolvedValue(undefined) as any;
        render(<ShareInput datasetId="d1" onGrant={onGrant} />);

        fireEvent.change(screen.getByLabelText("Access level"), { target: { value: "write" } });
        type("ana");
        act(() => { jest.advanceTimersByTime(300); });
        fireEvent.click(await screen.findByRole("button", { name: /Ana Souza/ }));

        await waitFor(() => expect(onGrant).toHaveBeenCalledWith({ user_id: "u2", level: "write" }));
    });

    test("an email is offered as an invitation, without searching", async () => {
        const onGrant = jest.fn().mockResolvedValue(undefined) as any;
        render(<ShareInput datasetId="d1" onGrant={onGrant} />);

        type("guest@uni.edu");
        act(() => { jest.advanceTimersByTime(300); });
        fireEvent.click(screen.getByRole("button", { name: "Invite guest@uni.edu" }));

        await waitFor(() => expect(onGrant).toHaveBeenCalledWith({ email: "guest@uni.edu", level: "read" }));
        expect(searchShareCandidates).not.toHaveBeenCalled();
    });

    test("an ORCID URL is offered as an invitation by ORCID", async () => {
        const onGrant = jest.fn().mockResolvedValue(undefined) as any;
        render(<ShareInput datasetId="d1" onGrant={onGrant} />);

        type("https://orcid.org/0000-0002-1825-0097");
        fireEvent.click(screen.getByRole("button", { name: "Invite 0000-0002-1825-0097" }));

        await waitFor(() => expect(onGrant).toHaveBeenCalledWith({ orcid: "0000-0002-1825-0097", level: "read" }));
    });

    test("a mistyped ORCID is refused on the spot", () => {
        render(<ShareInput datasetId="d1" onGrant={jest.fn() as any} />);

        type("0000-0002-1825-0098");

        expect(screen.getByText("This ORCID is not valid. Check the last digit.")).toBeTruthy();
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
    owner: { id: "o", name: "Olga Owner", email: "olga@usp.br" },
    permissions: [{ user: { id: "u2", name: "Ana Souza", email: "ana@usp.br" }, level: "read", granted_at: "2026-09-30T10:00:00+00:00", granted_by: "o" }],
    invitations: [
        { id: "i1", email: "guest@uni.edu", orcid: null, level: "read", created_at: "2026-09-30T10:00:00+00:00", accepted_at: null, accepted_by: null, revoked_at: null },
        { id: "i2", email: null, orcid: "0000-0002-1825-0097", level: "write", created_at: "2026-09-29T10:00:00+00:00", accepted_at: "2026-09-30T09:00:00+00:00", accepted_by: { id: "u3", name: "Bruno", email: "bruno@gmail.com" }, revoked_at: null },
        { id: "i3", email: "gone@uni.edu", orcid: null, level: "read", created_at: "2026-09-28T10:00:00+00:00", accepted_at: null, accepted_by: null, revoked_at: "2026-09-29T10:00:00+00:00" },
    ],
    review_links: [],
};

function renderList(handlers: any = {}) {
    render(<AccessList
        state={state}
        onChangeLevel={handlers.onChangeLevel ?? jest.fn()}
        onRevokePermission={handlers.onRevokePermission ?? jest.fn()}
        onRevokeInvitation={handlers.onRevokeInvitation ?? jest.fn()}
        onRegenerateLink={handlers.onRegenerateLink ?? jest.fn()}
    />);
}

describe("AccessList", () => {
    test("lists the owner, the permissions and the pending invitation", () => {
        renderList();

        expect(screen.getByText(/Olga Owner/)).toBeTruthy();
        expect(screen.getByText(/Ana Souza/)).toBeTruthy();
        expect(screen.getByText(/guest@uni.edu/).textContent).toContain("pending");
    });

    test("shows which account accepted an invitation", () => {
        renderList();

        expect(screen.getByText(/Accepted by Bruno/)).toBeTruthy();
    });

    test("hides revoked invitations", () => {
        renderList();

        expect(screen.queryByText(/gone@uni.edu/)).toBeNull();
    });

    test("changes a level and revokes", () => {
        const onChangeLevel = jest.fn();
        const onRevokePermission = jest.fn();
        renderList({ onChangeLevel, onRevokePermission });

        fireEvent.change(screen.getByLabelText("Access level for Ana Souza"), { target: { value: "write" } });
        fireEvent.click(screen.getByRole("button", { name: "Remove Ana Souza" }));

        expect(onChangeLevel).toHaveBeenCalledWith("u2", "write");
        expect(onRevokePermission).toHaveBeenCalledWith("u2");
    });

    test("a pending invitation can get a new link or be revoked", () => {
        const onRegenerateLink = jest.fn();
        const onRevokeInvitation = jest.fn();
        renderList({ onRegenerateLink, onRevokeInvitation });

        fireEvent.click(screen.getByRole("button", { name: "New link for guest@uni.edu" }));
        fireEvent.click(screen.getByRole("button", { name: "Revoke invitation for guest@uni.edu" }));

        expect(onRegenerateLink).toHaveBeenCalledWith("i1");
        expect(onRevokeInvitation).toHaveBeenCalledWith("i1");
    });
});
```

`components/Share/__tests__/ReviewLinksSection.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ReviewLinksSection } from "../ReviewLinksSection";

const links: any = [
    { id: "r1", label: "JGR, round 1", created_at: "2026-09-01T10:00:00+00:00", revoked_at: null, views: { count: 12, first_at: "2026-09-02T10:00:00+00:00", last_at: "2026-09-20T10:00:00+00:00" } },
    { id: "r2", label: "Nature, round 1", created_at: "2026-09-10T10:00:00+00:00", revoked_at: null, views: { count: 0, first_at: null, last_at: null } },
];

describe("ReviewLinksSection", () => {
    test("shows how each link was used, without saying by whom", () => {
        render(<ReviewLinksSection links={links} embargoActive onCreate={jest.fn() as any} onRevoke={jest.fn()} />);

        expect(screen.getByText(/Opened 12 times/)).toBeTruthy();
        expect(screen.getByText(/Not opened yet/)).toBeTruthy();
    });

    test("warns that free text is not redacted", () => {
        render(<ReviewLinksSection links={[]} embargoActive onCreate={jest.fn() as any} onRevoke={jest.fn()} />);

        expect(screen.getByText(/description and other free text are shown as written/)).toBeTruthy();
    });

    test("creates a link with a label", async () => {
        const onCreate = jest.fn().mockResolvedValue(undefined) as any;
        render(<ReviewLinksSection links={[]} embargoActive onCreate={onCreate} onRevoke={jest.fn()} />);

        fireEvent.change(screen.getByLabelText("Label, seen only by you"), { target: { value: "JGR, round 2" } });
        fireEvent.click(screen.getByRole("button", { name: "Create reviewer link" }));

        await waitFor(() => expect(onCreate).toHaveBeenCalledWith("JGR, round 2"));
    });

    test("no link can be created without an embargo", () => {
        render(<ReviewLinksSection links={[]} embargoActive={false} onCreate={jest.fn() as any} onRevoke={jest.fn()} />);

        expect(screen.queryByRole("button", { name: "Create reviewer link" })).toBeNull();
        expect(screen.getByText(/exist only while the dataset is under embargo/)).toBeTruthy();
    });

    test("revokes a link", () => {
        const onRevoke = jest.fn();
        render(<ReviewLinksSection links={links} embargoActive onCreate={jest.fn() as any} onRevoke={onRevoke} />);

        fireEvent.click(screen.getByRole("button", { name: "Revoke JGR, round 1" }));

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
const searchShareCandidates = jest.fn() as any;
const mutate = jest.fn();

jest.mock("../../../gateways/BFFAPI", () => ({
    BFFAPI: jest.fn().mockImplementation(() => ({ grantAccess, searchShareCandidates })),
}));
jest.mock("swr", () => ({
    __esModule: true,
    default: () => ({
        data: { owner: { id: "o", name: "Olga", email: "olga@usp.br" }, permissions: [], invitations: [], review_links: [] },
        error: undefined,
        mutate,
    }),
}));

import { ShareDialog } from "../ShareDialog";

const dataset: any = { id: "d1", name: "Ozone 2025", embargo: { active: true, until: "2026-12-01T23:59:59+00:00" } };

describe("ShareDialog", () => {
    test("an invitation shows its link once, and the list is refreshed", async () => {
        grantAccess.mockResolvedValue({ kind: "invitation", invitation: { id: "i1" }, link: "https://datamap.pcs.usp.br/invitations/tok" });
        render(<ShareDialog dataset={dataset} show onClose={jest.fn()} />);

        fireEvent.change(screen.getByLabelText("Add people"), { target: { value: "guest@uni.edu" } });
        fireEvent.click(screen.getByRole("button", { name: "Invite guest@uni.edu" }));

        expect(await screen.findByDisplayValue("https://datamap.pcs.usp.br/invitations/tok")).toBeTruthy();
        expect(screen.getByText(/shown only once/)).toBeTruthy();
        await waitFor(() => expect(mutate).toHaveBeenCalled());
    });

    test("a refusal is shown in words", async () => {
        grantAccess.mockRejectedValue({ httpCode: 400, errors: [{ code: "already_has_access" }] });
        render(<ShareDialog dataset={dataset} show onClose={jest.fn()} />);

        fireEvent.change(screen.getByLabelText("Add people"), { target: { value: "guest@uni.edu" } });
        fireEvent.click(screen.getByRole("button", { name: "Invite guest@uni.edu" }));

        expect(await screen.findByText("This person already has access.")).toBeTruthy();
    });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest components/Share/__tests__`
Expected: FAIL — the component modules do not exist.

- [ ] **Step 3: Implement**

The dialog follows the identity of webapp #101: `PopupModal` (white card, `border-b` header, footer with the Close button) widened with `maxWidthClassName`, inputs and selects from `contants/EditFormConstants.ts`, section labels in the uppercase 11px style of `CardItem`, row actions in the text-link style of `components/DatasetDetails/TextActionButton.tsx` (written inline here because those buttons need an `aria-label`, which `TextActionButton` does not take), and the one-time link in the mint `bg-secondary-500` notice.

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

export const SHARE_ROW_ACTION_CLASS = "text-[13px] leading-5 font-medium text-primary-600 hover:text-primary-900 underline-offset-2 hover:underline transition-colors";

export const SHARE_PERSON_NAME_CLASS = "text-sm font-medium text-primary-900";

export const SHARE_PERSON_DETAIL_CLASS = "text-[13px] text-primary-500";
```

`components/Share/PersonInitial.tsx`:

```tsx
export function PersonInitial(props: { name?: string | null }) {
    const initial = (props.name ?? "?").trim().charAt(0).toUpperCase() || "?";

    return (
        <span aria-hidden="true" className="flex flex-none items-center justify-center h-8 w-8 rounded-full bg-primary-200 text-xs font-semibold text-primary-700">
            {initial}
        </span>
    );
}
```

`components/Share/ShareInput.tsx`:

```tsx
import { useEffect, useState } from "react";
import { EDIT_FORM_ERROR_CLASS, EDIT_FORM_INPUT_CLASS, EDIT_FORM_SELECT_CLASS } from "../../contants/EditFormConstants";
import { EMBARGO_ERROR_MESSAGES } from "../../contants/EmbargoConstants";
import { SHARE_PERSON_DETAIL_CLASS, SHARE_PERSON_NAME_CLASS } from "../../contants/ShareConstants";
import { BFFAPI } from "../../gateways/BFFAPI";
import { useDebouncedValue } from "../../hooks/UseDebouncedValue";
import { classifyShareInput } from "../../lib/shareTarget";
import { GrantRequest, PermissionLevel, ShareUser } from "../../types/GatekeeperAPI";
import { PersonInitial } from "./PersonInitial";

interface Props {
    datasetId: string
    onGrant(request: GrantRequest): Promise<void>
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

    return (
        <div className="relative flex flex-col gap-2">
            <div className="flex gap-2">
                <label htmlFor="share-input" className="sr-only">Add people</label>
                <input
                    id="share-input"
                    type="text"
                    autoComplete="off"
                    className={EDIT_FORM_INPUT_CLASS}
                    placeholder="Add people by name, email or ORCID"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                />
                <label htmlFor="share-level" className="sr-only">Access level</label>
                <select
                    id="share-level"
                    className={`${EDIT_FORM_SELECT_CLASS} w-36 flex-none`}
                    value={level}
                    onChange={(e) => setLevel(e.target.value as PermissionLevel)}
                >
                    <option value="read">Can view</option>
                    <option value="write">Can edit</option>
                </select>
            </div>

            {target.kind === "invalid_orcid" &&
                <p className={`${EDIT_FORM_ERROR_CLASS} m-0`}>{EMBARGO_ERROR_MESSAGES.invalid_orcid}</p>
            }

            {(target.kind === "email" || target.kind === "orcid") &&
                <button
                    type="button"
                    className="self-start btn-primary-outline btn-small m-0"
                    onClick={() => grant(target.kind === "email"
                        ? { email: target.value, level }
                        : { orcid: target.value, level })}
                >
                    Invite {target.value}
                </button>
            }

            {target.kind === "text" && suggestions.length > 0 &&
                <ul className="m-0 p-1 list-none rounded-md border border-primary-200 bg-primary-0 shadow-lg shadow-primary-900/10">
                    {suggestions.map((user) => (
                        <li key={user.id}>
                            <button
                                type="button"
                                className="flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left hover:bg-primary-100"
                                onClick={() => grant({ user_id: user.id, level })}
                            >
                                <PersonInitial name={user.name} />
                                <span className="flex flex-col min-w-0">
                                    <span className={SHARE_PERSON_NAME_CLASS}>{user.name}</span>
                                    <span className={`${SHARE_PERSON_DETAIL_CLASS} truncate`}>{user.email}</span>
                                </span>
                            </button>
                        </li>
                    ))}
                </ul>
            }
        </div>
    );
}
```

`components/Share/OneTimeLink.tsx`:

```tsx
import { useState } from "react";
import { MaterialSymbol } from "react-material-symbols";
import { EDIT_FORM_INPUT_CLASS } from "../../contants/EditFormConstants";
import { SHARE_ROW_ACTION_CLASS } from "../../contants/ShareConstants";

interface Props {
    link: string
    onDismiss(): void
}

export function OneTimeLink(props: Props) {
    const [copied, setCopied] = useState(false);

    async function copy() {
        await navigator.clipboard?.writeText(props.link);
        setCopied(true);
    }

    return (
        <div className="flex flex-col gap-2.5 rounded-lg border border-primary-200 bg-secondary-500 p-4">
            <p className="m-0 text-sm font-semibold text-primary-900">This link is shown only once. Copy it now and send it yourself.</p>
            <div className="flex gap-2">
                <label htmlFor="one-time-link" className="sr-only">Link</label>
                <input id="one-time-link" readOnly className={`${EDIT_FORM_INPUT_CLASS} font-mono text-xs`} value={props.link} onFocus={(e) => e.target.select()} />
                <button type="button" className="inline-flex flex-none items-center gap-1.5 h-10 px-3.5 rounded-md bg-primary-900 text-primary-50 text-[13px] font-semibold whitespace-nowrap hover:bg-primary-800 transition-colors" onClick={copy}>
                    <MaterialSymbol icon="content_copy" size={16} grade={-25} weight={400} /> {copied ? "Copied" : "Copy"}
                </button>
            </div>
            <button type="button" className={`self-start ${SHARE_ROW_ACTION_CLASS}`} onClick={props.onDismiss}>Done</button>
        </div>
    );
}
```

`components/Share/AccessList.tsx`:

```tsx
import { EDIT_FORM_SELECT_CLASS } from "../../contants/EditFormConstants";
import { SHARE_PERSON_DETAIL_CLASS, SHARE_PERSON_NAME_CLASS, SHARE_ROW_ACTION_CLASS, SHARE_SECTION_LABEL_CLASS } from "../../contants/ShareConstants";
import { PermissionLevel, ShareState } from "../../types/GatekeeperAPI";
import { PersonInitial } from "./PersonInitial";

interface Props {
    state: ShareState
    onChangeLevel(userId: string, level: PermissionLevel): void
    onRevokePermission(userId: string): void
    onRevokeInvitation(invitationId: string): void
    onRegenerateLink(invitationId: string): void
}

export function AccessList(props: Props) {
    const invitations = props.state.invitations.filter((invitation) => !invitation.revoked_at);

    return (
        <section className="flex flex-col gap-2" aria-labelledby="access-list-title">
            <h4 id="access-list-title" className={SHARE_SECTION_LABEL_CLASS}>People with access</h4>
            <ul className="m-0 p-0 list-none divide-y divide-primary-100">
                <li className="flex justify-between items-center gap-3 py-3">
                    <span className="flex items-center gap-3 min-w-0">
                        <PersonInitial name={props.state.owner.name} />
                        <span className="flex flex-col min-w-0">
                            <span className={SHARE_PERSON_NAME_CLASS}>{props.state.owner.name}</span>
                            <span className={`${SHARE_PERSON_DETAIL_CLASS} truncate`}>{props.state.owner.email}</span>
                        </span>
                    </span>
                    <span className="text-[13px] font-medium text-primary-500">Owner</span>
                </li>

                {props.state.permissions.map((permission) => (
                    <li key={permission.user.id} className="flex justify-between items-center gap-3 py-3">
                        <span className="flex items-center gap-3 min-w-0">
                            <PersonInitial name={permission.user.name} />
                            <span className="flex flex-col min-w-0">
                                <span className={SHARE_PERSON_NAME_CLASS}>{permission.user.name}</span>
                                <span className={`${SHARE_PERSON_DETAIL_CLASS} truncate`}>{permission.user.email}</span>
                            </span>
                        </span>
                        <span className="flex flex-none items-center gap-3">
                            <label htmlFor={`level-${permission.user.id}`} className="sr-only">Access level for {permission.user.name}</label>
                            <select
                                id={`level-${permission.user.id}`}
                                className={`${EDIT_FORM_SELECT_CLASS} h-9 w-32`}
                                value={permission.level}
                                onChange={(e) => props.onChangeLevel(permission.user.id, e.target.value as PermissionLevel)}
                            >
                                <option value="read">Can view</option>
                                <option value="write">Can edit</option>
                            </select>
                            <button
                                type="button"
                                aria-label={`Remove ${permission.user.name}`}
                                className={SHARE_ROW_ACTION_CLASS}
                                onClick={() => props.onRevokePermission(permission.user.id)}
                            >
                                Remove
                            </button>
                        </span>
                    </li>
                ))}

                {invitations.map((invitation) => {
                    const who = invitation.email ?? invitation.orcid;
                    return (
                        <li key={invitation.id} className="flex justify-between items-center gap-3 py-3">
                            <span className="flex items-center gap-3 min-w-0">
                                <PersonInitial name={who} />
                                {invitation.accepted_by
                                    ? <span className={SHARE_PERSON_NAME_CLASS}>{who} <span className={SHARE_PERSON_DETAIL_CLASS}>Accepted by {invitation.accepted_by.name} ({invitation.accepted_by.email})</span></span>
                                    : <span className={SHARE_PERSON_NAME_CLASS}>{who} <span className={SHARE_PERSON_DETAIL_CLASS}>· pending</span></span>
                                }
                            </span>
                            {!invitation.accepted_at &&
                                <span className="flex flex-none gap-3">
                                    <button type="button" aria-label={`New link for ${who}`} className={SHARE_ROW_ACTION_CLASS} onClick={() => props.onRegenerateLink(invitation.id)}>
                                        New link
                                    </button>
                                    <button type="button" aria-label={`Revoke invitation for ${who}`} className={SHARE_ROW_ACTION_CLASS} onClick={() => props.onRevokeInvitation(invitation.id)}>
                                        Revoke
                                    </button>
                                </span>
                            }
                        </li>
                    );
                })}
            </ul>
        </section>
    );
}
```

`components/Share/ReviewLinksSection.tsx`:

```tsx
import { useState } from "react";
import { EDIT_FORM_HINT_CLASS, EDIT_FORM_INPUT_CLASS, EDIT_FORM_LABEL_CLASS } from "../../contants/EditFormConstants";
import { REVIEW_LINK_LABEL_MAX } from "../../contants/EmbargoConstants";
import { SHARE_PERSON_DETAIL_CLASS, SHARE_PERSON_NAME_CLASS, SHARE_ROW_ACTION_CLASS, SHARE_SECTION_LABEL_CLASS } from "../../contants/ShareConstants";
import { formatEmbargoDate } from "../../lib/embargoDates";
import { ReviewLink } from "../../types/GatekeeperAPI";

interface Props {
    links: ReviewLink[]
    embargoActive: boolean
    onCreate(label: string): Promise<void>
    onRevoke(linkId: string): void
}

export function ReviewLinksSection(props: Props) {
    const [label, setLabel] = useState("");
    const [creating, setCreating] = useState(false);

    async function create() {
        setCreating(true);
        try {
            await props.onCreate(label.trim());
            setLabel("");
        } finally {
            setCreating(false);
        }
    }

    return (
        <section className="flex flex-col gap-2.5 border-t border-primary-200 pt-5" aria-labelledby="review-links-title">
            <h4 id="review-links-title" className={SHARE_SECTION_LABEL_CLASS}>Reviewer links</h4>
            <p className={EDIT_FORM_HINT_CLASS}>
                A reviewer link lets a venue&apos;s reviewers read the metadata without an account. Authors, contacts,
                collaborators, institution, project and references are redacted, and no file can be downloaded.
                The description and other free text are shown as written: check that they do not name you.
            </p>

            {!props.embargoActive &&
                <p className="m-0 text-sm text-primary-700">Reviewer links exist only while the dataset is under embargo.</p>
            }

            {props.embargoActive &&
                <div className="flex gap-2 items-end">
                    <div className="w-full">
                        <label htmlFor="review-link-label" className={EDIT_FORM_LABEL_CLASS}>Label, seen only by you</label>
                        <input
                            id="review-link-label"
                            type="text"
                            className={EDIT_FORM_INPUT_CLASS}
                            maxLength={REVIEW_LINK_LABEL_MAX}
                            placeholder="e.g. JGR Atmospheres, round 1"
                            value={label}
                            onChange={(e) => setLabel(e.target.value)}
                        />
                    </div>
                    <button
                        type="button"
                        className="flex-none h-10 px-3.5 rounded-md bg-primary-900 text-primary-50 text-[13px] font-semibold whitespace-nowrap hover:bg-primary-800 transition-colors disabled:opacity-50"
                        disabled={creating || label.trim() === ""}
                        onClick={create}
                    >
                        Create reviewer link
                    </button>
                </div>
            }

            <ul className="m-0 p-0 list-none divide-y divide-primary-100">
                {props.links.map((link) => (
                    <li key={link.id} className="flex justify-between items-center gap-3 py-3">
                        <span className="flex flex-col min-w-0">
                            <span className={SHARE_PERSON_NAME_CLASS}>{link.label}</span>
                            <span className={SHARE_PERSON_DETAIL_CLASS}>
                                {link.revoked_at
                                    ? "Revoked"
                                    : link.views.count === 0
                                        ? "Not opened yet"
                                        : `Opened ${link.views.count} times · first ${formatEmbargoDate(link.views.first_at)} · last ${formatEmbargoDate(link.views.last_at)}`}
                            </span>
                        </span>
                        {!link.revoked_at &&
                            <button type="button" aria-label={`Revoke ${link.label}`} className={`flex-none ${SHARE_ROW_ACTION_CLASS}`} onClick={() => props.onRevoke(link.id)}>
                                Revoke
                            </button>
                        }
                    </li>
                ))}
            </ul>
        </section>
    );
}
```

`components/Share/ShareDialog.tsx`:

```tsx
import { useState } from "react";
import useSWR from "swr";
import { messageForApiError } from "../../contants/EmbargoConstants";
import { BFFAPI } from "../../gateways/BFFAPI";
import { fetcher } from "../../lib/fetcher";
import { GetDatasetDetailsResponse } from "../../types/BffAPI";
import { GrantRequest, PermissionLevel, ShareState } from "../../types/GatekeeperAPI";
import Modal from "../base/PopupModal";
import { AccessList } from "./AccessList";
import { OneTimeLink } from "./OneTimeLink";
import { ReviewLinksSection } from "./ReviewLinksSection";
import { ShareInput } from "./ShareInput";

interface Props {
    dataset: GetDatasetDetailsResponse
    show: boolean
    onClose(): void
}

export function ShareDialog(props: Props) {
    const [bffGateway] = useState(() => new BFFAPI());
    const [error, setError] = useState<string | null>(null);
    const [oneTimeLink, setOneTimeLink] = useState<string | null>(null);
    const datasetId = props.dataset.id;

    const { data, error: loadError, mutate } = useSWR(props.show ? `/api/datasets/${datasetId}/share` : null, fetcher);
    const state = data as ShareState;

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
        if (result?.kind === "invitation") {
            setOneTimeLink(result.link);
        }
    }

    return (
        <Modal
            title={`Share “${props.dataset.name}”`}
            show={props.show}
            confimButtonText=""
            cancelButtonText="Close"
            cancel={props.onClose}
            maxWidthClassName="max-w-2xl"
        >
            <div className="flex flex-col gap-5">
                {error && <p role="alert" className="m-0 text-sm text-error-600">{error}</p>}
                {oneTimeLink && <OneTimeLink link={oneTimeLink} onDismiss={() => setOneTimeLink(null)} />}

                <ShareInput datasetId={datasetId} onGrant={onGrant} />

                {loadError && <p className="m-0 text-sm text-error-600">The people with access could not be loaded.</p>}
                {state &&
                    <AccessList
                        state={state}
                        onChangeLevel={(userId, level: PermissionLevel) => run(() => bffGateway.changePermissionLevel(datasetId, userId, level))}
                        onRevokePermission={(userId) => run(() => bffGateway.revokePermission(datasetId, userId))}
                        onRevokeInvitation={(id) => run(() => bffGateway.revokeInvitation(datasetId, id))}
                        onRegenerateLink={async (id) => {
                            const result = await run(() => bffGateway.regenerateInvitationLink(datasetId, id));
                            if (result) setOneTimeLink(result.link);
                        }}
                    />
                }

                {state &&
                    <ReviewLinksSection
                        links={state.review_links}
                        embargoActive={props.dataset.embargo?.active === true}
                        onCreate={async (label) => {
                            const result = await run(() => bffGateway.createReviewLink(datasetId, label));
                            if (result) setOneTimeLink(result.link);
                        }}
                        onRevoke={(id) => run(() => bffGateway.revokeReviewLink(datasetId, id))}
                    />
                }
            </div>
        </Modal>
    );
}
```

`components/Share/ShareButton.tsx` — an outline twin of the dark *Download* button in the dataset header (`components/DownloadDatafilesButton.tsx`):

```tsx
import { useState } from "react";
import { MaterialSymbol } from "react-material-symbols";
import { GetDatasetDetailsResponse } from "../../types/BffAPI";
import { ShareDialog } from "./ShareDialog";

export function ShareButton(props: { dataset: GetDatasetDetailsResponse }) {
    const [show, setShow] = useState(false);

    return (
        <>
            <button
                type="button"
                className="inline-flex items-center gap-2 h-[38px] px-3.5 rounded-md border border-primary-300 bg-primary-0 text-primary-900 text-sm font-semibold whitespace-nowrap hover:bg-primary-100 transition-colors"
                onClick={() => setShow(true)}
            >
                <MaterialSymbol icon="person_add" size={18} grade={-25} weight={400} /> Share
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

- [ ] **Step 5: Commit**

```bash
git add hooks/UseDebouncedValue.ts contants/ShareConstants.ts components/Share/ components/DatasetDetailsPage.tsx
git commit -m "feat: share dialog with tenancy search, invitations and reviewer links"
```

---

### Task 11: Anonymous review page

**Files:**
- Create: `lib/reviewMetadata.ts`, `lib/reviewPage.ts`, `components/Review/ReviewMetadataList.tsx`, `pages/review/[token].tsx`
- Test: `lib/__tests__/reviewMetadata.test.ts`, `lib/__tests__/reviewPage.test.ts`, `components/Review/__tests__/ReviewMetadataList.test.tsx`

**Interfaces:**
- Consumes: `getReviewPage` (Task 4), `REDACTED` (Task 1), `ROUTE_PAGE_DATASETS_SNAPSHOTS_DETAILS` (existing), `ReviewPageResponse` (Task 1).
- Produces: `displayValue(value: unknown): string`, `reviewMetadataEntries(data): { key, label, value, redacted }[]`, `reviewPageProps(page: ReviewPageResponse)`, `ReviewMetadataList({ data })`.

- [ ] **Step 1: Write the failing tests**

`lib/__tests__/reviewMetadata.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import { displayValue, reviewMetadataEntries } from "../reviewMetadata";

describe("displayValue", () => {
    test("a redacted list keeps its length", () => {
        expect(displayValue([{ name: "[redacted]" }, { name: "[redacted]" }, { name: "[redacted]" }]))
            .toBe("[redacted], [redacted], [redacted]");
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

describe("reviewMetadataEntries", () => {
    test("marks redacted rows, skips the description, labels known keys", () => {
        const entries = reviewMetadataEntries({
            authors: [{ name: "[redacted]" }],
            institution: "[redacted]",
            license: "CC-BY-4.0",
            description: "long text",
            grid_type: "regular",
        });

        expect(entries).toEqual([
            { key: "authors", label: "Authors", value: "[redacted]", redacted: true },
            { key: "grid_type", label: "Grid type", value: "regular", redacted: false },
            { key: "institution", label: "Institution", value: "[redacted]", redacted: true },
            { key: "license", label: "License", value: "CC-BY-4.0", redacted: false },
        ]);
    });
});
```

`lib/__tests__/reviewPage.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import { reviewPageProps } from "../reviewPage";

describe("reviewPageProps", () => {
    test("an active embargo renders the page", () => {
        const page: any = { state: "active", embargo_until: "2026-12-01T23:59:59+00:00", dataset: { name: "x", data: {}, versions: [] } };

        expect(reviewPageProps(page)).toEqual({ props: { page } });
    });

    test("after the embargo, a published dataset redirects to its public page", () => {
        expect(reviewPageProps({ state: "ended", dataset_id: "d1", published: true }))
            .toEqual({ redirect: { destination: "/datasets/d1", permanent: false } });
    });

    test("after the embargo, an unpublished dataset says so", () => {
        expect(reviewPageProps({ state: "ended", dataset_id: "d1", published: false }))
            .toEqual({ props: { ended: true } });
    });
});
```

`components/Review/__tests__/ReviewMetadataList.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { ReviewMetadataList } from "../ReviewMetadataList";

describe("ReviewMetadataList", () => {
    test("shows redacted fields as redacted, and the rest as they are", () => {
        render(<ReviewMetadataList data={{ authors: [{ name: "[redacted]" }, { name: "[redacted]" }], license: "CC-BY-4.0" }} />);

        expect(screen.getByText("[redacted], [redacted]").className).toContain("italic");
        expect(screen.getByText("CC-BY-4.0")).toBeTruthy();
    });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx jest lib/__tests__/reviewMetadata.test.ts lib/__tests__/reviewPage.test.ts components/Review/__tests__`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement**

`lib/reviewMetadata.ts`:

```ts
import { REDACTED } from "../contants/EmbargoConstants";

const LABELS: Record<string, string> = {
    additional_information: "Additional information",
    authors: "Authors",
    category: "Category",
    citation: "Citation",
    colaborators: "Collaborators",
    contacts: "Contacts",
    creation_date: "Created",
    data_type: "Data type",
    database: "Database",
    end_date: "End date",
    grid_type: "Grid type",
    institution: "Institution",
    level: "Level",
    license: "License",
    location: "Location",
    owner: "Owner",
    project: "Project",
    realm: "Realm",
    reference: "References",
    references: "References",
    resolution: "Resolution",
    source: "Source",
    source_instrument: "Source instrument",
    start_date: "Start date",
    tags: "Tags",
    variables: "Variables",
};

const NOT_LISTED = new Set(["description", "is_enabled", "id", "name", "version"]);

export function displayValue(value: unknown): string {
    if (value === null || value === undefined || value === "") {
        return "—";
    }
    if (Array.isArray(value)) {
        return value.length === 0 ? "—" : value.map(displayValue).join(", ");
    }
    if (typeof value === "object") {
        const parts = Object.values(value as Record<string, unknown>).map(displayValue).filter((part) => part !== "—");
        return parts.length ? parts.join(" · ") : "—";
    }
    return String(value);
}

export function reviewMetadataEntries(data: Record<string, unknown>): { key: string, label: string, value: string, redacted: boolean }[] {
    return Object.keys(data)
        .filter((key) => !NOT_LISTED.has(key))
        .sort()
        .map((key) => {
            const value = displayValue(data[key]);
            return { key, label: LABELS[key] ?? key.replace(/_/g, " "), value, redacted: value.includes(REDACTED) };
        });
}
```

`lib/reviewPage.ts`:

```ts
import { ROUTE_PAGE_DATASETS_SNAPSHOTS_DETAILS } from "../contants/InternalRoutesConstants";
import { ReviewPageResponse } from "../types/GatekeeperAPI";

export function reviewPageProps(page: ReviewPageResponse) {
    if (page.state === "active") {
        return { props: { page } };
    }
    if (page.published) {
        return { redirect: { destination: ROUTE_PAGE_DATASETS_SNAPSHOTS_DETAILS({ id: page.dataset_id }), permanent: false } };
    }
    return { props: { ended: true } };
}
```

`components/Review/ReviewMetadataList.tsx` — one `FactRow` per field, the row component #101 introduced for the dataset page's facts:

```tsx
import { reviewMetadataEntries } from "../../lib/reviewMetadata";
import { FactRow } from "../DatasetDetails/DataCard/FactRow";

export function ReviewMetadataList(props: { data: Record<string, unknown> }) {
    return (
        <div className="flex flex-col">
            {reviewMetadataEntries(props.data).map((entry) => (
                <FactRow
                    key={entry.key}
                    label={entry.label}
                    valueClassName={entry.redacted ? "italic font-normal text-primary-400" : "font-medium"}
                >
                    {entry.value}
                </FactRow>
            ))}
        </div>
    );
}
```

`pages/review/[token].tsx` — laid out like the logged-in dataset page since #101 (`max-w-5xl` column, status pill row, 30px title, white cards), inside the public `Layout`:

```tsx
import Head from "next/head";
import { MaterialSymbol } from "react-material-symbols";
import { Description } from "../../components/DatasetSnapshot/Description";
import Layout from "../../components/Layout";
import { ReviewMetadataList } from "../../components/Review/ReviewMetadataList";
import { formatEmbargoDate } from "../../lib/embargoDates";
import { bytesToSize } from "../../lib/file";
import { reviewPageProps } from "../../lib/reviewPage";
import { getReviewPage } from "../../lib/share";
import { ReviewPageActive } from "../../types/GatekeeperAPI";

interface Props {
    page?: ReviewPageActive
    ended?: boolean
}

export default function ReviewPage(props: Props) {
    return (
        <Layout fluid={true} hideFooter={true}>
            <Head>
                <meta name="robots" content="noindex, nofollow" />
            </Head>
            <div className="mx-auto w-full max-w-5xl px-8 pt-10 pb-24 flex flex-col gap-7">
                {props.ended &&
                    <div className="flex gap-3 items-start rounded-lg border border-primary-200 bg-primary-0 p-6" role="status">
                        <MaterialSymbol icon="lock_open" size={20} grade={-25} weight={400} className="mt-1 text-primary-700" />
                        <div>
                            <h2 className="m-0 text-lg leading-snug tracking-[-0.01em]">The embargo on this dataset has ended</h2>
                            <p className="m-0 mt-1 text-sm text-primary-600">The dataset has not been published yet. Its page will appear here once it is.</p>
                        </div>
                    </div>
                }

                {props.page &&
                    <>
                        <div className="flex gap-3 items-start rounded-lg border border-primary-200 bg-secondary-500 px-4 py-3 text-sm leading-5 text-primary-700" role="note">
                            <MaterialSymbol icon="visibility_off" size={18} grade={-25} weight={400} className="mt-0.5 text-primary-900" />
                            <span>
                                Anonymous copy for review. Information that identifies the authors is redacted.
                                The data are under embargo until {formatEmbargoDate(props.page.embargo_until)} and cannot be downloaded.
                            </span>
                        </div>

                        <div className="flex flex-col gap-2.5 min-w-0">
                            <div className="flex items-center gap-2.5">
                                <span className="inline-flex px-2.5 py-[3px] rounded-full text-xs leading-[18px] font-semibold text-primary-900 bg-secondary-500">For review</span>
                            </div>
                            <h1 className="m-0 text-[30px] leading-[1.2] font-semibold tracking-tight text-primary-900 [text-wrap:balance]">
                                {props.page.dataset.name}
                            </h1>
                        </div>

                        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-10 items-start">
                            <div className="flex flex-col gap-7 min-w-0">
                                <Description title="About Dataset" description={String(props.page.dataset.data.description ?? "")} />

                                <section className="flex flex-col gap-3">
                                    <h2 className="m-0 text-lg leading-7 font-semibold tracking-[-0.01em] text-primary-900">Files</h2>
                                    <div className="rounded-lg border border-primary-200 bg-primary-0 px-4">
                                        {props.page.dataset.versions.map((version) => (
                                            <div key={version.name} className="flex justify-between items-baseline gap-4 py-3 border-b border-primary-100 last:border-b-0 text-sm">
                                                <span className="font-mono text-primary-500">v{version.name}</span>
                                                <span className="text-primary-900">{version.files_summary.count} files · {bytesToSize(version.files_summary.total_size_bytes)}</span>
                                            </div>
                                        ))}
                                    </div>
                                </section>
                            </div>

                            <aside className="rounded-lg border border-primary-200 bg-primary-0 px-4 pt-3 pb-1">
                                <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-primary-500">Metadata</span>
                                <ReviewMetadataList data={props.page.dataset.data} />
                            </aside>
                        </div>
                    </>
                }
            </div>
        </Layout>
    );
}

export async function getServerSideProps({ query }) {
    try {
        return reviewPageProps(await getReviewPage(query.token as string));
    } catch (error) {
        if (error?.response?.status === 404) {
            return { notFound: true };
        }
        throw error;
    }
}
```

`Description` (from `components/DatasetSnapshot`) renders markdown through `react-markdown`; it is used only by the page, which no Jest test imports.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/reviewMetadata.test.ts lib/__tests__/reviewPage.test.ts components/Review/__tests__ contants/__tests__/TelemetryConstants.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/reviewMetadata.ts lib/reviewPage.ts lib/__tests__/reviewMetadata.test.ts lib/__tests__/reviewPage.test.ts components/Review/ "pages/review/[token].tsx"
git commit -m "feat: anonymous reviewer page with redacted metadata"
```

---

### Task 12: DOI landing page

**Files:**
- Create: `lib/doiLanding.ts`, `pages/doi/datasets/[datasetId]/versions/[versionName].tsx`
- Test: `lib/__tests__/doiLanding.test.ts`

**Interfaces:**
- Consumes: `getEmbargoStatus` (Task 4), `ROUTE_PAGE_DATASETS_VERSION_DETAILS` (existing), `formatEmbargoDate` (Task 3).
- Produces: `doiLandingProps(status: EmbargoStatusResponse | null, datasetId, versionName)`.

- [ ] **Step 1: Write the failing test**

`lib/__tests__/doiLanding.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import { doiLandingProps } from "../doiLanding";

describe("doiLandingProps", () => {
    test("under embargo, only the date is shown", () => {
        expect(doiLandingProps({ embargoed: true, until: "2026-12-01T23:59:59+00:00" }, "d1", "2"))
            .toEqual({ props: { until: "2026-12-01T23:59:59+00:00" } });
    });

    test("otherwise it goes where the DOI has always led", () => {
        expect(doiLandingProps({ embargoed: false, until: null }, "d1", "2"))
            .toEqual({ redirect: { destination: "/app/datasets/d1/versions/2", permanent: false } });
    });

    test("when the status cannot be read, it goes there too, and that page enforces access", () => {
        expect(doiLandingProps(null, "d1", "2"))
            .toEqual({ redirect: { destination: "/app/datasets/d1/versions/2", permanent: false } });
    });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx jest lib/__tests__/doiLanding.test.ts`
Expected: FAIL — `Cannot find module '../doiLanding'`.

- [ ] **Step 3: Implement**

`lib/doiLanding.ts`:

```ts
import { ROUTE_PAGE_DATASETS_VERSION_DETAILS } from "../contants/InternalRoutesConstants";
import { EmbargoStatusResponse } from "../types/GatekeeperAPI";

export function doiLandingProps(status: EmbargoStatusResponse | null, datasetId: string, versionName: string) {
    if (status?.embargoed && status.until) {
        return { props: { until: status.until } };
    }
    return {
        redirect: {
            destination: ROUTE_PAGE_DATASETS_VERSION_DETAILS({ id: datasetId, versionName }),
            permanent: false,
        },
    };
}
```

`pages/doi/datasets/[datasetId]/versions/[versionName].tsx`:

```tsx
import Head from "next/head";
import { MaterialSymbol } from "react-material-symbols";
import Layout from "../../../../../components/Layout";
import { doiLandingProps } from "../../../../../lib/doiLanding";
import { getEmbargoStatus } from "../../../../../lib/embargo";
import { formatEmbargoDate } from "../../../../../lib/embargoDates";
import { logError } from "../../../../../lib/logging";

export default function DoiLandingPage(props: { until: string }) {
    return (
        <Layout fluid={true} hideFooter={true}>
            <Head>
                <meta name="robots" content="noindex, nofollow" />
            </Head>
            <div className="mx-auto w-full max-w-lg px-8 pt-16 pb-24">
                <div className="flex flex-col items-center gap-3 rounded-lg border border-primary-200 bg-primary-0 p-8 text-center" role="status">
                    <span className="flex items-center justify-center h-11 w-11 rounded-full bg-secondary-500 text-primary-900">
                        <MaterialSymbol icon="lock_clock" size={22} grade={-25} weight={400} />
                    </span>
                    <h1 className="m-0 text-xl leading-snug font-semibold tracking-[-0.01em] text-primary-900">This dataset is under embargo</h1>
                    <p className="m-0 text-sm leading-5 text-primary-600">
                        Its data will be available after {formatEmbargoDate(props.until)}.
                    </p>
                </div>
            </div>
        </Layout>
    );
}

export async function getServerSideProps({ query }) {
    const datasetId = query.datasetId as string;
    const versionName = query.versionName as string;

    let status = null;
    try {
        status = await getEmbargoStatus(datasetId);
    } catch (error) {
        logError("reading the embargo status failed", error);
    }
    return doiLandingProps(status, datasetId, versionName);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/doiLanding.test.ts contants/__tests__/TelemetryConstants.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/doiLanding.ts lib/__tests__/doiLanding.test.ts "pages/doi/datasets/[datasetId]/versions/[versionName].tsx"
git commit -m "feat: the DOI lands on an embargo notice while the embargo lasts"
```

---

### Task 13: Invitation page and claim on sign-in

**Files:**
- Create: `lib/invitationPage.ts`, `components/Invitation/AcceptInvitation.tsx`, `pages/invitations/[token].tsx`
- Modify: `pages/api/auth/[...nextauth].ts`
- Test: `lib/__tests__/invitationPage.test.ts`, `components/Invitation/__tests__/AcceptInvitation.test.tsx`, `pages/api/auth/__tests__/[...nextauth].test.ts` (append)

**Interfaces:**
- Consumes: `BFFAPI.acceptInvitation` (Task 6), `claimInvitations` (Task 4), `ROUTE_PAGE_LOGIN`, `ROUTE_PAGE_INVITATION`, `ROUTE_PAGE_DATASETS_DETAILS`.
- Produces: `invitationPageProps(signedIn: boolean, token: string, host: string)`, `AcceptInvitation({ token })`, `claimPendingInvitations(uid: string): Promise<void>` (exported from `[...nextauth].ts`).

- [ ] **Step 1: Write the failing tests**

`lib/__tests__/invitationPage.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import { invitationPageProps } from "../invitationPage";

describe("invitationPageProps", () => {
    test("a signed-in user gets the page", () => {
        expect(invitationPageProps(true, "tok", "datamap.pcs.usp.br")).toEqual({ props: { token: "tok" } });
    });

    test("anyone else signs in first and comes back to the same invitation", () => {
        const result: any = invitationPageProps(false, "tok", "datamap.pcs.usp.br");

        expect(result.redirect.permanent).toBe(false);
        expect(result.redirect.destination).toContain("/account/login");
        expect(decodeURIComponent(result.redirect.destination)).toContain("callbackUrl=/invitations/tok");
    });
});
```

`components/Invitation/__tests__/AcceptInvitation.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { render, screen, waitFor } from '@testing-library/react';

const acceptInvitation = jest.fn() as any;
const replace = jest.fn();

jest.mock("../../../gateways/BFFAPI", () => ({
    BFFAPI: jest.fn().mockImplementation(() => ({ acceptInvitation })),
}));
jest.mock("next/router", () => ({ __esModule: true, default: { replace: (url: string) => replace(url) } }));

import { AcceptInvitation } from "../AcceptInvitation";

describe("AcceptInvitation", () => {
    test("accepts once and opens the dataset", async () => {
        acceptInvitation.mockResolvedValue({ dataset_id: "d1", level: "read" });

        render(<AcceptInvitation token="tok" />);

        await waitFor(() => expect(replace).toHaveBeenCalledWith("/app/datasets/d1"));
        expect(acceptInvitation).toHaveBeenCalledTimes(1);
        expect(acceptInvitation).toHaveBeenCalledWith("tok");
    });

    test("an invitation already used says what to do", async () => {
        acceptInvitation.mockRejectedValue({ httpCode: 409 });

        render(<AcceptInvitation token="tok" />);

        expect(await screen.findByText(/already been accepted/)).toBeTruthy();
    });

    test("an invitation revoked or unknown says what to do", async () => {
        acceptInvitation.mockRejectedValue({ httpCode: 404 });

        render(<AcceptInvitation token="tok" />);

        expect(await screen.findByText(/no longer valid/)).toBeTruthy();
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
import { ROUTE_PAGE_INVITATION, ROUTE_PAGE_LOGIN } from "../contants/InternalRoutesConstants";

export function invitationPageProps(signedIn: boolean, token: string, host: string) {
    if (signedIn) {
        return { props: { token } };
    }
    return {
        redirect: {
            destination: ROUTE_PAGE_LOGIN({
                hostname: `https://${host}`,
                callbackUrl: ROUTE_PAGE_INVITATION({ token }),
                error: encodeURIComponent("Sign in to accept the invitation."),
            }),
            permanent: false,
        },
    };
}
```

`components/Invitation/AcceptInvitation.tsx`:

```tsx
import Router from "next/router";
import { useEffect, useRef, useState } from "react";
import { MaterialSymbol } from "react-material-symbols";
import { GENERIC_ERROR_MESSAGE } from "../../contants/EmbargoConstants";
import { ROUTE_PAGE_DATASETS_DETAILS } from "../../contants/InternalRoutesConstants";
import { BFFAPI } from "../../gateways/BFFAPI";

export function AcceptInvitation(props: { token: string }) {
    const started = useRef(false);
    const [message, setMessage] = useState<string | null>(null);

    useEffect(() => {
        if (started.current) {
            return;
        }
        started.current = true;

        new BFFAPI().acceptInvitation(props.token)
            .then((result) => Router.replace(ROUTE_PAGE_DATASETS_DETAILS({ id: result.dataset_id })))
            .catch((error) => {
                if (error?.httpCode === 409) {
                    setMessage("This invitation has already been accepted. If it was not by you, ask the person who invited you for a new link.");
                } else if (error?.httpCode === 404) {
                    setMessage("This invitation is no longer valid. Ask the person who invited you for a new link.");
                } else {
                    setMessage(GENERIC_ERROR_MESSAGE);
                }
            });
    }, [props.token]);

    return (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-primary-200 bg-primary-0 p-8 text-center" role="status">
            <span className="flex items-center justify-center h-11 w-11 rounded-full bg-secondary-500 text-primary-900">
                <MaterialSymbol icon={message ? "info" : "progress_activity"} size={22} grade={-25} weight={400} className={message ? "" : "animate-spin"} />
            </span>
            <p className="m-0 text-sm leading-5 text-primary-700">{message ?? "Accepting the invitation..."}</p>
        </div>
    );
}
```

`pages/invitations/[token].tsx`:

```tsx
import { getToken } from "next-auth/jwt";
import { AcceptInvitation } from "../../components/Invitation/AcceptInvitation";
import Layout from "../../components/Layout";
import { invitationPageProps } from "../../lib/invitationPage";

export default function InvitationPage(props: { token: string }) {
    return (
        <Layout fluid={true} hideFooter={true}>
            <div className="mx-auto w-full max-w-lg px-8 pt-16 pb-24">
                <AcceptInvitation token={props.token} />
            </div>
        </Layout>
    );
}

export async function getServerSideProps({ req, query }) {
    const session = await getToken({ req });
    return invitationPageProps(Boolean(session?.uid), query.token as string, req.headers.host);
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

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx jest lib/__tests__/invitationPage.test.ts components/Invitation/__tests__ "pages/api/auth/__tests__" contants/__tests__/TelemetryConstants.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/invitationPage.ts lib/__tests__/invitationPage.test.ts components/Invitation/ "pages/invitations/[token].tsx" "pages/api/auth/[...nextauth].ts" "pages/api/auth/__tests__/[...nextauth].test.ts"
git commit -m "feat: accept invitations by link, and claim pending ones at sign-in"
```

---

### Task 14: A manual DOI ends the embargo, and only with consent

A manual DOI is managed outside DataMap and is usually already public at DataCite, so the gatekeeper refuses one on an embargoed dataset unless the request says `end_embargo: true` (contracts, *Embargo*). This task makes the DOI form ask first.

**Files:**
- Modify: `types/GatekeeperAPI.ts` (`DOICreationRequest`), `types/BffAPI.ts` (`CreateDOIRequest`)
- Modify: `lib/doi.ts` (`createDOI`)
- Create: `components/Embargo/ManualDoiConfirmation.tsx`
- Modify: `components/DatasetDetails/DatasetCitation.tsx` (`CitationManualDOIForm`, `DOIManagementAlert.errorCodeMapping`)
- Test: `lib/__tests__/doi.test.ts`, `components/Embargo/__tests__/ManualDoiConfirmation.test.tsx`

**Interfaces:**
- Consumes: `manualDoiGate`, `ManualDoiGate` (Task 3); `EMBARGO_ERROR_MESSAGES` with `embargo_manual_doi`, `embargo_manual_doi_ends_embargo` (Task 1).
- Produces: `CreateDOIRequest.endEmbargo?: boolean`; `DOICreationRequest.end_embargo?: boolean`; `ManualDoiConfirmation({ gate, show, onConfirm, onCancel })`.

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

describe("ManualDoiConfirmation", () => {
    test("under embargo, the owner is told what ends and confirms it", () => {
        const onConfirm = jest.fn();
        render(<ManualDoiConfirmation gate="ends_embargo" show onConfirm={onConfirm} onCancel={jest.fn()} />);

        expect(screen.getByText(/usually already public at DataCite/)).toBeTruthy();
        expect(screen.getByText(/This cannot be undone/)).toBeTruthy();
        expect(screen.getByText(/use a DOI generated by DataMap/)).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "End embargo and register DOI" }));

        expect(onConfirm).toHaveBeenCalled();
    });

    test("under embargo, anyone else gets an explanation and nothing to confirm", () => {
        render(<ManualDoiConfirmation gate="owner_only" show onConfirm={jest.fn()} onCancel={jest.fn()} />);

        expect(screen.getByText(/Only the owner of this dataset can end its embargo/)).toBeTruthy();
        expect(screen.queryByRole("button", { name: "End embargo and register DOI" })).toBeNull();
        expect(screen.queryByRole("button", { name: "Register DOI" })).toBeNull();
    });

    test("without an embargo, the user learns it can no longer be embargoed, and confirms", () => {
        const onConfirm = jest.fn();
        render(<ManualDoiConfirmation gate="blocks_future_embargo" show onConfirm={onConfirm} onCancel={jest.fn()} />);

        expect(screen.getByText(/can no longer be put under embargo/)).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Register DOI" }));

        expect(onConfirm).toHaveBeenCalled();
    });

    test("cancel sends nothing", () => {
        const onConfirm = jest.fn();
        const onCancel = jest.fn();
        render(<ManualDoiConfirmation gate="ends_embargo" show onConfirm={onConfirm} onCancel={onCancel} />);

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

`components/Embargo/ManualDoiConfirmation.tsx`:

```tsx
import { ManualDoiGate } from "../../lib/embargoState";
import Modal from "../base/PopupModal";

interface Props {
    gate: ManualDoiGate
    show: boolean
    onConfirm(): void
    onCancel(): void
}

export function ManualDoiConfirmation(props: Props) {
    if (props.gate === "owner_only") {
        return (
            <Modal title="Only the owner can do this" show={props.show} confimButtonText="" cancelButtonText="Close" cancel={props.onCancel}>
                <p className="m-0">
                    A manual DOI is managed outside DataMap and is usually already public at DataCite, so registering
                    one ends the embargo. Only the owner of this dataset can end its embargo.
                </p>
                <p className="m-0 mt-2">To keep the embargo, use a DOI generated by DataMap.</p>
            </Modal>
        );
    }

    if (props.gate === "ends_embargo") {
        return (
            <Modal
                title="Registering a manual DOI ends the embargo"
                show={props.show}
                confimButtonText="End embargo and register DOI"
                cancelButtonText="Cancel"
                destructive
                cancel={props.onCancel}
                confim={props.onConfirm}
            >
                <p className="m-0">
                    A manual DOI is managed outside DataMap and is usually already public at DataCite. Registering it
                    here ends the embargo: the files become available to the namespace and the dataset&apos;s public
                    page is published. This cannot be undone.
                </p>
                <p className="m-0 mt-2">To keep the embargo, use a DOI generated by DataMap.</p>
            </Modal>
        );
    }

    return (
        <Modal
            title="Register a manual DOI"
            show={props.show}
            confimButtonText="Register DOI"
            cancelButtonText="Cancel"
            cancel={props.onCancel}
            confim={props.onConfirm}
        >
            <p className="m-0">After a manual DOI is registered, this dataset can no longer be put under embargo.</p>
        </Modal>
    );
}
```

- [ ] **Step 5: Wire the DOI form**

`components/DatasetDetails/DatasetCitation.tsx`:

1. Imports: add `import Router from "next/router";`, `import { EMBARGO_ERROR_MESSAGES } from "../../contants/EmbargoConstants";`, `import { manualDoiGate } from "../../lib/embargoState";`, `import { ManualDoiConfirmation } from "../Embargo/ManualDoiConfirmation";`.

2. In `CitationManualDOIForm`, replace the `async function onSubmit(values, { setSubmitting }) { … }` block with:

```tsx
    const gate = manualDoiGate(props.dataset);
    const [pendingIdentifier, setPendingIdentifier] = useState<string | null>(null);
    const [sending, setSending] = useState(false);

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
                show={pendingIdentifier !== null}
                onConfirm={() => send(pendingIdentifier)}
                onCancel={() => setPendingIdentifier(null)}
            />
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

### Task 15: The images the emails show stay where they are served

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

### Task 16: Full verification

**Files:** none changed unless a check fails.

- [ ] **Step 1: Whole test suite**

Run: `npm run test 2>&1 | tail -30`
Expected: `Tests:` line with `0 failed`; `Test Suites:` all passed. Read the exit status separately: `npm run test >/dev/null 2>&1; echo "exit=$?"` → `exit=0`.

- [ ] **Step 2: Type-check and production build**

Run: `npm run build; echo "exit=$?"`
Expected: `exit=0`; the route list includes `/app/datasets/shared`, `/review/[token]`, `/invitations/[token]`, `/doi/datasets/[datasetId]/versions/[versionName]` and the new `/api/...` routes.

- [ ] **Step 3: The images the emails load are served**

Run: `npm run start & sleep 5; for f in datamap-tile-36.png datamap-tile-22.png; do curl -s -o /dev/null -w "$f %{http_code} %{content_type}\n" http://localhost:3000/img/email/$f; done; kill %1`
Expected: `datamap-tile-36.png 200 image/png` and `datamap-tile-22.png 200 image/png`

- [ ] **Step 4: Lint**

Run: `npx next lint; echo "exit=$?"`
Expected: `exit=0` with no errors in the files this plan touched (pre-existing warnings elsewhere are acceptable; do not fix unrelated files).

- [ ] **Step 5: Manual check against a gatekeeper with plans 02 and 03**

With the gatekeeper integration stack up (`make ENV_FILE_PATH=integration-test.env integration-test-up` in the gatekeeper repo) and the webapp's `.env.local` pointing `DATAMAP_BASE_URL` at it, run `npm run dev` and walk through:

1. Create a dataset with *Embargo, hidden* and a date 30 days ahead → the dataset page shows the badge; the Settings tab shows the embargo section.
2. Share → type a colleague's name from the tenancy → pick → they appear under *Who has access*.
3. Share → type an unknown email → *Invite* → the one-time link appears once.
4. Create a reviewer link → open it in a private window → names are `[redacted]`, no file names, no download.
5. Open `/doi/datasets/<id>/versions/1` in a private window → embargo notice, no dataset name.
6. Sign in as a second account with no tenancy → *Shared with me* lists nothing; accept the invitation link → redirected to the dataset.

7. On an embargoed dataset, open the DOI form, choose a manual DOI, Save → the confirmation explains the embargo ends; Cancel sends nothing. As a `write` collaborator, the same dialog says only the owner can.
8. On a dataset without an embargo that has a manual DOI → the Settings tab says it can no longer be put under embargo.

Record anything that differs from the contracts in the PR description; do not change the contracts from this plan.

- [ ] **Step 6: Commit any fixes**

```bash
git status --short
git add -A && git commit -m "fix: issues found in the embargo webapp verification"
```

(Skip the commit if `git status --short` is empty.)

---

### Task 17: nginx — the DOI lands on the webapp page (gatekeeper repo)

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

| RFC / contracts requirement | Task |
|---|---|
| Embargo choice at creation, open or hidden, ≤ 90 days | 9 |
| Badge, mode switch, extend (≤ 90 days), end early, per access flags | 7, 8 |
| Extension by permission holders when the owner is disabled | 8 (`can_extend_embargo` drives `showExtend`) |
| File list withheld for tenancy members in open mode | 8 |
| Download and delete hidden where not allowed | 8 |
| Share dialog: tenancy search, email/ORCID detection with checksum, levels, list, revoke | 3, 10 |
| Invitation link shown once, regenerate, accepted-by shown | 10 |
| Reviewer links: label, one-time link, views count/first/last, revoke, free-text warning | 10 |
| Anonymous review page: redacted metadata, counts only, ended → redirect or notice | 11 |
| DOI landing notice, no metadata; redirect otherwise | 12, 17 |
| Invitation page, login with callback, 409 message | 13 |
| Claim pending invitations at sign-in, never blocking | 13 |
| Accounts with no tenancy: Shared with me, dataset pages, dataset BFF routes | 5, 7, 8 |
| Post-embargo banner: registered but not findable, manual promotion | 3, 8 |
| Telemetry pages and events | 2, 6 |
| Manual DOI under embargo: confirm, `end_embargo: true`, owner only; no embargo after a manual DOI | 1, 3, 8, 14 |
| Email images at `{PUBLIC_BASE_URL}/img/email/datamap-tile-{36,22}.png` (shipped by #101; guarded here) | 15, 16 |
