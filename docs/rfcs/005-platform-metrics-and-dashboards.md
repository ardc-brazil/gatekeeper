# RFC 005: Platform Metrics and Dashboards

| Status | Accepted |
|--------|----------|
| Author | DataMap Team |
| Created | 2026-09-26 |
| Updated | 2026-09-26 |

## Summary

Prometheus, Loki, Alloy and Grafana run in production (RFC 004 §1, §7), but
only the gatekeeper emits metrics, nothing measures the host or the other
containers, and Grafana has no dashboards. This RFC defines:

1. **One metric contract** shared by every DataMap service — the same names and
   labels in Python and in Node — so a single dashboard covers all of them.
2. **What each service emits**: gatekeeper, datamap-webapp (server and
   browser), archivist and zipper.
3. **The infrastructure exporters** added to the observability stack.
4. **Dashboards as versioned JSON** in this repository, provisioned read-only.
5. **What comes from logs instead of metrics**, and why.

## Motivation

The questions asked of the platform today have no answer without reading logs
by hand:

- Is the host out of disk, memory or CPU — and is it us or the neighbour?
- Which routes are slow, which fail, and since when?
- Is DataCite or MinIO the reason a request was slow?
- How many people downloaded, uploaded, searched, logged in this week?
- What does the site feel like in a browser: how long pages take, which break?
- Is the archivist moving files, and is the zipper producing zips?

Every serious production failure this year was found late because nothing
measured it. The upload hook failed for ninety days; the collocation backlog
had no gauge. Metrics that exist but are not on a dashboard are nearly as
invisible as metrics that do not exist.

### Goals

- Infrastructure, HTTP, integration and business visibility for every deployed
  service, on dashboards that ship with the code.
- Cardinality bounded by design, so Prometheus stays cheap on a CPU-saturated
  host (RFC 004, host capacity).
- No credential that needs manual rotation.

### Non-goals

- Alert delivery. Alertmanager's destination is still undecided
  (`docs/runbooks/observability.md`); new rules follow the existing ones and are
  visible in Grafana until that is decided.
- Distributed tracing. `X-Request-Id` already correlates webapp and gatekeeper
  logs; tracing can come later if that stops being enough.
- datamap-vis (a CLI, not deployed) and metadata-extractor (not deployed yet).
  metadata-extractor adopts the contract when it gets a production deployment.

## The metric contract

### Names

- Prefix `datamap_`. Units in the name, base units only: `_seconds`, `_bytes`,
  `_total` for counters.
- Which service emitted a series is **not** a label the code sets. It is the
  Prometheus `job` (`gatekeeper`, `webapp`, `archivist`, `zipper`), so the same
  metric name from two services never collides and one query spans them.

### Shared metrics — every service with an HTTP surface

| Metric | Type | Labels |
|---|---|---|
| `datamap_http_requests_total` | counter | `method`, `route`, `status` |
| `datamap_http_request_duration_seconds` | histogram | `method`, `route` |
| `datamap_http_request_size_bytes` | histogram | `method`, `route` |
| `datamap_http_response_size_bytes` | histogram | `method`, `route` |
| `datamap_http_requests_in_progress` | gauge | `method` |

`route` is the **route template** (`/v1/datasets/{id}`,
`/api/datasets/[datasetId]`), never the raw path. A request that matches no
route is `route="unmatched"`. Probes (`/health-check`) are excluded, as the
access log already excludes them.

Duration buckets, in seconds, for all services:
`0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30`.
Size buckets, in bytes: powers of 4 from 256 B to 64 MiB.

### Shared metrics — every service that calls another

| Metric | Type | Labels |
|---|---|---|
| `datamap_external_request_duration_seconds` | histogram | `service`, `operation`, `outcome` |

`service` is the callee (`gatekeeper`, `datacite`, `minio`, `postgres`).
`operation` is a fixed name chosen in code (`doi.create`, `object.put`,
`GET /v1/datasets/{id}`), never a URL with ids in it. `outcome` is `success`,
`client_error`, `server_error`, `timeout` or `error`. A count is the histogram's
`_count`; there is no separate counter.

### Labels that are forbidden

`user_id`, `dataset_id`, `file_id`, `request_id`, raw paths, free-text search
queries. Each would be one series per value. Every one of them is already in the
JSON access logs, which is where per-user and per-dataset questions are answered
(see *Metrics or logs*).

`tenancy` is allowed on business counters only: tenancies are a small,
admin-created set. A request may carry several; the counter uses the dataset's
own tenancy, which is exactly one.

### Process metrics

Each service exposes its runtime's default collectors (`process_*`,
`python_gc_*`, Node's `nodejs_*` event-loop and heap metrics). Nothing to write.

## Per service

### gatekeeper

Served on port 9095, as today (`app/metrics_server.py`).

**HTTP.** The middleware in `app/setup.py` reads the route template from
`request.scope["route"]` after the handler ran, replacing the UUID regex in
`app/metrics.py`, which leaves tenancy names, version names, client keys and
provider references in the label. Adds a `client` label — the name of the API
client (webapp, archivist, zipper), a handful of values — so BFF traffic and
internal traffic separate on the dashboard.

**Integrations**, all as `datamap_external_request_duration_seconds`:
- `service="datacite"`: every method of `app/gateway/doi/doi.py`, with the
  outcome taken from the status DataCite answered with.
- `service="minio"`: every method of the object-storage gateway. A missing
  object is `client_error`, not a failure.
- `service="postgres"`: SQLAlchemy's `before/after_cursor_execute` and
  `handle_error` events, with `operation` the statement type (select, insert,
  update, delete, other).
- `datamap_db_pool_connections{state}` (`checked_out`, `idle`, `overflow`) and
  `datamap_db_pool_size`, read from the pool at scrape time.

There is no `dependency_up` gauge. The dependency health check runs only when
someone calls it, so the gauge would hold whatever the last caller saw.
`pg_up`, MinIO's `up` and the outcomes above say the same thing continuously.

**Auth.** `datamap_auth_failures_total{kind, reason}`, counted in the three
interceptors, with `kind` one of `authn`, `authz`, `tus`. `reason` is one of the
codes the code already raises; anything else is `other`.

**Business events**, counted in the service where they happen:

| Metric | Labels |
|---|---|
| `datamap_dataset_events_total` | `action`: created, updated, deleted, enabled, version_created, version_published, version_enabled, version_deleted |
| `datamap_download_urls_issued_total` | `tenancy`, `format` |
| `datamap_download_bytes_issued_total` | `tenancy` |
| `datamap_uploads_completed_total` | `tenancy`, `format` |
| `datamap_upload_bytes_total` | `tenancy` |
| `datamap_doi_operations_total` | `operation` (create, state.findable, …, delete), `mode`, `outcome` |
| `datamap_search_total` | `has_text`, `has_filters`, `empty` |

`format` is the file extension, from a fixed list of scientific and office
formats; anything else is `other`. The file name comes from whoever uploads.

Dataset views are not a separate counter: they are
`datamap_http_requests_total{route="/api/v1/datasets/{id}", method="GET"}`.

`download_urls_issued` counts presigned URLs, not completed downloads: the
bytes go from MinIO to the browser through nginx. Completed downloads come from
the nginx access log (see *Metrics or logs*).

**Business state**, computed by a custom collector (`app/platform_state.py`)
at scrape time, cached for 60 seconds so a 15-second scrape costs a few
GROUP BYs a minute. A failed read keeps the last numbers rather than failing
the scrape:

| Metric | Labels |
|---|---|
| `datamap_datasets` (enabled) | `tenancy`, `design_state`, `visibility` |
| `datamap_data_files` | — |
| `datamap_stored_bytes` | — |
| `datamap_users` | `enabled` |
| `datamap_dois` | `state` |

Both instances report the same values; dashboards take `max()` across
instances, never `sum()`.

### datamap-webapp

**Server.** prom-client in the standalone Next.js process.

- The HTTP contract, recorded in `lib/requestLogging.ts`, which already
  measures every API route. `route` is rebuilt from `req.query`'s dynamic keys.
- Calls to the gatekeeper, through an axios interceptor in `lib/rpc.ts`:
  `datamap_external_request_duration_seconds{service="gatekeeper"}`.
- `datamap_webapp_logins_total{provider, outcome}` from NextAuth's events.
- Served at `/api/metrics`. nginx forwards everything on port 3000 to the
  internet, so the route answers only requests carrying
  `Authorization: Bearer $METRICS_TOKEN`. Prometheus reads the same token from
  the env file; it is a static shared secret, not one that expires.

**Browser.** Nothing the browser experiences reaches any log today. A beacon
posts batches to `POST /api/telemetry`:

| Metric | Labels |
|---|---|
| `datamap_web_vitals_seconds` (histogram) | `metric` (LCP, INP, FCP, TTFB), `page` |
| `datamap_web_vitals_cls` (histogram, unitless) | `page` |
| `datamap_web_page_views_total` | `page` |
| `datamap_web_errors_total` | `page` |
| `datamap_web_ui_events_total` | `event`, `page` |

`page` is the Next.js page template (`/datasets/[datasetId]`), from the router,
never `asPath`. `event` is drawn from a fixed list — `search`, `filter_applied`,
`download_clicked`, `upload_started`, `upload_completed`, `upload_failed`,
`notebook_opened`, `tenancy_switched`, `dataset_created`, `version_created` —
and anything else is dropped. The endpoint is public and unauthenticated by
nature, so the allowlist is what keeps a stranger from minting series. Each
accepted batch is also written as one JSON log line, so the same events are
queryable per user in Loki.

Grafana Faro was considered: richer (sessions, stack traces), but it needs the
Alloy receiver published through nginx, adds a component on a CPU-saturated
host, and puts browser data only in Loki. The beacon reuses the webapp's own
origin and feeds both.

### archivist

No HTTP server today. `prometheus_client.start_http_server` on port 9096, in a
thread, on the docker network only.

| Metric | Labels |
|---|---|
| `datamap_archivist_job_runs_total` | `outcome` |
| `datamap_archivist_job_duration_seconds` | — |
| `datamap_archivist_last_success_timestamp_seconds` | — |
| `datamap_archivist_datasets_processed_total` | `outcome` |
| `datamap_archivist_files_moved_total` | `outcome` |
| `datamap_archivist_bytes_moved_total` | — |
| `datamap_archivist_file_copy_duration_seconds` | — |
| `datamap_external_request_duration_seconds` | calls to the gatekeeper |

### zipper

Runs `uvicorn --workers 3`, so prometheus_client needs multiprocess mode
(`PROMETHEUS_MULTIPROC_DIR`, cleared at start). Port 9093 is published, so
metrics go on a separate internal port, 9095, like the gatekeeper.

HTTP contract, plus:

| Metric | Labels |
|---|---|
| `datamap_zip_jobs_total` | `outcome` |
| `datamap_zip_jobs_in_progress` | — |
| `datamap_zip_duration_seconds` | — |
| `datamap_zip_input_bytes_total`, `datamap_zip_output_bytes_total` | — |

**Prerequisite:** the zipper reports `SUCCESS` to the gatekeeper from a
`finally` block, whether zipping succeeded or not. That is fixed first, in its
own change; a success metric on top of it would repeat the lie.

## Infrastructure

Added to `docker-compose-observability.yaml`, all on
`gatekeeper_gatekeeper-network`, none published:

| Component | Scrape | Notes |
|---|---|---|
| node-exporter | 30s | host `/proc`, `/sys`, `/` read-only. Host-wide by nature: panels say *shared host* |
| cAdvisor v0.55 | 30s | `--docker_only`, housekeeping 30s, series kept only for `name=~"datamap_.*"`. Older versions cannot read Docker's containerd image store |
| postgres-exporter | 30s | logs in with the application's own credentials, from the same env file, so a rotation reaches it with nothing else to change |
| nginx-prometheus-exporter | 30s | reads `stub_status` from the host nginx (runbook) |
| MinIO | 30s | native `/minio/v2/metrics/cluster`, `MINIO_PROMETHEUS_AUTH_TYPE=public` |
| tusd | 15s | native `/metrics`, already on by default in v2.4 |

**MinIO without a token.** A bearer token from `mc admin prometheus generate`
is signed with the root credentials and breaks when they rotate
(`docs/runbooks/credential-rotation.md`); someone would have to remember to
regenerate it. Prometheus reaches MinIO on the docker network, so `public` is
used instead. The metrics carry bucket sizes and request counts, not object
names or data. Port 9000 is published on the host, so whether the endpoint is
reachable from outside depends on the host firewall; the runbook has the check.

**Cost.** CPU is the host's constraint. cAdvisor is the expensive exporter,
hence `--docker_only`, the 30s housekeeping, and dropping every non-DataMap
series at scrape time. node-exporter and postgres-exporter are negligible.

## Metrics or logs

Loki already holds every service's JSON logs, and a Loki metric query turns
them into a panel with no code change. The split:

| Question | Source | Why |
|---|---|---|
| rates, latencies, error ratios, anything alerted on | Prometheus | cheap to query over weeks; histograms give real percentiles |
| distinct users per day, per-dataset and per-user activity | Loki (`count by (user_id)` over access logs) | unbounded label values; fine in a log query, fatal in a metric |
| completed downloads, page requests, bytes served | Loki, nginx access log | nginx is the only component that sees them |
| the webapp before its metrics ship | Loki, `datamap_frontend` access log | already there today |
| recent errors with context | Loki | the log line is the context |

This is why the webapp dashboard has useful panels on day one: its access log
is already in Loki.

For nginx, production runs on the host (`docs/runbooks/two-instances.md`), not
in a container, so Alloy does not see its logs. The runbook adds a JSON access
log and mounts `/var/log/nginx` read-only into Alloy.

## Dashboards

JSON files under `infrastructure/grafana/dashboards/<folder>/`, provisioned by
`infrastructure/grafana/provisioning/dashboards/`, one Grafana folder per
directory. `allowUiUpdates: false`: a change made in the UI would be lost on the
next start, so the repository is the only place a dashboard changes. To edit,
change it in the UI, export the JSON, and commit it.

The datasources get fixed uids, `prometheus` and `loki`, so the JSON refers to
them by a stable name.

| Folder | Dashboard | Content |
|---|---|---|
| Infra | Host | CPU, load, memory, disk usage, IO and time-to-full, network |
| Infra | Containers | per `datamap_*` container: CPU, memory, network, restarts |
| Infra | Postgres | connections, transactions, cache hit, locks, size, deadlocks |
| Infra | Storage | MinIO capacity and S3 traffic; tusd uploads and bytes |
| Infra | Nginx | connections and request rate; status, latency and bytes from logs |
| HTTP | Requests | filter by service, instance, method, route, status, client: rate, errors, p50/p95/p99, sizes, in-flight, slowest routes; logs by request id |
| Integrations | Dependencies | DataCite, MinIO, Postgres, gatekeeper-from-webapp: latency, errors, pool |
| Business | Platform usage | datasets, versions, downloads, uploads, searches, views, DOIs, logins, distinct users; download and upload funnels; per tenancy |
| Webapp | Experience | Web Vitals per page, JS errors, page views, UI events, BFF and gatekeeper latency, Node runtime |
| Pipelines | Upload to archive | TUS hooks, collocation backlog, archivist runs, snapshots, zips |

A unit test (`app/grafana_dashboards_test.py`) loads every file and checks that
it is valid JSON, has a unique uid, uses only the `prometheus` and `loki`
datasource uids, and that every `datamap_*` metric it queries is one the code
declares. A dashboard querying a renamed metric draws an empty panel that looks
like a quiet system; the test is what prevents that.

## Alerts

Added to `infrastructure/prometheus/alerts.yml`, each with a promtool test:

| Alert | Fires when |
|---|---|
| `HostDiskFillingUp` | a filesystem is over 85% or predicted full within 24h |
| `HostMemoryLow` | available memory under 10% for 15 minutes |
| `ContainerRestarting` | a `datamap_*` container restarted more than twice in an hour |
| `PostgresConnectionsHigh` | over 80% of `max_connections` for 10 minutes |
| `LatencyHigh` | p95 of a service over 2s for 15 minutes |
| `DataCiteFailing` | any DataCite call failed in 15 minutes |
| `ArchivistStalled` | no successful archivist run in an hour |
| `ZipsFailing` | any zip failed in 30 minutes |

## Rollout

Each phase is a separate change in its own repository.

| Phase | Repository | Change |
|---|---|---|
| 0 | gatekeeper | datasource uids, dashboard provisioning, dashboard test, this RFC |
| 1 | gatekeeper | HTTP contract; HTTP dashboard |
| 2 | gatekeeper | exporters; Host, Containers, Postgres, Storage, Nginx dashboards; alerts; runbook |
| 3 | datamap-webapp | server metrics, `/api/metrics`, telemetry beacon; Webapp dashboard |
| 4 | gatekeeper | integrations, auth, business metrics; Integrations and Business dashboards |
| 5 | archivist | metrics; scrape; Pipelines dashboard |
| 6 | zipper | SUCCESS fix; multiprocess metrics; scrape |

The label rename from `path` to `route` in phase 1 breaks the continuity of
`datamap_http_requests_total` history; `ServerErrorsElevated` sums over the
label, so it is unaffected.

## Open questions

- Where alerts are delivered (unchanged from the runbook).
- Whether port 9000 and 9001 should bind `127.0.0.1` only, since nginx is the
  only intended way in. Not required by this RFC; worth doing on its own.
