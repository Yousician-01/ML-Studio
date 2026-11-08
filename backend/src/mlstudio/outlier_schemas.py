"""Bounded optional outlier and numeric feature-selection intent."""

from typing import Literal

from pydantic import Field, model_validator

from mlstudio.schemas import InputModel


class OutlierFeature(InputModel):
    source: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    multiplier: float = Field(default=1.5, ge=0.1, le=10, allow_inf_nan=False)
    tails: Literal["both", "lower", "upper"] = "both"
    indicator: str | None = Field(
        default=None, min_length=1, max_length=200, pattern=r"^[A-Za-z][A-Za-z0-9_]*$"
    )
    missing: Literal["preserve", "reject"] = "preserve"
    invalid: Literal["reject", "coerce"] = "reject"


class OutlierConfig(InputModel):
    version: Literal["outlier-treatment-v1"] = "outlier-treatment-v1"
    features: list[OutlierFeature] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def distinct_outputs(self):
        names = [
            name for feature in self.features for name in [feature.name, feature.indicator] if name
        ]
        if len(names) != len(set(names)):
            raise ValueError("Outlier output and indicator names must be distinct.")
        return self


class ResolvedOutlierConfig(OutlierConfig):
    input_dtypes: dict[str, str]


class FeatureSelection(InputModel):
    version: Literal["feature-selection-v1"] = "feature-selection-v1"
    method: Literal["variance_threshold"] = "variance_threshold"
    stage: Literal["post_preprocessing"] = "post_preprocessing"
    features: list[str] = Field(min_length=1, max_length=128)
    threshold: float = Field(default=0, ge=0, le=1e12, allow_inf_nan=False)

    @model_validator(mode="after")
    def distinct_features(self):
        if len(self.features) != len(set(self.features)) or any(
            not name or len(name) > 200 for name in self.features
        ):
            raise ValueError("Choose distinct eligible feature names.")
        return self
