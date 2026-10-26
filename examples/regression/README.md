# Synthetic regression demonstration

This walkthrough reuses [customers.csv](../retention/customers.csv): 120 entirely
synthetic observations, never real customer data. Here `monthly_spend` is a numeric
target, not the classification demo's `churn` label. This is a workflow example,
not a benchmark or a claim of business generalization.

Use the [verified Windows source setup](../../README.md#supported-installation-source-checkout-only).
For a disposable workspace, set `MLSTUDIO_HOME` outside the repository before
migrations/startup; see [Development](../../docs/development.md). The task cannot
be changed on an existing Project, so create a separate regression Project.

## Configure and execute

1. Create a Project with task **Regression**, name `Synthetic spend` and problem
   statement `Predict synthetic monthly spend from tenure and plan`.
2. In **Data**, upload `examples/retention/customers.csv`. Select `monthly_spend`
   as target. Inspect physical/semantic types and missing observations. Set its
   effective type to continuous if necessary. There are 120 source rows and six
   missing target values; missing targets will be excluded, not imputed.
3. In **Explore**, inspect numeric target statistics and the histogram. Select
   `tenure_months` for the source scatter and Pearson relationship. These use
   complete source pairs, not predictions or a held-out test partition. Missing
   pairs are reported separately. No grouped categorical target view is provided.
4. In **Prepare**, explicitly exclude `customer_id` and `churn`. Keep these features:

   | Feature | Effective semantics | Missing values | Scaling / encoding |
   | --- | --- | --- | --- |
   | `tenure_months` | continuous | Median | Standard |
   | `plan` | categorical | Most frequent | One-hot |

   There is no positive-class selector. No transformation modifies the source.
5. In **Train**, explicitly configure a 20% test split and seed 42. Regression has
   no stratification control. Select **Linear Regression** and keep its displayed
   `fit_intercept` default. Save any edited fields and resolve readiness issues.
   With this source/target, 114 eligible rows give 91 training and 23 test rows.
6. Open **Code** and inspect the read-only generated Python. Return to **Train**
   and click **Run experiment**. Only an actual terminal **Succeeded** Run has
   successful evaluation evidence. Preprocessing is fitted on training rows only.
7. Open **Evaluate** for that Run. Inspect MAE, MSE, RMSE, R², held-out population
   and frozen configuration. Classification metrics and confusion matrix do not
   apply. A negative R² is valid; unavailable R² has a reason instead of zero.
8. In **Runs**, inspect provenance, artifacts, tracking status and historical Code.
   It is the persisted executed source, not the current Pipeline rendered again.

## Second Run and history

9. Change only the model to **Ridge**, keeping visible defaults (`alpha=1`,
   `fit_intercept=true`), the same feature preparation and split. Review Code and
   execute a second Run. Do not edit the first Run.
10. In **Evaluate**, select exactly these two successful Runs. Compare frozen
    configuration and values. Compatible context/integrity permits B − A deltas;
    differing contexts show warnings instead. No winner is selected, and matching
    context does not independently prove identical held-out row membership.
11. Reload and inspect both Runs and their historical Code. Saved configuration
    and evidence remain in the local workspace. Working Pipeline edits or Dataset
    replacement must not rewrite past Runs. Check the separate local MLflow status;
    a synchronization failure must not change a successful execution outcome.

Scores are deliberately not specified. No residual/predicted-versus-actual plots
exist because prediction-level evidence is not stored. The source scatter in
Explore is a different population and purpose. Read [Security](../../SECURITY.md)
before using sensitive data; the local subprocess is not a secure sandbox.
