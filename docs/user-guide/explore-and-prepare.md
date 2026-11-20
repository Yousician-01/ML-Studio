# Explore and Prepare

## Data Preparation Studio (v0.5 development)

The primary workflow is **Dataset → Data Preparation → Train → Runs / Evaluate**.
Uploading a CSV opens the studio; an existing Project loads its saved source and
recipe. Dataset navigation remains for source management. Old `view=prepare` and
`view=explore` links work; Explore opens diagnostics within the unified workspace.

The central table shows the existing bounded **20 source-preview rows**, plus
stateless temporal and generalized outputs from the backend. Scroll, select headers, search names,
or page through 30 columns. Headers show actual semantic types, missingness where
available, target and exclusion status. Cells are read-only. `null` means missing;
exclusion controls estimator input and does not delete visible source values.

### Column actions

Right-click a header or use **⋯**. The same type-aware actions are searchable in
**Add Transformation**. Arrow keys/Home/End navigate menus; Escape closes them.
Numeric inputs expose existing imputation/scaling; categorical/binary inputs expose
missing-value and one-hot options. Datetime inputs open the reused component,
cycle, difference/tenure, age and nested-expression editors with unchanged UTC
semantics. **View Column Profile** opens source evidence; **Dataset diagnostics**
retains existing overview, quality and relationship views. Regression continues to
use its own numeric diagnostics. Derived distributions are not fabricated.

Configure an operation, then **Apply** or Cancel. Apply changes the studio draft.
Temporal editing requires its existing preview before **Apply temporal changes**.
**Save preparation** persists that IR using the existing revision-checked API.
Configure generated-feature preprocessing through the generated column's menu.
Invalid saved intent remains visibly blocked until repaired.

**Source & target** reuses upload, semantic and target controls. These Dataset
changes save immediately and are outside transformation undo; save/discard a pending
draft first. Binary positive-class selection changes the preparation draft and
requires Save. Source replacement preserves history and requires explicit reset
when the current recipe becomes stale.

### Applied Steps, undo and save

The collapsible right panel is reconstructed from IR, not button-click history.
Fixed stages are source, parsing policies, dependency-ordered temporal outputs, generalized expressions,
feature participation, then existing per-feature preprocessing branches. Dormant
choices are labelled **not executed**; invalid legacy entries remain repairable.
There is no arbitrary reordering.

- **Select** a step for non-destructive inspection. Expression prefixes are actually
  recomputed by the existing runtime, not hidden from a previously calculated final
  table. Active intent and the Live Code Companion stay on the latest draft.
- **Edit** reuses the relevant editor. **Remove** changes only that configuration;
  dependents remain with warnings so references can be repaired explicitly.
- **Revert to this step** confirms and lists later configurations to remove from
  the draft. Dataset, target, model and split context remain. Reverting before
  participation restores original non-target candidates as included; review
  identifiers/unsupported types. It never deletes source bytes or Runs. Save is
  required to persist the revert.
- **Undo/Redo** covers 30 applied draft edits, including add/edit/remove/revert.
  A new edit clears redo; Save/Discard resets history. Applied Steps is current
  configuration, not undo history.

Applied IR and undo history can recover when navigating within the same tab (five
Project/Dataset buffers), checked against saved IR/schema. Conflicts retain work
but block saving. This memory is not authoritative persistence and cannot survive
full reload/tab close. Browser traversal confirmation varies; memory recovery also
protects applied drafts when traversal cannot be cancelled. Unapplied form fields
have leave warnings but are outside that buffer. Save for durable persistence.

### Preview and Train boundaries

The latest table is a source-plus-derived reference, **not a fitted training
matrix**. Imputers/scalers/encoders are never fitted on the full Dataset to create
a preview. Selecting a fitted stage shows an explicit unavailable state; fitted
one-hot output names/width are not guessed. Row-wise derivations do not fit statistics.

**Continue to Train** saves pending intent, validates returned preparation and
blocks invalid/stale transformations. Model/split configuration remains in Train;
their absence does not prevent opening it. Tracking, generation, Code Mode and
historical evaluation retain their existing paths.

**View options → Reset preparation** preserves the existing reset: it saves a
fresh current-source recipe and clears preparation, model and split after explicit
confirmation. It is separate from reverting a draft step.

## Explore: source evidence

Explore reads managed source and its interpretation, not model predictions. It presents deterministic profiles/missingness, numeric distributions and box plots, categorical frequencies, and supported relationships. Classification views include target class information. Numeric correlations describe association, not causality or leakage-proof feature selection.

Regression provides numeric target statistics/histogram, paginated numeric feature selection, full-pair Pearson correlation and a source scatter capped at 200 pairs. Correlation uses eligible complete source pairs; missing-pair counts are separate. Grouped categorical regression target summaries are not implemented.

Unavailable relationships carry reasons, not invented values. No source plot is a residual plot or held-out evaluation. Raw rows/pairs are transient explicit local inspection, not profile rows in SQLite or ordinary logs.

## Prepare: explicit intent

Review inclusion, effective semantics and target context. Supported operations include compatible mean/median/most-frequent imputation, numeric standard/min-max/robust scaling, and categorical one-hot encoding. Datetime sources can produce explicit temporal features as described below. Raw datetime, text and identifier values still cannot silently reach numeric estimators.

Binary requires an explicit typed positive class. Regression/multiclass do not invent one. Target is never a feature and is never imputed. Missing binary/regression targets are excluded before splitting; missing multiclass targets are rejected.

Studio panels update a draft on Apply; **Save preparation** persists it. The retained
legacy Prepare component still saves per-feature edits immediately. Neither rewrites
CSV. Learned preparation fits training rows only inside the complete model pipeline.

Open **Show Code** to inspect the recipe in Python. Viewing does not save a proposed pipeline or create a draft. Incomplete/invalid configuration produces validation instead of executable-looking stale source. Train uses explicit save actions; unsaved Train input can be previewed without silently persisting it.

After source replacement, resolve stale configuration and validation before training. See [Training](training.md) and [Code workspace](code-workspace.md).

## Datetime feature engineering (v0.5 development)

Available for binary classification, multiclass classification and regression. In
Dataset or **Source & target**, set the source's semantic type to **datetime**. Open
its column menu or Add Transformation in Data Preparation:

1. Choose it in **Datetime feature engineering** and configure parsing. Use
   `ISO8601`, or a numeric explicit format such as `%d/%m/%Y`. Apply the source
   policy; configure every reference column too.
2. In **Guided Mode**, name an output and select a calendar component, predicate,
   date difference or calendar age. Add multiple features by repeating this step.
   Periodic components offer raw, sine/cosine, or both; cyclic outputs append
   `_sin` and `_cos` to your chosen name.
3. Use another datetime column or an explicit fixed ISO reference. For example,
   tenure/recency is `date_diff(prediction_date, signup_date, days)` or
   `date_diff(prediction_date, last_active_at, days)`. Time until a deadline is
   `date_diff(deadline, prediction_date, days)`; reverse operands in Expression Mode.
4. **Expression Mode** builds nested functions and references using controls,
   never Python text. For example `cyclic_sin(hour(transaction_at))`, or a cyclic
   encoding referencing a previously defined hour feature. Both modes produce the
   same recipe. Edit/remove individual definitions or remove unused source policies.
5. Explicitly exclude configured raw datetime sources using the checkbox or their
   feature participation controls. They remain available for derivation and in the
   immutable CSV, but must not be sent untransformed to the estimator.
6. Preview types, up to 20 source-row values, missing/invalid counts and warnings.
   **Apply temporal changes**, then **Save preparation**. Configure generated-feature
   imputation/scaling from its column menu.
7. Inspect **Show Code**, configure Train, and run normally. The complete saved
   model accepts the original raw input columns and performs the same derivations.

### Operation catalogue

| Operation | Output / meaning |
| --- | --- |
| `year`, `quarter`, `month`, `day` | Numeric calendar year, quarter 1–4, month 1–12, day of month |
| `day_of_week`, `iso_week`, `iso_year`, `day_of_year` | Monday 0–Sunday 6; ISO week and ISO week-year (which can differ from calendar year); ordinal day |
| `hour`, `minute`, `second` | Numeric UTC clock components |
| `is_weekend`, `is_leap_year`, `is_month_start`, `is_month_end`, `is_quarter_start`, `is_quarter_end`, `is_year_start`, `is_year_end` | Binary 0/1; missing timestamps remain missing, not false |
| `cyclic_sin`, `cyclic_cos` | Numeric encoding of an allowed component or its derived reference |
| `date_diff(first, second, unit)` | First minus second in seconds/minutes/hours/days; fractional and negative durations retained |
| `calendar_age(birth, reference)` | Completed calendar years; not elapsed days divided by 365. A Feb-29 anniversary occurs March 1 in non-leap years; reversed dates produce signed completed years |

Cycles use `sin/cos(2*pi*(value-base)/period)`: quarter (period 4, base 1), month
(12, 1), weekday (7, 0), hour (24, 0), minute/second (60, 0). Year, age, durations,
day-of-month, day-of-year and ISO week have no automatic fixed-period encoding.

### Parsing, missing values and prediction context

All extraction occurs in **UTC**. Explicit offsets are converted to UTC; named
local timezone/DST interpretation is not offered. For naive timestamps/date-only
sources, choose **Interpret explicitly as UTC** or **Reject without timezone**.
Date-only values denote midnight, not an observed event time. Fixed literals must
be explicit ISO dates/timestamps; naive fixed literals also mean UTC. There is no
implicit current date, runtime inference clock, or inferred prediction timestamp.

Ambiguous `05/11/2026` is invalid under ISO parsing; explicitly choose `%d/%m/%Y`
or `%m/%d/%Y`. Supported directives are `%Y`, `%m`, `%d`, `%H`, `%M`, `%S`, `%f`,
`%z` and literal `%%`; a format must contain year/month/day. Locale-dependent month
names and automatic mixed-format/encoding detection are excluded. Numeric Unix
timestamps/identifiers are not silently parsed; sources must contain string dates.
Detection itself is unchanged and conservative.

Missing values propagate through every operation. Invalid/disallowed values are
counted separately and either block the recipe or become missing through explicit
**Coerce to missing**. Preview counts cover the full source; downstream learned
imputation/scaling still fits training rows only. Full-source invalid dates are
reported even in rows that may later be excluded for a missing target.

Warnings ask you to confirm prediction-time availability of events/references and
consider whether a random split is appropriate. No name-based leakage judgement
or automatic split change is made. Chronological splitting, forecasting, lags,
windows, holiday calendars and arbitrary Python expressions remain deferred.
Generalized arithmetic uses the separate extension described below. Unsaved temporal edits are local UI state; save before closing.


## Generalized Derived Feature Builder (v0.5 development)

Use **Add Transformation > Create Derived Feature** for an empty builder, or the
same action from a non-target column header's right-click/ellipsis menu to preselect an
operand. This stays within Data Preparation. Numeric, boolean and string inputs
are supported; raw datetime needs the temporal editor first. Inputs can be source
columns, typed constants, or derived references. The target cannot be referenced.

**Guided Mode** configures one operation and its inputs. **Expression Mode** nests
operations with visual controls, including IF conditions and branches. Both use
the same typed expression tree. Switching a nested expression to Guided Mode is
refused with an explanation; nothing is flattened or lost. Names start with an
ASCII letter, contain letters/numbers/underscores, and are at most 200 characters.
Names cannot collide with source columns or either kind of derived feature.

For example, create and Apply these in order (the notation illustrates the visual
controls; users do not enter Python):

```text
profit = revenue - cost
profit_margin = safe_divide(profit, revenue)
is_premium = customer_type == "Premium"
high_value = IF(revenue > 5000 AND is_premium, 1, 0)
```

Choose `profit` and `is_premium` as **Derived feature reference**, not Source column.
References execute in stable dependency order even if saved definitions are listed
out of order. Cycles, self-references, absent references and target inputs are
rejected. Existing numeric/binary `temporal-v1` outputs can feed generalized
expressions, for example `safe_divide(tenure_days, 365.25)`. Temporal expressions
cannot consume generalized outputs: temporal runs first.

### Supported operations and value rules

- Arithmetic: add, subtract, multiply, safe divide, modulo, absolute value,
  negation, power, square root, natural log, log1p, round, floor, ceiling, minimum
  and maximum of two values. No strings are silently parsed as numbers. Numeric
  categorical codes remain numeric operands; arithmetic on them is an explicit
  user choice, not an inference of meaningful quantitative distance.
- Comparisons: equal, not equal, greater/greater-or-equal, less/less-or-equal, with
  compatible numeric, boolean or string operands. Boolean and numeric types are
  distinct. Exact integers beyond +/-(2^53-1) are rejected before float conversion;
  large finite floating-point values retain ordinary floating-point semantics.
- Boolean: AND, OR, NOT, is missing, is not missing. Logic uses nullable/Kleene
  semantics: `false AND unknown` is false; `true OR unknown` is true; otherwise
  unknown propagates. Comparisons involving missing values produce unknown.
- Conditional: IF requires a boolean condition and compatible branches. An unknown
  condition produces missing, rather than silently choosing the false branch.
- Strings: trim, lower, upper, length, starts with, ends with, contains, concatenate,
  replace literal substring. No regular expressions. Missing inputs propagate.
- Null handling: coalesce selects the first nonmissing row-wise value, with
  compatible input types. This does not estimate or fit an imputation statistic.

Zero denominators, invalid logarithm/square-root domains, invalid real powers and
numeric overflow produce missing, never uncontrolled infinity or an automatic
zero. Round defaults to zero decimal places, accepts precision -12 through 12,
and uses ties-to-even. Ordinary operations propagate missing inputs. Preview
reports missing counts and rows affected by invalid/domain computations; those
counts may overlap and are not necessarily additive. Coalesce can recover an
invalid result; unselected IF branches do not count as invalid output evidence.
Numeric outputs use float64; boolean outputs are stable 0/1/missing for downstream
estimators, while expression logic preserves their boolean type. String outputs
are categorical and need one-hot encoding for numeric estimators. Null-only outputs
need an operation establishing a concrete type; they are not guessed.

### Preview, Apply and historical steps

**Preview derived feature** invokes the backend's real runtime for that feature
and its dependency closure. It shows output type, bounded sample values, full-source
missing/domain counts and warnings. Other unrelated invalid definitions are retained
and can be repaired individually using the editor's feature buttons. They continue
to block full preparation/training until fixed. **Apply derived feature** requires
a matching successful preview and changes only the Studio draft. Cancel discards
that form. Save preparation persists the complete IR with the existing revision
guard; Apply alone is not durable storage or execution.

New columns appear in the table and **Applied Steps** after temporal derivations
and before feature participation/fitted branches. Select a step to recompute its
actual expression prefix, Edit to reopen its builder, or Remove/Revert with the
existing confirmation. Renaming/removing a feature retains dependent definitions
and warns; references must be repaired explicitly. Invalid groups expose each
retained definition for repair. Undo/Redo and Save/Discard retain their Studio
semantics. Editing a name does not rewrite downstream references automatically.

Configure compatible downstream imputation/scaling/encoding from the new column's
menu. Missing outputs are never silently imputed; included missing outputs without
appropriate imputation block model configuration. All-missing training inputs still
fail safely. Learned statistics fit training rows only after the split.

The same fixed `derived-v1` runtime runs preview, generated workloads, validation/
test transformations and the complete saved-model pipeline. Inference callers pass
original raw inputs, not precomputed derived values; missing required columns fail
validation. Live Code/Code Mode use existing generation/snapshot paths. Historical
Runs and source artifacts remain immutable. Comparison conservatively suppresses
metric deltas when frozen derived definitions/input interpretations differ.

Bounds: 128 generalized features; depth 8 (root at depth 0), 256 nodes/expression,
1,024 nodes/configuration; dependency depth 16; 16 arguments/call; 1,000 characters/
literal; 4,096 characters/computed string. Oversized computed strings become missing
with invalid diagnostics. Preview retains the existing 20-row browser bound.
No arbitrary Python, cross-row aggregates, row filtering, lag/window operations,
learned thresholds, new scalers/encoders/imputers, or arbitrary step reordering.

## Advanced Imputation (v0.5 development)

Choose **Advanced Imputation** from an included or excluded compatible column's
right-click/ellipsis menu or search in **Add Transformation**. Existing quick
mean/median/most-frequent options remain available. The supervised label cannot be
imputed. Supported targets are numeric, categorical and binary model features,
including temporal and generalized outputs.

Each configuration has ordered rules, a final fallback and an optional indicator.
Use **Add Rule**, **Edit Rule**, **Remove Rule**, **Up** and **Down** to configure
precedence within this stage. Conditions reuse the visual derived-expression
controls: comparisons, boolean logic and missing checks can read compatible source,
temporal and generalized columns. Only explicitly true conditions match; unknown
conditions do not. Every rule additionally requires the target cell to remain
missing. Nonmissing original cells are preserved, and the first successful fill
wins. An unavailable group statistic leaves the cell for later rules/fallback.

Strategies are compatible constants, global mean/median/most-frequent, or the same
statistics grouped by up to four columns. Mean/median require numeric inputs;
boolean and string constants must retain their types. Statistical donors are all
observed training values in the configured group/global population, not merely rows
matching the recipient predicate. Conditions select recipients; they do not filter
the donor population. No validation/test/inference values estimate statistics.

For example:

```text
Target: income
Rule 1: WHEN employment_type = "Salaried"
        fill remaining missing income with training median grouped by city
Rule 2: fill remaining missing income with global training median
Fallback: leave missing and warn
Indicator: income_was_missing
```

The final fallback can leave missing, use a constant, or use a global training
statistic. There is no implicit global substitution for an unavailable group.
Missing keys are unmatched, not converted into a string category. Unseen groups
and groups with no observed donors continue through later rules/fallback. Composite
keys retain scalar type and column boundaries. Numeric grouping codes remain
numeric; strings and booleans are not silently interchangeable. Most-frequent ties
use the smallest numeric value, Unicode string order, or false before true.

All predicates and keys read the immutable **pre-imputation** inputs. A rule on one
column never sees another column's newly imputed value, regardless of rule/config
order. Grouping by the imputation target itself is rejected. Label references,
unavailable inputs and post-imputation indicator references are rejected. Indicators
cannot feed earlier temporal/generalized expressions.

An indicator is always 1 for an originally missing cell and 0 otherwise, independent
of rule success. Its name must be a distinct letter-led identifier. It is included
automatically as a binary model input when its imputation target is included;
excluded targets retain dormant configuration without executing it or emitting an
indicator. Indicators do not receive separate earlier feature operations.

**Preview imputation** validates configuration and reports original missingness,
observational predicate match counts (which can overlap), and up to 20 indicator
values. It never estimates group/global statistics or displays fitted fill values.
Even constant-only configurations use this conservative configuration preview.
The main table retains pre-imputation target cells and marks indicator output;
selecting an active fitted Applied Step reports values unavailable.

**Apply imputation** requires a matching successful preview and updates the draft.
Save preparation persists it with existing revision guards. Cancel, Undo/Redo,
Discard, reopen and Applied Steps retain their existing semantics. Applying advanced
configuration removes the active quick imputer while remembering its former
strategy. Removing the advanced step restores that strategy, subject to validation.
Explicitly applying a quick setting replaces advanced configuration and removes
its indicator. Scaling/encoding remain after the shared imputation stage. Both
imputers are never silently applied together. Downstream invalid definitions are
retained for repair rather than deleted.

All current estimators require complete inputs. **Leave missing and warn** is a
valid saved choice, but if missing values actually remain, training or prediction
fails with an explicit request for another rule/fallback. A training feature with
no observed values requires a compatible constant fallback. An unavailable
statistical fallback fails rather than inventing zero. Numeric inputs/constants
must be finite and exact integer conversion stays within the documented safe range.

The complete fitted model stores its training statistics; callers supply raw input
columns only. The same runtime executes generated Python and saved inference after
temporal/generalized stages and before scaling/encoding. Existing splits, target
filtering, historical Runs, source CSV and Code Mode boundaries remain unchanged.
Comparison conservatively suppresses deltas when frozen advanced rules differ.

Bounds: 64 configured targets, 16 rules per target, four grouping columns per rule,
10,000 observed groups per fitted rule and 50,000 across the transformer. Predicates
retain the derived depth/size bounds and add a 4,096-node configuration total. Text
constants are at most 1,000 characters. Excessive group cardinality fails safely.
There are no learned thresholds, KNN/iterative/predictive imputers, post-imputation
dependencies or arbitrary global step reordering. Imputation does not filter rows;
use the separate cleaning selection operations below.

## Data cleaning, selection and validation (v0.5 development)

**Imputation fills cells. Row filtering removes or retains whole observations.**
Neither changes the managed CSV. The Studio's column menu and searchable
**Add Transformation** expose Remove/Keep Rows Where This Column Is Missing,
Replace Values, Replace With Missing, Normalize Missing Tokens, Change Data Type,
Fill Missing Datetime and Validate Column. Global actions include Filter Rows,
Remove Duplicate Rows and Data Quality Rules. The supervised label is excluded.

Choose one column for the common missing-row action, then Preview and Apply. For
multiple columns choose **any** or **all** missing and whether to keep matching
rows or remove them. General filters use the existing visual expression controls
with source or pre-imputation temporal/generalized references. Only explicitly true
predicates match: Keep matches drops unknowns; Remove matches retains unknowns.

Cleaning has fixed stages. Raw-column operations execute in their stored order,
then temporal/generalized derivations run, then ordered filters/deduplication run,
then missing-target handling/splitting and fitted imputation/scaling/encoding.
Source validation therefore happens before derivation and selection. Filters can
use derived columns; raw cleaning/validation cannot depend on future derived or
imputed outputs. There is no arbitrary global step reordering. Add source operations
before their dependents; Applied Steps shows the actual fixed-stage order.

### Source values and explicit type correction

- **Normalize Missing Tokens** changes only explicitly listed strings to missing.
  Choose trim-before-match and case sensitivity. A blank token line denotes an
  empty string; trim permits matching whitespace-only input. CSV parser defaults
  may already have treated tokens such as NA as missing; cleaning does not recover
  original lexical tokens from parsed values.
- **Replace Values** uses exact typed matches, case-sensitive strings and explicit
  null matching. A condition selects rows instead of the exact-match field; unknown
  does not match. Replacement can change nonmissing cells. For example, select
  numeric `age < 0` and replace with missing. Boolean and numeric matches are distinct.
- **Change Data Type** executes a real conversion, not just a semantic label.
  Continuous conversion explicitly parses numeric strings, rejecting booleans,
  non-finite and unsafe integral values. Categorical conversion explicitly renders
  numeric/boolean inputs as strings; it preserves existing strings. Binary conversion
  accepts booleans, numeric 0/1, or the case-sensitive tokens `true`, `false`, `1`, `0`.
  Missing values stay missing. Datetime conversion uses the explicit parsing policy.
- Invalid conversion is **Reject** or explicitly confirmed **Coerce to missing**.
  Numeric precision loss is rejected/coerced rather than hidden. Review diagnostics
  and configure downstream missing-value handling. Converted effective types and
  physical dtypes belong to this recipe; original Dataset interpretation is retained.

### Original datetime columns

**Fill Missing Datetime** parses the selected raw column with the existing ISO or
numeric-format policy, explicit naive UTC/reject behavior and invalid reject/coerce
behavior. Supply a fixed ISO date or timestamp, optionally with a stateless condition.
Fixed dates mean UTC midnight. No local timezone or current clock is substituted.

Only originally missing cells are filled. Valid instants retain their meaning;
outputs are canonical UTC ISO strings, including supported subsecond precision.
Invalid values coerced during that same fill remain missing rather than receiving
the fill silently. To deliberately coerce and then fill them, use separate explicit
conversion/fill steps. Downstream temporal derivations consume the cleaned values
through the resolved canonical ISO policy. For datetime **conversion**, the single
Invalid conversion control governs parsing; for **fill**, Invalid timestamps governs it.

Forward/backward fill, interpolation, timestamp statistics and clock-based fills
remain unsupported.

### Quality rules and duplicates

Raw-column quality rules support required/nonmissing, numeric min/max/ranges,
typed allowed values, string length bounds and numeric/string/boolean compatibility.
Choose report, reject, or explicitly confirmed coercion to missing. Missing inputs
are ignored by range/length/type checks; use required to disallow them. Allowed-value
checks permit missing only if null is explicitly allowed. Validation never removes
rows; rejection is an explicit error in training or prediction, and report-only
findings do not block. Use datetime parsing policies for timestamp validity.

Diagnostics show rule/column, invalid count, status and at most five scalar examples
in the explicit local preview. They are not persisted as raw rows or ordinary logs.
Required constraints must be repaired explicitly; coerce-to-missing does not magically
make a required value present.

Deduplication uses an explicit set of raw/derived keys and **first** or **last**
occurrence in source order. Select all desired eligible feature keys or a subset;
the label cannot be part of duplicate identity. Missing keys compare as duplicates
according to pandas behavior. Contradictory outcomes for equal feature keys retain
the chosen occurrence; this is not a solution for near-duplicate/entity leakage.

### Preview, training and inference boundaries

The table and editor use actual backend transformations, accurate full-source
before/retained/removed counts, per-selection counts and at most 20 retained rows
with original row numbers. **Original source preview** shows the unmodified source
sample. Selecting an Applied Step recomputes the true prefix. No fitted imputer,
encoder or scaler is learned for preview. Rejected conversions can expose diagnostic
proposals, but errors block Apply and further valid-stage claims.

Apply/Cancel, Save/Discard, edit/remove/clear, revert and Undo/Redo use the existing
IR and revision guard. The whole cleaning configuration can be repaired locally
before preview/apply. Removing a cleaning operation retains downstream intent for
explicit repair. Saved source bytes and historical Runs remain unchanged.

Training-only filters/deduplication run before the existing split and before target
exclusion. Binary/regression missing labels still follow exclusion; multiclass
missing labels remain invalid even if a feature filter could remove those rows.
Selection cannot silently remove an entire classification class. Existing split,
class coverage and minimum-population checks apply to the retained population.
Source population counts retain the original CSV count; eligible/training/test
counts reflect actual selection and target policy. Invalid subsets block training.

Saved models repeat row-wise cleaning, conversion, datetime fill and validation from
raw input columns. They **never run training filters or deduplicate inference**.
Every accepted input row gets a prediction, including rows excluded from training;
violated rejection constraints fail explicitly rather than shortening predictions.
Training-only key columns are not added to model requirements solely for selection.
Generated Python executes both stages with the same runtime. Comparison suppresses
metric deltas when frozen cleaning/selection/validation contexts differ.

Limits: 64 cleaning steps, 16 missing-filter columns, 32 duplicate keys, 32 tokens,
128 allowed values, 1,000 characters per scalar string, depth 8/256 nodes per
predicate and 4,096 predicate nodes overall. Only source-column cleaning/validation
and pre-imputation selection are supported; post-imputation cleaning, unrestricted
regex, learned thresholds, row-wise rejection-result schemas and ordered time-series
fills are deferred. No new dependency, database migration or separate workspace.

## Advanced numeric and categorical features (v0.5 development)

Use a column's context/ellipsis menu or searchable **Add Transformation**:
**Transform Numeric**, **Bin Numeric**, **Group Rare Categories**, or **Encode
Ordinal**. Compatible temporal and generalized outputs are also supported. The
guided editor offers Preview / validate, Apply and Cancel. Apply changes the draft;
Save persists it. Applied Steps supports editing, removal, reverting, undo/redo and
reconstruction after reload. Outputs always create new named features; explicitly
exclude the original if it should not enter the model. Renaming/removing upstream
definitions retains stale downstream intent for explicit repair.

### Mathematics and power/quantile transforms

- Natural log requires values greater than zero; log1p requires greater than -1;
  square root permits zero; reciprocal rejects zero. Choose reject or explicitly
  mark invalid values as missing. Overflow/nonfinite math results never become
  infinity. Existing missing values remain missing. These operations reuse the
  generalized expression runtime and have actual source-value previews.
- Yeo-Johnson accepts finite negative/zero/positive inputs. Box-Cox requires strictly
  positive observed inputs, with no automatic offset. Both learn power parameters
  from training rows and do not automatically standardize the output.
- Quantile transformation supports uniform/normal output. Select 2–1,000 quantiles;
  the actual count is capped to nonmissing training rows. Estimation uses all training
  rows, deterministic settings and no random subsampling. Inference extremes map
  to fitted distribution endpoints. All fitted numeric methods require at least two
  distinct nonmissing training values; constant/all-missing inputs fail explicitly.

### Bins, rare groups and ordinal mappings

Explicit finite, strictly increasing boundaries are stateless. Intervals are
left-closed/right-open; a value exactly on a boundary enters the higher bin.
Underflow/overflow use open-ended outer bins. Output labels are `bin_0`, `bin_1`,
etc.; missing remains missing. Equal-width binning learns training min/max;
quantile binning learns training quantiles. Both are fitted, support 2–100 requested
bins and reuse edges at inference. Duplicate quantile edges collapse; requested
count is not guaranteed. The saved transform's `diagnostics_` contains requested
and actual counts. No pretraining fitted-bin values are shown.

Rare grouping uses exactly one threshold: absolute training count, or fraction
of **all training rows**, including missing rows in the denominator. Categories
meeting the threshold are retained. Known rare values map to the chosen label;
unseen values explicitly map to rare, pass through for the encoder, or reject.
Missing values remain missing. Typed comparisons distinguish boolean, numeric and
string categories. Retained categories become encoder-safe strings, so numeric
and boolean labels are textual in this categorical output. Ambiguous string-label
collisions and a rare label matching a retained category are rejected. The training
mapping is limited to 10,000 categories; high-cardinality inputs warn in diagnostics.

Ordinal encoding uses explicitly typed category-to-integer rows, with unique keys
and codes (no alphabetical inference). Unknowns reject, use a distinct explicit
integer code, or become missing. Missing inputs remain missing. Ordinal outputs are
continuous numeric features, without automatic one-hot encoding. Bin/rare outputs
are categorical and get the existing one-hot encoder by default. Numeric outputs
can use the existing scaling controls.

### Execution and preview boundaries

Execution order is raw cleaning → temporal/generalized derivation → training-only
selection → split → Advanced Imputation → feature engineering → existing branch
imputation/encoding/scaling → estimator. A quick source-column imputer is a later
branch operation and does **not** fill engineering inputs. Use Advanced Imputation
on a direct input, or quick imputation on an engineered output. Imputing a raw
column cannot retroactively change a temporal/generalized value already computed.
No transform silently imputes. Learned methods preserve missing inputs; configure
compatible output imputation or expect a complete-input validation/error.

Fitted-method previews show compatibility, missingness and domain diagnostics only;
they never fit or fabricate transformed values. Stateless previews display actual
source-derived samples (up to 20 rows), missing and invalid counts. With upstream
Advanced Imputation, preview still shows pre-fit source values rather than invented
fills. Input diagnostics describe current retained data, not a fitted training sample.
Training determines final validity of degenerate subsets, rare-label collisions and
actual bin counts. Saved models retain learned parameters and derive features from
raw inference inputs without loading the training CSV or reducing row count.

Limits: 64 engineering outputs, 99 explicit boundaries, 100 bins, 1,000 quantiles,
1,000 ordinal entries, 10,000 training categories per rare mapping. Output names
must be distinct and cannot replace source columns. Supervised labels and
post-imputation indicators cannot be inputs. Only earlier stateless engineering
outputs may feed later engineering operations; fitted-output chains and backward
stage references remain unsupported. Branch imputation
is available for outputs; earlier Advanced Imputation cannot consume them. No
arbitrary reordering, replacement mode, signed-log variant or new estimator is added.
Existing pipelines and historical Run artifacts remain unchanged.

## Actionable EDA, outliers and feature selection (v0.5 development)

Dataset diagnostics and source column profiles reuse the existing EDA Workbench:
histograms, boxplots, categorical frequencies, missingness, quality observations
and bounded Pearson heatmaps. Regression retains its target summary/scatter and
now reuses the same selected-feature profile and source correlation components.
These views describe the **original source Dataset**, before preparation, filtering
or splitting. They do not describe current draft transformations or historical
training partitions. Summary statistics use full-source observations, while the
existing regression scatter shows at most 200 evenly spaced complete pairs.

The column profile shows Q1/median/Q3, IQR, lower/upper fences, below/above/total
potential outliers and percentage of nonmissing observations. The exploratory IQR
multiplier defaults to 1.5 and accepts 0.1–10. Missing/all-missing, nonfinite and
unsafe numeric ranges have explicit unavailable states. Constant/zero-IQR source
profiles remain descriptive. Continuous profiles also show population variance
(ddof=0), a configurable low-variance threshold, and insufficient-observation
guidance. Integer-coded categorical features are not treated as continuous merely
because they have numeric storage. Missingness thresholds reuse observed counts.
Strong-correlation summaries use a configurable absolute threshold (default 0.90)
over the existing first-12-feature matrix, never unbounded pairwise analysis.
Correlation is diagnostic and never removes a feature automatically.

Use **Treat Outliers**, **Add Outlier Indicator**, **Review Feature Selection**,
**Exclude Feature**, **Handle Missing Values**, **Transform Numeric**, or **Group
Rare Categories** from compatible profiles. These open the existing Studio editors;
only outlier and variance configuration have new editors. Target labels have no
predictor actions. A typed handoff checks Project/Dataset/revision and current
draft compatibility. It carries the action/feature and optionally the configured
multiplier, never learned fences, a mask or a full recipe. The Studio remains open
with unsaved edits and undo history preserved. Apply changes the draft; Save is
still required. Stale evidence or incompatible draft semantics are rejected.

### IQR clipping and indicators

Select a compatible continuous source, temporal, generalized or numeric engineered
feature. Configure the multiplier (0.1–10), both/lower/upper tails, new output name,
optional indicator, and explicit participation for each output. The original column
is unchanged; review its participation separately. Add Outlier Indicator starts with
the clipped output excluded and the indicator included. No row deletion occurs.

Q1/Q3 use linear quantiles from **training rows only**. Fences are Q1 − multiplier
× IQR and Q3 + multiplier × IQR. The clipped output and numeric 0/1 indicator share
these exact stored fences and selected tails. Values on a fence are not outliers.
At least two valid observations are required. Zero IQR gives coincident fences;
off-fence values are clipped to that point in the configured tails, and the saved
transform records `zero_iqr` diagnostics. All-missing/too-small subsets and numeric
overflow fail explicitly. Missing values are preserved in output and indicator,
or rejected by explicit policy. Nonfinite inputs reject or explicitly become
missing. There is no silent imputation.

Outlier treatment runs after shared Advanced Imputation and feature engineering,
before per-feature branch imputation/encoding/scaling. A direct input's Advanced
Imputation can fill it; a source quick imputer runs later and cannot affect it.
Engineering outputs that need filling can use output branch imputation after
clipping. Outlier outputs cannot feed earlier stages or another outlier transform.
Configuration diagnostics never fit source fences or invent output preview values.

### Variance threshold selection

Choose 1–128 included continuous numeric features and a finite threshold from 0 to
1e12. Selection fits population variance on the training partition **after each
eligible branch's configured imputation/scaling**, and retains variance strictly
greater than the threshold. Standard-scaled nonconstant features generally have
variance near 1; the editor lists scaled eligible features and explains these units.
This is not necessarily raw-source variance. Encoded categories and other numeric
branches remain untouched and retain their deterministic order. Missing/nonfinite
eligible training outputs require explicit imputation/cleaning. If no eligible
numeric feature survives, training fails with guidance; no fake selected mask is
shown before training. Manual participation remains authoritative and is not a
second exclusion list.

Applied Steps groups each clipping output with its shared indicator, and shows
variance selection after branch preprocessing. Edit/remove/revert, undo/redo and
save/reload use the existing workflow. Removing a producer is blocked while dependent transformations or variance
eligibility still reference its outputs. Remove consumers first. Explicit bulk
revert remains available with confirmation; Undo restores the draft. Maximum 64 outlier treatments, no in-place replacement
or arbitrary reordering. Source/prepared distribution comparisons and fitted Run
parameter display are deferred. Saved model artifacts retain fences, variances and
the selected mask, derive from raw prediction inputs without the training CSV, and
preserve one prediction per accepted input row. Historical Runs are unchanged;
different frozen treatment/selection contexts suppress comparison deltas.

## Lineage, dependency safety and inference schemas (v0.5 development)

Choose **Inspect Feature Lineage** from a column menu or Add Transformation search.
The existing Studio dialog shows the producer, stage, semantic/physical type,
model participation, direct/transitive inputs and downstream consumers. Shared
Advanced Imputation is identified as fitted, with group/condition inputs. Source
values and intermediate outputs may be excluded from the estimator while remaining
required for reconstruction. The pipeline API returns a computed `lineage-v1`
registry; it is not another persisted recipe or execution graph.

Structural validation rejects missing/colliding outputs, target predictor use,
cycles and stage-invalid dependencies. Temporal/generalized expressions retain
existing topological resolution. Engineering operations run in stored order: an
**earlier stateless engineering output** may feed another stateless or fitted
operation. An engineering output that requires fitted state cannot feed another
engineering operation. Numeric engineered outputs can already feed the later
outlier stage; outlier outputs can use later branch imputation/scaling and variance
selection. Outlier-to-outlier chains, earlier-stage consumers of later outputs,
post-imputation indicator inputs and arbitrary fitted graphs remain unsupported.

Removal explains direct and transitive affected steps and blocks until consumers
are removed. Output-renaming edits cannot silently delete their consumers. Removing
a source parsing policy is blocked if temporal features still use it. Unrelated
settings and undo/redo remain intact. Explicit confirmed bulk revert/reset may
remove a whole suffix/recipe. Previously invalid saved drafts remain inspectable
for repair; backend readiness and compilation reject structural errors.

Newly compiled visual models freeze `schema-contract-v1`. Raw requirements are
resolved from actual compiler inputs: intermediate dependencies count, but the
supervised label, generated outputs, unrelated source columns and selection-only
keys are not requested merely because they existed in the training CSV. Harmless
extra columns are ignored **before** derivation, so they cannot shadow generated
outputs. Required names must be present and unique. Raw scalar values are left
unchanged: existing normalizers, conversions, datetime parsers, unknown-category
and missing-value policies remain authoritative. There is no duplicate parser or
silent imputation in the schema guard.

The fitted preprocessor records actual scikit-learn feature names/order, count,
numeric matrix representation and variance mask when present. Prediction checks
these names/counts, numeric/finite completeness and row cardinality before the
estimator receives the matrix. Invalid input fails as a batch with actionable
errors; no partial-row response, refitting or training-CSV lookup is introduced.
No full-source estimator schema or learned encoded expansion is fabricated before
training. Structural safeguards cannot identify future-information leakage,
proxy-label leakage or a statistically unsuitable split automatically.

See the [Training guide](training.md#saved-model-schema-contracts-v05-development)
for inspection. Historical Runs/source files are untouched. Older plans without a
schema contract retain their original generated source and inference behavior;
they are not retroactively upgraded. Manually edited Python remains user-controlled.
