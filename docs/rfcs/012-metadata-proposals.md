# RFC 012: Metadata proposals reviewed like pull requests

| Status | Draft |
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
for the next version of the same dataset.

The decisions that shape everything else:

1. **A new service, Scribe, writes; the gatekeeper owns.** Scribe is the
   evolution of the `metadata-extractor` prototype: same place in the
   architecture (polls jobs in the shared Postgres, reads MinIO), new output
   (families, proposals with provenance and confidence) and a provider-neutral
   LLM interface. The gatekeeper owns the tables, the states and the review
   endpoints. The webapp owns the screens.
2. **The family is the unit of description.** Files are grouped by the exact
   signature `extension + sorted column names` computed over *every* file of
   the dataset, never over a sample. Two NetCDF families with different columns
   are two families. Nobody merges or splits families by hand; if the rule is
   wrong, the rule is fixed.
3. **Every field carries provenance and confidence, and the machine's text is
   never overwritten.** A field stores the generated value, the final value,
   who decided, when, and the provenance: `header`, `rule`, `kb`,
   `llm:<model>`, `exemplar`, `imported:<source>`, `selected-of-k`, `human`.
   The difference between the two texts is what the research measures.
4. **Nothing is synchronous.** Upload never waits for extraction, extraction
   never waits for generation, and a person can publish a dataset whose
   families were never read. Every step is a job with a visible state, per
   dataset and per family, and a per-user "processing" view.
5. **The depositor is asked only what the files cannot tell.** One optional
   free-text line at upload ("how was this data obtained?") and, after
   extraction, the instrument as the first visible gap in the proposal. The
   answer is written to the field as `human`, never passed through the model
   to "normalize" it; the model only receives it as context.
6. **The LLM is a configuration, not a dependency.** One interface
   (`complete(messages, schema)`), one adapter speaking the OpenAI-compatible
   API, and the provider chosen by `LLM_BASE_URL` + `LLM_MODEL` + key: a cloud
   router today, Ollama or vLLM on the DataMap host when a tenancy needs the
   data to stay in.
7. **A new version is born as a draft.** Columns unchanged from the previous
   version arrive marked `exemplar · from v<n-1>` and can be accepted in bulk;
   new columns are generated. Approved proposals and sibling datasets of the
   same instrument are the references the generator looks for first, then
   public repositories of the same instrument family (ARM), imported once and
   kept with `imported:<source>`.
8. **The draft is visible from the start.** The reviewer is the depositor and
   knows the data better than any sample the screen could show. Anchoring is a
   declared threat to validity of the research, not a UI constraint. What is
   logged per field is the verdict, the diff and the time to decide.

## Motivation

### Problem statement

Production has 462 datasets (204 enabled, 258,724 files, 2.3 TiB) and the
metadata schema in `datasets.data` is present everywhere and empty almost
everywhere: `variables` is filled in 0% of datasets, `source_instrument` in 14%,
`description` in 77%, `license` in 11%, `resolution` is the literal
`{"spatial": "", "temporal": ""}` in 100%. Search cannot find a dataset by what
it measures, the DOI record is minted from a near-empty document, and a
depositor who wants to do it right has 521 columns to describe by hand.

The pilot that precedes this RFC (`research/master/piloto`) measured, on ARM
curated datastreams and on real DataMap files, what a generator can and cannot
do:

- Variable names, units when the header carries them, coverage and a content
  description come from the file structure alone; a cheap open model proposes
  a `long_name` for 99.9% of variables, and a human would accept it with at
  most a light edit for about 90% of them (F32, F41).
- What the structure cannot tell is *origin*: instrument, method, site. The
  model abstains or guesses (an impact disdrometer became "optical"). One
  sentence from the depositor about origin raises the instrument field from
  38% to 63% filled (F43).
- A single sheet per dataset built from a sample of files describes a fraction
  of the archive without saying so: in a multi-instrument dataset the sample
  covered 2 of 9 instruments. Grouping by family describes all 9 (F45). In the
  archive, 35 of 133 readable datasets have more than one column signature and
  61 have files without a header line (F44).
- Without memory, a new version renames the same columns (5–33% identical);
  with the previous approved proposal as example, 74–89% are inherited (F42).
- Cost with the cheap model: about US$ 0.008 per family generation; the whole
  enabled archive is a few dollars.

### What exists today

- **Gatekeeper.** `datasets.data` JSONB with the ~30-key schema; `datasets`,
  `dataset_versions`, `data_files` and the N:N `dataset_versions_data_files`;
  `file_collocation_status` (pending | processing | completed) driven by the
  Archivist; internal routes under `/api/v1/internal/...` authenticated by
  `X-Api-Key` / `X-Api-Secret` (`app/controller/interceptor/authentication.py`);
  the email outbox (`app/service/email.py`, `EMAIL_ENABLED`, dispatched by the
  Archivist every 5 minutes); Casbin roles per resource (`datasets_read`,
  `datasets_write`, `datasets_admin`), dataset ownership and membership outside
  Casbin (`app/service/dataset_access.py`).
- **Archivist.** APScheduler with one `file_collocation` job every 15 minutes
  (`archivist/app/jobs/file_collocation_job.py`), discovery through
  `GET /internal/datasets/collocation/pending`, `GatekeeperClient` with httpx,
  `FailureReporter`, `Heartbeat`, `make manual-trigger DATASET_ID=...`.
- **metadata-extractor** (prototype, branch `datamap-vis`, service directory
  `metadata-extractor/`). Polls `extraction_jobs` every 30 s, reads XLSX and
  NetCDF through handlers, writes `file_metadata` (row count, sample path,
  extractor version, llm provider) and `column_metadata` (name, dtype,
  position, min/max/mean/std, null count, sample values, description), and
  generates column descriptions with Gemini (`app/llm/gemini.py`, a
  `LLMProvider` protocol with `complete(prompt) -> str`). Its tables are
  duplicated in the gatekeeper on that branch
  (`migrations/versions/2026_02_26_2210-a4458e0c5350_add_metadata_extraction_tables.py`)
  and are not on `main`.
- **Pilot library** (`research/master/piloto`, Python). Readers for NetCDF,
  delimited text (TOA5, Thies, csv with preamble, gz/bz2) and xlsx; sentinel
  detection; family grouping by signature; a writer that produces a family
  record in two steps (prose, then JSON per chunk of 40 variables) with CF /
  GCMD / FLUXNET candidates, unit validation, style exemplars and documentation
  retrieval; provenance and confidence per field; a Pydantic profile
  (`DatasetRecord`, `FamilyRecord`, `VariableRecord`). 108 tests.
- **Design.** `research/master/design/Revisao de Metadados v2.dc.html`:
  screens for upload (5a), post-extraction (5b, 3a), dataset review (2a),
  family review (2b), field history (3b), tenancy instruments (3c), families
  without a proposal (4a–4c).

### Goals

- Every enabled dataset gets a proposal for its dataset-level fields and for
  every readable family, at a cost of cents, without anyone asking.
- A depositor reviews 521 columns in minutes: filters, bulk accept of
  high-confidence fields, three suggestions only where generations disagree.
- Provenance per field survives into `datasets.data`, the snapshot and the
  DOI record, so a consumer can tell what a machine wrote and what a person
  confirmed.
- Approved proposals feed the next ones: previous version, sibling datasets,
  tenancy instruments with manuals.
- Everything a field went through is a queryable event log, because the
  dissertation's effort hypothesis (H5) is measured from it.

### Non-goals

- Replacing the depositor. The machine never publishes.
- Describing images, documents, packages or proprietary binaries variable by
  variable. They are listed as families with a role and a free description.
- A judge model in production. Confidence comes from the generator and from
  rules; the research judge stays in the pilot.
- Training or fine-tuning models.

## Technical design

### Services and responsibilities

```
webapp ──BFF──> gatekeeper ──(shared Postgres, MinIO)──> Scribe
                   ▲   ▲                                   │
                   │   └──── internal API ◄── Archivist ◄──┘ (jobs)
                   └──── email outbox (dispatch by Archivist)
```

| Service | Owns | Does |
|---|---|---|
| Gatekeeper | all tables, states, permissions, review endpoints, `datasets.data` | creates jobs when files land, applies verdicts, builds the final document, mints DOI from it |
| Archivist | scheduling | after collocation of a dataset, enqueues one `extract` job per file (existing cycle, no new scheduler) |
| Scribe (evolves `metadata-extractor`) | reading files, signatures, generation | polls `processing_jobs`; `extract`: header + sample + stats per file → `file_metadata`, `column_metadata`, signature; `generate`: one proposal per family, then the dataset synthesis; writes `metadata_proposals` and `proposal_fields` |
| Webapp | screens | review, families, instruments, processing view |

Scribe does not call the gatekeeper's HTTP API: like the prototype, it reads
and writes the shared database and MinIO through the gatekeeper-owned schema,
under its own DB role restricted to the metadata tables. The gatekeeper keeps
the only write path to `datasets.data`.

### Data model

New tables (Alembic migration in the gatekeeper; Scribe imports the same
SQLAlchemy models from a small shared package or mirrors them, as the prototype
does today — see Open questions).

**`file_metadata`** (from the prototype, extended): `id`, `data_file_id` (FK,
unique), `format` (netcdf | delimited | xlsx | binary | text | package),
`signature` (sha1 of sorted column names, 10 chars), `row_count`,
`global_attrs` JSONB, `time_start`, `time_end`, `lat`, `lon`, `alt`,
`sample_path` (MinIO, first rows / bytes), `extractor_version`,
`extracted_at`, `error`.

**`column_metadata`** (from the prototype, extended): `id`, `file_metadata_id`
(FK), `position`, `name`, `dtype`, `dims` JSONB, `role` (coordinate | data | qc
| auxiliary), `header_attrs` JSONB (units, long_name, _FillValue…), `count`,
`null_count`, `min`, `max`, `mean`, `min_clean`, `max_clean`, `mean_clean`,
`suspected_fill` JSONB, `sample_values` JSONB.

**`file_families`**: `id`, `dataset_version_id` (FK), `signature`,
`format`, `extension`, `file_count`, `total_bytes`, `time_start`, `time_end`,
`state` (reading | ready | no_proposal_format | no_proposal_no_header),
`role` (raw | processed | documentation | image | package | null, `human`),
`raw_of_family_id` (FK, nullable), `description` (human, nullable).
Unique (`dataset_version_id`, `signature`).

**`metadata_proposals`**: `id`, `dataset_version_id` (FK), `family_id` (FK,
nullable: null = dataset level), `state` (draft | in_review | approved |
returned | published), `model`, `prompt_version`, `scribe_version`,
`references` JSONB (what was used: previous version, siblings, imported),
`depositor_note` (text, nullable), `cost_usd`, `tokens_in`, `tokens_out`,
`generated_at`, `reviewed_by`, `reviewed_at`, `returned_note`.

**`proposal_fields`**: `id`, `proposal_id` (FK), `item` (variable name or null
for dataset-level), `field` (long_name | units | standard_name | name |
description | keywords | instrument | measurement_technique |
temporal_coverage | spatial_coverage | …), `generated_value` JSONB,
`suggestions` JSONB (up to 3, when generations disagreed), `candidates` JSONB
(standard names, units), `final_value` JSONB, `provenance` (enum above),
`confidence` numeric, `state` (draft | accepted | corrected | rejected),
`decided_by`, `decided_at`, `seconds_to_decide`, `comment`.
Unique (`proposal_id`, `item`, `field`).

**`field_events`** (append-only): `id`, `proposal_field_id` (FK), `type`
(generated | inherited | suggested | accepted | corrected | rejected |
restored | regenerated), `value` JSONB, `provenance`, `actor_id` (nullable),
`at`, `note`. The history drawer (3b) and H5 read only this table.

**`instruments`**: `id`, `tenancy`, `name`, `manufacturer`, `model`,
`serial`, `kind` (text), `created_by`, `created_at`.
**`instrument_documents`**: `id`, `instrument_id`, `data_file_id` or
`storage_path`, `kind` (manual | spec | other), `uploaded_by`, `uploaded_at`.
**`instrument_references`**: `id`, `instrument_id`, `source`
(`imported:arm` | `exemplar`), `payload` JSONB (variable names, standard
names, units), `imported_at`.
`datasets.data.instrument_id` links a dataset (or a family) to an instrument;
the free-text origin stays in `proposal_fields` as `human`.

**`processing_jobs`**: `id`, `kind` (extract | signature | generate |
regenerate | import_reference), `dataset_version_id`, `family_id` (nullable),
`data_file_id` (nullable), `state` (pending | running | done | failed |
cancelled), `attempts`, `progress` (0–100), `message`, `requested_by`
(nullable), `created_at`, `started_at`, `finished_at`, `error`. Replaces the
prototype's `extraction_jobs`.

### States and transitions

Proposal (dataset and family alike):

```
draft ──generation done──> in_review ──Finish review──> approved ──publish──> published
  ▲                            │  ▲                       │
  │                            │  └──── Return (curator) ─┘
  └──── new version / regenerate (only families not approved)
```

Field: `draft → accepted | corrected | rejected`; `rejected → draft` on
regenerate; a field a person wrote from scratch is `corrected` with no
generated value. Only `accepted` and `corrected` fields are written to
`datasets.data` on publish; the rest are omitted, never published as drafts.

Family: `reading → ready | no_proposal_format | no_proposal_no_header`. A
family without a proposal still publishes, as "listed, not described", with
whatever the person typed.

### Flow

1. Upload (TUS) → `data_files` rows → Archivist collocates files (existing).
2. On collocation `completed`, the gatekeeper enqueues one `extract` job per
   file and one `signature` job per dataset version.
3. Scribe `extract`: reads header, dims, attributes, a stratified sample of
   rows and per-column statistics with sentinel detection; writes
   `file_metadata` / `column_metadata`; stores the sample for the data card.
   Files it cannot parse get `format = binary` and the first bytes.
4. Scribe `signature` (after all extracts of the version are done or failed):
   groups files into `file_families`, sets `file_count`, period and state;
   enqueues one `generate` job per readable family plus one for the dataset
   level, in that order.
5. Scribe `generate` (family): looks for references in this order — approved
   proposal of the previous version of this dataset; approved proposals of
   other datasets with the same `instrument_id` in the tenancy;
   `instrument_references`; (later) ARM import by instrument family — then
   builds the context (structure, header units, statistics, 10 sample values,
   vocabulary candidates, style exemplars, documentation excerpts from the
   instrument manual, the depositor note) and calls the LLM twice per chunk of
   40 variables (prose, then JSON), three generations only for text fields
   (`long_name`, description) when `LLM_SUGGESTIONS=3`; applies rules
   (header units win, qc fields derived, invented standard names dropped);
   writes `proposal_fields` with provenance and confidence and one `generated`
   event per field. Columns matching an approved previous-version proposal are
   written as `inherited` with provenance `exemplar` and confidence 1.
6. Scribe `generate` (dataset): synthesis over the family records and the
   depositor note; writes dataset-level fields.
7. The proposal turns `in_review`; the person is notified (email outbox, dedup
   key `proposal-ready:<proposal_id>`), the dataset page shows the pill.
8. Review: per-field verdicts and bulk accept through the gatekeeper; every
   verdict is a `field_event`. Setting the instrument or attaching a manual
   enqueues `regenerate` for families not yet approved.
9. Finish review → `approved`; a curator (tenancy admin) may `Return` with a
   note. Publish writes the final document into `datasets.data` (with a
   `provenance` sub-document per key), refreshes `search_vector`, and the DOI
   is minted from that document.
10. New version: the gatekeeper copies nothing; Scribe generates the new
    version's families with the previous approved proposal as the first
    reference, so unchanged columns come back `exemplar · from v<n-1>`.

### Endpoints (gatekeeper)

Internal (client credentials, Archivist and Scribe):

- `POST /internal/metadata/jobs/claim?kind=&limit=` — claim pending jobs
  (`SELECT … FOR UPDATE SKIP LOCKED`), returns them `running`.
- `PUT /internal/metadata/jobs/{id}` — progress, done, failed.
- The Archivist's existing collocation flow gains one call:
  `POST /internal/datasets/{id}/versions/{vid}/metadata/enqueue` after
  `completed`.

User-facing (BFF → gatekeeper, `X-User-Token`, dataset access rules):

- `GET /datasets/{id}/versions/{vid}/families` — list with state, counts,
  pending fields.
- `GET /datasets/{id}/versions/{vid}/proposals/{pid}/fields?item=&state=&min_conf=&page=`
  — paginated; server-side filters (pending, low confidence).
- `POST …/fields/{fid}/verdict` — `{state, final_value, comment}`;
  `POST …/fields/bulk-accept` — `{min_confidence}` or `{field_ids}`.
- `GET …/fields/{fid}/history` — events across versions (joins by item and
  field through `dataset_versions`).
- `POST …/proposals/{pid}/finish`, `POST …/proposals/{pid}/return` (admin),
  `POST …/proposals/{pid}/regenerate`.
- `PUT …/families/{fid}` — role, description, `raw_of_family_id`, declared
  variables (creates `proposal_fields` with provenance `human`).
- `GET /datasets/{id}/versions/{vid}/files/{file_id}/sample` — the data card
  and "View sample".
- `GET|POST /tenancies/{t}/instruments`, `POST …/instruments/{iid}/documents`,
  `PUT /datasets/{id}/instrument`.
- `GET /me/processing` — jobs of the user's datasets, grouped by dataset and
  family.

### LLM interface and configuration

Scribe keeps a single `LLMProvider` protocol, extended from the prototype's:
`complete(messages, schema: type | None, max_tokens) -> Completion` with
`tokens_in`, `tokens_out`, `cost_usd` (from a price table in configuration),
`latency`. One implementation, `OpenAICompatible`, covers OpenRouter, OpenAI,
Ollama (`/v1`) and vLLM. Gemini stays as a second adapter only if a tenancy
asks for it; it is not the default.

```
LLM_BASE_URL=https://openrouter.ai/api/v1      # or http://ollama:11434/v1
LLM_MODEL=deepseek/deepseek-v4.1-flash-1017
LLM_API_KEY=…
LLM_PRICE_IN_PER_M=0.15   LLM_PRICE_OUT_PER_M=0.60
LLM_SUGGESTIONS=3          # generations for text fields; 1 disables suggestions
LLM_MAX_PARALLEL=4
SCRIBE_SAMPLE_ROWS=200000  SCRIBE_SAMPLE_VALUES=10  SCRIBE_CHUNK=40
```

Prompts are versioned files shipped with Scribe (`prompts/<name>_v<k>.md`);
`metadata_proposals.prompt_version` records which one wrote each proposal. No
temperature is sent; repetitions measure noise, as in the pilot.

### Reuse of the pilot

The pilot's `extract`, `extract_tabular`, `knowledge` (CF, GCMD, FLUXNET,
units), `writer` and `profile` modules become Scribe's core, published as a
package (`datamap-scribe-core` or vendored under `scribe/core/`), with the
harness, judge, tables and labels left behind in the research repository.
What changes on the way in: opaque family ids in prompts (never the dataset
name), the exemplar pool that includes the same instrument class (the pilot
excluded it for the experiment), and persistence to the tables above instead
of JSON files.

### Permissions

Review verdicts: dataset owner, members when `members_can_edit`, and tenancy
admins (`datasets_write` on the dataset, same rule as editing metadata today).
`Return`: tenancy admins only (`datasets_admin`); this is the "curator" and
needs no new role. Instruments: any member of the tenancy can read; create and
attach manual require `datasets_write` in the tenancy. Internal job endpoints:
a dedicated client for Scribe with the scoped policies of RFC 011 once merged,
the generic internal client until then.

### Notifications and the processing view

Two emails through the existing outbox: "your proposal is ready to review"
(dedup `proposal-ready:<id>`) and "a curator returned your proposal" (dedup
`proposal-returned:<id>:<n>`). `EMAIL_ENABLED` stays as it is. The processing
view reads `processing_jobs` for the user's datasets; the dataset page pill
reads the proposal state and the family states.

### Publishing

On `published`, the gatekeeper builds `datasets.data` from the approved fields:
dataset-level keys as today, plus `variables` (one entry per family and
variable with `long_name`, `units`, `standard_name`) and a `provenance`
sub-document (`{key: {source, decided_by, decided_at}}`). The search vector and
the DOI payload are built from this document only. The machine text stays in
`proposal_fields` and is never part of the public record.

### Configuration

Gatekeeper: nothing beyond the migration and a feature flag
`METADATA_PROPOSALS_ENABLED` to hide the tab while Scribe is not deployed.
Archivist: `METADATA_ENQUEUE_ENABLED`. Scribe: the block above plus Postgres
and MinIO credentials, `SCRIBE_POLL_SECONDS=15`, `SCRIBE_BATCH=5`.

### Observability

Scribe logs `job_id`, `kind`, `dataset_id`, `family_id`, `model`, `tokens_in`,
`tokens_out`, `cost_usd`, `latency_s` as fields; metrics: jobs by kind and
state, cost per day, median seconds from upload to `in_review`, proposals by
state. The gatekeeper exposes cost per dataset in the proposal card.

## Testing

- Scribe unit tests: readers on the pilot's fixtures (TOA5, Thies, csv with
  preamble, xlsx, NetCDF with int fill), signature grouping, sentinel
  detection, writer with a mock provider (chunking, retry on missing
  variables, suggestions only when generations disagree).
- Gatekeeper integration tests (the only ones that catch SQL and route bugs):
  enqueue on collocation, claim with `SKIP LOCKED` under two workers, verdict
  transitions, bulk accept, publish builds `datasets.data` with provenance,
  `Return` requires admin, a family without proposal publishes as listed.
- Webapp component tests for the field anatomy and the family table filters.
- A replay test: Scribe against the 15 datasets of the pilot's descriptive
  round reproduces the pilot's coverage table within noise.

## Rollout

- **Increment A — read and propose one family.** Migration; `processing_jobs`;
  Scribe `extract`/`signature`/`generate` with the OpenAI-compatible adapter;
  Archivist enqueue; family list and family review (2b) with verdicts and bulk
  accept; publish writes `datasets.data`. Feature-flagged; run against the 15
  pilot datasets in staging.
- **Increment B — dataset level and history.** Dataset synthesis, dataset
  review (2a), `field_events` drawer (3b), emails, processing view, new
  version as draft with inheritance.
- **Increment C — origin and instruments.** Upload line (5a), post-extraction
  question (5b), instruments page (3c), manuals as documentation excerpts,
  regenerate after manual; families without proposal (4a–4c).
- **Increment D — references.** Sibling datasets as exemplars, ARM import by
  instrument family, three suggestions with `selected-of-k`.
- **Backfill.** After A, one `generate` per family of every enabled dataset,
  rate-limited, a few dollars in total; proposals land `in_review` and owners
  are notified in batches.

Each increment ships behind the flag and is validated with the integration
suite before the flag is turned on in production.

## Alternatives considered

- **Generate inside the gatekeeper as a background job.** Fewer moving parts,
  but LLM clients, file readers (xarray, pandas, openpyxl) and long-running
  work would enter the API process; the platform already separates heavy work
  into services (Archivist, Zipper), and the prototype exists.
- **Keep `metadata-extractor` as is and add a proposals layer.** Its unit is
  the file, not the family; it writes descriptions directly without review;
  its only provider is Gemini. Evolving it is cheaper than keeping two.
- **Families by normalized names.** Would merge the three pluviometer families
  that differ only by the timezone in the date header, hiding a real change.
  Exact signature keeps the fact; inheritance by exemplar makes twin families
  cheap.
- **Let reviewers merge or split families.** Asks the person to fix the
  algorithm through the UI; rejected.
- **Show data before the draft (anchoring).** Rejected: the reviewer is the
  depositor. Anchoring is a declared limitation of the research.
- **A separate "curator" role.** Tenancy admin already is that person.
- **Scribe calls the gatekeeper HTTP API instead of the database.** Cleaner
  boundary, but every extract would push MBs of column metadata through the
  API; the prototype's shared-schema approach with a restricted DB role is kept
  for the tables Scribe owns the content of.

## Out of scope

- Variable-level free-text descriptions (CF has none; `long_name` is the
  description). A human `comment` per field exists.
- Reading proprietary binary formats (Thies LBN/GBF, Vaisala, radar vendors).
- Fixed-width text without delimiters (the Joss disdrometer exports): listed as
  `no_proposal_format` until a reader exists.
- Embedding search, data quality timelines (ARM-style DQR) and plots: the
  per-file sample and statistics stored here are the input for that later.
- Judge model, labelling tools, agreement metrics: research only.

## Open questions

1. **Shared models.** Scribe and the gatekeeper need the same SQLAlchemy
   models for the metadata tables. A small package `datamap-schema` imported by
   both, or the prototype's duplication with a migration test that compares
   them?
2. **Where the pilot code lives.** Vendored into `scribe/core/` (one repo, one
   deploy) or published from the research repo as a package (one source of
   truth for the dissertation)?
3. **Sample storage.** Per-file samples in MinIO under a `scribe/` prefix of the
   dataset bucket, or inline JSONB capped at 64 KiB? MinIO keeps the row small
   and serves the data card directly.
4. **Backfill policy.** Generate for every enabled dataset at once, or only when
   an owner opens the tab? The first costs a few dollars and surfaces 462
   notifications; the second never reaches dormant datasets.
5. **Embargoed datasets and cloud LLMs.** Default to the local provider when
   `embargo_until` is set, or let the tenancy choose?
6. **Service name.** Scribe is proposed; Cataloguer and Annotator were the
   alternatives.
