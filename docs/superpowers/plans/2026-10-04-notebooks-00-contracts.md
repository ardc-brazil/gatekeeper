# Notebooks: Cross-Service Contracts

Spec: `docs/rfcs/007-notebooks.md`, increment A ("a notebook that opens with the data in it"). This file fixes the interfaces the gatekeeper, the JupyterHub deployment (hub, image, entrypoint), the SDKs, the archivist and the webapp share, so each plan can be implemented against it. When a plan and this file disagree, this file wins; change it first, then the plans.

## Plans

| # | Plan | Repo | Depends on |
|---|---|---|---|
| 01 | `2026-10-04-notebooks-01-gatekeeper-sessions.md` | gatekeeper | — |
| 02 | `2026-10-04-notebooks-02-infrastructure-hub.md` | gatekeeper (`infrastructure/`) | this file; its smoke test needs 01 merged |
| 03 | `2026-10-04-notebooks-03-sdk.md` | datamap-sdk (new) | this file (manifest and bearer routes) |
| 04 | `2026-10-04-notebooks-04-archivist-purge.md` | archivist | this file (internal routes) |
| 05 | `2026-10-04-notebooks-05-webapp.md` | datamap-webapp | this file; merges after 01 and 02 |

01, 03 and 04 start together against this file. 02 starts together too but its CI smoke test only passes once 01's internal routes exist. 05 starts against this file with the gatekeeper mocked in its tests and merges last.

Migration: one revision, `b8c9d0e1f2a3`, `down_revision = "c3d4e5f6a7b8"` (the tenancy requests migration of RFC 009, current head of `main` on 2026-10-08). Never re-pointed.

Deploy order: gatekeeper (01) → hub, image and nginx (02) → archivist (04) → webapp (05). The SDK is published before 02 builds the image. Rollout gate 1 (admins only) is the Casbin `admin` policy that already covers `/notebooks`; gate 2 is the `notebooks_user` role granted to everyone.

## Conventions

- Gatekeeper routes are mounted under `/api/v1`. Paths below omit that prefix.
- **User routes** carry `X-Api-Key`, `X-Api-Secret`, `X-User-Id`, `X-Datamap-Tenancies` and use `Depends(authenticate), Depends(authorize)`, exactly as the dataset routes do.
- **Bearer routes** accept `Authorization: Bearer <session token>` *instead of* the four headers. On those routes `authenticate` verifies the token, `parse_user_header` yields the token's `sub`, `parse_tenancy_header` yields the token's `tenancies`, and `authorize` enforces Casbin with the subject `notebook_session` rather than the user id. Every other route answers 401 to a bearer token.
- **Internal routes** carry `X-Api-Key`, `X-Api-Secret` of a client (the hub's, the archivist's) and use `Depends(authenticate)` only, like `/internal/datasets`.
- **Admin routes** are out of increment A.
- Timestamps are ISO 8601 with timezone. UUIDs are strings. Version names are strings (`dataset_versions.name`), never integers.
- Errors keep the existing handlers: `NotFoundException` → `404 {"detail": ...}`; `ConflictException` → `409 {"detail": ...}`; `ForbiddenException` → `403 {"detail": "forbidden"}`. A new `RefusedException(status_code, code, **extra)` → `{"detail": code, ...extra}` carries 413, 429 and 503.
- A caller who may not see a dataset gets **404** on every notebook route that names it, reads and writes alike, the same as the dataset routes.

## Shared enums and constants

```python
# app/model/notebook.py (gatekeeper)
class Kernel(str, enum.Enum):
    PYTHON = "python3"
    R = "ir"

class SessionState(str, enum.Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    ENDED = "ended"
    FAILED = "failed"

LIVE_STATES = (SessionState.STARTING, SessionState.RUNNING)

class StopReason(str, enum.Enum):
    IDLE = "idle"
    USER = "user"
    ADMIN = "admin"
    MAX_AGE = "max_age"
    SPAWN_ERROR = "spawn_error"

SESSION_ROLE = "notebook_session"       # Casbin subject for bearer requests
TOKEN_AUDIENCE = "notebook_session"     # JWT aud
TOKEN_ISSUER = "gatekeeper"
TOKEN_GRACE = timedelta(minutes=10)     # exp = max_hours + this
MANIFEST_URL_TTL = timedelta(hours=1)   # pre-signed URLs in the manifest
PROGRESS_KEEP = 50                      # last N lines kept
PROGRESS_LINE_MAX = 200
OUTPUTS_MOUNT = "/outputs"
DATA_MOUNT = "/data"
WORK_MOUNT = "/home/jovyan/work"
```

```ts
// datamap-webapp types/GatekeeperAPI.ts
export type NotebookKernel = "python3" | "ir";
export type SessionState = "starting" | "running" | "stopped" | "ended" | "failed";
export type StopReason = "idle" | "user" | "admin" | "max_age" | "spawn_error";
```

Settings (gatekeeper `Config`):

| Setting | Default | Meaning |
|---|---|---|
| `AUTH_NOTEBOOK_SESSION_TOKEN_SECRET` | required | HS256 key for session tokens; the hub holds the same value |
| `NOTEBOOK_SEATS` | `4` | concurrent live sessions on the platform |
| `NOTEBOOK_SESSION_MAX_HOURS` | `12` | hard limit; token `exp` is this plus `TOKEN_GRACE` |
| `NOTEBOOK_DATA_MAX_BYTES` | `21474836480` | 20 GB, the mounted selection ceiling |
| `NOTEBOOK_STORAGE_QUOTA_BYTES` | `2147483648` | 2 GB per user, `notebooks/{user_id}/` |
| `NOTEBOOK_STORAGE_PATH` | `/storage/notebooks` | where the gatekeeper sees `notebooks/`, read only |
| `NOTEBOOK_OUTPUTS_RETENTION_HOURS` | `24` | outputs kept after the last session ends |
| `NOTEBOOK_HUB_URL` | `http://datamap_jupyterhub:8000/hub` | the hub, inside the docker network |
| `NOTEBOOK_HUB_API_TOKEN` | required | an admin API token the hub config registers |
| `NOTEBOOK_HUB_TIMEOUT_SECONDS` | `5` | connect and read timeout for hub calls |

Hub-side values the hub reads from its own environment (plan 02): `DATAMAP_API_URL` (`http://gatekeeper:9092/api/v1`), `DATAMAP_HUB_API_KEY` and `DATAMAP_HUB_API_SECRET` (a client the hub uses on internal routes), `AUTH_NOTEBOOK_SESSION_TOKEN_SECRET`, `NOTEBOOK_HUB_API_TOKEN`, `NOTEBOOK_SEATS`, `NOTEBOOK_SESSION_MAX_HOURS`, `NOTEBOOK_IDLE_MINUTES` (`60`), `NOTEBOOK_SESSION_CPUS` (`2`), `NOTEBOOK_SESSION_MEMORY` (`12g`), `NOTEBOOK_IMAGE`, `NOTEBOOK_STORAGE_HOST_PATH` (the host directory that holds `notebooks/` and `sessions/`).

## Storage layout

On the storage volume (`STORAGE_DOCKER_VOLUME` on the host), siblings of the MinIO bucket directory:

```
notebooks/{user_id}/                         ← container /home/jovyan/work   rw
notebooks/{user_id}/{notebook.path}          ← the .ipynb; path has no directory component in A
notebooks/{user_id}/.outputs/{notebook_id}/  ← container /outputs            rw
sessions/{session_id}/data/                  ← container /data               ro (root:root 0555)
```

The gatekeeper mounts the volume read only at `/storage` and reads `/storage/notebooks` (`NOTEBOOK_STORAGE_PATH`). It never writes to it. The hub bind-mounts `NOTEBOOK_STORAGE_HOST_PATH/notebooks/{user_id}` and `.../sessions/{session_id}/data` into the user container. The entrypoint creates what is missing, as root, before dropping privileges.

Mount path of a dataset inside the container: `/data/{dataset_id}/{version_name}/{file name}`. File names are the `data_files.name` values; a name with `/` keeps its directories.

## Session token

Minted by the gatekeeper on `POST /notebooks/{id}/sessions`, HS256 with `AUTH_NOTEBOOK_SESSION_TOKEN_SECRET`:

```json
{
  "iss": "gatekeeper",
  "aud": "notebook_session",
  "sub": "<user_id>",
  "tenancies": ["datamap/production/data-amazon"],
  "notebook_id": "<uuid>",
  "session_id": "<uuid>",
  "datasets": [{"id": "<dataset_id>", "version": "<version_name>"}],
  "kernel": "python3",
  "locale": "pt-BR",
  "iat": 1790950000,
  "exp": 1790993800
}
```

`exp = iat + NOTEBOOK_SESSION_MAX_HOURS * 3600 + 600`. A token is valid only while its `session_id` row is in a live state; the gatekeeper checks the row on every bearer request.

## Hub login and Lab URL

The webapp logs the browser into the hub with a form POST, so the token never sits in a URL or an access log:

```
POST /hub/login
Content-Type: application/x-www-form-urlencoded

token=<session token>&next=/user/<user_id>/lab/tree/<notebook.path>
```

The hub's authenticator reads `token` from the form, verifies it with the shared secret, uses `sub` as the hub username and stores the claims as `auth_state`. The response sets the hub cookie and redirects to `next`. The Lab iframe is `/user/{user_id}/lab/tree/{notebook.path}`. Both are same-origin with the webapp, behind nginx.

## Container environment

Set by the spawner from `auth_state`:

| Variable | Value |
|---|---|
| `DATAMAP_SESSION_TOKEN` | the session token |
| `DATAMAP_API_URL` | `http://gatekeeper:9092/api/v1` (docker network; nginx is not in the path) |
| `DATAMAP_NOTEBOOK_ID` | `notebook_id` claim |
| `DATAMAP_SESSION_ID` | `session_id` claim |
| `DATAMAP_DATASETS` | the `datasets` claim as JSON |
| `DATAMAP_KERNEL` | `python3` or `ir` |
| `DATAMAP_LOCALE` | `pt-BR` or `en` |
| `MEM_LIMIT` | bytes, for `jupyter-resource-usage` |
| `CPU_LIMIT` | cores, for `jupyter-resource-usage` |
| `JUPYTERHUB_*` | the hub's own |

Container name: `datamap-notebook-{user_id}`. Network: `gatekeeper_gatekeeper-network` (the hub joins it too).

## Manifest

`GET /notebooks/{id}/manifest`, bearer only, and only for the token's own `notebook_id` (any other id → 404):

```json
{
  "notebook_id": "<uuid>",
  "notebook_path": "smps_monthly_climatology.ipynb",
  "notebook_exists": false,
  "kernel": "python3",
  "outputs_path": "/outputs",
  "datasets": [
    {
      "dataset_id": "<uuid>",
      "dataset_title": "GoAmazon 2014/5 — Aerosol size distribution, T3 site",
      "version_name": "2",
      "mount_path": "/data/<dataset_id>/2",
      "file_count": 14,
      "total_bytes": 2469606195,
      "files": [
        {"id": "<uuid>", "name": "t3_smps_20140201_20140228.nc", "size_bytes": 176160768,
         "relative_path": "t3_smps_20140201_20140228.nc", "url": "http://minio:9000/datamap/...?X-Amz-..."}
      ]
    }
  ]
}
```

`files` holds the selection (every file of the version when `file_ids` is null). `url` is a pre-signed GET valid for `MANIFEST_URL_TTL`. `notebook_exists` is whether the `.ipynb` is already on disk; when false the entrypoint writes the generated first cell (plan 02) before Lab starts.

## Progress

The entrypoint reports what it is doing, one line per step, bearer only:

```
POST /notebooks/{id}/session/progress
{"line": "Mounting 14 files · 2.3 GB"}
```

`GET /notebooks/{id}/session` returns the accumulated `progress` list. Lines are cut at `PROGRESS_LINE_MAX` characters; the gatekeeper keeps the last `PROGRESS_KEEP`. The last line the entrypoint sends is the measurement, `"Mounted 14 files · 2.3 GB in 18 s"`.

## Internal routes (hub and archivist)

| Route | Body | Does |
|---|---|---|
| `POST /internal/notebook-sessions/{id}/started` | — | `starting → running`; 204; idempotent; 404 unknown id |
| `POST /internal/notebook-sessions/{id}/stopped` | `{"reason": StopReason}` optional | live → `stopped` (`ended` for `max_age`, `failed` for `spawn_error`); 204; idempotent |
| `GET /internal/notebook-sessions/purgeable` | — | `{"sessions": [{"id", "user_id"}], "outputs": [{"notebook_id", "user_id"}], "notebooks": [{"notebook_id", "user_id", "path"}]}` |
| `POST /internal/notebook-sessions/{id}/purged` | — | marks `sessions/{id}/data` deleted; 204 |
| `POST /internal/notebooks/{id}/outputs-purged` | — | marks `.outputs/{id}` deleted; 204 |
| `POST /internal/notebooks/{id}/purged` | — | marks the soft-deleted notebook's file removed; 204 |

**Stop reason.** The hub cannot tell why a server stopped: the culler, the user and an administrator all go through the same REST call. So `reason` in `stopped` is optional. The hub sends `spawn_error` when `start()` raised, and nothing otherwise. The gatekeeper derives a missing reason: `user` or `admin` when it recorded that it asked the hub to stop that session itself (`stop_requested` column), else `max_age` when `now - started_at >= NOTEBOOK_SESSION_MAX_HOURS`, else `idle`.

`purgeable.sessions` is every session not live and not yet purged. `purgeable.outputs` is every notebook whose last session stopped more than `NOTEBOOK_OUTPUTS_RETENTION_HOURS` ago, has no live session, and whose outputs were not purged since that stop. `purgeable.notebooks` is every soft-deleted notebook whose file was not removed yet. The archivist deletes the paths and reports each one.

## Hub REST API the gatekeeper uses

`DELETE {NOTEBOOK_HUB_URL}/api/users/{user_id}/server` with `Authorization: token {NOTEBOOK_HUB_API_TOKEN}`. 204 stopped, 202 stopping, 404 no server (treated as stopped). Anything else, or a timeout, → the gatekeeper answers `503 {"detail": "hub_unavailable"}` and leaves the row as it was.

## Gatekeeper user routes

| Route | Request | Response | Errors |
|---|---|---|---|
| `GET /notebooks/` | `?dataset_id=` optional | `{"content": [Notebook]}` | — |
| `POST /notebooks/` | `{"dataset_id", "version_name", "kernel", "name"?, "file_ids"?}` | 201 `Notebook` | 404 dataset not readable; 409 `version_not_published`; 409 `name_taken`; 413 `selection_too_large` `{max_bytes, selected_bytes}`; 400 `file_not_in_version` |
| `GET /notebooks/{id}` | — | `Notebook` | 404 |
| `PATCH /notebooks/{id}` | `{"name"?, "file_ids"?}` (`"file_ids": null` = all) | `Notebook` | 404; 409 `name_taken`; 409 `session_running` when `file_ids` changes under a live session; 413 |
| `DELETE /notebooks/{id}` | — | 204 | 404; 503 `hub_unavailable` if a live session cannot be stopped |
| `GET /notebooks/{id}/content` | `?download=1` | the `.ipynb` JSON; `Content-Disposition: attachment` with `download` | 404; 404 `content_not_written` when the file does not exist yet |
| `POST /notebooks/{id}/sessions` | `{"locale": "pt-BR"}` | 201 `{"session": Session, "token", "login_url": "/hub/login", "lab_path": "/user/<uid>/lab/tree/<path>"}` | 404; 409 `version_not_published`; 409 `session_elsewhere` `{notebook_id}`; 413 `storage_full` `{quota_bytes, used_bytes}`; 429 `no_seats` `{seats_total}` |
| `GET /notebooks/{id}/session` | — | `Session` or `{"state": null}` when the notebook never ran | 404 |
| `DELETE /notebooks/{id}/session` | — | 204 | 404; 503 `hub_unavailable` |
| `GET /notebooks/-/capacity` | — | `{"seats_taken", "seats_total", "storage_used_bytes", "storage_quota_bytes", "data_max_bytes"}` | — |

Payloads:

```json
Notebook = {
  "id", "name", "path", "kernel", "size_bytes", "created_at", "updated_at",
  "dataset": {"id", "title", "version_name", "source_deleted": false} | null,
  "file_ids": [..] | null,
  "mounted_files": 14, "mounted_bytes": 2469606195,
  "session": Session | null
}
Session = {
  "id", "state", "stop_reason", "requested_at", "started_at", "stopped_at",
  "mounted_files", "mounted_bytes", "progress": ["..."], "max_hours": 12
}
```

`POST /notebooks/{id}/sessions` on a `stopped`, `ended` or `failed` notebook is "Resume": a new session row, the same notebook file, a fresh `/data`, and `/outputs` as it was if still within retention. `POST` on a notebook with a live session returns 200 with that session and a fresh token, so a reload of the page recovers.

`DELETE /notebooks/{id}` is a soft delete: `deleted_at` is set, the notebook leaves every listing, and plan 04 removes the file.

`name` is the file name without `.ipynb`: `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`. `path` is `name + ".ipynb"`. When `name` is omitted on create the gatekeeper derives one from the dataset title (lower case, non-alphanumerics to `_`, cut at 40) and appends `_2`, `_3`, … until it is free.

## Metrics (gatekeeper, RFC 005 contract)

| Metric | Type | Labels |
|---|---|---|
| `datamap_notebook_sessions_active` | gauge | `kernel` |
| `datamap_notebook_session_requests_total` | counter | `outcome` = started, resumed, no_seats, storage_full, forbidden, not_published, elsewhere |
| `datamap_notebook_session_duration_seconds` | histogram | `stop_reason` |

Copy duration and bytes are measured by the entrypoint and reported as the last progress line; a gatekeeper histogram for them is deferred until something reads it.

## Casbin

Policy rows inserted by the migration (production), by `tests/integration/fixtures/seed_clients.sql` (tests) and listed in `app/resources/casbin_seed_policies.sql`, each guarded by `WHERE NOT EXISTS` on `(ptype, v0, v1, v2)`:

```
p, notebook_session, /api/v1/datasets/[0-9a-f-]{36}$, GET, allow
p, notebook_session, /api/v1/datasets/[0-9a-f-]{36}/versions/[^/]+$, GET, allow
p, notebook_session, /api/v1/datasets/[0-9a-f-]{36}/versions/[^/]+/files/[0-9a-f-]{36}$, GET, allow
p, notebook_session, /api/v1/notebooks/[0-9a-f-]{36}/manifest$, GET, allow
p, notebook_session, /api/v1/notebooks/[0-9a-f-]{36}/session/progress$, POST, allow
p, notebooks_user, /api/v1/notebooks(/.*)?$, (GET|POST|PATCH|DELETE), allow
```

`notebooks_user` is the role gate 2 grants (a `g` row per user). In gate 1 only `admin` reaches `/notebooks` through its `/*` policy. The webapp decides whether to show the Notebooks entry by calling `GET /notebooks/-/capacity` and reading 200 or 401, not by hard-coding a role.
