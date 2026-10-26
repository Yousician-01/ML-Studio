# ML Studio v0.1.0 baseline audit

Audit dates: 2026-10-23–24; completed 2026-10-24. Evidence: local `release/v0.1.0` checkout at
`ae6f444bce47165ce7293d41584380bbc7cec629`. The `v0.1.0` tag resolves to commit
`aa3bc3e0bd874a07ec14055a3434cb361d539b7c`; `git diff v0.1.0 HEAD` shows no
tracked content differences. This describes the inspected tree, not an independently
verified remote release or the latest state of `main`.

## Method, authority and confidence

Read-only static inspection of application source, migrations, tests, manifests,
CI, documentation and the eight [frozen contracts](../specifications/project-v0.1.md).
Those contracts define v0.1; proposed later releases in this audit do not amend them.
Only the eight requested audit documents are being added. No application, test,
dependency, workflow or existing documentation edits are authorized by this audit.

**Verified here** means established from source or Git inspection. **Test-covered**
means relevant assertions exist; it does not mean the tests were executed here.
The earlier validation reported 471 backend and 28 frontend cases passing; those
are historical session results, not a fresh run or proof of remote CI status.
No tests, dependency installations, application launches or browser interaction
checks were performed for this audit. Visual appearance, keyboard interaction,
responsive layout and accessibility in a running browser are **NOT VERIFIED**.

The checkout began with a modified `frontend/next-env.d.ts` and an unrelated
untracked file named `-remote --tags origin v0.1.0`. Neither belongs to this audit;
both must be left untouched and excluded from its eventual commit.

## Factual capability inventory

Paths below are repository-relative. Test files are under `backend/tests/` unless
prefixed with `frontend/`. Partial means a deliberate limited implementation,
not necessarily a broken v0.1 contract.

| Capability | Actual implementation and boundaries | Principal evidence | Coverage inspected |
| --- | --- | --- | --- |
| Projects | Implemented create/list/read/edit/delete; required problem statement, optional success context; fixed binary objective; one active Dataset and one mutable recipe | `models.py:Project`, `schemas.py:ProjectCreate/ProjectPatch`, `api/projects.py`; frontend `project-form.tsx`, `projects.tsx` | `test_projects_datasets.py`, `test_project_deletion.py` |
| Source ingestion | Managed exact CSV bytes, generated UUID identity, SHA-256, staged publication; explicit replacement retains history | `services/datasets.py:ingest`, `services/artifacts.py:source_path/verified_source` | ingestion, traversal, limits, commit failure, replacement and concurrent edits in `test_projects_datasets.py` |
| CSV interpretation | UTF-8/BOM, comma/header/standard quoting; strict widths, unique headers, at least one row; pandas NA tokens; precision-risk integer reread; no encoding/dialect discovery | `codegen/csv_runtime.py:parse_csv_bytes`; numeric infinity rejection in `services/source.py:describe_columns` | `test_codegen.py:test_embedded_parser_parity`, malformed/precision fixtures; `test_source.py` |
| Dataset semantics | Physical dtype distinct from seven semantic types; deterministic `semantic-v2`; override/reset; metadata mutable, source immutable; exactly two non-null target classes | `services/source.py:infer_semantic/target_classes`, `services/datasets.py:configure`, `schemas.py` | `test_source.py`, `test_semantics_visual_eda.py`, typed class and override tests |
| Preview | First 20 parsed source rows; not a transformed preview; JSON-safe large-integer tagging | `services/source.py:PREVIEW_LIMIT/json_scalar`, `data-view.tsx` | preview and unsafe-integer tests in `test_projects_datasets.py` |
| Explore | Full-source descriptive EDA, distributions, missingness, duplicate/constant/near-constant/high-cardinality observations; source-order paging/filtering; Pearson feature correlation | `services/profiles.py:build_profile/read_profile`, `profile_schemas.py`, `explore.tsx`, `explore-charts.tsx` | `test_profiles.py`, `test_semantics_visual_eda.py`; no full browser suite |
| Preparation | Per-column inclusion; mean/median/most-frequent imputation where compatible; standard/min-max/robust scaling; one-hot; explicit operation order | `pipeline_schemas.py:Operation/FeatureIntent`, `services/pipelines.py:validate`, `prepare.tsx` | `test_pipelines.py`, `test_train_configuration.py`, codegen leakage tests |
| Feature engineering | Partial: preparation only. No derived-column expressions, text vectorizers, date extraction, selection learners, resampling or joins | Operation discriminated union and compiler whitelist | unsupported operation/semantic assertions |
| Models | Exactly Logistic Regression, Decision Tree Classifier, Random Forest Classifier; curated parameters, explicit defaults; sklearn 1.9.1 | `pipeline_schemas.py:ModelIntent`, `services/pipelines.py:response`, `codegen/plan.py:classifier`, `train.tsx` | `test_train_configuration.py`, all-three actual execution tests in `test_runs.py` |
| Split/target | One seeded random train/test split, optional binary stratification; positive class explicitly typed; only missing-target rows excluded | `services/train_validation.py`, `codegen/compatibility.py`, `workload_runtime.py` | split allocation, tiny populations, typed orientation and missing-target cases |
| Code generation | Pure deterministic LF Python from resolved plan; fixed imports/helper sources; read-only current preview; no fitting in preview | `codegen/schemas.py`, `plan.py`, `render.py:generate`, `services/code_preview.py` | six byte goldens, literal injection, hash order, parser parity, read-only preview tests in `test_codegen.py` |
| Execution | Exact persisted file launched via isolated Python flags and argument list; lifespan-owned thread/process; one workspace execution lease; timeout and bounded outputs | `execution/service.py:create`, `coordinator.py:Coordinator`, `process.py` | `test_runs.py`, `test_run_boundaries.py`, `test_run_results.py` |
| Run history | Frozen IR/plan/source/manifest/provenance; terminal fact guard; historical Code never regenerated; active Runs prevent deletion | `models.py:Run/protect_run_history`, `execution/service.py:response/historical_source`, `api/runs.py` | terminal immutability, idempotency, historical source and deletion tests |
| Evaluate | Accuracy/Precision/Recall/F1, conditional AUC with reason, typed 2x2 matrix, frozen context; deep-linked/paginated selection and latest successful default | `components/run-results.tsx`, `evaluate.tsx`, `lib/api/evaluation-policy.ts` | frontend `evaluation.test.mjs`, `run-views.test.mjs` |
| Comparison | Exactly two distinct successful Project Runs; fingerprint, source/target, typed orientation, split, versions including SciPy, population/support and metric protocol checks; no ranking | `compareContext/comparisonSelection/metricDelta` | matching/mismatching contexts, unavailable vs zero, integrity and duplicate selection |
| Tracking | Separate local MLflow client/store; stable association, failure isolation, startup reconciliation; selected config/result/source artifacts and model reference, not a second authoritative Run system | `execution/tracking.py`, migration `0005_tracking` | `test_tracking.py` including association-write failure, unavailable AUC and URI containment |
| Persistence | SQLite/SQLAlchemy/Alembic; projects/datasets/runs; JSON intent/evidence; filesystem source/model/results/logs; no automatic GC | `models.py`, `db/`, `alembic/versions/0001..0005`, `execution/artifacts.py` | migrations, foreign keys, rollback, crash/recovery/orphan cases |
| Contributor/release | Windows PR CI with frontend/backend checks; source/editable install only; wheel build is quality check; Apache-2.0 repository license | `.github/workflows/ci.yml`, manifests, README, CONTRIBUTING, SECURITY | workflow inspected; GitHub settings and run history unverified |

Backend paths in this table abbreviate `backend/src/mlstudio/`; component paths
abbreviate `frontend/src/components/`. See the [gap analysis](ARCHITECTURE_GAP_ANALYSIS.md)
for exact extension boundaries and the [frontend audit](FRONTEND_UX_AUDIT.md) for UX findings.

## What the stored Run actually proves

`execution/service.py:create` freezes IR, resolved plan, generated source, a manifest,
Dataset reference, versions and population counts before admission commits. `Coordinator`
launches that source and validates final result/model evidence before success. The
backend does not unpickle the model to establish success: it checks a bounded regular,
nonempty artifact and validates the structured result. Complete-pipeline behavior
is additionally exercised by model/library tests; a model hash alone is not a semantic
or safety proof.

The current `mlstudio-result-v1` result contains five scalar metrics, AUC availability
reason, typed negative/positive labels, a 2x2 matrix, source/eligible/training/test
counts, Dataset/generator/version identity and the model-output declaration.
It does **not** retain predictions, probabilities, per-row assignments, test row IDs,
ROC points, residuals, feature importance, loss curves or general metric records.
Counts and a seed do not independently prove identical held-out membership.

`service.source_integrity` verifies the manifest's historical source against the
frozen Project/Dataset ownership, source path, size and hash. Availability changes
response metadata, not SUCCEEDED/FAILED or retained SQLite metrics. Historical
integrity problems exclude comparison deltas. Current active Dataset edits are
not used to reconstruct Run evidence.

## Practical limits established from source

- `Settings`: 50 MiB CSV, 1,800-second workload timeout, 10 MiB per log, 1 MiB result,
  1 GiB model and 64 MiB disk reserve defaults. These are not RAM/CPU quotas.
- Explore returns 20 columns per page, 10 categories/bins and at most 12 correlation
  columns, but still parses the source and computes full-source facts server-side.
- Only continuous/categorical/binary features execute; detected text/date/identifier
  semantics must be excluded or deliberately reinterpreted. Detection is not support
  for NLP/date feature engineering.
- One run at a time per workspace; no queue, user cancellation, resume, distributed
  scheduler or GPU contract. Interrupted attempts fail closed, not resumed.
- Python/package versions are recorded and enforced, not recreated by a lock/environment
  manager. Retained evidence can be inspected without successfully retraining it.
- No authentication, untrusted-code sandbox, remote storage, hosted deployment,
  multiple active sources, serving, editable code or AI functionality is present.
- API TypeScript types are hand-maintained; there is no generated client, public
  extension SDK or stable plugin-loading contract.

## Architecture and product assessment

The system is a coherent binary-tabular prototype, not a generalized ML platform
with hidden task support. Its strongest reusable asset is the evidence pipeline.
Its main growth constraint is task-specific assumptions crossing validation,
compilation, result interpretation and UI. Preserve the evidence pipeline and
extend versioned task contracts incrementally. Do not rewrite the executor simply
to add a regression estimator.

Existing documentation permits focused Markdown documentation under `docs/` and
asks contributors not to duplicate authority. These audit documents are proposals
and evidence indexes, not replacement frozen specifications or approved scope.
