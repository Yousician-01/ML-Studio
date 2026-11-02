# Explore and Prepare

## Explore: source evidence

Explore reads managed source and its interpretation, not model predictions. It presents deterministic profiles/missingness, numeric distributions and box plots, categorical frequencies, and supported relationships. Classification views include target class information. Numeric correlations describe association, not causality or leakage-proof feature selection.

Regression provides numeric target statistics/histogram, paginated numeric feature selection, full-pair Pearson correlation and a source scatter capped at 200 pairs. Correlation uses eligible complete source pairs; missing-pair counts are separate. Grouped categorical regression target summaries are not implemented.

Unavailable relationships carry reasons, not invented values. No source plot is a residual plot or held-out evaluation. Raw rows/pairs are transient explicit local inspection, not profile rows in SQLite or ordinary logs.

## Prepare: explicit intent

Review inclusion, effective semantics and target context. Supported operations include compatible mean/median/most-frequent imputation, numeric standard/min-max/robust scaling, and categorical one-hot encoding. Controls expose supported combinations; unsupported text/datetime/identifier handling must be resolved or excluded rather than silently transformed.

Binary requires an explicit typed positive class. Regression/multiclass do not invent one. Target is never a feature and is never imputed. Missing binary/regression targets are excluded before splitting; missing multiclass targets are rejected.

Prepare controls save working visual intent immediately. They do not rewrite CSV. Learned imputers, scalers and encoders fit training data only inside the generated sklearn pipeline. The model artifact includes the complete preparation/model pipeline.

Open **Show Code** to inspect the recipe in Python. Viewing does not save a proposed pipeline or create a draft. Incomplete/invalid configuration produces validation instead of executable-looking stale source. Train uses explicit save actions; unsaved Train input can be previewed without silently persisting it.

After source replacement, resolve stale configuration and validation before training. See [Training](training.md) and [Code workspace](code-workspace.md).
