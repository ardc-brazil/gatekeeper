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

Three rules apply to every step below.

**`docker restart` does not re-read `env_file`.** Environment variables are
fixed when a container is created. A restart after changing a value changes
nothing and looks like it worked. Always `up -d --force-recreate`.

**Run compose from the checkout that deploys**, which is the runner's:

```bash
cd /home/datamap/actions-runner/_work/gatekeeper/gatekeeper
export COMPOSE_PROJECT_NAME=gatekeeper
```

That is the only checkout on the host. There used to be a second one at
`~/gatekeeper`, which lagged — it was two commits behind while this was written,
and Compose read from there would quietly reinstate the infrastructure of
whatever commit it sat on, including the MinIO image pin. It is gone.

**Never paste a new value into a terminal.** `scripts/set_env_value.py` prompts
for it with the echo off, writes it into the file, and prints only an eight
character fingerprint:

```bash
sops secrets/production/gatekeeper.env
```

`sops` re-encrypts on save and only the changed value gets new ciphertext, so the
diff names what moved. When the value must not reach an editor buffer at all,
`scripts/set_env_value.py <file> DOI_PASSWORD` prompts with the echo off and
prints only a fingerprint; point it at a decrypted copy and re-encrypt after.

Two files hold the same credential when they print the same fingerprint, which
is how a shared secret is checked without anyone reading it, and the only thing
about a credential that is safe to quote in a message:

```bash
python3 scripts/env_fingerprint.py <file> AUTH_FILE_UPLOAD_TOKEN_SECRET
```

Each service's configuration is now encrypted in its own repository, so "the
file" is a `sops --decrypt` away rather than a path on the host. A secret two
services share has to change in both repositories: the webapp signs upload
tokens with `AUTH_FILE_UPLOAD_TOKEN_SECRET` and the API verifies them.

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

Set `MINIO_ROOT_PASSWORD` in `secrets/production/gatekeeper.env`, merge it, let
the deploy update the host's checkout, then recreate MinIO from a decrypted copy
— see [host-applied-changes.md](host-applied-changes.md) for why the variables
have to be in the shell:

```bash
cd /home/datamap/actions-runner/_work/gatekeeper/gatekeeper
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; umask 077
~/bin/sops --decrypt secrets/production/gatekeeper.env > "$T/env"
export ENV_FILE_PATH="$T/env"
set -a; . "$ENV_FILE_PATH"; set +a
```

```bash
docker compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml \
  up -d --force-recreate --wait minio
```

Then prove both directions — the new password works and the old one does not:

```bash
docker exec -e MC_HOST_l="http://$MINIO_ROOT_USER:$MINIO_ROOT_PASSWORD@127.0.0.1:9000" \
  datamap_min_io mc admin info l | head -3
```

with the environment sourced as above. Then run it again with the old password
substituted by hand, and watch it be refused.

A step that only confirms the new value tells you nothing: the old one has to
be seen failing.

## 4. MinIO access keys

One per consumer: gatekeeper, tusd, archivist. They are already three distinct
accounts — keep it that way, so that any future rotation stays this cheap.

```bash
docker exec -e MC_HOST_l="http://$MINIO_ROOT_USER:$MINIO_ROOT_PASSWORD@127.0.0.1:9000" \
  datamap_min_io mc admin user svcacct add l "$MINIO_ROOT_USER" \
    --access-key <new-key> --secret-key <new-secret>
```

Update the consumer's env file, recreate it, confirm it reads and writes, and
only then remove the old account:

```bash
mc admin user svcacct rm l <old-key>
```

Removing it before the consumer is verified turns a rotation into an outage.

## 6. Upload token

The webapp's BFF signs a JWT with `AUTH_FILE_UPLOAD_TOKEN_SECRET`
(`pages/api/auth/token.ts`) and gatekeeper verifies it, so the two have to hold
the same value and move together. The tokens last a day, so rotating invalidates
up to 24 hours of issued ones — in practice whoever has an upload open or a page
already loaded.

Set it in `secrets/production/gatekeeper.env` here **and** in the webapp's
`secrets/production/frontend.env.sops` — the same value in both, in two
repositories — then recreate the API instances and the webapp. A mismatch fails every upload with an
authorisation error that says nothing about its cause, so confirm the two files
agree before recreating anything:

```bash
sops --decrypt secrets/production/gatekeeper.env > /tmp/a.env
sops --decrypt --input-type dotenv --output-type dotenv \
  <webapp>/secrets/production/frontend.env.sops > /tmp/b.env
for f in /tmp/a.env /tmp/b.env; do
  python3 scripts/env_fingerprint.py "$f" AUTH_FILE_UPLOAD_TOKEN_SECRET
done
rm -f /tmp/a.env /tmp/b.env
```

`--input-type` on the second: sops reads the format from the extension, and
`.env.sops` is not one it knows.

Two identical fingerprints, and no value on screen.

## 7. Postgres

The leaked one, and the most coupled: `gk_admin` is used by gatekeeper ×2, the
archivist, and the scripts. `gk_admin` is a superuser; `datamap_ops_read` also
exists and is not in any environment file, so leave it alone.

Postgres does not re-authenticate live connections, so the running application
keeps working after the `ALTER` and fails only when the pool opens a new
connection. That is the window, and it is why the environment files are updated
first.

1. New value into all four files. Four identical fingerprints before anything
   is recreated.

   The password is shared, and the files live in two repositories:
   `secrets/production/gatekeeper.env` and `scripts-gatekeeper.env` here,
   `archivist.env.sops` and `archivist-test.env.sops` in the archivist. Decrypt
   each and compare the fingerprints before anything is recreated.
2. `ALTER USER gk_admin PASSWORD '<new>';`
3. Roll the API (`docker-deployment-rolling`), then recreate the archivist.

Verify by asking the application, not the database. The proof is that the rolled
instance started at all: the app runs `alembic upgrade head` before it serves, so
an instance that reports healthy has authenticated with the new value through its
own pool. `docker-deployment-rolling` waits for exactly that, and fails if it does
not come.

```bash
docker ps --filter name=datamap_gatekeeper --format "{{.Names}}\t{{.Status}}"
```

Both `healthy`, and the roll returned. `/api/v1/health-check/` is not the proof —
it is deliberately shallow and does no I/O, so it answers whether or not the
database is reachable.

`/api/v1/health-check/dependencies` does report the database, but it is behind
authentication *and* a Casbin policy — three headers and a client that has been
granted the route. Measured: no credential in any environment file reaches it
(`{"detail":"not_authorized"}`). It is for an operator who has set that up, not
for a check at the end of a rotation.

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
