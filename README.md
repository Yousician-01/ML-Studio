# ML Studio

**Visual ML. Real code. Reproducible experiments.**

ML Studio **0.1.0** is an open-source, local-first binary-classification prototype.
Create a prediction problem, inspect a CSV, configure explicit preprocessing and
a model, execute the generated Python, and review immutable experiment evidence.

> Start visually. Understand everything. Drop into code whenever you need.
> Never lose reproducibility.

## What is implemented

| Workspace | Existing v0.1 capability |
| --- | --- |
| Projects | Create, edit, open, and explicitly delete local Projects |
| Data | One active managed CSV, source preview, physical/semantic types, overrides, binary target, and explicit replacement |
| Explore | Deterministic source summaries, distributions, missingness, quality observations, and correlation |
| Prepare | Explicit positive class, feature inclusion/exclusion, compatible imputation, scaling, and one-hot encoding |
| Train | Logistic Regression, Decision Tree, or Random Forest; curated parameters; one reproducible train/test split; actual local execution |
| Evaluate | Frozen Run metrics and confusion matrix; conditional ROC-AUC; exactly-two comparison with context/integrity warnings |
| Runs | Immutable attempts, frozen configuration, provenance, artifacts, tracking status, and historical Code |
| Code | Read-only generated Python for the current Working Pipeline; historical Python is retrieved from its original Run artifact |

Generated Python is the **actual workload executed**, not decorative export code.
Preprocessing learns from training rows only. Precision, Recall, F1 and ROC-AUC use
the explicit positive class. Missing metrics are unavailable, never fabricated zero.
Matching comparison context does not independently prove identical held-out rows;
there is no ranking or automatic winner.

SQLite and managed local files own Project, Dataset, Working Pipeline and Run
truth. Local MLflow is supporting tracking; its failure does not invalidate an
otherwise successful Run. Dataset replacement retains the source used by history.
Missing/corrupt historical sources or Run artifacts produce integrity warnings;
retained SQLite metrics remain available and comparison deltas are suppressed.

## Supported installation: source checkout only

Acceptance environment: **Windows, Python 3.14.2, Node.js 24.13.0**, with npm.
Broader manifest runtime ranges are compatibility declarations, not additional
tested platforms. macOS/Linux and other runtime versions are **not verified** for
this release. No Docker, remote database, or MLflow server is required.

Clone/download the 0.1.0 source and run these PowerShell commands from its root:

~~~powershell
python -m venv backend/.venv
cd backend
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn mlstudio.main:create_app --factory --host 127.0.0.1 --port 8000
~~~

In a second terminal, from the source root:

~~~powershell
cd frontend
npm.cmd ci
npm.cmd run dev
~~~

Open http://127.0.0.1:3000. The default API is http://127.0.0.1:8000/api/v1.
Follow [Development](docs/development.md) for settings, migration checks,
production-build validation, storage paths, and contributor CI.

Keep the source checkout: migration discovery depends on its layout. Installing
only the backend wheel is **not supported** for launching the application. CI's
wheel build checks packaging quality; it does not prove standalone installability.

## First reproducible experiment

Use the committed [synthetic retention demo](examples/retention/README.md): create
a Project, upload its CSV, select the target, inspect Explore, configure Prepare
and Train, inspect Code, and click **Run experiment**. Evaluate its held-out results
and inspect historical Code in Runs. Create a second Run and compare exactly two.

## Limits and local safety

This is a trusted local development tool, not a production service. Keep both
processes bound to loopback. There is no authentication or multi-user isolation.
The separate Python subprocess is **not sandboxed**. Uploads default to 50 MiB;
parsing and training can consume substantially more memory. Treat joblib models
as trusted local artifacts, not a safe external interchange format.

State persists under the configurable local workspace outside the source tree.
Crash remnants can remain; recovery fails closed if process ownership or storage
cannot be established. Project deletion is permanent and may leave local MLflow
tracking copies. No automatic garbage collection or backup is provided.
See [Security](SECURITY.md) and [recovery/retention guidance](docs/development.md#recovery-and-retention).

v0.1 excludes regression/multiclass, additional model families, AutoML,
cross-validation, ROC curves, prediction storage, threshold tuning, editable
Python, AI assistance, authentication, cloud execution, and production serving.
The broader product vision does not expand this release's frozen contracts.

## Project documents

- [Vision](VISION.md) explains the long-term product direction.
- [Roadmap](ROADMAP.md) records staged work; [Prototype](docs/prototype.md)
  summarizes the v0.1 scope; [Architecture](docs/architecture.md) explains the
  frozen execution and persistence boundaries.
- The authoritative v0.1 contracts cover [Project](docs/specifications/project-v0.1.md),
  [Dataset](docs/specifications/dataset-v0.1.md),
  [User Journey](docs/specifications/user-journey-v0.1.md),
  [Pipeline IR](docs/specifications/pipeline-ir-v0.1.md),
  [Run](docs/specifications/run-v0.1.md),
  [Execution](docs/specifications/execution-v0.1.md),
  [Code Generation](docs/specifications/code-generation-v0.1.md), and
  [Persistence](docs/specifications/persistence-v0.1.md).
- [ADRs](docs/decisions/README.md) preserve architectural decisions;
  [Development](docs/development.md) and [Contributing](CONTRIBUTING.md) explain
  the repository workflow. See [Security](SECURITY.md), the
  [Code of Conduct](CODE_OF_CONDUCT.md), and the [Changelog](CHANGELOG.md).

ML Studio is licensed under the [Apache License 2.0](LICENSE).
