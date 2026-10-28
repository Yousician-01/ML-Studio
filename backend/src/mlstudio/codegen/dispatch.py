"""Explicit internal compiler dispatch. Public regression admission is separate."""

from mlstudio.codegen import plan as binary_plan
from mlstudio.codegen.render import generate as binary_generate
from mlstudio.codegen.schemas import EffectiveExecutionPlan
from mlstudio.codegen.v2 import plan as regression_plan
from mlstudio.codegen.v2.schemas import RegressionPlan
from mlstudio.pipeline_schemas import PipelineIR, RegressionPipelineIR


def load_plan(payload):
    if not isinstance(payload, dict):
        raise ValueError("Expected a versioned execution plan.")
    if payload.get("plan_version") == "0.1":
        return EffectiveExecutionPlan.model_validate(payload)
    if payload.get("plan_version") == "0.2":
        return RegressionPlan.model_validate(payload)
    if payload.get("plan_version") == "0.3":
        from mlstudio.codegen.multiclass import MulticlassPlan

        return MulticlassPlan.model_validate(payload)
    raise ValueError("Unsupported execution plan version.")


def resolve_for_version(ir, dataset, selected_target, frame):
    if ir.ir_version == "0.3":
        from mlstudio.codegen.multiclass import resolve

        return resolve(ir, dataset, selected_target, frame)
    if isinstance(ir, PipelineIR):
        return binary_plan.resolve(ir, dataset, selected_target, frame)
    if isinstance(ir, RegressionPipelineIR):
        return regression_plan.resolve(ir, dataset, selected_target, frame)
    raise ValueError("Unsupported Pipeline IR version/task.")


def generate_for_version(plan):
    payload = plan if isinstance(plan, dict) else plan.model_dump(mode="json")
    resolved = load_plan(payload)
    if isinstance(resolved, EffectiveExecutionPlan):
        return binary_generate(resolved)
    from mlstudio.codegen.v2.render import generate

    return generate(resolved)
