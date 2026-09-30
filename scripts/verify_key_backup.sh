#!/bin/bash
# Prove that the copy of the age key in the password manager can decrypt
# secrets/production, and that the test would have failed if it could not.
#
#   pbpaste | scripts/verify_key_backup.sh -          # paste, nothing on disk
#   scripts/verify_key_backup.sh /path/to/key.txt     # from a file
#
# Runs sops inside a container with only that key mounted, so it cannot fall back
# to ~/.config/sops/age/keys.txt and pass for the wrong reason. Until this passes,
# the backup is a hypothesis; see docs/runbooks/secrets.md.
set -euo pipefail

SOURCE=${1:-}
FILE=${2:-secrets/production/gatekeeper.env}
IMAGE=ghcr.io/getsops/sops:v3.13.3-alpine

if [ -z "$SOURCE" ]; then
  echo "usage: $0 <key-file|-> [encrypted-file]" >&2
  echo "       pbpaste | $0 -" >&2
  exit 2
fi

work=$(mktemp -d)
chmod 700 "$work"
trap 'rm -rf "$work"' EXIT

# Reading the key from stdin is the point of the `-` form: a paste from the
# password manager never becomes a file the caller has to remember to delete.
if [ "$SOURCE" = "-" ]; then
  ( umask 077; cat > "$work/key.txt" )
elif [ -f "$SOURCE" ]; then
  ( umask 077; cat "$SOURCE" > "$work/key.txt" )
else
  echo "no such file: $SOURCE" >&2
  exit 2
fi

if ! grep -q "AGE-SECRET-KEY-" "$work/key.txt"; then
  echo "that does not contain an age secret key. Paste all of it, including" >&2
  echo "the AGE-SECRET-KEY- line." >&2
  exit 1
fi

decrypt_with() {
  docker run --rm \
    -v "$(cd "$(dirname "$FILE")" && pwd):/secrets:ro" \
    -v "$1:/key.txt:ro" \
    -e SOPS_AGE_KEY_FILE=/key.txt \
    "$IMAGE" --decrypt "/secrets/$(basename "$FILE")" 2>&1
}

echo "=== the backed-up key decrypts $FILE ==="
if output=$(decrypt_with "$work/key.txt") \
  && count=$(printf %s "$output" | grep -cE '^[A-Za-z_][A-Za-z0-9_]*='); then
  echo "  yes: $count variables"
else
  echo "  NO. This backup cannot restore production configuration." >&2
  printf '  %s\n' "$output" | head -3 >&2
  exit 1
fi

# Without this the test proves only that decryption happened somehow, which is
# also what a silent fallback to a local key would look like.
echo
echo "=== and a wrong key is refused, so the test above meant something ==="
printf 'AGE-SECRET-KEY-1QQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQ\n' \
  > "$work/wrong.txt"
if decrypt_with "$work/wrong.txt" >/dev/null 2>&1; then
  echo "  a deliberately wrong key ALSO decrypted it: this test proves nothing" >&2
  exit 1
fi
echo "  refused, as it must be"

echo
echo "The key in the password manager is a working backup."
