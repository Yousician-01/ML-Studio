# Runs and evaluation

## Immutable evidence

Runs preserve source, Dataset identity/interpretation, configuration, resolved plan, provenance, results and fitted-model artifacts. Working-pipeline edits/replacement never update history. Historical Code reads the executed file. MLflow is secondary, never Evaluate's authority.

Evaluate defaults visibly to the latest successful visual Run and keeps explicit selection in the URL. Use paginated history/deep links for older Runs. Active/failed Runs show status/diagnostics rather than successful metrics. Stale, unknown and cross-Project IDs are unavailable selections, not silently substituted. Code Run reports are a separate selectable evidence source when valid reporting exists.

## Metrics

| Task | Evaluation |
| --- | --- |
| Binary | Accuracy, Precision, Recall, F1 using frozen typed positive class; conditional ROC-AUC with reason if unavailable; typed 2x2 matrix |
| Multiclass | Accuracy; macro/weighted Precision, Recall, F1; per-class support/metrics; typed NxN matrix. No multiclass ROC-AUC. |
| Regression | MAE, MSE, RMSE and conditional R-squared with reason if unavailable. Negative R-squared is valid. No classification matrix. |

Held-out population and frozen split/model context accompany results. Unavailable metrics are **not zero**. Matrix rows are actual classes, columns predicted classes. Binary order is negative then positive: TN/FP first row, FN/TP second. Typed labels preserve meaning.

Code reports are explicitly emitted through the reporting bridge. Successful process exit alone does not guarantee valid evaluation. Reports are bounded and validated separately from visual Run protocols; missing reports/predictions are not inferred.

## Compare exactly two visual Runs

Select two distinct successful Runs in the Project. Comparability checks fingerprint, task/target, typed class orientation, source interpretation, split settings, relevant versions, held-out population, metric definitions and artifact integrity. Frozen model/preparation context is shown side by side.

Compatible contexts permit B minus A metric deltas. Otherwise values remain with warnings and deltas are suppressed. Compatible settings do not independently prove identical held-out row membership. No ranking or winner is declared. Code reports are not interchangeable controlled visual experiments.

## Integrity and limits

Compromised artifact integrity permits retained SQLite metrics only with warning and excludes comparison deltas. Missing evidence is never reconstructed from the current recipe. Do not edit historical rows/artifacts to clear warnings.

No per-sample predictions are retained for ROC curves, residual/predicted-versus-actual plots or threshold tuning. Explore scatter is a different population and purpose. Model artifacts are trusted local files, not a safe external exchange format. See [Security](../../SECURITY.md) and [Troubleshooting](../troubleshooting.md).
