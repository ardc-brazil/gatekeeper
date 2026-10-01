"""Dump the production database to the NAS, verify it, and prune old copies.

The dump runs inside the database container over the unix socket, so this holds
no credential of its own.

    python3 scripts/backup_database.py --output-dir /home/datamap/storage/backups/postgres
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:  # invoked as `python3 -m scripts.backup_database`
    from scripts.backup_metrics import write as write_metrics
except ImportError:  # invoked as `python3 scripts/backup_database.py`
    from backup_metrics import write as write_metrics

CONTAINER = "datamap_gatekeeper_db"
DATABASE = "gatekeeper_db"
ROLE = "gk_admin"

PREFIX = f"{DATABASE}-"
SUFFIX = ".dump"
STAMP = "%Y%m%dT%H%M%SZ"
NAME = re.compile(rf"^{re.escape(PREFIX)}(\d{{8}}T\d{{6}}Z){re.escape(SUFFIX)}$")

# The NAS is an autofs mount: when the NFS server is unreachable the directory
# still exists and is empty, so a backup would land on the local disk believing
# it reached the NAS. This file only exists on the NAS.
MARKER = ".datamap-nas"


def backup_name(moment: datetime) -> str:
    return f"{PREFIX}{moment.strftime(STAMP)}{SUFFIX}"


def parse_backup_date(name: str) -> datetime | None:
    match = NAME.match(name)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), STAMP).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def storage_is_mounted(directory: Path) -> bool:
    return (directory / MARKER).exists()


def to_prune(
    names: list[str], now: datetime, keep_daily: int, keep_monthly: int
) -> list[str]:
    if keep_daily < 1 or keep_monthly < 1:
        raise ValueError("retention must keep at least one daily and one monthly copy")

    dated = [(name, parse_backup_date(name)) for name in names]
    recognised = sorted(
        ((name, when) for name, when in dated if when is not None),
        key=lambda pair: pair[1],
        reverse=True,
    )
    if not recognised:
        return []

    daily_after = now - timedelta(days=keep_daily)
    monthly_after = now - timedelta(days=31 * keep_monthly)

    expired = []
    for name, when in recognised:
        if when >= daily_after:
            continue
        if when.day == 1 and when >= monthly_after:
            continue
        expired.append(name)

    # Whatever the retention says, leaving nothing behind is never the answer.
    if len(expired) == len(recognised):
        expired.remove(recognised[0][0])
    return expired


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, capture_output=True, **kwargs)


def take_backup(directory: Path, now: datetime) -> Path:
    final = directory / backup_name(now)
    partial = final.with_suffix(final.suffix + ".partial")

    with partial.open("wb") as handle:
        subprocess.run(
            ["docker", "exec", CONTAINER, "pg_dump", "-U", ROLE, "-d", DATABASE, "-Fc"],
            check=True,
            stdout=handle,
            stderr=subprocess.PIPE,
        )

    with partial.open("rb") as handle:
        run(["docker", "exec", "-i", CONTAINER, "pg_restore", "--list"], stdin=handle)

    partial.rename(final)
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--keep-daily", type=int, default=30)
    parser.add_argument("--keep-monthly", type=int, default=12)
    parser.add_argument("--metrics-file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    directory: Path = arguments.output_dir
    if not storage_is_mounted(directory):
        print(
            f"{directory} does not carry {MARKER}: the NAS is not mounted, refusing "
            "to write a backup to the local disk",
            file=sys.stderr,
        )
        return 2

    now = datetime.now(timezone.utc)
    size = 0
    if arguments.dry_run:
        print(f"would write {backup_name(now)}")
    else:
        written = take_backup(directory, now)
        size = written.stat().st_size
        print(f"wrote {written.name} ({size // 1024} KiB), verified")

    names = [path.name for path in directory.iterdir() if path.is_file()]
    expired = to_prune(names, now, arguments.keep_daily, arguments.keep_monthly)
    for name in expired:
        if arguments.dry_run:
            print(f"would prune {name}")
        else:
            (directory / name).unlink()
            print(f"pruned {name}")

    remaining = [
        path.name
        for path in directory.iterdir()
        if path.is_file() and parse_backup_date(path.name)
    ]
    print(f"{len(remaining)} backups kept")

    if arguments.metrics_file and not arguments.dry_run:
        if write_metrics(arguments.metrics_file, now, size, len(remaining)):
            print(f"metrics written to {arguments.metrics_file}")
        else:
            # The backup succeeded; a metric that could not be written is
            # not a reason to report failure.
            print(
                f"could not write metrics to {arguments.metrics_file}", file=sys.stderr
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
