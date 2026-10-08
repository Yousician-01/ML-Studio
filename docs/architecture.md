# Architecture — Prototype v0.1

**Status:** implemented through Phase 6: local execution, immutable Run history,
and separate local MLflow tracking. Evaluate and AI remain unimplemented.
[ADR 0001](decisions/0001-use-pipeline-ir.md)
establishes Pipeline IR, and the [v0.1 specifications](specifications/project-v0.1.md)
define the current contracts. Prefer the smallest local application that
validates the [prototype](prototype.md), without speculative services.

## Domain and execution flow

```text
Project
├── active Dataset (zero or one)
├── mutable Working Pipeline IR
└── historical Runs

Dataset + Working Pipeline IR
        ↓
Validator
        ↓
Effective Execution Plan
        ↓
Code Generator
        ↓
Exact Generated Python Artifact
        ↓
Local Subprocess Executor
        ↓
Structured Results + Fitted Model + Logs
        ↓
Run Finalization
        ↓
ML Studio Persistence + separate MLflow Tracking
```

The Working Pipeline IR is canonical editable experiment intent. It may be
incomplete, invalid, or stale after Dataset changes. Validation resolves
execution readiness against the immutable Dataset and semantic context; it does
not silently rewrite intent. The effective plan contains resolved operations,
classes, split settings, and model parameters for the workload. The generator
renders that plan as human-readable Python using mature public ML libraries.

**Generated Python is the actual data-science workload.** The executor launches
the exact source frozen for the Run; it does not independently rebuild and fit a
second sklearn pipeline. Generated code loads the Dataset, excludes only missing
target rows, splits before fitting preprocessing, constructs the complete
preprocessing-plus-classifier pipeline, fits on training data, evaluates held-out
data, and emits a structured result and fitted model. No learned transform uses
held-out data to fit. Current Working Pipeline Code is a preview; historical Code
reads the persisted source attempted for that Run, never a new rendering.

The ML Studio orchestrator owns process launch, Run lifecycle, stdout/stderr
capture, result validation, artifact finalization, persistence coordination,
and MLflow synchronization. Validation/generation failure before the frozen
package exists creates no Run. Once a Run is created, launch or workload failure
is recorded as FAILED. A successful Run requires valid local results and
artifacts; MLflow failure alone does not make it fail.

## Local persistence and tracking

```text
Domain metadata and current state  → SQLite through SQLAlchemy
Schema evolution                   → Alembic
Source Datasets and Run artifacts  → managed local filesystem
Complete fitted model             → joblib
Experiment tracking               → local MLflow
```

A configurable ML Studio workspace root groups the SQLite database, Project
artifacts, and local MLflow storage outside the source repository by default.
Stable Project, Dataset, and Run IDs establish identity; paths locate bytes. A
Project has at most one active Dataset, while retained Runs keep references to
their original immutable sources. A Run freezes configured IR, effective plan,
semantic context, exact generated source, and relevant provenance before its
workload begins. The generated source artifact is the file the executor attempts
to run. Model and result artifacts are validated and finalized before SUCCEEDED.

ML Studio's database is authoritative for Projects, Runs, lifecycle, and artifact
references. MLflow tracks parameters, metrics, provenance, and artifacts as a
separate integration; Projects and Runs are not reconstructed by crawling it.
Tracking state can be repaired without rewriting historical experiment facts.
SQLAlchemy and normal transaction discipline avoid needless SQLite coupling so
PostgreSQL remains a future hosted/multi-user migration path, not a v0.1
dependency. No remote MLflow, cloud storage, Docker, Redis, or distributed queue
is required by this architecture.

## Product boundaries and later AI

The v0.1 task is binary classification on CSV with a single train/test split,
three curated classifiers, and a narrow preprocessing vocabulary. Data, Explore,
Prepare, Train, and Evaluate form the user workspace; Runs and Code support
inspection. Arbitrary user Python, reverse parsing, regression, multiclass,
XGBoost, HPO, deployment, and multi-user execution are outside v0.1.

The broader AI Advisor may later consume structured Project, Dataset, Pipeline,
validation, and Run facts to explain suggestions. It is not in the first
deterministic implementation slice and cannot silently edit state or override
validation. Core execution works without AI. Source rows and secrets are not
ordinary logging or AI-context material.

Local workloads inherit their runtime permissions; no sandbox or secure
multi-tenant isolation is promised. See [Security](../SECURITY.md). Concrete
framework selection, setup commands, and test tooling belong to implementation,
not to this architecture summary.
