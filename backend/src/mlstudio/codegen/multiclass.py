"""Explicit multiclass contracts; reuse binary feature/model resolution and renderer."""

from typing import Literal

from pydantic import Field

from mlstudio.codegen.compatibility import library_versions, python_version
from mlstudio.codegen.plan import classifier
from mlstudio.codegen.schemas import EffectiveExecutionPlan, PlanModel, SourceContract
from mlstudio.pipeline_schemas import TypedScalar
from mlstudio.services.cleaning import resolved as resolved_cleaning
from mlstudio.services.derived import resolved as resolved_derived
from mlstudio.services.feature_engineering import resolved as resolved_engineering
from mlstudio.services.imputation import resolved as resolved_imputation
from mlstudio.services.temporal import features as temporal_features
from mlstudio.services.temporal import resolved as resolved_temporal


class MulticlassTarget(PlanModel):
    column: str
    physical_dtype: str
    semantic_type: str
    classes: tuple[TypedScalar, ...] = Field(min_length=3, max_length=50)
    missing_value_policy: Literal["reject"] = "reject"


class MulticlassRuntime(PlanModel):
    version: Literal["cli-v1"] = "cli-v1"
    arguments: tuple[str, ...] = ("--dataset", "--result", "--model")
    result_schema: Literal["mlstudio-result-v3"] = "mlstudio-result-v3"
    model_format: Literal["joblib-complete-pipeline"] = "joblib-complete-pipeline"


class MulticlassEvaluation(PlanModel):
    metrics: tuple[str, ...] = (
        "accuracy",
        "precision_macro",
        "recall_macro",
        "f1_macro",
        "precision_weighted",
        "recall_weighted",
        "f1_weighted",
    )
    zero_division: Literal[0] = 0
    confusion_order: Literal["sorted-typed-classes"] = "sorted-typed-classes"
    definitions: Literal["sklearn-multiclass-v1"] = "sklearn-multiclass-v1"
    roc_auc: Literal["unsupported"] = "unsupported"


class MulticlassPlan(EffectiveExecutionPlan):
    plan_version: Literal["0.3"] = "0.3"
    ir_version: Literal["0.3"] = "0.3"
    task: Literal["multiclass_classification"] = "multiclass_classification"
    generator: Literal["mlstudio-python-v3"] = "mlstudio-python-v3"
    target: MulticlassTarget
    runtime: MulticlassRuntime = Field(default_factory=MulticlassRuntime)
    evaluation: MulticlassEvaluation = Field(default_factory=MulticlassEvaluation)


def resolve(ir, dataset, selected_target, frame):
    from mlstudio.services.pipelines import validate

    issues, classes, _, _ = validate(ir, dataset, selected_target, frame)
    if any(issue.severity == "blocking" for issue in issues):
        return None, issues
    columns = sorted(dataset.columns, key=lambda c: c["source_order"])
    target = next(c for c in columns if c["name"] == ir.target.column)
    return MulticlassPlan(
        dataset=ir.dataset,
        source=SourceContract(size_bytes=dataset.size_bytes),
        target=MulticlassTarget(
            column=ir.target.column,
            physical_dtype=str(frame[ir.target.column].dtype),
            semantic_type=target["semantic_override"] or target["inferred_semantic_type"],
            classes=tuple(classes),
        ),
        temporal=resolved_temporal(ir, dataset, frame),
        derived=resolved_derived(ir, dataset, frame),
        imputation=resolved_imputation(ir, dataset, frame),
        cleaning=resolved_cleaning(ir, dataset, frame),
        feature_engineering=resolved_engineering(ir, dataset, frame),
        features=temporal_features(ir, dataset, frame),
        split=ir.split.model_dump(),
        model=classifier(ir),
        implementation={"python": python_version(), "libraries": library_versions()},
    ), issues
