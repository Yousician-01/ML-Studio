# Development

## Implemented workflow

The application supports Project creation and metadata editing, managed CSV
ingestion/replacement, source summaries and previews, semantic overrides, and
binary target selection. SQLite stores domain metadata; immutable source files
live in the managed workspace. Phase 1.5 adds a shared visual foundation,
contextual validation, and permanent Project deletion. Phase 2 implements
deterministic source exploration. Pipeline IR, preprocessing, training, Runs,
generated code, MLflow, and AI are not implemented.
The [v0.1 contracts](specifications/project-v0.1.md) remain authoritative.

Keep changes scoped, use mature libraries, preserve exact generated-source
execution and training-only preprocessing in later phases, and validate behavior
with meaningful tests. Follow [Contributing](../CONTRIBUTING.md). Vision explains
why; Roadmap stages work; Prototype summarizes scope; Architecture explains the
system; specifications govern contracts; ADRs preserve decisions; Issues track
work; PRs record review; CHANGELOG records user-visible changes; Git records edits.

## Verified local setup

The backend targets Python 3.12+. These commands were verified on Windows
PowerShell using Python 3.14.2 and Node 24.13.0. The frontend requires Node 22.13+
and npm; Node 24 is recommended. Other platforms were not exercised in Phase 0.
No Docker or separate database service is needed.

From the repository root:

```powershell
python -m venv backend/.venv
cd backend
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Run backend commands from `backend/`. Defaults work without an environment file.
The optional [backend example](../backend/.env.example) lists settings; a local
`.env` in the command's current directory is loaded, and environment variables
take precedence. Never commit a real environment file.

Initialize the database, then start the backend:

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic current
.venv/Scripts/python.exe -m uvicorn mlstudio.main:create_app --factory --host 127.0.0.1 --port 8000
```

Migration `0002_project_dataset` adds `projects` and `datasets` after the unchanged
`0001_foundation`. Both fresh installation and upgrade from Phase 0 are tested.
Startup does not run migrations or call `metadata.create_all()`; Alembic owns
schema evolution. Run `alembic upgrade head` when updating an existing workspace.

In another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

Expected response:
`{"status":"ok","service":"ml-studio-api","database":"ready"}`.
The endpoint checks SQLite with a trivial query. A query failure returns a
sanitized HTTP 503, not internal paths or stack traces. Health proves database
connectivity, not migration currency; use Alembic's current command for that.
OpenAPI uses the package's `0.0.0` development metadata, not a published release.

From `frontend/`:

```powershell
npm.cmd ci
npm.cmd run dev
```

Open `http://127.0.0.1:3000` to list or create Projects. Creation opens the Data
workspace. Upload a CSV, review columns, choose semantic overrides, and select
a target. Changes save immediately; reloading restores them from SQLite. Project
context/settings offers an explicit metadata save. API failures show retryable
errors. `npm.cmd` avoids PowerShell systems that block `npm.ps1`; no
execution-policy change is needed.

The [frontend example](../frontend/.env.example) documents public
`NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://127.0.0.1:8000/api/v1`.
It includes the API prefix and is embedded at build time. Restart development or
rebuild production after changes. The browser calls FastAPI directly; CORS must
allow the frontend origin.

## Central configuration and runtime workspace

| Setting | Default / behavior |
| --- | --- |
| `MLSTUDIO_APP_NAME` | `ML Studio` |
| `MLSTUDIO_ENVIRONMENT` | `development`; also accepts `production` and `test` |
| `MLSTUDIO_API_PREFIX` | `/api/v1`; update the frontend URL if changed |
| `MLSTUDIO_HOME` | ML Studio's platform user-data directory, via platformdirs |
| `MLSTUDIO_DATABASE_URL` | Optional absolute SQLite file URL; otherwise `mlstudio.db` under the workspace |
| `MLSTUDIO_MAX_CSV_UPLOAD_BYTES` | `52428800` (50 MiB), positive integer; source upload limit |
| `MLSTUDIO_CORS_ORIGINS` | JSON array of `http://localhost:3000` and `http://127.0.0.1:3000`; no credentials or wildcard defaults |

The default runtime workspace is outside the repository. Windows normally uses
local application data; other systems follow platformdirs conventions. Resolving
settings or importing the application creates no files. Lifespan or Alembic
initialization creates required directories. For disposable validation, this
override was verified before running migrations and starting the backend:

```powershell
$env:MLSTUDIO_HOME = Join-Path ([System.IO.Path]::GetTempPath()) ('mlstudio-phase1-' + [guid]::NewGuid().ToString())
```

Keep custom workspaces outside the repository. An explicit database URL takes
precedence over the default database and must name an absolute synchronous SQLite
file. Tests clear ambient ML Studio settings and use temporary directories rather
than the developer's real workspace or local `.env`.

Ignore rules protect environments, Python caches, Node modules, Next output,
SQLite files, logs, and local artifacts. Example environments and synthetic CSV
fixtures remain eligible for version control.

## CSV ingestion and interpretation

Accepted files use UTF-8 (optional BOM), comma separators, a header, and standard
CSV quoting. Headers must be nonblank, unique, and free of control characters.
There must be at least one data row; inconsistent row widths, invalid encoding,
invalid quoting, NULs, and non-finite numeric values are rejected. Blank physical
lines are ignored; empty fields remain missing observations. Python's CSV reader
validates structure before pandas parses the same bytes; differences in header
or row counts are rejected. The standard CSV field limit is 131072 characters.
The file extension is not used as proof of valid CSV.

Parsing uses pandas `read_csv` with `encoding="utf-8-sig"`, `low_memory=False`,
and its default missing tokens (including empty fields, `NA`, `N/A`, `NULL`, and
`NaN`). Quoting does not escape pandas missing-token interpretation. Numeric and
boolean parsing follows pandas; dates stay source strings. The parsing convention
`csv-utf8-v1` and installed pandas version are recorded with each Dataset.
Physical dtypes describe this parsed representation, not declarations in CSV.
Precision-risk integer columns are re-read as tokens and stored in pandas nullable
Int64/UInt64 arrays so missing cells cannot force rounding through float64.
Integers beyond NumPy's range use exact Python integers in an object column.
If a Dataset was ingested before this precision fix with large integer labels and
missing cells, re-upload its unchanged source to refresh cached schema/profile
metadata. The fix does not rewrite previously persisted observations or source bytes.

The source limit defaults to 50 MiB; the request stream is also capped at that
limit plus 1 MiB of multipart overhead before unbounded temporary spooling can
occur. Oversized uploads return HTTP 413. Ingestion is synchronous and reads the
bounded source into memory for pandas profiling. This is intended for local
tabular data, not arbitrarily large analytical workloads.

Managed storage:

```text
MLSTUDIO_HOME/
├── mlstudio.db
├── .ingestion/                 temporary writes, cleaned after handled failures
└── projects/<project_id>/datasets/<dataset_id>/source.csv
```

Generated UUIDs determine paths. Original filenames are descriptive metadata.
The exact source bytes receive one SHA-256 fingerprint (`sha256:<hex>`); they
are never rewritten. Finalization renames a completed temporary file before
committing Dataset metadata and the Project's active reference. Transactions
and Project revisions protect database updates; SQLite and the filesystem are
not a single atomic transaction. A process crash can leave an unreferenced file;
automatic garbage collection is deliberately absent. Never remove retained
Dataset artifacts merely because they are no longer active.

Dataset reads verify the fingerprint. Missing/corrupt sources return an explicit
error while preserving metadata. Responses include only the first 20 parsed
source rows. Preview rows and observed target labels are read from the artifact,
not stored in SQLite or written to ordinary application logs.

Inference rules run in this order:

1. No non-missing values: `unknown`.
2. Exactly two distinct non-missing values: `binary`.
3. Names equal to `id`, starting `id_`, or ending `_id`, with at least three
   distinct values and at least 95% uniqueness: `identifier` only for integer
   physical types or strings. Floating measurements do not qualify.
4. Other numeric columns: `continuous` with variation, otherwise `unknown`.
5. String values all matching an ISO date/datetime shape and successfully parsing
   as ISO dates: `datetime`. Numeric timestamps are not inferred as datetime.
6. Any string over 80 characters or containing at least eight whitespace-separated
   words: `text`.
7. Other strings: `categorical` at up to 20 distinct values or a uniqueness ratio
   of at most 20%; otherwise `text`.
8. Remaining types: `unknown`.

These are heuristics, not feature recommendations. Every column initially has
the `feature` role. Overrides retain the inferred type and can be reset.
Selecting a target requires exactly two distinct non-missing values across the
full source. Neither overrides nor previews bypass this check. Positive-class
selection belongs to Working Pipeline configuration in Prepare and is not silently chosen.

Project owns the target. Roles are derived rather than independently persisted
in Dataset columns. Working Pipeline IR owns feature inclusion; former targets
remain excluded until explicitly re-enabled in Prepare. Dataset replacement
resets the current target and starts with fresh schema inference and no overrides;
it retains old metadata/artifacts and leaves the old Pipeline binding stale.

## API and metadata

All routes below are under `/api/v1`; `/docs` exposes typed OpenAPI contracts.

| Method and path | Behavior |
| --- | --- |
| `POST /projects` | Create Project; HTTP 201 |
| `GET /projects` | List Projects by latest update |
| `GET /projects/{id}` | Retrieve Project; unknown IDs return 404 |
| `PATCH /projects/{id}` | Update name, description, problem statement, success context |
| `DELETE /projects/{id}?revision=N` | Permanently delete the Project and its managed sources; HTTP 204; stale revision returns 409 |
| `POST /projects/{id}/dataset` | Multipart `file`; replacement requires `expected_dataset_id` matching the active Dataset; HTTP 201 |
| `GET /projects/{id}/dataset` | Summary, column interpretation, target classes, limited source preview |
| `PATCH /projects/{id}/dataset` | Supply current `dataset_id` and Project `revision`; set `semantic_overrides` by column name and/or `target_column` |
| `GET /projects/{id}/dataset/profile?dataset_id=UUID&revision=N&offset=0` | Bounded source profile for the current Dataset/configuration; stale requests return 409 |

Omit `target_column` to leave it unchanged; send null to clear it. An override
value of null restores inference. Stale configuration or unconfirmed replacement
returns 409. Invalid CSV or target returns sanitized 422 feedback. Reads do not
update Project timestamps; persisted edits use UTC ISO timestamps.

The two domain tables use ordinary SQLAlchemy types. Dataset's ordered JSON
column metadata keeps schema observations and overrides together without adding
one table per column. Project's composite active-Dataset foreign key enforces
same-Project ownership, and Dataset's owner foreign key requires a real Project.
SQLite foreign keys are enabled on every connection. No raw rows, Pipeline IR,
or Run records are added by this phase.

## Source exploration and deletion

Explore reads the fingerprint-verified immutable source using the ingestion parser.
Profiles are computed on demand over the full source, not the 20-row preview.
Explore requests its structured profile directly from the Project snapshot; it
does not fetch Data's unused raw preview on navigation or refresh.
No profile cache or raw values are persisted in SQLite. Responses identify the
Dataset, fingerprint, Project revision, and `source-profile-v1` calculation version.
The server checks identity/revision before and after computation. The UI aborts
obsolete requests, remounts on a new snapshot, and refreshes on navigation,
explicit Refresh, or return from another browser tab. It does not poll for edits
made by another client while the page remains active.
Automatic focus refresh applies only to Explore, preserving Data's file selection
when the native file picker closes.

Profile limits and conventions:

- 20 columns per page; 10 categorical values by descending frequency, with ties
  in first-source-occurrence order. Remaining observations are counted as Other.
  Categorical labels beyond 120 characters are visibly shortened; target labels
  are never shortened or numerically coerced. Missing values are separate.
- Continuous/unknown columns with numeric physical dtype receive summaries.
  Quartiles use linear interpolation; standard deviation is the sample statistic.
  Boxplot whiskers are observed values within 1.5 IQR, with an outlier count;
  an interpolated quartile is the endpoint when no in-fence observation extends
  beyond that side of the box (small/skewed samples).
  Histograms use up to 10 equal-width bins over observed min/max; repeated edges
  collapse at floating-point precision and constant data uses one bin.
- Unsafe integers retain exact tagged extrema; float summaries/charts are
  explicitly unavailable rather than rounded. Overflowing summaries are also
  unavailable. All-missing, constant, and insufficient observations are explicit.
- Pearson correlation uses the first 12 continuous numeric feature candidates
  in source order, pairwise complete observations, and a displayed pair count.
  Targets, excluded columns, and categorical/identifier columns are omitted.
  Constant, insufficient, or unsafe-integer pairs return null rather than zero.
- High cardinality means at least 20 distinct values and at least 50% uniqueness
  among non-missing observations for discrete, text, or identifier columns.
  Duplicate counts exclude the first identical row. Class proportions and
  identifier flags are observations, not preprocessing recommendations.

NumPy is now a direct backend dependency for numeric summaries and correlation;
pandas remains responsible for parsing and source observations. Charts use native
HTML/SVG with readable tables and labels, without a chart framework.

Project deletion requires explicit UI confirmation and the current revision.
The service validates generated UUID paths and rejects linked/redirected trees.
A revision-guarded database write lock precedes staging recovery so overlapping
requests cannot mistake another live deletion for a crashed operation.
Within a database transaction it clears the active reference and removes owned
metadata, then renames the Project directory to `MLSTUDIO_HOME/.deleting/<id>`
before committing. Handled pre-commit failures roll back and restore the directory.
After commit, it removes the staged files. Cleanup failure returns a sanitized
503 and the same DELETE request can retry; a staged pre-commit crash is likewise
recoverable by retry. This is not a SQLite/filesystem atomic transaction or a trash
feature. There is no automatic recovery worker. Replaced sources are deleted only
with their owning Project; other Projects and external originals remain untouched.

## Verified checks

From `backend/`:

```powershell
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m pip check
```

Tests cover health, Project persistence, source bytes/fingerprints, schema and
inference, overrides, binary target validation, replacement retention, upload
limits, stale edits, integrity failures, constraints, and migrations. The tested
Starlette release emits an upstream deprecation warning for its supported httpx
TestClient adapter; tests pass.

From `frontend/`:

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

Next.js 16.3.8 and React 19.3.0 were resolved from npm's stable releases.
TypeScript 6.0.3 is pinned because Next's typescript-eslint parser rejects 7.0.
ESLint 9.39.5 is pinned because Next's React lint plugin fails with ESLint 10.11.0.
npm labels ESLint 9 deprecated; revisit these tooling pins when upstream support
lands. No lint rules are disabled to hide these failures. Next build does not
run lint, so all three commands are required.

Run `git diff --check` and inspect `git status` before committing. Phase 1 adds
pandas and python-multipart as direct backend dependencies; no training library
is installed. Setup commands must stay backed by actual
verification; do not document aspirational commands as working instructions.

Phase 1 verification passed 69 backend tests, Ruff checks, `pip check`, fresh
and Phase 0 Alembic upgrades, and `alembic check` with no schema drift.
`npm.cmd ci`, typecheck, lint, and production build also passed. The clean npm
install reported zero vulnerabilities; the existing ESLint deprecation remains.

Headless Chrome exercised the real UI with synthetic CSVs in a disposable
workspace outside the repository: create Project, upload, inspect summary and
preview, override a semantic type, reject a three-class target, select a valid
binary target, reload and recover configuration, reject malformed replacement,
then explicitly replace and verify the former artifact remains. This check used
the production server (`npm.cmd run start`) and the development server. No
browser automation dependency was added to the application.

Phase 1.5/2 verification includes bounded profile
calculations, typed target distributions, numerical precision edges, stale profile
requests, and deletion isolation/rollback/retry. Ruff, `pip check`, fresh Alembic
upgrade/schema check, frontend typecheck/lint, and production build also pass.
Headless Chrome verified contextual upload/target errors, semantic overrides,
Explore charts and missingness, reload, external replacement refresh, exact large
integer labels, dialog Escape/focus restoration, responsive layout, and permanent
Project deletion while preserving another Project. Synthetic files and screenshots
were kept outside the repository.

## Working Pipeline and Prepare

Run `alembic upgrade head` before starting an updated backend. Migration
`0003_working_pipeline` adds Project-owned JSON intent and migrates existing
former-target exclusions into its feature map, then removes the temporary
`former_targets` field. Source artifacts and Project revisions are preserved.

`GET /api/v1/projects/{id}/pipeline` returns canonical IR `0.1`, the current
revision, source column context, typed target classes, and contextual validation.
`PATCH` on that resource takes `{revision, ir}`. Incomplete or semantically
invalid intent can be saved; unsupported structural vocabulary returns 422.
`POST /api/v1/projects/{id}/pipeline/reset` takes `{revision, dataset_id}` for an
explicit reset. Stale writes return 409. GET never changes Project state.

Initial feature candidates retain the existing included default, with no
operations. Unsupported semantic types are visible blocking issues until
excluded or their interpretation is corrected in Data. Numerical preparation
requires continuous semantics and numeric physical values; categorical/binary
preparation supports most-frequent imputation and one-hot encoding. Operation
order and duplicate families are validated without silently repairing intent.
Incompatible excluded-feature operations remain dormant non-blocking issues.
Prepare validity concerns preparation intent; classifier, raw passthrough,
missing-feature support, split feasibility, and execution readiness still need
the later Train/execution implementation. Model and split remain null.

Positive class uses `{value_type, value}` for string, integer, float, or boolean.
Unsafe integers use canonical decimal strings within the integer wrapper, so
browser JSON cannot round them. The float tag retains float meaning even when
JavaScript serializes an integral float without a decimal point. Class labels
are the only source values intentionally persisted as experiment intent; no
preview rows or observed-class lists are stored in SQLite.

Data target changes reconcile a matching working recipe: remove the new target
from features, restore the former target excluded, preserve unrelated feature
choices, and clear positive class. Replacement retains the old recipe's binding
and marks it stale. Prepare offers an explicit confirmed reset for the current
source; it does not infer schema compatibility or delete the previous artifact.
Data/Explore role views derive participation from the matching IR. A stale old
recipe never assigns roles to the replacement Dataset.

## Manual GitHub setup

The workspace began without a remote. Publish it to the chosen owner/repository
through the maintainer's normal process; no remote is assumed by this guide.

Before inviting public reports and contributions, maintainers should:

- Enable Private Vulnerability Reporting and verify the private report action;
  update [SECURITY.md](../SECURITY.md) if a verified private contact is added.
- Establish a private conduct-reporting channel and replace the explicit pending
  channel notice in [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md).
- Configure default-branch protection or a ruleset appropriate to the team;
  require review where feasible and require checks only when real checks exist.
- Review repository security settings, including available secret scanning and
  push protection. Enable dependency alerts when a dependency graph exists.
- Set a repository description, for example “Visual ML. Real code. Reproducible
  experiments.” Consider topics such as `machine-learning`, `local-first`,
  `tabular-data`, and `reproducibility`.
- Verify Issue Forms and the PR template render correctly on GitHub.
- Optionally enable Discussions for open-ended conversation and a Project board
  for milestones; neither is necessary to contribute.

No CODEOWNERS is supplied because ownership is not established. No Dependabot
configuration is supplied in Phase 0.
These settings are not activated by documentation and remain manual work.
