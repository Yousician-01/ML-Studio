# Roadmap

This is intended sequencing, not a delivery commitment. There are no release
dates. Checked items exist; unchecked items are planned. The
[Prototype](docs/prototype.md) summarizes scope; the
[v0.1 specifications](docs/specifications/project-v0.1.md) are authoritative.

## v0.1 — Local binary-classification prototype

- [x] Repository foundation, contribution templates, and Pipeline IR ADR
- [x] Prototype v0.1 domain specifications: Project, Dataset, User Journey,
  Pipeline IR, Run, Execution, Code Generation, and Persistence
- [ ] First end-to-end implementation slice: Create Project → Upload CSV → Select
  target → Configure preprocessing → Select Logistic Regression → Generate Python
  → Execute that exact Python → Persist Run and fitted model → Show metrics → Show
  exact executed code
- [ ] Expand the slice to the full frozen v0.1 scope: source exploration and
  profiling, Decision Tree and Random Forest classifiers, supported preparation,
  single-split evaluation, immutable Run history, two-Run comparison, current
  Code preview, local MLflow tracking, and essential leakage/readiness checks
- [ ] Verify local setup, synthetic example workflow, and prototype acceptance
  checks against the implemented application

Implementation is the next milestone. Generated Python is the workload, with no
separate hidden sklearn training path. The AI Advisor is broader product
direction and is not required before the deterministic workflow works.

## v0.2 — Experimentation

- [ ] Richer Run comparison and Experiment navigation
- [ ] Improved reproducibility diagnostics and environment capture
- [ ] Broader Pipeline Critic validation beyond essential v0.1 checks
- [ ] Hyperparameter optimization, considering Optuna
- [ ] Evaluate explicit Python extension points

## Future / exploration

Broader task types and model families, AI assistance, MLOps (including possible
Evidently integration), NLP, deep learning, and LLM experimentation require
separate scope decisions. They do not expand Prototype v0.1.

Track actionable work in GitHub Issues and implementation discussion in Pull
Requests. Record significant decisions through [ADRs](docs/decisions/README.md),
user-visible changes in the [changelog](CHANGELOG.md), and exact history in Git.
