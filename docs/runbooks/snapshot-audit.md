# Auditing public DOIs against their snapshots

A DOI in state `FINDABLE` is citable: it is registered at DataCite and resolves
to the dataset's public page. That page is served from a JSON snapshot in object
storage. If the snapshot is missing, the citation resolves to a 404 and only a
reader complains.

Run this after any release that touches the DOI or snapshot flow, and whenever
someone reports a public dataset that does not open.

## The check

```bash
ssh datamap-prod 'docker exec datamap_gatekeeper_db psql -U gk_admin -d gatekeeper_db -At -F"|" -c \
  "SELECT d.state, d.mode, v.dataset_id, v.name, d.identifier
     FROM dois d JOIN dataset_versions v ON v.id = d.version_id
    WHERE d.state = '\''FINDABLE'\'';"' > /tmp/findable.txt

ssh datamap-prod 'ls /home/datamap/storage/datamap/infrastructure/minio/datamap/snapshots/' > /tmp/snapshots.txt
```

```bash
python3 - <<'PY'
snaps = set(open("/tmp/snapshots.txt").read().split())
missing = []
for line in open("/tmp/findable.txt"):
    if not line.strip():
        continue
    state, mode, dataset_id, version, identifier = line.strip().split("|")
    for name in (f"{dataset_id}-{version}.json", f"{dataset_id}-latest.json"):
        if name not in snaps:
            missing.append((identifier, name))
print(f"{len(missing)} snapshot(s) missing")
for identifier, name in missing:
    print(" ", identifier, "->", name)
PY
```

Expect zero. The `-latest.json` is the one the public page reads; the
`{dataset_id}-{version}.json` is the per-version page.

## When something is missing

First check whether the dataset is still enabled:

```sql
SELECT id, is_enabled, tenancy FROM datasets WHERE id = '<dataset_id>';
```

A disabled dataset with a `FINDABLE` DOI has no snapshot **by design** — the
backfill skips it. That is not a broken publication; it is a DOI that outlived
the dataset it points to, and the decision is whether to re-enable the dataset or
ask DataCite to move the DOI out of `FINDABLE`.

Three datasets were in that state as of 2026-09-11, all in the `data-amazon`
tenancy, and were deliberately left alone:

```
795b7da4-1ac3-4a09-8fcf-a1e316917223  v5  10.60748/nyxw-0j55
ac6d7821-7f24-4106-9040-33e60cb8ff56  v2  10.60748/8jkp-tq54
f554f14a-1505-4963-9e81-0d2b6be1994d  v1  10.60748/1e49-x094
```

If the dataset **is** enabled, the snapshot genuinely failed to publish, and
until this release the API would have answered 200 anyway. Re-publishing is not
a supported operation today: `change_doi_state` refuses `FINDABLE → FINDABLE`.
The recovery used in January 2026 was a one-off script that wrote all 270
snapshot files directly. If it happens again, that is the signal to build a
republish endpoint rather than repeat the script.

## Why this is worth running

The snapshot files carry a single write date, 2026-01-15, while the DOIs they
describe span October 2024 to March 2025. That gap is a manual repair nobody
recorded. The failure that made it necessary was silent: both call sites logged
the error and returned success, so a researcher received a public DOI pointing
at nothing and the system reported that everything went fine.
