# Notebooks — Archivist Purge Implementation Plan (04)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Where the code goes.** This plan lives in the gatekeeper repo with the other notebook plans, but every file it changes is in the **archivist repo, `/Users/caio.maia/workspace/datamap/archivist`**, except Task 5's one line in the gatekeeper's `infrastructure/grafana/external-metrics.txt`. Paths are relative to the archivist repo root unless a task says otherwise. Work in a git worktree of the archivist repo on branch `feat/notebook-purge`, created from `origin/main`; never in the main checkout.

**Verified against:** archivist `main` at `57ca8fd` (#9, email dispatch every 5 minutes). If `main` has moved, diff `app/main.py`, `app/config.py`, `app/client/gatekeeper_client.py` and `app/metrics.py` against it before starting.

**Goal:** Delete what a finished notebook session leaves on disk: the session's `/data` copy as soon as the session is over, a notebook's outputs 24 hours after its last session, and the file of a notebook the user deleted. The gatekeeper says what; the archivist deletes it and reports back, one item at a time.

**Architecture:** One APScheduler job on its own executor, every 15 minutes, modelled on `notification_dispatch_job.py`: ask `GET /internal/notebook-sessions/purgeable`, turn each entry into a path under the storage mount, refuse any path that escapes it, delete, report with the matching `POST .../purged` route. A path that is already gone is reported as purged too: the aim is that the gatekeeper stops listing it. Nothing here touches MinIO.

**Tech Stack:** Python 3.10 (`python:3.10.14-alpine`), APScheduler 3.10, httpx, prometheus-client, pytest, unittest.mock.

**Spec:** `docs/rfcs/007-notebooks.md` (§Data in the session, *Purge*). **Contracts:** `docs/superpowers/plans/2026-10-04-notebooks-00-contracts.md`, *Storage layout* and *Internal routes* (wins over this plan on any interface).

## Global Constraints

- The archivist mounts the host storage directory (the same path MinIO's volume binds, `STORAGE_DOCKER_VOLUME` in the gatekeeper's env) at `/storage`, read-write. `NOTEBOOK_STORAGE_PATH` is `/storage` inside the container; `NOTEBOOK_STORAGE_HOST_PATH` is the host path the compose file binds. The archivist never writes under `/storage/datamap` (the bucket): every path it deletes is under `notebooks/` or `sessions/`, and the service refuses anything else.
- Routes, exactly: `GET {api}/api/v1/internal/notebook-sessions/purgeable`; `POST .../internal/notebook-sessions/{id}/purged`; `POST .../internal/notebooks/{id}/outputs-purged`; `POST .../internal/notebooks/{id}/purged`. Client headers as `GatekeeperClient` already sends.
- Paths, exactly: session data `sessions/{session_id}/data` (and the then-empty `sessions/{session_id}`); outputs `notebooks/{user_id}/.outputs/{notebook_id}`; notebook file `notebooks/{user_id}/{path}` where `path` comes from the gatekeeper and has no directory component.
- A missing path counts as purged and is reported. A path that cannot be deleted (permission, a file in use) is logged and left for the next run; the job never raises on one item.
- Metric: `datamap_archivist_notebook_purges_total{kind, outcome}` with `kind` = `session_data`, `outputs`, `notebook`; `outcome` = `deleted`, `absent`, `failed`. Also `datamap_external_request_duration_seconds` through `metrics.external_call("gatekeeper", "notebooks.purgeable" | "notebooks.purged")`.
- Settings: `NOTEBOOK_PURGE_INTERVAL_MINUTES=15`, `ENABLE_NOTEBOOK_PURGE=True`, `NOTEBOOK_STORAGE_PATH="/storage"`. `ENABLE_NOTEBOOK_PURGE=False` until the gatekeeper has the routes (the same pattern as `ENABLE_NOTIFICATION_DISPATCH`).
- Logging through `app.logging_config.fields`; idle runs stay quiet with `Heartbeat`; repeated failures are collapsed with `FailureReporter`, as the dispatch job does.
- Code style (CLAUDE.md): no narrating comments; type hints; `ruff check app` and `ruff format --check app` clean (ruff 0.5.3, as CI pins).

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `app/config.py` | modify | three settings |
| `app/client/gatekeeper_client.py` | modify | four calls |
| `app/service/notebook_purge_service.py` | create | `PurgeTarget`, `targets_for(purgeable, root)`, `delete(target)` |
| `app/jobs/notebook_purge_job.py` | create | `run_notebook_purge_job()` |
| `app/metrics.py` | modify | `notebook_purge(kind, outcome)` |
| `app/main.py` | modify | the job and its executor |
| `docker-compose.yaml`, `local.env.example`, `README.md` | modify | mount and variables |
| `tests/unit/test_notebook_purge_service.py`, `tests/unit/test_notebook_purge_job.py`, `tests/unit/test_gatekeeper_client.py` (append) | create / modify | tests |
| gatekeeper `infrastructure/grafana/external-metrics.txt` | modify | declare the metric |

---

### Task 1: Settings and the gatekeeper calls

**Files:**
- Modify: `app/config.py`, `app/client/gatekeeper_client.py`, `local.env.example`
- Modify: `tests/unit/test_gatekeeper_client.py` (append)

**Interfaces:**
- Produces: `settings.NOTEBOOK_PURGE_INTERVAL_MINUTES: int`, `settings.ENABLE_NOTEBOOK_PURGE: bool`, `settings.NOTEBOOK_STORAGE_PATH: str`; `GatekeeperClient.get_notebook_purgeable() -> dict`, `report_session_purged(session_id: str) -> None`, `report_outputs_purged(notebook_id: str) -> None`, `report_notebook_purged(notebook_id: str) -> None`.

- [ ] **Step 1: Failing client tests**

Open `tests/unit/test_gatekeeper_client.py`, see how it patches `httpx` (it patches `app.client.gatekeeper_client.httpx.get` and friends with `unittest.mock.patch`), and append in the same style:

```python
class TestNotebookPurgeCalls(unittest.TestCase):
    def setUp(self):
        self.client = GatekeeperClient()

    @patch("app.client.gatekeeper_client.httpx.get")
    def test_purgeable_asks_the_internal_route_and_returns_the_body(self, get):
        get.return_value = Mock(status_code=200, json=lambda: {"sessions": [], "outputs": [], "notebooks": []})
        get.return_value.raise_for_status = Mock()

        result = self.client.get_notebook_purgeable()

        self.assertEqual(result, {"sessions": [], "outputs": [], "notebooks": []})
        self.assertTrue(get.call_args.args[0].endswith("/api/v1/internal/notebook-sessions/purgeable"))

    @patch("app.client.gatekeeper_client.httpx.post")
    def test_each_report_posts_to_its_route(self, post):
        post.return_value = Mock(status_code=204)
        post.return_value.raise_for_status = Mock()

        self.client.report_session_purged("s1")
        self.client.report_outputs_purged("n1")
        self.client.report_notebook_purged("n2")

        urls = [call.args[0] for call in post.call_args_list]
        self.assertTrue(urls[0].endswith("/api/v1/internal/notebook-sessions/s1/purged"))
        self.assertTrue(urls[1].endswith("/api/v1/internal/notebooks/n1/outputs-purged"))
        self.assertTrue(urls[2].endswith("/api/v1/internal/notebooks/n2/purged"))

    @patch("app.client.gatekeeper_client.httpx.post")
    def test_a_refused_report_raises(self, post):
        request = httpx.Request("POST", "http://gatekeeper:9092/x")
        post.return_value = httpx.Response(500, request=request)

        with self.assertRaises(httpx.HTTPStatusError):
            self.client.report_session_purged("s1")
```

(Add `import httpx` and `from unittest.mock import Mock, patch` at the top if the file lacks them.)

Run: `pytest tests/unit/test_gatekeeper_client.py -q`
Expected: 3 new failures with `AttributeError: 'GatekeeperClient' object has no attribute 'get_notebook_purgeable'`

- [ ] **Step 2: Settings**

In `app/config.py`, after `ENABLE_NOTIFICATION_DISPATCH`:

```python
    NOTEBOOK_PURGE_INTERVAL_MINUTES: int = 15
    ENABLE_NOTEBOOK_PURGE: bool = True
    NOTEBOOK_STORAGE_PATH: str = "/storage"
```

Append to `local.env.example`:

```
# Notebooks (gatekeeper RFC 007): the host path MinIO's volume binds, mounted at /storage
NOTEBOOK_STORAGE_HOST_PATH=../data-storage
NOTEBOOK_PURGE_INTERVAL_MINUTES=15
ENABLE_NOTEBOOK_PURGE=false  # Set to true once the gatekeeper has the purgeable route
```

- [ ] **Step 3: The calls**

Append to `GatekeeperClient` in `app/client/gatekeeper_client.py`:

```python
    def get_notebook_purgeable(self) -> Dict:
        url = f"{self.base_url}/api/v1/internal/notebook-sessions/purgeable"
        with metrics.external_call("gatekeeper", "notebooks.purgeable") as call:
            response = httpx.get(url, headers=self.headers, timeout=self.timeout)
            call.status = response.status_code
            response.raise_for_status()
        return response.json()

    def report_session_purged(self, session_id: str) -> None:
        self._report(f"/api/v1/internal/notebook-sessions/{session_id}/purged")

    def report_outputs_purged(self, notebook_id: str) -> None:
        self._report(f"/api/v1/internal/notebooks/{notebook_id}/outputs-purged")

    def report_notebook_purged(self, notebook_id: str) -> None:
        self._report(f"/api/v1/internal/notebooks/{notebook_id}/purged")

    def _report(self, path: str) -> None:
        with metrics.external_call("gatekeeper", "notebooks.purged") as call:
            response = httpx.post(
                f"{self.base_url}{path}", headers=self.headers, timeout=self.timeout
            )
            call.status = response.status_code
            response.raise_for_status()
```

Run the client tests. Expected: all passed.

- [ ] **Step 4: Commit**

```bash
git add app/config.py app/client/gatekeeper_client.py local.env.example tests/unit/test_gatekeeper_client.py
git commit -m "feat(notebooks): settings and gatekeeper calls for the purge job"
```

---

### Task 2: The purge service

**Files:**
- Create: `app/service/notebook_purge_service.py`
- Create: `tests/unit/test_notebook_purge_service.py`

**Interfaces:**
- Produces: `PurgeTarget(kind: str, id: str, path: str)`; `targets_for(purgeable: dict, root: str) -> list[PurgeTarget]` (raises nothing; skips and logs an entry whose path escapes `root`); `delete(target: PurgeTarget) -> str` returning `"deleted"`, `"absent"` or `"failed"`.

- [ ] **Step 1: Failing tests**

`tests/unit/test_notebook_purge_service.py`:

```python
import os
import tempfile
import unittest

from app.service.notebook_purge_service import PurgeTarget, delete, targets_for

PURGEABLE = {
    "sessions": [{"id": "s1", "user_id": "u1"}],
    "outputs": [{"notebook_id": "n1", "user_id": "u1"}],
    "notebooks": [{"notebook_id": "n2", "user_id": "u1", "path": "old.ipynb"}],
}


class TestTargets(unittest.TestCase):
    def test_each_entry_maps_to_its_path_under_the_root(self):
        targets = targets_for(PURGEABLE, "/storage")

        self.assertEqual(
            targets,
            [
                PurgeTarget("session_data", "s1", "/storage/sessions/s1/data"),
                PurgeTarget("outputs", "n1", "/storage/notebooks/u1/.outputs/n1"),
                PurgeTarget("notebook", "n2", "/storage/notebooks/u1/old.ipynb"),
            ],
        )

    def test_a_path_that_escapes_the_root_is_skipped(self):
        purgeable = {
            "sessions": [],
            "outputs": [],
            "notebooks": [{"notebook_id": "n9", "user_id": "../datamap", "path": "x.ipynb"}],
        }

        self.assertEqual(targets_for(purgeable, "/storage"), [])

    def test_a_notebook_path_with_a_directory_is_skipped(self):
        purgeable = {
            "sessions": [],
            "outputs": [],
            "notebooks": [{"notebook_id": "n9", "user_id": "u1", "path": "../../etc/passwd"}],
        }

        self.assertEqual(targets_for(purgeable, "/storage"), [])

    def test_missing_lists_are_tolerated(self):
        self.assertEqual(targets_for({}, "/storage"), [])


class TestDelete(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_a_session_directory_is_removed_with_its_parent(self):
        data = os.path.join(self.root, "sessions", "s1", "data", "ds", "v1")
        os.makedirs(data)
        with open(os.path.join(data, "a.nc"), "wb") as handle:
            handle.write(b"x")

        outcome = delete(PurgeTarget("session_data", "s1", os.path.join(self.root, "sessions", "s1", "data")))

        self.assertEqual(outcome, "deleted")
        self.assertFalse(os.path.exists(os.path.join(self.root, "sessions", "s1")))

    def test_an_outputs_directory_is_removed(self):
        outputs = os.path.join(self.root, "notebooks", "u1", ".outputs", "n1")
        os.makedirs(outputs)

        self.assertEqual(delete(PurgeTarget("outputs", "n1", outputs)), "deleted")
        self.assertFalse(os.path.exists(outputs))
        self.assertTrue(os.path.isdir(os.path.join(self.root, "notebooks", "u1")))

    def test_a_notebook_file_is_removed(self):
        os.makedirs(os.path.join(self.root, "notebooks", "u1"))
        path = os.path.join(self.root, "notebooks", "u1", "old.ipynb")
        with open(path, "w") as handle:
            handle.write("{}")

        self.assertEqual(delete(PurgeTarget("notebook", "n2", path)), "deleted")
        self.assertFalse(os.path.exists(path))

    def test_an_absent_path_is_absent_not_failed(self):
        self.assertEqual(
            delete(PurgeTarget("outputs", "n1", os.path.join(self.root, "nothing"))), "absent"
        )

    def test_a_path_that_cannot_be_removed_is_failed(self):
        locked = os.path.join(self.root, "notebooks", "u1", ".outputs", "n1")
        os.makedirs(locked)
        with open(os.path.join(locked, "f"), "w") as handle:
            handle.write("x")
        os.chmod(locked, 0o555)
        try:
            self.assertEqual(delete(PurgeTarget("outputs", "n1", locked)), "failed")
        finally:
            os.chmod(locked, 0o755)
```

Run: `pytest tests/unit/test_notebook_purge_service.py -q`
Expected: FAIL with `ModuleNotFoundError`

(The last test needs a non-root user: as root the `chmod` does not bite. CI runs as a normal user; locally, skip it with `pytest -k "not cannot_be_removed"` if you are root.)

- [ ] **Step 2: The service**

`app/service/notebook_purge_service.py`:

```python
"""Turns the gatekeeper's purge list into paths under the storage mount and deletes them."""

import logging
import os
import shutil
from dataclasses import dataclass

from app.logging_config import fields

logger = logging.getLogger(__name__)

SESSION_DATA = "session_data"
OUTPUTS = "outputs"
NOTEBOOK = "notebook"


@dataclass(frozen=True)
class PurgeTarget:
    kind: str
    id: str
    path: str


def _inside(root: str, *parts: str) -> str | None:
    base = os.path.realpath(root)
    full = os.path.realpath(os.path.join(base, *parts))
    if full == base or not full.startswith(base + os.sep):
        return None
    return full


def targets_for(purgeable: dict, root: str) -> list[PurgeTarget]:
    targets: list[PurgeTarget] = []
    for entry in purgeable.get("sessions") or []:
        path = _inside(root, "sessions", str(entry["id"]), "data")
        if path is None:
            logger.warning("purge entry skipped", extra=fields(kind=SESSION_DATA, id=entry.get("id")))
            continue
        targets.append(PurgeTarget(SESSION_DATA, str(entry["id"]), path))
    for entry in purgeable.get("outputs") or []:
        path = _inside(root, "notebooks", str(entry["user_id"]), ".outputs", str(entry["notebook_id"]))
        if path is None:
            logger.warning("purge entry skipped", extra=fields(kind=OUTPUTS, id=entry.get("notebook_id")))
            continue
        targets.append(PurgeTarget(OUTPUTS, str(entry["notebook_id"]), path))
    for entry in purgeable.get("notebooks") or []:
        name = str(entry.get("path", ""))
        path = None if os.sep in name or not name else _inside(root, "notebooks", str(entry["user_id"]), name)
        if path is None:
            logger.warning("purge entry skipped", extra=fields(kind=NOTEBOOK, id=entry.get("notebook_id")))
            continue
        targets.append(PurgeTarget(NOTEBOOK, str(entry["notebook_id"]), path))
    return targets


def delete(target: PurgeTarget) -> str:
    if not os.path.lexists(target.path):
        return "absent"
    try:
        if os.path.isdir(target.path) and not os.path.islink(target.path):
            shutil.rmtree(target.path)
        else:
            os.remove(target.path)
        if target.kind == SESSION_DATA:
            parent = os.path.dirname(target.path)
            if os.path.isdir(parent) and not os.listdir(parent):
                os.rmdir(parent)
    except OSError as error:
        logger.warning(
            "purge failed",
            extra=fields(kind=target.kind, id=target.id, error=str(error)),
        )
        return "failed"
    return "deleted"
```

Run the tests. Expected: 9 passed.

- [ ] **Step 3: Commit**

```bash
git add app/service/notebook_purge_service.py tests/unit/test_notebook_purge_service.py
git commit -m "feat(notebooks): purge targets and deletion under the storage mount

Every path is resolved under the mount and refused if it escapes it; the
bucket directory is never a candidate. A path already gone is 'absent', so
the gatekeeper can stop listing it."
```

---

### Task 3: The job, its metric and its schedule

**Files:**
- Modify: `app/metrics.py`
- Create: `app/jobs/notebook_purge_job.py`
- Modify: `app/main.py`
- Create: `tests/unit/test_notebook_purge_job.py`

**Interfaces:**
- Produces: `metrics.notebook_purge(kind: str, outcome: str) -> None`; `run_notebook_purge_job() -> None`.

- [ ] **Step 1: The metric**

In `app/metrics.py`, inside `Metrics.__init__` after `_copy_duration`:

```python
        self._notebook_purges = Counter(
            "datamap_archivist_notebook_purges_total",
            "Notebook session data, outputs and files the purge job handled",
            ["kind", "outcome"],
            registry=self.registry,
        )
```

and the method after `file_copy`:

```python
    def notebook_purge(self, kind: str, outcome: str) -> None:
        self._notebook_purges.labels(kind=kind, outcome=outcome).inc()
```

- [ ] **Step 2: Failing job tests**

`tests/unit/test_notebook_purge_job.py`:

```python
import io
import json
import logging
import unittest
from unittest.mock import patch

import httpx

from app.jobs import notebook_purge_job
from app.logging_config import setup_logging
from app.service.notebook_purge_service import PurgeTarget

EMPTY = {"sessions": [], "outputs": [], "notebooks": []}
ONE_OF_EACH = {
    "sessions": [{"id": "s1", "user_id": "u1"}],
    "outputs": [{"notebook_id": "n1", "user_id": "u1"}],
    "notebooks": [{"notebook_id": "n2", "user_id": "u1", "path": "old.ipynb"}],
}


def _entries(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().strip().splitlines() if line]


class JobTestCase(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        setup_logging(stream=self.stream)
        notebook_purge_job._failures = type(notebook_purge_job._failures)()
        notebook_purge_job._heartbeat = type(notebook_purge_job._heartbeat)()
        patcher = patch.object(notebook_purge_job.settings, "ENABLE_NOTEBOOK_PURGE", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)

    def _above_debug(self) -> list[dict]:
        return [e for e in _entries(self.stream) if e["level"] != "DEBUG"]


class TestRun(JobTestCase):
    @patch.object(notebook_purge_job, "delete", return_value="deleted")
    @patch.object(notebook_purge_job, "GatekeeperClient")
    def test_every_target_is_deleted_and_reported(self, gatekeeper, delete):
        client = gatekeeper.return_value
        client.get_notebook_purgeable.return_value = ONE_OF_EACH

        notebook_purge_job.run_notebook_purge_job()

        self.assertEqual(delete.call_count, 3)
        client.report_session_purged.assert_called_once_with("s1")
        client.report_outputs_purged.assert_called_once_with("n1")
        client.report_notebook_purged.assert_called_once_with("n2")
        summary = self._above_debug()[-1]
        self.assertEqual(summary["message"], "notebook purge completed")
        self.assertEqual(summary["deleted"], 3)

    @patch.object(notebook_purge_job, "delete", return_value="absent")
    @patch.object(notebook_purge_job, "GatekeeperClient")
    def test_an_absent_path_is_still_reported(self, gatekeeper, delete):
        client = gatekeeper.return_value
        client.get_notebook_purgeable.return_value = {"sessions": [{"id": "s1", "user_id": "u1"}], "outputs": [], "notebooks": []}

        notebook_purge_job.run_notebook_purge_job()

        client.report_session_purged.assert_called_once_with("s1")

    @patch.object(notebook_purge_job, "delete", return_value="failed")
    @patch.object(notebook_purge_job, "GatekeeperClient")
    def test_a_failed_deletion_is_not_reported(self, gatekeeper, delete):
        client = gatekeeper.return_value
        client.get_notebook_purgeable.return_value = {"sessions": [{"id": "s1", "user_id": "u1"}], "outputs": [], "notebooks": []}

        notebook_purge_job.run_notebook_purge_job()

        client.report_session_purged.assert_not_called()
        self.assertEqual(self._above_debug()[-1]["failed"], 1)

    @patch.object(notebook_purge_job, "delete", return_value="deleted")
    @patch.object(notebook_purge_job, "GatekeeperClient")
    def test_a_refused_report_does_not_stop_the_others(self, gatekeeper, delete):
        client = gatekeeper.return_value
        client.get_notebook_purgeable.return_value = ONE_OF_EACH
        request = httpx.Request("POST", "http://g/x")
        client.report_session_purged.side_effect = httpx.HTTPStatusError(
            "500", request=request, response=httpx.Response(500, request=request)
        )

        notebook_purge_job.run_notebook_purge_job()

        client.report_outputs_purged.assert_called_once()
        client.report_notebook_purged.assert_called_once()

    @patch.object(notebook_purge_job, "GatekeeperClient")
    def test_an_idle_run_writes_one_heartbeat_an_hour(self, gatekeeper):
        gatekeeper.return_value.get_notebook_purgeable.return_value = EMPTY

        for _ in range(12):
            notebook_purge_job.run_notebook_purge_job()

        self.assertEqual([e["message"] for e in self._above_debug()], ["notebook purge idle"])

    @patch.object(notebook_purge_job, "GatekeeperClient")
    def test_a_gatekeeper_that_is_down_is_reported_once(self, gatekeeper):
        gatekeeper.return_value.get_notebook_purgeable.side_effect = httpx.ConnectError("refused")

        for _ in range(3):
            notebook_purge_job.run_notebook_purge_job()

        errors = [e for e in self._above_debug() if e["level"] == "ERROR"]
        self.assertEqual(len(errors), 1)

    @patch.object(notebook_purge_job, "GatekeeperClient")
    def test_switched_off_does_nothing(self, gatekeeper):
        with patch.object(notebook_purge_job.settings, "ENABLE_NOTEBOOK_PURGE", False):
            notebook_purge_job.run_notebook_purge_job()

        gatekeeper.assert_not_called()
```

Run: `pytest tests/unit/test_notebook_purge_job.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: The job**

`app/jobs/notebook_purge_job.py`:

```python
"""APScheduler job that deletes what finished notebook sessions left on disk."""

import logging

import httpx

from app.client.gatekeeper_client import GatekeeperClient
from app.config import settings
from app.logging_config import FailureReporter, Heartbeat, fields
from app.metrics import metrics
from app.service.notebook_purge_service import (
    NOTEBOOK,
    OUTPUTS,
    SESSION_DATA,
    PurgeTarget,
    delete,
    targets_for,
)

logger = logging.getLogger(__name__)

_failures = FailureReporter()
_heartbeat = Heartbeat()

REPORTERS = {
    SESSION_DATA: "report_session_purged",
    OUTPUTS: "report_outputs_purged",
    NOTEBOOK: "report_notebook_purged",
}


def run_notebook_purge_job() -> None:
    if not settings.ENABLE_NOTEBOOK_PURGE:
        logger.debug("notebook purge is switched off")
        return

    try:
        client = GatekeeperClient()
        purgeable = client.get_notebook_purgeable()
        if not isinstance(purgeable, dict):
            raise ValueError(f"unexpected purgeable response: {purgeable!r}")
    except (httpx.HTTPError, ValueError) as error:
        if _failures.should_report("purge", str(error)):
            logger.error("notebook purge could not list targets", extra=fields(error=str(error)))
        return
    if _failures.is_failing("purge"):
        logger.info("notebook purge recovered", extra=fields(repeats_suppressed=_failures.suppressed("purge")))
    _failures.clear("purge")

    targets = targets_for(purgeable, settings.NOTEBOOK_STORAGE_PATH)
    if not targets:
        if _heartbeat.due():
            logger.info("notebook purge idle", extra=fields(quiet_runs=_heartbeat.last_quiet_runs))
        return

    summary = {"deleted": 0, "absent": 0, "failed": 0, "unreported": 0}
    for target in targets:
        outcome = delete(target)
        metrics.notebook_purge(target.kind, outcome)
        summary[outcome] += 1
        if outcome == "failed":
            continue
        if not _report(client, target):
            summary["unreported"] += 1

    level = logging.WARNING if summary["failed"] or summary["unreported"] else logging.INFO
    logger.log(level, "notebook purge completed", extra=fields(**summary))


def _report(client: GatekeeperClient, target: PurgeTarget) -> bool:
    try:
        getattr(client, REPORTERS[target.kind])(target.id)
        return True
    except httpx.HTTPError as error:
        logger.warning(
            "purge not acknowledged",
            extra=fields(kind=target.kind, id=target.id, error=str(error)),
        )
        return False
```

Check `Heartbeat` in `app/logging_config.py` exposes `last_quiet_runs` as the dispatch job uses it; if the attribute is named differently there, use that name.

Run the job tests. Expected: 7 passed.

- [ ] **Step 4: Schedule it**

In `app/main.py`:

```python
from app.jobs.notebook_purge_job import run_notebook_purge_job
```

In `create_scheduler`, add to `executors`:

```python
        # Deleting a 20 GB copy on the NAS must not hold email or collocation.
        "purge": ThreadPoolExecutor(max_workers=1),
```

In `add_jobs`, after the notification job:

```python
    scheduler.add_job(
        func=run_notebook_purge_job,
        trigger=IntervalTrigger(minutes=settings.NOTEBOOK_PURGE_INTERVAL_MINUTES),
        id="notebook_purge",
        name="Notebook Purge Job",
        executor="purge",
        replace_existing=True,
    )
    logger.info(
        "added notebook purge job",
        extra=fields(
            interval_minutes=settings.NOTEBOOK_PURGE_INTERVAL_MINUTES,
            enabled=settings.ENABLE_NOTEBOOK_PURGE,
        ),
    )
```

If `tests/unit/test_main.py` asserts the exact set of jobs or executors, extend its expectation with `notebook_purge` and `purge`.

Run: `pytest tests -q && ruff check app && ruff format --check app`
Expected: all passed, no findings

- [ ] **Step 5: Commit**

```bash
git add app/metrics.py app/jobs/notebook_purge_job.py app/main.py tests/unit/test_notebook_purge_job.py tests/unit/test_main.py
git commit -m "feat(notebooks): purge job on its own executor every 15 minutes

Failures to delete are left for the next run and counted; a report the
gatekeeper refuses does not stop the others. Idle runs are one heartbeat an
hour, like the dispatch job."
```

---

### Task 4: The mount

**Files:**
- Modify: `docker-compose.yaml`, `README.md`

- [ ] **Step 1: Compose**

In `docker-compose.yaml`, on the `archivist` service add:

```yaml
    environment:
      # (existing entries stay)
      - NOTEBOOK_STORAGE_PATH=/storage
    volumes:
      # The same host directory MinIO's volume binds. Only notebooks/ and
      # sessions/ are ever written here; the bucket is read by nobody.
      - ${NOTEBOOK_STORAGE_HOST_PATH}:/storage
```

`${NOTEBOOK_STORAGE_HOST_PATH}` is expanded by Compose from the shell, so the archivist's `make docker-run` (which includes the env file) is the way to start it, as for every other variable in this file. Add the variable to `secrets/production/archivist.env.sops` with the production host path (the same value as the gatekeeper's `STORAGE_DOCKER_VOLUME`), through `sops`, before the deploy that carries this change; a blank value makes Compose bind the host's `/` — which is exactly the kind of failure `host-applied-changes.md` in the gatekeeper warns about. Confirm after the first deploy with `docker inspect datamap_archivist --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'`.

- [ ] **Step 2: README**

Under *Key Features* in `README.md`, add one bullet:

```markdown
- **Notebook purge**: every 15 minutes deletes the session data, expired outputs and deleted notebook files the gatekeeper lists (`/storage`, RFC 007 in the gatekeeper repo)
```

- [ ] **Step 3: Build and commit**

Run: `docker build -t archivist .`
Expected: builds.

```bash
git add docker-compose.yaml README.md
git commit -m "feat(notebooks): mount the storage directory so the purge job can delete under it"
```

---

### Task 5: Declare the metric for the dashboards (gatekeeper repo)

**Files:**
- Modify (gatekeeper repo): `infrastructure/grafana/external-metrics.txt`

- [ ] **Step 1: Add the line**

Under the `# archivist (app/metrics.py)` block:

```
datamap_archivist_notebook_purges_total
```

Run (gatekeeper repo): `pytest app/grafana_dashboards_test.py -q`
Expected: passes (nothing queries it yet; the line is there for when a panel does).

- [ ] **Step 2: Commit on the gatekeeper branch**

```bash
git add infrastructure/grafana/external-metrics.txt
git commit -m "docs(metrics): declare the archivist's notebook purge counter"
```

---

### Task 6: Verify end to end and open the pull request

- [ ] **Step 1: Against a gatekeeper with plan 01**

With the gatekeeper integration stack up (plan 01, Task 9) and `GATEKEEPER_API_URL=http://localhost:9094` plus the integration client key in a local env file:

```bash
make ENV_FILE_PATH=local.env DATASET_ID=unused python-run
```

is the scheduler; for a single pass use a Python one-liner instead:

```bash
ENABLE_NOTEBOOK_PURGE=true NOTEBOOK_STORAGE_PATH=../data-storage_test_integration \
  python -c "from app.jobs.notebook_purge_job import run_notebook_purge_job as r; r()"
```

after creating and stopping a session through the integration tests (`TestInternal.test_purgeable_lists_a_stopped_session_until_it_is_reported` leaves one listed if you comment out its last two assertions for the check). Expected: the log line `notebook purge completed` with `deleted` or `absent` and `unreported: 0`, and `GET /internal/notebook-sessions/purgeable` no longer listing the session.

- [ ] **Step 2: Suite, lint, PR**

```bash
pytest tests -q
ruff check app && ruff format --check app
git push -u origin feat/notebook-purge
gh pr create --title "feat(notebooks): purge job for session data, outputs and deleted notebooks" --body "$(cat <<'EOF'
## Summary
- every 15 minutes, asks the gatekeeper what to delete and deletes it under the storage mount, refusing any path outside notebooks/ and sessions/
- reports each item back so it stops being listed; a failure is left for the next run
- `datamap_archivist_notebook_purges_total{kind,outcome}`

Spec: gatekeeper `docs/rfcs/007-notebooks.md`. Contracts: gatekeeper `docs/superpowers/plans/2026-10-04-notebooks-00-contracts.md`.

## Test plan
- [ ] unit suite green
- [ ] a stopped session's data directory disappears and the session leaves `purgeable`
- [ ] `NOTEBOOK_STORAGE_HOST_PATH` set in the encrypted env before deploy; mount verified with `docker inspect`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Deploy order (contracts): gatekeeper 01 first, then this, with `ENABLE_NOTEBOOK_PURGE=true` only once the gatekeeper's routes answer.
