import type { Column, Scalar } from "./projects";
import type { TypedScalar } from "./pipelines";

export type Frequency = {
  value: Scalar;
  count: number;
  percentage: number;
  label_truncated: boolean;
};
export type NumericProfile = {
  count: number;
  mean: number | null;
  standard_deviation: number | null;
  minimum: Scalar;
  q1: number | null;
  median: number | null;
  q3: number | null;
  maximum: Scalar;
  lower_whisker: number | null;
  upper_whisker: number | null;
  outlier_count: number | null;
  lower_fence: number | null;
  upper_fence: number | null;
  outlier_percentage: number | null;
  skewness: number | null;
  skewness_unavailable_reason: string | null;
  histogram: { lower: number; upper: number; count: number }[];
  unavailable_reason: string | null;
};
export type ColumnProfile = {
  name: string;
  physical_dtype: string;
  semantic_type: Column["effective_semantic_type"];
  inferred_semantic_type: Column["inferred_semantic_type"];
  semantic_override: Column["semantic_override"];
  role: Column["role"];
  non_missing_count: number;
  missing_count: number;
  missing_percentage: number;
  distinct_count: number;
  uniqueness_percentage: number;
  high_cardinality: boolean;
  identifier: boolean;
  constant: boolean;
  near_constant: boolean;
  dominant_count: number;
  dominant_percentage: number;
  numeric: NumericProfile | null;
  frequencies: Frequency[] | null;
  other_count: number;
  unavailable_reason: string | null;
};
export type Profile = {
  task: "binary_classification" | "multiclass_classification";
  dataset_id: string;
  revision: number;
  fingerprint: string;
  original_filename: string;
  profile_version: "source-profile-v2";
  population: "full_source";
  row_count: number;
  column_count: number;
  feature_count: number;
  missing_cells: number;
  missing_percentage: number;
  duplicate_rows: number;
  duplicate_percentage: number;
  semantic_counts: Record<string, number>;
  quality: {
    constant_count: number; near_constant_count: number; all_missing_count: number;
    identifier_count: number; high_cardinality_count: number; missing_column_count: number;
    missing_columns: { name: string; count: number; percentage: number }[];
    missing_column_limit: number; near_constant_threshold: number;
  };
  filtered_column_count: number;
  target: {
    column: string;
    missing_count: number;
    non_missing_count: number;
    classes: Frequency[];
    majority_percentage: number;
    positive_class: TypedScalar | null;
  } | null;
  columns: ColumnProfile[];
  column_offset: number;
  column_limit: number;
  category_limit: number;
  histogram_bin_limit: number;
  correlation: {
    method: "pearson";
    columns: string[];
    values: (number | null)[][];
    pair_counts: number[][];
    eligible_count: number;
    column_limit: number;
    unavailable_reason: string | null;
  };
};

export type TargetRelationship = {
  feature: string; target: string; paired_rows: number; missing_pair_rows: number;
  missing_feature_rows: number; missing_target_rows: number;
  pearson: number | null; correlation_unavailable_reason: string | null;
  points: { x: number; y: number }[]; point_limit: 200;
  sampling: "evenly-spaced-source-order-v1"; scatter_unavailable_reason: string | null;
};
export type RegressionProfile = {
  task: "regression"; profile_version: "regression-source-profile-v1"; population: "full_source";
  dataset_id: string; revision: number; fingerprint: string; original_filename: string;
  source_integrity: "verified"; row_count: number; column_count: number;
  target: null | { name: string; physical_dtype: string; semantic_type: Column["effective_semantic_type"];
    role: "target"; observed_count: number; missing_count: number; distinct_count: number;
    constant: boolean; numeric: NumericProfile; standard_deviation_definition: "sample-ddof-1"; quantile_definition: "linear" };
  numeric_feature_count: number; feature_offset: number; feature_limit: 20; histogram_bin_limit: 10;
  feature_options: { name: string; physical_dtype: string; semantic_type: Column["effective_semantic_type"]; role: Column["role"] }[];
  relationship: TargetRelationship | null;
};
export type SourceProfile = Profile | RegressionProfile;
