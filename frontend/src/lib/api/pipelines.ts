import type { Column } from "./projects";

export type TypedScalar =
  | { value_type: "string"; value: string }
  | { value_type: "integer"; value: number | string }
  | { value_type: "float"; value: number }
  | { value_type: "boolean"; value: boolean };
export type Operation =
  | { type: "impute"; strategy: "mean" | "median" | "most_frequent" }
  | { type: "scale"; method: "standard" | "min_max" | "robust" }
  | { type: "encode"; method: "one_hot" };
export type FeatureIntent = { included: boolean; operations: Operation[] };
export type ModelIntent =
  | { type: "logistic_regression"; parameters: { C: number | null; penalty: "l1" | "l2" | null; max_iter: number | null } }
  | { type: "decision_tree"; parameters: { max_depth: number | null; min_samples_split: number | null; min_samples_leaf: number | null } }
  | { type: "random_forest"; parameters: { n_estimators: number | null; max_depth: number | null; min_samples_split: number | null; min_samples_leaf: number | null } };
export type SplitIntent = { test_size: number | null; random_seed: number | null; stratify: boolean | null };
export type PipelineIR = {
  ir_version: "0.1";
  dataset: { dataset_id: string; fingerprint: string } | null;
  target: { column: string; positive_class: TypedScalar | null; missing_value_policy: "exclude_rows" } | null;
  features: Record<string, FeatureIntent>;
  model: ModelIntent | null;
  split: SplitIntent | null;
};
export type PipelineIssue = {
  severity: "blocking" | "non_blocking";
  scope: "pipeline" | "target" | "feature" | "train";
  code: string;
  message: string;
  column: string | null;
  field: string | null;
};
export type WorkingPipeline = {
  revision: number;
  ir: PipelineIR;
  columns: Column[];
  target_classes: TypedScalar[];
  target_missing_count: number;
  issues: PipelineIssue[];
  prepare_valid: boolean;
  code_generation_ready: boolean;
  original_filename: string | null;
  eligible_rows: number;
  train_rows: number | null;
  test_rows: number | null;
  model_defaults: ModelIntent[];
  split_defaults: SplitIntent;
  executable: false;
  stale: boolean;
};
