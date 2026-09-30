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

## Round-tripping is not byte-exact, and that is fine

`sops` in dotenv mode drops blank lines. Measured on
`gatekeeper.prod.env`: 38 keys, same order, every value identical, comments
preserved, six blank lines gone. `make` reads the same 37 variables with the
same values from either file — the only difference it sees is `ENV_FILE_PATH`
itself, which is the path being read.

So do not expect `diff` against the plaintext to be empty. Compare keys and
values, which is what `scripts/env_fingerprint.py` is for.

## What the deploy does

It installs the pinned `sops`, decrypts `secrets/production/gatekeeper.env` into
the runner's temporary directory under `umask 077`, and **compares it against the
plaintext still on the host**. Any difference — a changed value, a variable on
one side only — stops the deploy before anything is built. The decrypted file is
removed afterwards, including when the job fails.

Only then does the rest of the deploy use the decrypted copy.

So the plaintext on the host is no longer what runs, but it is still the
reference the encrypted copy is checked against. That is deliberate: it makes
drift impossible to deploy rather than merely documented. After changing a value
on the host, encrypt it back in, or the next deploy refuses:

```bash
sops --encrypt --input-type dotenv --output-type dotenv \
  ~/environment/gatekeeper.prod.env > secrets/production/gatekeeper.env
```

The failure names the variables and not their values, so the output of a refused
deploy is safe to paste anywhere:

```
/home/datamap/environment/gatekeeper.prod.env and /tmp/gatekeeper.env differ:
  LOG_LEVEL: value differs
  SOME_NEW_VARIABLE: missing from the first file
```

Removing the plaintext entirely would remove that check with it, so it is not a
tidying step: it needs something else to compare against first.
