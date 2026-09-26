# Rotating a production credential

Two values were readable by anyone for months (see the commit that removed
them). Everything that was ever committed is treated as leaked, because it is.
This is the order to replace them in, and how to tell that each step worked.

Rotation is the expensive half of getting secrets out of the repository. The
cheap half — SOPS — is worth nothing until this is done, because encrypting a
value that is already public only makes it look finished.

## Before starting

No uploads may be in flight: rotating the upload token invalidates the ones
already issued.

```bash
ssh datamap-prod 'ls -lt --time-style=+%Y-%m-%dT%H:%M ~/storage/datamap/infrastructure/minio/datamap/staged | head -3'
ssh datamap-prod 'ss -tn state established "( sport = :1080 )" | wc -l'
```

A count of 1 is the header alone, so it means zero connections.

Two rules apply to every step below.

**`docker restart` does not re-read `env_file`.** Environment variables are
fixed when a container is created. A restart after changing a value changes
nothing and looks like it worked. Always `up -d --force-recreate`.

**Never paste a new value into a terminal.** `scripts/set_env_value.py` prompts
for it with the echo off, writes it into the file, and prints only an eight
character fingerprint:

```bash
python3 scripts/set_env_value.py ~/environment/gatekeeper.prod.env DOI_PASSWORD
```

Two files hold the same credential when they print the same fingerprint, which
is how a shared secret is checked without anyone reading it, and the only thing
about a credential that is safe to quote in a message:

```bash
python3 scripts/env_fingerprint.py ~/environment/frontend.prod.env AUTH_FILE_UPLOAD_TOKEN_SECRET
```

`openssl rand -base64 32 | tr -d '/+=' | cut -c1-32` is enough for a machine
credential. The credentials a person logs in with — MinIO root, Grafana,
pgAdmin, the console's basic auth, DataCite — have to be chosen by whoever will
type them.

**A value cannot contain `#`, `$` or a backtick.** The Makefile reads these
files with `include`, so they are parsed as make syntax before a container sees
them. Measured: `POSTGRES_PASSWORD=abc#def` reaches make as `abc`, silently —
the deploy would apply a password nobody chose and report nothing. The setter
refuses those characters rather than leave it to be discovered.

## The order, and why

Least coupled first, so that a mistake is cheap while the procedure is still
unfamiliar. The two that need the quiet window are last.

| | credential | moves with it | window |
|---|---|---|---|
| 1 | Grafana admin, pgAdmin | one container each | none |
| 2 | DataCite (`DOI_PASSWORD`) | gatekeeper ×2 | none |
| 3 | MinIO root | the MinIO container | ~10s of storage |
| 4 | MinIO access keys ×3 | gatekeeper ×2, tusd, archivist | none |
| 5 | `DATAMAP_API_SECRET`, `GATEKEEPER_API_SECRET` | webapp, archivist | none |
| 6 | `AUTH_FILE_UPLOAD_TOKEN_SECRET` | gatekeeper ×2 **and** webapp | uploads break |
| 7 | `POSTGRES_PASSWORD` | gatekeeper ×2, archivist, scripts | seconds |

Steps 4 and 5 have no window because the old and the new credential can both
be valid at once: create, move the consumer, verify, then delete the old one.
Steps 6 and 7 have no such overlap, which is what makes them the expensive
ones.

## 3. MinIO root

Verified on the same image (`RELEASE.2024-03-21T23-13-43Z`) before doing it
here: a service account whose parent is root **survives** a root password
change. The three application access keys do not move with this step.

The console login is the reason to rotate it: the root username has been public
since 2024, and the community console has no second factor.

Edit `MINIO_ROOT_PASSWORD` in `~/environment/gatekeeper.prod.env`, then

```bash
cd ~/gatekeeper
make ENV_FILE_PATH=~/environment/gatekeeper.prod.env docker-build
docker compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml \
  up -d --force-recreate --wait minio
```

Then prove both directions — the new password works and the old one does not:

```bash
ssh datamap-prod 'set -a; . ~/environment/gatekeeper.prod.env; set +a;
  docker exec -e MC_HOST_l="http://$MINIO_ROOT_USER:$MINIO_ROOT_PASSWORD@127.0.0.1:9000" \
    datamap_min_io mc admin info l | head -3'
```

A step that only confirms the new value tells you nothing: the old one has to
be seen failing.

## 4. MinIO access keys

One per consumer: gatekeeper, tusd, archivist. They are already three distinct
accounts — keep it that way, so that any future rotation stays this cheap.

```bash
ssh datamap-prod 'set -a; . ~/environment/gatekeeper.prod.env; set +a;
  docker exec -e MC_HOST_l="http://$MINIO_ROOT_USER:$MINIO_ROOT_PASSWORD@127.0.0.1:9000" \
    datamap_min_io mc admin user svcacct add l "$MINIO_ROOT_USER" \
      --access-key <new-key> --secret-key <new-secret>'
```

Update the consumer's env file, recreate it, confirm it reads and writes, and
only then remove the old account:

```bash
mc admin user svcacct rm l <old-key>
```

Removing it before the consumer is verified turns a rotation into an outage.

## 6. Upload token

`AUTH_FILE_UPLOAD_TOKEN_SECRET` is an HMAC secret shared by gatekeeper and the
webapp. Both sign with it, so both have to move together; tokens already issued
stop validating.

Set it in `~/environment/gatekeeper.prod.env` **and**
`~/environment/frontend.prod.env` — the same value in both — then recreate the
API instances and the webapp. A mismatch fails every upload with an
authorisation error that says nothing about its cause, so confirm the two files
agree before recreating anything:

```bash
for f in gatekeeper.prod.env frontend.prod.env; do
  python3 scripts/env_fingerprint.py ~/environment/$f AUTH_FILE_UPLOAD_TOKEN_SECRET
done
```

Two identical fingerprints, and no value on screen.

## 7. Postgres

The leaked one, and the most coupled: `gk_admin` is used by gatekeeper ×2, the
archivist, and the scripts. `gk_admin` is a superuser; `datamap_ops_read` also
exists and is not in any environment file, so leave it alone.

Postgres does not re-authenticate live connections, so the running application
keeps working after the `ALTER` and fails only when the pool opens a new
connection. That is the window, and it is why the environment files are updated
first.

1. New value into all four files: `gatekeeper.prod.env`,
   `archivist.prod.env`, `archivist-test.prod.env`,
   `scripts-gatekeeper.prod.env`. Four identical fingerprints before anything
   is recreated:

   ```bash
   for f in gatekeeper archivist archivist-test scripts-gatekeeper; do
     python3 scripts/env_fingerprint.py ~/environment/$f.prod.env POSTGRES_PASSWORD
   done
   ```
2. `ALTER USER gk_admin PASSWORD '<new>';`
3. Roll the API (`docker-deployment-rolling`), then recreate the archivist.

Verify by asking the application, not the database: a `200` from the API means
it authenticated with the new value through its own pool.

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://datamap.pcs.usp.br/api/v1/health-check/dependencies/
```

`local.env` on each developer's machine still holds the old password, because
that is where the leak came from. Give it a value of its own; it has no reason
to match production.

## Afterwards

The guard in the deploy job compares every credential-named variable in
`~/environment/*.env` against every tracked file, and fails the deploy on a
match. It is what makes this a one-time exercise rather than a recurring one.
Run it by hand after a rotation to confirm nothing was pasted back in:

```bash
python3 scripts/check_tracked_secrets.py ~/environment
```
