# Explore and Prepare

## Data Preparation Studio (v0.5 development)

The primary workflow is **Dataset → Data Preparation → Train → Runs / Evaluate**.
Uploading a CSV opens the studio; an existing Project loads its saved source and
recipe. Dataset navigation remains for source management. Old `view=prepare` and
`view=explore` links work; Explore opens diagnostics within the unified workspace.

The central table shows the existing bounded **20 source-preview rows**, plus
stateless temporal outputs from the backend. Scroll, select headers, search names,
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
Fixed stages are source, parsing policies, dependency-ordered temporal outputs,
feature participation, then existing per-feature preprocessing branches. Dormant
choices are labelled **not executed**; invalid legacy entries remain repairable.
There is no arbitrary reordering.

- **Select** a step for non-destructive inspection. Temporal prefixes are actually
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

The latest table is a source-plus-temporal reference, **not a fitted training
matrix**. Imputers/scalers/encoders are never fitted on the full Dataset to create
a preview. Selecting a fitted stage shows an explicit unavailable state; fitted
one-hot output names/width are not guessed. No new preprocessing/EDA algorithms
are introduced.

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
windows, holiday calendars, generic arithmetic and arbitrary Python expressions
remain deferred. Unsaved temporal edits are local UI state; save before closing.
