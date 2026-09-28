# Prototype scope

**Status:** intended scope, not implemented functionality. This document is the
authoritative bootstrap scope. The next design session will develop Prototype
Specification v0.1 and Pipeline IR v0.1 before application work begins.

## Hypothesis and users

Can ML Studio make going from an unfamiliar tabular dataset to a correct,
reproducible baseline ML Experiment substantially easier and more understandable
than manually assembling the same workflow in a notebook?

The initial users are learners, analysts, and Python practitioners who need a
baseline and want to understand its construction.

## Planned workflow

1. Create a Project with a name, problem statement, task, and target/objective.
2. Upload a CSV in the Data Bench; inspect inferred schema and confirm the target.
3. Profile the dataset and perform basic EDA in Explore.
4. Configure cleaning and preprocessing in Feature Engineering.
5. Choose a model and split configuration, validate the Pipeline, and train.
6. Evaluate, compare Runs, and inspect generated Python.

Cleaning and preprocessing must be recorded in Pipeline state. Inferred types
need user review. Target selection must be reconciled with the uploaded schema.
Preprocessors learn only from training data; test data must not influence fitted
transformations or model selection. EDA must make the viewed partition clear.
Detailed split/EDA semantics remain part of the upcoming specification.

## Intended capabilities

Tasks: **classification and regression**. Input: **CSV only** initially.

| Area | Prototype candidates |
| --- | --- |
| Classification | Logistic Regression, Decision Tree, Random Forest, XGBoost |
| Regression | Linear Regression, Decision Tree Regressor, Random Forest Regressor, XGBoost Regressor |
| Preprocessing | SimpleImputer, StandardScaler, MinMaxScaler, RobustScaler, OneHotEncoder |
| Splitting | Train/test split, configurable test size, deterministic random seed, stratification where appropriate |
| EDA | Dataset summary, inferred column types, missing values, target distribution, histograms, box plots, correlation analysis, categorical distributions, basic outlier information, class imbalance information |
| Classification evaluation | Accuracy, Precision, Recall, F1, ROC-AUC where appropriate, Confusion Matrix |
| Regression evaluation | MAE, RMSE, R² |

Exact supported parameters, CSV limits, inference rules, multiclass metric
averaging, ROC-AUC eligibility, and invalid-configuration behavior still need
specification. Candidate tools do not imply that every combination is valid.
Correlation is descriptive, not evidence of causation.

## Experiments and generated code

A Run should preserve dataset identity/version, Pipeline configuration, model,
hyperparameters, seed, metrics, artifacts, plots, and environment versions through
MLflow. Basic comparison belongs to v0.1; richer comparison is later. Run failure
must be visible and must not look like success. Dataset identity does not imply
uploading raw datasets into tracking storage.

Every visual ML operation should have reproducible Pipeline state. The same
Pipeline IR should drive execution and readable, executable generated Python.
Generated code should run independently of ML Studio wherever practical, with
documented data and environment requirements. The initial direction is
**visual configuration → managed Python**, not arbitrary bidirectional editing.

## AI objective and correctness

The planned AI Advisor should explain suggestions using structured Project
facts, including schema, profiling, Pipeline state, and Run results. Present
Recommendation, Reason, Evidence, Confidence, and Alternative where practical;
uncertainty must be visible. Suggestions require explicit user action and normal
deterministic validation. AI must not be required to execute a valid Pipeline.

Essential deterministic checks should prevent or warn about preprocessing and
target leakage, incorrect train/test handling, inappropriate metrics for
imbalanced targets, accidental identifier features, unsupported missing values,
and incorrect preprocessing order. A broader Pipeline Critic can evolve later.
Exact error-versus-warning rules need design; no validator can guarantee valid
scientific conclusions.

## Explicit non-goals

- Authentication, teams, multi-tenancy, and enterprise RBAC
- Cloud deployment platform, production model serving, and Kubernetes
- Distributed training, feature stores, and arbitrary database connectors
- Computer vision, NLP workflows, deep learning, and LLM fine-tuning
- Agents and autonomous experimentation
- Real-time monitoring
- Arbitrary visual ↔ Python synchronization
- Plugin marketplace

These are outside the prototype, not promises for later releases.

## Success criteria to validate

None of the runtime criteria is claimed as achieved at bootstrap.

1. A stranger understands what ML Studio does from the README.
2. A stranger can run it locally using verified instructions without maintainer help.
3. A stranger completes an end-to-end tabular Experiment on an unfamiliar CSV.
4. Every visual ML operation has reproducible Pipeline state.
5. Generated Python reproduces the Pipeline wherever technically practical;
   comparisons document tolerances and unavoidable differences.
6. Tracking preserves enough information to understand and reconstruct a Run,
   assuming the referenced dataset remains available.
7. AI recommendations reference actual structured Project facts, not generic advice.
8. Representative common ML mistakes trigger actionable prevention or warnings.

The next specification should define concrete acceptance examples and a notebook
comparison exercise measuring completion, understanding, and correctness, without
inventing benchmark results now.
