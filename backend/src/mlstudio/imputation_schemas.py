"""Bounded versioned configuration for training-fitted advanced imputation."""

from typing import Literal

from pydantic import (
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from mlstudio.derived_schemas import Expression, LiteralExpression
from mlstudio.imputation_runtime_v1 import (
    imputation_bounds,
    imputation_predicate,
    imputation_validate,
)
from mlstudio.schemas import InputModel


class ImputationFallback(InputModel):
    strategy: Literal["constant", "mean", "median", "most_frequent", "leave_missing"] = (
        "leave_missing"
    )
    value: StrictStr | StrictBool | StrictInt | StrictFloat | None = None

    @field_validator("value")
    @classmethod
    def finite_scalar(cls, value):
        return LiteralExpression(kind="literal", value=value).value


class ImputationRule(InputModel):
    condition: Expression | None = None
    strategy: Literal["constant", "mean", "median", "most_frequent"]
    value: StrictStr | StrictBool | StrictInt | StrictFloat | None = None
    group_by: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("condition", mode="before")
    @classmethod
    def bounded_condition(cls, value):
        if isinstance(value, dict):
            imputation_predicate(value, {})
        return value

    @field_validator("value")
    @classmethod
    def finite_scalar(cls, value):
        return LiteralExpression(kind="literal", value=value).value


class ColumnImputation(InputModel):
    rules: list[ImputationRule] = Field(min_length=1, max_length=16)
    fallback: ImputationFallback = Field(default_factory=ImputationFallback)
    indicator: str | None = Field(default=None, min_length=1, max_length=200)
    previous_strategy: Literal["mean", "median", "most_frequent"] | None = None


class ImputationConfig(InputModel):
    version: Literal["imputation-v1"] = "imputation-v1"
    columns: dict[str, ColumnImputation] = Field(default_factory=dict, max_length=64)

    @model_validator(mode="before")
    @classmethod
    def bounded_predicates(cls, value):
        if isinstance(value, dict):
            imputation_bounds(value)
        return value


class ResolvedImputationConfig(ImputationConfig):
    input_types: dict[str, Literal["numeric", "boolean", "string", "unsupported"]]
    input_dtypes: dict[str, str]


def validate_imputation(config, input_types, target=None):
    return imputation_validate(config, input_types, target)
