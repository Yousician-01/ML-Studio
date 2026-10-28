import type { PipelineIR, TypedScalar } from "./pipelines";

export type RunState = "CREATED" | "RUNNING" | "SUCCEEDED" | "FAILED";
export type RunRequest = { request_id: string; expected_revision: number; expected_source_sha256: string; expected_plan_sha256: string };
export type Constructor = { name: string; parameters: Record<string, string | number | boolean | null | number[]> };
export type BinaryMetric = "accuracy" | "precision" | "recall" | "f1" | "roc_auc";
export type Metric = BinaryMetric | "mae" | "mse" | "rmse" | "r2" | "precision_macro" | "recall_macro" | "f1_macro" | "precision_weighted" | "recall_weighted" | "f1_weighted";
export type BinaryResult = {
  schema_version: "mlstudio-result-v1";
  metrics: Record<BinaryMetric, number | null>;
  roc_auc_unavailable_reason: string | null;
  population: { source: number; eligible: number; training: number; test: number };
  confusion_matrix: { labels: [TypedScalar, TypedScalar]; values: [[number, number], [number, number]] };
};
export type RegressionResult = { schema_version: "mlstudio-result-v2"; task: "regression"; metrics: Record<"mae" | "mse" | "rmse" | "r2", number | null>; r2_unavailable_reason: string | null; population: BinaryResult["population"] };
export type MulticlassResult = { schema_version: "mlstudio-result-v3"; task: "multiclass_classification"; metrics: Record<"accuracy" | "precision_macro" | "recall_macro" | "f1_macro" | "precision_weighted" | "recall_weighted" | "f1_weighted", number>; population: BinaryResult["population"]; confusion_matrix: { labels: TypedScalar[]; values: number[][] }; per_class: { label: TypedScalar; precision: number; recall: number; f1: number; support: number }[] };
export type RunResult = BinaryResult | RegressionResult | MulticlassResult;
export type FrozenModel = { name?: string; estimator?: string; type?: string; parameters: Constructor["parameters"] };
export type FrozenTarget = { column: string; positive_class?: TypedScalar; negative_class?: TypedScalar; classes?: TypedScalar[]; physical_dtype?: string; semantic_type?: string; missing_value_policy?: string; value_type?: string };
export type FrozenPlan = {
  plan_version: string; ir_version: string; task?: "regression" | "multiclass_classification";
  generator: string;
  source: { parser: string; size_bytes: number; encoding: string; missing_values: string; integer_policy: string };
  target: FrozenTarget;
  split: { test_size: number; random_seed: number; stratify?: boolean; shuffle?: boolean };
  model: FrozenModel;
  features: { name: string; physical_dtype: string; semantic_type: string; operations: Constructor[] }[];
  implementation: { version: string; python: string; libraries: Record<string, string> };
  evaluation: { metrics: Metric[]; zero_division?: number; confusion_order?: string; roc_auc?: string; definitions?: string; r2_policy?: string };
  runtime: { version: string; result_schema: string };
};
export type Run = {
  id: string; project_id: string; dataset_id: string; sequence: number; revision: number;
  request_id: string; state: RunState; created_at: string; started_at: string | null; finished_at: string | null;
  summary: { task?: "regression" | "multiclass_classification"; result_schema?: string; model: FrozenModel; split: { test_size: number; random_seed: number; stratify?: boolean; shuffle?: boolean };
    target: FrozenTarget; dataset_fingerprint: string };
  result: RunResult | null;
  failure: null | { code: string; stage: string; message: string };
  provenance: Record<string, string>; artifacts: Record<string, { size_bytes: number | null; sha256: string | null; integrity: string }>;
  tracking_status: "NOT_ATTEMPTED" | "SYNCHRONIZED" | "FAILED"; mlflow_run_id: string | null; tracking_error: string | null;
  pipeline_ir: PipelineIR | null; execution_plan: FrozenPlan | null;
  snapshot_error: string | null; result_error?: string | null;
};
export type RunPage = { items: Run[]; total: number; offset: number; limit: number };
export type RunCode = { run_id: string; source: string; source_sha256: string; filename: string };
export type Capacity = { occupied: boolean; recovery_required: boolean };
