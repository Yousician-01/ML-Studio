# Run — Prototype v0.1

## Purpose and domain ownership

A Run is **an immutable historical record of one actual execution attempt of a
frozen, execution-ready ML Studio experiment configuration**. The attempt may
fail before Python starts. It answers what was attempted, against which exact
Dataset and resolved semantic interpretation, which exact generated Python was
prepared and, if the workload started, executed, what happened, what results and
durable artifacts were produced, and under which relevant environment. It also
records the tracking association when established.

A Run is an ML Studio domain entity, not the mutable Working Pipeline and not
merely an MLflow Run. ML Studio owns its identity, lifecycle, success/failure
semantics, and artifact requirements. This document defines intended behavior,
not implemented functionality. Normative requirements use must/must not; examples
are illustrative. No API, database, filesystem implementation, framework, execution
implementation, or integration is selected here.

## Existing-contract consistency

The current [Project](project-v0.1.md), [Dataset](dataset-v0.1.md),
[User Journey](user-journey-v0.1.md), and [Pipeline IR](pipeline-ir-v0.1.md)
specifications take precedence over older broad plans where scope differs.

| Existing contract | Finding |
| --- | --- |
| Project v0.1 | Its wording creates a Run when execution/training begins and freezes inputs at its start. This contract specifies an earlier, distinct CREATED boundary after an executable package is frozen but before the Python workload starts. If “begins” means workload start, the timings conflict; the precise boundary below governs this specification. Historical immutability is preserved. |
| Dataset v0.1 | No direct contradiction found. Immutable sources, durable historical references, and frozen execution-relevant interpretation follow its requirements. |
| User Journey v0.1 | No direct contradiction found. It leaves Run internals open and supports read-only historical Code and two-Run comparison. Requiring the exact persisted executed program strengthens its historical-code expectation. |
| Pipeline IR v0.1 | Its “when execution successfully begins” snapshot wording needs the same creation/start clarification as Project. Its plan-to-executor responsibility diagram omits the newly required code-generation step; generated Python becomes the actual workload here. IR structure and the distinction between configured and effective intent are unchanged. |

Run v0.1 also narrows Pipeline IR's deferred suggestion of generating code from
historical configuration: historical Code must retrieve the original artifact,
not regenerate it with today's generator. This is a new explicit historical
integrity decision, not permission to alter existing files.

Older planning differences remain separate:

- [Prototype scope](../prototype.md) and [roadmap](../../ROADMAP.md) include
  regression and broader classification questions. The newer specifications
  limit this prototype to binary classification and three classifiers.
- [Architecture](../architecture.md), [vision](../../VISION.md), and the older
  prototype include XGBoost in the intended ecosystem; it is outside the frozen
  v0.1 model set. Older Bench terminology also differs from Prepare.
- Architecture portrays execution and Python generation as parallel consumers
  of IR. This contract makes generated Python the executed workload; it must not
  coexist with a separate hidden ML implementation for the same Run.
- Older plans describe MLflow tracking but do not settle failure isolation.
  The local success contract and separate tracking state below now do so; this
  is a refinement, not abandonment of MLflow.
- Architecture and [ADR 0001](../decisions/0001-use-pipeline-ir.md) still describe
  IR details as pending. Their status text is not revised here. ADR 0001's shared
  representation principle remains intact.

## Project and Working Pipeline relationship

```text
Project
├── Dataset
├── Working Pipeline IR
└── Runs
    ├── Run 001
    ├── Run 002
    └── Run 003
```

Working Pipeline IR is mutable current experiment intent and may be incomplete,
invalid, or stale. A Run belongs to its Project and records one frozen execution
attempt. Model, preprocessing, split, target, semantic-override, Dataset, or
current-code changes must never rewrite an existing Run.

## Run creation boundary

Clicking Train does not itself create a Run:

```text
User clicks Train
        ↓
Validate Working Pipeline
        ↓
Resolve effective execution semantics
        ↓
Generate executable Python
        ↓
Freeze required execution inputs and executable artifact
        ↓
CREATE RUN
```

Validation failure, effective-plan resolution failure, code-generation failure,
or failure to establish the required frozen package produces **no Run**. A Run
comes into existence only when ML Studio has that package and is ready to make
an actual local execution attempt. Non-blocking dormant-configuration warnings
allowed by Pipeline IR do not themselves prevent creation.

The required pre-execution package establishes the canonical IR snapshot,
execution-relevant resolved interpretation, exact Dataset reference, and exact
executable Python. Results and fitted model outputs cannot be required before
execution; they are requirements for successful completion. This distinction
does not specify transaction mechanics, process protocols, or UI error behavior.
Once the package and Run identity exist, a failed workload launch is a FAILED
Run rather than an absent Run.

## Identity and timestamps

Every Run has a stable, globally unique machine identity within ML Studio's
domain, an owning Project association, and a project-local sequence number for
human ordering. `run_id` and `sequence_number` name these concepts, not database
fields. Labels such as Run 001, Run 002, and Run 003 use the sequence number;
the sequence is not the sole identity.

Sequence numbers must not be silently reused after historical Run deletion.
No UUID format, database sequence mechanism, or gap-free allocation requirement
is chosen. An MLflow Run ID is a separate infrastructure reference.

The minimum lifecycle timestamps establish:

- creation, when identity and the frozen package are established;
- execution start, when the actual generated Python workload starts;
- terminal completion/failure, when the outcome is finalized.

Execution start is absent while CREATED; terminal time is absent while active.
Do not invent timestamps for events that did not occur. Timestamp storage types
and clock mechanics are not defined here.

## Lifecycle and historical immutability

Exactly four core states exist in v0.1:

```text
CREATED ─┬→ FAILED
         └→ RUNNING ─┬→ SUCCEEDED
                     └→ FAILED
```

| State | Meaning |
| --- | --- |
| CREATED | Identity exists and the required frozen pre-execution package is established; the local Python workload has not started. |
| RUNNING | The exact generated Python workload process associated with this Run has successfully started. |
| SUCCEEDED | The workload completed and all required results/artifacts were durably persisted and Run finalization completed. |
| FAILED | A post-creation launch attempt failed, or a started workload did not satisfy the complete success contract. Available partial evidence remains historical. |

SUCCEEDED and FAILED are terminal. Frozen inputs are immutable from creation;
lifecycle metadata, execution observations, and outputs naturally accumulate
while active. Once terminal, historical experiment facts, results, and artifact
associations are immutable. Separate external tracking synchronization state may
be repaired later without rewriting those facts. Normal progression does not
violate historical immutability.

A failed Run must not become successful by retrying under the same identity.
Any future retry would create a new Run; no retry UX is defined in v0.1.
There are no queued, paused, cancelled, retrying, scheduled, or interrupted states.
Cancellation is out of scope. Crash recovery is not designed here.

A local process-launch failure, unavailable Python environment, or process-creation
failure after Run creation follows CREATED → FAILED. RUNNING is never used for an
unstarted process, and no execution-start timestamp is invented. The frozen
package and failure evidence remain under the existing Run identity.

## Conceptual Run structure

```text
Run
├── Identity
├── Snapshot
├── Code
├── Execution
├── Results
├── Artifacts
├── Provenance
└── Tracking
```

Identity establishes Run/Project association and ordering. Snapshot records
configuration and resolved context. Code refers to the exact prepared executable
program, which is the program used if the workload starts.
Execution records lifecycle, timing, and failure information. Results contain
evaluation outcomes; Artifacts identifies durable evidence; Provenance explains
the environment; Tracking records the separate infrastructure association/outcome.

These are conceptual responsibilities, not independent services, database tables,
serialization fields, or a complete Artifact entity. Code and Results can refer
to artifacts without requiring duplicate copies of the same information.

## Frozen configuration and resolved semantic context

The canonical Pipeline IR snapshot preserves the exact configured intent used,
including IR version, Dataset ID/fingerprint, target and typed positive class,
the fixed missing-target policy, feature inclusion and ordered operations, model
configuration/resolved parameters, and split configuration. Preserve excluded
features and their dormant operations as configured; do not replace the snapshot
with a pruned effective plan.

Additional frozen resolved context records only interpretation needed to establish
the actual execution that is not already in IR. At minimum this covers physical
and effective semantic interpretation of the target and effective input columns,
plus source/target interpretation necessary to establish usable classes and
eligible target rows. Include other resolved interpretation only if execution
depends on it. An excluded feature's configuration remains in IR; its unrelated
descriptive statistics need not be frozen merely because the column exists.

For example, if `age` was physically integer and effectively continuous at Run
001, that interpretation remains historical even if the Dataset later labels
age categorical. A non-normative fragment illustrating the relevant distinction:

```json
{
  "age": {
    "physical_type": "integer",
    "effective_semantic_type": "continuous"
  }
}
```

The positive class retains its Pipeline IR typed-scalar meaning, such as string
`yes`, without independently maintaining a competing copy. The snapshot must
establish the two usable class meanings and relevant target interpretation even
after current Dataset metadata changes. Source parsing and eligibility semantics
must be reproducible under the later Execution contract; this is not a requirement
to persist a per-row prediction or eligibility table.

Do not copy the entire Dataset Profile, EDA charts, or unrelated statistics.
Snapshot information may be preserved directly or through durable immutable
references; references to mutable current metadata are insufficient. Exact
serialization and execution-specific resolution mechanics are deferred.

## Dataset artifacts, local persistence, and deletion

Every Run must retain a durable reference to the exact Dataset identity/content
used. Its fingerprint supports verification of the referenced source. Multiple
Runs may reference the same immutable Dataset source artifact:

```text
Run 001 ─┐
Run 002 ─┼→ Dataset Artifact ABC
Run 003 ─┘
```

Do not duplicate raw Dataset contents into every Run bundle merely for convenience.
Normal workspace behavior, including Dataset replacement, must not silently
destroy an artifact required by historical Runs. A fingerprint alone cannot
reconstruct a lost source, and current data must not substitute for missing
historical data.

v0.1 persists Run artifacts on the user's local machine. There may be a local
workspace root grouping Project, Dataset, and Run artifacts, but no root path,
directory name, filename, layout, environment variable, or storage format is
fixed here. Stable IDs/artifact references identify domain objects; paths locate
stored data. Human-readable filenames are not entity identity.

Required artifacts must remain reliably resolvable through ML Studio's
persistence/artifact layer without reliance on remembered filename conventions.
No generic distributed artifact service is introduced.

Run deletion behavior is not fully designed. Sequence numbers cannot be reused;
cleanup must respect ownership and references, especially Dataset artifacts
still needed by other Runs. Project deletion remains governed by Project v0.1.
Reference counting, garbage collection, locking, retention implementation,
corruption handling, and exact cleanup mechanics belong to persistence/storage
design. Historical immutability does not imply an undeletable-record policy.

## Generated Python as the executed historical artifact

The exact generated Python associated with a Run is the actual program ML Studio
uses if that Run's workload starts:

```text
Pipeline IR
    ↓
Validator
    ↓
Effective Execution Plan
    ↓
Code Generator
    ↓
Executable Python Artifact
    ↓
Local Python Executor
```

There must not be one program generated for display and a separate hidden ML
execution implementation. Generated Python is a first-class immutable Run
artifact, persisted as part of the frozen executable package and retained for
historical inspection, including when launch or later execution fails. If launch
fails, it is the exact program prepared for the attempt, not a program that ran.

Current Working Pipeline Code may be generated dynamically. Historical Run Code
must resolve the original frozen artifact. Do not regenerate code with today's
generator and present it as the exact program executed historically. Both Code
views remain read-only as required by User Journey. A CREATED Run's artifact is
the program prepared for its attempt; it must not falsely claim the workload has
already run.

### Workload and orchestration boundary

Generated Python represents the data-science workload: loading the referenced
Dataset, applying target-row eligibility semantics, deterministic splitting,
constructing preprocessing and model, fitting, evaluating, and producing required
model/results outputs.

ML Studio orchestration owns lifecycle transitions, launching that program,
capturing stdout/stderr, collecting outputs, artifact finalization, Run
finalization, and tracking coordination. Generated Python must not become the
whole application lifecycle. Exact inputs, outputs, process protocol, imports,
and execution mechanisms remain for later specifications.

## Required artifacts and results

A successful Run must durably preserve/reference all of the following locally:

| Required evidence | Domain requirement |
| --- | --- |
| Frozen Pipeline IR | Exact configured intent, including excluded-feature configuration |
| Resolved semantic context | Execution-relevant historical interpretation beyond IR |
| Generated Python | Exact immutable program actually executed |
| Trained model artifact | Complete fitted inference pipeline for compatible raw feature input |
| Evaluation results | Standard binary-classification results with interpretable class/partition context |
| Basic execution provenance | Relevant ML Studio, Python, and used ML-library versions |

The Dataset source is a required durable historical reference, not a required
per-Run copy. Required evidence can share representations/references; the table
does not mandate one file per row. Exact filenames and serialization formats are
not chosen.

The trained model artifact must include the fitted preprocessing and fitted
classifier needed together for inference, rather than saving only the final
classifier and losing fitted preprocessing. The domain requirement is a usable
complete fitted inference pipeline. No pickle, joblib, MLflow model format, or
registry format is prescribed, and no inference UI is introduced.

Successful binary-classification results record Accuracy, Precision, Recall, F1,
and Confusion Matrix. Positive-class interpretation and evaluation population
must remain understandable from frozen context. Undefined/unavailable metric
conditions must be represented honestly under the later Execution contract,
not fabricated as zero. ROC-AUC remains conditional on the later score/probability
contract. Metric selection, custom metrics, ranking, and winner/loser semantics
are not added.

Logs/diagnostics should be retained where useful as supporting evidence; they
are distinct from the required reproducibility artifacts above. Per-row
predictions are **not required artifacts** in v0.1. Prediction-table persistence,
prediction browsing, and inference UI are outside scope.

## Success, failure, and partial evidence

Success requires the entire ML Studio contract:

```text
Training + required evaluation + required local artifact persistence
         + Run finalization = SUCCEEDED
```

Successful fitting alone is insufficient. If training succeeds but the complete
model artifact or another required artifact cannot be persisted, the Run is
FAILED. A successful MLflow write cannot compensate for missing required local
evidence. Partial outputs must not be presented as a complete successful result.

Distinguish failures before creation, after creation but before launch, and after
the workload starts:

```text
Invalid Working Pipeline / plan-resolution failure / code-generation failure
    → no frozen executable package → NO RUN

Frozen executable package → Run created → workload starts → execution fails
    → FAILED RUN retained as history

Frozen executable package → Run created → workload launch fails
    → FAILED RUN retained as history; no RUNNING state or start timestamp
```

A failed Run is valuable historical evidence and must not be automatically
deleted. Preserve available frozen IR, resolved context, generated Python,
available provenance, logs/diagnostics, and a structured failure summary wherever
possible. It may lack a trained model, final metrics, or complete evaluation
artifacts. Retained partial artifacts must be identifiable as partial evidence;
failure does not authorize substituting later outputs under the same identity.

At domain level, failure information supports a stage, a user-facing summary,
and a diagnostic reference when diagnostics are available. A raw traceback is
not the primary user-facing contract. Traceback/stdout/stderr may be retained
separately without casually logging raw Dataset values or secrets.

Execution startup, data loading, preprocessing, training, evaluation, artifact
persistence, and finalization illustrate possible stages, not a frozen enum.
Exact taxonomy and mechanics belong to Execution. If persistence itself fails,
evidence retention is best effort; do not claim durability for unavailable
artifacts or mark the Run successful to hide the problem.

## Provenance

Retain basic provenance covering the ML Studio version, Python version, and
versions of ML libraries actually relevant to generated execution, such as
scikit-learn and pandas when used. Capture available provenance for failed
attempts as well as successful ones. Execution-specific resolved behavior not
expressed in IR must remain explainable through the frozen package/provenance,
not depend on today's library defaults.

Do not blindly snapshot every installed package or require OS/platform metadata
without an execution reason. **Reproducibility metadata is not the same as a fully
captured reproducible environment.** v0.1 does not promise full environment
reconstruction or identical numerical results on arbitrary environments.

## MLflow association and failure isolation

MLflow is the chosen experiment-tracking infrastructure from the beginning of
v0.1. Intended integration concerns include parameters, metrics, tags, artifacts,
model logging, and local tracking. This specification does not implement them or
define a custom replacement tracker.

MLflow supports ML Studio's domain semantics rather than owning them. Normal
v0.1 tracking associates one ML Studio Run with one MLflow Run, retaining the
relevant tracking identity/reference separately from ML Studio's Run ID. MLflow's
experiment hierarchy must not automatically define Project semantics. Exact tag
names, mappings, local backend, and bidirectional traceability mechanisms are
integration work.

Core Run status and tracking outcome are separate:

```text
Run.status       — CREATED / RUNNING / SUCCEEDED / FAILED
Tracking.status  — separate infrastructure outcome; vocabulary deferred
```

Tracking may be unavailable, failed, or partial without a remote/local MLflow
identity having been established. Absence of that identity must be representable
honestly and must not require a fabricated reference. No DEGRADED core Run state
is introduced.

| ML Studio execution contract | MLflow outcome | Core Run outcome |
| --- | --- | --- |
| Training, required evaluation, local artifacts, and finalization complete | Tracking fails or is incomplete | SUCCEEDED; tracking separately reports its issue |
| Required local model artifact fails to persist | Logging succeeds, possibly with partial data | FAILED |
| Workload launch fails or execution fails after start | Any tracking outcome | FAILED; retain available evidence |

MLflow tracking failure alone must not block valid local execution or convert an
otherwise complete success into FAILED. Required local evidence cannot depend
solely on a successful MLflow logging operation. MLflow state never overrides
ML Studio history or its success contract.

**Historical experiment truth is immutable; external integration synchronization
state may be repaired without rewriting that truth.** Immutable facts include
Run ID and sequence, frozen Pipeline IR, Dataset identity/fingerprint, resolved
semantic context, exact generated Python, terminal outcome, metrics/results,
model artifact association, execution provenance, and historical timestamps.

Repairable tracking state may include synchronization outcome, failure information,
reconciliation state, and an external tracking reference once established. A Run
may remain SUCCEEDED while tracking changes from failed to synchronized. Such a
repair cannot rewrite its experiment facts or terminal status. If an external
MLflow Run identity already exists, it must not be casually replaced in a way
that falsifies historical traceability. Partial external creation, duplicate
logging, retry after partial synchronization, and reconciliation with an existing
external Run belong to MLflow integration design. No retry schedule, worker,
queue, or synchronization algorithm is defined here.

## Historical views and workspace changes

The domain must preserve enough immutable information for descriptive comparison
of **exactly two Runs**: model type, preprocessing, exposed model parameters,
split configuration, and key metrics. Dataset/target/evaluation-context differences
must remain identifiable, and absent results must not look like zero scores.
Do not introduce N-way comparison, ranking, winner selection, statistical
significance testing, or recommendation scoring.

Historical Code uses the exact persisted artifact, independently of current
Working Pipeline Code. Replacing a Dataset leaves the Run's Dataset ID/fingerprint,
source artifact reference, IR, semantic context, code, results, and model artifact
unchanged. Changing target or semantic overrides leaves its historical target,
typed positive class, resolved interpretation, and Python unchanged. Historical
views must not substitute current Project metadata for those facts.

## Non-normative churn lifecycle example

This fictional example illustrates behavior, not implementation pseudocode or
an acceptance test. The Working Pipeline references `customers.csv`, target
`churn`, typed string positive class `yes`, configured preprocessing, Logistic
Regression, and an 80/20 stratified split with seed 42.

1. The user selects Train. Validation finds no blocking issues.
2. Effective execution semantics resolve, and executable Python is generated.
3. The required inputs, source reference, resolved context, and exact Python are
   frozen. Run 001 receives its machine identity and project-local sequence and
   enters CREATED.
4. That exact Python begins execution. Run 001 becomes RUNNING and records its
   actual start time.
5. Training and required evaluation complete. The complete fitted preprocessing
   plus classifier artifact, evaluation results, and required provenance are
   durably preserved with the existing frozen evidence.
6. The normal MLflow association/tracking outcome is recorded separately as the
   attempt proceeds. Run finalization completes and Run 001 becomes SUCCEEDED
   with its terminal timestamp. Its success would be unchanged if tracking alone
   had failed; the tracking record would show that failure instead.
7. Historical Code retrieves the saved program, even after the user changes the
   current Working Pipeline.

If tracking later synchronizes after Run 001 is terminal, only the separate
tracking state changes. Run 001 remains SUCCEEDED with the same frozen facts.

For a second valid frozen package, Run 002 reaches RUNNING but fails during
training. It becomes FAILED with its code, snapshot, available provenance,
diagnostics, and failure summary retained where possible. It may have no usable
model or final metrics. Neither failure nor another Train action rewrites Run 001
or turns Run 002 into a later success. A validation failure before package creation
would create neither Run nor historical execution attempt.
If Run 003 is created from another valid frozen package but its local Python
process cannot start, it transitions directly from CREATED to FAILED. Its
prepared code and failure evidence remain, with no execution-start time.

## Normative Run invariants

1. A Run represents one actual execution attempt, including a post-creation
   launch attempt that fails before workload start. CREATED records the frozen
   package ready for that attempt.
2. Invalid Working Pipeline configuration does not create a Run.
3. Effective-plan resolution failure before package creation does not create a Run.
4. Code-generation failure before package creation does not create a Run.
5. Creation requires frozen execution inputs and an existing executable Python artifact.
6. Every Run has stable machine identity within ML Studio's domain.
7. Every Run has a project-local sequence number that is not silently reused.
8. Working Pipeline changes never mutate historical Runs.
9. Dataset replacement never mutates historical Runs.
10. Later semantic overrides never mutate historical Runs.
11. Later target changes never mutate historical Runs.
12. The Run's generated Python artifact is the program used if its workload starts;
    a launch-failed Run retains it as the exact program prepared for the attempt.
13. Historical Python is persisted, not regenerated and presented as original code.
14. A successful Run retains a complete fitted inference pipeline/model artifact.
15. Per-row predictions are not required artifacts in v0.1.
16. A failed launch or execution attempt after creation remains a historical Run;
    CREATED may transition directly to FAILED without passing through RUNNING.
17. Failed Runs preserve available evidence wherever possible.
18. SUCCEEDED requires the complete ML Studio success contract, not merely fitting.
19. Failure to persist a required ML Studio artifact prevents SUCCEEDED.
20. MLflow tracking failure alone does not make an otherwise successful Run fail.
21. MLflow does not define ML Studio Run identity.
22. MLflow does not define ML Studio lifecycle semantics.
23. Raw Dataset contents are not duplicated per Run merely for convenience.
24. Each Run durably references the exact Dataset artifact/content used.
25. Execution-relevant semantic interpretation is frozen for historical reproducibility.
26. Configured Pipeline IR is frozen for the Run, including dormant excluded intent.
27. Split configuration is frozen for the Run.
28. Required execution provenance is retained for success; failed attempts retain
    what is available.
29. Reproducibility metadata does not imply full environment reconstruction.
30. Terminal experiment history, results, and artifact associations are immutable;
    separate external tracking state may be repaired without changing that truth.
31. Retrying a failed historical Run must not rewrite that Run into success.
32. Run comparison is descriptive and does not declare winners.
33. Domain identity is not based solely on filesystem paths or readable filenames.
34. Required artifact references must remain resolvable through ML Studio's
    persistence/artifact layer.
35. RUNNING means the generated workload process successfully started; launch
    failure records no execution-start timestamp.
36. An established external MLflow reference must not be casually replaced in a
    way that falsifies historical traceability.

## Explicit exclusions

Run v0.1 does not define authentication, users, teams, multi-tenancy, cloud
execution, remote workers, distributed training, Kubernetes, scheduling, queues,
cancellation, pause/resume, automatic retries, model registry, model promotion,
deployment, serving, inference UI, prediction-history storage, per-row prediction
persistence, HPO trials, AutoML, cross-validation Runs, experiment ranking, winner
selection, statistical significance, artifact garbage collection, storage quotas,
or cloud object storage. No crash-recovery system is introduced.

## Genuine unresolved Run-domain questions

**No blocking Run v0.1 domain questions remain.** CREATED → FAILED captures a
post-creation launch failure, and repairable external tracking state remains
separate from immutable historical experiment truth.

Minimum semantic context, required artifacts, partial evidence, IDs/sequences,
timestamps, and Dataset retention obligations are defined above. Their storage
and execution mechanics are deferred below, not additional Run-domain questions.

## Later-specification interactions

### Execution specification

Resolve exact effective-plan semantics, generated-program input/output contract,
process launch and launch-failure mechanics, Dataset artifact delivery,
target-row exclusion timing and eligibility, deterministic split algorithm, random-state propagation, leakage
prevention and training-only fitting, operation/estimator mappings, prediction
semantics, conditional ROC-AUC score/probability contract, metric/result return,
model serialization, failure-stage taxonomy, stdout/stderr handling, and required
artifact finalization mechanics. This document defines none of those mechanisms.

### Code-generation specification

Resolve deterministic generation from validated IR/effective plans, program
structure, readability, imports, identity between visible executable code and
actual workload, current Working Pipeline preview, historical artifact retrieval,
and generator version/provenance considerations. Historical inspection must not
regenerate and substitute a different program.

### Persistence/storage design

Resolve local workspace root and OS conventions, Project/Dataset/Run storage
locations, artifact reference representation, atomic writes/finalization,
retention, Run deletion cleanup, shared Dataset preservation, and corruption or
missing-artifact handling. No filesystem layout, database schema, or retention
algorithm is chosen here.

### MLflow integration

Resolve tracking URI/local backend setup, Project-to-experiment mapping if any,
Run-to-MLflow association, tags/metadata, parameter/metric logging, artifact and
model logging strategy, tracking failure/retry mechanics, and duplicate/partial
logging behavior, including reconciliation with an established external Run
identity. Any integration must preserve separate ML Studio identity,
local artifact success requirements, and tracking failure isolation.
