from typing import Literal

from pydantic import BaseModel

from mlstudio.pipeline_schemas import TypedScalar
from mlstudio.schemas import Scalar, SemanticType


class Frequency(BaseModel):
    value: Scalar
    count: int
    percentage: float
    label_truncated: bool = False


class HistogramBin(BaseModel):
    lower: float
    upper: float
    count: int


class NumericProfile(BaseModel):
    count: int
    mean: float | None
    standard_deviation: float | None
    minimum: Scalar
    q1: float | None
    median: float | None
    q3: float | None
    maximum: Scalar
    lower_whisker: float | None
    upper_whisker: float | None
    outlier_count: int | None
    lower_fence: float | None = None
    upper_fence: float | None = None
    outlier_percentage: float | None = None
    skewness: float | None = None
    skewness_unavailable_reason: str | None = None
    histogram: list[HistogramBin]
    unavailable_reason: str | None = None


class ColumnProfile(BaseModel):
    name: str
    physical_dtype: str
    semantic_type: SemanticType
    inferred_semantic_type: SemanticType
    semantic_override: SemanticType | None
    role: Literal["feature", "target", "excluded"]
    non_missing_count: int
    missing_count: int
    missing_percentage: float
    distinct_count: int
    uniqueness_percentage: float
    high_cardinality: bool
    identifier: bool
    constant: bool
    near_constant: bool
    dominant_count: int
    dominant_percentage: float
    numeric: NumericProfile | None
    frequencies: list[Frequency] | None
    other_count: int
    unavailable_reason: str | None


class TargetProfile(BaseModel):
    column: str
    missing_count: int
    non_missing_count: int
    classes: list[Frequency]
    majority_percentage: float
    positive_class: TypedScalar | None = None


class MissingColumn(BaseModel):
    name: str
    count: int
    percentage: float


class QualitySummary(BaseModel):
    constant_count: int
    near_constant_count: int
    all_missing_count: int
    identifier_count: int
    high_cardinality_count: int
    missing_column_count: int
    missing_columns: list[MissingColumn]
    missing_column_limit: int = 20
    near_constant_threshold: float = 95.0


class CorrelationProfile(BaseModel):
    method: Literal["pearson"] = "pearson"
    columns: list[str]
    values: list[list[float | None]]
    pair_counts: list[list[int]]
    eligible_count: int
    column_limit: int
    unavailable_reason: str | None = None


class ProfileResponse(BaseModel):
    dataset_id: str
    revision: int
    fingerprint: str
    original_filename: str
    profile_version: Literal["source-profile-v2"] = "source-profile-v2"
    population: Literal["full_source"] = "full_source"
    row_count: int
    column_count: int
    feature_count: int
    missing_cells: int
    missing_percentage: float
    duplicate_rows: int
    duplicate_percentage: float
    semantic_counts: dict[str, int]
    quality: QualitySummary
    filtered_column_count: int
    target: TargetProfile | None
    columns: list[ColumnProfile]
    column_offset: int
    column_limit: int
    category_limit: int
    histogram_bin_limit: int
    correlation: CorrelationProfile
