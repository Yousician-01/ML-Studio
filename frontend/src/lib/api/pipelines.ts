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
export type PipelineIR = {
  ir_version: "0.1";
  dataset: { dataset_id: string; fingerprint: string } | null;
  target: { column: string; positive_class: TypedScalar | null; missing_value_policy: "exclude_rows" } | null;
  features: Record<string, FeatureIntent>;
  model: null;
  split: null;
};
export type PipelineIssue = {
  severity: "blocking" | "non_blocking";
  scope: "pipeline" | "target" | "feature" | "train";
  code: string;
  message: string;
  column: string | null;
};
export type WorkingPipeline = {
  revision: number;
  ir: PipelineIR;
  columns: Column[];
  target_classes: TypedScalar[];
  target_missing_count: number;
  issues: PipelineIssue[];
  prepare_valid: boolean;
  executable: false;
  stale: boolean;
};
