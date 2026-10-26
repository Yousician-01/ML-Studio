import type { Column, ProjectTask } from "./projects";
export type TypedScalar = { value_type: "string"; value: string } | { value_type: "integer"; value: number | string } | { value_type: "float"; value: number } | { value_type: "boolean"; value: boolean };
export type Operation = { type: "impute"; strategy: "mean" | "median" | "most_frequent" } | { type: "scale"; method: "standard" | "min_max" | "robust" } | { type: "encode"; method: "one_hot" };
export type FeatureIntent = { included: boolean; operations: Operation[] };
export type ModelIntent =
 | { type: "logistic_regression"; parameters: { C: number | null; penalty: "l1" | "l2" | null; max_iter: number | null } }
 | { type: "decision_tree"; parameters: { max_depth: number | null; min_samples_split: number | null; min_samples_leaf: number | null } }
 | { type: "random_forest"; parameters: { n_estimators: number | null; max_depth: number | null; min_samples_split: number | null; min_samples_leaf: number | null } }
 | { type: "linear_regression"; parameters: { fit_intercept: boolean } }
 | { type: "ridge"; parameters: { alpha: number; fit_intercept: boolean } };
export type SplitIntent = { test_size: number | null; random_seed: number | null; stratify?: boolean | null };
type Recipe = { dataset: { dataset_id: string; fingerprint: string } | null; features: Record<string, FeatureIntent>; model: ModelIntent | null; split: SplitIntent | null };
export type PipelineIR = Recipe & (
 { ir_version: "0.1"; target: { column: string; positive_class: TypedScalar | null; missing_value_policy: "exclude_rows" } | null }
 | { ir_version: "0.2"; task: "regression"; target: { column: string; value_type: "numeric"; missing_value_policy: "exclude_rows" } | null });
export type PipelineIssue = { severity: "blocking" | "non_blocking"; scope: "pipeline" | "target" | "feature" | "train"; code: string; message: string; column: string | null; field: string | null };
export type ParameterSchema = { type?: string; default?: unknown; title?: string; minimum?: number; exclusiveMinimum?: number; anyOf?: ParameterSchema[]; enum?: (string | null)[] };
export type ModelDescriptor = { catalogue_version: string; id: ModelIntent["type"]; task: ProjectTask; name: string; parameter_schema: { properties: Record<string, ParameterSchema> }; defaults: Record<string, string | number | boolean | null>; contextual_constraints: Record<string, { minimum?: number | null; exclusive_minimum?: number | null; choices?: string[] | null; allow_none?: boolean; message: string }>; feature_requirements: { supported_semantics: string[]; supports_sparse: boolean }; compiler_adapter: string };
export type WorkingPipeline = { revision: number; ir: PipelineIR; columns: Column[]; target_classes: TypedScalar[]; target_missing_count: number; issues: PipelineIssue[]; prepare_valid: boolean; configuration_ready: boolean; code_generation_ready: boolean; original_filename: string | null; eligible_rows: number; train_rows: number | null; test_rows: number | null; model_defaults: ModelIntent[]; model_catalogue: ModelDescriptor[]; split_defaults: SplitIntent; executable: false; stale: boolean };
