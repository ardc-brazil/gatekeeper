import json
import subprocess
import time
import uuid
from typing import Callable

API_CONTAINER = "datamap_gatekeeper_test_integration"


def container_log(since_seconds: int = 60) -> str:
    result = subprocess.run(
        ["docker", "logs", "--since", f"{since_seconds}s", API_CONTAINER],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout + result.stderr


def wait_for_log(
    written: Callable[[str], bool], timeout: float = 5.0, since_seconds: int = 60
) -> str:
    """Poll the container log until `written` holds, and return the log either
    way, so the caller's own assertion is what reports a timeout."""
    deadline = time.monotonic() + timeout
    while True:
        log = container_log(since_seconds)
        if written(log) or time.monotonic() >= deadline:
            return log
        time.sleep(0.05)


def flush_log(http_client, headers: dict, since_seconds: int = 60) -> str:
    """Wait until a request made now is in the log. Every line written before it
    is then in the log too, which is what an assertion of absence needs."""
    barrier = f"barrier-{uuid.uuid4()}"
    http_client.get("/clients/", headers={**headers, "X-Request-Id": barrier})
    return wait_for_log(lambda log: barrier in log, since_seconds=since_seconds)


def access_lines(log: str, marker: str) -> list[dict]:
    return [
        entry
        for line in log.splitlines()
        if marker in line
        for entry in [json.loads(line)]
        if entry.get("logger") == "http.access"
    ]
