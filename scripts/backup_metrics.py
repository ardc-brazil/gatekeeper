"""Write the backup's outcome where node_exporter's textfile collector reads it.

A backup that fails silently is worth little more than no backup. This is what
turns "did it run last night" into a question Prometheus answers.
"""

import os
from datetime import datetime
from pathlib import Path

METRICS = (
    (
        "datamap_backup_last_success_timestamp_seconds",
        "Unix time of the last database backup that was written and verified",
    ),
    ("datamap_backup_last_size_bytes", "Size of the last database backup"),
    ("datamap_backup_kept", "Backups currently on the NAS"),
)


def render(moment: datetime, size_bytes: int, kept: int) -> str:
    values = (int(moment.timestamp()), size_bytes, kept)
    lines = []
    for (name, help_text), value in zip(METRICS, values):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {value}")
    return "\n".join(lines) + "\n"


def write(target: Path, moment: datetime, size_bytes: int, kept: int) -> bool:
    partial = target.with_suffix(target.suffix + ".partial")
    try:
        partial.write_text(render(moment, size_bytes, kept))
        os.replace(partial, target)
    except OSError:
        partial.unlink(missing_ok=True)
        return False
    return True
