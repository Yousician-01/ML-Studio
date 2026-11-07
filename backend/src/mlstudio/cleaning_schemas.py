"""Bounded cleaning intent; row selection is explicitly training-only."""

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

from mlstudio.cleaning_runtime_v1 import cleaning_bounds, cleaning_scalar
from mlstudio.datetime_policy import DatetimeSource
from mlstudio.derived_schemas import Expression
from mlstudio.schemas import InputModel

Scalar = StrictStr | StrictBool | StrictInt | StrictFloat | None


class CleaningStepBase(InputModel):
    id: str = Field(min_length=1, max_length=80)


class CleaningColumnStep(CleaningStepBase):
    column: str = Field(min_length=1, max_length=200)


class NormalizeStep(CleaningColumnStep):
    kind: Literal["normalize"]
    tokens: list[Annotated[StrictStr, Field(max_length=1000)]] = Field(max_length=32)
    trim: StrictBool = False
    case_sensitive: StrictBool = True


class ConvertStep(CleaningColumnStep):
    kind: Literal["convert"]
    destination: Literal["continuous", "categorical", "binary", "datetime"]
    invalid: Literal["reject", "coerce"] = "reject"
    policy: DatetimeSource = Field(default_factory=DatetimeSource)


class ReplaceStep(CleaningColumnStep):
    kind: Literal["replace"]
    match: Scalar = None
    value: Scalar = None
    condition: Expression | None = None

    @field_validator("match", "value")
    @classmethod
    def safe_scalar(cls, value):
        cleaning_scalar(value)
        return value


class DatetimeFillStep(CleaningColumnStep):
    kind: Literal["datetime_fill"]
    value: str = Field(min_length=10, max_length=100)
    condition: Expression | None = None
    policy: DatetimeSource = Field(default_factory=DatetimeSource)


class ValidateStep(CleaningColumnStep):
    kind: Literal["validate"]
    check: Literal["required", "range", "allowed", "length", "type"]
    action: Literal["report", "reject", "coerce"] = "report"
    minimum: StrictFloat | StrictInt | None = None
    maximum: StrictFloat | StrictInt | None = None
    values: list[Scalar] = Field(default_factory=list, max_length=128)
    expected: Literal["numeric", "string", "boolean"] | None = None

    @field_validator("minimum", "maximum")
    @classmethod
    def safe_bounds(cls, value):
        cleaning_scalar(value)
        return value

    @field_validator("values")
    @classmethod
    def safe_values(cls, values):
        for value in values:
            cleaning_scalar(value)
        return values


class MissingFilterStep(CleaningStepBase):
    kind: Literal["missing_filter"]
    columns: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        min_length=1, max_length=16
    )
    mode: Literal["any", "all"] = "any"
    keep: Literal["missing", "present"] = "present"


class FilterStep(CleaningStepBase):
    kind: Literal["filter"]
    condition: Expression
    keep: Literal["matches", "nonmatches"] = "matches"


class DeduplicateStep(CleaningStepBase):
    kind: Literal["deduplicate"]
    columns: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        min_length=1, max_length=32
    )
    keep: Literal["first", "last"] = "first"


CleaningStep = Annotated[
    NormalizeStep
    | ConvertStep
    | ReplaceStep
    | DatetimeFillStep
    | ValidateStep
    | MissingFilterStep
    | FilterStep
    | DeduplicateStep,
    Field(discriminator="kind"),
]


class CleaningConfig(InputModel):
    version: Literal["cleaning-v1"] = "cleaning-v1"
    steps: list[CleaningStep] = Field(default_factory=list, max_length=64)

    @model_validator(mode="before")
    @classmethod
    def bounded_conditions(cls, value):
        if isinstance(value, dict):
            cleaning_bounds(value)
        return value

    @model_validator(mode="after")
    def unique_ids(self):
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("Cleaning step ids must be unique.")
        return self


class ResolvedCleaningConfig(CleaningConfig):
    input_dtypes: dict[str, str]
    input_types: dict[str, str]
    selection_types: dict[str, str] = Field(default_factory=dict)
    target: str


def validate_cleaning(config, source_types, target=None, selection_types=None):
    from mlstudio.cleaning_runtime_v1 import cleaning_validate

    return cleaning_validate(config, source_types, target, selection_types)
