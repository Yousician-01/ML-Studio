# Development

## Implemented workflow

The application supports Project creation and metadata editing, managed CSV
ingestion/replacement, source summaries and previews, semantic overrides, and
binary target selection. SQLite stores domain metadata; immutable source files
live in the managed workspace. Phase 1.5 adds a shared visual foundation,
contextual validation, and permanent Project deletion. Phase 2 implements
deterministic source exploration. Phase 3 adds persisted Pipeline IR and Prepare
configuration; Phase 3.5 adds visual exploration and improved semantic detection.
Phase 4 completes Train configuration and code-generation readiness.
Phase 5 adds deterministic complete Python source and a read-only Code preview.
Phase 6A adds backend Run persistence, exact-source subprocess execution, output
validation/finalization, and conservative recovery. Phase 6B adds Train execution,
Runs/history inspection, and local MLflow tracking. Phase 7 adds frozen Run
evaluation and exactly-two Run comparison. AI remains deferred.
The [v0.1 contracts](specifications/project-v0.1.md) remain authoritative.

Keep changes scoped, use mature libraries, preserve exact generated-source
execution and training-only preprocessing, and validate behavior
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
connectivity, not migration currency. Domain requests check the database revision
against Alembic's installed script heads before opening a session. A missing or
stale revision returns a sanitized 503 with current/required revisions and the
explicit `python -m alembic upgrade head` command (from an activated backend
environment). No automatic migration runs. Failed checks retry on the next
request; a successful check is remembered for the app lifetime. Restart the
backend after deploying code or replacing a running database. Multiple current
and required heads are compared as sets. The message also cautions that databases
from a newer app version need that version; it never suggests a downgrade.
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
3. With at least three distinct values and at least 95% uniqueness among
   non-missing observations: UUID-shaped strings are identifiers; otherwise an
   `id`, `uuid`, `guid`, `identifier`, or `key` name token is required, together
   with integer-like numbers or opaque alphanumeric/underscore/hyphen strings.
   Names split on boundaries and CamelCase, so `paid`, `width`, and `middle`
   are not ID hints. Integral floats can represent IDs with missing cells;
   fractional measurements, ordinary dates, and uniqueness alone do not qualify.
4. Other numeric columns: `continuous` with variation, otherwise `unknown`.
5. String values all matching an ISO date/datetime shape and successfully parsing
   as ISO dates: `datetime`. Numeric timestamps are not inferred as datetime.
6. Any string over 80 characters or containing at least eight whitespace-separated
   words: `text`.
7. Other strings: `categorical` at up to 20 distinct values or a uniqueness ratio
   of at most 20%; otherwise `text`.
8. Remaining types: `unknown`.

New ingestion records `semantic-v2` per column. Older stored inferences are not
silently recomputed: Data offers **Refresh detected types** to update inference
explicitly while preserving overrides, source bytes, physical observations, and
preparation intent. Semantic edits increment the Project revision and invalidate
older profile requests. Data shows manual override state and an explicit reset
to detected type; Prepare revalidates retained operations using effective types.

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
| `PATCH /projects/{id}/dataset` | Supply current `dataset_id` and Project `revision`; set `semantic_overrides` by column name, `target_column`, and/or `refresh_inference: true` |
| `GET /projects/{id}/dataset/profile?dataset_id=UUID&revision=N&offset=0` | Bounded source profile for the current Dataset/configuration; stale requests return 409 |

Omit `target_column` to leave it unchanged; send null to clear it. An override
value of null restores inference. Stale configuration or unconfirmed replacement
returns 409. Invalid CSV or target returns sanitized 422 feedback. Reads do not
update Project timestamps; persisted edits use UTC ISO timestamps.

The two domain tables use ordinary SQLAlchemy types. Dataset's ordered JSON
column metadata keeps schema observations and overrides together without adding
one table per column. Project's composite active-Dataset foreign key enforces
same-Project ownership, and Dataset's owner foreign key requires a real Project.
SQLite foreign keys are enabled on every connection. No raw rows or profile caches are stored in these tables. Project also owns
Working Pipeline JSON intent. Phase 6A adds immutable Run records separately.

## Source exploration and deletion

Explore reads the fingerprint-verified immutable source using the ingestion parser.
Profiles are computed on demand over the full source, not the 20-row preview.
Explore requests its structured profile directly from the Project snapshot; it
does not fetch Data's unused raw preview on navigation or refresh.
No profile cache or raw values are persisted in SQLite. Responses identify the
Dataset, fingerprint, Project revision, and `source-profile-v2` calculation version.
The server checks identity/revision before and after computation. The UI aborts
obsolete requests, remounts on a new snapshot, and refreshes on navigation,
explicit Refresh, or return from another browser tab. It does not poll for edits
made by another client while the page remains active.
Automatic focus refresh applies only to Explore, preserving Data's file selection
when the native file picker closes.

Profile limits and conventions:

- Column search is case-insensitive and limited to 200 characters. Semantic and
  observation filters use validated vocabularies and apply before pagination;
  Dataset-wide overview, target, quality, and correlations remain unfiltered.
  Missingness lists the 20 most-missing columns, descending count with source
  order ties; the column browser can filter all missing columns page by page.
- Constant means exactly one distinct non-missing value; all-missing is separate.
  Near constant means more than one distinct value and a dominant value occurring
  in at least 95% of non-missing observations. Missing values are not a category
  in that denominator. Counts are observations, never automatic exclusions.
- Skewness is adjusted Fisher-Pearson: `sqrt(n*(n-1))/(n-2) * m3/m2**1.5`,
  where `mk = mean((x-mean(x))**k)` over non-missing numeric observations.
  Shift/scale normalization avoids unnecessary overflow. Fewer than three,
  constant, or precision-limited observations return an explicit unavailable
  result. No qualitative skewness bands or recommendations are assigned.

- 20 columns per page; 10 categorical values by descending frequency, with ties
  in first-source-occurrence order. Remaining observations are counted as Other.
  Categorical labels beyond 120 characters are visibly shortened; target labels
  are never shortened or numerically coerced. Missing values are separate.
- Continuous/unknown columns with numeric physical dtype receive summaries.
  Quartiles use linear interpolation; standard deviation is the sample statistic.
  Fences are `Q1 - 1.5*(Q3-Q1)` and `Q3 + 1.5*(Q3-Q1)`; outliers are
  strictly outside them, with percentage over non-missing observations.
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
HTML/SVG with readable tables and labels, without a chart framework. Explore
provides interactive histograms, boxplots, frequency/missingness bars, and a
Pearson heatmap with exact hover/focus values and accessible tables. Charts use
bounded backend aggregates, not source rows. Positive class is displayed only
when explicitly configured in a matching Working Pipeline.

The [Data Inspector reference](https://github.com/Yousician-01/Data-Inspector)
was reviewed for deterministic EDA coverage. ML Studio keeps its own contracts
and definitions (95% non-missing dominance and adjusted skewness); no health
score, hard-coded preparation recommendations, or Isolation Forest is run.

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
npm.cmd run test
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

Next.js 16.3.8 and React 19.3.0 were resolved from npm's stable releases.
TypeScript 6.0.3 is pinned because Next's typescript-eslint parser rejects 7.0.
ESLint 9.39.5 is pinned because Next's React lint plugin fails with ESLint 10.11.0.
npm labels ESLint 9 deprecated; revisit these tooling pins when upstream support
lands. No lint rules are disabled to hide these failures. Next build does not
run lint or tests, so all four commands are required.

Run `git diff --check` and inspect `git status` before committing. Backend dependencies are declared in
`backend/pyproject.toml`; frontend dependencies and scripts are declared in
`frontend/package.json`. Setup commands must stay backed by actual
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
the model-aware validation described below. Execution still belongs to a later
phase; unconfigured model and split remain null until explicitly selected.

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

## Phase 3.5 verification

The recovered slice passes 177 backend tests, Ruff check/format check, `pip check`,
frontend typecheck/lint/production build, and `git diff --check`. Fresh and
existing-schema disposable workspaces pass Alembic upgrade and schema checks.
No new database migration or dependency is needed for this slice.

Chrome exercised both development and production with a synthetic 101-row,
13-column source containing IDs, UUIDs, missing values, duplicates, constants,
near constants, skew/outliers, correlated values, categories, and long names.
Verified flows include override/reset, binary target rejection/acceptance,
reload persistence, visual profiles/search/filters, effective semantics in
Prepare, retained incompatible operations, and configured positive-class display.
Chart focus exposes exact values; coefficient tables, reduced motion, and
390px/900px layouts were checked. Explore does not request the Data preview.
An intentionally stale disposable database produced the migration instruction
in the real UI; explicit upgrade followed by Retry recovered without an app
restart. Browser fixtures, profiles, screenshots, and databases stayed in TEMP.

## Train configuration (Phase 4)

Train uses the same Project-owned Working Pipeline JSON and existing Pipeline
GET/PATCH endpoints as Prepare. There is no new table, migration, estimator,
training dependency, or separate training-settings representation. GET is
read-only; opening Train does not select a model or split. The response includes
an explicit default catalog, Dataset filename, eligible/train/test row counts,
contextual issues (including parameter field paths), and `code_generation_ready`.
`executable` remains a legacy false field on this configuration contract. Train's
Run action uses saved `code_generation_ready`, a current executable Code preview,
revision/hash checks, and separately queried execution capacity. The Run API
revalidates all inputs; the legacy field is not an execution authorization signal.

The frozen specifications define the parameter surface, penalty values, and
minimum model constraints. They explicitly leave numeric defaults to
implementation. ML Studio materializes these defaults when a model is selected:

| Model | Explicit defaults | Contextual validity |
| --- | --- | --- |
| `logistic_regression` | `C=1.0`, `penalty="l2"`, `max_iter=1000` | Finite C > 0; penalty l1/l2; integer max_iter >= 1 |
| `decision_tree` | `max_depth=null`, `min_samples_split=2`, `min_samples_leaf=1` | Depth null or integer >= 1; split integer >= 2; leaf integer >= 1 |
| `random_forest` | Tree defaults plus `n_estimators=100` | Tree constraints; integer estimators >= 1 |

There are no additional model parameter caps imported from the superseded Phase 4
prompt. Unknown parameters (including class_weight, criterion, solver, and
max_features), booleans as numbers, numeric strings, non-finite numbers, and
fractional integer parameters are rejected at the typed API boundary. Null can
represent unresolved draft values; null max_depth specifically means unlimited.
Out-of-range numeric intent is persisted with blocking issues rather than clamped.
Omitted supported fields materialize the explicit defaults; supplying null retains
unresolved intent. Switching models uses the new model's defaults, including when
switching back; no hidden per-model history is kept.

The split defaults to `test_size=0.2`, `random_seed=42`, `stratify=true` when the
user explicitly configures it. The UI shows percentages; JSON stores the fraction.
The Phase 4 supported range is 0.05?0.50 and the seed is an integer 0?2147483647.
These implementation limits/defaults are not additional frozen specification text.
There is one experiment seed. Future code generation retains frozen mappings:
l1 -> liblinear, l2 -> lbfgs, with no solver control; tree/forest random state uses
the split seed. Logistic Regression random state is not required by that contract.

Split feasibility uses only non-missing target counts. Test row count is
`ceil(eligible_rows * test_size)`; training gets the remainder. Stratification
requires at least two observations per class and two rows per partition. Binary
largest-remainder allocation is checked in sorted class order, with NumPy's
legacy RandomState seeded tie breaking matching the intended sklearn allocation.
No row indices are generated and no source rows are sampled or split. A requested
stratified allocation that would omit a class is blocking, even if minimum
partition sizes pass. Non-stratified configuration makes no class-representation
guarantee. See the reviewed [sklearn splitter source](https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/model_selection/_split.py)
and [allocation source](https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/utils/extmath.py).
Phase 5 must verify this against its chosen supported sklearn version.

Readiness extends the existing validator: source binding, target and typed
positive class, feature-map completeness, effective semantics, operation grammar,
model parameters, and split feasibility must have no blocking issues. Dormant
excluded-operation incompatibilities remain non-blocking. For this initial
configuration surface, missing included feature values require explicit
imputation; all-missing eligible features are blocking even with imputation.
Non-numeric raw values require encoding. This avoids claiming unverified native
missing-value support from an unselected future library version. No operation is
automatically inserted and no feature is silently dropped.

Train parameter and split forms save explicitly; model selection saves defaults
immediately. Pending editor strings are visibly unsaved UI state and suppress the
ready message until saved. Editing one form temporarily disables the other so a
save cannot discard its unsaved input. Navigation discards only unsaved input;
saved intent survives navigation, reload, and app restart. Revision conflicts
return 409, preserve the current editor, and require reload before further edits.
Target changes retain model/split, reset positive class, reconcile participation,
and revalidate stratification. Replacement retains a stale old binding; explicit
reset in Prepare clears the whole working recipe, including model and split.

Browser acceptance used disposable synthetic data outside the repository. Chrome
verified all model controls/defaults, l1 selection, model switching, parameter and
split edits, invalid drafts, reload/navigation, 409 recovery, impossible singleton
stratification, explicit non-stratified recovery, loading/error/retry states,
long names, 900px layout, keyboard focus, and reduced motion. The ready state says
**Ready for code generation**; there is no execution button. The same acceptance
flow passed on development and production servers; restarting the backend
restored saved model/split intent and readiness. Final validation passed 275
backend tests, Ruff check/format check, pip check, frontend typecheck/lint/build,
and disposable fresh/existing-schema Alembic upgrade/check. No dependency changes
were required.

## Contributor CI

[Contributor CI](../.github/workflows/ci.yml) runs on every `pull_request` targeting
`main`, including documentation-only PRs. There are no path filters or matrix jobs.
The stable status-check names are **Frontend checks** and **Backend checks**.

Both jobs use GitHub-hosted Windows runners, matching the documented local platform.
The frontend uses Node 24.13.0 and runs `npm ci`, `npm run test`,
`npm run typecheck`, `npm run lint`, and `npm run build` from `frontend/`.
It also runs `git diff --check HEAD^ HEAD` at the repository root after fetching
the PR merge commit and its base parent; this checks committed PR changes rather
than only a clean checkout.

The backend uses Python 3.14.2 and runs `python -m pip install -e ".[dev]"`,
`python -m pytest`, `python -m ruff check .`, `python -m ruff format --check .`,
`python -m pip check`, and `python -m pip wheel --no-deps --wheel-dir dist .`
from `backend/`. The wheel command uses the existing Hatchling build backend
declared in `pyproject.toml`; no separate build CLI dependency is needed.
CI sets `MLSTUDIO_HOME` under the runner temporary directory; tests also isolate
their workspaces. Wheels are validation output only and are not published.

Actions are pinned to full commit SHAs. Permissions are limited to `contents: read`,
checkout does not persist credentials, and no repository secrets, privileged PR
trigger, deployment environment, or shared dependency cache is used. Superseded
runs for the same PR are cancelled, and jobs have bounded timeouts. Local hooks
remain optional and are not installed by CI.

## Manual GitHub setup

Repository settings must be configured by maintainers on GitHub; files alone
do not activate or verify branch protection or rulesets.

Before inviting public reports and contributions, maintainers should:

- Enable Private Vulnerability Reporting and verify the private report action;
  update [SECURITY.md](../SECURITY.md) if a verified private contact is added.
- Establish a private conduct-reporting channel and replace the explicit pending
  channel notice in [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md).
- Enable Actions and allow the SHA-pinned official `actions/checkout`,
  `actions/setup-node`, and `actions/setup-python` actions. Keep default workflow
  permissions read-only and do not enable write tokens or secrets for fork PRs.
- Open a PR targeting `main` and let **Frontend checks** and **Backend checks**
  appear. Configure a branch-protection rule or ruleset for `main` requiring PRs,
  at least one approving review, and both exact status-check names above (source:
  GitHub Actions). Require the branch to be up to date before merging so checks
  cover the current merge result. Restrict bypasses to explicitly authorized
  maintainers and prevent force pushes/deletion of `main`.
- Keep fork-workflow approval requirements enabled and review workflow changes
  before approving execution. The files do not configure these GitHub settings.
- Review repository security settings, including available secret scanning and
  push protection. Enable dependency alerts when a dependency graph exists.
- Set a repository description, for example “Visual ML. Real code. Reproducible
  experiments.” Consider topics such as `machine-learning`, `local-first`,
  `tabular-data`, and `reproducibility`.
- Verify Issue Forms and the PR template render correctly on GitHub.
- Optionally enable Discussions for open-ended conversation and a Project board
  for milestones; neither is necessary to contribute.

No CODEOWNERS is supplied because ownership is not established. No Dependabot
configuration is supplied.
These settings are not activated by documentation and remain manual work.


## Deterministic Code preview (Phase 5)

`GET /api/v1/projects/{project_id}/code` reads a consistent persisted context,
verifies the managed source, validates intent, resolves a typed
`EffectiveExecutionPlan`, and renders Python. It returns `ready`, structured
`issues`, current `project_id`/`dataset_id`/`revision`, `source` (null when blocked),
`source_sha256`, `plan_sha256`, `generator`, `filename`, and library versions.
No preview cache, table, migration, Run directory, or historical artifact is created.
The UI aborts superseded requests, checks the returned revision against current
Project state, refreshes on focus/navigation, and hides old source while refreshing.

### Versions and resolved implementation choices

The generator identity is `mlstudio-python-v1`; the plan schema is `0.1` and the
implementation contract is `sklearn-local-v1`. Bump generator identity whenever
rendered source or embedded helper behavior changes after release. Working previews
may change; Phase 6 must preserve exact historical source instead of regenerating it.

Python remains >=3.12, pandas >=2.2,<4, and NumPy >=2,<3. The tested local environment
is Python 3.14.2, pandas 3.0.6, NumPy 2.5.3, scipy 1.18.1, scikit-learn 1.9.1,
and joblib 1.5.3. Scikit-learn is pinned to 1.9.1; joblib is explicit
`>=1.5.3,<1.6`. The sklearn pin intentionally precedes removal of the frozen
`penalty` API. Its upstream deprecation warning is expected; L1/liblinear and
L2/lbfgs are verified with real library fixtures. Other declared pandas/NumPy/Python
versions are not claimed tested by this acceptance run.

A plan records the exact installed relevant versions and Python version. The future
script refuses an environment that differs. Dataset parser/pandas provenance must
match the current interpretation; restore a compatible environment or explicitly
replace/review the Dataset when it does not. This is compatibility protection, not
full environment recreation. No environment/requirements artifact is generated.

Features use separate branches in source-column order, including features that
share operations. Empty operation lists become explicit passthrough; excluded
features never enter the plan. Parameter keys/imports have stable order; branch
names use controlled ordinals. Output is UTF-8 without BOM, LF, four-space indentation,
one trailing newline, and escaped builtin Python literals. Dataset names/labels
never become Python identifiers or source fragments.

Resolved options include OneHotEncoder `handle_unknown="ignore"`, sparse float64
output, no category dropping/frequency grouping; ColumnTransformer `remainder="drop"`,
`sparse_threshold=1.0`, one job; training-only SimpleImputer statistics without
indicators or empty-column fallback; conventional centering/scaling, MinMax range
0..1 without clipping, and Robust interquartile scaling. All included training
columns must have observed values: otherwise the workload fails before fitting.
The complete preprocessing+classifier pipeline is the eventual inference artifact.

Model defaults and curated controls remain unchanged. Internal choices explicitly
resolve estimator defaults, tree/forest seeds and single-job forest execution.
Logistic Regression emits its frozen penalty/solver pair plus matching internal
`l1_ratio` for sklearn 1.9.1 compatibility; its random state also receives the
experiment seed. None of these internal choices adds a visual/IR parameter.

Readiness rejects sklearn-incompatible target representations without changing
labels: non-integral floats and unsupported oversized object integers are examples.
Strings, booleans, supported integers (including lossless large int64 labels), and
integral floats are tested. Nullable large integer targets and categorical features
are refused because sklearn converts their pandas extension dtype to float64 and
can merge distinct values. Non-nullable large int64 target labels remain supported.
No label encoding is introduced.

### Faithful standalone loading

The shared `codegen/csv_runtime.py` parser is used by ingestion and embedded as
ordinary Python in the generated script. The renderer bundles fixed package helper
source; generated code imports no ML Studio modules. UTF-8/BOM, strict headers and
row widths, pandas NA conventions, and precision-sensitive integer rereads remain
identical. Preview and generated loading hash the same bounded byte buffer that is
parsed. This prevents a later path replacement from changing the already-verified
buffer; it is not a filesystem sandbox or an atomic-read guarantee against all
local concurrent writers. Digest mismatch refuses loading.

### Future workload interface: cli-v1

The source accepts three required absolute paths, supplied by Phase 6:

```text
python generated_run.py --dataset <source.csv> --result <result.json> --model <model.joblib>
```

This documents the generated interface; Phase 5 does not invoke this command.
Outputs must be distinct new files in existing executor-prepared directories.
The source verifies versions, size, SHA-256, physical interpretation and typed
classes; excludes only missing-target rows; splits; constructs preprocessing and
classifier; fits training data; predicts/evaluates held-out rows; and writes the
complete fitted pipeline with joblib plus a structured JSON result. No database,
workspace discovery, Run ID, Project display name, MLflow, or lifecycle logic is in
that script. Runtime paths never enter generated experiment identity.

`mlstudio-result-v1` success fields are:

- `schema_version`, `status="success"`, `dataset` ID/fingerprint, `generator`;
- `metrics`: accuracy, precision, recall, f1, roc_auc (number or null);
- `roc_auc_unavailable_reason` (string or null);
- `confusion_matrix`: typed `labels` in negative/positive order and 2x2 `values`;
- `population`: source, eligible, training, test row counts;
- `artifacts.model`: complete_pipeline kind and supplied output filename;
- `versions`: exact Python and relevant library versions.

Precision/recall/F1 explicitly use the chosen positive class and zero_division=0.
ROC-AUC uses its matched probability column or correctly oriented decision scores,
never hard predictions. One-class held-out truth produces null plus a reason.
JSON uses sorted keys and allow_nan=False. Typed unsafe integer labels use decimal
strings; the script's Python label constants remain exact integers.

On failure, the script attempts a result with schema_version, status="failed",
stage, and a sanitized message, then exits nonzero. Fixed training-partition
validation messages explain missing classes or entirely missing training features;
other exceptions receive a generic stage message. No raw exception text/rows are
printed. Output writes use temporary files and replacement; Phase 6 still owns
validation, immutable finalization, checksums/references, and deciding Run success.
A partial model alongside a failure result is not a successful artifact. Per-row
prediction persistence is not included.

### Phase boundary and verification

The split guarantee now explicitly requires equivalent source interpretation,
eligible target rows and relevant execution/library version in addition to source
identity, target and split configuration. Model/preprocessing changes alone do not
change split inputs. Only this approved wording was corrected in User Journey.

Tests combine full-source byte goldens, AST/compile checks, import-only standalone
parser parity, literal/adversarial checks, preview side-effect guards, and isolated
sklearn/joblib compatibility fixtures. Library test fixtures may fit tiny models
and serialize to pytest temporary directories; application preview never does.
No generated workload main function or production subprocess executor is run in
Phase 5. Phase 6A now exercises full generated-program execution and local Run
finalization. Phase 6B adds Runs UI and MLflow; Evaluate remains later work.

## Local Run execution (Phase 6A)

Run `alembic upgrade head` before starting the backend. Migration `0004_runs`
adds `runs` and a Project-local sequence counter. Counter allocation does not change
the experiment revision or Project update timestamp. `psutil>=7,<8` is used only
for process creation-time identity, tree termination, and restart reconciliation.

The backend exposes:

- `POST /api/v1/projects/{project_id}/runs`: accepts `request_id` (UUID),
  `expected_revision`, `expected_source_sha256`, and `expected_plan_sha256` from
  the current Code preview. Returns 202 after package creation and worker handoff.
- `GET /api/v1/projects/{project_id}/runs?offset=0&limit=50`: descending sequence,
  bounded pagination (maximum 100).
- `GET /api/v1/projects/{project_id}/runs/{run_id}`: lifecycle, frozen summaries,
  validated successful result, sanitized failure, and artifact integrity.
- `GET /api/v1/projects/{project_id}/runs/{run_id}/code`: exact persisted source;
  missing/corrupt source returns an error and is never regenerated.

Matching request retries return the original attempt even after current edits.
Inconsistent reuse and stale revision/source/plan hashes return 409. Fresh
validation, resolution and generation precede creation. A short transaction checks
revision and allocates sequence, publishes the verified package, then commits
CREATED. No transaction stays open during training. Browser disconnect does not
own or stop execution. Additional attempts receive 409 while capacity is occupied;
there is one OS-locked execution slot per workspace and no queue.

The managed layout is `projects/<project_id>/runs/<run_id>/`, containing frozen
`pipeline_ir.json`, `execution_plan.json`, `generated_run.py`, and `package.json`.
The manifest records Dataset reference, hashes/sizes, Project revision, versions,
and source/eligible counts. No source CSV is copied into the Run. IR preserves
excluded/dormant configuration; the effective plan remains separate evidence.

The lifespan-owned worker launches the persisted script with the backend venv
interpreter, `-I -B -u -X utf8`, explicit absolute Dataset/output arguments,
`shell=False`, Run cwd, and stdin disconnected. Environment inheritance is limited
to OS/runtime variables and numeric thread counts are fixed to one. **The subprocess
is not a security sandbox.** No arbitrary Python is accepted by the Run API.

Operational defaults (all use the `MLSTUDIO_` environment prefix):

| Setting | Default |
| --- | --- |
| `RUN_TIMEOUT_SECONDS` | 1800 (30 minutes) |
| `RUN_LOG_BYTES` | 10485760 per stdout/stderr stream (10 MiB) |
| `RUN_RESULT_BYTES` | 1048576 (1 MiB) |
| `RUN_MODEL_BYTES` | 1073741824 (1 GiB) |
| `RUN_DISK_RESERVE_BYTES` | 67108864 (64 MiB package-preparation reserve) |
| `RUN_TERMINATION_GRACE_SECONDS` | 5 |

Both pipes are drained continuously; excess log bytes are discarded and truncation
is recorded. Timeout terminates the owned process/tree, escalates if needed, reaps,
and closes logs before terminal finalization. No memory quota or resource sandbox
is claimed. Logs may contain sensitive information and are not returned by these APIs.

The child writes result/model only into `.pending/`. Exit zero is insufficient:
strict bounded JSON rejects duplicate keys/nonfinite values, checks exact protocol,
Dataset/generator/environment, typed class orientation, matrix/counts, metric
consistency, ROC-AUC availability, and the complete-pipeline model declaration.
The model must be a bounded nonempty regular managed file. Production ingestion
never unpickles it; checksums prove byte integrity, not pickle safety.

After process quiescence, required inputs are reverified, outputs flushed/hashed
and renamed, diagnostics finalized, and only then is SUCCEEDED committed. Failure
keeps evidence without promoting partial output references or metrics. SQLite and
filesystem writes are ordered but are not a shared atomic transaction. A storage
or DB outage can leave an active record requiring recovery; it cannot manufacture
success. Windows uses file fsync and same-volume rename; POSIX also fsyncs parent
directories.

Startup reconciliation never resumes or infers success. It verifies process
creation time and exact arguments (or scans for the unique exact Run command in
the launch/journal gap), stops safely owned workloads, and records interrupted
attempts FAILED. Ownership uncertainty preserves evidence and blocks new execution
until reconciled. Orphan published packages are quarantined in `.run-orphans/`,
never launched. Missing historical inputs remain corruption, never regeneration.
Active attempts block Project deletion; terminal Run rows are removed before
Dataset/Project rows using the existing staged directory deletion protocol.

Run tests use isolated temporary workspaces and include actual generated execution
for all three supported classifiers. No Runs frontend, MLflow, Evaluate, queue,
retry/cancellation endpoint, or editable code is introduced by Phase 6A.

## Train, historical Runs, and local tracking (Phase 6B)

Migration `0005_tracking` adds only the nullable MLflow Run ID, separate tracking
status, sanitized tracking error, and tracking timestamp. It does not rewrite
`0004_runs` or change immutable execution facts. Run `alembic upgrade head`.

Train submits only saved, reviewed revision/source/plan hashes and a fresh request
UUID. The browser retains an unresolved submission identity in localStorage before
POST; this is transport recovery, never authoritative experiment or Run state.
An uncertain response can be checked with the same request ID. A deliberate new
execution gets a new ID. A stale 409 refreshes preview state and requires review;
there is no automatic resubmission, save-and-run, queue, or execution retry.

`GET /api/v1/projects/{project_id}/runs/capacity` reports workspace occupancy and
recovery needs. The Run list accepts optional `request_id` filtering for recovery.
Runs uses 20-item pages, descending sequence. Active detail/list reads poll every
two seconds, stop at terminal state, and abort/clear timers on navigation. Capacity
checks occur every three seconds while Train is mounted. Browser disconnection
does not cancel execution. Network errors require explicit status refresh.

Run detail reads verified frozen IR/plan, typed classes, metrics, compact confusion
matrix, provenance and artifact integrity. Historical Code uses the dedicated
`/runs/{run_id}/code` endpoint and never regenerates. Current Code is a preview of
the mutable Working Pipeline. Dataset replacement or current edits cannot rewrite
historical configuration or source. Runs does not implement Evaluate or comparison.

The backend depends on `mlflow-skinny==3.16.1` (tracking client), using the existing
SQLAlchemy/Alembic dependencies; no MLflow server or additional frontend library
is needed. Explicit client URIs ignore inherited `MLFLOW_TRACKING_URI` and registry
URI. MLflow telemetry and workspace multiplexing are disabled. The pinned client's
`_MLFLOW_SERVER_ARTIFACT_ROOT` setting also places its default experiment locally;
tests cover that integration detail. Reused experiment/Run artifact URIs must be
local paths under the managed tracking root, including link checks.

```text
MLSTUDIO_HOME/
├── mlstudio.db                    # authoritative domain database
├── projects/<project_id>/runs/    # authoritative immutable evidence
└── mlflow/
    ├── mlflow.db                  # independent MLflow SQLite schema
    └── artifacts/<project_id>/   # MLflow evidence copies/model references
```

Tracking begins after terminal local finalization and release of execution capacity.
It uses a separate local tracking lock, synchronous MLflow client writes, one
attempt per completion, and one reconciliation pass at backend startup. No retry
scheduler exists. A failed synchronization records `FAILED` without changing the
local SUCCEEDED/FAILED outcome. Startup reuses the persisted MLflow ID or searches
the exact ML Studio Run tag after an interrupted association write. Ambiguous
associations fail safely; they do not create another tracking Run.

Captured data: identity/provenance tags, model/split/target/typed positive-class
parameters, concise preprocessing, successful core metrics and available ROC-AUC,
frozen IR/plan/package/source, and successful result. A model reference records its
workspace-relative path, size and hash; tracking never loads the pickle. Failed
attempts log safe failure stage/code and input evidence, without partial metrics
or models. Raw CSV, stdout/stderr, arbitrary exceptions, autologging and generated
workload MLflow imports are excluded. MLflow is repairable tracking infrastructure,
not the domain authority or the only copy of required evidence. Project deletion
does not implement MLflow garbage collection; tracking copies may remain locally.

Frontend policy, transport, polling and server-rendered view checks use the existing
Node/TypeScript/React dependencies: `npm run test`. They do not replace browser
verification of interaction, responsive layout, focus, and reduced-motion behavior.
