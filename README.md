# ML Studio

**Visual ML. Real code. Reproducible experiments.**

ML Studio **0.2.0** is an open-source, local-first workspace for binary
classification and regression. Inspect a CSV, configure explicit preparation and
a model, review generated Python, and run a reproducible local experiment.
Code is read-only; the generated source is the actual workload executed.

## What is implemented

| Workspace | Capability |
| --- | --- |
| Projects | Create, edit, open and explicitly delete local Projects; choose an immutable task at creation |
| Data | One active managed CSV, source preview, physical/semantic types, overrides, task-specific target validation and explicit replacement |
| Explore | Classification summaries, distributions, missingness and correlations; regression target statistics/histogram and numeric feature relationships |
| Prepare | Explicit feature inclusion/exclusion, compatible imputation, scaling and one-hot encoding; typed positive class for binary classification |
| Train | Logistic Regression, Decision Tree and Random Forest classifiers; Linear Regression and Ridge regressors; curated parameters and one reproducible train/test split |
| Evaluate | Frozen classification metrics/confusion matrix/conditional ROC-AUC, or MAE/MSE/RMSE/R²; exactly-two comparison with context and integrity warnings |
| Runs | Immutable attempts, frozen configuration, provenance, artifacts, tracking status and historical Code |
| Code | Deterministic read-only Python for the current Working Pipeline, and original persisted Python for a historical Run |

Preprocessing learns from training rows only. Missing targets are excluded, never
imputed. Classification metrics use the explicitly selected positive class;
regression has no class orientation or stratification. Missing metrics are
unavailable, never zero; negative R² remains valid. Comparisons do not rank Runs
or independently prove identical held-out row membership.

SQLite and managed local files own Project, Dataset, Pipeline and Run truth.
MLflow provides separate local tracking; its failure does not invalidate an
otherwise successful Run. Replacement retains historical source artifacts.
Missing/corrupt evidence produces warnings and suppresses comparison deltas
without rewriting retained SQLite metrics.

## Supported installation: source checkout only

Verified environment: **Windows, Python 3.14.2, Node.js 24.13.0**, npm 11.6.2.
Broader manifest ranges are compatibility declarations, not verified platforms.
macOS/Linux and other runtime versions are not acceptance-verified. No Docker,
remote database or MLflow server is required.

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
See [Development](docs/development.md) for configuration and storage details.
MLflow initializes its separate local storage through the application integration;
do not start a separate tracking service.

**Existing workspace:** stop the backend and all workers, and back up SQLite and
managed files together before running migrations. The new head is
`0006_task_objectives`. Downgrade across this revision is refused; restore a
consistent pre-upgrade backup for rollback. Keep the source checkout: migration
discovery depends on it. The backend wheel is a packaging check, not a supported
standalone installation.

## First reproducible experiments

Follow the committed [classification demonstration](examples/retention/README.md)
or [regression demonstration](examples/regression/README.md). Both use the same
entirely synthetic CSV. Create the appropriate Project task, inspect Data/Explore,
configure Prepare and Train, review Code, execute, then inspect Evaluate and Runs.
Create a second Run to compare exactly two frozen contexts.

## Limits and local safety

This is a trusted local tool, not a production service. Keep both processes on
loopback. There is no authentication or multi-user isolation. The subprocess is
**not a secure sandbox** and inherits local user privileges. Uploads default to
50 MiB; parsing, profiling and training can consume substantially more memory.
Treat joblib artifacts as trusted local files, not a safe external interchange.

- Regression Explore provides numeric relationships; categorical grouped target
  summaries are not implemented. Its bounded source scatter is not prediction data.
- No prediction-level evidence is stored, so regression residual/predicted-versus-
  actual plots and classification ROC curves are unavailable.
- No Visual Mode, editable Code Mode, arbitrary Python, AI assistance, multiclass,
  neural networks, NLP, clustering, AutoML, cross-validation, threshold tuning,
  cloud execution or production serving is implemented.
- SQLite and managed files are local; no automatic garbage collection, backup,
  encryption-at-rest or secure multi-tenant isolation is provided. Crash remnants
  can remain; recovery fails closed when ownership cannot be established.
- Permanent Project deletion may leave local MLflow tracking copies.

See [Security](SECURITY.md) and [recovery/retention](docs/development.md#recovery-and-retention).
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

- [Architecture](docs/architecture.md) describes current version boundaries;
  [Development](docs/development.md) owns setup, validation and phase references.
- [Frozen v0.1 contracts](docs/specifications/project-v0.1.md) retain their historical
  binary identity. The [v0.2 contracts](docs/development/v0.2-phase-2-contracts.md),
  [compiler](docs/development/v0.2-phase-4-compiler.md) and remaining linked phase
  documents describe the implemented regression extension.
- [Vision](VISION.md), [Roadmap](ROADMAP.md) and the [v0.1 prototype](docs/prototype.md)
  preserve longer-term direction and historical scope, not additional implemented features.
- [Contributing](CONTRIBUTING.md), [ADRs](docs/decisions/README.md),
  [Changelog](CHANGELOG.md) and [Code of Conduct](CODE_OF_CONDUCT.md).

ML Studio is licensed under the [Apache License 2.0](LICENSE).
