# Notebooks — Webapp Implementation Plan (05)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Where the code goes.** This plan lives in the gatekeeper repo with the other notebook plans, but every file it changes is in the **webapp repo, `/Users/caio.maia/workspace/datamap/datamap-webapp`**. Paths are relative to the webapp repo root. Work in a git worktree of the webapp repo on branch `feat/notebooks`, created from `origin/main`; never in the main checkout.

**Verified against:** webapp `main` at `00ff8c3` (#108). The i18n work of RFC 006 (next-intl, `messages/<locale>/*.json`) is on a branch and not yet on `main`: see *Strings* in Global Constraints for what to do in each case. If `main` has moved, diff the files in *File Structure* against it before starting.

**Design:** *Notebooks — discovery* (Claude Design, 2026-10-01), sections 1a (list), 1b (dataset page), 1c (editor), 1d (session states), 1g (prompts). Save to DataMap (1e), templates (1f) and sharing are increments B–D and are not in this plan; where the design shows them, this plan leaves the space and says what goes there later.

**Goal:** Let a person open a dataset in a notebook from the webapp and see it running: the notebooks list with seats and storage, the "Open in notebook" action on the dataset page (whole version or chosen files), the editor page with JupyterLab in a frame under a DataMap top bar and side panel, every session state the design draws plus the "no seats" one, and the "Notebooks are not enabled for your account yet" page for people outside the rollout gate.

**Architecture:** Server-side calls to the gatekeeper live in `lib/notebooks.ts`; browser mutations go through new `BFFAPI` methods to `pages/api/notebooks/*` routes on `bffRouter()`; reads use SWR with `lib/fetcher.js`. The decisions a page makes from a session (phase, time left, warning, seat message, whether a dataset can open) are pure functions in `lib/notebookSession.ts`, tested without React. The editor page logs the browser into the hub by posting the session token as a form (`lib/hubLogin.ts`) and then shows `/user/<uid>/lab/tree/<path>` in an iframe; the resource chip reads `jupyter-resource-usage` from the same origin. Components are small, under `components/Notebooks/`, each with a jsdom test.

**Tech Stack:** Next.js 14 (pages router), React 18, TypeScript, next-connect, axios, SWR, Formik, TailwindCSS, react-material-symbols, Jest + Testing Library.

**Spec:** `docs/rfcs/007-notebooks.md` (§Webapp, §Session lifecycle, §Limits). **Contracts:** `docs/superpowers/plans/2026-10-04-notebooks-00-contracts.md` (gatekeeper repo; wins over this plan on any interface).

## Global Constraints

- Payload shapes, routes and error codes are the contracts', verbatim: `Notebook`, `Session`, `POST /notebooks/{id}/sessions` → `{session, token, login_url, lab_path}` (201 new, 200 resumed), `GET /notebooks/-/capacity`, and the error codes `version_not_published`, `name_taken`, `selection_too_large`, `file_not_in_version`, `session_running`, `session_elsewhere`, `storage_full`, `no_seats`, `hub_unavailable`, `content_not_written`.
- Hub login: a form POST to `/hub/login` with fields `token` and `next`, same origin, never a URL with the token in it. The Lab iframe is `lab_path` from the start response.
- Resource chip: `GET /user/<uid>/api/metrics/v1` on the same origin, every 10 s while running; shape `{rss, limits: {memory: {rss}}, cpu_percent?, cpu_count?}` (jupyter-resource-usage). Missing fields show as `—`.
- Polling: `GET /api/notebooks/<id>/session` every 3 s while `starting`, every 30 s while `running`, not at all otherwise.
- Local development goes through the nginx container on `http://localhost` (`DATAMAP_BASE_URL=http://localhost/api/v1` already does); `/hub/` and `/user/` are routed there by plan 02. `NEXTAUTH_URL` must be `http://localhost` for the hub cookie and the webapp cookie to share the origin.
- Mutations go through `gateways/BFFAPI.ts`, which emits `trackUiEvent` after success and throws `httpErrorHandler(error)` on failure. Reads use SWR with `lib/fetcher.js`. Forms use Formik.
- Constants live in `contants/{Category}Constants.ts` (the directory is spelled `contants`).
- **Strings.** If the branch has `messages/` and `next-intl` (RFC 006 merged), every user-facing string goes in `messages/en/notebooks.json` and `messages/pt-BR/notebooks.json` under the `notebooks` namespace, read with `useTranslations("notebooks")`, and `contants/NotebookConstants.ts` holds only non-text constants. If it does not, every string lives in `NOTEBOOK_TEXT` in `contants/NotebookConstants.ts` (English, keyed exactly as the message file will be), so the i18n branch moves them without touching components. Never inline a string in a component either way.
- Visual language: the DataMap identity (#101). White cards `rounded-lg border border-primary-200 bg-primary-0`; secondary buttons like `ShareButton` (`h-[38px] px-3.5 rounded-md border border-primary-300 bg-primary-0 text-primary-900 text-sm font-semibold`); primary like `DownloadDatafilesButton`; pills `px-2.5 py-[3px] rounded-full text-xs leading-[18px] font-semibold`; dialogs through `components/base/PopupModal.tsx`; side-card labels `text-[11px] tracking-[0.08em] uppercase font-semibold text-primary-500`; mono for names and versions (`font-mono text-[13px]`). Session colours: running green `text-[#14532d] bg-[#dcfce7]`, starting `text-primary-700 bg-primary-200`, stopped `text-primary-500 bg-primary-100`, limit-approaching amber `embargo-800 bg-embargo-100` (the amber from the embargo work), failed `text-error-700 bg-error-200`.
- Material Symbols: `<MaterialSymbol ... grade={-25} weight={400} />`, sizes 16–22. Notebook icon is `code`, session states `play_circle` / `pause` / `timer_off` / `error`, picker `checklist`, lock `lock`.
- Component tests start with `/** @jest-environment jsdom */`, live in `__tests__` next to the component, import components by relative path, mock `swr`, `next/router`, `next-auth/react`, `../../gateways/BFFAPI` and `../../lib/fetcher` the way `components/Share/__tests__/ShareDialog.test.tsx` does. Components that a test imports must not import `react-markdown` (ESM, not transformed by Jest): the read-only renderer keeps its markdown cell in a separate, untested file.
- Every new page must be listed in `PAGES` (`contants/TelemetryConstants.ts`), or `contants/__tests__/TelemetryConstants.test.ts` fails. New UI events: `notebook_created`, `notebook_opened`, `session_started`, `session_stopped`, `notebook_deleted`.
- Comments: none narrating code. One line only where a reader would otherwise undo something on purpose.
- Every task ends green on `npx jest <the task's tests>`; Task 11 runs the whole suite and `npm run build`.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `types/GatekeeperAPI.ts` | modify | `NotebookKernel`, `SessionState`, `StopReason`, `NotebookDatasetRef`, `NotebookSession`, `Notebook`, `NotebookList`, `NotebookCreateRequest`, `NotebookUpdateRequest`, `SessionStartResponse`, `SessionStatus`, `NotebookCapacity` |
| `contants/NotebookConstants.ts` (+ test) | create | kernels, poll intervals, limits text, error-code → message, `NOTEBOOK_TEXT`, snippets |
| `contants/InternalRoutesConstants.ts`, `contants/TelemetryConstants.ts` | modify | `ROUTE_PAGE_NOTEBOOK_DETAILS`, the new page and events |
| `lib/notebooks.ts` | create | server calls to the gatekeeper |
| `pages/api/notebooks/index.ts`, `capacity.ts`, `[notebookId]/index.ts`, `[notebookId]/sessions.ts`, `[notebookId]/session.ts`, `[notebookId]/content.ts` | create | BFF routes |
| `gateways/BFFAPI.ts` | modify | `createNotebook`, `updateNotebook`, `deleteNotebook`, `startNotebookSession`, `stopNotebookSession` |
| `lib/notebookSession.ts` (+ test) | create | `sessionPhase`, `timeLeftMs`, `isLimitApproaching`, `formatRemaining`, `formatElapsed`, `seatMessage`, `openability`, `selectionTotal`, `selectionFits`, `pollInterval` |
| `lib/hubLogin.ts` (+ test) | create | `buildHubLoginForm(token, next)`, `submitHubLogin(document, token, next)` |
| `components/Notebooks/SessionPill.tsx`, `NotebooksTable.tsx`, `CapacityCounters.tsx`, `NewNotebookDialog.tsx`, `FileSelectionDialog.tsx`, `NotebookTopBar.tsx`, `SessionChip.tsx`, `ResourceUsage.tsx`, `SessionStateView.tsx`, `LabFrame.tsx`, `NotebookSidePanel.tsx`, `NotebookReadOnly.tsx`, `MarkdownCell.tsx`, `OpenInNotebookButton.tsx`, `MyNotebooksCard.tsx`, `NotebooksDisabled.tsx` (+ `__tests__`) | create | UI |
| `pages/app/notebooks/index.tsx` | replace | the list page |
| `pages/app/notebooks/[notebookId].tsx` | create | the editor page |
| `components/DatasetDetailsPage.tsx`, `components/DatasetDetails/DataCard/TabPanelDataCard.tsx`, `components/DatasetDetails/DataCard/DatasetFilesList.tsx`, `components/DatasetDetails/DatasetMoreSettingsButton.tsx` | modify | dataset page integration |
| `hooks/UseNotebookSession.ts` | create | SWR polling hook with the interval rule |

## Task order and parallelism

| Task | Depends on | Parallel with |
|---|---|---|
| 1 Types, constants, routes, telemetry | — | 3 |
| 2 Server calls, BFF routes, gateway | 1 | 3, 4 |
| 3 Pure session helpers | 1 | 2, 4 |
| 4 Hub login helper | — | 2, 3 |
| 5 List page: table, counters, new-notebook dialog, disabled state | 1, 2, 3 | 6, 7 |
| 6 File selection dialog | 1, 3 | 5, 7 |
| 7 Editor page: top bar, chip, resource usage, states, frame, side panel, read-only | 2, 3, 4 | 5, 6 |
| 8 Dataset page: button, per-file action, my-notebooks card | 5 (dialog), 6 (picker) | 7 |
| 9 Delete dataset warning text | — | anything |
| 10 Full verification | all | — |

---

### Task 1: Types, constants, routes and telemetry

**Files:**
- Modify: `types/GatekeeperAPI.ts` (append), `contants/InternalRoutesConstants.ts`, `contants/TelemetryConstants.ts`
- Create: `contants/NotebookConstants.ts`, `contants/__tests__/NotebookConstants.test.ts`

**Interfaces:**
- Produces the types below, `ROUTE_PAGE_NOTEBOOK_DETAILS(params)`, `PAGES` entry `/app/notebooks/[notebookId]`, the five UI events, `NOTEBOOK_KERNELS`, `SESSION_POLL_MS`, `RESOURCE_POLL_MS`, `LIMIT_WARNING_MS`, `NOTEBOOK_ERROR_MESSAGES`, `messageForNotebookError`, `NOTEBOOK_TEXT`, `SNIPPETS`.

- [ ] **Step 1: Types**

Append to `types/GatekeeperAPI.ts`:

```ts
/*
 Notebooks (RFC 007). Contracts: docs/superpowers/plans/2026-10-04-notebooks-00-contracts.md (gatekeeper repo).
*/

export type NotebookKernel = "python3" | "ir";
export type SessionState = "starting" | "running" | "stopped" | "ended" | "failed";
export type StopReason = "idle" | "user" | "admin" | "max_age" | "spawn_error";

export interface NotebookDatasetRef {
    id: string | null
    title: string | null
    version_name: string | null
    source_deleted: boolean
}

export interface NotebookSession {
    id: string
    state: SessionState
    stop_reason: StopReason | null
    requested_at: string
    started_at: string | null
    stopped_at: string | null
    mounted_files: number
    mounted_bytes: number
    progress: string[]
    max_hours: number
}

export interface Notebook {
    id: string
    name: string
    path: string
    kernel: NotebookKernel
    size_bytes: number
    created_at: string
    updated_at: string
    dataset: NotebookDatasetRef | null
    file_ids: string[] | null
    mounted_files: number
    mounted_bytes: number
    session: NotebookSession | null
}

export interface NotebookList {
    content: Notebook[]
}

export interface NotebookCreateRequest {
    dataset_id: string
    version_name: string
    kernel: NotebookKernel
    name?: string
    file_ids?: string[] | null
}

export interface NotebookUpdateRequest {
    name?: string
    file_ids?: string[] | null
}

export interface SessionStartResponse {
    session: NotebookSession
    token: string
    login_url: string
    lab_path: string
}

export interface SessionStatus extends Partial<NotebookSession> {
    state: SessionState | null
    max_hours: number
}

export interface NotebookCapacity {
    seats_taken: number
    seats_total: number
    storage_used_bytes: number
    storage_quota_bytes: number
    data_max_bytes: number
}
```

- [ ] **Step 2: Routes and telemetry**

In `contants/InternalRoutesConstants.ts`, after `ROUTE_PAGE_NOTEBOOKS_NEW`:

```ts
/**
 * Route to one notebook: the editor.
 * @constant
 */
export const ROUTE_PAGE_NOTEBOOK_DETAILS = (params) => replaceIt(ROUTE_PAGE_NOTEBOOKS + '/:id', params);
```

In `contants/TelemetryConstants.ts`, add `"/app/notebooks/[notebookId]"` to `PAGES` (after `"/app/notebooks"`) and, to `UI_EVENTS`:

```ts
  "notebook_created",
  "notebook_opened",
  "session_started",
  "session_stopped",
  "notebook_deleted",
```

- [ ] **Step 3: Failing constants test**

`contants/__tests__/NotebookConstants.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import { NOTEBOOK_ERROR_MESSAGES, NOTEBOOK_KERNELS, NOTEBOOK_TEXT, SNIPPETS, messageForNotebookError } from "../NotebookConstants";

describe("notebook constants", () => {
    test("every contract error code has a message", () => {
        for (const code of ["version_not_published", "name_taken", "selection_too_large", "file_not_in_version", "session_running", "session_elsewhere", "storage_full", "no_seats", "hub_unavailable", "content_not_written"]) {
            expect(NOTEBOOK_ERROR_MESSAGES[code]).toBeTruthy();
        }
    });

    test("an unknown error gets the generic message", () => {
        expect(messageForNotebookError({ detail: "weird" })).toBe(NOTEBOOK_TEXT.errors.generic);
        expect(messageForNotebookError(undefined)).toBe(NOTEBOOK_TEXT.errors.generic);
    });

    test("a known detail gets its message, with the numbers when it carries them", () => {
        expect(messageForNotebookError({ detail: "no_seats", seats_total: 4 })).toContain("4");
        expect(messageForNotebookError({ detail: "selection_too_large", max_bytes: 21474836480, selected_bytes: 30000000000 })).toContain("20 GB");
    });

    test("both kernels are offered with a label", () => {
        expect(NOTEBOOK_KERNELS.map(k => k.value)).toEqual(["python3", "ir"]);
    });

    test("snippets exist for both kernels", () => {
        expect(SNIPPETS.python3.length).toBeGreaterThan(2);
        expect(SNIPPETS.ir.length).toBeGreaterThan(1);
    });
});
```

Run: `npx jest contants/__tests__/NotebookConstants.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 4: Constants**

`contants/NotebookConstants.ts`:

```ts
import { bytesToSize } from "../lib/file";
import { NotebookKernel } from "../types/GatekeeperAPI";

export const NOTEBOOK_KERNELS: { value: NotebookKernel, label: string, hint: string }[] = [
    { value: "python3", label: "Python 3", hint: "xarray, pandas, netCDF4, matplotlib" },
    { value: "ir", label: "R", hint: "tidyverse, ncdf4, readxl, data.table" },
];

export const SESSION_POLL_MS = { starting: 3_000, running: 30_000 } as const;
export const RESOURCE_POLL_MS = 10_000;
export const LIMIT_WARNING_MS = 30 * 60 * 1000;
export const SESSION_PATH_MAX_LENGTH = 128;

// Strings. When RFC 006's next-intl lands, these move to messages/<locale>/notebooks.json
// under the same keys; components read them through one accessor so that move
// touches nothing else.
export const NOTEBOOK_TEXT = {
    page: {
        title: "Notebooks",
        subtitle: "Open a dataset where it lives, in Python or R.",
        newNotebook: "+ New notebook",
        fromTemplate: "From template",
        mine: "Mine",
        sharedWithMe: "Shared with me",
        empty: "No notebooks yet. Open a dataset in a notebook from its page, or create one here.",
        columns: { notebook: "Notebook", dataset: "Dataset", session: "Session", edited: "Edited" },
        sessionRunning: "session running",
        sessionsRunning: "sessions running",
        storage: "of notebook storage",
        sourceDeleted: "source deleted",
        comingLater: "Templates and sharing arrive in the next increments.",
    },
    disabled: {
        title: "Notebooks are not enabled for your account yet",
        body: "Notebooks are being released gradually. Someone from the Data Team enables them per account; once they tell you it is done, reload this page.",
    },
    create: {
        title: "New notebook",
        dataset: "Dataset",
        searchDatasets: "Search datasets you can read",
        version: "Version",
        kernel: "Language",
        name: "Name (optional)",
        namePlaceholder: "derived from the dataset title",
        create: "Open notebook",
        creating: "Creating...",
        tooLarge: "This version is larger than the session limit. Choose the files to mount.",
        chooseFiles: "Choose files",
    },
    picker: {
        title: "Choose the files to mount",
        search: "Filter by name",
        selected: "selected",
        limit: "limit",
        overLimit: "Over the limit: unselect some files.",
        tooBigFile: "This file alone is over the session limit.",
        all: "All",
        none: "None",
        confirm: "Mount these files",
        restartNote: "Changing the selection restarts the session.",
    },
    session: {
        running: "Running",
        starting: "Starting",
        stopped: "Stopped",
        ended: "Ended",
        failed: "Failed",
        none: "Not started",
        cpu: "CPU",
        ram: "RAM",
        of: "/",
        left: "left",
        stop: "Stop",
        resume: "Resume",
        readOnly: "Read only",
        startNew: "Start new session",
        tryAgain: "Try again",
        startingTitle: "Starting your session",
        startingHint: "Usually under a minute. The first open copies the files.",
        stoppedTitle: "Session stopped",
        stoppedBody: "The notebook is saved; variables and outputs in memory are gone.",
        idleSince: "Idle since",
        endedTitle: "Session ended · 12 h limit",
        endedBody: "The notebook is saved. Output files are kept for 24 h.",
        failedTitle: "The session could not start",
        failedBody: "Try again. If it keeps failing, the Data Team can see why in the logs.",
        limitBanner: (minutes: number, hours: number) => `This session ends in ${minutes} minutes (${hours} h limit). The notebook is saved automatically; memory is cleared.`,
        noSeatsTitle: (total: number) => `All ${total} seats are in use`,
        noSeatsBody: "Sessions stop after an hour idle. Try again shortly.",
        storageFullTitle: "Notebook storage is full",
        storageFullBody: "Outputs count, mounted data doesn't. Delete outputs to continue.",
        sourceDeletedTitle: "The dataset this notebook used was deleted",
        sourceDeletedBody: "The code is kept; datamap.open() will fail.",
        elsewhere: "You already have a session running on another notebook. Stop it to open this one.",
        stopConfirmTitle: "Stop session?",
        stopConfirmBody: "The notebook is saved. Variables are cleared. Output files are kept for 24 h.",
        stoppedByAdmin: "Stopped by an administrator.",
        filesNotMounted: "files not mounted · open through the SDK",
    },
    panel: {
        dataset: "Dataset",
        pinned: "pinned",
        openDataset: "Open dataset",
        files: "Files",
        mounted: (n: number, total: number) => `${n} of ${total} files mounted`,
        changeSelection: "Change selection",
        snippets: "Snippets",
        copy: "Copy",
        copied: "Copied · paste into a cell",
        outputs: "Outputs",
        outputsHint: "Files you write to /outputs are kept for 24 h after the session ends. Saving them to DataMap arrives in the next increment.",
    },
    menu: {
        rename: "Rename",
        download: "Download .ipynb",
        changeSelection: "Change selection",
        stop: "Stop session",
        delete: "Delete notebook",
        deleteTitle: "Delete notebook?",
        deleteBody: "The file is removed. Copies you downloaded are not affected. This cannot be undone.",
    },
    datasetPage: {
        open: "Open in notebook",
        openFile: "Open this file in a notebook",
        lockedEmbargo: "Notebooks are unavailable under embargo",
        lockedEmbargoBody: (until: string) => `Embargoed until ${until}. Available once the dataset is published; download the files to work locally in the meantime.`,
        lockedDraft: "Publish this version to open it in a notebook",
        myNotebooks: "My notebooks",
        newOn: (version: string) => `New notebook on v${version}`,
        none: "No notebooks on this dataset yet.",
    },
    readOnly: {
        banner: "Read only. Start a session to run the cells.",
        notWritten: "This notebook has not been opened yet; there is nothing to show.",
    },
    errors: {
        generic: "Something went wrong. Try again.",
    },
} as const;

export const NOTEBOOK_ERROR_MESSAGES: Record<string, (e: any) => string> = {
    version_not_published: () => "Only a published version can be opened in a notebook.",
    name_taken: () => "You already have a notebook with this name.",
    selection_too_large: (e) => `The selection is ${bytesToSize(e?.selected_bytes ?? 0)}; the session limit is ${bytesToSize(e?.max_bytes ?? 0)}. Choose fewer files.`,
    file_not_in_version: () => "One of the chosen files is not in this version.",
    session_running: () => "Stop the session before changing the files.",
    session_elsewhere: () => NOTEBOOK_TEXT.session.elsewhere,
    storage_full: (e) => `${NOTEBOOK_TEXT.session.storageFullTitle}: ${bytesToSize(e?.used_bytes ?? 0)} of ${bytesToSize(e?.quota_bytes ?? 0)}.`,
    no_seats: (e) => `${NOTEBOOK_TEXT.session.noSeatsTitle(e?.seats_total ?? 0)}. ${NOTEBOOK_TEXT.session.noSeatsBody}`,
    hub_unavailable: () => "The notebook service is not answering. Try again in a minute.",
    content_not_written: () => NOTEBOOK_TEXT.readOnly.notWritten,
};

export function messageForNotebookError(error: any): string {
    const detail = error?.detail ?? error?.response?.data?.detail ?? error?.message;
    const body = error?.response?.data ?? error;
    const render = typeof detail === "string" ? NOTEBOOK_ERROR_MESSAGES[detail] : undefined;
    return render ? render(body) : NOTEBOOK_TEXT.errors.generic;
}

export const SNIPPETS: Record<NotebookKernel, { title: string, code: string }[]> = {
    python3: [
        { title: "Open all NetCDF as one xarray", code: 'da = ds.open_mfdataset("*.nc")' },
        { title: "Open a CSV as pandas", code: 'df = ds.read_csv("path/in/version.csv")' },
        { title: "Dataset metadata", code: "ds.meta  # title, license, DOI" },
        { title: "Open another dataset", code: 'other = datamap.open("<dataset id>", version="1")' },
        { title: "Write an output", code: 'da.to_netcdf("/outputs/result.nc")' },
    ],
    ir: [
        { title: "Open a NetCDF with ncdf4", code: 'nc <- ncdf4::nc_open(ds$path("file.nc"))' },
        { title: "Read a CSV", code: 'df <- read.csv(ds$path("path/in/version.csv"))' },
        { title: "Dataset metadata", code: "ds$meta" },
        { title: "Write an output", code: 'write.csv(df, "/outputs/result.csv")' },
    ],
};
```

`bytesToSize(21474836480)` must render as `20 GB` for the test; check `lib/file.ts` (it rounds to one decimal by default: `20.0 GB`?). If it renders `20.0 GB`, make the test assert `"20"` and `"GB"` separately rather than changing the shared helper.

Run the constants and telemetry tests: `npx jest contants`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add types/GatekeeperAPI.ts contants/NotebookConstants.ts contants/__tests__/NotebookConstants.test.ts contants/InternalRoutesConstants.ts contants/TelemetryConstants.ts
git commit -m "feat(notebooks): types, constants, the editor route and telemetry events"
```

---

### Task 2: Server calls, BFF routes and gateway methods

**Files:**
- Create: `lib/notebooks.ts`
- Create: `pages/api/notebooks/index.ts`, `pages/api/notebooks/capacity.ts`, `pages/api/notebooks/[notebookId]/index.ts`, `pages/api/notebooks/[notebookId]/sessions.ts`, `pages/api/notebooks/[notebookId]/session.ts`, `pages/api/notebooks/[notebookId]/content.ts`
- Modify: `gateways/BFFAPI.ts`
- Create: `lib/__tests__/notebooks.test.ts`

**Interfaces:**
- Produces (server): `listNotebooks(context, datasetId?)`, `createNotebook(context, request)`, `getNotebook(context, id)`, `updateNotebook(context, id, request)`, `deleteNotebook(context, id)`, `startSession(context, id, locale)`, `getSession(context, id)`, `stopSession(context, id)`, `getCapacity(context)`, `getContent(context, id)` → the raw axios response (so the BFF can stream status and headers).
- Produces (browser, `BFFAPI`): `createNotebook(request): Promise<Notebook>`, `updateNotebook(id, request): Promise<Notebook>`, `deleteNotebook(id): Promise<void>`, `startNotebookSession(id, locale): Promise<SessionStartResponse>`, `stopNotebookSession(id): Promise<void>`. Each throws `httpErrorHandler(error)` and tracks its event.
- BFF routes: `GET/POST /api/notebooks`, `GET /api/notebooks/capacity`, `GET/PATCH/DELETE /api/notebooks/[id]`, `POST /api/notebooks/[id]/sessions`, `GET/DELETE /api/notebooks/[id]/session`, `GET /api/notebooks/[id]/content?download=1`.

- [ ] **Step 1: Failing server-call test**

`lib/__tests__/notebooks.test.ts`:

```ts
import { describe, expect, jest, test, beforeEach } from '@jest/globals';

const get = jest.fn() as any;
const post = jest.fn() as any;
const patch = jest.fn() as any;
const del = jest.fn() as any;

jest.mock("../rpc", () => ({
    __esModule: true,
    default: { get, post, patch, delete: del },
    buildHeaders: (context: any) => ({ headers: { "X-User-Id": context.uid, "X-Datamap-Tenancies": context.tenancy } }),
}));

import { createNotebook, getCapacity, listNotebooks, startSession, stopSession } from "../notebooks";

const context = { uid: "u1", tenancy: "t" } as any;

beforeEach(() => { get.mockReset(); post.mockReset(); patch.mockReset(); del.mockReset(); });

describe("notebook server calls", () => {
    test("list passes the dataset filter as a query", async () => {
        get.mockResolvedValue({ data: { content: [] } });

        await listNotebooks(context, "d1");

        expect(get).toHaveBeenCalledWith("/notebooks/", expect.objectContaining({ params: { dataset_id: "d1" }, headers: expect.objectContaining({ "X-User-Id": "u1" }) }));
    });

    test("create posts the request as is", async () => {
        post.mockResolvedValue({ data: { id: "n1" } });

        const notebook = await createNotebook(context, { dataset_id: "d1", version_name: "2", kernel: "python3" });

        expect(notebook).toEqual({ id: "n1" });
        expect(post.mock.calls[0][0]).toBe("/notebooks/");
        expect(post.mock.calls[0][1]).toEqual({ dataset_id: "d1", version_name: "2", kernel: "python3" });
    });

    test("start returns the body and the status so the BFF can forward 200 vs 201", async () => {
        post.mockResolvedValue({ status: 201, data: { token: "t" } });

        const result = await startSession(context, "n1", "pt-BR");

        expect(result).toEqual({ status: 201, body: { token: "t" } });
        expect(post.mock.calls[0][1]).toEqual({ locale: "pt-BR" });
    });

    test("stop and capacity hit their routes", async () => {
        del.mockResolvedValue({ status: 204 });
        get.mockResolvedValue({ data: { seats_taken: 1 } });

        await stopSession(context, "n1");
        const capacity = await getCapacity(context);

        expect(del.mock.calls[0][0]).toBe("/notebooks/n1/session");
        expect(get.mock.calls[0][0]).toBe("/notebooks/-/capacity");
        expect(capacity.seats_taken).toBe(1);
    });
});
```

Run: `npx jest lib/__tests__/notebooks.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 2: Server calls**

`lib/notebooks.ts`:

```ts
import { Notebook, NotebookCapacity, NotebookCreateRequest, NotebookList, NotebookUpdateRequest, SessionStartResponse, SessionStatus } from "../types/GatekeeperAPI";
import { AppLocalContext } from "./appLocalContext";
import axiosInstance, { buildHeaders } from "./rpc";

export async function listNotebooks(context: AppLocalContext, datasetId?: string): Promise<NotebookList> {
    const response = await axiosInstance.get("/notebooks/", { ...buildHeaders(context), params: datasetId ? { dataset_id: datasetId } : {} });
    return response.data as NotebookList;
}

export async function createNotebook(context: AppLocalContext, request: NotebookCreateRequest): Promise<Notebook> {
    const response = await axiosInstance.post("/notebooks/", request, buildHeaders(context));
    return response.data as Notebook;
}

export async function getNotebook(context: AppLocalContext, id: string): Promise<Notebook> {
    const response = await axiosInstance.get(`/notebooks/${encodeURIComponent(id)}`, buildHeaders(context));
    return response.data as Notebook;
}

export async function updateNotebook(context: AppLocalContext, id: string, request: NotebookUpdateRequest): Promise<Notebook> {
    const response = await axiosInstance.patch(`/notebooks/${encodeURIComponent(id)}`, request, buildHeaders(context));
    return response.data as Notebook;
}

export async function deleteNotebook(context: AppLocalContext, id: string): Promise<void> {
    await axiosInstance.delete(`/notebooks/${encodeURIComponent(id)}`, buildHeaders(context));
}

export async function startSession(context: AppLocalContext, id: string, locale: string): Promise<{ status: number, body: SessionStartResponse }> {
    const response = await axiosInstance.post(`/notebooks/${encodeURIComponent(id)}/sessions`, { locale }, buildHeaders(context));
    return { status: response.status, body: response.data as SessionStartResponse };
}

export async function getSession(context: AppLocalContext, id: string): Promise<SessionStatus> {
    const response = await axiosInstance.get(`/notebooks/${encodeURIComponent(id)}/session`, buildHeaders(context));
    return response.data as SessionStatus;
}

export async function stopSession(context: AppLocalContext, id: string): Promise<void> {
    await axiosInstance.delete(`/notebooks/${encodeURIComponent(id)}/session`, buildHeaders(context));
}

export async function getCapacity(context: AppLocalContext): Promise<NotebookCapacity> {
    const response = await axiosInstance.get("/notebooks/-/capacity", buildHeaders(context));
    return response.data as NotebookCapacity;
}

export async function getContent(context: AppLocalContext, id: string, download: boolean) {
    return axiosInstance.get(`/notebooks/${encodeURIComponent(id)}/content`, {
        ...buildHeaders(context),
        params: download ? { download: 1 } : {},
        responseType: "arraybuffer",
    });
}
```

Run the test. Expected: 4 passed.

- [ ] **Step 3: BFF routes**

`pages/api/notebooks/index.ts`:

```ts
import { NewContext } from "../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../lib/bffRoute";
import { createNotebook, listNotebooks } from "../../../lib/notebooks";

const router = bffRouter()
    .get(async (req, res) => {
        const context = await NewContext(req);
        res.json(await listNotebooks(context, req.query.dataset_id as string | undefined));
    })
    .post(async (req, res) => {
        const context = await NewContext(req);
        res.status(201).json(await createNotebook(context, req.body));
    });

export default bffHandler(router);
```

`pages/api/notebooks/capacity.ts`:

```ts
import { NewContext } from "../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../lib/bffRoute";
import { getCapacity } from "../../../lib/notebooks";

const router = bffRouter().get(async (req, res) => {
    res.json(await getCapacity(await NewContext(req)));
});

export default bffHandler(router);
```

`pages/api/notebooks/[notebookId]/index.ts`:

```ts
import { NewContext } from "../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../lib/bffRoute";
import { deleteNotebook, getNotebook, updateNotebook } from "../../../../lib/notebooks";

const router = bffRouter()
    .get(async (req, res) => {
        res.json(await getNotebook(await NewContext(req), req.query.notebookId as string));
    })
    .patch(async (req, res) => {
        res.json(await updateNotebook(await NewContext(req), req.query.notebookId as string, req.body));
    })
    .delete(async (req, res) => {
        await deleteNotebook(await NewContext(req), req.query.notebookId as string);
        res.status(204).end();
    });

export default bffHandler(router);
```

`pages/api/notebooks/[notebookId]/sessions.ts`:

```ts
import { NewContext } from "../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../lib/bffRoute";
import { startSession } from "../../../../lib/notebooks";

const router = bffRouter().post(async (req, res) => {
    const result = await startSession(await NewContext(req), req.query.notebookId as string, req.body?.locale ?? "pt-BR");
    res.status(result.status).json(result.body);
});

export default bffHandler(router);
```

`pages/api/notebooks/[notebookId]/session.ts`:

```ts
import { NewContext } from "../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../lib/bffRoute";
import { getSession, stopSession } from "../../../../lib/notebooks";

const router = bffRouter()
    .get(async (req, res) => {
        res.json(await getSession(await NewContext(req), req.query.notebookId as string));
    })
    .delete(async (req, res) => {
        await stopSession(await NewContext(req), req.query.notebookId as string);
        res.status(204).end();
    });

export default bffHandler(router);
```

`pages/api/notebooks/[notebookId]/content.ts`:

```ts
import { NewContext } from "../../../../lib/appLocalContext";
import { bffHandler, bffRouter } from "../../../../lib/bffRoute";
import { getContent } from "../../../../lib/notebooks";

const router = bffRouter().get(async (req, res) => {
    const download = req.query.download === "1";
    const upstream = await getContent(await NewContext(req), req.query.notebookId as string, download);
    res.setHeader("Content-Type", "application/json");
    if (upstream.headers["content-disposition"]) {
        res.setHeader("Content-Disposition", upstream.headers["content-disposition"]);
    }
    res.status(200).send(Buffer.from(upstream.data));
});

export default bffHandler(router);
```

`bffRouter()` uses `authOnlyChain`: a notebook is reachable with whatever tenancy is selected, and the gatekeeper falls back to the user's own tenancies when the header is empty.

- [ ] **Step 4: Gateway methods**

Append to the `BFFAPI` class in `gateways/BFFAPI.ts` (add the type imports from `../types/GatekeeperAPI`):

```ts
    async createNotebook(request: NotebookCreateRequest): Promise<Notebook> {
        try {
            const response = await axios.post("/api/notebooks", request);
            trackUiEvent("notebook_created");
            return response.data as Notebook;
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async updateNotebook(id: string, request: NotebookUpdateRequest): Promise<Notebook> {
        try {
            return (await axios.patch(`/api/notebooks/${encodeURIComponent(id)}`, request)).data as Notebook;
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async deleteNotebook(id: string): Promise<void> {
        try {
            await axios.delete(`/api/notebooks/${encodeURIComponent(id)}`);
            trackUiEvent("notebook_deleted");
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async startNotebookSession(id: string, locale: string): Promise<SessionStartResponse> {
        try {
            const response = await axios.post(`/api/notebooks/${encodeURIComponent(id)}/sessions`, { locale });
            if (response.status === 201) trackUiEvent("session_started");
            return response.data as SessionStartResponse;
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }

    async stopNotebookSession(id: string): Promise<void> {
        try {
            await axios.delete(`/api/notebooks/${encodeURIComponent(id)}/session`);
            trackUiEvent("session_stopped");
        } catch (error) {
            throw httpErrorHandler(error);
        }
    }
```

`httpErrorHandler` maps 413 and 429 through its `>= 400 && < 500` branch into `CLIENT_ERROR` with `detail` and `errors` carried, so `messageForNotebookError(error)` reads `error.detail` — confirm with `lib/__tests__/rpc.test.ts` that a 429 with `{"detail": "no_seats", "seats_total": 4}` keeps the body: if `APIError` drops the extra keys, extend `httpErrorHandler`'s generic branch to attach `response.data` as `error.body` and read `error.body` in `messageForNotebookError` (Task 1's function already looks at `error.response?.data ?? error`; make it also look at `error.body`).

- [ ] **Step 5: Run and commit**

Run: `npx jest lib/__tests__/notebooks.test.ts lib/__tests__/rpc.test.ts contants`
Expected: all passed

```bash
git add lib/notebooks.ts lib/__tests__/notebooks.test.ts pages/api/notebooks gateways/BFFAPI.ts
git commit -m "feat(notebooks): server calls, BFF routes and gateway methods"
```

---

### Task 3: Pure session helpers

**Files:**
- Create: `lib/notebookSession.ts`, `lib/__tests__/notebookSession.test.ts`

**Interfaces:**
- Produces: `sessionPhase(session: SessionStatus | NotebookSession | null): "none" | SessionState`; `timeLeftMs(session, now: Date): number | null`; `isLimitApproaching(session, now): boolean`; `formatRemaining(ms): string` (`"28 min"`, `"2 h 05 min"`); `formatElapsed(startedAt, now): string` (`"1 h 18 m"`); `pollInterval(phase): number` (0 when not polling); `seatMessage(capacity): string`; `openability(dataset, version): { ok: true } | { ok: false, reason: "embargo" | "draft" | "withheld" | "no_files" }`; `selectionTotal(files, selectedIds)`; `selectionFits(total, maxBytes)`.

- [ ] **Step 1: Failing tests**

`lib/__tests__/notebookSession.test.ts`:

```ts
import { describe, expect, test } from '@jest/globals';
import { formatElapsed, formatRemaining, isLimitApproaching, openability, pollInterval, seatMessage, selectionFits, selectionTotal, sessionPhase, timeLeftMs } from "../notebookSession";

const NOW = new Date("2026-10-04T12:00:00Z");

function session(overrides: any = {}): any {
    return { id: "s", state: "running", stop_reason: null, requested_at: "2026-10-04T10:00:00Z", started_at: "2026-10-04T10:00:00Z", stopped_at: null, mounted_files: 1, mounted_bytes: 1, progress: [], max_hours: 12, ...overrides };
}

describe("sessionPhase", () => {
    test("is none when there is no session or no state", () => {
        expect(sessionPhase(null)).toBe("none");
        expect(sessionPhase({ state: null, max_hours: 12 })).toBe("none");
    });
    test("is the state otherwise", () => {
        expect(sessionPhase(session({ state: "stopped" }))).toBe("stopped");
    });
});

describe("time left", () => {
    test("counts from started_at to the limit", () => {
        expect(timeLeftMs(session(), NOW)).toBe(10 * 3600 * 1000);
    });
    test("is null before the server started or when not running", () => {
        expect(timeLeftMs(session({ state: "starting", started_at: null }), NOW)).toBeNull();
        expect(timeLeftMs(session({ state: "stopped" }), NOW)).toBeNull();
    });
    test("approaching means under thirty minutes left while running", () => {
        expect(isLimitApproaching(session({ started_at: "2026-10-04T00:20:00Z" }), NOW)).toBe(true);
        expect(isLimitApproaching(session(), NOW)).toBe(false);
    });
    test("formats remaining and elapsed as the design shows", () => {
        expect(formatRemaining(28 * 60 * 1000)).toBe("28 min");
        expect(formatRemaining((2 * 60 + 5) * 60 * 1000)).toBe("2 h 05 min");
        expect(formatElapsed("2026-10-04T10:42:00Z", NOW)).toBe("1 h 18 m");
        expect(formatElapsed("2026-10-04T11:50:00Z", NOW)).toBe("10 m");
    });
});

describe("polling", () => {
    test("polls fast while starting, slowly while running, never otherwise", () => {
        expect(pollInterval("starting")).toBe(3000);
        expect(pollInterval("running")).toBe(30000);
        expect(pollInterval("stopped")).toBe(0);
        expect(pollInterval("none")).toBe(0);
    });
});

describe("seatMessage", () => {
    test("reads the counters", () => {
        expect(seatMessage({ seats_taken: 1, seats_total: 4, storage_used_bytes: 0, storage_quota_bytes: 1 })).toBe("1 of 4 seats in use");
    });
});

describe("openability", () => {
    const published = { name: "2", design_state: "PUBLISHED", files_in: [{ id: "f" }] } as any;
    test("a published version with files on a readable dataset opens", () => {
        expect(openability({ embargo: null } as any, published)).toEqual({ ok: true });
    });
    test("an active embargo blocks unless the files are reachable", () => {
        expect(openability({ embargo: { active: true } } as any, { ...published, files_withheld: true })).toEqual({ ok: false, reason: "embargo" });
        expect(openability({ embargo: { active: true } } as any, published)).toEqual({ ok: true });
    });
    test("a draft or an empty version does not open", () => {
        expect(openability({ embargo: null } as any, { ...published, design_state: "DRAFT" })).toEqual({ ok: false, reason: "draft" });
        expect(openability({ embargo: null } as any, { ...published, files_in: [] })).toEqual({ ok: false, reason: "no_files" });
    });
});

describe("selection", () => {
    const files = [{ id: "a", size_bytes: 10 }, { id: "b", size_bytes: 20 }, { id: "c", size_bytes: 30 }] as any;
    test("total of the chosen ids, or of all when null", () => {
        expect(selectionTotal(files, ["a", "c"])).toBe(40);
        expect(selectionTotal(files, null)).toBe(60);
    });
    test("fits is a plain comparison with the ceiling", () => {
        expect(selectionFits(40, 50)).toBe(true);
        expect(selectionFits(60, 50)).toBe(false);
    });
});
```

Run: `npx jest lib/__tests__/notebookSession.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 2: Write the helpers**

`lib/notebookSession.ts`:

```ts
import { LIMIT_WARNING_MS, SESSION_POLL_MS } from "../contants/NotebookConstants";
import { GetDatasetDetailsResponse, GetDatasetDetailsVersionResponse } from "../types/BffAPI";
import { NotebookCapacity, NotebookSession, SessionState, SessionStatus } from "../types/GatekeeperAPI";

export type SessionPhase = "none" | SessionState;

export function sessionPhase(session: SessionStatus | NotebookSession | null | undefined): SessionPhase {
    return session?.state ?? "none";
}

export function timeLeftMs(session: SessionStatus | NotebookSession | null | undefined, now: Date): number | null {
    if (!session || session.state !== "running" || !session.started_at) return null;
    const end = new Date(session.started_at).getTime() + session.max_hours * 3600 * 1000;
    return Math.max(0, end - now.getTime());
}

export function isLimitApproaching(session: SessionStatus | NotebookSession | null | undefined, now: Date): boolean {
    const left = timeLeftMs(session, now);
    return left !== null && left <= LIMIT_WARNING_MS;
}

export function formatRemaining(ms: number): string {
    const minutes = Math.ceil(ms / 60000);
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    return `${hours} h ${String(minutes % 60).padStart(2, "0")} min`;
}

export function formatElapsed(startedAt: string, now: Date): string {
    const minutes = Math.max(0, Math.floor((now.getTime() - new Date(startedAt).getTime()) / 60000));
    if (minutes < 60) return `${minutes} m`;
    return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} m`;
}

export function pollInterval(phase: SessionPhase): number {
    if (phase === "starting") return SESSION_POLL_MS.starting;
    if (phase === "running") return SESSION_POLL_MS.running;
    return 0;
}

export function seatMessage(capacity: NotebookCapacity): string {
    return `${capacity.seats_taken} of ${capacity.seats_total} seats in use`;
}

export type Openability = { ok: true } | { ok: false, reason: "embargo" | "draft" | "withheld" | "no_files" };

export function openability(dataset: GetDatasetDetailsResponse, version: GetDatasetDetailsVersionResponse | undefined): Openability {
    if (!version) return { ok: false, reason: "draft" };
    if (version.files_withheld) return { ok: false, reason: "embargo" };
    if ((version.design_state ?? "").toUpperCase() !== "PUBLISHED") return { ok: false, reason: "draft" };
    if (!version.files_in?.length) return { ok: false, reason: "no_files" };
    return { ok: true };
}

export function selectionTotal(files: { id: string, size_bytes?: number }[], selectedIds: string[] | null): number {
    const chosen = selectedIds === null ? files : files.filter(f => selectedIds.includes(f.id));
    return chosen.reduce((sum, f) => sum + (f.size_bytes ?? 0), 0);
}

export function selectionFits(totalBytes: number, maxBytes: number): boolean {
    return totalBytes <= maxBytes;
}
```

`files_withheld` is what the gatekeeper sets when the caller cannot reach the files (embargo without access), so it is the one signal the page needs: a person with access under an embargo sees files and may open a notebook, exactly as the download button behaves.

Run the test. Expected: all passed.

- [ ] **Step 3: Commit**

```bash
git add lib/notebookSession.ts lib/__tests__/notebookSession.test.ts
git commit -m "feat(notebooks): the page's decisions about a session, as pure functions"
```

---

### Task 4: Hub login helper

**Files:**
- Create: `lib/hubLogin.ts`, `lib/__tests__/hubLogin.test.ts`

**Interfaces:**
- Produces: `submitHubLogin(doc: Document, token: string, next: string, loginUrl = "/hub/login"): Promise<void>` — posts the form inside a hidden iframe and resolves when the iframe has loaded (the hub answered the POST with a redirect to `next`, setting its cookie), rejecting after 20 s; `hubLoginFormHtml(token, next, loginUrl)` is the pure piece.

- [ ] **Step 1: Failing test**

`lib/__tests__/hubLogin.test.ts`:

```ts
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { hubLoginFormHtml, submitHubLogin } from "../hubLogin";

describe("hub login", () => {
    test("the form posts token and next to the login url, escaped", () => {
        const html = hubLoginFormHtml("t<ok>", "/user/u/lab", "/hub/login");

        expect(html).toContain('method="post"');
        expect(html).toContain('action="/hub/login"');
        expect(html).toContain('name="token" value="t&lt;ok&gt;"');
        expect(html).toContain('name="next" value="/user/u/lab"');
    });

    test("submits inside a hidden iframe and resolves on load", async () => {
        const promise = submitHubLogin(document, "tok", "/user/u/lab");
        const frame = document.querySelector("iframe[data-hub-login]") as HTMLIFrameElement;
        expect(frame).toBeTruthy();
        expect(frame.style.display).toBe("none");

        frame.dispatchEvent(new Event("load"));

        await expect(promise).resolves.toBeUndefined();
        expect(document.querySelector("iframe[data-hub-login]")).toBeNull();
    });
});
```

- [ ] **Step 2: Write it**

`lib/hubLogin.ts`:

```ts
const LOGIN_TIMEOUT_MS = 20_000;

function escapeAttribute(value: string): string {
    return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function hubLoginFormHtml(token: string, next: string, loginUrl: string): string {
    return `<form method="post" action="${escapeAttribute(loginUrl)}">`
        + `<input type="hidden" name="token" value="${escapeAttribute(token)}">`
        + `<input type="hidden" name="next" value="${escapeAttribute(next)}">`
        + `</form><script>document.forms[0].submit()</script>`;
}

/**
 * Logs the browser into the hub by posting the session token as a form inside
 * a hidden iframe: the hub sets its cookie on the response and redirects to
 * `next`. The token never appears in a URL.
 */
export function submitHubLogin(doc: Document, token: string, next: string, loginUrl = "/hub/login"): Promise<void> {
    return new Promise((resolve, reject) => {
        const frame = doc.createElement("iframe");
        frame.setAttribute("data-hub-login", "1");
        frame.style.display = "none";
        let loads = 0;
        const done = (error?: Error) => {
            clearTimeout(timer);
            frame.remove();
            error ? reject(error) : resolve();
        };
        const timer = setTimeout(() => done(new Error("hub login timed out")), LOGIN_TIMEOUT_MS);
        frame.addEventListener("load", () => {
            // The first load is the srcdoc form; the second is the hub's answer.
            loads += 1;
            if (loads >= 2 || !("srcdoc" in frame)) done();
        });
        doc.body.appendChild(frame);
        if ("srcdoc" in frame) {
            frame.srcdoc = hubLoginFormHtml(token, next, loginUrl);
        } else {
            done(new Error("srcdoc unsupported"));
        }
    });
}
```

In jsdom `srcdoc` exists on the element but no navigation happens, so the test dispatches one `load`; count the first load as done when the test environment never fires a second one: make the resolve condition `loads >= 2 || process.env.NODE_ENV === "test"`? No: keep the code honest and change the test to dispatch `load` twice. Update the test's middle line to:

```ts
        frame.dispatchEvent(new Event("load"));
        frame.dispatchEvent(new Event("load"));
```

Run: `npx jest lib/__tests__/hubLogin.test.ts`
Expected: 2 passed

- [ ] **Step 3: Commit**

```bash
git add lib/hubLogin.ts lib/__tests__/hubLogin.test.ts
git commit -m "feat(notebooks): log the browser into the hub with a form post, never a URL"
```

---

### Task 5: The list page

**Files:**
- Create: `components/Notebooks/SessionPill.tsx`, `NotebooksTable.tsx`, `CapacityCounters.tsx`, `NewNotebookDialog.tsx`, `NotebooksDisabled.tsx`, `__tests__/SessionPill.test.tsx`, `__tests__/NotebooksTable.test.tsx`, `__tests__/NewNotebookDialog.test.tsx`, `__tests__/NotebooksDisabled.test.tsx`
- Replace: `pages/app/notebooks/index.tsx`

**Interfaces:**
- Produces: `SessionPill({ session })`; `NotebooksTable({ notebooks })` with rows linking to `ROUTE_PAGE_NOTEBOOK_DETAILS`; `CapacityCounters({ capacity })`; `NewNotebookDialog({ show, onClose, dataset?, version?, fileIds? })` creating through `BFFAPI.createNotebook` then `Router.push` to the editor; `NotebooksDisabled()`.

- [ ] **Step 1: Failing tests**

`components/Notebooks/__tests__/SessionPill.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { SessionPill } from "../SessionPill";

describe("SessionPill", () => {
    test("names each state", () => {
        render(<SessionPill session={{ state: "running" } as any} />);
        expect(screen.getByText("Running")).toBeTruthy();
    });
    test("a notebook that never ran is Not started", () => {
        render(<SessionPill session={null} />);
        expect(screen.getByText("Not started")).toBeTruthy();
    });
    test("idle becomes Stopped, as the design says", () => {
        render(<SessionPill session={{ state: "stopped", stop_reason: "idle" } as any} />);
        expect(screen.getByText("Stopped")).toBeTruthy();
    });
});
```

`components/Notebooks/__tests__/NotebooksTable.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { NotebooksTable } from "../NotebooksTable";

const notebook = (overrides: any = {}): any => ({
    id: "n1", name: "smps_monthly_climatology", path: "smps_monthly_climatology.ipynb", kernel: "python3",
    size_bytes: 38000, created_at: "2026-10-01T10:00:00Z", updated_at: "2026-10-03T17:42:00Z",
    dataset: { id: "d1", title: "GoAmazon T3", version_name: "2", source_deleted: false },
    file_ids: null, mounted_files: 14, mounted_bytes: 2469606195, session: { state: "running" },
    ...overrides,
});

describe("NotebooksTable", () => {
    test("one row per notebook linking to its page, with dataset and version", () => {
        render(<NotebooksTable notebooks={[notebook()]} />);

        expect(screen.getByRole("link", { name: /smps_monthly_climatology/ }).getAttribute("href")).toBe("/app/notebooks/n1");
        expect(screen.getByText("GoAmazon T3")).toBeTruthy();
        expect(screen.getByText("v2")).toBeTruthy();
        expect(screen.getByText("Running")).toBeTruthy();
    });

    test("a deleted source is named as such", () => {
        render(<NotebooksTable notebooks={[notebook({ dataset: { id: null, title: null, version_name: "1", source_deleted: true } })]} />);

        expect(screen.getByText(/source deleted/)).toBeTruthy();
    });

    test("the empty list says what to do", () => {
        render(<NotebooksTable notebooks={[]} />);

        expect(screen.getByText(/No notebooks yet/)).toBeTruthy();
    });
});
```

`components/Notebooks/__tests__/NewNotebookDialog.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test, beforeEach } from '@jest/globals';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const createNotebook = jest.fn() as any;
const push = jest.fn();
let datasets: any;

jest.mock("../../../gateways/BFFAPI", () => ({ BFFAPI: jest.fn().mockImplementation(() => ({ createNotebook })) }));
jest.mock("swr", () => ({ __esModule: true, default: () => ({ data: datasets, error: undefined }) }));
jest.mock("next/router", () => ({ __esModule: true, default: { push: (...a: any[]) => push(...a) }, useRouter: () => ({ push }) }));
jest.mock("../../../lib/fetcher", () => ({ fetcher: jest.fn(), SWRRetry: jest.fn() }));

import { NewNotebookDialog } from "../NewNotebookDialog";

const published = { id: "d1", name: "GoAmazon T3", current_version: { name: "2", design_state: "PUBLISHED", files_count: 14, files_size_in_bytes: 2469606195 } };

beforeEach(() => { createNotebook.mockReset(); push.mockReset(); datasets = { content: [published] }; });

describe("NewNotebookDialog", () => {
    test("creates on the chosen dataset and kernel, then opens the editor", async () => {
        createNotebook.mockResolvedValue({ id: "n9" });
        render(<NewNotebookDialog show onClose={jest.fn()} />);

        fireEvent.click(screen.getByText("GoAmazon T3"));
        fireEvent.click(screen.getByLabelText("R"));
        fireEvent.click(screen.getByRole("button", { name: "Open notebook" }));

        await waitFor(() => expect(createNotebook).toHaveBeenCalledWith({ dataset_id: "d1", version_name: "2", kernel: "ir", name: undefined, file_ids: undefined }));
        expect(push).toHaveBeenCalledWith("/app/notebooks/n9");
    });

    test("prefilled from a dataset page it skips the search", async () => {
        createNotebook.mockResolvedValue({ id: "n9" });
        render(<NewNotebookDialog show onClose={jest.fn()} dataset={{ id: "d1", name: "GoAmazon T3" } as any} version={{ name: "2" } as any} fileIds={["f1"]} />);

        expect(screen.queryByPlaceholderText("Search datasets you can read")).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Open notebook" }));

        await waitFor(() => expect(createNotebook).toHaveBeenCalledWith(expect.objectContaining({ dataset_id: "d1", version_name: "2", file_ids: ["f1"] })));
    });

    test("a gatekeeper refusal is shown with its message", async () => {
        createNotebook.mockRejectedValue({ detail: "selection_too_large", max_bytes: 100, selected_bytes: 200 });
        render(<NewNotebookDialog show onClose={jest.fn()} dataset={{ id: "d1", name: "x" } as any} version={{ name: "2" } as any} />);

        fireEvent.click(screen.getByRole("button", { name: "Open notebook" }));

        await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Choose fewer files"));
    });
});
```

`components/Notebooks/__tests__/NotebooksDisabled.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { NotebooksDisabled } from "../NotebooksDisabled";

describe("NotebooksDisabled", () => {
    test("explains the gradual release", () => {
        render(<NotebooksDisabled />);
        expect(screen.getByText(/not enabled for your account yet/)).toBeTruthy();
    });
});
```

Run: `npx jest components/Notebooks`
Expected: FAIL (modules not found)

- [ ] **Step 2: Components**

`components/Notebooks/SessionPill.tsx`:

```tsx
import { NOTEBOOK_TEXT } from "../../contants/NotebookConstants";
import { sessionPhase } from "../../lib/notebookSession";
import { NotebookSession, SessionStatus } from "../../types/GatekeeperAPI";

const STYLE: Record<string, string> = {
    running: "text-[#14532d] bg-[#dcfce7]",
    starting: "text-primary-700 bg-primary-200",
    stopped: "text-primary-500 bg-primary-100",
    ended: "text-primary-500 bg-primary-100",
    failed: "text-error-700 bg-error-200",
    none: "text-primary-400 bg-primary-50",
};

export function SessionPill(props: { session: NotebookSession | SessionStatus | null | undefined }) {
    const phase = sessionPhase(props.session);
    const label = NOTEBOOK_TEXT.session[phase];
    return (
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-[3px] rounded-full text-xs leading-[18px] font-semibold ${STYLE[phase]}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${phase === "running" ? "bg-[#16a34a]" : "bg-current opacity-60"}`} aria-hidden="true" />
            {label}
        </span>
    );
}
```

`components/Notebooks/NotebooksTable.tsx`:

```tsx
import Link from "next/link";
import Moment from "react-moment";
import { ROUTE_PAGE_NOTEBOOK_DETAILS } from "../../contants/InternalRoutesConstants";
import { NOTEBOOK_TEXT } from "../../contants/NotebookConstants";
import { Notebook } from "../../types/GatekeeperAPI";
import { SessionPill } from "./SessionPill";

export function NotebooksTable(props: { notebooks: Notebook[] }) {
    if (!props.notebooks.length) {
        return (
            <div className="mt-8 flex flex-col items-center gap-3 rounded-lg border border-dashed border-primary-300 bg-primary-0 px-6 py-16 text-center">
                <p className="m-0 max-w-md text-sm text-primary-600">{NOTEBOOK_TEXT.page.empty}</p>
            </div>
        );
    }
    const columns = "grid grid-cols-[minmax(0,1.6fr)_minmax(0,1.2fr)_130px_130px] items-center gap-3";
    return (
        <div className="mt-6 border border-primary-200 rounded-lg bg-primary-0 overflow-hidden">
            <div className={`${columns} px-4 py-2 text-[11px] tracking-[0.08em] uppercase font-semibold text-primary-500 border-b border-primary-200 bg-primary-50`}>
                <span>{NOTEBOOK_TEXT.page.columns.notebook}</span>
                <span>{NOTEBOOK_TEXT.page.columns.dataset}</span>
                <span>{NOTEBOOK_TEXT.page.columns.session}</span>
                <span>{NOTEBOOK_TEXT.page.columns.edited}</span>
            </div>
            <ul className="list-none m-0 p-0">
                {props.notebooks.map(notebook => (
                    <li key={notebook.id} className={`${columns} min-h-[52px] px-4 py-2 border-b border-primary-100 last:border-b-0 text-sm hover:bg-primary-50`}>
                        <span className="min-w-0 flex flex-col">
                            <Link href={ROUTE_PAGE_NOTEBOOK_DETAILS({ id: notebook.id })} className="font-mono text-[13px] text-primary-900 truncate hover:underline">
                                {notebook.name}
                            </Link>
                            <span className="text-xs text-primary-500">{notebook.kernel === "ir" ? "R" : "Python"}</span>
                        </span>
                        <span className="min-w-0 flex flex-col">
                            {notebook.dataset?.source_deleted
                                ? <span className="text-primary-400 line-through truncate">{notebook.dataset.title ?? "—"} <span className="no-underline">— {NOTEBOOK_TEXT.page.sourceDeleted}</span></span>
                                : <span className="truncate text-primary-900">{notebook.dataset?.title ?? "—"}</span>}
                            {notebook.dataset?.version_name && <span className="font-mono text-xs text-primary-500">v{notebook.dataset.version_name}</span>}
                        </span>
                        <span><SessionPill session={notebook.session} /></span>
                        <span className="text-[13px] text-primary-600"><Moment date={notebook.updated_at} fromNow /></span>
                    </li>
                ))}
            </ul>
        </div>
    );
}
```

`components/Notebooks/CapacityCounters.tsx`:

```tsx
import { NOTEBOOK_TEXT } from "../../contants/NotebookConstants";
import { bytesToSize } from "../../lib/file";
import { NotebookCapacity } from "../../types/GatekeeperAPI";

export function CapacityCounters(props: { capacity?: NotebookCapacity }) {
    if (!props.capacity) return null;
    const { seats_taken, seats_total, storage_used_bytes, storage_quota_bytes } = props.capacity;
    return (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[13px] text-primary-600">
            <span><span className="font-semibold text-primary-900">{seats_taken}</span> of {seats_total} {seats_taken === 1 ? NOTEBOOK_TEXT.page.sessionRunning : NOTEBOOK_TEXT.page.sessionsRunning}</span>
            <span><span className="font-semibold text-primary-900">{bytesToSize(storage_used_bytes)}</span> of {bytesToSize(storage_quota_bytes)} {NOTEBOOK_TEXT.page.storage}</span>
        </div>
    );
}
```

`components/Notebooks/NotebooksDisabled.tsx`:

```tsx
import { NOTEBOOK_TEXT } from "../../contants/NotebookConstants";

export function NotebooksDisabled() {
    return (
        <div data-testid="notebooks-disabled" className="mt-8 rounded-lg border border-primary-200 bg-primary-0 p-6">
            <h5 className="m-0">{NOTEBOOK_TEXT.disabled.title}</h5>
            <p className="text-sm text-primary-700 mt-2 mb-0">{NOTEBOOK_TEXT.disabled.body}</p>
        </div>
    );
}
```

`components/Notebooks/NewNotebookDialog.tsx`:

```tsx
import Router from "next/router";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { EDIT_FORM_ERROR_CLASS } from "../../contants/EditFormConstants";
import { ROUTE_PAGE_NOTEBOOK_DETAILS } from "../../contants/InternalRoutesConstants";
import { NOTEBOOK_KERNELS, NOTEBOOK_TEXT, messageForNotebookError } from "../../contants/NotebookConstants";
import { BFFAPI } from "../../gateways/BFFAPI";
import { bytesToSize } from "../../lib/file";
import { SWRRetry, fetcher } from "../../lib/fetcher";
import { GetDatasetsResponse, GetMinimalDatasetsDetasetDetailsResponse } from "../../types/BffAPI";
import { NotebookKernel } from "../../types/GatekeeperAPI";
import Modal from "../base/PopupModal";

interface Props {
    show: boolean
    onClose(): void
    dataset?: { id: string, name: string }
    version?: { name: string }
    fileIds?: string[]
}

export function NewNotebookDialog(props: Props) {
    const [bffGateway] = useState(() => new BFFAPI());
    const [search, setSearch] = useState("");
    const [chosen, setChosen] = useState<{ id: string, name: string, version: string } | null>(
        props.dataset && props.version ? { id: props.dataset.id, name: props.dataset.name, version: props.version.name } : null
    );
    const [kernel, setKernel] = useState<NotebookKernel>("python3");
    const [name, setName] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const prefilled = Boolean(props.dataset && props.version);

    const { data } = useSWR<GetDatasetsResponse>(
        props.show && !prefilled ? `/api/datasets?minimal=true&page=1&page_size=30&full_text=${encodeURIComponent(search)}` : null,
        fetcher,
        { onErrorRetry: SWRRetry }
    );
    const candidates = useMemo(
        () => ((data?.content ?? []) as GetMinimalDatasetsDetasetDetailsResponse[]).filter(d => (d.current_version?.design_state ?? "").toString().toUpperCase() === "PUBLISHED"),
        [data]
    );

    async function create() {
        if (!chosen) return;
        setBusy(true);
        setError(null);
        try {
            const notebook = await bffGateway.createNotebook({
                dataset_id: chosen.id,
                version_name: chosen.version,
                kernel,
                name: name.trim() || undefined,
                file_ids: props.fileIds,
            });
            props.onClose();
            Router.push(ROUTE_PAGE_NOTEBOOK_DETAILS({ id: notebook.id }));
        } catch (e) {
            setError(messageForNotebookError(e));
        } finally {
            setBusy(false);
        }
    }

    return (
        <Modal title={NOTEBOOK_TEXT.create.title} show={props.show} confimButtonText={busy ? NOTEBOOK_TEXT.create.creating : NOTEBOOK_TEXT.create.create}
            cancelButtonText="Cancel" cancel={props.onClose} confim={create} confirmDisabled={busy || !chosen} maxWidthClassName="max-w-2xl">
            <div className="flex flex-col gap-4">
                {!prefilled && (
                    <div className="flex flex-col gap-2">
                        <label className="text-[13px] font-semibold text-primary-900">{NOTEBOOK_TEXT.create.dataset}</label>
                        <input type="search" className="h-9 py-0 px-3 bg-primary-0 rounded-md" placeholder={NOTEBOOK_TEXT.create.searchDatasets} value={search} onChange={e => setSearch(e.target.value)} />
                        <ul className="list-none m-0 p-0 max-h-56 overflow-y-auto border border-primary-200 rounded-md">
                            {candidates.map(d => (
                                <li key={d.id}>
                                    <button type="button" onClick={() => setChosen({ id: d.id, name: d.name, version: d.current_version.name })}
                                        className={`w-full text-left px-3 py-2 text-sm border-b border-primary-100 last:border-b-0 hover:bg-primary-50 ${chosen?.id === d.id ? "bg-primary-100" : ""}`}>
                                        <span className="text-primary-900">{d.name}</span>
                                        <span className="ml-2 font-mono text-xs text-primary-500">v{d.current_version.name} · {d.current_version.files_count} files · {bytesToSize(d.current_version.files_size_in_bytes ?? 0)}</span>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
                {prefilled && <p className="m-0 text-sm text-primary-700">{chosen?.name} <span className="font-mono text-xs text-primary-500">v{chosen?.version}</span></p>}
                <fieldset className="flex flex-col gap-2">
                    <legend className="text-[13px] font-semibold text-primary-900">{NOTEBOOK_TEXT.create.kernel}</legend>
                    {NOTEBOOK_KERNELS.map(k => (
                        <label key={k.value} className="flex items-center gap-2 text-sm">
                            <input type="radio" name="kernel" value={k.value} checked={kernel === k.value} onChange={() => setKernel(k.value)} aria-label={k.label} />
                            <span className="text-primary-900">{k.label}</span>
                            <span className="text-xs text-primary-500">{k.hint}</span>
                        </label>
                    ))}
                </fieldset>
                <label className="flex flex-col gap-1 text-[13px] font-semibold text-primary-900">
                    {NOTEBOOK_TEXT.create.name}
                    <input type="text" className="h-9 py-0 px-3 bg-primary-0 rounded-md font-mono text-[13px] font-normal" placeholder={NOTEBOOK_TEXT.create.namePlaceholder} value={name} onChange={e => setName(e.target.value)} maxLength={128} />
                </label>
                {error && <p role="alert" className={EDIT_FORM_ERROR_CLASS}>{error}</p>}
            </div>
        </Modal>
    );
}
```

`GetDatasetsResponse` holds `content`; check `types/BffAPI.ts:145` for the exact field (`content` in `pages/app/datasets/index.tsx`'s usage) and the shape of the minimal item's `current_version`.

- [ ] **Step 3: The page**

Replace `pages/app/notebooks/index.tsx`:

```tsx
import { useState } from "react";
import useSWR from "swr";
import LoggedLayout from "../../../components/LoggedLayout";
import { CapacityCounters } from "../../../components/Notebooks/CapacityCounters";
import { NewNotebookDialog } from "../../../components/Notebooks/NewNotebookDialog";
import { NotebooksDisabled } from "../../../components/Notebooks/NotebooksDisabled";
import { NotebooksTable } from "../../../components/Notebooks/NotebooksTable";
import { NOTEBOOK_TEXT } from "../../../contants/NotebookConstants";
import { SWRRetry, fetcher } from "../../../lib/fetcher";
import { NotebookCapacity, NotebookList } from "../../../types/GatekeeperAPI";

export default function ListNotebooksPage() {
  const [showNew, setShowNew] = useState(false);
  const { data: capacity, error: capacityError } = useSWR<NotebookCapacity>("/api/notebooks/capacity", fetcher, { onErrorRetry: SWRRetry });
  const { data: notebooks } = useSWR<NotebookList>(capacity ? "/api/notebooks" : null, fetcher, { onErrorRetry: SWRRetry, refreshInterval: 15_000 });
  const disabled = capacityError?.status === 401 || capacityError?.status === 403;

  return (
    <LoggedLayout>
      <div className="w-full max-w-5xl mx-auto">
        <div className="flex flex-wrap justify-between items-end gap-6">
          <div>
            <h2 className="m-0">{NOTEBOOK_TEXT.page.title}</h2>
            <p className="mt-2 mb-0 text-[15px] leading-[23px] text-primary-600">{NOTEBOOK_TEXT.page.subtitle}</p>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" className="btn-primary-outline m-0 flex-none" disabled title={NOTEBOOK_TEXT.page.comingLater}>{NOTEBOOK_TEXT.page.fromTemplate}</button>
            <button type="button" className="btn-primary m-0 flex-none" disabled={disabled || !capacity} onClick={() => setShowNew(true)}>{NOTEBOOK_TEXT.page.newNotebook}</button>
          </div>
        </div>
        {disabled
          ? <NotebooksDisabled />
          : <>
            <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-b border-primary-200 pb-3">
              <nav className="flex gap-6" aria-label="Notebooks">
                <span className="pb-0 text-sm font-medium border-b-2 border-primary-900 text-primary-900">{NOTEBOOK_TEXT.page.mine}{notebooks && <span className="ml-1.5 font-normal text-primary-500">{notebooks.content.length}</span>}</span>
                <span className="text-sm font-medium text-primary-400" title={NOTEBOOK_TEXT.page.comingLater}>{NOTEBOOK_TEXT.page.sharedWithMe}</span>
              </nav>
              <CapacityCounters capacity={capacity} />
            </div>
            {notebooks && <NotebooksTable notebooks={notebooks.content} />}
          </>}
        <NewNotebookDialog show={showNew} onClose={() => setShowNew(false)} />
      </div>
    </LoggedLayout>
  );
}

ListNotebooksPage.auth = {
  role: "admin",
  loading: <div>loading...</div>,
};
```

`ListNotebooksPage.auth.role` is not enforced by `_app.tsx` (its comment says so); the gate is the gatekeeper answering 401 on capacity, which this page turns into `NotebooksDisabled`. The sidebar entry stays visible for everyone, which is what the design and the RFC want: people see the feature exists and learn how to get it.

- [ ] **Step 4: Run and commit**

Run: `npx jest components/Notebooks contants`
Expected: all passed

```bash
git add components/Notebooks pages/app/notebooks/index.tsx
git commit -m "feat(notebooks): the list page - seats, storage, table, new-notebook dialog, disabled state"
```

---

### Task 6: The file selection dialog

**Files:**
- Create: `components/Notebooks/FileSelectionDialog.tsx`, `components/Notebooks/__tests__/FileSelectionDialog.test.tsx`

**Interfaces:**
- Produces: `FileSelectionDialog({ show, onClose, files, maxBytes, initial?: string[] | null, onConfirm(ids: string[]), restartNote?: boolean })`. `files` are `GetDatasetDetailsVersionFileResponse[]`. Confirm is disabled while the total is over `maxBytes`; a single file over `maxBytes` is greyed with the reason.

- [ ] **Step 1: Failing test**

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react';
import { FileSelectionDialog } from "../FileSelectionDialog";

const files: any = [
    { id: "a", name: "a.nc", size_bytes: 30 },
    { id: "b", name: "b.nc", size_bytes: 30 },
    { id: "big", name: "huge.nc", size_bytes: 500 },
];

describe("FileSelectionDialog", () => {
    test("shows the running total against the limit and refuses to go over", () => {
        const onConfirm = jest.fn();
        render(<FileSelectionDialog show onClose={jest.fn()} files={files} maxBytes={50} initial={[]} onConfirm={onConfirm} />);

        fireEvent.click(screen.getByLabelText("a.nc"));
        expect(screen.getByText(/30 B/)).toBeTruthy();
        fireEvent.click(screen.getByLabelText("b.nc"));
        expect(screen.getByText(/Over the limit/)).toBeTruthy();
        expect((screen.getByRole("button", { name: "Mount these files" }) as HTMLButtonElement).disabled).toBe(true);

        fireEvent.click(screen.getByLabelText("b.nc"));
        fireEvent.click(screen.getByRole("button", { name: "Mount these files" }));
        expect(onConfirm).toHaveBeenCalledWith(["a"]);
    });

    test("a file over the limit on its own cannot be chosen", () => {
        render(<FileSelectionDialog show onClose={jest.fn()} files={files} maxBytes={50} initial={[]} onConfirm={jest.fn()} />);

        const big = screen.getByLabelText("huge.nc") as HTMLInputElement;
        expect(big.disabled).toBe(true);
        expect(screen.getByTitle("This file alone is over the session limit.")).toBeTruthy();
    });

    test("filters by name and selects all that fit", () => {
        const onConfirm = jest.fn();
        render(<FileSelectionDialog show onClose={jest.fn()} files={files} maxBytes={100} initial={null} onConfirm={onConfirm} />);

        fireEvent.change(screen.getByPlaceholderText("Filter by name"), { target: { value: "b" } });
        expect(screen.queryByLabelText("a.nc")).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "None" }));
        fireEvent.click(screen.getByRole("button", { name: "All" }));
        fireEvent.click(screen.getByRole("button", { name: "Mount these files" }));
        expect(onConfirm).toHaveBeenCalledWith(["a", "b"]);
    });
});
```

(`initial={null}` means "everything was selected", so the dialog starts with every file that fits checked; `All` selects every file that fits, never the ones over the limit.)

- [ ] **Step 2: Component**

```tsx
import { useMemo, useState } from "react";
import { NOTEBOOK_TEXT } from "../../contants/NotebookConstants";
import { bytesToSize, fileNameResolution } from "../../lib/file";
import { selectionFits, selectionTotal } from "../../lib/notebookSession";
import { GetDatasetDetailsVersionFileResponse } from "../../types/BffAPI";
import Modal from "../base/PopupModal";

interface Props {
    show: boolean
    onClose(): void
    files: GetDatasetDetailsVersionFileResponse[]
    maxBytes: number
    initial?: string[] | null
    onConfirm(ids: string[]): void
    restartNote?: boolean
}

export function FileSelectionDialog(props: Props) {
    const fits = (f: GetDatasetDetailsVersionFileResponse) => (f.size_bytes ?? 0) <= props.maxBytes;
    const [selected, setSelected] = useState<Set<string>>(() => new Set(
        props.initial === null || props.initial === undefined ? props.files.filter(fits).map(f => f.id) : props.initial
    ));
    const [filter, setFilter] = useState("");
    const visible = useMemo(
        () => props.files.filter(f => f.name.toLowerCase().includes(filter.toLowerCase())).sort((a, b) => a.name.localeCompare(b.name)),
        [props.files, filter]
    );
    const total = selectionTotal(props.files, Array.from(selected));
    const ok = selectionFits(total, props.maxBytes) && selected.size > 0;

    function toggle(id: string) {
        const next = new Set(selected);
        next.has(id) ? next.delete(id) : next.add(id);
        setSelected(next);
    }

    return (
        <Modal title={NOTEBOOK_TEXT.picker.title} show={props.show} confimButtonText={NOTEBOOK_TEXT.picker.confirm} cancelButtonText="Cancel"
            cancel={props.onClose} confim={() => ok && props.onConfirm(Array.from(selected))} confirmDisabled={!ok} maxWidthClassName="max-w-2xl" noPaddingContent>
            <div className="flex flex-col">
                <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 border-b border-primary-200">
                    <input type="search" className="h-9 py-0 px-3 bg-primary-0 rounded-md" placeholder={NOTEBOOK_TEXT.picker.search} value={filter} onChange={e => setFilter(e.target.value)} />
                    <div className="flex items-center gap-2 text-[13px]">
                        <button type="button" className="btn-primary-outline btn-small m-0" onClick={() => setSelected(new Set(props.files.filter(fits).map(f => f.id)))}>{NOTEBOOK_TEXT.picker.all}</button>
                        <button type="button" className="btn-primary-outline btn-small m-0" onClick={() => setSelected(new Set())}>{NOTEBOOK_TEXT.picker.none}</button>
                    </div>
                </div>
                <ul className="list-none m-0 p-0 max-h-80 overflow-y-auto">
                    {visible.map(file => {
                        const tooBig = !fits(file);
                        return (
                            <li key={file.id} className="flex items-center gap-3 px-5 h-10 border-b border-primary-100 last:border-b-0 text-sm" title={tooBig ? NOTEBOOK_TEXT.picker.tooBigFile : undefined}>
                                <input type="checkbox" id={`pick-${file.id}`} checked={selected.has(file.id)} disabled={tooBig} onChange={() => toggle(file.id)} />
                                <label htmlFor={`pick-${file.id}`} className={`flex-1 min-w-0 font-mono text-[13px] truncate ${tooBig ? "text-primary-400" : "text-primary-900"}`}>{fileNameResolution(file.name)}</label>
                                <span className="font-mono text-xs text-primary-500">{bytesToSize(file.size_bytes ?? 0)}</span>
                            </li>
                        );
                    })}
                </ul>
                <div className={`flex items-center justify-between px-5 py-3 border-t border-primary-200 text-[13px] ${ok || selected.size === 0 ? "text-primary-600" : "text-error-700"}`}>
                    <span>{selected.size} {NOTEBOOK_TEXT.picker.selected} · {bytesToSize(total)} {NOTEBOOK_TEXT.picker.of ?? "/"} {bytesToSize(props.maxBytes)} {NOTEBOOK_TEXT.picker.limit}</span>
                    {!selectionFits(total, props.maxBytes) && <span>{NOTEBOOK_TEXT.picker.overLimit}</span>}
                    {props.restartNote && ok && <span className="text-primary-500">{NOTEBOOK_TEXT.picker.restartNote}</span>}
                </div>
            </div>
        </Modal>
    );
}
```

`fileNameResolution` shortens a path for display; the `<label>` text is what the tests query, so if it shortens `a.nc` to something else, query by the full name in the test instead.

Run: `npx jest components/Notebooks/__tests__/FileSelectionDialog.test.tsx`
Expected: 3 passed

- [ ] **Step 3: Commit**

```bash
git add components/Notebooks/FileSelectionDialog.tsx components/Notebooks/__tests__/FileSelectionDialog.test.tsx
git commit -m "feat(notebooks): the file picker, with the running total against the session limit"
```

---

### Task 7: The editor page

**Files:**
- Create: `hooks/UseNotebookSession.ts`
- Create: `components/Notebooks/SessionChip.tsx`, `ResourceUsage.tsx`, `NotebookTopBar.tsx`, `SessionStateView.tsx`, `LabFrame.tsx`, `NotebookSidePanel.tsx`, `NotebookReadOnly.tsx`, `MarkdownCell.tsx`
- Create: `components/Notebooks/__tests__/SessionChip.test.tsx`, `__tests__/SessionStateView.test.tsx`, `__tests__/NotebookSidePanel.test.tsx`, `__tests__/NotebookReadOnly.test.tsx`
- Create: `pages/app/notebooks/[notebookId].tsx`

**Interfaces:**
- `useNotebookSession(notebookId)` → `{ session: SessionStatus | undefined, mutate }` polling at `pollInterval(sessionPhase(session))`.
- `SessionChip({ session, now, usage? })` → pill + `CPU x / n` + `RAM a / b` + remaining bar, amber when approaching.
- `ResourceUsage({ userId, enabled })` → `usage` object polled from `/user/<uid>/api/metrics/v1`; rendered inside the chip.
- `NotebookTopBar({ notebook, session, usage, onRename, onStop, onDownload, onChangeSelection, onDelete })`.
- `SessionStateView({ phase, session, notebook, refusal, onResume, onStartNew, onReadOnly, onTryAgain })` renders the non-running states and the `refusal` (`no_seats`, `storage_full`, `session_elsewhere`, `hub_unavailable`) the start call returned.
- `LabFrame({ labPath, title })` → the iframe.
- `NotebookSidePanel({ notebook, session, onChangeSelection })` → dataset card, mounted files, snippets with copy, outputs note.
- `NotebookReadOnly({ content })` → cells rendered without a kernel; `MarkdownCell` in its own file imports `react-markdown`.

- [ ] **Step 1: Failing tests**

`components/Notebooks/__tests__/SessionChip.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import { SessionChip } from "../SessionChip";

const NOW = new Date("2026-10-04T12:00:00Z");
const running: any = { state: "running", started_at: "2026-10-04T10:42:00Z", max_hours: 12 };

describe("SessionChip", () => {
    test("shows state, usage and time used of the limit", () => {
        render(<SessionChip session={running} now={NOW} usage={{ cpuPercent: 40, cpuCount: 2, rss: 1.1 * 1024 ** 3, limit: 12 * 1024 ** 3 }} />);

        expect(screen.getByText("Running")).toBeTruthy();
        expect(screen.getByText("0.4 / 2")).toBeTruthy();
        expect(screen.getByText("1.1 GB / 12 GB")).toBeTruthy();  // exact text follows bytesToSize; adjust if it prints "12.0 GB"
        expect(screen.getByText("1 h 18 m / 12 h")).toBeTruthy();
    });

    test("turns amber and counts down under thirty minutes", () => {
        render(<SessionChip session={{ ...running, started_at: "2026-10-04T00:20:00Z" }} now={NOW} usage={undefined} />);

        expect(screen.getByText("20 min left")).toBeTruthy();
        expect(screen.getByTestId("session-chip").className).toContain("embargo");
    });

    test("missing usage shows dashes, never zeros", () => {
        render(<SessionChip session={running} now={NOW} usage={undefined} />);

        expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    });
});
```

`components/Notebooks/__tests__/SessionStateView.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react';
import { SessionStateView } from "../SessionStateView";

const notebook: any = { id: "n1", name: "x", dataset: { id: "d1", title: "T", version_name: "2", source_deleted: false }, mounted_files: 14, mounted_bytes: 2469606195 };

describe("SessionStateView", () => {
    test("starting shows the progress lines", () => {
        render(<SessionStateView phase="starting" session={{ state: "starting", progress: ["Preparing your session", "Mounting 14 files · 2.3 GB"], max_hours: 12 } as any} notebook={notebook} />);

        expect(screen.getByText("Starting your session")).toBeTruthy();
        expect(screen.getByText("Mounting 14 files · 2.3 GB")).toBeTruthy();
    });

    test("stopped offers Resume and Read only", () => {
        const onResume = jest.fn();
        const onReadOnly = jest.fn();
        render(<SessionStateView phase="stopped" session={{ state: "stopped", stopped_at: "2026-10-03T18:40:00Z", stop_reason: "idle", max_hours: 12 } as any} notebook={notebook} onResume={onResume} onReadOnly={onReadOnly} />);

        fireEvent.click(screen.getByRole("button", { name: "Resume" }));
        fireEvent.click(screen.getByRole("button", { name: "Read only" }));
        expect(onResume).toHaveBeenCalled();
        expect(onReadOnly).toHaveBeenCalled();
    });

    test("ended names the limit and offers a new session", () => {
        render(<SessionStateView phase="ended" session={{ state: "ended", stop_reason: "max_age", max_hours: 12 } as any} notebook={notebook} onStartNew={jest.fn()} />);

        expect(screen.getByText(/12 h limit/)).toBeTruthy();
        expect(screen.getByRole("button", { name: "Start new session" })).toBeTruthy();
    });

    test("a refusal replaces the state: no seats", () => {
        render(<SessionStateView phase="none" session={null} notebook={notebook} refusal={{ detail: "no_seats", seats_total: 4 }} onTryAgain={jest.fn()} />);

        expect(screen.getByText("All 4 seats are in use")).toBeTruthy();
        expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    });

    test("a deleted source says so and does not offer to start", () => {
        render(<SessionStateView phase="none" session={null} notebook={{ ...notebook, dataset: { ...notebook.dataset, source_deleted: true } }} />);

        expect(screen.getByText(/was deleted/)).toBeTruthy();
        expect(screen.queryByRole("button", { name: /Resume|Start/ })).toBeNull();
    });

    test("an administrator's stop is named", () => {
        render(<SessionStateView phase="stopped" session={{ state: "stopped", stop_reason: "admin", max_hours: 12 } as any} notebook={notebook} />);

        expect(screen.getByText("Stopped by an administrator.")).toBeTruthy();
    });
});
```

`components/Notebooks/__tests__/NotebookSidePanel.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { NotebookSidePanel } from "../NotebookSidePanel";

const notebook: any = { id: "n1", kernel: "python3", dataset: { id: "d1", title: "GoAmazon T3", version_name: "2", source_deleted: false }, file_ids: null, mounted_files: 14, mounted_bytes: 2469606195 };

describe("NotebookSidePanel", () => {
    test("shows the pinned dataset, the mount count and the snippets", () => {
        render(<NotebookSidePanel notebook={notebook} session={{ state: "running", mounted_files: 14, mounted_bytes: 2469606195 } as any} versionFileCount={40} onChangeSelection={jest.fn()} />);

        expect(screen.getByText("GoAmazon T3")).toBeTruthy();
        expect(screen.getByText(/v2/)).toBeTruthy();
        expect(screen.getByText("14 of 40 files mounted")).toBeTruthy();
        expect(screen.getByText("Open all NetCDF as one xarray")).toBeTruthy();
    });

    test("copies a snippet to the clipboard and says so", async () => {
        const writeText = jest.fn(async () => undefined);
        Object.assign(navigator, { clipboard: { writeText } });
        render(<NotebookSidePanel notebook={notebook} session={null} versionFileCount={14} onChangeSelection={jest.fn()} />);

        fireEvent.click(screen.getAllByRole("button", { name: "Copy" })[0]);

        await waitFor(() => expect(writeText).toHaveBeenCalledWith('da = ds.open_mfdataset("*.nc")'));
        expect(screen.getByText("Copied · paste into a cell")).toBeTruthy();
    });

    test("R notebooks get R snippets", () => {
        render(<NotebookSidePanel notebook={{ ...notebook, kernel: "ir" }} session={null} versionFileCount={14} onChangeSelection={jest.fn()} />);

        expect(screen.getByText("Open a NetCDF with ncdf4")).toBeTruthy();
    });
});
```

`components/Notebooks/__tests__/NotebookReadOnly.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';

jest.mock("../MarkdownCell", () => ({ MarkdownCell: (props: any) => <div data-testid="md">{props.source}</div> }));

import { NotebookReadOnly } from "../NotebookReadOnly";

const content = {
    cells: [
        { cell_type: "code", source: ["import datamap\n", "ds = datamap.open()"], outputs: [{ output_type: "stream", text: ["<Dataset ds-1 v2>\n"] }] },
        { cell_type: "markdown", source: ["# Notes"] },
        { cell_type: "code", source: ["1/0"], outputs: [{ output_type: "error", ename: "ZeroDivisionError", evalue: "division by zero" }] },
    ],
};

describe("NotebookReadOnly", () => {
    test("renders code, stream outputs, markdown and errors without a kernel", () => {
        render(<NotebookReadOnly content={content} />);

        expect(screen.getByText(/import datamap/)).toBeTruthy();
        expect(screen.getByText(/<Dataset ds-1 v2>/)).toBeTruthy();
        expect(screen.getByTestId("md").textContent).toBe("# Notes");
        expect(screen.getByText(/ZeroDivisionError: division by zero/)).toBeTruthy();
        expect(screen.getByText(/Read only/)).toBeTruthy();
    });
});
```

Run: `npx jest components/Notebooks`
Expected: the four new files FAIL (modules not found)

- [ ] **Step 2: Hook and chip**

`hooks/UseNotebookSession.ts`:

```ts
import useSWR from "swr";
import { SWRRetry, fetcher } from "../lib/fetcher";
import { pollInterval, sessionPhase } from "../lib/notebookSession";
import { SessionStatus } from "../types/GatekeeperAPI";

export function useNotebookSession(notebookId: string | undefined) {
    const { data, mutate, error } = useSWR<SessionStatus>(
        notebookId ? `/api/notebooks/${encodeURIComponent(notebookId)}/session` : null,
        fetcher,
        { onErrorRetry: SWRRetry, refreshInterval: (latest) => pollInterval(sessionPhase(latest)) }
    );
    return { session: data, mutate, error };
}
```

`components/Notebooks/ResourceUsage.tsx` (a hook, despite the directory; it renders nothing):

```ts
import { useEffect, useState } from "react";
import { RESOURCE_POLL_MS } from "../../contants/NotebookConstants";

export interface Usage { cpuPercent?: number, cpuCount?: number, rss?: number, limit?: number }

export function useResourceUsage(userId: string | undefined, enabled: boolean): Usage | undefined {
    const [usage, setUsage] = useState<Usage | undefined>(undefined);
    useEffect(() => {
        if (!enabled || !userId) { setUsage(undefined); return; }
        let cancelled = false;
        async function read() {
            try {
                const response = await fetch(`/user/${encodeURIComponent(userId)}/api/metrics/v1`, { credentials: "include" });
                if (!response.ok) return;
                const body = await response.json();
                if (!cancelled) setUsage({ cpuPercent: body.cpu_percent, cpuCount: body.cpu_count, rss: body.rss, limit: body.limits?.memory?.rss });
            } catch {
                // The server is between states; the chip shows dashes until the next read.
            }
        }
        read();
        const timer = setInterval(read, RESOURCE_POLL_MS);
        return () => { cancelled = true; clearInterval(timer); };
    }, [userId, enabled]);
    return usage;
}
```

`components/Notebooks/SessionChip.tsx`:

```tsx
import { NOTEBOOK_TEXT } from "../../contants/NotebookConstants";
import { bytesToSize } from "../../lib/file";
import { formatElapsed, formatRemaining, isLimitApproaching, timeLeftMs } from "../../lib/notebookSession";
import { SessionStatus } from "../../types/GatekeeperAPI";
import { Usage } from "./ResourceUsage";
import { SessionPill } from "./SessionPill";

export function SessionChip(props: { session: SessionStatus | null | undefined, now: Date, usage: Usage | undefined }) {
    const session = props.session;
    const running = session?.state === "running" && !!session.started_at;
    const approaching = isLimitApproaching(session, props.now);
    const left = timeLeftMs(session, props.now);
    const cpu = props.usage?.cpuPercent !== undefined && props.usage?.cpuCount !== undefined
        ? `${(props.usage.cpuPercent / 100).toFixed(1)} / ${props.usage.cpuCount}` : "—";
    const ram = props.usage?.rss !== undefined && props.usage?.limit !== undefined
        ? `${bytesToSize(props.usage.rss)} / ${bytesToSize(props.usage.limit)}` : "—";
    const tone = approaching ? "border-embargo-200 bg-embargo-50 text-embargo-800" : "border-primary-200 bg-primary-0 text-primary-700";
    return (
        <div data-testid="session-chip" className={`inline-flex items-center gap-3 h-[38px] px-3 rounded-md border text-[13px] ${tone}`}>
            <SessionPill session={session} />
            {running && <>
                <span><span className="text-primary-500">{NOTEBOOK_TEXT.session.cpu}</span> {cpu}</span>
                <span><span className="text-primary-500">{NOTEBOOK_TEXT.session.ram}</span> {ram}</span>
                {approaching && left !== null
                    ? <span className="font-semibold">{formatRemaining(left)} {NOTEBOOK_TEXT.session.left}</span>
                    : <span>{formatElapsed(session!.started_at!, props.now)} / {session!.max_hours} h</span>}
            </>}
        </div>
    );
}
```

- [ ] **Step 3: Top bar, states, frame, panel, read-only**

`components/Notebooks/NotebookTopBar.tsx`:

```tsx
import Link from "next/link";
import { useState } from "react";
import { MaterialSymbol } from "react-material-symbols";
import { ROUTE_PAGE_NOTEBOOKS } from "../../contants/InternalRoutesConstants";
import { NOTEBOOK_TEXT } from "../../contants/NotebookConstants";
import useComponentVisible from "../../hooks/UseComponentVisible";
import { Notebook, SessionStatus } from "../../types/GatekeeperAPI";
import { Logo } from "../Brand/Logo";
import { Usage } from "./ResourceUsage";
import { SessionChip } from "./SessionChip";

interface Props {
    notebook: Notebook
    session: SessionStatus | null | undefined
    usage: Usage | undefined
    now: Date
    onRename(name: string): void
    onStop(): void
    onDownload(): void
    onChangeSelection(): void
    onDelete(): void
}

export function NotebookTopBar(props: Props) {
    const [editing, setEditing] = useState(false);
    const [name, setName] = useState(props.notebook.name);
    const menu = useComponentVisible(false);
    const live = props.session?.state === "starting" || props.session?.state === "running";

    return (
        <header className="flex items-center gap-4 h-14 px-4 border-b border-primary-200 bg-primary-0">
            <Link href="/" className="flex items-center"><Logo size="md" /></Link>
            <nav className="flex items-center gap-2 text-sm min-w-0" aria-label="Breadcrumb">
                <Link href={ROUTE_PAGE_NOTEBOOKS} className="text-primary-500 hover:text-primary-900">{NOTEBOOK_TEXT.page.title}</Link>
                <span className="text-primary-300">/</span>
                {editing
                    ? <form onSubmit={e => { e.preventDefault(); setEditing(false); if (name !== props.notebook.name) props.onRename(name); }}>
                        <input autoFocus className="h-8 px-2 font-mono text-[13px] rounded-md" value={name} onChange={e => setName(e.target.value)} onBlur={() => setEditing(false)} aria-label={NOTEBOOK_TEXT.menu.rename} />
                    </form>
                    : <button type="button" className="flex items-center gap-1.5 font-mono text-[13px] text-primary-900 truncate" onClick={() => setEditing(true)}>
                        {props.notebook.path}
                        <MaterialSymbol icon="edit" size={16} grade={-25} weight={400} className="text-primary-400" />
                    </button>}
            </nav>
            <div className="ml-auto flex items-center gap-2">
                <SessionChip session={props.session} now={props.now} usage={props.usage} />
                {live && <button type="button" className="h-[38px] px-3.5 rounded-md border border-primary-300 bg-primary-0 text-primary-900 text-sm font-semibold hover:bg-primary-100" onClick={props.onStop}>{NOTEBOOK_TEXT.session.stop}</button>}
                <button type="button" disabled title={NOTEBOOK_TEXT.panel.outputsHint} className="h-[38px] px-3.5 rounded-md bg-primary-900 text-primary-50 text-sm font-semibold opacity-50 cursor-not-allowed">Save to DataMap</button>
                <div className="relative" ref={menu.ref}>
                    <button type="button" aria-label="More" className="h-[38px] w-[38px] rounded-md border border-primary-300 bg-primary-0 hover:bg-primary-100 flex items-center justify-center" onClick={() => menu.setIsComponentVisible(true)}>
                        <MaterialSymbol icon="more_horiz" size={20} grade={-25} weight={400} />
                    </button>
                    <div className={`${!menu.isComponentVisible && "hidden"} absolute right-0 z-10 mt-1 w-56 rounded-md border border-primary-200 bg-primary-0 shadow-lg py-1`} role="menu">
                        <MenuItem onClick={props.onDownload}>{NOTEBOOK_TEXT.menu.download}</MenuItem>
                        <MenuItem onClick={props.onChangeSelection}>{NOTEBOOK_TEXT.menu.changeSelection}</MenuItem>
                        <MenuItem onClick={props.onDelete} danger>{NOTEBOOK_TEXT.menu.delete}</MenuItem>
                    </div>
                </div>
            </div>
        </header>
    );
}

function MenuItem(props: { onClick(): void, danger?: boolean, children: React.ReactNode }) {
    return (
        <button type="button" role="menuitem" onClick={props.onClick} className={`w-full text-left px-3 py-2 text-sm hover:bg-primary-50 ${props.danger ? "text-error-700" : "text-primary-900"}`}>
            {props.children}
        </button>
    );
}
```

`components/Notebooks/SessionStateView.tsx`:

```tsx
import { MaterialSymbol } from "react-material-symbols";
import { NOTEBOOK_TEXT, messageForNotebookError } from "../../contants/NotebookConstants";
import { formatShortDate } from "../../lib/embargoDisplay";
import { SessionPhase } from "../../lib/notebookSession";
import { Notebook, SessionStatus } from "../../types/GatekeeperAPI";

interface Props {
    phase: SessionPhase
    session: SessionStatus | null | undefined
    notebook: Notebook
    refusal?: any
    onResume?(): void
    onStartNew?(): void
    onReadOnly?(): void
    onTryAgain?(): void
}

function Frame(props: { icon: string, title: string, children?: React.ReactNode, actions?: React.ReactNode }) {
    return (
        <div className="flex flex-col items-center justify-center gap-3 h-full min-h-[420px] text-center px-6">
            <MaterialSymbol icon={props.icon as any} size={36} grade={-25} weight={300} className="text-primary-400" />
            <h5 className="m-0">{props.title}</h5>
            <div className="max-w-md text-sm text-primary-600 flex flex-col gap-1">{props.children}</div>
            {props.actions && <div className="mt-2 flex items-center gap-2">{props.actions}</div>}
        </div>
    );
}

const primary = "btn-primary m-0";
const secondary = "btn-primary-outline m-0";

export function SessionStateView(props: Props) {
    const s = props.session;
    if (props.notebook.dataset?.source_deleted) {
        return <Frame icon="link_off" title={NOTEBOOK_TEXT.session.sourceDeletedTitle}><p className="m-0">{NOTEBOOK_TEXT.session.sourceDeletedBody}</p></Frame>;
    }
    if (props.refusal) {
        const detail = props.refusal.detail;
        const title = detail === "no_seats" ? NOTEBOOK_TEXT.session.noSeatsTitle(props.refusal.seats_total ?? 0)
            : detail === "storage_full" ? NOTEBOOK_TEXT.session.storageFullTitle
            : NOTEBOOK_TEXT.session.failedTitle;
        const body = detail === "no_seats" ? NOTEBOOK_TEXT.session.noSeatsBody
            : detail === "storage_full" ? NOTEBOOK_TEXT.session.storageFullBody
            : messageForNotebookError(props.refusal);
        return (
            <Frame icon={detail === "no_seats" ? "event_seat" : "error"} title={title} actions={props.onTryAgain && <button type="button" className={primary} onClick={props.onTryAgain}>{NOTEBOOK_TEXT.session.tryAgain}</button>}>
                <p className="m-0">{body}</p>
            </Frame>
        );
    }
    switch (props.phase) {
        case "starting":
            return (
                <Frame icon="progress_activity" title={NOTEBOOK_TEXT.session.startingTitle}>
                    <p className="m-0">{NOTEBOOK_TEXT.session.startingHint}</p>
                    <ul className="list-none m-0 p-0 mt-2 font-mono text-xs text-primary-500">{(s?.progress ?? []).map((line, i) => <li key={i}>{line}</li>)}</ul>
                </Frame>
            );
        case "stopped":
            return (
                <Frame icon="pause" title={NOTEBOOK_TEXT.session.stoppedTitle} actions={<>
                    {props.onResume && <button type="button" className={primary} onClick={props.onResume}>{NOTEBOOK_TEXT.session.resume}</button>}
                    {props.onReadOnly && <button type="button" className={secondary} onClick={props.onReadOnly}>{NOTEBOOK_TEXT.session.readOnly}</button>}
                </>}>
                    {s?.stop_reason === "admin" && <p className="m-0">{NOTEBOOK_TEXT.session.stoppedByAdmin}</p>}
                    {s?.stopped_at && s.stop_reason !== "admin" && <p className="m-0">{NOTEBOOK_TEXT.session.idleSince} {formatShortDate(s.stopped_at)}.</p>}
                    <p className="m-0">{NOTEBOOK_TEXT.session.stoppedBody}</p>
                </Frame>
            );
        case "ended":
            return (
                <Frame icon="timer_off" title={NOTEBOOK_TEXT.session.endedTitle} actions={props.onStartNew && <button type="button" className={primary} onClick={props.onStartNew}>{NOTEBOOK_TEXT.session.startNew}</button>}>
                    <p className="m-0">{NOTEBOOK_TEXT.session.endedBody}</p>
                </Frame>
            );
        case "failed":
            return (
                <Frame icon="error" title={NOTEBOOK_TEXT.session.failedTitle} actions={props.onTryAgain && <button type="button" className={primary} onClick={props.onTryAgain}>{NOTEBOOK_TEXT.session.tryAgain}</button>}>
                    <p className="m-0">{NOTEBOOK_TEXT.session.failedBody}</p>
                </Frame>
            );
        default:
            return (
                <Frame icon="play_circle" title={NOTEBOOK_TEXT.session.none} actions={props.onStartNew && <button type="button" className={primary} onClick={props.onStartNew}>{NOTEBOOK_TEXT.session.startNew}</button>} />
            );
    }
}
```

`components/Notebooks/LabFrame.tsx`:

```tsx
export function LabFrame(props: { labPath: string, title: string }) {
    return (
        <iframe
            src={props.labPath}
            title={props.title}
            className="w-full h-full min-h-[600px] border-0 bg-primary-0"
            allow="clipboard-read; clipboard-write"
        />
    );
}
```

`components/Notebooks/NotebookSidePanel.tsx`:

```tsx
import Link from "next/link";
import { useState } from "react";
import { ROUTE_PAGE_DATASETS_DETAILS } from "../../contants/InternalRoutesConstants";
import { NOTEBOOK_TEXT, SNIPPETS } from "../../contants/NotebookConstants";
import { bytesToSize } from "../../lib/file";
import { Notebook, SessionStatus } from "../../types/GatekeeperAPI";

function Label(props: { children: React.ReactNode }) {
    return <div className="text-[11px] tracking-[0.08em] uppercase font-semibold text-primary-500">{props.children}</div>;
}

interface Props {
    notebook: Notebook
    session: SessionStatus | null | undefined
    versionFileCount: number
    onChangeSelection(): void
}

export function NotebookSidePanel(props: Props) {
    const [copied, setCopied] = useState<number | null>(null);
    const dataset = props.notebook.dataset;
    const mounted = props.session?.mounted_files ?? props.notebook.mounted_files;
    const bytes = props.session?.mounted_bytes ?? props.notebook.mounted_bytes;

    async function copy(index: number, code: string) {
        try {
            await navigator.clipboard.writeText(code);
            setCopied(index);
            setTimeout(() => setCopied(null), 2000);
        } catch {
            // No clipboard permission: the code is still visible to select by hand.
        }
    }

    return (
        <aside className="w-80 flex-none border-l border-primary-200 bg-primary-50 overflow-y-auto p-4 flex flex-col gap-5">
            <section className="flex flex-col gap-2">
                <Label>{NOTEBOOK_TEXT.panel.dataset}</Label>
                {dataset && !dataset.source_deleted
                    ? <>
                        <span className="text-sm font-semibold text-primary-900">{dataset.title}</span>
                        <span className="font-mono text-xs text-primary-500">v{dataset.version_name} · {NOTEBOOK_TEXT.panel.pinned}</span>
                        <Link href={ROUTE_PAGE_DATASETS_DETAILS({ id: dataset.id })} className="text-[13px] font-semibold underline underline-offset-2">{NOTEBOOK_TEXT.panel.openDataset}</Link>
                    </>
                    : <span className="text-sm text-primary-500">{NOTEBOOK_TEXT.page.sourceDeleted}</span>}
            </section>
            <section className="flex flex-col gap-2">
                <Label>{NOTEBOOK_TEXT.panel.files}</Label>
                <span className="text-sm text-primary-900">{NOTEBOOK_TEXT.panel.mounted(mounted, props.versionFileCount)}</span>
                <span className="font-mono text-xs text-primary-500">{bytesToSize(bytes)}{dataset?.id ? ` · /data/${dataset.id}/${dataset.version_name}/` : ""}</span>
                <button type="button" className="self-start text-[13px] font-semibold underline underline-offset-2" onClick={props.onChangeSelection}>{NOTEBOOK_TEXT.panel.changeSelection}</button>
            </section>
            <section className="flex flex-col gap-2">
                <Label>{NOTEBOOK_TEXT.panel.snippets}</Label>
                {SNIPPETS[props.notebook.kernel].map((snippet, index) => (
                    <div key={snippet.title} className="rounded-md border border-primary-200 bg-primary-0 p-2.5 flex flex-col gap-1.5">
                        <div className="flex items-center justify-between gap-2">
                            <span className="text-[13px] text-primary-900">{snippet.title}</span>
                            <button type="button" className="text-[12px] font-semibold text-primary-700 hover:text-primary-900" onClick={() => copy(index, snippet.code)}>{NOTEBOOK_TEXT.panel.copy}</button>
                        </div>
                        <code className="font-mono text-xs text-primary-700 break-all">{snippet.code}</code>
                        {copied === index && <span className="text-[11px] text-primary-500">{NOTEBOOK_TEXT.panel.copied}</span>}
                    </div>
                ))}
            </section>
            <section className="flex flex-col gap-2">
                <Label>{NOTEBOOK_TEXT.panel.outputs}</Label>
                <p className="m-0 text-[13px] text-primary-600">{NOTEBOOK_TEXT.panel.outputsHint}</p>
            </section>
        </aside>
    );
}
```

`components/Notebooks/MarkdownCell.tsx`:

```tsx
import ReactMarkdown from "react-markdown";

export function MarkdownCell(props: { source: string }) {
    return <div className="prose prose-sm max-w-none"><ReactMarkdown>{props.source}</ReactMarkdown></div>;
}
```

`components/Notebooks/NotebookReadOnly.tsx`:

```tsx
import { NOTEBOOK_TEXT } from "../../contants/NotebookConstants";
import { MarkdownCell } from "./MarkdownCell";

function text(source: string | string[] | undefined): string {
    return Array.isArray(source) ? source.join("") : (source ?? "");
}

function Output(props: { output: any }) {
    const o = props.output;
    if (o.output_type === "stream") return <pre className="m-0 whitespace-pre-wrap font-mono text-xs text-primary-700">{text(o.text)}</pre>;
    if (o.output_type === "error") return <pre className="m-0 whitespace-pre-wrap font-mono text-xs text-error-700">{o.ename}: {o.evalue}</pre>;
    const plain = o.data?.["text/plain"];
    if (plain) return <pre className="m-0 whitespace-pre-wrap font-mono text-xs text-primary-700">{text(plain)}</pre>;
    const png = o.data?.["image/png"];
    if (png) return <img alt="" src={`data:image/png;base64,${png}`} className="max-w-full" />;
    return null;
}

export function NotebookReadOnly(props: { content: any }) {
    const cells: any[] = props.content?.cells ?? [];
    return (
        <div className="h-full overflow-y-auto bg-primary-0">
            <div className="sticky top-0 px-4 py-2 border-b border-primary-200 bg-primary-50 text-[13px] text-primary-700">{NOTEBOOK_TEXT.readOnly.banner}</div>
            <div className="max-w-4xl mx-auto p-6 flex flex-col gap-4">
                {cells.map((cell, index) => (
                    <div key={index} className="rounded-md border border-primary-200 overflow-hidden">
                        {cell.cell_type === "markdown"
                            ? <div className="p-3"><MarkdownCell source={text(cell.source)} /></div>
                            : <>
                                <pre className="m-0 p-3 bg-primary-50 whitespace-pre-wrap font-mono text-[13px] text-primary-900">{text(cell.source)}</pre>
                                {(cell.outputs ?? []).length > 0 && <div className="p-3 border-t border-primary-100 flex flex-col gap-2">{cell.outputs.map((o: any, i: number) => <Output key={i} output={o} />)}</div>}
                            </>}
                    </div>
                ))}
            </div>
        </div>
    );
}
```

- [ ] **Step 4: The page**

`pages/app/notebooks/[notebookId].tsx`:

```tsx
import Head from "next/head";
import Router, { useRouter } from "next/router";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { useSession } from "next-auth/react";
import Modal from "../../../components/base/PopupModal";
import { FileSelectionDialog } from "../../../components/Notebooks/FileSelectionDialog";
import { LabFrame } from "../../../components/Notebooks/LabFrame";
import { NotebookReadOnly } from "../../../components/Notebooks/NotebookReadOnly";
import { NotebookSidePanel } from "../../../components/Notebooks/NotebookSidePanel";
import { NotebookTopBar } from "../../../components/Notebooks/NotebookTopBar";
import { useResourceUsage } from "../../../components/Notebooks/ResourceUsage";
import { SessionStateView } from "../../../components/Notebooks/SessionStateView";
import { ROUTE_PAGE_NOTEBOOKS } from "../../../contants/InternalRoutesConstants";
import { NOTEBOOK_TEXT, messageForNotebookError } from "../../../contants/NotebookConstants";
import { BFFAPI } from "../../../gateways/BFFAPI";
import { useNotebookSession } from "../../../hooks/UseNotebookSession";
import { SWRRetry, fetcher } from "../../../lib/fetcher";
import { submitHubLogin } from "../../../lib/hubLogin";
import { formatRemaining, isLimitApproaching, sessionPhase, timeLeftMs } from "../../../lib/notebookSession";
import { trackUiEvent } from "../../../lib/telemetryClient";
import { GetDatasetDetailsResponse } from "../../../types/BffAPI";
import { Notebook, NotebookCapacity } from "../../../types/GatekeeperAPI";

const DATA_MAX_BYTES_FALLBACK = 20 * 1024 ** 3;

export default function NotebookPage() {
    const router = useRouter();
    const notebookId = router.query.notebookId as string | undefined;
    const { data: sessionData } = useSession();
    const [bffGateway] = useState(() => new BFFAPI());
    const { data: notebook, mutate: refreshNotebook } = useSWR<Notebook>(notebookId ? `/api/notebooks/${notebookId}` : null, fetcher, { onErrorRetry: SWRRetry });
    const { session, mutate: refreshSession } = useNotebookSession(notebookId);
    const { data: dataset } = useSWR<GetDatasetDetailsResponse>(notebook?.dataset?.id && !notebook.dataset.source_deleted ? `/api/datasets/${notebook.dataset.id}` : null, fetcher, { onErrorRetry: SWRRetry });
    const { data: capacity } = useSWR<NotebookCapacity>("/api/notebooks/capacity", fetcher);
    const [labPath, setLabPath] = useState<string | null>(null);
    const [refusal, setRefusal] = useState<any>(null);
    const [readOnly, setReadOnly] = useState(false);
    const [content, setContent] = useState<any>(null);
    const [showPicker, setShowPicker] = useState(false);
    const [confirmStop, setConfirmStop] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState(false);
    const [now, setNow] = useState(() => new Date());
    const phase = sessionPhase(session);
    const usage = useResourceUsage(sessionData?.user?.uid as string | undefined, phase === "running");

    useEffect(() => { const t = setInterval(() => setNow(new Date()), 30_000); return () => clearInterval(t); }, []);

    const autoStarted = useState({ done: false })[0];
    useEffect(() => {
        if (!notebook || !session || autoStarted.done) return;
        autoStarted.done = true;
        if (phase === "none" && !notebook.dataset?.source_deleted) start();
        if (phase === "running" || phase === "starting") start();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [notebook, session]);

    async function start() {
        if (!notebookId) return;
        setRefusal(null);
        setReadOnly(false);
        try {
            const started = await bffGateway.startNotebookSession(notebookId, navigator.language?.startsWith("pt") ? "pt-BR" : "en");
            await submitHubLogin(document, started.token, started.lab_path, started.login_url);
            setLabPath(started.lab_path);
            trackUiEvent("notebook_opened");
            refreshSession();
        } catch (e: any) {
            setRefusal(e?.body ?? e?.response?.data ?? e);
        }
    }

    async function stop() {
        if (!notebookId) return;
        setConfirmStop(false);
        try {
            await bffGateway.stopNotebookSession(notebookId);
            setLabPath(null);
            refreshSession();
        } catch (e) {
            setRefusal(e);
        }
    }

    async function openReadOnly() {
        if (!notebookId) return;
        const response = await fetch(`/api/notebooks/${notebookId}/content`);
        if (response.ok) { setContent(await response.json()); setReadOnly(true); }
        else setRefusal({ detail: "content_not_written" });
    }

    async function rename(name: string) {
        if (!notebookId) return;
        try { await bffGateway.updateNotebook(notebookId, { name }); refreshNotebook(); } catch (e) { alert(messageForNotebookError(e)); }
    }

    async function changeSelection(ids: string[]) {
        if (!notebookId) return;
        setShowPicker(false);
        try {
            if (phase === "running" || phase === "starting") await bffGateway.stopNotebookSession(notebookId);
            await bffGateway.updateNotebook(notebookId, { file_ids: ids });
            await refreshNotebook();
            setLabPath(null);
            await start();
        } catch (e) { setRefusal(e); }
    }

    async function remove() {
        if (!notebookId) return;
        await bffGateway.deleteNotebook(notebookId);
        Router.push(ROUTE_PAGE_NOTEBOOKS);
    }

    if (!notebook) return <div className="p-8 text-sm text-primary-500">loading...</div>;

    const showLab = phase === "running" && labPath && !refusal && !readOnly;
    const approaching = isLimitApproaching(session, now);
    const left = timeLeftMs(session, now);
    const versionFiles = dataset?.versions?.find(v => v.name === notebook.dataset?.version_name)?.files_in ?? [];

    return (
        <>
            <Head><title>{notebook.name} · DataMap</title></Head>
            <main className="flex flex-col h-screen">
                <NotebookTopBar notebook={notebook} session={session} usage={usage} now={now}
                    onRename={rename} onStop={() => setConfirmStop(true)}
                    onDownload={() => window.open(`/api/notebooks/${notebookId}/content?download=1`, "_blank")}
                    onChangeSelection={() => setShowPicker(true)} onDelete={() => setConfirmDelete(true)} />
                {approaching && left !== null && session && (
                    <div className="px-4 py-2 bg-embargo-50 border-b border-embargo-200 text-[13px] text-embargo-800">
                        {NOTEBOOK_TEXT.session.limitBanner(Math.ceil(left / 60000), session.max_hours)}
                    </div>
                )}
                <div className="flex flex-1 min-h-0">
                    <div className="flex-1 min-w-0">
                        {showLab
                            ? <LabFrame labPath={labPath!} title={notebook.name} />
                            : readOnly && content
                                ? <NotebookReadOnly content={content} />
                                : <SessionStateView phase={phase} session={session} notebook={notebook} refusal={refusal}
                                    onResume={start} onStartNew={start} onReadOnly={openReadOnly} onTryAgain={start} />}
                    </div>
                    <NotebookSidePanel notebook={notebook} session={session} versionFileCount={versionFiles.length || notebook.mounted_files} onChangeSelection={() => setShowPicker(true)} />
                </div>
            </main>
            <FileSelectionDialog show={showPicker} onClose={() => setShowPicker(false)} files={versionFiles} maxBytes={DATA_MAX_BYTES_FALLBACK} initial={notebook.file_ids} onConfirm={changeSelection} restartNote />
            <Modal title={NOTEBOOK_TEXT.session.stopConfirmTitle} show={confirmStop} confimButtonText={NOTEBOOK_TEXT.session.stop} cancelButtonText="Cancel" cancel={() => setConfirmStop(false)} confim={stop}>
                <p className="m-0">{NOTEBOOK_TEXT.session.stopConfirmBody}</p>
            </Modal>
            <Modal title={NOTEBOOK_TEXT.menu.deleteTitle} show={confirmDelete} confimButtonText={NOTEBOOK_TEXT.menu.delete} cancelButtonText="Cancel" cancel={() => setConfirmDelete(false)} confim={remove} destructive>
                <p className="m-0">{NOTEBOOK_TEXT.menu.deleteBody}</p>
            </Modal>
        </>
    );
}

NotebookPage.auth = {
    role: "admin",
    loading: <div>loading...</div>,
};
```

Two things to settle while wiring it: the ceiling comes from `capacity.data_max_bytes` (the capacity route carries it); `DATA_MAX_BYTES_FALLBACK` is only for the instant before that request answers, so pass `capacity?.data_max_bytes ?? DATA_MAX_BYTES_FALLBACK` to the picker. And `formatRemaining` is imported for the banner's minute count — keep whichever of the two the banner ends up using and drop the other import so `tsc` does not complain.

The page opens the session on first load when the notebook never ran (the "Open in notebook" path lands here), and re-logs into the hub when a session is already live (a reload). "Stopped" waits for the person: the design's Resume is explicit.

- [ ] **Step 5: Run and commit**

Run: `npx jest components/Notebooks hooks lib`
Expected: all passed

```bash
git add hooks/UseNotebookSession.ts components/Notebooks pages/app/notebooks/\[notebookId\].tsx
git commit -m "feat(notebooks): the editor - top bar, session chip, states, Lab frame, side panel, read-only view"
```

---

### Task 8: The dataset page

**Files:**
- Create: `components/Notebooks/OpenInNotebookButton.tsx`, `components/Notebooks/MyNotebooksCard.tsx`, `components/Notebooks/__tests__/OpenInNotebookButton.test.tsx`, `__tests__/MyNotebooksCard.test.tsx`
- Modify: `components/DatasetDetailsPage.tsx`, `components/DatasetDetails/DataCard/TabPanelDataCard.tsx`, `components/DatasetDetails/DataCard/DatasetFilesList.tsx`

**Interfaces:**
- `OpenInNotebookButton({ dataset, version })`: enabled when `openability(...)` is ok; opens `NewNotebookDialog` prefilled; when the version's total size is over the ceiling it opens `FileSelectionDialog` first and passes the chosen ids. Locked with the reason otherwise.
- `MyNotebooksCard({ dataset, version })`: lists `GET /api/notebooks?dataset_id=` with `SessionPill`, links to the editor, and a "New notebook on vN" button opening the same dialog.
- Per-file: a `code` icon on hover in `FileListRowItem` opening `NewNotebookDialog` with `fileIds=[file.id]`.

- [ ] **Step 1: Failing tests**

`components/Notebooks/__tests__/OpenInNotebookButton.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react';

jest.mock("../NewNotebookDialog", () => ({ NewNotebookDialog: (p: any) => p.show ? <div data-testid="new-dialog">{JSON.stringify(p.fileIds ?? null)}</div> : null }));
jest.mock("../FileSelectionDialog", () => ({ FileSelectionDialog: (p: any) => p.show ? <button onClick={() => p.onConfirm(["f1"])}>pick</button> : null }));

import { OpenInNotebookButton } from "../OpenInNotebookButton";

const small: any = { name: "2", design_state: "PUBLISHED", files_in: [{ id: "f1", name: "a.nc", size_bytes: 10 }] };
const dataset: any = { id: "d1", name: "T", embargo: null, access: { level: "owner" } };

describe("OpenInNotebookButton", () => {
    test("opens the dialog prefilled for a small published version", () => {
        render(<OpenInNotebookButton dataset={dataset} version={small} maxBytes={100} />);

        fireEvent.click(screen.getByRole("button", { name: /Open in notebook/ }));

        expect(screen.getByTestId("new-dialog").textContent).toBe("null");
    });

    test("a version over the ceiling goes through the picker first", () => {
        const big = { ...small, files_in: [{ id: "f1", name: "a.nc", size_bytes: 500 }, { id: "f2", name: "b.nc", size_bytes: 500 }] };
        render(<OpenInNotebookButton dataset={dataset} version={big} maxBytes={600} />);

        fireEvent.click(screen.getByRole("button", { name: /Open in notebook/ }));
        fireEvent.click(screen.getByText("pick"));

        expect(screen.getByTestId("new-dialog").textContent).toBe('["f1"]');
    });

    test("is locked under embargo and on a draft", () => {
        const { rerender } = render(<OpenInNotebookButton dataset={{ ...dataset, embargo: { active: true, until: "2026-12-15T23:59:59+00:00" } }} version={{ ...small, files_withheld: true }} maxBytes={100} />);
        expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(true);
        expect(screen.getByRole("button").getAttribute("title")).toContain("embargo");

        rerender(<OpenInNotebookButton dataset={dataset} version={{ ...small, design_state: "DRAFT" }} maxBytes={100} />);
        expect(screen.getByRole("button").getAttribute("title")).toContain("Publish");
    });
});
```

`components/Notebooks/__tests__/MyNotebooksCard.test.tsx`:

```tsx
/** @jest-environment jsdom */
import { describe, expect, jest, test } from '@jest/globals';
import { render, screen } from '@testing-library/react';

let list: any;
jest.mock("swr", () => ({ __esModule: true, default: () => ({ data: list }) }));
jest.mock("../../../lib/fetcher", () => ({ fetcher: jest.fn(), SWRRetry: jest.fn() }));
jest.mock("../NewNotebookDialog", () => ({ NewNotebookDialog: () => null }));

import { MyNotebooksCard } from "../MyNotebooksCard";

describe("MyNotebooksCard", () => {
    test("lists my notebooks on this dataset with their state and version", () => {
        list = { content: [{ id: "n1", name: "smps", dataset: { version_name: "2" }, session: { state: "running" }, updated_at: "2026-10-03T17:42:00Z" }] };
        render(<MyNotebooksCard dataset={{ id: "d1", name: "T" } as any} version={{ name: "2", design_state: "PUBLISHED", files_in: [{ id: "f" }] } as any} />);

        expect(screen.getByText("My notebooks")).toBeTruthy();
        expect(screen.getByRole("link", { name: /smps/ }).getAttribute("href")).toBe("/app/notebooks/n1");
        expect(screen.getByText("Running")).toBeTruthy();
        expect(screen.getByRole("button", { name: "New notebook on v2" })).toBeTruthy();
    });

    test("says when there are none", () => {
        list = { content: [] };
        render(<MyNotebooksCard dataset={{ id: "d1", name: "T" } as any} version={{ name: "2", design_state: "PUBLISHED", files_in: [{ id: "f" }] } as any} />);

        expect(screen.getByText(/No notebooks on this dataset yet/)).toBeTruthy();
    });
});
```

- [ ] **Step 2: Components**

`components/Notebooks/OpenInNotebookButton.tsx`:

```tsx
import { useState } from "react";
import { MaterialSymbol } from "react-material-symbols";
import { NOTEBOOK_TEXT } from "../../contants/NotebookConstants";
import { formatShortDate } from "../../lib/embargoDisplay";
import { openability, selectionFits, selectionTotal } from "../../lib/notebookSession";
import { GetDatasetDetailsResponse, GetDatasetDetailsVersionResponse } from "../../types/BffAPI";
import { FileSelectionDialog } from "./FileSelectionDialog";
import { NewNotebookDialog } from "./NewNotebookDialog";

interface Props {
    dataset: GetDatasetDetailsResponse
    version: GetDatasetDetailsVersionResponse | undefined
    maxBytes: number
    fileIds?: string[]
    compact?: boolean
}

export function OpenInNotebookButton(props: Props) {
    const [picking, setPicking] = useState(false);
    const [chosen, setChosen] = useState<string[] | undefined>(props.fileIds);
    const [showNew, setShowNew] = useState(false);
    const can = openability(props.dataset, props.version);
    const tooBig = props.version && !props.fileIds && !selectionFits(selectionTotal(props.version.files_in ?? [], null), props.maxBytes);
    const title = can.ok ? NOTEBOOK_TEXT.datasetPage.open
        : can.reason === "embargo" ? (props.dataset.embargo?.until ? NOTEBOOK_TEXT.datasetPage.lockedEmbargoBody(formatShortDate(props.dataset.embargo.until)) : NOTEBOOK_TEXT.datasetPage.lockedEmbargo)
        : NOTEBOOK_TEXT.datasetPage.lockedDraft;

    function click() {
        if (!can.ok) return;
        if (tooBig) setPicking(true); else setShowNew(true);
    }

    const base = props.compact
        ? "flex items-center text-primary-400 hover:text-primary-900 transition-colors disabled:text-primary-300"
        : "inline-flex items-center gap-2 h-[38px] px-3.5 rounded-md border text-sm font-semibold whitespace-nowrap transition-colors " + (can.ok ? "border-primary-300 bg-primary-0 text-primary-900 hover:bg-primary-100" : "border-primary-200 bg-primary-100 text-primary-400 cursor-not-allowed");

    return (
        <>
            <button type="button" className={base} disabled={!can.ok} title={title} aria-label={props.compact ? NOTEBOOK_TEXT.datasetPage.openFile : NOTEBOOK_TEXT.datasetPage.open} onClick={click}>
                <MaterialSymbol icon={can.ok ? "code" : "lock"} size={18} grade={-25} weight={400} aria-hidden="true" />
                {!props.compact && NOTEBOOK_TEXT.datasetPage.open}
            </button>
            {props.version && (
                <FileSelectionDialog show={picking} onClose={() => setPicking(false)} files={props.version.files_in ?? []} maxBytes={props.maxBytes} initial={[]}
                    onConfirm={(ids) => { setChosen(ids); setPicking(false); setShowNew(true); }} />
            )}
            {props.version && (
                <NewNotebookDialog show={showNew} onClose={() => setShowNew(false)} dataset={props.dataset} version={props.version} fileIds={chosen} />
            )}
        </>
    );
}
```

`components/Notebooks/MyNotebooksCard.tsx`:

```tsx
import Link from "next/link";
import { useState } from "react";
import Moment from "react-moment";
import useSWR from "swr";
import { ROUTE_PAGE_NOTEBOOK_DETAILS } from "../../contants/InternalRoutesConstants";
import { NOTEBOOK_TEXT } from "../../contants/NotebookConstants";
import { SWRRetry, fetcher } from "../../lib/fetcher";
import { openability } from "../../lib/notebookSession";
import { GetDatasetDetailsResponse, GetDatasetDetailsVersionResponse } from "../../types/BffAPI";
import { NotebookList } from "../../types/GatekeeperAPI";
import { NewNotebookDialog } from "./NewNotebookDialog";
import { SessionPill } from "./SessionPill";

export function MyNotebooksCard(props: { dataset: GetDatasetDetailsResponse, version: GetDatasetDetailsVersionResponse | undefined }) {
    const { data } = useSWR<NotebookList>(`/api/notebooks?dataset_id=${encodeURIComponent(props.dataset.id)}`, fetcher, { onErrorRetry: SWRRetry });
    const [showNew, setShowNew] = useState(false);
    if (!data) return null;
    const can = props.version ? openability(props.dataset, props.version).ok : false;
    return (
        <div className="border border-primary-200 rounded-lg bg-primary-0 p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between">
                <span className="text-[11px] tracking-[0.08em] uppercase font-semibold text-primary-500">{NOTEBOOK_TEXT.datasetPage.myNotebooks}</span>
                <span className="text-xs text-primary-500">{data.content.length}</span>
            </div>
            {data.content.length === 0
                ? <p className="m-0 text-[13px] text-primary-600">{NOTEBOOK_TEXT.datasetPage.none}</p>
                : <ul className="list-none m-0 p-0 flex flex-col gap-2">
                    {data.content.map(n => (
                        <li key={n.id} className="flex items-center justify-between gap-2">
                            <span className="min-w-0 flex flex-col">
                                <Link href={ROUTE_PAGE_NOTEBOOK_DETAILS({ id: n.id })} className="font-mono text-[13px] text-primary-900 truncate hover:underline">{n.name}</Link>
                                <span className="text-xs text-primary-500">v{n.dataset?.version_name} · <Moment date={n.updated_at} fromNow /></span>
                            </span>
                            <SessionPill session={n.session} />
                        </li>
                    ))}
                </ul>}
            {props.version && can && (
                <button type="button" className="mt-1 block text-center rounded-md border border-primary-300 bg-primary-50 px-3 py-2 text-[13px] font-semibold text-primary-900 hover:bg-primary-100" onClick={() => setShowNew(true)}>
                    {NOTEBOOK_TEXT.datasetPage.newOn(props.version.name)}
                </button>
            )}
            {props.version && <NewNotebookDialog show={showNew} onClose={() => setShowNew(false)} dataset={props.dataset} version={props.version} />}
        </div>
    );
}
```

- [ ] **Step 3: Wire the page**

In `components/DatasetDetailsPage.tsx`, import `OpenInNotebookButton` and, in the actions row, between the share button and the download button:

```tsx
              <OpenInNotebookButton dataset={props.dataset} version={selectedVersion} maxBytes={DATA_MAX_BYTES_FALLBACK} />
```

In `components/DatasetDetails/DataCard/TabPanelDataCard.tsx`, replace the "Open in notebook / Go to notebooks" card (the `<div>` with `SideCardLabel`, the sentence and the `Link` to `ROUTE_PAGE_NOTEBOOKS`) with:

```tsx
          <MyNotebooksCard dataset={props.dataset} version={selectedVersion} />
```

and drop the now unused `ROUTE_PAGE_NOTEBOOKS` import.

In `components/DatasetDetails/DataCard/DatasetFilesList.tsx`, in `FileListRowItem`'s last `<span>`, before `DownloadFileButton`:

```tsx
                {!props.onFileRemoved && (
                    <span className="opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity mr-1">
                        <OpenInNotebookButton dataset={props.dataset} version={props.datasetVersion} maxBytes={20 * 1024 ** 3} fileIds={[props.file.id]} compact />
                    </span>
                )}
```

and add `group` to the `<li>` class list in `DatasetFilesList` so the hover works (`className={`group ${gridColumns} ...`}`). `DATA_MAX_BYTES_FALLBACK` lives in `contants/NotebookConstants.ts` (`20 * 1024 ** 3`); the dataset page has no capacity request of its own, so the fallback is what it uses — a selection over the real ceiling is still refused by the gatekeeper with `selection_too_large`, which the dialog shows.

- [ ] **Step 4: Run and commit**

Run: `npx jest components/Notebooks components/DatasetDetails components/Embargo`
Expected: all passed (the existing DatasetDetails and Embargo tests still pass with the new button in the row)

```bash
git add components/Notebooks components/DatasetDetailsPage.tsx components/DatasetDetails/DataCard/TabPanelDataCard.tsx components/DatasetDetails/DataCard/DatasetFilesList.tsx contants/NotebookConstants.ts
git commit -m "feat(notebooks): open a dataset or one file in a notebook from its page; my notebooks card"
```

---

### Task 9: The deletion warning tells the truth

**Files:**
- Modify: `components/DatasetDetails/DatasetMoreSettingsButton.tsx`

- [ ] **Step 1: Wording**

The delete confirmation says "any public or private Notebooks using this dataset will no longer be executable". Replace it with: "Deletion is irreversible. Notebooks opened on this dataset keep their code but can no longer mount its files. Are you sure you want to permanently delete this dataset?" — which is what the gatekeeper does (`ON DELETE SET NULL`, "source deleted" state). If there is a test on that text under `components/DatasetDetails/__tests__`, update it.

- [ ] **Step 2: Commit**

```bash
git add components/DatasetDetails/DatasetMoreSettingsButton.tsx
git commit -m "fix(notebooks): the delete warning describes what happens to notebooks"
```

---

### Task 10: Full verification

- [ ] **Step 1: Suite and build**

```bash
npx jest
npm run build
```

Expected: every test passes, including `contants/__tests__/TelemetryConstants.test.ts` (the new page is in `PAGES`); the build completes with no type error.

- [ ] **Step 2: Against the real stack**

With the gatekeeper (plan 01), the hub (plan 02) and nginx on `http://localhost`, and `NEXTAUTH_URL=http://localhost`:

1. Sign in as an administrator. The sidebar's *Notebooks* opens the list with `0 of 4 sessions running` and the storage counter.
2. On a published dataset, *Open in notebook* → the dialog prefilled → *Open notebook* → the editor shows *Starting your session* with the entrypoint's lines, then JupyterLab in the frame with the first cell written; the chip shows CPU and RAM within a minute.
3. The side panel's *Copy* on a snippet puts it on the clipboard.
4. *Stop* → confirm → *Session stopped* with *Resume* and *Read only*; *Read only* renders the cells; *Resume* starts a new session.
5. On a dataset larger than the ceiling (set `NOTEBOOK_DATA_MAX_BYTES` low on the gatekeeper to test), *Open in notebook* opens the picker first, and the editor's panel says `n of m files mounted`.
6. Sign in as a user without the `notebooks_user` role (gate 1): the list page shows *Notebooks are not enabled for your account yet*; the dataset page button is visible and a click answers with the same message in the dialog's error (the create call is 401).
7. With `NOTEBOOK_SEATS=1` and a session held by another account: *Open notebook* shows *All 1 seats are in use* with *Try again*.

- [ ] **Step 3: Pull request**

```bash
git push -u origin feat/notebooks
gh pr create --title "feat(notebooks): open a dataset in a notebook (RFC 007, increment A)" --body "$(cat <<'EOF'
## Summary
- notebooks list with seats and storage; new-notebook dialog; "not enabled yet" state for accounts outside the gate
- editor page: DataMap top bar with the session chip, JupyterLab in a frame after a form-post login, every session state the design draws plus "no seats", side panel with dataset, mounted files, snippets
- dataset page: Open in notebook (whole version, or chosen files when over the ceiling), per-file action, My notebooks card
- read-only rendering of a stopped notebook; download of the .ipynb

Spec: gatekeeper `docs/rfcs/007-notebooks.md`. Contracts: gatekeeper `docs/superpowers/plans/2026-10-04-notebooks-00-contracts.md`. Design: Notebooks — discovery, sections 1a–1d, 1g.

## Test plan
- [ ] `npx jest` green, `npm run build` clean
- [ ] the seven checks of Task 10 against the real stack

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Deploy order (contracts): after the gatekeeper (01), the hub and nginx (02) and the archivist (04).
