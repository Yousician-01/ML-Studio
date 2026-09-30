# Prototype scope — v0.1

**Status:** the domain contracts are complete; implementation is beginning. This
is a concise product summary, not a claim that the application already runs.
The [v0.1 specifications](specifications/project-v0.1.md) govern normative
behavior; the [architecture](architecture.md) describes execution and storage.

## Hypothesis and users

Can ML Studio make the path from an unfamiliar tabular Dataset to a correct,
reproducible baseline binary-classification experiment easier to understand than
assembling the same workflow manually in a notebook? The initial users are
learners, analysts, and Python practitioners who want to inspect how their
baseline was built.

## Planned workspace and workflow

```text
Project → Data → Explore → Prepare → Train → Evaluate
                      Supporting views: Runs, Code
```

Create a Project, upload an immutable CSV source, inspect its schema and source
data, choose a binary target and positive class, explore distributions and
missingness, then configure preprocessing and features in the Working Pipeline.
Choose a model and one train/test split, resolve validation issues, train, inspect
the selected Run's results, and compare exactly two Runs where useful. Runs and
Code are supporting views, not compulsory wizard steps. The Working Pipeline may
remain incomplete while being edited; historical Runs remain unchanged.

## Frozen v0.1 capabilities

| Area | Scope |
| --- | --- |
| Task and source | Binary classification on tabular CSV; at most one active Dataset per Project; prior Dataset artifacts retained for historical Runs |
| Explore | Source profile, target distribution/class imbalance, missingness, numerical and categorical distributions, basic box plots, applicable correlation, high-cardinality, duplicate-row and possible-identifier observations |
| Prepare | Compatible mean/median/most-frequent imputation; no scaling or StandardScaler/MinMaxScaler/RobustScaler; no categorical encoding or OneHotEncoder; explicit feature inclusion/exclusion |
| Train | One seeded train/test split with explicit test size and stratification choice; Logistic Regression, Decision Tree Classifier, or Random Forest Classifier with curated parameters |
| Evaluate | Accuracy, Precision, Recall, F1, 2×2 Confusion Matrix, and ROC-AUC when valid and available |
| Runs and Code | Immutable Run snapshots and exact executed-source artifacts; current Working Pipeline code preview; read-only historical Code; two-Run comparison |
| Local storage/tracking | SQLite through SQLAlchemy, Alembic migrations, managed filesystem artifacts, joblib complete fitted pipeline, and local MLflow tracking |

Pipeline IR records visual intent. Validation derives the effective plan, code
generation renders it as readable Python, and the local executor launches that
**exact frozen Python** as the ML workload. There is no parallel hidden sklearn
implementation for the same experiment. Learned preprocessing fits only on
training data. The source Dataset is never overwritten. ML Studio owns Run truth
and required local artifacts; MLflow tracks experiments but is not the domain
database. Failed Runs retain available diagnostics without appearing successful.

The Code view distinguishes a mutable Working Pipeline preview from a selected
Run's persisted historical source. An invalid current configuration does not
produce fabricated runnable code or alter past Runs. Generated Python is managed,
read-only v0.1 code; arbitrary Python editing and reverse parsing are not part
of this prototype.

## Boundaries and later direction

Prototype v0.1 does not include regression, multiclass classification, XGBoost,
feature creation, PCA, polynomial/log transforms, automated feature selection,
resampling, outlier treatment, arbitrary transformers, cross-validation, HPO,
AutoML, notebooks as the execution model, cloud execution, production serving,
authentication, teams, or multi-tenancy. Python extension points and broader
model/task support require later decisions.

The AI Advisor is broader product direction, grounded in structured Project and
Run facts and subject to explicit user action. It is not part of the first
deterministic implementation slice and is not needed to execute a valid Pipeline.
Deterministic validation and transparent evidence come first.

## Success criteria to validate during implementation

No runtime criterion is claimed as achieved yet. A user should eventually be
able to install ML Studio with verified instructions, complete an end-to-end
binary-classification experiment on an unfamiliar CSV, inspect the exact Python
executed, compare Runs without losing history, and understand leakage and
validation feedback. Reproducibility checks must use the recorded Dataset,
configuration, seed, code, artifacts, and environment context, while acknowledging
library and numerical limits. Acceptance checks should use synthetic data and
make observed outcomes explicit rather than inventing benchmark results.
