"""Versioned aggregate regression evidence. Never unpickle models to validate results."""

import math
from typing import Annotated, Literal

from pydantic import Field, JsonValue

from mlstudio.codegen.schemas import PlanModel, SourceContract
from mlstudio.codegen.v2.schemas import (
    ModelImplementation,
    RegressionPlan,
    evaluation_context,
    plan_sha256,
)
from mlstudio.execution.artifacts import bounded_read, canonical, strict_json
from mlstudio.execution.results import ExecutionFailure
from mlstudio.pipeline_schemas import DatasetBinding

Loss = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0)]
Count = Annotated[int, Field(strict=True, gt=0)]
Hash = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class RegressionMetrics(PlanModel):
    mae: Loss
    mse: Loss
    rmse: Loss
    r2: Annotated[float, Field(strict=True, allow_inf_nan=False, le=1)] | None


class Population(PlanModel):
    source: Count
    eligible: Count
    training: Annotated[int, Field(strict=True, ge=2)]
    test: Count


class ModelArtifact(PlanModel):
    kind: Literal["complete_pipeline"]
    filename: Literal["model.joblib"]


class Artifacts(PlanModel):
    model: ModelArtifact


class RegressionResult(PlanModel):
    schema_version: Literal["mlstudio-result-v2"]
    task: Literal["regression"]
    status: Literal["success"]
    dataset: DatasetBinding
    source: SourceContract
    generator: Literal["mlstudio-python-v2"]
    implementation_version: Literal["sklearn-local-v2"]
    plan_sha256: Hash
    source_sha256: Hash
    model: ModelImplementation
    evaluation: dict[str, JsonValue]
    metrics: RegressionMetrics
    r2_unavailable_reason: Literal["test_population_too_small", "constant_test_target"] | None
    test_target_constant: Annotated[bool, Field(strict=True)]
    population: Population
    artifacts: Artifacts
    versions: dict[str, str]


def validate_result(path, limit, plan, population, *, expected_source_sha256):
    try:
        result = strict_json(bounded_read(path, limit))
    except FileNotFoundError:
        raise ExecutionFailure("result_missing", "result") from None
    except (ValueError, OSError, RecursionError):
        raise ExecutionFailure("result_invalid", "result") from None
    try:
        plan = RegressionPlan.model_validate(plan)
        parsed = RegressionResult.model_validate(result)
        expected = {
            "dataset": plan.dataset.model_dump(mode="json"),
            "source": plan.source.model_dump(mode="json"),
            "generator": plan.generator,
            "implementation_version": plan.implementation.version,
            "plan_sha256": plan_sha256(plan),
            "source_sha256": expected_source_sha256,
            "model": plan.model.model_dump(mode="json"),
            "evaluation": evaluation_context(plan),
            "versions": {"python": plan.implementation.python, **plan.implementation.libraries},
        }
        # Compare raw JSON, not coerced models: bool/int/string context must stay exact.
        if any(canonical(result[key]) != canonical(value) for key, value in expected.items()):
            raise ValueError()
        if (
            set(population) != {"source", "eligible"}
            or any(type(v) is not int or v <= 0 for v in population.values())
            or population["eligible"] > population["source"]
        ):
            raise ValueError()
        test = math.ceil(population["eligible"] * plan.split.test_size)
        expected_population = {
            **population,
            "test": test,
            "training": population["eligible"] - test,
        }
        if result["population"] != expected_population:
            raise ValueError()
        if not math.isclose(
            parsed.metrics.rmse, math.sqrt(parsed.metrics.mse), rel_tol=1e-9, abs_tol=1e-12
        ):
            raise ValueError()
        if test < 2:
            expected_reason = "test_population_too_small"
            if not parsed.test_target_constant:
                raise ValueError()
        elif parsed.test_target_constant:
            expected_reason = "constant_test_target"
        else:
            expected_reason = None
        if parsed.r2_unavailable_reason != expected_reason:
            raise ValueError()
        if (parsed.metrics.r2 is None) != (expected_reason is not None):
            raise ValueError()
        return result
    except (ValueError, KeyError, TypeError, OverflowError, RecursionError):
        raise ExecutionFailure("result_invalid", "result") from None
