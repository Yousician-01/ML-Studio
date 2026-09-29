# Dataset — Prototype v0.1

## Purpose and scope

This conceptual domain specification defines a **Dataset** as a Project-owned
reference to immutable uploaded source data, with descriptive schema information,
semantic interpretation, and reproducible observations. It describes intended
behavior, not implemented functionality.

Prototype v0.1 supports **CSV input, binary classification, and at most one active
source Dataset per Project**, consistent with [Project v0.1](project-v0.1.md).
There are no shared Datasets or cross-project dataset registries.

This is not a database schema, filesystem design, dataframe representation,
Pydantic model, TypeScript interface, REST contract, Pipeline IR schema, or MLflow
dataset schema. It follows the reproducibility principles in the
[vision](../../VISION.md), [architecture](../architecture.md), and
[Pipeline IR ADR](../decisions/0001-use-pipeline-ir.md).

**Existing scope conflict:** the older [prototype scope](../prototype.md) and
[roadmap](../../ROADMAP.md) include regression, and the prototype document leaves
multiclass evaluation questions open. This specification follows the newer
Project specification's binary-classification boundary. Those older documents
remain unchanged. Resolving Project's deferred replacement and target-change
questions below refines its boundaries without changing historical Run guarantees.

## Project relationship and immutable source

A newly created Project may have no active Dataset. After an accepted upload it
references one active source Dataset. Each Dataset belongs to one Project in the
prototype domain model. Historical source references retained after replacement
do not introduce multiple active Datasets or multi-dataset workflows.

The original uploaded CSV is the source Dataset. Its source artifact is immutable:
imputation, scaling, encoding, feature removal, feature creation, and outlier
treatment must not overwrite it. Such operations belong to the Working Pipeline;
listing them here does not add operations to prototype scope.

```text
Source Dataset + Working Pipeline → derived representation used for execution
```

Users must be able to distinguish original data from transformed data. Updating
semantic annotations or recomputing descriptive metadata does not change source
contents. Derived execution data is not a replacement for the original source.

## Identity and source artifact

| Concept | Meaning |
| --- | --- |
| Dataset ID | Stable, unique identity of the Dataset entity, independent of its filename. No identifier format is chosen. |
| Original filename | Descriptive upload metadata; identical filenames may contain different data. |
| Upload/attachment timestamp | Records when this Dataset entered its Project; precise event timing and representation remain unspecified. |
| Source format | CSV in v0.1. |
| Content fingerprint | Deterministic checksum of the immutable uploaded contents, identifying the exact source independently of filename. |
| Source artifact reference | Reference to the stored artifact containing the original uploaded CSV. |

```text
Dataset → Source Artifact (immutable uploaded CSV)
```

Raw CSV contents are not embedded in Project or Dataset metadata. No storage
medium, artifact location, or persistence implementation is selected here.

The fingerprint concerns exact uploaded contents, not a normalized or transformed
table. Identical contents must produce the same fingerprint under the same
fingerprinting definition. Different filenames do not imply different contents;
the same filename does not imply identical contents. Entity identity and content
identity are distinct: this does not prescribe deduplication or shared ownership.
The hashing algorithm is deferred. A fingerprint identifies contents but cannot
reconstruct missing data or explain parsing by itself.

## Schema: physical type and semantic type

CSV does not declare dataframe dtypes. **Physical type** describes how source
values are interpreted when parsed; **semantic type** describes their intended
ML meaning. Neither should be treated as interchangeable with the other.

For example, `1001, 1002, 1003` may parse numerically while representing an
identifier. `0, 1` may be physically numeric and semantically binary/categorical.
A string may represent datetime information.

For each column, the Dataset should conceptually describe its name, interpreted
source/physical type, observed missing-value status, and basic cardinality
information. Observed missingness does not declare a future nullability contract.
Detailed counts and summaries belong to Profile and need not be duplicated in
schema metadata. Parsing and missing-value conventions must be explicit enough
to reproduce observations; exact rules are deferred.

## Semantic types and user overrides

Use this small vocabulary:

| Semantic type | Meaning and prototype value |
| --- | --- |
| continuous | Quantitative values for which numerical magnitude is meaningful. |
| categorical | Discrete category labels, including numerically stored codes. |
| binary | Two-category meaning; not restricted to numeric `0` and `1`. |
| datetime | Date/time meaning, useful for recognizing temporal information and reviewing suitability. |
| identifier | Entity/record identity, useful for flagging values that may be unsuitable predictors. |
| text | Free-form textual meaning, useful for distinguishing unsupported text inputs from categories. |
| unknown | Meaning has not been determined reliably and needs review. |

Recognizing datetime or text does not promise datetime feature engineering or NLP
support. Semantic labels inform interpretation and compatibility checks; they do
not automatically select transformations or establish model readiness.

Keep the system's **inferred semantic type** distinct from the **effective
semantic type** used in the current context:

```text
Effective semantic type = user override, if present; otherwise inferred type
```

Users must be able to override inference and remove an override to return to the
inferred interpretation. An override changes interpretation, not source values or
physical type. It does not bypass compatibility validation. Recomputed inference
must not silently erase an explicit override. No frontend controls are specified.

## Column roles and target consistency

Roles describe how columns participate in the current ML task, independently of
semantic type. The minimal vocabulary is:

- **feature:** an intended input candidate, subject to Pipeline compatibility.
- **target:** the selected outcome to predict.
- **excluded:** not used as a feature or target in the current configuration.

For example, `customer_id` may have semantic type `identifier` and role `excluded`;
`churn` may have semantic type `binary` and role `target`. These are examples,
not automatic rules. Feature exclusion changes configuration, not source data.

The Project's selected target and the Dataset's current column-role view must
agree: there is no target role before selection, and a selected target corresponds
to exactly one column in the active Dataset. That column cannot also be a feature.
Current roles describe intent; they do not prove execution validity.

The authoritative persistence location for target selection, semantic overrides,
and feature/exclusion decisions is deferred. The conceptual role view must not
create independent competing copies of the same decision across Project, Dataset,
and Working Pipeline. Defaults and synchronization mechanisms need later design.

## Dataset Profile: observations, not decisions

Dataset Profile contains deterministic descriptive observations of the immutable
source data. It is not Pipeline configuration or a container for recommendations.

| Level | Examples of observations |
| --- | --- |
| Dataset | Row count, column count, duplicate-row count, total missing cells |
| Column | Missing count/percentage, unique count/cardinality, numerical summary statistics, categorical frequencies, distribution observations where appropriate |

Profile observations must be reproducible from the same source under the same
explicit parsing and profiling definitions. Missing-value interpretation,
distinct-value counting, and duplicate-row comparison need defined conventions;
no detailed Profile schema is fixed here. Recalculation must remain grounded in
the source, not silently substitute transformed execution data. If interpretation
affects which summaries are applicable, that context must be distinguishable.

“`income` contains 14.2% missing values” is an observation. “`income` should use
median imputation” is a recommendation or Pipeline decision and does not belong
in Profile. Likewise, “`customer_id` has 99.9% unique values” is an observation;
“This may be an identifier and could be excluded” is a separate recommendation.
Semantic inference is also an interpretation, not proof derived from uniqueness
alone. Profile must not contain model or AI recommendations.

Source profiling describes the uploaded data; it does not authorize fitting
preprocessing on all rows or using held-out outcomes for model selection.
Partition-aware EDA and execution rules remain outside this specification.

## Dataset Preview

Dataset Preview is an informational view of sample rows from the immutable
source. Preview rows are not part of persistent Dataset identity and are not the
source of truth for full-dataset statistics or target validation. No pagination
API, sampling algorithm, or frontend behavior is selected here. Source previews
must remain distinguishable from any future transformed-data views.

## Target selection constraints and changes

A selected target must belong to the active Dataset. For binary classification,
the **effective target must represent exactly two classes after legitimate
missing/invalid target handling**. Labels such as `yes/no`, `true/false`, and
`churn/stay` can represent binary outcomes; numeric `0/1` is not required.

Two observed values alone do not establish target suitability. Missing/invalid
handling, label interpretation, and positive-class meaning require further
definition. A semantic override to `binary` cannot make an incompatible target
valid. Target encoding and cleaning configuration are not defined here, and no
silent dropping, merging, or coercion of classes is authorized.

Changing the target changes the current Project/Working Pipeline context and
requires revalidation of target-dependent configuration, including feature roles
and any assumptions about the prior target. Historical Runs retain the target
and source with which they executed. Neither target changes nor semantic edits
may retroactively change those Runs; their snapshot structure remains deferred.

## Replacement, detachment, and historical identity

Replacing the active Dataset is a significant Project change. The replacement
must be treated as a new source association, never an in-place rewrite of the
source used by historical Runs. At most one Dataset remains active.

Replacement requires revalidation of **target selection, semantic overrides,
and the Working Pipeline**. Columns may disappear, physical types may change,
the target may disappear, and semantic assumptions may no longer hold. Matching
column names alone do not prove compatibility. Unresolved incompatibilities
must prevent the current configuration from being treated as ready to execute.
Exact reset/preservation behavior and the UI flow are deferred.

Historical Runs must continue to identify the exact original contents they used
through Dataset identity and fingerprint. Replacement must preserve access to
those contents for reconstruction rather than redirect old references to the
replacement. Detailed retention, cleanup, and ownership mechanisms remain open;
a missing historical source cannot be reconstructed from a checksum alone and
must not be silently replaced. Project deletion remains governed by
[Project v0.1](project-v0.1.md).

This is an identity and reproducibility requirement, not a dataset version-control
system. It introduces no DVC dependency, branching, registry, or multi-source
execution. A separate **detach Dataset while keeping Project** operation is
deferred because the core prototype workflow does not require it.

## Acceptance, suitability, and size

Basic Dataset acceptance requires a readable CSV source, an established header
and schema, at least one usable column, and at least one data row. Completely
empty and header-only inputs are invalid. Malformed CSV must fail clearly rather
than silently lose problematic records.

Duplicate column names require explicit, unambiguous handling before acceptance;
they must not silently collapse columns or make target references ambiguous.
The exact rejection/disambiguation policy and other CSV parsing edge cases are
deferred. An unreadable or unaccepted upload must not be presented as a usable
active Dataset or erase an existing valid source association.

**Accepted Dataset** and **Dataset suitable for a particular Pipeline** are
different judgments. A valid CSV may have no selected target, an unsuitable
target, unsupported feature types, or insufficient usable examples. Acceptance
does not imply readiness for binary-classification training.

The prototype targets local proof-of-concept tabular datasets. It does not promise
arbitrary sizes. Supported resource and size limits will be established through
implementation and testing; no MB or row limit is invented here.

## Privacy

Datasets may contain sensitive information. Raw values, source contents, and
preview rows must not be casually included in application logs, including error
messages. Profile should avoid unnecessary exposure: categorical labels,
frequencies, and other summaries can themselves reveal sensitive information.

Creating or attaching a Dataset does not authorize automatically sending its raw
contents to AI. Future AI data-sharing behavior requires an explicit specification.
These are domain requirements, not claims of implemented privacy controls.

## Conceptual lifecycle

```text
Uploaded → Parsed → Schema Inferred → Profiled → Semantic Types Reviewed/Overridden → Target Selected
```

This is a typical progression, not a rigid persisted state machine or mandatory
navigation order. Invalid uploads may fail before acceptance. An accepted Dataset
may await profiling, semantic review, or target selection. Parsing, inference,
Profile, and Preview may be recomputed under explicit interpretation rules
without mutating the source or rewriting historical Run context.

## Dataset invariants

1. The original source artifact is immutable.
2. Filename is not Dataset identity.
3. Dataset contents have a deterministic fingerprint independent of filename.
4. A Project has at most one active source Dataset; each Dataset belongs to one Project.
5. Cleaning/preprocessing does not mutate the source Dataset.
6. Semantic inference may be overridden by the user.
7. Physical type and semantic type are distinct.
8. Historical Runs remain associated with the exact Dataset contents they used.
9. Replacing the active Dataset never changes historical Runs.
10. Replacement requires revalidation of target selection, semantic overrides, and Working Pipeline compatibility.
11. Profile observations are deterministic descriptive facts, not recommendations.
12. Raw dataset values must not be casually included in application logs.
13. Current column roles and Project target selection must agree; a target is not also a feature.

## Non-normative conceptual representation

This sketch explains relationships. Labels are not final field names; nesting
does not determine persistence ownership, serialization, or embedded storage.

```text
Dataset
  Identity
    stable ID, original filename, source format: CSV
    content fingerprint, upload/attachment timestamp
  Source Artifact
    reference to immutable uploaded CSV
  Schema / current interpretation
    columns
      name, interpreted physical type
      observed missing status, basic cardinality information
      inferred semantic type, optional user override, effective semantic type
      current role consistent with Project and Working Pipeline
  Profile
    descriptive dataset summary
    descriptive column summaries

Dataset Preview → informational view over Source Artifact
Project → zero or one active Dataset reference
```

## Out of scope

This specification does not define Pipeline IR, transformations, imputation,
scaling or encoding configuration, feature engineering operations, model
configuration, Run schema/internals, MLflow mapping, or AI recommendation schema.

It excludes shared dataset registries, multiple active Datasets, joins,
SQL/database connectors, URL ingestion, Parquet/Excel support, object-storage
connectors, streaming data, and separate train/validation/test file uploads.
Cloud object storage design, DVC, frontend controls, API endpoints, filesystem
layout, and persistence implementation are also outside scope.

## Unresolved questions

- Which configuration owner is authoritative for target, role, and semantic
  decisions, and how should Working Pipeline compatibility be revalidated after
  Dataset replacement or target changes? Pipeline IR design must resolve the
  configuration boundary without creating competing state.
- What legitimate missing/invalid target handling, label interpretation, and
  positive-class rules establish an executable binary target? These need later
  validation and Pipeline specifications, without silently changing source data.
- What source interpretation and semantic context must a Run preserve to
  reproduce its execution after current annotations change? The Run specification
  must define that boundary without relying on mutable current metadata.
- What CSV parsing, duplicate-header, missingness, fingerprinting, and profiling
  conventions establish repeatable interpretation and descriptive observations?
- How will historical source availability, missing-artifact reporting, and
  Project-owned cleanup be reconciled with persistence and deletion?
