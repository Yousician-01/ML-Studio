# Persistence — Prototype v0.1

## Purpose, authority, and scope

This is the final pre-implementation specification for durable Project state, Dataset metadata and source artifacts, mutable Working Pipeline IR, immutable Run evidence, execution outputs, and MLflow associations. It refines the current [Project](project-v0.1.md), [Dataset](dataset-v0.1.md), [User Journey](user-journey-v0.1.md), [Pipeline IR](pipeline-ir-v0.1.md), [Run](run-v0.1.md), [Execution](execution-v0.1.md), and [Code Generation](code-generation-v0.1.md) contracts. These specifications govern domain behavior when older planning documents differ.

```text
Project → mutable current workspace state
        → immutable historical Runs and their referenced Dataset artifacts
```

ML Studio owns Project, Dataset, Working Pipeline, Run identity/lifecycle, snapshots, artifact references, and success/failure truth. SQLite stores their structured metadata. The managed filesystem stores artifact bytes. MLflow is supporting experiment tracking, not ML Studio's domain database: Projects and Runs must never be reconstructed by crawling MLflow.

## Frozen storage architecture and workspace

Prototype v0.1 uses **SQLite through SQLAlchemy**, **Alembic** migrations, a **local managed filesystem** for artifacts, **joblib** for complete fitted inference pipelines, and **local MLflow**. PostgreSQL is a future migration possibility, not a v0.1 runtime dependency. SQLite is an implementation choice, never domain identity.

A single ML Studio workspace root owns runtime state. Its OS-specific default may be chosen during implementation and should be configurable; no absolute platform path is part of this contract. The source repository is not the normal runtime workspace.

```text
ML_STUDIO_HOME/
├── mlstudio.db
├── projects/
│   └── <project_id>/
│       ├── datasets/
│       │   └── <dataset_id>/
│       │       └── source.csv
│       └── runs/
│           └── <run_id>/
│               ├── generated_run.py
│               ├── pipeline_ir.json
│               ├── execution_plan.json
│               ├── result.json
│               ├── model.joblib
│               ├── stdout.log
│               └── stderr.log
└── mlflow/
```

This is the v0.1 final-artifact layout. Per-Run temporary files/areas may be added for safe writes. These names are storage conventions, not identity or an API for callers to infer artifacts. ML Studio resolves recorded artifact references against the configured root. Users need not manually edit workspace contents. Test fixtures may reside in the source tree, but ordinary uploaded data, Runs, models, and MLflow state do not.

## IDs, timestamps, references, and database boundary

Stable generated Project, Dataset, and Run IDs identify entities; artifact records receive stable IDs where useful. Names, original filenames, paths, and MLflow IDs do not substitute for ML Studio IDs. A Run also has its Project-local sequence number for display and historical ordering; it must not be silently reused after deletion. ID format and allocation details remain implementation choices. Store timestamps in an unambiguous UTC representation, preserving absent execution-start or terminal timestamps when those events have not occurred.

An artifact reference records at least kind, owner (Project, Dataset, or Run as applicable), relative workspace location, and creation metadata; size and checksum are useful integrity metadata. Validate that resolved locations remain inside the managed workspace and correct owner's area. A path locates bytes; the reference and entity IDs establish the historical association. An external upload path is never a durable Dataset reference. Do not duplicate arbitrary large artifacts into SQLite.

Domain/application services use focused persistence repositories or services backed by SQLAlchemy. Keep normal domain code free of raw SQLite-specific SQL and avoid SQLite-only schema types or implicit SQLite behavior where reasonable. Use ordinary transactions, uniqueness and referential constraints, and explicit lifecycle updates. This is not a speculative generic database framework and does not require PostgreSQL infrastructure, Docker, credentials, or multi-user support. Use Alembic versioned migrations from the first implemented schema; deleting and recreating a user's database is not a schema-evolution policy.

## Structured domain state

**Project metadata** persists ID, name, optional description, required problem statement, ML objective (including the v0.1 task and current target context), creation and updated timestamps, at most one active Dataset reference, canonical current Working Pipeline IR, and any current-state/version metadata needed for safe edits. Project `updated` reflects persisted changes to Project-owned current state, not mere viewing; Run lifecycle timestamps remain Run facts. Run metrics and artifacts are not Project fields.

**Dataset metadata** persists Dataset ID, owning Project, original filename, CSV format, content fingerprint, upload/attachment timestamp, managed source reference, inferred/physical schema, semantic interpretation and overrides, and current versus historical association needed for replacement. Do not store raw CSV bytes or preview rows in SQLite. Target and feature/exclusion decisions must have one authoritative persisted location, with Dataset column roles exposed as a consistent view rather than a competing editable copy: Project ML Objective holds the current selected target, Working Pipeline IR holds explicit feature participation and target execution intent, and Dataset metadata holds source interpretation/semantic overrides. Changes reconcile these views under the Dataset and IR contracts. A stale or incomplete Working Pipeline can be saved but cannot execute until validated.

**Run metadata** persists globally stable Run ID, owner Project, Project-local sequence, lifecycle state, relevant creation/start/terminal times, frozen Dataset ID/fingerprint and source association, frozen configured IR and resolved semantic/execution context, exact generated-code reference, effective-plan reference, result/model/log references when available, failure evidence, execution provenance, and separately repairable MLflow Run association and synchronization state. The canonical current Working Pipeline and the frozen Run snapshot are distinct. Snapshot state must not be read through mutable current Project or Dataset records to reconstruct historical truth. Frozen IR includes excluded features and dormant operations; the effective plan describes only what actually enters execution. The plan is historical evidence, not a second editable IR.

Current Working Pipeline persistence accepts incomplete, invalid, or replacement-stale canonical IR. Saving it does not assert readiness or create a Run. Source schema and semantic overrides remain Dataset concerns rather than duplicated IR fields. Selected target and role views remain consistent when valid, while temporary stale state is represented honestly and revalidated before execution.

## Managed Dataset artifact and replacement

On accepted CSV ingestion, copy the source into the managed `projects/<project_id>/datasets/<dataset_id>/source.csv` location, establish the deterministic content fingerprint of the immutable uploaded contents, and associate metadata with that managed artifact. The external user-selected file can later move or disappear without changing Dataset identity. Acceptance must not publish metadata that points to a missing/incomplete copy. The source artifact is immutable after acceptance; preprocessing never overwrites it.

Replacing an active Dataset creates a **new Dataset ID and managed source artifact** and updates the Project's active reference. The previous Dataset metadata/artifact remain available while any retained Run references them, even when the Project now uses Dataset B. Replacement reconciles target, overrides, and Working Pipeline as required by Dataset v0.1; matching column names alone do not validate old intent. No in-place source overwrite, automatic historical redirect, or sophisticated garbage collection occurs. Prefer conservative retention over breaking historical Runs.

## Frozen Run package and exact source

Train follows the existing pre-creation boundary:

```text
validate Working Pipeline and Dataset
→ resolve effective execution plan and semantic context
→ generate Python
→ prepare, validate, and freeze source + required inputs/snapshots
→ create Run
→ attempt to launch that exact persisted Python file
```

The Run ID may be allocated to name an isolated staging/final directory before the Run record exists; ID allocation or temporary files alone do not create a domain Run. Only after the required frozen package exists and is ready for an execution attempt is the Run created. A failure during validation, plan resolution, code generation, or required pre-Run package preparation creates **no Run**. Staging remnants may be cleaned up or diagnosed but are not historical Runs. Once created, a launch failure is a FAILED Run, with no invented execution-start timestamp.

For each Run, persist canonical, deterministically serialized `pipeline_ir.json` and `execution_plan.json`, the frozen execution-relevant semantic context, exact Dataset ID/fingerprint/source reference, and `generated_run.py`. JSON snapshot artifacts are inspectable historical evidence; important searchable fields/references may also be in SQLite. Serialization must preserve typed positive-class meaning, explicit resolved settings, and configured excluded-feature state. Historical interpretation cannot require rerunning today's plan resolver or reading today's Dataset overrides. The frozen package records relevant ML Studio/code-generator, Python, pandas, scikit-learn, joblib, and execution implementation/version provenance as applicable; it does not promise a fully recreated environment.

The persisted `generated_run.py` is **the file the executor attempts to execute**. Do not persist source A and execute regenerated source B. Historical Code reads this artifact, even if the Run later fails. Missing historical source is reported as missing, never silently regenerated and presented as the original. The execution environment supplies runtime Dataset and output locations without making those paths domain identity.

## Workload outputs, joblib model, and diagnostics

The generated workload writes machine-readable `result.json` independently of stdout/stderr. It communicates required core metrics, conditional ROC-AUC or its unavailability reason, ordered 2×2 Confusion Matrix, workload outcome, and relevant output reference(s) under the Execution contract. The orchestrator validates schema, consistency, process outcome, and required artifacts before marking a Run SUCCEEDED. Exit code zero without a valid required result and complete fitted model is insufficient. Partial result data on a FAILED Run is diagnostic, not finalized evaluation.

Serialize the **complete fitted sklearn preprocessing-plus-classifier `Pipeline`** as `model.joblib`; a bare classifier is insufficient. Record the relevant Python/scikit-learn/joblib versions. A joblib artifact is not promised to load under arbitrary future dependency versions. **joblib/pickle-style model artifacts must be treated as trusted local ML Studio artifacts and must not be loaded from untrusted external sources.** v0.1 provides no secure portable model-exchange format or arbitrary external model import.

Capture `stdout.log` and `stderr.log` separately as diagnostics. Their text is not the canonical result protocol, nor is it authoritative for metrics, artifact identity, or Run status. Failed Runs retain their frozen package and available logs/failure metadata; partial model or result outputs are marked non-authoritative and never promoted to successful artifacts. Avoid intentionally writing raw Dataset rows, secrets, or credentials to logs, generated comments, failure messages, SQLite metadata, or MLflow tags. Raw Dataset contents belong in the managed source artifact. Normal local-user filesystem permissions apply; no encryption-at-rest claim is made.

## Atomic finalization, integrity, and recovery

An artifact becomes authoritative only after a completed write, validation, and finalization. Use a temporary-write → validate → atomic rename/replace pattern where practical, especially for `result.json`, `model.joblib`, and pre-Run generated source/snapshots. Temporary/in-progress output is distinguishable from final historical output in the per-Run area. Finalization must ensure the executor's `generated_run.py` has the same bytes as the frozen artifact; a late rewrite cannot change what the Run means.

SQLite cannot atomically commit arbitrary filesystem writes. Use an ordered, recoverable protocol: prepare artifact bytes, validate them, finalize them, persist their references, and only then finalize the Run state. Transactions protect database state, but they do not pretend to cover filesystem renames. A Run cannot become SUCCEEDED while any required local artifact is missing, invalid, or unreferenced. If finalization fails after creation, record FAILED with available evidence. No full transactional filesystem or complex recovery engine is required.

Store and verify useful integrity metadata for immutable source Dataset, exact generated source, fitted model, and structured result. The Dataset content fingerprint remains the single fingerprint for its exact uploaded bytes; an artifact checksum may use that same content identity and must not invent a competing Dataset identity. Hashing every log is unnecessary. If a referenced historical artifact is absent or fails integrity verification, surface it as missing/corrupt, preserve metadata, and do not reconstruct it from current state or mark a Run successful. Historical source especially must not be regenerated as a substitute.

An interrupted Run left CREATED or RUNNING after application/process interruption needs a diagnosable state and available staging/log evidence. Startup inspection may identify such Runs; it must not silently mark them SUCCEEDED. The precise recovery policy can be implemented as needed without adding a new core Run state. No queued, interrupted, or retrying state is introduced; terminal FAILED Runs are not restarted under the same identity.

## Historical immutability and deletion

After terminal completion, frozen IR, effective plan, generated source, Dataset identity, model/result artifacts, metrics, terminal outcome, and historical timestamps are immutable. During execution, lifecycle observations and outputs can be added according to Run v0.1; this is not a license to rewrite frozen inputs. If an artifact becomes unavailable later, record/report availability separately rather than altering historical experiment facts. Explicit deletion, if ever exposed, is distinct from rewriting a retained Run.

Prototype v0.1 need not expose Project or Run deletion in the user journey. Destructive lifecycle details are deferred; do not introduce speculative cascades, garbage collection, or storage quotas. If Project deletion is implemented, it follows Project v0.1's conceptual removal of Project-owned state and resources, while never deleting a source artifact still needed by a retained Run. Run sequence numbers are not reused. An original user-owned upload outside the managed workspace is never deleted by this policy. Backups, archive/export/import, and sync are outside v0.1.

## Local MLflow association and failure isolation

MLflow uses local storage under or associated with `ML_STUDIO_HOME/mlflow/`; exact backend and artifact URIs are implementation choices. No remote MLflow server or cloud object store is required. Maintain an explicit ML Studio Run ID ↔ MLflow Run ID association when an MLflow identity exists. These are distinct IDs. MLflow can receive parameters, metrics, provenance, and model/artifact copies or references, but ML Studio remains the source of domain truth. Required generated source, snapshots, structured results, and fitted model remain resolvable through ML Studio's own persistence; MLflow is never their only copy.

MLflow failure, partial synchronization, or absence of an MLflow Run ID does not change an otherwise complete local Run from SUCCEEDED to FAILED. Keep tracking/synchronization status and failure information separate from core Run status. Tracking state may later be repaired, including establishment of an external ID, without changing immutable experiment facts. Conversely, successful MLflow logging cannot repair missing local required evidence or turn a FAILED Run into SUCCEEDED.

## Persistence invariants

1. SQLite holds structured domain metadata/state; normal application access uses SQLAlchemy, and Alembic manages schema evolution.
2. Raw CSV bytes and other large immutable artifacts live on the managed filesystem, not in SQLite.
3. SQLite is not domain identity; stable IDs identify entities, and filenames/paths only locate bytes.
4. External upload paths are not durable Dataset references; ML Studio keeps its own immutable managed source copy.
5. Dataset replacement never overwrites an artifact required by a retained historical Run; such sources are retained.
6. The current Working Pipeline IR is mutable persisted state and may be incomplete or invalid.
7. Frozen Run snapshots preserve configured IR, resolved context and effective plan independently of mutable Project state.
8. Exact generated source is frozen before Run creation; that persisted file is the file the executor attempts to launch.
9. Historical generated source is never regenerated and presented as original evidence.
10. Structured results are independent of stdout/stderr; required outputs are validated before SUCCEEDED.
11. The fitted inference artifact contains preprocessing and classifier together and is serialized with joblib.
12. Untrusted external joblib/pickle artifacts are not loaded as trusted ML Studio models.
13. Important artifacts use temporary-write, validation, and atomic finalization where practical.
14. No Run becomes SUCCEEDED with missing, corrupt, partial, or unreferenced required artifacts.
15. Missing/corrupt historical artifacts are surfaced, not silently recreated or substituted.
16. Terminal experiment facts and artifact associations are immutable; FAILED Runs may retain diagnostics without promoting partial outputs.
17. MLflow is tracking, not ML Studio's domain database; its Run ID is distinct from ML Studio's.
18. MLflow failure alone does not invalidate an otherwise successful local Run; required historical artifacts do not exist solely in MLflow.
19. Runtime workspace data lives outside the source repository by default, and raw rows are not casually duplicated into metadata/logging.
20. Persistence remains reasonably portable to future PostgreSQL use without requiring PostgreSQL, Docker, cloud storage, or a remote MLflow server in v0.1.

## Non-normative churn lifecycle

For the established churn Project, creation writes a Project record in SQLite. Uploading `customers.csv` copies it to the managed Dataset area, fingerprints its exact bytes, then records its Dataset metadata and active Project association. Target selection and preprocessing edits save the current Working Pipeline IR, even before it is ready to train. On Train, validation resolves the effective plan, the generator produces Python, the IR/plan/source and Dataset association are frozen, and only then is Run 001 created. The executor launches that exact `generated_run.py`, captures separate logs, finalizes and validates `model.joblib` and `result.json`, finalizes the Run's local outcome, and coordinates separate MLflow synchronization.

If a later `customers-new.csv` upload becomes Dataset B, it receives a new ID/source artifact and becomes the Project's active Dataset. Dataset A remains stored because Run 001 refers to it. The current Working Pipeline can be reconciled and changed for Dataset B without changing Run 001's Dataset fingerprint, snapshots, source, model, metrics, or historical Code.

## Explicit exclusions and remaining questions

Persistence v0.1 excludes PostgreSQL/MySQL runtime support, Redis or distributed databases, S3/cloud/remote artifact stores, a remote MLflow requirement, Docker/Kubernetes requirements, multi-user persistence, authentication/RBAC/collaboration, Project sync, cloud backup, export/import, artifact garbage collection, sophisticated quotas, application encryption-at-rest, arbitrary external model import, model registry semantics, and production deployment storage.

No blocking Persistence v0.1 questions remain. Exact SQL table/ORM names, migration filenames, OS-specific default root, MLflow backend URI, checksum algorithm, and temporary filename convention are implementation choices constrained by this contract. Implementation can settle them without another domain specification. Older [prototype scope](../prototype.md) and [roadmap](../../ROADMAP.md) plan a broader classification/regression/XGBoost surface, while current v0.1 specifications support binary classification and three classifiers. The older [architecture](../architecture.md) diagrams execution and generated Python as parallel consumers of IR; current Run/Execution/Code Generation contracts make persisted generated Python the actual workload. Those planning files remain unchanged.

## Implementation handoff

The v0.1 domain and persistence contracts are now frozen enough to begin implementation without another domain specification. Implementation findings may reveal defects requiring a targeted specification revision, but speculative design documentation should not delay coding. Begin with a thin end-to-end slice:

```text
Create Project → Upload CSV → Select target → Configure preprocessing
→ Select Logistic Regression → Generate Python → Execute that Python
→ Persist Run → Show metrics → Show exact executed code
```
