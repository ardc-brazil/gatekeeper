# Metrics, logs and alerts

Prometheus scrapes the gatekeeper, Loki holds the logs, Alloy ships them, and
Grafana reads both. None of it is part of the automated deploy: they hold their
own data and do not need replacing when the application changes.

## Starting it

```bash
cd ~/gatekeeper
make ENV_FILE_PATH=../environment/gatekeeper.prod.env observability-run
```

Grafana listens on `127.0.0.1:3001`, not on a public interface. Reach it over an
SSH tunnel:

```bash
ssh -L 3001:127.0.0.1:3001 datamap-prod
```

Then <http://localhost:3001>.

**Set `GF_SECURITY_ADMIN_PASSWORD` in `gatekeeper.prod.env` before the first
start.** Without it Grafana takes `admin`/`admin` and asks for a new password at
first login, which is fine for one operator and not fine for a shared host.

Prometheus is not published at all. It is reachable only from Grafana, over the
docker network.

## Where the metrics come from

The gatekeeper serves them on **port 9095**, which Compose does not publish.
A Prometheus scrape config cannot send `X-Api-Key` and `X-Api-Secret`, so the
docker network is the boundary rather than an authorisation check. The port is
not proxied by nginx and not reachable from outside the host.

```bash
# from the host, as Prometheus does
docker exec datamap_gatekeeper python3 -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:9095/metrics').read().decode()[:400])"
```

## The alerts

| Alert | Fires when | Why it exists |
|---|---|---|
| `UploadHooksFailing` | any TUS hook answers 5xx in ten minutes | this failed every time for ninety days in 2026 and lost three uploads |
| `SnapshotPublicationFailing` | a snapshot fails to publish | a findable DOI with no page behind it |
| `CollocationBacklogNotDraining` | datasets pending for two hours | the Archivist retries forever and never gives up |
| `GatekeeperDown` | no successful scrape for five minutes | |
| `ServerErrorsElevated` | over 5% of requests are 5xx for ten minutes | |

**Nothing delivers these anywhere yet.** They are visible in Prometheus under
Alerts and in Grafana, but there is no Alertmanager, so nobody is paged or
emailed. Choosing a destination — email, Slack, a webhook — is the step that
turns this from "someone can see it" into "someone is told", and it is the
remaining half of the problem this was built for.

## Where the logs are

Alloy reads the containers' logs through the Docker daemon and pushes them to
Loki. **Only `datamap_*` containers**: the host runs three unrelated projects
and their logs are not ours to collect.

Loki keeps them on the host disk, in the `loki_data` volume, for **90 days**.
Measured on 2026-09-23, every container together produces about 8 MB a day, of
which MinIO is 98% — so 90 days is under a gigabyte before compression, against
110 GB free.

Not on the NAS: the volume does not justify it, and Loki's write-ahead log
wants fsync and locking semantics that NFS does not guarantee.

### Querying

In Grafana, pick the Loki datasource. The fields the applications log as JSON
are labels, so:

```logql
{container="datamap_gatekeeper", level="ERROR"}
{level="ERROR"} |= "tus hook failed"
{container="datamap_gatekeeper"} | json | request_id="110a59d6-…"
```

`level` and `logger` are labels. `request_id` deliberately is **not**: a label
per request is one stream per request, which is how a Loki index falls over.
Filter on it with `| json | request_id="…"` instead.

### What Alloy is allowed to do

It mounts the Docker socket. That is root-equivalent access to the host, which
is the price of reading other containers' logs and worth knowing rather than
discovering. The mount is read-only and the config ships only `datamap_*`, but
neither of those constrains what the socket itself permits.

## Changing an alert

The rules are code and have tests:

```bash
make observability-check
```

That validates the config and runs `promtool test rules`, which asserts each
alert fires when it should and stays quiet when it should not. CI runs the same
thing. A rule that never fires looks exactly like a system that never fails, so
a new rule needs a test that proves it can fire.

After editing, reload without restarting:

```bash
docker exec datamap_prometheus wget -qO- --post-data='' http://127.0.0.1:9090/-/reload
```

## Checking it is working

```bash
docker exec datamap_prometheus wget -qO- 'http://127.0.0.1:9090/api/v1/targets?state=active'
```

Expect `"health":"up"` for `gatekeeper`, `loki` and `alloy`. `down` with a DNS error means
the observability stack is not on the same docker network as the application —
it joins `gatekeeper_gatekeeper-network`, which the application stack creates.
Start the application first.
