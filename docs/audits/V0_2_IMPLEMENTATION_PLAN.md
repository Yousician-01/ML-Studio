# ML Studio v0.2.0 implementation plan (proposed)

> For future implementers: this is an audit proposal awaiting product approval,
> not authorization to change code. Use the approved execution workflow task by
> task after approval; do not treat the proposal as a replacement frozen spec.

**Goal:** preserve the complete v0.1 binary workflow/history while adding a small
single-target regression workflow with Linear Regression and Ridge.

**Architecture:** extend typed task/model policies and dispatch by explicit IR,
plan and result versions. Keep current v1 compiler/result behavior available;
reuse managed source, exact-source subprocess ownership and immutable finalization.

**Tech stack:** existing FastAPI/Pydantic/SQLAlchemy/SQLite/Alembic, pandas/sklearn,
Next/React/TypeScript and current tests. No new dependency is necessary for this scope.

**Design inputs:** [gap analysis](ARCHITECTURE_GAP_ANALYSIS.md),
[feature feasibility](ML_FEATURE_EXPANSION.md) and
[roadmap](DEVELOPMENT_ROADMAP.md). The v0.1 files under `docs/specifications/`
remain authoritative for existing v1 behavior. Future normative contracts must
be approved separately; this audit does not change them.

## Objectives and explicit exclusions

Ship new regression Projects with an explicit task, numeric target, existing
feature preparation, seeded unstratified holdout, two models, deterministic Python,
immutable Runs, MAE/MSE/RMSE/conditional R2 and task-aware historical comparison.
Keep legacy binary Projects/configurations/Runs/source bytes accessible. Introduce
a small model catalogue for existing models plus these two, not a plugin runtime.
Include task-aware prerequisites and unsaved Train navigation protection.

Exclude multiclass, text, clustering, PCA, other regressors, new ensembles, ROC or
residual plots, per-sample prediction storage, cross-validation/HPO, visual canvas,
editable code, AI, optional ML packages, platform expansion and packaging overhaul.

## Proposed decisions needing approval

1. Task is selected at new Project creation and is not convertible in place in
   v0.2. Existing Projects remain binary; Dataset replacement does not change task.
2. Two initial regressors only. Defaults proposed: Linear Regression with
   `fit_intercept=true`; Ridge `alpha=1.0`, `fit_intercept=true`. Allow finite
   nonnegative alpha; retain missing/invalid editable values as contextual issues.
3. Regression excludes missing targets, never imputes them; finite numeric values
   required, booleans/object labels and unsafe precision conversions rejected.
   Numeric two-valued and constant targets are permitted when regression is explicit.
4. MAE/MSE/RMSE required and finite; R2 unavailable with reason for fewer than two
   test rows or constant test target. Negative finite R2 is valid. No positive class,
   confusion matrix or ROC-AUC for regression; no fabricated values in those slots.
5. Existing binary working recipes stay IR `0.1`; new regression intent uses `0.2`
   with an explicit task discriminator. No bulk automatic historical JSON migration.

## Global constraints and review focus

- Keep source UUID/fingerprint identity, source bytes and inference/override semantics.
- Keep v1 generated-source goldens unchanged; no newline normalization in tests.
- Runs execute exact frozen bytes; history never regenerated against a newer library.
- Metrics and snapshots come from Run evidence, not current Project/MLflow state.
- Preserve exactly-two selection, typed binary orientation, integrity warnings and
  unavailable-not-zero semantics. Cross-task comparisons cannot display deltas.
- Keep the declared Windows/Python 3.14.2/Node 24.13.0 acceptance environment unless
  an explicit dependency/platform decision changes it. Do not silently upgrade sklearn.
- Preserve source/editable distribution and existing CI required checks.

Five highest-risk inputs to test: released-schema Projects with cyclic Dataset
ownership; old v1 snapshots under new readers; constant/tiny/negative-R2 regression
targets; unknown/cross-task result versions; replacement or stale revision between
preview and admission. Each is assigned to a task below.

## Actual storage and migration implications

`projects` currently has an equality check fixing `ml_objective`; `active_dataset_id`
has a composite FK to `datasets(project_id,id)`, and `datasets.project_id` refers
back to Projects. `runs` has a composite Dataset ownership FK, terminal constraints,
JSON manifest/artifacts/summary/result and separate tracking fields. Current Alembic
head is `0005_tracking`. JSON intent has strict Pydantic `ir_version: Literal['0.1']`.

At least one new migration is required to widen the Project objective constraint.
Do not edit `0002_project_dataset`, add a second independent authoritative task
column, or run metadata.create_all. SQLite likely needs a checked table rebuild;
test the exact procedure with FK enforcement and all ownership cycles. Approve
the migration method only after fixture proof, including rollback/failure behavior.
Do not prescribe globally disabling foreign keys as an untested shortcut.

Run storage can retain the existing JSON columns; a new task need not add another
Run table. New task identity belongs in new frozen IR/plan/result/summary data.
Legacy Run task is inferred only from its frozen v1 protocol, never current Project.
No schema change is needed merely to keep the regression metrics dictionary.

Before applying an upgrade, use normal application shutdown, preserve a backup of
SQLite and managed files, and establish no live worker owns the workspace. Recovery
must not be bypassed by editing active Run rows. Exact IDs, revisions, sequence
allocation, Dataset references, tracking association and all historical bytes/hashes
are migration invariants. Schema migration is not permission to repair Run evidence.

## Task 1 — pin legacy behavior and migration fixtures

**Existing files to inspect/extend:** `backend/tests/test_run_boundaries.py`,
`test_projects_datasets.py`, `test_codegen.py`, `test_historical_source.py`,
`frontend/tests/{evaluation,run-views}.test.mjs`; migrations `0001..0005`.
**Proposed new test:** `backend/tests/test_task_compatibility.py`.

**Interface:** produces a disposable fixture upgraded through the actual released
migrations with empty/incomplete/stale binary Projects, active/replaced sources,
successful/failed Runs and tracking associations. Include missing/corrupt source
variants; do not commit real user databases, raw data or fitted models.

- [ ] Add assertions for unchanged IDs, revisions, source/artifact/source-code hashes,
  result dictionaries and terminal timestamps before/after upgrade.
- [ ] Add v1-reader and unchanged binary golden assertions before changing contracts.
- [ ] Verify those tests pass against baseline; retain failing expectations for the
  new task/constraint until subsequent work implements them.

Validation: from `backend`, `.venv/Scripts/python.exe -m pytest
tests/test_task_compatibility.py tests/test_codegen.py::test_source_goldens -q`.
Expected final result: all selected cases pass without changing any v1 golden bytes.

## Task 2 — task contract, objective migration and Dataset target policy

**Modify:** `models.py:Project`, `schemas.py:ProjectCreate/ProjectResponse`,
`api/projects.py`, `services/datasets.py`, `services/source.py`,
`services/pipeline_state.py`, `pipeline_schemas.py` under `backend/src/mlstudio/`.
**Create:** `services/task_policies.py`, proposed
`backend/alembic/versions/0006_task_objectives.py`,
`backend/tests/test_task_targets.py`.

**Proposed interfaces:** `load_ir(payload: dict, objective: str)` returns a strict
legacy or regression intent; `validate_target_for_task(frame, column, task)`
returns task-specific facts without modifying source or labels. Existing
`target_classes` remains the binary policy, not a universal target validator.

- [ ] Test new task creation, existing task default, no in-place task conversion,
  numeric missing/constant/two-valued regression targets and invalid Boolean/object/
  infinity/precision-risk cases. Target selection must not require two unique values.
- [ ] Add strict regression IR with explicit task and target policy, existing feature
  operations and no positive class; unknown versions/unsupported structural fields fail.
- [ ] Implement and prove the objective constraint migration with Task 1 fixtures.
  Check `PRAGMA foreign_key_check`, ownership isolation, revision parity and schema/model
  parity on fresh and upgraded databases. Include interrupted migration failure tests.
- [ ] Keep source replacement's retained old binding/stale intent semantics; clear the
  new target context without silently binding an old recipe to a new source.

Targeted tests: `test_task_compatibility.py`, `test_task_targets.py`, existing
replacement/typed-target cases. Do not replace old binary assertions with broader ones.

## Task 3 — built-in model capabilities and contextual readiness

**Modify:** `pipeline_schemas.py`, `services/pipelines.py`,
`services/train_validation.py`, `codegen/compatibility.py`.
**Create:** `model_catalog.py`, `backend/tests/test_model_catalog.py`,
`backend/tests/test_regression_configuration.py`.

**Proposed interface:** `model_descriptor(model_id, task)` binds a typed parameter
schema/defaults, validation rules, matrix/missing-value capabilities, compiler adapter
ID/revision and safe UI metadata. Extend PipelineResponse with a compatible descriptor
surface or a small read-only catalogue response; do not add arbitrary import strings.

- [ ] Register all existing models first. Test identical defaults, accepted/rejected
  fields and resolved behavior; descriptor/model/renderer coverage is exhaustive.
- [ ] Add `linear_regression` and `ridge` for regression only. Fit/transform requirements
  produce explicit issues rather than silently adding a scaler or dropping a feature.
- [ ] Add regression split checks: existing 5–50% test fraction/seed bounds, no
  stratification, at least two usable training rows and one test row. Warn honestly
  that R2 may be unavailable; do not calculate a fake binary allocation.
- [ ] Persist incomplete intent and return readiness issues; never split/fit a feature
  matrix during configuration validation.

Targeted tests: catalogue/configuration plus existing `test_train_configuration.py`
and `test_pipelines.py` behavior relevant to legacy persistence and dormant intent.

## Task 4 — versioned regression compiler and result validation

**Keep unchanged:** v1 rendering/helper/golden behavior.
**Create proposed modules:** `codegen/v2/{schemas,plan,render,workload_runtime}.py`,
`execution/regression_results.py`, a small `codegen/dispatch.py` and
`backend/tests/{test_regression_codegen,test_regression_results}.py`.
**Modify callers:** `services/code_preview.py`, `execution/service.py`,
`execution/results.py`, coordinator dispatch points as needed; no second trainer.

**Proposed identities/interfaces:** regression IR/plan `0.2`, generator
`mlstudio-python-v2`, implementation `sklearn-local-v2`, result
`mlstudio-result-v2` with task `regression`. Retain `cli-v1` arguments and existing
process ownership because that CLI need not change. A pure
`generate_for_version(plan)` dispatches without falling back on unknown versions;
`validate_result_for_version(...)` chooses the frozen plan's result contract.

- [ ] Golden-test regression source separately, safe literals, deterministic bytes,
  source order, manifest Dataset binding and exact environment enforcement.
- [ ] Resolve all estimator choices explicitly. Suggested Ridge solver is deterministic
  `lsqr` for supported dense/sparse configurations, with explicit tolerance/iteration
  bound; validate the pinned sklearn behavior before freezing the new goldens.
- [ ] Generated code excludes only missing targets, splits before fitting learned
  preparation, predicts once, computes the agreed metrics and persists the complete
  preprocessing-plus-regressor artifact. Use the same verified source byte buffer.
- [ ] New result has Dataset/generator/versions/population, task, named regression
  metrics and availability reasons; no manufactured binary class fields. Reject
  wrong task/shape, invalid counts, nonfinite required losses and inconsistent RMSE.
- [ ] Test valid negative R2, true zero losses, constant/one-row test R2 unavailability,
  numeric overflow and malformed outputs. Do not claim losses independently verified
  from source rows without prediction evidence; structural consistency is not a
  full re-computation proof. Model/library fixtures verify workload calculations.

Targeted tests: new regression goldens/results, original six source goldens and
existing verified-buffer/literal tests. Shared parser behavior must remain unchanged.

## Task 5 — immutable admission, history and tracking integration

**Modify:** `execution/{service,coordinator,tracking}.py`,
`execution/schemas.py` and `api/runs.py` only where task dispatch is required.
**Create:** `backend/tests/test_regression_runs.py`.

**Interface:** keep RunRequest's revision/source/plan hashes and request identity.
Freeze task-specific summary/result with version information; old Run responses
remain readable. Separate tracking fields remain mutable; terminal facts do not.

- [ ] Execute both regressors through the actual persisted file; check byte/hash
  equality with reviewed preview and historical Code after later edits/replacement.
- [ ] Verify idempotent same request, stale admission, Dataset corruption, complete
  fitted artifact and failed finalization use the existing lifecycle correctly.
- [ ] Make tracking task-aware: no access to absent positive-class fields, record
  declared task/metrics, skip unavailable R2, keep failures separate from Run success.
- [ ] Read legacy successful/failed Runs without any new training dependency path;
  never regenerate their source or coerce result shapes into the regression protocol.

Reuse existing timeout/recovery/concurrency failure fixtures rather than recreate
expensive process simulations per estimator. Add new failure cases only at changed
task/result/summary boundaries.

## Task 6 — task-aware forms and historical evaluation

**Modify frontend files:** `lib/api/{projects,pipelines,runs,profiles,evaluation-policy}.ts`;
`components/{project-form,workspace,data-view,explore,prepare,train,run-results,evaluate,runs}.tsx`;
Code/readiness links if task wording changes.
**Tests:** extend `frontend/tests/{evaluation,run-views}.test.mjs` and fixtures;
add focused draft-navigation/task-form interaction coverage only as needed.

**Interfaces:** Project objective is authoritative for current creation/configuration;
frozen result/plan task is authoritative for history. Use discriminated known result
versions with an explicit unsupported-protocol state, not unchecked optional fields.

- [ ] Add explicit new-Project task choice and task-aware target form/Explore summary.
  Regression has numeric distribution rather than class bars/positive-class control.
- [ ] Render descriptor-driven model controls; keep current supported binary defaults.
  Protect dirty Train inputs before changing route/mode; no state-library rewrite.
- [ ] Share task-specific result/context components between Evaluate and Runs.
  Render R2 negative/null distinctly, metric units/context, and no binary matrix
  for regression. Preserve old 2x2 typed orientation and AUC reason behavior.
- [ ] Exactly-two comparison requires same task, target/source interpretation,
  frozen split/population/versions/metric definitions and integrity. Values remain
  visible when deltas are blocked; no cross-task winner or active-Dataset lookup.
- [ ] Preserve URL deep links, latest-success selection, paginated history and stale/
  missing/cross-Project states with mixed historical result versions.

Targeted commands: `npm.cmd run test`; then typecheck/lint/build for the integration
gate. Browser acceptance must use actual responses, not only SSR markup.

## Task 7 — documentation, final acceptance and release gate

After authorized implementation, update README, architecture/development/contributor
status, changelog and version metadata. Add approved versioned future contracts
without rewriting frozen v0.1 files, plus a synthetic regression Dataset/walkthrough.
State supported source distribution and platform limits; do not claim a stable
extension SDK or additional model families.

- [ ] Fresh source/editable Windows setup and fresh Alembic head.
- [ ] Upgrade disposable released-schema fixtures with replaced sources, incomplete/
  stale recipes, success/failure histories and tracking; compare bytes/metadata.
- [ ] Real UI binary demo still works; regression demo creates/configures/executes both
  models, inspects Code/Evaluate/history, compares two Runs and survives restart.
- [ ] Verify invalid targets, missing R2, stale revision, source integrity warnings
  and suppressed cross-task/compromised deltas; no lost Train draft on navigation.
- [ ] Backend full pytest, Ruff lint/format, pip check and wheel quality check;
  frontend npm ci/tests/typecheck/lint/build once at the final gate; diff/hygiene checks.
- [ ] Confirm required remote CI and tag/release identity manually before release.

Unknown historical versions must produce an inspectable unsupported state where
safe, not a crash or silent reinterpretation. Old evidence remains immutable even
when a new environment cannot rerun it. Runtime artifacts, user DBs and fitted
models must not enter the repository. These are release acceptance requirements,
not checks executed by this documentation-only audit.

## Handoff

Approve or revise the five proposed decisions before implementation. Address A1–A3
from the risk register within Tasks 1–5; A4 custom-code security is deliberately
outside v0.2. No implementation, staging, commit, push or tag is authorized here.
