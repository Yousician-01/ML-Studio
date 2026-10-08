export function evaluationRun(id = "a") {
  const target = { column: "outcome", physical_dtype: "bool", semantic_type: "binary", positive_class: { value_type: "boolean", value: true }, negative_class: { value_type: "boolean", value: false }, missing_value_policy: "exclude_rows" };
  return {
    id, project_id: "project", dataset_id: "dataset", sequence: id === "a" ? 1 : 2, state: "SUCCEEDED", created_at: "2026-01-01T00:00:00Z", snapshot_error: null,
    summary: { dataset_fingerprint: "sha256:abc", target, split: { test_size: .2, random_seed: 42, stratify: true }, model: { name: "LogisticRegression", parameters: {} } },
    provenance: { mlstudio: "0.1", executor: "local-subprocess-v1" },
    artifacts: Object.fromEntries(["pipeline_ir.json", "execution_plan.json", "package.json", "generated_run.py", "result.json", "model.joblib"].map(name => [name, { integrity: "verified" }])),
    execution_plan: { plan_version: "0.1", ir_version: "0.1", generator: "mlstudio-python-v1", source: { parser: "csv-utf8-v1", size_bytes: 100, encoding: "utf-8-sig", missing_values: "pandas-default", integer_policy: "lossless-precision-risk-reread" }, target, split: { test_size: .2, random_seed: 42, stratify: true }, features: [], model: { name: "LogisticRegression", parameters: {} }, implementation: { version: "sklearn-local-v1", python: "3.12", libraries: { pandas: "2", numpy: "2", "scikit-learn": "1" } }, evaluation: { metrics: ["accuracy", "precision", "recall", "f1", "roc_auc"], zero_division: 0, confusion_order: "negative-positive", roc_auc: "positive-score-or-unavailable" }, runtime: { version: "cli-v1", result_schema: "mlstudio-result-v1" } },
    result: { schema_version: "mlstudio-result-v1", metrics: { accuracy: .75, precision: 0, recall: 0, f1: 0, roc_auc: null }, roc_auc_unavailable_reason: "Only one observed held-out class.", population: { source: 20, eligible: 20, training: 16, test: 4 }, confusion_matrix: { labels: [target.negative_class, target.positive_class], values: [[3, 1], [0, 0]] } },
  };
}

