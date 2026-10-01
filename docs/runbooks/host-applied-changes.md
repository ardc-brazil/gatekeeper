# Infrastructure the deploy does not apply

The deploy rolls the two API instances and nothing else. Three things in this
repository reach production only when someone applies them by hand:

| File | Applied by | Why not the deploy |
| --- | --- | --- |
| `infrastructure/nginx/datamap.conf` | `sudo cp` + `nginx -t` + reload | nginx runs on the host under systemd, not in a container, and the runner has no `sudo` |
| `docker-compose-database.yaml` | `docker compose up -d <service>` | Postgres and pgAdmin hold data; recreating them on every merge would be an outage per merge |
| `docker-compose-infrastructure.yaml` | same | MinIO and TUSd, same reason |

Merging a change to any of them changes nothing on the host. The checkout the
runner deploys from only catches up when a later push to `main` runs the deploy,
so **merge first, wait for the deploy, then apply** — otherwise the compose file
on disk is still the old one and the command silently does nothing useful.

## The short way

Everything below is wrapped in `Makefile.infra`, which takes no `ENV_FILE_PATH` —
each target decrypts what it needs and removes it on the way out:

```bash
cd /home/datamap/actions-runner/_work/gatekeeper/gatekeeper
make -f Makefile.infra                 # the list
make -f Makefile.infra workspace-status # is the merge you want even here yet?
make -f Makefile.infra nginx-diff
make -f Makefile.infra nginx-apply     # asks for sudo
make -f Makefile.infra pgadmin
```

`nginx-apply` and `pgadmin` both finish by running `pgadmin-check`, so a target
that reports success has been verified rather than merely executed.

The rest of this page is what those targets do, and why each step is there. Read
it when a target fails, or before adding one.

## The one checkout

```bash
cd /home/datamap/actions-runner/_work/gatekeeper/gatekeeper
export COMPOSE_PROJECT_NAME=gatekeeper
```

There used to be a second, manual checkout at `~/gatekeeper`; it is gone. The
project name matters: Compose derives it from the directory, and without this
every container and volume is namespaced to the runner's path instead of the one
the running stack already uses.

## Compose needs the variables in the shell, not in `env_file`

This is the trap. Setting `ENV_FILE_PATH` alone is not enough:

```
WARN The "DATABASE_DOCKER_VOLUME" variable is not set. Defaulting to a blank string.
WARN The "STORAGE_DOCKER_VOLUME" variable is not set. Defaulting to a blank string.
```

`env_file:` is handed to the container; `${VAR}` in the compose file is expanded
by Compose from its own environment. The Makefile bridges the two with `include
${ENV_FILE_PATH}` plus `export`, which is why `make` works and a bare `docker
compose` does not. Those two variables are the host paths of the database and
object storage, so a blank one is not a warning to skim past.

Either go through `make`, or source the file — `Makefile.infra` does the second,
which is why its targets need no `ENV_FILE_PATH`:

```bash
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; umask 077
~/bin/sops --decrypt secrets/production/gatekeeper.env > "$T/env"

export ENV_FILE_PATH="$T/env"
set -a; . "$ENV_FILE_PATH"; set +a
```

No warnings left is the check that this worked. See
[secrets.md](secrets.md) for the decryption itself.

The main `Makefile` now refuses to run without `ENV_FILE_PATH` rather than
proceeding with everything blank, which is the same failure wearing a different
hat: an empty `include` is a silent no-op in make.

## nginx

```bash
sudo cp /etc/nginx/sites-available/datamap \
        /etc/nginx/sites-available/datamap.$(date +%F-%H%M).bak
sudo cp infrastructure/nginx/datamap.conf /etc/nginx/sites-available/datamap
sudo nginx -t && sudo systemctl reload nginx
```

`nginx -t` before the reload, always: a reload with a bad file leaves the old
configuration running, but `systemctl restart` would not.

`nginx-diff` first. If they differ by more than your change, something was
applied to the host and never committed, and copying over it loses that — the
first run of that target found the host carrying an earlier revision of a comment,
which is harmless, and is exactly the shape a harmful difference would take.

## One service, not the stack

Name the service, and name both compose files — the running stack was created
from both, and Compose acts only on the services in the files it is given:

```bash
docker compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml \
  up -d gatekeeper-pgadmin
```

Service names are not container names: the service is `gatekeeper-pgadmin`, the
container is `datamap_pgadmin`. `docker compose config --services` lists them.

The orphan warning about `datamap_grafana` and the other observability
containers is expected — they share the project name but live in a third compose
file. **Never pass `--remove-orphans` here.** It would delete the entire
observability stack.

## Give it time before believing the check

pgAdmin takes about twenty seconds to answer: gunicorn, then Postfix. A `curl`
fired the instant the container starts returns `000`, and nginx in front of it
returns `502`, and neither means the change failed. Poll instead of measuring
once.

## pgAdmin is reachable only through nginx

Its port is published on `127.0.0.1:5050` so the only way in is
<https://datamap.pcs.usp.br/pgadmin>, over TLS. Published on every interface it
also answered plain HTTP on the university network, where the password and the
TOTP code travelled in clear.

After recreating it, check all three:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5050/login
curl -sL -o /dev/null -w "%{http_code}\n" https://datamap.pcs.usp.br/pgadmin
curl -s -o /dev/null --max-time 5 "http://$(hostname -I | awk '{print $1}'):5050/login" \
  && echo "still exposed" || echo "closed, as intended"
```

`200`, `200`, and closed. The third is the point of the change and the only one
that fails loudly if the port was republished on every interface by accident.
