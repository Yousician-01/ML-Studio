# Project — Prototype v0.1

## Purpose and scope

This conceptual product-domain specification defines a **Project** as the current
workspace for one ML problem. It describes intended behavior, not implemented
functionality. It is not a database schema, Pydantic model, TypeScript interface,
REST API contract, Pipeline IR definition, or MLflow schema.

The first supported task for this specification is **binary classification**.
The intended interaction is to create a Project, upload a CSV, select a target,
understand the Dataset, visually configure basic preprocessing, perform basic
EDA, configure features and a model, train, evaluate, inspect generated Python,
modify the working configuration, create another Run, and compare Runs.

This document follows the principles in the [vision](../../VISION.md), the
representation boundary in [architecture](../architecture.md), and
[ADR 0001](../decisions/0001-use-pipeline-ir.md). Pipeline IR design remains separate.

**Existing scope conflict:** the [README](../../README.md),
[roadmap](../../ROADMAP.md), and [bootstrap prototype scope](../prototype.md)
include classification and regression; the prototype document also leaves
multiclass evaluation questions open. This specification intentionally follows
the current instruction to start with binary classification only. It does not
revise those documents or settle their broader scope. Regression may be considered
after the core interaction model has been validated; it is not defined here.

## Domain hierarchy

```text
Project
├── Identity
├── ML Objective
├── Dataset (zero or one active source Dataset reference)
├── Working Pipeline (one current editable configuration, initially empty)
└── Runs (zero or more historical execution records)
```

These are conceptual relationships. Containment here does not require embedding
related records or their contents in one storage representation.

## Project identity

| Concept | Meaning and initial presence |
| --- | --- |
| Project ID | Stable, unique identity established at creation; independent of the name. No identifier format is chosen. |
| Name | Required human-readable name. Renaming does not change Project identity; names need not serve as unique identifiers. |
| Description | Optional short summary of the work or its context. |
| Problem statement | Required statement of what the user intends to predict; exists at creation. |
| Created timestamp | Records when the Project was created and remains unchanged. |
| Updated timestamp | Records the latest persisted change to Project-owned current state. Merely viewing the Project is not an update. |

**Description:** “Exploration of customer churn using historical subscription data.”

**Problem statement:** “Predict whether an active customer will churn within the
next 30 days.”

The description summarizes the work; the problem statement identifies the
prediction problem. They are separate concepts even if a user uses similar
wording. Timestamp formats and synchronization with Run lifecycle events are
not specified here.

## ML Objective

The Project contains the user's ML Objective:

- **Task type:** `binary_classification` for this specification, present at creation.
- **Target column:** initially unset; selected from the active Dataset once available.
- **User objective / success context:** optional, editable context about what
  matters when evaluating a solution.

For example, “Missing actual churners is more costly than contacting customers
who would not churn” expresses success context. The problem statement explains
**what is being predicted**; success context explains **what matters when
evaluating it**. Success context may be absent while the user clarifies the goal.
Its presence does not automatically choose a metric, threshold, or model.

This context belongs to the Project because it can later inform metric
recommendations, AI recommendations, and interpretation of experiments. AI
behavior and context representation are not defined here.

A selected target cannot be valid unless it belongs to the active Dataset.
Membership alone is not sufficient to establish suitability for binary
classification. Detailed target validation belongs to later specifications.

## Dataset relationship

A Project references **at most one active source Dataset**. Immediately after
creation it may reference none. The initial input direction is CSV, but Dataset
schema, storage, and profiling are separate concerns.

The Project stores the relationship to its active Dataset, not raw CSV contents
or dataset rows in Project metadata. This specification does not introduce
multi-dataset workflows or define replacement/detachment behavior. If such
changes are later supported, a target must not remain valid merely because it
was valid for a previous Dataset, and historical Runs must not be rewritten.

## Working Pipeline

A Project has **one current editable Working Pipeline**, which may initially
be empty or incomplete. It represents what the user is currently configuring
through ML Studio, not the last successfully executed configuration.

The user may add, remove, or modify preprocessing; change feature configuration;
change the model; and change hyperparameters. These edits change the Working
Pipeline without destroying prior history. An incomplete working configuration
is legitimate Project state and does not imply readiness to train.

The Working Pipeline is conceptually structured Pipeline state, consistent with
ADR 0001. Its schema, operation definitions, and execution validation are
deliberately not specified here. Persistent working configuration is domain
state; temporary, unsaved input in an editor is UI state.

## Runs and snapshot boundary

A Project can have zero or more Runs. A Run is created when the user begins
execution/training of the configured Pipeline. Each Run must receive a **frozen
snapshot of the relevant experiment configuration at its start**. It must not
depend on a live reference to the mutable Working Pipeline to explain what ran.

**Runs are immutable historical experiment records.** Later Project or Working
Pipeline edits must never reinterpret or overwrite an existing Run's execution
configuration. The historical context must remain tied to what was executed,
including the applicable Dataset and target, rather than whichever references
the Project holds later. Snapshot contents and representation belong to the
future Run specification.

```text
Working Pipeline A → Train → Run 001 (frozen configuration A)
        |
        └─ edit preprocessing, features, model, or hyperparameters
                ↓
Working Pipeline B → Train → Run 002 (frozen configuration B)

Run 001 still represents A. Run 002 represents B.
Further working edits change neither historical configuration.
```

Outcomes become known during execution and belong to that Run. Recording an
execution's own progress and outcome does not authorize editing its frozen
configuration or rewriting its recorded history. Detailed Run lifecycle and
result-finalization rules are deferred; no Run schema or MLflow mapping is
defined here.

## Project versus Run

| Concept | Question it answers |
| --- | --- |
| Project — current workspace | “What am I working on?” |
| Working Pipeline — current plan | “What am I currently planning to execute?” |
| Run — historical execution | “What exactly did I execute at that point in time, and what happened?” |

A Project's current plan can differ from every historical Run. Comparing Runs
must use their historical configurations and results, not substitute the latest
Working Pipeline for either Run.

## Lifecycle and legitimate incompleteness

The following describes a typical progression, not a rigid state machine or
stored status enumeration:

```text
Created → Dataset Attached → Target Selected → Pipeline Configured → Runs Created
```

| Stage | Information present or legitimately absent |
| --- | --- |
| Immediately after creation | Identity, name, problem statement, and task exist. Description and success context may be absent. No Dataset or target is required yet; the Working Pipeline may be empty and there are no Runs. |
| Dataset attached | One active Dataset is referenced. Target selection and Working Pipeline configuration may still be incomplete. |
| Target selected | The target refers to the active Dataset. The Working Pipeline may still be incomplete; training readiness requires separate validation. |
| Pipeline configured | A working configuration exists. Runs may still be empty until execution begins. |
| After experimentation | Dataset and target exist for the executed workflow, and one or more Runs may exist. The Working Pipeline remains editable and may become incomplete again without invalidating historical Runs. |

A Project does not cease to exist because it is not ready to train. These stages
do not prescribe a mandatory Bench navigation order or a full validation policy.

## Persistence semantics

Persisted Project state must survive application restarts. The same identity,
metadata, ML Objective, active Dataset reference, and current Working Pipeline
must be recoverable. Runs must remain associated with their Project and retain
their historical meaning independently of later working edits.

Recovering a Dataset reference does not itself guarantee that its underlying
data is still available. Missing-data handling needs separate design. This
specification does not choose a database, file format, filesystem layout, save
interaction, or crash-recovery mechanism; unsaved UI input has no persistence
guarantee here.

## Deletion semantics

Deleting a Project conceptually removes it from ML Studio along with its
project-owned state, including its current configuration and owned Run history.
Historical immutability prohibits rewriting Runs, not this explicit Project
removal. Removing a Dataset reference does not by itself authorize deleting an
original user-owned source file.

Detailed artifact ownership and cleanup, retention policies, soft deletion,
recovery, deletion during an active Run, and cloud object lifecycle are future
considerations. No deletion mechanism or recoverability guarantee is chosen here.

## Domain exclusions

**UI state belongs elsewhere.** Currently selected Bench, selected column,
collapsed sidebar, chart zoom, modal visibility, temporary hover state, unsaved
text input, and table pagination are not Project domain fields. If persistent UI
preferences are needed later, model them separately.

**Run results belong to Runs.** Accuracy, precision, recall, F1, ROC-AUC,
confusion matrix, training duration, model artifact, and training logs must not
live directly on the mutable Project entity. A UI can display Run information
without making it Project metadata.

**Raw data belongs to the Dataset concern.** Raw CSV contents and dataset rows
are not fields inside the Project representation; the Project references its
Dataset.

## Project-level invariants

1. Every Project has a stable, unique identity.
2. A Project has at most one active source Dataset in v0.1.
3. A Project may exist before a Dataset is attached.
4. A target cannot be valid unless it belongs to the active Dataset.
5. There is one current Working Pipeline; it is mutable and may be incomplete.
6. Historical Runs are immutable records, with configuration frozen at Run start.
7. Editing the Working Pipeline never retroactively modifies an existing Run.
8. Run results do not live directly on Project.
9. Raw dataset contents do not live directly inside Project metadata.
10. Frontend/UI state does not belong to the Project domain model.
11. The task type in this specification is `binary_classification`.

## Non-normative conceptual representation

This relationship sketch is illustrative. Labels are not finalized field names,
and indentation does not prescribe serialization, storage, or API structure.

```text
Project
  Identity
    stable ID, name, description, problem statement
    created timestamp, updated timestamp
  ML Objective
    task type: binary_classification
    target column: unset or selected from active Dataset
    user objective / success context: optional
  Active Dataset
    no reference yet, or one Dataset reference
  Working Pipeline
    one current editable configuration, possibly empty
    reference or structured state — representation deferred
  Runs
    zero or more Run references
    each Run preserves its own historical execution
```

## Out of scope

This specification does not define Dataset schema, Dataset profiling
representation, Pipeline IR, preprocessing operations, model schema, Run schema,
an Experiment abstraction, MLflow mapping, generated-code representation, API
endpoints, database schema, filesystem layout, AI context schema, or frontend
component state. Those concerns will be designed separately.

## Unresolved questions

- Can the active Dataset be replaced or detached in v0.1, and how would current
  target and Working Pipeline configuration be reconciled?
- What current configuration must be invalidated or reviewed when the target
  changes after configuration or execution?
- Which Run lifecycle events, if any, affect the Project's updated timestamp?
- What save/recovery interaction establishes that working edits are persisted,
  and how should unavailable Dataset references be presented?
- What exact historical context must a Run capture, and how are its outcomes
  finalized while preserving immutable history? These belong to the Run specification.
- What resources are Project-owned for deletion, especially while a Run is active?

These questions do not relax the invariants above and do not introduce additional
v0.1 capabilities.
