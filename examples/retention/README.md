# Synthetic customer-retention demonstration

For the v0.5 checkout, upload completion opens **Data Preparation**. Use
**Source & target** for the Data controls below, **Dataset diagnostics** for Explore,
and column menus for the preparation choices. Apply editors, then **Save preparation**
and **Continue to Train**. Legacy Prepare/Explore URLs remain supported.

Optional v0.5 cleaning exercise: open `monthly_spend`'s column menu and choose
**Remove Rows Where This Column Is Missing**. Preview the actual retained count,
then Apply and Save in a separate experiment. This selects training/evaluation
rows, whereas imputation fills cells. Saved inference does not drop rows. Use
Undo/Discard to retain this walkthrough's original experiment configuration.

`customers.csv` contains 120 entirely synthetic customers, three candidate features,
an identifier and a binary `churn` outcome. Blank cells are missing observations,
including four missing targets. No row represents a real person. Scores illustrate
the workflow; they are not a benchmark or evidence of business generalization.

Use the [installation guide](../../docs/installation.md).
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

   Apply the column editors and Save preparation. Source data is immutable; transformations are learned
   only when the experiment trains. Four missing-target rows are excluded before
   splitting; the target is never imputed.
5. In **Train**, click **Configure 80 / 20 split** if not configured. Keep test size
   `20`, experiment seed `42`, and stratification `Yes`. Save edited split fields
   with **Save split**. Select **Logistic Regression**, keeping visible defaults
   `C=1`, `penalty=l2`, `max_iter=1000`. Save edited parameters if necessary.
   Expected population: 116 eligible rows, 92 training rows and 24 test rows.
6. Use **Show Code** in the toolbar to inspect the current read-only Python.
   Opening or refreshing the viewer does not execute training. Return to **Train**,
   resolve any readiness issues,
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
is provided by this visual demonstration. Optional editable Code Mode is documented
in the [Code workspace guide](../../docs/user-guide/code-workspace.md). Read [Security](../../SECURITY.md) and the local
recovery/retention notes before handling sensitive real data.

## Optional v0.5 feature engineering experiment

In a disposable Project, select a continuous feature in Prepare and choose
**Transform Numeric ? log1p**, give it a distinct output name, Preview / validate,
Apply, and Save. Negative inputs at or below -1 must be cleaned or explicitly
marked missing; add output imputation when needed. Review whether to exclude the
original feature. Train normally and inspect the historical generated Python.

For a learned alternative, choose **Bin Numeric ? quantile bins** with five
requested bins and a distinct output name. The output uses the existing one-hot
encoder. Its pretraining preview validates configuration without learning edges.
Duplicate quantiles may produce fewer than five actual bins. Training learns the
edges only from training rows; saved prediction reuses them from raw inputs.
Comparisons across different frozen feature-engineering recipes suppress deltas.

## Optional v0.5 actionable EDA workflow

Open Dataset diagnostics, select a continuous source column, and inspect the
existing boxplot and IQR summary. Choose **Treat Outliers**, review multiplier/tails
and distinct output name, optionally enable the shared indicator, and explicitly
choose output participation. Validate, Apply and Save. These exploratory fences
are never copied; training learns its own fences. Use a disposable Project when
trying settings and preserve earlier Runs for comparison.

From the output menu choose **Review Feature Selection**, select included continuous
features, and start with threshold 0 to remove constants in the selected branch
units. Scaling changes those units; review the editor explanation. Save and train.
The saved model retains its fences and mask for raw-input prediction. Reload to
check Applied Steps and inspect historical Code without rewriting earlier Runs.

## Optional v0.5 lineage and contract review

Inspect Feature Lineage for an engineered/clipped output. Verify its source chain,
participation and fitted stage. Attempt to remove its producer: the Studio should
name the consumers and block removal. Remove consumers first, or explicitly revert
a suffix and use Undo to restore it. Save/reload keeps the same recipe.

After a new visual Run, use its frozen Python and trusted saved model to inspect
`pipeline.schema_contract_`. Prediction requires raw dependencies, not precomputed
outputs or the label. Extra columns are ignored; missing required inputs fail.
Compare the fitted estimator names/count/mask with the recorded contract. This is
structural evidence, not proof that the source features contain no future information.
