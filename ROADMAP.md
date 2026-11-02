# Roadmap

Delivered milestones and possible next work, not delivery dates. Current behavior is documented in the [user guides](docs/README.md); historical contracts remain versioned.

## Delivered milestones

- [x] v0.1: binary classification, managed CSVs, semantics, Explore/Prepare/Train, deterministic Python, immutable Runs/Evaluate, two-Run comparison and local MLflow.
- [x] v0.2: regression, Linear Regression/Ridge, task-aware compiler/results and numeric source exploration with preserved binary history.
- [x] v0.3: Code Drafts/snapshots, manual editing, opt-in Code Runs and evaluation reporting.
- [x] v0.4 beta implementation: multiclass, typed per-class results/matrix, Rust installer/supervisor, Live Code Companion and full-screen editing.
- [x] Public installation/tutorial/user guides and [beta readiness evidence](docs/development/beta-release-readiness.md).

## Beta release gates

- [ ] Maintainer review of documentation and validation evidence.
- [ ] Confirm remote contributor and platform CI for the release commit.
- [ ] Verify GitHub branch rules, private vulnerability reporting and private conduct contact.
- [ ] Review binary/checksum candidates before deliberate publication.
- [ ] Publish a tag/release only through an authorized maintainer action.

Checked implementation does not imply publication or acceptance on every platform. Windows and non-Windows evidence are separated in the readiness report.

## Possible later work

Broader reproducibility diagnostics, models/tasks, hyperparameter search, AI assistance, MLOps, NLP/deep learning and deployment require separate decisions. They are not part of this beta. No prediction-level charts, ROC curves or threshold tuning are implied by existing evaluation.

Track problems in Issues and focused PRs. Preserve [ADRs](docs/decisions/README.md), [frozen v0.1 specifications](docs/specifications/project-v0.1.md) and [Changelog](CHANGELOG.md) as history.
