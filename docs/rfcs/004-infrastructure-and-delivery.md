# RFC 004: Infrastructure and Delivery

| Status | Proposed |
|--------|----------|
| Author | Caio Maia |
| Created | 2026-09-09 |
| Updated | 2026-09-09 |

Covers all services (`gatekeeper`, `datamap-webapp`, `archivist`, `zipper`), not
just the one this directory lives in.

## Summary

DataMap runs in production from containers started by hand, with no CI, no
metrics, unstructured logs that are lost on every deploy, secrets in tracked
files, and migrations that never run. This RFC proposes the smallest set of
changes that makes the system operable by more than one person, and deliberately
argues **against** adopting Kubernetes to get there.

The ordering principle: nothing here is worth doing before a merge to `main` is
gated by tests, because that is the failure that let every other problem persist.

## Motivation

Evidence gathered on 2026-09-09, from production and from the test suites.

**Nothing gates a merge.** Neither repository has CI. The integration suite sat
at 18 failures for months; among them was a tenancy filter that made every file
upload fail. Production logs show 9 `post-finish` hooks over 90 days and 9
failures — three uploads attempted, three lost. Nobody was told.

**Logs are unusable and unsafe.** `setup_logging()` calls `basicConfig()` and
then attaches a second handler with a different formatter to a subset of loggers.
Two formats share one stream, lines duplicate through propagation, and loggers
outside the list fall back to the default. `TusService` logs the whole hook
payload, so signed upload tokens appear verbatim in the log. Logs live only in
the container and disappear when it is replaced.

**Migrations are not exercised.** They do run in production, by hand from the
host virtualenv with a second environment file that points at `0.0.0.0` instead
of the container. They do not run anywhere else: `.dockerignore` excludes
`alembic.ini` and `migrations/`, so the `docker exec ... alembic upgrade head`
in `integration-test-full` always fails, hidden behind
`|| echo "Migration may have failed"`. Every other schema comes from
`create_database()`, which is `Base.metadata.create_all()`, so **no test has
ever executed a migration** and the two could drift apart unnoticed. Embargo
(RFC 003) adds several.

**One instance, no health signal.** A single `datamap_gatekeeper` container, up
3 months. Only MinIO declares a healthcheck. "I can't upload" has had at least
two distinct causes — the tenancy filter and MinIO being down — and no way for
anyone to tell them apart without a shell on the host.

**Operations require SSH.** Every deploy, every log read, every restart.

### Goals

- A merge to `main` cannot land failing tests.
- A deploy is a consequence of a merge, not an act of typing.
- A log line from last month is findable, and contains no credentials.
- A restart of one process does not interrupt service.
- Someone new can tell whether the system is healthy without a shell.

### Non-goals

- Multi-node orchestration, autoscaling, service mesh.
- Zero-downtime guarantees stronger than "a rolling restart is invisible".
- Replacing Docker Compose.

## Decisions

### 1. Structured logging comes before log indexing

Format first: an index over duplicated, half-formatted lines that contain
secrets is worse than no index, because it makes the secrets searchable.

- **One handler, JSON output.** Configure the root logger only, and let
  propagation do its job. Drop the per-module handler loop, which is what causes
  duplicate lines.
- **`python-json-logger`** as the formatter. Fields: `timestamp`, `level`,
  `logger`, `message`, `request_id`, plus whatever the call site passes as
  `extra`.
- **Redaction is mandatory.** A logging filter drops or masks `X-User-Token`,
  `Authorization`, `X-Api-Secret`, and any key matching `token|secret|password`.
  `TusService` stops logging whole payloads and logs named fields instead.
- **Correlation id.** Middleware assigns a `request_id` per request and puts it
  in a `ContextVar` the formatter reads, so one upload can be followed across
  lines.
- **Uvicorn access logs** go through the same formatter rather than their own.

Log the fields worth querying — `dataset_id`, `user_id`, `hook_type`,
`status_code` — as fields, not interpolated into the message. This is what turns
"grep the logs" into "count failures by hook type", which is exactly the query
that would have surfaced the upload bug.

Only then does indexing pay off: **Loki + Grafana**, two containers in the same
Compose file, with Promtail reading the Docker socket. Retention on disk, not in
the container. Grafana is reused for metrics (§7), so this is one dependency, not
two.

Before that lands, two cheap measures, which this RFC originally conflated into
one. They address different failures and neither substitutes for the other.

**Rotation bounds the disk.** A `logging` block in Compose with `max-size` and
`max-file`, applied to every service through a YAML anchor. No container had any
limit, and `datamap_archivist` — the one service the deploy never replaces — had
accumulated **5.6 GB since 2025-12-18**, on a host shared with three unrelated
projects. The file is large enough that `docker logs --since 10m` takes minutes,
because the json-file driver has no index and scans the whole thing.

**Archiving makes a log survive a deploy.** Rotation does not do this: `docker
compose down` deletes the container together with its log file, so every deploy
erases the history of exactly the system it is changing. Every container the
deploy touches was proved empty of anything older than today. The deploy job now
writes `docker logs -t` to a gzipped, timestamped file under
`/home/datamap/logs` before replacing anything, and prunes past 30 days. Six
lines of workflow, no new containers, and it is what makes the goal "a log line
from last month is findable" true today rather than after §1 and Loki.

### 2. CI on GitHub-hosted runners, deploy on a self-hosted one

GitHub Actions is free at this scale: unlimited minutes on public repositories,
2,000 minutes a month on a free organisation. The full suite runs in about four
minutes.

**Two workflows, two trust levels.**

`test.yml` — on `pull_request`, `runs-on: ubuntu-latest`:

- `ruff check` and `ruff format --check`
- `pytest app`
- the integration suite, with Compose services
- `npx tsc --noEmit` and `npx jest` for the webapp

`deploy.yml` — on `push` to `main`, `runs-on: self-hosted`:

- build the image
- **run migrations, and stop if they fail** (§3)
- roll the instances one at a time (§4)
- verify health before declaring success

A self-hosted runner registered on the production host polls GitHub outbound. No
inbound SSH, no deploy key stored at GitHub, and it answers the "stop having to
SSH in" goal directly.

> **Rule that must not be broken:** pull request code never runs on the
> self-hosted runner. A PR from a fork executing on the production host is a
> full compromise. Tests run on `ubuntu-latest`; only `push` to `main` reaches
> the self-hosted runner.

Branch protection marks the test workflow as required. That single setting is
what converts "we have tests" into "tests protect us", and it is the one piece of
this RFC that is configured in the GitHub UI rather than in a file.

#### Registering the runner

**One runner, registered to the organisation, serving both repositories.** A
runner registered to a single repository would have to be installed twice on the
same host for no benefit.

Go to **github.com/organizations/ardc-brazil/settings/actions/runners → New
runner**, choose Linux x64, and use the download and configure commands it
prints. They carry the current runner version and a token that expires in an
hour and works once. Do not copy a version number out of this document: it goes
stale, and the installer refuses a release that is too old.

Run them on the production host as the `datamap` user — the Linux account that
owns `/home/datamap` and belongs to the docker group, the same one the manual
deploy runs as.

Change three things in what GitHub gives you:

1. Add `--labels production` to `./config.sh`, which is what `runs-on` matches.
2. Keep the URL exactly as shown, `https://github.com/ardc-brazil`, with no
   repository name. An organisation token and a repository URL do not go
   together.
3. Instead of `./run.sh`, install it as a service so it survives a reboot:

```bash
sudo ./svc.sh install datamap   # datamap is the user to run as, not a service name
sudo ./svc.sh start
```

Two things that went wrong the first time, both harmless once recognised:

- `error: exists /etc/systemd/system/actions.runner.*.service` means the install
  already succeeded and is being run a second time. The service is there and
  enabled; it only needs `sudo ./svc.sh start`.
- `status=203/EXEC` means systemd could not execute `ExecStart`. The unit points
  at `<runner root>/runsvc.sh`, which was only present under `bin/`:
  `cp bin/runsvc.sh runsvc.sh` and start again. The script uses relative paths
  and relies on the `WorkingDirectory` systemd sets, so it works from the root.

Then allow both repositories to reach it: **Settings → Actions → Runner groups →
Default**, set repository access to `gatekeeper` and `datamap-webapp`. Without
this an organisation runner is visible to no repository and the deploy job waits
forever for a runner that never picks it up.

`runs-on: [self-hosted, production]` matches on the `production` label given
above, so both workflows find it with no further configuration.

> **Both repositories are public.** Anyone can open a pull request, and a
> workflow running fork code on this runner would execute a stranger's code on
> the production host. What prevents it is that the deploy workflows trigger only
> on `push` to `main`, never on `pull_request` — keep it that way, and never move
> a `pull_request` trigger onto a self-hosted runner.
>
> GitHub's own guard is secondary here and weaker than it sounds: the approval
> policy is `first_time_contributors`, so someone whose pull request has been
> merged once needs no approval afterwards. Raising it to all external
> contributors, under **Settings → Actions → General**, costs nothing and is
> worth doing.

The workflows read the environment directory from a repository variable,
defaulting to `/home/datamap/environment`. Set `ENVIRONMENT_DIR` under
Settings → Secrets and variables → Actions if it ever moves.

The runner needs `make`, `curl` and Docker, all of which the host already has —
it is what the manual deploy uses.

### 3. Migrations run, and run before the switch

**The application runs them at startup.** `alembic.ini` and `migrations/` are no
longer excluded from the image, and `main.py` calls `alembic upgrade head` in
place of `Base.metadata.create_all()`. A failed migration means the container
never becomes healthy, which the deploy job waits for and reports.

This removes three moving parts rather than automating them: the host
virtualenv, the second environment file pointing at `0.0.0.0`, and the manual
step itself. `migrations/env.py` already resolves the connection from the same
settings the app uses, so inside the container it reaches the database by its
service name with no extra configuration.

It also closes the gap: because the schema now comes from the migrations, the
integration suite executes all 31 of them against an empty database on every
run. Verified — the migration-built schema and the model metadata agree today,
which nothing had ever confirmed.

The one thing to revisit under §4: with two instances, both would run
`upgrade head` at once. Alembic takes a lock per migration, so the race is
survivable, but the honest fix is a Postgres advisory lock around the call, or
moving the step back into the deploy job once there is more than one replica.

### 4. Two instances behind nginx, same hostname

Yes, this works with the same DNS name, and no DNS change is involved. nginx
already terminates every request; it gains an upstream with two members:

```nginx
upstream gatekeeper {
    server datamap_gatekeeper_a:9092 max_fails=2 fail_timeout=10s;
    server datamap_gatekeeper_b:9092 max_fails=2 fail_timeout=10s;
}

location /api/v1 {
    proxy_pass http://gatekeeper;
}
```

Two named services in Compose rather than `--scale`, because the services use
fixed `container_name`. Deploy replaces `_a`, waits for its healthcheck, then
replaces `_b`. Requests in flight land on the other instance.

**What this buys and what it does not.** It removes the process as a single point
of failure: a crash, an OOM, or a rolling deploy stops being an outage. It does
**not** remove the machine as a single point of failure. Two instances on one
host is redundancy against software, not against hardware. Say so plainly rather
than letting the diagram imply more.

Prerequisite: the app must tolerate two instances. Casbin reloads its policy
every 5 seconds in each process, which is fine. The Archivist must **not** be
duplicated — it is a scheduler, and two of them would process the same files
twice.

### 5. Health checks everywhere, and a status page

Every service declares a Compose `healthcheck`: Postgres via `pg_isready`, MinIO
on `/minio/health/live`, TUSd on its port, Gatekeeper on
`/api/v1/health-check/`. `depends_on` uses `condition: service_healthy` so a
deploy does not start the API against a database that is not up.

The API's own health endpoint is extended to report its dependencies —
database and object storage — as a document, and the administrative status page
in the backlog renders it. This is what lets the curation team distinguish "the
system is down" from "I hit a bug", which they cannot do today.

### 6. Secrets encrypted in the repository, with SOPS and age

Environment files are tracked today and carry real values. The goal is secrets
that live in git as code, without a paid service.

**SOPS + age**: values are encrypted in the file, keys are not, so a diff still
shows which variable changed without revealing it. The private key lives on the
production host and in the runner's environment. `sops -d` at deploy time
produces the `.env` the containers read.

Migration path: rotate everything currently committed — treat it as leaked,
because it is — then commit the encrypted files and delete the plaintext ones.

### 7. Prometheus metrics, including custom ones from the code

`prometheus-fastapi-instrumentator` gives request rate, latency and status codes
per route with a couple of lines at startup, and exposes `/metrics`.

Custom metrics are the point, and they are plain `prometheus_client` objects
declared next to the code that owns them:

```python
from prometheus_client import Counter, Histogram

UPLOAD_HOOKS = Counter(
    "datamap_tus_hook_total",
    "TUS hooks received",
    ["hook_type", "outcome"],          # outcome: accepted | rejected | error
)

EMBARGO_EVENTS = Counter(
    "datamap_embargo_events_total",
    "Embargo decisions recorded",
    ["event_type"],                    # created | extended | ended_early | ...
)

SNAPSHOT_PUBLISH = Histogram(
    "datamap_snapshot_publish_seconds",
    "Time spent publishing a dataset snapshot",
)
```

`UPLOAD_HOOKS.labels(hook_type="post-finish", outcome="error").inc()` on the
failure path would have made this year's upload bug a visible line on a chart
instead of a silence nobody was measuring. Alerting on it is the difference
between finding a production failure in an afternoon and finding it in 90 days.

With two instances, each process keeps its own counters and Prometheus scrapes
both as separate targets. That is correct; sum across instances in the query.

Grafana is the same one that serves logs (§1).

### 8. Not Kubernetes

Kubernetes solves scheduling across nodes, declarative rollouts, and
self-healing. On one machine, with a handful of services and one or two
developers, only the last two apply, and both are available far more cheaply:
Compose healthchecks with `restart: unless-stopped` cover self-healing, and the
deploy job covers rollout.

What it would cost: a control plane to keep alive and upgrade, manifests for
every service, an ingress controller replacing an nginx config that already
works, secret and volume abstractions on top of ones that already work, and a
body of knowledge that every future contributor now needs before they can deploy.
The stated goal is to raise maintainability *without* complicating; adopting an
orchestrator to run one replica per service on one host moves in the opposite
direction.

Revisit when one of these becomes true: a second machine, more than a handful of
services, or a team large enough that "who deploys" needs a policy. **k3s** is
then the small step up, and nothing in this RFC blocks it — Compose services with
healthchecks translate almost mechanically.

## Sequencing

Ordered by what unblocks what, not by size.

| # | Item | Why here |
|---|------|----------|
| 1 | ~~`test.yml` + branch protection~~ | **Done, 2026-09-10.** Required on `main` in both repositories, with review from a code owner |
| 2 | ~~`alembic.ini` in the image; migrations exercised~~ | **Done, 2026-09-11.** The application runs `upgrade head` at startup; the suite executes all 31 migrations on every run |
| 3 | ~~`deploy.yml` on a self-hosted runner~~ | **Done, 2026-09-11.** Merging `main` deploys; the first one moved production off a January branch |
| 4 | ~~Bounded and archived logs~~ | **Done, 2026-09-11.** Rotation on every service in all four repositories, and the deploy archives a container's log before replacing it |
| 5 | ~~Structured JSON logs, redaction, request id~~ | **Done, 2026-09-11**, in the gatekeeper and the archivist. Awaiting review |
| 6 | ~~Health checks + dependency report~~ | **Done, 2026-09-11.** Awaiting review. The status page itself stays in the backlog |
| 7 | Two instances behind nginx | Needs health checks to roll safely |
| 8 | SOPS secrets | Independent, but needs a rotation window |
| 9 | Prometheus + custom metrics | Needs somewhere to look, i.e. Grafana from §1 |
| 10 | Loki + Grafana | Last, and only worth it once logs are structured |

Items 1 to 3 are the ones that change how the team works; the rest are
improvements to a system that already defends itself.

### Where this stands, 2026-09-11

**In production.** Tests gate every merge; merging `main` deploys; the schema is
applied by the application at startup. The first automated deploy moved
production off a January branch and carried the upload fix with it — a test
upload landed correctly, file record and all.

**Verified after that deploy**: the corrected code is running, the schema is at
head, every container is up, the API answers, and — once logging was repaired
separately — a `post-finish` hook returning **200 in the logs**, with the file
record on an Archivist-organised path rather than `staged/`. The baseline this
replaces is 9 `post-finish` hooks and 9 × 500 over 90 days; it is recorded in
`docs/runbooks/post-deploy-verification.md`, which now closes end to end.

**Item 4 is in.** It turned out to be two changes rather than the one this RFC
described — see §1: rotation for the disk, archiving for the history. Both take
effect at the next deploy, and the first archived log will be whatever the
running containers have accumulated by then.

**Item 2 now covers the Archivist**, which this RFC had quietly left out: it had
no gate, no deploy, and a `make docker-deployment` typed over SSH. The image
build is its only gate, because the repository has no tests at all —
`tests/unit` and `tests/integration` are empty directories. That is a low bar,
and naming it is the point: the service that moves every uploaded file into
place is the one with no test covering it. The deploy also waits for
`Scheduler started` and then confirms the container is still running a minute
later, so a crash loop cannot report success.

The Zipper is deliberately excluded. It has no container, no directory and no
environment file on the production host: it was never finished, and automating
the delivery of something that does not run would be theatre.

**Item 5 is written and waiting for review.** One handler at the root, JSON,
redaction by filter rather than by remembering, and a `request_id` carried in a
`ContextVar`. One upload now reads as three correlated lines:

```json
{"message": "tus hook received", "hook_type": "post-finish", "dataset_id": "923b9884…", "logger": "controller:tus", "request_id": "110a59d6…"}
{"message": "tus hook failed",   "hook_type": "post-finish", "dataset_id": "923b9884…", "error": "Dataset not found: 923b9884…", "request_id": "110a59d6…"}
{"message": "request", "method": "POST", "path": "/api/v1/tus/hooks", "status_code": 500, "duration_ms": 5.4, "request_id": "110a59d6…"}
```

`hook_type` and `status_code` are fields, which is what turns grepping into
counting — the query that exposed the upload bug after ninety days.

One correction to what this RFC claimed: **no credential is in the production
log today.** `LOG_LEVEL` is `INFO`, so the `logger.debug(payload)` line never
fired, and a search of the current and archived logs finds nothing. The exposure
was on the hook's failure path, which logged the payload whole and was taken
nine times this year; those logs are gone. The path is removed rather than
depending on the level staying where it is.

Writing it found a defect of the same family it was meant to prevent. A log
field named `filename` collides with `LogRecord.filename`, and `logging` raises
rather than overwrite it — so **every TUS hook answered 500**, on the endpoint
whose bug had just been fixed, in the release meant to make it observable. No
unit test would have seen it. The integration suite did, on the first run.

The archivist got the same treatment, plus the thing that actually made its
5.6 GB: an idle run is now `DEBUG`, and a dataset failing the same way every
minute is reported once with the repeats counted, instead of once a minute
forever. That repository also got its first tests; it had none.

**Item 6 followed it**, because the same session kept needing it. There is now
an authenticated `GET /v1/health-check/dependencies` reporting the database and
the object storage with a status and a latency, which is the answer to "is it
down or did I hit a bug" that the curation team could not get without a shell.
The shallow `/health-check/` stays public and unchanged, because the deploy
waits on it and a degraded object storage must not block a deploy that is
fixing something else.

The compose healthchecks that came with it are worth recording for how they
failed. The one written for the gatekeeper used `http://localhost:9092`, which
is refused inside the container: `localhost` resolves to `::1` first and uvicorn
binds IPv4 only, so it would have reported unhealthy forever. And the postgres
healthcheck in the integration stack had been failing since it was written —
`${POSTGRES_USER}` is interpolated by Compose on the host, where the value only
exists under `make`. **A healthcheck that never passes is worse than no
healthcheck**, because it reports a broken system as fine, and neither of these
was visible in `docker compose config`. CI now fails unless every container
reaches healthy.

The status page for the curation team stays in the backlog; the endpoint it
would render exists now.

The Archivist gives item 5 a second target, and an open question. It runs its
collocation job **every minute**, not the 15 the documentation claims, and emits
eleven lines per run with nothing to do — three of them an eighty-character
`====` banner. Log the idle run at `DEBUG` and keep `INFO` for a run that
actually moved a file.

That is not what made 5.6 GB, though. Measured live, the steady state is 11
lines and 1,404 bytes a minute — 2 MB a day, against an average of 21 MB a day
over the life of the container. A full pass over the file found the rest:

```
34,033,376 lines    5,617,352,638 bytes
  ERROR     9,376,873 lines   2.56 GB
  INFO     15,227,223 lines   2.22 GB
```

**9.4 million errors**, nearly all of them one line: `Unexpected error
processing dataset 82e2913e-…: Server error '500 Internal Server Error' for url
'http://gatekeeper…'`. That is this year's upload bug seen from the other side —
the Archivist retrying a collocation the Gatekeeper could not answer, with no
backoff and nothing watching. The last one is timestamped 15:58 on 2026-09-11;
since then, none.

The same `docker inspect` that dates the log reports **`RestartCount` 169**. The
container was created on 2025-12-18 and last started on 2026-08-07, so what
looked like an uptime of five weeks is the latest of many restarts that
`restart: always` papered over. Nobody was told about those either.

So the 5.6 GB was a symptom, and the log that would have exposed the bug in an
afternoon was the log nobody could read. It is also the argument for §7: a
counter on that failure path is a line on a chart, where 9.4 million identical
log lines are just weather.

Two things follow for item 5. A retry loop with no backoff is a defect of its
own, independent of formatting. And a service that can emit 186 errors a minute
needs rate limiting or aggregation in the logging configuration, or a 200 MB
ceiling buys twenty minutes of history instead of a hundred days.

**Loose ends**, none blocking: `B904` is ignored in `ruff.toml` (19 call sites);
validation answers 400 where FastAPI's own answers 422; the Casbin auto-reload
failed to pick up a seeded policy once right after startup and could not be
reproduced afterwards; `actions/checkout@v4` and `actions/setup-python@v5` warn
about the Node 20 deprecation; three datasets may hold a published version
missing its files, with the query to check them in the runbook; and the
`archivist` repository is private, so branch protection is unavailable on the
free plan and its CI gates nothing until it is made public.

### What the first three taught us

**Nothing is verified until it runs where it will run.** The first CI run failed
three times over, each for a real reason rather than noise: ruff was installed
unpinned and linted with a version four releases ahead of the one in
`requirements.txt`; the snapshot tests needed a `datamap` bucket that exists only
because a developer's storage directory accumulated one; and the client tests
raced Casbin's five-second policy reload, which a human running the same commands
never notices because they type slowly.

**A local reproduction can lie.** The claim that the deploy job had been
validated locally was wrong: Docker reuses an existing named volume and ignores a
changed `device`, so a run that appeared to use an empty directory was still
reading the developer's storage, bucket included.

**Item 5 stopped being optional.** Running migrations in-process made the
application silent — `fileConfig()` disables every logger it does not name, so
three lines came out of a deploy and the TUS hook became unobservable on the very
day its bug was fixed. The immediate cause is repaired, but a logging setup that
one library call can disable is not a logging setup. Structured configuration
owned in one place is the fix, and it is next.

## Open questions

- **Repository visibility.** Public repositories get unlimited Actions minutes;
  a private organisation gets 2,000 a month. Enough either way at current volume,
  but worth confirming before relying on it.
- **Who holds the age private key**, and where the recovery copy lives. A secret
  store with one holder is an availability risk of its own.
- **Log retention window.** Disk on the production host is the constraint;
  30 days of structured logs is a reasonable starting point to measure.
- **Whether the Archivist should move off the production host.** It is the one
  component that must not be duplicated, which makes it awkward under any
  rollout scheme.
