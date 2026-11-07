"""Strict, versioned general feature expressions; bounds precede AST parsing."""

from typing import Annotated, Literal

from pydantic import (
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from mlstudio.derived_runtime_v1 import derived_bounds, derived_validate
from mlstudio.schemas import InputModel


class ColumnExpression(InputModel):
    kind: Literal["column"]
    name: str = Field(min_length=1, max_length=200)


class ReferenceExpression(InputModel):
    kind: Literal["reference"]
    name: str = Field(min_length=1, max_length=200)


class LiteralExpression(InputModel):
    kind: Literal["literal"]
    value: StrictStr | StrictBool | StrictInt | StrictFloat | None

    @field_validator("value")
    @classmethod
    def finite_primitive(cls, value):
        import math

        if isinstance(value, str) and len(value) > 1000:
            raise ValueError("Literal exceeds bounded length limit.")
        if type(value) is int and abs(value) > 2**53 - 1:
            raise ValueError(
                "Exact integer literal is outside supported safe range; "
                "use a value between -(2**53 - 1) and 2**53 - 1."
            )
        if type(value) in (int, float):
            try:
                finite = math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite:
                raise ValueError("Numeric literals must be finite.")
        return value


class DerivedParameters(InputModel):
    precision: Annotated[StrictInt, Field(ge=-12, le=12)] | None = None


class CallExpression(InputModel):
    kind: Literal["call"]
    operation: Literal[
        "add",
        "subtract",
        "multiply",
        "safe_divide",
        "modulo",
        "abs",
        "negate",
        "power",
        "sqrt",
        "log",
        "log1p",
        "round",
        "floor",
        "ceil",
        "minimum",
        "maximum",
        "equal",
        "not_equal",
        "greater",
        "greater_equal",
        "less",
        "less_equal",
        "and",
        "or",
        "not",
        "is_missing",
        "is_not_missing",
        "if",
        "trim",
        "lower",
        "upper",
        "length",
        "starts_with",
        "ends_with",
        "contains",
        "concat",
        "replace",
        "coalesce",
    ]
    arguments: list["Expression"] = Field(min_length=1, max_length=16)
    parameters: DerivedParameters = Field(default_factory=DerivedParameters)


Expression = Annotated[
    ColumnExpression | ReferenceExpression | LiteralExpression | CallExpression,
    Field(discriminator="kind"),
]
CallExpression.model_rebuild()


class DerivedFeature(InputModel):
    name: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    expression: Expression


class DerivedConfig(InputModel):
    version: Literal["derived-v1"] = "derived-v1"
    features: list[DerivedFeature] = Field(default_factory=list, max_length=128)

    @model_validator(mode="before")
    @classmethod
    def bounded_tree(cls, value):
        if isinstance(value, dict):
            derived_bounds(value)
        return value

    @model_validator(mode="after")
    def unique_outputs(self):
        names = [feature.name for feature in self.features]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate derived feature names.")
        return self


class ResolvedDerivedConfig(DerivedConfig):
    input_dtypes: dict[str, str]
    output_types: dict[str, Literal["numeric", "boolean", "string"]]
    input_types: dict[str, Literal["numeric", "boolean", "string", "unsupported"]] = Field(
        default_factory=dict
    )


def validate_derived(config, source_types, target, temporal_types=None):
    return derived_validate(config.model_dump(mode="json"), source_types, target, temporal_types)
