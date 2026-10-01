"""Every script here must start the way it is documented.

`python3 scripts/env_fingerprint.py` was documented and did not run: the module
imports from its own package, which only works through `-m`. Whoever reached for
the tool got a ModuleNotFoundError instead.

`-m` works for all of them. The ones below are also run by path, from a runbook
or by hand on the host, and a reader cannot be expected to know which form a
given script needs.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = sorted(
    path.stem
    for path in Path("scripts").glob("*.py")
    if path.stem != "__init__" and not path.stem.endswith("_test")
)

# Not generate_legacy_snapshots: it imports the application package, so it only
# runs as a module, and the Makefile invokes it that way.
ALSO_RUN_BY_PATH = [
    "backup_database",
    "backup_metrics",
    "check_tracked_secrets",
    "compare_env_files",
    "env_fingerprint",
    "set_env_value",
]


def _start(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout + result.stderr


def test_the_list_of_path_runnable_scripts_is_still_accurate():
    assert set(ALSO_RUN_BY_PATH) <= set(SCRIPTS), set(ALSO_RUN_BY_PATH) - set(SCRIPTS)


@pytest.mark.parametrize("name", SCRIPTS)
def test_starts_as_a_module(name: str):
    output = _start([sys.executable, "-m", f"scripts.{name}"])

    assert "ModuleNotFoundError" not in output, output[-400:]
    assert "ImportError" not in output, output[-400:]


@pytest.mark.parametrize("name", ALSO_RUN_BY_PATH)
def test_starts_as_a_path(name: str):
    output = _start([sys.executable, f"scripts/{name}.py"])

    assert "ModuleNotFoundError" not in output, output[-400:]
    assert "ImportError" not in output, output[-400:]
