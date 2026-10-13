# Synthetic customer-retention demonstration

`customers.csv` contains 120 entirely synthetic customers, three candidate features,
an identifier and a binary `churn` outcome. Blank cells are missing observations,
including four missing targets. No row represents a real person. Scores illustrate
the workflow; they are not a benchmark or evidence of business generalization.

Use the [supported Windows source setup](../../README.md#supported-installation-source-checkout-only).
For validation, set `MLSTUDIO_HOME` to a new temporary directory **before** running
Alembic and starting the backend. Never damage real Run evidence for this demo.

## First experiment

1. On **Projects**, click **New Project**. Name it `Synthetic retention`, set the
   problem statement to `Predict the synthetic churn label`, and create it.
2. In **Data**, choose `examples/retention/customers.csv` and click **Upload CSV**.
   Inspect the summary and source preview. Expected detected types: `customer_id`
   identifier, `tenure_months` and `monthly_spend` continuous, `plan` categorical,
   and `churn` binary. If needed, choose these effective types explicitly; source
   values must stay unchanged. Select **Target column → churn**.
3. In **Explore**, inspect target proportions, missingness, source distributions,
   and relationships. These are full-source facts, not transformed training data.
4. In **Prepare**, select **Positive class → yes (string)**. Exclude `customer_id`.
   Configure the remaining feature rows:

   | Feature | Missing values | Scaling / encoding |
   | --- | --- | --- |
   | `tenure_months` | Median | Standard |
   | `monthly_spend` | Median | Standard |
   | `plan` | Most frequent | One-hot |

   Changes save immediately. Source data is immutable; transformations are learned
   only when the experiment trains. Four missing-target rows are excluded before
   splitting; the target is never imputed.
5. In **Train**, click **Configure 80 / 20 split** if not configured. Keep test size
   `20`, experiment seed `42`, and stratification `Yes`. Save edited split fields
   with **Save split**. Select **Logistic Regression**, keeping visible defaults
   `C=1`, `penalty=l2`, `max_iter=1000`. Save edited parameters if necessary.
   Expected population: 116 eligible rows, 92 training rows and 24 test rows.
6. In **Code**, inspect the **Current Working Pipeline** read-only Python. Refreshing
   Code does not execute training. Return to **Train**, resolve any readiness issues,
   and click **Run experiment**. Wait for a genuine **Succeeded** status.
7. In **Runs**, open the Run. Inspect frozen configuration, metrics, provenance and
   artifacts, then click **Inspect historical Code**. It is the original executed
   source; changing the working model later must not rewrite it.
8. Open **Evaluate** or click **Evaluate this Run**. Inspect Accuracy, Precision,
   Recall, F1, conditional ROC-AUC and the matrix. Actual classes are rows;
   predicted classes are columns, ordered negative `no`, positive `yes`.

## Second experiment and comparison

9. Return to **Train** and select **Decision Tree**. Keep its visible defaults,
   the same feature preparation and the same split. Execute a second Run. This
   creates a new immutable identity rather than modifying the first Run.
10. In **Evaluate**, use **Evaluate #…** to select the first Run and **Compare #…**
    for the second. Exactly two successful Runs are compared. Matching source,
    typed target, split, versions, population and integrity permit `B − A` deltas.
    Model changes alone do not make the contexts incompatible. No winner is chosen;
    matching context does not independently prove identical held-out row membership.
11. Reload and restart the application. Projects, source configuration, both Runs,
    selected URL deep links and historical source should remain available. Check
    each Run's tracking state; local MLflow failure must not change its core result.

## Expected limits

Scores may vary outside the documented environment and are deliberately not fixed
acceptance thresholds. No ROC curve, threshold tuning, prediction table, AI advice
or editable Python is provided. Read [Security](../../SECURITY.md) and the local
recovery/retention notes before handling sensitive real data.
