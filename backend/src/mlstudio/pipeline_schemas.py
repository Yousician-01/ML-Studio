"""Canonical v0.1 intent, separate from contextual readiness and API state."""

import math
import re
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from mlstudio.schemas import ColumnResponse, InputModel


class TypedScalar(InputModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value_type: Literal["string", "integer", "float", "boolean"]
    value: str | int | float | bool

    @model_validator(mode="after")
    def compatible_value(self):
        # JSON/JavaScript serializes 1.0 as 1; the explicit tag retains float meaning.
        if self.value_type == "float" and type(self.value) is int:
            try:
                self.value = float(self.value)
            except OverflowError as error:
                raise ValueError("A class must be finite.") from error
        expected = {"string": str, "integer": int, "float": float, "boolean": bool}
        # Decimal strings are the lossless wire representation for unsafe integers only.
        if self.value_type == "integer" and isinstance(self.value, str):
            if re.fullmatch(r"-?(0|[1-9][0-9]*)", self.value) and abs(int(self.value)) > 2**53 - 1:
                return self
        elif type(self.value) is expected[self.value_type]:
            if self.value_type == "float" and not math.isfinite(self.value):
                raise ValueError("A class must be finite.")
            if self.value_type != "integer" or abs(self.value) <= 2**53 - 1:
                return self
        raise ValueError("Class value must preserve its declared scalar type.")


class DatasetBinding(InputModel):
    dataset_id: str
    fingerprint: str


class TargetIntent(InputModel):
    column: str
    positive_class: TypedScalar | None = None
    missing_value_policy: Literal["exclude_rows"] = "exclude_rows"


class Impute(InputModel):
    type: Literal["impute"]
    strategy: Literal["mean", "median", "most_frequent"]


class Scale(InputModel):
    type: Literal["scale"]
    method: Literal["standard", "min_max", "robust"]


class Encode(InputModel):
    type: Literal["encode"]
    method: Literal["one_hot"]


Operation = Annotated[Impute | Scale | Encode, Field(discriminator="type")]


class FeatureIntent(InputModel):
    included: Annotated[bool, Field(strict=True)]
    operations: list[Operation]


# Defaults are ML Studio choices, explicitly materialized on model selection.
# Ranges are contextual issues so intermediate numeric intent remains saveable.
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Integer = Annotated[int, Field(strict=True)]


class LogisticParameters(InputModel):
    C: Number | None = 1.0
    penalty: Literal["l1", "l2"] | None = "l2"
    max_iter: Integer | None = 1000


class TreeParameters(InputModel):
    max_depth: Integer | None = None
    min_samples_split: Integer | None = 2
    min_samples_leaf: Integer | None = 1


class ForestParameters(TreeParameters):
    n_estimators: Integer | None = 100


class LogisticModel(InputModel):
    type: Literal["logistic_regression"]
    parameters: LogisticParameters = Field(default_factory=LogisticParameters)


class TreeModel(InputModel):
    type: Literal["decision_tree"]
    parameters: TreeParameters = Field(default_factory=TreeParameters)


class ForestModel(InputModel):
    type: Literal["random_forest"]
    parameters: ForestParameters = Field(default_factory=ForestParameters)


ModelIntent = Annotated[LogisticModel | TreeModel | ForestModel, Field(discriminator="type")]


class SplitIntent(InputModel):
    test_size: Number | None = 0.2
    random_seed: Integer | None = 42
    stratify: Annotated[bool, Field(strict=True)] | None = True


class PipelineIR(InputModel):
    ir_version: Literal["0.1"] = "0.1"
    dataset: DatasetBinding | None = None
    target: TargetIntent | None = None
    features: dict[str, FeatureIntent] = Field(default_factory=dict)
    model: ModelIntent | None = None
    split: SplitIntent | None = None


class PipelineIssue(InputModel):
    severity: Literal["blocking", "non_blocking"] = "blocking"
    scope: Literal["pipeline", "target", "feature", "train"]
    code: str
    message: str
    column: str | None = None
    field: str | None = None


class PipelineResponse(InputModel):
    revision: int
    ir: PipelineIR
    columns: list[ColumnResponse]
    target_classes: list[TypedScalar]
    target_missing_count: int
    issues: list[PipelineIssue]
    prepare_valid: bool
    code_generation_ready: bool
    original_filename: str | None
    eligible_rows: int
    train_rows: int | None
    test_rows: int | None
    model_defaults: list[ModelIntent]
    split_defaults: SplitIntent = Field(default_factory=SplitIntent)
    executable: Literal[False] = False
    stale: bool


class PipelineUpdate(InputModel):
    revision: Annotated[int, Field(ge=1)]
    ir: PipelineIR


class PipelineReset(InputModel):
    revision: Annotated[int, Field(ge=1)]
    dataset_id: str
