from typing import Annotated, Literal

from pydantic import BaseModel, Field

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
    task: Literal["binary_classification"] = "binary_classification"
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


class NumericFeature(BaseModel):
    name: str
    physical_dtype: str
    semantic_type: SemanticType
    role: Literal["feature", "target", "excluded"]


class RegressionTargetProfile(NumericFeature):
    observed_count: int
    missing_count: int
    distinct_count: int
    constant: bool
    numeric: NumericProfile
    standard_deviation_definition: Literal["sample-ddof-1"] = "sample-ddof-1"
    quantile_definition: Literal["linear"] = "linear"


class ScatterPoint(BaseModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class TargetRelationship(BaseModel):
    feature: str
    target: str
    paired_rows: int
    missing_pair_rows: int
    missing_feature_rows: int
    missing_target_rows: int
    pearson: float | None
    correlation_unavailable_reason: str | None
    points: list[ScatterPoint] = Field(max_length=200)
    point_limit: Literal[200] = 200
    sampling: Literal["evenly-spaced-source-order-v1"] = "evenly-spaced-source-order-v1"
    scatter_unavailable_reason: str | None = None


class RegressionProfileResponse(BaseModel):
    task: Literal["regression"] = "regression"
    profile_version: Literal["regression-source-profile-v1"] = "regression-source-profile-v1"
    population: Literal["full_source"] = "full_source"
    dataset_id: str
    revision: int
    fingerprint: str
    original_filename: str
    source_integrity: Literal["verified"] = "verified"
    row_count: int
    column_count: int
    target: RegressionTargetProfile | None
    numeric_feature_count: int
    feature_options: list[NumericFeature]
    feature_offset: int
    feature_limit: Literal[20] = 20
    histogram_bin_limit: Literal[10] = 10
    relationship: TargetRelationship | None


SourceProfileResponse = Annotated[
    ProfileResponse | RegressionProfileResponse, Field(discriminator="task")
]
