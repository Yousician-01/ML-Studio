# User journey — Prototype v0.1

## Purpose and scope

The prototype should demonstrate that a user can take a small tabular
binary-classification problem from source data to a reproducible baseline ML
Experiment through a visual workflow while retaining visibility into Python.
It should prove the interaction model, not broad ML coverage.

This document defines intended user experience and product flow, not implemented
capabilities. [Project v0.1](project-v0.1.md) and
[Dataset v0.1](dataset-v0.1.md) govern domain relationships and take precedence
over older broad planning documents where scope differs. The
[vision](../../VISION.md) supplies product principles; the proposed
[architecture](../architecture.md) supplies context without prescribing UI design.

Known differences from older planning remain explicit:

- The [prototype scope](../prototype.md) and [roadmap](../../ROADMAP.md) include
  regression, and the prototype leaves multiclass evaluation questions open.
  This journey follows the newer binary-classification-only scope.
- The older prototype calls preprocessing **Feature Engineering**. This journey
  uses **Prepare**, combining basic preprocessing and feature inclusion without
  adding a separate Cleaning or Feature Engineering Bench.
- The older prototype lists XGBoost as a candidate, and architecture includes it
  in the intended ecosystem. It is excluded from this v0.1 journey, whose exact
  three-model set is frozen below.
- Older plans include an AI Advisor prototype. This journey defines a workflow
  that does not depend on AI and leaves AI behavior to separate work; it does not
  silently remove that broader roadmap item.

## Workspace and navigation

The primary workspace is:

```text
Project → Data → Explore → Prepare → Train → Evaluate
                      Supporting views: Runs, Code
```

These areas form a workspace, not a rigid wizard. Users can move backward and
forward between available areas without arbitrary “Complete Step” actions.
Prerequisites govern capabilities, not whether someone visited an earlier Bench.
Runs and Code are supporting views, not mandatory sequential Benches.

| Area or capability | Prerequisite and behavior |
| --- | --- |
| Project | Creation establishes the workspace; Dataset upload is separate. |
| Data | Available once the Project exists. |
| Explore | Source exploration requires an accepted, readable Dataset; target-specific observations require a selected target. |
| Prepare | Requires an accepted Dataset. Configuration may remain incomplete while the target is unset. |
| Train | Configuration must remain accessible for review and correction once there is a Dataset. Execution requires sufficient valid experiment configuration, including a valid target. |
| Evaluate | Results require a selected completed Run with evaluation results. A failed attempt does not supply successful evaluation. |
| Runs | History becomes useful once any Runs exist, including attempts without successful results. |
| Code | Current code requires enough Working Pipeline configuration to generate meaningful Python. Historical code uses a selected Run's frozen configuration independently of current working readiness. Both views are read-only and identify their context. |

An unavailable capability explains its prerequisite and where to address it.
An area may show an explanatory empty state before its capability is available;
this does not require a particular navigation implementation. Working-state
invalidation must not prevent reviewing existing historical Runs.

## Project creation

The user supplies a Project name and problem statement, may add a description,
and sees the task type explicitly as **binary classification**. There is no
promise of other selectable tasks. Description remains optional, consistent with
Project v0.1: it summarizes the work, while the problem statement says what is
being predicted.

Optional success/objective context describes what matters in evaluation, for
example: “Missing actual churners is more costly than contacting customers who
would not churn.” It does not automatically choose a metric or model.

Creation opens the Project workspace with no Dataset required, no target yet,
an initially empty Working Pipeline, and no Runs. Returning after a restart
should recover persisted Project work as required by Project v0.1; the save
interaction is not selected here.

## Data

Data helps users understand and configure interpretation of the source. The user
uploads one CSV, sees whether parsing and acceptance succeeded, inspects columns,
reviews inferred physical and semantic types, overrides semantic interpretation
where appropriate, selects a target, and previews source rows.

The minimum useful summary includes row and column counts, missingness,
duplicate-row count, column names, physical types, inferred/effective semantic
types, and basic cardinality. Summaries not yet available must not look like
zero counts. Detailed charts belong in Explore.

Physical type describes parsed representation; semantic type describes meaning.
A numeric identifier is not automatically a useful numerical feature. The user
can distinguish inferred interpretation from an explicit override and can remove
the override. Recognizing text or datetime does not promise NLP or date-feature
support. Overrides do not change source values or bypass validation.

The target is selected from the active Dataset's columns. Feedback explains when
it cannot currently form a valid binary target. Two classes need not be numeric
`0` and `1`; labels such as `churn/stay` are valid in principle. The effective
target must represent exactly two classes after legitimate missing/invalid
handling, whose rules remain deferred. The UI must not imply that selecting a
column or labeling it binary is sufficient, or silently drop/merge classes.

Data does not destructively clean the source. Keep this distinction visible:

```text
Data: original source values and their interpretation
Prepare: Working Pipeline transformations applied to that source for execution
```

Invalid uploads give actionable feedback and do not replace an existing valid
Dataset. Dataset Preview is informational, not evidence that the entire Dataset
is valid or that source statistics have changed.

## Explore

Explore exposes evidence about the source Dataset before modeling. The minimum
scope is target distribution and class imbalance, missing-value overview,
numerical distributions, categorical distributions, basic box plots, correlation
where applicable, high-cardinality observations, duplicate-row observations, and
evidence of possible identifiers.

Views identify the Dataset and whether they describe the full source or a
partition; they must not imply that source charts represent transformed data.
Target-dependent views explain when selection is missing. Inapplicable summaries
explain why rather than fabricate values. Correlation is descriptive, and a
box-plot observation does not automatically authorize outlier removal.

Separate facts from interpretation and recommendations:

| Evidence | Separate possible recommendation |
| --- | --- |
| “14.2% of `income` values are missing.” | “Consider median imputation.” |
| “`customer_id` has 99.9% unique values.” | “This may be an identifier and could be excluded.” |

Possible-identifier labels must be presented as uncertain interpretations backed
by observations. Explore primarily exposes evidence; deterministic checks or AI
may offer separately identified recommendations later. Neither the observations
nor viewing them silently changes configuration. AI behavior is not defined here.

Full-source inspection must not be presented as permission to fit preprocessing
on held-out data. v0.1 uses the single train/test split described in Train.
Repeatedly choosing configurations based on test results can influence subsequent
experiments; comparison must not suggest that those results constitute a fresh,
independent evaluation. This does not introduce additional evaluation schemes.

## Prepare

Prepare combines basic preprocessing and feature configuration in one area.
Every action configures the **Working Pipeline**; it never mutates the source
Dataset or historical Runs.

| Capability | Narrow v0.1 scope |
| --- | --- |
| Missing values | Mean or median imputation for appropriate numerical features; most-frequent imputation where appropriate |
| Scaling | None, StandardScaler, MinMaxScaler, RobustScaler for compatible numerical features |
| Categorical encoding | None or OneHotEncoder for compatible categorical features |
| Feature inclusion | Include or exclude a feature; the selected target cannot also be a feature |

Users can inspect which columns each configured transformation affects and its
relevant choices, then change or remove it. Unsupported combinations are visible
as issues to resolve. Excluding a column removes it from feature use, not from
the immutable source. These choices freeze the v0.1 Prepare surface. Selecting
none for scaling or encoding does not bypass model compatibility checks.
Feature creation, PCA, polynomial features, log/sqrt transforms, automated feature
selection, SMOTE/resampling, outlier removal/treatment, and arbitrary transformers
are excluded; they remain future possibilities.

### Defaults and feedback

Sensible defaults may be proposed, but selected defaults must be visible as
Pipeline configuration and remain inspectable and changeable. There is no opaque
“magic clean dataset” action or hidden transformation.

Configuration summaries and plain-language explanations should make the intended
effect understandable. v0.1 provides neither persisted nor interactive
transformed-row previews and does not continuously materialize transformed
Datasets for preview. The immutable source preview remains available through
Data. If future versions add transformed previews, they should be clearly labeled
derived/ephemeral views of Working Pipeline state, not new source Datasets.

## Train

Train answers: **“What model am I about to run, and with what configuration?”**
The user reviews the active Dataset, target, feature/preprocessing choices,
model, exposed hyperparameters, and train/test configuration before execution.

### Model and split configuration

v0.1 supports exactly Logistic Regression, Decision Tree Classifier, and Random
Forest Classifier: a linear baseline, a simple tree, and an ensemble tree. The
goal is to demonstrate model switching between Runs and meaningful comparison.

The curated model-specific UX surface is frozen to:

| Model | Exposed parameters |
| --- | --- |
| Logistic Regression | `C`, `penalty`, `max_iter` |
| Decision Tree Classifier | `max_depth`, `min_samples_split`, `min_samples_leaf` |
| Random Forest Classifier | `n_estimators`, `max_depth`, `min_samples_split`, `min_samples_leaf` |

Defaults are visible and parameters should have human-readable explanations.
Exact constraints, supported combinations, defaults, validation rules, execution
mapping, and control widgets remain for later specifications. Other estimator
constructor options are not part of this UX surface. ML Studio may control
randomness/determinism without exposing a separate model-specific control.

Train makes **test size, random seed, and stratification** visible and explains
their purpose. v0.1 uses a **single train/test split**. Favor reproducible splitting and class-preserving stratification
where appropriate; unsupported split choices require feedback rather than a
silent fallback. Numeric defaults and exact execution semantics remain deferred.
Preprocessing must be described as fitted on training data and applied to held-out
data, consistent with the existing correctness boundary.

Each Run freezes its exact split configuration. Two Runs with equivalent exact
Dataset/source identity, resolved source interpretation, eligible target rows,
target, split configuration, and relevant execution/library implementation version
must have equivalent deterministic splits. Model/preprocessing changes alone must
not change the evaluation population. This does not promise identical splits across
parser/library changes that alter eligibility or splitting behavior. v0.1 does not add
cross-validation, nested cross-validation, separate validation datasets, repeated
holdout, or hyperparameter optimization.

### Readiness and execution

The execution action is unavailable for obvious invalidity: no readable Dataset,
no target, an invalid binary target, no usable feature columns, unresolved
incompatible preprocessing, missing required model/split configuration, or stale
configuration awaiting revalidation. Explain the blocker and where to correct
it. Detailed validation rules are separate work.

When valid configuration is executed, the interaction is conceptually:

```text
Working Pipeline + Dataset identity + target/objective context
                 + execution configuration → new Run
```

The new Run freezes the relevant configuration at execution start. Feedback
identifies the Run and distinguishes execution in progress, success, and failure
without pretending those outcomes are already known. Errors do not appear as
successful metrics. This does not prescribe Run internals, background execution,
progress percentages, cancellation, or concurrency behavior.

## Evaluate

Evaluate presents the results of a **selected completed Run**, clearly identifying
its Run, source Dataset, target, and model. It must not relabel historical results
using the current Project configuration. Results belong to the Run.

The small binary-classification metric set is Accuracy, Precision, Recall, F1,
and a confusion matrix. ROC-AUC remains conditional on a later execution
specification establishing a clear score/probability contract and valid evaluation
context; it is not required merely to fill a slot. No other metrics are added.
Unavailable or undefined metrics need explanations, not fabricated zero values.

Show class labels and the positive-class interpretation relevant to the displayed
metrics, along with which evaluation partition they describe. Detailed encoding,
metric calculation, and threshold rules remain deferred.

No metric is universally best. Success/objective context can help a user interpret
tradeoffs and may later inform recommendations; automated metric selection is
not defined. A high score is not proof of correctness or generalization.

## Runs view

Runs provides immutable experiment history. Users can list Runs, identify each
Run, see creation/execution time, model, execution outcome, and available key
metrics, and select a Run for inspection. Missing results must be distinguishable
from poor results. Historical records remain available when current working
configuration changes or becomes invalid.

Comparison supports **exactly two Runs at a time**, showing model, preprocessing
configuration, exposed model hyperparameters, split configuration, and key
evaluation metrics. It answers: “What changed between these two experiments, and
how did the measured results differ?” There is no arbitrary N-way comparison,
advanced comparison charts, statistical significance testing, experiment ranking,
or automatic winner selection.

Comparison must make differing Dataset, target, or split context visible rather
than suggest all metric differences are directly comparable. It does not declare
a universal winner or overwrite history. A formal Experiment grouping abstraction
is not designed here.

## Code view

Code supports the product promise of inspectable Python:

```text
Visual configuration → readable generated Python
```

Code supports two explicitly identified, **read-only** contexts:

- **Current Working Pipeline:** Python for the current editable configuration.
- **Selected historical Run:** Python for the frozen configuration associated
  with that Run, unaffected by later working edits or Dataset replacement.

Both support transparency and reproducing the corresponding ML behavior wherever
practical. Show necessary source/environment assumptions and distinguish missing
prerequisites from available code. Current code must not falsely appear current
or runnable after invalidating edits. Historical code must use the selected Run's
context rather than substitute current Project settings.

Users can identify which context they are inspecting. Current-code inspection
does not require training first when meaningful generation is possible; an invalid
current plan does not itself invalidate historical code. No embedded IDE,
editable generated Python, arbitrary custom Python, or Python-to-visual
synchronization is included. Code-generation implementation remains out of scope.

## Iteration, replacement, and stale configuration

### Editing after a Run

The user creates Run 001 with median imputation and a Random Forest configured
with 100 trees. They return to Prepare, change median to mean imputation, then
return to Train and change 100 trees to 300. The Working Pipeline now represents
the new plan; Run 001 retains the original configuration and results. Executing
the valid new plan creates Run 002. Working Pipeline Code reflects the new plan;
Code for Run 001 still represents median imputation and 100 trees. Evaluate and
historical Code identify whichever Run is explicitly selected.

### Dataset and upstream changes

On accepted replacement, the new Dataset becomes the active source. Historical
Runs remain intact and identifiable with their original source. Target selection,
semantic overrides, and Working Pipeline compatibility all require revalidation.
The interaction must not imply that old Runs used the replacement Dataset.
No replacement dialog or separate detach operation is designed here.

Target changes, semantic-type changes, or a column no longer being applicable to
a configured operation can also invalidate downstream configuration. Distinguish
**invalid** configuration with a known blocker from **stale** configuration whose
compatibility has not yet been revalidated. Both require visible feedback before
execution. Do not silently reuse a prior readiness judgment, discard user choices,
or invent compatible replacements. Users can navigate back to correct the plan.

## Errors and empty states

Errors answer what failed, why when known, and what the user can do next. For
example, an unreadable CSV should explain the known parsing problem and suggest
correcting the file; an incompatible transformation should identify the affected
choice and direct the user to Prepare. Do not invent a cause when it is unknown.

Raw Python tracebacks are not the primary experience. Technical details may be
available separately for debugging, with care not to expose source values,
credentials, or other sensitive data. Failed operations must not silently erase
the active source, current plan, or existing historical results.

| Situation | Conceptual guidance, not final UI copy |
| --- | --- |
| Data before upload | Upload one CSV to begin examining the source. |
| Explore or Prepare without a Dataset | Upload an accepted Dataset first. |
| Train without a valid target | Select or correct the target in Data. |
| Evaluate without Runs | Train a model to create the first Run. |
| Evaluate with only failed/incomplete attempts | No completed evaluation is available; inspect the attempt in Runs. |
| Runs without Runs | No Runs yet; configure and execute a Pipeline to begin history. |
| Current Code before meaningful configuration | Configure the Working Pipeline; identify what is still missing. Historical Code for an existing Run remains separately accessible. |
| Historical Code without a selected Run | Select an existing Run to inspect its frozen configuration. |

## Deliberate v0.1 exclusions

Regression, multiclass classification, NLP, computer vision, deep learning, LLM
training, arbitrary custom Python, arbitrary bidirectional visual/code editing,
model deployment, production monitoring, hyperparameter optimization, AutoML,
database connectors, multiple active Datasets, joins, complex feature engineering,
collaboration, authentication, cloud execution, distributed execution, and a
plugin marketplace are outside this journey's prototype scope.

Also excluded are transformed-row previews (persisted or interactive), feature
creation, PCA, polynomial features, log/sqrt transforms, automated feature
selection, SMOTE/resampling, outlier removal/treatment, arbitrary transformers,
models beyond the three listed in Train, arbitrary estimator-parameter exposure,
editable generated Python, and an embedded IDE.

Evaluation excludes cross-validation, nested cross-validation, separate validation
datasets, and repeated holdout. Run comparison excludes arbitrary N-way comparison,
advanced charts, statistical significance testing, ranking, and automatic winner
selection. These comparison exclusions do not remove the basic Explore charts.

## UX invariants

1. The original source Dataset is never silently mutated.
2. Every transformation configured in Prepare is inspectable, including defaults.
3. Prepare modifies Working Pipeline state, not historical Runs.
4. Historical Runs remain unchanged when the Working Pipeline changes.
5. Upstream changes trigger downstream compatibility revalidation.
6. Users can always identify which Run they are evaluating.
7. Code identifies either the current Working Pipeline or a selected historical
   Run's frozen configuration. Both are read-only, and current edits never change
   what historical Run code represents.
8. Unavailable actions explain their prerequisites.
9. Explicit visible configuration takes precedence over hidden ML behavior.
10. Users are not forced through a rigid wizard.
11. Comparison shows exactly two Runs and never labels either universally better.
12. Each Run freezes its split configuration; equivalent exact Dataset/source identity,
    resolved source interpretation, eligible target rows, target, split configuration,
    and relevant execution/library version produce equivalent deterministic splits.
13. Source-row preview remains available in Data; v0.1 has no transformed-row previews.

## Non-normative walkthrough

This fictional example explains the intended interaction; it is not an acceptance
test, a benchmark, or a promise that the configuration fits every churn problem.

1. Create **Customer Churn**, describe the prediction problem, and optionally note
   that missing churners is more costly than unnecessary contact.
2. Upload `customers.csv`, inspect schema and source rows, and select `churn`
   with `churn/stay` labels as the target, subject to binary-target validation.
3. In Explore, inspect class imbalance, missingness, and feature distributions.
4. In Prepare, exclude `customer_id`, configure median imputation for `age`,
   OneHotEncoder for `city`, and StandardScaler for appropriate numerical features.
   Inspect the configuration and explanations without a transformed-row preview.
5. In Train, select Logistic Regression, review visible model defaults, test size,
   seed, and stratification, resolve blockers, and create Run 001.
6. In Evaluate, inspect Run 001's Accuracy, F1, other available metrics, and
   confusion matrix with their class/partition context.
7. Open Code to inspect read-only Python for the current Working Pipeline, then
   explicitly select Run 001 to inspect code for its frozen configuration.
8. Return to Train, change the model to Random Forest, review compatibility and
   its curated parameters, and keep the same Dataset, target, and split
   configuration. Create Run 002 using an equivalent deterministic split.
9. Compare exactly Run 001 and Run 002: inspect model, preprocessing, exposed
   hyperparameters, split configuration, and metric differences without changing
   either record or declaring a universal winner. Run 001's code remains frozen.

## Complexity boundaries and document exclusions

The frozen journey uses three models, curated parameters, a single train/test
split, read-only Code for current and historical configurations, and two-Run
comparison. Historical Code is an explicit transparency requirement, not an
embedded IDE. Transformed previews, a richer model catalog, and advanced Run
analytics remain excluded; no additional infrastructure is prescribed.

Immutable history, revalidation, meaningful errors, and visible configuration are
essential correctness requirements even in a small prototype; they are not reasons
to introduce a dataset registry or generalized workflow engine.

This document does not define Pipeline IR schema, Run schema, execution engine,
persistence implementation, API endpoints, database schema, exact frontend
component tree, CSS/design system, MLflow mapping, AI context schema, or the
code-generation algorithm.

## Unresolved questions for later specifications

- What minimum incomplete Working Pipeline configuration supports meaningful
  current-code inspection, and how should remaining prerequisites be explained?
- What parameter constraints, supported combinations, defaults, and validation
  rules apply to the frozen curated controls? Execution mapping remains deferred.
- What precise execution semantics fulfill the frozen deterministic single-split
  requirement, including legitimate target handling and class interpretation?
- Will the execution specification establish the clear score/probability contract
  needed to include conditional ROC-AUC?

Transformation previews, Prepare scope, model/parameter exposure, both read-only
Code contexts, two-Run comparison, and the single train/test approach are resolved
v0.1 decisions, not open scope questions.
