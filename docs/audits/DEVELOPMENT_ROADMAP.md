# Dependency-aware development roadmap

Date: 2026-10-24. Proposal for approval, not a release commitment. The inspected
v0.1 tree and evidence limits are recorded in [baseline](V0_1_BASELINE_AUDIT.md).
Algorithm feasibility is detailed in [ML_FEATURE_EXPANSION.md](ML_FEATURE_EXPANSION.md).
S/M/L/XL mean relative implementation plus validation effort; not dates or staffing
estimates. Releases may be split further after actual implementation evidence.

## Changes to the provisional sequence

1. **Task/result/version boundaries precede regression.** This does not require a
   universal task framework, graph engine or plugin API. A small built-in model
   catalogue is groundwork within v0.2, not a separate large registry project.
2. **UX improvements start in v0.2.** Task-aware prerequisites and protecting unsaved
   Train edits matter before dozens of models. A cosmetic redesign is not required.
3. **Visual understanding comes early.** The application already has Explore charts.
   Add a read-only recipe projection before editing arbitrary connections; do not
   delay all visualization until neural networks are complete.
4. **Bounded Visual and Code modes move earlier than deep learning.** They express
   the product's three experiences; implementing many algorithms first would grow
   UI duplication and postpone source-authority decisions.
5. **MLP and PyTorch are separate projects.** Classical MLP fits the sklearn path;
   deep learning changes devices, artifacts and progress/validation semantics.
6. **Multiclass needs its own contract.** Its omission from the provisional milestone
   labels must not lead to treating every classifier as automatically multiclass.
7. **v1.0 means stability of a declared scope, not all imagined algorithms.** AI,
   external boosters and GPU deep learning need not block a stable local platform.

## Dependency skeleton

```text
v0.1 evidence invariants + compatibility fixtures
    -> v0.2 task/results + two regressors + small catalogue
        -> v0.3 selected ensembles + read-only recipe projection
            -> v0.4 bounded Visual authoring
                -> v0.5 explicit Code revisions / guarded custom execution
        -> v0.6.0 multiclass -> v0.6.1 text pipelines
        -> v0.7 target-free clustering (new evaluation semantics)
        -> v0.8 sklearn MLP (new training-series evidence)
    -> v0.9 integration/compatibility -> v1.0 scoped stability

Optional external boosting and PyTorch: separate need-driven adapters, not implicit prerequisites.
```

The order after v0.2 is a recommendation. Multiclass/NLP can be prioritized over
Code Mode if users value task breadth more than free editing. Do not implement
both paths simultaneously without preserving their independently releasable gates.

## v0.2.0 — generalized supervised boundary and regression

- **Goal/scope:** retain binary behavior and add single-target tabular regression
  with Linear Regression/Ridge, MAE/MSE/RMSE/conditional R2, the existing holdout and
  preparation vocabulary. Add catalogue descriptors and task-aware controls.
- **Prerequisites:** approve task/version/result/migration policy; build realistic
  released-schema compatibility fixtures; see [implementation plan](V0_2_IMPLEMENTATION_PLAN.md).
- **Backend:** widen Project objective safely; new IR/plan/result dispatch and
  regression workload; catalogue existing models before adding regressors.
- **Frontend:** task at creation, numeric target policy, no positive class or
  regression stratification, discriminated historical metrics and comparison;
  guard discarded Train drafts.
- **Tests/docs:** v1 golden preservation, schema upgrade fixtures, actual two-regressor
  execution, metric edge/result validation, source corruption and comparison;
  task contracts, source setup and synthetic regression guide.
- **Acceptance:** old Projects/Runs remain unchanged and readable; both task workflows
  execute exact persisted source; invalid/unknown task versions fail explicitly.
- **Exclude:** multiclass, clustering, text, new charts requiring predictions,
  feature engineering, custom code, graph engine, PyTorch, external libraries.
- **Effort/risk:** L; highest risk is legacy/migration/result compatibility, not fitting
  LinearRegression. Do not expose eight regressors before this gate passes.

## v0.3.0 — selected ensembles and inspectable recipe structure

- **Goal/scope:** add Decision Tree/Random Forest regressors and Extra Trees for
  supported binary/regression tasks; read-only projection of the saved recipe.
  This is a small catalogue extension, not every boosting library.
- **Prerequisites:** v0.2 task/results/catalogue and source-hash compatibility.
- **Backend:** curated new capabilities/constructors, matrix/resource checks and
  provenance; no new scheduler or model-import mechanism.
- **Frontend:** descriptor-driven parameter forms and accessible read-only recipe
  map; clear feature/split/model/evaluation identities.
- **Tests/docs:** descriptor coverage, constructor/parameter/golden tests, actual
  bounded fitting per adapter family, map equivalence/accessibility; ensemble guide.
- **Acceptance:** adding a model does not duplicate task validation; map has no
  independent execution state and does not invent node-level progress.
- **Exclude:** user-drawn graphs, generic nested estimators, XGBoost/LightGBM/CatBoost,
  HPO and feature-importance claims without frozen evidence.
- **Effort/risk:** M/L; sparse/default/resource differences across models. A later
  v0.3.x may add Gradient Boosting or constrained Bagging after separate acceptance;
  AdaBoost/HistGradientBoosting remain candidates, not obligations.

## v0.4.0 — bounded Visual authoring

- **Goal/scope:** edit the existing recipe through nodes/panels and typed permitted
  connections, with identical forms/canvas execution semantics.
- **Prerequisites:** read-only projection, stable task/capability descriptors, UI draft
  guards; approved layout storage and accessible canvas choice.
- **Backend:** reuse revision-guarded intent APIs; validate only representable recipes.
  Add layout metadata separately if persisted; no second executable graph store.
- **Frontend:** node selection/parameter panels, typed edges, issue mapping, keyboard
  alternatives and a clear switch back to forms. React Flow is a candidate, not yet installed.
- **Tests/docs:** forms-to-canvas roundtrip and plan/hash equality, layout-only edits,
  illegal/cyclic edges, stale saves and keyboard workflows; visual recipe semantics.
- **Acceptance:** no semantic loss switching views; unsupported connections are blocked;
  no learned transformation is implied to fit on the full source before splitting.
- **Exclude:** arbitrary DAGs, joins/multiple sources, execution-per-node animation,
  fitted transformed previews and custom node plugins.
- **Effort/risk:** L; mismatched authority and misleading dataflow are the main risks.

## v0.5.0 — editable Code revisions, conditionally executable

- **Goal/scope:** explicit fork from generated source into one editable Python file;
  retained structured parent, source-authority switch, saved exact-source Runs with
  honest custom-evidence trust labels.
- **Prerequisites:** approved trust boundary and custom result contract; revision
  lineage storage, draft behavior and descendant cleanup acceptance.
- **Backend:** code revision/source artifacts and manifest source-kind dispatch;
  reuse owned execution with explicit custom-output validation policy.
- **Frontend:** lazy editor (Monaco/alternative decision), save/fork/return-to-parent,
  disabled structured controls for custom revision, consent and diagnostics/history.
- **Tests/docs:** mode authority, retained parent, exact source, malformed/custom
  results, managed artifact containment, descendants/timeouts, secret-log handling;
  security and custom-result contract.
- **Acceptance:** arbitrary Python is never reverse-converted; history remains intact;
  execution is either explicitly trusted-local or unavailable. Custom self-reported
  metrics never imply controlled comparability with generated evaluations.
- **Exclude:** terminals, arbitrary dependency installation, multi-file workspaces,
  debugger, VS Code extensions and untrusted hosted execution.
- **Effort/risk:** XL; security/trust is a release gate. If it cannot be met, ship
  fork/save/inspect only as an explicitly non-executable editor increment and defer
  executable Code Mode. Do not market that increment as completed custom execution.

## v0.6.0 — multiclass; v0.6.1 — sparse text classification

These are separate acceptance milestones, not one inseparable release.

- **Goal/scope:** first add a finite typed class vocabulary, NxN confusion matrix and
  explicit metric averaging. Then text columns with built-in cleaning, Count/TF-IDF,
  bounded n-grams and mixed sparse tabular input; start with existing compatible models.
- **Prerequisites:** task/result dispatch, matrix capabilities, source versioning;
  text further requires train-only vocabulary and shape-aware branches.
- **Backend:** multiclass policy/result renderer contract; then 1D text selector,
  vectorizer constructors, sparse/resource bounds and fitted vocabulary evidence policy.
- **Frontend:** averaging/class context and general matrix; then text-specific
  Prepare controls and honest unsupported-model messages.
- **Tests/docs:** absent training classes, typed labels, average/AUC availability;
  held-out vocabulary leakage, empty docs/vocabulary, Unicode, sparse end-to-end and
  memory limits; separate multiclass and text walkthroughs.
- **Acceptance:** every score states its task/average/population; unseen text tokens
  never enter learned vocabulary; existing binary/regression histories still render.
- **Exclude:** embeddings, language detection framework, document annotation,
  arbitrary tokenizer code, transformer models and raw-document logging.
- **Effort/risk:** L each; label conventions and sparse/text resource expansion.

## v0.7.0 — target-free experiments

- **Goal/scope:** K-Means and MiniBatch K-Means with explicit in-sample descriptive
  cluster evidence; no fake supervised target or accuracy.
- **Prerequisites:** target-free task/row policy, assignment evidence/privacy contract,
  feature-space comparability and bounded result storage.
- **Backend:** clustering adapter/evaluator, sizes/inertia/conditional silhouette,
  assignment artifacts; existing Run ownership/finalization stays authoritative.
- **Frontend:** target-free preparation, cluster settings, sizes/validity/context and
  clear in-sample labels. Projection is optional only with actual frozen evidence.
- **Tests/docs:** cluster/sample bounds, seed, missing features, single-cluster and
  undefined metrics, assignment integrity; synthetic clustering guide.
- **Acceptance:** clustering Runs remain valid without a target; cluster labels are
  nominal and comparison does not pretend rowwise cluster IDs align.
- **Exclude:** DBSCAN/agglomerative/GMM/PCA in the first increment, supervised metric
  reuse, t-SNE/UMAP and arbitrary N-way comparisons. Add those via later 0.7.x gates.
- **Effort/risk:** L; a new evidence/fit population rather than another classifier.

## v0.8.0 — classical neural models

- **Goal/scope:** sklearn MLPClassifier/MLPRegressor, curated layers/solvers, seed,
  validation policy and actual bounded loss/validation history where available.
- **Prerequisites:** approved early-stopping population semantics and series protocol;
  task/model resource bounds and progress without fabricated epochs.
- **Backend:** MLP capabilities, safe shape/solver defaults, versioned training-series
  artifact; same complete preprocessing-plus-model retention.
- **Frontend:** bounded layer list, solver-specific controls and truthful series view.
- **Tests/docs:** convergence/failure, small validation sets, series integrity,
  solver/input compatibility and exact-source preservation; MLP limits guide.
- **Acceptance:** test holdout is never used for early stopping; internal validation
  preprocessing scope is stated; no new deep-learning dependency required.
- **Exclude:** PyTorch/GPU/CNN/RNN/transformers, distributed training and arbitrary architectures.
- **Effort/risk:** M/L; internal validation leakage claims and compute cost.

## v0.9.0 — integration, adoption and extension boundaries

- **Goal/scope:** stabilize approved tasks/modes and improve contributor/adoption
  friction; do not use this version as a bucket for every unshipped algorithm.
- **Prerequisites:** real user feedback and compatibility evidence across prior releases.
- **Backend:** only demonstrated integrity/performance fixes, version dispatch and
  small internal adapter contracts; optional dependency states if extras are approved.
- **Frontend:** consistent draft/readiness/conflict semantics and accessible mode/history
  navigation; no new design system by default.
- **Tests/docs:** upgrade corpus spanning versions, focused browser acceptance,
  measured large-history behavior, tested platform claims, API/support and recovery guides.
- **Acceptance:** supported source setup is repeatable; declared old histories remain
  inspectable; plugin/provider boundaries are documented rather than implied.
- **Exclude:** marketplace, cloud orchestration, authentication as a bolt-on, production
  serving and arbitrary undocumented plugin execution.
- **Effort/risk:** M/L; integration debt and an uncontrolled compatibility matrix.

## v1.0.0 — stable declared local platform

- **Goal/scope:** stable user-facing contracts for the tasks/modes actually accepted;
  useful without AI and honest about optional functionality.
- **Prerequisites:** explicit supported environments, upgrade policy, trustworthy
  release/security channels and no unresolved P0/P1 in declared scope.
- **Backend/frontend:** only stabilization required by acceptance; publish compatibility
  and evidence semantics. Preserve data/history/source authority through upgrades.
- **Tests/docs:** source install, migrations, core workflows, safety/failure/recovery,
  accessibility and optional-component absence; complete supported feature inventory.
- **Acceptance:** reproducible synthetic demos, required CI and release identity verified;
  limitations and deprecations documented; no dependence on an AI API key.
- **Exclude:** unimplemented roadmap promises and an implied enterprise/security SLA.
- **Effort/risk:** M after earlier gates; scope inflation is the main release risk.

## Deferred parallel candidates, not v1.0 prerequisites

PyTorch CPU/GPU adapters, CNN/RNN/transformer data contracts, external boosters,
t-SNE/UMAP, advanced feature engineering, HPO, multi-file IDEs and optional AI each
require separate approved scope. PyTorch should start with a small CPU experiment
and can use the existing admission/history machinery through a new workload adapter.
Do not reimplement orchestration or require PyTorch before the three experiences
are useful. AI should propose user-reviewed changes through the same contracts,
never become required for validation or execution.
