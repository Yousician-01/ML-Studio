# Changelog

Notable user-visible changes are recorded here in a Keep-a-Changelog-inspired
format. There are no published releases yet. Exact implementation history belongs
in Git and Pull Requests.

## [Unreleased]

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
