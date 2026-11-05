# RFC 012: Metadata proposals reviewed like pull requests

| Status | Draft (architecture agreed 2026-11-01; implementation after the qualification exam) |
|--------|-------|
| Author | DataMap Team |
| Created | 2026-11-01 |
| Updated | 2026-11-01 |

## Summary

When files arrive, DataMap reads them, groups them into *file families* (same
format, same columns), and writes a **metadata proposal** for the dataset and
for every family, variable by variable. The depositor reviews it as a reviewer
reviews a pull request: accept, correct or reject each field. Nothing generated
reaches search, the public snapshot or the DOI without a person. What a person
approves becomes an example for the next proposal of the same instrument and
for the next version of the same dataset. The same document that the generator
writes is the one a depositor can bring already curated, the one the review
approves, and the one DataMap exports.

The decisions that shape everything else (research decisions D19–D27 in
`research/master/decisoes.md`):

1. **A new service, Scribe, writes; the gatekeeper owns.** Scribe reads files,
   computes signatures, calls the LLM and writes proposals. The gatekeeper owns
   every table, every state, every permission and every review endpoint. The
   webapp owns the screens. The `metadata-extractor` prototype (JCDL 2026
   experiment) is not reused as a service; clean pieces of it may be.
2. **One database, one migration chain, one models package.** Scribe's tables
   live next to `datasets`, `dataset_versions` and `data_files`, in the same
   schema, because they join with them. Only the gatekeeper runs Alembic.
   A package `datamap-schema` holds the SQLAlchemy models and is imported by
   both services. Scribe polls jobs straight from the database; there are no
   new internal HTTP routes between services.
3. **The family is the unit of description.** Files are grouped by the exact
   signature `extension + sorted column names`, computed over *every* file of
   the dataset version, never over a sample. Two NetCDF families with
   different columns are two families; three CSV families that differ only by
   a timezone in a header are three families. Nobody merges or splits families
   by hand; if the rule is wrong, the rule is fixed.
4. **Approved metadata lives in typed tables, not in `datasets.data`.**
   `dataset_metadata`, `family_metadata` and `variable_metadata` are the
   record; `datasets.data` becomes a document generated from them for the code
   that still reads it, until it is retired. Search can then answer "datasets
   that measure `air_temperature`".
5. **Every field carries provenance and confidence, and the machine's text is
   never overwritten.** A field keeps the generated value, the final value,
   who decided, when, and the provenance: `header`, `rule`, `kb`,
   `llm:<model>`, `exemplar`, `imported:<source>`, `selected-of-k`, `human`.
   The difference between the two texts is what the research measures.
6. **Nothing is synchronous.** Upload never waits for extraction, extraction
   never waits for generation, and a dataset can be published while families
   are still being read. Every step is a job with a visible state, per dataset
   and per family, and a per-user "processing" view.
7. **The depositor is asked only what the files cannot tell.** One optional
   free-text line at upload ("how was this data obtained?") and, after
   extraction, the instrument as the first visible gap. The answer is written
   as `human`, never passed through the model; the model only gets it as
   context.
8. **The LLM is a configuration.** One interface, one adapter speaking the
   OpenAI-compatible API, provider chosen by `LLM_BASE_URL` + `LLM_MODEL` +
   key: a cloud router, or Ollama on the DataMap host. For embargoed datasets
   the default is the local provider; the person may choose a frontier model
   after an explicit, recorded consent that says what leaves the host.
9. **A new version is born as a draft.** Columns unchanged from the previous
   version arrive marked `exemplar · from v<n-1>` and are accepted in bulk;
   new columns are generated.
10. **The draft is visible from the start.** The reviewer is the depositor and
    knows the data better than any sample. Anchoring is a declared threat to
    validity of the research, not a UI constraint (D25).
11. **A curator is a role, not the tenancy admin.** `curator` is assigned per
    tenancy and may approve, return and edit proposals of any dataset in it.

## Motivation

### Problem statement

Production has 462 datasets (204 enabled, 258,724 files, 2.3 TiB) and the
metadata schema in `datasets.data` is present everywhere and empty almost
everywhere: `variables` is filled in 0% of datasets, `source_instrument` in 14%,
`description` in 77%, `license` in 11%, `resolution` is the literal
`{"spatial": "", "temporal": ""}` in 100%. Search cannot find a dataset by what
it measures, the DOI record is minted from a near-empty document, and a
depositor who wants to do it right has 521 columns to describe by hand.

The pilot that precedes this RFC (`research/master/piloto`) measured what a
generator can and cannot do, on ARM curated datastreams, on real DataMap files
and against the DataMap curation group's own documents:

- Variable names, units when the header carries them, coverage and a content
  description come from the file structure alone; a cheap open model proposes
  a `long_name` for 99.9% of variables, and a human accepts it with at most a
  light edit for about 90% of them on ARM (F32) and 94–96% on a DataMap
  disdrometer judged against the curation group's reference (F46).
- What the structure cannot tell is *origin* and *source conventions*: an
  impact disdrometer became "optical"; ERA5 abbreviations (`alnid`) were
  misread. One sentence from the depositor about origin raises the instrument
  field from 38% to 63% filled (F43); the source's parameter table would fix
  the abbreviations (F46).
- A single sheet per dataset built from a sample of files describes a fraction
  of the archive without saying so: in a multi-instrument dataset the sample
  covered 2 of 9 instruments; families cover all 9 (F45). In the archive, 35 of
  133 readable datasets have more than one column signature and 61 have files
  without a header line (F44).
- Without memory, a new version renames the same columns; with the previous
  approved proposal as example, 74–89% are inherited (F42).
- Cost with the cheap model: about US$ 0.008 per family generation.

### What exists today

- **Gatekeeper.** `datasets.data` JSONB with the ~30-key schema; `datasets`,
  `dataset_versions`, `data_files` and the N:N `dataset_versions_data_files`;
  `file_collocation_status` (pending | processing | completed) driven by the
  Archivist; the email outbox (`app/service/email.py`, `EMAIL_ENABLED`);
  Casbin roles per resource (`datasets_read`, `datasets_write`,
  `datasets_admin`), dataset ownership and membership outside Casbin
  (`app/service/dataset_access.py`).
- **Archivist.** APScheduler, `file_collocation` every 15 minutes, discovery
  through `GET /internal/datasets/collocation/pending`, `GatekeeperClient`,
  `FailureReporter`, `Heartbeat`, `make manual-trigger`.
- **metadata-extractor** (prototype, `datamap-vis` branch). Polls
  `extraction_jobs`, reads XLSX and NetCDF, writes `file_metadata` and
  `column_metadata`, describes columns with Gemini. Its tables are not on
  `main`. Not reused as a service.
- **Pilot library** (`research/master/piloto`). Readers for NetCDF, delimited
  text (TOA5, Thies, csv with preamble, gz/bz2) and xlsx; sentinel detection;
  family grouping by signature; a writer producing a family record in two steps
  (prose, then JSON per chunk of 40 variables) with CF / GCMD / FLUXNET
  candidates, unit validation, style exemplars, documentation retrieval, retry
  on incomplete chunks; provenance and confidence per field; a Pydantic
  profile (`DatasetRecord`, `FamilyRecord`, `VariableRecord`); a converter
  from the curation group's ARM-style JSON. 110 tests.
- **Curation group documents** (`ardc-brazil/datamap-curadoria`). ARM
  DOD-style JSON for five Joss disdrometer campaigns and for METEORS (80
  variables with `long_name`, `units`, `standard_name`; 25 global attributes
  that are the `datasets.data` keys). The NetCDF files in production were
  written from them.
- **Design.** `research/master/design/Revisao de Metadados v2.dc.html`:
  upload (5a), post-extraction (5b, 3a), dataset review (2a), family review
  (2b), field history (3b), tenancy instruments (3c), families without a
  proposal (4a–4c).

### Goals

- Every enabled dataset gets a proposal for its dataset-level fields and for
  every readable family, at a cost of cents.
- A depositor reviews 521 columns in minutes: filters, bulk accept of
  high-confidence fields, three suggestions only where generations disagree.
- Approved metadata is typed, indexed and provenance-aware; search, snapshot
  and DOI are built from it.
- A depositor who already has curated metadata brings it in one file and it
  goes through the same review.
- Approved proposals feed the next ones: previous version, sibling datasets,
  tenancy instruments with manuals.
- Everything a field went through is a queryable event log (H5).

### Non-goals

- Replacing the depositor. The machine never publishes.
- Describing images, documents, packages or proprietary binaries variable by
  variable. They are listed as families with a role and a free description.
- A judge model in production. Confidence comes from the generator and rules.
- Training or fine-tuning models.

## Technical design

### Services and responsibilities

```
webapp ──BFF──> gatekeeper ──┐
                   ▲         │ shared Postgres (one schema) + MinIO
                   │         ▼
             Archivist     Scribe (polls processing_jobs; reads files; calls LLM)
             (collocation, email dispatch; enqueue is done by the gatekeeper)
```

| Service | Owns | Does |
|---|---|---|
| Gatekeeper | all tables, states, permissions, review and import endpoints, publishing | enqueues `extract` + `signature` jobs when collocation completes; applies verdicts; publishes approved fields into the typed tables; regenerates `datasets.data` for legacy readers; mints DOI |
| Scribe | nothing (reads and writes gatekeeper-owned tables under a restricted DB role) | `extract` per file; `signature` per version; `generate` / `regenerate` per family and for the dataset level; `import` for curated documents |
| Archivist | scheduling | unchanged; its collocation completion is the trigger |
| Webapp | screens | review, families, history, instruments, processing view, upload field |

Scribe's database user may write only to the metadata, family, proposal, event
and job tables, and read the rest. Its MinIO credentials are read-only on the
dataset bucket plus write on the `scribe/` sample prefix.

### Metadata model

This is the standard the dissertation describes; every table below is also a
section of the exported document. Types are Postgres; vocabularies are named
where a field has one.

**Dataset level — `dataset_metadata`** (one row per `dataset_version_id`;
profile: Science-on-Schema.org `Dataset` with a DataCite 4 crosswalk)

| column | type | vocabulary / rule |
|---|---|---|
| `title` | text | |
| `description` | text | |
| `keywords` | text[] | free, GCMD science keywords preferred |
| `instrument_id` | uuid FK `instruments` | nullable |
| `origin_note` | text | the depositor's free sentence; always `human` |
| `measurement_technique` | text | |
| `processing_level` | enum | `raw` (NASA L0, ARM 00/a0) · `calibrated_qc` (L1, a1/b1) · `aggregated` (L3) · `derived` (L2/L4, c1); property of the family, dataset carries the maximum; optional |
| `time_start`, `time_end` | timestamptz | computed from files, confirmable |
| `geo_lat`, `geo_lon`, `geo_alt`, `geo_bbox` | numeric / geometry | point or box, computed, confirmable |
| `spatial_resolution`, `temporal_resolution` | text | |
| `institution`, `project`, `funder` | text | |
| `license` | text | SPDX id |
| `references` | jsonb | list of {citation, doi, url} |
| `extra` | jsonb | attributes with no slot above (e.g. ARM `data_stream`, `facility_id`), shown, not indexed |
| `provenance` | jsonb | `{column: {source, decided_by, decided_at}}` |

Authors, contributors and the DOI stay where they are today (`dataset_versions`,
`dois`, authors in the dataset record) and are referenced, not duplicated.

**Family level — `file_families` + `family_metadata`**

| column | type | rule |
|---|---|---|
| `signature` | char(10) | sha1 of sorted column names |
| `format`, `extension` | text | netcdf · delimited · xlsx · binary · text · package |
| `file_count`, `total_bytes` | bigint | over the whole version |
| `time_start`, `time_end` | timestamptz | |
| `state` | enum | reading · ready · no_proposal_format · no_proposal_no_header |
| `role` | enum | raw · processed · documentation · image · package; `human` |
| `processing_level` | enum | as above |
| `raw_of_family_id` | uuid FK | optional link "raw version of" |
| `summary` | text | one paragraph |
| `instrument_id` | uuid FK | optional, overrides the dataset's |
| `sampling_interval` | interval | |
| `description` | text | human, for families without a proposal |

**Variable level — `variable_metadata`** (one row per published variable;
profile: CF for variables, ACDD for global attributes)

| column | type | rule |
|---|---|---|
| `family_id` | uuid FK | |
| `name` | text | as in the file |
| `dims` | text[] | |
| `dtype` | text | |
| `role` | enum | coordinate · data · qc · auxiliary |
| `long_name` | text | the description; CF has no separate one |
| `units` | text | UDUNITS-parsable when possible; header value wins |
| `standard_name` | text | **must exist in the CF standard name table**; otherwise null and the value goes to `comment` |
| `valid_min`, `valid_max`, `missing_value` | numeric | from header or declared |
| `ancillary_variables` | text[] | e.g. the `qc_` flag |
| `attributes` | jsonb | other header attributes (`cell_methods`, bins, calibration), shown, not indexed |
| `comment` | text | human |
| `provenance`, `confidence` | jsonb / numeric | per column |

Indexes: (`standard_name`), (`units`), trigram on `name` and `long_name`, so
the dataset list can filter by variable.

**File level — `file_metadata`, `column_metadata`** (per file, feed the data
card, "View sample" and the signature): format, signature, row count, global
attributes, coverage, sample path in MinIO (`scribe/<dataset>/<file>.json`,
first rows or first bytes), extractor version; per column: position, name,
dtype, dims, role, header attributes, count, nulls, min/max/mean raw and
clean, suspected sentinels, sample values.

**Review — `metadata_proposals`, `proposal_fields`, `field_events`**

- `metadata_proposals`: `dataset_version_id`, `family_id` (null = dataset
  level), `state` (draft · in_review · approved · returned · published),
  `model`, `prompt_version`, `scribe_version`, `references` jsonb, `consent`
  jsonb (provider, who, when, for embargoed datasets), `cost_usd`,
  `tokens_in`, `tokens_out`, `generated_at`, `reviewed_by`, `reviewed_at`,
  `returned_note`.
- `proposal_fields`: `proposal_id`, `item` (variable name or null), `field`,
  `generated_value` jsonb, `suggestions` jsonb (≤ 3), `candidates` jsonb,
  `final_value` jsonb, `provenance`, `confidence`, `state` (draft · accepted ·
  corrected · rejected), `decided_by`, `decided_at`, `seconds_to_decide`,
  `comment`. Unique (`proposal_id`, `item`, `field`).
- `field_events` (append-only): `proposal_field_id`, `type` (generated ·
  inherited · suggested · imported · accepted · corrected · rejected ·
  restored · regenerated), `value`, `provenance`, `actor_id`, `at`, `note`.

**Instruments — `instruments`, `instrument_documents`, `instrument_references`**
per tenancy: name, manufacturer, model, serial, kind; documents (manual, spec)
as files; references (`imported:arm`, `exemplar`) with the variable names,
units and standard names reused as context.

**Jobs — `processing_jobs`**: `kind` (extract · signature · generate ·
regenerate · import), `dataset_version_id`, `family_id`, `data_file_id`,
`state` (pending · running · done · failed · cancelled), `attempts`,
`progress`, `message`, `requested_by`, timestamps, `error`. Claimed with
`SELECT … FOR UPDATE SKIP LOCKED`.

**Legacy — `datasets.data`**: regenerated from the tables on every publish for
readers not yet migrated; no new field is ever added to it.

### The DataMap Metadata Document

One JSON document (YAML accepted, same schema), versioned by `schema_version`,
with three parts mirroring the tables: `dataset`, `families[]` (each with
`variables[]`), and optional `provenance` / `confidence` per field. It is:

- what Scribe writes (as a proposal),
- what the review approves and publish records,
- what `GET /datasets/{id}/versions/{vid}/metadata` exports (and what the
  published NetCDF files may receive as attributes on download, later),
- what a depositor uploads in the dedicated field of the deposit form, or
  attaches later, to bring curated metadata in. Import creates a proposal
  with provenance `imported:depositor`, families matched by signature or by
  variable names; `standard_name` values are validated against the CF table;
  the proposal goes through the same review (a curator may accept all at
  once).

The curation group's ARM-style JSON is accepted as-is through a converter
(`global attributes` → `dataset` and `extra`, `variables` → one family,
`"N/A"` / `-9999` → absent), the same converter the pilot already ships.

```json
{
  "schema_version": "1.0",
  "dataset": {
    "title": "Go Amazon: Disdrometer RD-80, Atto Campina",
    "description": "...",
    "keywords": ["disdrometer", "rain rate", "Amazon"],
    "instrument": {"name": "RD-80 Joss-Waldvogel disdrometer", "serial": "2102502"},
    "origin_note": "RD-80 at the ATTO Campina site, calibrated 2021-08-06",
    "processing_level": "calibrated_qc",
    "time_start": "2020-03-03T00:00:00Z", "time_end": "2024-09-17T23:59:00Z",
    "geo": {"lat": -2.1816, "lon": -59.0219, "alt": 59},
    "license": "CC-BY-4.0",
    "extra": {"data_level": "b1", "effective_measurement_area": "0.005 m2"}
  },
  "families": [{
    "signature": "5cc47247cc", "format": "netcdf", "extension": ".nc",
    "processing_level": "calibrated_qc",
    "variables": [{
      "name": "rain_rate", "dims": ["time"], "dtype": "float32", "role": "data",
      "long_name": "Rain intensity", "units": "mm/h", "standard_name": "rainfall_rate",
      "missing_value": -9999, "ancillary_variables": ["qc_rain_rate"],
      "provenance": "imported:depositor", "confidence": 1
    }]
  }]
}
```

### States and transitions

Proposal (dataset and family alike):

```
draft ──generation done──> in_review ──Finish review──> approved ──publish──> published
  ▲                            │  ▲                       │
  │                            │  └──── Return (curator) ─┘
  └──── new version / regenerate (only families and fields not approved)
```

Field: `draft → accepted | corrected | rejected`; `rejected → draft` on
regenerate; a field a person wrote from scratch is `corrected` with no
generated value. Only `accepted` and `corrected` fields are published.
Regeneration never overwrites an accepted or corrected field and always
writes an event.

Family: `reading → ready | no_proposal_format | no_proposal_no_header`. A
family without a proposal still publishes as "listed, not described".

### Flow

1. Upload (TUS) → `data_files` → Archivist collocates (existing). The deposit
   form has one optional line, `origin_note`, and one optional file, the
   metadata document.
2. When the Archivist sets collocation `completed`, the gatekeeper enqueues one
   `extract` per file and one `signature` per version; if a metadata document
   was uploaded, one `import`.
3. Scribe `extract`: header, dims, attributes, stratified row sample,
   per-column statistics with sentinel detection; `file_metadata`,
   `column_metadata`; sample to MinIO. Unparsable files: `format = binary`,
   first bytes.
4. Scribe `signature`: groups files into `file_families` over the whole
   version; enqueues `generate` per readable family, then for the dataset.
5. Scribe `generate` (family): references in order — approved previous
   version, approved siblings with the same `instrument_id`, instrument
   references — then structure, header units, statistics, 10 sample values,
   vocabulary candidates, style exemplars, documentation excerpts from the
   instrument manual, the `origin_note`; prose then JSON per chunk of 40
   variables, with one retry on incomplete chunks; three generations for text
   fields only when `LLM_SUGGESTIONS=3`; rules (header units win, `qc_` names
   derived, standard names outside the CF table dropped); opaque family ids
   in prompts (never the dataset name). Writes fields, events, cost.
6. Scribe `generate` (dataset): synthesis over family records and
   `origin_note`.
7. `in_review`; notification (outbox, dedup `proposal-ready:<id>`; emails off
   during the backfill); dataset page pill.
8. Review: verdicts and bulk accept; setting instrument or attaching a manual
   enqueues `regenerate` for families not approved.
9. Finish review → `approved`; a curator may `Return` with a note. Publish
   writes the typed tables, regenerates `datasets.data`, refreshes
   `search_vector`; the DOI record is built from the tables.
10. New version: Scribe generates with the previous approved proposal as the
    first reference; unchanged columns come back `exemplar · from v<n-1>`.

### Endpoints (gatekeeper, BFF → gatekeeper with `X-User-Token`)

- `GET /datasets/{id}/versions/{vid}/families`
- `GET …/proposals/{pid}/fields?item=&state=&min_conf=&page=` (server-side
  filters and pagination)
- `POST …/fields/{fid}/verdict` `{state, final_value, comment}`;
  `POST …/fields/bulk-accept` `{min_confidence}` or `{field_ids}`
- `GET …/fields/{fid}/history`
- `POST …/proposals/{pid}/finish` · `POST …/proposals/{pid}/return` (curator)
  · `POST …/proposals/{pid}/regenerate`
- `PUT …/families/{fid}` (role, description, `raw_of_family_id`, declared
  variables as `human` fields)
- `GET …/files/{file_id}/sample`
- `GET …/metadata` (export) · `POST …/metadata/import` (document upload)
- `PUT /datasets/{id}/instrument` · `PUT /datasets/{id}/llm-consent`
- `GET|POST /tenancies/{t}/instruments` · `POST …/instruments/{iid}/documents`
- `GET /me/processing`

No new internal service routes: the gatekeeper enqueues inside the existing
collocation-status handler; Scribe claims from the database.

### LLM interface and configuration

`LLMProvider.complete(messages, schema | None, max_tokens) -> Completion`
with tokens, cost (price table in configuration) and latency. One adapter,
`OpenAICompatible`, for OpenRouter, OpenAI, Ollama (`/v1`) and vLLM.

```
LLM_BASE_URL=https://openrouter.ai/api/v1       # or http://ollama:11434/v1
LLM_MODEL=deepseek/deepseek-v4.1-flash-1017
LLM_API_KEY=…
LLM_LOCAL_BASE_URL=http://ollama:11434/v1        # used for embargoed datasets by default
LLM_LOCAL_MODEL=…
LLM_PRICE_IN_PER_M=0.15  LLM_PRICE_OUT_PER_M=0.60
LLM_SUGGESTIONS=1          # 3 enables suggestions (increment D)
LLM_MAX_PARALLEL=4
SCRIBE_SAMPLE_ROWS=200000  SCRIBE_SAMPLE_VALUES=10  SCRIBE_CHUNK=40
SCRIBE_POLL_SECONDS=15     SCRIBE_BATCH=5
```

Embargoed datasets run on `LLM_LOCAL_*` unless the dataset carries a recorded
consent; the consent dialog states exactly what is sent: column names, header
attributes, statistics and ten values per variable, never the files. Prompts
are versioned files; `prompt_version` is recorded per proposal; no temperature
is sent.

### Reuse of the pilot

`extract`, `extract_tabular`, `knowledge` (CF, GCMD, FLUXNET, units),
`writer`, `profile` and the curation converter move into `scribe/core/`
(vendored; the research repository keeps the pilot, harness, judge, labels and
analysis scripts). Vocabulary tables ship with Scribe and are updated by
release.

### Permissions

- Verdicts, finish review: dataset owner, members when `members_can_edit`,
  tenancy `curator`.
- `Return`, approve any proposal in the tenancy: `curator` (new Casbin role,
  assigned in the members screen; the admin receives it by default only until
  that screen exists).
- Instruments: read for tenancy members; create and attach for `datasets_write`.
- Import: same as editing metadata.

### Notifications and the processing view

Outbox templates "proposal ready" and "proposal returned" (dedup keys above);
`EMAIL_ENABLED` unchanged; no email during the backfill. The processing view
reads `processing_jobs` for the user's datasets; the dataset pill reads the
proposal and family states.

### Publishing

On `published`, approved fields are written to the typed tables, `datasets.data`
is regenerated from them, `search_vector` is rebuilt (now including variable
names, long names and standard names), and the DOI payload is built from the
tables. Machine text stays in `proposal_fields` and never enters the public
record.

### Observability

Scribe logs `job_id`, `kind`, `dataset_id`, `family_id`, `model`, `tokens_in`,
`tokens_out`, `cost_usd`, `latency_s` as fields; metrics: jobs by kind and
state, cost per day, seconds from upload to `in_review`, proposals by state.
The proposal card shows the cost per dataset.

## Testing

- Scribe unit tests from the pilot's fixtures: readers, signatures, sentinels,
  writer with a mock provider (chunking, retry, suggestions), converter.
- Gatekeeper integration tests: enqueue on collocation, claim under two
  workers, verdict transitions, bulk accept, publish into the typed tables and
  the regenerated JSONB, `Return` requires `curator`, a family without a
  proposal publishes as listed, import creates a reviewable proposal and
  rejects non-CF standard names into `comment`.
- Webapp component tests for the field anatomy and family table filters.
- Replay: Scribe on the pilot's 15 datasets reproduces the pilot's coverage
  within noise.

## Rollout

Implementation starts after the qualification exam. Order:

- **A — read and propose one family.** Migration (all tables),
  `datamap-schema`, Scribe `extract` / `signature` / `generate` with the
  adapter, enqueue on collocation, family list and family review (2b) with
  verdicts and bulk accept, publish into the typed tables. Feature-flagged;
  staging on the pilot's 15 datasets.
- **B — dataset level, history, versions.** Dataset synthesis and review
  (2a), `field_events` drawer (3b), processing view, new version as draft
  with inheritance, `curator` role.
- **C — origin, instruments, import.** Upload line (5a), post-extraction
  question (5b), instruments page (3c), manuals as context, regenerate after
  manual, families without proposal (4a–4c), metadata document import and
  export, embargo consent.
- **D — references and suggestions.** Siblings as exemplars, ARM import by
  instrument family, three suggestions with `selected-of-k`, emails.
- **Backfill** only at the end, when the increments and the experiment are
  settled: one generation per family of every enabled dataset, no email.

## Alternatives considered

- Generate inside the gatekeeper as a job: LLM clients and file readers in
  the API process; rejected.
- Evolve `metadata-extractor` in place: its unit is the file, it writes
  descriptions without review, Gemini only; rejected, pieces may be reused.
- A separate database or schema for Scribe: joins with the dataset tables
  are everywhere and nothing is gained; rejected.
- Families by normalized names: hides a real header change; rejected.
- Reviewers merging or splitting families: asks the person to fix the
  algorithm; rejected.
- Data before the draft: the reviewer is the depositor; rejected (D25).
- Curator = tenancy admin: the admin is often not a curator; rejected.
- Keep `datasets.data` as the record: cannot filter by variable; rejected.
- Samples as JSONB: up to 16 GB in the database; MinIO instead.

## Out of scope

- Variable-level free-text descriptions (CF has none); a `comment` exists.
- Proprietary binary formats and fixed-width text without delimiters (listed
  as `no_proposal_format` until a reader exists).
- Embedding search, data quality timelines, plots: the stored samples and
  statistics are their input.
- Judge model, labelling tools, agreement metrics: research only.
- Availability, throughput and capacity planning: not the focus now.

## Decisions log

| date | decision |
|---|---|
| 2026-10-29 | Families as the unit; exemplar pool includes the same instrument class in production; multi-suggestions optional; manual as upload (D19) |
| 2026-10-30 | Depositor note as a context source; answer written as `human` (D22). Exact signature; no manual merge; sentinels in tabular files (D23). No post-hoc exclusion in analysis (D24) |
| 2026-11-01 | No data-before-draft (D25). Own service, LLM by configuration, async extraction with per-user progress, new version as draft (D26). One database, samples in MinIO, backfill at the end, `curator` role, typed tables, processing levels, import document, Scribe, Ollama (D27). Scribe polls the database; restricted credentials; suggestions off in A; `origin_note` as a dataset field; regenerate never overwrites approved fields |
| 2026-11-05 | Rule-check flags (`units_parseable`, `standard_name_in_table`, `units_compatible_with_standard_name`) shown per variable on the review screen, as a validation signal next to provenance and confidence (D32; addendum below) |

## Addendum (2026-11-05): rule-check flags on the review screen

**Context.** The pilot already computes three deterministic checks per
variable after generation (`piloto/src/piloto/writer.py`, `_flags`):
`units_parseable` (the unit string parses), `standard_name_in_table` (the
chosen standard name exists in the CF table) and
`units_compatible_with_standard_name` (the unit has the canonical dimension
of that standard name). They are stored on the variable record but the review
screen (design v2, October 2026) shows only provenance and confidence. The
systematic review found one study in which attaching an automatic validation
report to the generated proposal cut review time from 47 to 18 minutes for
twenty tables, without a controlled design (Pyatetsky, Suleykin and Sorokina,
2025, `pyatetsky2025bridging` in `research/master/literature-review/referencias-rsl.bib`).

**Decision (D32, 2026-11-05).** The Scribe persists the flags with each
variable field (`column_metadata.flags` jsonb, same keys as the pilot), and
the family review table shows them as one signal per variable, next to
provenance and confidence: green when every applicable check passes, amber
with the failing check named (for example "unit `degC` is not compatible with
`air_pressure`"). The signal is informational: it does not block accept, is
not a verdict, and is not a judge. The filter bar gains "has a failing check"
alongside "pending" and "low confidence". Bulk accept by `min_confidence`
skips variables with a failing check unless the user opts in.

**Not changed.** The rules themselves (header units win, `qc_` names derived,
standard names outside the CF table dropped) stay in `generate`. No new
endpoint: flags travel in the existing field payload. Increment A.

**To fold into the body later:** `column_metadata` table (add `flags`), the
family review screen description, and the field payload in Endpoints.
