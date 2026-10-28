"""Internal strict result dispatch from the frozen expected protocol, not current task."""

from pydantic import ValidationError

from mlstudio.codegen.schemas import EffectiveExecutionPlan
from mlstudio.execution import regression_results, results
from mlstudio.execution.artifacts import bounded_read, strict_json
from mlstudio.execution.results import ExecutionFailure


def validate_result_for_version(path, limit, plan, population, *, expected_source_sha256=None):
    if not isinstance(plan, dict):
        raise ExecutionFailure("result_invalid", "result")
    version = plan.get("plan_version")
    runtime = plan.get("runtime")
    if not isinstance(runtime, dict):
        raise ExecutionFailure("result_invalid", "result")
    protocol = runtime.get("result_schema")
    if version == "0.3" and protocol == "mlstudio-result-v3":
        from mlstudio.execution.multiclass_results import validate_result

        return validate_result(path, limit, plan, population)
    if version == "0.1" and protocol == "mlstudio-result-v1":
        try:
            EffectiveExecutionPlan.model_validate(plan)
        except ValidationError as exc:
            raise ExecutionFailure("result_invalid", "result") from exc
        return results.validate_result(path, limit, plan, population)
    if version == "0.2" and protocol == "mlstudio-result-v2" and expected_source_sha256:
        return regression_results.validate_result(
            path, limit, plan, population, expected_source_sha256=expected_source_sha256
        )
    raise ExecutionFailure("result_invalid", "result")


def failure_stage_for_version(path, limit, plan):
    """Read only fixed structural stages, never child exception messages."""
    if plan.get("plan_version") in ("0.1", "0.3"):
        if plan.get("plan_version") == "0.3":
            try:
                result = strict_json(bounded_read(path, limit))
                if (
                    isinstance(result, dict)
                    and result.get("schema_version") == "mlstudio-result-v3"
                    and result.get("status") == "failed"
                    and result.get("stage")
                    in {
                        "runtime_inputs",
                        "data_loading",
                        "target",
                        "split",
                        "training_partition_validation",
                        "preprocessing",
                        "training",
                        "evaluation",
                        "artifact_output",
                    }
                ):
                    return result["stage"]
            except (OSError, ValueError, TypeError, RecursionError):
                pass
            return "execution"
        return results.failure_stage(path, limit)
    try:
        result = strict_json(bounded_read(path, limit))
        if (
            plan.get("plan_version") == "0.2"
            and plan.get("runtime", {}).get("result_schema") == "mlstudio-result-v2"
            and isinstance(result, dict)
            and set(result) == {"schema_version", "task", "status", "stage", "message"}
            and result["schema_version"] == "mlstudio-result-v2"
            and result["task"] == "regression"
            and result["status"] == "failed"
            and result["stage"]
            in {
                "runtime_inputs",
                "data_loading",
                "target",
                "split",
                "preprocessing",
                "training_partition_validation",
                "training",
                "evaluation",
                "artifact_output",
            }
        ):
            return result["stage"]
    except (OSError, ValueError, TypeError, RecursionError):
        pass
    return "execution"
