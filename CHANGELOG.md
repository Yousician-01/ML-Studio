# Changelog

Notable user-visible changes are recorded here in a Keep-a-Changelog-inspired
format. Exact implementation history belongs in Git and Pull Requests. A prepared
release entry does not imply that its tag or GitHub release has been published.

## [Unreleased]

## [0.4.0-beta.1] - Prepared, not published

### Added

- Multiclass Projects using the existing classifiers, explicit IR 0.3 and typed
  macro/weighted/per-class results with an NxN confusion matrix.
- Persistent Code Drafts/snapshots, guarded visual reentry, default-off local
  Python Code Runs and an explicit evaluation reporting bridge.
- Workspace-wide read-only Live Code Companion with docked/floating layouts,
  proposed unsaved Train previews, full-screen editing and archived-session resume.
- Repository-based Rust CLI for install/start/status/logs/doctor/abort of the real
  FastAPI and production Next.js servers; source/local-artifact bootstrap,
  checked process ownership, bounded logs and pre-migration workspace backups.
- Public installation, tutorial, user guides, troubleshooting and release evidence.

### Compatibility and fixes

- Preserve binary/regression protocol identities and immutable historical source.
  Code drafts never replace visual Pipeline IR. MLflow remains secondary.
- Migrations 0007-0009 add Code Drafts/Code Runs and multiclass support. Stop all
  writers and back up complete workspaces before upgrade; use a consistent backup
  for rollback where downgrade is refused. Current head: `0009_multiclass`.
- Regression workspace rendering test now waits for resolved Project/Dataset state
  while retaining task-propagation and no-classification-profiling assertions.
- CLI input/build validation and lifecycle hardening; local Monaco asset handling.

### Release boundaries

- Public/CLI identity is 0.4.0-beta.1; frontend/backend package metadata remains
  independently versioned at 0.2.0. This entry does not publish anything.
- Trusted local single-user execution, not a sandbox, cloud/deployment service or
  authentication boundary. Code execution remains disabled by default.
- No ROC curves, per-sample prediction evidence, AutoML or extra model families.
- Windows validation and unverified macOS/Linux acceptance are recorded separately
  in [beta readiness](docs/development/beta-release-readiness.md).

## [0.2.0] — Prepared for release

### Added

- Immutable Project task selection: binary classification or regression, with
  task-specific target validation and explicit regression Pipeline IR 0.2.
- Linear Regression and Ridge configuration, deterministic versioned Python
  generation, exact-source local execution and strict regression result protocol.
- MAE, MSE, RMSE and conditional R² in frozen Runs/Evaluate and local MLflow
  tracking. Negative R² remains valid; unavailable metrics include reasons.
- Regression Explore target statistics/histogram, paginated numeric feature
  selection, full-pair Pearson correlation and bounded source scatter.
- Task-aware Data, Prepare, Train, Code, Runs and Evaluate; guarded revision-bound
  Train drafts and comparison compatibility checks across frozen contexts.
- A regression walkthrough reusing the committed synthetic Dataset.

### Compatibility and upgrade

- Existing binary IR 0.1, compiler/result protocols and six generated-source
  goldens remain unchanged; two regression goldens cover the new compiler.
- Existing Run history is read from frozen evidence, never regenerated or silently
  converted. Source/artifact integrity warnings continue to exclude metric deltas.
- Migration `0006_task_objectives` preserves existing records while widening the
  Project objective constraint. Stop workers and back up SQLite plus managed files
  before upgrade. Downgrade across this revision is refused; restore a consistent
  pre-upgrade backup if needed. No dependency changes are part of this release.

### Known limitations

- Verified environment remains Windows, Python 3.14.2, Node.js 24.13.0; source
  checkout/editable backend installation only. Other platforms are unverified.
- Trusted local execution, SQLite and managed files; no secure Python sandbox,
  authentication, multi-user isolation, cloud execution or automatic backup/GC.
- No categorical grouped regression summaries, prediction-level plots/evidence,
  Visual Mode, editable Code Mode, AI assistance or additional task/model families.
- Final remote Contributor CI must run after pushing; local release preparation
  does not assert that GitHub validation or release publication has occurred.

## [0.1.0] — Prototype

### Added

- Local Projects, managed immutable CSV ingestion/replacement, semantic detection
  and overrides, binary target selection, and source preview.
- Deterministic Explore summaries and visualizations; explicit feature preparation,
  positive class, model parameters, and reproducible train/test split configuration.
- Deterministic read-only Python generation and execution of the exact persisted
  source in a local subprocess, with training-only learned preprocessing.
- Immutable Runs, validated binary metrics, complete fitted model artifacts,
  provenance, historical Code, and failure-isolated local MLflow tracking.
- Evaluate and exactly-two Run comparison with frozen-context compatibility,
  typed confusion-matrix orientation and honest metric unavailability.
- Contributor CI and a committed synthetic two-experiment demonstration.

### Fixed

- Historical Dataset-source integrity now participates in Run evidence warnings
  and comparison-delta exclusion without rewriting terminal facts or metrics.
- SciPy version differences or missing evidence now suppress comparison deltas.

### Release boundaries

- Source checkout/editable installation only. Backend wheel builds are packaging
  checks, not supported standalone application distribution.
- Supported acceptance environment: Windows, Python 3.14.2, Node.js 24.13.0.
- Trusted local use only: no authentication, sandbox, cloud execution, AI, editable
  Python, regression/multiclass, ROC curves, or automatic artifact garbage collection.

## Bootstrap history

### Added

- Project vision, prototype scope, roadmap, proposed architecture, and Pipeline IR ADR.
- Contribution, conduct, security, development, and GitHub reporting guidance.
- Apache License 2.0 and repository hygiene configuration.

### Changed

### Fixed

### Security
