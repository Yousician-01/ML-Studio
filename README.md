# ML Studio

**Visual ML. Real code. Reproducible experiments.**

ML Studio is an open-source, local-first machine-learning workspace where visual
operations, executable Python, experiments, and AI reasoning operate over the
same reproducible ML pipeline. It aims to make an unfamiliar tabular Dataset
easier to understand, prepare, train on, and evaluate without hiding what ran.

> Start visually. Understand everything. Drop into code whenever you need.
> Never lose reproducibility.

## Status

The Prototype v0.1 domain specifications are complete. **Projects, CSV ingestion,
source exploration, Prepare, and Train configuration are implemented:** create a local Project, inspect source
columns and preview rows, override semantic types, and select a binary target.
SQLite preserves configuration, and managed source artifacts survive replacement.
Explore provides interactive histograms, boxplots, frequency/missingness bars,
a correlation heatmap, and searchable column observations. Projects can be permanently deleted with explicit confirmation.
Prepare persists versioned Pipeline IR with explicit positive class, feature
participation, and ordered preprocessing intent. Train completes explicit model
and split configuration with contextual code-generation readiness. Code provides
a deterministic, read-only Python preview of the complete configured workload,
including source integrity checks and training-only preprocessing. Previewing
does not execute transformations, train, or create Run artifacts.
Train executes saved experiments as immutable local Runs with validated results
and complete model artifacts. Runs provides historical configuration and exact
executed source; local MLflow tracking remains separate from authoritative Run state.
Follow the verified
[development setup](docs/development.md) to run the two local processes.

## Prototype v0.1

The planned local workflow creates a Project, uploads one active CSV Dataset,
explores the source, configures a Working Pipeline, trains a binary classifier,
and inspects or compares historical Runs. The workspace areas are **Data,
Explore, Prepare, Train, and Evaluate**, with **Runs** and **Code** as supporting
views. The Working Pipeline can be incomplete while the user edits it; only a
validated configuration can execute.

The supported classifiers are Logistic Regression, Decision Tree Classifier,
and Random Forest Classifier. Preparation includes compatible imputation,
scaling, one-hot encoding, and explicit feature inclusion. Evaluation uses one
train/test split and reports Accuracy, Precision, Recall, F1, a Confusion Matrix,
and ROC-AUC when valid and available. Preprocessing learns only from training
data.

**Visual → Inspect → Extend** is the broader direction: configure visually,
inspect the Python and experiment evidence, and eventually use explicit code
extension points. In v0.1, generated Python is read-only and is the **actual ML
workload executed** for a Run, not decorative export code. Current Working
Pipeline Code is a preview; each historical Run keeps the exact generated source
attempted for that Run. Runs preserve Dataset identity, configuration, results,
and the complete fitted preprocessing-plus-classifier pipeline.

ML Studio's local persistence design uses SQLite through SQLAlchemy, Alembic
migrations, managed filesystem artifacts, joblib model serialization, and local
MLflow tracking. ML Studio owns Project and Run truth; MLflow supports tracking.
Stable IDs identify domain entities; storage paths do not.

Prototype v0.1 does not include regression, multiclass classification, XGBoost,
arbitrary Python editing, AutoML, cross-validation, cloud execution, production
serving, or multi-user collaboration. The planned AI Advisor follows the
deterministic workflow; it is not part of the first implementation slice.

> An AI that understands your experiment—not merely your prompt.

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
