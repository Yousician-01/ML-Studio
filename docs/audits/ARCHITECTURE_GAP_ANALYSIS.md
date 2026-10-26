# Architecture gap analysis and risk register

Date: 2026-10-24. Baseline, confidence and audit restrictions:
[baseline audit](V0_1_BASELINE_AUDIT.md). All future interfaces below are proposals.

Backend module references such as `models.py`, `services/` and `execution/` are
relative to `backend/src/mlstudio/`; frontend modules are relative to
`frontend/src/`. Migration and test paths are repository-relative as shown.

## Architecture to preserve

```text
Project current state + managed source
  -> typed editable Pipeline IR
  -> contextual validation
  -> resolved execution plan
  -> deterministic generated Python
  -> immutable execution package
  -> exact-source subprocess
  -> task-specific result validation + artifact finalization
  -> historical Run response
  -> Evaluate / Runs / Code / separate MLflow synchronization
```

This separation is real in `services/pipelines.py`, `codegen/plan.py`, `render.py`,
`execution/service.py`, `coordinator.py`, `results.py` and `tracking.py`. It is not
necessary to replace FastAPI, SQLAlchemy, SQLite, React state or the local process
coordinator to introduce another supervised task.

## Task extension map

| Family | Present barrier | Minimum extension, not a rewrite |
| --- | --- | --- |
| Binary | Already complete within frozen scope | Preserve v1 paths and exact output behavior |
| Multiclass | Two classes in Data/Prepare/compatibility/training validation; one positive class; fixed matrix/metrics/UI | Class vocabulary and averaging/AUC contracts, general matrix and result type, task-specific split checks and forms |
| Regression | DB objective check; binary target selection, class allocation and `[0,1]` metric validation | Numeric target policy, non-stratified split, regression results/metrics/UI, objective migration and versioned compiler |
| Clustering | Target mandatory for readiness/eligibility; executor expects held-out supervised evidence | Target-free task and population protocol, fit/assignment policy, cluster/noise evidence and task evaluator |
| Dimensionality reduction | Only feature-local operations and final classifier; no learned cross-column stage | Explicit multivariate transformer stage, fit scope and projection evidence; distinguish transform from experiment task |
| Text classification | Text recognized but blocked as included feature; 2D tabular per-column selectors | Text branch with 1D input, train-only vocabulary, sparse-aware composition and bounded text input semantics |
| Neural networks | No epoch/checkpoint/device protocol | sklearn MLP fits supervised path first; PyTorch needs a separate workload adapter and new evidence contracts, not a new scheduler by default |

Important: the sparse limitation is **not** that all current matrices are dense.
`plan.operation` uses `OneHotEncoder(sparse_output=True)` and
`ImplementationContract.sparse_threshold=1.0`. Mixed branch shapes, centering,
estimator requirements and vocabulary bounds still need explicit capabilities.

## Existing model abstractions and recommended extension

Current registrations are a closed Pydantic union in `pipeline_schemas.py:ModelIntent`;
defaults in `LogisticParameters/TreeParameters/ForestParameters`; response choices in
`services/pipelines.py:response`; range checks in `train_validation.py:train_issues`;
resolved constructors in `codegen/plan.py:classifier`; import whitelist in
`codegen/render.py:IMPORTS`; frontend labels/parameter presentation in `train.tsx`
and TypeScript unions in `lib/api/pipelines.ts`.

Extend these into a small built-in catalogue, not dynamic plugin discovery. A
proposed `ModelCapability` record should bind an algorithm ID and adapter revision,
supported tasks, existing parameter schema/defaults, contextual constraints, input
matrix capabilities, missing-value policy, preprocessing requirements, prediction/
score capabilities, applicable evaluation protocol, compiler adapter ID and UI
labels/help. Keep library class imports and arbitrary executable objects out of
persisted user intent. Algorithm adapter revision and installed package version
are different facts; freeze both when materializing a new plan.

Generate a read-only UI descriptor from validated backend entries. Runtime
validation remains Python's responsibility; frontend types/rendering should consume
a constrained descriptor, not execute arbitrary JSON-schema extensions. Do not
derive silent learned preprocessing from a model's requirements: show an issue
and require a user choice. Start by registering the existing three models and
proving unchanged v1 goldens, then add two regressors.

## Pipeline representation: smallest viable migration

The current IR is a feature-branch recipe, not a DAG: `features[name].operations`
feeds a single model and split. It is suitable as the shared semantic authority
for forms and a **bounded** Visual editor. A layout/selection canvas is separate
UI metadata, never another executable graph. Position changes must not change
generated source hashes. See [three modes](THREE_MODE_ARCHITECTURE.md).

Add a new versioned task envelope for future tasks; do not make `ir_version: "0.1"`
silently mean regression. Legacy readers/compiler behavior must remain available.
For a later true DAG, introduce typed node/port IDs and an explicit lossless recipe
adapter only when branching or cross-column operations require it. Reject an
unsupported graph instead of dropping nodes while returning to No-Code.

## Execution invariants and limitations

`WorkspaceLease` combines OS locking with the coordinator's thread guard; admission
checks revision and expected source/plan hashes; request identity is unique per
Project. The process runs `sys.executable -I -B -u -X utf8` with `shell=False`, an
allowlisted environment, bounded stream draining and an identity-checked cleanup.
Recovery journals exact arguments and PID creation time, fails uncertain attempts,
and quarantines recoverable unreferenced published packages. SQLite and filesystem
publication are sequenced, not a single atomic transaction. Preserve this protocol.

No cancellation endpoint/state or automatic resumption exists. The model is valid
for short trusted-local sklearn experiments; GPU workers, arbitrary descendants,
interactive terminals and potentially hung training callbacks need their own
ownership/termination acceptance tests. Subprocess isolation is not a sandbox.

`protect_run_history` guards ORM writes, not an adversarial operator with SQLite
or filesystem access. Hashes detect byte changes relative to retained metadata;
they are not signed authenticity or encryption. Do not market them as such.

## Risk register

P0 = critical current blocker. P1 = prerequisite before the dependent expansion.
P2 = important but deferrable. P3 = optional. **No confirmed current P0 defect was
established by this static audit.** P1 items below are confirmed extension barriers,
not claims that binary v0.1 is broken. S/M/L/XL denote relative engineering effort
including tests/docs; no delivery dates are implied.

| ID / priority / kind | Evidence and mechanism | Impact / affected feature | Resolution / effort / dependency |
| --- | --- | --- | --- |
| A1 P1 extension barrier | `models.py:Project` and migration `0002` enforce `ml_objective = 'binary_classification'`; `target_classes`, `train_issues`, `TargetPlan` require two classes | Regression/unsupervised cannot be enabled safely with UI flags | Task contracts and tested objective migration; L; product task decision |
| A2 P1 extension barrier | `execution/results.py:validate_result` demands exact v1 keys, 2x2 counts and metrics in `[0,1]`; frontend `RunResult` mirrors it | Negative R2, regression losses and clustering results would be rejected or misrendered | Version-dispatched result validation/views/comparison; L; A1 |
| A3 P1 compatibility prerequisite | `PipelineIR` and plan use Literal `0.1`; generator/helper bytes and six goldens encode v1 behavior; JSON stored directly | Widening existing unions or editing shared templates can silently reinterpret old configurations | Explicit legacy reader/compiler path and v2 dispatch; L; before any new task |
| A4 P1 security prerequisite | `process.environment/launch`, SECURITY: no sandbox/auth; logs capture raw process streams | Editable arbitrary Python can read files/network, spawn descendants and produce private output | Explicit trusted-local consent, source lineage/hash, custom result/artifact trust boundary and process tests before Code execution; XL; code-authority decision |
| A5 P2 confirmed coupling | Model schema/default/validation/compiler/import/UI definitions spread across seven sites | Drift as algorithm catalogue grows | Built-in capability descriptors using existing Pydantic schemas; M; v0.2 groundwork |
| A6 P2 confirmed cost, scale risk | `api/runs.py:list_runs` calls `service.response` for each row; it rehashes sources and every artifact, potentially 1 GiB models | Many large Runs / Evaluate latest scan can be expensive | Measure with representative history; then explicit verification freshness/batching policy; M; no silent trust cache |
| A7 P2 security/resource limitation | CSV byte limit and timeout are present; no process RAM cap; no model parameter upper bounds in `train_issues`; EDA parses full source | High-cardinality encoding/large forests/NLP can exhaust memory | Conservative task-specific size/cardinality/work bounds and documented failure behavior; M; before text/deep workloads |
| A8 P2 reproducibility limitation | `library_versions` and runtime verify versions; broad Python/dependency ranges, no backend environment lock | Drift is detected but old environment is not recreated; old models may not load after upgrades | Retain provenance, document restore path and capture tested constraints; M; before broad dependency upgrades |
| A9 P2 local-writer race risk | `verified_source` hashes then `parse_source` reopens in Data/Explore; generated workload instead hashes/parses same byte buffer | Concurrent external file mutation can make an interactive profile differ from verified bytes | Document trusted storage; reuse bounded verified-buffer loading if reproducible race matters; S/M; not a confirmed observed failure |
| A10 P2 confirmed evidence gap | v1 result keeps counts/matrix/AUC only, no prediction scores or row membership | ROC/residual plots and stronger comparisons cannot be reconstructed from metrics | New opt-in versioned immutable evidence, bounded and privacy-reviewed; M/L; task/result contract |
| A11 P2 confirmed UX/state limits | `Train.ConfigurationForm` temporary edits discarded on unmount; duplicated view-local loading/conflict logic | Mode switches / growing forms can lose drafts or repeat stale UI patterns | Navigation guard and draft policy, then small shared resource hooks; M; before multi-mode editing |
| A12 P2 confirmed documentation drift | `docs/architecture.md` opening says Evaluate unimplemented; CHANGELOG says no published releases while local tag exists | Contributors may design from obsolete phase descriptions | Correct authority/status references in a later authorized docs change; S; remote publication still unverified |
| A13 P2 external verification gap | Contributor docs recommend rulesets/private reports; source cannot prove GitHub settings or release assets | Adoption/security reporting expectations may not hold | Maintainer verifies branch checks, reporting channel and release/tag state; S; account access |
| A14 P2 confirmed API constraint | Metadata PATCH has no client revision field; ORM revision catches overlapping DB writes only, unlike Pipeline/Dataset PATCH | Sequential stale settings form can overwrite newer metadata | Add explicit optional/required revision policy in a versioned API change; S/M; client compatibility |
| A15 P3 maintainability | Monolithic global CSS and dense view components; hand-maintained TS/API contracts | More tasks/modes multiply edits and drift | Extract only as features require; shared descriptors and contract fixtures first; M; no state-framework rewrite |

## Storage migration gates

Current schema has cyclic Project/active-Dataset ownership plus Run composite
ownership constraints. Migration `0003` already transforms a legacy role field
into JSON; `0004/0005` add Runs/tracking. Changing the Project objective check on
SQLite is a table-rebuild problem, not a string replacement. Validate a migration
on disposable copies with active sources, replacements, incomplete and stale IR,
successful/failed Runs and tracking links. Preserve UUIDs, revisions, sequence
allocation, all Run JSON/artifact hashes and foreign-key integrity. Never update
historical JSON just to satisfy the newest Pydantic model.

## No architectural rewrite is warranted

Reject a universal graph engine, plugin marketplace, generic repository layer,
distributed scheduler or environment manager as a prerequisite for two regressors.
Use explicit task policies and small versioned adapters. Make cancellation,
prediction evidence and optional libraries separately releasable when needed.
