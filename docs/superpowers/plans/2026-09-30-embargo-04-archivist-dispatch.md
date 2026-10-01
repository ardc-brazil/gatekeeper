# Embargo 04 — Archivist Notification Dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every 5 minutes the Archivist asks the gatekeeper to send the email that is due, by calling `POST /api/v1/internal/notifications/dispatch`.

**Architecture:** One new `GatekeeperClient` method, one new APScheduler job module modelled on `file_collocation_job`, and its registration in `app/main.py` on an executor of its own so a long collocation run never delays it. The Archivist only triggers; the gatekeeper owns the messages, the templates and SMTP (RFC 003 §Notifications, contracts §Notifications).

**Tech Stack:** Python 3.10.14, APScheduler 3.10.4, httpx 0.27, pydantic-settings, python-json-logger, pytest 8.2.1, ruff 0.5.3.

**Repository:** this plan is stored in the gatekeeper repo with the other embargo plans, but **every file it changes is in the Archivist repo, `/Users/caio.maia/workspace/datamap/archivist`**. All paths below are relative to that root. Do the work in a worktree of the Archivist repo on a branch such as `feat/notification-dispatch`, never in its main checkout.

## Global Constraints

- Route: `POST {GATEKEEPER_API_URL}/api/v1/internal/notifications/dispatch`, client credentials only (`X-Api-Key`, `X-Api-Secret`), no body. Response `200 {"queued": int, "sent": int, "failed": int, "skipped": int, "retried": int}` (contracts §Notifications).
- Interval: `NOTIFICATION_DISPATCH_INTERVAL_MINUTES`, default `5`. Switch: `ENABLE_NOTIFICATION_DISPATCH`, default `true`.
- Job id `notification_dispatch`, `replace_existing=True`, `coalesce=True`, `max_instances=1` (the scheduler's job defaults), executor `notifications`.
- An HTTP error never escapes the job: it is logged once per distinct error through `FailureReporter` and the next run retries.
- Log messages are short and lowercase; structured data goes through `fields(...)` from `app/logging_config.py`.
- **No metrics.** The Archivist exposes none yet (README: "Metrics/monitoring integration (Prometheus)" is unchecked); the email metrics `datamap_emails_total` and `datamap_email_pending` live in the gatekeeper (plan 01). Out of scope here.
- Lint: `ruff==0.5.3`, `ruff check app` and `ruff format --check app`, as CI runs them.
- Tests: `pytest tests -q`, as CI runs them. `tests/conftest.py` already sets the five required settings, so plain `pytest` needs no env file. The Makefile targets (`make test`, `make test-unit`) `include ${ENV_FILE_PATH}` at the top, so they need `ENV_FILE_PATH=local.env` (or any env file) on the command line.
- Deploy after the gatekeeper route exists (contracts §Plans, deploy order). If the Archivist ships first, set `ENABLE_NOTIFICATION_DISPATCH=false` in its production env until it does; otherwise it logs one `404` error and stays quiet until the route appears.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `app/config.py` | modify | two settings: interval and switch |
| `local.env.example` | modify | document the two settings |
| `app/client/gatekeeper_client.py` | modify | `dispatch_notifications()` |
| `app/jobs/notification_dispatch_job.py` | create | `run_notification_dispatch_job()` |
| `app/main.py` | modify | `notifications` executor; register the job |
| `tests/unit/test_gatekeeper_client.py` | create | client method |
| `tests/unit/test_notification_dispatch_job.py` | create | job behaviour, asserted on JSON log lines |
| `tests/unit/test_main.py` | create | executor and job registration |

---

### Task 1: Client method `dispatch_notifications()`

**Files:**
- Modify: `app/client/gatekeeper_client.py` (append a method to `GatekeeperClient`, after `update_collocation_status`)
- Test: `tests/unit/test_gatekeeper_client.py`

**Interfaces:**
- Consumes: `settings.GATEKEEPER_API_URL`, `GATEKEEPER_API_KEY`, `GATEKEEPER_API_SECRET` (existing).
- Produces: `GatekeeperClient.dispatch_notifications(self) -> Dict[str, int]` — returns the parsed JSON counts; raises `httpx.HTTPError` on transport or non-2xx errors. It does **not** log the error itself: the job reports it once through `FailureReporter`, and a log line here would repeat it every 5 minutes.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_gatekeeper_client.py`:

```python
import unittest
from unittest.mock import patch

import httpx

from app.client.gatekeeper_client import GatekeeperClient

COUNTS = {"queued": 2, "sent": 3, "failed": 0, "skipped": 1, "retried": 0}


def _response(status_code: int, json_body=None) -> httpx.Response:
    request = httpx.Request(
        "POST", "http://gatekeeper:9092/api/v1/internal/notifications/dispatch"
    )
    return httpx.Response(status_code, json=json_body, request=request)


class TestDispatchNotifications(unittest.TestCase):
    def test_it_posts_to_the_internal_dispatch_route(self):
        with patch("app.client.gatekeeper_client.httpx.post") as post:
            post.return_value = _response(200, COUNTS)

            GatekeeperClient().dispatch_notifications()

        url = post.call_args.args[0]
        self.assertTrue(url.endswith("/api/v1/internal/notifications/dispatch"), url)

    def test_it_sends_the_client_credentials(self):
        with patch("app.client.gatekeeper_client.httpx.post") as post:
            post.return_value = _response(200, COUNTS)

            GatekeeperClient().dispatch_notifications()

        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers["X-Api-Key"], "test")
        self.assertEqual(headers["X-Api-Secret"], "test")

    def test_it_returns_the_counts_the_gatekeeper_answered(self):
        with patch("app.client.gatekeeper_client.httpx.post") as post:
            post.return_value = _response(200, COUNTS)

            counts = GatekeeperClient().dispatch_notifications()

        self.assertEqual(counts, COUNTS)

    def test_a_server_error_raises(self):
        with patch("app.client.gatekeeper_client.httpx.post") as post:
            post.return_value = _response(500, {"detail": "Internal server error"})

            with self.assertRaises(httpx.HTTPStatusError):
                GatekeeperClient().dispatch_notifications()

    def test_a_server_error_is_not_logged_here(self):
        with (
            patch("app.client.gatekeeper_client.httpx.post") as post,
            patch("app.client.gatekeeper_client.logger") as logger,
        ):
            post.return_value = _response(500, {"detail": "Internal server error"})

            with self.assertRaises(httpx.HTTPStatusError):
                GatekeeperClient().dispatch_notifications()

        logger.error.assert_not_called()

    def test_a_timeout_raises(self):
        with patch("app.client.gatekeeper_client.httpx.post") as post:
            post.side_effect = httpx.ReadTimeout("timed out")

            with self.assertRaises(httpx.HTTPError):
                GatekeeperClient().dispatch_notifications()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/caio.maia/workspace/datamap/archivist && pytest tests/unit/test_gatekeeper_client.py -q`
Expected: 6 failed, each with `AttributeError: 'GatekeeperClient' object has no attribute 'dispatch_notifications'`.

- [ ] **Step 3: Write the minimal implementation**

Append to the `GatekeeperClient` class in `app/client/gatekeeper_client.py`:

```python
    def dispatch_notifications(self) -> Dict[str, int]:
        """
        Ask the gatekeeper to send the email that is due.

        Returns:
            Counts of messages queued, sent, failed, skipped and retried.
        """
        url = f"{self.base_url}/api/v1/internal/notifications/dispatch"
        response = httpx.post(url, headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
```

`Dict` is already imported at the top of the module (`from typing import List, Dict`).

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/caio.maia/workspace/datamap/archivist && pytest tests/unit/test_gatekeeper_client.py -q`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/caio.maia/workspace/datamap/archivist
git add app/client/gatekeeper_client.py tests/unit/test_gatekeeper_client.py
git commit -m "feat: a client call that asks the gatekeeper to send due email

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: The job `run_notification_dispatch_job()`

**Files:**
- Create: `app/jobs/notification_dispatch_job.py`
- Test: `tests/unit/test_notification_dispatch_job.py`

**Interfaces:**
- Consumes: `GatekeeperClient.dispatch_notifications() -> Dict[str, int]` (Task 1); `FailureReporter`, `Heartbeat`, `fields` from `app/logging_config.py` (existing).
- Produces: `run_notification_dispatch_job() -> None`, importable at module level (the APScheduler job store is persistent and stores the function by reference). Module globals `_failures` and `_heartbeat`, reset by tests the same way `test_file_collocation_job.py` does.

Behaviour:

| Situation | Log |
|---|---|
| all counts zero | DEBUG `no notifications due`; at most once an hour INFO `notification dispatch idle` with `quiet_runs` |
| any count non-zero, `failed == 0` | INFO `notification dispatch completed` with the five counts |
| `failed > 0` | WARNING `notification dispatch completed` with the five counts — a failed email is a person who did not get it |
| `httpx.HTTPError` or a non-JSON body (`ValueError`) | ERROR `notification dispatch failed` with `error`, once per distinct error; the job returns |
| the same error on the next runs | nothing (counted by `FailureReporter`) |
| a success after failures | the failure record is cleared, so the next failure is reported again |
| any other exception | ERROR `fatal error in notification dispatch job` with `exc_info`, re-raised, as the collocation job does |

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_notification_dispatch_job.py`:

```python
import io
import json
import logging
import unittest
from unittest.mock import patch

import httpx

from app.jobs import notification_dispatch_job
from app.logging_config import setup_logging

IDLE = {"queued": 0, "sent": 0, "failed": 0, "skipped": 0, "retried": 0}
BUSY = {"queued": 4, "sent": 3, "failed": 0, "skipped": 1, "retried": 0}
WITH_FAILURE = {"queued": 0, "sent": 1, "failed": 2, "skipped": 0, "retried": 0}


def _entries(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().strip().splitlines() if line]


def _server_error() -> httpx.HTTPStatusError:
    request = httpx.Request(
        "POST", "http://gatekeeper:9092/api/v1/internal/notifications/dispatch"
    )
    response = httpx.Response(500, request=request)
    return httpx.HTTPStatusError(
        "Server error '500 Internal Server Error'", request=request, response=response
    )


class JobTestCase(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        setup_logging(stream=self.stream)
        notification_dispatch_job._failures = type(
            notification_dispatch_job._failures
        )()
        notification_dispatch_job._heartbeat = type(
            notification_dispatch_job._heartbeat
        )()

    def tearDown(self):
        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)

    def _run(self, *outcomes) -> None:
        with patch.object(notification_dispatch_job, "GatekeeperClient") as gatekeeper:
            gatekeeper.return_value.dispatch_notifications.side_effect = list(outcomes)
            for _ in outcomes:
                notification_dispatch_job.run_notification_dispatch_job()

    def _above_debug(self) -> list[dict]:
        return [e for e in _entries(self.stream) if e["level"] != "DEBUG"]


class TestAnIdleRunIsSilent(JobTestCase):
    def test_an_hour_of_idle_runs_writes_one_line(self):
        self._run(*[IDLE] * 12)

        self.assertEqual(len(self._above_debug()), 1)

    def test_that_line_says_the_dispatch_is_alive_and_idle(self):
        self._run(*[IDLE] * 12)

        self.assertEqual(self._above_debug()[0]["message"], "notification dispatch idle")

    def test_it_reports_how_many_runs_it_stayed_quiet_for(self):
        self._run(*[IDLE] * 12)

        self.assertEqual(self._above_debug()[0]["quiet_runs"], 0)


class TestARunThatSentSomethingReportsItsCounts(JobTestCase):
    def test_it_writes_one_summary_line(self):
        self._run(BUSY)

        lines = self._above_debug()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["message"], "notification dispatch completed")

    def test_the_counts_are_fields(self):
        self._run(BUSY)

        line = self._above_debug()[0]
        self.assertEqual(
            {k: line[k] for k in ("queued", "sent", "failed", "skipped", "retried")},
            BUSY,
        )

    def test_it_is_info_when_nothing_failed(self):
        self._run(BUSY)

        self.assertEqual(self._above_debug()[0]["level"], "INFO")

    def test_it_is_a_warning_when_an_email_failed(self):
        self._run(WITH_FAILURE)

        self.assertEqual(self._above_debug()[0]["level"], "WARNING")


class TestAnHttpErrorDoesNotEscapeTheJob(JobTestCase):
    def test_the_job_returns_normally(self):
        self._run(_server_error())

    def test_the_error_is_logged(self):
        self._run(_server_error())

        errors = [e for e in _entries(self.stream) if e["level"] == "ERROR"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["message"], "notification dispatch failed")

    def test_a_timeout_is_handled_like_any_http_error(self):
        self._run(httpx.ReadTimeout("timed out"))

        errors = [e for e in _entries(self.stream) if e["level"] == "ERROR"]
        self.assertEqual(len(errors), 1)

    def test_a_body_that_is_not_json_is_handled_too(self):
        self._run(ValueError("Expecting value: line 1 column 1 (char 0)"))

        errors = [e for e in _entries(self.stream) if e["level"] == "ERROR"]
        self.assertEqual(len(errors), 1)


class TestARepeatedFailureIsReportedOnce(JobTestCase):
    def test_an_hour_of_the_same_failure_writes_one_error(self):
        self._run(*[_server_error() for _ in range(12)])

        errors = [e for e in _entries(self.stream) if e["level"] == "ERROR"]
        self.assertEqual(len(errors), 1)

    def test_a_failure_after_a_recovery_is_reported_again(self):
        self._run(_server_error(), BUSY, _server_error())

        errors = [e for e in _entries(self.stream) if e["level"] == "ERROR"]
        self.assertEqual(len(errors), 2)


class TestAnUnexpectedErrorIsFatal(JobTestCase):
    def test_it_is_re_raised(self):
        with self.assertRaises(RuntimeError):
            self._run(RuntimeError("boom"))

    def test_it_is_logged_with_its_traceback(self):
        with self.assertRaises(RuntimeError):
            self._run(RuntimeError("boom"))

        fatal = [e for e in _entries(self.stream) if e["level"] == "ERROR"][0]
        self.assertEqual(fatal["message"], "fatal error in notification dispatch job")
        self.assertIn("exc_info", fatal)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/caio.maia/workspace/datamap/archivist && pytest tests/unit/test_notification_dispatch_job.py -q`
Expected: collection error, `ImportError: cannot import name 'notification_dispatch_job' from 'app.jobs'`.

- [ ] **Step 3: Write the minimal implementation**

Create `app/jobs/notification_dispatch_job.py`:

```python
"""APScheduler job that asks the gatekeeper to send the email that is due."""

import logging

import httpx

from app.client.gatekeeper_client import GatekeeperClient
from app.logging_config import FailureReporter, Heartbeat, fields

logger = logging.getLogger(__name__)

COUNT_KEYS = ("queued", "sent", "failed", "skipped", "retried")

# One key: the dispatch is a single call, not a list of datasets.
_FAILURE_KEY = "dispatch"

_failures = FailureReporter()

_heartbeat = Heartbeat()


def run_notification_dispatch_job() -> None:
    logger.debug("starting notification dispatch job")

    try:
        counts = GatekeeperClient().dispatch_notifications()
    except (httpx.HTTPError, ValueError) as e:
        if _failures.should_report(_FAILURE_KEY, str(e)):
            logger.error("notification dispatch failed", extra=fields(error=str(e)))
        return
    except Exception as e:
        logger.error(
            "fatal error in notification dispatch job",
            extra=fields(error=str(e)),
            exc_info=True,
        )
        raise

    _failures.clear(_FAILURE_KEY)
    summary = {key: int(counts.get(key, 0)) for key in COUNT_KEYS}

    if not any(summary.values()):
        logger.debug("no notifications due")
        if _heartbeat.due():
            logger.info(
                "notification dispatch idle",
                extra=fields(quiet_runs=_heartbeat.last_quiet_runs),
            )
        return

    level = logging.WARNING if summary["failed"] else logging.INFO
    logger.log(level, "notification dispatch completed", extra=fields(**summary))
```

Check before moving on that `ValueError` is what `httpx.Response.json()` raises on a non-JSON body: `json.JSONDecodeError` is a subclass of `ValueError`, so it is.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/caio.maia/workspace/datamap/archivist && pytest tests/unit/test_notification_dispatch_job.py -q`
Expected: `15 passed`.

If `test_it_is_logged_with_its_traceback` fails on the `exc_info` key, open `app/logging_config.py` `JsonFormatter` and check the key python-json-logger 2.0.7 writes the traceback under; it is `exc_info` for this formatter, which `test_logging_config.py` relies on too. Assert on the key it actually writes, not on a guess.

- [ ] **Step 5: Commit**

```bash
cd /Users/caio.maia/workspace/datamap/archivist
git add app/jobs/notification_dispatch_job.py tests/unit/test_notification_dispatch_job.py
git commit -m "feat: a job that asks the gatekeeper to send due email, quietly when idle

An HTTP error is reported once and retried on the next run; a failed
email in the counts is a warning, since it is a person who did not get it.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Settings, executor and registration

**Files:**
- Modify: `app/config.py` (the `# Job configuration` block)
- Modify: `local.env.example` (the `# Job Configuration` block)
- Modify: `app/main.py` (`create_scheduler`, `add_jobs`, imports)
- Test: `tests/unit/test_main.py`

**Interfaces:**
- Consumes: `run_notification_dispatch_job` (Task 2).
- Produces: `settings.NOTIFICATION_DISPATCH_INTERVAL_MINUTES: int = 5`, `settings.ENABLE_NOTIFICATION_DISPATCH: bool = True`; scheduler executor alias `"notifications"`; job id `"notification_dispatch"`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_main.py`:

```python
import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch

from app import main


def _registered(scheduler: MagicMock) -> dict:
    return {c.kwargs["id"]: c.kwargs for c in scheduler.add_job.call_args_list}


class TestTheDispatchJobIsRegistered(unittest.TestCase):
    def test_it_is_added_with_a_stable_id(self):
        scheduler = MagicMock()

        main.add_jobs(scheduler)

        self.assertIn("notification_dispatch", _registered(scheduler))

    def test_it_runs_the_dispatch_job(self):
        scheduler = MagicMock()

        main.add_jobs(scheduler)

        job = _registered(scheduler)["notification_dispatch"]
        self.assertIs(job["func"], main.run_notification_dispatch_job)

    def test_it_runs_every_five_minutes_by_default(self):
        scheduler = MagicMock()

        main.add_jobs(scheduler)

        job = _registered(scheduler)["notification_dispatch"]
        self.assertEqual(job["trigger"].interval, timedelta(minutes=5))

    def test_the_interval_comes_from_the_settings(self):
        scheduler = MagicMock()

        with patch.object(main.settings, "NOTIFICATION_DISPATCH_INTERVAL_MINUTES", 2):
            main.add_jobs(scheduler)

        job = _registered(scheduler)["notification_dispatch"]
        self.assertEqual(job["trigger"].interval, timedelta(minutes=2))

    def test_it_runs_on_its_own_executor(self):
        scheduler = MagicMock()

        main.add_jobs(scheduler)

        job = _registered(scheduler)["notification_dispatch"]
        self.assertEqual(job["executor"], "notifications")

    def test_it_replaces_the_stored_job(self):
        scheduler = MagicMock()

        main.add_jobs(scheduler)

        job = _registered(scheduler)["notification_dispatch"]
        self.assertTrue(job["replace_existing"])

    def test_it_is_still_registered_when_switched_off(self):
        scheduler = MagicMock()

        with patch.object(main.settings, "ENABLE_NOTIFICATION_DISPATCH", False):
            main.add_jobs(scheduler)

        self.assertIn("notification_dispatch", _registered(scheduler))

    def test_switching_it_off_keeps_the_collocation_job(self):
        scheduler = MagicMock()

        with patch.object(main.settings, "ENABLE_NOTIFICATION_DISPATCH", False):
            main.add_jobs(scheduler)

        self.assertIn("file_collocation", _registered(scheduler))


class TestASwitchedOffDispatchJob(unittest.TestCase):
    def test_it_does_not_call_the_gatekeeper(self):
        from app.jobs import notification_dispatch_job

        with (
            patch.object(notification_dispatch_job.settings, "ENABLE_NOTIFICATION_DISPATCH", False),
            patch.object(notification_dispatch_job, "GatekeeperClient") as gatekeeper,
        ):
            notification_dispatch_job.run_notification_dispatch_job()

        gatekeeper.assert_not_called()


class TestTheSchedulerHasAnExecutorForNotifications(unittest.TestCase):
    def _scheduler(self):
        with (
            patch.object(main, "get_scheduler_engine"),
            patch.object(main, "SQLAlchemyJobStore"),
        ):
            return main.create_scheduler()

    def test_the_notifications_executor_exists(self):
        self.assertIn("notifications", self._scheduler()._executors)

    def test_the_default_executor_is_still_there_for_collocation(self):
        self.assertIn("default", self._scheduler()._executors)
```

`_executors` is APScheduler 3's private registry, filled by the constructor's `configure()`. It is the only way to see the executors before `start()`; if an APScheduler upgrade moves it, this test is the one to update.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/caio.maia/workspace/datamap/archivist && pytest tests/unit/test_main.py -q`
Expected: failures — `KeyError: 'notification_dispatch'` / `AssertionError: 'notification_dispatch' not found`, `AttributeError: ... has no attribute 'NOTIFICATION_DISPATCH_INTERVAL_MINUTES'`, and `'notifications' not found` in the executors. `test_switching_it_off_keeps_the_collocation_job` may already pass only after the settings exist; that is fine.

- [ ] **Step 3: Add the settings**

In `app/config.py`, the `# Job configuration` block becomes:

```python
    # Job configuration
    JOB_INTERVAL_MINUTES: int = 15
    SHARD_THRESHOLD: int = 30  # Files per shard folder
    ENABLE_SCHEDULER: bool = True  # Set to False to disable automatic scheduling
    MAX_WORKERS: int = 10  # Number of parallel workers for file operations
    NOTIFICATION_DISPATCH_INTERVAL_MINUTES: int = 5
    ENABLE_NOTIFICATION_DISPATCH: bool = True
```

In `local.env.example`, the `# Job Configuration` block becomes:

```
# Job Configuration
JOB_INTERVAL_MINUTES=15
SHARD_THRESHOLD=30
ENABLE_SCHEDULER=true  # Set to false to disable automatic scheduling (use only manual triggers)
NOTIFICATION_DISPATCH_INTERVAL_MINUTES=5
ENABLE_NOTIFICATION_DISPATCH=true  # Set to false until the gatekeeper has the dispatch route
```

- [ ] **Step 4: Add the executor and register the job**

In `app/main.py`, add the import next to the collocation one:

```python
from app.jobs.file_collocation_job import run_file_collocation_job
from app.jobs.notification_dispatch_job import run_notification_dispatch_job
```

In `create_scheduler()`, the executors become:

```python
    # Configure executors
    executors = {
        "default": ThreadPoolExecutor(max_workers=1),  # Single worker for singleton job
        # Its own thread, or a long collocation run would hold every email back.
        "notifications": ThreadPoolExecutor(max_workers=1),
    }
```

At the end of `add_jobs()`, after the collocation job's `logger.info(...)`:

```python
    scheduler.add_job(
        func=run_notification_dispatch_job,
        trigger=IntervalTrigger(minutes=settings.NOTIFICATION_DISPATCH_INTERVAL_MINUTES),
        id="notification_dispatch",
        name="Notification Dispatch Job",
        executor="notifications",
        replace_existing=True,
    )

    logger.info(
        "added notification dispatch job",
        extra=fields(interval_minutes=settings.NOTIFICATION_DISPATCH_INTERVAL_MINUTES),
    )
```

and add `fields` to the logging import at the top of `app/main.py`:

```python
from app.logging_config import fields, setup_logging
```

The job is registered whether or not it is switched on, and the switch is read when the job runs. The job store is persistent: a job left out of `add_jobs` would stay in `apscheduler_jobs` from an earlier deploy and keep running, so not registering it would not switch it off.

In `app/jobs/notification_dispatch_job.py`, import the settings and check the switch first thing in `run_notification_dispatch_job()`:

```python
from app.config import settings
```

```python
def run_notification_dispatch_job() -> None:
    if not settings.ENABLE_NOTIFICATION_DISPATCH:
        logger.debug("notification dispatch is switched off")
        return

    logger.debug("starting notification dispatch job")
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd /Users/caio.maia/workspace/datamap/archivist && pytest tests/unit/test_main.py -q`
Expected: `11 passed`.

- [ ] **Step 6: Commit**

```bash
cd /Users/caio.maia/workspace/datamap/archivist
git add app/config.py local.env.example app/main.py tests/unit/test_main.py
git commit -m "feat: dispatch due email every 5 minutes, on a thread of its own

A long collocation run used to be the only job on the scheduler's one
worker; the dispatch gets its own executor so it is never held behind it.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Full suite, lint and a local run against the gatekeeper

**Files:** none new.

**Interfaces:**
- Consumes: the gatekeeper's `POST /api/v1/internal/notifications/dispatch` (plan 01). The local run in Step 3 needs a gatekeeper with plan 01 merged; if it is not yet available, do Steps 1–2 and record that Step 3 is pending.

- [ ] **Step 1: Run the whole suite as CI does**

Run: `cd /Users/caio.maia/workspace/datamap/archivist && pytest tests -q`
Expected: every test passes, including the existing `test_file_collocation_job.py`, `test_heartbeat.py` and `test_logging_config.py`; the count is the previous total plus 31.

- [ ] **Step 2: Lint and format as CI does**

Run:

```bash
cd /Users/caio.maia/workspace/datamap/archivist
pip install ruff==0.5.3
ruff check app
ruff format --check app
```

Expected: `All checks passed!` and `N files already formatted`. If `ruff format --check` lists a file, run `ruff format app`, re-run the tests, and commit the formatting on its own:

```bash
git add app
git commit -m "style: ruff format

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 3: Run the job once against a local gatekeeper**

With the gatekeeper running locally (port 9092) and plan 01 merged:

```bash
cd /Users/caio.maia/workspace/datamap/archivist
GATEKEEPER_API_URL=http://localhost:9092 python -c "
from app.logging_config import setup_logging
from app.jobs.notification_dispatch_job import run_notification_dispatch_job
setup_logging()
run_notification_dispatch_job()
"
```

with `GATEKEEPER_API_KEY`, `GATEKEEPER_API_SECRET`, `POSTGRES_PASSWORD`, `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` exported from `local.env`.

Expected: with nothing queued, one INFO line `{"message": "notification dispatch idle", "quiet_runs": 0, ...}`; with a message queued in the gatekeeper's `email_messages`, one `notification dispatch completed` line whose `sent` (or `skipped`) is 1. With the wrong secret, one ERROR `notification dispatch failed` naming a `401`, and the process exits 0.

- [ ] **Step 4: Run the service and confirm both jobs are scheduled**

```bash
cd /Users/caio.maia/workspace/datamap/archivist
make ENV_FILE_PATH=local.env python-run
```

Expected in the startup log, under `Scheduled jobs:`:

```
  - File Collocation Job (ID: file_collocation), Next run: ...
  - Notification Dispatch Job (ID: notification_dispatch), Next run: ...
```

followed by `Scheduler started, waiting for jobs to execute...` — the line the deploy waits for (`.github/workflows/ci.yml` readiness check). Stop it with Ctrl+C.

- [ ] **Step 5: Push and open the PR**

```bash
cd /Users/caio.maia/workspace/datamap/archivist
git push -u origin feat/notification-dispatch
gh pr create --base main --title "feat: dispatch due email every 5 minutes" --body "Calls the gatekeeper's POST /api/v1/internal/notifications/dispatch (RFC 003 §Notifications, gatekeeper plan 01) every NOTIFICATION_DISPATCH_INTERVAL_MINUTES (default 5), on an executor of its own.

Merge after the gatekeeper route is deployed, or set ENABLE_NOTIFICATION_DISPATCH=false in production until it is.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

---

## Self-review against the spec

- Route, credentials and response shape: contracts §Notifications → Task 1.
- 5-minute interval, own executor, stable id, `replace_existing`, coalesce/max_instances: RFC §How a message moves, archivist report §1 → Task 3.
- "The Archivist triggers; the gatekeeper owns the data, the templates and the SMTP connection": the job only calls and logs → Task 2.
- At-most-once delivery and `SKIP LOCKED` are the gatekeeper's (plan 01); nothing here retries a message, only the call, and the call is idempotent on the gatekeeper side.
- Metrics: explicitly out of scope (Global Constraints).
- Deploy order and the switch: Global Constraints, Task 3 Step 3, Task 4 Step 5.
