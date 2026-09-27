"""Compare two environment files by key and value, reporting neither value.

The deploy decrypts secrets/production into a temporary file and runs this
against the plaintext still on the host. A mismatch means the encrypted copy has
drifted from what production actually uses, and the deploy stops rather than
applying a configuration nobody reviewed.

    python3 scripts/compare_env_files.py a.env b.env
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ASSIGNMENT = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


@dataclass(frozen=True)
class Difference:
    name: str
    reason: str


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ASSIGNMENT.match(stripped)
        if match is None:
            continue
        values[match.group(1)] = match.group(2).strip().strip("\"'")
    return values


def compare(first: Path, second: Path) -> list[Difference]:
    left, right = read_env(first), read_env(second)

    differences = []
    for name in sorted(set(left) | set(right)):
        if name not in right:
            differences.append(Difference(name, "missing from the second file"))
        elif name not in left:
            differences.append(Difference(name, "missing from the first file"))
        elif left[name] != right[name]:
            differences.append(Difference(name, "value differs"))
    return differences


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    first, second = Path(sys.argv[1]), Path(sys.argv[2])
    differences = compare(first, second)

    if not differences:
        print(f"{len(read_env(first))} variables, identical in both files")
        return 0

    print(f"{first} and {second} differ:", file=sys.stderr)
    for difference in differences:
        print(f"  {difference.name}: {difference.reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
