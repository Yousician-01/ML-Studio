"""Validate aggregate multiclass evidence against the frozen plan; never unpickle."""

import math

from mlstudio.code_runtime import validate_multiclass_evaluation
from mlstudio.codegen.multiclass import MulticlassPlan
from mlstudio.execution.artifacts import bounded_read, canonical, strict_json
from mlstudio.execution.results import ExecutionFailure, fields


def validate_result(path, limit, plan, population):
    try:
        result = strict_json(bounded_read(path, limit))
        resolved = MulticlassPlan.model_validate(plan)
        fields(
            result,
            "schema_version task status dataset generator metrics confusion_matrix "
            "per_class population artifacts versions",
        )
        if (
            result["schema_version"] != "mlstudio-result-v3"
            or result["status"] != "success"
            or result["task"] != "multiclass_classification"
            or canonical(result["dataset"]) != canonical(plan["dataset"])
            or result["generator"] != resolved.generator
            or result["versions"]
            != {"python": resolved.implementation.python, **resolved.implementation.libraries}
            or canonical(result["confusion_matrix"]["labels"])
            != canonical(plan["target"]["classes"])
        ):
            raise ValueError()
        fields(result["population"], "source eligible training test")
        test = math.ceil(population["source"] * resolved.split.test_size)
        counts = {**population, "test": test, "training": population["source"] - test}
        if (
            any(type(v) is not int or v <= 0 for v in result["population"].values())
            or population["source"] != population["eligible"]
            or result["population"] != counts
            or min(test, counts["training"]) < len(resolved.target.classes)
        ):
            raise ValueError()
        evaluation = {
            key: result[key] for key in ("task", "metrics", "confusion_matrix", "per_class")
        }
        validate_multiclass_evaluation({**evaluation, "population": {"test": test}})
        if any(row["support"] == 0 for row in result["per_class"]):
            raise ValueError()
        if result["artifacts"] != {
            "model": {"kind": "complete_pipeline", "filename": "model.joblib"}
        }:
            raise ValueError()
        return result
    except FileNotFoundError:
        raise ExecutionFailure("result_missing", "result") from None
    except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError):
        raise ExecutionFailure("result_invalid", "result") from None
