# Production secrets

Production configuration used to exist in exactly one place: `~/environment` on
the production host, edited by hand, with no history, no review and no backup.
It is now also in this repository, encrypted, so that changing it is a commit
and losing that host is not the end of it.

Two values were public in this repository for months before that — since
2024-04-07 and 2025-09-02 — and have been rotated. Encrypting first would have
hidden values that were already known; see the commit that removed them.

## What is and is not protected

The deploy host and the CI runner are the same machine, so the plaintext is
written on it at deploy time either way. **This is not secrecy from someone with
that host.** What it buys is version control, review, and a copy that survives
the disk.

Keys are readable in the encrypted files and only values are hidden, which is
deliberate: a diff still shows *which* variable changed.

## The key

One age key, at `~/.config/sops/age/keys.txt` on the production host and on each
maintainer's machine, `0600`. Its public half is in `.sops.yaml` and is the only
thing that decides who can encrypt.

**Losing every copy of the private key means re-issuing every credential in
`secrets/production` by hand**: rotating the database password, the MinIO root and
service accounts, the client secrets, the upload token, the DOI account. There
is no recovery path that does not go through
[credential-rotation.md](credential-rotation.md).

So the key belongs in a password manager, not only on these two machines.

### Proving that copy works

A backup nobody has restored from is a hypothesis, and the ways a pasted key goes
wrong are quiet: a truncated paste, a missing final newline, a field that ate the
whitespace.

```bash
pbpaste | scripts/verify_key_backup.sh -
```

It decrypts inside a container with only that key mounted, so it cannot fall back
to `~/.config/sops/age/keys.txt` and pass for the wrong reason, and it then
checks that a deliberately wrong key **is** refused — because a test that only
ever passes proves nothing. Reading from stdin means the paste never becomes a
file to remember to delete.

Until this passes, treat the plaintext on the host as the real recovery path and
do not remove it.

## Reading and changing a value

```bash
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt

sops --decrypt secrets/production/gatekeeper.env        # read it
sops secrets/production/gatekeeper.env                  # edit it, in $EDITOR
```

`sops` re-encrypts on save, and only the values that changed get new
ciphertext, so the diff stays legible.

Do not decrypt into a file inside the repository. `.gitignore` covers the
obvious names, but the habit is what protects the repository, not the list.

## `sops` drops blank lines

Worth knowing before comparing a decrypted file against anything: dotenv mode
loses blank lines. Measured when the encrypted copies were first made against the
plaintext they came from — 38 keys, same order, every value identical, comments
preserved, six blank lines gone, and `make` reading the same 37 variables with the
same values from either file.

So compare keys and values, not bytes. `scripts/env_fingerprint.py` and
`scripts/compare_env_files.py` both do that, the first for one variable and the
second for a whole file.

## What the deploy does

It installs the pinned `sops`, decrypts every file in `secrets/production` into
the runner's temporary directory under `umask 077`, and uses `gatekeeper.env` as
the environment the containers read. The decrypted copies are removed afterwards,
including when the job fails.

`scripts/check_tracked_secrets.py` runs against those decrypted copies and fails
the deploy if any of their values appears in a tracked file.

It sees this repository's credentials only. The archivist and the webapp hold
their own encrypted configuration in their own repositories and decrypt it in
their own deploys — one owner per secret, nothing to drift, and each repository
guarding what it holds. A secret shared across two of them, like the upload
token the webapp signs and this service verifies, has to be changed in both.

**The encrypted copies are the source of truth.** There is no plaintext to drift
from any more, which is why the deploy no longer compares against one — with a
single source, drift is not something to detect, it is something that cannot
happen. The files that used to hold it are at `~/environment/retired-<date>/` on
the host, and can be deleted once nobody misses them.

## Running something by hand on the host

`~/environment` no longer holds a plaintext file to point `ENV_FILE_PATH` at, so
decrypt one where it will be cleaned up:

```bash
cd /home/datamap/actions-runner/_work/gatekeeper/gatekeeper
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; umask 077
~/bin/sops --decrypt secrets/production/scripts-gatekeeper.env > "$T/env"
make ENV_FILE_PATH="$T/env" SCRIPT=generate_legacy_snapshots run-script
```

The `trap` is the point: without it the file outlives the shell. The archivist's
own configuration works the same way, with `--input-type dotenv --output-type
dotenv`, because sops cannot infer the format of its `.env.sops` names.

`make` is doing more than passing a path: `include ${ENV_FILE_PATH}` plus
`export` puts every variable in its own environment, which is what `${VAR}` in a
compose file is expanded from. A bare `docker compose` with only `ENV_FILE_PATH`
set leaves those blank — including the host paths of the database and object
storage. Source the file as well, and see
[host-applied-changes.md](host-applied-changes.md):

```bash
set -a; . "$ENV_FILE_PATH"; set +a
```

The retired plaintext is in `~/environment/retired-<date>/` if something needs it
in a hurry, and can be deleted once nobody has.

## Changing a value

Edit the encrypted file and merge it. There is no second copy to keep in step:

```bash
sops secrets/production/gatekeeper.env
```
