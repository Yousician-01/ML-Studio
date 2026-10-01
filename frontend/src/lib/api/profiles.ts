import type { Column, Scalar } from "./projects";

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
  outlier_count: number;
  histogram: { lower: number; upper: number; count: number }[];
  unavailable_reason: string | null;
};
export type ColumnProfile = {
  name: string;
  physical_dtype: string;
  semantic_type: Column["effective_semantic_type"];
  role: Column["role"];
  non_missing_count: number;
  missing_count: number;
  missing_percentage: number;
  distinct_count: number;
  uniqueness_percentage: number;
  high_cardinality: boolean;
  identifier: boolean;
  numeric: NumericProfile | null;
  frequencies: Frequency[] | null;
  other_count: number;
  unavailable_reason: string | null;
};
export type Profile = {
  dataset_id: string;
  revision: number;
  fingerprint: string;
  original_filename: string;
  profile_version: "source-profile-v1";
  population: "full_source";
  row_count: number;
  column_count: number;
  feature_count: number;
  missing_cells: number;
  missing_percentage: number;
  duplicate_rows: number;
  duplicate_percentage: number;
  semantic_counts: Record<string, number>;
  target: {
    column: string;
    missing_count: number;
    non_missing_count: number;
    classes: Frequency[];
    majority_percentage: number;
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
