"""Optional bounded feature-engineering-v1 intent and frozen input contract."""

from typing import Annotated, Literal

from pydantic import Field, StrictInt, model_validator

from mlstudio.derived_schemas import LiteralExpression
from mlstudio.schemas import InputModel


class EngineeringOutput(InputModel):
    source: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")


class MathFeature(EngineeringOutput):
    method: Literal["log", "log1p", "sqrt", "reciprocal"]
    invalid: Literal["reject", "coerce"] = "reject"


class PowerFeature(EngineeringOutput):
    method: Literal["yeo_johnson", "box_cox"]


class QuantileFeature(EngineeringOutput):
    method: Literal["quantile"]
    distribution: Literal["uniform", "normal"] = "uniform"
    quantiles: int = Field(default=100, ge=2, le=1000, strict=True)


class BoundaryFeature(EngineeringOutput):
    method: Literal["boundaries"]
    boundaries: list[float] = Field(min_length=1, max_length=99)

    @model_validator(mode="after")
    def increasing(self):
        import math

        if any(not math.isfinite(v) for v in self.boundaries) or any(
            a >= b for a, b in zip(self.boundaries, self.boundaries[1:], strict=False)
        ):
            raise ValueError("Bin boundaries must be finite and strictly increasing.")
        return self


class FittedBins(EngineeringOutput):
    method: Literal["width", "quantile_bins"]
    bins: int = Field(default=5, ge=2, le=100, strict=True)


class RareFeature(EngineeringOutput):
    method: Literal["rare"]
    min_count: int | None = Field(default=None, ge=1, le=1000000, strict=True)
    min_frequency: float | None = Field(default=0.02, gt=0, le=1, allow_inf_nan=False)
    rare_label: str = Field(default="Other", min_length=1, max_length=200)
    unknown: Literal["rare", "preserve", "reject"] = "rare"

    @model_validator(mode="after")
    def one_threshold(self):
        if (self.min_count is None) == (self.min_frequency is None):
            raise ValueError("Choose exactly one rare-category frequency threshold.")
        return self


class OrdinalValue(LiteralExpression):
    kind: Literal["literal"] = "literal"
    code: Annotated[StrictInt, Field(ge=-(2**31), le=2**31 - 1)]


class OrdinalFeature(EngineeringOutput):
    method: Literal["ordinal"]
    mapping: list[OrdinalValue] = Field(min_length=1, max_length=1000)
    unknown: Literal["reject", "code", "missing"] = "reject"
    unknown_code: Annotated[StrictInt, Field(ge=-(2**31), le=2**31 - 1)] | None = None

    @model_validator(mode="after")
    def unique_mapping(self):
        from mlstudio.feature_engineering_runtime_v1 import engineering_key

        keys = [engineering_key(item.value) for item in self.mapping]
        codes = [item.code for item in self.mapping]
        if None in keys or len(set(keys)) != len(keys) or len(set(codes)) != len(codes):
            raise ValueError("Ordinal keys and codes must be unique and nonmissing.")
        if (self.unknown == "code") != (self.unknown_code is not None):
            raise ValueError("Configure an unknown code only for the code policy.")
        if self.unknown_code in codes:
            raise ValueError("Unknown code must not collide with a mapped code.")
        return self


EngineeringFeature = Annotated[
    MathFeature
    | PowerFeature
    | QuantileFeature
    | BoundaryFeature
    | FittedBins
    | RareFeature
    | OrdinalFeature,
    Field(discriminator="method"),
]


class EngineeringConfig(InputModel):
    version: Literal["feature-engineering-v1"] = "feature-engineering-v1"
    features: list[EngineeringFeature] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def unique_outputs(self):
        names = [feature.name for feature in self.features]
        if len(names) != len(set(names)):
            raise ValueError("Engineering output names must be unique.")
        return self


class ResolvedEngineeringConfig(EngineeringConfig):
    input_dtypes: dict[str, str]
    input_types: dict[str, str]
