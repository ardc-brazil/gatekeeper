# Notebooks — Hub, Image and Host Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run JupyterHub on the production host with one container per session, built from an image that carries Python, R, both SDKs and an entrypoint that materialises `/data` from the gatekeeper's manifest; route it through nginx; prove the limits with a smoke test in CI; and give the operator a runbook, a dashboard and one alert.

**Architecture:** The hub is a container on the gatekeeper's docker network, reaching Docker through a socket proxy that allows only what DockerSpawner needs. A custom authenticator accepts the gatekeeper's session token from a form POST and stores its claims; a DockerSpawner subclass turns those claims into the container's environment, mounts and limits, and reports `started` and `stopped` to the gatekeeper's internal routes. The user image starts as root: the entrypoint fetches the manifest, writes the first cell if the notebook is new, copies the selection into `/data`, locks it to `root:root 0555`, reports progress, and then hands over to the stock `start.sh`, which drops to the unprivileged user and starts the single-user server. Nothing in the hub or the image holds a credential other than the per-session token and the hub's own client key.

**Tech Stack:** JupyterHub 4.1 (`quay.io/jupyterhub/jupyterhub:4.1.6`), dockerspawner 13, jupyterhub-idle-culler 1.4, `tecnativa/docker-socket-proxy`, `quay.io/jupyter/minimal-notebook:python-3.11` with conda-forge R, PyJWT, requests, Docker Compose, nginx on the host, GitHub Actions, GHCR, Prometheus, Grafana.

**Spec:** `docs/rfcs/007-notebooks.md` (§Components, §Session lifecycle, §Data in the session, §Image, §Limits, §Observability, §Testing). **Contracts:** `docs/superpowers/plans/2026-10-04-notebooks-00-contracts.md` (wins over this plan on any interface). **Depends on:** plan 01's internal routes, manifest and progress route, for the smoke test to pass end to end; the hub and image build without it.

## Global Constraints

- Container limits exactly: `mem_limit` and `memswap_limit` = `NOTEBOOK_SESSION_MEMORY` (`12g` in production), `nano_cpus` = `NOTEBOOK_SESSION_CPUS × 1e9` (`2`), `cpu_shares` 1024, `pids_limit` 256, `cap_drop ALL` plus the five capabilities `start.sh` needs to drop privileges, `no-new-privileges`.
- Container name `datamap-notebook-{user_id}`; network `gatekeeper_gatekeeper-network`; hub container `datamap_jupyterhub`, published on `127.0.0.1:8000` only.
- Mounts and ownership as the contracts' *Storage layout*: `/home/jovyan/work` and `/outputs` owned by the kernel user, `/data` `root:root 0555` before Lab starts.
- Environment variables set on the container exactly as the contracts' *Container environment* table.
- Hub login is a form POST with `token` and `next`. The token is never placed in a URL. The authenticator stores `{"claims", "token"}` as `auth_state`, which requires `JUPYTERHUB_CRYPT_KEY`.
- Idle timeout `NOTEBOOK_IDLE_MINUTES` (60), hard limit `NOTEBOOK_SESSION_MAX_HOURS` (12), `active_server_limit = NOTEBOOK_SEATS`, named servers off.
- Spawn timeouts `start_timeout = http_timeout = 900`: a 20 GB copy on the NAS is inside that; the limit is there so a stuck copy ends.
- The hub keeps its own state in SQLite on a named volume, not in PostgreSQL. The RFC said PostgreSQL so the backup would cover it; the backup script dumps exactly one database by name, and the hub's state is not a record of anything (the gatekeeper's `notebook_sessions` is). Task 8 amends the RFC.
- Outbound network from a session is not restricted in increment A. The RFC's "gatekeeper, MinIO, PyPI and CRAN only" needs a filtering proxy, which Task 8 records as the follow-up.
- Pure logic lives in modules that import neither `jupyterhub` nor `dockerspawner`, so it is unit-tested from the gatekeeper's `.venv` (PyJWT and requests are there). Everything that needs the hub runtime is proved by the smoke test.
- nginx on the production host is applied by hand through `Makefile.infra`; the container nginx (`default.conf`) is for local stacks. Both get the same two location blocks.
- Code style (CLAUDE.md): no narrating comments; one-line comment only where a reader would otherwise undo something on purpose. Type hints everywhere. Python 3.11 is fine inside the hub and the image (neither is the gatekeeper), but keep the pure modules 3.10-compatible since the gatekeeper's venv runs their tests.
- The notebook image is built by its own workflow and pushed to GHCR; CI pulls it. A 4 GB image is not rebuilt on every push.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `infrastructure/jupyterhub/datamap_hub/__init__.py` | create | package |
| `infrastructure/jupyterhub/datamap_hub/claims.py` | create | `decode_claims(token, secret) -> dict`, `InvalidToken` |
| `infrastructure/jupyterhub/datamap_hub/container.py` | create | `Settings`, `settings_from_env`, `memory_bytes`, `container_env`, `volumes_for`, `host_config`, `container_name` |
| `infrastructure/jupyterhub/datamap_hub/authenticator.py` | create | `DataMapTokenAuthenticator` |
| `infrastructure/jupyterhub/datamap_hub/spawner.py` | create | `DataMapSpawner` (reports started/stopped) |
| `infrastructure/jupyterhub/jupyterhub_config.py` | create | the hub configuration, all values from the environment |
| `infrastructure/jupyterhub/Dockerfile`, `requirements.txt` | create | hub image |
| `infrastructure/jupyterhub/pytest.ini`, `tests/test_claims.py`, `tests/test_container.py` | create | unit tests for the pure modules |
| `infrastructure/jupyterhub/image/Dockerfile` | create | user image |
| `infrastructure/jupyterhub/image/datamap_entrypoint/__init__.py`, `plan.py` | create | pure helpers: copy plan, first cell, locale settings, sizes |
| `infrastructure/jupyterhub/image/entrypoint.py` | create | the entrypoint |
| `infrastructure/jupyterhub/image/tests/test_plan.py` | create | unit tests |
| `docker-compose-notebooks.yaml` | create | hub + socket proxy, production and local |
| `docker-compose-infrastructure.yaml` | modify | storage volume read-only on both gatekeeper instances |
| `infrastructure/jupyterhub/smoke/compose.yaml`, `wiremock/mappings/*.json`, `wiremock/__files/sample.nc`, `smoke_test.py` | create | the smoke test |
| `Makefile`, `Makefile.infra`, `local.env.template` | modify | targets and variables |
| `infrastructure/nginx/datamap.conf`, `infrastructure/nginx/default.conf` | modify | `/hub/` and `/user/` |
| `.github/workflows/ci.yml` | modify | `notebooks` job: hub unit tests + smoke |
| `.github/workflows/notebook-image.yml` | create | build, push, smoke the user image |
| `.github/workflows/notebooks.yml` | create | apply the hub on the host |
| `infrastructure/prometheus/prometheus.yml`, `alerts.yml`, `alerts_test.yml` | modify | hub scrape, cadvisor keep, one alert |
| `infrastructure/grafana/dashboards/Business/notebooks.json` | create | dashboard |
| `docs/runbooks/notebooks.md`, `README.md`, `docs/README.md`, `docs/rfcs/007-notebooks.md` | create / modify | runbook, links, amendments |

---

### Task 1: The hub's pure modules

**Files:**
- Create: `infrastructure/jupyterhub/datamap_hub/__init__.py` (empty)
- Create: `infrastructure/jupyterhub/datamap_hub/claims.py`, `container.py`
- Create: `infrastructure/jupyterhub/pytest.ini`, `tests/__init__.py` (empty), `tests/test_claims.py`, `tests/test_container.py`

**Interfaces:**
- Produces: `decode_claims(token: str, secret: str) -> dict` raising `InvalidToken`; `Settings(api_url, storage_host_path, image, cpus, memory, network, pids_limit, hub_api_key, hub_api_secret)`; `settings_from_env(environ) -> Settings`; `memory_bytes(spec) -> int`; `container_env(claims, token, settings) -> dict[str, str]`; `volumes_for(claims, storage_host_path) -> dict[str, dict]`; `host_config(settings) -> dict`; `container_name(user_id) -> str`.

- [ ] **Step 1: pytest configuration for this directory**

`infrastructure/jupyterhub/pytest.ini`:

```ini
[pytest]
pythonpath = . image
testpaths = tests image/tests
python_files = test_*.py
addopts = -q --tb=short
```

- [ ] **Step 2: Failing tests for the claims**

`infrastructure/jupyterhub/tests/test_claims.py`:

```python
import time
import uuid

import jwt
import pytest

from datamap_hub.claims import InvalidToken, decode_claims

SECRET = "hub-test-secret"


def a_token(secret: str = SECRET, **overrides) -> str:
    now = int(time.time())
    payload = {
        "iss": "gatekeeper",
        "aud": "notebook_session",
        "sub": str(uuid.uuid4()),
        "tenancies": ["t"],
        "notebook_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "datasets": [{"id": str(uuid.uuid4()), "version": "2"}],
        "kernel": "python3",
        "locale": "pt-BR",
        "iat": now,
        "exp": now + 600,
    }
    payload.update(overrides)
    return jwt.encode(payload, secret, algorithm="HS256")


def test_a_gatekeeper_token_decodes_to_its_claims():
    claims = decode_claims(a_token(kernel="ir"), SECRET)

    assert claims["kernel"] == "ir"
    assert claims["aud"] == "notebook_session"


def test_another_secret_is_refused():
    with pytest.raises(InvalidToken):
        decode_claims(a_token(secret="other"), SECRET)


def test_an_upload_token_is_refused_by_audience():
    with pytest.raises(InvalidToken):
        decode_claims(a_token(aud="file_upload"), SECRET)


def test_an_expired_token_is_refused():
    with pytest.raises(InvalidToken):
        decode_claims(a_token(exp=int(time.time()) - 1), SECRET)


def test_a_token_missing_a_session_id_is_refused():
    now = int(time.time())
    token = jwt.encode(
        {"iss": "gatekeeper", "aud": "notebook_session", "sub": "x", "iat": now, "exp": now + 60},
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(InvalidToken):
        decode_claims(token, SECRET)
```

- [ ] **Step 3: Run to verify they fail**

Run: `cd infrastructure/jupyterhub && ../../../../../.venv/bin/python -m pytest tests/test_claims.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'datamap_hub'`

- [ ] **Step 4: Write `claims.py`**

```python
import jwt

AUDIENCE = "notebook_session"
ISSUER = "gatekeeper"
REQUIRED = ("sub", "notebook_id", "session_id", "datasets", "kernel")


class InvalidToken(Exception):
    pass


def decode_claims(token: str, secret: str) -> dict:
    try:
        payload = jwt.decode(
            token, secret, algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUER
        )
    except jwt.InvalidTokenError as error:
        raise InvalidToken(str(error))
    missing = [key for key in REQUIRED if key not in payload]
    if missing:
        raise InvalidToken(f"claims missing: {', '.join(missing)}")
    return payload
```

Run the claims tests. Expected: 5 passed.

- [ ] **Step 5: Failing tests for the container description**

`infrastructure/jupyterhub/tests/test_container.py`:

```python
import uuid

import pytest

from datamap_hub.container import (
    Settings,
    container_env,
    container_name,
    host_config,
    memory_bytes,
    settings_from_env,
    volumes_for,
)

CLAIMS = {
    "sub": str(uuid.uuid4()),
    "notebook_id": str(uuid.uuid4()),
    "session_id": str(uuid.uuid4()),
    "datasets": [{"id": str(uuid.uuid4()), "version": "2"}],
    "kernel": "ir",
    "locale": "pt-BR",
}

SETTINGS = Settings(
    api_url="http://gatekeeper:9092/api/v1",
    storage_host_path="/mnt/nas",
    image="ghcr.io/ardc-brazil/datamap-notebook:x",
    cpus=2.0,
    memory="12g",
    network="gatekeeper_gatekeeper-network",
    pids_limit=256,
    hub_api_key="k",
    hub_api_secret="s",
)


def test_memory_bytes_reads_docker_suffixes():
    assert memory_bytes("12g") == 12 * 1024**3
    assert memory_bytes("512m") == 512 * 1024**2
    assert memory_bytes("1073741824") == 1024**3


def test_memory_bytes_refuses_nonsense():
    with pytest.raises(ValueError):
        memory_bytes("lots")


def test_container_env_carries_the_contract_variables():
    env = container_env(CLAIMS, "tok", SETTINGS)

    assert env["DATAMAP_SESSION_TOKEN"] == "tok"
    assert env["DATAMAP_API_URL"] == "http://gatekeeper:9092/api/v1"
    assert env["DATAMAP_NOTEBOOK_ID"] == CLAIMS["notebook_id"]
    assert env["DATAMAP_SESSION_ID"] == CLAIMS["session_id"]
    assert env["DATAMAP_KERNEL"] == "ir"
    assert env["DATAMAP_LOCALE"] == "pt-BR"
    assert env["MEM_LIMIT"] == str(12 * 1024**3)
    assert env["CPU_LIMIT"] == "2.0"
    assert '"version": "2"' in env["DATAMAP_DATASETS"]


def test_volumes_follow_the_storage_layout():
    volumes = volumes_for(CLAIMS, "/mnt/nas")
    uid, nb, sid = CLAIMS["sub"], CLAIMS["notebook_id"], CLAIMS["session_id"]

    assert volumes[f"/mnt/nas/notebooks/{uid}"] == {"bind": "/home/jovyan/work", "mode": "rw"}
    assert volumes[f"/mnt/nas/notebooks/{uid}/.outputs/{nb}"] == {"bind": "/outputs", "mode": "rw"}
    assert volumes[f"/mnt/nas/sessions/{sid}/data"] == {"bind": "/data", "mode": "rw"}


def test_host_config_is_the_limits_table():
    config = host_config(SETTINGS)

    assert config["mem_limit"] == 12 * 1024**3
    assert config["memswap_limit"] == 12 * 1024**3
    assert config["nano_cpus"] == 2_000_000_000
    assert config["cpu_shares"] == 1024
    assert config["pids_limit"] == 256
    assert config["cap_drop"] == ["ALL"]
    assert "SETUID" in config["cap_add"]
    assert config["security_opt"] == ["no-new-privileges:true"]


def test_container_name_is_prefixed_with_the_user():
    assert container_name("abc") == "datamap-notebook-abc"


def test_settings_from_env_reads_every_variable():
    settings = settings_from_env(
        {
            "DATAMAP_API_URL": "http://g/api/v1",
            "NOTEBOOK_STORAGE_HOST_PATH": "/x",
            "NOTEBOOK_IMAGE": "img",
            "NOTEBOOK_SESSION_CPUS": "1.5",
            "NOTEBOOK_SESSION_MEMORY": "1g",
            "DATAMAP_HUB_API_KEY": "k",
            "DATAMAP_HUB_API_SECRET": "s",
        }
    )

    assert settings.cpus == 1.5
    assert settings.memory == "1g"
    assert settings.network == "gatekeeper_gatekeeper-network"
    assert settings.pids_limit == 256


def test_settings_from_env_names_what_is_missing():
    with pytest.raises(KeyError):
        settings_from_env({"DATAMAP_API_URL": "x"})
```

- [ ] **Step 6: Run to verify they fail, then write `container.py`**

```python
import json
from dataclasses import dataclass

WORK_MOUNT = "/home/jovyan/work"
OUTPUTS_MOUNT = "/outputs"
DATA_MOUNT = "/data"
DEFAULT_NETWORK = "gatekeeper_gatekeeper-network"
DEFAULT_PIDS = 256
# What jupyter's start.sh needs to chown the home and drop to the kernel user.
PRIVILEGE_DROP_CAPS = ["CHOWN", "SETUID", "SETGID", "FOWNER", "DAC_OVERRIDE", "FSETID"]

_UNITS = {"k": 1024, "m": 1024**2, "g": 1024**3}


@dataclass(frozen=True)
class Settings:
    api_url: str
    storage_host_path: str
    image: str
    cpus: float
    memory: str
    network: str
    pids_limit: int
    hub_api_key: str
    hub_api_secret: str


def settings_from_env(environ) -> Settings:
    return Settings(
        api_url=environ["DATAMAP_API_URL"],
        storage_host_path=environ["NOTEBOOK_STORAGE_HOST_PATH"],
        image=environ["NOTEBOOK_IMAGE"],
        cpus=float(environ["NOTEBOOK_SESSION_CPUS"]),
        memory=environ["NOTEBOOK_SESSION_MEMORY"],
        network=environ.get("NOTEBOOK_NETWORK", DEFAULT_NETWORK),
        pids_limit=int(environ.get("NOTEBOOK_PIDS_LIMIT", DEFAULT_PIDS)),
        hub_api_key=environ["DATAMAP_HUB_API_KEY"],
        hub_api_secret=environ["DATAMAP_HUB_API_SECRET"],
    )


def memory_bytes(spec: str) -> int:
    text = spec.strip().lower()
    if text.isdigit():
        return int(text)
    if text and text[-1] in _UNITS and text[:-1].isdigit():
        return int(text[:-1]) * _UNITS[text[-1]]
    raise ValueError(f"not a memory size: {spec!r}")


def container_name(user_id: str) -> str:
    return f"datamap-notebook-{user_id}"


def container_env(claims: dict, token: str, settings: Settings) -> dict[str, str]:
    return {
        "DATAMAP_SESSION_TOKEN": token,
        "DATAMAP_API_URL": settings.api_url,
        "DATAMAP_NOTEBOOK_ID": claims["notebook_id"],
        "DATAMAP_SESSION_ID": claims["session_id"],
        "DATAMAP_DATASETS": json.dumps(claims["datasets"]),
        "DATAMAP_KERNEL": claims["kernel"],
        "DATAMAP_LOCALE": claims.get("locale", "pt-BR"),
        "MEM_LIMIT": str(memory_bytes(settings.memory)),
        "CPU_LIMIT": str(settings.cpus),
    }


def volumes_for(claims: dict, storage_host_path: str) -> dict[str, dict]:
    root = storage_host_path.rstrip("/")
    user_id, notebook_id, session_id = claims["sub"], claims["notebook_id"], claims["session_id"]
    return {
        f"{root}/notebooks/{user_id}": {"bind": WORK_MOUNT, "mode": "rw"},
        f"{root}/notebooks/{user_id}/.outputs/{notebook_id}": {"bind": OUTPUTS_MOUNT, "mode": "rw"},
        f"{root}/sessions/{session_id}/data": {"bind": DATA_MOUNT, "mode": "rw"},
    }


def host_config(settings: Settings) -> dict:
    memory = memory_bytes(settings.memory)
    return {
        "mem_limit": memory,
        "memswap_limit": memory,
        "nano_cpus": int(settings.cpus * 1_000_000_000),
        "cpu_shares": 1024,
        "pids_limit": settings.pids_limit,
        "cap_drop": ["ALL"],
        "cap_add": list(PRIVILEGE_DROP_CAPS),
        "security_opt": ["no-new-privileges:true"],
    }
```

`/data` is mounted `rw` on purpose: the entrypoint writes it before locking it with ownership and mode; a `ro` mount would stop the copy itself.

Run: `cd infrastructure/jupyterhub && ../../../../../.venv/bin/python -m pytest`
Expected: 13 passed

- [ ] **Step 7: Commit**

```bash
git add infrastructure/jupyterhub/pytest.ini infrastructure/jupyterhub/datamap_hub infrastructure/jupyterhub/tests
git commit -m "feat(notebooks): hub token claims and the container description, as pure code

Everything DockerSpawner is told about a session - environment, mounts,
cgroup limits - comes from these two modules, which import no hub code and
are tested from the gatekeeper's venv."
```

---

### Task 2: Authenticator, spawner, hub configuration and hub image

**Files:**
- Create: `infrastructure/jupyterhub/datamap_hub/authenticator.py`, `spawner.py`
- Create: `infrastructure/jupyterhub/jupyterhub_config.py`
- Create: `infrastructure/jupyterhub/Dockerfile`, `infrastructure/jupyterhub/requirements.txt`

**Interfaces:**
- Consumes: Task 1.
- Produces: `DataMapTokenAuthenticator` (form field `token`, `auth_state = {"claims", "token"}`, `pre_spawn_start` configures the spawner); `DataMapSpawner` (reports `started` and `stopped` to `{api_url}/internal/notebook-sessions/{session_id}/...` with the hub client key); the hub reads every value from the environment listed in the contracts.

- [ ] **Step 1: The authenticator**

`infrastructure/jupyterhub/datamap_hub/authenticator.py`:

```python
import os

from jupyterhub.auth import Authenticator

from datamap_hub.claims import InvalidToken, decode_claims
from datamap_hub.container import container_env, settings_from_env, volumes_for


class DataMapTokenAuthenticator(Authenticator):
    """Logs a browser in with the gatekeeper's session token, posted as a form field."""

    async def authenticate(self, handler, data):
        token = (data or {}).get("token")
        if not token:
            return None
        try:
            claims = decode_claims(token, os.environ["AUTH_NOTEBOOK_SESSION_TOKEN_SECRET"])
        except InvalidToken as error:
            self.log.warning("session token refused: %s", error)
            return None
        return {"name": claims["sub"], "auth_state": {"claims": claims, "token": token}}

    async def pre_spawn_start(self, user, spawner):
        auth_state = await user.get_auth_state()
        if not auth_state:
            raise RuntimeError("no session claims for this user; log in again")
        settings = settings_from_env(os.environ)
        claims = auth_state["claims"]
        spawner.environment.update(container_env(claims, auth_state["token"], settings))
        spawner.volumes = volumes_for(claims, settings.storage_host_path)
        spawner.session_id = claims["session_id"]
```

- [ ] **Step 2: The spawner**

`infrastructure/jupyterhub/datamap_hub/spawner.py`:

```python
import asyncio
import functools
import os

import requests
from dockerspawner import DockerSpawner
from traitlets import Unicode

REPORT_TIMEOUT = 5


class DataMapSpawner(DockerSpawner):
    session_id = Unicode("", config=False)

    _started_reported = False
    _stopped_reported = False

    def get_state(self):
        state = super().get_state()
        if self.session_id:
            state["session_id"] = self.session_id
        return state

    def load_state(self, state):
        super().load_state(state)
        self.session_id = state.get("session_id", "")

    def clear_state(self):
        super().clear_state()
        self.session_id = ""
        self._started_reported = False
        self._stopped_reported = False

    async def start(self):
        self._started_reported = False
        self._stopped_reported = False
        try:
            result = await super().start()
        except Exception:
            await self._report("stopped", {"reason": "spawn_error"})
            raise
        await self._report("started", None)
        self._started_reported = True
        return result

    async def stop(self, now=False):
        await super().stop(now=now)
        await self._report("stopped", None)

    async def poll(self):
        status = await super().poll()
        if status is not None and self._started_reported:
            await self._report("stopped", None)
        return status

    async def _report(self, event: str, body: dict | None) -> None:
        if not self.session_id:
            return
        if event == "stopped":
            if self._stopped_reported:
                return
            self._stopped_reported = True
        url = f"{os.environ['DATAMAP_API_URL']}/internal/notebook-sessions/{self.session_id}/{event}"
        headers = {
            "X-Api-Key": os.environ["DATAMAP_HUB_API_KEY"],
            "X-Api-Secret": os.environ["DATAMAP_HUB_API_SECRET"],
        }
        call = functools.partial(
            requests.post, url, json=body or {}, headers=headers, timeout=REPORT_TIMEOUT
        )
        try:
            response = await asyncio.get_running_loop().run_in_executor(None, call)
            if response.status_code >= 400:
                self.log.warning(
                    "gatekeeper refused %s for session %s: %s",
                    event, self.session_id, response.status_code,
                )
        except requests.RequestException as error:
            self.log.warning("could not report %s for session %s: %s", event, self.session_id, error)
```

The report is best effort and never raises: a gatekeeper that is being rolled must not make a stop fail, and the gatekeeper derives a missing `stopped` from the culler's next call or an admin's.

- [ ] **Step 3: The hub configuration**

`infrastructure/jupyterhub/jupyterhub_config.py`:

```python
import os
import sys

from datamap_hub.container import container_name, host_config, settings_from_env

c = get_config()  # noqa: F821

settings = settings_from_env(os.environ)
seats = int(os.environ.get("NOTEBOOK_SEATS", "4"))
max_hours = int(os.environ.get("NOTEBOOK_SESSION_MAX_HOURS", "12"))
idle_minutes = int(os.environ.get("NOTEBOOK_IDLE_MINUTES", "60"))

c.JupyterHub.bind_url = "http://:8000"
c.JupyterHub.hub_ip = "0.0.0.0"
c.JupyterHub.hub_connect_ip = os.environ.get("NOTEBOOK_HUB_HOSTNAME", "datamap_jupyterhub")
c.JupyterHub.db_url = "sqlite:////srv/jupyterhub/data/jupyterhub.sqlite"
c.JupyterHub.cookie_secret_file = "/srv/jupyterhub/data/cookie_secret"
c.JupyterHub.authenticate_prometheus = False
c.JupyterHub.active_server_limit = seats
c.JupyterHub.allow_named_servers = False
c.JupyterHub.cleanup_servers = False
c.JupyterHub.tornado_settings = {
    "headers": {"Content-Security-Policy": "frame-ancestors 'self'"}
}

c.JupyterHub.authenticator_class = "datamap_hub.authenticator.DataMapTokenAuthenticator"
c.Authenticator.enable_auth_state = True
c.Authenticator.admin_users = set()
c.Authenticator.auto_login = False

c.JupyterHub.spawner_class = "datamap_hub.spawner.DataMapSpawner"
c.Spawner.default_url = "/lab"
c.Spawner.start_timeout = 900
c.Spawner.http_timeout = 900
c.DockerSpawner.image = settings.image
c.DockerSpawner.pull_policy = "ifnotpresent"
c.DockerSpawner.network_name = settings.network
c.DockerSpawner.use_internal_ip = True
c.DockerSpawner.remove = True
c.DockerSpawner.name_template = container_name("{username}")
c.DockerSpawner.extra_host_config = host_config(settings)
c.DockerSpawner.extra_create_kwargs = {"user": "root"}
c.DockerSpawner.notebook_dir = "/home/jovyan"

c.JupyterHub.services = [
    {
        "name": "idle-culler",
        "command": [
            sys.executable,
            "-m",
            "jupyterhub_idle_culler",
            f"--timeout={idle_minutes * 60}",
            f"--max-age={max_hours * 3600}",
            "--cull-every=60",
        ],
    },
    {
        "name": "gatekeeper",
        "api_token": os.environ["NOTEBOOK_HUB_API_TOKEN"],
    },
]
c.JupyterHub.load_roles = [
    {
        "name": "idle-culler",
        "scopes": ["list:users", "read:users:activity", "read:servers", "delete:servers"],
        "services": ["idle-culler"],
    },
    {
        "name": "gatekeeper",
        "scopes": ["list:users", "read:users", "read:servers", "delete:servers", "admin:servers"],
        "services": ["gatekeeper"],
    },
]
```

`cleanup_servers = False` so a hub restart leaves running sessions alone; the spawner's `load_state` brings `session_id` back and `poll` keeps reporting.

- [ ] **Step 4: Hub image**

`infrastructure/jupyterhub/requirements.txt`:

```
dockerspawner==13.0.0
jupyterhub-idle-culler==1.4.0
PyJWT==2.8.0
requests==2.31.0
```

`infrastructure/jupyterhub/Dockerfile`:

```dockerfile
FROM quay.io/jupyterhub/jupyterhub:4.1.6

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY datamap_hub /srv/jupyterhub/datamap_hub
COPY jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py
RUN mkdir -p /srv/jupyterhub/data

WORKDIR /srv/jupyterhub
CMD ["jupyterhub", "-f", "/srv/jupyterhub/jupyterhub_config.py"]
```

- [ ] **Step 5: Build it**

Run: `docker build -t datamap-hub:dev infrastructure/jupyterhub`
Expected: builds. Then `docker run --rm datamap-hub:dev python -c "import datamap_hub.authenticator, datamap_hub.spawner; print('imports ok')"` prints `imports ok`.

- [ ] **Step 6: Commit**

```bash
git add infrastructure/jupyterhub/datamap_hub/authenticator.py infrastructure/jupyterhub/datamap_hub/spawner.py \
  infrastructure/jupyterhub/jupyterhub_config.py infrastructure/jupyterhub/Dockerfile infrastructure/jupyterhub/requirements.txt
git commit -m "feat(notebooks): the hub - token login, per-session container, lifecycle reports

The authenticator takes the gatekeeper's token from a form field and keeps
its claims in auth_state; the spawner turns them into the container and
tells the gatekeeper when the server is up and when it is gone. The hub's
own state is SQLite on a volume: it records nothing the gatekeeper does not."
```

---

### Task 3: The notebook image and its entrypoint

**Files:**
- Create: `infrastructure/jupyterhub/image/Dockerfile`
- Create: `infrastructure/jupyterhub/image/datamap_entrypoint/__init__.py` (empty), `plan.py`
- Create: `infrastructure/jupyterhub/image/entrypoint.py`
- Create: `infrastructure/jupyterhub/image/tests/__init__.py` (empty), `tests/test_plan.py`

**Interfaces:**
- Consumes: the manifest and progress routes (contracts), container environment variables.
- Produces: `plan.copies(manifest) -> list[Copy]` with `Copy(url, destination, size_bytes)`; `plan.first_cell(manifest, kernel) -> dict` (an `.ipynb` document); `plan.lab_locale_settings(locale) -> dict | None`; `plan.human_size(n) -> str`; an entrypoint that leaves `/data` locked, `/home/jovyan/work` and `/outputs` owned by the kernel user, and `exec`s `start.sh`.

- [ ] **Step 1: Failing tests for the pure helpers**

`infrastructure/jupyterhub/image/tests/test_plan.py`:

```python
import json
import uuid

from datamap_entrypoint.plan import (
    copies,
    first_cell,
    human_size,
    lab_locale_settings,
)

DATASET_ID = str(uuid.uuid4())
MANIFEST = {
    "notebook_id": str(uuid.uuid4()),
    "notebook_path": "smps.ipynb",
    "notebook_exists": False,
    "kernel": "python3",
    "outputs_path": "/outputs",
    "datasets": [
        {
            "dataset_id": DATASET_ID,
            "dataset_title": "GoAmazon T3",
            "version_name": "2",
            "mount_path": f"/data/{DATASET_ID}/2",
            "file_count": 2,
            "total_bytes": 300,
            "files": [
                {"id": "a", "name": "a.nc", "size_bytes": 100, "relative_path": "a.nc", "url": "http://m/a"},
                {"id": "b", "name": "q/flags.csv", "size_bytes": 200, "relative_path": "q/flags.csv", "url": "http://m/b"},
            ],
        }
    ],
}


def test_copies_map_each_file_under_the_mount_path():
    plan = copies(MANIFEST)

    assert [(c.url, c.destination, c.size_bytes) for c in plan] == [
        ("http://m/a", f"/data/{DATASET_ID}/2/a.nc", 100),
        ("http://m/b", f"/data/{DATASET_ID}/2/q/flags.csv", 200),
    ]


def test_a_relative_path_cannot_escape_the_mount():
    manifest = json.loads(json.dumps(MANIFEST))
    manifest["datasets"][0]["files"][0]["relative_path"] = "../../etc/passwd"

    try:
        copies(manifest)
    except ValueError as error:
        assert "escapes" in str(error)
    else:
        raise AssertionError("expected a ValueError")


def test_python_first_cell_imports_datamap_and_opens_the_dataset():
    document = first_cell(MANIFEST, "python3")

    source = "".join(document["cells"][0]["source"])
    assert source.startswith("# Generated by DataMap · GoAmazon T3 · v2")
    assert "import datamap" in source
    assert "ds = datamap.open()" in source
    assert f"/data/{DATASET_ID}/2/" in source
    assert document["metadata"]["kernelspec"]["name"] == "python3"
    assert document["nbformat"] == 4


def test_r_first_cell_uses_the_r_package():
    document = first_cell(MANIFEST, "ir")

    source = "".join(document["cells"][0]["source"])
    assert "library(datamap)" in source
    assert "ds <- datamap::open()" in source
    assert document["metadata"]["kernelspec"]["name"] == "ir"
    assert document["metadata"]["kernelspec"]["language"] == "R"


def test_locale_settings_only_for_portuguese():
    assert lab_locale_settings("pt-BR") == {"locale": "pt_BR"}
    assert lab_locale_settings("pt") == {"locale": "pt_BR"}
    assert lab_locale_settings("en") is None


def test_human_size():
    assert human_size(0) == "0 B"
    assert human_size(1536) == "1.5 KB"
    assert human_size(2469606195) == "2.3 GB"
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd infrastructure/jupyterhub && ../../../../../.venv/bin/python -m pytest image/tests`
Expected: FAIL with `ModuleNotFoundError: No module named 'datamap_entrypoint'`

- [ ] **Step 3: Write `plan.py`**

`infrastructure/jupyterhub/image/datamap_entrypoint/plan.py`:

```python
import os
from dataclasses import dataclass

KERNELSPECS = {
    "python3": {"name": "python3", "display_name": "Python 3 (datamap)", "language": "python"},
    "ir": {"name": "ir", "display_name": "R (datamap)", "language": "R"},
}

PYTHON_FIRST_CELL = """# Generated by DataMap · {title} · v{version}
import datamap
ds = datamap.open()            # this notebook's dataset, pinned to v{version}
ds.files                       # {count} files · {mount}/
"""

R_FIRST_CELL = """# Generated by DataMap · {title} · v{version}
library(datamap)
ds <- datamap::open()          # this notebook's dataset, pinned to v{version}
ds$files                       # {count} files · {mount}/
"""


@dataclass(frozen=True)
class Copy:
    url: str
    destination: str
    size_bytes: int


def copies(manifest: dict) -> list[Copy]:
    plan: list[Copy] = []
    for dataset in manifest["datasets"]:
        mount = dataset["mount_path"].rstrip("/")
        for file in dataset["files"]:
            destination = os.path.normpath(os.path.join(mount, file["relative_path"]))
            if destination != mount and not destination.startswith(mount + "/"):
                raise ValueError(f"relative path escapes the mount: {file['relative_path']!r}")
            plan.append(Copy(url=file["url"], destination=destination, size_bytes=file["size_bytes"]))
    return plan


def first_cell(manifest: dict, kernel: str) -> dict:
    dataset = manifest["datasets"][0]
    template = R_FIRST_CELL if kernel == "ir" else PYTHON_FIRST_CELL
    source = template.format(
        title=dataset["dataset_title"],
        version=dataset["version_name"],
        count=dataset["file_count"],
        mount=dataset["mount_path"],
    )
    return {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": source.splitlines(keepends=True),
            }
        ],
        "metadata": {"kernelspec": dict(KERNELSPECS[kernel])},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def lab_locale_settings(locale: str) -> dict | None:
    if (locale or "").lower().startswith("pt"):
        return {"locale": "pt_BR"}
    return None


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
```

Run the tests. Expected: 6 passed.

- [ ] **Step 4: The entrypoint**

`infrastructure/jupyterhub/image/entrypoint.py`:

```python
#!/opt/conda/bin/python
"""Runs as root before the single-user server: materialises the session, then
hands over to jupyter's start.sh, which drops to the kernel user."""

import json
import os
import pwd
import shutil
import sys
import time

import requests

from datamap_entrypoint.plan import copies, first_cell, human_size, lab_locale_settings

API = os.environ["DATAMAP_API_URL"].rstrip("/")
TOKEN = os.environ["DATAMAP_SESSION_TOKEN"]
NOTEBOOK_ID = os.environ["DATAMAP_NOTEBOOK_ID"]
KERNEL = os.environ.get("DATAMAP_KERNEL", "python3")
LOCALE = os.environ.get("DATAMAP_LOCALE", "pt-BR")
NB_USER = os.environ.get("NB_USER", "jovyan")
HOME = f"/home/{NB_USER}"
WORK = f"{HOME}/work"
OUTPUTS = "/outputs"
DATA = "/data"
START_SH = "/usr/local/bin/start.sh"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
CHUNK = 8 * 1024 * 1024


def progress(line: str) -> None:
    print(f"[datamap] {line}", flush=True)
    try:
        requests.post(
            f"{API}/notebooks/{NOTEBOOK_ID}/session/progress",
            json={"line": line[:200]},
            headers=HEADERS,
            timeout=5,
        )
    except requests.RequestException as error:
        print(f"[datamap] progress not delivered: {error}", flush=True)


def fail(line: str) -> None:
    progress(f"Failed: {line}")
    sys.exit(1)


def manifest() -> dict:
    response = requests.get(f"{API}/notebooks/{NOTEBOOK_ID}/manifest", headers=HEADERS, timeout=30)
    if response.status_code != 200:
        fail(f"manifest answered {response.status_code}")
    return response.json()


def owned_dir(path: str, uid: int, gid: int) -> None:
    os.makedirs(path, exist_ok=True)
    os.chown(path, uid, gid)


def download(url: str, destination: str) -> None:
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with requests.get(url, stream=True, timeout=(10, 300)) as response:
        if response.status_code != 200:
            raise RuntimeError(f"{response.status_code} on {destination}")
        with open(destination, "wb") as handle:
            for chunk in response.iter_content(CHUNK):
                handle.write(chunk)


def lock_data() -> None:
    for directory, dirs, files in os.walk(DATA):
        os.chown(directory, 0, 0)
        os.chmod(directory, 0o555)
        for name in files:
            full = os.path.join(directory, name)
            os.chown(full, 0, 0)
            os.chmod(full, 0o444)


def write_lab_locale(uid: int, gid: int) -> None:
    settings = lab_locale_settings(LOCALE)
    if settings is None:
        return
    directory = f"{HOME}/.jupyter/lab/user-settings/@jupyterlab/translation-extension"
    os.makedirs(directory, exist_ok=True)
    path = f"{directory}/plugin.jupyterlab-settings"
    with open(path, "w") as handle:
        json.dump(settings, handle)
    for parent in (f"{HOME}/.jupyter", f"{HOME}/.jupyter/lab", f"{HOME}/.jupyter/lab/user-settings",
                   f"{HOME}/.jupyter/lab/user-settings/@jupyterlab", directory, path):
        os.chown(parent, uid, gid)


def main() -> None:
    user = pwd.getpwnam(NB_USER)
    uid, gid = user.pw_uid, user.pw_gid
    progress("Preparing your session")
    document = manifest()

    owned_dir(WORK, uid, gid)
    owned_dir(OUTPUTS, uid, gid)
    notebook_path = os.path.join(WORK, document["notebook_path"])
    if not document["notebook_exists"] and not os.path.exists(notebook_path):
        with open(notebook_path, "w") as handle:
            json.dump(first_cell(document, KERNEL), handle, indent=1)
        os.chown(notebook_path, uid, gid)
    write_lab_locale(uid, gid)

    plan = copies(document)
    total = sum(copy.size_bytes for copy in plan)
    progress(f"Mounting {len(plan)} files · {human_size(total)}")
    started = time.monotonic()
    done = 0
    for index, copy in enumerate(plan, start=1):
        try:
            download(copy.url, copy.destination)
        except Exception as error:
            fail(f"could not copy {os.path.basename(copy.destination)}: {error}")
        done += copy.size_bytes
        if index % 10 == 0 or index == len(plan):
            progress(f"Copied {index} of {len(plan)} files · {human_size(done)}")
    os.makedirs(DATA, exist_ok=True)
    lock_data()
    elapsed = time.monotonic() - started
    progress(f"Mounted {len(plan)} files · {human_size(total)} in {elapsed:.0f} s")

    if shutil.which("start.sh") is None and not os.path.exists(START_SH):
        fail("start.sh not found in the image")
    os.execv(START_SH, ["start.sh", *sys.argv[1:]])


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: The image**

`infrastructure/jupyterhub/image/Dockerfile`:

```dockerfile
FROM quay.io/jupyter/minimal-notebook:python-3.11

ARG DATAMAP_SDK_VERSION=0.1.0
ARG DATAMAP_R_SDK_REF=r-0.1.0

USER ${NB_UID}

RUN mamba install --yes --channel conda-forge \
      xarray=2024.6 pandas=2.2 netcdf4=1.7 h5netcdf=1.3 matplotlib=3.9 scipy=1.14 openpyxl=3.1 \
      r-base=4.4 r-irkernel=1.3 r-tidyverse=2.0 r-ncdf4=1.22 r-readxl=1.4 r-data.table=1.15 r-remotes=2.5 \
    && mamba clean --all -f -y \
    && fix-permissions "${CONDA_DIR}" \
    && fix-permissions "/home/${NB_USER}"

RUN pip install --no-cache-dir \
      "jupyter-resource-usage==1.1.0" \
      "jupyterlab-language-pack-pt-br==4.2.post2" \
      "datamap==${DATAMAP_SDK_VERSION}"

RUN R -e "remotes::install_github('ardc-brazil/datamap-sdk', ref='${DATAMAP_R_SDK_REF}', subdir='r', upgrade='never')" \
    && R -e "library(datamap)"

RUN python -c "import datamap, xarray, netCDF4, h5netcdf" \
    && jupyter kernelspec list | grep -E "ir|python3"

USER root
COPY --chown=root:root entrypoint.py /opt/datamap/entrypoint.py
COPY --chown=root:root datamap_entrypoint /opt/datamap/datamap_entrypoint
RUN chmod 755 /opt/datamap/entrypoint.py
ENV PYTHONPATH=/opt/datamap

ENTRYPOINT ["tini", "-g", "--", "/opt/conda/bin/python", "/opt/datamap/entrypoint.py"]
CMD ["jupyterhub-singleuser"]
```

The image's `ENTRYPOINT` replaces the base image's `start.sh`; the entrypoint `exec`s it at the end, so everything `start.sh` does (set `NB_UID`, drop privileges, run the command) still happens, after `/data` is in place. DockerSpawner passes `jupyterhub-singleuser` plus its arguments as the container command, which arrive in `sys.argv[1:]`.

Pins: use the versions conda-forge resolves on the day of the build and write them back into the Dockerfile; the ones above are the intent, not a tested solve. `DATAMAP_SDK_VERSION` and `DATAMAP_R_SDK_REF` are what plan 03 publishes; until then build with `--build-arg DATAMAP_SDK_VERSION=` pointing at a test release, or comment the two SDK lines out locally and never commit that.

- [ ] **Step 6: Build and inspect**

```bash
docker build -t datamap-notebook:dev infrastructure/jupyterhub/image
docker run --rm datamap-notebook:dev /opt/conda/bin/python -c "import datamap_entrypoint.plan; print('ok')"
docker run --rm datamap-notebook:dev jupyter kernelspec list
docker images datamap-notebook:dev --format "{{.Size}}"
```

Expected: `ok`; `ir` and `python3` listed; a size in the 4 GB range (the R stack is most of it). Running the image without the `DATAMAP_*` variables exits with a `KeyError`, which is correct: it is only ever started by the hub.

- [ ] **Step 7: Commit**

```bash
git add infrastructure/jupyterhub/image
git commit -m "feat(notebooks): the session image - Python, R, both SDKs and the entrypoint

The entrypoint runs as root before Lab: manifest, first cell, copy into
/data, lock it root:root 0555, report progress, then exec start.sh, which
drops to the kernel user. Read-only is ownership, not a mount flag, because
the same directory has to be written for a few seconds first."
```

---

### Task 4: Compose, Makefile and environment

**Files:**
- Create: `docker-compose-notebooks.yaml`
- Modify: `docker-compose-infrastructure.yaml`, `Makefile`, `Makefile.infra`, `local.env.template`

**Interfaces:**
- Produces: `make ENV_FILE_PATH=... notebooks-run | notebooks-down | notebooks-logs | notebooks-unit`; `make -f Makefile.infra notebooks`; the gatekeeper instances see `/storage` read only.

- [ ] **Step 1: The notebooks stack**

`docker-compose-notebooks.yaml`:

```yaml
version: '3'

x-logging: &logging
  driver: json-file
  options:
    max-size: "20m"
    max-file: "10"

services:
  # The hub never sees the socket: this answers only the calls DockerSpawner
  # makes (containers, images, networks) and refuses the rest.
  docker-socket-proxy:
    image: tecnativa/docker-socket-proxy:0.3.0
    container_name: datamap_docker_socket_proxy
    restart: always
    logging: *logging
    environment:
      - CONTAINERS=1
      - IMAGES=1
      - NETWORKS=1
      - POST=1
      - INFO=1
      - VERSION=1
      - EXEC=0
      - VOLUMES=0
      - SECRETS=0
      - SERVICES=0
      - SWARM=0
      - NODES=0
      - TASKS=0
      - BUILD=0
      - COMMIT=0
      - CONFIGS=0
      - DISTRIBUTION=0
      - PLUGINS=0
      - SYSTEM=0
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - gatekeeper_gatekeeper-network

  jupyterhub:
    build: ./infrastructure/jupyterhub
    image: datamap-hub
    container_name: datamap_jupyterhub
    restart: always
    logging: *logging
    env_file:
      - ${ENV_FILE_PATH}
    environment:
      - DOCKER_HOST=tcp://datamap_docker_socket_proxy:2375
      - NOTEBOOK_STORAGE_HOST_PATH=${STORAGE_DOCKER_VOLUME}
    volumes:
      - hub_data:/srv/jupyterhub/data
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      - docker-socket-proxy
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://127.0.0.1:8000/hub/health"]
      interval: 30s
      start_interval: 2s
      timeout: 5s
      retries: 3
      start_period: 60s
    networks:
      - gatekeeper_gatekeeper-network

volumes:
  hub_data:
    driver: local

networks:
  gatekeeper_gatekeeper-network:
    driver: bridge
    name: gatekeeper_gatekeeper-network
```

`NOTEBOOK_STORAGE_HOST_PATH` is `${STORAGE_DOCKER_VOLUME}`, the same host path MinIO's volume binds, expanded by Compose from the shell — which is why this stack is started through `make` and never with a bare `docker compose` (see `docs/runbooks/host-applied-changes.md`, *Compose needs the variables in the shell*).

- [ ] **Step 2: The gatekeeper's read-only view**

In `docker-compose-infrastructure.yaml`, add to both `gatekeeper` and `gatekeeper_b`:

```yaml
    volumes:
      - storage:/storage:ro
```

The `storage` volume is already declared at the bottom of that file. `NOTEBOOK_STORAGE_PATH` defaults to `/storage/notebooks`, so nothing else changes.

- [ ] **Step 3: Makefile targets**

In `Makefile`, after `observability-check`:

```make
notebooks-run: # Usage: make ENV_FILE_PATH=<decrypted-env> notebooks-run
	@echo "${On_Green}Starting JupyterHub and the docker socket proxy${Color_Off}"
	docker compose -f docker-compose-notebooks.yaml up -d --build

notebooks-down:
	@echo "${On_Green}Stopping JupyterHub (sessions keep running until culled)${Color_Off}"
	docker compose -f docker-compose-notebooks.yaml down

notebooks-logs:
	docker compose -f docker-compose-notebooks.yaml logs --timestamps --no-color --tail 200

notebooks-unit:
	@echo "${On_Green}Hub and entrypoint unit tests${Color_Off}"
	cd infrastructure/jupyterhub && python -m pytest

# Usage: make NOTEBOOK_IMAGE=<image> SMOKE_STORAGE=<host dir> notebooks-smoke
notebooks-smoke:
	@echo "${On_Green}Smoke test: hub + socket proxy + stubbed gatekeeper${Color_Off}"
	mkdir -p $(SMOKE_STORAGE)
	NOTEBOOK_IMAGE=$(NOTEBOOK_IMAGE) SMOKE_STORAGE=$(SMOKE_STORAGE) \
		docker compose -f infrastructure/jupyterhub/smoke/compose.yaml up -d --build --wait --wait-timeout 180
	NOTEBOOK_IMAGE=$(NOTEBOOK_IMAGE) SMOKE_STORAGE=$(SMOKE_STORAGE) \
		python -m pytest infrastructure/jupyterhub/smoke/smoke_test.py -q; status=$$?; \
	NOTEBOOK_IMAGE=$(NOTEBOOK_IMAGE) SMOKE_STORAGE=$(SMOKE_STORAGE) \
		docker compose -f infrastructure/jupyterhub/smoke/compose.yaml down -v; \
	exit $$status
```

The guard at the top of the Makefile refuses to run without an `ENV_FILE_PATH` that exists, unconditionally, and then `include`s and exports it. `notebooks-unit` and `notebooks-smoke` need no environment of their own, so they are run with `ENV_FILE_PATH=local.env.template`: its `CHANGE_ME` values are exported into the shell and ignored, and a variable given on the `make` command line (`NOTEBOOK_IMAGE=...`) wins over one the included file sets. `python` in `notebooks-unit` is whatever is on `PATH`: in CI the setup-python interpreter, locally the venv (`source ../../../.venv/bin/activate` first, or call the target with `PATH=../../../.venv/bin:$PATH`).

In `Makefile.infra`, add `notebooks` to `.PHONY` and to `help`, and the target after `observability`:

```make
notebooks:
	@$(require_host)
	@$(with_env) $(MAKE) ENV_FILE_PATH="$$ENV_FILE_PATH" notebooks-run
	@for i in $$(seq 1 30); do \
		if [ "$$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8000/hub/health)" = "200" ]; then \
			printf "  $(Green)ok$(Off)   hub answers on 127.0.0.1:8000\n"; exit 0; \
		fi; sleep 2; \
	done; printf "  $(Red)FAIL$(Off) the hub never answered /hub/health\n"; exit 1
```

- [ ] **Step 4: Local environment template**

Append to `local.env.template`:

```
# Notebooks hub (RFC 007). The hub shares AUTH_NOTEBOOK_SESSION_TOKEN_SECRET above.
NOTEBOOK_HUB_API_TOKEN=local-hub-api-token-change-me
JUPYTERHUB_CRYPT_KEY=CHANGE_ME_openssl_rand_hex_32
DATAMAP_API_URL=http://gatekeeper:9092/api/v1
DATAMAP_HUB_API_KEY=CHANGE_ME_a_client_key
DATAMAP_HUB_API_SECRET=CHANGE_ME_its_secret
NOTEBOOK_IMAGE=ghcr.io/ardc-brazil/datamap-notebook:latest
NOTEBOOK_SEATS=4
NOTEBOOK_SESSION_MAX_HOURS=12
NOTEBOOK_IDLE_MINUTES=60
NOTEBOOK_SESSION_CPUS=2
NOTEBOOK_SESSION_MEMORY=12g
```

(`AUTH_NOTEBOOK_SESSION_TOKEN_SECRET` and `NOTEBOOK_HUB_API_TOKEN` were added to the template by plan 01 Task 1; keep one line each — remove the plan 01 `NOTEBOOK_HUB_API_TOKEN=` line in favour of this one.)

- [ ] **Step 5: Run the stack locally**

With `local.env` carrying real values (a client created with `POST /clients` for `DATAMAP_HUB_API_KEY/SECRET`, `openssl rand -hex 32` for `JUPYTERHUB_CRYPT_KEY`), and the gatekeeper stack up:

```bash
make ENV_FILE_PATH=local.env notebooks-run
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/hub/health
make ENV_FILE_PATH=local.env notebooks-logs
```

Expected: `200`; the logs show `JupyterHub app:... Hub API listening` and the two services (`idle-culler`, `gatekeeper`) registered, no traceback.

- [ ] **Step 6: Commit**

```bash
git add docker-compose-notebooks.yaml docker-compose-infrastructure.yaml Makefile Makefile.infra local.env.template
git commit -m "feat(notebooks): the hub stack, and the gatekeeper's read-only view of storage

The hub reaches Docker through a socket proxy that allows containers, images
and networks and nothing else. The gatekeeper mounts the storage volume
read-only so it can measure quota and read a notebook without ever being
able to write one."
```

---

### Task 5: nginx

**Files:**
- Modify: `infrastructure/nginx/datamap.conf` (host), `infrastructure/nginx/default.conf` (container)

- [ ] **Step 1: Host configuration**

In `infrastructure/nginx/datamap.conf`, inside the `listen 443 ssl` server block, after the `/files/` (tusd) location:

```nginx
    # jupyterhub, and the single-user servers it proxies under /user/.
    # Websockets for kernels, and a long read timeout: a cell can run for
    # minutes without a byte on the wire.
    location ~ ^/(hub|user)/ {
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Scheme $scheme;
        proxy_buffering off;
        proxy_read_timeout 86400;
        client_max_body_size 64m;
        proxy_pass http://127.0.0.1:8000;
    }
```

- [ ] **Step 2: Container configuration**

In `infrastructure/nginx/default.conf`, the same block with `proxy_pass http://datamap_jupyterhub:8000;` and without `X-Scheme`.

- [ ] **Step 3: Check the syntax without touching the host**

```bash
docker run --rm -v "$PWD/infrastructure/nginx/default.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27 nginx -t
```

Expected: `syntax is ok` and `test is successful`. The host file is validated on the host by `nginx-apply`, which runs `nginx -t` before reloading; the upstream names it references do not resolve in a container.

- [ ] **Step 4: Commit**

```bash
git add infrastructure/nginx/datamap.conf infrastructure/nginx/default.conf
git commit -m "feat(notebooks): route /hub/ and /user/ to the hub, with websockets

Applied on the host by hand, like every nginx change
(docs/runbooks/host-applied-changes.md)."
```

---

### Task 6: The smoke test and the workflows

**Files:**
- Create: `infrastructure/jupyterhub/smoke/compose.yaml`
- Create: `infrastructure/jupyterhub/smoke/wiremock/mappings/manifest.json`, `progress.json`, `internal.json`, `sample_file.json`
- Create: `infrastructure/jupyterhub/smoke/wiremock/__files/sample.nc`
- Create: `infrastructure/jupyterhub/smoke/smoke_test.py`
- Modify: `.github/workflows/ci.yml`
- Create: `.github/workflows/notebook-image.yml`, `.github/workflows/notebooks.yml`

**Interfaces:**
- Consumes: Tasks 1–4; the contracts' manifest, progress and internal routes, which WireMock stubs here.
- Produces: a job that proves the hub spawns a container with the right limits, mounts and ownership, that both kernels and both SDKs are in the image, and that the hub reports `started` and `stopped`.

- [ ] **Step 1: The stubbed gatekeeper**

Fixed identifiers, used by the mappings and the test alike:

```
USER_ID     = 0f3a4c7e-1b2d-4e5f-8a9b-0c1d2e3f4a5b
NOTEBOOK_ID = 7d8e9f0a-1b2c-4d3e-9f4a-5b6c7d8e9f0a
SESSION_ID  = 2a3b4c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d
DATASET_ID  = 9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b
```

`infrastructure/jupyterhub/smoke/wiremock/mappings/manifest.json`:

```json
{
  "request": {
    "method": "GET",
    "urlPath": "/api/v1/notebooks/7d8e9f0a-1b2c-4d3e-9f4a-5b6c7d8e9f0a/manifest",
    "headers": {"Authorization": {"matches": "Bearer .+"}}
  },
  "response": {
    "status": 200,
    "headers": {"Content-Type": "application/json"},
    "jsonBody": {
      "notebook_id": "7d8e9f0a-1b2c-4d3e-9f4a-5b6c7d8e9f0a",
      "notebook_path": "smoke.ipynb",
      "notebook_exists": false,
      "kernel": "python3",
      "outputs_path": "/outputs",
      "datasets": [
        {
          "dataset_id": "9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b",
          "dataset_title": "Smoke dataset",
          "version_name": "1",
          "mount_path": "/data/9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b/1",
          "file_count": 1,
          "total_bytes": 64,
          "files": [
            {
              "id": "c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e5f",
              "name": "sample.nc",
              "size_bytes": 64,
              "relative_path": "sample.nc",
              "url": "http://gatekeeper:8080/files/sample.nc"
            }
          ]
        }
      ]
    }
  }
}
```

`progress.json`:

```json
{
  "request": {
    "method": "POST",
    "urlPath": "/api/v1/notebooks/7d8e9f0a-1b2c-4d3e-9f4a-5b6c7d8e9f0a/session/progress"
  },
  "response": {"status": 204}
}
```

`internal.json`:

```json
{
  "request": {
    "method": "POST",
    "urlPathPattern": "/api/v1/internal/notebook-sessions/2a3b4c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d/(started|stopped)",
    "headers": {"X-Api-Key": {"equalTo": "smoke-hub-key"}}
  },
  "response": {"status": 204}
}
```

`sample_file.json`:

```json
{
  "request": {"method": "GET", "urlPath": "/files/sample.nc"},
  "response": {"status": 200, "bodyFileName": "sample.nc", "headers": {"Content-Type": "application/octet-stream"}}
}
```

`__files/sample.nc`: 64 bytes, any content. Create it with `head -c 64 /dev/urandom > infrastructure/jupyterhub/smoke/wiremock/__files/sample.nc` once and commit it; the test asserts the size, not the content.

- [ ] **Step 2: The smoke stack**

`infrastructure/jupyterhub/smoke/compose.yaml`:

```yaml
services:
  docker-socket-proxy:
    image: tecnativa/docker-socket-proxy:0.3.0
    container_name: datamap_smoke_socket_proxy
    environment:
      - CONTAINERS=1
      - IMAGES=1
      - NETWORKS=1
      - POST=1
      - INFO=1
      - VERSION=1
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - gatekeeper_gatekeeper-network

  gatekeeper:
    image: wiremock/wiremock:3.3.1
    container_name: datamap_smoke_gatekeeper
    command: ["--port", "8080", "--verbose"]
    volumes:
      - ./wiremock/mappings:/home/wiremock/mappings:ro
      - ./wiremock/__files:/home/wiremock/__files:ro
    ports:
      - "127.0.0.1:8089:8080"
    networks:
      gatekeeper_gatekeeper-network:
        aliases:
          - gatekeeper
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/__admin/health"]
      interval: 5s
      timeout: 5s
      retries: 10

  jupyterhub:
    build: ../
    image: datamap-hub:smoke
    container_name: datamap_jupyterhub
    environment:
      - DOCKER_HOST=tcp://datamap_smoke_socket_proxy:2375
      - AUTH_NOTEBOOK_SESSION_TOKEN_SECRET=smoke-session-secret
      - NOTEBOOK_HUB_API_TOKEN=smoke-hub-token
      - JUPYTERHUB_CRYPT_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
      - DATAMAP_API_URL=http://gatekeeper:8080/api/v1
      - DATAMAP_HUB_API_KEY=smoke-hub-key
      - DATAMAP_HUB_API_SECRET=smoke-hub-secret
      - NOTEBOOK_IMAGE=${NOTEBOOK_IMAGE}
      - NOTEBOOK_STORAGE_HOST_PATH=${SMOKE_STORAGE}
      - NOTEBOOK_SEATS=2
      - NOTEBOOK_SESSION_MAX_HOURS=1
      - NOTEBOOK_IDLE_MINUTES=30
      - NOTEBOOK_SESSION_CPUS=1
      - NOTEBOOK_SESSION_MEMORY=2g
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      docker-socket-proxy:
        condition: service_started
      gatekeeper:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://127.0.0.1:8000/hub/health"]
      interval: 5s
      timeout: 5s
      retries: 20
      start_period: 20s
    networks:
      - gatekeeper_gatekeeper-network

networks:
  gatekeeper_gatekeeper-network:
    name: gatekeeper_gatekeeper-network
```

The network name is fixed so the user containers, which the hub attaches to `gatekeeper_gatekeeper-network`, land next to the stubbed gatekeeper. On a machine where the real stack is up this collides on purpose: run the smoke test only where it is not.

- [ ] **Step 3: The test**

`infrastructure/jupyterhub/smoke/smoke_test.py`:

```python
import json
import os
import subprocess
import time

import jwt
import pytest
import requests

HUB = "http://127.0.0.1:8000"
WIREMOCK = "http://127.0.0.1:8089/__admin"
SECRET = "smoke-session-secret"
HUB_TOKEN = "smoke-hub-token"
USER_ID = "0f3a4c7e-1b2d-4e5f-8a9b-0c1d2e3f4a5b"
NOTEBOOK_ID = "7d8e9f0a-1b2c-4d3e-9f4a-5b6c7d8e9f0a"
SESSION_ID = "2a3b4c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d"
DATASET_ID = "9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b"
CONTAINER = f"datamap-notebook-{USER_ID}"
STORAGE = os.environ["SMOKE_STORAGE"]


def token(**overrides) -> str:
    now = int(time.time())
    payload = {
        "iss": "gatekeeper",
        "aud": "notebook_session",
        "sub": USER_ID,
        "tenancies": ["smoke"],
        "notebook_id": NOTEBOOK_ID,
        "session_id": SESSION_ID,
        "datasets": [{"id": DATASET_ID, "version": "1"}],
        "kernel": "python3",
        "locale": "pt-BR",
        "iat": now,
        "exp": now + 3600,
    }
    payload.update(overrides)
    return jwt.encode(payload, SECRET, algorithm="HS256")


def docker(*args: str) -> str:
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True).stdout.strip()


def in_container(*command: str) -> str:
    return docker("exec", CONTAINER, *command)


def wiremock_count(method: str, path: str) -> int:
    response = requests.post(
        f"{WIREMOCK}/requests/count", json={"method": method, "urlPath": path}, timeout=10
    )
    return response.json()["count"]


def server_ready() -> bool:
    response = requests.get(
        f"{HUB}/hub/api/users/{USER_ID}", headers={"Authorization": f"token {HUB_TOKEN}"}, timeout=10
    )
    if response.status_code != 200:
        return False
    server = response.json().get("servers", {}).get("")
    return bool(server and server.get("ready"))


@pytest.fixture(scope="module")
def session() -> requests.Session:
    browser = requests.Session()
    response = browser.post(
        f"{HUB}/hub/login",
        data={"token": token(), "next": f"/user/{USER_ID}/lab"},
        allow_redirects=False,
        timeout=30,
    )
    assert response.status_code == 302, response.text
    assert any(c.startswith("jupyterhub") for c in browser.cookies.keys())
    deadline = time.time() + 600
    while time.time() < deadline:
        if server_ready():
            break
        time.sleep(5)
    else:
        print(docker("logs", "--tail", "100", "datamap_jupyterhub"))
        raise AssertionError("the single-user server never became ready")
    yield browser
    requests.delete(
        f"{HUB}/hub/api/users/{USER_ID}/server",
        headers={"Authorization": f"token {HUB_TOKEN}"},
        timeout=30,
    )


def test_a_bad_token_does_not_log_in():
    response = requests.post(
        f"{HUB}/hub/login", data={"token": token() + "x"}, allow_redirects=False, timeout=30
    )
    assert response.status_code != 302
    assert not any(c.startswith("jupyterhub-hub-login") for c in response.cookies.keys())


def test_the_container_carries_the_limits(session):
    inspect = json.loads(docker("inspect", CONTAINER))[0]["HostConfig"]
    assert inspect["Memory"] == 2 * 1024**3
    assert inspect["MemorySwap"] == 2 * 1024**3
    assert inspect["NanoCpus"] == 1_000_000_000
    assert inspect["PidsLimit"] == 256
    assert inspect["CapDrop"] == ["ALL"]
    assert "no-new-privileges:true" in inspect["SecurityOpt"]


def test_data_is_mounted_and_locked(session):
    assert in_container("stat", "-c", "%U:%a", "/data") == "root:555"
    path = f"/data/{DATASET_ID}/1/sample.nc"
    assert in_container("stat", "-c", "%U:%a:%s", path) == "root:444:64"
    assert in_container("stat", "-c", "%U", "/home/jovyan/work") == "jovyan"
    assert in_container("stat", "-c", "%U", "/outputs") == "jovyan"


def test_the_first_cell_was_written_for_the_new_notebook(session):
    document = json.loads(in_container("cat", "/home/jovyan/work/smoke.ipynb"))
    source = "".join(document["cells"][0]["source"])
    assert "import datamap" in source
    assert "Smoke dataset" in source


def test_both_kernels_and_both_sdks_are_present(session):
    kernels = in_container("jupyter", "kernelspec", "list")
    assert "python3" in kernels and "ir" in kernels
    assert in_container("python", "-c", "import datamap; print('py')") == "py"
    assert "r" in in_container("Rscript", "-e", "library(datamap); cat('r')")


def test_the_lab_locale_follows_the_token(session):
    settings = in_container(
        "cat", "/home/jovyan/.jupyter/lab/user-settings/@jupyterlab/translation-extension/plugin.jupyterlab-settings"
    )
    assert json.loads(settings) == {"locale": "pt_BR"}


def test_the_hub_reported_started_and_progress(session):
    assert wiremock_count("POST", f"/api/v1/internal/notebook-sessions/{SESSION_ID}/started") == 1
    assert wiremock_count("POST", f"/api/v1/notebooks/{NOTEBOOK_ID}/session/progress") >= 3


def test_the_lab_answers_through_the_hub(session):
    response = session.get(f"{HUB}/user/{USER_ID}/api/status", timeout=30)
    assert response.status_code == 200
    assert "kernels" in response.json()


def test_stopping_reports_stopped_and_removes_the_container(session):
    response = requests.delete(
        f"{HUB}/hub/api/users/{USER_ID}/server",
        headers={"Authorization": f"token {HUB_TOKEN}"},
        timeout=30,
    )
    assert response.status_code in (202, 204)
    deadline = time.time() + 120
    while time.time() < deadline:
        running = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name={CONTAINER}"], capture_output=True, text=True
        ).stdout.strip()
        if not running and wiremock_count("POST", f"/api/v1/internal/notebook-sessions/{SESSION_ID}/stopped") == 1:
            return
        time.sleep(3)
    raise AssertionError("the container is still up or the stop was never reported")


def test_the_session_directory_is_on_the_host():
    assert os.path.isfile(f"{STORAGE}/sessions/{SESSION_ID}/data/{DATASET_ID}/1/sample.nc")
    assert os.path.isfile(f"{STORAGE}/notebooks/{USER_ID}/smoke.ipynb")
```

- [ ] **Step 4: Run it locally**

Stop the local gatekeeper stack first if it is up (the network name collides). Then:

```bash
make ENV_FILE_PATH=local.env.template NOTEBOOK_IMAGE=datamap-notebook:dev SMOKE_STORAGE=/tmp/datamap-smoke notebooks-smoke
```

Expected: 10 passed, then the stack comes down. On a failure, `docker logs datamap_jupyterhub` and `docker logs datamap-notebook-<USER_ID>` (if still there) say which step the entrypoint reached; the progress lines are also in WireMock's request journal at `http://127.0.0.1:8089/__admin/requests`.

Make it fail first: set `NOTEBOOK_SESSION_MEMORY=1g` in the smoke compose, run, watch `test_the_container_carries_the_limits` fail, revert.

- [ ] **Step 5: CI job**

In `.github/workflows/ci.yml`, after the `integration` job and before `deploy` (do not add it to `deploy`'s `needs`: the gatekeeper deploy must not wait on the hub's image registry):

```yaml
  notebooks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Hub and entrypoint unit tests
        run: make ENV_FILE_PATH=local.env.template notebooks-unit

      # The session image is 4 GB and built by notebook-image.yml; here it is
      # pulled, not built. The hub image is small and built from this checkout.
      - name: Pull the session image
        run: docker pull ghcr.io/${{ github.repository_owner }}/datamap-notebook:latest

      - name: Smoke test
        run: |
          make ENV_FILE_PATH=local.env.template \
               NOTEBOOK_IMAGE=ghcr.io/${{ github.repository_owner }}/datamap-notebook:latest \
               SMOKE_STORAGE="${{ runner.temp }}/notebooks" \
               notebooks-smoke

      - name: Logs on failure
        if: failure()
        run: |
          docker logs datamap_jupyterhub 2>&1 | tail -200 || true
          docker logs datamap-notebook-0f3a4c7e-1b2d-4e5f-8a9b-0c1d2e3f4a5b 2>&1 | tail -100 || true
          curl -s http://127.0.0.1:8089/__admin/requests | head -c 20000 || true
```

The GHCR package must be public for an unauthenticated pull; the image workflow's last step says so, as the MinIO mirror's does.

- [ ] **Step 6: The image workflow**

`.github/workflows/notebook-image.yml`:

```yaml
name: notebook image

# The session image is 4 GB; it is built when its definition changes and
# pulled everywhere else. The smoke test runs against the image just pushed
# before it is tagged latest.
on:
  push:
    branches: [main]
    paths:
      - infrastructure/jupyterhub/image/**
      - .github/workflows/notebook-image.yml
  workflow_dispatch:
    inputs:
      sdk_version:
        description: datamap SDK version on PyPI
        required: false
      r_sdk_ref:
        description: datamap R package git ref
        required: false

concurrency:
  group: notebook-image
  cancel-in-progress: false

env:
  IMAGE: ghcr.io/${{ github.repository_owner }}/datamap-notebook

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      packages: write
      contents: read
    outputs:
      tag: ${{ steps.meta.outputs.tag }}
    steps:
      - uses: actions/checkout@v4

      - id: meta
        run: echo "tag=$(date -u +%Y%m%d)-${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"

      - uses: docker/setup-buildx-action@v3

      - name: Sign in to the registry
        run: |
          echo "${{ secrets.GITHUB_TOKEN }}" \
            | docker login ghcr.io -u "${{ github.actor }}" --password-stdin

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: infrastructure/jupyterhub/image
          push: true
          tags: ${{ env.IMAGE }}:${{ steps.meta.outputs.tag }}
          build-args: |
            DATAMAP_SDK_VERSION=${{ inputs.sdk_version || '0.1.0' }}
            DATAMAP_R_SDK_REF=${{ inputs.r_sdk_ref || 'r-0.1.0' }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Sign out
        if: always()
        run: docker logout ghcr.io || true

  smoke:
    needs: [build]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
          cache: pip
      - run: pip install -r requirements.txt
      - name: Smoke test the new image
        run: |
          make ENV_FILE_PATH=local.env.template \
               NOTEBOOK_IMAGE=${{ env.IMAGE }}:${{ needs.build.outputs.tag }} \
               SMOKE_STORAGE="${{ runner.temp }}/notebooks" \
               notebooks-smoke

  promote:
    needs: [build, smoke]
    runs-on: ubuntu-latest
    permissions:
      packages: write
    steps:
      - name: Sign in to the registry
        run: |
          echo "${{ secrets.GITHUB_TOKEN }}" \
            | docker login ghcr.io -u "${{ github.actor }}" --password-stdin
      - name: Tag the smoke-tested image as latest
        run: |
          docker pull ${{ env.IMAGE }}:${{ needs.build.outputs.tag }}
          docker tag ${{ env.IMAGE }}:${{ needs.build.outputs.tag }} ${{ env.IMAGE }}:latest
          docker push ${{ env.IMAGE }}:latest
          echo "Pin NOTEBOOK_IMAGE=${{ env.IMAGE }}:${{ needs.build.outputs.tag }} in secrets/production/gatekeeper.env"
          echo "The package starts private: make it public under github.com/orgs/${{ github.repository_owner }}/packages"
      - name: Sign out
        if: always()
        run: docker logout ghcr.io || true
```

Production pins a dated tag in the encrypted env, never `latest`; `latest` exists for CI.

- [ ] **Step 7: The apply workflow**

`.github/workflows/notebooks.yml`, modelled on `observability.yml`:

```yaml
name: notebooks

# The hub holds sessions people are working in; it moves only when its own
# configuration does, never with the application deploy.
on:
  push:
    branches: [main]
    paths:
      - docker-compose-notebooks.yaml
      - infrastructure/jupyterhub/datamap_hub/**
      - infrastructure/jupyterhub/jupyterhub_config.py
      - infrastructure/jupyterhub/Dockerfile
      - infrastructure/jupyterhub/requirements.txt
      - .github/workflows/notebooks.yml

concurrency:
  group: notebooks-production
  cancel-in-progress: false

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
          cache: pip
      - run: pip install -r requirements.txt
      - run: make ENV_FILE_PATH=local.env.template notebooks-unit

  apply:
    needs: [validate]
    # Never `pull_request`: code from a fork must not run on the production host.
    runs-on: [self-hosted, production]
    environment: production
    env:
      COMPOSE_PROJECT_NAME: gatekeeper
    steps:
      - uses: actions/checkout@v4

      - name: Show what is being applied
        run: git log --oneline -1

      - name: Install the pinned sops
        run: bash scripts/install_sops.sh

      - name: Decrypt the environment
        run: |
          umask 077
          mkdir -p "$RUNNER_TEMP/env"
          "$HOME/bin/sops" --decrypt secrets/production/gatekeeper.env \
            > "$RUNNER_TEMP/env/gatekeeper.env"
          echo "ENV_FILE_PATH=$RUNNER_TEMP/env/gatekeeper.env" >> "$GITHUB_ENV"
        env:
          SOPS_AGE_KEY_FILE: /home/datamap/.config/sops/age/keys.txt

      # Recreating the hub does not touch the session containers
      # (cleanup_servers is off); the spawner reloads their state on start.
      - name: Apply
        run: make ENV_FILE_PATH="$ENV_FILE_PATH" notebooks-run

      - name: The hub must answer
        run: |
          for _ in $(seq 1 30); do
            code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/hub/health || true)
            if [ "$code" = "200" ]; then echo "hub healthy"; exit 0; fi
            sleep 2
          done
          docker logs --tail 100 datamap_jupyterhub
          exit 1

      - name: Remove the decrypted environment
        if: always()
        run: rm -rf "$RUNNER_TEMP/env"

      - name: Logs on failure
        if: failure()
        run: docker logs --tail 100 datamap_jupyterhub 2>&1 || true
```

- [ ] **Step 8: Lint the workflows and commit**

Run: `actionlint` if installed (the `lint` job runs it: check `.github/workflows/ci.yml` lines 40–46 for the exact command and run the same), else rely on CI.

```bash
git add infrastructure/jupyterhub/smoke .github/workflows/ci.yml .github/workflows/notebook-image.yml .github/workflows/notebooks.yml
git commit -m "test(notebooks): smoke test the hub against a stubbed gatekeeper, in CI

It proves the things a unit test cannot: the cgroup limits on the real
container, /data locked root:root, both kernels and SDKs in the image, the
started and stopped reports. The session image is built by its own workflow
and pulled here; the hub image is built from the checkout."
```

---

### Task 7: Observability

**Files:**
- Modify: `infrastructure/prometheus/prometheus.yml`, `alerts.yml`, `alerts_test.yml`
- Create: `infrastructure/grafana/dashboards/Business/notebooks.json`

- [ ] **Step 1: Scrape the hub, keep the session containers**

In `infrastructure/prometheus/prometheus.yml`, after the `archivist` job:

```yaml
  # JupyterHub's own counters: spawns, their duration, running servers.
  - job_name: jupyterhub
    metrics_path: /hub/metrics
    static_configs:
      - targets: ["datamap_jupyterhub:8000"]
```

and in the `cadvisor` job change the keep regex so session containers are stored too:

```yaml
      - source_labels: [name]
        regex: "datamap[_-].*"
        action: keep
```

- [ ] **Step 2: The alert, test first**

Append to `infrastructure/prometheus/alerts_test.yml`:

```yaml
  - interval: 1m
    name: seats refused for an hour alert
    input_series:
      - series: 'datamap_notebook_session_requests_total{outcome="no_seats",job="gatekeeper"}'
        values: "0+1x90"
    alert_rule_test:
      - eval_time: 90m
        alertname: NotebookSeatsExhausted
        exp_alerts:
          - exp_labels:
              severity: warning
              outcome: no_seats
              job: gatekeeper
            exp_annotations:
              summary: "People have been refused a notebook seat for an hour"
              description: >-
                Every seat has been taken for an hour and someone keeps asking.
                Either the envelope is too small or the idle timeout too long;
                docs/runbooks/notebooks.md says how to tell.

  - interval: 1m
    name: one refusal does not alert
    input_series:
      - series: 'datamap_notebook_session_requests_total{outcome="no_seats",job="gatekeeper"}'
        values: "0 0 1+0x120"
    alert_rule_test:
      - eval_time: 60m
        alertname: NotebookSeatsExhausted
        exp_alerts: []
```

Run: `make ENV_FILE_PATH=local.env.template observability-check`
Expected: the new tests FAIL (`alertname NotebookSeatsExhausted does not exist`).

Append to `infrastructure/prometheus/alerts.yml`, in the `datamap` group:

```yaml
      - alert: NotebookSeatsExhausted
        # A 30m window with for: 1h: a lone refusal is true for 30 minutes and
        # never fires; refusals that keep coming for an hour do.
        expr: increase(datamap_notebook_session_requests_total{outcome="no_seats"}[30m]) > 0
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "People have been refused a notebook seat for an hour"
          description: >-
            Every seat has been taken for an hour and someone keeps asking.
            Either the envelope is too small or the idle timeout too long;
            docs/runbooks/notebooks.md says how to tell.
```

Run `observability-check` again. Expected: all rule tests pass and the config is valid.

- [ ] **Step 3: The dashboard**

`infrastructure/grafana/dashboards/Business/notebooks.json`:

```json
{
  "id": null,
  "uid": "datamap-notebooks",
  "title": "Business — Notebooks",
  "description": "Sessions, seats, how they end, and what the session containers cost. RFC 007.",
  "tags": ["datamap", "business", "notebooks"],
  "timezone": "browser",
  "editable": false,
  "graphTooltip": 1,
  "refresh": "1m",
  "schemaVersion": 39,
  "version": 1,
  "time": {"from": "now-24h", "to": "now"},
  "timepicker": {},
  "templating": {"list": []},
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": {"type": "grafana", "uid": "-- Grafana --"},
        "enable": true,
        "hide": true,
        "iconColor": "rgba(0, 211, 255, 1)",
        "name": "Annotations & Alerts",
        "type": "dashboard"
      }
    ]
  },
  "links": [
    {"type": "dashboards", "tags": ["datamap"], "asDropdown": true, "title": "DataMap", "includeVars": false, "keepTime": true}
  ],
  "panels": [
    {
      "id": 1,
      "type": "stat",
      "title": "Sessions live",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"x": 0, "y": 0, "w": 4, "h": 4},
      "targets": [
        {"refId": "A", "datasource": {"type": "prometheus", "uid": "prometheus"}, "expr": "sum(datamap_notebook_sessions_active)", "instant": true, "range": false, "legendFormat": ""}
      ],
      "fieldConfig": {"defaults": {"unit": "short", "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}, {"color": "orange", "value": 3}, {"color": "red", "value": 4}]}, "color": {"mode": "thresholds"}}, "overrides": []},
      "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": false}, "colorMode": "value", "graphMode": "area", "textMode": "auto", "justifyMode": "auto", "orientation": "auto"}
    },
    {
      "id": 2,
      "type": "stat",
      "title": "Seats refused, 24h",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"x": 4, "y": 0, "w": 4, "h": 4},
      "targets": [
        {"refId": "A", "datasource": {"type": "prometheus", "uid": "prometheus"}, "expr": "sum(increase(datamap_notebook_session_requests_total{outcome=\"no_seats\"}[24h]))", "instant": true, "range": false, "legendFormat": ""}
      ],
      "fieldConfig": {"defaults": {"unit": "short", "decimals": 0, "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}, {"color": "red", "value": 1}]}, "color": {"mode": "thresholds"}}, "overrides": []},
      "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": false}, "colorMode": "value", "graphMode": "none", "textMode": "auto", "justifyMode": "auto", "orientation": "auto"}
    },
    {
      "id": 3,
      "type": "timeseries",
      "title": "Live sessions by kernel",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"x": 8, "y": 0, "w": 16, "h": 8},
      "targets": [
        {"refId": "A", "datasource": {"type": "prometheus", "uid": "prometheus"}, "expr": "datamap_notebook_sessions_active", "legendFormat": "{{kernel}}"}
      ],
      "fieldConfig": {"defaults": {"unit": "short", "decimals": 0, "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 20, "stacking": {"mode": "normal"}}, "color": {"mode": "palette-classic"}}, "overrides": []},
      "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": true}, "tooltip": {"mode": "multi", "sort": "none"}}
    },
    {
      "id": 4,
      "type": "timeseries",
      "title": "Start requests by outcome, per hour",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"x": 0, "y": 8, "w": 12, "h": 8},
      "targets": [
        {"refId": "A", "datasource": {"type": "prometheus", "uid": "prometheus"}, "expr": "sum by (outcome) (increase(datamap_notebook_session_requests_total[1h]))", "legendFormat": "{{outcome}}"}
      ],
      "fieldConfig": {"defaults": {"unit": "short", "decimals": 0, "custom": {"drawStyle": "bars", "lineWidth": 1, "fillOpacity": 60, "stacking": {"mode": "normal"}}, "color": {"mode": "palette-classic"}}, "overrides": []},
      "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": true}, "tooltip": {"mode": "multi", "sort": "none"}}
    },
    {
      "id": 5,
      "type": "timeseries",
      "title": "How sessions end, per day",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"x": 12, "y": 8, "w": 12, "h": 8},
      "targets": [
        {"refId": "A", "datasource": {"type": "prometheus", "uid": "prometheus"}, "expr": "sum by (stop_reason) (increase(datamap_notebook_session_duration_seconds_count[1d]))", "legendFormat": "{{stop_reason}}"}
      ],
      "fieldConfig": {"defaults": {"unit": "short", "decimals": 0, "custom": {"drawStyle": "bars", "lineWidth": 1, "fillOpacity": 60, "stacking": {"mode": "normal"}}, "color": {"mode": "palette-classic"}}, "overrides": []},
      "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": true}, "tooltip": {"mode": "multi", "sort": "none"}}
    },
    {
      "id": 6,
      "type": "timeseries",
      "title": "Session length, p50 and p90 over a day",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"x": 0, "y": 16, "w": 12, "h": 8},
      "targets": [
        {"refId": "A", "datasource": {"type": "prometheus", "uid": "prometheus"}, "expr": "histogram_quantile(0.5, sum by (le) (rate(datamap_notebook_session_duration_seconds_bucket[1d])))", "legendFormat": "p50"},
        {"refId": "B", "datasource": {"type": "prometheus", "uid": "prometheus"}, "expr": "histogram_quantile(0.9, sum by (le) (rate(datamap_notebook_session_duration_seconds_bucket[1d])))", "legendFormat": "p90"}
      ],
      "fieldConfig": {"defaults": {"unit": "s", "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 0}, "color": {"mode": "palette-classic"}}, "overrides": []},
      "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": true}, "tooltip": {"mode": "multi", "sort": "none"}}
    },
    {
      "id": 7,
      "type": "timeseries",
      "title": "Session containers: CPU cores in use",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"x": 12, "y": 16, "w": 12, "h": 8},
      "targets": [
        {"refId": "A", "datasource": {"type": "prometheus", "uid": "prometheus"}, "expr": "sum by (name) (rate(container_cpu_usage_seconds_total{name=~\"datamap-notebook-.*\"}[5m]))", "legendFormat": "{{name}}"}
      ],
      "fieldConfig": {"defaults": {"unit": "short", "decimals": 2, "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 10, "stacking": {"mode": "normal"}}, "color": {"mode": "palette-classic"}}, "overrides": []},
      "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": true}, "tooltip": {"mode": "multi", "sort": "none"}}
    },
    {
      "id": 8,
      "type": "timeseries",
      "title": "Session containers: memory",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"x": 0, "y": 24, "w": 24, "h": 8},
      "targets": [
        {"refId": "A", "datasource": {"type": "prometheus", "uid": "prometheus"}, "expr": "container_memory_working_set_bytes{name=~\"datamap-notebook-.*\"}", "legendFormat": "{{name}}"}
      ],
      "fieldConfig": {"defaults": {"unit": "bytes", "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 10}, "color": {"mode": "palette-classic"}}, "overrides": []},
      "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": true}, "tooltip": {"mode": "multi", "sort": "none"}}
    }
  ]
}
```

Run: `../../../.venv/bin/python -m pytest app/grafana_dashboards_test.py -q`
Expected: all passed (the three `datamap_notebook_*` metrics are declared by plan 01's `app/metrics.py`; `container_*` names are not checked).

- [ ] **Step 4: Commit**

```bash
git add infrastructure/prometheus/prometheus.yml infrastructure/prometheus/alerts.yml \
  infrastructure/prometheus/alerts_test.yml infrastructure/grafana/dashboards/Business/notebooks.json
git commit -m "feat(notebooks): scrape the hub, keep session containers in cadvisor, one alert, one dashboard

The alert is the signal the RFC asked for: refusals that keep coming for an
hour mean the envelope is too small or the idle timeout too long. A lone
refusal, which four seats will produce, does not page anyone."
```

---

### Task 8: Runbook, links and the RFC

**Files:**
- Create: `docs/runbooks/notebooks.md`
- Modify: `README.md`, `docs/README.md`, `docs/rfcs/007-notebooks.md`

- [ ] **Step 1: The runbook**

`docs/runbooks/notebooks.md`:

```markdown
# Notebooks

JupyterHub runs as `datamap_jupyterhub`, one container per session named
`datamap-notebook-<user id>`, all on the gatekeeper's docker network. The hub
is not part of the application deploy: `.github/workflows/notebooks.yml`
applies it when its own configuration changes, and `make -f Makefile.infra
notebooks` does the same by hand. The design is RFC 007.

## First start

1. Create a client for the hub: `POST /api/v1/clients` through Swagger, name
   `jupyterhub`. Put its key and secret in `secrets/production/gatekeeper.env`
   as `DATAMAP_HUB_API_KEY` and `DATAMAP_HUB_API_SECRET`.
2. Add to the same file, with `sops`:
   `AUTH_NOTEBOOK_SESSION_TOKEN_SECRET` (`openssl rand -base64 32`),
   `NOTEBOOK_HUB_API_TOKEN` (`openssl rand -hex 32`),
   `JUPYTERHUB_CRYPT_KEY` (`openssl rand -hex 32`),
   `DATAMAP_API_URL=http://gatekeeper:9092/api/v1`,
   `NOTEBOOK_IMAGE=ghcr.io/ardc-brazil/datamap-notebook:<dated tag>`,
   `NOTEBOOK_SEATS=4`, `NOTEBOOK_SESSION_MAX_HOURS=12`,
   `NOTEBOOK_IDLE_MINUTES=60`, `NOTEBOOK_SESSION_CPUS=2`,
   `NOTEBOOK_SESSION_MEMORY=12g`.
   The gatekeeper reads the first two and `NOTEBOOK_SEATS`,
   `NOTEBOOK_SESSION_MAX_HOURS`; the hub reads all of them. They must agree,
   which is why they live in one file.
3. Merge, let the deploy roll the gatekeeper (it now mounts the storage
   volume read-only at `/storage`), then:
   `make -f Makefile.infra notebooks` and `make -f Makefile.infra nginx-apply`.
4. Check: `curl -s -o /dev/null -w "%{http_code}" https://datamap.pcs.usp.br/hub/health`
   answers 200, and `GET /api/v1/notebooks/-/capacity` with an admin's
   headers answers seats `0/4`.

## Where things are

| What | Where |
|---|---|
| Notebook files | `${STORAGE_DOCKER_VOLUME}/notebooks/<user id>/` on the host |
| Outputs | `.../notebooks/<user id>/.outputs/<notebook id>/`, purged 24 h after the last session by the archivist |
| Session data copies | `.../sessions/<session id>/data/`, deleted by the archivist once the session is over |
| Hub state | docker volume `gatekeeper_hub_data` (SQLite). Disposable: the record is `notebook_sessions` in PostgreSQL |
| Session record | `notebook_sessions`, append-only |

## Seats

`NOTEBOOK_SEATS` in the env, read by both the gatekeeper (the transaction that
hands out a seat) and the hub (`active_server_limit`, the second fence).
Changing it is a commit to the encrypted env, a gatekeeper roll and a hub
apply. Who holds the seats right now:

```sql
SELECT s.user_id, u.name, s.dataset_id, s.kernel, s.started_at
FROM notebook_sessions s JOIN users u ON u.id = s.user_id
WHERE s.state IN ('starting', 'running') ORDER BY s.started_at;
```

The `NotebookSeatsExhausted` alert fires after an hour of refusals. If the
sessions holding the seats are idle on the dashboard (no CPU), shorten
`NOTEBOOK_IDLE_MINUTES`; if they are busy, the envelope is the limit and
RFC 007's arithmetic says what a fifth seat costs.

## Stopping a session by hand

Through the hub, with the token from the env:

```bash
curl -X DELETE -H "Authorization: token $NOTEBOOK_HUB_API_TOKEN" \
  http://127.0.0.1:8000/hub/api/users/<user id>/server
```

The hub reports the stop to the gatekeeper, which records it as `idle`
(it cannot tell an operator's stop from the culler's). To record it as
`admin`, use the gatekeeper's `DELETE /api/v1/notebooks/<id>/session` as the
owner through Swagger instead; the admin route proper is increment D.

## Logs

The hub and every session container log to Loki like any other container:
`{container="datamap_jupyterhub"}` and `{container=~"datamap-notebook-.*"}`.
The entrypoint's lines start with `[datamap]`; the same lines are in the
session's `progress` on `GET /api/v1/notebooks/<id>/session`.

## Updating the session image

Push a change under `infrastructure/jupyterhub/image/`; the `notebook image`
workflow builds, smoke-tests and pushes a dated tag, then `latest`. Pin the
dated tag in the env and apply the hub. Running sessions keep their image;
the next start uses the new one. The package on GHCR must be public, or
nothing can pull it.

## What this does not do yet

- Outbound traffic from a session is not filtered. `pip install` and
  `install.packages` work, and so does anything else. A filtering proxy is
  the follow-up recorded in RFC 007.
- The administration page is increment D. Until then: this runbook, Swagger
  and Grafana.

## When it breaks

- **"Starting" never ends, then fails.** `docker logs datamap-notebook-<uid>`:
  the entrypoint says which step. A manifest 401 means the session row is not
  live (stopped meanwhile) or the secrets differ between hub and gatekeeper.
  A copy error names the file; check MinIO and the pre-signed URL's host.
- **The hub answers but sessions never spawn.** `docker logs datamap_jupyterhub`
  for `docker.errors`; the socket proxy allows containers, images and
  networks only, and a new DockerSpawner version may need another endpoint.
- **A session container is running but the gatekeeper says `stopped`.** The
  hub's `stopped` report reached the gatekeeper for a container that then
  came back, or the hub was recreated with `cleanup_servers` on. Stop it by
  hand (above) and start again.
- **`/data` is writable or owned by jovyan.** The entrypoint did not run as
  root: `extra_create_kwargs={"user": "root"}` is missing from the hub config.
```

- [ ] **Step 2: Links**

In `README.md`, in the production URLs list next to Grafana:

```markdown
* Notebooks: `https://datamap.pcs.usp.br/hub/` — JupyterHub; opened from the webapp, not directly
```

In `docs/README.md`, add `| [007](rfcs/007-notebooks.md) | Notebooks | Draft |` to the RFC table.

- [ ] **Step 3: Amend the RFC**

In `docs/rfcs/007-notebooks.md`:

1. *Components*: replace "The hub's own state goes in a `jupyterhub` database on the existing PostgreSQL, so the backup timer from the database runbook covers it without a second mechanism." with "The hub's own state is SQLite on a named volume. The backup script dumps one database by name, and the hub's state is not a record: `notebook_sessions` is. Losing the volume means sessions re-login; nothing is lost that the gatekeeper does not hold."
2. *Limits* table, the Network row: "Not restricted in increment A. `pip install` and `install.packages` work, and so does any other outbound call. A filtering proxy for PyPI and CRAN only is the follow-up." Add the same to *Open questions*.
3. *Session lifecycle*: the "Starting" screen gets its lines from the entrypoint's progress reports (plan 01's amendment already says so; confirm it is there).
4. *Observability*: add "JupyterHub's own `/hub/metrics` is scraped as job `jupyterhub`; cadvisor keeps `datamap-notebook-*` containers."
5. *Testing*, the hub smoke test bullet: describe what Task 6 runs: form login, container limits, `/data` ownership, both kernels and SDKs, started and stopped reports against a stubbed gatekeeper.

Update the header's `Updated` date.

- [ ] **Step 4: Validation and pull request**

```bash
make ENV_FILE_PATH=local.env.template notebooks-unit
make ENV_FILE_PATH=local.env.template observability-check
../../../.venv/bin/python -m pytest app/grafana_dashboards_test.py -q
ruff check && ruff format
```

Expected: all green. Then commit, push and open the PR with the attribution in the system reminder:

```bash
git add docs/runbooks/notebooks.md README.md docs/README.md docs/rfcs/007-notebooks.md
git commit -m "docs(notebooks): runbook for the hub, and RFC 007 amended for SQLite and egress"
git push -u origin HEAD
gh pr create --title "feat(notebooks): JupyterHub, session image and host routing for RFC 007" --body "$(cat <<'EOF'
## Summary
- hub: token login by form POST, DockerSpawner subclass with the limits table, started/stopped reports, idle culler
- session image: Python 3.11 + R, both SDKs, entrypoint that materialises /data from the manifest and locks it
- compose for the hub and socket proxy; the gatekeeper mounts storage read-only
- nginx /hub/ and /user/ with websockets (host file applied by hand)
- smoke test in CI against a stubbed gatekeeper; image workflow on GHCR; apply workflow on the host
- hub scraped, one alert, one dashboard, a runbook

Spec: docs/rfcs/007-notebooks.md. Contracts: docs/superpowers/plans/2026-10-04-notebooks-00-contracts.md.

## Test plan
- [ ] `notebooks-unit` green
- [ ] smoke test green in CI with the GHCR image
- [ ] `observability-check` and the dashboard test green
- [ ] after merge: `make -f Makefile.infra notebooks`, `nginx-apply`, `/hub/health` 200 through nginx

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
