"""Working intent validation and revision-guarded persistence, never execution."""

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype
from sqlalchemy import select

from mlstudio.models import Dataset, Project, utc_now
from mlstudio.pipeline_schemas import PipelineIR, PipelineIssue, PipelineResponse, TypedScalar
from mlstudio.services.artifacts import verified_source
from mlstudio.services.pipeline_state import column_role, initialize
from mlstudio.services.source import DomainError, json_scalar, parse_source


def typed_scalar(value) -> TypedScalar:
    value = json_scalar(value)
    if isinstance(value, dict):
        return TypedScalar(**value)
    kind = {str: "string", int: "integer", float: "float", bool: "boolean"}[type(value)]
    return TypedScalar(value_type=kind, value=value)


def validate(ir: PipelineIR, dataset, selected_target, frame):
    issues = []

    def issue(code, message, scope="pipeline", column=None, dormant=False):
        issues.append(
            PipelineIssue(
                code=code,
                message=message,
                scope=scope,
                column=column,
                severity="non_blocking" if dormant else "blocking",
            )
        )

    issue("model_missing", "Model configuration belongs to the upcoming Train bench.", "train")
    issue("split_missing", "Split configuration belongs to the upcoming Train bench.", "train")
    if dataset is None:
        issue("dataset_missing", "Upload a Dataset in Data.")
        return issues, [], 0, False
    stale = ir.dataset is not None and (
        ir.dataset.dataset_id != dataset.id or ir.dataset.fingerprint != dataset.fingerprint
    )
    if stale:
        issue(
            "dataset_stale", "Dataset changed. Explicitly reset preparation for the current source."
        )
        return issues, [], 0, True
    if ir.dataset is None:
        issue("dataset_missing", "Initialize preparation for the current Dataset.")
    columns = {c["name"]: c for c in dataset.columns}
    classes, missing = [], 0
    if ir.target is None:
        issue("target_missing", "Select a binary target in Data.", "target")
    else:
        name = ir.target.column
        if name != selected_target:
            issue(
                "target_context",
                "Target differs from Data. Restore the selected target context.",
                "target",
            )
        if name not in columns:
            issue("target_missing_column", "The configured target column is absent.", "target")
        else:
            series = frame[name]
            missing = int(series.isna().sum())
            if series.nunique() != 2:
                issue(
                    "target_not_binary",
                    "Target must contain exactly two non-missing classes.",
                    "target",
                )
            else:
                classes = [typed_scalar(v) for v in series.dropna().unique()]
            if ir.target.positive_class is None:
                issue("positive_class_missing", "Choose the positive class explicitly.", "target")
            elif ir.target.positive_class not in classes:
                issue(
                    "positive_class_invalid",
                    "Positive class must match an observed class and its type.",
                    "target",
                )
    target = ir.target.column if ir.target else None
    for name in columns:
        if name != target and name not in ir.features:
            issue(
                "feature_missing",
                "Column is missing from the feature map. Reset or restore its configuration.",
                "feature",
                name,
            )
    if not any(
        f.included and name in columns and name != target for name, f in ir.features.items()
    ):
        issue("features_empty", "Include at least one usable feature.")
    for name, feature in ir.features.items():
        if name not in columns:
            issue(
                "feature_absent",
                "Configured column does not exist in this Dataset.",
                "feature",
                name,
            )
            continue
        if name == target or name == selected_target:
            issue(
                "target_feature", "The target must be absent from the feature map.", "feature", name
            )
        semantic = columns[name]["semantic_override"] or columns[name]["inferred_semantic_type"]
        numeric = is_numeric_dtype(frame[name].dtype) and not is_bool_dtype(frame[name].dtype)
        dormant = not feature.included

        def feature_issue(code, message, name=name, dormant=dormant):
            issue(code, message, "feature", name, dormant)

        if semantic not in {"continuous", "categorical", "binary"}:
            if feature.included:
                feature_issue(
                    "unsupported_semantic",
                    "Unsupported v0.1 feature type. Exclude it or review its meaning in Data.",
                )
            elif feature.operations:
                feature_issue(
                    "dormant_unsupported",
                    "Incompatible operations are retained but dormant.",
                )
        if semantic == "continuous" and not numeric:
            if feature.included or feature.operations:
                feature_issue(
                    "physical_mismatch",
                    "Continuous preparation requires numeric source values.",
                )
        families = [op.type for op in feature.operations]
        if len(families) != len(set(families)):
            feature_issue("duplicate_operation", "Each operation family may occur at most once.")
        if "impute" in families and families[0] != "impute":
            feature_issue("operation_order", "Imputation must precede scaling or encoding.")
        if "scale" in families and "encode" in families:
            feature_issue(
                "operation_combination", "Scaling and encoding cannot share one feature sequence."
            )
        for op in feature.operations:
            compatible = (
                (
                    op.type == "impute"
                    and (
                        semantic == "continuous"
                        and numeric
                        or semantic in {"categorical", "binary"}
                        and op.strategy == "most_frequent"
                    )
                )
                or (op.type == "scale" and semantic == "continuous" and numeric)
                or (op.type == "encode" and semantic in {"categorical", "binary"})
            )
            if not compatible:
                feature_issue(
                    "operation_incompatible",
                    f"{op.type.capitalize()} is incompatible with this semantic/physical type.",
                )
    return issues, classes, missing, stale


def snapshot(session, project_id):
    return session.execute(
        select(Project, Dataset)
        .outerjoin(Dataset, Dataset.id == Project.active_dataset_id)
        .where(Project.id == project_id)
        .execution_options(populate_existing=True)
    ).one()


def response(project, dataset, settings):
    frame = parse_source(verified_source(settings.home, dataset)) if dataset else pd.DataFrame()
    ir = PipelineIR.model_validate(project.working_pipeline)
    issues, classes, missing, stale = validate(ir, dataset, project.target_column, frame)
    columns = (
        [
            {
                **c,
                "effective_semantic_type": c["semantic_override"] or c["inferred_semantic_type"],
                "role": column_role(project, dataset, c["name"]),
            }
            for c in dataset.columns
        ]
        if dataset
        else []
    )
    return PipelineResponse(
        revision=project.revision,
        ir=ir,
        columns=columns,
        target_classes=classes,
        target_missing_count=missing,
        issues=issues,
        prepare_valid=not any(i.severity == "blocking" and i.scope != "train" for i in issues),
        stale=stale,
    )


def read(session, project, settings):
    project, dataset = snapshot(session, project.id)
    return response(project, dataset, settings)


def save(session, project, body, settings, reset=False):
    project, dataset = snapshot(session, project.id)
    if body.revision != project.revision:
        raise DomainError("Project changed. Reload Prepare before saving again.", 409)
    if reset:
        if dataset is None or body.dataset_id != dataset.id:
            raise DomainError("Dataset changed. Reload before resetting preparation.", 409)
        project.working_pipeline = initialize(dataset, project.target_column)
    else:
        # Binding changes are deliberate reset operations, never generic edit side effects.
        if body.ir.dataset != PipelineIR.model_validate(project.working_pipeline).dataset:
            raise DomainError("Use explicit reset to change the Dataset binding.", 409)
        project.working_pipeline = body.ir.model_dump(mode="json")
    project.updated_at = utc_now()
    session.flush()  # Existing ORM version guard also catches concurrent DB transactions.
    result = response(project, dataset, settings)
    session.commit()
    return result
