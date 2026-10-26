# ML feature expansion feasibility

Date: 2026-10-24. This is a proposal, not current capability or approved scope.
Repository baseline: [baseline](V0_1_BASELINE_AUDIT.md). Relative effort S/M/L/XL
includes implementation, contract work, validation, UI and docs, not calendar time.
Within-family order below is intentional; do not add every listed algorithm at once.

## Shared prerequisites and present support

Only binary Logistic Regression, Decision Tree Classifier and Random Forest
Classifier are supported. Random Forest is an existing bagged-tree ensemble;
that does not imply a generic Bagging UI. All other algorithms below are missing.
Text detection, sparse one-hot output and a process executor are reusable building
blocks, not implemented NLP/deep-learning capabilities.

Each expansion must pass four boundaries: task/target/split intent; resolved
constructor/input capabilities; generated workload; task-specific validated result
and historical UI. See `pipeline_schemas.py`, `services/pipelines.py`,
`codegen/{schemas,plan,render}.py`, `execution/results.py` and frontend
`lib/api/{pipelines,runs,evaluation-policy}.ts`. Keep legacy paths intact.

Use built-in sklearn estimators first: no new dependency is needed for the listed
classical families. Verify constructors and resolved defaults against the pinned
supported sklearn version when implementing; do not blindly copy examples from
another version. Optional external libraries need independent adapters, provenance,
license review and tested Python/platform compatibility; no dependency is installed
or upgraded by this audit.

## A. Regression

### Task and evidence contract

New Projects select regression explicitly; existing Projects remain binary. A
regression target must be numeric and finite when observed, excluding booleans,
uninterpretable object columns and unsupported precision-losing conversions.
Missing targets may be excluded under an explicit frozen policy; do not impute
them. Constant targets are not automatically unusable, but affect R2 availability.
The first release supports one target and the same seeded random holdout, with
stratification unavailable. Feature semantics and train-only fitting remain intact.

Return MAE, MSE and RMSE as finite nonnegative losses in a new result protocol.
R2 can be negative; fewer than two test rows or constant test ground truth should
produce an explicit unavailable reason under the proposed policy. Do not inherit
the v1 validator's `[0,1]` constraint. Do not serialize NaN/-Infinity or silently
accept library force-finite substitutions as measured R2. Required-loss overflow
should fail validation with a safe stage rather than finalize a misleading score.
These are proposed ML Studio policies; R2 edge behavior is documented by the
[official r2_score API](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.r2_score.html).

Basic evaluation is a metric table and population/context. Actual/predicted and
residual plots require new frozen per-sample or deliberately aggregated evidence;
they cannot be reconstructed from v1 scalar metrics. Do not promise these plots
in the minimal regression release. Task, target interpretation/units and metric
definition join the comparison policy; lower-loss direction is explanatory, not
a winner declaration.

### Per-estimator assessment

All rows inherit the regression contract, backend result dispatch, task-aware
Data/Prepare/Train/Evaluate and shared compatibility tests above. Feature/model
preprocessing stays explicit, never auto-added. Additional requirements are:

| Order / algorithm / effort | Backend and pipeline work | Frontend configuration | Specific tests / risks |
| --- | --- | --- | --- |
| R1 Linear Regression / M after task foundation | Add `LinearRegression` capability, resolved intercept/solver-related choices; existing numeric/OHE branches | Small intercept form and regression summary | Exact source, rank-deficient design, sparse path, constant target and complete model roundtrip; coefficients not causal explanations |
| R2 Ridge / M | Add nonnegative-alpha contract with a deliberate positive default; resolve solver compatible with declared sparse/dense inputs | Alpha/intercept controls and scaling explanation | Invalid alpha, ill-conditioned columns, deterministic solver support; no unrecorded solver selection |
| R3 Lasso / M | Explicit alpha, iteration/tolerance and convergence policy; resolve coordinate selection/seed where relevant | Alpha and bounded iteration controls | Convergence warnings/insufficient iterations, constant features and sparse compatibility; do not promise automatic feature selection quality |
| R4 ElasticNet / M | Add bounded `l1_ratio`, alpha and solver choices using the same supervised adapter | Alpha/l1-ratio help plus iteration controls | Ratio boundaries and persisted fitted pipeline; small sample/high dimension convergence costs |
| R5 Decision Tree Regressor / S after R1 | Reuse tree parameter schema where meanings match; regression criteria distinct from `gini` | Depth/minimum sample fields and criterion descriptor | Small leaf populations, held-out negative R2, seed and artifact tests; old classifier ID stays unchanged |
| R6 Random Forest Regressor / M | Forest schema, explicit regression criterion/max-features/bootstrap/seed/work bound | Number of trees/depth, resource warning | Full source determinism, n_jobs policy and output size; do not inherit classifier max-features implicitly |
| R7 K-Nearest Neighbors Regression / M | Neighbors/weights/metric capabilities; train size guard; explicit fit representation | Neighbors/weights and scaling prerequisite | k greater than training rows, zero-distance/tied neighbors and sparse route; model retains training information, a privacy/storage concern |
| R8 Support Vector Regression / M/L | Kernel/C/epsilon/gamma, matrix compatibility and workload bounds | Constrained kernel controls; no arbitrary kernel code | Nonlinear runtime growth, sparse/dense variants, constant/negative targets and timeout; avoid large-data performance claims |

Start v0.2 with **R1 and R2 only**. Linear-family solver/regularization distinctions
are grounded in [sklearn linear models](https://scikit-learn.org/stable/modules/linear_model.html).
KNN depends on neighborhood/metric and training population
([API](https://scikit-learn.org/stable/modules/generated/sklearn.neighbors.KNeighborsRegressor.html));
kernel SVR needs careful scaling and workload sizing
([API](https://scikit-learn.org/stable/modules/generated/sklearn.svm.SVR.html)).
The release order/UX/effort assessments are architectural recommendations.

## B. Bagging and boosting

These reuse supervised task protocols once available. Binary metrics already exist;
regression metrics require the new protocol; multiclass needs a separate averaging
and label-vocabulary contract. Do not infer every estimator supports every matrix,
missing-value policy or score method. Ensemble capability checks must include the
base estimator and learned preprocessing, not just the outer class name.

| Recommended order / family | Current support | Backend/pipeline changes | Frontend and evidence | Tests / risk / effort |
| --- | --- | --- | --- | --- |
| E1 Extra Trees Classifier/Regressor | None | New IDs; extend tree/forest descriptors, explicit criteria/seed/bootstrap/max-features | Existing Train fields plus task-specific results; importance plots only with new evidence | Estimator defaults differ from Random Forest; reproducibility and memory bounds; M |
| E2 Bagging Classifier/Regressor | Random Forest only, no generic wrapper | Whitelist one compatible tree base initially; typed nested parameters, clone/seed semantics, no arbitrary estimator objects | Constrained base-estimator selector and ensemble controls | Base-parameter invalidity, seed propagation, fit/serialization; avoid a universal meta-estimator builder; M/L |
| E3 Gradient Boosting Classifier/Regressor | None | Explicit stage count/rate/depth, loss, subsampling and supported input representation | Curated boosting controls, existing task results; no fabricated stage curves | Learning/preprocessing separation, failure/size limits, solver-version defaults; M |
| E4 HistGradientBoosting Classifier/Regressor | None | Dense-input declaration; bounded explicit densification only if approved, otherwise reject sparse combination; categorical/missing policy remains explicit | Explain why a sparse recipe is incompatible; no silent OHE removal | Matrix guards, dense memory estimate, bin/category constraints, early-stopping population; M/L |
| E5 AdaBoost Classifier/Regressor | None | Base-estimator/task compatibility, weight support and version-resolved loss/algorithm options | Small curated stump-based configuration initially | Invalid base estimator, algorithm removals/version differences, degenerate classes; M/L |
| E6 optional XGBoost | None | Extra adapter/package gate, pinned tested build, sparse/missing and objective mappings, no library autologging as truth | Available only when verified dependency installed; actionable missing-extra state | Objective/label encodings, CPU build, serialization/provenance and reproducibility; L |
| E7 optional LightGBM | None | Separate optional adapter and environment check, leaf/depth/category policies | Curated task/categorical controls rather than full library parameters | Native library availability, determinism/thread policy and categorical interpretation; L |
| E8 optional CatBoost | None | Optional adapter; explicit raw categorical/text feature contract rather than universal numeric preprocessing | Library-specific allowed input/parameter UI | String/category identity, serialization and platform wheels; L |

Score availability, input handling and ensemble-specific controls should be checked
against the [official ensemble guide](https://scikit-learn.org/stable/modules/ensemble.html).
Recommendations above deliberately constrain the application surface beyond what
the libraries can expose. Extra Trees is a smaller first extension than all boosting
families. Missing optional packages must never hide or prevent reading old Runs.
Do not assume compatible Python 3.14.2 wheels exist for any future extra without
checking at that release. No optional-library installation matrix was run here.

## C. Clustering, projection and target-free tasks

Task-free-target is not represented today: Project/IR/readiness/population/result
and frontend summaries assume `target`. Add a task policy distinguishing
`clustering` from `dimensionality_reduction`, with no fabricated positive class or
supervised holdout. A first clustering experiment can fit selected source rows and
report explicitly **in-sample descriptive** evidence. An inductive holdout evaluation
is a later distinct policy, not an inherited classification split.

Freeze missing-feature handling, selected population, scaling, distances and
algorithm seed/parameters. Keep labels/assignments and any projection in new bounded
immutable artifacts, not raw rows in ordinary SQLite metadata. Cluster IDs are
nominal and can permute; never compare numeric cluster IDs as if they were classes.
External ground-truth metrics are absent unless a separate evaluation label is
explicitly supplied in a later contract.

| Order / algorithm / effort | Backend and pipeline changes | Frontend / metrics and visuals | Tests / main constraint |
| --- | --- | --- | --- |
| U1 K-Means / L with task foundation | Target-free recipe, explicit cluster count/init/n_init/seed, fitted transform pipeline and assignment evidence | Cluster count/sizes and inertia; silhouette only when valid; projection labelled as projection | k/population bounds, reproducibility, empty/duplicate clusters, sample evidence integrity; scaling changes distances |
| U2 MiniBatch K-Means / M | Reuse task; explicit batch size/init/passes, no promise of out-of-core CSV ingestion | Batch controls and same descriptive outputs | Batch-size/population edges and seed; minibatch estimator alone does not make ingestion streaming |
| U3 DBSCAN / M/L | eps/min_samples/metric and explicit noise label policy; no universal predict-on-new-data claim | Cluster/noise counts, noise fraction; silhouette policy must state noise filtering | All-noise/one-cluster/duplicate points, quadratic-neighborhood memory risk; no fabricated held-out accuracy |
| U4 Agglomerative / L | Linkage/metric compatibility, optional connectivity, fit-only capability; output size bounds | Linkage control, sizes; dendrogram only if linkage evidence retained | Ward distance restrictions, sample count/resource cap, no generic predict API |
| U5 Gaussian Mixture / M/L | Component count/covariance/reg_covar, seed/n_init, convergence and probability evidence | Component sizes, convergence, likelihood/AIC/BIC with explicit evaluated population | Singular covariance, tiny components, nonconvergence and seed; avoid equating AIC with classification accuracy |
| U6 PCA / L first global transform | Cross-column numeric transform stage after feature branches; explicit component count/solver/whitening; trained artifact and projection scope | Explained variance and bounded component projection; no predictive score by default | rank/component/population bounds, centering/memory behavior and fit-vs-transform leakage |
| U7 t-SNE visualization / L, defer | Separate visualization adapter and sampled evidence, not a general predictive transformer | Label sampling/seed/perplexity; no metric-preserving or new-row transform promise | Repeated embeddings may differ; no invented links to old points; expensive pairwise work |
| U8 optional UMAP / L, defer | Optional dependency, explicit neighbor/distance/seed and fitted embedding evidence | Bounded projection labelled with assumptions | Version/thread determinism, dependency/platform support; embedding quality is not model accuracy |

Silhouette needs a valid label population with at least two and fewer clusters than
samples; define unavailable reasons rather than zero. Sampling, exclusion of DBSCAN
noise and distance settings must be frozen for comparisons. Internal metrics are
not universal measures across arbitrary preprocessing spaces.
[Clustering guide](https://scikit-learn.org/stable/modules/clustering.html).
Mixture likelihood and information criteria need their own result semantics
([GaussianMixture API](https://scikit-learn.org/stable/modules/generated/sklearn.mixture.GaussianMixture.html)).
PCA belongs at a multivariate boundary; current feature-local operation lists cannot
express it faithfully ([PCA API](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html)).

## D. NLP and text pipelines

Present support is semantic `text` detection and source inspection only. Included
text is blocked by `services/pipelines.py:validate`. `render.generate` selects
features as lists of columns, producing 2D branches; a text vectorizer generally
needs one document sequence. Current `Constructor.parameters` also cannot represent
all nested vocabulary/transformer choices. Extend typed contracts rather than
passing arbitrary Python tokenizer functions through JSON.

| Increment / effort | Backend and Dataset/pipeline work | Frontend/evidence | Tests / risk |
| --- | --- | --- | --- |
| N1 document selection and missing policy / M | Explicit text column, one-dimensional branch, empty/missing document behavior and document-length limits | Text-specific Prepare controls and redacted/limited source preview | Null, empty, whitespace, Unicode, all-empty training subset; never stringify missing data into a token |
| N2 cleaning/tokenization / M | Versioned deterministic built-in cleaning options; preserve raw source; declare lowercase/accents/token pattern/stopword source | Explain each enabled cleaning step; no inferred language promises | Unicode boundaries, punctuation, language/stopword assumptions; no arbitrary callback code |
| N3 Bag of Words / M | `CountVectorizer`, train-only vocabulary and explicit min_df/max_df/max_features/ngram range | Vocabulary bounds and token-count settings | Held-out token never learned, empty vocabulary, feature names and artifact identity |
| N4 TF-IDF / M | `TfidfVectorizer` or Count+TFIDF in typed sequence; explicit normalization/IDF choices | Weighting description; same sparse branch | IDF learned on training only, unknown tokens, fit artifact roundtrip |
| N5 word/character n-grams / M | Analyzer choice and bounded n-gram range; character features not a second raw Dataset | Analyzer-specific form and resource warnings | Token explosion, one-character docs, vocabulary/memory caps |
| N6 mixed text/tabular classification / L | Preserve sparse combination, select compatible classifier; scale numeric branch before sparse concat, avoid centering combined sparse matrix | Reuse task Train/Evaluate with input compatibility issues | Sparse end-to-end and memory tests; Logistic Regression first, not every tree or booster |
| N7 vocabulary/feature inspection / M/L | Bounded immutable feature-name/statistic evidence from trained vocabulary; privacy review | Top terms and weights, clearly fitted-training facts | Names/weights alignment, truncation and sensitive token leakage; no raw document logging |

These increments use sklearn's existing vectorizers; NLTK/spaCy/embeddings are not
prerequisites. Sparse vocabulary handling is supported by
[the official feature-extraction guide](https://scikit-learn.org/stable/modules/feature_extraction.html).
The application still needs a new shape-aware compiler branch, resource bounds and
historical feature evidence. Start binary text classification; general language
understanding, transformers, token annotation and arbitrary text cleaning scripts
remain later scopes. Multiclass text requires the separate multiclass result policy.

## E. Neural networks in two deliberately separate stages

### E1: sklearn MLP (M/L after supervised task contracts)

Add separate MLPClassifier and MLPRegressor capabilities, typed bounded hidden-layer
sizes, activation/optimizer choices, learning-rate/regularization/iteration controls,
seed and early-stopping policy. UI needs a simple layer-size list and solver-specific
controls, not a neural graph editor. Data ingestion need not change for tabular input;
scaling and sparse/dense compatibility must be explicit. Existing classifier or
regression metrics apply; no new dependency is required.

Training/validation learning curves are **new evidence**. Persist actual available
loss/validation series with their population and step meaning; never synthesize
epochs from iterations or use held-out test data for early stopping. If using the
estimator's internal validation split, label its preprocessing scope honestly:
outer training preprocessing is fitted before that internal split. A stricter
inner-validation leakage guarantee requires an explicit earlier split and additional
adapter work. Solver capabilities and early-stopping behavior differ, so constrain
options and test their interactions rather than render all parameters together.
[Official MLP guidance](https://scikit-learn.org/stable/modules/neural_networks_supervised.html).

Tests: seed repeatability in a declared environment, nonconvergence, tiny internal
validation populations, classification/regression result validation, artifact
roundtrip and loss-series bounds/availability. CPU time and memory remain bounded
operational risks. MLP first is smaller than introducing a deep-learning framework.

### E2: PyTorch adapter (XL, separate experimental milestone)

Reuse Run identity, immutable packages, process admission, logs and finalization.
Add a **workload adapter**, not an independent competing history store. It must
define architecture configuration versus custom-code authority, generated training
loop, data loader/batch semantics, optimizer/scheduler, validation and early stopping,
CPU/GPU selection, seed/device/determinism provenance, checkpoints, metrics series
and model reconstruction/serialization metadata. A sklearn joblib-complete-pipeline
declaration must not be reused for a tensor checkpoint.

First scope should be a curated small CPU tabular network; GPU support only after
device/version/resource/cleanup tests. Never silently switch devices or report
cross-device bitwise reproducibility. PyTorch itself warns that reproducibility is
not guaranteed across all releases/platforms/devices
([official reproducibility notes](https://docs.pytorch.org/docs/2.14/notes/randomness.html)).
An optional installation extra must be tested on the actual supported Python/OS;
do not make all users install accelerator packages. UI eventually needs genuine
epoch/batch progress, separate training/validation series, cancellation semantics,
checkpoint state and device errors. Tests include CPU actual execution, checkpoint
integrity, architecture lineage, adapter-version mismatch, out-of-memory failure
reporting and descendant cleanup. GPU tests require actual GPU hardware and must
not be certified from mocks. CNN/RNN/transformer datasets, distributed training,
custom arbitrary architecture code and deployment are separate later projects.

## Recommended expansion order

1. Task/result version boundaries and compatibility fixtures, plus catalogue for
   existing models; then Linear Regression and Ridge.
2. Additional regressors/Extra Trees selectively; small ensemble release rather
   than all meta-estimators and external boosters together.
3. Bounded Visual mapping and Code lineage groundwork can proceed before large
   algorithm expansion; see [roadmap](DEVELOPMENT_ROADMAP.md).
4. Multiclass and text each get their own acceptance contract; K-Means begins a
   separate target-free milestone. None is just another model dropdown entry.
5. sklearn MLP before optional PyTorch; t-SNE/UMAP/external boosters only with
   demonstrated user need and tested dependency support.

Every new family needs a synthetic reproducible walkthrough, safe invalid-input
states, new-plan golden/source identity assertions, full fitted-artifact checks,
and historical v1 read/compare tests. Existing Runs must remain inspectable even
when their optional training environment is no longer installed.
