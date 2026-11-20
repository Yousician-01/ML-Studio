"""Resolve regression intent using existing preparation grammar, without execution."""

from mlstudio.codegen.compatibility import library_versions, python_version
from mlstudio.codegen.schemas import SourceContract
from mlstudio.codegen.v2.schemas import (
    Implementation,
    NumericTarget,
    RegressionPlan,
    RegressionSplit,
)
from mlstudio.lineage import contract_intent
from mlstudio.model_catalog import descriptor_for
from mlstudio.pipeline_schemas import RegressionPipelineIR
from mlstudio.services.cleaning import resolved as resolved_cleaning
from mlstudio.services.derived import resolved as resolved_derived
from mlstudio.services.feature_engineering import resolved as resolved_engineering
from mlstudio.services.imputation import resolved as resolved_imputation
from mlstudio.services.outliers import resolved as resolved_outliers
from mlstudio.services.pipelines import validate
from mlstudio.services.temporal import features as temporal_features
from mlstudio.services.temporal import resolved as resolved_temporal


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
        schema_contract=contract_intent(ir, dataset),
        source=SourceContract(size_bytes=dataset.size_bytes),
        target=NumericTarget(
            column=ir.target.column,
            physical_dtype=str(frame[ir.target.column].dtype),
            semantic_type=target["semantic_override"] or target["inferred_semantic_type"],
        ),
        temporal=resolved_temporal(ir, dataset, frame),
        derived=resolved_derived(ir, dataset, frame),
        imputation=resolved_imputation(ir, dataset, frame),
        cleaning=resolved_cleaning(ir, dataset, frame),
        feature_engineering=resolved_engineering(ir, dataset, frame),
        outlier_treatment=resolved_outliers(ir, dataset, frame),
        feature_selection=ir.feature_selection,
        features=temporal_features(ir, dataset, frame),
        split=RegressionSplit(**ir.split.model_dump()),
        model=model,
        implementation=Implementation(python=python_version(), libraries=library_versions()),
    ), issues
