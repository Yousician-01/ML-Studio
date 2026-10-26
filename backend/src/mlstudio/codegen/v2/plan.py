"""Resolve regression intent using existing preparation grammar, without execution."""

from mlstudio.codegen.compatibility import library_versions, python_version
from mlstudio.codegen.plan import operation
from mlstudio.codegen.schemas import FeaturePlan, SourceContract
from mlstudio.codegen.v2.schemas import (
    Implementation,
    NumericTarget,
    RegressionPlan,
    RegressionSplit,
)
from mlstudio.model_catalog import descriptor_for
from mlstudio.pipeline_schemas import RegressionPipelineIR
from mlstudio.services.pipelines import validate


def resolve(ir, dataset, selected_target, frame):
    ir = RegressionPipelineIR.model_validate(ir.model_dump(mode="json"))
    issues, _, _, _ = validate(ir, dataset, selected_target, frame)
    issues = [issue for issue in issues if issue.code != "regression_execution_unavailable"]
    if any(issue.severity == "blocking" for issue in issues):
        return None, issues
    columns = sorted(dataset.columns, key=lambda column: column["source_order"])
    target = next(c for c in columns if c["name"] == ir.target.column)
    model = {
        "type": ir.model.type,
        "adapter": descriptor_for(ir.model, "regression").compiler_adapter,
        "parameters": ir.model.parameters.model_dump(mode="json"),
    }
    return RegressionPlan(
        dataset=ir.dataset,
        source=SourceContract(size_bytes=dataset.size_bytes),
        target=NumericTarget(
            column=ir.target.column,
            physical_dtype=str(frame[ir.target.column].dtype),
            semantic_type=target["semantic_override"] or target["inferred_semantic_type"],
        ),
        features=tuple(
            FeaturePlan(
                name=c["name"],
                physical_dtype=str(frame[c["name"]].dtype),
                semantic_type=c["semantic_override"] or c["inferred_semantic_type"],
                operations=tuple(operation(op) for op in ir.features[c["name"]].operations),
            )
            for c in columns
            if c["name"] in ir.features and ir.features[c["name"]].included
        ),
        split=RegressionSplit(**ir.split.model_dump()),
        model=model,
        implementation=Implementation(python=python_version(), libraries=library_versions()),
    ), issues
