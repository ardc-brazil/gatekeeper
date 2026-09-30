#!/bin/bash
# Prove that the copy of the age key in the password manager can decrypt
# secrets/production, and that the test would have failed if it could not.
#
#   scripts/verify_key_backup.sh /path/to/key-pasted-from-password-manager.txt
#
# Runs sops inside a container with only that file mounted, so it cannot fall
# back to ~/.config/sops/age/keys.txt and pass for the wrong reason. Until this
# passes, the backup is a hypothesis; see docs/runbooks/secrets.md.
set -euo pipefail

KEY=${1:-}
FILE=${2:-secrets/production/gatekeeper.env}
IMAGE=ghcr.io/getsops/sops:v3.13.3-alpine

if [ -z "$KEY" ] || [ ! -f "$KEY" ]; then
  echo "usage: $0 <key-file-from-password-manager> [encrypted-file]" >&2
  exit 2
fi

decrypt_with() {
  docker run --rm \
    -v "$(cd "$(dirname "$FILE")" && pwd):/secrets:ro" \
    -v "$(cd "$(dirname "$1")" && pwd)/$(basename "$1"):/key.txt:ro" \
    -e SOPS_AGE_KEY_FILE=/key.txt \
    "$IMAGE" --decrypt "/secrets/$(basename "$FILE")" 2>&1
}

echo "=== the backed-up key decrypts $FILE ==="
if output=$(decrypt_with "$KEY") && count=$(printf %s "$output" | grep -cE '^[A-Za-z_][A-Za-z0-9_]*='); then
  echo "  yes: $count variables"
else
  echo "  NO. This backup cannot restore production configuration." >&2
  printf '  %s\n' "$output" | head -3 >&2
  exit 1
fi

# Without this the test proves only that decryption happened somehow, which is
# what a silent fallback to a local key would also look like.
echo
echo "=== and a wrong key is refused, so the test above meant something ==="
wrong=$(mktemp)
trap 'rm -f "$wrong"' EXIT
docker run --rm "$IMAGE" --version >/dev/null 2>&1 || true
printf 'AGE-SECRET-KEY-1QQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQ\n' > "$wrong"
if decrypt_with "$wrong" >/dev/null 2>&1; then
  echo "  a deliberately wrong key ALSO decrypted it: this test proves nothing" >&2
  exit 1
fi
echo "  refused, as it must be"

echo
echo "The key in the password manager is a working backup."
