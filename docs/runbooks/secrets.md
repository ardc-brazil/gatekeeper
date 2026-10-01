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
the deploy if any of their values appears in a tracked file. That is why every
file is decrypted and not only the gatekeeper's: reading one would quietly stop
checking the other services' credentials.

**The encrypted copies are the source of truth.** There is no plaintext to drift
from any more, which is why the deploy no longer compares against one — with a
single source, drift is not something to detect, it is something that cannot
happen. The files that used to hold it are at `~/environment/retired-<date>/` on
the host, and can be deleted once nobody misses them.

To change a value, edit the encrypted file and merge it. There is no second copy
to keep in step:

```bash
sops secrets/production/gatekeeper.env
```
