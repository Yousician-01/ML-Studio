import type { PipelineIR, TypedScalar } from "./pipelines";

export type RunState = "CREATED" | "RUNNING" | "SUCCEEDED" | "FAILED";
export type RunRequest = { request_id: string; expected_revision: number; expected_source_sha256: string; expected_plan_sha256: string };
export type Constructor = { name: string; parameters: Record<string, string | number | boolean | null | number[]> };
export type Metric = "accuracy" | "precision" | "recall" | "f1" | "roc_auc";
export type RunResult = {
  schema_version: string;
  metrics: Record<Metric, number | null>;
  roc_auc_unavailable_reason: string | null;
  population: { source: number; eligible: number; training: number; test: number };
  confusion_matrix: { labels: [TypedScalar, TypedScalar]; values: [[number, number], [number, number]] };
};
export type FrozenPlan = {
  plan_version: string; ir_version: string;
  generator: string;
  source: { parser: string; size_bytes: number; encoding: string; missing_values: string; integer_policy: string };
  target: { column: string; physical_dtype: string; semantic_type: string; missing_value_policy: string; positive_class: TypedScalar; negative_class: TypedScalar };
  split: { test_size: number; random_seed: number; stratify: boolean };
  model: Constructor;
  features: { name: string; physical_dtype: string; semantic_type: string; operations: Constructor[] }[];
  implementation: { version: string; python: string; libraries: Record<string, string> };
  evaluation: { metrics: Metric[]; zero_division: number; confusion_order: string; roc_auc: string };
  runtime: { version: string; result_schema: string };
};
export type Run = {
  id: string; project_id: string; dataset_id: string; sequence: number; revision: number;
  request_id: string; state: RunState; created_at: string; started_at: string | null; finished_at: string | null;
  summary: { model: Constructor; split: { test_size: number; random_seed: number; stratify: boolean };
    target: { column: string; positive_class: TypedScalar; negative_class: TypedScalar }; dataset_fingerprint: string };
  result: RunResult | null;
  failure: null | { code: string; stage: string; message: string };
  provenance: Record<string, string>; artifacts: Record<string, { size_bytes: number; sha256: string; integrity: string }>;
  tracking_status: "NOT_ATTEMPTED" | "SYNCHRONIZED" | "FAILED"; mlflow_run_id: string | null; tracking_error: string | null;
  pipeline_ir: PipelineIR | null; execution_plan: FrozenPlan | null;
  snapshot_error: string | null;
};
export type RunPage = { items: Run[]; total: number; offset: number; limit: number };
export type RunCode = { run_id: string; source: string; source_sha256: string; filename: string };
export type Capacity = { occupied: boolean; recovery_required: boolean };
