import type { Column, ProjectTask, Scalar } from "./projects";
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
export type TemporalOperation = "year" | "quarter" | "month" | "day" | "day_of_week" | "iso_week" | "iso_year" | "day_of_year" | "hour" | "minute" | "second" | "is_weekend" | "is_leap_year" | "is_month_start" | "is_month_end" | "is_quarter_start" | "is_quarter_end" | "is_year_start" | "is_year_end" | "date_diff" | "calendar_age" | "cyclic_sin" | "cyclic_cos";
export type TemporalExpression = { kind: "column" | "reference"; name: string } | { kind: "literal"; value: string } | { kind: "call"; operation: TemporalOperation; arguments: TemporalExpression[]; parameters: { unit?: "seconds" | "minutes" | "hours" | "days" | null } };
export type TemporalConfig = { version: "temporal-v1"; sources: Record<string, { format: string; naive: "utc" | "reject"; invalid: "reject" | "coerce" }>; features: { name: string; expression: TemporalExpression }[] };
export type DerivedOperation = "add" | "subtract" | "multiply" | "safe_divide" | "modulo" | "abs" | "negate" | "power" | "sqrt" | "log" | "log1p" | "round" | "floor" | "ceil" | "minimum" | "maximum" | "equal" | "not_equal" | "greater" | "greater_equal" | "less" | "less_equal" | "and" | "or" | "not" | "is_missing" | "is_not_missing" | "if" | "trim" | "lower" | "upper" | "length" | "starts_with" | "ends_with" | "contains" | "concat" | "replace" | "coalesce";
export type DerivedExpression = { kind: "column" | "reference"; name: string } | { kind: "literal"; value: string | number | boolean | null } | { kind: "call"; operation: DerivedOperation; arguments: DerivedExpression[]; parameters: { precision?: number | null } };
export type DerivedConfig = { version: "derived-v1"; features: { name: string; expression: DerivedExpression }[] };
export type ImputationStrategy = "constant" | "mean" | "median" | "most_frequent";
export type ImputationRule = { condition: DerivedExpression | null; strategy: ImputationStrategy; value: string | number | boolean | null; group_by: string[] };
export type ImputationFallback = { strategy: ImputationStrategy | "leave_missing"; value: string | number | boolean | null };
export type ColumnImputation = { rules: ImputationRule[]; fallback: ImputationFallback; indicator: string | null; previous_strategy: "mean" | "median" | "most_frequent" | null };
export type ImputationConfig = { version: "imputation-v1"; columns: Record<string, ColumnImputation> };
export type ImputationDiagnostics = { missing_count: number; rule_matches: number[]; indicator_values: number[] };
export type OutlierFeature = { source: string; name: string; multiplier: number; tails: "both" | "lower" | "upper"; indicator: string | null; missing: "preserve" | "reject"; invalid: "reject" | "coerce" };
export type OutlierConfig = { version: "outlier-treatment-v1"; features: OutlierFeature[] };
export type FeatureSelection = { version: "feature-selection-v1"; method: "variance_threshold"; stage: "post_preprocessing"; features: string[]; threshold: number };
export type OutlierDiagnostic = { fitted: boolean; missing_count: number; multiplier: number; message: string };
export type EngineeringFeature = { source: string; name: string } & (
 { method: "log" | "log1p" | "sqrt" | "reciprocal"; invalid: "reject" | "coerce" }
 | { method: "yeo_johnson" | "box_cox" }
 | { method: "quantile"; quantiles: number; distribution: "uniform" | "normal" }
 | { method: "boundaries"; boundaries: number[] }
 | { method: "width" | "quantile_bins"; bins: number }
 | { method: "rare"; min_count: number | null; min_frequency: number | null; rare_label: string; unknown: "rare" | "preserve" | "reject" }
 | { method: "ordinal"; mapping: { value: string | number | boolean; code: number }[]; unknown: "reject" | "code" | "missing"; unknown_code: number | null });
export type EngineeringConfig = { version: "feature-engineering-v1"; features: EngineeringFeature[] };
export type EngineeringDiagnostic = { fitted: boolean; missing_count: number; invalid_count: number; message: string };
export type CleaningPolicy = { format: string; naive: "utc" | "reject"; invalid: "reject" | "coerce" };
export type CleaningScalar = string | number | boolean | null;
export type CleaningStep = { id: string } & (
 { kind: "normalize"; column: string; tokens: string[]; trim: boolean; case_sensitive: boolean }
 | { kind: "convert"; column: string; destination: "continuous" | "categorical" | "binary" | "datetime"; invalid: "reject" | "coerce"; policy: CleaningPolicy }
 | { kind: "replace"; column: string; match: CleaningScalar; value: CleaningScalar; condition: DerivedExpression | null }
 | { kind: "datetime_fill"; column: string; value: string; condition: DerivedExpression | null; policy: CleaningPolicy }
 | { kind: "validate"; column: string; check: "required" | "range" | "allowed" | "length" | "type"; action: "report" | "reject" | "coerce"; minimum: number | null; maximum: number | null; values: CleaningScalar[]; expected: "numeric" | "string" | "boolean" | null }
 | { kind: "missing_filter"; columns: string[]; mode: "any" | "all"; keep: "missing" | "present" }
 | { kind: "filter"; condition: DerivedExpression; keep: "matches" | "nonmatches" }
 | { kind: "deduplicate"; columns: string[]; keep: "first" | "last" });
export type CleaningConfig = { version: "cleaning-v1"; steps: CleaningStep[] };
export type CleaningPreview = { columns: { name: string; physical_dtype: string; semantic_type: string; missing_count: number; unique_count: number }[]; rows: Scalar[][]; row_indices: number[]; source_rows: number; retained_rows: number; removed_rows: number; events: { id: string; kind: string; before: number; retained: number; removed: number }[]; diagnostics: { id: string; column?: string | null; invalid_count: number; status: string; message: string; examples: Scalar[] }[] };
export type TemporalPreview = { outlier_treatment?: Record<string, OutlierDiagnostic>; feature_selection?: FeatureSelection | null; feature_engineering?: Record<string, EngineeringDiagnostic>; cleaning?: CleaningPreview | null; imputation?: Record<string, ImputationDiagnostics>; revision: number; limit: number; columns: { name: string; semantic_type: string; missing_count: number; invalid_count?: number; physical_dtype?: string; values: (number | string | boolean | null)[] }[]; sources: Record<string, { missing_count: number; invalid_count: number; date_only_count: number }>; warnings: string[]; errors: string[] };
type Recipe = { outlier_treatment?: OutlierConfig | null; feature_selection?: FeatureSelection | null; feature_engineering?: EngineeringConfig | null; cleaning?: CleaningConfig | null; imputation?: ImputationConfig | null; derived?: DerivedConfig | null; temporal?: TemporalConfig | null; dataset: { dataset_id: string; fingerprint: string } | null; features: Record<string, FeatureIntent>; model: ModelIntent | null; split: SplitIntent | null };
export type PipelineIR = Recipe & (
 { ir_version: "0.1"; target: { column: string; positive_class: TypedScalar | null; missing_value_policy: "exclude_rows" } | null }
 | { ir_version: "0.2"; task: "regression"; target: { column: string; value_type: "numeric"; missing_value_policy: "exclude_rows" } | null }
 | { ir_version: "0.3"; task: "multiclass_classification"; target: { column: string; missing_value_policy: "reject" } | null });
export type PipelineIssue = { severity: "blocking" | "non_blocking"; scope: "pipeline" | "target" | "feature" | "train"; code: string; message: string; column: string | null; field: string | null };
export type ParameterSchema = { type?: string; default?: unknown; title?: string; minimum?: number; exclusiveMinimum?: number; anyOf?: ParameterSchema[]; enum?: (string | null)[] };
export type ModelDescriptor = { catalogue_version: string; id: ModelIntent["type"]; task: ProjectTask; name: string; parameter_schema: { properties: Record<string, ParameterSchema> }; defaults: Record<string, string | number | boolean | null>; contextual_constraints: Record<string, { minimum?: number | null; exclusive_minimum?: number | null; choices?: string[] | null; allow_none?: boolean; message: string }>; feature_requirements: { supported_semantics: string[]; supports_sparse: boolean }; compiler_adapter: string };
export type WorkingPipeline = { revision: number; ir: PipelineIR; columns: Column[]; target_classes: TypedScalar[]; target_missing_count: number; issues: PipelineIssue[]; prepare_valid: boolean; configuration_ready: boolean; code_generation_ready: boolean; original_filename: string | null; eligible_rows: number; train_rows: number | null; test_rows: number | null; model_defaults: ModelIntent[]; model_catalogue: ModelDescriptor[]; split_defaults: SplitIntent; executable: false; stale: boolean };
