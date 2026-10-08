# RFC 007: Notebooks

| Status | Draft |
|--------|-------|
| Author | DataMap Team |
| Created | 2026-10-02 |
| Updated | 2026-10-03 |

## Summary

Researchers download a dataset to open it in a notebook on their own machine.
This RFC puts the notebook next to the data: **JupyterLab, embedded in the
DataMap shell, one container per user, with the dataset's files already on disk
and a `datamap` library already loaded, in Python or R.**

The shape of the feature was settled in the design document (*Notebooks —
discovery*, Claude Design, 2026-10-01) and is restated here as decisions. The
resource envelope and the scope were settled in review on 2026-10-02 and
2026-10-03. The decisions that shape everything else:

1. **One dataset per notebook, pinned to a version.** A notebook is a view on a
   version; a newer version is offered, never applied. The schema, the token
   and the mount layout carry a *list* of datasets with one entry, so that more
   than one later is a UI change and not a migration.
2. **A session mounts a selection of files, never more than 20 GB.** A version
   under the ceiling selects everything by default; a larger one opens with a
   picker. There is no second code path for data that is not on disk.
3. **Sessions are ephemeral and bounded.** A session starts when the notebook
   is opened, stops silently after 60 minutes idle, and ends after 12 hours no
   matter what. The notebook file survives; memory does not.
4. **Hard limits in cgroups, not advisories on screen.** The host is shared
   with a project that already saturates its CPU (RFC 004, *What the host can
   take*). DataMap reserves 8 cores and 56 GB for notebooks and the hub enforces
   that from the outside.
5. **`/data` is read only; the notebook writes to `/outputs`.** That is what
   makes "Save to DataMap" a file picker rather than a diff.
6. **Access is checked where the data is served**, by the gatekeeper, against a
   session token, with the same rule the download link uses — embargo
   included. The kernel can read exactly what the dataset page would show the
   same person.
7. **Everything the design drew ships under this RFC**, in four increments
   that each deploy on their own: open with the data, save the result back,
   share, then templates and administration.

## Motivation

### Problem statement

The landing page has promised notebook integration since the first release
("No need to switch between applications or download files"). The webapp ships
a `/app/notebooks` page that says "coming soon", a "New notebook" entry in the
create menu, an "Open in notebook" card on every dataset, and a deletion warning
about notebooks that do not exist. RFC 005 reserved the `notebook_opened`
telemetry event. Every piece of the product has a notebook-shaped hole in it.

The research use is concrete: a researcher finds a NetCDF dataset in the
catalogue, wants to plot one variable over a year, and today has to download
2 GB, install xarray, and remember the file layout. An author who publishes a
dataset wants to attach "here is how you read these files" and has nowhere to
put it that runs. Many of them work in R, not Python.

### What exists today

- **No user credential.** The gatekeeper authenticates the webapp with
  `X-Api-Key` and `X-Api-Secret` and trusts `X-User-Id` from it. A kernel
  running the user's code cannot be handed the webapp's key, so a per-user,
  per-session credential has to exist before any library can call the API.
- **Files are served by pre-signed MinIO URL**, after the gatekeeper has
  checked tenancy, visibility and embargo (RFC 003). That check is the one the
  notebook goes through; there is no second copy of it.
- **Uploads land in the bucket under `staged/`**, the gatekeeper creates a
  `DataFile` in `PENDING`, and the archivist collocates it. "Save to DataMap"
  is that path minus TUS.
- **The host is saturated.** 32 cores at a sustained load of 32, 114 GB of
  125 GB memory free, by a neighbouring Jupyter container (`efc_datamap_jupyter`)
  that is not ours. Memory is available; CPU is not, and anything we run will
  compete with it.
- **Storage is a NAS**, mounted on the host and handed to MinIO as a bind
  volume (`STORAGE_DOCKER_VOLUME`). MinIO of the version we run stores objects
  in its own layout (`xl.meta` plus parts); the bucket directory is not a tree
  of files that can be mounted into a container.
- **One person maintains four services.** The scope below is phased so that
  each increment is usable on its own, and the order is the order of value.

### Goals

- Open any dataset version the user can read in a running kernel, with the
  files on a local path and a library that knows the dataset, in under a
  minute for the common case.
- Put the result back: output files and the notebook that produced them become
  a new version or a new dataset, as a draft, with provenance.
- Keep DataMap's own services unaffected by anything a notebook does: a runaway
  cell costs that user their session, not anyone else their API.
- Make every limit visible to the user before it bites, and every session
  visible to an administrator.
- Reuse the dataset authorization path. No notebook-specific rule about who
  may read which file.
- Know how the feature is used, per dataset and per user, from durable data.

### Non-goals

- Heavy or long-running computation. A session is for exploration; anything
  that needs more than 2 cores, 12 GB or 12 hours is a different product.
- GPUs. The host has none that we know of, and nothing here assumes one.
- Kernels other than Python and R.
- Real-time collaboration on one notebook. Sharing is read only, with
  "Duplicate to edit".
- Running notebooks on a second machine. The design does not prevent it (see
  *Alternatives*), but this RFC runs where the data is.
- Draft versions. Only published versions open in a notebook.

## Decisions

Restated from the design document where it decided, decided in review where
it did not.

| Topic | Decision | Source |
|---|---|---|
| Runtime | JupyterHub, one Docker container per session, JupyterLab inside a DataMap frame | RFC |
| Kernels | Python 3 and R, chosen when the notebook is created; one image with both | review |
| Datasets per notebook | One, pinned to the version it was opened on; schema takes a list | design, review |
| Newer version | Quiet card offers "Switch"; switching re-mounts and restarts the kernel | design |
| Data in the session | Selected files copied to `/data`, read only, at most 20 GB per session; a version under 20 GB selects all; a larger one opens with a picker; a single file over 20 GB cannot be selected | review |
| Session end | Silently stopped after 60 min idle; hard limit 12 h; warning 30 min before | design (12 h, 30 min), RFC (60 min) |
| Sessions per user | One. Opening a second notebook offers to stop the first | design (open), RFC |
| Seats on the platform | 4 concurrent sessions; the fifth user is told to wait | review |
| CPU per session | 2 cores ceiling, 1 core guaranteed | review |
| Memory per session | 12 GB, hard — what Colab gives, so "if it runs on Colab it runs here" | review |
| Notebook storage per user | 2 GB; outputs count, mounted data does not | design |
| Outputs after a session | Kept 24 h, then purged | design |
| Embargo | The dataset's own rule: owner and people with a `dataset_permissions` row can open it; everyone else sees the embargo dialog | review |
| Published only | A notebook opens a published version, never a draft | review |
| Visibility | Private by default; shared with the dataset's share dialog; read only for others | design |
| Notebook saved into a dataset | A snapshot, not a link | design (open), RFC |
| Download | The `.ipynb` can be downloaded at any time, without data | review |
| Administration | An admin page: live sessions with Stop, seats, storage per user, usage per dataset | review |
| Rollout | Admins, then everyone | review |
| Language | Strings through next-intl, pt-BR and en, per RFC 006; JupyterLab gets its pt-BR language pack | RFC |

## Technical design

### Components

```
browser ──/app/notebooks/{id}──▶ datamap-webapp ──RPC──▶ gatekeeper
   │                                                        │  mints session token
   │  iframe /user/{uid}/lab        ┌────────────┐          │  owns notebook rows
   └───────── /hub/login?token ───▶ │ JupyterHub │ ◀────────┘  asks hub to start/stop
                                    │ + culler   │
                                    └─────┬──────┘ docker socket (proxied, read/create only)
                                          │ spawns
                                    ┌─────▼──────┐
                                    │ datamap-   │  cpus=2 (shares=1024) mem=12g pids=256
                                    │ notebook   │  /data      ← copied, root:root 0555
                                    │ (per user) │  /outputs   ← notebooks/{uid}/.outputs/{nb}
                                    │ py + R     │  /home/jovyan/work ← notebooks/{uid}/
                                    └─────┬──────┘
                                          │ Authorization: Bearer <session token>
                                    gatekeeper ──▶ MinIO (pre-signed URL, loopback)
```

Six pieces, four of them new:

| Piece | Where | New? |
|---|---|---|
| `jupyterhub` container, `jupyterhub_config.py`, a JWT authenticator (~60 lines), idle culler | `gatekeeper/infrastructure/jupyterhub/` | yes |
| `datamap-notebook` image: `jupyter/minimal-notebook` base, Python and R stacks, both SDKs, entrypoint that materialises `/data` | `gatekeeper/infrastructure/jupyterhub/image/` | yes |
| `datamap` Python package and `datamap` R package | `datamap-sdk/` (new repository, `python/` and `r/`) | yes |
| Curated template notebooks | `gatekeeper/infrastructure/jupyterhub/templates/` | yes |
| Gatekeeper: notebook, session and permission entities, session token, bearer authentication, save-back, admin and internal routes | `gatekeeper/app/` | changes |
| Webapp: list, editor frame, picker, session states, save modal, share, templates, admin page, dataset page integration | `datamap-webapp/` | changes |
| nginx: `/hub/` and `/user/` with websocket upgrade | `gatekeeper/infrastructure/nginx/default.conf` | one block |

The hub reaches Docker through `tecnativa/docker-socket-proxy` with only
`CONTAINERS`, `IMAGES` and `NETWORKS` enabled. The hub's own state goes in a
`jupyterhub` database on the existing PostgreSQL, so the backup timer from the
database runbook covers it without a second mechanism.

### Session lifecycle

A session belongs to one user and one notebook. States, as the user sees them
(design 1d) and as the gatekeeper stores them:

```
          open notebook            ready              60 min idle | Stop
 (none) ──────────────▶ starting ────────▶ running ─────────────────────▶ stopped
                           │                 │                              │
                           │ spawn failed    │ 12 h                         │ Resume
                           ▼                 ▼                              ▼
                         failed            ended                        starting
```

| Transition | Who | How |
|---|---|---|
| open → `starting` | webapp → gatekeeper `POST /notebooks/{id}/sessions` | gatekeeper checks seat count, storage quota, dataset readability (embargo rule included), selection size; inserts the row; mints the token; returns the hub login URL |
| `starting` → `running` | hub → gatekeeper `POST /internal/notebook-sessions/{id}/started` | after the single-user server answers its health check |
| `running` → `stopped` | culler (idle 60 min) or user (Stop) or admin (Stop) | hub `post_stop_hook` → `POST /internal/notebook-sessions/{id}/stopped` |
| `running` → `ended` | culler `--max-age=43200` | same hook, `reason=max_age` |
| `stopped` → `starting` | user (Resume, or just opening it) | same as open; `/outputs` is reattached if still within 24 h |
| any → `failed` | spawn timeout or image error | hook with `reason=spawn_error`; the user sees "Could not start, try again" |

Idle means what `jupyterhub-idle-culler` means: no kernel activity and no open
websocket for 60 minutes. A plot sitting on screen with no cell running is idle.
That is deliberate: the seat is the scarce thing, not the user's attention.

The 12 h bar on the session chip reads `started_at` from the gatekeeper. CPU
and memory on the chip come from `jupyter-resource-usage`, installed in the
image and exposed at `/user/{uid}/api/metrics/v1`; the hub lives under the same
hostname as the webapp, so the page can read it with the hub cookie. The 30 min
warning is a client-side computation on `started_at`.

The "Starting" screen shows what the entrypoint is doing. The entrypoint writes
one line per step to `/session/progress`, which DockerSpawner surfaces through
the hub's progress API; the webapp polls `GET /notebooks/{id}/session` and the
gatekeeper proxies that endpoint with its hub admin token.

### Data in the session

Three mounts, all on the storage volume, as siblings of the MinIO bucket
directory and never inside it:

```
${STORAGE_DOCKER_VOLUME}/
  datamap/                      ← MinIO bucket, untouched
  notebooks/{user_id}/          ← /home/jovyan/work  rw   permanent, in the 2 GB quota
  notebooks/{user_id}/.outputs/{notebook_id}/
                                ← /outputs           rw   purged 24 h after the session ends
  sessions/{session_id}/data/   ← /data              ro   deleted when the session stops
```

The entrypoint runs as root, creates the user's directories with the kernel's
uid on first use, materialises `/data`, sets it to `root:root 0555`, and then
drops to the unprivileged user through the base image's `start.sh`. Read only
is enforced by ownership, not by a mount flag, because the same directory has
to be writable for a few seconds first.

**Selection.** A session mounts the files in the notebook's selection, stored
on `notebook_datasets.file_ids`. Null means "all files of the version", which
is the default when the version is at or under `NOTEBOOK_DATA_MAX_BYTES`
(20 GB). For a larger version, "Open in notebook" on the dataset page opens
the file picker instead of a session: a searchable list with sizes, checkboxes
and a running total, which refuses to go over 20 GB and greys out any single
file over it with the reason. The per-file button on a file row pre-selects
that file. A 1 TB dataset therefore opens, with the files the researcher
chose; what it does not do is pretend the whole thing is on disk.

Changing the selection restarts the session, because `/data` is root-owned
once the kernel is running. The side panel lists mounted files, says "14 of 40
files mounted · change selection (restarts the session)", and the rest is
`ds.files` with `local=False` and no path.

**Materialising `/data`.** The entrypoint asks the gatekeeper for the
selection's manifest (`GET /notebooks/{id}/manifest` with the session token),
then downloads each file by its pre-signed URL into
`/data/{dataset_id}/v{N}/{original name}`. MinIO is on the same host, so this
is a loopback copy at NAS speed: the design's "usually under 20 s" holds for a
2.3 GB version, and the ceiling bounds the worst case at roughly a minute. The
copy runs inside the user's own cgroup, so a slow copy costs that user, not the
hub. Six seats times 20 GB is 120 GB of scratch at the very worst, deleted when
the session stops.

Why copy rather than mount: a published version is immutable, so a copy never
goes stale; the MinIO storage layout cannot be bind-mounted; and a real path on
a real filesystem is what every researcher's existing snippet assumes, in
either language and for every file type — NetCDF, CSV, xlsx, text, or a raw
instrument dump with no extension. Nothing in the SDK has to understand the
format; the library the researcher already uses does. The lazy alternative is
in *Alternatives considered*, with what it would buy and cost.

The gatekeeper mounts `notebooks/` read only: that is where it measures the
quota, reads an `.ipynb` to serve or render it, and reads `/outputs` to save
files back. It never writes there; only JupyterLab does, inside the user's
container.

**Quota.** `du` over `notebooks/{user_id}/` when a session is requested, and
again when it stops; the figure is stored on the user's row and shown on the
list page ("184 MB of 2 GB"). Over the quota, a new session is refused with the
"Notebook storage is full" dialog (design 1g). There is no filesystem quota: the
NAS may not support project quotas, and a refusal at the next start is enough
for a 2 GB limit that only outputs can fill.

**Purge.** The archivist, which already runs the scheduled jobs, gets one more:
every 15 minutes, delete `sessions/{id}/data` for sessions not `running` or
`starting`, and `.outputs/{notebook_id}` for notebooks whose last session ended
more than 24 h ago. The gatekeeper's internal API tells it which, the same way
it tells it which files to collocate.

### Session token and SDK authentication

The gatekeeper mints a JWT when a session is requested, signed with
`AUTH_NOTEBOOK_SESSION_TOKEN_SECRET` (HS256, the same pattern as the signed
upload token). Claims:

```json
{
  "sub": "<user_id>",
  "tenancies": ["data-amazon"],
  "notebook_id": "<uuid>",
  "session_id": "<uuid>",
  "datasets": [{"id": "<uuid>", "version": 2}],
  "kernel": "python3",
  "locale": "pt-BR",
  "iat": 1790950000,
  "exp": 1790993200
}
```

`exp` is `iat` plus the 12 h limit plus 10 minutes. Three parties use it:

1. **The hub**, to log the user in. The webapp sends the browser to
   `/hub/login?token=<jwt>` once; the authenticator verifies the signature and
   expiry, uses `sub` as the hub username, and stores the claims as
   `auth_state`. The hub cookie carries the rest of the session.
2. **The spawner**, to configure the container. `pre_spawn_start` reads
   `auth_state` and sets `DATAMAP_SESSION_TOKEN`, `DATAMAP_API_URL`,
   `DATAMAP_NOTEBOOK_ID`, `DATAMAP_DATASETS` (JSON), `MEM_LIMIT` and
   `CPU_LIMIT` (the last two are what `jupyter-resource-usage` displays), and
   the Lab locale.
3. **The SDKs and the entrypoint**, as `Authorization: Bearer <jwt>` against
   the gatekeeper.

**Bearer authentication in the gatekeeper.** `authenticate` gains a second
path: when `Authorization: Bearer` is present and no API key is, verify the JWT,
look up `notebook_sessions` by `session_id`, and require state `starting` or
`running`. On success, `request.state` carries the user id and tenancies the
`user_parser` and `tenancy_parser` interceptors read today from headers, so
every downstream service and repository is unchanged. Revocation is the state
check: when the session stops, the token stops working within one request.

The bearer path is allowed on dataset read routes only: `GET /datasets/{id}`,
version and file listing, download URL, and the notebook's own manifest.
Casbin gets one subject role, `notebook_session`, with exactly those objects
and `GET`. The token cannot create, upload or delete anything, so a notebook
that leaks its token to a third party leaks read access to what that user
could already read, for at most 12 hours.

Outside a session there is no credential in this RFC: client keys are issued
to applications and carry `X-User-Id` on trust, so they must never reach a
researcher. The personal token for the SDK on a laptop or in Colab is RFC 010:
the same bearer path with a second branch, and what makes the Colab
alternative cheap.

### SDK surface

Both packages are thin on purpose: they answer "what is this dataset and where
are its files", and get out of the way of xarray, pandas, ncdf4 or whatever
the researcher already uses on a path.

Python, pre-imported in the generated first cell:

```python
import datamap
ds = datamap.open()                        # pinned dataset and version, from the environment
ds = datamap.open("3f9c1e", version=1)     # any other the user can read, listing and metadata only
ds.meta                                    # title, coverage, license, DOI, version
ds.files                                   # [File(name, size, type, local, path)]
ds.path("t3_smps_20140201_20140228.nc")    # the local path, or raises if not mounted
ds.open_mfdataset("t3_smps_*.nc")          # xarray over the local paths; convenience
ds.read_csv("quality_flags/flags.csv")     # pandas; convenience
```

R, loaded in the generated first cell:

```r
library(datamap)
ds <- datamap::open()
ds$meta
ds$files                                   # data.frame: name, size, type, local, path
ds$path("t3_smps_20140201_20140228.nc")
ncdf4::nc_open(ds$path("t3_smps_20140201_20140228.nc"))
```

`datamap.open()` with no argument reads `DATAMAP_DATASETS`. With an id it
returns listing and metadata for another dataset the user can read, with no
local files: mounting a second dataset is the "multiple datasets" extension,
and the function signature already fits it. Every call goes through the
gatekeeper; the SDK never sees MinIO credentials.

### Save to DataMap

Design 1e, as mechanics. The modal lists `/outputs` (read from the gatekeeper's
read-only mount) and the notebook itself, pre-checked; the user picks files and
a target.

| Target | Who | What the gatekeeper does |
|---|---|---|
| New version of this dataset | writers of the dataset | creates `v{N+1}` as a draft carrying the existing files, uploads each chosen file to `staged/{uuid}` in the bucket, creates its `DataFile` in `PENDING` exactly as the TUS post-finish hook does, records provenance on the version, and re-pins the notebook to `v{N+1}` |
| New dataset derived from this one | anyone who can read the source | creates a draft dataset in the user's tenancy with `derived_from` pointing at the source version, then the same upload path |

Nothing publishes: the save lands as a draft, and the existing dataset flow
takes over. The archivist collocates the staged objects as it does for every
upload. The copy from `/outputs` to the bucket runs as a background task in
the gatekeeper with a status the modal polls; 2 GB is the most it can ever be.

Provenance is a `jsonb` on the version: `{"notebook_id", "session_id",
"kernel", "sdk_version", "saved_at"}`, and a `derived_from_dataset_id`,
`derived_from_version` pair on the dataset. Both show on the dataset page.
The saved `.ipynb` is a snapshot: later edits to the live notebook do not
change it, and deleting the notebook does not remove it.

### Sharing

`notebook_permissions` has the shape of `dataset_permissions` (RFC 003) with
`read` as the only level. The dataset share dialog is reused; when the invitee
cannot read the dataset, it offers "Share both" (design 1g). A reader opens
the notebook read only: the `.ipynb` is rendered client-side from
`GET /notebooks/{id}/content`, with the author's last outputs, no kernel and
no seat. "Duplicate to edit" copies the file into the reader's directory as a
new notebook pinned to the same version when they can read it, or with no
dataset ("Attach another dataset") when they cannot.

### Templates

Six curated notebooks, each in a Python and an R variant where the libraries
exist, in `gatekeeper/infrastructure/jupyterhub/templates/` and served by
`GET /notebooks/templates`. The picker shows them with the "fits .nc / .csv /
any" footer and greys out the ones the chosen version has no files for. A
template is a file copied into the user's directory with the first cell
rewritten for the chosen dataset; it has no identity of its own afterwards.

### Data model

```sql
CREATE TABLE notebooks (
  id          uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id    uuid         NOT NULL REFERENCES users(id),
  name        varchar(128) NOT NULL,            -- file name without .ipynb, unique per owner
  path        varchar(512) NOT NULL,            -- relative to notebooks/{owner_id}/
  kernel      varchar(16)  NOT NULL,            -- python3 | ir
  size_bytes  bigint       NOT NULL DEFAULT 0,
  created_at  timestamptz  NOT NULL DEFAULT now(),
  updated_at  timestamptz  NOT NULL DEFAULT now(),
  UNIQUE (owner_id, name)
);

-- One row today; the service enforces that. More than one is the
-- multi-dataset extension and needs no migration.
CREATE TABLE notebook_datasets (
  notebook_id     uuid     NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
  position        smallint NOT NULL DEFAULT 0,
  dataset_id      uuid     NULL REFERENCES datasets(id) ON DELETE SET NULL,
  dataset_version integer  NULL,
  file_ids        jsonb    NULL,                -- null: every file of the version
  PRIMARY KEY (notebook_id, position)
);

-- Append-only. Rows outlive the notebook and the dataset: this is the usage record.
CREATE TABLE notebook_sessions (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  notebook_id     uuid        NULL REFERENCES notebooks(id) ON DELETE SET NULL,
  user_id         uuid        NOT NULL REFERENCES users(id),
  tenancy         varchar(64) NOT NULL,
  dataset_id      uuid        NULL,             -- denormalised, no FK, survives deletion
  dataset_version integer     NULL,
  kernel          varchar(16) NOT NULL,
  state           varchar(16) NOT NULL,         -- starting | running | stopped | ended | failed
  mounted_files   integer     NOT NULL DEFAULT 0,
  mounted_bytes   bigint      NOT NULL DEFAULT 0,
  requested_at    timestamptz NOT NULL DEFAULT now(),
  started_at      timestamptz NULL,
  stopped_at      timestamptz NULL,
  stop_reason     varchar(32) NULL              -- idle | user | admin | max_age | spawn_error
);

CREATE INDEX idx_notebook_sessions_live
  ON notebook_sessions (user_id) WHERE state IN ('starting', 'running');
CREATE INDEX idx_notebook_sessions_dataset
  ON notebook_sessions (dataset_id, requested_at DESC);

CREATE TABLE notebook_permissions (
  notebook_id uuid        NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
  user_id     uuid        NOT NULL REFERENCES users(id),
  level       varchar(16) NOT NULL,             -- read
  granted_by  uuid        NULL REFERENCES users(id),
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (notebook_id, user_id)
);

ALTER TABLE users ADD COLUMN notebook_storage_bytes bigint NOT NULL DEFAULT 0;

ALTER TABLE dataset_versions ADD COLUMN provenance jsonb NULL;
ALTER TABLE datasets
  ADD COLUMN derived_from_dataset_id uuid    NULL REFERENCES datasets(id) ON DELETE SET NULL,
  ADD COLUMN derived_from_version    integer NULL;
```

`notebook_datasets.dataset_id` is nullable with `ON DELETE SET NULL` so that
deleting a dataset leaves the notebook with its code and the "source deleted"
state (design 1d) instead of failing the delete or cascading into someone's
work.

The seat limit is a count over `idx_notebook_sessions_live`, taken inside the
same transaction that inserts the `starting` row, with `SELECT ... FOR UPDATE`
on a one-row `notebook_capacity` table so two requests cannot both see five
seats taken. The hub's own `active_server_limit` is set to the same number as a
second fence, not as the first.

### Routes

Gatekeeper, under the existing authentication (webapp key plus `X-User-Id`):

| Route | Does |
|---|---|
| `GET /notebooks/` | the caller's notebooks and the ones shared with them, with session state and dataset name and version; `?dataset_id=` for the dataset page card |
| `GET /notebooks/templates` | the curated templates with their file-type filters |
| `POST /notebooks/` | create from a dataset version (`dataset_id`, `version`, `kernel`, optional `file_ids`, optional `template`); writes the first cell; 409 when the version cannot be read or is not published; 413 when the selection is over the ceiling |
| `GET/PATCH/DELETE /notebooks/{id}` | read, rename, change selection, delete (stops a live session first) |
| `GET /notebooks/{id}/content` | the `.ipynb` JSON; `?download=1` serves it as an attachment |
| `POST /notebooks/{id}/duplicate` | copy into the caller's directory |
| `GET/PUT/DELETE /notebooks/{id}/permissions` | share, same shape as the dataset routes |
| `POST /notebooks/{id}/sessions` | start or resume; 429 `no_seats`, 413 `storage_full`, 409 `session_elsewhere` |
| `GET /notebooks/{id}/session` | current state, `started_at`, progress lines while starting |
| `DELETE /notebooks/{id}/session` | stop |
| `GET /notebooks/{id}/outputs` | files in `/outputs`, for the save modal |
| `POST /notebooks/{id}/save` | Save to DataMap; returns a task id |
| `GET /notebooks/{id}/save/{task_id}` | upload progress and the resulting version or dataset |
| `GET /notebooks/-/capacity` | seats taken and total, for the list page |

Admin, under the `admin` role:

| Route | Does |
|---|---|
| `GET /admin/notebooks/sessions` | live sessions: user, dataset, kernel, started, mounted size |
| `DELETE /admin/notebooks/sessions/{id}` | stop, `reason=admin`; the user sees "stopped by an administrator" |
| `GET /admin/notebooks/storage` | storage per user, descending |
| `GET /admin/notebooks/usage?since=` | sessions and distinct users per dataset, per tenancy, per kernel, per month, from `notebook_sessions` |

Internal, under the hub's own client key:

| Route | Does |
|---|---|
| `POST /internal/notebook-sessions/{id}/started` | hub reports the server is up |
| `POST /internal/notebook-sessions/{id}/stopped` | hub reports stop, with reason |
| `GET /internal/notebook-sessions/purgeable` | archivist asks what to delete |

Bearer (session token), read only: the dataset read routes listed under
*Session token*, plus `GET /notebooks/{id}/manifest`.

### Limits and how each is enforced

| Limit | Value | Enforced by | User sees |
|---|---|---|---|
| CPU | 2 cores ceiling, 1 guaranteed | Docker `nano_cpus=2e9`, `cpu_shares=1024` | chip "CPU 0.4 / 2" |
| Memory | 12 GB | Docker `mem_limit=12g`, `memswap_limit=12g`; OOM kills the kernel, not the server | chip "RAM 1.1 / 12 GB"; Lab's "kernel died" |
| Processes | 256 | Docker `pids_limit` | nothing, unless a fork bomb |
| Time | 12 h | `jupyterhub-idle-culler --max-age=43200` | bar on the chip, amber at 30 min, "Session ended" screen |
| Idle | 60 min | `--timeout=3600` | "Session stopped · idle since" |
| Seats | 4 | gatekeeper transaction; hub `active_server_limit=4` | "All 4 seats are in use. Sessions stop after an hour idle; try again shortly." with the count |
| Sessions per user | 1 | partial index query; hub `named_servers=False` | "Stop the session of *x* to open this one?" |
| Notebook storage | 2 GB | `du` at start and stop | "184 MB of 2 GB", "Notebook storage is full" dialog |
| Mounted data | 20 GB per session | gatekeeper, at creation and at every selection change | picker's running total; "14 of 40 files mounted" |
| Outputs retention | 24 h | archivist purge | "1 output file is kept for 24 h" |
| Network | gatekeeper, MinIO, PyPI and CRAN only | Docker network with egress rules on the host | `pip install` and `install.packages` work; `requests.get("https://...")` does not |

The arithmetic: 4 × 12 GB is 48 GB, and 8 GB more for the hub, the culler,
the socket proxy and the page cache of four concurrent copies makes the 56 GB
envelope — under half of the 114 GB the host had free with the neighbour
running. CPU is not oversubscribed: 4 × 2 = 8 ceilings on 8 cores, with the
`cpu_shares` floor as a tie-breaker when all four are busy at once.

Twelve gigabytes is what a Colab session gets, which turns the limit into a
promise users already understand: if it runs on Colab, it runs here. The
design's 8 GB and the first draft's 4 GB were both rejected for the same
reason: a seat limit is visible and has a queue, while a memory limit kills
the kernel in the middle of a cell, which is the worse experience. Memory is
the resource this host has to spare; seats are what the idle culler gives
back.

Both numbers are one setting each (`NOTEBOOK_SESSION_MEMORY`,
`NOTEBOOK_SEATS`) and one hub value. If four seats turn out to be the thing
people hit, 6 × 8 GB is the same 48 GB with two more seats, and CPU goes to
12 ceilings on 8 cores, which an exploration workload can absorb.

The "no seats" message is the one screen the design did not draw. It has to
exist on day one: with four seats and a 60 min idle timeout, it will be seen.

### Webapp

Pages and components, following design 1a–1g:

- `/app/notebooks` — list with "Mine" and "Shared with me", the seat counter
  and the storage counter. Session column is the only live cell, polled every
  10 s while a session is `starting`. "+ New notebook" opens the dataset and
  kernel choice; "From template" opens the template picker.
- `/app/notebooks/{id}` — the editor frame. DataMap draws the 56 px top bar
  (name, session chip, Share, Save to DataMap, menu with Download `.ipynb`,
  Change selection, Stop, Delete) and the 320 px side panel (dataset, mounted
  files, snippets, outputs); JupyterLab fills the rest in an iframe at
  `/user/{uid}/lab/tree/{path}`. Same origin, so the hub cookie and the
  resource-usage endpoint are reachable, and the single-user server's default
  `frame-ancestors 'self'` allows the frame.
- Session states (design 1d) replace the iframe: starting (progress lines),
  stopped (Resume / Read only / Download), limit approaching (banner, from
  `started_at`), ended, source deleted, stopped by an administrator, and the
  new "no seats".
- File picker: used from the dataset page for versions over the ceiling, from
  the per-file button, and from "Change selection" in the menu.
- Save to DataMap: the three-step modal from design 1e, polling the save task.
- Dataset page: "Open in notebook" between Share and Download, enabled by the
  same readability rule as Download (so embargo behaves identically), with the
  lock and dialog for those who cannot; per-file hover action; "My notebooks"
  card; provenance and "derived from" on versions and datasets that have them.
- `/app/admin/notebooks` — live sessions with Stop, seats, storage per user,
  usage per dataset for a chosen period. Admin role only.
- Snippets in the side panel **copy to the clipboard**. Inserting into the
  active cell from outside the iframe needs a JupyterLab extension listening
  for `postMessage`; that is a follow-up and the panel's copy explains the
  difference ("copied · paste into a cell").

Every string goes through the next-intl catalogue (RFC 006), pt-BR and en. The
image installs `jupyterlab-language-pack-pt-BR` and the spawner sets Lab's
locale from the token's `locale` claim, so the frame and the thing inside it
agree.

### Image

`datamap-notebook`, built in CI from `gatekeeper/infrastructure/jupyterhub/image/`,
tagged by date and pinned in `jupyterhub_config.py`. Base `jupyter/minimal-notebook`
on Python 3.11 (the kernel is not the gatekeeper; 3.10 is not a constraint
here). Pinned: `xarray`, `pandas`, `netCDF4`, `h5netcdf`, `matplotlib`,
`scipy`, `openpyxl`, `jupyter-resource-usage`, `jupyterlab-language-pack-pt-BR`,
`datamap`; and for R, `IRkernel`, `tidyverse`, `ncdf4`, `readxl`, `data.table`,
`datamap`. One image with both kernels: about 4 GB on disk, which costs nothing
per session and keeps the spawner to one configuration. The SDK versions are
shown on the "Starting" screen because they are what users will cite in a
method record.

`pip install` and `install.packages` work inside a session and are lost when
the session stops. That is the stated behaviour: "One fixed environment", and
a package someone needs every time is a request to add it to the image.

### Rollout

Two gates, both Casbin policy on the `/notebooks` object, no code between them:

| Gate | Who | What we watch |
|---|---|---|
| 1 | `admin` role (the page is already gated this way) | spawn time, copy time on the NAS, host load with 2–3 sessions, culler behaviour, the picker on a large dataset |
| 2 | every tenancy | seat contention, storage growth, which templates get used, what breaks in real NetCDF and real R |

The webapp's existing `ListNotebooksPage.auth = { role: "admin" }` becomes a
check on the same policy so the two cannot disagree.

### Increments

Four increments, each deployable and useful on its own, in the order of value.

**A — a notebook that opens with the data in it.** Hub, socket proxy, image
with both kernels, nginx, compose. Gatekeeper tables, session token, bearer
path, notebook and session routes, manifest, internal hub routes, Casbin role,
seat transaction. Python and R SDKs, published. Entrypoint. Archivist purge
job. Webapp list, create dialog, editor frame, session chip and states, file
picker, dataset page actions, no-seats screen, download, strings. Integration
tests, hub smoke test, metrics, dashboard panel, runbook.

**B — the result goes back.** Outputs listing, save task, staged upload and
`DataFile` creation, draft version and derived dataset, provenance columns,
re-pin. Save modal, provenance on the dataset page. An integration test that
a saved file is collocated by the archivist like an upload.

**C — sharing.** Permissions, duplicate, content for readers. Share dialog
reuse, "share both" prompt, read-only renderer, "Shared with me".

**D — templates and administration.** Six templates in two languages, picker,
type filter. Admin routes and page: sessions with Stop, storage, usage.

A is a feature people can use; B is what makes it a repository feature rather
than a scratchpad; C and D are what make it a product that can be supported.

### Observability

Two kinds, with different lifetimes.

**Operational, in Prometheus**, following the RFC 005 contract and low
cardinality by design:

| Metric | Type | Labels |
|---|---|---|
| `datamap_notebook_sessions_active` | gauge | `kernel` |
| `datamap_notebook_session_requests_total` | counter | `outcome` = started, no_seats, storage_full, forbidden, spawn_error |
| `datamap_notebook_session_duration_seconds` | histogram | `stop_reason` |
| `datamap_notebook_data_copy_seconds` | histogram | — |
| `datamap_notebook_data_copy_bytes` | histogram | — |
| `datamap_notebook_saves_total` | counter | `target` = version, dataset; `outcome` |

Container CPU and memory per session come from cAdvisor, which the
observability stack already runs; the dashboard panel filters on the
`datamap-notebook-` container name prefix. One alert: `no_seats` refusals above
zero for an hour, which is the signal that the envelope is too small or the
idle timeout too long.

**Usage, in PostgreSQL.** Prometheus cannot carry a `dataset_id` label without
blowing its cardinality, and it forgets after the retention window. The
questions that matter for the feature — which datasets get opened, by how
many people, in which language, whether the saves come back — are answered
from `notebook_sessions`, which is append-only and survives the deletion of
the notebook and of the dataset. They are queries, not materialised data:
`GET /admin/notebooks/usage` runs them for the admin page, and the same SQL
can sit behind a Grafana panel on a read-only PostgreSQL datasource if that
is ever wanted. Sessions per dataset per month is the first one; it is an
index scan on `idx_notebook_sessions_dataset`.

The hub's logs go through Alloy to Loki like every other container. The
entrypoint logs with `session_id` and `dataset_id` as fields.

### Testing

- **Unit**: token mint and verify, seat transaction, selection size, quota
  refusal, state transitions, provenance payload, SDKs against a mocked
  gatekeeper.
- **Integration** (the suite that catches what matters, per the project
  guidelines): bearer authentication on each allowed route and 401 on every
  other; a stopped session's token refused; seat exhaustion with four fake
  sessions; the embargo rule applied to a session request exactly as to a
  download; `ON DELETE SET NULL` when the dataset goes; a save creating a
  draft version with `PENDING` files the archivist job then collocates; the
  internal hub routes under the hub's client key and 401 under the webapp's;
  the admin routes under `admin` and 403 under a member.
- **Hub smoke test** in CI: compose up the hub with the socket proxy, log in
  with a token minted by the test, assert the container appears with
  `mem_limit=12g` and `/data` owned by root, run one cell in each kernel, stop
  it, assert the stopped hook fired. This is the test that proves the limits
  are real.
- **Make the first integration test fail first**: write the bearer test
  before the bearer path, and watch it get 401.

## Alternatives considered

### JupyterLite in the browser

Zero host CPU: Pyodide runs the kernel in the user's tab. Rejected because the
data has to travel to the browser, which is the problem this feature removes;
`netCDF4` does not exist for Pyodide; there is no R; and 2 GB in browser
memory is a crash, not a session. It remains the natural renderer for a
shared read-only notebook with small files, and nothing here prevents adding it.

### One shared JupyterLab, no hub

One container, one process, users told apart by directory. Rejected: no
isolation of files, tokens or memory between users; one OOM kills everyone; no
per-user limit of any kind. Fine for a demo, a liability the day after.

### Mounting the MinIO storage directory

The bucket directory is in MinIO's `xl` layout and is not a file tree. Even if
it were, mounting it exposes every private and embargoed dataset to `ls`, which
discards RFC 003. Rejected on both counts.

### A FUSE mount (rclone, s3fs) instead of a copy

What it buys: no copy, so a session starts in seconds whatever the version's
size; no 20 GB ceiling and no picker, because a 1 TB version appears as a
tree and only the bytes a cell touches cross the loopback; `/data` stays a
real path, so the SDKs and every library work unchanged.

What it costs, in order of how much it worries us:

1. **Privilege in the one container that runs untrusted code.** A mount
   inside the container needs `/dev/fuse` and `CAP_SYS_ADMIN`. The way around
   it is to mount on the host, per session, from a privileged helper, and
   bind the mount point in — which puts one `rclone` process per session on
   the host, outside any session cgroup, with mounts to clean up after every
   crash and stale ones after every hub restart.
2. **Credentials.** The container cannot hold the MinIO root key, so each
   session needs an STS credential scoped to its dataset. The bucket is
   sharded by upload date (`datamap/{y}/{m}/{d}/{dataset_id}/{shard}/`), so
   the scope is a wildcard on the dataset id across every date, which is one
   more policy mechanism to get right and to test for leaks.
3. **The names.** The mount shows `datamap/2024/03/11/{id}/0/{uuid}`, not
   `/data/{id}/v2/{name}`, so a symlink tree built from the manifest sits on
   top, and the version pin is whichever symlinks exist.
4. **Failure modes a copy does not have.** A NAS hiccup under a FUSE read
   leaves the kernel in an uninterruptible wait; a copy either finishes or
   fails before the kernel starts. And `rclone --vfs-cache-mode full` still
   writes what it reads to a local cache, so "no copy" is partial.

More work than the copy and the picker, plus an operational surface the
copy does not have. The copy with a ceiling gives the
same result for every version under 20 GB and a usable result above it. If
the picker turns out to be the thing people hit every day, this is the
upgrade, and nothing in the SDK or the routes changes when it lands.

### Google Colab, or another hosted Jupyter

**What it is.** Colab is Google's free hosted Jupyter: a Google account gets a
virtual machine with 2 cores, about 12 GB of memory, sometimes a GPU, for up to
12 hours, with a fresh disk every session. "Open in Colab" is a link that
loads an `.ipynb` from a public URL into that machine.

**How it would work here.** The gatekeeper serves the `.ipynb`; the link opens
it in Colab; the first cell runs `pip install datamap`, the user pastes a
personal token, and the SDK downloads the files from DataMap into the
Colab machine through the same pre-signed URLs. Everything after that is the
researcher's own session on Google's hardware.

**What it would enable.** No seat limit and no load on our host; a GPU when
Google has one spare; a tool many researchers already use. The SDK's laptop
mode is the same code, so once a personal token exists this is small: the
token, the link, and a template whose first cell installs the SDK.

**Why it is not the base.** The data leaves the host every session, which is
the one thing the feature exists to avoid; a 2 GB version is a two-minute
download each time and a 20 GB one is not practical; there is nothing to
save back without the SDK doing an upload; a Google account is a requirement
we cannot make of every partner; and Google can change or withdraw the free
tier at will. It is a good complement for public datasets and for people
who need a GPU, and it is listed under *Open questions* as the second thing
a personal token would unlock.

### BinderHub or Kubernetes

RFC 004 decision 8 already says no Kubernetes. BinderHub builds an image per
repository, which is a different product.

### Hub-less: the gatekeeper spawns containers itself

Fewer moving parts on paper: no hub, no authenticator, no socket proxy. Rejected
because the hub is the part that already handles the hard cases: proxying
websockets per user, the culler, spawn progress, server limits, and the cookie
dance for the iframe. Rewriting those in the gatekeeper is more code than
configuring them, and the gatekeeper would need the Docker socket, which it
should never have.

## Out of scope

- Kernels other than Python and R; any package not in the image surviving a
  session.
- Changing limits from the admin page. CPU, memory, seats and the ceiling are
  settings and a deploy, so that a change is reviewed and recorded like any
  other.
- Running sessions on another machine. The spawner is the only place that
  would change (DockerSpawner to SSH or Swarm), and the token, SDK and routes
  stay as they are.
- Notebook versioning or history beyond the file on disk and the snapshots
  saved into datasets.
- Inserting a snippet into the active cell from the side panel (needs a Lab
  extension; the panel copies to the clipboard until then).
- Adding files to a running session without a restart.
- The `datamap-vis` NL2Vis widget inside the notebook. It is a natural guest
  once the SDK exists.

## Open questions

- **NAS throughput for the copy.** The 20 GB ceiling assumes the copy runs at
  NAS sequential speed on the loopback. Measure with a 10 GB selection in gate
  1; if it takes more than two minutes, either lower the ceiling or put
  `sessions/` on the local disk (110 GB free, which caps it at 3 × 20 GB plus
  margin).
- **Whether the neighbour's container keeps its 32 cores.** The CPU numbers
  here assume it does. If it goes away, the only thing to change is the seat
  count.
- **Personal tokens.** Decided and designed in RFC 010: a read-only,
  revocable token a user creates on the profile page, the same bearer path
  with a second branch, and `datamap.login()` plus `ds.download()` in the
  SDK. Downloads keep requiring an account and a tenancy, public dataset or
  not.
- **Who pays for PyPI and CRAN.** Installs are allowed and cost egress and a
  few seconds. If it becomes a problem, a local proxy cache (devpi, or a CRAN
  mirror) is one container.
- **Multiple datasets per notebook.** The schema and the token take a list;
  the mount layout is already per dataset. What is undecided is the UI for
  choosing them and how the 20 GB ceiling is split. Not before A has run.
