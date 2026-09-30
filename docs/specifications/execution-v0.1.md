# Execution — Prototype v0.1

## Purpose and status

Execution turns validated Pipeline IR into one deterministic local binary
classification attempt. This is a domain execution contract, not an
implementation. It fixes correctness, ownership, and outcome rules while leaving
generated source layout, artifact storage, and MLflow integration to later work.

```text
Validated Pipeline IR
        ↓
Resolve Effective Execution Plan
        ↓
Generate Executable Python
        ↓
Freeze Execution Package
        ↓
Create Run
        ↓
Launch Generated Python Locally
        ↓
Execute ML Workload
        ↓
Produce Structured Outputs
        ↓
Persist Required Artifacts
        ↓
Finalize Run
```

For a Run whose workload starts, the Python shown in historical Code is the
**exact Python launched for that Run**. A launch-failed Run retains the exact
prepared program but must not claim that it ran. There is no second hidden ML
pipeline implementation. These boundaries follow the current
[Project](project-v0.1.md), [Dataset](dataset-v0.1.md),
[User Journey](user-journey-v0.1.md), [Pipeline IR](pipeline-ir-v0.1.md), and
[Run](run-v0.1.md) contracts.

## Contract consistency and scope differences

| Current specification | Execution relationship |
| --- | --- |
| Project v0.1 | Execution starts from its current Working Pipeline; once created, a Run's history never follows later Project edits. Project's older “Run begins” wording is refined by Run v0.1's prelaunch CREATED boundary. |
| Dataset v0.1 | Execution resolves one immutable CSV source by exact identity/fingerprint and uses effective semantic interpretation without modifying the source. |
| User Journey v0.1 | Execution covers its single train/test split, three classifiers, core binary metrics, and visible failures. Historical Code uses the actual frozen program. |
| Pipeline IR v0.1 | Only valid/reconciled IR yields an effective plan. IR holds intent rather than fitted objects or results. Its `exclude_rows` policy applies to missing targets only; every non-missing target value counts as an observed class. There is no separate silently discardable non-missing invalid-value category in v0.1. |
| Run v0.1 | The executable package is frozen before creation. CREATED → FAILED covers launch failure; RUNNING means the process started. Required local artifacts and finalization govern success independently of MLflow. |

The older [prototype](../prototype.md) and [roadmap](../../ROADMAP.md) include
regression, XGBoost, and the Feature Engineering label. This contract follows the
newer binary-only, three-model, Prepare scope. [Architecture](../architecture.md)
depicts generated Python and execution as parallel outputs of IR; the Run and
this contract require generated Python to be the executed workload.
[Vision](../../VISION.md) supports reproducibility and local-first behavior, and
[ADR 0001](../decisions/0001-use-pipeline-ir.md) supports structured shared intent.
Older statements that IR design is pending remain unchanged.

## Ownership boundaries

| Responsibility | Contract |
| --- | --- |
| Pipeline IR | Canonical user intent; may be incomplete or stale until validated. No fitted objects, results, or runtime state. |
| Effective Execution Plan | Derived from valid IR, the exact Dataset, and resolved effective semantics. Contains fully resolved instructions needed for generation; it is not a second editable configuration. Its schema is not defined here. |
| Code Generator | Converts the plan into executable Python. Generation mechanics belong to Code Generation. |
| Generated Python | Loads the source, applies target eligibility, splits data, constructs and fits preprocessing/model, predicts, evaluates, and produces a complete fitted inference artifact and machine-readable results. |
| Local Executor / Orchestrator | Creates and transitions Runs, launches the frozen Python, captures stdout/stderr, observes process completion, collects and validates structured outputs, finalizes artifacts and Run state, and coordinates tracking. |

ML Studio orchestration must not replace generated Python with an independent ML
execution path. Generated Python need not own Run lifecycle or MLflow coordination.

## Local process and Run creation

Each Run's generated workload runs in a **separate local process** from the
long-lived ML Studio application process. This gives an execution boundary for
exceptions, diagnostics, and Run identity; it is not a security sandbox. No
specific subprocess API, container, queue, scheduler, or remote worker is chosen.

Before Run creation, validate the Working Pipeline against the active Dataset,
resolve its effective plan, generate the Python, and freeze its execution inputs
and executable artifact. Failure in any of these steps creates **no Run**.
Non-blocking dormant excluded-feature warnings do not by themselves prevent
creation. The package must identify the exact source and interpretation used;
current Project state cannot be substituted later.

After creation, launch failure yields **CREATED → FAILED**. The Run retains its
prepared code and available evidence; it has no execution-start timestamp.
**RUNNING** begins only after the generated workload process successfully starts.
Data loading, preprocessing, training, evaluation, result validation, or required
artifact finalization failure after launch yields FAILED. A failed Run remains
historical, with available evidence preserved where possible.

## Exact Dataset loading and target eligibility

Execution must resolve the immutable Dataset artifact named by the frozen
Dataset ID/fingerprint and verify it is the intended source. It must never switch
to the Project's current active Dataset merely because the latter has changed.
Artifact resolution and checksum mechanics belong to Persistence.

The target is explicit and never an input feature or a feature-style imputation
candidate. Resolve the frozen typed positive class and target semantics first.
For v0.1, target handling has exactly two cases:

```text
missing target     → exclude row under missing_value_policy = exclude_rows
non-missing target → retain row and count its value as an observed class
```

Exclude **only missing-target rows** before splitting. The source interpretation
must make missingness reproducible and the population change visible as required
by Pipeline IR. No non-missing value is silently discarded as an “invalid” class.
There is no class merging or coercion to force binary suitability.

After exclusion, the target must have **exactly two distinct non-missing values**.
Fewer than two or more than two fails binary-target validation. For example,
`yes`, `no`, and `maybe` are three observed classes: `maybe` rows remain present
and the configuration is invalid for v0.1. The configured typed positive class
must match one of the two values; the other is negative. Labels need not be
numeric `0/1` and must not be silently stringified. If invalidity is detected
before Run creation, create no Run; if discovered after a frozen Run starts,
that Run is FAILED. Exact CSV missing-value parsing belongs to the Dataset and
later implementation contracts, not a third target-handling policy here.

## Single deterministic train/test split

Use one held-out train/test split on rows with **non-missing targets only**. The
frozen IR names `test_size`, `random_seed`, and `stratify`; each Run retains these
choices.
Given the same Dataset contents/identity, target, eligible row population,
split configuration, and relevant execution implementation/version, the split
should be equivalent across Runs. Model or preprocessing changes must not change
which eligible rows are held out merely by changing the model.

With `stratify: true`, use target classes as the stratification basis. Preserve
the class distribution to the degree the requested split permits. If class
counts or test size make stratification impossible, fail clearly; never silently
switch to an unstratified split. A non-stratified split uses the requested choice
and seed, with no unannounced fallback. Exact integer allocation, ordering, and
library call choices remain implementation details, subject to the equivalence
contract. No cross-validation, repeated holdout, separate test upload, or HPO
splitting is added. No bit-for-bit promise extends across arbitrary future
Python, library, platform, or numerical environment changes.

## Leakage prevention and feature participation

The order is normative:

```text
Immutable source Dataset
    ↓
Resolve target; exclude missing-target rows under frozen semantics
    ↓
Separate X (included features only) and y (target)
    ↓
Split eligible rows into training and held-out test partitions
    ↓
Fit learned preprocessing on X_train only
    ↓
Transform X_train with fitted preprocessing; fit classifier with y_train
    ↓
Transform X_test with that same fitted preprocessing
    ↓
Predict and evaluate against y_test
```

Learned preprocessing must never fit on the whole source before splitting.
Training data alone determines imputation statistics, scaling parameters, and
one-hot category vocabularies. Test feature values and held-out labels must not
influence those fitted states. The fitted transformations are then applied to
held-out input without refitting. Avoid target leakage: the target never enters
X, and a former target can participate only if explicitly re-enabled and valid
under Pipeline IR rules.

Only features with `included: true` in the valid effective configuration may
enter fitting or model input. Excluded features do not influence learned
preprocessing. Their dormant IR operations stay in the frozen configured IR but
are ignored by the effective plan. Incompatible active operations are blocking;
dormant semantic incompatibilities on excluded features are non-blocking warnings.
An execution plan cannot silently rewrite an unsupported active sequence.

## Preparation semantics

Respect the ordered per-feature IR operations and narrow v0.1 grammar:

```text
Numerical:   raw → optional imputation → optional scaling
Categorical: raw → optional imputation → optional one-hot encoding
```

| IR operation | Intended mature-library mapping |
| --- | --- |
| `impute(mean / median / most_frequent)` | Corresponding simple imputation strategy, subject to effective feature semantics |
| `scale(standard / min_max / robust)` | StandardScaler / MinMaxScaler / RobustScaler |
| `encode(one_hot)` | OneHotEncoder |

“None” for scaling or encoding means **no operation**, not a synthetic `none`
object. No-operation features retain their raw meaning only if compatible with
the chosen classifier. Unsupported order or combination must be blocked before
launch where possible; generated code must not reorder intent to make it run.
Mature sklearn composition primitives such as Pipeline and ColumnTransformer
are appropriate for implementation, while IR domain identifiers remain
library-independent. Exact composition and handling of library options belong
to Code Generation and the chosen library-version matrix.

## Classifier and parameter semantics

Map the three domain model types to the corresponding sklearn classifiers:

| IR model type | Classifier | Curated explicit parameters |
| --- | --- | --- |
| `logistic_regression` | Logistic Regression | `C`, `penalty`, `max_iter` |
| `decision_tree` | Decision Tree Classifier | `max_depth`, `min_samples_split`, `min_samples_leaf` |
| `random_forest` | Random Forest Classifier | `n_estimators`, `max_depth`, `min_samples_split`, `min_samples_leaf` |

Effective values must be explicit and reproducible. A user-visible “default”
resolves to a value before execution rather than inheriting an unrecorded future
sklearn default. Unsupported values or combinations must fail clearly, preferably
before Run creation; never silently change requested intent to placate a library.

Basic parameter validity is frozen at the domain boundary:

| Model | Parameter | Required constraint |
| --- | --- | --- |
| Logistic Regression | `C` | Finite numeric value greater than 0; boolean is not a numeric substitute |
| Logistic Regression | `penalty` | One of the curated v0.1 values supported by ML Studio; exact curated values and solver mapping are finalized with Code Generation |
| Logistic Regression | `max_iter` | Integer at least 1; boolean is not an integer substitute |
| Decision Tree Classifier | `max_depth` | Null or integer at least 1 |
| Decision Tree Classifier | `min_samples_split` | Integer at least 2 |
| Decision Tree Classifier | `min_samples_leaf` | Integer at least 1 |
| Random Forest Classifier | `n_estimators` | Integer at least 1 |
| Random Forest Classifier | `max_depth` | Null or integer at least 1 |
| Random Forest Classifier | `min_samples_split` | Integer at least 2 |
| Random Forest Classifier | `min_samples_leaf` | Integer at least 1 |

The integer constraints above exclude booleans. Implementation/package
configuration must pin or constrain supported sklearn versions, and each Run
records the actual version used in provenance. Execution-affecting choices must
be explicitly resolved rather than accidentally inherited from future sklearn
defaults. In particular, generated Logistic Regression execution must use an
explicitly compatible solver/penalty mapping; `solver` is not added to the
user-facing Pipeline IR parameter surface. Exact solver mapping and numeric
defaults are Code Generation decisions. Additional restrictions required by the
selected sklearn version may be enforced, but invalid configurations fail
clearly rather than being silently rewritten. The current
[Logistic Regression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html)
and [Random Forest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html)
documentation illustrate why version-dependent defaults and compatibility need
an explicit implementation choice.

Where a supported estimator has stochastic behavior,
propagate the IR `random_seed` to its relevant random-state setting unless an
exception is explicitly justified and captured in provenance. Apply the same
principle to other stochastic v0.1 behavior. The seed is a reproducibility
control, not a universal cross-environment identity guarantee.

## Fitted inference artifact and prediction

A successful Run persists a **complete fitted inference pipeline**, capable of
applying its fitted preprocessing and classifier together to compatible raw
feature input. A bare classifier is insufficient when imputation, scaling, or
encoding was fitted. No model format is chosen here; Persistence handles the
artifact mechanics.

Evaluate the held-out test set using predictions from that fitted classifier.
Predicted class labels must correspond to the two frozen target classes.
The configured positive class controls positive-class metrics; do not assume
numeric `1` or estimator class order encodes user intent. v0.1 does not expose
threshold tuning; standard supported estimator prediction behavior is used.

## Required evaluation and conditional ROC-AUC

The standard binary evaluation records Accuracy, Precision, Recall, F1, and
Confusion Matrix. Precision, Recall, and F1 use the configured positive class.
Confusion Matrix uses exactly **`[negative_class, positive_class]`** ordering.
It remains a 2×2 matrix even if one class is absent from the held-out test
partition. Precision, Recall, and F1 use deterministic zero-division behavior
equivalent to returning `0` when a metric denominator is undefined, rather than
depending on warning-based library defaults. This does not turn ordinary poor
performance into unavailability. No metric
selection, ranking, winner labeling, optimization metric, or custom metric is
introduced.

ROC-AUC is conditional because it needs a continuous score whose direction
means **more confidence in the configured positive class**. Prefer
`predict_proba` and select the probability column matching that class. Otherwise
use `decision_function` only after verifying its class orientation and reversing
it when needed. Never use hard `predict()` labels as a continuous score. Do not
assume library default class ordering matches the user's chosen positive class.
These constraints match the [scikit-learn ROC-AUC documentation](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.roc_auc_score.html)
and [ROC visualization guidance](https://scikit-learn.org/stable/visualizations.html).

ROC-AUC requires both classes in held-out ground truth. If no valid score exists,
or the held-out test partition contains only one class, report ROC-AUC as
**unavailable with a reason**.
Do not fabricate a zero or calculate from hard predictions. That metric-specific
unavailability does not fail an otherwise successful Run when all required core
metrics and artifacts are valid. This keeps an optional metric from overriding
the Run's required success contract. Exact result representation is deferred.

## Structured output and diagnostics

Generated Python must produce machine-readable structured results for ML Studio.
The result communicates workload outcome, finalized metric values or explicit
unavailability, confusion-matrix labels/values, and references to produced
artifacts. The executor validates this information; a console sentence is not
the canonical result channel. The contract does not select a file path, transport,
or finalized schema. An illustrative fragment is:

```json
{
  "status": "success",
  "metrics": {
    "accuracy": 0.87,
    "precision": 0.82,
    "recall": 0.79,
    "f1": 0.80,
    "roc_auc": 0.89
  },
  "confusion_matrix": {"labels": ["no", "yes"], "values": "illustrative"},
  "artifacts": {"model": "illustrative-reference"}
}
```

This is **non-normative** and does not set artifact names, paths, matrix
serialization, or result field names. Stdout/stderr are separate diagnostic
channels to capture for failure analysis; arbitrary text from them must not be
parsed as authoritative metrics, artifact identity, Run status, or structured
result. Logs and diagnostics should avoid raw rows, secrets, and sensitive data.

## Process exit, validation, and finalization

Zero process exit is necessary but insufficient for success. Before SUCCEEDED,
orchestration must verify successful process completion, valid structured result,
required core evaluation, complete fitted model artifact, frozen IR/semantic/code
evidence, local artifact persistence, and successful Run finalization. An exit
code of zero with missing, corrupt, or inconsistent required outputs is FAILED.
Nonzero exit after process start is FAILED. Post-creation launch failure is
CREATED → FAILED. Started processes follow CREATED → RUNNING → SUCCEEDED/FAILED.

A FAILED Run retains available frozen inputs, exact generated code, stdout/stderr,
structured failure information, and partial diagnostics where possible. Partial
metrics from a failed workload are **diagnostic only**, never finalized evaluation
results. Do not make a raw traceback the primary user-facing message.

At minimum, a failure explanation should identify a broad stage when known:
launch, data loading, preprocessing, training, evaluation, artifact persistence,
result validation, or finalization. These are useful conceptual distinctions,
not a frozen exception/error-code enum; exact taxonomy can be refined alongside
the process protocol. Run identity and frozen facts cannot be silently rewritten
to turn a failed attempt into success.

## Tracking, provenance, privacy, and operational limits

MLflow is supporting experiment-tracking infrastructure, coordinated by ML
Studio orchestration. Generated Python must not use MLflow as its primary result
channel or own the whole tracking lifecycle. The structured output and Run
artifacts must provide enough information for an adapter to log model parameters,
metrics, artifacts, provenance, and association without owning domain semantics.
If local execution, required artifacts, and Run finalization succeed but MLflow
logging fails, the Run remains SUCCEEDED with separate repairable tracking state.
No tracking retry mechanism is designed here.

Record at least ML Studio, Python, and relevant used ML-library versions,
including the actual sklearn version, as Run provenance. Do not snapshot all
installed packages or promise full environment reconstruction. Raw Dataset rows
must not be casually written to application
logs, stdout/stderr, MLflow tags, or user-facing failure messages. Generated
Python is produced by ML Studio from its supported configuration; v0.1 does not
allow arbitrary user Python. A separate process isolates failures but does not
provide a security sandbox.

No concurrent Run guarantee or scheduler is required. A minimal implementation
may execute one Run at a time per local workspace. Parallel scheduling policy
is deferred. Cancellation is outside v0.1; no timeout contract is established
here. Basic process safety and crash handling require later operational design,
but no queue, retry service, or automatic cancellation is introduced.

## Non-normative churn walkthrough

Assume the fictional `customers.csv` source, target `churn`, typed string
positive class `yes`, and frozen Pipeline IR from
[the churn example](pipeline-ir-v0.1.md). `customer_id` is excluded. `age`,
`income`, and `tenure_months` use median imputation then StandardScaler;
`city` and `plan` use most-frequent imputation then OneHotEncoder. The model is
Logistic Regression with `C = 1.0`, `penalty = l2`, and `max_iter = 1000`.
The split is 20% test, seed 42, stratified. These numbers illustrate intent,
not universal defaults.

1. Validate the IR against the exact Dataset and semantic context. Resolve a
   plan containing only the included features, target interpretation, model, and
   split; any dormant excluded operations remain out of execution.
2. Generate executable Python, freeze it with the Dataset identity, semantic
   context, and IR, then create Run 001 in CREATED.
3. Launch that exact Python in a separate local process. Its successful start
   moves Run 001 to RUNNING.
4. The workload loads the referenced source, excludes only missing-target rows
   under frozen semantics, verifies exactly two non-missing classes and the
   configured positive class, then
   makes the seeded stratified train/test split on eligible rows.
5. It fits imputation, scaling, and category vocabulary on training features
   only; applies the fitted preparation to train/test features; fits the
   classifier on training data and predicts held-out labels.
6. It computes core metrics using positive class `yes`, records a 2×2 confusion
   matrix ordered `[no, yes]` with explicit zero-division behavior, and uses the
   `yes` probability for ROC-AUC if a
   valid score and both test classes are present. Otherwise ROC-AUC is unavailable
   with a reason, without changing the core result.
7. It produces the complete fitted preprocessing-plus-classifier artifact and
   machine-readable result. Orchestration validates and persists required outputs,
   finalizes Run 001 as SUCCEEDED, and coordinates separate MLflow tracking.

If launch fails after creation, Run 001 instead becomes FAILED without a RUNNING
state or execution-start timestamp. If process execution or required artifact
finalization fails later, the Run is FAILED with available diagnostics retained.
This walkthrough is conceptual, not process pseudocode.

## Normative execution invariants

1. Only execution-ready validated configuration may proceed to code generation
   and execution; non-blocking dormant warnings alone do not prevent readiness.
2. Validation failure before Run creation creates no Run.
3. Effective-plan resolution failure before Run creation creates no Run.
4. Code-generation failure before Run creation creates no Run.
5. The Run's exact generated Python is the program launched if the workload starts;
   launch failure retains it as the exact prepared program.
6. Each Run workload executes locally in a separate process.
7. Process-launch failure after creation produces a FAILED Run.
8. RUNNING means the generated process successfully started.
9. Execution uses the exact frozen Dataset artifact referenced by the Run.
10. Only missing-target rows are excluded before splitting; all non-missing
    values count as observed classes, and exactly two are required.
11. Target values are never feature-style imputed.
12. Eligible target data must contain exactly two usable classes.
13. Positive class must match one eligible target class.
14. Target is never included as a feature.
15. Train/test splitting precedes fitting learned preprocessing.
16. Learned preprocessing fits only on training data.
17. Test data does not influence imputation statistics.
18. Test data does not influence scaling parameters.
19. Test data does not influence categorical vocabularies.
20. Excluded features do not influence preprocessing or model fitting.
21. Pipeline operation order is respected.
22. Unsupported effective operation combinations are not silently rewritten.
23. Only the three frozen classifier families are supported.
24. Effective model parameters are explicit.
25. Random seed propagates to supported stochastic execution behavior.
26. Successful Runs persist complete fitted inference pipelines, not bare classifiers.
27. Precision, Recall, and F1 respect the configured positive class and return
    zero deterministically when an otherwise required denominator is undefined.
28. Confusion Matrix is always 2×2 with `[negative_class, positive_class]` order,
    including when one class is absent from the held-out ground truth.
29. ROC-AUC never uses hard class predictions as continuous scores.
30. Stdout/stderr are diagnostic, not the canonical result channel.
31. Generated workloads produce machine-readable structured results.
32. Exit code zero alone does not imply successful Run completion.
33. Required outputs and artifacts validate before SUCCEEDED.
34. Failed Runs do not expose partial metrics as finalized results.
35. MLflow is not the generated-process result channel.
36. MLflow failure alone does not fail an otherwise successful ML Studio Run.
37. Raw Dataset records are not casually dumped into logs or tracking metadata.
38. Execution provenance is retained.
39. Execution does not promise cross-environment bit-for-bit equivalence.
40. No hidden second ML implementation may diverge from the Run's Python artifact.
41. Supported sklearn dependency versions are pinned or constrained by implementation;
    each Run records the actual version and resolves execution-affecting choices.
42. Curated model parameters obey the explicit constraints above; incompatible
    solver/penalty or other unsupported combinations fail clearly.
43. A one-class held-out partition alone does not fail a Run when required core
    results are valid; ROC-AUC is unavailable in that case.

## Explicit exclusions

Execution v0.1 excludes regression, multiclass classification, XGBoost, arbitrary
estimators or user Python, custom Python nodes, notebooks, cross-validation,
repeated holdout, HPO, AutoML, distributed/remote/cloud/GPU execution guarantees,
Kubernetes, queues, scheduling, cancellation, pause/resume, automatic retries,
online inference, deployment/serving, streaming data, environment/container
reconstruction, and arbitrary user dependency installation. It does not create
an additional model, Dataset connector, or preparation operation.

## Genuine unresolved Execution questions

**No blocking Execution v0.1 questions remain.** Only missing-target rows are
excluded; the binary target has exactly two non-missing classes. Basic model
parameter constraints and deterministic one-class test-set metric behavior are
frozen above. Exact Logistic Regression solver/penalty mapping, curated penalty
values, and numeric defaults remain Code Generation/library-version decisions,
with explicit compatibility required. Structured-result transport, model
serialization, log location, and tracking retries belong to later contracts.
Parallel scheduling and timeouts remain deferred operational policies.

## Later-specification boundaries

### Code Generation

Define exact Python source structure, imports, deterministic rendering,
readability, comments, naming, generator versioning, and mapping of a validated
effective plan to source. The current Working Pipeline preview and immutable
historical artifact must accurately identify their respective contexts. Code
Generation must honor the selected library/parameter compatibility matrix,
including an explicit Logistic Regression solver/penalty mapping and resolved
defaults without adding a user-facing solver field.

### Persistence

Define local workspace root, Dataset/Run artifact paths, model serialization,
structured-result transport/location, log storage, atomic writes/finalization,
artifact resolution, retention/deletion, and corruption handling. No path,
filename, or file format is frozen here.

### MLflow integration

Define local tracking setup, Project/experiment and Run mappings, tags, metrics,
artifact/model logging, partial synchronization, and retry/reconciliation.
Preserve ML Studio's Run identity, local success contract, and repairable tracking
state. A separate large MLflow specification is unnecessary unless implementation
shows a need.
