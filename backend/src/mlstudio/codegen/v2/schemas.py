"""Frozen regression implementation contract, independent of editable intent."""

import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, model_validator

from mlstudio.codegen.schemas import FeaturePlan, PlanModel, SourceContract
from mlstudio.pipeline_schemas import DatasetBinding

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Integer = Annotated[int, Field(strict=True)]
Boolean = Annotated[bool, Field(strict=True)]


class LinearParameters(PlanModel):
    fit_intercept: Boolean
    copy_X: Boolean = True
    tol: Number = 1e-6
    n_jobs: Integer = 1
    positive: Boolean = False

    @model_validator(mode="after")
    def fixed_implementation(self):
        if not self.copy_X or self.tol != 1e-6 or self.n_jobs != 1 or self.positive:
            raise ValueError("Unsupported Linear Regression implementation parameters.")
        return self


class RidgeParameters(PlanModel):
    alpha: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0)]
    fit_intercept: Boolean
    copy_X: Boolean = True
    max_iter: Integer = 10000
    tol: Number = 1e-6
    solver: Literal["lsqr"] = "lsqr"
    positive: Boolean = False
    random_state: None = None

    @model_validator(mode="after")
    def fixed_implementation(self):
        if not self.copy_X or self.max_iter != 10000 or self.tol != 1e-6 or self.positive:
            raise ValueError("Unsupported Ridge implementation parameters.")
        return self


class LinearImplementation(PlanModel):
    type: Literal["linear_regression"]
    adapter: Literal["sklearn-linear-v2"] = "sklearn-linear-v2"
    estimator: Literal["LinearRegression"] = "LinearRegression"
    parameters: LinearParameters


class RidgeImplementation(PlanModel):
    type: Literal["ridge"]
    adapter: Literal["sklearn-ridge-v2"] = "sklearn-ridge-v2"
    estimator: Literal["Ridge"] = "Ridge"
    parameters: RidgeParameters


ModelImplementation = Annotated[
    LinearImplementation | RidgeImplementation, Field(discriminator="type")
]


class NumericTarget(PlanModel):
    column: str
    physical_dtype: str
    semantic_type: str
    value_type: Literal["numeric"] = "numeric"
    missing_value_policy: Literal["exclude_rows"] = "exclude_rows"
    numeric_conversion: Literal["lossless-float64"] = "lossless-float64"


class RegressionSplit(PlanModel):
    test_size: Annotated[float, Field(strict=True, ge=0.05, le=0.5)]
    random_seed: Annotated[int, Field(strict=True, ge=0, le=2147483647)]
    shuffle: Literal[True] = True


class Implementation(PlanModel):
    version: Literal["sklearn-local-v2"] = "sklearn-local-v2"
    python: str
    libraries: dict[str, str]
    grouping: Literal["one-branch-per-feature-source-order"] = "one-branch-per-feature-source-order"
    remainder: Literal["drop"] = "drop"
    sparse_threshold: Literal[1.0] = 1.0
    empty_training_feature: Literal["fail"] = "fail"

    @model_validator(mode="after")
    def complete_versions(self):
        if set(self.libraries) != {"pandas", "numpy", "scikit-learn", "joblib", "scipy"}:
            raise ValueError("Incomplete library environment contract.")
        if not self.python or not all(self.libraries.values()):
            raise ValueError("Missing runtime versions.")
        return self


class Runtime(PlanModel):
    version: Literal["cli-v1"] = "cli-v1"
    result_schema: Literal["mlstudio-result-v2"] = "mlstudio-result-v2"
    model_format: Literal["joblib-complete-pipeline"] = "joblib-complete-pipeline"


class Evaluation(PlanModel):
    metrics: tuple[Literal["mae"], Literal["mse"], Literal["rmse"], Literal["r2"]] = (
        "mae",
        "mse",
        "rmse",
        "r2",
    )
    definitions: Literal["sklearn-regression-v1"] = "sklearn-regression-v1"
    r2_policy: Literal["unavailable-if-small-or-constant"] = "unavailable-if-small-or-constant"


class RegressionPlan(PlanModel):
    plan_version: Literal["0.2"] = "0.2"
    ir_version: Literal["0.2"] = "0.2"
    task: Literal["regression"] = "regression"
    generator: Literal["mlstudio-python-v2"] = "mlstudio-python-v2"
    dataset: DatasetBinding
    source: SourceContract
    target: NumericTarget
    features: tuple[FeaturePlan, ...]
    split: RegressionSplit
    model: ModelImplementation
    implementation: Implementation
    runtime: Runtime = Field(default_factory=Runtime)
    evaluation: Evaluation = Field(default_factory=Evaluation)

    @model_validator(mode="after")
    def feature_contract(self):
        names = [feature.name for feature in self.features]
        if not names or len(set(names)) != len(names) or self.target.column in names:
            raise ValueError("Invalid ordered feature contract.")
        if any(
            op.name
            not in {
                "SimpleImputer",
                "StandardScaler",
                "MinMaxScaler",
                "RobustScaler",
                "OneHotEncoder",
            }
            for feature in self.features
            for op in feature.operations
        ):
            raise ValueError("Unsupported feature constructor.")
        return self


def evaluation_context(plan):
    return {
        "target": plan.target.model_dump(mode="json"),
        "split": plan.split.model_dump(mode="json"),
        "features": [feature.model_dump(mode="json") for feature in plan.features],
        "metric_definitions": plan.evaluation.model_dump(mode="json"),
    }


def plan_sha256(plan):
    data = json.dumps(
        plan.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()
    return "sha256:" + hashlib.sha256(data).hexdigest()
