# Roadmap

This is intended sequencing, not a delivery commitment. There are no release
dates. Checked items exist; unchecked items are planned. The
[prototype specification](docs/prototype.md) is authoritative for scope.

## v0.1 — Prototype Foundation

- [x] Repository documentation, contribution templates, and initial Pipeline IR ADR
- [ ] Prototype Specification v0.1 and Pipeline IR v0.1 design — next work
- [ ] Execution engine foundation driven by validated Pipeline IR
- [ ] Project creation, CSV ingestion, schema inspection, and target selection
- [ ] Dataset profiling and basic EDA
- [ ] Basic preprocessing and reproducible splitting with essential leakage checks
- [ ] Baseline classification/regression training and evaluation
- [ ] MLflow integration and basic Run comparison
- [ ] Readable generated Python with execution parity checks
- [ ] AI Advisor prototype grounded in structured facts, with explicit user control
- [ ] Verified local setup, example workflow, and prototype acceptance checks

Application work starts only after the specification and IR design are reviewed.
The AI Advisor follows the deterministic workflow; no AI is implemented now.

## v0.2 — Experimentation

- [ ] Richer Run comparison and Experiment navigation
- [ ] Improved reproducibility diagnostics and environment capture
- [ ] Broader Pipeline Critic validation beyond essential v0.1 checks
- [ ] Hyperparameter optimization, considering Optuna
- [ ] Evaluate explicit Python extension points

## Future / Exploration

MLOps (including possible Evidently integration), NLP, deep learning, and LLM
experimentation are exploratory directions. They require separate scope decisions.

Track actionable problems in GitHub Issues and implementation discussion in Pull
Requests. Link significant decisions through [ADRs](docs/decisions/README.md),
and record user-visible changes in the [changelog](CHANGELOG.md). Do not maintain
a parallel daily development diary.
