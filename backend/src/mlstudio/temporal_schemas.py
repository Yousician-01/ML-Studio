"""Versioned, bounded temporal expressions carried by the existing Pipeline IR."""

import re
from typing import Annotated, Literal

from pydantic import Field, model_serializer, model_validator

from mlstudio.schemas import InputModel


class DatetimeSource(InputModel):
    format: str = Field(default="ISO8601", min_length=1, max_length=100)
    naive: Literal["utc", "reject"] = "reject"
    invalid: Literal["reject", "coerce"] = "reject"

    @model_validator(mode="after")
    def explicit_format(self):
        if self.format != "ISO8601" and not (
            "%Y" in self.format and "%m" in self.format and "%d" in self.format
        ):
            raise ValueError("Use ISO8601 or an explicit format containing year, month and day.")
        if self.format != "ISO8601" and (
            set(re.findall(r"%([A-Za-z%])", self.format)) - set("YmdHMSfz%")
        ):
            raise ValueError(
                "Use numeric date/time directives; locale-dependent formats are unsupported."
            )
        return self


class ColumnExpression(InputModel):
    kind: Literal["column"]
    name: str = Field(min_length=1, max_length=200)


class ReferenceExpression(InputModel):
    kind: Literal["reference"]
    name: str = Field(min_length=1, max_length=200)


class LiteralExpression(InputModel):
    kind: Literal["literal"]
    value: str = Field(min_length=10, max_length=100)


class TemporalParameters(InputModel):
    unit: Literal["seconds", "minutes", "hours", "days"] | None = None


class CallExpression(InputModel):
    kind: Literal["call"]
    operation: Literal[
        "year",
        "quarter",
        "month",
        "day",
        "day_of_week",
        "iso_week",
        "iso_year",
        "day_of_year",
        "hour",
        "minute",
        "second",
        "is_weekend",
        "is_leap_year",
        "is_month_start",
        "is_month_end",
        "is_quarter_start",
        "is_quarter_end",
        "is_year_start",
        "is_year_end",
        "date_diff",
        "calendar_age",
        "cyclic_sin",
        "cyclic_cos",
    ]
    arguments: list["Expression"] = Field(min_length=1, max_length=2)
    parameters: TemporalParameters = Field(default_factory=TemporalParameters)


Expression = Annotated[
    ColumnExpression | ReferenceExpression | LiteralExpression | CallExpression,
    Field(discriminator="kind"),
]
CallExpression.model_rebuild()


class DerivedFeature(InputModel):
    name: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    expression: Expression


class TemporalConfig(InputModel):
    version: Literal["temporal-v1"] = "temporal-v1"
    sources: dict[str, DatetimeSource] = Field(default_factory=dict, max_length=32)
    features: list[DerivedFeature] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def unique_outputs(self):
        names = [feature.name for feature in self.features]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate derived feature names.")
        return self


class TemporalFields(InputModel):
    temporal: TemporalConfig | None = None

    @model_serializer(mode="wrap")
    def omit_absent_extension(self, handler):
        # Keep old serialized IR/plans, their hashes and source goldens unchanged.
        data = handler(self)
        if self.temporal is None:
            data.pop("temporal", None)
        return data


class ResolvedTemporalConfig(TemporalConfig):
    input_dtypes: dict[str, str]


class TemporalPlanFields(TemporalFields):
    temporal: ResolvedTemporalConfig | None = None


def validate_temporal(config, semantics, target):
    """Stable topological order and output types; no Python expression evaluation."""
    from mlstudio.temporal_runtime_v1 import temporal_literal

    features = {feature.name: feature.expression for feature in config.features}
    if set(features) & set(semantics):
        raise ValueError("Derived feature names must not collide with source columns.")
    for name in config.sources:
        if name == target or semantics.get(name) != "datetime":
            raise ValueError("Temporal sources must be non-target columns with datetime semantics.")
    order, types, visiting = [], {}, set()
    nodes = 0

    def infer(expression, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 8 or nodes > 1024:
            raise ValueError("Temporal expressions exceed the bounded depth or size limit.")
        if expression.kind == "column":
            if expression.name not in config.sources:
                raise ValueError("Datetime column reference needs an explicit parsing policy.")
            return ("datetime", None)
        if expression.kind == "literal":
            temporal_literal(expression.value)
            return ("datetime", None)
        if expression.kind == "reference":
            return visit(expression.name, depth + 1)
        op = expression.operation
        args = [infer(arg, depth + 1) for arg in expression.arguments]
        if op in {"date_diff", "calendar_age"}:
            if args != [("datetime", None), ("datetime", None)]:
                raise ValueError("Date differences and age require two datetime arguments.")
        elif op in {"cyclic_sin", "cyclic_cos"}:
            if len(args) != 1 or args[0][1] not in {
                "quarter",
                "month",
                "day_of_week",
                "hour",
                "minute",
                "second",
            }:
                raise ValueError("Cyclical encoding requires a supported periodic component.")
        elif args != [("datetime", None)]:
            raise ValueError("Calendar extraction requires exactly one datetime argument.")
        if (op == "date_diff") != (expression.parameters.unit is not None):
            raise ValueError("An explicit unit is required only for date_diff.")
        return ("binary" if op.startswith("is_") else "continuous", op)

    def visit(name, depth=0):
        if name in types:
            return types[name]
        if name in visiting:
            raise ValueError("Cyclic derived feature dependencies.")
        if name not in features:
            raise ValueError("Unresolved derived feature reference.")
        visiting.add(name)
        result = infer(features[name], depth)
        if result[0] == "datetime":
            raise ValueError("Model features must be numeric/binary, not raw datetime values.")
        types[name] = result
        visiting.remove(name)
        order.append(name)
        return result

    for name in features:
        visit(name)
    return order, types
