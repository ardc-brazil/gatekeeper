"""Fail if a production credential value appears in any tracked file.

Runs on the production host, where the environment files live. Reports the
variable name and the file that contains it, never the value.
"""

import re
import subprocess
import sys
from pathlib import Path

DEFAULT_ENV_DIR = Path("/home/datamap/environment")

# Deliberately not `_USER`: usernames collide across services by design, and a
# username is not what a deploy should be blocked on.
CREDENTIAL_KEY = re.compile(r"SECRET|PASSWORD|TOKEN|_KEY$|_KEY_ID$")

MIN_VALUE_LENGTH = 8

ASSIGNMENT = re.compile(r"^([A-Z0-9_]+)=(.*)$")


def production_credentials(env_dir: Path) -> dict[str, str]:
    credentials: dict[str, str] = {}
    for path in sorted(env_dir.glob("*.env")):
        for line in path.read_text(errors="replace").splitlines():
            match = ASSIGNMENT.match(line.strip())
            if match is None:
                continue
            name, value = match.group(1), match.group(2).strip().strip("\"'")
            if CREDENTIAL_KEY.search(name) and len(value) >= MIN_VALUE_LENGTH:
                credentials.setdefault(value, name)
    return credentials


def scan(credentials: dict[str, str], paths: list[Path]) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    for path in paths:
        try:
            content = path.read_text(errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        for value, name in credentials.items():
            if value in content:
                findings.append((name, str(path)))
    return findings


def tracked_files() -> list[Path]:
    listing = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    return [Path(name) for name in listing.decode().split("\0") if name]


def main() -> int:
    env_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ENV_DIR
    if not env_dir.is_dir():
        print(f"environment directory not found: {env_dir}", file=sys.stderr)
        return 2

    credentials = production_credentials(env_dir)
    if not credentials:
        print(f"no credentials read from {env_dir}", file=sys.stderr)
        return 2

    findings = scan(credentials, tracked_files())

    print(f"checked {len(credentials)} production credentials against tracked files")
    if not findings:
        print("no production credential is tracked")
        return 0

    print("\nproduction credentials found in tracked files:", file=sys.stderr)
    for name, path in sorted(set(findings)):
        print(f"  {name} -> {path}", file=sys.stderr)
    print(
        "\nRotate the value and remove it from the file. A tracked credential is "
        "public: this repository is public.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
