# Architecture — ML Studio v0.2

**Status:** local binary-classification and regression workflows, including
Explore, Prepare, Train, immutable Runs, Evaluate, read-only Code and local MLflow
tracking. AI and editable Python are not implemented.
[ADR 0001](decisions/0001-use-pipeline-ir.md) establishes Pipeline IR. The
[frozen v0.1 specifications](specifications/project-v0.1.md) retain the legacy
binary contract; the linked v0.2 phase documents describe the regression extension.

## Domain and execution flow

A Project is a mutable local workspace with one immutable task selected at creation,
one active Dataset, current Working Pipeline intent and historical Runs. Task is
stored in the existing `ml_objective` field; omission at creation remains binary
classification. Metadata PATCH cannot change it.

~~~text
Managed Dataset + Working Pipeline IR
    → validation → resolved Effective Execution Plan
    → deterministic generated Python → frozen Run package
    → exact persisted source in local subprocess
    → validated results + complete fitted model + bounded logs
    → local Run finalization → separate MLflow synchronization
~~~

The Working Pipeline can be incomplete, invalid or stale after replacement.
Validation reports issues without silently rewriting intent. A reviewed preview
binds revision, plan hash and source hash. Admission revalidates these before
publishing an immutable package. Execution launches its persisted source file,
not a separately rebuilt sklearn workload. The script verifies the exact bounded
CSV buffer it parses, excludes missing targets, splits before fitting preparation,
and writes the complete fitted pipeline and structured held-out results.

## Version boundaries

| Contract | Binary classification | Regression |
| --- | --- | --- |
| Pipeline IR / effective plan | `0.1` | `0.2`, explicit `task="regression"` |
| Generator | `mlstudio-python-v1` | `mlstudio-python-v2` |
| Implementation | `sklearn-local-v1` | `sklearn-local-v2` |
| Result | `mlstudio-result-v1` | `mlstudio-result-v2`, explicit regression task |
| Workload CLI | `cli-v1` | `cli-v1` |

The binary reader, renderer, embedded source helpers and six source goldens remain
unchanged. Two separate regression goldens pin the new compiler. Dispatch is
explicit; unknown/cross-task versions fail instead of upgrading historical intent.
Linear Regression and Ridge have explicit resolved parameters; binary estimators
remain Logistic Regression, Decision Tree and Random Forest.

Regression accepts finite numeric non-Boolean targets with lossless integer-to-
float64 conversion. Constant and two-valued numeric targets are valid. There is
no positive class, target imputation or stratification. Its result validates
MAE/MSE/RMSE and conditional R², population, plan/source binding and relevant
versions. Negative R² is valid; unavailable R² carries a reason. Binary class
orientation and conditional AUC retain their original protocol.

See [task contracts](development/v0.2-phase-2-contracts.md),
[model configuration](development/v0.2-phase-3-configuration.md),
[compiler/result protocol](development/v0.2-phase-4-compiler.md) and
[shared execution/tracking](development/v0.2-phase-5-execution.md).

## Persistence, history and tracking

SQLite through SQLAlchemy owns metadata; Alembic owns schema evolution. Managed
filesystem artifacts hold source Datasets and immutable Run evidence. IDs identify
objects; paths locate bytes. Replacement creates a new Dataset and retains old
sources. A Run freezes IR, resolved plan, source, semantic context and provenance.
Validated result/model artifacts and hashes are finalized before success.

Historical Code reads its original artifact. Runs/Evaluate use frozen evidence,
never the active Dataset, current Pipeline or MLflow as authority. Compromised
artifacts produce warnings; retained SQLite metrics remain visible but cannot
participate in delta comparison. Exactly-two comparison checks task, source/target
interpretation, split, relevant versions, metric definitions and population.
Matching context does not independently prove identical held-out row membership.
No automatic ranking or winner is produced.

MLflow has its own local SQLite database and managed artifacts. Task-aware metrics
and configuration are synchronized after core terminal finalization. Null metrics
are skipped; zero and negative R² are retained. Tracking failure is secondary and
does not change the execution outcome. No remote MLflow service is required.

Migration `0006_task_objectives` widens only the Project objective constraint. Its
SQLite rebuild uses a dedicated offline connection, explicit transaction, checked
foreign-key boundary, pre/post ownership checks and integrity validation. Stop
workers and back up the complete workspace first. Downgrade is deliberately refused.
See [migration proof](development/v0.2-phase-1-compatibility.md).

## Source exploration and frontend

Explore computes source facts, not fitted or held-out results. Regression verifies
identity, size and fingerprint before parsing the same bounded buffer, and checks
revision before/after computation. Target statistics and Pearson relationships
use full eligible observations; source scatter is capped at 200 pairs. Raw pairs
are transient explicit local-UI evidence, never metadata or ordinary logs.
Categorical grouped regression summaries and prediction-level plots are deferred.
See [regression Explore](development/v0.2-phase-6.1-regression-explore.md).

The frontend discriminates task/protocol, obtains model descriptors from the
backend and protects unsaved Train drafts. Browser draft/submission recovery is
not authoritative domain state. See [frontend integration](development/v0.2-phase-6-frontend.md).

## Trust and product boundary

Local workloads inherit the current user's operating-system privileges. A separate
subprocess, bounded logs, timeouts and restricted environment inheritance are
**not a secure sandbox**. There is no authentication, multi-user isolation, cloud
execution or arbitrary Python input. Models are trusted local joblib artifacts.
No PostgreSQL, Docker, distributed queue or new service is needed. See
[Security](../SECURITY.md) and [Development](development.md) for operational limits.
