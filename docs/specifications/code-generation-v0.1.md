# Code Generation — Prototype v0.1

## Purpose and authority

This contract defines how ML Studio renders an execution-ready binary-classification experiment as readable, executable Python. The generated Python is the **actual data-science workload** launched for a Run, not illustrative export code. It refines [Pipeline IR](pipeline-ir-v0.1.md), [Run](run-v0.1.md), [Execution](execution-v0.1.md), and the [User Journey](user-journey-v0.1.md). Those specifications govern their respective domain boundaries; this document does not define a source schema, process protocol, or storage layout.

```text
Validated Pipeline IR + resolved Dataset semantics
    → Effective Execution Plan → Code Generator → Generated Python → Local Executor
```

There is no separate backend implementation that constructs and trains the same ML pipeline while similar-looking code is generated only for display. The generated program performs the workload. The executor handles application orchestration.

## Two Code contexts

**Working Pipeline Code** is a read-only preview generated from the current mutable Working Pipeline after it has enough valid configuration to resolve an execution-ready plan. It shows what ML Studio would execute if trained now. It can change with working edits and is not historical evidence. An incomplete or execution-invalid configuration must show its missing or blocking prerequisites; it must not be represented by fabricated runnable Python. Preview generation only renders source: it does not train, mutate the Dataset, create a Run or historical artifact, or create MLflow history.

**Historical Run Code** is the exact immutable Python source artifact frozen for the selected Run. It is retrieved from that artifact, never regenerated with the current generator or reconstructed from current Project state. If a Run failed to launch, the source identifies the program prepared for the attempt, not a program that ran. Both contexts must be visibly identified and remain read-only.

## Input and rendering contract

The generator consumes a validated, execution-ready **effective execution plan** containing resolved Dataset identity and interpretation, target and typed class semantics, effective included features and ordered operations, split settings, classifier, and effective parameters. It renders resolved execution intent; it does not independently reinterpret the editable IR, resolve a different default, or silently change a feature, target, class, operation, order, split, model family, or effective parameter. Excluded features and their dormant operations remain in frozen configured IR but do not enter generated workload code.

For the same effective plan, generator version, and relevant generation configuration, generation must be semantically equivalent and should be byte-stable. Use a stable feature order based on the resolved plan, stable grouping and branch naming, stable imports, and stable formatting. Do not use unordered traversal, random names, timestamps, or incidental machine state in source. A deterministic version header is optional when provenance already captures generator identity. Record the generator/ML Studio version with the Run so future generator changes do not obscure provenance. The actual supported pandas/scikit-learn versions are constrained by the implementation and recorded for each Run as required by Execution; source stability alone is not a cross-version bit-for-bit result guarantee.

The source should use explicit, necessary imports from Python's standard library, pandas, and public scikit-learn APIs. No wildcard imports, private sklearn internals, `eval`, `exec`, encoded pipeline blobs, opaque generated DSL, or unnecessary metaprogramming. Use meaningful names, visible configuration, logical sections, and only comments that clarify experiment steps. A stable conceptual order is: imports; runtime inputs/constants; Dataset loading; target handling; feature selection; split; preprocessing; classifier and fitted pipeline; fit; predictions and evaluation; conditional ROC-AUC; complete model output; structured result output. Helper-function layout and exact formatting remain implementation choices.

## Dataset, target, features, and split

The generated program receives or resolves the exact immutable Dataset artifact identified for the Run. The source makes CSV loading understandable while treating artifact paths as runtime locations, not Dataset identity; it must not bake a user's absolute machine path into historical experiment semantics. The program preserves the frozen source interpretation needed to reproduce class and feature behavior. It must not embed source rows, secrets, credentials, or unrelated user data in source, comments, or diagnostics. Necessary column names and configuration may appear.

Target handling names the configured target and typed positive class. It excludes **only missing-target rows before splitting**. It does not filter a non-missing third class, stringify all labels, or silently alter target values. Binary validation follows Execution: exactly two distinct non-missing eligible classes are required; the configured typed positive class matches one, and the other is the negative class. A mismatch or third class is an error, not a coercion. Compatible source parsing and missing-value interpretation must follow the frozen resolved context.

The feature matrix contains only explicitly included, validated non-target columns. The target never enters it. Excluded columns, including `customer_id` in the example below, never reach a preprocessing branch or estimator. Included features with no operations remain present through explicit passthrough when their raw representation is compatible with the classifier; an empty operation list must not accidentally drop them or bypass readiness validation.

Generated Python visibly performs the one frozen `train_test_split` with explicit `test_size` and `random_state` from `random_seed`; `stratify` uses the eligible target when configured, otherwise no stratification. The split is made after target-missing exclusion and before fitting any learned preprocessing. If the requested split is infeasible, fail clearly rather than substituting another split. Equivalent source/eligible rows, target, split settings, and relevant execution version must yield equivalent partitions independently of model or preprocessing edits, as Execution requires.

## Leakage-safe preprocessing composition

Generate mature sklearn composition, ordinarily a `ColumnTransformer` of per-feature or semantically equivalent grouped branches inside a `Pipeline` with the classifier. A branch's operation order exactly follows the effective IR grammar: numeric raw → optional `SimpleImputer` (`mean`, `median`, or compatible `most_frequent`) → optional `StandardScaler`, `MinMaxScaler`, or `RobustScaler`; categorical raw → optional compatible `SimpleImputer` → optional `OneHotEncoder`. Do not insert an operation to make incompatible raw data trainable or silently reorder unsupported intent.

The combined pipeline is fitted on **training features only**; the fitted transforms then process held-out features for prediction. No imputation statistic, scaling statistic, or categorical vocabulary is learned from the entire source before splitting. A fitted `OneHotEncoder` inside the persisted inference pipeline carries its learned categories, so compatible future raw feature input does not need an independently reconstructed vocabulary. Any library options needed for supported unknown-category behavior belong to the resolved implementation/version contract and must not silently change the intended operation.

Features with identical ordered operations and compatible resolved semantics may share one `ColumnTransformer` branch when this produces the same behavior as separate branches. Group membership, order, and names must be deterministic. Features with different sequences or configurations must stay separate. Included no-operation features use explicit passthrough as appropriate; excluded features are omitted. The complete fitted preprocessing-plus-classifier `Pipeline`, not a bare classifier, is the inference artifact.

## Classifier construction and resolved values

The only classifiers are `LogisticRegression`, `DecisionTreeClassifier`, and `RandomForestClassifier`. Generated source instantiates the selected sklearn estimator explicitly with ML Studio's resolved effective values; a UI “default” is resolved before generation rather than inherited accidentally from a future sklearn release. This does not require exposing every sklearn constructor option as a user control. Validate the parameter constraints in Execution before Run creation where possible, and fail clearly if a chosen supported sklearn version rejects an otherwise intended combination.

| IR model | Explicit generated configuration |
| --- | --- |
| `logistic_regression` | `C`, `penalty`, `max_iter`, and internally resolved `solver` |
| `decision_tree` | `max_depth`, `min_samples_split`, `min_samples_leaf`, `random_state=random_seed` |
| `random_forest` | `n_estimators`, `max_depth`, `min_samples_split`, `min_samples_leaf`, `random_state=random_seed` |

For v0.1, Logistic Regression's curated penalty values are exactly `l1` and `l2`. `solver` is **not** a user-facing IR parameter. Resolve and emit the following fixed internal mapping:

| `penalty` | Explicit `solver` |
| --- | --- |
| `l2` | `lbfgs` |
| `l1` | `liblinear` |

Do not add `elasticnet` or a no-penalty mode. Do not rely on sklearn's solver default. Generated source shows `C`, `penalty`, `max_iter`, and `solver` together. The mapping is an execution-affecting resolved choice and belongs in Run provenance alongside the source and library version. Logistic Regression's `random_state` is not required for the fixed `lbfgs`/`liblinear` mapping by this contract; stochastic choices elsewhere follow Execution's seed rule.

## Prediction, metrics, and ROC-AUC

Use the fitted complete pipeline to predict on held-out raw features using the supported classifier's standard prediction behavior; no threshold tuning is generated. Compute Accuracy, Precision, Recall, F1, and Confusion Matrix according to [Execution](execution-v0.1.md). Precision/Recall/F1 use the configured positive class and explicit zero-division behavior equivalent to `0`. The Confusion Matrix always uses `[negative_class, positive_class]` and is 2×2, even when the held-out labels contain one class.

ROC-AUC uses a continuous score whose increasing direction means more confidence in the configured positive class. Prefer `predict_proba`, selecting the score column by matching the configured positive class against the fitted classifier's `classes_` order. If probability is unavailable, use `decision_function` only with verified class orientation, reversing the score where the positive class requires it. Never use hard predictions as scores. If no suitable score exists or held-out truth has only one class, emit ROC-AUC as unavailable with a reason; do not fabricate zero or fail an otherwise complete Run solely for that conditional metric.

## Workload outputs and orchestration boundary

Generated Python loads data, enforces target eligibility, selects features, splits, builds and fits the complete sklearn pipeline, predicts, evaluates, emits a fitted model artifact, and writes machine-readable structured results. The results communicate workload outcome, required metrics or explicit unavailability, ordered confusion-matrix labels/values, and produced artifact reference(s). They must not depend on parsing stdout. Stdout/stderr may carry human-readable diagnostics, subject to the Dataset privacy rules.

The executor/orchestrator owns Run creation and lifecycle transitions, process launch, stdout/stderr capture, result and artifact validation, local finalization, and MLflow synchronization/reconciliation. Generated source does not manage Projects, UI state, Run history, ML Studio database records, application routing, or tracking policy. Runtime-provided inputs can supply Dataset, structured-result, and model-output destinations through arguments, environment, or configuration; the exact interface and paths are implementation/Persistence decisions. Source should remain readable and independent of incidental absolute storage paths wherever practical. Serialization format and artifact locations are not fixed here.

## Creation, failure, and historical boundary

Training crosses this boundary in order: validate the Working Pipeline and resolve the effective plan; generate source; freeze that source with required execution inputs; create the Run; launch **that exact frozen source**. Validation, resolution, or code-generation failure before Run creation creates no Run. Launch failure or later workload/output failure after Run creation produces a FAILED Run under Run/Execution semantics. A zero process exit without valid required outputs is insufficient for SUCCEEDED.

Do not generate one source for display and another for execution. The Run's frozen source artifact is both its historical Code view and the program the executor attempts to launch. Later generator versions may render different code from similar old IR; they never rewrite that historical artifact.

## Code Generation invariants

1. Generated Python is the actual attempted ML workload; no hidden second ML implementation executes the experiment.
2. Working Pipeline Code is a read-only, mutable preview; preview generation creates no Run, training, historical artifact, or MLflow history.
3. Historical Run Code retrieves the exact persisted source; it is never regenerated and passed off as the original.
4. Generation accepts only an execution-ready resolved plan and never silently reinterprets configured intent.
5. Equivalent effective input, generator version, and generation configuration yield semantically equivalent, preferably byte-stable source.
6. Source excludes incidental timestamps, random names, and unstable ordering; it is readable and uses explicit public-library imports.
7. The target is never a feature; only missing target rows are excluded, and non-missing third classes are not discarded.
8. The frozen typed positive class and derived negative class govern prediction-score interpretation and evaluation.
9. The eligible rows are split before any learned preprocessing is fitted; learning uses training data only.
10. Excluded features and dormant operations do not execute; compatible included no-operation features are not dropped.
11. Per-feature operation order is preserved, and grouping occurs only when semantically equivalent and deterministic.
12. The persisted model artifact contains the complete fitted preprocessing-plus-classifier pipeline.
13. Only the three v0.1 classifiers are generated, with explicit execution-affecting values.
14. Logistic Regression uses explicit `l2 → lbfgs` and `l1 → liblinear` mapping; tree and forest random state comes from the frozen seed.
15. Positive-class metrics use the configured class and explicit zero-division behavior; Confusion Matrix has `[negative_class, positive_class]` order.
16. ROC-AUC never uses hard predictions and reports unavailability when scores or both held-out classes are absent.
17. Canonical results are structured and are not scraped from stdout.
18. Source does not embed raw Dataset contents, secrets, or machine-specific paths as domain identity.
19. Code-generation failure before Run creation creates no Run; the frozen source is generated once for the Run and is the exact source attempted.
20. Generator evolution never rewrites historical Run code.

## Non-normative churn walkthrough

For immutable `customers.csv`, target `churn`, positive class `"yes"`, and negative class derived as `"no"`, the effective features exclude `customer_id`; `age`, `income`, and `tenure_months` use median imputation then standard scaling; `city` and `plan` use most-frequent imputation then one-hot encoding. The model is Logistic Regression with `C=1.0`, `penalty="l2"`, `max_iter=1000`, and internal `solver="lbfgs"`. The split is test size `0.2`, seed `42`, stratified.

Conceptually, the source imports only the required pandas/sklearn and output helpers, obtains runtime Dataset/result/model destinations, loads the CSV, removes missing-`churn` rows, validates exactly two typed labels and the positive class, and constructs `X` from the five included non-target columns and `y` from `churn`. It makes `train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)` before fitting anything. A deterministic `ColumnTransformer` groups the three identically prepared numeric columns and two identically prepared categorical columns, each with its ordered imputer and scaler/encoder. A `Pipeline` couples that transformer to `LogisticRegression(C=1.0, penalty="l2", max_iter=1000, solver="lbfgs")`, fits on training data, predicts the test set, and calculates the required metrics with `"yes"` as positive and `["no", "yes"]` as Confusion Matrix order. It selects `"yes"`'s `predict_proba` column from the fitted class order for conditional ROC-AUC, writes the complete fitted pipeline to the provided model destination, and emits structured results to the provided result destination. This is a conceptual sequence, not a mandated full source template or storage protocol.

## Exclusions and remaining boundary

Code Generation v0.1 excludes regression, multiclass classification, XGBoost, arbitrary estimators or user Python, custom Python nodes or transformers, notebooks/Jupyter execution, Python-to-visual reverse parsing, bidirectional code editing, editable historical code, plugins, HPO, cross-validation, deployment/serving, cloud execution, containers, environment-file generation, and requirements-file generation as a Run artifact.

No blocking Code Generation v0.1 questions remain. Deterministic grouping, formatting, runtime input injection, generator-version provenance, and structured result emission are constrained above without fixing implementation details. The exact default numeric values and selected supported dependency versions must be resolved and recorded by implementation before execution; they do not authorize implicit library defaults.

Persistence still needs to define the local workspace root; Project directories; Dataset artifact storage; Run artifact storage; exact generated-source, structured-result, and stdout/stderr paths; model serialization format; artifact reference representation; atomic writes and finalization; integrity and corruption behavior; deletion and retention; and MLflow local storage placement. Those questions do not block this Code Generation contract.

The older [prototype scope](../prototype.md), [architecture](../architecture.md), [vision](../../VISION.md), and [roadmap](../../ROADMAP.md) discuss a broader future model/task set or describe execution and generated Python as parallel consumers of IR. The current v0.1 specifications narrow the task to binary classification with three classifiers and make generated Python the executed workload. The older documents remain unchanged.
