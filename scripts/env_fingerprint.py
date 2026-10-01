"""Print a fingerprint of one or more variables in an environment file.

A credential shared by two services is correct when both files print the same
fingerprint. Nothing else about the value is revealed, so the comparison can be
made, quoted and shared.

    python3 scripts/env_fingerprint.py secrets/decrypted.env AUTH_FILE_UPLOAD_TOKEN_SECRET
"""

import re
import sys
from pathlib import Path

try:  # invoked as `python3 -m scripts.env_fingerprint`
    from scripts.set_env_value import fingerprint
except ImportError:  # invoked as `python3 scripts/env_fingerprint.py`
    from set_env_value import fingerprint

ABSENT = "absent"


def fingerprints(path: Path, names: list[str]) -> dict[str, str]:
    content = path.read_text()
    found: dict[str, str] = {}
    for name in names:
        match = re.search(rf"^{re.escape(name)}=(.*)$", content, re.MULTILINE)
        if match is None:
            found[name] = ABSENT
            continue
        found[name] = fingerprint(match.group(1).strip().strip("\"'"))
    return found


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2

    path = Path(sys.argv[1]).expanduser()
    found = fingerprints(path, sys.argv[2:])
    for name, value in found.items():
        print(f"{name} {value}")
    return 1 if ABSENT in found.values() else 0


if __name__ == "__main__":
    sys.exit(main())
