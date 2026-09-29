# Pipeline IR — Prototype v0.1

## Purpose and contract status

Pipeline IR v0.1 is **the canonical, serializable description of the current
executable ML experiment configuration of an ML Studio Project**. Its primary
responsibility is to represent user experiment intent independently of UI state
and specific ML-library implementation classes.

“Executable configuration” describes its purpose, not a guarantee that every
editable state is ready to execute. Working Pipeline IR may be incomplete,
invalid, or stale. Only validated intent may proceed to execution.

This document formalizes the decided v0.1 structure and semantics. Requirements
expressed as must/must not and the invariant section are normative. Illustrative
values and the full churn example are non-normative. This is a domain contract,
not an implemented schema model, API, database design, or execution engine.

```text
Project
├── Dataset
├── Working Pipeline IR (mutable)
└── Runs
    ├── Run 001 → frozen Pipeline IR snapshot
    └── Run 002 → frozen Pipeline IR snapshot
```

The contract supports visual configuration, validation, execution, generated
Python, Run history, comparison, and future AI reasoning without adding those
systems' representations to the IR.

## Relationship to existing specifications

[Project v0.1](project-v0.1.md), [Dataset v0.1](dataset-v0.1.md), and the frozen
[User Journey v0.1](user-journey-v0.1.md) supply the current domain and product
boundaries. This contract preserves their immutable source, mutable working
configuration, immutable Run history, binary classification, and limited
preparation/model scope.

Target-missing policy, positive-class intent, name-keyed features, and ordered
operations resolve previously deferred details rather than contradict those
specifications. Project target selection and the Dataset role view must agree
with IR intent before execution; inconsistent intermediate state must be repaired,
not treated as competing authoritative execution configuration. Dataset semantic
interpretation remains outside the IR. No persistence ownership is chosen here.

One qualification needs explicit visibility: User Journey promises equivalent
splits for identical Dataset identity, target, and split configuration. This
contract also requires identical **eligible target rows**. If source
interpretation changes which rows are eligible, the earlier three-item condition
alone is insufficient. Execution must establish eligibility deterministically;
this document does not silently revise User Journey.

Older-document differences remain separate:

- [Prototype scope](../prototype.md) and [roadmap](../../ROADMAP.md) include
  regression and leave broader classification questions open. This contract is
  binary-classification-only.
- The older prototype lists XGBoost, and [architecture](../architecture.md) and
  [vision](../../VISION.md) include it in the intended ecosystem. It is not an IR
  v0.1 model type. The older Feature Engineering label is Prepare in User Journey.
- Architecture and [ADR 0001](../decisions/0001-use-pipeline-ir.md) say the schema
  is not yet finalized. This document supplies the decided v0.1 contract while
  preserving their architectural separation; older status text remains unchanged.

## Intent, validation, and execution separation

```text
Dataset + Working Pipeline IR + current domain context
                         ↓
                     Validator
                         ↓
                 Valid / Invalid
                   ↓         └─ stop; preserve intent for repair
        Effective Execution Plan
                   ↓
                Executor
                   ↓
                  Run
```

IR represents **user intent**. Validation determines whether that intent is
executable against the referenced Dataset and current context. The valid path
means no blocking validation issues; non-blocking issues may remain. Only that
path derives an effective execution plan. Execution consumes that derived plan;
it must not treat editable IR as runtime state.

The diagram shows responsibilities, not a lifecycle implementation. A Run freezes
configuration when execution successfully begins, before any training outcome is
known; “successfully begins” does not mean training must finish successfully.
IR must not contain estimator objects, fitted transformers, trained models,
execution results, or runtime state.

## Top-level contract and version

The chosen shape is:

```text
PipelineIR
├── ir_version
├── dataset
│   ├── dataset_id
│   └── fingerprint
├── target
│   ├── column
│   ├── positive_class
│   │   ├── value
│   │   └── value_type
│   └── missing_value_policy
├── features
│   └── <column_name>
│       ├── included
│       └── operations[]
├── model
│   ├── type
│   └── parameters
└── split
    ├── test_size
    ├── random_seed
    └── stratify
```

These are the v0.1 top-level sections; no evaluation section is included. Binary
classification is the v0.1 task boundary, not an additional task-selection field.
One canonical representation serves both incomplete/editable and execution-ready
Working Pipeline state. There is no separate `DraftPipelineIR` or second draft
serialization format. Unconfigured top-level configuration can be null, and
`features` can initially be empty. Before a Dataset is attached, `dataset` may
also be null. Population evolves as the user configures the experiment; no fake
placeholder values are required merely to resemble an execution-ready shape.
Validation determines readiness and requires the necessary configuration to be
resolved before execution.

For example, this **non-normative incomplete intent** uses the same representation
as the complete churn example below. Its fingerprint is illustrative:

```json
{
  "ir_version": "0.1",
  "dataset": {
    "dataset_id": "ds_123",
    "fingerprint": "illustrative-content-fingerprint"
  },
  "target": null,
  "features": {},
  "model": null,
  "split": null
}
```

`ir_version` is explicitly `"0.1"`, identifying this contract's structure and
semantics independently of application release versions. Future incompatible
evolution may require migration/version handling. No migration framework is
defined here; an unsupported version must not be interpreted as v0.1 by accident.

## Dataset reference and replacement

`dataset.dataset_id` identifies the intended Dataset entity;
`dataset.fingerprint` identifies its exact immutable source contents. Both must
be compatible with the referenced source. Filename is not identity. The hash
algorithm is not selected here.

The reference supports compatibility validation, stale-pipeline detection,
reproducibility, and association between intent and source. Raw contents,
Dataset Profile, and the full schema are not embedded or duplicated. A
fingerprint does not itself preserve an artifact or reconstruct missing contents.

Dataset replacement must not silently rewrite IR:

```text
Project active Dataset:       ds_001 → ds_002
Working Pipeline reference:   ds_001 (unchanged)
Result: stale; reconciliation/revalidation required before execution
```

Only after explicit reconciliation against the replacement succeeds may the
Working Pipeline adopt its Dataset ID and fingerprint. Matching column names
alone do not prove compatibility. Target, semantic overrides, and Working
Pipeline compatibility require review as established by Dataset v0.1. Historical
Runs and their old references remain unchanged. No reconciliation algorithm or
UI flow is prescribed.

## Target and positive class

Target intent contains `column`, `positive_class`, and `missing_value_policy`.
The column must exist in the referenced Dataset, and the effective target must
contain exactly two usable classes. Numeric `0/1` is not required; labels such
as `yes/no` can represent binary classes.

`positive_class` must explicitly identify one of those classes before execution.
It determines the intended interpretation of Precision, Recall, F1, the confusion
matrix, and any future supported ROC-AUC. ML Studio may suggest a likely value,
but the effective value must be visible and user-confirmable. Lexical, numeric,
or library class ordering must not silently determine user intent.

Positive class is a typed scalar with `value` and `value_type`, for example
`{"value": "yes", "value_type": "string"}` or
`{"value": 1, "value_type": "integer"}`. The v0.1 type vocabulary is exactly
`string`, `integer`, `float`, and `boolean`. Preserve source-compatible scalar
semantics rather than normalizing all labels to strings. The value and its type
must correspond to an observed usable target class under Dataset parsing/target
semantics. The wrapper is structured, but its value cannot be an array, object,
datetime, or arbitrary serialized Python value. Implementation-specific
Python/JSON conversion and target encoding mechanics remain outside this contract.

For v0.1, `missing_value_policy` is fixed to `"exclude_rows"`. Missing target
values are never imputed: their rows are excluded from supervised training and
evaluation. This population change must be visible and acknowledged by the user,
not silently performed. The field expresses the policy; no acknowledgement UI
state or event record is added to the IR.

This policy authorizes exclusion of missing targets only, not arbitrary invalid
labels, silent class merging, or feature-based row removal. Missingness and
eligibility interpretation and exclusion timing belong to later execution
semantics. Insufficient classes after exclusion block execution.

### Target changes

Changing the target requires revalidation of all target-dependent intent:

- The new target must not remain an input feature and must be absent from the
  reconciled feature map.
- The former target returns to the reconciled non-target feature map with
  `included: false`. It must not automatically become included; the user must
  explicitly enable it if they want it as a feature.
- Positive-class selection must be resolved for the new target.
- Binary suitability and missing-target population effects must be re-evaluated.

Dependent edits need not happen atomically, but unresolved state cannot execute.
Changing current target intent never changes historical Runs.

## Features and participation

`features` is a mapping **keyed by Dataset column name**, not an array. No stable
column IDs, graph nodes, or independent column registry are introduced. Dataset
validation must establish usable unique names so references are unambiguous.

Each represented feature contains an explicit boolean `included` and an ordered
`operations` array. Only explicitly included, validated features may become
model inputs. Once a target is configured and the Working Pipeline is reconciled
with the referenced Dataset, every non-target Dataset column must appear exactly
once as a feature key, including excluded columns with `included: false`. The
target must not appear in `features`, even as an excluded entry; it is represented
only in `target`.

```text
Dataset columns = feature keys ∪ {target column}
feature keys ∩ {target column} = ∅
```

This completeness requirement applies to reconciled intent with a configured
target. An initially incomplete or temporarily stale Pipeline may violate it
during Dataset replacement or target changes, but execution readiness requires
the relationship to be restored. Missing or stale feature keys are reconciliation
issues even if a stale entry is marked excluded. No omitted column is implicitly
included.

An excluded feature may retain its operations. For example, an excluded `age`
entry may retain median imputation followed by standard scaling. This is valid
configuration state: the operations remain inspectable user intent but do not
execute while `included` is false. Re-enabling the feature requires validation
against current context, not blind reuse of earlier readiness. Retained operations
may be incompatible with an excluded feature's current semantics without blocking
execution: they remain dormant and must not be silently deleted.

A Run's frozen IR preserves configured excluded-feature state rather than silently
pruning it to match effective inputs. This does not define snapshot storage.

## Supported operations and ordering

An operation array represents intended order. Its extensibility does not permit
arbitrary ordering or arbitrary transformations in v0.1. The UI produces supported
sequences; unsupported combinations and orderings cannot execute. Incompatibility
in effective, included-feature operations blocks readiness; dormant excluded
configuration follows the non-blocking rule below. Serialization alone does not
establish readiness or expand the supported operation vocabulary.

| Family | Operation shape | Allowed choices |
| --- | --- | --- |
| Imputation | `{"type": "impute", "strategy": "median"}` | `mean`, `median`, `most_frequent` |
| Scaling | `{"type": "scale", "method": "standard"}` | `standard`, `min_max`, `robust` |
| Encoding | `{"type": "encode", "method": "one_hot"}` | `one_hot` |

Values in the shape column illustrate one allowed choice, not a default.
Mean and median require appropriate numerical semantics. Most-frequent imputation
can apply where compatible, including categorical features. Numerical storage
alone does not authorize numerical preparation for a semantically categorical
identifier or label.

No scaling operation means no scaling is configured. No encoding operation means
no encoding is configured. Do not serialize a `none` operation for either; the
User Journey's “none” choices are represented by absence of those operations.
An empty array means no transformations are configured for that feature, not
that raw values are necessarily compatible with the model.

### Narrow v0.1 grammar

```text
Numerical feature:   raw → optional imputation → optional scaling
Categorical feature: raw → optional imputation → optional encoding
```

Each optional stage occurs at most once. For example, median imputation followed
by standard scaling expresses the numerical sequence. Scaling followed by
imputation is a validation issue, as are repeated or unsupported stages, and
blocks execution when effective. The validator must not silently reorder intent.
Scaling plus encoding on the same
feature is not one of these v0.1 sequences.

Exact compatibility for Dataset semantic types, including binary interpretation,
requires validation rules; this grammar does not promise support for text,
datetime, identifier, or unknown features merely because a sequence can be stored.
No arbitrary graphs, nodes, edges, ports, branching, plugins, or user-defined
operations are introduced.

## Editable state and validation boundary

Working Pipeline IR may retain incomplete, invalid, or stale intent so users can
understand and repair it. Examples include a replaced Dataset reference, a
missing feature column, a changed target, scaling retained after a semantic
change to categorical, unsupported operation order, or no usable included
features. Every edit need not atomically rewrite dependent configuration.

Validation must distinguish executable intent from repairable draft state and
must cover at least:

- Dataset identity/fingerprint and active-Project compatibility;
- target existence, binary suitability, positive-class validity, and the fixed
  missing-target policy;
- agreement with current Project target context and target/feature separation;
- feature existence, reconciled map completeness, explicit participation, and
  at least one usable input;
- supported operations, meaningful order, and compatibility with effective
  Dataset semantics for active feature preparation;
- model type and parameter validity;
- split configuration validity for the eligible target population.

Validation distinguishes only two conceptual severities here:

- **Blocking issues:** prevent execution. These include missing required intent,
  unreconciled Dataset/target/feature relationships, and incompatible effective
  operations on included features.
- **Non-blocking issues:** deserve user attention but do not affect the effective
  plan. Incompatible dormant operations on an excluded feature produce such an
  issue/warning and do not prevent execution.

For example, `age` may retain `{"type": "scale", "method": "standard"}` with
`included: false` after its effective semantic type becomes categorical. The
scaling is dormant: preserve it, report a non-blocking issue, and omit age from
the effective plan. If the user enables age, that same incompatible operation
becomes blocking and must be resolved before execution. This rule concerns
dormant operation compatibility; it does not waive feature-map reconciliation
or introduce unsupported operation families.

Execution readiness requires **no blocking validation issues**, not the absence
of all warnings. Excluded-feature configuration never becomes an effective input
merely because it exists.

Validation resolves physical/inferred/effective semantic interpretation from the
Dataset domain. Editable IR does not duplicate that schema or semantic overrides.
A semantic change can invalidate intent without changing source contents or their
fingerprint. A later Run specification must freeze the relevant interpretation
so historical reproducibility does not depend on current mutable metadata.

IR with blocking issues, including unreconciled stale context, must not execute.
Dormant semantic incompatibilities alone do not make the effective plan invalid.
Validation status, error
payloads, runtime objects, and repair UI state are not additional IR sections.
No validator implementation, error-code enums, API response schema, frontend
warning components, localization, or detailed validation result objects are
specified here.

## Model intent, resolved parameters, and library independence

`model.type` is exactly one of `logistic_regression`, `decision_tree`, or
`random_forest`. These are ML Studio domain identifiers. No Python import paths,
library class names, serialized estimators, or fitted models belong here.

The curated parameter surface is:

| Model type | Parameters |
| --- | --- |
| `logistic_regression` | `C`, `penalty`, `max_iter` |
| `decision_tree` | `max_depth`, `min_samples_split`, `min_samples_leaf` |
| `random_forest` | `n_estimators`, `max_depth`, `min_samples_split`, `min_samples_leaf` |

Execution-ready IR must carry resolved explicit values for these configured
parameters. A UI may label a selection “default,” but the IR must record its
resolved value rather than rely silently on a library's current or future
default. An incomplete draft with unresolved required values is not executable.
Exact constraints, supported combinations, and defaults are not chosen here.

Execution-specific deterministic settings not exposed by these controls may be
resolved by the execution contract. This is not permission to depend on hidden,
unversioned library behavior or to expose every constructor option. The execution
and Run specifications must account for these settings and their provenance.

IR semantics belong to ML Studio. For example, `type: "scale", method:
"standard"` denotes ML Studio's standard-scaling operation, not an import path
such as `sklearn.preprocessing.StandardScaler`. An adapter may map it to that
library for v0.1; mapping, library versions, and implementation objects remain
outside editable IR. The same principle applies to model identifiers.

## Split and evaluation boundary

`split` contains explicit `test_size`, `random_seed`, and `stratify` choices for
a **single train/test split**. Every Run freezes the configuration it used.

Two Runs with the same Dataset contents/identity, target, eligible target rows,
and split configuration must receive equivalent deterministic splits. Changing
the model or feature preparation must not accidentally change the evaluation
population. Exact splitting algorithms, exclusion timing, and random-state
propagation belong to the execution specification.

No cross-validation, nested cross-validation, repeated holdout, separate
validation datasets, or hyperparameter optimization belongs to v0.1.

Standard binary-classification execution produces Accuracy, Precision, Recall,
F1, and Confusion Matrix as outputs. These are not selectable IR configuration.
There is **no `evaluation` section**, metric selection, optimization metric,
custom metric, or evaluation result field. ROC-AUC remains conditional and
deferred until execution defines a clear score/probability contract.

Classification-threshold tuning is not supported. There is no threshold field;
execution uses the supported estimator's standard prediction behavior. Its exact
mapping to the chosen positive-class semantics remains execution-spec work.

## Effective execution plan and Run snapshot boundary

The effective execution plan is derived from validated IR, the referenced
Dataset, its effective semantic context, and execution semantics. Preserved
configuration can be ineffective: an excluded feature's operations remain in IR
but do not enter effective model input. Non-blocking dormant incompatibilities
do not prevent deriving the plan when no blocking issues remain. Derivation must
not erase the canonical
user configuration or silently repair invalid active intent.

This specification neither defines a plan schema nor makes it another persisted
canonical representation. Whether/how to persist a plan is deferred.

At execution start, a Run must be associated with frozen experiment configuration.
The future Run specification must preserve enough context to establish exact
Dataset contents, configured Pipeline IR (including excluded-feature intent),
target semantics, relevant semantic interpretation, split configuration, and
execution environment/provenance. Current edits must not alter that history.
These are obligations, not Run fields. Runtime and library versions must not be
added to editable IR simply because reproducibility needs them elsewhere.

## Full non-normative churn example

**NON-NORMATIVE:** the following complete example uses the frozen shape, not
mandatory defaults, a real Dataset, or a fully validated library configuration.
Assume fictional `customers.csv` has unique columns `customer_id`, `age`,
`income`, `city`, `plan`, `tenure_months`, and `churn`; age/income/tenure are
appropriate numerical features, city/plan are categorical, and usable churn
labels are `yes/no`. The illustrative fingerprint is a placeholder for the
Dataset's actual deterministic fingerprint, not a proposed algorithm or format.
The user has acknowledged exclusion of missing-target rows.

```json
{
  "ir_version": "0.1",
  "dataset": {
    "dataset_id": "ds_customers_example",
    "fingerprint": "illustrative-content-fingerprint"
  },
  "target": {
    "column": "churn",
    "positive_class": {"value": "yes", "value_type": "string"},
    "missing_value_policy": "exclude_rows"
  },
  "features": {
    "customer_id": {
      "included": false,
      "operations": []
    },
    "age": {
      "included": true,
      "operations": [
        {"type": "impute", "strategy": "median"},
        {"type": "scale", "method": "standard"}
      ]
    },
    "income": {
      "included": true,
      "operations": [
        {"type": "impute", "strategy": "median"},
        {"type": "scale", "method": "standard"}
      ]
    },
    "city": {
      "included": true,
      "operations": [
        {"type": "impute", "strategy": "most_frequent"},
        {"type": "encode", "method": "one_hot"}
      ]
    },
    "plan": {
      "included": true,
      "operations": [
        {"type": "impute", "strategy": "most_frequent"},
        {"type": "encode", "method": "one_hot"}
      ]
    },
    "tenure_months": {
      "included": true,
      "operations": [
        {"type": "impute", "strategy": "median"},
        {"type": "scale", "method": "standard"}
      ]
    }
  },
  "model": {
    "type": "logistic_regression",
    "parameters": {"C": 1.0, "penalty": "l2", "max_iter": 1000}
  },
  "split": {"test_size": 0.2, "random_seed": 42, "stratify": true}
}
```

Every non-target source column is represented exactly once, and the target is
absent from the feature map. Its positive class is a typed string scalar.
Source contents/semantics are not copied, and there is no evaluation configuration.
Numerical example values do not freeze
defaults or settle later parameter compatibility rules.

## Mutation examples

These describe edits to intent, not APIs, commands, or event formats. Every case
preserves historical Runs and requires the relevant readiness checks.

| Change | Working Pipeline semantics |
| --- | --- |
| Model switch | Change `model.type` from `logistic_regression` to `random_forest`; resolve its curated `n_estimators`, `max_depth`, `min_samples_split`, and `min_samples_leaf` values. Logistic-specific parameters are not silently treated as Random Forest parameters. Until resolved and valid, the new intent cannot execute. |
| Scaling change | For `age`, change the existing scale method from `standard` to `robust`, retaining its position after imputation. Revalidate compatibility. |
| Feature exclusion | Change `features.age.included` from true to false; preserve its imputation/scaling array. The effective plan omits age while the IR and subsequent snapshot retain the configuration. If its semantic type later becomes incompatible, report a non-blocking dormant issue; re-enabling makes that incompatibility blocking. |
| Dataset replacement | The Project adopts `ds_002`; IR still names `ds_001` and its old fingerprint. Mark the working context stale; update the reference only after explicit successful reconciliation. |
| Target change | Replace `churn` with another candidate column; remove the new target from the reconciled feature map and restore `churn` with `included: false`. Resolve the new typed positive class, binary suitability, missing-target effects, and dependent configuration. Only explicit user action can enable the former target as a feature. |

## Normative Pipeline IR invariants

1. IR represents experiment intent, not execution results.
2. Working Pipeline IR is mutable.
3. A Run freezes the relevant IR used for its execution.
4. IR references exact Dataset identity and content fingerprint.
5. Dataset contents are not embedded in IR.
6. Target intent is explicit before execution.
7. Positive class is explicit before execution as a source-compatible typed scalar
   using `string`, `integer`, `float`, or `boolean`, matching an observed usable class.
8. Missing target values are never feature-style imputed in v0.1.
9. Missing-target rows use the explicit `exclude_rows` policy with visible,
   acknowledged population effects.
10. The current target cannot participate as an input feature and is absent from
    the reconciled feature map.
11. Former targets return to the reconciled feature map with `included: false`;
    only explicit user action can enable them.
12. Features are keyed by column name and enumerate every non-target Dataset
    column exactly once when the target is configured and intent is reconciled.
13. Every represented feature has explicit inclusion state.
14. Excluded features retain configured operations without executing them;
    dormant semantic incompatibilities are non-blocking and are not silently erased.
15. Feature operations are ordered arrays.
16. Operation order has semantic meaning and must not be silently rearranged.
17. Only the defined v0.1 operation grammar is executable.
18. One canonical IR represents incomplete, invalid/stale, and execution-ready
    intent; there is no separate draft format or requirement for fake values.
19. Execution requires no blocking validation issues. Non-blocking dormant
    issues may remain; re-enabling a feature requires its effective operations
    to pass validation.
20. Dataset replacement does not silently rewrite IR.
21. Semantic compatibility is validated against Dataset effective semantics.
22. Model types are ML Studio identifiers, not library class/import paths.
23. Execution-ready model parameter values are resolved explicitly rather than
    silently inherited from library defaults.
24. Split configuration is explicit and frozen for each Run.
25. Evaluation results do not belong in IR.
26. Evaluation metric selection does not belong in IR v0.1.
27. Threshold tuning does not belong in IR v0.1.
28. Fitted transformers and models do not belong in IR.
29. UI state does not belong in IR.
30. The IR contract is explicitly versioned.
31. Execution derives an effective plan from valid IR rather than using editable
    intent as runtime state.

## Explicit exclusions from IR

The following do not belong in Pipeline IR v0.1:

- Project name, description, problem statement, or user objective prose;
- raw Dataset contents, Dataset Profile, full Dataset schema, EDA outputs, charts;
- recommendations, AI conversation/context, or AI recommendations;
- UI navigation state, selected tab/Bench, component state, frontend definitions;
- generated metric values, predictions, or confusion-matrix values;
- trained/fitted model objects or fitted transformer objects;
- MLflow IDs, logs, runtime process state, or library import paths;
- API endpoint information or environment/library version records.

Exclusion from IR does not remove legitimate Project context or Run provenance
from their own domains. A deliberately chosen class label in target configuration
is not an invitation to embed dataset rows or treat IR as safe to log wholesale.

## Out of scope

This document does not define Run schema, execution engine or library-adapter
implementation, code-generation algorithm, MLflow mapping, persistence/database
schema, frontend architecture, API contracts, AI Advisor behavior, or an IR
migration engine. It selects no frontend/backend frameworks and implements no
Pydantic or TypeScript models.

Arbitrary custom Python, arbitrary DAG workflows, plugin systems, custom
operations, regression, multiclass classification, hyperparameter optimization,
and AutoML are outside v0.1. No feature creation, PCA, polynomial features,
log/sqrt transforms, automated feature selection, SMOTE/resampling, or outlier
treatment is added to the frozen Prepare scope.

## Remaining IR-level questions

**No blocking Pipeline IR v0.1 design questions remain.**

Incomplete intent uses the same canonical representation, positive class uses
a typed scalar, reconciled feature maps enumerate all and only non-target
columns, and dormant excluded-feature incompatibilities are non-blocking.
These decisions do not introduce new capabilities or change the architecture.
Deferred Run, Execution, and Code Generation concerns remain separated below;
this design status does not claim those contracts or executable validation exist.

## Interactions with later specifications

### Run specification

Define the exact frozen semantic context, relationship to the configured IR
snapshot, Dataset artifact retention/reference, execution provenance, environment
and library version capture, and Run identity/lifecycle. Preserve excluded-feature
configuration and historical target/split meaning without depending on current
Project metadata. No Run fields are chosen in this document.

### Execution specification

Define exact operation-to-library mappings, parameter constraints/defaults and
supported combinations, training-only fitting, leakage prevention, deterministic
split algorithm, target-row exclusion timing/eligibility, random-state
propagation, estimator prediction semantics, conditional ROC-AUC score/probability
contract, and execution failure behavior. Resolve execution-specific settings
without implicit mutable library defaults. No execution mechanism is chosen here.

### Code-generation specification

Define generation from current Working Pipeline IR and from frozen historical
Run configuration, equivalence expectations between Python and ML Studio
execution, and library/version assumptions. Preserve the two explicitly identified
read-only Code contexts. Generation and treatment of incomplete current intent
must not make invalid configuration appear executable.
