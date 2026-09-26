"""Set one variable in an environment file without the value being visible.

Prompts twice with the echo off, writes the value verbatim, and prints only a
fingerprint. Two files hold the same credential when they print the same
fingerprint, which is how a shared secret is checked without anyone reading it.

    python3 scripts/set_env_value.py ~/environment/gatekeeper.prod.env DOI_PASSWORD
"""

import getpass
import hashlib
import os
import re
import sys
from pathlib import Path


def fingerprint(value: str) -> str:
    return hashlib.sha1(value.encode()).hexdigest()[:8]


# The Makefile reads these files with `include`, so they are parsed as make
# syntax before a container ever sees them: `#` starts a comment and `$` is a
# variable reference. A password containing either breaks the deploy in a way
# that looks nothing like its cause.
REINTERPRETED = "#$`"


def replace_assignment(content: str, name: str, value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("a value cannot contain a newline")
    if value != value.strip():
        raise ValueError("a value cannot start or end with whitespace")
    offending = sorted(set(value) & set(REINTERPRETED))
    if offending:
        raise ValueError(
            f"a value cannot contain {' '.join(offending)}: "
            "the Makefile reads this file as make syntax"
        )

    pattern = re.compile(rf"^{re.escape(name)}=.*$", re.MULTILINE)
    matches = pattern.findall(content)
    if not matches:
        raise KeyError(f"{name} is not assigned in this file")
    if len(matches) > 1:
        raise ValueError(f"{name} is assigned {len(matches)} times")

    return pattern.sub(lambda _: f"{name}={value}", content, count=1)


def prompt_twice(name: str) -> str:
    value = getpass.getpass(f"new {name}: ")
    if not value:
        raise SystemExit("empty value, nothing written")
    if value != getpass.getpass("again: "):
        raise SystemExit("the two entries differ, nothing written")
    return value


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    path, name = Path(sys.argv[1]).expanduser(), sys.argv[2]
    content = path.read_text()
    value = prompt_twice(name)

    try:
        updated = replace_assignment(content, name, value)
    except (KeyError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1

    # Write through a temporary file in the same directory so an interrupted
    # write cannot leave the environment file truncated.
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(updated)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)

    print(f"{name} written to {path}")
    print(f"fingerprint: {fingerprint(value)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
