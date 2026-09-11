# Post-deploy verification

What to check after the first deploy that carries the September 2026 fixes, and
what the numbers were before it, so a change is visible rather than assumed.

Production sat on `better-full-text-search @ 4d8e2d8` (January) until this
deploy. Every step below is read-only.

## Baseline, measured 2026-09-09

Over a 90-day window on `datamap_gatekeeper`:

| Hook type | Calls | Result |
|---|---|---|
| `pre-create` | 3 | 200 — does not touch the database |
| `post-create` | 3 | 200 — does not touch the database |
| `post-receive` | 1 | 200 — does not touch the database |
| `post-finish` | 9 | **9 × 500** |

Nine `post-finish` hooks, nine failures, no successes. TUSd recorded three
`UploadFinished` in the same period, in three episodes (01/07, 17/07, 21/08),
each retried by TUSd. Three uploads attempted, three lost.

## Result, 2026-09-11

An upload to dataset `7a9b5d5e-fa6d-4c18-a42c-34f28fea6241`, after the deploy
and after logging was repaired:

| Hook type | Calls | Result |
|---|---|---|
| `pre-create` | 1 | 200 |
| `post-create` | 1 | 200 |
| `post-receive` | 1 | 200 |
| `post-finish` | 1 | **200** |

The file record exists, and its `storage_path` is
`datamap/2026/09/11/7a9b5d5e-.../1/9147151a...` rather than `staged/`, so the
Archivist collected it as well. Every step below passed.

## Before you read any log

Container logs do not survive a deploy — `docker compose down` deletes the
container together with its log file. From the deploy that carries
[#75](https://github.com/ardc-brazil/gatekeeper/pull/75) onward, the previous
container's log is archived first:

```bash
ssh datamap-prod 'ls -lh /home/datamap/logs | tail'
ssh datamap-prod 'zcat /home/datamap/logs/datamap_gatekeeper-<stamp>.log.gz | grep tus/hooks'
```

Kept for 30 days. So `docker logs` answers for the running container, and that
directory answers for everything before it.

## 1. The right code is running

```bash
ssh datamap-prod 'docker exec datamap_gatekeeper sed -n "28,42p" app/repository/dataset.py'
```

Expect `if restrict_by_tenancy:` guarding the tenancy filter. If the filter is
still unconditional, the deploy did not take.

```bash
ssh datamap-prod 'docker exec datamap_gatekeeper python3 -m alembic current'
```

Expect a revision marked `(head)`.

## 2. The upload works

The decisive check, and it needs a real upload through the interface — the hook
only fires at the end of a transfer.

Ask someone on the curation team to upload one small file to a dataset they own,
then:

```bash
ssh datamap-prod 'docker logs --since 1h datamap_gatekeeper 2>&1 | grep -oE "payload.type=[a-z-]+" | sort | uniq -c'
ssh datamap-prod 'docker logs --since 1h datamap_gatekeeper 2>&1 | grep "tus/hooks" | grep -oE "\" [0-9]{3} " | sort | uniq -c'
```

Expect `post-finish` to appear with **200**. Any 500 there means the upload is
still failing, and the body of the log line names the reason.

Confirm the file reached the database, not just the hook:

```bash
ssh datamap-prod 'docker exec datamap_gatekeeper_db psql -U gk_admin -d gatekeeper_db -c \
  "SELECT name, size_bytes, created_at FROM data_files ORDER BY created_at DESC LIMIT 5;"'
```

## 3. Granting access takes effect

Previously a person granted a tenancy kept seeing an empty screen until they
signed out and back in, and removing a tenancy answered 500.

- Grant a tenancy to a test user through the Swagger UI
- In the web app, that person uses **"I already have access — check again"** on
  the access-pending screen; the data should appear without signing out
- Remove the same tenancy: expect 200, not 500

## 4. Nothing else moved

```bash
ssh datamap-prod 'docker ps --format "table {{.Names}}\t{{.Status}}" | grep datamap_'
```

All five `datamap_*` containers up. MinIO in particular: it has crashed before,
and while it is down every upload fails for an entirely different reason than
the one this deploy fixes.

```bash
ssh datamap-prod 'docker logs --since 1h datamap_gatekeeper 2>&1 | grep -ciE "traceback|500 Internal"'
```

## If it has to be rolled back

The deploy is a container restart, so rolling back is deploying the previous
commit — re-run the workflow from the commit before the merge, or on the host:

```bash
cd ~/gatekeeper && git checkout <previous-sha> && \
  ENV_FILE_PATH=../environment/gatekeeper.prod.env make docker-deployment-no-prune
```

No migration in this release alters the schema, so a rollback needs no database
step. That will not hold for the embargo release (RFC 003), which adds tables.

## Outstanding, independent of the deploy

Three datasets failed their uploads and may have a published version missing its
files: `4b87824c-4ab6-469a-b52d-7b3d61fb7bcd`,
`8efa2399-8fc1-40ad-9f20-3b30d3f0e746`, `31d84f35-3b97-4d52-9e0c-ab4dd4d9c30e`.

```bash
ssh datamap-prod 'docker exec datamap_gatekeeper_db psql -U gk_admin -d gatekeeper_db -c \
  "SELECT d.id, d.name, v.name AS version, v.design_state, count(f.id) AS files
     FROM datasets d
     JOIN dataset_versions v ON v.dataset_id = d.id
     LEFT JOIN dataset_versions_data_files vf ON vf.dataset_version_id = v.id
     LEFT JOIN data_files f ON f.id = vf.data_file_id
    WHERE d.id IN (
      '\''4b87824c-4ab6-469a-b52d-7b3d61fb7bcd'\'',
      '\''8efa2399-8fc1-40ad-9f20-3b30d3f0e746'\'',
      '\''31d84f35-3b97-4d52-9e0c-ab4dd4d9c30e'\'')
    GROUP BY d.id, d.name, v.name, v.design_state
    ORDER BY d.id, v.name;"'
```

A published version with zero files is one of those lost uploads. The fix
restores the ability to upload; it does not recover what was lost, and the
researcher will have to send the files again.
