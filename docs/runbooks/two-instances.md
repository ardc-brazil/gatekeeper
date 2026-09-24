# Putting the second instance behind nginx

The application side is automated; **the nginx change is not, and has to be
applied by hand**. nginx runs on the host, not in a container, and its
configuration is not version controlled — `infrastructure/nginx/datamap.conf`
in this repository is a copy of what should be live after this change, not
something that deploys itself.

Nothing here touches pgadmin, TUSd, MinIO or the webapp.

## Before

```
/etc/nginx/sites-enabled/datamap   →   proxy_pass http://localhost:9092
```

One instance. The process is a single point of failure: a crash, an OOM or a
deploy is an outage.

## After

```
upstream gatekeeper {
    server 127.0.0.1:9092 max_fails=1 fail_timeout=5s;
    server 127.0.0.1:9192 max_fails=1 fail_timeout=5s;
}
```

Two, and the deploy replaces them one at a time.

## The steps

Merge the application change first, so both containers exist and answer before
nginx is told to use them.

**1. Confirm both instances are up.**

```bash
curl -s -o /dev/null -w "9092 -> %{http_code}\n" http://localhost:9092/api/v1/health-check/
curl -s -o /dev/null -w "9192 -> %{http_code}\n" http://localhost:9192/api/v1/health-check/
```

Both must be `200`. If 9192 is not, stop: the rest would send half the traffic
nowhere.

**2. Keep the current file, named by date.**

```bash
sudo cp /etc/nginx/sites-enabled/datamap \
        /etc/nginx/sites-available/datamap.$(date +%Y-%m-%d).bak
```

**3. Put the new one in place.**

```bash
sudo cp ~/gatekeeper/infrastructure/nginx/datamap.conf /etc/nginx/sites-enabled/datamap
```

**4. Check it before it takes effect.**

```bash
sudo nginx -t
```

`syntax is ok` and `test is successful`, both. If not, the file from step 2 goes
back and nothing has changed yet — nginx is still serving the old config.

**5. Reload, which does not drop connections.**

```bash
sudo systemctl reload nginx
```

**6. Confirm.**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://datamap.pcs.usp.br/api/v1/health-check/
for i in $(seq 1 20); do
  curl -s https://datamap.pcs.usp.br/api/v1/health-check/ >/dev/null || echo "falhou"
done
```

Twenty requests, no output. Then watch which instance answers:

```bash
docker logs --since 1m datamap_gatekeeper | grep -c '"logger": "http.access"'
docker logs --since 1m datamap_gatekeeper_b | grep -c '"logger": "http.access"'
```

Both counts above zero means the upstream is balancing.

## Going back

```bash
sudo cp /etc/nginx/sites-available/datamap.<date>.bak /etc/nginx/sites-enabled/datamap
sudo nginx -t && sudo systemctl reload nginx
```

The second container can stay running; nothing reaches it once nginx stops
pointing there.

## How long the rollout takes, and why it is not shorter

`docker compose up --wait` returns the moment the healthcheck passes. The
timeout on it is a ceiling, not a duration: an instance is healthy in about two
seconds, and that is when the command returns.

The floor is set by nginx, not by the container. After a failure nginx ejects an
instance for `fail_timeout`, so replacing the second one before the first is
retried leaves it with nowhere to send. Measured with a request every 200ms:

| rollout | failed requests |
|---|---|
| ~25s, first attempt | 0 |
| **5s, no pause between instances** | **10 × 502** |
| 17s, `fail_timeout 10s` and a 12s pause | 0 |
| **11s, `fail_timeout 5s` and a 7s pause** | **0** |

Making it faster is what broke it. `UPSTREAM_RECOVERY` in the Makefile is that
pause, and it has to stay above the `fail_timeout` in the nginx config — change
one and change the other.

## Why `proxy_connect_timeout 2s`

It is the setting that makes the difference, and not the obvious one. When a
container dies, its address stops answering rather than refusing, so nginx waits
out `proxy_connect_timeout` — **60 seconds by default** — before trying the other
instance.

Measured against two instances with a request every 200ms, killing one:

| | failed requests |
|---|---|
| default timeout | 5 |
| `proxy_connect_timeout 2s` | **0** |

`max_fails` was the first guess and made no difference at all: 5 either way.

## What this does and does not buy

It removes the **process** as a single point of failure: a crash, an OOM or a
deploy stops being an outage. A graceful rolling restart was measured at 319
requests with zero failures, in eleven seconds.

It does **not** remove the machine. Two instances on one host is redundancy
against software, not against hardware. If the host goes, everything goes.

## TUSd

TUSd calls the hook by name, and both instances answer to the alias
`gatekeeper` on the docker network, so `TUS_HOOK_API` reaches whichever is up.
For that to hold, the value in `gatekeeper.prod.env` has to be the alias rather
than one container:

```
TUS_HOOK_API=http://gatekeeper:9092/api/v1/tus/hooks
```

It currently reads `http://datamap_gatekeeper:9092/...`, which pins it to the
first instance. Docker's DNS round-robin has no health check, so a request may
still land on an instance that is down — TUSd retries its hooks, which is why
this is an improvement rather than a guarantee.
