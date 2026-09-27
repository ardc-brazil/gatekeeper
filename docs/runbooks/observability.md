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

## Dashboards

They are JSON files under `infrastructure/grafana/dashboards/`, one Grafana
folder per directory, loaded at start and re-read every 30 seconds. Grafana
refuses to save changes to them: the repository is the only place they change.

To change one, edit it in Grafana, then *Share → Export → Save to file*
(leave "Export for sharing externally" off, so the datasources stay `prometheus`
and `loki`), replace the file, set `"id": null`, and commit. Then:

```bash
pytest app/grafana_dashboards_test.py
```

It fails when a panel queries a `datamap_*` metric nobody declares — a renamed
metric draws an empty panel that looks exactly like a quiet system. Metrics
declared by other services (webapp, archivist, zipper) are listed in
`infrastructure/grafana/external-metrics.txt`.

The design and the metric contract are in
`docs/rfcs/005-platform-metrics-and-dashboards.md`.

## Where the metrics come from

| Job | Target | What |
|---|---|---|
| `gatekeeper` | `datamap_gatekeeper:9095`, `datamap_gatekeeper_b:9095` | the application |
| `webapp` | `datamap_frontend:9095` | the BFF, its calls to the gatekeeper, and the browser's telemetry |
| `archivist` | `datamap_archivist:9096` | collocation runs, files and bytes moved |
| `zipper` | `datamap_zipper:9095`, once it is deployed (commented out in `prometheus.yml`) | zips built, failed, duration and size |
| `node` | `host.docker.internal:9100` | the host: CPU, memory, disk, network |
| `cadvisor` | `datamap_cadvisor:8080` | every `datamap_*` container |
| `postgres` | `datamap_postgres_exporter:9187` | the gatekeeper database |
| `nginx` | `datamap_nginx_exporter:9113` | the host nginx's `stub_status` |
| `minio`, `minio_bucket` | `minio:9000` (the alias: MinIO rejects the underscore in `datamap_min_io`) | capacity, S3 traffic, bucket sizes |
| `tusd` | `datamap_tusd:1080` | uploads and hooks |
| `prometheus`, `loki`, `alloy` | | the stack itself |

The gatekeeper serves them on **port 9095**, which Compose does not publish.
A Prometheus scrape config cannot send `X-Api-Key` and `X-Api-Secret`, so the
docker network is the boundary rather than an authorisation check. The port is
not proxied by nginx and not reachable from outside the host.

```bash
# from the host, as Prometheus does
docker exec datamap_gatekeeper python3 -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:9095/metrics').read().decode()[:400])"
```

### What the exporters are allowed to do

- **cAdvisor** runs privileged and mounts `/var/lib/docker` and `/sys`: like
  Alloy's socket, root-equivalent. It sees the neighbours' containers too;
  Prometheus drops every series whose `name` is not `datamap_*` before storing.
- **node-exporter** runs on the host network with the host's PID namespace, and
  reads `/`, `/proc` and `/sys` read-only. It listens on the docker0 address
  only (`172.17.0.1:9100`), which containers reach and the internet does not.
- **postgres-exporter** logs in with the application's own `POSTGRES_USER`,
  read from the same env file, so a credential rotation reaches it with nothing
  else to change.

## One-time host setup

The compose file cannot do these: nginx runs on the host and its configuration
is not in this repository, and MinIO is not recreated by the automated deploy.
Until they are done, the Nginx dashboard is empty and the `minio` target
answers 403. Nothing else depends on them.

### 1. The addresses the exporters use

```bash
ip -4 addr show docker0 | grep inet          # expect 172.17.0.1
sudo ss -ltnp | grep -E ':(8081|9100)\b'      # expect nothing
```

If docker0 is not `172.17.0.1`, set `HOST_METRICS_ADDRESS` to its address in
the `env` of `.github/workflows/observability.yml`. If either port is taken,
pick another and change it in `docker-compose-observability.yaml` and
`infrastructure/prometheus/prometheus.yml`.

### 2. nginx: a status page and a JSON access log

Check that nginx reads `conf.d` inside its `http` block:

```bash
sudo nginx -T 2>/dev/null | grep -n "include /etc/nginx/conf.d"
```

Create `/etc/nginx/conf.d/datamap-observability.conf`:

```nginx
# JSON access log for Loki, next to the existing one, for DataMap's hosts only.
# $uri and never $request_uri: presigned download URLs carry their signature
# in the query string.
map $host $datamap_json_log {
    ~datamap\.pcs\.usp\.br$  1;
    default                  0;
}

log_format datamap_json escape=json '{'
    '"time":"$time_iso8601",'
    '"remote_addr":"$remote_addr",'
    '"request_method":"$request_method",'
    '"uri":"$uri",'
    '"status":"$status",'
    '"bytes_sent":$bytes_sent,'
    '"request_time":$request_time,'
    '"upstream_addr":"$upstream_addr",'
    '"upstream_status":"$upstream_status",'
    '"upstream_response_time":"$upstream_response_time",'
    '"request_id":"$http_x_request_id",'
    '"referer":"$http_referer",'
    '"user_agent":"$http_user_agent",'
    '"vhost":"$host"'
'}';

access_log /var/log/nginx/datamap.access.json.log datamap_json if=$datamap_json_log;

# Read by datamap_nginx_exporter from the docker network. Public requests get 403.
server {
    listen 8081;
    access_log off;

    location = /stub_status {
        stub_status;
        allow 127.0.0.1;
        allow 172.16.0.0/12;
        deny all;
    }
}
```

An `access_log` at the `http` level adds to the one `nginx.conf` already
declares there; it does not replace it. One inside a `server` block would.

```bash
sudo nginx -t && sudo systemctl reload nginx
curl -s http://127.0.0.1:8081/stub_status          # "Active connections: …"
curl -s -o /dev/null https://datamap.pcs.usp.br/
sudo tail -1 /var/log/nginx/datamap.access.json.log # one JSON line
```

The existing logrotate rule for `/var/log/nginx/*.log` covers the new file.

### 3. Containers must reach the host

```bash
docker run --rm --network gatekeeper_gatekeeper-network \
  --add-host host.docker.internal:host-gateway curlimages/curl:8.10.1 \
  -s -m 5 http://host.docker.internal:8081/stub_status
```

A timeout means the host firewall drops traffic from the docker bridges:

```bash
sudo ufw allow from 172.16.0.0/12 to any port 8081,9100 proto tcp
```

### 4. MinIO, once

`MINIO_PROMETHEUS_AUTH_TYPE=public` takes effect when the container is
recreated, and the automated deploy never recreates MinIO. Downloads pause for
the few seconds it takes:

```bash
cd ~/gatekeeper
COMPOSE_PROJECT_NAME=gatekeeper ENV_FILE_PATH=../environment/gatekeeper.prod.env \
  docker compose -f docker-compose-infrastructure.yaml up -d minio
```

Port 9000 is published on the host. From **outside** the host, confirm the
metrics are not reachable:

```bash
curl -s -m 5 -o /dev/null -w "%{http_code}\n" \
  http://datamap.pcs.usp.br:9000/minio/v2/metrics/cluster   # expect 000 (no answer)
```

A `200` means port 9000 is open to the internet. Close it in the firewall;
nginx reaches MinIO on `localhost` and does not need it open.

### 5. Check

After the next observability deploy, every target should be `up`:

```bash
docker exec datamap_prometheus wget -qO- 'http://127.0.0.1:9090/api/v1/targets?state=active' \
  | grep -o '"job":"[a-z_]*"\|"health":"[a-z]*"' | paste - -
```

## The alerts

| Alert | Fires when | Why it exists |
|---|---|---|
| `UploadHooksFailing` | any TUS hook answers 5xx in ten minutes | this failed every time for ninety days in 2026 and lost three uploads |
| `SnapshotPublicationFailing` | a snapshot fails to publish | a findable DOI with no page behind it |
| `CollocationBacklogNotDraining` | datasets pending for two hours | the Archivist retries forever and never gives up |
| `GatekeeperDown` | no successful scrape for five minutes | |
| `ServerErrorsElevated` | over 5% of one service's requests are 5xx for ten minutes | |
| `LatencyHigh` | a service's p95 is over 2s for fifteen minutes, with real traffic | |
| `HostDiskFillingUp` | a filesystem is over 85% full, or on course to fill within a day | a full disk stops uploads first |
| `HostMemoryLow` | under 10% of memory available for fifteen minutes | the host is shared: check Containers first |
| `ContainerRestarting` | a `datamap_*` container restarted more than twice in an hour | |
| `PostgresConnectionsHigh` | over 80% of `max_connections` for ten minutes | |
| `DataCiteFailing` | a call to DataCite failed, timed out or found nobody, in fifteen minutes | DOIs cannot be created or published |
| `ArchivistStalled` | no successful archivist run in an hour, an hour after it started | files stay in `staged/` |
| `ZipsFailing` | a zip failed in the last half hour | |

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
