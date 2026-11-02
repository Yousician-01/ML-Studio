# Your first experiment

Use the committed [synthetic customer CSV](../examples/retention/customers.csv): 120 observations, no real people. This demonstrates workflow, not performance on a real business problem. See the [classification example](../examples/retention/README.md) for a second experiment and the [regression example](../examples/regression/README.md) for another task.

1. Follow [Installation](installation.md), run `mls start`, and open http://127.0.0.1:3000. Keep the launcher terminal open. Projects should show existing local Projects or an empty state.
2. Create `Synthetic retention`. Choose **Binary Classification** and the problem statement `Predict the synthetic churn label`. Task is fixed for that Project; regression/multiclass use separate Projects.
3. In **Data**, upload `examples/retention/customers.csv`. Expect 120 source rows and five columns. Inspect missingness and source preview. Types should be `customer_id`: identifier, `tenure_months`/`monthly_spend`: continuous, `plan`: categorical, and `churn`: binary. Use semantic overrides if needed; physical dtype and source bytes remain unchanged.
4. Select `churn` as target. Its non-missing values are `no` and `yes`. Four missing targets are allowed and will be excluded before splitting, never imputed.
5. Open **Explore**. Inspect target balance, missingness and source distributions. These describe source data, not a trained model or its test set.
6. In **Prepare**, choose positive class `yes (string)` and exclude `customer_id`. Keep `tenure_months` and `monthly_spend` with median imputation and standard scaling. Keep `plan` with most-frequent imputation and one-hot encoding. These controls save immediately. Learned preparation fits training data only; it never rewrites the source.
7. In **Train**, configure an 80/20 split, seed 42 and stratification. Save split edits. Choose **Logistic Regression** and retain `C=1`, `penalty=l2`, `max_iter=1000`; save parameter edits. With this source, 116 eligible rows produce 92 training and 24 test rows. Resolve readiness messages before execution.
8. Click **Show Code** in the toolbar. The read-only Live Python Viewer shows the current recipe and can dock or float. Inspect loading, split, preparation, fitting and reporting. Opening it neither creates a draft nor trains. Invalid configuration produces validation rather than presenting older code as current.
9. Click **Run experiment** when ready. Observe the real status, then open the Run in **Runs**. Success has frozen configuration, source, results, fitted model, provenance and separate tracking status. Failure has diagnostics instead of invented metrics.
10. Open **Evaluate** for that Run. Inspect Accuracy, Precision, Recall, F1, conditional ROC-AUC and its reason if unavailable. The matrix uses actual classes as rows and predictions as columns: negative `no`, then positive `yes`. Synthetic scores do not establish real-world generalization.
11. Inspect historical Code from Runs: it is the exact executed source even after recipe edits. Optionally run a Decision Tree with the same preparation/split and compare exactly two successful Runs. Context warnings suppress deltas; no winner is chosen.
12. Reload, stop with Ctrl+C and restart using `mls start`. Project, Dataset, saved pipeline and Run history should persist. The URL preserves explicit historical Run selection.

## Optional: edit Python

In Show Code, choose **Edit Code**, read the confirmation, then explicitly enter full-screen Code Mode. Save a draft and optionally a snapshot. Closing the editor does not delete it; saved drafts survive restart. Manual edits never update visual Pipeline IR. Returning requires an explicit choice to preserve a snapshot or discard active changes.

Saving is not execution. Code Runs require trusted local opt-in, disabled by default; see [Code workspace](user-guide/code-workspace.md). Do not enable execution merely to follow this visual tutorial.

## Other tasks

For regression, use a new Project and the [spend example](../examples/regression/README.md). For multiclass, provide 3-50 supported homogeneous string/integer classes with no missing targets and enough examples per class for both partitions. See [target rules](user-guide/projects-and-data.md) and [Training](user-guide/training.md). No external downloadable dataset is implied.
