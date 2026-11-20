# Training

## Models in this beta

| Task | Estimators | Main configuration |
| --- | --- | --- |
| Binary | Logistic Regression; Decision Tree; Random Forest | Logistic C, penalty, max iterations; tree depth/minimum split/leaf; forest estimator count |
| Multiclass | Logistic Regression; Decision Tree; Random Forest | Same curated families; Logistic is L2/lbfgs, not binary-only L1/liblinear |
| Regression | Linear Regression; Ridge | Fit intercept; Ridge alpha |

This is a curated catalogue, not arbitrary sklearn import. Forms/readiness enforce ranges and combinations. No boosting, AutoML, neural networks, cross-validation or hyperparameter search.

## Configure, save, review, run

1. Finish target selection and Prepare intent.
2. Configure held-out test proportion (5-50%) and seed. Classification supports stratification; regression does not. Save split edits.
3. Select a model and save edited parameters. Resolve readiness errors: missing preparation, unsupported semantics, stale Dataset binding or impossible splits. Multiclass requires every class in both partitions and bounded class/test populations.
4. Open **Show Code**. Unsaved Train fields can yield a proposed preview; this is not a saved recipe or Run. Resolve invalid intermediate input.
5. Start **Run experiment** from a ready saved pipeline. Admission checks reviewed revision, plan and source identity. Stale changes require refresh rather than silently executing another configuration.

A Run freezes fingerprint, interpretation, IR, resolved plan, Python and provenance. Execution runs that persisted file in a local subprocess, not another hidden training path. Splitting precedes learned preparation. SQLite/files are authoritative; MLflow is secondary.

Visual lifecycle: CREATED / RUNNING / SUCCEEDED or FAILED. Timeouts, bounded logs/results and validation limit execution, but provide no secure sandbox or hard memory quota. Code Runs have separate records/lifecycle; draft saves are not experiments.

Inspect failures and tracking status in Runs. MLflow synchronization failure does not turn a correctly finalized local success into failed execution. See [Runs and evaluation](runs-and-evaluation.md).

## Saved-model schema contracts (v0.5 development)

For newly compiled visual models, import the Run's **frozen generated Python** to
register its portable transformer classes before loading its trusted `model.joblib`.
Inspect `pipeline.schema_contract_`: `raw.raw_inputs` lists exact required columns,
original physical/semantic hints, intermediate-only use and configured cleaning
policies. `raw.extra_columns` is `ignored`. Missing values follow the saved cleaning,
parsing, imputation and transform policies, not a new schema parser.

`estimator` records fitted scikit-learn feature names/order, count, dtype, dense/sparse
representation and the variance selected mask when applicable. The fitted wrapper
checks names/width, numeric/finite values and one-row-in/one-row-out before prediction.
Inputs may arrive in a different raw column order; projection restores the required
order. Additional columns, including target labels and precomputed generated values,
are ignored. Missing required columns or duplicate names fail explicitly. Valid
cleaning-normalized/coerced values still use the same saved runtime.

Older model artifacts have no required `schema_contract_` attribute. Keep using their
frozen source and existing environment; no historical source is regenerated. These
contracts are for compiled visual workflows, not a sandbox or a guarantee against
future-information leakage in user features. No public prediction endpoint, new
schema artifact, per-row partial response or untrusted model loading is added.
