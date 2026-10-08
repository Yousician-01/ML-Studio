import type { PipelineIR, TypedScalar } from "./pipelines";

export type RunState = "CREATED" | "RUNNING" | "SUCCEEDED" | "FAILED";
export type RunRequest = { request_id: string; expected_revision: number; expected_source_sha256: string; expected_plan_sha256: string };
type Constructor = { name: string; parameters: Record<string, string | number | boolean | null> };
export type Run = {
  id: string; project_id: string; dataset_id: string; sequence: number; revision: number;
  request_id: string; state: RunState; created_at: string; started_at: string | null; finished_at: string | null;
  summary: { model: Constructor; split: { test_size: number; random_seed: number; stratify: boolean };
    target: { column: string; positive_class: TypedScalar; negative_class: TypedScalar }; dataset_fingerprint: string };
  result: null | { metrics: { accuracy: number; precision: number; recall: number; f1: number; roc_auc: number | null };
    roc_auc_unavailable_reason: string | null; population: { source: number; eligible: number; training: number; test: number };
    confusion_matrix: { labels: [TypedScalar, TypedScalar]; values: [[number, number], [number, number]] } };
  failure: null | { code: string; stage: string; message: string };
  provenance: Record<string, string>; artifacts: Record<string, { size_bytes: number; sha256: string; integrity: string }>;
  tracking_status: "NOT_ATTEMPTED" | "SYNCHRONIZED" | "FAILED"; mlflow_run_id: string | null; tracking_error: string | null;
  pipeline_ir: PipelineIR | null; execution_plan: null | { features: { name: string; semantic_type: string; operations: Constructor[] }[] };
  snapshot_error: string | null;
};
export type RunPage = { items: Run[]; total: number; offset: number; limit: number };
export type RunCode = { run_id: string; source: string; source_sha256: string; filename: string };
export type Capacity = { occupied: boolean; recovery_required: boolean };
