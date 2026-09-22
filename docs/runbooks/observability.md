# Metrics and alerts

Prometheus scrapes the gatekeeper; Grafana reads Prometheus. Neither is part of
the automated deploy: they hold their own data and do not need replacing when
the application changes.

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

Expect `"health":"up"` for the `gatekeeper` job. `down` with a DNS error means
the observability stack is not on the same docker network as the application —
it joins `gatekeeper_gatekeeper-network`, which the application stack creates.
Start the application first.
