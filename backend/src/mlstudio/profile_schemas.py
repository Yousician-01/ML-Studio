from typing import Literal

from pydantic import BaseModel

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
    outlier_count: int
    histogram: list[HistogramBin]
    unavailable_reason: str | None = None


class ColumnProfile(BaseModel):
    name: str
    physical_dtype: str
    semantic_type: SemanticType
    role: Literal["feature", "target", "excluded"]
    non_missing_count: int
    missing_count: int
    missing_percentage: float
    distinct_count: int
    uniqueness_percentage: float
    high_cardinality: bool
    identifier: bool
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
    profile_version: Literal["source-profile-v1"] = "source-profile-v1"
    population: Literal["full_source"] = "full_source"
    row_count: int
    column_count: int
    feature_count: int
    missing_cells: int
    missing_percentage: float
    duplicate_rows: int
    duplicate_percentage: float
    semantic_counts: dict[str, int]
    target: TargetProfile | None
    columns: list[ColumnProfile]
    column_offset: int
    column_limit: int
    category_limit: int
    histogram_bin_limit: int
    correlation: CorrelationProfile
